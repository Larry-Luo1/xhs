"""
请求签名服务 - 基于 xhshow 纯 Python 签名库

xhshow.Xhshow 是主客户端，sign_headers_post() 一次调用即可返回
包含 x-s、x-t、x-s-common 等所有签名请求头的 dict。

每个账号维护独立的 SessionManager，以保持序列号连续性，
让签名更接近真实浏览器行为。
"""
from __future__ import annotations

import threading
from typing import Dict, Optional

from src.utils.logger import logger

try:
    from xhshow.client import Xhshow
    from xhshow.session import SessionManager
    _XHSHOW_AVAILABLE = True
except ImportError:
    _XHSHOW_AVAILABLE = False
    logger.error("xhshow 未安装，请执行: pip install xhshow")


class SignService:
    """
    封装 xhshow 签名客户端。

    - 每个 SignService 实例共享一个 Xhshow() 客户端（线程安全）
    - 每个账号持有独立的 SessionManager，跨请求维护序列号状态
    """

    def __init__(self):
        if not _XHSHOW_AVAILABLE:
            raise RuntimeError("xhshow 未安装，请执行: pip install xhshow")
        self._client = Xhshow()
        self._sessions: Dict[str, SessionManager] = {}  # account_id -> SessionManager
        self._lock = threading.Lock()
        logger.info("签名后端: xhshow (纯Python)")

    def get_session(self, account_id: str) -> SessionManager:
        """获取或创建账号专属 SessionManager"""
        with self._lock:
            if account_id not in self._sessions:
                self._sessions[account_id] = SessionManager()
                logger.debug(f"[{account_id}] 创建新的签名 SessionManager")
            return self._sessions[account_id]

    def sign_post(self, uri: str, cookie: str, payload: Optional[Dict] = None,
                  account_id: str = "default") -> Dict[str, str]:
        """
        为 POST 请求生成完整签名请求头。
        """
        session = self.get_session(account_id)
        try:
            headers = self._client.sign_headers_post(
                uri=uri,
                cookies=cookie,
                payload=payload,
                session=session,
            )
            logger.debug(f"[{account_id}] 签名成功 uri={uri} x-s={headers.get('x-s', '')[:12]}...")
            return headers
        except Exception as e:
            logger.error(f"[{account_id}] xhshow POST 签名失败: {e}")
            raise

    def sign_get(self, uri: str, cookie: str, params: Optional[Dict] = None,
                 account_id: str = "default") -> Dict[str, str]:
        """
        为 GET 请求生成完整签名请求头。

        :param uri:        请求路径，如 /api/sns/web/v2/comment/page
        :param cookie:     账号 cookie 字符串
        :param params:     GET 查询参数 dict
        :param account_id: 账号标识
        :return: 签名 headers dict
        """
        session = self.get_session(account_id)
        try:
            headers = self._client.sign_headers_get(
                uri=uri,
                cookies=cookie,
                params=params,
                session=session,
            )
            logger.debug(f"[{account_id}] GET 签名成功 uri={uri} x-s={headers.get('x-s', '')[:12]}...")
            return headers
        except Exception as e:
            logger.error(f"[{account_id}] xhshow GET 签名失败: {e}")
            raise

    def invalidate_session(self, account_id: str) -> None:
        """签名失效时重置 SessionManager（清除序列号状态）"""
        with self._lock:
            self._sessions.pop(account_id, None)
        logger.debug(f"[{account_id}] 签名 Session 已重置")
