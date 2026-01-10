#!/usr/bin/env python3
"""
Initialize Annotation Priors from Historical Annotations

This script builds the initial priors document by:
1. Loading all existing annotations from MongoDB (~2900+ annotations)
2. Computing sentence embeddings using sentence-transformers
3. Building skill priors from annotation patterns
4. Saving to MongoDB for use by the suggestion system

Run this once after deploying the annotation suggestion feature,
or whenever you need to rebuild the priors from scratch.

Usage:
    cd /path/to/job-search
    source .venv/bin/activate
    python scripts/initialize_annotation_priors.py

    # With options:
    python scripts/initialize_annotation_priors.py --force  # Force rebuild even if exists
    python scripts/initialize_annotation_priors.py --dry-run  # Show stats without saving
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Initialize annotation priors from historical annotations"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild even if priors already exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show stats without saving to MongoDB",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("=" * 60)
    logger.info("Annotation Priors Initialization")
    logger.info("=" * 60)

    # Import after logging setup to capture import logs
    try:
        from src.services.annotation_priors import (
            load_priors,
            rebuild_priors,
            save_priors,
            get_priors_stats,
            should_rebuild_priors,
        )
    except ImportError as e:
        logger.error(f"Failed to import annotation_priors module: {e}")
        logger.error("Make sure you're running from the job-search directory with venv activated")
        sys.exit(1)

    # Step 1: Load existing priors (or create empty)
    logger.info("\n[Step 1] Loading existing priors...")
    priors = load_priors()

    current_count = priors.get("sentence_index", {}).get("count", 0)
    logger.info(f"  Current embeddings indexed: {current_count}")
    logger.info(f"  Current skills tracked: {len(priors.get('skill_priors', {}))}")

    # Check if rebuild needed
    needs_rebuild = should_rebuild_priors(priors)
    logger.info(f"  Rebuild recommended: {needs_rebuild}")

    if current_count > 0 and not args.force and not needs_rebuild:
        logger.info("\nPriors already exist and are up-to-date.")
        logger.info("Use --force to rebuild anyway.")

        # Show current stats
        stats = get_priors_stats(priors)
        logger.info("\nCurrent priors stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        return 0

    # Step 2: Rebuild priors
    logger.info("\n[Step 2] Rebuilding priors from all annotations...")
    start_time = datetime.now()

    try:
        priors = rebuild_priors(priors)
    except Exception as e:
        logger.error(f"Failed to rebuild priors: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"  Rebuild completed in {duration:.1f} seconds")

    # Show new stats
    new_count = priors.get("sentence_index", {}).get("count", 0)
    skills_count = len(priors.get("skill_priors", {}))
    logger.info(f"  Annotations indexed: {new_count}")
    logger.info(f"  Skills tracked: {skills_count}")

    # Step 3: Save priors
    if args.dry_run:
        logger.info("\n[Step 3] Dry run - NOT saving to MongoDB")
    else:
        logger.info("\n[Step 3] Saving priors to MongoDB...")
        success = save_priors(priors)
        if success:
            logger.info("  Priors saved successfully!")
        else:
            logger.error("  Failed to save priors!")
            sys.exit(1)

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("INITIALIZATION COMPLETE")
    logger.info("=" * 60)

    stats = get_priors_stats(priors)
    logger.info("\nFinal priors stats:")
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")

    # Show some sample skills
    skill_priors = priors.get("skill_priors", {})
    if skill_priors:
        logger.info("\nSample skill priors (top 10 by observation count):")
        sorted_skills = sorted(
            skill_priors.items(),
            key=lambda x: x[1].get("relevance", {}).get("n", 0),
            reverse=True
        )[:10]

        for skill, prior in sorted_skills:
            rel = prior.get("relevance", {})
            logger.info(
                f"  {skill}: relevance={rel.get('value')} "
                f"(conf={rel.get('confidence', 0):.2f}, n={rel.get('n', 0)})"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
