"""Application logging configuration."""

from __future__ import annotations

import logging

LOGGER_NAME = "oci_license_poc"


def configure_logging() -> logging.Logger:
    """Configure INFO-level console logging for the application once.

    Returns:
        The root application logger shared by all modules in this project.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return logger
