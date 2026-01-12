"""
Unit tests for LinkedIn Job Scraper (GAP-065)

Tests the LinkedIn scraper without making actual HTTP requests.
Uses mocked responses to test HTML parsing and error handling.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.services.linkedin_scraper import (
    extract_job_id,
    normalize_linkedin_url,
    scrape_linkedin_job,
    linkedin_job_to_mongodb_doc,
    _parse_job_html,
    _extract_title,
    _extract_company,
    _extract_location,
    _extract_description,
    _extract_job_criteria,
    _clean_description,
    _generate_dedupe_key,
    LinkedInJobData,
    LinkedInScraperError,
    JobNotFoundError,
    RateLimitError,
    ParseError,
)


class TestExtractJobId:
    """Tests for job ID extraction from various input formats."""

    def test_extract_raw_job_id(self):
        """Test extraction of raw numeric job ID."""
        assert extract_job_id("4081234567") == "4081234567"
        assert extract_job_id("  4081234567  ") == "4081234567"

    def test_extract_from_jobs_view_url(self):
        """Test extraction from /jobs/view/ URL format."""
        url = "https://www.linkedin.com/jobs/view/4081234567"
        assert extract_job_id(url) == "4081234567"

        url_with_params = "https://www.linkedin.com/jobs/view/4081234567?trk=search"
        assert extract_job_id(url_with_params) == "4081234567"

    def test_extract_from_jobs_url(self):
        """Test extraction from /jobs/ URL format (older)."""
        url = "https://linkedin.com/jobs/4081234567"
        assert extract_job_id(url) == "4081234567"

    def test_extract_from_current_job_id_param(self):
        """Test extraction from currentJobId query parameter."""
        url = "https://linkedin.com/jobs/search/?currentJobId=4081234567"
        assert extract_job_id(url) == "4081234567"

    def test_invalid_input_raises_error(self):
        """Test that invalid inputs raise ValueError."""
        with pytest.raises(ValueError, match="Could not extract job ID"):
            extract_job_id("not-a-job-id")

        with pytest.raises(ValueError, match="Could not extract job ID"):
            extract_job_id("https://linkedin.com/in/username")


class TestGenerateDedupeKey:
    """Tests for dedupe key generation."""

    def test_basic_dedupe_key_with_job_id(self):
        """Test dedupe key with job_id uses source|job_id format."""
        key = _generate_dedupe_key("TestCorp", "Senior Software Engineer", "San Francisco, CA", "linkedin_import", job_id="4081234567")
        assert key == "linkedin_import|4081234567"

    def test_basic_dedupe_key_without_job_id(self):
        """Test fallback dedupe key without job_id uses normalized text format."""
        key = _generate_dedupe_key("TestCorp", "Senior Software Engineer", "San Francisco, CA", "linkedin_import")
        # New format: source|company|title|location (all normalized - no spaces/special chars)
        assert key == "linkedin_import|testcorp|seniorsoftwareengineer|sanfranciscoca"

    def test_dedupe_key_with_special_chars(self):
        """Test dedupe key normalizes special chars (removes all non-alphanumeric)."""
        key = _generate_dedupe_key("Test Corp, Inc.", "Senior (Cloud) Engineer!", "Remote", "linkedin_import")
        # All special chars removed, spaces removed
        assert key == "linkedin_import|testcorpinc|seniorcloudengineer|remote"

    def test_dedupe_key_with_empty_values(self):
        """Test dedupe key handles empty/None values."""
        key = _generate_dedupe_key("", "Engineer", None, "linkedin_import")
        assert key == "linkedin_import||engineer|"

    def test_dedupe_key_default_source(self):
        """Test dedupe key uses default source if not specified."""
        key = _generate_dedupe_key("Company", "Title", "Location")
        assert key == "linkedin_import|company|title|location"


class TestLinkedInJobToMongoDoc:
    """Tests for converting LinkedIn data to MongoDB document."""

    def test_basic_conversion(self):
        """Test basic conversion to MongoDB format."""
        job_data = LinkedInJobData(
            job_id="4081234567",
            title="Senior Software Engineer",
            company="TestCorp",
            location="San Francisco, CA",
            description="A great job opportunity...",
            job_url="https://www.linkedin.com/jobs/view/4081234567",
            seniority_level="Mid-Senior level",
            employment_type="Full-time",
            scraped_at=datetime(2025, 12, 1, 10, 0, 0),
        )

        doc = linkedin_job_to_mongodb_doc(job_data)

        # jobId is the LinkedIn job ID directly
        assert doc["jobId"] == "4081234567"
        assert doc["title"] == "Senior Software Engineer"
        assert doc["company"] == "TestCorp"
        assert doc["location"] == "San Francisco, CA"
        assert doc["description"] == "A great job opportunity..."
        assert doc["jobUrl"] == "https://www.linkedin.com/jobs/view/4081234567"

        # dedupeKey with job_id uses source|job_id format
        assert doc["dedupeKey"] == "linkedin_import|4081234567"

        assert doc["status"] == "under processing"  # Ready for batch processing
        assert "batch_added_at" in doc  # For batch table sorting
        assert doc["score"] is None
        assert doc["source"] == "linkedin_import"

        # Check metadata (now uses linkedin_job_id instead of job_id)
        assert doc["linkedin_metadata"]["linkedin_job_id"] == "4081234567"
        assert doc["linkedin_metadata"]["seniority_level"] == "Mid-Senior level"
        assert doc["linkedin_metadata"]["employment_type"] == "Full-time"

    def test_conversion_with_minimal_data(self):
        """Test conversion with only required fields."""
        job_data = LinkedInJobData(
            job_id="123",
            title="Engineer",
            company="Co",
            location="Remote",
            description="Job desc",
            job_url="https://linkedin.com/jobs/view/123",
        )

        doc = linkedin_job_to_mongodb_doc(job_data)

        assert doc["jobId"] == "123"
        assert doc["title"] == "Engineer"
        # dedupeKey with job_id uses source|job_id format
        assert doc["dedupeKey"] == "linkedin_import|123"
        assert doc["linkedin_metadata"]["seniority_level"] is None


# Sample HTML for testing HTML parsing
SAMPLE_JOB_HTML = """
<!DOCTYPE html>
<html>
<head><title>Job Posting</title></head>
<body>
<section class="top-card-layout">
    <h1 class="top-card-layout__title">Senior Software Engineer</h1>
    <a class="topcard__org-name-link" href="/company/testcorp">TestCorp Inc</a>
    <span class="topcard__flavor--bullet">San Francisco, CA (Hybrid)</span>
