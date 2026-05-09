"""Playwright 自动登录 - 获取完整 Cookie"""
from __future__ import annotations

import json
from typing import Optional

from playwright.sync_api import sync_playwright, Browser, BrowserContext

from config.config import HEADLESS_MODE
from src.utils.logger import logger

XHS_HOME = "https://www.xiaohongshu.com"
XHS_LOGIN = "https://www.xiaohongshu.com/explore"


def login_and_get_cookie(account_id: str, timeout: int = 120) -> Optional[str]:
    """
    启动 Playwright 打开小红书登录页，等待用户手动扫码/登录（非 headless 模式）。
    登录成功后提取完整 Cookie 字符串并返回。

    :param account_id: 账号标识（仅用于日志）
    :param timeout:    最长等待登录完成的秒数
    :return: cookie 字符串，失败返回 None
    """
    logger.info(f"[{account_id}] 启动 Playwright 进行登录...")

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(
            headless=False,  # 必须显示，用户手动扫码
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context: BrowserContext = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()

        # 隐藏 webdriver 特征
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page.goto(XHS_LOGIN, timeout=30_000)
        logger.info(f"[{account_id}] 请在浏览器中完成登录（最多等待 {timeout}s）...")

        # 等待登录成功（检测登录后才有的用户头像元素）
        try:
            page.wait_for_selector("div.user-avatar", timeout=timeout * 1_000)
        except Exception:
            # 也可检测 cookie 中是否包含 xhsTrackerId
            cookies = context.cookies()
            has_auth = any(c["name"] in ("xhsTrackerId", "web_session") for c in cookies)
            if not has_auth:
                logger.error(f"[{account_id}] 登录超时或失败")
                browser.close()
                return None

        cookies = context.cookies()
        browser.close()

    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    logger.success(f"[{account_id}] 登录成功，Cookie 长度: {len(cookie_str)}")
    return cookie_str


def get_xsec_token_from_page(note_url: str, cookie: str) -> Optional[str]:
    """
    通过 Playwright 访问帖子详情页，从页面源码中提取 xsec_token。
    """
    logger.debug(f"正在从页面获取 xsec_token: {note_url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS_MODE,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        # 注入已有 Cookie
        cookie_items = []
        for part in cookie.split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                cookie_items.append({"name": name.strip(), "value": value.strip(), "domain": ".xiaohongshu.com", "path": "/"})
        context.add_cookies(cookie_items)

        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        xsec_token: Optional[str] = None

        def handle_response(response):
            nonlocal xsec_token
            if "xsec_token" in response.url:
                try:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(response.url)
                    params = urllib.parse.parse_qs(parsed.query)
                    token = params.get("xsec_token", [None])[0]
                    if token:
                        xsec_token = token
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            page.goto(note_url, timeout=30_000, wait_until="networkidle")
        except Exception as e:
            logger.warning(f"页面加载超时（可能仍可获取 token）: {e}")

        # 尝试从 URL 参数中获取（某些页面重定向后携带）
        if not xsec_token:
            current_url = page.url
            if "xsec_token" in current_url:
                import urllib.parse
                params = urllib.parse.parse_qs(urllib.parse.urlparse(current_url).query)
                xsec_token = params.get("xsec_token", [None])[0]

        # 尝试从 meta 标签获取
        if not xsec_token:
            try:
                meta = page.query_selector('meta[name="xsec_token"]')
                if meta:
                    xsec_token = meta.get_attribute("content")
            except Exception:
                pass

        browser.close()

    if xsec_token:
        logger.debug(f"xsec_token 获取成功: {xsec_token[:20]}...")
    else:
        logger.warning("未能从页面获取 xsec_token")
    return xsec_token
