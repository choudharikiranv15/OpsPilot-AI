"""Logging configuration for OpsPilot."""

import logging
import sys
from pathlib import Path
from typing import Optional


class OpsPilotLogger:
    """Centralized logger for OpsPilot with console and file output support."""

    _instance: Optional['OpsPilotLogger'] = None
    _logger: Optional[logging.Logger] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is None:
            self._logger = logging.getLogger("opspilot")
            self._logger.setLevel(logging.DEBUG)
            self._setup_console_handler()

    def _setup_console_handler(self):
        """Setup console handler with appropriate formatting."""
        if not self._logger.handlers:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                "[%(levelname)s] %(message)s"
            )
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

    def set_level(self, level: str):
        """Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        log_level = level_map.get(level.upper(), logging.INFO)
        self._logger.setLevel(log_level)
        for handler in self._logger.handlers:
            handler.setLevel(log_level)

    def enable_debug(self):
        """Enable debug level logging."""
        self.set_level("DEBUG")

    def add_file_handler(self, log_file: str):
        """Add file handler for persistent logging."""
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

    def debug(self, msg: str, *args, **kwargs):
        """Log debug message."""
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info message."""
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning message."""
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error message."""
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        """Log critical message."""
        self._logger.critical(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        """Log exception with traceback."""
        self._logger.exception(msg, *args, **kwargs)


# Global logger instance
_logger: Optional[OpsPilotLogger] = None


def get_logger() -> OpsPilotLogger:
    """Get the global OpsPilot logger instance."""
    global _logger
    if _logger is None:
        _logger = OpsPilotLogger()
    return _logger


def setup_logging(debug: bool = False, log_file: Optional[str] = None):
    """
    Setup logging configuration.

    Args:
        debug: Enable debug level logging
        log_file: Optional file path for persistent logging
    """
    logger = get_logger()
    if debug:
        logger.enable_debug()
    if log_file:
        logger.add_file_handler(log_file)
    return logger


# Convenience functions
def debug(msg: str, *args, **kwargs):
    """Log debug message."""
    get_logger().debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    """Log info message."""
    get_logger().info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    """Log warning message."""
    get_logger().warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    """Log error message."""
    get_logger().error(msg, *args, **kwargs)


def critical(msg: str, *args, **kwargs):
    """Log critical message."""
    get_logger().critical(msg, *args, **kwargs)
