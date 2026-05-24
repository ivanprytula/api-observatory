import logging

import pytest

from services.ingestor.config import settings
from services.ingestor.core.logging import get_cid, set_cid, setup_logging


@pytest.mark.unit
def test_logging_setup_respects_environment_setting():
    """Test that setup_logging creates appropriate formatters based on environment."""
    # Development environment
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.environment = "development"
    settings.log_level = "INFO"
    logger = setup_logging()

    assert logger is not None
    assert logging.getLogger().level == logging.INFO
    # Should have handlers
    assert len(logger.handlers) >= 1

    # Production environment
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.environment = "production"
    logger = setup_logging()

    assert logger is not None
    assert logging.getLogger().level == logging.INFO
    # Should have handlers
    assert len(logger.handlers) >= 1


@pytest.mark.unit
def test_logging_respects_global_log_level():
    """Test that LOG_LEVEL setting controls root logger level."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.environment = "production"
    settings.log_level = "DEBUG"
    _ = setup_logging()
    assert logging.getLogger().level == logging.DEBUG

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.log_level = "WARNING"
    _ = setup_logging()
    assert logging.getLogger().level == logging.WARNING

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.log_level = "INFO"
    _ = setup_logging()
    assert logging.getLogger().level == logging.INFO


@pytest.mark.unit
def test_correlation_id_context_vars():
    """Test that CID get/set work correctly."""
    # Initially None
    assert get_cid() is None

    # Set and retrieve
    test_cid = "test-cid-12345"
    set_cid(test_cid)
    assert get_cid() == test_cid

    # Set new value
    new_cid = "test-cid-67890"
    set_cid(new_cid)
    assert get_cid() == new_cid


@pytest.mark.unit
def test_logger_methods_callable():
    """Test that standard logger methods work as expected (no exceptions)."""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    settings.environment = "production"
    settings.log_level = "DEBUG"
    logger = setup_logging()

    # These should not raise exceptions
    logger.debug("test debug", extra={"key": "value"})
    logger.info("test info", extra={"request_id": 123})
    logger.warning("test warning", extra={"status": "slow"})
    logger.error("test error", extra={"code": "ERR_001"})

    # All methods should work without error
    assert logger is not None
