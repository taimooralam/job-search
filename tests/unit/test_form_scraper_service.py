"""
Unit tests for FormScraperService.

Tests form scraping, LLM field extraction, caching, and answer generation integration.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.form_scraper_service import (
    FormScraperService,
    FormExtractionOutput,
    ExtractedFormField,
)


# ===== FIXTURES =====


@pytest.fixture
def mock_firecrawl():
    """Mock FirecrawlApp for scraping."""
    with patch("src.services.form_scraper_service.FirecrawlApp") as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_llm():
    """Mock invoke_unified_sync for field extraction."""
    with patch("src.services.form_scraper_service.invoke_unified_sync") as mock:
        yield mock


@pytest.fixture
def mock_db_client():
    """Mock MongoDB client."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    mock_db.__getitem__ = MagicMock(return_value=MagicMock())
    return mock_client


@pytest.fixture
def sample_form_html():
    """Sample scraped form content."""
    return """
    # Apply for Software Engineer

    ## Application Form

    **First Name** *
    [Text input]

    **Last Name** *
    [Text input]

    **Email** *
    [Email input]

    **Resume** *
    [File upload - PDF, DOC, DOCX]

    **Why are you interested in this role?** *
    [Textarea - 500 characters max]

    **Work Authorization** *
    - Yes, I am authorized to work
    - No, I require sponsorship

    **LinkedIn Profile**
    [URL input]
    """


@pytest.fixture
def sample_extraction_output():
    """Sample LLM extraction output."""
    return {
        "form_title": "Apply for Software Engineer",
        "fields": [
            {"label": "First Name", "field_type": "text", "required": True},
            {"label": "Last Name", "field_type": "text", "required": True},
            {"label": "Email", "field_type": "email", "required": True},
            {"label": "Resume", "field_type": "file", "required": True},
            {
                "label": "Why are you interested in this role?",
                "field_type": "textarea",
                "required": True,
                "limit": 500,
            },
            {
                "label": "Work Authorization",
                "field_type": "select",
                "required": True,
                "options": ["Yes, I am authorized to work", "No, I require sponsorship"],
            },
            {"label": "LinkedIn Profile", "field_type": "url", "required": False},
        ],
        "requires_login": False,
        "form_type": "greenhouse",
    }


@pytest.fixture
def sample_job():
    """Sample job document from MongoDB."""
    from bson import ObjectId

    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "job_description": "We are looking for a talented software engineer...",
        "application_url": "https://jobs.greenhouse.io/acme/apply",
        "pain_points": ["Need to scale backend systems", "Improve CI/CD pipeline"],
        "strategic_needs": ["Build microservices architecture"],
        "extracted_jd": {"top_keywords": ["Python", "AWS", "Kubernetes"]},
        "company_research": {"summary": "Acme Corp is a leading tech company"},
        "fit_rationale": "Strong match for backend engineering role",
    }


# ===== TEST CLASSES =====


class TestFormExtractionOutput:
    """Tests for Pydantic model validation."""

    def test_valid_extraction_output(self, sample_extraction_output):
        """Test valid extraction output parses correctly."""
        output = FormExtractionOutput(**sample_extraction_output)

        assert output.form_title == "Apply for Software Engineer"
        assert len(output.fields) == 7
        assert output.requires_login is False
        assert output.form_type == "greenhouse"

    def test_minimal_extraction_output(self):
        """Test minimal output with empty fields list."""
        output = FormExtractionOutput(fields=[])

        assert output.form_title is None
        assert output.fields == []
        assert output.requires_login is False
        assert output.form_type == "unknown"

    def test_field_with_options(self):
        """Test field with options parses correctly."""
        field = ExtractedFormField(
            label="Select Country",
            field_type="select",
            required=True,
            options=["USA", "Canada", "UK"],
        )

        assert field.label == "Select Country"
        assert field.options == ["USA", "Canada", "UK"]


