import importlib
import logging

import pytest

from pfa.core.logging import configure_logging


def test_imports():
    for name in (
        "pfa",
        "pfa.cli",
        "pfa.core.config",
        "pfa.data",
        "pfa.ml",
        "pfa.api",
        "pfa.analytics",
    ):
        assert importlib.import_module(name)


def test_logging_is_idempotent_and_validated():
    logger = logging.getLogger("pfa")
    original_handlers = logger.handlers[:]
    original_level, original_propagate = logger.level, logger.propagate
    try:
        logger.handlers = []
        configure_logging()
        configure_logging("WARNING")
        assert len(logger.handlers) == 1
        assert logger.level == logging.WARNING
        assert not logger.propagate
        with pytest.raises(ValueError):
            configure_logging("INVALID")
    finally:
        for handler in logger.handlers:
            if handler not in original_handlers:
                handler.close()
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate
