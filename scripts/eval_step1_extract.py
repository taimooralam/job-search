#!/usr/bin/env python3
"""
Eval Step 1: Extract eligible jobs from MongoDB across 4 signal tiers.

Outputs:
  data/eval/raw/all_eligible_jobs.json  — all eligible jobs with tier + weight
  data/eval/exclusions.json             — all excluded jobs with reasons
  data/eval/queries.json                — exact queries used
"""

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

EVAL_DIR = Path("data/eval")
RAW_DIR = EVAL_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

ANALYSIS_DATE = datetime(2026, 4, 13, tzinfo=timezone.utc)

# Signal tier weights
TIER_WEIGHTS = {"A": 1.00, "B": 0.85, "C": 0.65, "D": 0.40}

# Fields to extract
FIELDS = {
    "_id": 1, "title": 1, "company": 1, "location": 1,
    "job_description": 1, "job_criteria": 1,
    "score": 1, "tier": 1, "score_breakdown": 1,
    "status": 1, "is_ai_job": 1, "ai_categories": 1,
    "extracted_jd": 1, "cv_review": 1,
    "applied_at": 1, "response_received": 1, "interview_invited": 1, "callback": 1,
    "fit_score": 1, "createdAt": 1, "url": 1, "jobURL": 1, "linkedinUrl": 1,
    "source": 1, "dedupeKey": 1, "cv_generated_at": 1,
}


def compute_recency_multiplier(doc):
    """Compute recency multiplier based on createdAt or applied_at."""
    date_str = doc.get("applied_at") or doc.get("createdAt")
    if not date_str:
        return 1.00
    try:
        if isinstance(date_str, str):
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        elif isinstance(date_str, datetime):
            dt = date_str if date_str.tzinfo else date_str.replace(tzinfo=timezone.utc)
        else:
            return 1.00
        age_months = (ANALYSIS_DATE - dt).days / 30.44
        if age_months <= 12:
            return 1.00
        elif age_months <= 24:
            return 0.90
        else:
            return 0.80
    except (ValueError, TypeError):
        return 1.00


def assign_signal_tier(doc):
    """Assign a job to its highest signal tier."""
    status = doc.get("status")
    score = doc.get("score")
    is_ai = doc.get("is_ai_job", False)
    has_jd = bool(doc.get("job_description"))

    # Tier A: applied + response
    if status == "applied" and any([
        doc.get("response_received"),
        doc.get("interview_invited"),
        doc.get("callback"),
    ]):
        return "A"

    # Tier B: applied + score >= 60
    if status == "applied" and score is not None and score >= 60:
        return "B"

    # Tier C: AI + score >= 50 + JD
    if is_ai and score is not None and score >= 50 and has_jd:
        return "C"

    # Tier D: AI + scored + JD
    if is_ai and score is not None and has_jd:
        return "D"

    return None  # Not eligible


def normalize_for_dedup(doc):
    """Create a normalized key for deduplication."""
    title = (doc.get("title") or "").lower().strip()
    company = (doc.get("company") or "").lower().strip()
    location = (doc.get("location") or "").lower().strip()
    # Remove common suffixes
    for suffix in [" gmbh", " inc", " inc.", " ltd", " ltd.", " llc", " ag", " se"]:
        company = company.replace(suffix, "")
    return f"{title}|{company}|{location}"


def serialize_doc(doc):
    """Make a MongoDB doc JSON-serializable."""
    result = {}
    for k, v in doc.items():
        if k == "_id":
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = {sk: str(sv) if isinstance(sv, datetime) else sv for sk, sv in v.items()}
        else:
            result[k] = v
    return result


