"""
主入口 - 小红书评论用户 ID 采集系统

用法：
  python main.py login-phone              # 批量手机验证码登录所有 phone_data.txt 账号
  python main.py login-phone --phone +15416485577  # 登录指定手机号
  python main.py login --account acct_01  # 扫码登录（备用）
  python main.py validate                 # 验证所有账号 Cookie 有效性
  python main.py crawl --url "..."        # 单帖爬取
  python main.py crawl --file urls.txt --workers 3  # 多帖并发爬取
  python main.py accounts                 # 列出所有账号
  python main.py proxy list               # 列出所有代理
"""
import argparse
import json
import sys

from config.config import ACCOUNTS, PROXIES, PHONE_ACCOUNTS
from src.account.account_pool import AccountPool
from src.account.login import login_and_get_cookie, phone_login
from src.crawler.comment_crawler import XhsCrawler, crawl_many
from src.proxy.proxy_pool import ProxyPool
from src.utils.db import init_db
from src.utils.logger import logger, setup_logger


# -------------------------------------------------------------------------
# 子命令：login（扫码，保留备用）
# -------------------------------------------------------------------------

def cmd_login(args) -> None:
    pool = AccountPool()
    pool.add_account(args.account, username=args.username or "")
    cookie = login_and_get_cookie(args.account, timeout=args.timeout)
    if cookie:
        pool.update_cookie(args.account, cookie)
        logger.success(f"账号 {args.account} 登录成功，Cookie 已保存")
    else:
        logger.error(f"账号 {args.account} 登录失败")
        sys.exit(1)


# -------------------------------------------------------------------------
# 子命令：login-phone（手机验证码自动登录）
# -------------------------------------------------------------------------

def cmd_login_phone(args) -> None:
    """批量或单个手机号验证码登录"""
    account_pool = AccountPool()
    proxy_pool = ProxyPool()

    # 确定要登录的手机号列表
    targets = PHONE_ACCOUNTS  # 全部
    if args.phone:
        targets = [p for p in PHONE_ACCOUNTS if p["phone"] == args.phone]
        if not targets:
            logger.error(f"phone_data.txt 中未找到手机号 {args.phone}")
            sys.exit(1)

    if not targets:
        logger.error("phone_data.txt 为空或未找到手机号")
        sys.exit(1)

    success, failed = 0, 0
    for i, entry in enumerate(targets):
        phone = entry["phone"]
        sms_url = entry["sms_url"]
        account_id = phone  # 用手机号作为账号ID

        # 如果 Cookie 已有效，跳过登录
        account_pool.add_account(account_id, username=phone)
        if not args.force and account_pool.validate_cookie(account_id):
            logger.info(f"[{phone}] Cookie 仍有效，跳过登录")
            success += 1
            continue

        # 从代理池中取一个代理分配给该账号
        proxy_dict = proxy_pool.bind_proxy_to_account(account_id)

        cookie = phone_login(
            phone=phone,
            sms_url=sms_url,
            proxy=proxy_dict,
            headless=not args.show_browser,
        )
        if cookie:
            account_pool.update_cookie(account_id, cookie)
            logger.success(f"[{phone}] 登录成功，Cookie 已保存")
            success += 1
        else:
            logger.error(f"[{phone}] 登录失败")
            failed += 1

    print(f"\n登录完成：成功 {success}，失败 {failed}")


# -------------------------------------------------------------------------
# 子命令：validate（验证 Cookie 有效性）
# -------------------------------------------------------------------------

def cmd_validate(args) -> None:
    pool = AccountPool()
    accounts = pool.list_accounts()
    active = [a for a in accounts if a["status"] == "active"]
    print(f"检测 {len(active)} 个 active 账号...")
    valid, invalid = 0, 0
    for a in active:
        ok = pool.validate_cookie(a["account_id"])
        status = "✓ 有效" if ok else "✗ 失效"
        print(f"  {a['account_id']:<24} {status}")
        if ok:
            valid += 1
        else:
            invalid += 1
    print(f"\n有效: {valid}，失效: {invalid}")


# -------------------------------------------------------------------------
# 子命令：proxy
# -------------------------------------------------------------------------

def cmd_proxy(args) -> None:
    pool = ProxyPool()

    if args.proxy_cmd == "add":
        pool.add_proxy(
            host=args.host,
            port=args.port,
            protocol=args.protocol,
            username=args.proxy_user or "",
            password=args.proxy_pass or "",
        )
        print(f"已添加代理 {args.protocol}://{args.host}:{args.port}")

    elif args.proxy_cmd == "check":
        pool.validate_all()
        print("代理检测完成")

    elif args.proxy_cmd == "list":
        from src.utils.db import Proxy, get_session
        with get_session() as session:
            proxies = session.query(Proxy).all()
        for p in proxies:
            status = "✓" if p.is_valid else "✗"
            bound = p.bound_account_id or "-"
            print(f"  [{status}] {p.protocol}://{p.host}:{p.port}  bound={bound}")


# -------------------------------------------------------------------------
# 子命令：accounts
# -------------------------------------------------------------------------

def cmd_accounts(args) -> None:
    pool = AccountPool()
    accounts = pool.list_accounts()
    if not accounts:
        print("账号池为空")
        return
    print(f"{'账号ID':<26} {'状态':<16} {'请求数':<10} {'Cookie更新时间'}")
    print("-" * 75)
    for a in accounts:
        print(
            f"{a['account_id']:<26} {a['status']:<16} "
            f"{a['request_count'] or 0:<10} {a['cookie_updated_at'] or '-'}"
        )


