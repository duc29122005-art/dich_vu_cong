"""Application logging. Callers must never include feedback, PII, or secrets."""

import logging


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure one application handler without changing root logging."""
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Invalid logging level")
    logger = logging.getLogger("pfa")
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    return logger
