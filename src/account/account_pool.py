"""账号池管理 - 多账号状态机 + Cookie管理"""
from __future__ import annotations

import datetime
import json
import threading
from typing import Dict, List, Optional

from src.utils.db import Account, get_session
from src.utils.logger import logger


class AccountStatus:
    ACTIVE = "active"
    RATE_LIMITED = "rate_limited"
    BANNED = "banned"
    INVALID = "invalid"


class AccountPool:
    """
    线程安全的账号池，支持：
    - 轮询获取可用账号
    - 状态标记（限速/封禁/失效）
    - Cookie 更新与持久化
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._index = 0  # 轮询指针

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def get_active_account(self) -> Optional[Dict]:
        """获取一个可用账号，返回 dict 或 None"""
        with self._lock:
            with get_session() as session:
                accounts = (
                    session.query(Account)
                    .filter(Account.status == AccountStatus.ACTIVE)
                    .filter(Account.cookie.isnot(None))
                    .all()
                )
                if not accounts:
                    logger.warning("账号池：没有可用的 active 账号")
                    return None

                account = accounts[self._index % len(accounts)]
                self._index += 1
                return self._to_dict(account)

    def get_account_by_id(self, account_id: str) -> Optional[Dict]:
        with get_session() as session:
            account = (
                session.query(Account)
                .filter(Account.account_id == account_id)
                .first()
            )
            return self._to_dict(account) if account else None

    def add_account(self, account_id: str, username: str = "") -> None:
        """添加新账号（尚未登录，无 Cookie）"""
        with get_session() as session:
            existing = session.query(Account).filter(Account.account_id == account_id).first()
            if existing:
                logger.info(f"账号 {account_id} 已存在，跳过添加")
                return
            account = Account(account_id=account_id, username=username, status=AccountStatus.INVALID)
            session.add(account)
            session.commit()
            logger.info(f"已添加账号: {account_id}")

    def update_cookie(self, account_id: str, cookie: str, user_id: str = "") -> None:
        """登录成功后更新 Cookie"""
        with get_session() as session:
            account = session.query(Account).filter(Account.account_id == account_id).first()
            if not account:
                logger.error(f"更新Cookie失败：账号 {account_id} 不存在")
                return
            account.cookie = cookie
            if user_id:
                account.user_id = user_id
            account.status = AccountStatus.ACTIVE
            account.cookie_updated_at = datetime.datetime.now(datetime.timezone.utc)
            session.commit()
            logger.info(f"账号 {account_id} Cookie 已更新")

    def mark_rate_limited(self, account_id: str) -> None:
        self._update_status(account_id, AccountStatus.RATE_LIMITED)
        logger.warning(f"账号 {account_id} 标记为限速")

    def mark_banned(self, account_id: str) -> None:
        self._update_status(account_id, AccountStatus.BANNED)
        logger.error(f"账号 {account_id} 标记为封禁")

    def mark_invalid(self, account_id: str) -> None:
        self._update_status(account_id, AccountStatus.INVALID)
        logger.warning(f"账号 {account_id} Cookie 失效，需重新登录")

    def mark_active(self, account_id: str) -> None:
        self._update_status(account_id, AccountStatus.ACTIVE)

    def validate_cookie(self, account_id: str) -> bool:
        """
        调用 XHS /api/sns/web/v2/user/me 验证 Cookie 是否仍有效。
        有效返回 True，否则标记为 invalid 并返回 False。
        """
        account = self.get_account_by_id(account_id)
        if not account or not account.get("cookie"):
            return False
        import requests as _req
        try:
            r = _req.get(
                "https://edith.xiaohongshu.com/api/sns/web/v2/user/me",
                headers={
                    "Cookie": account["cookie"],
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                    "Referer": "https://www.xiaohongshu.com/",
                },
                timeout=10,
            )
            data = r.json()
            if data.get("code") == 0 and data.get("data"):
                logger.info(f"账号 {account_id} Cookie 有效")
                return True
            else:
                logger.warning(f"账号 {account_id} Cookie 已失效 (code={data.get('code')})")
                self.mark_invalid(account_id)
                return False
        except Exception as e:
            logger.warning(f"账号 {account_id} Cookie 验证异常: {e}")
            return False

    def increment_request_count(self, account_id: str) -> None:
        with get_session() as session:
            account = session.query(Account).filter(Account.account_id == account_id).first()
            if account:
                account.request_count = (account.request_count or 0) + 1
                session.commit()

    def list_accounts(self) -> List[Dict]:
        with get_session() as session:
            accounts = session.query(Account).all()
            return [self._to_dict(a) for a in accounts]

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _update_status(self, account_id: str, status: str) -> None:
        with get_session() as session:
            account = session.query(Account).filter(Account.account_id == account_id).first()
            if account:
                account.status = status
                account.updated_at = datetime.datetime.now(datetime.timezone.utc)
                session.commit()

    @staticmethod
    def _to_dict(account: Account) -> Dict:
        return {
            "account_id": account.account_id,
            "username": account.username,
            "cookie": account.cookie,
            "user_id": account.user_id,
            "status": account.status,
            "request_count": account.request_count,
            "cookie_updated_at": str(account.cookie_updated_at) if account.cookie_updated_at else None,
        }
