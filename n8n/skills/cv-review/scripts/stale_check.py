#!/usr/bin/env python3
"""
LinkedIn Stale Check — verify if jobs are still accepting applications.

Downloads proxies from VPS, rotates them with LinkedIn cookies, checks each
job URL for closure signals. Marks closed jobs in MongoDB. Skips favorites
and recently-checked jobs.

Usage:
    python scripts/stale_check.py                    # check 20 jobs
    python scripts/stale_check.py --limit 50         # check 50
    python scripts/stale_check.py --status "ready for applying"
    python scripts/stale_check.py --dry-run           # list candidates only
    python scripts/stale_check.py --recheck-days 3    # re-check after 3 days (default: 7)
"""

import argparse
import http.cookiejar
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

# Force unbuffered output for background/pipe mode
print = partial(print, flush=True)

import requests
from bson import ObjectId
from pymongo import MongoClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[4]
COOKIES_PATH = PROJECT_ROOT / "data" / "linkedin-cookies.txt"
DOTENV_PATH = PROJECT_ROOT / ".env"

VPS_HOST = "root@72.61.92.76"
VPS_PROXIES_PATH = "/var/lib/scout/proxies.json"

CLOSURE_SIGNALS = [
    "no longer accepting applications",
    "this job has expired",
    "job is closed",
    "this job is no longer available",
    "position has been filled",
    "application deadline has passed",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Rate limiting
MIN_DELAY = 8
MAX_DELAY = 15
BATCH_SIZE = 10
BATCH_PAUSE_MIN = 30
BATCH_PAUSE_MAX = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    """Load .env file into os.environ."""
    if DOTENV_PATH.exists():
        for line in DOTENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def download_proxies() -> list[str]:
    """Download working proxy list from VPS."""
    try:
        result = subprocess.run(
            ["ssh", VPS_HOST, f"cat {VPS_PROXIES_PATH}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            proxies = json.loads(result.stdout)
            return proxies
    except Exception as e:
        print(f"  WARNING: Could not download proxies: {e}")
    return []


def load_cookies() -> http.cookiejar.MozillaCookieJar:
    """Load LinkedIn cookies from Netscape format file."""
    if not COOKIES_PATH.exists():
        print(f"  ERROR: Cookies not found at {COOKIES_PATH}")
        sys.exit(1)
    cj = http.cookiejar.MozillaCookieJar(str(COOKIES_PATH))
    cj.load(ignore_discard=True, ignore_expires=True)
    return cj


def check_job(job_url: str, cookies: http.cookiejar.MozillaCookieJar,
              proxy_url: str | None) -> tuple[str, str]:
    """
    Check a single job URL for closure signals.

    Returns:
        (status, reason) — status is "open", "closed", "error", "cookies_expired"
    """
    s = requests.Session()
    s.cookies = cookies
    s.headers.update(HEADERS)

    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    try:
        r = s.get(job_url, proxies=proxies, timeout=15, allow_redirects=True)

        if r.status_code == 404:
            return "closed", "404_not_found"

        if r.status_code == 429:
            return "error", "rate_limited_429"

        text = r.text.lower()

        # Check for cookie expiration (login wall)
        if "sign in" in text[:2000] and "job" not in text[:500]:
            return "cookies_expired", "login_wall_detected"

        # Check closure signals
        for signal in CLOSURE_SIGNALS:
            if signal in text:
                return "closed", signal

        return "open", "accepting_applications"

    except requests.exceptions.ProxyError:
        return "error", "proxy_failed"
    except requests.exceptions.ConnectTimeout:
        return "error", "connect_timeout"
    except requests.exceptions.ReadTimeout:
        return "error", "read_timeout"
    except Exception as e:
        return "error", str(e)[:80]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LinkedIn stale check for pipeline jobs")
    parser.add_argument("--limit", type=int, default=20, help="Max jobs to check (default: 20)")
    parser.add_argument("--status", default="under processing", help="MongoDB status filter")
    parser.add_argument("--recheck-days", type=int, default=7, help="Skip jobs checked within N days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without checking")
    parser.add_argument("--no-proxy", action="store_true", help="Skip proxies, check directly")
    parser.add_argument("--job-ids", nargs="+", help="Specific MongoDB ObjectIds to check")
    args = parser.parse_args()

    load_env()
    mongo_uri = os.environ.get("MONGODB_URI")
    if not mongo_uri:
        print("ERROR: MONGODB_URI not set")
        sys.exit(1)

    client = MongoClient(mongo_uri)
    db = client.get_default_database()
    col = db["level-2"]

    # Build query
    recheck_cutoff = datetime.now(timezone.utc) - timedelta(days=args.recheck_days)

    if args.job_ids:
        # Specific IDs mode — skip status/recheck filters
        oids = [ObjectId(jid) for jid in args.job_ids]
        query = {"_id": {"$in": oids}, "jobUrl": {"$exists": True, "$ne": ""}}
    else:
        # Discovery mode — skip favorites, skip recently checked
        query = {
            "status": args.status,
            "jobUrl": {"$exists": True, "$ne": ""},
            "$or": [
                {"stale_checked_at": {"$exists": False}},
                {"stale_checked_at": {"$lt": recheck_cutoff}},
            ],
        }

    jobs = list(col.find(
        query,
        {"title": 1, "company": 1, "jobUrl": 1, "is_favorite": 1, "stale_checked_at": 1},
    ).sort("createdAt", -1).limit(args.limit))

    print(f"=== Stale Check ===")
    print(f"Status filter: {args.status}")
    print(f"Recheck window: {args.recheck_days} days")
    print(f"Candidates: {len(jobs)}")

    if not jobs:
        print("No jobs to check.")
        return

    if args.dry_run:
        for i, j in enumerate(jobs, 1):
            fav = " [FAV]" if j.get("is_favorite") else ""
            last = j.get("stale_checked_at", "never")
            print(f"  {i}. {j['company']} — {j['title']}{fav} (last: {last})")
        return

    # Download proxies
    proxies = []
    if not args.no_proxy:
        print("Downloading proxies from VPS...")
        proxies = download_proxies()
        print(f"  {len(proxies)} proxies loaded")

    # Load cookies
    cookies = load_cookies()
    print(f"  Cookies loaded from {COOKIES_PATH.name}")

    # Run checks
    stats = {"open": 0, "closed": 0, "error": 0, "skipped_fav": 0}
    closed_jobs = []
    start_time = time.time()

    for i, job in enumerate(jobs, 1):
        job_id = str(job["_id"])
        company = job.get("company", "?")
        title = job.get("title", "?")
        url = job["jobUrl"]
        is_fav = job.get("is_favorite", False)

        # Pick proxy (round-robin)
        proxy = proxies[(i - 1) % len(proxies)] if proxies else None

        # Check
        status, reason = check_job(url, cookies, proxy)

        # Handle cookies expired — stop immediately
        if status == "cookies_expired":
            print(f"\n  STOP: LinkedIn cookies expired. Refresh at {COOKIES_PATH}")
            print(f"  Checked {i-1}/{len(jobs)} before stopping.")
            break

        # Update stale_checked_at regardless of result
        col.update_one(
            {"_id": job["_id"]},
            {"$set": {"stale_checked_at": datetime.now(timezone.utc), "stale_check_result": status}},
        )

        if status == "closed":
            if is_fav:
                # Keep favorites, just mark as checked
                stats["skipped_fav"] += 1
                icon = "⭐"
                print(f"  [{i}/{len(jobs)}] {icon} {company} — {title} → CLOSED but FAVORITE (kept)")
            else:
                # Discard non-favorites
                col.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "status": "closed",
                        "closed_detected_at": datetime.now(timezone.utc),
                        "closed_reason": reason,
                    }},
                )
                stats["closed"] += 1
                closed_jobs.append(f"{company} — {title} ({reason})")
                print(f"  [{i}/{len(jobs)}] CLOSED {company} — {title} ({reason})")
        elif status == "open":
            stats["open"] += 1
            print(f"  [{i}/{len(jobs)}] OPEN  {company} — {title}")
        else:
            stats["error"] += 1
            print(f"  [{i}/{len(jobs)}] ERROR {company} — {title} ({reason})")

        # Rate limiting
        if i < len(jobs):
            if i % BATCH_SIZE == 0:
                pause = random.uniform(BATCH_PAUSE_MIN, BATCH_PAUSE_MAX)
                print(f"  --- batch pause {pause:.0f}s ---")
                time.sleep(pause)
            else:
                delay = random.gauss((MIN_DELAY + MAX_DELAY) / 2, 2)
                delay = max(MIN_DELAY, min(MAX_DELAY, delay))
                time.sleep(delay)

    elapsed = time.time() - start_time
    checked = stats["open"] + stats["closed"] + stats["error"] + stats["skipped_fav"]

    print(f"\n=== Summary ({elapsed:.0f}s) ===")
    print(f"Checked: {checked}/{len(jobs)}")
    print(f"Open: {stats['open']} | Closed: {stats['closed']} | Favorites kept: {stats['skipped_fav']} | Errors: {stats['error']}")
    if closed_jobs:
        print(f"\nDiscarded ({len(closed_jobs)}):")
        for c in closed_jobs:
            print(f"  - {c}")


if __name__ == "__main__":
    main()
