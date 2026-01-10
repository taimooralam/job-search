"""
Repository Pattern for MongoDB Operations

Provides abstraction layer over MongoDB for eventual dual-write
(Atlas + VPS) support.

Public API:
- get_job_repository(): Factory to get job repository instance
- get_priors_repository(): Factory to get priors repository instance
- JobRepositoryInterface: Abstract interface for jobs collection
- PriorsRepositoryInterface: Abstract interface for priors collection
- WriteResult: Result dataclass for write operations

Usage:
    from src.common.repositories import get_job_repository, get_priors_repository

    # For jobs (level-2 collection)
    job_repo = get_job_repository()
    result = job_repo.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "completed"}}
    )

    # For annotation priors
    priors_repo = get_priors_repository()
    doc = priors_repo.find_one({"_id": "annotation_priors"})

Phase Migration:
- Phase 1: Atlas-only (current)
- Phase 3: Shadow mode (log VPS writes)
- Phase 4: Write-through (actual dual-write)
- Phase 5: Read validation (compare Atlas vs VPS)
"""

from .base import JobRepositoryInterface, WriteResult
from .priors_repository import PriorsRepositoryInterface
from .config import (
    get_job_repository,
    reset_repository,
    get_priors_repository,
    reset_priors_repository,
    RepositoryConfig,
    SyncMode,
)

__all__ = [
    # Job repository
    "get_job_repository",
    "reset_repository",
    "JobRepositoryInterface",
    # Priors repository
    "get_priors_repository",
    "reset_priors_repository",
    "PriorsRepositoryInterface",
    # Shared
    "WriteResult",
    "RepositoryConfig",
    "SyncMode",
]
