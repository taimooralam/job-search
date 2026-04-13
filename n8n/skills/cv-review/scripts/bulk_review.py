#!/usr/bin/env python3
"""
Bulk CV Review — run independent hiring-manager reviews locally via Codex CLI.

Queries MongoDB for jobs with generated CVs but no review, builds prompts
using the same shared logic as CVReviewService, pipes each through
`codex exec`, and persists structured reviews back to MongoDB.

Runs locally on Mac where Codex OAuth auth works (single process, no token
rotation conflict). Replaces VPS batch pipeline Step 8 which fails due to
multi-container OAuth token contention. See openai/codex#10332.

Usage:
    python scripts/bulk_review.py                              # all unreviewed (limit 20)
    python scripts/bulk_review.py --limit 5                    # first 5
    python scripts/bulk_review.py --company "Google"           # filter by company
    python scripts/bulk_review.py --status "ready for applying"
    python scripts/bulk_review.py --re-review --limit 10       # overwrite existing reviews
    python scripts/bulk_review.py --dry-run                    # list candidates only
    python scripts/bulk_review.py --job-id 6612abc123def456    # single job
"""

import argparse
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — add repo root so src.* imports work
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _SKILL_DIR.parent.parent.parent  # n8n/skills/cv-review/scripts -> repo root

sys.path.insert(0, str(_REPO_ROOT))

# Load .env from repo root
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

from bson import ObjectId
from pymongo import MongoClient

from src.services.cv_review_core import (
    DEFAULT_CV_REVIEW_MODEL,
    REVIEWER_SYSTEM_PROMPT,
    build_cv_review_document,
    build_user_prompt,
    derive_bridge_quality_score,
    derive_failure_modes,
    derive_headline_evidence_bounded,
    parse_review_json,
)


# ---------------------------------------------------------------------------
# MongoDB query builder
# ---------------------------------------------------------------------------

def build_query(args: argparse.Namespace) -> dict:
    """Build MongoDB query from CLI args."""
    if args.job_id:
        ids = [ObjectId(jid) for jid in args.job_id]
        if len(ids) == 1:
            return {"_id": ids[0]}
        return {"_id": {"$in": ids}}

    # CV text can be in cv_text or cv_editor_state
    cv_condition = {"$or": [
        {"cv_text": {"$exists": True, "$ne": ""}},
        {"cv_editor_state.text": {"$exists": True, "$ne": ""}},
        {"cv_editor_state.content": {"$exists": True, "$ne": ""}},
    ]}

    query: dict = {**cv_condition, "extracted_jd": {"$exists": True, "$ne": {}}}

    if not args.re_review:
        query["cv_review"] = {"$exists": False}
    if args.company:
        query["company"] = {"$regex": re.escape(args.company), "$options": "i"}
    if args.status:
        query["status"] = args.status
    if args.tier:
        query["tier"] = args.tier
    if args.since:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.since)
        query["createdAt"] = {"$gte": cutoff}

    return query


# ---------------------------------------------------------------------------
# Job field helpers
# ---------------------------------------------------------------------------

# Projection — fetch only what we need
PROJECTION = {
    "company": 1, "title": 1, "location": 1, "tier": 1, "status": 1,
    "cv_text": 1, "cv_editor_state": 1, "extracted_jd": 1,
    "pain_points": 1, "company_research": 1, "createdAt": 1,
}


def get_cv_text(job: dict) -> str | None:
    """Extract CV text from job — same fallback logic as CVReviewService."""
    cv_text = job.get("cv_text") or None
    if not cv_text:
        editor_state = job.get("cv_editor_state") or {}
        if isinstance(editor_state, dict):
            cv_text = editor_state.get("text") or editor_state.get("content") or None
    return cv_text


def validate_extracted_jd(jd: dict | None) -> bool:
    """Require at least one substantive field for a useful review."""
    if not jd or not isinstance(jd, dict):
        return False
    return any(jd.get(f) for f in (
        "responsibilities", "technical_skills", "top_keywords", "ideal_candidate_profile",
    ))


# ---------------------------------------------------------------------------
# Codex invocation
# ---------------------------------------------------------------------------