class TestFormScraperServiceScraping:
    """Tests for form scraping functionality."""

    @pytest.mark.asyncio
    async def test_scrape_form_success(
        self, mock_firecrawl, mock_llm, sample_form_html, sample_extraction_output
    ):
        """Test successful form scraping and extraction."""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.markdown = sample_form_html
        mock_firecrawl.scrape.return_value = mock_result

        # Mock invoke_unified_sync return value
        mock_llm_result = MagicMock()
        mock_llm_result.success = True
        mock_llm_result.content = json.dumps(sample_extraction_output)
        mock_llm.return_value = mock_llm_result

        # Create service with mocked DB
        with patch.object(FormScraperService, "_get_cached_form_fields", return_value=None):
            with patch.object(FormScraperService, "_cache_form_fields", return_value=True):
                service = FormScraperService()
                service.firecrawl = mock_firecrawl

                result = await service.scrape_form(
                    job_id="test_job_id",
                    application_url="https://example.com/apply",
                    force_refresh=False,
                )

        assert result["success"] is True
        assert len(result["fields"]) == 7
        assert result["form_type"] == "greenhouse"
        assert result["from_cache"] is False

    @pytest.mark.asyncio
    async def test_scrape_form_uses_cache(self, mock_firecrawl):
        """Test that cached form fields are returned without re-scraping."""
        cached_fields = [
            {"label": "Name", "field_type": "text", "required": True}
        ]
        cached_data = {
            "fields": cached_fields,
            "form_type": "workday",
            "form_title": "Application",
            "scraped_at": datetime.utcnow().isoformat(),
        }

        with patch.object(
            FormScraperService, "_get_cached_form_fields", return_value=cached_data
        ):
            service = FormScraperService()

            result = await service.scrape_form(
                job_id="test_job_id",
                application_url="https://example.com/apply",
                force_refresh=False,
            )

        assert result["success"] is True
        assert result["fields"] == cached_fields
        assert result["from_cache"] is True
        # FireCrawl should not be called when using cache
        mock_firecrawl.scrape.assert_not_called()

    @pytest.mark.asyncio
    async def test_scrape_form_force_refresh_bypasses_cache(
        self, mock_firecrawl, mock_llm, sample_form_html, sample_extraction_output
    ):
        """Test that force_refresh=True bypasses cache."""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.markdown = sample_form_html
        mock_firecrawl.scrape.return_value = mock_result

        mock_llm_result = MagicMock()
        mock_llm_result.success = True
        mock_llm_result.content = json.dumps(sample_extraction_output)
        mock_llm.return_value = mock_llm_result

        with patch.object(
            FormScraperService, "_get_cached_form_fields"
        ) as mock_cache_check:
            with patch.object(FormScraperService, "_cache_form_fields", return_value=True):
                service = FormScraperService()
                service.firecrawl = mock_firecrawl

                result = await service.scrape_form(
                    job_id="test_job_id",
                    application_url="https://example.com/apply",
                    force_refresh=True,
                )

        # Cache check should not be called when force_refresh=True
        mock_cache_check.assert_not_called()
        assert result["success"] is True
        assert result["from_cache"] is False

    @pytest.mark.asyncio
    async def test_scrape_form_invalid_url(self):
        """Test error handling for invalid URL."""
        service = FormScraperService()

        result = await service.scrape_form(
            job_id="test_job_id",
            application_url="not-a-valid-url",
            force_refresh=False,
        )

        assert result["success"] is False
        assert "Invalid URL" in result["error"]

    @pytest.mark.asyncio
    async def test_scrape_form_empty_url(self):
        """Test error handling for empty URL."""
        service = FormScraperService()

        result = await service.scrape_form(
            job_id="test_job_id",
            application_url="",
            force_refresh=False,
        )

        assert result["success"] is False
        assert "No application URL" in result["error"]

    @pytest.mark.asyncio
    async def test_scrape_form_firecrawl_failure(self, mock_firecrawl):
        """Test error handling when FireCrawl fails."""
        mock_firecrawl.scrape.side_effect = Exception("Connection timeout")

        with patch.object(FormScraperService, "_get_cached_form_fields", return_value=None):
            service = FormScraperService()
            service.firecrawl = mock_firecrawl

            result = await service.scrape_form(
                job_id="test_job_id",
                application_url="https://example.com/apply",
                force_refresh=False,
            )

        assert result["success"] is False
        assert "Could not access" in result["error"]

    @pytest.mark.asyncio
    async def test_scrape_form_login_required(self, mock_firecrawl, mock_llm):
        """Test handling of login-protected forms."""
        mock_result = MagicMock()
        mock_result.markdown = "Please log in to continue..." + " " * 100  # Ensure > 100 chars
        mock_firecrawl.scrape.return_value = mock_result

        mock_llm_result = MagicMock()
        mock_llm_result.success = True
        mock_llm_result.content = json.dumps({
            "form_title": None,
            "fields": [],
            "requires_login": True,
            "form_type": "unknown",
        })
        mock_llm.return_value = mock_llm_result

        with patch.object(FormScraperService, "_get_cached_form_fields", return_value=None):
            with patch.object(FormScraperService, "_cache_form_fields", return_value=True):
                service = FormScraperService()
                service.firecrawl = mock_firecrawl

                result = await service.scrape_form(
                    job_id="test_job_id",
                    application_url="https://example.com/apply",
                    force_refresh=False,
                )

        assert result["success"] is False
        assert "require login" in result["error"]

    @pytest.mark.asyncio
    async def test_scrape_form_no_fields_found(self, mock_firecrawl, mock_llm):
        """Test handling when no form fields are found."""
        # Content must be long enough (>= 100 chars) to pass initial check
        mock_result = MagicMock()
        mock_result.markdown = "Welcome to our company website! " * 10  # Make it longer
        mock_firecrawl.scrape.return_value = mock_result

        mock_llm_result = MagicMock()
        mock_llm_result.success = True
        mock_llm_result.content = json.dumps({
            "form_title": None,
            "fields": [],
            "requires_login": False,
            "form_type": "unknown",
        })
        mock_llm.return_value = mock_llm_result

        with patch.object(FormScraperService, "_get_cached_form_fields", return_value=None):
            service = FormScraperService()
            service.firecrawl = mock_firecrawl

            result = await service.scrape_form(
                job_id="test_job_id",
                application_url="https://example.com/about",
                force_refresh=False,
            )

        assert result["success"] is False
        assert "No form fields found" in result["error"]


