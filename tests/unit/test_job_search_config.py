"""
Unit tests for JobSearchConfig.

Tests the configuration and preset system for pull-on-demand job search.
"""

import pytest
import os
from unittest.mock import patch

from src.common.job_search_config import (
    JobSearchConfig,
    JobTitlePreset,
    RegionPreset,
    SourceConfig,
    DEFAULT_JOB_TITLES,
    DEFAULT_REGIONS,
    DEFAULT_SOURCES,
)


class TestJobTitlePreset:
    """Tests for JobTitlePreset dataclass."""

    def test_create_preset(self):
        """Test creating a job title preset."""
        preset = JobTitlePreset(
            id="senior_swe",
            label="Senior Software Engineer",
            search_term="Senior Software Engineer"
        )

        assert preset.id == "senior_swe"
        assert preset.label == "Senior Software Engineer"
        assert preset.search_term == "Senior Software Engineer"


class TestRegionPreset:
    """Tests for RegionPreset dataclass."""

    def test_create_gulf_region(self):
        """Test creating a Gulf region preset."""
        preset = RegionPreset(
            id="gulf",
            label="Gulf Region",
            countries=[
                {"name": "UAE", "indeed_code": "AE"},
                {"name": "Saudi Arabia", "indeed_code": "SA"},
            ],
            is_remote=False,
        )

        assert preset.id == "gulf"
        assert len(preset.countries) == 2
        assert preset.is_remote is False

    def test_create_remote_region(self):
        """Test creating a remote region preset."""
        preset = RegionPreset(
            id="worldwide_remote",
            label="Worldwide Remote",
            countries=[{"name": "Worldwide", "indeed_code": None}],
            is_remote=True,
        )

        assert preset.id == "worldwide_remote"
        assert preset.is_remote is True


class TestSourceConfig:
    """Tests for SourceConfig dataclass."""

    def test_create_source(self):
        """Test creating a source configuration."""
        source = SourceConfig(
            id="indeed",
            label="Indeed",
            supports_location=True,
            supports_remote=True,
        )

        assert source.id == "indeed"
        assert source.supports_location is True
        assert source.supports_remote is True


class TestDefaultPresets:
    """Tests for default preset values."""

    def test_default_job_titles_count(self):
        """Test that we have 10 default job titles."""
        assert len(DEFAULT_JOB_TITLES) == 10

    def test_default_job_titles_ids(self):
        """Test that default job titles have expected IDs."""
        ids = [t.id for t in DEFAULT_JOB_TITLES]
        expected = [
            "senior_swe", "lead_swe", "staff_swe", "principal_swe",
            "tech_lead", "software_architect", "vp_engineering",
            "head_engineering", "director_swe", "cto"
        ]
        assert ids == expected

    def test_default_regions_count(self):
        """Test that we have 2 default regions."""
        assert len(DEFAULT_REGIONS) == 2

    def test_default_regions_ids(self):
        """Test that default regions have expected IDs."""
        ids = [r.id for r in DEFAULT_REGIONS]
        assert ids == ["gulf", "worldwide_remote"]

    def test_default_sources_count(self):
        """Test that we have 3 default sources."""
        assert len(DEFAULT_SOURCES) == 3

    def test_default_sources_ids(self):
        """Test that default sources have expected IDs."""
        ids = [s.id for s in DEFAULT_SOURCES]
        assert ids == ["indeed", "bayt", "himalayas"]


