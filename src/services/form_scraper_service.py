"""
Form Scraper Service

Scrapes job application forms and extracts form fields using FireCrawl and LLM.
Caches scraped forms in MongoDB to avoid re-scraping.

Two modes of operation:
1. Direct scrape: scrape_form(url) → extract fields → generate answers
2. Discovery mode: discover_and_scrape_form(company, title) →
   search for official posting → scrape → extract → answer

Usage:
    service = FormScraperService()

    # Direct scrape (existing URL)
    result = await service.scrape_form(
        job_id="...",
        application_url="https://...",
    )

    # Discovery mode (batch pipeline)
    result = await service.discover_and_scrape_form(
        job_id="...",
        company="TechCorp",
        title="Software Engineer",
        fallback_url="https://linkedin.com/jobs/...",
    )
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.unified_llm import invoke_unified_sync
from src.common.repositories import (
    get_job_repository,
    JobRepositoryInterface,
    get_form_cache_repository,
    FormCacheRepositoryInterface,
)
from src.common.types import FormField

logger = logging.getLogger(__name__)


# ===== PYDANTIC MODELS FOR LLM OUTPUT =====


class ExtractedFormField(BaseModel):
    """Pydantic model for a single form field extracted by LLM."""

    label: str = Field(..., min_length=1, description="Field label/question text")
    field_type: str = Field(
        default="text",
        description="Type: text, textarea, url, file, checkbox, select, radio, date, number, email, phone",
    )
    required: bool = Field(default=False, description="Whether field is required")
    limit: Optional[int] = Field(
        default=None, description="Character/word limit if applicable"
    )
    options: Optional[List[str]] = Field(
        default=None, description="Options for select/checkbox/radio fields"
    )
    default_value: Optional[str] = Field(
        default=None, description="Default value or placeholder text"
    )


class FormExtractionOutput(BaseModel):
    """Pydantic model for LLM form extraction output."""

    form_title: Optional[str] = Field(
        default=None, description="Title of the application form if found"
    )
    fields: List[ExtractedFormField] = Field(
        default_factory=list, description="List of extracted form fields"
    )
    requires_login: bool = Field(
        default=False, description="Whether the form requires authentication"
    )
    form_type: str = Field(
        default="unknown",
        description="Type of form: workday, greenhouse, lever, taleo, custom, unknown",
    )


# ===== PROMPTS =====

SYSTEM_PROMPT_FORM_EXTRACTION = """You are an expert at analyzing job application forms.
Extract all form fields from the provided HTML/markdown content.

**FIELD TYPES:**
- text: Single-line text input (name, email, phone, short answers)
- textarea: Multi-line text input (cover letter, long answers, "why" questions)
- url: URL input (LinkedIn, portfolio, website)
- file: File upload (resume, cover letter PDF)
- select: Dropdown selection
- radio: Radio button choice
- checkbox: Checkbox selection (multi-select or single confirm)
- date: Date picker
- number: Numeric input (years of experience, salary)
- email: Email address input
- phone: Phone number input

**EXTRACTION RULES:**
1. Extract ALL visible form fields, including:
   - Required questions (usually marked with *)
   - Optional questions
   - Standard fields (name, email, phone, resume upload)
   - Custom questions (company-specific)
2. For textarea fields, look for character limits (e.g., "500 characters max")
3. For select/radio/checkbox, extract all available options
4. Mark fields as required if they have *, "required", or are clearly mandatory
5. Identify the ATS/form type if recognizable (Workday, Greenhouse, Lever, Taleo)
6. Set requires_login=true if the page shows login/sign-in prompts instead of the form

**OUTPUT FORMAT (JSON only):**
{
  "form_title": "Application for Software Engineer",
  "fields": [
    {"label": "First Name", "field_type": "text", "required": true},
    {"label": "Resume", "field_type": "file", "required": true},
    {"label": "Why are you interested in this role?", "field_type": "textarea", "required": true, "limit": 500},
    {"label": "Work Authorization", "field_type": "select", "required": true, "options": ["Yes", "No", "Require sponsorship"]}
  ],
  "requires_login": false,
  "form_type": "greenhouse"
}

