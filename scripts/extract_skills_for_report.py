#!/usr/bin/env python3 -u
"""
Extract skills from MongoDB jobs for whitelist analysis.

This script:
1. Queries jobs for target roles from level-2 collection
2. Filters out non-engineering roles
3. Uses existing extracted_jd if available
4. Runs JDExtractor (Claude CLI only, no GPT-4o fallback) for jobs without extraction
5. Aggregates skills per role
6. Outputs report to reports/skills-analysis.md

Usage:
    python scripts/extract_skills_for_report.py
"""

import asyncio
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import MongoClient

# Disable GPT-4o fallback - Claude CLI only
os.environ["USE_FALLBACK"] = "false"

from src.common.json_utils import parse_llm_json
from src.layer1_4.prompts import JD_EXTRACTION_SYSTEM_PROMPT, JD_EXTRACTION_USER_TEMPLATE


# Target roles with their MongoDB regex patterns
TARGET_ROLES = {
    "engineering_manager": r"engineering manager",
    "staff_engineer": r"staff.*(software|engineer)",
    "principal_engineer": r"principal.*(software|engineer)",
    "software_architect": r"software architect",
    "head_of_engineering": r"head of (engineering|software|technology)",
    "director_engineering": r"director.*(engineering|software)",
    "cto": r"\bcto\b|chief technology officer|chief technical officer",
}

# Keywords that indicate an engineering role (for filtering)
ENGINEERING_KEYWORDS = [
    "software", "engineer", "developer", "programming", "code", "technical",
    "architecture", "system design", "backend", "frontend", "full-stack",
    "devops", "sre", "infrastructure", "cloud", "aws", "kubernetes",
    "python", "java", "typescript", "javascript", "golang", "rust",
    "microservices", "distributed", "api", "database", "ci/cd",
]

# MongoDB connection
MONGO_URI = "mongodb+srv://taimooralam12_db_user:NmMQ016ztAMOGuox@cluster0.5cu0htu.mongodb.net/"
DB_NAME = "jobs"
COLLECTION_NAME = "level-2"

# Concurrency settings
MAX_CONCURRENT = 10


def get_mongodb_client() -> MongoClient:
    """Get MongoDB client."""
    return MongoClient(MONGO_URI)


def is_engineering_role(job: Dict) -> bool:
    """Check if job is actually an engineering role based on description."""
    description = job.get("job_description", "").lower()
    title = job.get("title", "").lower()

    # Must have at least 3 engineering keywords in description
    keyword_count = sum(1 for kw in ENGINEERING_KEYWORDS if kw in description)

    # Title should also have some tech indicator
    title_has_tech = any(kw in title for kw in ["engineer", "developer", "architect", "cto", "technical", "software", "lead"])

    return keyword_count >= 3 and title_has_tech


def query_jobs_for_role(collection, role_pattern: str) -> List[Dict]:
    """Query jobs matching a role pattern."""
    return list(collection.find(
        {"title": {"$regex": role_pattern, "$options": "i"}},
        {
            "_id": 1,
            "jobId": 1,
            "title": 1,
            "company": 1,
            "job_description": 1,
            "extracted_jd": 1,
        }
    ))


def extract_skills_from_existing(job: Dict) -> Optional[Tuple[List[str], List[str]]]:
    """Extract skills from existing extracted_jd if available."""
    extracted = job.get("extracted_jd")
    if not extracted:
        return None

    tech_skills = extracted.get("technical_skills", [])
    soft_skills = extracted.get("soft_skills", [])

    if tech_skills or soft_skills:
        return (tech_skills, soft_skills)
    return None


