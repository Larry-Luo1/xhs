"""Playwright 自动登录 - 获取完整 Cookie"""
from __future__ import annotations

import time
from typing import Optional

import requests as _requests
from playwright.sync_api import sync_playwright, Browser, BrowserContext

from config.config import HEADLESS_MODE
from src.utils.logger import logger

XHS_HOME = "https://www.xiaohongshu.com"
XHS_LOGIN = "https://www.xiaohongshu.com/explore"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
)


def _poll_sms_code(sms_url: str, wait_first: int = 15, interval: int = 3, timeout: int = 90) -> Optional[str]:
    """
    轮询宝号 API 获取最新验证码。

    :param sms_url:    https://baohao.vip/api/record?token=xxx
    :param wait_first: 发送验证码后先等待几秒
    :param interval:   轮询间隔秒数
    :param timeout:    最长等待时间
    :return: 6 位验证码字符串，失败返回 None
    """
    logger.info(f"等待 {wait_first}s 后开始轮询验证码...")
    time.sleep(wait_first)

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = _requests.get(sms_url, timeout=10)
            data = r.json()
            code = data.get("data", {}).get("code", "")
            if code and code.strip():
                logger.success(f"获取到验证码: {code}")
                return code.strip()
        except Exception as e:
            logger.warning(f"轮询验证码失败: {e}")
        time.sleep(interval)

    logger.error("验证码获取超时")
    return None


