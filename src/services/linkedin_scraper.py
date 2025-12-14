"""
LinkedIn Job Scraper Service (GAP-065)

Scrapes job details from LinkedIn's public guest API without authentication.
Uses the publicly accessible job posting endpoint to extract job information.

API Reference:
- Job details: https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# LinkedIn public guest API base URL
LINKEDIN_JOB_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# User agent to mimic browser (LinkedIn blocks raw requests)
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


@dataclass
class LinkedInJobData:
    """Parsed LinkedIn job data."""
    job_id: str
    title: str
    company: str
    location: str
    description: str
    job_url: str

    # Optional job criteria
    seniority_level: Optional[str] = None
    employment_type: Optional[str] = None
    job_function: Optional[str] = None
    industries: Optional[List[str]] = None

    # Metadata
    scraped_at: Optional[datetime] = None
    raw_html: Optional[str] = None


class LinkedInScraperError(Exception):
    """Base exception for LinkedIn scraper errors."""
    pass


class JobNotFoundError(LinkedInScraperError):
    """Raised when the job posting is not found on LinkedIn."""
    pass


class RateLimitError(LinkedInScraperError):
    """Raised when LinkedIn rate limits the request."""
    pass


class ParseError(LinkedInScraperError):
    """Raised when the job page cannot be parsed."""
    pass


def extract_job_id(input_str: str) -> str:
    """
    Extract LinkedIn job ID from various input formats.

    Supports:
    - Raw job ID: "4081234567"
    - Full URL: "https://www.linkedin.com/jobs/view/4081234567"
    - URL with query params: "https://linkedin.com/jobs/view/4081234567?trk=..."

    Args:
        input_str: Job ID or LinkedIn URL

    Returns:
        Extracted job ID

    Raises:
        ValueError: If job ID cannot be extracted
    """
    input_str = input_str.strip()

    # If it's just digits, return as-is
    if input_str.isdigit():
        return input_str

    # Try to extract from URL patterns
    # Pattern 1: /jobs/view/{job_id}
    match = re.search(r'/jobs/view/(\d+)', input_str)
    if match:
        return match.group(1)

    # Pattern 2: /jobs/{job_id} (older format)
    match = re.search(r'/jobs/(\d+)', input_str)
    if match:
        return match.group(1)

    # Pattern 3: currentJobId={job_id} in query params
    match = re.search(r'currentJobId=(\d+)', input_str)
    if match:
        return match.group(1)

    raise ValueError(
        f"Could not extract job ID from: {input_str}. "
        "Expected a numeric job ID or LinkedIn job URL."
    )


def scrape_linkedin_job(job_id_or_url: str) -> LinkedInJobData:
    """
    Scrape job details from LinkedIn's public guest API.

    Args:
        job_id_or_url: LinkedIn job ID or URL

    Returns:
        LinkedInJobData with parsed job information

    Raises:
        JobNotFoundError: If job doesn't exist
        RateLimitError: If rate limited by LinkedIn
        ParseError: If HTML cannot be parsed
        LinkedInScraperError: For other errors
    """
    # Extract job ID from input
    job_id = extract_job_id(job_id_or_url)
    logger.info(f"Scraping LinkedIn job: {job_id}")

    # Build URL
    url = LINKEDIN_JOB_URL.format(job_id=job_id)

    try:
        # Make request with browser-like headers
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        # Check for rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "60")
            raise RateLimitError(
                f"LinkedIn rate limit hit. Retry after {retry_after} seconds."
            )

        # Check for not found
        if response.status_code == 404:
            raise JobNotFoundError(f"Job {job_id} not found on LinkedIn.")

        # Check for other errors
        if response.status_code != 200:
            raise LinkedInScraperError(
                f"LinkedIn returned status {response.status_code}: {response.text[:200]}"
            )

        # Parse HTML
        html_content = response.text
        job_data = _parse_job_html(job_id, html_content)

        logger.info(f"Successfully scraped job: {job_data.title} at {job_data.company}")
        return job_data

    except requests.exceptions.Timeout:
        raise LinkedInScraperError(f"Request timed out after {REQUEST_TIMEOUT}s")
    except requests.exceptions.RequestException as e:
        raise LinkedInScraperError(f"Network error: {str(e)}")


def _parse_job_html(job_id: str, html: str) -> LinkedInJobData:
    """
    Parse LinkedIn job posting HTML.

    Args:
        job_id: The LinkedIn job ID
        html: Raw HTML content

    Returns:
        Parsed LinkedInJobData

    Raises:
        ParseError: If required fields cannot be extracted
    """
    soup = BeautifulSoup(html, "html.parser")

    # Extract title
    title = _extract_title(soup)
    if not title:
        raise ParseError("Could not extract job title from LinkedIn page")

    # Extract company
    company = _extract_company(soup)
    if not company:
        raise ParseError("Could not extract company name from LinkedIn page")

    # Extract location
    location = _extract_location(soup) or "Location not specified"

    # Extract description
    description = _extract_description(soup)
    if not description:
        raise ParseError("Could not extract job description from LinkedIn page")

    # Extract job criteria (optional)
    criteria = _extract_job_criteria(soup)

    # Build job URL
    job_url = f"https://www.linkedin.com/jobs/view/{job_id}"

    return LinkedInJobData(
        job_id=job_id,
        title=title,
        company=company,
        location=location,
        description=description,
        job_url=job_url,
        seniority_level=criteria.get("seniority_level"),
        employment_type=criteria.get("employment_type"),
        job_function=criteria.get("job_function"),
        industries=criteria.get("industries"),
        scraped_at=datetime.utcnow(),
        raw_html=html[:5000]  # Store first 5KB for debugging
    )


def _extract_title(soup: BeautifulSoup) -> Optional[str]:
    """Extract job title from page."""
    # Primary: h1 with job-title class
    title_elem = soup.find("h1", class_=re.compile(r"top-card-layout__title"))
    if title_elem:
        return title_elem.get_text(strip=True)

    # Fallback: h2 with title class
    title_elem = soup.find("h2", class_=re.compile(r"title"))
    if title_elem:
        return title_elem.get_text(strip=True)

    # Fallback: h1 tag
    title_elem = soup.find("h1")
    if title_elem:
        return title_elem.get_text(strip=True)

    return None


def _extract_company(soup: BeautifulSoup) -> Optional[str]:
    """Extract company name from page."""
    # Primary: company link
    company_elem = soup.find("a", class_=re.compile(r"topcard__org-name-link"))
    if company_elem:
        return company_elem.get_text(strip=True)

    # Fallback: span with company class
    company_elem = soup.find("span", class_=re.compile(r"topcard__flavor"))
    if company_elem:
        return company_elem.get_text(strip=True)

    # Fallback: look for "at Company" pattern in subtitle
    subtitle = soup.find(class_=re.compile(r"subtitle"))
    if subtitle:
        text = subtitle.get_text(strip=True)
        # Company is typically first part before location
        return text.split("·")[0].strip() if "·" in text else text

    return None


def _extract_location(soup: BeautifulSoup) -> Optional[str]:
    """Extract job location from page."""
    # Primary: location span
    loc_elem = soup.find("span", class_=re.compile(r"topcard__flavor--bullet"))
    if loc_elem:
        return loc_elem.get_text(strip=True)

    # Fallback: look for location in subtitles
    for elem in soup.find_all(class_=re.compile(r"location")):
        text = elem.get_text(strip=True)
        if text:
            return text

    return None


def _extract_description(soup: BeautifulSoup) -> Optional[str]:
    """Extract job description from page."""
    # Primary: description section
    desc_elem = soup.find("div", class_=re.compile(r"description"))
    if desc_elem:
        # Find the inner content div
        content = desc_elem.find("div", class_=re.compile(r"show-more"))
        if content:
            return _clean_description(content)
        return _clean_description(desc_elem)

    # Fallback: section with description class
    desc_section = soup.find("section", class_=re.compile(r"description"))
    if desc_section:
        return _clean_description(desc_section)

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


def _extract_job_criteria(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract job criteria (seniority, type, function, industries)."""
    criteria = {}

    # Find criteria list
    criteria_list = soup.find("ul", class_=re.compile(r"job-criteria"))
    if not criteria_list:
        return criteria

    # Parse each criterion
    for item in criteria_list.find_all("li", class_=re.compile(r"job-criteria__item")):
        # Get header (criterion type)
        header = item.find(class_=re.compile(r"job-criteria__subheader"))
        if not header:
            continue
        header_text = header.get_text(strip=True).lower()

        # Get value
        value_elem = item.find(class_=re.compile(r"job-criteria__text"))
        if not value_elem:
            continue
        value = value_elem.get_text(strip=True)

        # Map to our fields
        if "seniority" in header_text:
            criteria["seniority_level"] = value
        elif "employment" in header_text or "type" in header_text:
            criteria["employment_type"] = value
        elif "function" in header_text:
            criteria["job_function"] = value
        elif "industr" in header_text:
            # Industries can be multiple
            criteria["industries"] = [v.strip() for v in value.split(",")]

    return criteria


