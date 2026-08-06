"""Unit tests for structured logging subsystem."""

import logging
from app.core.logging import setup_logging, get_logger, requests_logger, ai_logger, ingestion_logger, exceptions_logger


def test_setup_logging_runs_cleanly():
    setup_logging()
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) > 0


def test_get_logger_prefix():
    lg = get_logger("custom_service")
    assert lg.name == "workmate.custom_service"

    lg_prefixed = get_logger("workmate.existing")
    assert lg_prefixed.name == "workmate.existing"


def test_predefined_named_loggers():
    assert requests_logger.name == "workmate.requests"
    assert ai_logger.name == "workmate.ai_requests"
    assert ingestion_logger.name == "workmate.ingestion_jobs"
    assert exceptions_logger.name == "workmate.exceptions"
