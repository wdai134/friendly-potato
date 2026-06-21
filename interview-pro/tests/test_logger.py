"""测试 logger 模块 — 结构化日志输出。"""
import logging
import pytest
from unittest.mock import patch, MagicMock
from agent.logger import setup_logger


# ═══════════════════════════════════════════════════════════════════════
# setup_logger() tests
# ═══════════════════════════════════════════════════════════════════════

def test_setup_logger_returns_logger():
    """应返回 logging.Logger 实例。"""
    logger = setup_logger("test-logger")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test-logger"


def test_setup_logger_default_name():
    """默认名称为 interview-pro。"""
    logger = setup_logger()
    assert logger.name == "interview-pro"


def test_setup_logger_default_level():
    """默认级别为 INFO。"""
    logger = setup_logger("test-level")
    assert logger.level == logging.INFO


def test_setup_logger_custom_level_string():
    """支持字符串级别。"""
    logger = setup_logger("test-debug", "DEBUG")
    assert logger.level == logging.DEBUG


def test_setup_logger_custom_level_int():
    """支持整数级别。"""
    logger = setup_logger("test-warning", logging.WARNING)
    assert logger.level == logging.WARNING


def test_setup_logger_has_console_handler():
    """应包含控制台输出 handler。"""
    logger = setup_logger("test-handlers-cons")
    handler_types = [type(h) for h in logger.handlers]
    assert logging.StreamHandler in handler_types


def test_setup_logger_has_file_handler():
    """应包含文件输出 handler。"""
    with patch("agent.logger.os.makedirs"):
        with patch("agent.logger.logging.FileHandler") as mock_fh:
            mock_handler = MagicMock()
            mock_handler.formatter = None
            mock_fh.return_value = mock_handler
            logger = setup_logger("test-file-handler-unique")
            # mock_fh 被调用一次（文件 handler 已创建）
            mock_fh.assert_called_once()



def test_setup_logger_is_idempotent():
    """重复调用不添加重复 handler。"""
    logger1 = setup_logger("test-idempotent")
    handler_count_1 = len(logger1.handlers)

    logger2 = setup_logger("test-idempotent")
    handler_count_2 = len(logger2.handlers)

    assert logger1 is logger2
    assert handler_count_1 == handler_count_2
    assert handler_count_1 > 0


def test_setup_logger_creates_log_directory():
    """logs/ 目录不存在时应创建。"""
    # 必须用全新 logger name + 模拟目录不存在
    # patch agent.logger.os 因为模块内 import os
    with patch("agent.logger.os.makedirs") as mock_mkdirs:
        with patch("agent.logger.os.path.exists", return_value=False):
            with patch("agent.logger.logging.FileHandler") as mock_fh:
                mock_handler = MagicMock()
                mock_handler.formatter = None
                mock_fh.return_value = mock_handler
                setup_logger("test-mkdir-unique3")
                mock_mkdirs.assert_called_once()


def test_setup_logger_handlers_have_formatter():
    """所有 handler 都应配置了 Formatter。"""
    logger = setup_logger("test-formatter")
    for handler in logger.handlers:
        assert handler.formatter is not None
