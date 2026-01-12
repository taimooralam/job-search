"""
Indeed Job Scraper Service

Scrapes job details from Indeed job postings.
Uses direct HTTP requests with FireCrawl fallback for anti-bot bypass.

Unlike LinkedIn's public guest API, Indeed uses Cloudflare protection,
so we try direct HTTP first for speed, then fall back to FireCrawl's
stealth proxy if blocked.

URL Formats Supported:
- https://www.indeed.com/viewjob?jk=abc123def4567890
- https://indeed.com/rc/clk?jk=abc123def4567890
- https://www.indeed.com/jobs?q=...&vjk=abc123def4567890
- Raw key: abc123def4567890 (16-char alphanumeric)
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from src.common.dedupe import generate_dedupe_key as _unified_dedupe_key

logger = logging.getLogger(__name__)

# Indeed job URL format
INDEED_JOB_URL = "https://www.indeed.com/viewjob?jk={job_key}"

# User agent to mimic browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Request timeout in seconds
REQUEST_TIMEOUT = 15

# Job key pattern: 16-char alphanumeric (hex)
JOB_KEY_PATTERN = re.compile(r'^[a-f0-9]{16}$', re.IGNORECASE)


@dataclass
class IndeedJobData:
    """Parsed Indeed job data."""
    job_key: str
    title: str
    company: str
    location: str
    description: str
    job_url: str

    # Optional fields
    salary: Optional[str] = None
    job_type: Optional[str] = None

    # Metadata
    scraped_at: Optional[datetime] = None
    scrape_method: str = "direct"  # "direct" or "firecrawl"
    raw_html: Optional[str] = None


class IndeedScraperError(Exception):
    """Base exception for Indeed scraper errors."""
    pass


class JobNotFoundError(IndeedScraperError):
    """Raised when the job posting is not found on Indeed."""
    pass


class BlockedError(IndeedScraperError):
    """Raised when Indeed blocks the request (Cloudflare)."""
    pass


class ParseError(IndeedScraperError):
    """Raised when the job page cannot be parsed."""
    pass


def extract_job_key(input_str: str) -> str:
    """
    Extract Indeed job key from various input formats.

    Supports:
    - Raw job key: "abc123def4567890" (16-char hex)
    - viewjob URL: "https://indeed.com/viewjob?jk=abc123def4567890"
    - clk URL: "https://indeed.com/rc/clk?jk=abc123def4567890"
    - search URL with vjk: "https://indeed.com/jobs?q=...&vjk=abc123def4567890"

    Args:
        input_str: Job key or Indeed URL

    Returns:
        Extracted job key (16-char alphanumeric, lowercase)

    Raises:
        ValueError: If job key cannot be extracted
    """
    input_str = input_str.strip()

    # Check if it's already a raw job key (16-char hex)
    if JOB_KEY_PATTERN.match(input_str):
        return input_str.lower()

    # Extract from jk= parameter (most common)
    jk_match = re.search(r'[?&]jk=([a-f0-9]{16})', input_str, re.IGNORECASE)
    if jk_match:
        return jk_match.group(1).lower()

    # Extract from vjk= parameter (search results page)
    vjk_match = re.search(r'[?&]vjk=([a-f0-9]{16})', input_str, re.IGNORECASE)
    if vjk_match:
        return vjk_match.group(1).lower()

    raise ValueError(
        f"Could not extract job key from: {input_str}. "
        "Expected a 16-character job key or Indeed job URL with jk= parameter."
    )


def scrape_indeed_job(job_key_or_url: str) -> IndeedJobData:
    """
    Scrape job details from Indeed.

    Strategy: Try direct HTTP first, fall back to FireCrawl if blocked.

    Args:
        job_key_or_url: Indeed job key or URL

    Returns:
        IndeedJobData with parsed job information

    Raises:
        JobNotFoundError: If job doesn't exist
        BlockedError: If all scraping methods are blocked
        ParseError: If HTML cannot be parsed
        IndeedScraperError: For other errors
    """
    # Extract job key from input
    job_key = extract_job_key(job_key_or_url)
    logger.info(f"Scraping Indeed job: {job_key}")

    url = INDEED_JOB_URL.format(job_key=job_key)

    # Try direct HTTP first (free, fast)
    try:
        job_data = _scrape_direct(job_key, url)
        job_data.scrape_method = "direct"
        logger.info(f"Successfully scraped job via direct HTTP: {job_data.title}")
        return job_data
    except BlockedError as e:
        logger.info(f"Direct scraping blocked: {e}. Falling back to FireCrawl.")
    except JobNotFoundError:
        # Don't retry with FireCrawl if job doesn't exist
        raise
    except Exception as e:
        logger.warning(f"Direct scraping failed: {e}. Trying FireCrawl fallback.")

    # Fall back to FireCrawl (has stealth proxy)
    try:
        job_data = _scrape_firecrawl(job_key, url)
        job_data.scrape_method = "firecrawl"
        logger.info(f"Successfully scraped job via FireCrawl: {job_data.title}")
        return job_data
    except Exception as e:
        logger.error(f"FireCrawl scraping also failed: {e}")
        raise IndeedScraperError(f"Could not scrape Indeed job after all attempts: {str(e)}")


def _scrape_direct(job_key: str, url: str) -> IndeedJobData:
    """Scrape using direct HTTP request."""
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )
    except requests.exceptions.Timeout:
        raise IndeedScraperError(f"Request timed out after {REQUEST_TIMEOUT}s")
    except requests.exceptions.RequestException as e:
        raise IndeedScraperError(f"Network error: {str(e)}")

    # Check for not found
    if response.status_code == 404:
        raise JobNotFoundError(f"Job {job_key} not found on Indeed")

    # Check for Cloudflare challenge in headers
    if response.status_code == 403 or "cf-ray" in response.headers:
        raise BlockedError("Cloudflare challenge detected (403 or cf-ray header)")

    if response.status_code != 200:
        raise IndeedScraperError(f"Indeed returned status {response.status_code}")

    # Check for Cloudflare challenge in content
    if "Just a moment" in response.text or "cf-browser-verification" in response.text:
        raise BlockedError("Cloudflare challenge page detected in response body")

    # Check for Indeed's job expired page
    if "this job has expired" in response.text.lower():
        raise JobNotFoundError(f"Job {job_key} has expired on Indeed")

    return _parse_indeed_html(job_key, url, response.text)


def _scrape_firecrawl(job_key: str, url: str) -> IndeedJobData:
    """Scrape using FireCrawl with stealth proxy."""
    try:
        from firecrawl import FirecrawlApp
        from src.common.config import Config
    except ImportError as e:
        raise IndeedScraperError(f"FireCrawl not available: {e}")

    if not Config.FIRECRAWL_API_KEY:
        raise IndeedScraperError("FIRECRAWL_API_KEY not configured")

    firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

    try:
        # Use stealth proxy for anti-bot bypass
        result = firecrawl.scrape_url(url, params={
            "formats": ["html"],
            "waitFor": 2000,  # Wait for JS to load
        })
    except Exception as e:
        raise IndeedScraperError(f"FireCrawl request failed: {str(e)}")

    if not result or not result.get("html"):
        raise IndeedScraperError("FireCrawl returned no HTML content")

    html = result.get("html", "")

    # Check if FireCrawl also got blocked
    if "Just a moment" in html or "cf-browser-verification" in html:
        raise BlockedError("FireCrawl also received Cloudflare challenge")

    return _parse_indeed_html(job_key, url, html)


def _parse_indeed_html(job_key: str, url: str, html: str) -> IndeedJobData:
    """
    Parse Indeed job posting HTML.

    Args:
        job_key: The Indeed job key
        url: The job URL
        html: Raw HTML content

    Returns:
        Parsed IndeedJobData

    Raises:
        ParseError: If required fields cannot be extracted
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = _extract_title(soup)
    if not title:
        raise ParseError("Could not extract job title from Indeed page")

    # Extract company
    company = _extract_company(soup)
    if not company:
        raise ParseError("Could not extract company name from Indeed page")

    # Extract location
    location = _extract_location(soup) or "Location not specified"

    # Extract description
    description = _extract_description(soup)
    if not description:
        raise ParseError("Could not extract job description from Indeed page")

    # Extract optional fields
    salary = _extract_salary(soup)
    job_type = _extract_job_type(soup)

    return IndeedJobData(
        job_key=job_key,
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=url,
        salary=salary,
        job_type=job_type,
        scraped_at=datetime.utcnow(),
        raw_html=html[:5000]  # Store first 5KB for debugging
    )


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract job title from Indeed page."""
    # Primary: jobsearch-JobInfoHeader-title class
    title_elem = soup.find(class_=re.compile(r'jobsearch-JobInfoHeader-title'))
    if title_elem:
        return title_elem.get_text(strip=True)

    # Fallback: data-testid for title
    title_elem = soup.find(attrs={"data-testid": "jobsearch-JobInfoHeader-title"})
    if title_elem:
        return title_elem.get_text(strip=True)

    # Fallback: h1 tag with job title
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        # Filter out generic headers
        if text and len(text) > 3 and "indeed" not in text.lower():
            return text

    return None


def _extract_company(soup: BeautifulSoup) -> Optional[str]:
    """Extract company name from Indeed page."""
    # Primary: data-testid for company name
    company_elem = soup.find(attrs={"data-testid": "inlineHeader-companyName"})
    if company_elem:
        # Get the text, but might be wrapped in an anchor
        link = company_elem.find("a")
        if link:
            return link.get_text(strip=True)
        return company_elem.get_text(strip=True)

    # Fallback: company name class patterns
    for pattern in [r'companyName', r'css-1h7lukg', r'css-1saizt3', r'icl-u-lg-mr--sm']:
        company_elem = soup.find(class_=re.compile(pattern))
        if company_elem:
            text = company_elem.get_text(strip=True)
            if text and len(text) > 1:
                return text

    # Fallback: company link with specific attributes
    company_link = soup.find("a", attrs={"data-tn-element": "companyName"})
    if company_link:
        return company_link.get_text(strip=True)

    return None


def _extract_location(soup: BeautifulSoup) -> Optional[str]:
    """Extract job location from Indeed page."""
    # Primary: data-testid for location
    loc_elem = soup.find(attrs={"data-testid": "inlineHeader-companyLocation"})
    if loc_elem:
        return loc_elem.get_text(strip=True)

    # Fallback: companyLocation class
    loc_elem = soup.find(class_=re.compile(r'companyLocation'))
    if loc_elem:
        return loc_elem.get_text(strip=True)

    # Fallback: look for location icon followed by text
    loc_elem = soup.find(class_=re.compile(r'css-1rldrqf|jobsearch-JobInfoHeader-subtitle'))
    if loc_elem:
        text = loc_elem.get_text(strip=True)
        # Location is often after company name, separated by various chars
        parts = re.split(r'[•·|]', text)
        if len(parts) > 1:
            return parts[-1].strip()

    return None


def _extract_description(soup: BeautifulSoup) -> Optional[str]:
    """Extract job description from Indeed page."""
    # Primary: jobDescriptionText id
    desc_elem = soup.find(id="jobDescriptionText")
    if desc_elem:
        return _clean_description(desc_elem)

    # Fallback: jobsearch-jobDescriptionText class
    desc_elem = soup.find(class_=re.compile(r'jobsearch-jobDescriptionText'))
    if desc_elem:
        return _clean_description(desc_elem)

    # Fallback: job-description class
    desc_elem = soup.find(class_=re.compile(r'job-description|description'))
    if desc_elem:
        return _clean_description(desc_elem)

    return None


def _extract_salary(soup: BeautifulSoup) -> Optional[str]:
    """Extract salary information if present."""
    # Look for salary in metadata
    salary_elem = soup.find(class_=re.compile(r'salary-snippet|attribute_snippet|metadata'))
    if salary_elem:
        text = salary_elem.get_text(strip=True)
        # Check if it looks like salary
        if "$" in text or "year" in text.lower() or "hour" in text.lower():
            return text

    # Look for data-testid salary
    salary_elem = soup.find(attrs={"data-testid": re.compile(r'salary|compensation')})
    if salary_elem:
        return salary_elem.get_text(strip=True)

    return None


def _extract_job_type(soup: BeautifulSoup) -> Optional[str]:
    """Extract job type (Full-time, Part-time, etc.)."""
    job_types = ["Full-time", "Part-time", "Contract", "Temporary", "Internship", "Remote"]

    # Look in metadata header
    metadata_elem = soup.find(class_=re.compile(r'jobsearch-JobMetadataHeader|metadata'))
    if metadata_elem:
        text = metadata_elem.get_text(strip=True)
        for jtype in job_types:
            if jtype.lower() in text.lower():
                return jtype

    # Look in attributes/tags
    for attr_elem in soup.find_all(class_=re.compile(r'attribute|tag|badge')):
        text = attr_elem.get_text(strip=True)
        for jtype in job_types:
            if jtype.lower() in text.lower():
                return jtype

    return None


def _clean_description(elem) -> str:
    """Clean and format job description HTML."""
    # Get text while preserving some structure
    # Replace <br> with newlines
    for br in elem.find_all("br"):
        br.replace_with("\n")

    # Replace <li> with bullet points
    for li in elem.find_all("li"):
        li.insert(0, "• ")
        li.append("\n")

    # Replace <p> with double newlines
    for p in elem.find_all("p"):
        p.append("\n\n")

    # Get text and clean up whitespace
    text = elem.get_text()

    # Clean up excessive whitespace while preserving paragraph breaks
    lines = text.split("\n")
    cleaned_lines = []
    prev_empty = False

    for line in lines:
        line = line.strip()
        if not line:
            if not prev_empty:
                cleaned_lines.append("")
                prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False

    return "\n".join(cleaned_lines).strip()


def _generate_dedupe_key(
    company: str,
    title: str,
    location: str,
    source: str = "indeed_import",
    job_key: str = None,
) -> str:
    """
    Generate a dedupeKey using unified dedupe module.

    Uses job_key (Indeed's unique ID) if available, otherwise falls back
    to normalized text-based key.

    Args:
        company: Company name
        title: Job title
        location: Job location
        source: Job source (defaults to "indeed_import")
        job_key: Indeed's unique job key (16-char hex)

    Returns:
        Dedupe key string
    """
    return _unified_dedupe_key(
        source=source,
        source_id=job_key,
        company=company,
        title=title,
        location=location,
    )


def indeed_job_to_mongodb_doc(job_data: IndeedJobData) -> Dict[str, Any]:
    """
    Convert Indeed job data to MongoDB level-2 schema document.

    Args:
        job_data: Parsed Indeed job data

    Returns:
        MongoDB document matching level-2 schema
    """
    dedupe_key = _generate_dedupe_key(
        job_data.company,
        job_data.title,
        job_data.location,
        "indeed_import",
        job_key=job_data.job_key,  # Use Indeed's unique ID for robust deduplication
    )

    return {
        "jobId": job_data.job_key,  # Use Indeed job key
        "title": job_data.title,
        "company": job_data.company,
        "location": job_data.location,
        "jobUrl": job_data.job_url,
        "description": job_data.description,
        "dedupeKey": dedupe_key,
        "createdAt": datetime.utcnow(),
        "status": "under processing",  # Match batch processing filter
        "batch_added_at": datetime.utcnow(),  # For batch table sorting
        "score": None,  # Will be set by quick scorer
        "source": "indeed_import",

        # Indeed-specific metadata
        "indeed_metadata": {
            "indeed_job_key": job_data.job_key,
            "salary": job_data.salary,
            "job_type": job_data.job_type,
            "scraped_at": job_data.scraped_at.isoformat() if job_data.scraped_at else None,
            "scrape_method": job_data.scrape_method,
        }
    }
