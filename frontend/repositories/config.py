"""
Repository Configuration and Factory

Provides factory function to get the appropriate repository implementation
based on environment configuration.

NOTE: This is a simplified copy for frontend/Vercel deployment.
Keep in sync with src/common/repositories/config.py
"""

import os
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .base import JobRepositoryInterface

logger = logging.getLogger(__name__)


class SyncMode(str, Enum):
    """VPS sync mode for dual-write operations."""
    DISABLED = "disabled"  # Phase 1: Atlas-only
    SHADOW = "shadow"      # Phase 3: Log what would be written
    WRITE = "write"        # Phase 4: Actual dual-write
    READ_COMPARE = "read_compare"  # Phase 5: Compare Atlas vs VPS reads


@dataclass
class RepositoryConfig:
    """
    Configuration for repository initialization.

    Loaded from environment variables with sensible defaults.
    """
    # Atlas (required)
    atlas_uri: str

    # Database/collection names
    database: str = "jobs"
    collection: str = "level-2"

    # VPS configuration (Phase 3+)
    vps_enabled: bool = False
    vps_uri: Optional[str] = None
    sync_mode: SyncMode = SyncMode.DISABLED

    @classmethod
    def from_env(cls) -> "RepositoryConfig":
        """
        Load configuration from environment variables.

        Environment variables:
        - MONGODB_URI (required): Atlas MongoDB connection string
        - VPS_MONGODB_URI: VPS MongoDB connection string
        - VPS_MONGODB_ENABLED: Enable VPS sync (true/false)
        - VPS_SYNC_MODE: Sync mode (disabled/shadow/write/read_compare)
        """
        atlas_uri = os.getenv("MONGODB_URI")
        if not atlas_uri:
            raise ValueError("MONGODB_URI environment variable is required")

        vps_enabled = os.getenv("VPS_MONGODB_ENABLED", "false").lower() == "true"
        vps_uri = os.getenv("VPS_MONGODB_URI")

        sync_mode_str = os.getenv("VPS_SYNC_MODE", "disabled").lower()
        try:
            sync_mode = SyncMode(sync_mode_str)
        except ValueError:
            logger.warning(f"Invalid VPS_SYNC_MODE '{sync_mode_str}', defaulting to disabled")
            sync_mode = SyncMode.DISABLED

        return cls(
            atlas_uri=atlas_uri,
            vps_enabled=vps_enabled,
            vps_uri=vps_uri,
            sync_mode=sync_mode,
        )


# Singleton repository instance
_repository_instance: Optional[JobRepositoryInterface] = None


def get_job_repository() -> JobRepositoryInterface:
    """
    Get the job repository instance.

    Factory function that returns the appropriate repository implementation
    based on configuration. Uses singleton pattern for connection pooling.

    Phase 1: Returns AtlasJobRepository
    Phase 3+: Will return DualWriteJobRepository when VPS is enabled
    """
    global _repository_instance

    if _repository_instance is None:
        config = RepositoryConfig.from_env()

        if config.vps_enabled and config.sync_mode != SyncMode.DISABLED:
            # Phase 3+: Dual-write repository
            raise NotImplementedError(
                "Dual-write repository not yet implemented. "
                "Set VPS_MONGODB_ENABLED=false for Phase 1."
            )
        else:
            # Phase 1: Atlas-only
            from .atlas_repository import AtlasJobRepository
            _repository_instance = AtlasJobRepository(
                mongodb_uri=config.atlas_uri,
                database=config.database,
                collection=config.collection,
            )
            logger.info("Initialized Atlas-only job repository (Phase 1)")

    return _repository_instance


def reset_repository() -> None:
    """Reset the repository singleton."""
    global _repository_instance

    if _repository_instance is not None:
        from .atlas_repository import AtlasJobRepository
        if isinstance(_repository_instance, AtlasJobRepository):
            AtlasJobRepository.reset_connection()

    _repository_instance = None
    logger.info("Repository singleton reset")
