"""
Unit tests for BaytSource job source.

Tests the Bayt.com integration via JobSpy for Gulf region job searching.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
import pandas as pd

from src.services.job_sources import JobData
from src.services.job_sources.bayt_source import BaytSource


class TestBaytSource:
    """Tests for the BaytSource class."""

    def test_get_source_name(self):
        """Test that source name is correct."""
        source = BaytSource()
        assert source.get_source_name() == "bayt"

    def test_generate_dedupe_key(self):
        """Test deduplication key generation - new format: source|normalized_fields."""
        source = BaytSource()
        job = JobData(
            title="Senior Engineer",
            company="Gulf Tech",
            location="Dubai, UAE",
            description="...",
            url="...",
        )

        key = source.generate_dedupe_key(job)
        # New format: source|company|title|location (all normalized - no special chars)
        assert key == "bayt|gulftech|seniorengineer|dubaiuae"

    def test_generate_dedupe_key_normalizes(self):
        """Test that dedupe key normalizes to alphanumeric only."""
        source = BaytSource()
        job = JobData(
            title="  SENIOR Engineer  ",
            company="  GULF Tech CO  ",
            location="DUBAI, UAE  ",
            description="...",
            url="...",
        )

        key = source.generate_dedupe_key(job)
        # All non-alphanumeric chars removed
        assert key == "bayt|gulftechco|seniorengineer|dubaiuae"

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_success(self, mock_scrape):
        """Test successful job fetching from Bayt."""
        # Mock JobSpy response as DataFrame
        mock_df = pd.DataFrame([
            {
                "title": "Senior Software Engineer",
                "company": "Careem",
                "location": "Dubai",
                "description": "Build the future of transportation",
                "job_url": "https://bayt.com/job/1",
                "min_amount": 25000,
                "max_amount": 35000,
                "currency": "AED",
                "interval": "monthly",
                "is_remote": False,
                "date_posted": "2024-12-15",
                "job_type": "full-time",
            },
            {
                "title": "Tech Lead",
                "company": "Noon",
                "location": "Riyadh",
                "description": "Lead engineering teams",
                "job_url": "https://bayt.com/job/2",
                "min_amount": None,
                "max_amount": None,
                "currency": None,
                "is_remote": True,
                "date_posted": None,
                "job_type": None,
            },
        ])
        mock_scrape.return_value = mock_df

        source = BaytSource()
        jobs = source.fetch_jobs({"search_term": "software engineer", "results_wanted": 25})

        assert len(jobs) == 2
        assert jobs[0].title == "Senior Software Engineer"
        assert jobs[0].company == "Careem"
        assert jobs[0].location == "Dubai"
        assert "AED" in jobs[0].salary
        assert jobs[1].title == "Tech Lead"
        assert jobs[1].location == "Riyadh (Remote)"

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_empty_results(self, mock_scrape):
        """Test handling of empty results from Bayt."""
        mock_scrape.return_value = pd.DataFrame()

        source = BaytSource()
        jobs = source.fetch_jobs({"search_term": "nonexistent job"})

        assert jobs == []

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_error_handling(self, mock_scrape):
        """Test error handling during job fetch."""
        mock_scrape.side_effect = Exception("Network error")

        source = BaytSource()
        jobs = source.fetch_jobs({"search_term": "engineer"})

        assert jobs == []

    def test_fetch_jobs_no_search_term(self):
        """Test that fetch fails gracefully without search term."""
        source = BaytSource()
        source._jobspy_available = True  # Pretend JobSpy is available

        jobs = source.fetch_jobs({})

        assert jobs == []

    def test_fetch_jobs_jobspy_not_available(self):
        """Test that fetch fails gracefully when JobSpy is not installed."""
        source = BaytSource()
        source._jobspy_available = False

        jobs = source.fetch_jobs({"search_term": "engineer"})

        assert jobs == []

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_default_location(self, mock_scrape):
        """Test that jobs without location get Gulf Region default."""
        mock_df = pd.DataFrame([
            {
                "title": "Developer",
                "company": "StartupGulf",
                "location": "",  # Empty location
                "description": "Build things",
                "job_url": "https://bayt.com/job/3",
                "min_amount": None,
                "max_amount": None,
                "is_remote": False,
                "date_posted": None,
            },
        ])
        mock_scrape.return_value = mock_df

        source = BaytSource()
        jobs = source.fetch_jobs({"search_term": "developer"})

        assert len(jobs) == 1
        assert jobs[0].location == "Gulf Region"

    @patch("jobspy.scrape_jobs")
    def test_fetch_jobs_skips_incomplete(self, mock_scrape):
        """Test that jobs without title or company are skipped."""
        mock_df = pd.DataFrame([
            {
                "title": "",  # Missing title
                "company": "SomeCompany",
                "location": "Dubai",
                "description": "...",
                "job_url": "...",
            },
            {
                "title": "Engineer",
                "company": "",  # Missing company
                "location": "Dubai",
                "description": "...",
                "job_url": "...",
            },
            {
                "title": "Valid Job",
                "company": "Valid Company",
                "location": "Dubai",
                "description": "...",
                "job_url": "...",
            },
        ])
        mock_scrape.return_value = mock_df

        source = BaytSource()
        jobs = source.fetch_jobs({"search_term": "engineer"})

        assert len(jobs) == 1
        assert jobs[0].title == "Valid Job"
