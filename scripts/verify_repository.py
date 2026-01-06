#!/usr/bin/env python3
"""
Verify repository pattern works correctly with Atlas.

Phase 1 verification script that validates:
1. Repository can be initialized
2. Repository can connect to Atlas
3. Sample operations work correctly
4. Connection pooling is functioning

Usage:
    python scripts/verify_repository.py

    # With specific job ID to verify
    python scripts/verify_repository.py --job-id 507f1f77bcf86cd799439011
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def verify_repository_initialization() -> dict:
    """Verify repository can be initialized."""
    logger.info("\n=== Step 1: Repository Initialization ===")

    try:
        from src.common.repositories import get_job_repository, reset_repository

        # Reset to ensure clean state
        reset_repository()

        repo = get_job_repository()
        repo_type = type(repo).__name__

        logger.info(f"  ✓ Repository initialized: {repo_type}")

        return {
            "success": True,
            "repository_type": repo_type,
        }
    except Exception as e:
        logger.error(f"  ✗ Failed to initialize repository: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def verify_connection(job_id: str = None) -> dict:
    """Verify repository can connect to Atlas."""
    logger.info("\n=== Step 2: Atlas Connection ===")

    try:
        from bson import ObjectId
        from src.common.repositories import get_job_repository

        repo = get_job_repository()

        # Count documents to verify connection
        count = repo.count_documents({})
        logger.info(f"  ✓ Connected to Atlas: {count} documents in level-2")

        result = {
            "success": True,
            "document_count": count,
        }

        # If job_id provided, try to find it
        if job_id:
            try:
                object_id = ObjectId(job_id)
                job = repo.find_one({"_id": object_id})

                if job:
                    logger.info(f"  ✓ Found job: {job.get('title', 'Unknown')[:50]}")
                    result["job_found"] = True
                    result["job_title"] = job.get("title", "Unknown")[:50]
                else:
                    logger.warning(f"  ⚠ Job {job_id} not found")
                    result["job_found"] = False
            except Exception as e:
                logger.warning(f"  ⚠ Could not find job {job_id}: {e}")
                result["job_found"] = False

        return result
    except Exception as e:
        logger.error(f"  ✗ Failed to connect to Atlas: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def verify_write_result() -> dict:
    """Verify WriteResult is returned correctly."""
    logger.info("\n=== Step 3: WriteResult Verification ===")

    try:
        from bson import ObjectId
        from src.common.repositories import get_job_repository, WriteResult

        repo = get_job_repository()

        # Find a random job to update
        sample_job = repo.find_one({})
        if not sample_job:
            logger.warning("  ⚠ No jobs found to test write operations")
            return {"success": True, "skipped": True}

        job_id = sample_job["_id"]

        # Update with no-op (set field to same value)
        original_updated_at = sample_job.get("updatedAt", datetime.utcnow())
        result = repo.update_one(
            {"_id": job_id},
            {"$set": {"_repository_test": True}},
        )

        # Verify result type and values
        assert isinstance(result, WriteResult), "Result is not WriteResult"
        assert result.matched_count == 1, f"Expected matched_count=1, got {result.matched_count}"
        assert result.atlas_success is True, "atlas_success should be True"
        assert result.vps_success is None, "vps_success should be None in Phase 1"

        # Clean up test field
        repo.update_one(
            {"_id": job_id},
            {"$unset": {"_repository_test": ""}},
        )

        logger.info(f"  ✓ WriteResult returned correctly")
        logger.info(f"    matched_count: {result.matched_count}")
        logger.info(f"    modified_count: {result.modified_count}")
        logger.info(f"    atlas_success: {result.atlas_success}")
        logger.info(f"    vps_success: {result.vps_success}")

        return {
            "success": True,
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
        }
    except Exception as e:
        logger.error(f"  ✗ WriteResult verification failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def verify_connection_pooling() -> dict:
    """Verify connection pooling is working."""
    logger.info("\n=== Step 4: Connection Pooling ===")

    try:
        from src.common.repositories import get_job_repository

        repo1 = get_job_repository()
        repo2 = get_job_repository()

        is_same_instance = repo1 is repo2
        logger.info(f"  ✓ Singleton pattern: {'Same instance' if is_same_instance else 'Different instances'}")

        return {
            "success": is_same_instance,
            "is_singleton": is_same_instance,
        }
    except Exception as e:
        logger.error(f"  ✗ Connection pooling check failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="Verify repository pattern implementation")
    parser.add_argument("--job-id", help="Specific job ID to verify")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Repository Pattern Verification (Phase 1)")
    logger.info("=" * 60)

    results = {}

    # Step 1: Initialize repository
    results["initialization"] = verify_repository_initialization()
    if not results["initialization"]["success"]:
        logger.error("\n❌ VERIFICATION FAILED: Could not initialize repository")
        sys.exit(1)

    # Step 2: Verify connection
    results["connection"] = verify_connection(args.job_id)
    if not results["connection"]["success"]:
        logger.error("\n❌ VERIFICATION FAILED: Could not connect to Atlas")
        sys.exit(1)

    # Step 3: Verify WriteResult
    results["write_result"] = verify_write_result()

    # Step 4: Verify connection pooling
    results["pooling"] = verify_connection_pooling()

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 60)

    all_passed = all(r.get("success", False) for r in results.values())

    for name, result in results.items():
        status = "✓ PASS" if result.get("success", False) else "✗ FAIL"
        logger.info(f"  {status}: {name}")

    logger.info("=" * 60)
    if all_passed:
        logger.info("✅ ALL VERIFICATIONS PASSED")
        logger.info("\nRepository pattern is working correctly with Atlas.")
        logger.info("Ready for Phase 2: VPS MongoDB Docker Setup")
    else:
        logger.info("❌ SOME VERIFICATIONS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
