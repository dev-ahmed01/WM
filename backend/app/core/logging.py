"""Structured application logging configuration and named loggers."""

# Assumption: Pre-configured named loggers use the prefix 'workmate.' to provide consistent logging hierarchy across all application modules.

import sys
import logging
from app.core.config import settings

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Configures root logger with standard formatter and settings level."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers on re-initialization
    root_logger.handlers.clear()
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Helper returning a named logger under the workmate namespace."""
    full_name = f"workmate.{name}" if not name.startswith("workmate.") else name
    return logging.getLogger(full_name)


# Predefined named loggers for consistent subsystem logging
requests_logger = get_logger("requests")
ai_logger = get_logger("ai_requests")
ingestion_logger = get_logger("ingestion_jobs")
exceptions_logger = get_logger("exceptions")
