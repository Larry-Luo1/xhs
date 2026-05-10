# 项目配置文件 - 开发环境

import os

_BASE = os.path.dirname(os.path.dirname(__file__))

def _load_ip_pool(path: str = None):
    """从 ip_pool.txt 加载代理列表"""
    path = path or os.path.join(_BASE, "ip_pool.txt")
    proxies = []
    if not os.path.exists(path):
        return proxies
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                host, _, port = line.partition(":")
                try:
                    proxies.append({"host": host.strip(), "port": int(port.strip()), "protocol": "http", "username": "", "password": ""})
                except ValueError:
                    pass
    return proxies

def _load_phone_data(path: str = None):
    """从 phone_data.txt 加载手机号与验证码 URL 对应关系"""
    path = path or os.path.join(_BASE, "phone_data.txt")
    phones = []
    if not os.path.exists(path):
        return phones
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("phone") or line.startswith("#"):
                continue
            if "----" in line:
                phone, _, url = line.partition("----")
                phones.append({"phone": phone.strip(), "sms_url": url.strip()})
    return phones

# 账号配置（通过 login --phone 命令自动填充，此处无需手动维护）
ACCOUNTS = []

# 代理配置 - 从 ip_pool.txt 自动加载
PROXIES = _load_ip_pool()

# 手机号配置 - 从 phone_data.txt 自动加载
PHONE_ACCOUNTS = _load_phone_data()

# 日志配置
LOG_LEVEL = "DEBUG"
LOG_DIR = "logs"

# 请求配置
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

# 采集配置
COMMENTS_PER_PAGE = 20
MAX_PAGES = 100
THROTTLE_DELAY_MIN = 3
THROTTLE_DELAY_MAX = 8

# 数据库配置
DATABASE_URL = "sqlite:///xhs.db"

# Chrome配置
HEADLESS_MODE = True
DISABLE_BLINK_FEATURES = True

# 手机登录配置
SMS_POLL_INTERVAL = 3    # 轮询验证码间隔（秒）
SMS_POLL_TIMEOUT = 90    # 最长等待验证码时间（秒）
SMS_WAIT_BEFORE_POLL = 15  # 发送验证码后等待几秒再开始轮询
