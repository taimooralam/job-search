"""
Unit tests for Indeed Job Scraper

Tests the Indeed scraper without making actual HTTP requests.
Uses mocked responses to test HTML parsing, error handling, and FireCrawl fallback.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.services.indeed_scraper import (
    extract_job_key,
    scrape_indeed_job,
    indeed_job_to_mongodb_doc,
    _parse_indeed_html,
    _extract_title,
    _extract_company,
    _extract_location,
    _extract_description,
    _extract_salary,
    _extract_job_type,
    _clean_description,
    _generate_dedupe_key,
    IndeedJobData,
    IndeedScraperError,
    JobNotFoundError,
    BlockedError,
    ParseError,
)


class TestExtractJobKey:
    """Tests for job key extraction from various input formats."""

    def test_extract_raw_job_key(self):
        """Test extraction of raw 16-char hex job key."""
        assert extract_job_key("abc123def4567890") == "abc123def4567890"
        assert extract_job_key("  ABC123DEF4567890  ") == "abc123def4567890"
        # Uppercase should be lowercased
        assert extract_job_key("ABCDEF1234567890") == "abcdef1234567890"

    def test_extract_from_viewjob_url(self):
        """Test extraction from viewjob URL format."""
        url = "https://www.indeed.com/viewjob?jk=abc123def4567890"
        assert extract_job_key(url) == "abc123def4567890"

        url_https = "https://indeed.com/viewjob?jk=abc123def4567890"
        assert extract_job_key(url_https) == "abc123def4567890"

    def test_extract_from_clk_url(self):
        """Test extraction from rc/clk URL format."""
        url = "https://indeed.com/rc/clk?jk=abc123def4567890"
        assert extract_job_key(url) == "abc123def4567890"

    def test_extract_from_search_vjk(self):
        """Test extraction from search URL with vjk parameter."""
        url = "https://www.indeed.com/jobs?q=engineer&l=remote&vjk=abc123def4567890"
        assert extract_job_key(url) == "abc123def4567890"

    def test_extract_from_url_with_other_params(self):
        """Test extraction from URL with additional query parameters."""
        url = "https://www.indeed.com/viewjob?jk=abc123def4567890&from=search&vjs=3"
        assert extract_job_key(url) == "abc123def4567890"

    def test_invalid_input_raises_error(self):
        """Test that invalid inputs raise ValueError."""
        with pytest.raises(ValueError, match="Could not extract job key"):
            extract_job_key("not-a-job-key")

        with pytest.raises(ValueError, match="Could not extract job key"):
            extract_job_key("https://indeed.com/company/acme")

    def test_short_key_raises_error(self):
        """Test that keys shorter than 16 chars raise ValueError."""
        with pytest.raises(ValueError, match="Could not extract job key"):
            extract_job_key("abc123")  # Too short

    def test_non_hex_key_raises_error(self):
        """Test that non-hex keys raise ValueError."""
        with pytest.raises(ValueError, match="Could not extract job key"):
            extract_job_key("ghij1234567890mn")  # 'g', 'h', 'i', 'j' are not hex


class TestGenerateDedupeKey:
    """Tests for dedupe key generation."""

    def test_basic_dedupe_key(self):
        """Test basic dedupe key generation - new format: source|normalized_fields."""
        key = _generate_dedupe_key("TestCorp", "Senior Software Engineer", "San Francisco, CA", "indeed_import")
        # Without job_key, uses fallback: source|company|title|location (normalized)
        assert key == "indeed_import|testcorp|seniorsoftwareengineer|sanfranciscoca"

    def test_dedupe_key_with_job_key(self):
        """Test dedupe key uses job_key when provided (robust deduplication)."""
        key = _generate_dedupe_key("TestCorp", "Engineer", "NYC", "indeed_import", job_key="abc123def4567890")
        # With job_key: source|job_key (preferred)
        assert key == "indeed_import|abc123def4567890"

    def test_dedupe_key_with_special_chars(self):
        """Test dedupe key strips special chars (normalized alphanumeric)."""
        key = _generate_dedupe_key("Test Corp, Inc.", "Senior (Cloud) Engineer!", "Remote", "indeed_import")
        # All non-alphanumeric chars removed
        assert key == "indeed_import|testcorpinc|seniorcloudengineer|remote"

    def test_dedupe_key_with_empty_values(self):
        """Test dedupe key handles empty/None values."""
        key = _generate_dedupe_key("", "Engineer", None, "indeed_import")
        assert key == "indeed_import||engineer|"

    def test_dedupe_key_default_source(self):
        """Test dedupe key uses default source if not specified."""
        key = _generate_dedupe_key("Company", "Title", "Location")
        assert key == "indeed_import|company|title|location"


class TestIndeedJobToMongoDoc:
    """Tests for converting Indeed data to MongoDB document."""

    def test_basic_conversion(self):
        """Test basic conversion to MongoDB format."""
        job_data = IndeedJobData(
            job_key="abc123def4567890",
            title="Senior Software Engineer",
            company="TestCorp",
            location="San Francisco, CA",
            description="A great job opportunity...",
            job_url="https://www.indeed.com/viewjob?jk=abc123def4567890",
            salary="$150,000 - $200,000 a year",
            job_type="Full-time",
            scraped_at=datetime(2025, 12, 31, 10, 0, 0),
            scrape_method="direct",
        )

        doc = indeed_job_to_mongodb_doc(job_data)

        # jobId is the Indeed job key
        assert doc["jobId"] == "abc123def4567890"
        assert doc["title"] == "Senior Software Engineer"
        assert doc["company"] == "TestCorp"
        assert doc["location"] == "San Francisco, CA"
        assert doc["description"] == "A great job opportunity..."
        assert doc["jobUrl"] == "https://www.indeed.com/viewjob?jk=abc123def4567890"

        # dedupeKey uses job_key for robust deduplication: source|job_key
        assert doc["dedupeKey"] == "indeed_import|abc123def4567890"

        assert doc["status"] == "under processing"  # Ready for batch processing
        assert "batch_added_at" in doc  # For batch table sorting
        assert doc["score"] is None
        assert doc["source"] == "indeed_import"

        # Check metadata
        assert doc["indeed_metadata"]["indeed_job_key"] == "abc123def4567890"
        assert doc["indeed_metadata"]["salary"] == "$150,000 - $200,000 a year"
        assert doc["indeed_metadata"]["job_type"] == "Full-time"
        assert doc["indeed_metadata"]["scrape_method"] == "direct"

    def test_conversion_with_minimal_data(self):
        """Test conversion with only required fields."""
        job_data = IndeedJobData(
            job_key="1234567890abcdef",
            title="Engineer",
            company="Co",
            location="Remote",
            description="Job desc",
            job_url="https://indeed.com/viewjob?jk=1234567890abcdef",
        )

        doc = indeed_job_to_mongodb_doc(job_data)

        assert doc["jobId"] == "1234567890abcdef"
        assert doc["title"] == "Engineer"
        # Uses job_key for deduplication
        assert doc["dedupeKey"] == "indeed_import|1234567890abcdef"
        assert doc["indeed_metadata"]["salary"] is None
        assert doc["indeed_metadata"]["job_type"] is None


# Sample Indeed HTML for testing HTML parsing
SAMPLE_INDEED_HTML = """
<!DOCTYPE html>
<html>
<head><title>Job Posting - Indeed</title></head>
<body>
<div class="jobsearch-JobInfoHeader-title-container">
    <h1 class="jobsearch-JobInfoHeader-title">Senior Software Engineer</h1>
