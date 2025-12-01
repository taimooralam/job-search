"""
Automated Job Ingestion Configuration

Loads configuration from environment variables for the automated
job ingestion system (Indeed via JobSpy + Himalayas.app).
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class IngestConfig:
    """Configuration for automated job ingestion."""

    # General settings
    enabled: bool = True
    score_threshold: int = 70  # Minimum quick_score for auto-ingestion (Tier B+)
    results_per_source: int = 50  # Max jobs to fetch per source per run

    # Indeed/JobSpy settings
    indeed_search_terms: List[str] = field(default_factory=list)
    indeed_locations: List[str] = field(default_factory=list)
    indeed_country: str = "USA"
    indeed_hours_old: Optional[int] = None  # Only fetch jobs posted within N hours

    # Himalayas settings
    himalayas_keywords: List[str] = field(default_factory=list)
    himalayas_max_results: int = 100
    himalayas_worldwide_only: bool = False

    @classmethod
    def from_env(cls) -> "IngestConfig":
        """
        Load configuration from environment variables.

        Environment variables:
            AUTO_INGEST_ENABLED: Enable/disable auto-ingestion (default: true)
            AUTO_INGEST_SCORE_THRESHOLD: Minimum score for ingestion (default: 70)
            AUTO_INGEST_RESULTS_PER_SOURCE: Max results per source (default: 50)

            INDEED_SEARCH_TERMS: Comma-separated search terms
            INDEED_LOCATIONS: Comma-separated locations
            INDEED_COUNTRY: Country code (default: USA)
            INDEED_HOURS_OLD: Only jobs within N hours (optional)

            HIMALAYAS_KEYWORDS: Comma-separated filter keywords
            HIMALAYAS_MAX_RESULTS: Max results (default: 100)
            HIMALAYAS_WORLDWIDE_ONLY: Only worldwide jobs (default: false)
        """
        def parse_bool(val: str, default: bool = False) -> bool:
            if not val:
                return default
            return val.lower() in ("true", "1", "yes", "on")

        def parse_list(val: str) -> List[str]:
            if not val:
                return []
            return [item.strip() for item in val.split(",") if item.strip()]

        def parse_int(val: str, default: int) -> int:
            if not val:
                return default
            try:
                return int(val)
            except ValueError:
                return default

        return cls(
            enabled=parse_bool(os.getenv("AUTO_INGEST_ENABLED", "true"), True),
            score_threshold=parse_int(os.getenv("AUTO_INGEST_SCORE_THRESHOLD"), 70),
            results_per_source=parse_int(os.getenv("AUTO_INGEST_RESULTS_PER_SOURCE"), 50),

            indeed_search_terms=parse_list(os.getenv("INDEED_SEARCH_TERMS", "")),
            indeed_locations=parse_list(os.getenv("INDEED_LOCATIONS", "")),
            indeed_country=os.getenv("INDEED_COUNTRY", "USA"),
            indeed_hours_old=parse_int(os.getenv("INDEED_HOURS_OLD"), None) if os.getenv("INDEED_HOURS_OLD") else None,

            himalayas_keywords=parse_list(os.getenv("HIMALAYAS_KEYWORDS", "")),
            himalayas_max_results=parse_int(os.getenv("HIMALAYAS_MAX_RESULTS"), 100),
            himalayas_worldwide_only=parse_bool(os.getenv("HIMALAYAS_WORLDWIDE_ONLY"), False),
        )

    def get_indeed_search_configs(self) -> List[dict]:
        """
        Generate search configurations for Indeed.

        Creates one config per search term, optionally crossed with locations.

        Returns:
            List of search config dictionaries
        """
        if not self.indeed_search_terms:
            return []

        configs = []
        locations = self.indeed_locations if self.indeed_locations else [""]

        for term in self.indeed_search_terms:
            for location in locations:
                config = {
                    "search_term": term,
                    "location": location,
                    "results_wanted": self.results_per_source,
                    "country": self.indeed_country,
                }
                if self.indeed_hours_old:
                    config["hours_old"] = self.indeed_hours_old
                configs.append(config)

        return configs

    def get_himalayas_config(self) -> dict:
        """
        Generate search configuration for Himalayas.

        Returns:
            Search config dictionary
        """
        return {
            "keywords": self.himalayas_keywords,
            "max_results": self.himalayas_max_results,
            "worldwide_only": self.himalayas_worldwide_only,
        }


# Global config instance (lazily loaded)
_config: Optional[IngestConfig] = None


def get_ingest_config() -> IngestConfig:
    """Get the global ingestion configuration."""
    global _config
    if _config is None:
        _config = IngestConfig.from_env()
    return _config


def reload_config() -> IngestConfig:
    """Reload configuration from environment."""
    global _config
    _config = IngestConfig.from_env()
    return _config
