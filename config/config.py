# 项目配置文件 - 开发环境

# 账号配置
ACCOUNTS = []

# 代理配置
PROXIES = []

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
