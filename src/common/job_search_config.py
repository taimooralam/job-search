"""
Job Search Configuration

Defines search presets for job titles, regions, and sources used by the
pull-on-demand job search system.

Usage:
    config = JobSearchConfig.from_env()
    presets = config.get_presets()
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class JobTitlePreset:
    """A predefined job title search configuration."""
    id: str
    label: str
    search_term: str


@dataclass
class RegionPreset:
    """A predefined region search configuration."""
    id: str
    label: str
    countries: List[Dict[str, Any]]  # [{"name": "UAE", "indeed_code": "AE"}, ...]
    is_remote: bool = False


@dataclass
class SourceConfig:
    """Configuration for a job source."""
    id: str
    label: str
    supports_location: bool
    supports_remote: bool


# Default job title presets for senior engineering roles
DEFAULT_JOB_TITLES: List[JobTitlePreset] = [
    JobTitlePreset(
        id="senior_swe",
        label="Senior Software Engineer",
        search_term="Senior Software Engineer"
    ),
    JobTitlePreset(
        id="lead_swe",
        label="Lead Software Engineer",
        search_term="Lead Software Engineer"
    ),
    JobTitlePreset(
        id="staff_swe",
        label="Staff Software Engineer",
        search_term="Staff Software Engineer"
    ),
    JobTitlePreset(
        id="principal_swe",
        label="Principal Software Engineer",
        search_term="Principal Software Engineer"
    ),
    JobTitlePreset(
        id="tech_lead",
        label="Tech Lead",
        search_term="Tech Lead"
    ),
    JobTitlePreset(
        id="software_architect",
        label="Software Architect",
        search_term="Software Architect"
    ),
    JobTitlePreset(
        id="vp_engineering",
        label="VP Engineering",
        search_term="VP Engineering"
    ),
    JobTitlePreset(
        id="head_engineering",
        label="Head of Engineering",
        search_term="Head of Engineering"
    ),
    JobTitlePreset(
        id="director_swe",
        label="Director Software Engineering",
        search_term="Director Software Engineering"
    ),
    JobTitlePreset(
        id="cto",
        label="CTO",
        search_term="CTO Chief Technology Officer"
    ),
]


# Default region presets
DEFAULT_REGIONS: List[RegionPreset] = [
    RegionPreset(
        id="gulf",
        label="Gulf Region",
        countries=[
            {"name": "UAE", "indeed_code": "AE"},
            {"name": "Saudi Arabia", "indeed_code": "SA"},
            {"name": "Qatar", "indeed_code": "QA"},
            {"name": "Kuwait", "indeed_code": "KW"},
        ],
        is_remote=False,
    ),
    RegionPreset(
        id="worldwide_remote",
        label="Worldwide Remote",
        countries=[{"name": "Worldwide", "indeed_code": None}],
        is_remote=True,
    ),
]


# Default source configurations
DEFAULT_SOURCES: List[SourceConfig] = [
    SourceConfig(
        id="indeed",
        label="Indeed",
        supports_location=True,
        supports_remote=True,
    ),
    SourceConfig(
        id="bayt",
        label="Bayt",
        supports_location=False,  # Bayt only uses search_term in JobSpy
        supports_remote=False,
    ),
    SourceConfig(
        id="himalayas",
        label="Himalayas",
        supports_location=False,  # API returns all remote jobs
        supports_remote=True,
    ),
]


@dataclass
class JobSearchConfig:
    """
    Configuration for the job search system.

    Loads settings from environment variables with sensible defaults.
    """

    # Cache settings
    cache_ttl_hours: int = 6
    max_results_per_source: int = 25

    # Presets
    job_titles: List[JobTitlePreset] = field(default_factory=lambda: DEFAULT_JOB_TITLES.copy())
    regions: List[RegionPreset] = field(default_factory=lambda: DEFAULT_REGIONS.copy())
    sources: List[SourceConfig] = field(default_factory=lambda: DEFAULT_SOURCES.copy())

    @classmethod
    def from_env(cls) -> "JobSearchConfig":
        """
        Create configuration from environment variables.

        Environment variables:
            JOB_SEARCH_CACHE_TTL_HOURS: Cache TTL in hours (default: 6)
            JOB_SEARCH_MAX_RESULTS_PER_SOURCE: Max results per source (default: 25)
        """
        cache_ttl = int(os.environ.get("JOB_SEARCH_CACHE_TTL_HOURS", "6"))
        max_results = int(os.environ.get("JOB_SEARCH_MAX_RESULTS_PER_SOURCE", "25"))

        return cls(
            cache_ttl_hours=cache_ttl,
            max_results_per_source=max_results,
        )

    def get_job_title_by_id(self, title_id: str) -> Optional[JobTitlePreset]:
        """Get a job title preset by its ID."""
        for title in self.job_titles:
            if title.id == title_id:
                return title
        return None

    def get_region_by_id(self, region_id: str) -> Optional[RegionPreset]:
        """Get a region preset by its ID."""
        for region in self.regions:
            if region.id == region_id:
                return region
        return None

    def get_source_by_id(self, source_id: str) -> Optional[SourceConfig]:
        """Get a source config by its ID."""
        for source in self.sources:
            if source.id == source_id:
                return source
        return None

    def get_presets(self) -> Dict[str, Any]:
        """
        Get all presets as a dictionary for API responses.

        Returns:
            Dictionary with job_titles, regions, and sources
        """
        return {
            "job_titles": [
                {
                    "id": t.id,
                    "label": t.label,
                    "search_term": t.search_term,
                }
                for t in self.job_titles
            ],
            "regions": [
                {
                    "id": r.id,
                    "label": r.label,
                    "countries": r.countries,
                    "is_remote": r.is_remote,
                }
                for r in self.regions
            ],
            "sources": [
                {
                    "id": s.id,
                    "label": s.label,
                    "supports_location": s.supports_location,
                    "supports_remote": s.supports_remote,
                }
                for s in self.sources
            ],
        }

    def build_search_configs(
        self,
        job_titles: List[str],
        regions: List[str],
        sources: List[str],
        remote_only: bool = False,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build search configurations for each source based on selected presets.

        Args:
            job_titles: List of job title IDs or raw search terms
            regions: List of region IDs ("gulf", "worldwide_remote")
            sources: List of source IDs ("indeed", "bayt", "himalayas")
            remote_only: Only search for remote positions
            max_results: Override max results per source

        Returns:
            List of search configurations, one per source
        """
        configs = []
        results_limit = max_results or self.max_results_per_source

        # Resolve job titles (support both preset IDs and raw terms)
        search_terms = []
        for title in job_titles:
            preset = self.get_job_title_by_id(title)
            if preset:
                search_terms.append(preset.search_term)
            else:
                # Use raw search term
                search_terms.append(title)

        # Resolve regions
        resolved_regions = []
        for region_id in regions:
            preset = self.get_region_by_id(region_id)
            if preset:
                resolved_regions.append(preset)

        # If no valid regions, default to worldwide_remote
        if not resolved_regions:
            resolved_regions = [self.get_region_by_id("worldwide_remote")]

        # Build configs for each source
        for source_id in sources:
            source = self.get_source_by_id(source_id)
            if not source:
                continue

            config = {
                "source": source_id,
                "search_terms": search_terms,
                "results_wanted": results_limit,
                "regions": [],
            }

            # Add region-specific parameters
            for region in resolved_regions:
                region_config = {
                    "id": region.id,
                    "label": region.label,
                    "is_remote": region.is_remote or remote_only,
                }

                # Add country codes for Indeed
                if source_id == "indeed" and source.supports_location:
                    region_config["countries"] = region.countries

                config["regions"].append(region_config)

            configs.append(config)

        return configs
