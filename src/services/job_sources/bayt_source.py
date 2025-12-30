"""
Bayt.com Job Source (via JobSpy)

Fetches jobs from Bayt.com using the JobSpy open-source library.
Bayt is the largest job board in the Gulf region (UAE, Saudi Arabia, Qatar, Kuwait).

Note: Bayt only uses the search_term parameter in JobSpy and searches internationally.
Use responsibly with low volume for personal job searching.

ToS Considerations:
- This uses web scraping which may violate Bayt's ToS
- Risk is civil (cease & desist), not criminal for personal use
- Keep volume low and use caching to minimize requests
"""

import logging
from datetime import datetime
from typing import Callable, List, Optional

from . import JobSource, JobData

logger = logging.getLogger(__name__)

# Type alias for log callback
LogCallback = Callable[[str], None]


class BaytSource(JobSource):
    """Bayt.com job source using JobSpy scraper."""

    def __init__(self, log_callback: Optional[LogCallback] = None):
        """
        Initialize the Bayt source.

        Args:
            log_callback: Optional callback for verbose logging (e.g., to Redis/SSE)
        """
        self._jobspy_available = None
        self._log_callback = log_callback

    def _log(self, message: str) -> None:
        """Emit a log message via callback if available."""
        if self._log_callback:
            self._log_callback(message)

    def _check_jobspy(self) -> bool:
        """Check if JobSpy is available."""
        if self._jobspy_available is None:
            try:
                from jobspy import scrape_jobs
                self._jobspy_available = True
            except ImportError:
                logger.warning("JobSpy not installed. Run: pip install python-jobspy")
                self._jobspy_available = False
        return self._jobspy_available

    def get_source_name(self) -> str:
        return "bayt"

    def fetch_jobs(self, search_config: dict) -> List[JobData]:
        """
        Fetch jobs from Bayt.com using JobSpy.

        Note: Bayt in JobSpy only supports the search_term parameter.
        Location filtering is not supported - it searches internationally.

        Args:
            search_config: Dictionary with keys:
                - search_term: Job title/keywords to search (required)
                - results_wanted: Max results (optional, default: 25)

        Returns:
            List of JobData objects
        """
        if not self._check_jobspy():
            logger.error("JobSpy not available, returning empty list")
            self._log("[api_error] JobSpy library not available")
            return []

        from jobspy import scrape_jobs

        search_term = search_config.get("search_term", "")
        if not search_term:
            logger.warning("No search_term provided for Bayt source")
            self._log("[api_error] No search_term provided")
            return []

        results_wanted = search_config.get("results_wanted", 25)

        logger.info(
            f"Fetching Bayt jobs: term='{search_term}', max={results_wanted}"
        )
        self._log(f"[api_call] Scraping Bayt (term='{search_term}', max={results_wanted})...")

        try:
            # JobSpy scrape_jobs parameters for Bayt
            # Note: Bayt only uses search_term, location/country params are ignored
            scrape_params = {
                "site_name": ["bayt"],
                "search_term": search_term,
                "results_wanted": results_wanted,
            }

            # Fetch jobs as DataFrame
            jobs_df = scrape_jobs(**scrape_params)

            if jobs_df is None or jobs_df.empty:
                logger.info("No jobs found from Bayt")
                self._log("[api_result] No jobs found from Bayt")
                return []

            self._log(f"[api_result] Received {len(jobs_df)} raw jobs from Bayt")

            # Convert DataFrame to JobData objects
            jobs = self._convert_to_job_data(jobs_df)
            logger.info(f"Fetched {len(jobs)} jobs from Bayt")
            self._log(f"[convert_result] Converted {len(jobs)} valid jobs")
            return jobs

        except Exception as e:
            logger.error(f"Error fetching Bayt jobs: {e}")
            self._log(f"[api_error] Scraping failed: {str(e)}")
            return []

    def _convert_to_job_data(self, df) -> List[JobData]:
        """
        Convert JobSpy DataFrame to list of JobData.

        JobSpy DataFrame columns (Bayt):
        - site, job_url, job_url_direct, title, company, location
        - job_type, date_posted, interval, min_amount, max_amount
        - currency, is_remote, description, company_url, logo_photo_url
        """
        jobs = []

        for _, row in df.iterrows():
            try:
                # Extract salary info
                salary = None
                if row.get("min_amount") and row.get("max_amount"):
                    currency = row.get("currency", "USD")
                    interval = row.get("interval", "yearly")
                    salary = f"{currency} {row['min_amount']:,.0f} - {row['max_amount']:,.0f} {interval}"
                elif row.get("min_amount"):
                    currency = row.get("currency", "USD")
                    salary = f"{currency} {row['min_amount']:,.0f}+"

                # Parse posted date
                posted_date = None
                if row.get("date_posted"):
                    try:
                        posted_date = datetime.fromisoformat(str(row["date_posted"]))
                    except (ValueError, TypeError):
                        pass

                # Handle location with remote indicator
                location = str(row.get("location", "")) or ""
                if row.get("is_remote"):
                    if location:
                        location = f"{location} (Remote)"
                    else:
                        location = "Remote"

                # Default to Gulf region indicator if location empty
                if not location:
                    location = "Gulf Region"

                job = JobData(
                    title=str(row.get("title", "")).strip(),
                    company=str(row.get("company", "")).strip(),
                    location=location.strip(),
                    description=str(row.get("description", "")).strip(),
                    url=str(row.get("job_url", "") or row.get("job_url_direct", "")).strip(),
                    salary=salary,
                    job_type=str(row.get("job_type", "")) if row.get("job_type") else None,
                    posted_date=posted_date,
                    source_id=str(row.get("id", "")) if row.get("id") else None,
                )

                # Skip jobs without essential fields
                if job.title and job.company:
                    jobs.append(job)

            except Exception as e:
                logger.warning(f"Error converting Bayt job row: {e}")
                continue

        return jobs
