#!/usr/bin/env python3
"""Create iteration-4.1 blueprint artifact indexes."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger("iteration41_blueprint_indexes")


def get_db() -> Any:
    from pymongo import MongoClient

    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment")
    return MongoClient(uri)["jobs"]


def build_index_plan() -> dict[str, list[dict[str, Any]]]:
    return {
        "jd_facts": [
            {
                "keys": [
                    ("job_id", ASCENDING),
                    ("jd_text_hash", ASCENDING),
                    ("extractor_version", ASCENDING),
                    ("judge_prompt_version", ASCENDING),
                ],
                "kwargs": {"name": "jd_facts_unique", "unique": True},
            }
        ],
        "job_inference": [
            {
                "keys": [
                    ("jd_facts_id", ASCENDING),
                    ("research_enrichment_id", ASCENDING),
                    ("prompt_version", ASCENDING),
                    ("taxonomy_version", ASCENDING),
                ],
                "kwargs": {"name": "job_inference_unique", "unique": True},
            }
        ],
        "job_hypotheses": [
            {
                "keys": [
                    ("jd_facts_id", ASCENDING),
                    ("research_enrichment_id", ASCENDING),
                    ("prompt_version", ASCENDING),
                    ("taxonomy_version", ASCENDING),
                ],
                "kwargs": {"name": "job_hypotheses_unique", "unique": True},
            }
        ],
        "research_enrichment": [
            {
                "keys": [("job_id", ASCENDING), ("input_snapshot_id", ASCENDING), ("research_version", ASCENDING)],
                "kwargs": {"name": "research_enrichment_unique", "unique": True},
            },
            {
                "keys": [("job_id", ASCENDING), ("created_at", DESCENDING)],
                "kwargs": {"name": "research_enrichment_job_recent"},
            },
            {
                "keys": [("jd_facts_id", ASCENDING), ("classification_id", ASCENDING), ("application_surface_id", ASCENDING)],
                "kwargs": {"name": "research_enrichment_refs"},
            },
            {
                "keys": [("status", ASCENDING), ("updated_at", DESCENDING)],
                "kwargs": {"name": "research_enrichment_status_updated"},
            },
            {
                "keys": [("company_profile.canonical_domain", ASCENDING), ("status", ASCENDING)],
                "kwargs": {"name": "research_enrichment_company_domain_status"},
            }
        ],
        "research_company_cache": [
            {
                "keys": [("cache_key", ASCENDING)],
                "kwargs": {"name": "research_company_cache_key", "unique": True},
            }
        ],
        "research_application_cache": [
            {
                "keys": [("cache_key", ASCENDING)],
                "kwargs": {"name": "research_application_cache_key", "unique": True},
            }
        ],
        "research_stakeholder_cache": [
            {
                "keys": [("cache_key", ASCENDING)],
                "kwargs": {"name": "research_stakeholder_cache_key", "unique": True},
            }
        ],
        "cv_guidelines": [
            {
                "keys": [
                    ("jd_facts_id", ASCENDING),
                    ("job_inference_id", ASCENDING),
                    ("research_enrichment_id", ASCENDING),
                    ("prompt_version", ASCENDING),
                ],
                "kwargs": {"name": "cv_guidelines_unique", "unique": True},
            }
        ],
        "job_blueprint": [
            {
                "keys": [("job_id", ASCENDING), ("blueprint_version", ASCENDING)],
                "kwargs": {"name": "job_blueprint_unique", "unique": True},
            },
            {
                "keys": [("jd_facts_id", ASCENDING)],
                "kwargs": {"name": "job_blueprint_jd_facts_id"},
            },
            {
                "keys": [("job_inference_id", ASCENDING)],
                "kwargs": {"name": "job_blueprint_job_inference_id"},
            },
            {
                "keys": [("research_enrichment_id", ASCENDING)],
                "kwargs": {"name": "job_blueprint_research_enrichment_id"},
            },
            {
                "keys": [("cv_guidelines_id", ASCENDING)],
                "kwargs": {"name": "job_blueprint_cv_guidelines_id"},
            },
        ],
        "level-2": [
            {
                "keys": [("pre_enrichment.job_blueprint_refs.job_blueprint_id", ASCENDING)],
                "kwargs": {"name": "preenrich_job_blueprint_ref"},
            },
            {
                "keys": [
                    ("pre_enrichment.job_blueprint_status", ASCENDING),
                    ("pre_enrichment.job_blueprint_updated_at", DESCENDING),
                ],
                "kwargs": {"name": "preenrich_job_blueprint_status"},
            },
        ],
    }


def ensure_iteration41_indexes(db: Any, *, dry_run: bool = False) -> list[str]:
    created: list[str] = []
    for collection_name, specs in build_index_plan().items():
        collection = db[collection_name]
        for spec in specs:
            name = spec["kwargs"]["name"]
            if dry_run:
                created.append(name)
                continue
            collection.create_index(spec["keys"], **spec["kwargs"])
            created.append(name)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Create iteration-4.1 blueprint indexes")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    created = ensure_iteration41_indexes(get_db(), dry_run=args.dry_run)
    logger.info("iteration-4.1 blueprint indexes ensured=%d", len(created))


if __name__ == "__main__":
    main()
