"""Logging helpers for the VLM_Monitors runtime."""
from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: Optional[int] = None) -> None:
    """Configure root logging with a concise formatter."""
    log_level = level or logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s: %(message)s",
        handlers=[
            logging.FileHandler("temp/app.log"),
            logging.StreamHandler()
        ]
    )


__all__ = ["configure_logging"]
