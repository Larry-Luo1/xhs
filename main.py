"""
主入口 - 小红书评论用户 ID 采集系统

用法：
  python main.py --help
  python main.py login --account my_account
  python main.py proxy add --host 1.2.3.4 --port 8080
  python main.py crawl --url "https://www.xiaohongshu.com/explore/xxxx"
  python main.py crawl --file urls.txt
  python main.py proxy check
"""
import argparse
import sys

from config.config import ACCOUNTS, PROXIES
from src.account.account_pool import AccountPool
from src.account.login import login_and_get_cookie
from src.crawler.comment_crawler import XhsCrawler
from src.proxy.proxy_pool import ProxyPool
from src.utils.db import init_db
from src.utils.logger import logger, setup_logger


# -------------------------------------------------------------------------
# 子命令：login
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
    print(f"{'账号ID':<20} {'状态':<16} {'请求数':<10} {'Cookie更新时间'}")
    print("-" * 70)
    for a in accounts:
        print(
            f"{a['account_id']:<20} {a['status']:<16} "
            f"{a['request_count'] or 0:<10} {a['cookie_updated_at'] or '-'}"
        )


# -------------------------------------------------------------------------
# 子命令：crawl
# -------------------------------------------------------------------------

def cmd_crawl(args) -> None:
    crawler = XhsCrawler()
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

    all_results = {}
    for url in urls:
        logger.info(f"开始处理: {url}")
        user_ids = crawler.fetch_comment_user_ids(url)
        all_results[url] = user_ids
        print(f"\n[{url}]")
        if user_ids:
            print(f"  共 {len(user_ids)} 个评论用户 ID:")
            for uid in user_ids:
                print(f"    {uid}")
        else:
            print("  无评论或采集失败")

    if args.output:
        import json
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        logger.success(f"结果已保存到 {args.output}")


# -------------------------------------------------------------------------
# 启动时自动导入配置中预设的账号和代理
# -------------------------------------------------------------------------

def _bootstrap_from_config() -> None:
    """将 config.py 中预设的账号和代理导入数据库"""
    account_pool = AccountPool()
    proxy_pool = ProxyPool()

    for acc in ACCOUNTS:
        account_pool.add_account(
            account_id=acc.get("account_id", ""),
            username=acc.get("username", ""),
        )
        # 如果配置中已有 cookie，直接更新
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

    # login
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logger(log_level=args.log_level)

    # 初始化数据库
    init_db()

    # 从配置文件导入预设账号/代理
    _bootstrap_from_config()

    if args.command == "login":
        cmd_login(args)
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