def run_codex_review(full_prompt: str, model: str) -> tuple[dict | None, str | None]:
    """Run codex exec CLI and return (review_dict, error_str)."""
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    env["NO_COLOR"] = "1"

    try:
        result = subprocess.run(
            ["codex", "exec", "-m", model, "--full-auto"],
            input=full_prompt,
            text=True,
            capture_output=True,
            timeout=300,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout after 300s"
    except FileNotFoundError:
        return None, "codex not found — install with: npm i -g @openai/codex"

    if result.returncode != 0:
        error = result.stderr.strip() or f"exit code {result.returncode}"
        return None, error

    raw = result.stdout.strip()
    if not raw:
        return None, "empty response"

    review = parse_review_json(raw)
    if review is None:
        return None, f"invalid JSON: {raw[:200]}"

    return review, None


def classify_failure(error: str) -> str:
    """Classify codex failure: 'auth', 'timeout', or 'other'."""
    if not error:
        return "other"
    lower = error.lower()
    if any(p in lower for p in ("401", "unauthorized", "token expired", "authentication failed")):
        return "auth"
    if "timeout" in lower:
        return "timeout"
    return "other"


# ---------------------------------------------------------------------------
# Resource loaders (run once per batch)
# ---------------------------------------------------------------------------

def load_master_cv_text() -> str:
    """Load master CV text — try MasterCVStore, fallback to direct file."""
    try:
        from src.common.master_cv_store import MasterCVStore
        text = MasterCVStore().get_candidate_profile_text()
        if text:
            return text
    except Exception:
        pass

    # Fallback: read master-cv.md directly
    path = _REPO_ROOT / "data" / "master-cv" / "master-cv.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def load_project_texts() -> dict[str, str]:
    """Load AI project markdown files."""
    project_dir = _REPO_ROOT / "data" / "master-cv" / "projects"
    texts: dict[str, str] = {}
    for name in ("commander4.md", "lantern.md"):
        path = project_dir / name
        if path.exists():
            try:
                texts[name] = path.read_text(encoding="utf-8")[:3000]
            except OSError:
                pass
    return texts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk CV review via local Codex CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--limit", type=int, default=20, help="Max jobs to review (default: 20)")
    parser.add_argument("--status", help="Filter by job status (e.g. 'ready for applying')")
    parser.add_argument("--tier", help="Filter by tier (e.g. 'A', 'B')")
    parser.add_argument("--company", help="Filter by company name (substring, case-insensitive)")
    parser.add_argument("--since", type=int, help="Only jobs created in last N days")
    parser.add_argument("--job-id", nargs="+", help="Review specific job(s) by _id (one or more)")
    parser.add_argument("--re-review", action="store_true", help="Re-review jobs that already have cv_review")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without reviewing")
    parser.add_argument("--model", default=None, help="Codex model override (default: CV_REVIEW_MODEL env or gpt-5.2)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    model = args.model or os.getenv("CV_REVIEW_MODEL", DEFAULT_CV_REVIEW_MODEL)

    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        print("ERROR: MONGODB_URI not set")
        sys.exit(1)

    client = MongoClient(mongo_uri)
    db = client.get_default_database()
    collection = db["level-2"]

    query = build_query(args)
    jobs = list(
        collection.find(query, PROJECTION)
        .sort("createdAt", -1)
        .limit(args.limit)
    )

    print(f"Found {len(jobs)} candidate(s) for review")

    if args.dry_run:
        for job in jobs:
            _id = job["_id"]
            company = job.get("company", "?")
            title = job.get("title", "?")
            location = job.get("location", "?")
            has_review = "cv_review" in job if args.re_review else False
            marker = " [has review]" if has_review else ""
            print(f"  {_id} | {company} — {title} ({location}){marker}")
        return

    if not jobs:
        print("No jobs to review!")
        return

    # Load shared resources once
    print("Loading master CV and project files...")
    master_cv_text = load_master_cv_text()
    project_texts = load_project_texts()
    if master_cv_text:
        print(f"  Master CV: {len(master_cv_text)} chars")
    else:
        print("  WARNING: Master CV not available — hallucination checks will be limited")
    print(f"  Project files: {list(project_texts.keys())}")

    # Review loop
    reviewed = 0
    failed = 0
    skipped = 0
    verdicts: Counter = Counter()
    total_start = time.time()

    for i, job in enumerate(jobs, 1):
        job_id = job["_id"]
        company = job.get("company", "?")
        title = job.get("title", "?")

        print(f"\n[{i}/{len(jobs)}] {company} — {title} ({job_id})")

        # Validate required fields
        cv_text = get_cv_text(job)
        if not cv_text:
            print("  SKIP: no cv_text")
            skipped += 1
            continue

        extracted_jd = job.get("extracted_jd")
        if not validate_extracted_jd(extracted_jd):
            print("  SKIP: extracted_jd missing or incomplete")
            skipped += 1
            continue

        # Build prompt
        user_prompt = build_user_prompt(
            cv_text=cv_text,
            extracted_jd=extracted_jd,
            master_cv_text=master_cv_text,
            pain_points=job.get("pain_points"),
            company_research=job.get("company_research"),
            project_texts=project_texts,
        )
        full_prompt = (
            f"{REVIEWER_SYSTEM_PROMPT}\n\n"
            f"{user_prompt}\n\n"
            "IMPORTANT: Return ONLY valid JSON matching the schema above. "
            "No markdown, no explanation, just the JSON object."
        )

        if args.verbose:
            print(f"  Prompt: {len(full_prompt)} chars")
        print(f"  Calling codex ({model})...", end="", flush=True)

        t_start = time.time()
        review, error = run_codex_review(full_prompt, model)
        duration = time.time() - t_start

        if error:
            print(f" FAIL ({duration:.0f}s): {error}")
            cls = classify_failure(error)
            if cls == "auth":
                print("\n*** Auth failure detected — aborting batch ***")
                print("Re-authenticate Codex and retry.")
                break
            failed += 1
            continue

        # Derive taxonomy
        failure_modes = derive_failure_modes(review)
        headline_bounded = derive_headline_evidence_bounded(review)
        bridge_score = derive_bridge_quality_score(review)

        # Persist to MongoDB
        cv_review_doc = build_cv_review_document(
            review, model, failure_modes, headline_bounded, bridge_score,
        )
        collection.update_one({"_id": job_id}, {"$set": {"cv_review": cv_review_doc}})

        verdict = review.get("verdict", "?")
        confidence = review.get("confidence", 0)
        interview = "YES" if review.get("would_interview") else "NO"
        verdicts[verdict] += 1
        reviewed += 1

        print(f" {verdict} | conf={confidence:.2f} | interview={interview} | {duration:.0f}s")
        if failure_modes:
            print(f"  Failure modes: {', '.join(failure_modes)}")

    # Summary
    total_time = time.time() - total_start
    print(f"\n{'='*50}")
    print(f"Bulk Review Summary")
    print(f"{'='*50}")
    print(f"Reviewed: {reviewed}  |  Failed: {failed}  |  Skipped: {skipped}")
    if verdicts:
        for v in ("STRONG_MATCH", "GOOD_MATCH", "NEEDS_WORK", "WEAK_MATCH"):
            if verdicts[v]:
                print(f"  {v}: {verdicts[v]}")
    print(f"Total time: {total_time/60:.1f}m")


if __name__ == "__main__":
    main()
