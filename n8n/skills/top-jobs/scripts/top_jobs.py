#!/usr/bin/env python3
"""
Top jobs query CLI for MongoDB-backed job search collections.

Queries the `jobs.level-2` and/or `jobs.level-1` collections using tier-aware
waterfall selection and flexible filters. Results can be printed as a table,
JSON, CSV, or newline-delimited IDs. Optional actions:

- `--promote`: copy matched level-1 jobs into level-2 and mark them promoted
- `--batch`: queue matched level-2 jobs into the batch pipeline runner
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Path setup — match skill scripts that resolve repo root and load .env
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _SKILL_DIR.parent.parent.parent

sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

import requests
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

DEFAULT_LIMIT = 50
DEFAULT_SORT = "date"
DEFAULT_COLLECTION = "level-2"
DEFAULT_FORMAT = "table"
DEFAULT_RUNNER_URL = "https://runner.uqab.digital"
EXCLUDED_STATUSES = ["applied", "discarded", "closed", "rejected", "skipped"]

LOCATION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "eea": (
        "Germany", "Austria", "Netherlands", "Ireland", "France", "Spain",
        "Italy", "Portugal", "Sweden", "Denmark", "Finland", "Norway",
        "Belgium", "Luxembourg", "Poland", "Czech Republic", "Romania",
        "Hungary", "Greece", "Croatia", "Bulgaria", "Switzerland",
        "United Kingdom",
    ),
    "gcc": (
        "UAE", "United Arab Emirates", "Dubai", "Abu Dhabi", "Saudi Arabia",
        "Riyadh", "Jeddah", "Dammam", "Khobar", "Qatar", "Bahrain",
        "Kuwait", "Oman",
    ),
    "pk": (
        "Karachi", "Lahore", "Islamabad", "Rawalpindi", "Peshawar",
        "Faisalabad",
    ),
    "ksa": ("Saudi Arabia", "Riyadh", "Jeddah", "Dammam", "Khobar"),
    "uae": ("UAE", "United Arab Emirates", "Dubai", "Abu Dhabi"),
}

CATEGORY_PATTERNS: dict[str, str] = {
    "architect": r"architect|agentic",
    "lead": r"lead|tech\.lead|team\.lead|engineering\.lead",
    "staff": r"staff|principal|forward\.deployed",
    "head": r"head|director|vp|vice\.president|chief|cto|cio|caio",
    "manager": r"manager",
}


@dataclass(frozen=True)
class TierSpec:
    """Static definition for a tier query."""

    code: str
    label: str
    title_regex: str | None
    regions: tuple[str, ...] | None = None
    min_score: int | None = None
    require_ai: bool = False
    require_cv: bool = False
    category: str | None = None


@dataclass(frozen=True)
class ProfileSpec:
    """Title-family profile definition."""

    code: str
    label: str
    title_regex: str | None
    regions: tuple[str, ...] | None = None
    min_score: int | None = None
    require_ai: bool = False
    require_cv: bool = False
    category: str | None = None


TIERS: dict[str, TierSpec] = {
    "T1": TierSpec(
        code="T1",
        label="T1-AI Architect",
        title_regex=r"(ai|genai|llm|ml|artificial.intelligence|generative.ai).*(architect)|(architect).*(ai|genai|llm|ml)|agentic.*(architect|engineer)",
        regions=("remote", "eea"),
        category="architect",
    ),
    "T2": TierSpec(
        code="T2",
        label="T2-AI Lead",
        title_regex=r"(lead|tech.lead|team.lead|engineering.lead).*(ai|genai|llm|ml|platform)|(ai|genai|llm|ml).*(lead|tech.lead|engineering.lead)|ai.engineering.*(manager|lead)",
        regions=("remote", "eea"),
        category="lead",
    ),
    "T3": TierSpec(
        code="T3",
        label="T3-Staff/Principal AI",
        title_regex=r"(staff|principal).*(ai|genai|llm|ml|platform).*(engineer|developer)|(senior|staff|principal).*(ai|genai|llm).*(engineer|architect)|forward.deployed.*(ai|engineer)",
        regions=("remote", "eea"),
        category="staff",
    ),
    "T4": TierSpec(
        code="T4",
        label="T4-Head/Director",
        title_regex=r"(head|director|vp|vice.president|chief|cto).*(ai|engineering|software|technology|data|digital|platform|ml)|(cto|cio|caio)",
        regions=("gcc", "pk"),
        category="head",
    ),
    "T5": TierSpec(
        code="T5",
        label="T5-High-Score AI",
        title_regex=None,
        min_score=65,
        require_ai=True,
        require_cv=True,
    ),
    "T6": TierSpec(
        code="T6",
        label="T6-Engineering Manager + AI",
        title_regex=r"engineering.manager|manager.*(ai|ml|genai|software|platform)",
        regions=("remote", "eea"),
        require_ai=True,
        category="manager",
    ),
    "T7": TierSpec(
        code="T7",
        label="T7-GCC/PK Leadership",
        title_regex=r"(head|director|vp|cto).*(engineering|software|technology|platform)",
        regions=("gcc", "pk"),
        min_score=40,
        category="head",
    ),
}
TIER_ORDER = tuple(TIERS.keys())

PROFILES: dict[str, ProfileSpec] = {
    "tech-lead": ProfileSpec(
        code="tech-lead",
        label="P-Tech Lead",
        title_regex=r"tech[ ./-]*lead|technical[ ./-]*lead|engineering[ ./-]*lead|software[ ./-]*engineering[ ./-]*lead|data[ ./-]*engineering[ ./-]*lead|platform[ ./-]*engineering[ ./-]*lead|(?:development|engineering|software|data|platform|backend|frontend|ai|ml)[ ./-]*team[ ./-]*lead|lead[ ./-]*(?:software|platform|backend|frontend|full.?stack|data|ml|ai|application|systems?)?[ ./-]*(?:engineer|developer)|(?:software|platform|backend|frontend|full.?stack|data|ml|ai|application|systems?|developer)[ ./-]*(?:lead|technical[ ./-]*lead|tech[ ./-]*lead|engineering[ ./-]*lead)",
        category="lead",
    ),
    "architect": ProfileSpec(
        code="architect",
        label="P-Architect",
        title_regex=r"architect",
        category="architect",
    ),
    "staff-principal": ProfileSpec(
        code="staff-principal",
        label="P-Staff/Principal",
        title_regex=r"staff|principal|distinguished|fellow",
        category="staff",
    ),
    "head-director": ProfileSpec(
        code="head-director",
        label="P-Head/Director",
        title_regex=r"head|director|vp|vice[ ./-]*president|chief|cto|cio|caio",
        category="head",
    ),
    "engineering-manager": ProfileSpec(
        code="engineering-manager",
        label="P-Engineering Manager",
        title_regex=r"engineering[ ./-]*manager|software[ ./-]*engineering[ ./-]*manager|senior[ ./-]*engineering[ ./-]*manager|manager[, /-]*software[ ./-]*engineering|observability[ ./-]*engineering[ ./-]*manager|sr[ ./-]*engineering[ ./-]*manager",
        category="manager",
    ),
}
PROFILE_ORDER = tuple(PROFILES.keys())


def eprint(message: str) -> None:
    """Print a progress or error message to stderr."""
    print(message, file=sys.stderr)


def parse_tiers(raw: str) -> list[str]:
    """Parse a comma-separated tier list."""
    values = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("tier list cannot be empty")
    if "ALL" in values:
        return list(TIER_ORDER)
    invalid = [value for value in values if value not in TIERS]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid tier value(s): {', '.join(invalid)}")
    return values


def parse_regions(raw: str) -> list[str]:
    """Parse a comma-separated region override."""
    allowed = {"eea", "gcc", "pk", "remote", "ksa", "uae", "global"}
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    invalid = [value for value in values if value not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid region value(s): {', '.join(invalid)}")
    if "global" in values:
        return ["global"]
    return values


def parse_categories(raw: str) -> list[str]:
    """Parse a comma-separated category filter."""
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    invalid = [value for value in values if value not in CATEGORY_PATTERNS]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid category value(s): {', '.join(invalid)}")
    return values


def parse_profiles(raw: str) -> list[str]:
    """Parse a comma-separated profile list."""
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    invalid = [value for value in values if value not in PROFILES]
    if invalid:
        raise argparse.ArgumentTypeError(f"invalid profile value(s): {', '.join(invalid)}")
    return values


def parse_statuses(raw: str | None) -> list[str] | None:
    """Parse one or more exact status filters."""
    if not raw:
        return None
    values = [part.strip() for part in raw.split(",") if part.strip()]
    return values or None


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Query MongoDB for top jobs using tier-aware filters",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max jobs to return (default: 50)")
    parser.add_argument("--tier", type=parse_tiers, help="Comma-separated tiers T1-T7 or 'all' (default: all)")
    parser.add_argument("--profile", type=parse_profiles, help="Named role profile(s): tech-lead, architect, staff-principal, head-director, engineering-manager")
    parser.add_argument("--region", type=parse_regions, help="Location override: eea,gcc,pk,remote,ksa,uae,global")
    parser.add_argument("--category", type=parse_categories, help="Title category filter: architect,lead,staff,head,manager")
    parser.add_argument("--days", type=int, help="Only jobs created within the last N days")
    parser.add_argument("--min-score", type=float, help="Minimum score threshold")
    parser.add_argument("--require-cv", action="store_true", help="Only jobs with generated CV text")
    parser.add_argument("--status", help="Exact status filter, optionally comma-separated")
    parser.add_argument("--collection", choices=["level-2", "level-1", "both"], default=DEFAULT_COLLECTION, help="Collection to query (default: level-2)")
    parser.add_argument("--sort", choices=["score", "date", "score-date"], default=DEFAULT_SORT, help="Sort mode (default: date)")
    parser.add_argument("--company", help="Case-insensitive regex for company name")
    parser.add_argument("--title", help="Custom title regex override")
    parser.add_argument("--format", choices=["table", "json", "csv", "ids"], default=DEFAULT_FORMAT, help="Output format (default: table)")
    parser.add_argument("--ai-only", action="store_true", help="Only jobs with is_ai_job=true")
    parser.add_argument("--not-favorite", action="store_true", help="Exclude jobs marked favorite/starred")
    parser.add_argument("--no-header", action="store_true", help="Suppress header row in table output")
    parser.add_argument("--promote", action="store_true", help="Promote matched level-1 jobs into level-2")
    parser.add_argument("--batch", action="store_true", help="Queue matched jobs for batch pipeline processing")
    args = parser.parse_args()
    args.explicit_tier = args.tier is not None
    if args.profile and args.explicit_tier:
        parser.error("--profile cannot be combined with --tier; use one or the other")
    if args.tier is None:
        args.tier = list(TIER_ORDER)
    if args.limit <= 0:
        parser.error("--limit must be greater than 0")
    if args.days is not None and args.days <= 0:
        parser.error("--days must be greater than 0")
    return args


def get_database() -> Database:
    """Create and validate a MongoDB connection."""
    mongo_uri = os.getenv("MONGODB_URI")
    if not mongo_uri:
        raise RuntimeError("MONGODB_URI not set in environment or repo-root .env")
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
        return client["jobs"]
    except PyMongoError as exc:
        raise RuntimeError(f"MongoDB connection failed: {exc}") from exc


def build_regex_clause(field: str, pattern: str) -> dict[str, Any]:
    """Build a case-insensitive regex filter."""
    return {field: {"$regex": pattern, "$options": "i"}}


def combine_and(conditions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Combine a sequence of conditions into a MongoDB query."""
    active = [condition for condition in conditions if condition]
    if not active:
        return {}
    if len(active) == 1:
        return active[0]
    return {"$and": active}