def _generate_dedupe_key(company: str, title: str, location: str, source: str = "linkedin_import") -> str:
    """
    Generate a dedupeKey following the project's pattern.

    Format: company|title|location|source (all lowercase)
    Example: testcorp|senior software engineer|san francisco, ca|linkedin_import

    Args:
        company: Company name
        title: Job title
        location: Job location
        source: Job source (defaults to "linkedin_import")

    Returns:
        Dedupe key string
    """
    company_lower = (company or '').lower()
    title_lower = (title or '').lower()
    location_lower = (location or '').lower()
    source_lower = (source or '').lower()

    return f"{company_lower}|{title_lower}|{location_lower}|{source_lower}"


def linkedin_job_to_mongodb_doc(job_data: LinkedInJobData) -> Dict[str, Any]:
    """
    Convert LinkedIn job data to MongoDB level-2 schema document.

    Args:
        job_data: Parsed LinkedIn job data

    Returns:
        MongoDB document matching level-2 schema
    """
    dedupe_key = _generate_dedupe_key(
        job_data.company,
        job_data.title,
        job_data.location,
        "linkedin_import"
    )

    return {
        "jobId": job_data.job_id,  # Use LinkedIn job ID directly
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
        "source": "linkedin_import",

        # LinkedIn-specific metadata
        "linkedin_metadata": {
            "linkedin_job_id": job_data.job_id,
            "seniority_level": job_data.seniority_level,
            "employment_type": job_data.employment_type,
            "job_function": job_data.job_function,
            "industries": job_data.industries,
            "scraped_at": job_data.scraped_at.isoformat() if job_data.scraped_at else None,
        }
    }
