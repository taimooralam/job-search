#!/usr/bin/env python3
"""
Phase 0: Test Single JD Extraction

This script validates that JD extraction works with Claude CLI mandatory (no fallback).
It's a prerequisite before running the full parallel extraction pipeline.

Steps:
1. Connect to MongoDB jobs.level-2 collection
2. Find a sample job matching target roles
3. Run extraction with Claude CLI (no fallback)
4. Validate extraction result and confirm Claude CLI was used

Usage:
    python scripts/test_single_jd_extraction.py
"""

import os
import sys
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient
from src.common.config import Config
from src.layer1_4.claude_jd_extractor import JDExtractor, ExtractionResult
from src.common.llm_config import STEP_CONFIGS, StepConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== TARGET ROLE PATTERNS =====
TARGET_ROLE_PATTERNS = {
    "engineering_manager": r"engineering manager|eng manager|manager.*engineering",
    "staff_principal_engineer": r"staff.*engineer|principal.*engineer|software architect",
    "director_of_engineering": r"director.*engineering|director.*software",
    "head_of_engineering": r"head of engineering|head of software|vp engineering",
    "tech_lead": r"tech lead|lead.*engineer|lead software|team lead.*engineer",
    "senior_engineer": r"senior.*engineer|sr\.?\s*engineer|sr\.?\s*software",
    "cto": r"\bcto\b|chief technology|chief technical",
}


def step_1_verify_mongodb_connection() -> Optional[MongoClient]:
    """
    Step 0.1: Verify MongoDB connection.

    Returns:
        MongoClient if successful, None otherwise
    """
    print("\n" + "=" * 60)
    print("STEP 1: Verify MongoDB Connection")
    print("=" * 60)

    if not Config.MONGODB_URI:
        print("❌ MONGODB_URI not configured in .env")
        return None

    try:
        client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=5000)

        # Force connection to verify
        client.admin.command('ping')
        print(f"✅ Connected to MongoDB")

        # Access jobs database and level-2 collection
        jobs_db = client['jobs']
        level2 = jobs_db['level-2']

        # Get stats
        total_jobs = level2.count_documents({})
        with_extraction = level2.count_documents({"extracted_jd": {"$exists": True, "$ne": None}})
        with_description = level2.count_documents({"description": {"$exists": True, "$ne": ""}})

        print(f"   Database: jobs")
        print(f"   Collection: level-2")
        print(f"   Total jobs: {total_jobs:,}")
        print(f"   With description: {with_description:,}")
        print(f"   Already extracted: {with_extraction:,}")
        print(f"   Needing extraction: {with_description - with_extraction:,}")

        return client

    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return None


def step_2_find_sample_job(client: MongoClient) -> Optional[Dict[str, Any]]:
    """
    Step 0.2: Find a sample job matching target roles.

    Returns:
        Sample job document if found, None otherwise
    """
    print("\n" + "=" * 60)
    print("STEP 2: Find Sample Job")
    print("=" * 60)

    level2 = client['jobs']['level-2']

    # Combine all target role patterns
    combined_pattern = "|".join(f"({p})" for p in TARGET_ROLE_PATTERNS.values())

    # Find a job matching target roles that needs extraction
    sample = level2.find_one({
        "$and": [
            {"title": {"$regex": combined_pattern, "$options": "i"}},
            {"description": {"$exists": True, "$ne": ""}},
            {"$or": [
                {"extracted_jd": {"$exists": False}},
                {"extracted_jd": None},
            ]},
        ]
    })

    if not sample:
        # Fallback: find any job needing extraction
        print("⚠️  No unextracted target role jobs found, trying any job...")
        sample = level2.find_one({
            "$and": [
                {"description": {"$exists": True, "$ne": ""}},
                {"$or": [
                    {"extracted_jd": {"$exists": False}},
                    {"extracted_jd": None},
                ]},
            ]
        })

    if not sample:
        # Last resort: find any job with description (already extracted)
        print("⚠️  No unextracted jobs found, using already extracted job for test...")
        sample = level2.find_one({
            "description": {"$exists": True, "$ne": ""}
        })

    if sample:
        print(f"✅ Found sample job:")
        print(f"   ID: {sample['_id']}")
        print(f"   Title: {sample.get('title', 'N/A')}")
        print(f"   Company: {sample.get('company', 'N/A')}")
        print(f"   Description length: {len(sample.get('description', '')):,} chars")

        # Detect which role pattern it matches
        for role_key, pattern in TARGET_ROLE_PATTERNS.items():
            if re.search(pattern, sample.get('title', ''), re.IGNORECASE):
                print(f"   Matched role: {role_key}")
                break
        else:
            print(f"   Matched role: (no target role match)")

        return sample

    print("❌ No jobs found with descriptions")
    return None


def step_3_configure_mandatory_cli():
    """
    Step 0.3: Configure JD extraction to use Claude CLI mandatory (no fallback).
    """
    print("\n" + "=" * 60)
    print("STEP 3: Configure Mandatory Claude CLI")
    print("=" * 60)

    # Override the jd_extraction step config to disable fallback
    original_config = STEP_CONFIGS.get("jd_extraction", StepConfig())
    print(f"   Original config: tier={original_config.tier}, use_fallback={original_config.use_fallback}")

    # Create new config with use_fallback=False
    STEP_CONFIGS["jd_extraction"] = StepConfig(
        tier=original_config.tier,
        claude_model=original_config.claude_model,
        fallback_model=original_config.fallback_model,
        timeout_seconds=original_config.timeout_seconds,
        max_retries=original_config.max_retries,
        use_fallback=False,  # MANDATORY: Claude CLI only
    )

    updated_config = STEP_CONFIGS["jd_extraction"]
    print(f"   Updated config: tier={updated_config.tier}, use_fallback={updated_config.use_fallback}")
    print(f"   Claude model: {updated_config.get_claude_model()}")
    print("✅ Claude CLI is now mandatory (no fallback)")


