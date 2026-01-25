#!/usr/bin/env python3
"""
Cleanup Discarded Jobs from MongoDB level-2 Collection

This script permanently deletes all jobs with status: "discarded" from the
level-2 collection. These are jobs that were explicitly marked as not relevant
during the job review process.

Usage:
    # Dry run (preview only - default)
    python scripts/cleanup_discarded_jobs.py --dry-run

    # Actually delete
    python scripts/cleanup_discarded_jobs.py

    # Show sample of jobs that would be deleted
    python scripts/cleanup_discarded_jobs.py --dry-run --sample 5
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from src.common.repositories import get_job_repository


def run_cleanup(dry_run: bool = True, sample_count: int = 0):
    """
    Delete all discarded jobs from the level-2 collection.

    Args:
        dry_run: If True, only preview what would be deleted
        sample_count: Number of sample jobs to show (0 for none)
    """
    repo = get_job_repository()

    # Count discarded jobs
    query = {"status": "discarded"}
    count = repo.count_documents(query)

    print(f"\n{'='*60}")
    print(f"Discarded Jobs Cleanup")
    print(f"{'='*60}")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE (will delete)'}")
    print(f"Discarded jobs found: {count:,}")
    print(f"{'='*60}\n")

    if count == 0:
        print("No discarded jobs to delete. Collection is clean.")
        return

    # Show sample if requested
    if sample_count > 0:
        print(f"Sample of jobs to delete (showing {min(sample_count, count)}):\n")
        sample = repo.find(query, {"_id": 1, "title": 1, "company": 1}, limit=sample_count)
        for job in sample:
            print(f"  - {job.get('company', 'Unknown')}: {job.get('title', 'No title')}")
            print(f"    ID: {job['_id']}")
        print()

    if dry_run:
        print(f"Would delete {count:,} discarded jobs.")
        print(f"\n{'='*60}")
        print("To apply deletion, run without --dry-run flag:")
        print("  python scripts/cleanup_discarded_jobs.py")
        print(f"{'='*60}")
    else:
        # Perform actual deletion
        result = repo.delete_many(query)

        print(f"\n{'='*60}")
        print(f"DELETION COMPLETE")
        print(f"{'='*60}")
        # WriteResult uses modified_count for delete operations
        print(f"Jobs deleted: {result.modified_count:,}")

        # Verify deletion
        remaining = repo.count_documents(query)
        print(f"Remaining discarded jobs: {remaining}")

        if remaining > 0:
            print("\nWARNING: Some discarded jobs were not deleted!")
        else:
            print("\nAll discarded jobs have been removed.")


def main():
    parser = argparse.ArgumentParser(
        description="Delete all discarded jobs from MongoDB level-2 collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview what would be deleted (safe, no changes)
    python scripts/cleanup_discarded_jobs.py --dry-run

    # Show sample of jobs to delete
    python scripts/cleanup_discarded_jobs.py --dry-run --sample 5

    # Actually perform the deletion
    python scripts/cleanup_discarded_jobs.py
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletion without modifying database (recommended first run)"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        metavar="N",
        help="Show N sample jobs that would be deleted"
    )

    args = parser.parse_args()

    # Confirmation prompt for live mode
    if not args.dry_run:
        print("\n" + "!"*60)
        print("WARNING: Running in LIVE mode. This will PERMANENTLY DELETE jobs.")
        print("!"*60)
        response = input("\nType 'yes' to continue, or press Enter to abort: ")
        if response.lower() != 'yes':
            print("Aborted. Run with --dry-run to preview changes first.")
            sys.exit(0)

    try:
        run_cleanup(dry_run=args.dry_run, sample_count=args.sample)
    except Exception as e:
        print(f"Cleanup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
