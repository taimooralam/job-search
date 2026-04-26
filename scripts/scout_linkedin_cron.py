#!/usr/bin/env python3
"""Entry point for the shared scout search discovery pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from src.pipeline.discovery.scout_search_pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