def main():
    client = MongoClient(os.environ["MONGODB_URI"])
    col = client["jobs"]["level-2"]

    # Query ALL jobs that have score and JD
    print("Querying MongoDB level-2...")
    cursor = col.find(
        {"job_description": {"$exists": True, "$ne": None}},
        FIELDS,
    ).batch_size(1000)

    all_docs = list(cursor)
    print(f"Total documents fetched: {len(all_docs)}")

    # Phase 1: Exclusion pass
    eligible = []
    exclusions = []

    for doc in all_docs:
        jd = doc.get("job_description", "")
        if not jd or len(str(jd)) < 100:
            exclusions.append({
                "_id": str(doc["_id"]),
                "title": doc.get("title"),
                "reason": "excluded_missing_jd",
                "detail": f"JD length: {len(str(jd)) if jd else 0}",
            })
            continue

        if doc.get("score") is None:
            exclusions.append({
                "_id": str(doc["_id"]),
                "title": doc.get("title"),
                "reason": "excluded_no_score",
            })
            continue

        tier = assign_signal_tier(doc)
        if tier is None:
            exclusions.append({
                "_id": str(doc["_id"]),
                "title": doc.get("title"),
                "reason": "excluded_no_tier",
                "detail": f"status={doc.get('status')}, is_ai={doc.get('is_ai_job')}, score={doc.get('score')}",
            })
            continue

        doc["_signal_tier"] = tier
        doc["_signal_weight"] = TIER_WEIGHTS[tier]
        doc["_recency_multiplier"] = compute_recency_multiplier(doc)
        doc["_effective_weight"] = doc["_signal_weight"] * doc["_recency_multiplier"]
        eligible.append(doc)

    print(f"Eligible before dedup: {len(eligible)}")
    print(f"Excluded: {len(exclusions)}")

    # Phase 2: Deduplication
    dedup_map = {}  # normalized_key -> best doc
    dedup_excluded = []

    for doc in eligible:
        key = normalize_for_dedup(doc)
        if key in dedup_map:
            existing = dedup_map[key]
            # Keep higher tier, then higher score, then newer
            tier_rank = {"A": 4, "B": 3, "C": 2, "D": 1}
            new_rank = tier_rank[doc["_signal_tier"]]
            old_rank = tier_rank[existing["_signal_tier"]]

            if (new_rank > old_rank) or \
               (new_rank == old_rank and (doc.get("score", 0) or 0) > (existing.get("score", 0) or 0)):
                # New doc is better — swap
                dedup_excluded.append({
                    "_id": str(existing["_id"]),
                    "title": existing.get("title"),
                    "reason": "excluded_duplicate",
                    "kept_id": str(doc["_id"]),
                    "dedup_key": key,
                })
                dedup_map[key] = doc
            else:
                dedup_excluded.append({
                    "_id": str(doc["_id"]),
                    "title": doc.get("title"),
                    "reason": "excluded_duplicate",
                    "kept_id": str(existing["_id"]),
                    "dedup_key": key,
                })
        else:
            dedup_map[key] = doc

    exclusions.extend(dedup_excluded)
    final_eligible = list(dedup_map.values())

    print(f"Duplicates removed: {len(dedup_excluded)}")
    print(f"Final eligible: {len(final_eligible)}")

    # Tier breakdown
    tier_counts = Counter(doc["_signal_tier"] for doc in final_eligible)
    print(f"\nTier breakdown:")
    for t in ["A", "B", "C", "D"]:
        print(f"  Tier {t}: {tier_counts.get(t, 0)}")

    # Serialize and save
    serialized = [serialize_doc(doc) for doc in final_eligible]

    with open(RAW_DIR / "all_eligible_jobs.json", "w") as f:
        json.dump(serialized, f, indent=2, default=str)
    print(f"\nSaved {len(serialized)} eligible jobs to data/eval/raw/all_eligible_jobs.json")

    with open(EVAL_DIR / "exclusions.json", "w") as f:
        json.dump(exclusions, f, indent=2, default=str)
    print(f"Saved {len(exclusions)} exclusions to data/eval/exclusions.json")

    # Save queries used
    queries = {
        "analysis_date": ANALYSIS_DATE.isoformat(),
        "collection": "jobs.level-2",
        "base_query": {"job_description": {"$exists": True, "$ne": None}},
        "tier_definitions": {
            "A": "applied + response/interview/callback (weight 1.00)",
            "B": "applied + score >= 60 (weight 0.85)",
            "C": "is_ai_job + score >= 50 + JD present (weight 0.65)",
            "D": "is_ai_job + scored + JD present (weight 0.40)",
        },
        "total_fetched": len(all_docs),
        "excluded": len(exclusions),
        "duplicates_removed": len(dedup_excluded),
        "final_eligible": len(final_eligible),
        "tier_counts": dict(tier_counts),
    }
    with open(EVAL_DIR / "queries.json", "w") as f:
        json.dump(queries, f, indent=2)

    # Summary stats
    print(f"\n{'='*50}")
    print(f"STEP 1 COMPLETE")
    print(f"{'='*50}")
    print(f"Total fetched:     {len(all_docs)}")
    print(f"Excluded:          {len(exclusions)}")
    print(f"  - missing JD:    {sum(1 for e in exclusions if e['reason'] == 'excluded_missing_jd')}")
    print(f"  - no score:      {sum(1 for e in exclusions if e['reason'] == 'excluded_no_score')}")
    print(f"  - no tier:       {sum(1 for e in exclusions if e['reason'] == 'excluded_no_tier')}")
    print(f"  - duplicates:    {len(dedup_excluded)}")
    print(f"Final eligible:    {len(final_eligible)}")
    for t in ["A", "B", "C", "D"]:
        print(f"  Tier {t}:          {tier_counts.get(t, 0)}")


if __name__ == "__main__":
    main()
