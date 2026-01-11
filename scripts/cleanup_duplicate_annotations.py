#!/usr/bin/env python3
"""
Cleanup Duplicate Annotations from MongoDB

This script removes duplicate annotations that were created due to a bug where
editing annotations created new ones instead of updating existing ones.

Definition of Duplicate:
    Two annotations are duplicates if they have the same:
    - target.text (the annotated text)
    - target.char_start (optional, if available)
    - target.char_end (optional, if available)

Cleanup Strategy:
    For each group of duplicates:
    1. Keep the MOST RECENT one (highest created_at timestamp)
    2. Remove all older duplicates
    3. If no created_at, keep the first one encountered

Usage:
    # Dry run (preview only - default)
    python scripts/cleanup_duplicate_annotations.py --dry-run

    # Actually clean up
    python scripts/cleanup_duplicate_annotations.py

    # Verbose output
    python scripts/cleanup_duplicate_annotations.py --dry-run --verbose
"""

import argparse
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from pymongo import MongoClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_collection():
    """Get MongoDB level-2 collection."""
    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "jobs")
    collection_name = os.getenv("MONGO_COLLECTION", "level-2")

    if not mongo_uri:
        raise ValueError("MONGODB_URI or MONGO_URI environment variable required")

    client = MongoClient(mongo_uri)
    db = client[db_name]
    return db[collection_name]


def get_annotation_key(annotation: Dict[str, Any]) -> Tuple[str, Optional[int], Optional[int]]:
    """
    Generate a unique key for an annotation based on target text and position.

    Returns:
        Tuple of (text, char_start, char_end) where char_start/char_end may be None
    """
    target = annotation.get("target", {})
    text = target.get("text", "")
    char_start = target.get("char_start")
    char_end = target.get("char_end")

    return (text, char_start, char_end)


def get_annotation_timestamp(annotation: Dict[str, Any]) -> datetime:
    """
    Get the created_at timestamp for an annotation.

    Returns:
        datetime object, or datetime.min if no timestamp
    """
    created_at = annotation.get("created_at")
    if not created_at:
        return datetime.min

    if isinstance(created_at, datetime):
        return created_at

    # Parse ISO string
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min


def find_duplicates(annotations: List[Dict[str, Any]]) -> Dict[Tuple, List[Dict[str, Any]]]:
    """
    Group annotations by their key and identify groups with duplicates.

    Returns:
        Dict mapping keys to lists of annotations (only groups with > 1 annotation)
    """
    groups = defaultdict(list)

    for annotation in annotations:
        key = get_annotation_key(annotation)
        groups[key].append(annotation)

    # Only return groups with duplicates
    return {key: annots for key, annots in groups.items() if len(annots) > 1}