</div>
<div data-testid="inlineHeader-companyName">
    <a href="/cmp/TestCorp-Inc">TestCorp Inc</a>
</div>
<div data-testid="inlineHeader-companyLocation">San Francisco, CA (Remote)</div>

<div id="jobDescriptionText">
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

<div class="jobsearch-JobMetadataHeader">
    <div class="salary-snippet">$150,000 - $200,000 a year</div>
    <span>Full-time</span>
</div>
</body>
</html>
"""

# HTML that triggers Cloudflare challenge detection
CLOUDFLARE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Just a moment...</title></head>
<body>
<div id="cf-browser-verification">
    <noscript>Please enable JavaScript to view this page.</noscript>
</div>
</body>
</html>
"""

# HTML with expired job
EXPIRED_JOB_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="message">
    <h1>This job has expired</h1>
    <p>The job you're looking for is no longer available.</p>
</div>
</body>
</html>
"""


class TestParseIndeedHtml:
    """Tests for HTML parsing functions."""

    def test_parse_complete_job_html(self):
        """Test parsing a complete job HTML page."""
        job_data = _parse_indeed_html(
            "abc123def4567890",
            "https://indeed.com/viewjob?jk=abc123def4567890",
            SAMPLE_INDEED_HTML
        )

        assert job_data.job_key == "abc123def4567890"
        assert job_data.title == "Senior Software Engineer"
        assert job_data.company == "TestCorp Inc"
        assert "San Francisco" in job_data.location
        assert "talented engineer" in job_data.description
        assert job_data.salary == "$150,000 - $200,000 a year"
        assert job_data.job_type == "Full-time"

    def test_parse_missing_title_raises_error(self):
        """Test that missing title raises ParseError."""
        html_no_title = "<html><body><div>No title here</div></body></html>"

        with pytest.raises(ParseError, match="Could not extract job title"):
            _parse_indeed_html("abc123def4567890", "http://example.com", html_no_title)

    def test_parse_missing_company_raises_error(self):
        """Test that missing company raises ParseError."""
        html_no_company = """
        <html><body>
            <h1 class="jobsearch-JobInfoHeader-title">Job Title</h1>
        </body></html>
        """

        with pytest.raises(ParseError, match="Could not extract company"):
            _parse_indeed_html("abc123def4567890", "http://example.com", html_no_company)

    def test_parse_missing_description_raises_error(self):
        """Test that missing description raises ParseError."""
        html_no_desc = """
        <html><body>
            <h1 class="jobsearch-JobInfoHeader-title">Job Title</h1>
            <div data-testid="inlineHeader-companyName">Company</div>
        </body></html>
        """

        with pytest.raises(ParseError, match="Could not extract job description"):
            _parse_indeed_html("abc123def4567890", "http://example.com", html_no_desc)


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

    def test_clean_removes_excessive_whitespace(self):
        """Test that excessive whitespace is cleaned."""
        from bs4 import BeautifulSoup

        html = "<div><p>Line 1</p><p></p><p></p><p>Line 2</p></div>"
        soup = BeautifulSoup(html, "html.parser")
        result = _clean_description(soup.find("div"))

        # Should not have more than one empty line between paragraphs
        assert "\n\n\n" not in result


class TestScrapeIndeedJob:
    """Tests for the main scrape function with mocked HTTP."""

    @patch("src.services.indeed_scraper.requests.get")
    def test_successful_direct_scrape(self, mock_get):
        """Test successful job scraping via direct HTTP."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_INDEED_HTML
        mock_response.headers = {}
        mock_get.return_value = mock_response

        result = scrape_indeed_job("abc123def4567890")

        assert result.job_key == "abc123def4567890"
        assert result.title == "Senior Software Engineer"
        assert result.company == "TestCorp Inc"
        assert result.scrape_method == "direct"
        mock_get.assert_called_once()

    @patch("src.services.indeed_scraper.requests.get")
    def test_job_not_found(self, mock_get):
        """Test handling of 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(JobNotFoundError, match="not found"):
            scrape_indeed_job("abc123def4567890")

    @patch("src.services.indeed_scraper.requests.get")
    def test_job_expired(self, mock_get):
        """Test handling of expired job."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = EXPIRED_JOB_HTML
        mock_response.headers = {}
        mock_get.return_value = mock_response

        with pytest.raises(JobNotFoundError, match="expired"):
            scrape_indeed_job("abc123def4567890")

    @patch("src.services.indeed_scraper._scrape_firecrawl")
    @patch("src.services.indeed_scraper.requests.get")
    def test_cloudflare_block_triggers_firecrawl_fallback(self, mock_get, mock_firecrawl):
        """Test that Cloudflare challenge triggers FireCrawl fallback."""
        # Direct scrape returns Cloudflare challenge
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = CLOUDFLARE_HTML
        mock_response.headers = {}
        mock_get.return_value = mock_response

        # FireCrawl succeeds
        mock_firecrawl.return_value = IndeedJobData(
            job_key="abc123def4567890",
            title="Engineer",
            company="TestCorp",
            location="Remote",
            description="Job desc",
            job_url="https://indeed.com/viewjob?jk=abc123def4567890",
        )

        result = scrape_indeed_job("abc123def4567890")

        mock_firecrawl.assert_called_once()
        assert result.title == "Engineer"

    @patch("src.services.indeed_scraper._scrape_firecrawl")
    @patch("src.services.indeed_scraper.requests.get")
    def test_403_triggers_firecrawl_fallback(self, mock_get, mock_firecrawl):
        """Test that 403 status triggers FireCrawl fallback."""
        # Direct scrape returns 403
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {"cf-ray": "abc123"}
        mock_get.return_value = mock_response

        # FireCrawl succeeds
        mock_firecrawl.return_value = IndeedJobData(
            job_key="abc123def4567890",
            title="Engineer",
            company="TestCorp",
            location="Remote",
            description="Job desc",
            job_url="https://indeed.com/viewjob?jk=abc123def4567890",
        )

        result = scrape_indeed_job("abc123def4567890")

        mock_firecrawl.assert_called_once()

    @patch("src.services.indeed_scraper.requests.get")
    def test_network_timeout(self, mock_get):
        """Test handling of network timeout triggers fallback attempt."""
        import requests

        mock_get.side_effect = requests.exceptions.Timeout()

        # Without FireCrawl available, should raise error
        with pytest.raises(IndeedScraperError):
            scrape_indeed_job("abc123def4567890")

    @patch("src.services.indeed_scraper.requests.get")
    def test_accepts_full_url(self, mock_get):
        """Test that full URLs are accepted and parsed correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_INDEED_HTML
        mock_response.headers = {}
        mock_get.return_value = mock_response

        # Test with full URL
        result = scrape_indeed_job("https://www.indeed.com/viewjob?jk=abc123def4567890&from=search")

        assert result.job_key == "abc123def4567890"


class TestExtractFunctions:
    """Tests for individual extraction functions."""

    def test_extract_title_from_header(self):
        """Test title extraction from jobsearch header."""
        from bs4 import BeautifulSoup

        html = '<h1 class="jobsearch-JobInfoHeader-title">Software Engineer</h1>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_title(soup) == "Software Engineer"

    def test_extract_title_from_h1_fallback(self):
        """Test title extraction from plain h1."""
        from bs4 import BeautifulSoup

        html = '<h1>Data Scientist</h1>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_title(soup) == "Data Scientist"

    def test_extract_company_from_testid(self):
        """Test company extraction from data-testid."""
        from bs4 import BeautifulSoup

        html = '<div data-testid="inlineHeader-companyName">TestCorp</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_company(soup) == "TestCorp"

    def test_extract_company_from_link(self):
        """Test company extraction from link within testid element."""
        from bs4 import BeautifulSoup

        html = '<div data-testid="inlineHeader-companyName"><a href="#">TestCorp Inc</a></div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_company(soup) == "TestCorp Inc"

    def test_extract_location_from_testid(self):
        """Test location extraction from data-testid."""
        from bs4 import BeautifulSoup

        html = '<div data-testid="inlineHeader-companyLocation">Remote (US)</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_location(soup) == "Remote (US)"

    def test_extract_salary(self):
        """Test salary extraction."""
        from bs4 import BeautifulSoup

        html = '<div class="salary-snippet">$120,000 - $150,000 a year</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_salary(soup) == "$120,000 - $150,000 a year"

    def test_extract_salary_hourly(self):
        """Test salary extraction for hourly rate."""
        from bs4 import BeautifulSoup

        html = '<div class="salary-snippet">$50 - $75 an hour</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_salary(soup) == "$50 - $75 an hour"

    def test_extract_job_type_fulltime(self):
        """Test job type extraction for full-time."""
        from bs4 import BeautifulSoup

        html = '<div class="jobsearch-JobMetadataHeader">Full-time</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_job_type(soup) == "Full-time"

    def test_extract_job_type_contract(self):
        """Test job type extraction for contract."""
        from bs4 import BeautifulSoup

        html = '<div class="metadata">Contract position</div>'
        soup = BeautifulSoup(html, "html.parser")
        assert _extract_job_type(soup) == "Contract"

    def test_extract_description_from_id(self):
        """Test description extraction from id."""
        from bs4 import BeautifulSoup

        html = '<div id="jobDescriptionText"><p>Great opportunity</p></div>'
        soup = BeautifulSoup(html, "html.parser")
        desc = _extract_description(soup)
        assert "Great opportunity" in desc