def build_remote_clause() -> dict[str, Any]:
    """Build the remote location clause."""
    return {
        "$or": [
            {"location": {"$regex": r"remote|worldwide|anywhere|global", "$options": "i"}},
            {"location": {"$exists": False}},
            {"location": None},
            {"location": ""},
        ]
    }


def build_region_clause(regions: Sequence[str] | None) -> dict[str, Any]:
    """Build a location clause for one or more regions."""
    if not regions or "global" in regions:
        return {}

    clauses: list[dict[str, Any]] = []
    for region in regions:
        if region == "remote":
            clauses.append(build_remote_clause())
            continue
        keywords = LOCATION_KEYWORDS.get(region, ())
        if keywords:
            pattern = "|".join(re.escape(keyword) for keyword in keywords)
            clauses.append(build_regex_clause("location", pattern))

    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def build_category_clause(categories: Sequence[str] | None) -> dict[str, Any]:
    """Build a title category filter."""
    if not categories:
        return {}
    pattern = "|".join(f"(?:{CATEGORY_PATTERNS[category]})" for category in categories)
    return build_regex_clause("title", pattern)


def build_cv_clause() -> dict[str, Any]:
    """Require generated CV content."""
    return {
        "$or": [
            {"cv_text": {"$exists": True, "$ne": ""}},
            {"cv_editor_state.text": {"$exists": True, "$ne": ""}},
            {"cv_editor_state.content": {"$exists": True, "$ne": ""}},
        ]
    }


