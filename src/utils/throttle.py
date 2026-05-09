"""请求限速模块 - 模拟真实用户访问节奏"""
import random
import time

from config.config import THROTTLE_DELAY_MAX, THROTTLE_DELAY_MIN
from src.utils.logger import logger


class ThrottleManager:
    """每次调用 wait() 时随机休眠 [min, max] 秒，模拟人工浏览间隔"""

    def __init__(
        self,
        min_delay: float = THROTTLE_DELAY_MIN,
        max_delay: float = THROTTLE_DELAY_MAX,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay

    def wait(self, label: str = "") -> None:
        delay = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"限速等待 {delay:.1f}s {label}")
        time.sleep(delay)

    def wait_short(self) -> None:
        """页间短暂停顿（max的1/3）"""
        delay = random.uniform(0.5, self.max_delay / 3)
        time.sleep(delay)
