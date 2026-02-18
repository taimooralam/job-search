"""Shared utilities for the LinkedIn Intelligence skill."""

import hashlib
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
        name: Config filename without extension (e.g. 'safety-config').
    """
    config_path = get_script_dir() / "config" / f"{name}.json"
    with open(config_path) as f:
        return json.load(f)


def load_brand_voice() -> str:
    """Load the brand voice markdown guide."""
    voice_path = get_script_dir() / "config" / "brand-voice.md"
    return voice_path.read_text()


def generate_dedupe_hash(source: str, url: str, title: str) -> str:
    """Generate a SHA-256 dedupe hash from source + URL + title.

    This prevents storing the same LinkedIn item twice across sessions.
    """
    raw = f"{source}|{url}|{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()


def setup_logging(name: str = "linkedin-intel") -> logging.Logger:
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