class TestJobSearchConfig:
    """Tests for JobSearchConfig class."""

    def test_default_config(self):
        """Test creating config with defaults."""
        config = JobSearchConfig()

        assert config.cache_ttl_hours == 6
        assert config.max_results_per_source == 25
        assert len(config.job_titles) == 10
        assert len(config.regions) == 2
        assert len(config.sources) == 3

    @patch.dict(os.environ, {
        "JOB_SEARCH_CACHE_TTL_HOURS": "12",
        "JOB_SEARCH_MAX_RESULTS_PER_SOURCE": "50",
    })
    def test_from_env(self):
        """Test loading config from environment variables."""
        config = JobSearchConfig.from_env()

        assert config.cache_ttl_hours == 12
        assert config.max_results_per_source == 50

    def test_get_job_title_by_id_found(self):
        """Test getting a job title preset by ID."""
        config = JobSearchConfig()
        title = config.get_job_title_by_id("senior_swe")

        assert title is not None
        assert title.id == "senior_swe"
        assert title.label == "Senior Software Engineer"

    def test_get_job_title_by_id_not_found(self):
        """Test getting a non-existent job title preset."""
        config = JobSearchConfig()
        title = config.get_job_title_by_id("nonexistent")

        assert title is None

    def test_get_region_by_id_found(self):
        """Test getting a region preset by ID."""
        config = JobSearchConfig()
        region = config.get_region_by_id("gulf")

        assert region is not None
        assert region.id == "gulf"
        assert len(region.countries) == 4  # UAE, SA, QA, KW

    def test_get_region_by_id_not_found(self):
        """Test getting a non-existent region preset."""
        config = JobSearchConfig()
        region = config.get_region_by_id("nonexistent")

        assert region is None

    def test_get_source_by_id_found(self):
        """Test getting a source config by ID."""
        config = JobSearchConfig()
        source = config.get_source_by_id("indeed")

        assert source is not None
        assert source.id == "indeed"
        assert source.supports_location is True

    def test_get_source_by_id_not_found(self):
        """Test getting a non-existent source config."""
        config = JobSearchConfig()
        source = config.get_source_by_id("nonexistent")

        assert source is None

    def test_get_presets(self):
        """Test getting all presets as dictionary."""
        config = JobSearchConfig()
        presets = config.get_presets()

        assert "job_titles" in presets
        assert "regions" in presets
        assert "sources" in presets

        assert len(presets["job_titles"]) == 10
        assert len(presets["regions"]) == 2
        assert len(presets["sources"]) == 3

        # Check structure
        assert all("id" in t and "label" in t and "search_term" in t
                   for t in presets["job_titles"])
        assert all("id" in r and "label" in r and "countries" in r
                   for r in presets["regions"])
        assert all("id" in s and "label" in s and "supports_location" in s
                   for s in presets["sources"])

    def test_build_search_configs_with_preset_ids(self):
        """Test building search configs with preset IDs."""
        config = JobSearchConfig()
        configs = config.build_search_configs(
            job_titles=["senior_swe", "staff_swe"],
            regions=["gulf"],
            sources=["indeed"],
        )

        assert len(configs) == 1  # One config per source
        assert configs[0]["source"] == "indeed"
        assert len(configs[0]["search_terms"]) == 2
        assert "Senior Software Engineer" in configs[0]["search_terms"]
        assert "Staff Software Engineer" in configs[0]["search_terms"]

    def test_build_search_configs_with_raw_terms(self):
        """Test building search configs with raw search terms."""
        config = JobSearchConfig()
        configs = config.build_search_configs(
            job_titles=["Custom Job Title"],
            regions=["worldwide_remote"],
            sources=["himalayas"],
        )

        assert len(configs) == 1
        assert configs[0]["search_terms"] == ["Custom Job Title"]

    def test_build_search_configs_multiple_sources(self):
        """Test building search configs for multiple sources."""
        config = JobSearchConfig()
        configs = config.build_search_configs(
            job_titles=["senior_swe"],
            regions=["gulf"],
            sources=["indeed", "bayt", "himalayas"],
        )

        assert len(configs) == 3
        sources = [c["source"] for c in configs]
        assert "indeed" in sources
        assert "bayt" in sources
        assert "himalayas" in sources

    def test_build_search_configs_custom_max_results(self):
        """Test building search configs with custom max results."""
        config = JobSearchConfig()
        configs = config.build_search_configs(
            job_titles=["senior_swe"],
            regions=["gulf"],
            sources=["indeed"],
            max_results=50,
        )

        assert configs[0]["results_wanted"] == 50

    def test_build_search_configs_remote_only(self):
        """Test building search configs with remote_only flag."""
        config = JobSearchConfig()
        configs = config.build_search_configs(
            job_titles=["senior_swe"],
            regions=["gulf"],
            sources=["indeed"],
            remote_only=True,
        )

        # All regions should have is_remote=True
        for region in configs[0]["regions"]:
            assert region["is_remote"] is True
