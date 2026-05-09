"""日志模块"""
import sys
import os
from loguru import logger as _logger


def setup_logger(log_level: str = "DEBUG", log_dir: str = "logs") -> "logger":
    os.makedirs(log_dir, exist_ok=True)
    _logger.remove()
    _logger.add(
        sys.stdout,
        level=log_level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )
    _logger.add(
        os.path.join(log_dir, "xhs_{time:YYYY-MM-DD}.log"),
        rotation="00:00",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )
    return _logger


logger = setup_logger()
