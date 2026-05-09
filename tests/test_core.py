"""基础单元测试"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_db_init():
    """测试数据库初始化"""
    from src.utils.db import init_db, get_session, Account, Proxy, Task, CommentUser
    init_db()
    with get_session() as session:
        assert session.query(Account).count() >= 0


def test_account_pool_add_and_get():
    """测试账号池添加与查询"""
    from src.utils.db import init_db
    from src.account.account_pool import AccountPool

    init_db()
    pool = AccountPool()
    pool.add_account("test_acc_001", username="test_user")

    acc = pool.get_account_by_id("test_acc_001")
    assert acc is not None
    assert acc["account_id"] == "test_acc_001"
    assert acc["status"] == "invalid"  # 无 cookie 时为 invalid


def test_account_pool_cookie_update():
    """测试 Cookie 更新后状态变为 active"""
    from src.utils.db import init_db
    from src.account.account_pool import AccountPool, AccountStatus

    init_db()
    pool = AccountPool()
    pool.add_account("test_acc_002")
    pool.update_cookie("test_acc_002", "web_session=abc123; xhsTrackerId=xyz", user_id="uid_001")

    acc = pool.get_account_by_id("test_acc_002")
    assert acc["status"] == AccountStatus.ACTIVE
    assert "web_session" in acc["cookie"]


def test_proxy_pool_add():
    """测试代理池添加"""
    from src.utils.db import init_db
    from src.proxy.proxy_pool import ProxyPool

    init_db()
    pool = ProxyPool()
    pool.add_proxy("127.0.0.1", 8080, "http")

    proxies_dict = pool.build_requests_proxies("nonexistent_account")
    assert proxies_dict is None  # 未绑定账号则返回 None


def test_sign_service_placeholder():
    """测试签名服务占位符模式"""
    from src.crawler.sign_service import SignService

    svc = SignService()
    result = svc.sign("/api/sns/web/v2/comment/page", data={"note_id": "abc"}, cookie="")
    assert "x-s" in result
    assert "x-t" in result
    assert len(result["x-t"]) > 0


def test_xsec_token_extract_note_id():
    """测试从 URL 提取 note_id"""
    from src.crawler.xsec_token_manager import XsecTokenManager

    url1 = "https://www.xiaohongshu.com/explore/66a1b2c3d4e5f6a7b8c9d0e1"
    url2 = "https://www.xiaohongshu.com/discovery/item/66a1b2c3d4e5f6a7b8c9d0e1?xsec_token=abc"

    assert XsecTokenManager.extract_note_id_from_url(url1) == "66a1b2c3d4e5f6a7b8c9d0e1"
    assert XsecTokenManager.extract_note_id_from_url(url2) == "66a1b2c3d4e5f6a7b8c9d0e1"


def test_throttle():
    """测试限速器（短暂休眠）"""
    import time
    from src.utils.throttle import ThrottleManager

    throttle = ThrottleManager(min_delay=0.1, max_delay=0.2)
    start = time.time()
    throttle.wait()
    elapsed = time.time() - start
    assert 0.05 <= elapsed <= 0.5