def phone_login(
    phone: str,
    sms_url: str,
    proxy: Optional[dict] = None,
    headless: bool = True,
) -> Optional[str]:
    """
    通过手机验证码自动登录小红书。

    :param phone:   手机号，如 +15416485577
    :param sms_url: 验证码查询 URL
    :param proxy:   代理 dict {"host": ..., "port": ..., "protocol": ...}，可为 None
    :param headless: 是否无头模式（默认 True；如遇滑块可改为 False 手动处理）
    :return: cookie 字符串，失败返回 None
    """
    account_id = phone
    logger.info(f"[{account_id}] 开始手机验证码登录...")

    launch_args = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }
    if proxy:
        proto = proxy.get("protocol", "http")
        host = proxy["host"]
        port = proxy["port"]
        launch_args["proxy"] = {"server": f"{proto}://{host}:{port}"}
        if proxy.get("username"):
            launch_args["proxy"]["username"] = proxy["username"]
            launch_args["proxy"]["password"] = proxy.get("password", "")
        logger.info(f"[{account_id}] 使用代理 {host}:{port}")

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(**launch_args)
        context: BrowserContext = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            page.goto(XHS_LOGIN, timeout=30_000)
        except Exception as e:
            logger.warning(f"[{account_id}] 页面加载警告: {e}")

        # 等待登录框出现，点击「手机号登录」tab
        try:
            # XHS 登录框通常有两个 tab：验证码 / 密码；找手机号输入框
            page.wait_for_selector("input[placeholder*='手机号'], .phone-input input, input[name='phone']", timeout=15_000)
        except Exception:
            logger.warning(f"[{account_id}] 未找到手机号输入框，尝试点击登录入口...")
            try:
                # 有些页面需要先点击登录按钮
                page.click(".login-btn, [class*='login'], button:has-text('登录')", timeout=5_000)
                page.wait_for_selector("input[placeholder*='手机号'], .phone-input input", timeout=10_000)
            except Exception as e2:
                logger.error(f"[{account_id}] 无法找到登录入口: {e2}")
                # 截图保存便于调试
                page.screenshot(path=f"login_debug_{phone.replace('+','')}.png")
                browser.close()
                return None

        # 填手机号
        phone_input = page.locator(
            "input[placeholder*='手机号'], .phone-input input, input[name='phone'], input[type='tel']"
        ).first
        phone_input.fill(phone.replace("+1", "").replace("+", ""))  # XHS 国内用11位，美号先尝试完整填入
        logger.info(f"[{account_id}] 已填入手机号")

        # 点发送验证码
        try:
            send_btn = page.locator(
                "button:has-text('发送验证码'), button:has-text('获取验证码'), .send-code-btn, [class*='send']:has-text('验证码')"
            ).first
            send_btn.click(timeout=5_000)
            logger.info(f"[{account_id}] 已点击发送验证码")
        except Exception as e:
            logger.error(f"[{account_id}] 点击发送验证码失败: {e}")
            page.screenshot(path=f"login_debug_send_{phone.replace('+','')}.png")
            browser.close()
            return None

        # 轮询获取验证码
        from config.config import SMS_WAIT_BEFORE_POLL, SMS_POLL_INTERVAL, SMS_POLL_TIMEOUT
        code = _poll_sms_code(
            sms_url,
            wait_first=SMS_WAIT_BEFORE_POLL,
            interval=SMS_POLL_INTERVAL,
            timeout=SMS_POLL_TIMEOUT,
        )
        if not code:
            page.screenshot(path=f"login_debug_nocode_{phone.replace('+','')}.png")
            browser.close()
            return None

        # 填验证码
        try:
            code_input = page.locator(
                "input[placeholder*='验证码'], .code-input input, input[name='code'], input[maxlength='6']"
            ).first
            code_input.fill(code)
            logger.info(f"[{account_id}] 已填入验证码 {code}")
        except Exception as e:
            logger.error(f"[{account_id}] 填写验证码失败: {e}")
            browser.close()
            return None

        # 提交登录
        try:
            login_btn = page.locator(
                "button:has-text('登录'), button[type='submit'], .login-submit-btn"
            ).first
            login_btn.click(timeout=5_000)
        except Exception:
            page.keyboard.press("Enter")

        # 等待登录成功（web_session 出现）
        try:
            page.wait_for_function("document.cookie.includes('web_session')", timeout=30_000)
        except Exception:
            cookies = context.cookies()
            if not any(c["name"] == "web_session" for c in cookies):
                logger.error(f"[{account_id}] 登录失败，未获取到 web_session")
                page.screenshot(path=f"login_debug_fail_{phone.replace('+','')}.png")
                browser.close()
                return None

        # 等待 a1 写入
        logger.info(f"[{account_id}] 等待 JS 写入 a1 cookie...")
        time.sleep(3)
        try:
            page.wait_for_function("document.cookie.includes('a1')", timeout=10_000)
        except Exception:
            logger.warning(f"[{account_id}] a1 未写入，继续")

        cookies = context.cookies()
        browser.close()

    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    logger.success(f"[{account_id}] 登录成功，Cookie 长度: {len(cookie_str)}")
    return cookie_str


def login_and_get_cookie(account_id: str, timeout: int = 120) -> Optional[str]:
    """
    扫码登录（手动），保留供调试使用。
    """
    logger.info(f"[{account_id}] 启动 Playwright 进行扫码登录...")

    with sync_playwright() as p:
        browser: Browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context: BrowserContext = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page.goto(XHS_LOGIN, timeout=30_000)
        logger.info(f"[{account_id}] 请在浏览器中完成登录（最多等待 {timeout}s）...")

        deadline_ms = timeout * 1_000
        try:
            page.wait_for_function("document.cookie.includes('web_session')", timeout=deadline_ms)
        except Exception:
            cookies = context.cookies()
            if not any(c["name"] == "web_session" for c in cookies):
                logger.error(f"[{account_id}] 登录超时或失败")
                browser.close()
                return None

        logger.info(f"[{account_id}] 登录成功，等待 JS 写入 a1 cookie...")
        time.sleep(3)
        try:
            page.wait_for_function("document.cookie.includes('a1')", timeout=10_000)
        except Exception:
            logger.warning(f"[{account_id}] a1 cookie 未能获取，将继续使用现有 cookie")

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
