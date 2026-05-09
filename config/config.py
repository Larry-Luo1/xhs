# 项目配置文件 - 开发环境

# 账号配置
# 格式：{"account_id": "唯一标识", "username": "手机号", "cookie": "...", "user_id": ""}
# cookie 可在首次使用 `python main.py login --account <id>` 后自动写入数据库，此处留空即可
ACCOUNTS = [
    # {"account_id": "account_01", "username": "", "cookie": "", "user_id": ""},
]

# 代理配置
# 格式：{"host": "1.2.3.4", "port": 8080, "protocol": "http", "username": "", "password": ""}
PROXIES = [
    # {"host": "1.2.3.4", "port": 8080, "protocol": "http", "username": "", "password": ""},
]

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