def build_query(args: argparse.Namespace, spec: TierSpec | ProfileSpec) -> dict[str, Any]:
    """Build the MongoDB query for one tier or profile."""
    conditions: list[dict[str, Any]] = []
    statuses = parse_statuses(args.status)
    if statuses:
        conditions.append({"status": {"$in": statuses}})
    else:
        conditions.append({"status": {"$nin": EXCLUDED_STATUSES}})

    if args.days:
        cutoff = datetime.now(UTC) - timedelta(days=args.days)
        conditions.append({"createdAt": {"$gte": cutoff}})

    score_floor = spec.min_score
    if args.min_score is not None:
        score_floor = max(float(args.min_score), float(score_floor or args.min_score))
    if score_floor is not None:
        conditions.append({"score": {"$gte": score_floor}})

    if args.ai_only or spec.require_ai:
        conditions.append({"is_ai_job": True})
    if args.require_cv or spec.require_cv:
        conditions.append(build_cv_clause())
    if args.not_favorite:
        conditions.append(
            {
                "$and": [
                    {"$or": [{"starred": {"$exists": False}}, {"starred": {"$ne": True}}]},
                    {"$or": [{"is_favorite": {"$exists": False}}, {"is_favorite": {"$ne": True}}]},
                ]
            }
        )
    if args.company:
        conditions.append(build_regex_clause("company", args.company))

    title_pattern = args.title or spec.title_regex
    if title_pattern:
        conditions.append(build_regex_clause("title", title_pattern))
    if args.category:
        conditions.append(build_category_clause(args.category))

    regions = args.region or list(spec.regions or [])
    region_clause = build_region_clause(regions)
    if region_clause:
        conditions.append(region_clause)

    return combine_and(conditions)


