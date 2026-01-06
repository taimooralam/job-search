"""
Repository Pattern for MongoDB Operations

Provides abstraction layer over MongoDB for eventual dual-write
(Atlas + VPS) support.

Public API:
- get_job_repository(): Factory to get repository instance
- JobRepositoryInterface: Abstract interface for type hints
- WriteResult: Result dataclass for write operations

Usage:
    from src.common.repositories import get_job_repository

    repo = get_job_repository()
    result = repo.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"status": "completed"}}
    )

Phase Migration:
- Phase 1: Atlas-only (current)
- Phase 3: Shadow mode (log VPS writes)
- Phase 4: Write-through (actual dual-write)
- Phase 5: Read validation (compare Atlas vs VPS)
"""

from .base import JobRepositoryInterface, WriteResult
from .config import get_job_repository, reset_repository, RepositoryConfig, SyncMode

__all__ = [
    "get_job_repository",
    "reset_repository",
    "JobRepositoryInterface",
    "WriteResult",
    "RepositoryConfig",
    "SyncMode",
]
