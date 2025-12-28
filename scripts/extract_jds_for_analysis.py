#!/usr/bin/env python3
"""
Phase 1: Parallel JD Extraction for Bullet Point Analysis

Extracts structured JD intelligence from MongoDB level-2 jobs using Claude CLI.
Runs in parallel with controlled concurrency to speed up extraction.

This script:
1. Queries all jobs matching target roles (or all jobs with descriptions)
2. Filters to jobs needing extraction
3. Runs parallel extraction using JDExtractor.extract_batch()
4. Saves results to MongoDB
5. Aggregates patterns per role category (Phase 2)
6. Outputs summary statistics

Usage:
    python scripts/extract_jds_for_analysis.py

Options (via environment variables):
    MAX_CONCURRENT=5        - Max parallel extractions (default: 3)
    MAX_JOBS=100            - Max jobs to extract (default: unlimited)
    REEXTRACT=true          - Re-extract already extracted jobs (default: false)
    TARGET_ROLES_ONLY=true  - Only extract target roles (default: true)
"""

import os
import sys
import re
import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, asdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from bson import ObjectId
from pymongo import MongoClient, UpdateOne
from src.common.config import Config
from src.layer1_4.claude_jd_extractor import JDExtractor, ExtractionResult
from src.common.llm_config import STEP_CONFIGS, StepConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


# ===== CONFIGURATION =====

TARGET_ROLE_PATTERNS = {
    "engineering_manager": r"engineering manager|eng manager|manager.*engineering",
    "staff_principal_engineer": r"staff.*engineer|principal.*engineer|software architect",
    "director_of_engineering": r"director.*engineering|director.*software",
    "head_of_engineering": r"head of engineering|head of software|vp engineering",
    "tech_lead": r"tech lead|lead.*engineer|lead software|team lead.*engineer",
    "senior_engineer": r"senior.*engineer|sr\.?\s*engineer|sr\.?\s*software",
    "cto": r"\bcto\b|chief technology|chief technical",
}


