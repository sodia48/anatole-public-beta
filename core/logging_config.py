from __future__ import annotations

import logging
import os
import sys


_CONFIGURED = False


def configure_logging() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("anatole")

    if _CONFIGURED:
        return logger

    level = os.getenv("ANATOLE_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | anatole | %(message)s"
        )
    )
    logger.handlers.clear()
    logger.addHandler(handler)

    _CONFIGURED = True
    return logger