def mongo_sort(sort_mode: str) -> list[tuple[str, int]]:
    """Return the MongoDB sort sequence."""
    if sort_mode == "score":
        return [("score", DESCENDING), ("createdAt", DESCENDING)]
    if sort_mode == "score-date":
        return [("score", DESCENDING), ("createdAt", DESCENDING)]
    return [("createdAt", DESCENDING), ("score", DESCENDING)]


def collection_order(collection_name: str) -> list[str]:
    """Return the preferred collection query order."""
    if collection_name == "both":
        return ["level-2", "level-1"]
    return [collection_name]


def normalize_for_dedupe(text: str | None) -> str:
    """Normalize text for company/title dedupe fallback."""
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def result_identity(doc: dict[str, Any]) -> str:
    """Build a stable dedupe identity for merged results."""
    dedupe_key = doc.get("dedupeKey")
    if dedupe_key:
        return f"dedupe:{dedupe_key}"
    company = normalize_for_dedupe(doc.get("company"))
    title = normalize_for_dedupe(doc.get("title"))
    if company or title:
        return f"ct:{company}|{title}"
    return f"id:{doc.get('_id')}"


def extract_date(doc: dict[str, Any]) -> datetime:
    """Extract the best datetime value from a document."""
    for field in ("createdAt", "updatedAt", "promoted_at", "discovered_at", "last_seen_at", "postedDate"):
        value = doc.get(field)
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.astimezone(UTC)
            except ValueError:
                continue
    return datetime.fromtimestamp(0, tz=UTC)


