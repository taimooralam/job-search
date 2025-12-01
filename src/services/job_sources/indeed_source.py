"""
Indeed Job Source (via JobSpy)

Fetches jobs from Indeed using the JobSpy open-source library.
Indeed has no rate limiting in JobSpy, making it ideal for automated ingestion.

Note: This uses web scraping which may violate Indeed's ToS.
Use responsibly with low volume (~50 jobs/run).
"""

import logging
from datetime import datetime
from typing import List, Optional

from . import JobSource, JobData

logger = logging.getLogger(__name__)


class IndeedSource(JobSource):
    """Indeed job source using JobSpy scraper."""

    def __init__(self):
        self._jobspy_available = None

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
        return "indeed_auto"

    def fetch_jobs(self, search_config: dict) -> List[JobData]:
        """
        Fetch jobs from Indeed using JobSpy.

        Args:
            search_config: Dictionary with keys:
                - search_term: Job title/keywords to search (required)
                - location: Location to search (optional, default: "")
                - results_wanted: Max results (optional, default: 50)
                - country: Country code (optional, default: "USA")
                - hours_old: Only jobs posted within N hours (optional)

        Returns:
            List of JobData objects
        """
        if not self._check_jobspy():
            logger.error("JobSpy not available, returning empty list")
            return []

        from jobspy import scrape_jobs

        search_term = search_config.get("search_term", "")
        if not search_term:
            logger.warning("No search_term provided for Indeed source")
            return []

        location = search_config.get("location", "")
        results_wanted = search_config.get("results_wanted", 50)
        country = search_config.get("country", "USA")
        hours_old = search_config.get("hours_old")

        logger.info(
            f"Fetching Indeed jobs: term='{search_term}', "
            f"location='{location}', country={country}, max={results_wanted}"
        )

        try:
            # JobSpy scrape_jobs parameters
            scrape_params = {
                "site_name": ["indeed"],
                "search_term": search_term,
                "location": location,
                "results_wanted": results_wanted,
                "country_indeed": country,
            }

            if hours_old:
                scrape_params["hours_old"] = hours_old

            # Fetch jobs as DataFrame
            jobs_df = scrape_jobs(**scrape_params)

            if jobs_df is None or jobs_df.empty:
                logger.info("No jobs found from Indeed")
                return []

            # Convert DataFrame to JobData objects
            jobs = self._convert_to_job_data(jobs_df)
            logger.info(f"Fetched {len(jobs)} jobs from Indeed")
            return jobs

        except Exception as e:
            logger.error(f"Error fetching Indeed jobs: {e}")
            return []

    def _convert_to_job_data(self, df) -> List[JobData]:
        """
        Convert JobSpy DataFrame to list of JobData.

        JobSpy DataFrame columns:
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
                logger.warning(f"Error converting Indeed job row: {e}")
                continue

        return jobs
