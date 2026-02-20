"""Shared utilities for the URL Resolver skill."""

import json
import logging
import os
from pathlib import Path


def get_script_dir() -> Path:
    """Return the skill root directory (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def load_config(name: str) -> dict:
    """Load a JSON config file from the config/ directory.

    Args:
        name: Config filename without extension (e.g. 'ats-domains').
    """
    config_path = get_script_dir() / "config" / f"{name}.json"
    with open(config_path) as f:
        return json.load(f)


def setup_logging(name: str = "url-resolver") -> logging.Logger:
    """Configure and return a logger with consistent formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    return logger
