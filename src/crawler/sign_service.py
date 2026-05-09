"""
请求签名服务 - 生成 x-s / x-t / x-s-common

优先级：
  1. xhshow（纯 Python 签名库，pip install xhshow）
  2. execjs + 本地 JS 签名文件（assets/sign.js）
  3. 占位符（用于开发调试，不会发出有效请求）
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Dict, Optional

from src.utils.logger import logger

# ---------- 尝试加载 xhshow ----------
try:
    import xhshow  # type: ignore
    _XHSHOW_AVAILABLE = True
    logger.info("签名后端: xhshow (纯Python)")
except ImportError:
    _XHSHOW_AVAILABLE = False

# ---------- 尝试加载 execjs ----------
try:
    import execjs  # type: ignore
    _EXECJS_AVAILABLE = True
except ImportError:
    _EXECJS_AVAILABLE = False

_JS_SIGN_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "sign.js")


class SignService:
    """
    生成小红书请求所需签名参数：
      - x-s
      - x-t
      - x-s-common（部分接口使用）
    """

    def __init__(self):
        self._js_ctx = None
        self._backend = self._detect_backend()

    def _detect_backend(self) -> str:
        if _XHSHOW_AVAILABLE:
            return "xhshow"
        if _EXECJS_AVAILABLE and os.path.exists(_JS_SIGN_FILE):
            try:
                with open(_JS_SIGN_FILE, "r", encoding="utf-8") as f:
                    js_code = f.read()
                self._js_ctx = execjs.compile(js_code)
                logger.info("签名后端: execjs + sign.js")
                return "execjs"
            except Exception as e:
                logger.warning(f"execjs 初始化失败: {e}")
        logger.warning(
            "签名后端: 占位符模式（请安装 xhshow 或提供 assets/sign.js）"
        )
        return "placeholder"

    def sign(self, uri: str, data: Optional[Dict] = None, cookie: str = "") -> Dict[str, str]:
        """
        生成签名，返回需要添加到请求头的字段 dict。

        :param uri:    请求路径，如 /api/sns/web/v2/comment/page
        :param data:   POST body dict（某些签名算法需要）
        :param cookie: 当前账号的 cookie 字符串
        :return: {"x-s": ..., "x-t": ..., "x-s-common": ...}
        """
        if self._backend == "xhshow":
            return self._sign_xhshow(uri, data, cookie)
        if self._backend == "execjs":
            return self._sign_execjs(uri, data, cookie)
        return self._sign_placeholder(uri)

    # ------------------------------------------------------------------
    # 各后端实现
    # ------------------------------------------------------------------

    def _sign_xhshow(self, uri: str, data: Optional[Dict], cookie: str) -> Dict[str, str]:
        try:
            result = xhshow.sign(uri, data=data, cookie=cookie)
            # xhshow 通常返回 dict with x-s, x-t, x-s-common
            return {
                "x-s": result.get("x-s", ""),
                "x-t": result.get("x-t", str(int(time.time() * 1000))),
                "x-s-common": result.get("x-s-common", ""),
            }
        except Exception as e:
            logger.error(f"xhshow 签名失败: {e}")
            return self._sign_placeholder(uri)

    def _sign_execjs(self, uri: str, data: Optional[Dict], cookie: str) -> Dict[str, str]:
        try:
            result = self._js_ctx.call("sign", uri, data or {}, cookie)
            if isinstance(result, dict):
                return {
                    "x-s": result.get("x-s", ""),
                    "x-t": result.get("x-t", str(int(time.time() * 1000))),
                    "x-s-common": result.get("x-s-common", ""),
                }
        except Exception as e:
            logger.error(f"execjs 签名失败: {e}")
        return self._sign_placeholder(uri)

    @staticmethod
    def _sign_placeholder(uri: str) -> Dict[str, str]:
        """占位符签名（仅用于开发调试，不能通过服务端校验）"""
        ts = str(int(time.time() * 1000))
        fake_xs = hashlib.md5(f"{uri}{ts}".encode()).hexdigest()
        return {
            "x-s": fake_xs,
            "x-t": ts,
            "x-s-common": "",
        }
