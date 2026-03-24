# utils/logger.py  —  structured logging for the entire project
# Replaces all bare print() calls.

import logging
import sys

_FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATE = "%H:%M:%S"

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FMT, _DATE))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