</section>

<section class="description">
    <div class="show-more-less-html__markup">
        <p>We are looking for a talented engineer to join our team.</p>
        <strong>Responsibilities:</strong>
        <ul>
            <li>Design and implement scalable systems</li>
            <li>Collaborate with cross-functional teams</li>
            <li>Write clean, maintainable code</li>
        </ul>
        <strong>Requirements:</strong>
        <ul>
            <li>5+ years of experience</li>
            <li>Python and JavaScript proficiency</li>
        </ul>
    </div>
</section>

<ul class="job-criteria__list">
    <li class="job-criteria__item">
        <h3 class="job-criteria__subheader">Seniority level</h3>
        <span class="job-criteria__text">Mid-Senior level</span>
    </li>
    <li class="job-criteria__item">
        <h3 class="job-criteria__subheader">Employment type</h3>
        <span class="job-criteria__text">Full-time</span>
    </li>
    <li class="job-criteria__item">
        <h3 class="job-criteria__subheader">Job function</h3>
        <span class="job-criteria__text">Engineering</span>
    </li>
    <li class="job-criteria__item">
        <h3 class="job-criteria__subheader">Industries</h3>
        <span class="job-criteria__text">Technology, Software Development</span>
    </li>
</ul>
</body>
</html>
"""


class TestParseJobHtml:
    """Tests for HTML parsing functions."""

    def test_parse_complete_job_html(self):
        """Test parsing a complete job HTML page."""
        job_data = _parse_job_html("4081234567", SAMPLE_JOB_HTML)

        assert job_data.job_id == "4081234567"
        assert job_data.title == "Senior Software Engineer"
        assert job_data.company == "TestCorp Inc"
        assert job_data.location == "San Francisco, CA (Hybrid)"
        assert "talented engineer" in job_data.description
        assert job_data.seniority_level == "Mid-Senior level"
        assert job_data.employment_type == "Full-time"
        assert job_data.job_function == "Engineering"
        assert "Technology" in job_data.industries

    def test_parse_missing_title_raises_error(self):
        """Test that missing title raises ParseError."""
        html_no_title = "<html><body><div>No title here</div></body></html>"

        with pytest.raises(ParseError, match="Could not extract job title"):
            _parse_job_html("123", html_no_title)

    def test_parse_missing_company_raises_error(self):
        """Test that missing company raises ParseError."""
        html_no_company = """
        <html><body>
            <h1 class="top-card-layout__title">Job Title</h1>
        </body></html>
        """

        with pytest.raises(ParseError, match="Could not extract company"):
            _parse_job_html("123", html_no_company)


class TestCleanDescription:
    """Tests for description cleaning."""

    def test_clean_simple_text(self):
        """Test cleaning simple text."""
        from bs4 import BeautifulSoup

        html = "<div><p>Hello world</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        result = _clean_description(soup.find("div"))

        assert "Hello world" in result

    def test_clean_with_list_items(self):
        """Test cleaning text with list items."""
        from bs4 import BeautifulSoup

        html = "<div><ul><li>Item 1</li><li>Item 2</li></ul></div>"
        soup = BeautifulSoup(html, "html.parser")
        result = _clean_description(soup.find("div"))

        assert "Item 1" in result or "• Item 1" in result


class TestScrapeLinkedInJob:
    """Tests for the main scrape function with mocked HTTP."""

    @patch("src.services.linkedin_scraper.requests.get")
    def test_successful_scrape(self, mock_get):
        """Test successful job scraping."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_JOB_HTML
        mock_get.return_value = mock_response

        result = scrape_linkedin_job("4081234567")

        assert result.job_id == "4081234567"
        assert result.title == "Senior Software Engineer"
        assert result.company == "TestCorp Inc"
        mock_get.assert_called_once()

    @patch("src.services.linkedin_scraper.requests.get")
    def test_job_not_found(self, mock_get):
        """Test handling of 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(JobNotFoundError, match="not found"):
            scrape_linkedin_job("999999999")

    @patch("src.services.linkedin_scraper.requests.get")
    def test_rate_limit_error(self, mock_get):
        """Test handling of 429 rate limit response."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_get.return_value = mock_response

        with pytest.raises(RateLimitError, match="rate limit"):
            scrape_linkedin_job("4081234567")

    @patch("src.services.linkedin_scraper.requests.get")
    def test_network_timeout(self, mock_get):
        """Test handling of network timeout."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()

        with pytest.raises(LinkedInScraperError, match="timed out"):
            scrape_linkedin_job("4081234567")

    @patch("src.services.linkedin_scraper.requests.get")
    def test_accepts_full_url(self, mock_get):
        """Test that full URLs are accepted and parsed correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_JOB_HTML
        mock_get.return_value = mock_response

        # Test with full URL
        result = scrape_linkedin_job("https://www.linkedin.com/jobs/view/4081234567?trk=abc")

        assert result.job_id == "4081234567"


