"""
Job Sources Module

Provides unified interfaces for fetching jobs from multiple sources:
- Indeed (via JobSpy)
- Himalayas.app (remote jobs API)

Each source implements the JobSource abstract base class for consistent handling.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class JobData:
    """Unified job data structure across all sources."""
    title: str
    company: str
    location: str
    description: str
    url: str
    salary: Optional[str] = None
    job_type: Optional[str] = None  # full-time, part-time, contract
    posted_date: Optional[datetime] = None
    source_id: Optional[str] = None  # Original ID from the source


class JobSource(ABC):
    """Abstract base class for job data sources."""

    @abstractmethod
    def fetch_jobs(self, search_config: dict) -> List[JobData]:
        """
        Fetch jobs from the source based on search configuration.

        Args:
            search_config: Dictionary with source-specific search parameters

        Returns:
            List of JobData objects
        """
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """
        Get the unique identifier for this source.

        Returns:
            Source name (e.g., "indeed_auto", "himalayas_auto")
        """
        pass

    def generate_dedupe_key(self, job: JobData) -> str:
        """
        Generate a deduplication key for a job.

        Format: company|title|location|source (lowercase, normalized)

        Args:
            job: JobData object

        Returns:
            Deduplication key string
        """
        company = (job.company or "").lower().strip()
        title = (job.title or "").lower().strip()
        location = (job.location or "").lower().strip()
        source = self.get_source_name()

        return f"{company}|{title}|{location}|{source}"


# Import concrete implementations for convenience
from .indeed_source import IndeedSource
from .himalayas_source import HimalayasSource

__all__ = ["JobSource", "JobData", "IndeedSource", "HimalayasSource"]