class TestFormScraperServiceAnswerGeneration:
    """Tests for the combined scrape and generate flow."""

    @pytest.mark.asyncio
    async def test_scrape_and_generate_answers_success(
        self,
        mock_firecrawl,
        mock_llm,
        sample_form_html,
        sample_extraction_output,
        sample_job,
    ):
        """Test successful form scraping and answer generation."""
        from src.common.repositories.base import WriteResult

        # Setup scraping mocks
        mock_result = MagicMock()
        mock_result.markdown = sample_form_html
        mock_firecrawl.scrape.return_value = mock_result

        # Setup LLM mocks - invoke_unified_sync for field extraction
        mock_llm_result = MagicMock()
        mock_llm_result.success = True
        mock_llm_result.content = json.dumps(sample_extraction_output)
        mock_llm.return_value = mock_llm_result

        # Setup mock job repository
        mock_job_repository = MagicMock()
        mock_job_repository.find_one.return_value = sample_job
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )

        # Mock answer service
        mock_answer_service_instance = MagicMock()
        mock_answer_service_instance.generate_answers.return_value = [
            {
                "question": "Why are you interested?",
                "answer": "Generated answer",
                "field_type": "textarea",
                "required": True,
                "source": "auto_generated",
            }
        ]

        with patch.object(FormScraperService, "_get_cached_form_fields", return_value=None):
            with patch.object(FormScraperService, "_cache_form_fields", return_value=True):
                service = FormScraperService(job_repository=mock_job_repository)
                service.firecrawl = mock_firecrawl

                # Patch the import inside the method
                with patch.dict(
                    "sys.modules",
                    {
                        "src.services.answer_generator_service": MagicMock(
                            AnswerGeneratorService=MagicMock(
                                return_value=mock_answer_service_instance
                            )
                        )
                    },
                ):
                    result = await service.scrape_and_generate_answers(
                        job_id="507f1f77bcf86cd799439011",
                        application_url="https://example.com/apply",
                        force_refresh=False,
                    )

        assert result["success"] is True
        assert "fields" in result
        assert "planned_answers" in result
        assert len(result["planned_answers"]) >= 1


class TestProgressCallback:
    """Tests for progress callback functionality."""

    @pytest.mark.asyncio
    async def test_progress_callback_is_called(self, mock_firecrawl, mock_llm, sample_form_html, sample_extraction_output):
        """Test that progress callback is called during scraping."""
        progress_calls = []

        def track_progress(step, status, message):
            progress_calls.append((step, status, message))

        # Setup mocks
        mock_result = MagicMock()
        mock_result.markdown = sample_form_html
        mock_firecrawl.scrape.return_value = mock_result

        mock_llm_result = MagicMock()
        mock_llm_result.success = True
        mock_llm_result.content = json.dumps(sample_extraction_output)
        mock_llm.return_value = mock_llm_result

        with patch.object(FormScraperService, "_get_cached_form_fields", return_value=None):
            with patch.object(FormScraperService, "_cache_form_fields", return_value=True):
                service = FormScraperService()
                service.firecrawl = mock_firecrawl

                await service.scrape_form(
                    job_id="test_job_id",
                    application_url="https://example.com/apply",
                    force_refresh=False,
                    progress_callback=track_progress,
                )

        # Should have multiple progress callbacks
        assert len(progress_calls) >= 3
        # Check for expected steps
        steps = [call[0] for call in progress_calls]
        assert "cache_check" in steps
        assert "scrape_form" in steps
        assert "extract_fields" in steps
