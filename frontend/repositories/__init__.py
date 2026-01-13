"""
Frontend Repository Pattern for MongoDB Operations

Provides abstraction layer over MongoDB for eventual dual-write
(Atlas + VPS) support.

This is a copy of src/common/repositories/ for Vercel deployment,
which only includes the frontend/ directory.

Public API:
- get_job_repository(): Factory to get job repository instance
- JobRepositoryInterface: Abstract interface for jobs collection
- WriteResult: Result dataclass for write operations
"""

from .base import JobRepositoryInterface, WriteResult
from .config import (
    get_job_repository,
    reset_repository,
    RepositoryConfig,
    SyncMode,
)

__all__ = [
    "get_job_repository",
    "reset_repository",
    "JobRepositoryInterface",
    "WriteResult",
    "RepositoryConfig",
    "SyncMode",
]