def numeric_score(value: Any) -> float:
    """Coerce a score-like value into a float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def sort_documents(docs: list[dict[str, Any]], sort_mode: str) -> list[dict[str, Any]]:
    """Sort merged documents in Python for consistent cross-collection ordering."""
    if sort_mode == "date":
        return sorted(docs, key=lambda doc: (extract_date(doc), numeric_score(doc.get("score"))), reverse=True)
    return sorted(docs, key=lambda doc: (numeric_score(doc.get("score")), extract_date(doc)), reverse=True)


def fetch_spec_results(db: Database, args: argparse.Namespace, spec: TierSpec | ProfileSpec, remaining: int, seen: set[str]) -> list[dict[str, Any]]:
    """Fetch results for one tier or profile across the configured collection(s)."""
    fetch_limit = max(remaining * 6, 100)
    query = build_query(args, spec)
    merged: list[dict[str, Any]] = []

    for name in collection_order(args.collection):
        collection = db[name]
        docs = list(collection.find(query).sort(mongo_sort(args.sort)).limit(fetch_limit))
        for doc in docs:
            doc["_collection"] = name
        merged.extend(docs)

    selected: list[dict[str, Any]] = []
    local_seen = set(seen)
    for doc in sort_documents(merged, args.sort):
        identity = result_identity(doc)
        if identity in local_seen:
            continue
        local_seen.add(identity)
        doc["_matched_tier"] = spec.code
        doc["_matched_tier_label"] = spec.label
        selected.append(doc)
        if len(selected) >= remaining:
            break
    return selected


def query_profiles(db: Database, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Run the profile waterfall query and return the selected jobs."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for profile_code in args.profile or []:
        remaining = args.limit - len(selected)
        if remaining <= 0:
            break
        profile_docs = fetch_spec_results(db, args, PROFILES[profile_code], remaining, seen)
        for doc in profile_docs:
            seen.add(result_identity(doc))
        selected.extend(profile_docs)
        eprint(f"[query] profile {profile_code}: {len(profile_docs)} match(es), total={len(selected)}/{args.limit}")
    return selected[: args.limit]


def query_jobs(db: Database, args: argparse.Namespace) -> list[dict[str, Any]]:
    """Run the tier waterfall query and return the selected jobs."""
    if args.profile:
        return query_profiles(db, args)

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for tier_code in args.tier:
        remaining = args.limit - len(selected)
        if remaining <= 0:
            break
        tier_docs = fetch_spec_results(db, args, TIERS[tier_code], remaining, seen)
        for doc in tier_docs:
            seen.add(result_identity(doc))
        selected.extend(tier_docs)
        eprint(f"[query] {tier_code}: {len(tier_docs)} match(es), total={len(selected)}/{args.limit}")
    return selected[: args.limit]


def clean_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove helper metadata before serialization or insertion."""
    cleaned = dict(doc)
    for key in ("_collection", "_matched_tier", "_matched_tier_label"):
        cleaned.pop(key, None)
    return cleaned


def find_existing_level2(level2: Collection, doc: dict[str, Any]) -> dict[str, Any] | None:
    """Find an existing level-2 match by dedupeKey or title+company."""
    dedupe_key = doc.get("dedupeKey")
    if dedupe_key:
        existing = level2.find_one({"dedupeKey": dedupe_key}, {"_id": 1})
        if existing:
            return existing

    title = doc.get("title")
    company = doc.get("company")
    if title and company:
        return level2.find_one(
            {
                "title": {"$regex": f"^{re.escape(title)}$", "$options": "i"},
                "company": {"$regex": f"^{re.escape(company)}$", "$options": "i"},
            },
            {"_id": 1},
        )
    return None


