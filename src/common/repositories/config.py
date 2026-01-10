"""
Repository Configuration and Factory

Provides factory function to get the appropriate repository implementation
based on environment configuration.
"""

import os
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .base import JobRepositoryInterface
from .priors_repository import PriorsRepositoryInterface

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

        Returns:
            RepositoryConfig instance

        Raises:
            ValueError: If MONGODB_URI is not set
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

    Returns:
        JobRepositoryInterface implementation

    Raises:
        ValueError: If MongoDB URI is not configured
    """
    global _repository_instance

    if _repository_instance is None:
        config = RepositoryConfig.from_env()

        if config.vps_enabled and config.sync_mode != SyncMode.DISABLED:
            # Phase 3+: Dual-write repository
            # TODO: Implement DualWriteJobRepository
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
    """
    Reset the repository singleton.

    Used for testing or when configuration changes.
    """
    global _repository_instance

    if _repository_instance is not None:
        # Reset connection pool if applicable
        from .atlas_repository import AtlasJobRepository
        if isinstance(_repository_instance, AtlasJobRepository):
            AtlasJobRepository.reset_connection()

    _repository_instance = None
    logger.info("Repository singleton reset")


# Singleton priors repository instance
_priors_repository_instance: Optional[PriorsRepositoryInterface] = None


def get_priors_repository() -> PriorsRepositoryInterface:
    """
    Get the priors repository instance.

    Factory function that returns the appropriate repository implementation
    for the annotation_priors collection based on configuration.
    Uses singleton pattern for connection pooling.

    Phase 1: Returns AtlasPriorsRepository
    Phase 3+: Will return DualWritePriorsRepository when VPS is enabled

    Returns:
        PriorsRepositoryInterface implementation

    Raises:
        ValueError: If MongoDB URI is not configured
    """
    global _priors_repository_instance

    if _priors_repository_instance is None:
        config = RepositoryConfig.from_env()

        if config.vps_enabled and config.sync_mode != SyncMode.DISABLED:
            # Phase 3+: Dual-write repository
            raise NotImplementedError(
                "Dual-write priors repository not yet implemented. "
                "Set VPS_MONGODB_ENABLED=false for Phase 1."
            )
        else:
            # Phase 1: Atlas-only
            from .priors_repository import AtlasPriorsRepository
            _priors_repository_instance = AtlasPriorsRepository(
                mongodb_uri=config.atlas_uri,
                database=config.database,
                collection="annotation_priors",
            )
            logger.info("Initialized Atlas-only priors repository (Phase 1)")

    return _priors_repository_instance


def reset_priors_repository() -> None:
    """
    Reset the priors repository singleton.

    Used for testing or when configuration changes.
    """
    global _priors_repository_instance

    if _priors_repository_instance is not None:
        from .priors_repository import AtlasPriorsRepository
        if isinstance(_priors_repository_instance, AtlasPriorsRepository):
            AtlasPriorsRepository.reset_connection()

    _priors_repository_instance = None
    logger.info("Priors repository singleton reset")
