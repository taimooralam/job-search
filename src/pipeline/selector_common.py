"""Shared selector logic for the iteration-3 Mongo-native selector family."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from pymongo.collection import Collection

from src.common.blacklist import is_blacklisted
from src.common.dedupe import (
    REGION_PRIORITY,
    detect_region,
    generate_dedupe_key,
    normalize_for_dedupe,
)
from src.common.rule_scorer import is_non_english_jd

logger = logging.getLogger(__name__)

DEFAULT_MAIN_QUOTA = 8
POOL_MAX_AGE_HOURS = 48
PROFILES_PATH = Path(__file__).resolve().parents[2] / "data" / "selector_profiles.yaml"

LEADERSHIP_KEYWORDS = {
    "head", "lead", "director", "vp", "vice president",
    "chief", "principal", "staff", "manager", "cto", "cio",
}

STAFF_ARCHITECT_KEYWORDS = {
    "staff", "architect", "principal", "distinguished", "fellow",
}

AI_TITLE_KEYWORDS = {
    "ai", "artificial intelligence", "machine learning", "ml",
    "llm", "genai", "deep learning", "nlp", "computer vision",
    "data scientist", "data science",
}


@dataclass
class MainSelectorPlan:
    """Computed decisions for one main selector run."""

    candidates_seen: int
    filtered_blacklist: list[dict[str, Any]]
    filtered_non_english: list[dict[str, Any]]
    filtered_score: list[dict[str, Any]]
    duplicate_cross_location: list[dict[str, Any]]
    duplicate_db: list[dict[str, Any]]
    pool_available: list[dict[str, Any]]
    tier_low: list[dict[str, Any]]
    inserted_level2_only: list[dict[str, Any]]
    selected_for_preenrich: list[dict[str, Any]]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "candidates_seen": self.candidates_seen,
            "filtered_blacklist": len(self.filtered_blacklist),
            "filtered_non_english": len(self.filtered_non_english),
            "filtered_score": len(self.filtered_score),
            "duplicate_cross_location": len(self.duplicate_cross_location),
            "duplicate_db": len(self.duplicate_db),
            "tier_low_level1": len(self.tier_low),
            "inserted_level2": len(self.inserted_level2_only) + len(self.selected_for_preenrich),
            "selected_for_preenrich": len(self.selected_for_preenrich),
            "discarded_quota": 0,
            "profile_selected": 0,
        }


@dataclass
class ProfileSelectorPlan:
    """Computed decisions for one profile selector run."""

    candidates_seen: int
    filtered_blacklist: list[dict[str, Any]]
    filtered_non_english: list[dict[str, Any]]
    filtered_score: list[dict[str, Any]]
    filtered_location: list[dict[str, Any]]
    duplicate_db: list[dict[str, Any]]
    discarded_quota: list[dict[str, Any]]
    selected: list[dict[str, Any]]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "candidates_seen": self.candidates_seen,
            "filtered_blacklist": len(self.filtered_blacklist),
            "filtered_non_english": len(self.filtered_non_english),
            "filtered_score": len(self.filtered_score),
            "duplicate_cross_location": 0,
            "duplicate_db": len(self.duplicate_db),
            "tier_low_level1": 0,
            "inserted_level2": len(self.selected),
            "selected_for_preenrich": len(self.selected),
            "discarded_quota": len(self.discarded_quota),
            "profile_selected": len(self.selected),
        }


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def load_selector_profiles(path: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    """Load selector profile definitions from YAML."""
    with open(path or PROFILES_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def matches_location(job: dict[str, Any], patterns: list[str], mode: str = "any") -> bool:
    """Preserve the legacy profile-location matching behavior."""
    del mode  # Legacy code treated both values the same.
    location = (job.get("location") or "").lower()
    title = (job.get("title") or "").lower()
    combined = f"{location} {title}"
    return any(pattern.lower() in combined for pattern in patterns)


def compute_rank_score(
    job: dict[str, Any],
    boosts: dict[str, int],
    *,
    now: Optional[datetime] = None,
) -> float:
    """Compute the legacy dimensional rank score."""
    score = float(job.get("score", 0) or 0)
    title = (job.get("title") or "").lower()
    location = (job.get("location") or "").lower()
    current_time = now or utc_now()

    if boosts.get("leadership", 0) > 0 and any(keyword in title for keyword in LEADERSHIP_KEYWORDS):
        score += boosts["leadership"]
    if boosts.get("staff_architect", 0) > 0 and any(keyword in title for keyword in STAFF_ARCHITECT_KEYWORDS):
        score += boosts["staff_architect"]
    if boosts.get("remote", 0) > 0 and ("remote" in location or "remote" in title):
        score += boosts["remote"]

    if boosts.get("newest", 0) > 0:
        pooled_at = job.get("pooled_at")
        if isinstance(pooled_at, str):
            try:
                pooled_at = datetime.fromisoformat(pooled_at)
            except ValueError:
                pooled_at = None
        if isinstance(pooled_at, datetime):
            if pooled_at.tzinfo is None:
                pooled_at = pooled_at.replace(tzinfo=timezone.utc)
            age_hours = (current_time - pooled_at).total_seconds() / 3600
            if age_hours < 6:
                score += boosts["newest"]
            elif age_hours < 12:
                score += boosts["newest"] * 0.7
            elif age_hours < 24:
                score += boosts["newest"] * 0.4

    if any(keyword in title for keyword in AI_TITLE_KEYWORDS):
        score += 3

    return score


def compute_main_selector_plan(
    candidates: list[dict[str, Any]],
    *,
    db: Any,
    quota: int = DEFAULT_MAIN_QUOTA,
) -> MainSelectorPlan:
    """Compute batch-global main selector decisions from selector payloads."""
    after_blacklist: list[dict[str, Any]] = []
    filtered_blacklist: list[dict[str, Any]] = []
    for job in candidates:
        if is_blacklisted(job):
            filtered_blacklist.append(_annotate(job, "_decision_reason", "blacklist"))
        else:
            after_blacklist.append(job)

    after_language: list[dict[str, Any]] = []
    filtered_non_english: list[dict[str, Any]] = []
    for job in after_blacklist:
        if is_non_english_jd(job.get("title", ""), job.get("description", "")):
            filtered_non_english.append(_annotate(job, "_decision_reason", "non_english"))
        else:
            after_language.append(job)

    after_score: list[dict[str, Any]] = []
    filtered_score: list[dict[str, Any]] = []
    for job in after_language:
        if (job.get("score") or 0) > 0:
            after_score.append(job)
        else:
            filtered_score.append(_annotate(job, "_decision_reason", "score<=0"))

    deduped_cross, duplicate_cross_location = _consolidate_with_remainders(after_score)
    fresh_jobs, duplicate_db = main_dedupe_against_db(deduped_cross, db)

    pool_available = [_clone(job) for job in fresh_jobs]
    tier_low = [_clone(job) for job in fresh_jobs if job.get("tier") not in {"A", "B", "C"}]
    tier_c_plus = [_clone(job) for job in fresh_jobs if job.get("tier") in {"A", "B", "C"}]
    tier_c_plus.sort(key=lambda job: job.get("score", 0), reverse=True)

    selected_for_preenrich = [_annotate(job, "_rank", index + 1) for index, job in enumerate(tier_c_plus[:quota])]
    inserted_level2_only = [_annotate(job, "_rank", index + quota + 1) for index, job in enumerate(tier_c_plus[quota:])]

    return MainSelectorPlan(
        candidates_seen=len(candidates),
        filtered_blacklist=filtered_blacklist,
        filtered_non_english=filtered_non_english,
        filtered_score=filtered_score,
        duplicate_cross_location=duplicate_cross_location,
        duplicate_db=duplicate_db,
        pool_available=pool_available,
        tier_low=tier_low,
        inserted_level2_only=inserted_level2_only,
        selected_for_preenrich=selected_for_preenrich,
    )


def compute_profile_selector_plan(
    candidates: list[dict[str, Any]],
    *,
    db: Any,
    profile: dict[str, Any],
    now: Optional[datetime] = None,
) -> ProfileSelectorPlan:
    """Compute one profile selector run from the durable pool state."""
    current_time = now or utc_now()
    patterns = profile.get("location_patterns", [])
    boosts = profile.get("rank_boosts", {})
    quota = int(profile.get("quota", 0))
    location_mode = profile.get("location_mode", "any")

    after_blacklist: list[dict[str, Any]] = []
    filtered_blacklist: list[dict[str, Any]] = []
    for job in candidates:
        if is_blacklisted(job):
            filtered_blacklist.append(_annotate(job, "_decision_reason", "blacklist"))
        else:
            after_blacklist.append(job)

    after_language: list[dict[str, Any]] = []
    filtered_non_english: list[dict[str, Any]] = []
    for job in after_blacklist:
        if is_non_english_jd(job.get("title", ""), job.get("description", "")):
            filtered_non_english.append(_annotate(job, "_decision_reason", "non_english"))
        else:
            after_language.append(job)

    after_score: list[dict[str, Any]] = []
    filtered_score: list[dict[str, Any]] = []
    for job in after_language:
        if (job.get("score") or 0) > 0:
            after_score.append(job)
        else:
            filtered_score.append(_annotate(job, "_decision_reason", "score<=0"))

    matched: list[dict[str, Any]] = []
    filtered_location: list[dict[str, Any]] = []
    for job in after_score:
        if matches_location(job, patterns, mode=location_mode):
            matched.append(job)
        else:
            filtered_location.append(_annotate(job, "_decision_reason", "location_mismatch"))

    fresh_jobs, duplicate_db = profile_dedupe_against_db(matched, db)
    ranked_jobs = [_annotate(job, "_rank_score", compute_rank_score(job, boosts, now=current_time)) for job in fresh_jobs]
    ranked_jobs.sort(key=lambda job: job.get("_rank_score", 0), reverse=True)

    selected = [_annotate(job, "_rank", index + 1) for index, job in enumerate(ranked_jobs[:quota])]
    discarded_quota = [_annotate(job, "_rank", index + quota + 1) for index, job in enumerate(ranked_jobs[quota:])]

    return ProfileSelectorPlan(
        candidates_seen=len(candidates),
        filtered_blacklist=filtered_blacklist,
        filtered_non_english=filtered_non_english,
        filtered_score=filtered_score,
        filtered_location=filtered_location,
        duplicate_db=duplicate_db,
        discarded_quota=discarded_quota,
        selected=selected,
    )


def main_dedupe_against_db(jobs: list[dict[str, Any]], db: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mirror the legacy main-selector DB dedupe against level-2 only."""
    return _dedupe_against_db(jobs, db, collection_names=("level-2",), secondary_on_level1=False)