def promote_results(db: Database, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Promote matched level-1 jobs into level-2 when needed."""
    level1 = db["level-1"]
    level2 = db["level-2"]
    now = datetime.now(UTC)
    stats = {"checked": 0, "promoted": 0, "already_present": 0, "skipped": 0, "mapping": {}}

    for doc in results:
        if doc.get("_collection") != "level-1":
            stats["skipped"] += 1
            continue

        stats["checked"] += 1
        original_id = doc.get("_id")
        existing = find_existing_level2(level2, doc)
        if existing:
            level1.update_one(
                {"_id": original_id},
                {
                    "$set": {
                        "promoted_to_level2": True,
                        "promoted_job_id": existing["_id"],
                        "promoted_at": now,
                    }
                },
            )
            stats["already_present"] += 1
            stats["mapping"][str(original_id)] = str(existing["_id"])
            continue

        new_doc = clean_document(doc)
        new_doc.pop("_id", None)
        new_doc["status"] = "under processing"
        new_doc["source"] = "level1_promoted"
        new_doc["promoted_from_level1"] = True
        new_doc["level1_job_id"] = original_id
        new_doc["updatedAt"] = now
        result = level2.insert_one(new_doc)
        level1.update_one(
            {"_id": original_id},
            {
                "$set": {
                    "promoted_to_level2": True,
                    "promoted_job_id": result.inserted_id,
                    "promoted_at": now,
                }
            },
        )
        stats["promoted"] += 1
        stats["mapping"][str(original_id)] = str(result.inserted_id)

    return stats


def resolve_batch_ids(results: list[dict[str, Any]], mapping: dict[str, str]) -> tuple[list[str], int]:
    """Resolve the level-2 job IDs that can be queued."""
    resolved: list[str] = []
    skipped = 0
    seen = set()

    for doc in results:
        target_id: str | None = None
        if doc.get("_collection") == "level-2":
            target_id = str(doc["_id"])
        elif doc.get("_collection") == "level-1":
            target_id = mapping.get(str(doc["_id"]))
            if not target_id and doc.get("promoted_job_id"):
                target_id = str(doc["promoted_job_id"])

        if not target_id:
            skipped += 1
            continue
        if target_id in seen:
            continue
        seen.add(target_id)
        resolved.append(target_id)

    return resolved, skipped


def trigger_batch(job_ids: Sequence[str]) -> dict[str, int]:
    """Queue jobs in the batch pipeline runner."""
    runner_secret = os.getenv("RUNNER_API_SECRET", "")
    runner_url = os.getenv("RUNNER_URL", DEFAULT_RUNNER_URL)
    if not runner_secret:
        raise RuntimeError("RUNNER_API_SECRET not set; cannot queue batch pipeline")

    stats = {"queued": 0, "failed": 0}
    for job_id in job_ids:
        try:
            ObjectId(job_id)
        except (InvalidId, TypeError) as exc:
            raise RuntimeError(f"Invalid job ID for batch queue: {job_id}") from exc
        try:
            response = requests.post(
                f"{runner_url}/api/jobs/{job_id}/operations/batch-pipeline/queue",
                json={"tier": "quality"},
                headers={
                    "Authorization": f"Bearer {runner_secret}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if response.status_code in (200, 201, 202):
                stats["queued"] += 1
            else:
                eprint(f"[batch] failed {job_id}: HTTP {response.status_code}")
                stats["failed"] += 1
        except requests.RequestException as exc:
            eprint(f"[batch] failed {job_id}: {exc}")
            stats["failed"] += 1
    return stats


def make_row(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert a result into a flat row."""
    created = extract_date(doc)
    score = doc.get("score")
    return {
        "tier": doc.get("_matched_tier_label", doc.get("_matched_tier", "")),
        "id": str(doc.get("_id", "")),
        "score": "" if score is None else score,
        "title": doc.get("title") or "",
        "company": doc.get("company") or "",
        "location": doc.get("location") or "",
        "status": doc.get("status") or "",
        "date": created.strftime("%Y-%m-%d"),
        "collection": doc.get("_collection") or "",
        "source": doc.get("source") or "",
    }


def print_table(results: Sequence[dict[str, Any]], no_header: bool) -> None:
    """Print table output to stdout."""
    rows = [make_row(doc) for doc in results]
    widths = {
        "#": 3,
        "Tier": 20,
        "ID": 26,
        "Score": 6,
        "Title": 50,
        "Company": 25,
        "Location": 28,
        "Status": 16,
        "Date": 10,
    }
    header = (
        f"{'#':>3}  {'Tier':<{widths['Tier']}} {'ID':<{widths['ID']}} "
        f"{'Score':>{widths['Score']}}  {'Title':<{widths['Title']}} "
        f"{'Company':<{widths['Company']}} {'Location':<{widths['Location']}} "
        f"{'Status':<{widths['Status']}} {'Date':<{widths['Date']}}"
    )
    rule = (
        f"{'-' * 3} {'-' * widths['Tier']} {'-' * widths['ID']} {'-' * widths['Score']} "
        f"{'-' * widths['Title']} {'-' * widths['Company']} {'-' * widths['Location']} "
        f"{'-' * widths['Status']} {'-' * widths['Date']}"
    )
    if not no_header:
        print(header)
        print(rule)
    for index, row in enumerate(rows, start=1):
        print(
            f"{index:>3}  "
            f"{str(row['tier'])[:widths['Tier']]:<{widths['Tier']}} "
            f"{str(row['id'])[:widths['ID']]:<{widths['ID']}} "
            f"{str(row['score'])[:widths['Score']]:>{widths['Score']}}  "
            f"{str(row['title'])[:widths['Title']]:<{widths['Title']}} "
            f"{str(row['company'])[:widths['Company']]:<{widths['Company']}} "
            f"{str(row['location'])[:widths['Location']]:<{widths['Location']}} "
            f"{str(row['status'])[:widths['Status']]:<{widths['Status']}} "
            f"{str(row['date'])[:widths['Date']]:<{widths['Date']}}"
        )


def sanitize_for_json(value: Any) -> Any:
    """Convert BSON and datetime types into JSON-safe values."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        value = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_for_json(item) for key, item in value.items()}
    return value


def print_json(results: Sequence[dict[str, Any]]) -> None:
    """Print full JSON output to stdout."""
    payload = [sanitize_for_json(doc) for doc in results]
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def print_csv(results: Sequence[dict[str, Any]]) -> None:
    """Print CSV output to stdout."""
    fieldnames = ["tier", "id", "score", "title", "company", "location", "status", "date", "collection", "source"]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for doc in results:
        writer.writerow(make_row(doc))


def print_ids(results: Sequence[dict[str, Any]]) -> None:
    """Print one result ID per line."""
    for doc in results:
        print(str(doc.get("_id", "")))


def emit_results(results: Sequence[dict[str, Any]], output_format: str, no_header: bool) -> None:
    """Dispatch result rendering."""
    if output_format == "json":
        print_json(results)
        return
    if output_format == "csv":
        print_csv(results)
        return
    if output_format == "ids":
        print_ids(results)
        return
    print_table(results, no_header=no_header)


def main() -> int:
    """Run the top jobs query script."""
    args = parse_args()
    if args.promote and args.collection == "level-2":
        eprint("[promote] nothing to promote from level-2 only query")

    try:
        db = get_database()
        eprint("[query] connected to MongoDB")
        results = query_jobs(db, args)
        emit_results(results, output_format=args.format, no_header=args.no_header)
        eprint(f"[query] returned {len(results)} job(s)")

        promotion_stats = {"mapping": {}}
        if args.promote:
            promotion_stats = promote_results(db, results)
            eprint(
                "[promote] checked={checked} promoted={promoted} already_present={already_present} skipped={skipped}".format(
                    **promotion_stats
                )
            )

        if args.batch:
            job_ids, skipped = resolve_batch_ids(results, promotion_stats.get("mapping", {}))
            if skipped:
                eprint(f"[batch] skipped {skipped} level-1 result(s) without level-2 IDs")
            if job_ids:
                batch_stats = trigger_batch(job_ids)
                eprint("[batch] queued={queued} failed={failed}".format(**batch_stats))
            else:
                eprint("[batch] no queueable level-2 job IDs found")
        return 0
    except RuntimeError as exc:
        eprint(f"ERROR: {exc}")
        return 1
    except PyMongoError as exc:
        eprint(f"ERROR: MongoDB operation failed: {exc}")
        return 1
    except KeyboardInterrupt:
        eprint("ERROR: interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