def extract_via_claude_cli(
    job_id: str,
    title: str,
    company: str,
    job_description: str,
    model: str = "claude-opus-4-5-20251101"
) -> Optional[Tuple[List[str], List[str]]]:
    """Extract skills using Claude CLI directly (no fallback)."""
    # Build prompt
    user_prompt = JD_EXTRACTION_USER_TEMPLATE.format(
        title=title,
        company=company,
        job_description=job_description[:12000]  # Truncate if too long
    )

    full_prompt = f"{JD_EXTRACTION_SYSTEM_PROMPT}\n\n{user_prompt}"

    try:
        # Call Claude CLI directly
        result = subprocess.run(
            ["claude", "-p", full_prompt, "--model", model, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"    CLI error for {job_id}: {result.stderr[:100]}")
            return None

        # Parse response
        output = result.stdout.strip()

        # Try to parse as JSON
        try:
            data = json.loads(output)
            # Handle Claude CLI wrapper format
            if "result" in data:
                inner = data["result"]
                if isinstance(inner, str):
                    data = parse_llm_json(inner)
                else:
                    data = inner
        except json.JSONDecodeError:
            # Try to extract JSON from text
            data = parse_llm_json(output)

        if not data:
            print(f"    No JSON found for {job_id}")
            return None

        tech_skills = data.get("technical_skills", [])
        soft_skills = data.get("soft_skills", [])

        return (tech_skills, soft_skills)

    except subprocess.TimeoutExpired:
        print(f"    Timeout for {job_id}")
        return None
    except Exception as e:
        print(f"    Error for {job_id}: {e}")
        return None


async def extract_batch_parallel(
    jobs: List[Dict],
    max_concurrent: int = 10
) -> Dict[str, Tuple[List[str], List[str]]]:
    """Extract skills from a batch of jobs using parallel Claude CLI calls."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}

    async def extract_one(job: Dict) -> Tuple[str, Optional[Tuple[List[str], List[str]]]]:
        async with semaphore:
            job_id = str(job.get("_id", job.get("jobId", "unknown")))
            title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            description = job.get("job_description", "")

            # Run in executor to not block event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                extract_via_claude_cli,
                job_id, title, company, description
            )

            return job_id, result

    # Create tasks
    tasks = [extract_one(job) for job in jobs]

    # Run with progress
    for i, coro in enumerate(asyncio.as_completed(tasks)):
        job_id, result = await coro
        if result:
            results[job_id] = result

        # Progress update every 10 jobs
        if (i + 1) % 10 == 0:
            print(f"    Processed {i + 1}/{len(jobs)} jobs...")

    return results


def normalize_skill(skill: str) -> str:
    """Normalize skill name for aggregation."""
    return skill.lower().strip()


def aggregate_skills(
    all_skills: List[Tuple[List[str], List[str]]]
) -> Tuple[Counter, Counter]:
    """Aggregate technical and soft skills across all jobs."""
    tech_counter = Counter()
    soft_counter = Counter()

    for tech_skills, soft_skills in all_skills:
        for skill in tech_skills:
            tech_counter[normalize_skill(skill)] += 1
        for skill in soft_skills:
            soft_counter[normalize_skill(skill)] += 1

    return tech_counter, soft_counter


def generate_report(
    role_results: Dict[str, Dict],
    output_path: Path
) -> None:
    """Generate markdown report."""
    lines = [
        "# Skills Analysis Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "**Purpose:** Analyze skills from real job postings to verify/expand master CV whitelist",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Role | Jobs Found | Engineering Roles | With Extraction | Newly Extracted | Failed |",
        "|------|------------|-------------------|-----------------|-----------------|--------|",
    ]

    total_found = 0
    total_eng = 0
    total_existing = 0
    total_new = 0
    total_failed = 0

    for role, data in role_results.items():
        found = data["jobs_found"]
        eng = data["engineering_roles"]
        existing = data["existing_extractions"]
        new = data["new_extractions"]
        failed = data["failed_extractions"]
        total_found += found
        total_eng += eng
        total_existing += existing
        total_new += new
        total_failed += failed
        lines.append(f"| {role} | {found} | {eng} | {existing} | {new} | {failed} |")

    lines.append(f"| **Total** | **{total_found}** | **{total_eng}** | **{total_existing}** | **{total_new}** | **{total_failed}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Skills per role
    for role, data in role_results.items():
        tech_counter = data["technical_skills"]
        soft_counter = data["soft_skills"]
        job_count = data["engineering_roles"]

        if job_count == 0:
            continue

        lines.append(f"## {role.replace('_', ' ').title()} ({job_count} engineering jobs)")
        lines.append("")

        # Technical skills
        lines.append("### Technical Skills")
        lines.append("")
        lines.append("| Skill | Count | % of Jobs |")
        lines.append("|-------|-------|-----------|")

        for skill, count in tech_counter.most_common(50):
            pct = (count / job_count) * 100 if job_count > 0 else 0
            lines.append(f"| {skill} | {count} | {pct:.1f}% |")

        lines.append("")

        # Soft skills
        lines.append("### Soft Skills")
        lines.append("")
        lines.append("| Skill | Count | % of Jobs |")
        lines.append("|-------|-------|-----------|")

        for skill, count in soft_counter.most_common(30):
            pct = (count / job_count) * 100 if job_count > 0 else 0
            lines.append(f"| {skill} | {count} | {pct:.1f}% |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"\nReport written to: {output_path}")


async def main():
    """Main extraction workflow."""
    print("=" * 60)
    print("Skills Extraction for Whitelist Analysis")
    print("=" * 60)
    print(f"Model: claude-opus-4-5-20251101")
    print(f"Concurrency: {MAX_CONCURRENT}")
    print(f"Fallback: DISABLED (Claude CLI only)")
    print("=" * 60)

    # Connect to MongoDB
    client = get_mongodb_client()
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    role_results = {}

    for role_name, pattern in TARGET_ROLES.items():
        print(f"\n{'='*40}")
        print(f"Processing: {role_name}")
        print(f"{'='*40}")

        # Query jobs
        all_jobs = query_jobs_for_role(collection, pattern)
        print(f"Found {len(all_jobs)} jobs matching pattern")

        # Filter to engineering roles only
        jobs = [j for j in all_jobs if is_engineering_role(j)]
        skipped = len(all_jobs) - len(jobs)
        print(f"  - Engineering roles: {len(jobs)} (skipped {skipped} non-tech)")

        if not jobs:
            role_results[role_name] = {
                "jobs_found": len(all_jobs),
                "engineering_roles": 0,
                "existing_extractions": 0,
                "new_extractions": 0,
                "failed_extractions": 0,
                "technical_skills": Counter(),
                "soft_skills": Counter(),
            }
            continue

        # Separate jobs with and without existing extraction
        jobs_with_extraction = []
        jobs_without_extraction = []
        all_skills = []

        for job in jobs:
            existing = extract_skills_from_existing(job)
            if existing:
                jobs_with_extraction.append(job)
                all_skills.append(existing)
            else:
                jobs_without_extraction.append(job)

        print(f"  - With existing extraction: {len(jobs_with_extraction)}")
        print(f"  - Need extraction: {len(jobs_without_extraction)}")

        # Extract skills for jobs without existing extraction
        failed_count = 0
        if jobs_without_extraction:
            print(f"  - Extracting from {len(jobs_without_extraction)} jobs (concurrency={MAX_CONCURRENT})...")

            skills_map = await extract_batch_parallel(jobs_without_extraction, MAX_CONCURRENT)

            for job in jobs_without_extraction:
                job_id = str(job.get("_id", job.get("jobId", "unknown")))
                if job_id in skills_map:
                    all_skills.append(skills_map[job_id])
                else:
                    failed_count += 1

            print(f"  - Extracted: {len(skills_map)}, Failed: {failed_count}")

        # Aggregate skills
        tech_counter, soft_counter = aggregate_skills(all_skills)

        role_results[role_name] = {
            "jobs_found": len(all_jobs),
            "engineering_roles": len(jobs),
            "existing_extractions": len(jobs_with_extraction),
            "new_extractions": len(jobs_without_extraction) - failed_count,
            "failed_extractions": failed_count,
            "technical_skills": tech_counter,
            "soft_skills": soft_counter,
        }

        print(f"  - Unique technical skills: {len(tech_counter)}")
        print(f"  - Unique soft skills: {len(soft_counter)}")

    # Generate report
    output_path = Path(__file__).parent.parent / "reports" / "skills-analysis.md"
    generate_report(role_results, output_path)

    print("\n" + "=" * 60)
    print("Extraction complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
