"""
xsec_token 管理 - 获取与缓存（有效期 5 分钟）

获取策略：
  1. 通过 Playwright 访问帖子详情页（最可靠）
  2. 缓存命中且未过期则直接复用
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Dict, Optional

from src.utils.logger import logger

# token 有效期（秒），留 30s 裕量
_TOKEN_TTL = 270


class XsecTokenManager:
    """
    内存级 xsec_token 缓存，key = (note_id, account_id)
    """

    def __init__(self):
        # {cache_key: {"token": str, "expires_at": float}}
        self._cache: Dict[str, Dict] = {}

    def get_token(
        self,
        note_id: str,
        note_url: str,
        account_id: str,
        cookie: str,
    ) -> Optional[str]:
        """
        返回有效的 xsec_token，优先使用缓存。
        缓存缺失或过期时，通过 Playwright 刷新。
        """
        cache_key = f"{note_id}:{account_id}"
        cached = self._cache.get(cache_key)
        if cached and time.time() < cached["expires_at"]:
            logger.debug(f"xsec_token 命中缓存: {cache_key}")
            return cached["token"]

        token = self._fetch_from_page(note_url, cookie)
        if token:
            self._cache[cache_key] = {
                "token": token,
                "expires_at": time.time() + _TOKEN_TTL,
            }
        return token

    def invalidate(self, note_id: str, account_id: str) -> None:
        cache_key = f"{note_id}:{account_id}"
        self._cache.pop(cache_key, None)
        logger.debug(f"xsec_token 缓存已失效: {cache_key}")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_from_page(note_url: str, cookie: str) -> Optional[str]:
        """从帖子页面获取 xsec_token"""
        # 延迟导入避免循环依赖
        from src.account.login import get_xsec_token_from_page

        token = get_xsec_token_from_page(note_url, cookie)
        return token

    @staticmethod
    def extract_note_id_from_url(url: str) -> Optional[str]:
        """从小红书帖子 URL 中提取 note_id"""
        # 格式 1: https://www.xiaohongshu.com/explore/{note_id}
        # 格式 2: https://www.xiaohongshu.com/discovery/item/{note_id}
        parsed = urllib.parse.urlparse(url)
        segments = [s for s in parsed.path.split("/") if s]
        if segments:
            return segments[-1]
        return None