def step_4_run_extraction(sample: Dict[str, Any]) -> Optional[ExtractionResult]:
    """
    Step 0.4: Run single extraction with Claude CLI mandatory.

    Returns:
        ExtractionResult if successful, None otherwise
    """
    print("\n" + "=" * 60)
    print("STEP 4: Run Extraction")
    print("=" * 60)

    # Create extraction log callback to capture backend used
    backend_used = {"value": None}

    def extraction_log(job_id: str, level: str, data: Dict[str, Any]) -> None:
        message = data.get("message", "")
        backend = data.get("backend")

        # Capture backend from log
        if backend:
            backend_used["value"] = backend

        # Log with appropriate level
        if level == "error":
            print(f"   ❌ {message}")
        elif level == "warning":
            print(f"   ⚠️  {message}")
        elif level == "info":
            print(f"   ℹ️  {message}")
        else:
            if os.getenv("DEBUG"):
                print(f"   🔍 {message}")

    # Create extractor with mandatory CLI (tier="middle" uses Sonnet)
    extractor = JDExtractor(
        tier="middle",
        log_callback=extraction_log,
    )

    print(f"   Starting extraction...")
    print(f"   Model: {extractor.model}")
    print(f"   Timeout: {extractor.timeout}s")

    start_time = datetime.now()

    result = extractor.extract(
        job_id=str(sample['_id']),
        title=sample.get('title', ''),
        company=sample.get('company', ''),
        job_description=sample.get('description', ''),
    )

    duration = (datetime.now() - start_time).total_seconds()

    print(f"\n   Duration: {duration:.2f}s")
    print(f"   Backend used: {backend_used['value'] or 'unknown'}")

    if result.success:
        print(f"✅ Extraction successful!")
        print(f"   Role category: {result.extracted_jd.get('role_category')}")
        print(f"   Seniority: {result.extracted_jd.get('seniority_level')}")
        print(f"   Technical skills: {len(result.extracted_jd.get('technical_skills', []))}")
        print(f"   Top keywords: {len(result.extracted_jd.get('top_keywords', []))}")
        print(f"   Pain points: {len(result.extracted_jd.get('implied_pain_points', []))}")

        # Show competency weights
        weights = result.extracted_jd.get('competency_weights', {})
        print(f"   Competency weights:")
        print(f"      Delivery: {weights.get('delivery', 0)}%")
        print(f"      Process: {weights.get('process', 0)}%")
        print(f"      Architecture: {weights.get('architecture', 0)}%")
        print(f"      Leadership: {weights.get('leadership', 0)}%")
    else:
        print(f"❌ Extraction failed: {result.error}")

    return result


def step_5_validate_cli_used(result: ExtractionResult) -> bool:
    """
    Step 0.5: Validate that Claude CLI was used (not fallback).

    Returns:
        True if CLI was used, False otherwise
    """
    print("\n" + "=" * 60)
    print("STEP 5: Validate Claude CLI Was Used")
    print("=" * 60)

    if not result:
        print("❌ No result to validate")
        return False

    # Check model used - Claude models start with "claude-"
    is_claude_model = result.model.startswith("claude-")

    print(f"   Model used: {result.model}")
    print(f"   Is Claude model: {is_claude_model}")

    if is_claude_model:
        print("✅ Claude CLI was used successfully (no fallback)")
        return True
    else:
        print("❌ Fallback was used instead of Claude CLI")
        print("   This could indicate Claude CLI authentication issues")
        return False


def main():
    """Run Phase 0 validation."""
    print("\n" + "=" * 60)
    print("PHASE 0: Test Single JD Extraction")
    print("Validates MongoDB connection and Claude CLI extraction")
    print("=" * 60)

    # Step 1: Verify MongoDB connection
    client = step_1_verify_mongodb_connection()
    if not client:
        print("\n❌ Phase 0 FAILED: MongoDB connection issue")
        sys.exit(1)

    # Step 2: Find sample job
    sample = step_2_find_sample_job(client)
    if not sample:
        print("\n❌ Phase 0 FAILED: No suitable jobs found")
        sys.exit(1)

    # Step 3: Configure mandatory CLI
    step_3_configure_mandatory_cli()

    # Step 4: Run extraction
    result = step_4_run_extraction(sample)
    if not result or not result.success:
        print("\n❌ Phase 0 FAILED: Extraction failed")
        sys.exit(1)

    # Step 5: Validate CLI was used
    cli_used = step_5_validate_cli_used(result)
    if not cli_used:
        print("\n⚠️  Phase 0 WARNING: Fallback was used instead of Claude CLI")
        print("   Extraction works but Claude CLI authentication may need attention")

    # Summary
    print("\n" + "=" * 60)
    print("PHASE 0 COMPLETE")
    print("=" * 60)
    print("✅ MongoDB connection: OK")
    print("✅ Sample job found: OK")
    print(f"{'✅' if cli_used else '⚠️ '} Claude CLI: {'OK' if cli_used else 'Fallback used'}")
    print("✅ Extraction: SUCCESS")
    print("\n🚀 Ready to proceed with Phase 1: Parallel extraction")

    # Close connection
    client.close()


if __name__ == "__main__":
    main()