def select_annotation_to_keep(annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Select which annotation to keep from a group of duplicates.

    Strategy: Keep the most recent (highest created_at timestamp).
    If no timestamps, keep the first one.

    Returns:
        The annotation to keep
    """
    # Sort by created_at descending (most recent first)
    sorted_annotations = sorted(
        annotations,
        key=get_annotation_timestamp,
        reverse=True
    )
    return sorted_annotations[0]


def deduplicate_annotations(
    annotations: List[Dict[str, Any]],
    verbose: bool = False
) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    """
    Remove duplicate annotations from a list.

    Returns:
        Tuple of (deduplicated_list, duplicates_removed, duplicate_details)
    """
    duplicate_groups = find_duplicates(annotations)

    if not duplicate_groups:
        return annotations, 0, []

    # Build set of annotation IDs to remove
    ids_to_remove = set()
    duplicate_details = []

    for key, group in duplicate_groups.items():
        keeper = select_annotation_to_keep(group)
        keeper_id = keeper.get("id", "unknown")

        for annotation in group:
            ann_id = annotation.get("id", "unknown")
            if ann_id != keeper_id:
                ids_to_remove.add(ann_id)
                if verbose:
                    text_preview = key[0][:50] + "..." if len(key[0]) > 50 else key[0]
                    duplicate_details.append(
                        f"  Remove: {ann_id} (text: '{text_preview}', "
                        f"created: {annotation.get('created_at', 'unknown')})"
                    )

    # Filter out duplicates
    deduplicated = [
        ann for ann in annotations
        if ann.get("id", "unknown") not in ids_to_remove
    ]

    return deduplicated, len(ids_to_remove), duplicate_details


def cleanup_job_annotations(
    collection,
    job: Dict[str, Any],
    dry_run: bool = True,
    verbose: bool = False
) -> Dict[str, Any]:
    """
    Clean up duplicate annotations for a single job.

    Returns:
        Dict with cleanup results
    """
    job_id = job["_id"]
    title = job.get("title", "No title")
    jd_annotations = job.get("jd_annotations", {})
    annotations = jd_annotations.get("annotations", [])

    if not annotations:
        return {"job_id": str(job_id), "duplicates_removed": 0, "status": "no_annotations"}

    # Deduplicate
    deduplicated, removed_count, details = deduplicate_annotations(annotations, verbose)

    if removed_count == 0:
        return {"job_id": str(job_id), "duplicates_removed": 0, "status": "no_duplicates"}

    result = {
        "job_id": str(job_id),
        "title": title,
        "original_count": len(annotations),
        "final_count": len(deduplicated),
        "duplicates_removed": removed_count,
        "details": details,
        "status": "cleaned" if not dry_run else "would_clean"
    }

    if not dry_run:
        # Update the job document
        updated_jd_annotations = {**jd_annotations, "annotations": deduplicated}

        # Update aggregate counts if they exist
        if "relevance_counts" in updated_jd_annotations or "type_counts" in updated_jd_annotations:
            # Recalculate counts
            relevance_counts = defaultdict(int)
            type_counts = defaultdict(int)
            reframe_count = 0
            gap_count = 0

            for ann in deduplicated:
                if ann.get("relevance"):
                    relevance_counts[ann["relevance"]] += 1
                if ann.get("annotation_type"):
                    type_counts[ann["annotation_type"]] += 1
                if ann.get("has_reframe"):
                    reframe_count += 1
                if ann.get("relevance") == "gap":
                    gap_count += 1

            updated_jd_annotations["relevance_counts"] = dict(relevance_counts)
            updated_jd_annotations["type_counts"] = dict(type_counts)
            updated_jd_annotations["reframe_count"] = reframe_count
            updated_jd_annotations["gap_count"] = gap_count

        collection.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "jd_annotations": updated_jd_annotations,
                    "jd_annotations_dedupe_at": datetime.utcnow()
                }
            }
        )
        result["status"] = "cleaned"

    return result


def run_cleanup(dry_run: bool = True, verbose: bool = False):
    """
    Run the duplicate annotation cleanup across all jobs.
    """
    collection = get_collection()

    # Find all jobs with jd_annotations.annotations array
    query = {
        "jd_annotations.annotations": {"$exists": True},
        "jd_annotations.annotations.0": {"$exists": True}  # Has at least one annotation
    }

    jobs = list(collection.find(
        query,
        {
            "_id": 1,
            "title": 1,
            "company": 1,
            "jd_annotations": 1
        }
    ))

    print(f"\n{'='*70}")
    print(f"Duplicate Annotation Cleanup")
    print(f"{'='*70}")
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'LIVE (will modify database)'}")
    print(f"Jobs with annotations found: {len(jobs)}")
    print(f"{'='*70}\n")

    if not jobs:
        print("No jobs with annotations found.")
        return

    # Process each job
    total_duplicates_removed = 0
    jobs_with_duplicates = []

    for job in jobs:
        result = cleanup_job_annotations(collection, job, dry_run=dry_run, verbose=verbose)

        if result["duplicates_removed"] > 0:
            total_duplicates_removed += result["duplicates_removed"]
            jobs_with_duplicates.append(result)

            print(f"\nJob: {result.get('title', 'Unknown')}")
            print(f"  ID: {result['job_id']}")
            print(f"  Annotations: {result['original_count']} -> {result['final_count']} "
                  f"({result['duplicates_removed']} duplicates {'removed' if not dry_run else 'to remove'})")

            if verbose and result.get("details"):
                for detail in result["details"]:
                    print(detail)

    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Jobs scanned: {len(jobs)}")
    print(f"Jobs with duplicates: {len(jobs_with_duplicates)}")
    print(f"Total duplicates {'removed' if not dry_run else 'to remove'}: {total_duplicates_removed}")

    if dry_run and total_duplicates_removed > 0:
        print(f"\n{'='*70}")
        print("To apply these changes, run without --dry-run flag:")
        print("  python scripts/cleanup_duplicate_annotations.py")
        print(f"{'='*70}")
    elif not dry_run and total_duplicates_removed > 0:
        print(f"\nCleanup complete! {total_duplicates_removed} duplicate annotations removed.")
    else:
        print("\nNo duplicates found. Database is clean.")


def main():
    parser = argparse.ArgumentParser(
        description="Clean up duplicate annotations in MongoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview what would be cleaned (safe, no changes)
    python scripts/cleanup_duplicate_annotations.py --dry-run

    # Actually perform the cleanup
    python scripts/cleanup_duplicate_annotations.py

    # Verbose output showing each duplicate
    python scripts/cleanup_duplicate_annotations.py --dry-run --verbose
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database (recommended first run)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed information about each duplicate"
    )

    args = parser.parse_args()

    # Default to dry-run if no flag specified (safety measure)
    # User must explicitly NOT pass --dry-run to make changes
    if not args.dry_run:
        print("\n" + "!"*70)
        print("WARNING: Running in LIVE mode. This will modify the database.")
        print("!"*70)
        response = input("\nType 'yes' to continue, or press Enter to abort: ")
        if response.lower() != 'yes':
            print("Aborted. Run with --dry-run to preview changes first.")
            sys.exit(0)

    try:
        run_cleanup(dry_run=args.dry_run, verbose=args.verbose)
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