# -------------------------------------------------------------------------
# 子命令：crawl
# -------------------------------------------------------------------------

def cmd_crawl(args) -> None:
    urls = []
    if args.url:
        urls.append(args.url)
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        except FileNotFoundError:
            logger.error(f"URL 文件不存在: {args.file}")
            sys.exit(1)

    if not urls:
        logger.error("请通过 --url 或 --file 指定帖子链接")
        sys.exit(1)

    workers = getattr(args, "workers", 1)

    # 并发模式
    if workers > 1 or len(urls) > 1:
        # 获取所有 active 账号 ID
        pool = AccountPool()
        all_accounts = [a["account_id"] for a in pool.list_accounts() if a["status"] == "active"]
        account_ids = [args.account] if args.account else (all_accounts or None)
        all_results = crawl_many(urls, max_workers=workers, account_ids=account_ids)
    else:
        crawler = XhsCrawler()
        result = crawler.fetch_comment_user_ids(urls[0], account_id=args.account or None)
        all_results = {urls[0]: result}

    # 打印
    for url, user_ids in all_results.items():
        print(f"\n[{url}]")
        if user_ids:
            print(f"  共 {len(user_ids)} 个评论用户 ID:")
            for uid in user_ids:
                print(f"    {uid}")
        else:
            print("  无评论或采集失败")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        logger.success(f"结果已保存到 {args.output}")


# -------------------------------------------------------------------------
# 启动时自动导入配置中预设的账号和代理
# -------------------------------------------------------------------------

def _bootstrap_from_config() -> None:
    account_pool = AccountPool()
    proxy_pool = ProxyPool()

    for acc in ACCOUNTS:
        account_pool.add_account(
            account_id=acc.get("account_id", ""),
            username=acc.get("username", ""),
        )
        if acc.get("cookie"):
            account_pool.update_cookie(
                account_id=acc["account_id"],
                cookie=acc["cookie"],
                user_id=acc.get("user_id", ""),
            )

    for proxy in PROXIES:
        proxy_pool.add_proxy(
            host=proxy.get("host", ""),
            port=int(proxy.get("port", 80)),
            protocol=proxy.get("protocol", "http"),
            username=proxy.get("username", ""),
            password=proxy.get("password", ""),
        )


# -------------------------------------------------------------------------
# CLI 解析
# -------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xhs",
        description="小红书评论用户 ID 采集系统",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = parser.add_subparsers(dest="command")

    # login（扫码，备用）
    p_login = sub.add_parser("login", help="登录账号并保存 Cookie")
    p_login.add_argument("--account", required=True, help="账号唯一标识（自定义）")
    p_login.add_argument("--username", default="", help="账号用户名/手机号（可选）")
    p_login.add_argument("--timeout", type=int, default=120, help="等待登录的最长时间（秒）")

    # proxy
    p_proxy = sub.add_parser("proxy", help="管理代理池")
    proxy_sub = p_proxy.add_subparsers(dest="proxy_cmd")

    p_proxy_add = proxy_sub.add_parser("add", help="添加代理")
    p_proxy_add.add_argument("--host", required=True)
    p_proxy_add.add_argument("--port", type=int, required=True)
    p_proxy_add.add_argument("--protocol", default="http", choices=["http", "socks5"])
    p_proxy_add.add_argument("--proxy-user", default="")
    p_proxy_add.add_argument("--proxy-pass", default="")

    proxy_sub.add_parser("check", help="检测所有代理可用性")
    proxy_sub.add_parser("list", help="列出所有代理")

    # accounts
    sub.add_parser("accounts", help="列出所有账号状态")

    # crawl
    p_crawl = sub.add_parser("crawl", help="采集帖子评论用户 ID")
    p_crawl.add_argument("--url", default="", help="单个帖子 URL")
    p_crawl.add_argument("--file", default="", help="包含多个帖子 URL 的文本文件（每行一个）")
    p_crawl.add_argument("--output", default="", help="结果输出 JSON 文件路径")
    p_crawl.add_argument("--account", default="", help="指定使用的账号 ID，不指定则自动轮询")
    p_crawl.add_argument("--workers", type=int, default=1, help="并发数（默认 1，多 URL 时建议设为账号数）")

    # login-phone（手机验证码自动登录）
    p_lp = sub.add_parser("login-phone", help="手机验证码自动登录（读取 phone_data.txt）")
    p_lp.add_argument("--phone", default="", help="指定单个手机号，不填则批量登录全部")
    p_lp.add_argument("--force", action="store_true", help="强制重新登录（即使 Cookie 仍有效）")
    p_lp.add_argument("--show-browser", action="store_true", help="显示浏览器窗口（调试用）")

    # validate
    sub.add_parser("validate", help="验证所有账号 Cookie 有效性")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logger(log_level=args.log_level)
    init_db()
    _bootstrap_from_config()

    if args.command == "login":
        cmd_login(args)
    elif args.command == "login-phone":
        cmd_login_phone(args)
    elif args.command == "validate":
        cmd_validate(args)
    elif args.command == "proxy":
        cmd_proxy(args)
    elif args.command == "accounts":
        cmd_accounts(args)
    elif args.command == "crawl":
        cmd_crawl(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
