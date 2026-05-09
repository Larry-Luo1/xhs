"""
评论采集核心 - 实现方案B（JS注入+签名调用）

流程：
  1. 从账号池取账号 + 对应代理
  2. 获取/刷新 xsec_token
  3. 生成签名（x-s / x-t）
  4. requests 调用评论 API
  5. 解析评论用户 ID 并去重入库
  6. 翻页直至拉完所有评论
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Set

import requests

from config.config import (
    COMMENTS_PER_PAGE,
    MAX_PAGES,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRY_DELAY,
)
from src.account.account_pool import AccountPool
from src.crawler.sign_service import SignService
from src.crawler.xsec_token_manager import XsecTokenManager
from src.proxy.proxy_pool import ProxyPool
from src.utils.db import CommentUser, Task, get_session
from src.utils.logger import logger
from src.utils.throttle import ThrottleManager

# 评论分页接口
_COMMENT_API = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
_API_PATH = "/api/sns/web/v2/comment/page"

# 固定请求头（非签名部分）
_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Origin": "https://www.xiaohongshu.com",
    "Referer": "https://www.xiaohongshu.com/",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class XhsCrawler:
    """小红书评论采集器（方案B）"""

    def __init__(self):
        self.account_pool = AccountPool()
        self.proxy_pool = ProxyPool()
        self.sign_service = SignService()
        self.token_manager = XsecTokenManager()
        self.throttle = ThrottleManager()

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def fetch_comment_user_ids(self, note_url: str) -> List[str]:
        """
        采集指定帖子下所有评论的用户 ID 列表（去重）。

        :param note_url: 帖子完整 URL
        :return: user_id 列表
        """
        note_id = XsecTokenManager.extract_note_id_from_url(note_url)
        if not note_id:
            logger.error(f"无法从 URL 解析 note_id: {note_url}")
            return []

        logger.info(f"开始采集帖子 {note_id} 的评论用户")
        task = self._get_or_create_task(note_id, note_url)

        account = self.account_pool.get_active_account()
        if not account:
            logger.error("没有可用账号，终止采集")
            self._update_task_status(note_id, "failed", "no available account")
            return []

        account_id = account["account_id"]
        cookie = account["cookie"]

        # 确保账号有绑定代理
        self.proxy_pool.bind_proxy_to_account(account_id)
        proxies = self.proxy_pool.build_requests_proxies(account_id)

        # 获取 xsec_token
        xsec_token = self.token_manager.get_token(note_id, note_url, account_id, cookie)
        if not xsec_token:
            logger.warning(f"无法获取 xsec_token，将尝试不带 token 请求（可能失败）")

        self._update_task_status(note_id, "running")

        user_ids: Set[str] = set()
        try:
            user_ids = self._crawl_all_pages(
                note_id=note_id,
                account_id=account_id,
                cookie=cookie,
                xsec_token=xsec_token or "",
                proxies=proxies,
            )
        except Exception as e:
            logger.error(f"采集帖子 {note_id} 出错: {e}")
            self._update_task_status(note_id, "failed", str(e))
            return list(user_ids)

        # 入库去重
        self._save_comment_users(note_id, list(user_ids))
        self._update_task_status(note_id, "done", total=len(user_ids))
        logger.success(f"帖子 {note_id} 采集完成，共 {len(user_ids)} 个唯一评论用户")
        return list(user_ids)

    # ------------------------------------------------------------------
    # 分页采集
    # ------------------------------------------------------------------

    def _crawl_all_pages(
        self,
        note_id: str,
        account_id: str,
        cookie: str,
        xsec_token: str,
        proxies: Optional[Dict],
    ) -> Set[str]:
        user_ids: Set[str] = set()
        cursor = ""
        page = 1

        while page <= MAX_PAGES:
            logger.info(f"[{note_id}] 第 {page} 页，cursor={cursor!r}")

            result = self._fetch_page_with_retry(
                note_id=note_id,
                account_id=account_id,
                cookie=cookie,
                xsec_token=xsec_token,
                cursor=cursor,
                proxies=proxies,
            )

            if result is None:
                logger.warning(f"[{note_id}] 第 {page} 页请求失败，停止翻页")
                break

            comments = result.get("comments") or result.get("data", {}).get("comments", [])
            if not comments:
                logger.info(f"[{note_id}] 第 {page} 页无评论，采集结束")
                break

            page_user_ids = self._extract_user_ids(comments)
            user_ids.update(page_user_ids)
            logger.debug(f"[{note_id}] 第 {page} 页获得 {len(page_user_ids)} 个用户，累计 {len(user_ids)}")

            # 检查是否有下一页
            has_more = result.get("has_more", False)
            cursor = result.get("cursor", "")
            if not has_more or not cursor:
                logger.info(f"[{note_id}] 已到最后一页")
                break

            page += 1
            self.throttle.wait_short()

        return user_ids

    def _fetch_page_with_retry(
        self,
        note_id: str,
        account_id: str,
        cookie: str,
        xsec_token: str,
        cursor: str,
        proxies: Optional[Dict],
    ) -> Optional[Dict]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp_data = self._do_request(
                    note_id=note_id,
                    cookie=cookie,
                    xsec_token=xsec_token,
                    cursor=cursor,
                    proxies=proxies,
                )
                if resp_data is None:
                    continue

                code = resp_data.get("code", -1)

                if code == 0:
                    return resp_data.get("data", resp_data)

                if code in (-102, -121):  # need_login / auth_failed
                    logger.warning(f"[{account_id}] Cookie 失效 (code={code})")
                    self.account_pool.mark_invalid(account_id)
                    return None

                if code == 403 or code == -2:  # 签名错误
                    logger.warning(f"[{note_id}] 签名失效 (code={code})，尝试重签")
                    # 签名是无状态的，下次循环会重新生成
                    continue

                if code == -9:  # 频率限制
                    logger.warning(f"[{account_id}] 触发限速 (code={code})")
                    self.account_pool.mark_rate_limited(account_id)
                    self.throttle.wait()
                    continue

                logger.warning(f"[{note_id}] 未知响应码 code={code}，msg={resp_data.get('msg')}")
                return None

            except requests.exceptions.ProxyError:
                logger.error(f"代理错误（attempt {attempt}/{MAX_RETRIES}）")
                if proxies:
                    host = list(proxies.values())[0].split("@")[-1].split(":")[0]
                    self.proxy_pool.mark_invalid(host, 0)
                return None

            except requests.exceptions.Timeout:
                logger.warning(f"请求超时（attempt {attempt}/{MAX_RETRIES}）")
                import time
                time.sleep(RETRY_DELAY)

            except Exception as e:
                logger.error(f"请求异常（attempt {attempt}/{MAX_RETRIES}）: {e}")
                import time
                time.sleep(RETRY_DELAY)

        return None

    def _do_request(
        self,
        note_id: str,
        cookie: str,
        xsec_token: str,
        cursor: str,
        proxies: Optional[Dict],
    ) -> Optional[Dict]:
        payload = {
            "note_id": note_id,
            "cursor": cursor,
            "top_comment_id": "",
            "image_formats": ["jpg", "webp", "avif"],
            "xsec_token": xsec_token,
        }

        sign = self.sign_service.sign(uri=_API_PATH, data=payload, cookie=cookie)

        headers = {
            **_BASE_HEADERS,
            "Cookie": cookie,
            "x-s": sign["x-s"],
            "x-t": sign["x-t"],
        }
        if sign.get("x-s-common"):
            headers["x-s-common"] = sign["x-s-common"]

        resp = requests.post(
            _COMMENT_API,
            json=payload,
            headers=headers,
            proxies=proxies,
            timeout=REQUEST_TIMEOUT,
        )

        logger.debug(f"HTTP {resp.status_code} | note={note_id} | cursor={cursor!r}")

        if resp.status_code in (403, 401):
            return {"code": 403, "msg": f"HTTP {resp.status_code}"}

        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # 数据解析
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_user_ids(comments: List[Dict]) -> Set[str]:
        user_ids: Set[str] = set()
        for comment in comments:
            user_info = comment.get("user_info") or comment.get("user") or {}
            uid = user_info.get("user_id") or user_info.get("userid") or user_info.get("id")
            if uid:
                user_ids.add(str(uid))

            # 二级评论（sub_comments）
            sub = comment.get("sub_comments") or []
            for sub_comment in sub:
                sub_user = sub_comment.get("user_info") or sub_comment.get("user") or {}
                sub_uid = sub_user.get("user_id") or sub_user.get("userid") or sub_user.get("id")
                if sub_uid:
                    user_ids.add(str(sub_uid))

        return user_ids

    # ------------------------------------------------------------------
    # 数据库辅助
    # ------------------------------------------------------------------

    def _save_comment_users(self, note_id: str, user_ids: List[str]) -> None:
        with get_session() as session:
            for uid in user_ids:
                existing = (
                    session.query(CommentUser)
                    .filter(CommentUser.note_id == note_id, CommentUser.user_id == uid)
                    .first()
                )
                if existing:
                    existing.comment_count += 1
                else:
                    session.add(CommentUser(note_id=note_id, user_id=uid))
            session.commit()

    def _get_or_create_task(self, note_id: str, note_url: str) -> Task:
        with get_session() as session:
            task = session.query(Task).filter(Task.note_id == note_id).first()
            if not task:
                task = Task(note_id=note_id, note_url=note_url, status="pending")
                session.add(task)
                session.commit()
        return task

    def _update_task_status(
        self,
        note_id: str,
        status: str,
        error_msg: str = "",
        total: int = 0,
    ) -> None:
        with get_session() as session:
            task = session.query(Task).filter(Task.note_id == note_id).first()
            if task:
                task.status = status
                if error_msg:
                    task.error_msg = error_msg
                if total:
                    task.total_comments = total
                session.commit()