class TestExtractFunctions:
    """Tests for individual extraction functions."""

    def test_extract_title_from_h1(self):
        """Test title extraction from h1."""
        from bs4 import BeautifulSoup

        html = '<h1 class="top-card-layout__title">Software Engineer</h1>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_title(soup) == "Software Engineer"

    def test_extract_company_from_link(self):
        """Test company extraction from org link."""
        from bs4 import BeautifulSoup

        html = '<a class="topcard__org-name-link">TestCorp</a>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_company(soup) == "TestCorp"

    def test_extract_location_from_bullet(self):
        """Test location extraction from bullet span."""
        from bs4 import BeautifulSoup

        html = '<span class="topcard__flavor--bullet">Remote (US)</span>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_location(soup) == "Remote (US)"


class TestNormalizeLinkedInUrl:
    """Tests for LinkedIn URL normalization."""

    def test_normalize_standard_url(self):
        """Test normalization of standard LinkedIn job URL."""
        url = "https://www.linkedin.com/jobs/view/4081234567"
        assert normalize_linkedin_url(url) == "https://linkedin.com/jobs/view/4081234567"

    def test_normalize_country_subdomain(self):
        """Test normalization of URL with country subdomain."""
        url = "https://de.linkedin.com/jobs/view/4081234567"
        assert normalize_linkedin_url(url) == "https://linkedin.com/jobs/view/4081234567"

        url = "https://uk.linkedin.com/jobs/view/4081234567"
        assert normalize_linkedin_url(url) == "https://linkedin.com/jobs/view/4081234567"

    def test_normalize_slugified_title(self):
        """Test normalization of URL with slugified job title."""
        url = "https://de.linkedin.com/jobs/view/senior-engineer-at-company-4081234567"
        assert normalize_linkedin_url(url) == "https://linkedin.com/jobs/view/4081234567"

    def test_normalize_with_query_params(self):
        """Test normalization of URL with query parameters."""
        url = "https://linkedin.com/jobs/view/4081234567?trk=public_jobs_topcard"
        assert normalize_linkedin_url(url) == "https://linkedin.com/jobs/view/4081234567"

    def test_normalize_with_current_job_id_param(self):
        """Test normalization of URL with currentJobId parameter."""
        url = "https://linkedin.com/jobs/search/?currentJobId=4081234567"
        assert normalize_linkedin_url(url) == "https://linkedin.com/jobs/view/4081234567"

    def test_normalize_already_canonical(self):
        """Test that already canonical URL is returned unchanged."""
        url = "https://linkedin.com/jobs/view/4081234567"
        assert normalize_linkedin_url(url) == url

    def test_normalize_non_linkedin_url_returns_none(self):
        """Test that non-LinkedIn URLs return None."""
        assert normalize_linkedin_url("https://indeed.com/jobs/123") is None
        assert normalize_linkedin_url("https://google.com") is None

    def test_normalize_empty_or_none_returns_none(self):
        """Test that empty/None input returns None."""
        assert normalize_linkedin_url("") is None
        assert normalize_linkedin_url(None) is None

    def test_normalize_invalid_linkedin_url_returns_none(self):
        """Test that LinkedIn URLs without job ID return None."""
        assert normalize_linkedin_url("https://linkedin.com/in/username") is None
        assert normalize_linkedin_url("https://linkedin.com/company/acme") is None
