"""日志模块 — 结构化日志输出。

提供统一的日志格式和级别控制。
日志同时输出到控制台和 logs/ 目录下的文件。
"""

import logging
import os
from datetime import datetime


def setup_logger(name: str = "interview-pro", level: str | int = "INFO") -> logging.Logger:
    """创建日志器，同时输出到控制台和文件。

    Args:
        name: 日志器名称
        level: 日志级别，默认 INFO
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 格式化
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件输出
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"interview_{datetime.now().strftime('%Y-%m-%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
