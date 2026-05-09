"""代理池管理 - IP轮转与账号绑定"""
from __future__ import annotations

import datetime
import threading
from typing import Dict, List, Optional

import requests

from src.utils.db import Proxy, get_session
from src.utils.logger import logger


class ProxyPool:
    """
    代理池：
    - 每个账号绑定一个固定代理（account_id → proxy）
    - 支持有效性检测
    - 代理失效时从未绑定代理中轮转补充
    """

    CHECK_URL = "https://myip.ipip.net"
    CHECK_TIMEOUT = 10

    def __init__(self):
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def add_proxy(
        self,
        host: str,
        port: int,
        protocol: str = "http",
        username: str = "",
        password: str = "",
    ) -> None:
        """添加代理到池"""
        with get_session() as session:
            exists = (
                session.query(Proxy)
                .filter(Proxy.host == host, Proxy.port == port)
                .first()
            )
            if exists:
                logger.debug(f"代理 {host}:{port} 已存在，跳过")
                return
            proxy = Proxy(
                host=host,
                port=port,
                protocol=protocol,
                username=username or None,
                password=password or None,
            )
            session.add(proxy)
            session.commit()
            logger.info(f"已添加代理: {protocol}://{host}:{port}")

    def bind_proxy_to_account(self, account_id: str) -> Optional[Dict]:
        """为账号分配（或复用）一个有效代理，返回代理 dict"""
        with self._lock:
            with get_session() as session:
                # 已有绑定
                bound = (
                    session.query(Proxy)
                    .filter(Proxy.bound_account_id == account_id, Proxy.is_valid.is_(True))
                    .first()
                )
                if bound:
                    return self._to_dict(bound)

                # 从未绑定的可用代理中取一个
                free = (
                    session.query(Proxy)
                    .filter(Proxy.bound_account_id.is_(None), Proxy.is_valid.is_(True))
                    .first()
                )
                if not free:
                    logger.warning(f"账号 {account_id} 无可用代理可绑定")
                    return None

                free.bound_account_id = account_id
                session.commit()
                logger.info(f"账号 {account_id} 绑定代理 {free.host}:{free.port}")
                return self._to_dict(free)

    def get_proxy_for_account(self, account_id: str) -> Optional[Dict]:
        """查询账号已绑定的代理"""
        with get_session() as session:
            proxy = (
                session.query(Proxy)
                .filter(Proxy.bound_account_id == account_id, Proxy.is_valid.is_(True))
                .first()
            )
            return self._to_dict(proxy) if proxy else None

    def check_proxy(self, proxy_dict: Dict) -> bool:
        """检测代理是否可用"""
        proxies = self._build_requests_proxies(proxy_dict)
        try:
            resp = requests.get(self.CHECK_URL, proxies=proxies, timeout=self.CHECK_TIMEOUT)
            ok = resp.status_code == 200
            if ok:
                logger.debug(f"代理 {proxy_dict['host']}:{proxy_dict['port']} 有效，IP: {resp.text.strip()[:60]}")
            return ok
        except Exception as e:
            logger.warning(f"代理 {proxy_dict['host']}:{proxy_dict['port']} 检测失败: {e}")
            return False

    def mark_invalid(self, host: str, port: int) -> None:
        with get_session() as session:
            proxy = session.query(Proxy).filter(Proxy.host == host, Proxy.port == port).first()
            if proxy:
                proxy.is_valid = False
                proxy.bound_account_id = None
                proxy.last_checked_at = datetime.datetime.now(datetime.timezone.utc)
                session.commit()
                logger.warning(f"代理 {host}:{port} 已标记失效")

    def validate_all(self) -> None:
        """批量检测所有代理可用性"""
        with get_session() as session:
            proxies = session.query(Proxy).all()
            proxy_list = [self._to_dict(p) for p in proxies]

        for p in proxy_list:
            valid = self.check_proxy(p)
            with get_session() as session:
                proxy = session.query(Proxy).filter(Proxy.host == p["host"], Proxy.port == p["port"]).first()
                if proxy:
                    proxy.is_valid = valid
                    proxy.last_checked_at = datetime.datetime.now(datetime.timezone.utc)
                    if not valid:
                        proxy.bound_account_id = None
                    session.commit()

    def build_requests_proxies(self, account_id: str) -> Optional[Dict]:
        """
        返回可直接传入 requests 的 proxies dict。
        如果账号没有绑定代理则返回 None（直连）。
        """
        proxy = self.get_proxy_for_account(account_id)
        if not proxy:
            return None
        return self._build_requests_proxies(proxy)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _build_requests_proxies(proxy_dict: Dict) -> Dict:
        protocol = proxy_dict.get("protocol", "http")
        host = proxy_dict["host"]
        port = proxy_dict["port"]
        username = proxy_dict.get("username")
        password = proxy_dict.get("password")

        if username and password:
            url = f"{protocol}://{username}:{password}@{host}:{port}"
        else:
            url = f"{protocol}://{host}:{port}"

        return {"http": url, "https": url}

    @staticmethod
    def _to_dict(proxy: Proxy) -> Dict:
        return {
            "host": proxy.host,
            "port": proxy.port,
            "protocol": proxy.protocol,
            "username": proxy.username,
            "password": proxy.password,
            "bound_account_id": proxy.bound_account_id,
            "is_valid": proxy.is_valid,
        }
