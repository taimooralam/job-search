#!/usr/bin/env python3
"""
Proxy Refresh Cron — Fetch, validate, and cache proxies for scout jobs.

Runs every 20 minutes via cron. Strategy:
  1. Fetch ~5000+ candidates from 6 GitHub proxy lists
  2. Dedup against blocklist (known-bad proxies, expires after 2 hours)
  3. Dedup against current working list (no need to re-fetch known-good)
  4. Validate only NEW candidates against LinkedIn HTTPS
  5. Re-validate existing working proxies (remove dead ones)
  6. Merge: still-working + newly-passing → proxies.json
  7. Failed proxies → blocklist.json (skipped for 2 hours)

The scout cron jobs load proxies.json instantly with no validation delay.

Usage:
    python scripts/scout_proxy_refresh_cron.py
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

_SKILL_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _SKILL_ROOT)

from src.common.proxy_pool import fetch_candidates, validate_parallel, save_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("SCOUT_QUEUE_DIR", str(Path(_SKILL_ROOT) / "data" / "scout")))
WORKING_PATH = DATA_DIR / "proxies.json"
BLOCKLIST_PATH = DATA_DIR / "proxies_blocklist.json"

# Blocked proxies expire after 30 minutes (get retried)
# Free proxy lists recycle the same ~6000 IPs, so a long TTL starves the pool
BLOCKLIST_TTL_SECONDS = 1800


def load_json_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def load_blocklist() -> set:
    """Load blocklist, filtering out expired entries."""
    if not BLOCKLIST_PATH.exists():
        return set()
    try:
        with open(BLOCKLIST_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return set()

    now = time.time()
    # Format: {"proxy_url": blocked_timestamp, ...}
    active = {url for url, ts in data.items() if now - ts < BLOCKLIST_TTL_SECONDS}
    return active


def save_blocklist(blocked: dict) -> None:
    """Save blocklist with timestamps."""
    try:
        BLOCKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BLOCKLIST_PATH, "w") as f:
            json.dump(blocked, f)
    except IOError as e:
        logger.warning(f"Failed to save blocklist: {e}")


def main() -> None:
    start = time.time()
    logger.info("Proxy refresh: starting")

    # Step 1: Fetch candidates
    candidates = fetch_candidates()
    if not candidates:
        logger.error("Proxy refresh: no candidates fetched — aborting")
        return
    logger.info(f"Proxy refresh: {len(candidates)} candidates fetched")

    # Step 2: Load current state
    working_list = load_json_list(WORKING_PATH)
    working_set = set(working_list)
    blocklist = load_blocklist()

    # Step 3: Dedup candidates — remove blocked and already-working
    new_candidates = [
        p for p in candidates
        if p not in blocklist and p not in working_set
    ]
    logger.info(
        f"Proxy refresh: {len(candidates)} total → "
        f"{len(candidates) - len(new_candidates)} deduped "
        f"({len(blocklist)} blocked, {len(working_set)} working) → "
        f"{len(new_candidates)} new to test"
    )

    # Step 4: Validate new candidates
    newly_passing = []
    if new_candidates:
        logger.info(f"Proxy refresh: validating {len(new_candidates)} new candidates…")
        newly_passing = validate_parallel(new_candidates, max_workers=50)
        logger.info(f"Proxy refresh: {len(newly_passing)} new proxies passed")

    # Step 5: Re-validate existing working proxies
    still_working = []
    if working_list:
        logger.info(f"Proxy refresh: re-validating {len(working_list)} existing proxies…")
        still_working = validate_parallel(working_list, max_workers=50)
        died = len(working_list) - len(still_working)
        logger.info(f"Proxy refresh: {len(still_working)} still working, {died} died")

    # Step 6: Merge results
    all_working = list(dict.fromkeys(still_working + newly_passing))  # dedup, preserve order
    save_cache(all_working, WORKING_PATH)

    # Step 7: Update blocklist — add failed new candidates
    now = time.time()
    newly_passing_set = set(newly_passing)
    # Load existing blocklist with timestamps (not just active ones)
    try:
        with open(BLOCKLIST_PATH) as f:
            blocklist_data = json.load(f)
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        blocklist_data = {}

    # Prune expired entries
    blocklist_data = {url: ts for url, ts in blocklist_data.items() if now - ts < BLOCKLIST_TTL_SECONDS}

    # Add newly failed candidates
    for p in new_candidates:
        if p not in newly_passing_set:
            blocklist_data[p] = now

    # Add died working proxies
    still_working_set = set(still_working)
    for p in working_list:
        if p not in still_working_set:
            blocklist_data[p] = now

    save_blocklist(blocklist_data)

    elapsed = time.time() - start
    logger.info(
        f"Proxy refresh: done in {elapsed:.0f}s — "
        f"{len(all_working)} working, {len(blocklist_data)} blocked"
    )


if __name__ == "__main__":
    main()