@dataclass
class ExtractionStats:
    """Statistics from extraction run."""
    total_jobs: int = 0
    jobs_with_description: int = 0
    jobs_needing_extraction: int = 0
    jobs_extracted: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0
    total_duration_seconds: float = 0.0
    role_category_counts: Dict[str, int] = None

    def __post_init__(self):
        if self.role_category_counts is None:
            self.role_category_counts = {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def configure_mandatory_cli():
    """Configure JD extraction to use Claude CLI mandatory (no fallback)."""
    original_config = STEP_CONFIGS.get("jd_extraction", StepConfig())
    STEP_CONFIGS["jd_extraction"] = StepConfig(
        tier=original_config.tier,
        claude_model=original_config.claude_model,
        fallback_model=original_config.fallback_model,
        timeout_seconds=original_config.timeout_seconds,
        max_retries=original_config.max_retries,
        use_fallback=False,  # MANDATORY: Claude CLI only
    )
    logger.info(f"Configured Claude CLI mandatory (no fallback)")


def get_mongodb_client() -> MongoClient:
    """Get MongoDB client."""
    if not Config.MONGODB_URI:
        raise ValueError("MONGODB_URI not configured in .env")
    return MongoClient(Config.MONGODB_URI)


def query_jobs_needing_extraction(
    client: MongoClient,
    target_roles_only: bool = True,
    reextract: bool = False,
    max_jobs: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Query jobs from MongoDB level-2 that need extraction.

    Args:
        client: MongoDB client
        target_roles_only: Only query jobs matching target role patterns
        reextract: Include already extracted jobs for re-extraction
        max_jobs: Maximum number of jobs to return

    Returns:
        List of job documents
    """
    level2 = client['jobs']['level-2']

    # Build query
    query = {"description": {"$exists": True, "$ne": ""}}

    # Add target role filter
    if target_roles_only:
        combined_pattern = "|".join(f"({p})" for p in TARGET_ROLE_PATTERNS.values())
        query["title"] = {"$regex": combined_pattern, "$options": "i"}

    # Add extraction filter
    if not reextract:
        query["$or"] = [
            {"extracted_jd": {"$exists": False}},
            {"extracted_jd": None},
        ]

    # Execute query
    cursor = level2.find(query)
    if max_jobs:
        cursor = cursor.limit(max_jobs)

    jobs = list(cursor)
    logger.info(f"Found {len(jobs)} jobs to extract")

    return jobs


def detect_role_match(title: str) -> Optional[str]:
    """Detect which target role pattern a job title matches."""
    for role_key, pattern in TARGET_ROLE_PATTERNS.items():
        if re.search(pattern, title, re.IGNORECASE):
            return role_key
    return None


async def run_parallel_extraction(
    jobs: List[Dict[str, Any]],
    max_concurrent: int = 3
) -> List[ExtractionResult]:
    """
    Run parallel extraction using JDExtractor.extract_batch().

    Args:
        jobs: List of job documents from MongoDB
        max_concurrent: Maximum concurrent extractions

    Returns:
        List of ExtractionResult objects
    """
    # Convert to format expected by extract_batch
    jobs_for_extraction = [
        {
            "job_id": str(job["_id"]),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "job_description": job.get("description", ""),
        }
        for job in jobs
    ]

    # Create extractor
    extractor = JDExtractor(tier="middle")

    logger.info(f"Starting parallel extraction of {len(jobs)} jobs with max_concurrent={max_concurrent}")
    start_time = datetime.now()

    # Run batch extraction
    results = await extractor.extract_batch(jobs_for_extraction, max_concurrent=max_concurrent)

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"Extraction complete in {duration:.1f}s")

    return results


def save_results_to_mongodb(
    client: MongoClient,
    results: List[ExtractionResult]
) -> Dict[str, int]:
    """
    Save extraction results back to MongoDB.

    Args:
        client: MongoDB client
        results: List of ExtractionResult objects

    Returns:
        Dict with counts: {"updated": N, "failed": M}
    """
    level2 = client['jobs']['level-2']

    updates = []
    counts = {"updated": 0, "failed": 0}

    for result in results:
        if result.success and result.extracted_jd:
            updates.append(UpdateOne(
                {"_id": ObjectId(result.job_id)},
                {"$set": {
                    "extracted_jd": result.extracted_jd,
                    "extraction_model": result.model,
                    "extraction_duration_ms": result.duration_ms,
                    "extracted_at": result.extracted_at,
                }}
            ))
            counts["updated"] += 1
        else:
            counts["failed"] += 1

    if updates:
        level2.bulk_write(updates)
        logger.info(f"Saved {counts['updated']} extraction results to MongoDB")

    return counts


def aggregate_patterns_by_role(
    results: List[ExtractionResult]
) -> Dict[str, Dict[str, Any]]:
    """
    Phase 2: Aggregate patterns per role category.

    Args:
        results: List of successful ExtractionResult objects

    Returns:
        Dict mapping role_category to aggregated patterns
    """
    role_patterns = defaultdict(lambda: {
        "count": 0,
        "technical_skills": defaultdict(int),
        "soft_skills": defaultdict(int),
        "top_keywords": defaultdict(int),
        "implied_pain_points": [],
        "success_metrics": [],
        "competency_weights": {
            "delivery": [],
            "process": [],
            "architecture": [],
            "leadership": [],
        },
        "seniority_levels": defaultdict(int),
        "sample_responsibilities": [],
    })

    for result in results:
        if not result.success or not result.extracted_jd:
            continue

        jd = result.extracted_jd
        role_cat = jd.get("role_category", "unknown")
        patterns = role_patterns[role_cat]

        patterns["count"] += 1

        # Aggregate technical skills
        for skill in jd.get("technical_skills", []):
            patterns["technical_skills"][skill.lower()] += 1

        # Aggregate soft skills
        for skill in jd.get("soft_skills", []):
            patterns["soft_skills"][skill.lower()] += 1

        # Aggregate keywords
        for keyword in jd.get("top_keywords", []):
            patterns["top_keywords"][keyword.lower()] += 1

        # Collect pain points (unique)
        for pain in jd.get("implied_pain_points", []):
            if pain not in patterns["implied_pain_points"]:
                patterns["implied_pain_points"].append(pain)

        # Collect success metrics (unique)
        for metric in jd.get("success_metrics", []):
            if metric not in patterns["success_metrics"]:
                patterns["success_metrics"].append(metric)

        # Collect competency weights
        weights = jd.get("competency_weights", {})
        for key in ["delivery", "process", "architecture", "leadership"]:
            if key in weights:
                patterns["competency_weights"][key].append(weights[key])

        # Count seniority levels
        seniority = jd.get("seniority_level", "unknown")
        patterns["seniority_levels"][seniority] += 1

        # Sample responsibilities (first 3)
        if len(patterns["sample_responsibilities"]) < 10:
            for resp in jd.get("responsibilities", [])[:2]:
                if resp not in patterns["sample_responsibilities"]:
                    patterns["sample_responsibilities"].append(resp)

    # Convert defaultdicts and compute averages
    result = {}
    for role_cat, patterns in role_patterns.items():
        # Sort skills by frequency
        sorted_tech = sorted(
            patterns["technical_skills"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]
        sorted_soft = sorted(
            patterns["soft_skills"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:15]
        sorted_keywords = sorted(
            patterns["top_keywords"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:20]

        # Compute competency weight averages
        weight_avgs = {}
        for key, values in patterns["competency_weights"].items():
            if values:
                weight_avgs[key] = {
                    "avg": round(sum(values) / len(values), 1),
                    "min": min(values),
                    "max": max(values),
                }

        result[role_cat] = {
            "count": patterns["count"],
            "top_technical_skills": sorted_tech,
            "top_soft_skills": sorted_soft,
            "top_keywords": sorted_keywords,
            "implied_pain_points": patterns["implied_pain_points"][:15],
            "success_metrics": patterns["success_metrics"][:10],
            "competency_weight_stats": weight_avgs,
            "seniority_distribution": dict(patterns["seniority_levels"]),
            "sample_responsibilities": patterns["sample_responsibilities"][:10],
        }

    return result


def save_pattern_analysis(
    patterns: Dict[str, Dict[str, Any]],
    output_path: Path
) -> None:
    """Save pattern analysis to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(patterns, f, indent=2)
    logger.info(f"Saved pattern analysis to {output_path}")


def print_summary(stats: ExtractionStats, patterns: Dict[str, Dict[str, Any]]):
    """Print extraction summary."""
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)

    print(f"\nJobs:")
    print(f"   Total in database: {stats.total_jobs:,}")
    print(f"   With descriptions: {stats.jobs_with_description:,}")
    print(f"   Needing extraction: {stats.jobs_needing_extraction:,}")
    print(f"   Extracted this run: {stats.jobs_extracted:,}")
    print(f"   Succeeded: {stats.jobs_succeeded:,}")
    print(f"   Failed: {stats.jobs_failed:,}")
    print(f"   Duration: {stats.total_duration_seconds:.1f}s")

    if patterns:
        print(f"\nRole Categories Found:")
        for role_cat, data in sorted(patterns.items(), key=lambda x: x[1]["count"], reverse=True):
            print(f"   {role_cat}: {data['count']} jobs")

        print(f"\nTop Technical Skills (across all roles):")
        all_tech = defaultdict(int)
        for role_data in patterns.values():
            for skill, count in role_data["top_technical_skills"]:
                all_tech[skill] += count
        for skill, count in sorted(all_tech.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {skill}: {count}")

    print("\n" + "=" * 60)


async def main():
    """Run Phase 1 & 2: Parallel extraction and pattern aggregation."""
    print("\n" + "=" * 60)
    print("PHASE 1 & 2: Parallel JD Extraction + Pattern Aggregation")
    print("=" * 60)

    # Get configuration from environment
    max_concurrent = int(os.getenv("MAX_CONCURRENT", "3"))
    max_jobs = int(os.getenv("MAX_JOBS", "0")) or None
    reextract = os.getenv("REEXTRACT", "false").lower() == "true"
    target_roles_only = os.getenv("TARGET_ROLES_ONLY", "true").lower() == "true"

    print(f"\nConfiguration:")
    print(f"   Max concurrent: {max_concurrent}")
    print(f"   Max jobs: {max_jobs or 'unlimited'}")
    print(f"   Re-extract: {reextract}")
    print(f"   Target roles only: {target_roles_only}")

    # Configure mandatory CLI
    configure_mandatory_cli()

    # Connect to MongoDB
    client = get_mongodb_client()
    level2 = client['jobs']['level-2']

    # Get stats
    stats = ExtractionStats()
    stats.total_jobs = level2.count_documents({})
    stats.jobs_with_description = level2.count_documents({"description": {"$exists": True, "$ne": ""}})

    print(f"\nDatabase stats:")
    print(f"   Total jobs: {stats.total_jobs:,}")
    print(f"   With descriptions: {stats.jobs_with_description:,}")

    # Query jobs needing extraction
    jobs = query_jobs_needing_extraction(
        client,
        target_roles_only=target_roles_only,
        reextract=reextract,
        max_jobs=max_jobs
    )
    stats.jobs_needing_extraction = len(jobs)

    if not jobs:
        print("\n⚠️  No jobs to extract")
        client.close()
        return

    # Run parallel extraction
    start_time = datetime.now()
    results = await run_parallel_extraction(jobs, max_concurrent=max_concurrent)
    stats.total_duration_seconds = (datetime.now() - start_time).total_seconds()

    stats.jobs_extracted = len(results)
    stats.jobs_succeeded = sum(1 for r in results if r.success)
    stats.jobs_failed = sum(1 for r in results if not r.success)

    # Save results to MongoDB
    save_counts = save_results_to_mongodb(client, results)

    # Aggregate patterns (Phase 2)
    print("\n" + "=" * 60)
    print("PHASE 2: Aggregating Patterns by Role")
    print("=" * 60)

    patterns = aggregate_patterns_by_role(results)

    # Save pattern analysis
    output_path = project_root / "reports" / "jd-pattern-analysis.json"
    save_pattern_analysis(patterns, output_path)

    # Print summary
    print_summary(stats, patterns)

    # Close connection
    client.close()

    print("\n🚀 Ready to proceed with Phase 3: Analyze current bullet points")


if __name__ == "__main__":
    asyncio.run(main())
