"""
Unit tests for Job Sources module.

Tests the IndeedSource, HimalayasSource, and common utilities
for the automated job ingestion system.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import pandas as pd

from src.services.job_sources import JobData, IndeedSource, HimalayasSource


class TestJobData:
    """Tests for the JobData dataclass."""

    def test_job_data_creation(self):
        """Test creating a JobData instance with all fields."""
        job = JobData(
            title="Software Engineer",
            company="Acme Corp",
            location="San Francisco, CA",
            description="Build amazing things",
            url="https://example.com/job/123",
            salary="$150,000 - $200,000",
            job_type="full-time",
            posted_date=datetime(2024, 1, 15),
            source_id="job-123",
        )

        assert job.title == "Software Engineer"
        assert job.company == "Acme Corp"
        assert job.location == "San Francisco, CA"
        assert job.salary == "$150,000 - $200,000"

    def test_job_data_minimal(self):
        """Test creating a JobData with only required fields."""
        job = JobData(
            title="Engineer",
            company="Startup Inc",
            location="Remote",
            description="Work from anywhere",
            url="https://startup.com/careers",
        )

        assert job.title == "Engineer"
        assert job.salary is None
        assert job.job_type is None


class TestIndeedSource:
    """Tests for the IndeedSource class."""

    def test_get_source_name(self):
        """Test that source name is correct."""
        source = IndeedSource()
        assert source.get_source_name() == "indeed_auto"

    def test_generate_dedupe_key(self):
        """Test deduplication key generation."""
        source = IndeedSource()
        job = JobData(
            title="Senior Engineer",
            company="Big Tech Co",
            location="New York, NY",
            description="...",
            url="...",
        )

        key = source.generate_dedupe_key(job)
        assert key == "big tech co|senior engineer|new york, ny|indeed_auto"

    def test_generate_dedupe_key_normalizes(self):
        """Test that dedupe key normalizes whitespace and case."""
        source = IndeedSource()
        job = JobData(
            title="  SENIOR Engineer  ",
            company="  BIG Tech CO  ",
            location="NEW YORK, NY  ",
            description="...",
            url="...",
        )

        key = source.generate_dedupe_key(job)
        assert key == "big tech co|senior engineer|new york, ny|indeed_auto"

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_success(self, mock_scrape):
        """Test successful job fetching from Indeed."""
        # Mock JobSpy response as DataFrame
        mock_df = pd.DataFrame([
            {
                "title": "Software Engineer",
                "company": "Tech Corp",
                "location": "San Francisco",
                "description": "Build stuff",
                "job_url": "https://indeed.com/job/1",
                "min_amount": 120000,
                "max_amount": 180000,
                "currency": "USD",
                "interval": "yearly",
                "is_remote": False,
                "job_type": "fulltime",
                "date_posted": "2024-01-15",
            }
        ])
        mock_scrape.return_value = mock_df

        source = IndeedSource()
        source._jobspy_available = True  # Skip import check

        jobs = source.fetch_jobs({
            "search_term": "software engineer",
            "location": "San Francisco",
            "results_wanted": 10,
        })

        assert len(jobs) == 1
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].company == "Tech Corp"
        assert "120,000" in jobs[0].salary

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_empty(self, mock_scrape):
        """Test handling empty results from Indeed."""
        mock_scrape.return_value = pd.DataFrame()

        source = IndeedSource()
        source._jobspy_available = True

        jobs = source.fetch_jobs({"search_term": "nonexistent job"})

        assert len(jobs) == 0

    def test_fetch_jobs_no_search_term(self):
        """Test handling missing search term."""
        source = IndeedSource()
        source._jobspy_available = True

        jobs = source.fetch_jobs({})

        assert len(jobs) == 0


class TestHimalayasSource:
    """Tests for the HimalayasSource class."""

    def test_get_source_name(self):
        """Test that source name is correct."""
        source = HimalayasSource()
        assert source.get_source_name() == "himalayas_auto"

    def test_generate_dedupe_key(self):
        """Test deduplication key generation."""
        source = HimalayasSource()
        job = JobData(
            title="Remote Developer",
            company="Distributed Inc",
            location="Worldwide",
            description="...",
            url="...",
        )

        key = source.generate_dedupe_key(job)
        assert key == "distributed inc|remote developer|worldwide|himalayas_auto"

    @patch("src.services.job_sources.himalayas_source.requests.get")
    def test_fetch_jobs_success(self, mock_get):
        """Test successful job fetching from Himalayas API."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "title": "Backend Engineer",
                "companyName": "Remote First Co",
                "description": "Build APIs",
                "location": "Worldwide",
                "applicationLink": "https://apply.himalayas.app/123",
                "salaryCurrencyMinValue": 100000,
                "salaryCurrencyMaxValue": 150000,
                "salaryCurrency": "USD",
                "isRemote": True,
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        source = HimalayasSource()
        jobs = source.fetch_jobs({"max_results": 10})

        assert len(jobs) == 1
        assert jobs[0].title == "Backend Engineer"
        assert jobs[0].company == "Remote First Co"

    @patch("src.services.job_sources.himalayas_source.requests.get")
    def test_fetch_jobs_with_keyword_filter(self, mock_get):
        """Test keyword filtering."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "title": "Python Developer",
                "companyName": "PyShop",
                "description": "Write Python code",
                "location": "Remote",
            },
            {
                "title": "Java Developer",
                "companyName": "JavaCorp",
                "description": "Write Java code",
                "location": "Remote",
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        source = HimalayasSource()
        jobs = source.fetch_jobs({"keywords": ["python"]})

        assert len(jobs) == 1
        assert jobs[0].title == "Python Developer"

    @patch("src.services.job_sources.himalayas_source.requests.get")
    def test_fetch_jobs_worldwide_filter(self, mock_get):
        """Test worldwide-only filtering."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "title": "Global Engineer",
                "companyName": "Worldwide Corp",
                "description": "Work anywhere",
                "location": "Worldwide",
                "isWorldwide": True,
            },
            {
                "title": "US Engineer",
                "companyName": "US Only Inc",
                "description": "US only",
                "location": "United States",
                "isWorldwide": False,
            },
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        source = HimalayasSource()
        jobs = source.fetch_jobs({"worldwide_only": True})

        assert len(jobs) == 1
        assert jobs[0].company == "Worldwide Corp"

    @patch("src.services.job_sources.himalayas_source.requests.get")
    def test_fetch_jobs_api_error(self, mock_get):
        """Test handling API errors gracefully."""
        mock_get.side_effect = Exception("API error")

        source = HimalayasSource()
        jobs = source.fetch_jobs({})

        assert len(jobs) == 0

    @patch("src.services.job_sources.himalayas_source.requests.get")
    def test_fetch_jobs_timeout(self, mock_get):
        """Test handling request timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        source = HimalayasSource()
        jobs = source.fetch_jobs({})

        assert len(jobs) == 0


class TestIngestConfig:
    """Tests for ingestion configuration."""

    def test_config_from_env_defaults(self):
        """Test loading config with default values."""
        from src.common.ingest_config import IngestConfig

        config = IngestConfig()

        assert config.enabled is True
        assert config.score_threshold == 70
        assert config.results_per_source == 50

    def test_config_from_env_with_values(self):
        """Test loading config from environment variables."""
        import os
        from src.common.ingest_config import IngestConfig

        with patch.dict(os.environ, {
            "AUTO_INGEST_ENABLED": "false",
            "AUTO_INGEST_SCORE_THRESHOLD": "80",
            "INDEED_SEARCH_TERMS": "engineer,developer",
            "HIMALAYAS_KEYWORDS": "python,remote",
        }):
            config = IngestConfig.from_env()

        assert config.enabled is False
        assert config.score_threshold == 80
        assert "engineer" in config.indeed_search_terms
        assert "python" in config.himalayas_keywords

    def test_get_indeed_search_configs(self):
        """Test generating Indeed search configurations."""
        from src.common.ingest_config import IngestConfig

        config = IngestConfig(
            indeed_search_terms=["engineer", "manager"],
            indeed_locations=["SF", "NYC"],
            results_per_source=25,
        )

        configs = config.get_indeed_search_configs()

        # 2 terms x 2 locations = 4 configs
        assert len(configs) == 4
        assert configs[0]["search_term"] == "engineer"
        assert configs[0]["location"] == "SF"
        assert configs[0]["results_wanted"] == 25

    def test_get_himalayas_config(self):
        """Test generating Himalayas configuration."""
        from src.common.ingest_config import IngestConfig

        config = IngestConfig(
            himalayas_keywords=["python", "rust"],
            himalayas_max_results=50,
            himalayas_worldwide_only=True,
        )

        hconfig = config.get_himalayas_config()

        assert hconfig["keywords"] == ["python", "rust"]
        assert hconfig["max_results"] == 50
        assert hconfig["worldwide_only"] is True