def profile_dedupe_against_db(jobs: list[dict[str, Any]], db: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mirror the legacy profile-selector DB dedupe against level-1 and level-2."""
    return _dedupe_against_db(jobs, db, collection_names=("level-1", "level-2"), secondary_on_level1=False)


def upsert_low_tier_level1_job(
    level1: Collection,
    job: dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Upsert the main-selector low-tier compatibility row into level-1."""
    current_time = now or utc_now()
    dedupe_key = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
    existing = level1.find_one({"dedupeKey": dedupe_key}, {"_id": 1})
    level1.update_one(
        {"dedupeKey": dedupe_key},
        {
            "$setOnInsert": {
                "company": job.get("company"),
                "title": job.get("title"),
                "location": job.get("location"),
                "jobUrl": job.get("job_url"),
                "description": job.get("description", ""),
                "dedupeKey": dedupe_key,
                "createdAt": current_time,
                "updatedAt": current_time,
                "source": "scout_discarded",
                "auto_discovered": True,
                "quick_score": job.get("score"),
                "tier": job.get("tier"),
                "status": "discovered",
                "linkedin_metadata": {
                    "linkedin_job_id": job.get("job_id"),
                    "seniority_level": job.get("seniority") or job.get("seniority_level"),
                    "employment_type": job.get("employment_type"),
                    "job_function": job.get("job_function"),
                    "industries": job.get("industries"),
                    "work_mode": job.get("work_mode"),
                    "rule_score_breakdown": job.get("breakdown"),
                },
            }
        },
        upsert=True,
    )
    document = level1.find_one({"dedupeKey": dedupe_key}, {"_id": 1}) or {}
    return {
        "dedupe_key": dedupe_key,
        "level1_job_id": document.get("_id"),
        "inserted_now": existing is None,
    }


def upsert_level2_job(
    level2: Collection,
    job: dict[str, Any],
    *,
    source_tag: str,
    selected_for_preenrich: bool,
    selected_at: Optional[datetime] = None,
    status: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Upsert a selector output row into level-2 with safe lifecycle promotion."""
    current_time = now or utc_now()
    selected_time = selected_at or current_time
    dedupe_key = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
    existing = level2.find_one({"dedupeKey": dedupe_key}, {"_id": 1, "lifecycle": 1})

    set_on_insert: dict[str, Any] = {
        "company": job.get("company"),
        "title": job.get("title"),
        "location": job.get("location"),
        "jobUrl": job.get("job_url"),
        "description": job.get("description", ""),
        "dedupeKey": dedupe_key,
        "createdAt": current_time,
        "updatedAt": current_time,
        "status": status,
        "batch_added_at": current_time,
        "source": source_tag,
        "auto_discovered": True,
        "quick_score": job.get("score"),
        "quick_score_rationale": (
            f"Rule scorer: {job.get('tier')} tier, "
            f"role={job.get('detected_role')}, "
            f"seniority={job.get('seniority_level')}"
        ),
        "tier": job.get("tier"),
        "score": job.get("score"),
        "starred": job.get("tier") == "A",
        "starredAt": current_time if job.get("tier") == "A" else None,
        "salary": None,
        "jobType": job.get("employment_type"),
        "linkedin_metadata": {
            "linkedin_job_id": job.get("job_id"),
            "seniority_level": job.get("seniority") or job.get("seniority_level"),
            "employment_type": job.get("employment_type"),
            "job_function": job.get("job_function"),
            "industries": job.get("industries"),
            "work_mode": job.get("work_mode"),
            "rule_score_breakdown": job.get("breakdown"),
        },
    }
    if selected_for_preenrich:
        set_on_insert["lifecycle"] = "selected"
        set_on_insert["selected_at"] = selected_time

    level2.update_one({"dedupeKey": dedupe_key}, {"$setOnInsert": set_on_insert}, upsert=True)
    document = level2.find_one({"dedupeKey": dedupe_key}, {"_id": 1, "lifecycle": 1}) or {}
    level2_job_id = document.get("_id")
    lifecycle_updated = False

    if selected_for_preenrich and level2_job_id is not None and document.get("lifecycle") in {None, ""}:
        patch: dict[str, Any] = {"lifecycle": "selected", "selected_at": selected_time, "updatedAt": current_time}
        if status is not None:
            patch["status"] = status
        result = level2.update_one(
            {
                "_id": level2_job_id,
                "$or": [
                    {"lifecycle": {"$exists": False}},
                    {"lifecycle": None},
                ],
            },
            {"$set": patch},
        )
        lifecycle_updated = result.modified_count == 1

    return {
        "dedupe_key": dedupe_key,
        "level2_job_id": level2_job_id,
        "inserted_now": existing is None,
        "lifecycle_updated": lifecycle_updated,
    }


def _dedupe_against_db(
    jobs: list[dict[str, Any]],
    db: Any,
    *,
    collection_names: tuple[str, ...],
    secondary_on_level1: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not jobs:
        return [], []

    dedupe_keys: list[str] = []
    for job in jobs:
        dedupe_keys.append(generate_dedupe_key("linkedin_scout", source_id=job["job_id"]))
        dedupe_keys.append(generate_dedupe_key("linkedin_import", source_id=job["job_id"]))

    existing_keys: set[str] = set()
    for collection_name in collection_names:
        for document in db[collection_name].find({"dedupeKey": {"$in": dedupe_keys}}, {"dedupeKey": 1}):
            existing_keys.add(document["dedupeKey"])

    after_primary: list[dict[str, Any]] = []
    duplicate_primary: list[dict[str, Any]] = []
    for job in jobs:
        key_scout = generate_dedupe_key("linkedin_scout", source_id=job["job_id"])
        key_import = generate_dedupe_key("linkedin_import", source_id=job["job_id"])
        if key_scout in existing_keys or key_import in existing_keys:
            duplicate_primary.append(_annotate(job, "_decision_reason", "dedupe_key"))
        else:
            after_primary.append(job)

    secondary_collections = ("level-2", "level-1") if secondary_on_level1 else ("level-2",)
    existing_company_title: set[str] = set()
    for collection_name in secondary_collections:
        for document in db[collection_name].find(
            {"company": {"$exists": True}, "title": {"$exists": True}},
            {"company": 1, "title": 1},
        ):
            company_norm = normalize_for_dedupe(document.get("company"))
            title_norm = normalize_for_dedupe(document.get("title"))
            if company_norm and title_norm:
                existing_company_title.add(f"{company_norm}|{title_norm}")

    fresh: list[dict[str, Any]] = []
    duplicate_secondary: list[dict[str, Any]] = []
    for job in after_primary:
        company_norm = normalize_for_dedupe(job.get("company"))
        title_norm = normalize_for_dedupe(job.get("title"))
        company_title = f"{company_norm}|{title_norm}"
        if company_title in existing_company_title:
            duplicate_secondary.append(_annotate(job, "_decision_reason", "company_title"))
        else:
            fresh.append(job)

    duplicates = duplicate_primary + duplicate_secondary
    return fresh, duplicates


def _consolidate_with_remainders(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        company_norm = normalize_for_dedupe(job.get("company"))
        title_norm = normalize_for_dedupe(job.get("title"))
        groups.setdefault(f"{company_norm}|{title_norm}", []).append(job)

    kept: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []
    for grouped_jobs in groups.values():
        ranked = sorted(
            grouped_jobs,
            key=lambda job: (
                REGION_PRIORITY.get(detect_region(job.get("location", "")), 0),
                job.get("score", 0),
            ),
            reverse=True,
        )
        winner = ranked[0]
        kept.append(winner)
        for loser in ranked[1:]:
            discarded.append(_annotate(loser, "_kept_job_id", winner.get("job_id")))
    return kept, discarded


def _clone(job: dict[str, Any]) -> dict[str, Any]:
    return dict(job)


def _annotate(job: dict[str, Any], key: str, value: Any) -> dict[str, Any]:
    clone = _clone(job)
    clone[key] = value
    return clone