NO TEXT OUTSIDE JSON."""

USER_PROMPT_FORM_EXTRACTION_TEMPLATE = """Analyze this application form page and extract all form fields:

URL: {url}

PAGE CONTENT:
{content}

Extract all form fields with their types, requirements, and options.
JSON only:"""


class FormScraperService:
    """
    Service for scraping job application forms and extracting fields.

    Uses FireCrawl for web scraping and LLM for intelligent field extraction.
    Caches results in MongoDB to avoid redundant scraping.
    """

    def __init__(
        self,
        job_repository: Optional[JobRepositoryInterface] = None,
        form_cache_repository: Optional[FormCacheRepositoryInterface] = None,
    ):
        """
        Initialize the service.

        Args:
            job_repository: Optional job repository for level-2 operations.
            form_cache_repository: Optional form cache repository.
        """
        self._job_repository = job_repository
        self._form_cache_repository = form_cache_repository
        self.firecrawl = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)

    def _get_job_repository(self) -> JobRepositoryInterface:
        """Get job repository, using singleton if not provided."""
        if self._job_repository is not None:
            return self._job_repository
        return get_job_repository()

    def _get_form_cache_repository(self) -> FormCacheRepositoryInterface:
        """Get form cache repository, using singleton if not provided."""
        if self._form_cache_repository is not None:
            return self._form_cache_repository
        return get_form_cache_repository()

    def _get_cached_form_fields(
        self, application_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check MongoDB cache for previously scraped form fields.

        Args:
            application_url: The application form URL

        Returns:
            Cached form data if found, None otherwise
        """
        repo = self._get_form_cache_repository()
        cached = repo.find_by_url(application_url)
        if cached:
            logger.info(f"Cache HIT for form: {application_url[:50]}...")
            return {
                "fields": cached.get("fields", []),
                "form_type": cached.get("form_type", "unknown"),
                "form_title": cached.get("form_title"),
                "scraped_at": cached.get("scraped_at"),
            }
        return None

    def _cache_form_fields(
        self,
        application_url: str,
        fields: List[Dict[str, Any]],
        form_type: str,
        form_title: Optional[str],
    ) -> bool:
        """
        Cache scraped form fields in MongoDB.

        Args:
            application_url: The application form URL
            fields: List of extracted form fields
            form_type: Type of ATS/form system
            form_title: Title of the form

        Returns:
            True if cached successfully
        """
        repo = self._get_form_cache_repository()
        return repo.upsert_cache(
            url=application_url,
            fields=fields,
            form_type=form_type,
            form_title=form_title,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        reraise=True,
    )
    def _scrape_form_page(self, url: str) -> Optional[str]:
        """
        Scrape the application form page using FireCrawl.

        Args:
            url: Application form URL

        Returns:
            Page content as markdown, or None if scraping fails
        """
        try:
            result = self.firecrawl.scrape(
                url,
                formats=["markdown"],
                only_main_content=False,  # Include form fields which may be outside "main" content
            )

            if result and hasattr(result, "markdown"):
                content = result.markdown
                # Return up to 15000 chars to capture full forms
                return content[:15000] if content else None

            return None

        except Exception as e:
            logger.warning(f"FireCrawl scraping failed for {url}: {str(e)}")
            raise

    def _extract_fields_with_llm(
        self, url: str, content: str
    ) -> FormExtractionOutput:
        """
        Extract form fields from page content using LLM.

        Args:
            url: Application form URL (for context)
            content: Scraped page content

        Returns:
            FormExtractionOutput with extracted fields
        """
        user_prompt = USER_PROMPT_FORM_EXTRACTION_TEMPLATE.format(
            url=url, content=content[:12000]
        )

        # Use unified LLM with step config
        result = invoke_unified_sync(
            prompt=user_prompt,
            system=SYSTEM_PROMPT_FORM_EXTRACTION,
            step_name="form_scraping",
            validate_json=False,  # We'll parse JSON manually for better error handling
        )

        if not result.success:
            raise ValueError(f"Form extraction LLM failed: {result.error}")

        llm_output = result.content.strip()

        # Remove markdown code blocks if present
        if llm_output.startswith("```"):
            llm_output = re.sub(r"^```(?:json)?\s*", "", llm_output)
            llm_output = re.sub(r"\s*```$", "", llm_output)
            llm_output = llm_output.strip()

        # Parse JSON
        try:
            data = json.loads(llm_output)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            logger.error(f"LLM output:\n{llm_output[:500]}")
            raise ValueError(f"Failed to parse form extraction JSON: {e}")

        # Validate with Pydantic
        try:
            return FormExtractionOutput(**data)
        except ValidationError as e:
            logger.error(f"Pydantic validation failed: {e}")
            raise ValueError(f"Form extraction validation failed: {e}")

    async def scrape_form(
        self,
        job_id: str,
        application_url: str,
        force_refresh: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Scrape application form and extract fields.

        Args:
            job_id: MongoDB job ID
            application_url: URL to the application form
            force_refresh: Whether to bypass cache
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with fields, form_type, form_title, scraped_at, or error
        """

        def emit_progress(step: str, status: str, message: str):
            if progress_callback:
                progress_callback(step, status, message)

        # Validate URL
        if not application_url:
            return {
                "success": False,
                "error": "No application URL provided",
                "fields": [],
            }

        if not application_url.startswith(("http://", "https://")):
            return {
                "success": False,
                "error": "Invalid URL format. URL must start with http:// or https://",
                "fields": [],
            }

        # Check cache unless force_refresh
        if not force_refresh:
            emit_progress("cache_check", "processing", "Checking cache...")
            cached = self._get_cached_form_fields(application_url)
            if cached:
                emit_progress("cache_check", "success", "Using cached form fields")
                return {
                    "success": True,
                    "fields": cached["fields"],
                    "form_type": cached["form_type"],
                    "form_title": cached.get("form_title"),
                    "scraped_at": cached.get("scraped_at"),
                    "from_cache": True,
                }
            emit_progress("cache_check", "success", "Cache miss, scraping form...")

        # Scrape the form page
        emit_progress("scrape_form", "processing", "Scraping application form...")
        try:
            content = self._scrape_form_page(application_url)
        except Exception as e:
            emit_progress("scrape_form", "failed", f"Scraping failed: {str(e)}")
            return {
                "success": False,
                "error": "Could not access the application form. The page may require login or be blocking automated access.",
                "fields": [],
            }

        if not content or len(content) < 100:
            emit_progress("scrape_form", "failed", "Page content too short or empty")
            return {
                "success": False,
                "error": "Could not access the application form. The page may require login or be blocking automated access.",
                "fields": [],
            }

        emit_progress(
            "scrape_form", "success", f"Scraped {len(content)} characters"
        )

        # Extract fields with LLM
        emit_progress("extract_fields", "processing", "Extracting form fields...")
        try:
            extraction = self._extract_fields_with_llm(application_url, content)
        except Exception as e:
            emit_progress("extract_fields", "failed", f"Extraction failed: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to extract form fields: {str(e)}",
                "fields": [],
            }

        # Check if form requires login
        if extraction.requires_login:
            emit_progress("extract_fields", "warning", "Form requires authentication")
            return {
                "success": False,
                "error": "Could not access the application form. The page may require login or be blocking automated access.",
                "fields": [],
            }

        # Check if any fields were found
        if not extraction.fields:
            emit_progress("extract_fields", "warning", "No form fields found")
            return {
                "success": False,
                "error": "No form fields found on this page. Please verify the URL points to an application form.",
                "fields": [],
            }

        # Convert to FormField format
        fields = []
        for f in extraction.fields:
            field: FormField = {
                "label": f.label,
                "field_type": f.field_type,
                "required": f.required,
                "limit": f.limit,
                "options": f.options,
                "default_value": f.default_value,
            }
            fields.append(field)

        emit_progress(
            "extract_fields",
            "success",
            f"Extracted {len(fields)} form fields ({extraction.form_type})",
        )

        # Cache the results
        emit_progress("cache_results", "processing", "Caching results...")
        self._cache_form_fields(
            application_url=application_url,
            fields=fields,
            form_type=extraction.form_type,
            form_title=extraction.form_title,
        )
        emit_progress("cache_results", "success", "Cached form fields")

        return {
            "success": True,
            "fields": fields,
            "form_type": extraction.form_type,
            "form_title": extraction.form_title,
            "scraped_at": datetime.utcnow().isoformat(),
            "from_cache": False,
        }

    async def scrape_and_generate_answers(
        self,
        job_id: str,
        application_url: str,
        force_refresh: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Scrape form and generate answers for all fields.

        This is the main entry point for the scrape-form-answers endpoint.
        It combines form scraping with answer generation.

        Args:
            job_id: MongoDB job ID
            application_url: URL to the application form
            force_refresh: Whether to bypass cache
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with fields, planned_answers, or error
        """
        from src.services.answer_generator_service import AnswerGeneratorService

        def emit_progress(step: str, status: str, message: str):
            if progress_callback:
                progress_callback(step, status, message)

        # Step 1: Scrape form
        scrape_result = await self.scrape_form(
            job_id=job_id,
            application_url=application_url,
            force_refresh=force_refresh,
            progress_callback=progress_callback,
        )

        if not scrape_result.get("success"):
            return scrape_result

        fields = scrape_result["fields"]

        # Step 2: Load job from MongoDB for context
        emit_progress("load_job", "processing", "Loading job context...")
        repo = self._get_job_repository()
        job = repo.find_one({"_id": ObjectId(job_id)})
        if not job:
            emit_progress("load_job", "failed", "Job not found")
            return {
                "success": False,
                "error": f"Job not found: {job_id}",
                "fields": fields,
            }
        emit_progress("load_job", "success", "Job context loaded")

        # Step 3: Generate answers
        emit_progress("generate_answers", "processing", "Generating personalized answers...")
        try:
            answer_service = AnswerGeneratorService()
            planned_answers = answer_service.generate_answers(job, form_fields=fields)
            emit_progress(
                "generate_answers",
                "success",
                f"Generated {len(planned_answers)} answers",
            )
        except Exception as e:
            emit_progress("generate_answers", "failed", f"Answer generation failed: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to generate answers: {str(e)}",
                "fields": fields,
            }

        # Step 4: Save to MongoDB
        emit_progress("save_results", "processing", "Saving to database...")
        try:
            repo = self._get_job_repository()
            repo.update_one(
                {"_id": ObjectId(job_id)},
                {
                    "$set": {
                        "application_form_fields": fields,
                        "planned_answers": planned_answers,
                        "form_scraped_at": datetime.utcnow(),
                        "updatedAt": datetime.utcnow(),
                    }
                },
            )
            emit_progress("save_results", "success", "Saved to database")
        except Exception as e:
            logger.error(f"Failed to save form results: {e}")
            emit_progress("save_results", "failed", f"Save failed: {str(e)}")

        return {
            "success": True,
            "fields": fields,
            "planned_answers": planned_answers,
            "form_type": scrape_result.get("form_type"),
            "form_title": scrape_result.get("form_title"),
            "scraped_at": scrape_result.get("scraped_at"),
            "from_cache": scrape_result.get("from_cache", False),
        }

    # ===== DISCOVERY MODE: SEARCH → SCRAPE → ANSWER =====

    def _search_official_posting(
        self, company: str, title: str
    ) -> Optional[str]:
        """
        Use Firecrawl search to find the official job posting URL.

        Tries two search strategies:
        1. Direct careers page search: "{company}" "{title}" apply careers
        2. Broader search: "{company}" "{title}" job application

        Args:
            company: Company name
            title: Job title

        Returns:
            Official posting URL if found, None otherwise
        """
        # Domains to exclude (aggregators, not official postings)
        AGGREGATOR_DOMAINS = {
            "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
            "monster.com", "dice.com", "simplyhired.com", "careerbuilder.com",
            "jooble.org", "adzuna.com", "reed.co.uk", "seek.com.au",
            "google.com/search",
        }

        def _is_aggregator(url: str) -> bool:
            url_lower = url.lower()
            return any(domain in url_lower for domain in AGGREGATOR_DOMAINS)

        def _extract_results(search_response) -> List[Dict[str, Any]]:
            """Extract results from Firecrawl search response."""
            results = getattr(search_response, "data", None)
            if results is None:
                results = getattr(search_response, "web", None)
            if results is None and isinstance(search_response, list):
                results = search_response
            return results or []

        queries = [
            f'"{company}" "{title}" apply careers',
            f'"{company}" "{title}" job application',
        ]

        for query in queries:
            try:
                logger.info(f"[FormScraper] Searching: {query[:80]}...")
                response = self.firecrawl.search(query, limit=5)
                results = _extract_results(response)

                for result in results:
                    url = None
                    if isinstance(result, dict):
                        url = result.get("url") or result.get("link")
                    elif hasattr(result, "url"):
                        url = result.url

                    if url and not _is_aggregator(url):
                        logger.info(f"[FormScraper] Found official posting: {url}")
                        return url

            except Exception as e:
                logger.warning(f"[FormScraper] Search failed for query '{query[:50]}': {e}")
                continue

        logger.info(f"[FormScraper] No official posting found for {company} - {title}")
        return None

    async def discover_and_scrape_form(
        self,
        job_id: str,
        company: str,
        title: str,
        fallback_url: Optional[str] = None,
        force_refresh: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Full discovery pipeline: search → scrape → extract fields → generate answers.

        This is the batch pipeline entry point. It first uses Firecrawl to
        search for the official job posting, then scrapes it for form fields,
        and finally uses Sonnet to fill out answers from the job schema.

        Fallback behavior:
        - If search finds a URL but scraping/answering fails, saves only the
          discovered application_url to the job document.
        - If search fails entirely, falls back to scraping fallback_url.

        Args:
            job_id: MongoDB job ID
            company: Company name for search
            title: Job title for search
            fallback_url: URL to try if search fails (e.g., job.application_url)
            force_refresh: Whether to bypass cache
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with fields, planned_answers, discovered_url, or error
        """
        def emit_progress(step: str, status: str, message: str):
            if progress_callback:
                progress_callback(step, status, message)

        # Step 1: Search for official posting URL
        emit_progress("form_search", "processing",
            f"Searching for official {company} posting...")
        discovered_url = None
        try:
            discovered_url = self._search_official_posting(company, title)
        except Exception as e:
            logger.warning(f"[FormScraper] Discovery search error: {e}")

        if discovered_url:
            emit_progress("form_search", "completed",
                f"Found official posting: {discovered_url[:60]}...")
        else:
            emit_progress("form_search", "completed",
                "No official posting found, trying fallback URL")

        # Determine which URL to scrape
        scrape_url = discovered_url or fallback_url

        if not scrape_url:
            return {
                "success": False,
                "error": "No official posting found and no fallback URL available",
                "fields": [],
                "discovered_url": None,
            }

        # Step 2-4: Scrape → extract fields → generate answers
        # Reuse existing scrape_and_generate_answers for the heavy lifting
        result = await self.scrape_and_generate_answers(
            job_id=job_id,
            application_url=scrape_url,
            force_refresh=force_refresh,
            progress_callback=progress_callback,
        )

        # Attach discovered URL to result
        result["discovered_url"] = discovered_url

        # Fallback: if we discovered a URL but scraping/answering failed,
        # save just the application_url so the detail page can show it
        if discovered_url and not result.get("success"):
            try:
                repo = self._get_job_repository()
                repo.update_one(
                    {"_id": ObjectId(job_id)},
                    {
                        "$set": {
                            "application_url": discovered_url,
                            "updatedAt": datetime.utcnow(),
                        }
                    },
                )
                logger.info(
                    f"[FormScraper] Saved discovered URL for job {job_id}: "
                    f"{discovered_url[:60]}"
                )
                result["url_saved"] = True
            except Exception as e:
                logger.warning(f"[FormScraper] Failed to save discovered URL: {e}")

        return result
