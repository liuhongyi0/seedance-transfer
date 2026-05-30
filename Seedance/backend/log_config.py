"""
Unified logging configuration for Seedance Studio backend.

Usage:
  from log_config import get_logger
  logger = get_logger(__name__)

Level is controlled by LOG_LEVEL env var (default: INFO).
Format: 2026-05-30T12:34:56 INFO    [routers.auth] message here
"""

import logging
import os
import sys

LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

_formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_formatter)
_handler.setLevel(LEVEL)

# Root logger setup
_root = logging.getLogger()
_root.setLevel(LEVEL)
# Remove default handlers to avoid duplicate output
_root.handlers.clear()
_root.addHandler(_handler)

# Silence noisy libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the calling module."""
    return logging.getLogger(name)
