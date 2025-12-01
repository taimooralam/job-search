"""
Himalayas.app Job Source

Fetches remote jobs from Himalayas.app's free public API.
This is a legally compliant source focused on remote-first companies.

API: https://himalayas.app/jobs/api
MCP Server: https://mcp.himalayas.app/sse
"""

import logging
from datetime import datetime
from typing import List, Optional, Any, Dict

import requests

from . import JobSource, JobData

logger = logging.getLogger(__name__)


class HimalayasSource(JobSource):
    """Himalayas.app remote jobs source."""

    API_URL = "https://himalayas.app/jobs/api"
    TIMEOUT = 30  # seconds

    def get_source_name(self) -> str:
        return "himalayas_auto"

    def fetch_jobs(self, search_config: dict) -> List[JobData]:
        """
        Fetch remote jobs from Himalayas.app API.

        Args:
            search_config: Dictionary with keys:
                - keywords: List of keywords to filter by (optional)
                - max_results: Maximum jobs to return (optional, default: 100)
                - worldwide_only: Only include worldwide remote jobs (optional)

        Returns:
            List of JobData objects
        """
        keywords = search_config.get("keywords", [])
        max_results = search_config.get("max_results", 100)
        worldwide_only = search_config.get("worldwide_only", False)

        logger.info(
            f"Fetching Himalayas jobs: keywords={keywords}, "
            f"max={max_results}, worldwide_only={worldwide_only}"
        )

        try:
            response = requests.get(self.API_URL, timeout=self.TIMEOUT)
            response.raise_for_status()

            data = response.json()

            # API returns list of jobs directly
            if not isinstance(data, list):
                # Handle case where API might wrap jobs in an object
                data = data.get("jobs", data.get("data", []))

            if not data:
                logger.info("No jobs returned from Himalayas API")
                return []

            # Filter and convert jobs
            jobs = self._filter_and_convert(data, keywords, worldwide_only)

            # Limit results
            jobs = jobs[:max_results]

            logger.info(f"Fetched {len(jobs)} jobs from Himalayas")
            return jobs

        except requests.exceptions.Timeout:
            logger.error("Himalayas API request timed out")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Himalayas jobs: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Himalayas jobs: {e}")
            return []

    def _filter_and_convert(
        self,
        jobs_data: List[Dict[str, Any]],
        keywords: List[str],
        worldwide_only: bool
    ) -> List[JobData]:
        """
        Filter jobs by keywords and convert to JobData objects.

        Args:
            jobs_data: Raw job data from API
            keywords: Keywords to filter by (title or description match)
            worldwide_only: Only include jobs available worldwide

        Returns:
            Filtered list of JobData objects
        """
        jobs = []
        keywords_lower = [k.lower() for k in keywords]

        for job_dict in jobs_data:
            try:
                # Extract basic fields
                title = str(job_dict.get("title", "")).strip()
                company = str(job_dict.get("companyName", "") or job_dict.get("company", "")).strip()
                description = str(job_dict.get("description", "")).strip()

                # Build location from available fields
                location = self._build_location(job_dict)

                # Apply worldwide filter
                if worldwide_only:
                    location_lower = location.lower()
                    if "worldwide" not in location_lower and "anywhere" not in location_lower:
                        continue

                # Apply keyword filter if provided
                if keywords_lower:
                    text_to_search = f"{title} {description}".lower()
                    if not any(kw in text_to_search for kw in keywords_lower):
                        continue

                # Extract salary
                salary = self._extract_salary(job_dict)

                # Extract URL
                url = (
                    job_dict.get("applicationLink") or
                    job_dict.get("applyUrl") or
                    job_dict.get("url") or
                    ""
                )

                # If no direct URL, construct from slug if available
                if not url and job_dict.get("slug"):
                    url = f"https://himalayas.app/jobs/{job_dict['slug']}"

                # Parse posted date
                posted_date = self._parse_date(job_dict.get("pubDate") or job_dict.get("publishedAt"))

                job = JobData(
                    title=title,
                    company=company,
                    location=location,
                    description=description,
                    url=str(url).strip(),
                    salary=salary,
                    job_type=job_dict.get("employmentType") or job_dict.get("type"),
                    posted_date=posted_date,
                    source_id=str(job_dict.get("id", "")) if job_dict.get("id") else None,
                )

                # Skip jobs without essential fields
                if job.title and job.company:
                    jobs.append(job)

            except Exception as e:
                logger.warning(f"Error converting Himalayas job: {e}")
                continue

        return jobs

    def _build_location(self, job_dict: Dict[str, Any]) -> str:
        """Build location string from job data."""
        parts = []

        # Check various location fields
        if job_dict.get("locationRestrictions"):
            restrictions = job_dict["locationRestrictions"]
            if isinstance(restrictions, list):
                parts.extend(restrictions)
            elif isinstance(restrictions, str):
                parts.append(restrictions)

        if job_dict.get("location"):
            parts.append(str(job_dict["location"]))

        if job_dict.get("country"):
            parts.append(str(job_dict["country"]))

        # Check for worldwide/remote indicators
        if job_dict.get("isRemote") or job_dict.get("remote"):
            if not parts:
                parts.append("Remote")

        if job_dict.get("isWorldwide") or job_dict.get("worldwide"):
            parts.append("Worldwide")

        location = ", ".join(filter(None, parts)) if parts else "Remote"
        return location

    def _extract_salary(self, job_dict: Dict[str, Any]) -> Optional[str]:
        """Extract and format salary information."""
        # Try structured salary fields
        min_salary = job_dict.get("salaryCurrencyMinValue") or job_dict.get("minSalary")
        max_salary = job_dict.get("salaryCurrencyMaxValue") or job_dict.get("maxSalary")
        currency = job_dict.get("salaryCurrency", "USD")

        if min_salary and max_salary:
            try:
                return f"{currency} {int(min_salary):,} - {int(max_salary):,}"
            except (ValueError, TypeError):
                pass
        elif min_salary:
            try:
                return f"{currency} {int(min_salary):,}+"
            except (ValueError, TypeError):
                pass

        # Try salary string field
        salary_str = job_dict.get("salary") or job_dict.get("compensation")
        if salary_str:
            return str(salary_str)

        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None

        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

        try:
            # Try common formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except Exception:
            pass

        return None
