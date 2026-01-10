"""
Unit tests for src/services/claude_outreach_service.py

Tests the ClaudeOutreachService for generating per-contact outreach messages
using UnifiedLLM with Claude CLI primary and LangChain fallback.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.claude_outreach_service import (
    ClaudeOutreachService,
    OutreachPackage,
    generate_outreach_with_claude,
    CANDIDATE_NAME,
    CANDIDATE_CALENDLY,
    CANDIDATE_SIGNATURE,
)
from src.common.unified_llm import LLMResult
from src.common.mena_detector import MenaContext


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_contact():
    """Sample contact dictionary."""
    return {
        "name": "Jane Smith",
        "role": "Engineering Manager",
        "contact_type": "hiring_manager",
        "why_relevant": "Directly manages the team this role joins",
    }


@pytest.fixture
def sample_job_context():
    """Sample job context dictionary."""
    return {
        "job_id": "test_job_123",
        "company": "TechCorp",
        "role": "Senior Software Engineer",
        "location": "San Francisco, CA",
        "jd_text": "We need a senior engineer to lead our platform team...",
        "pain_points": [
            "Team scaling challenges",
            "Technical debt in core systems",
        ],
        "company_signals": [
            "Series B funding",
            "Expanding engineering team",
        ],
        "achievements": [
            "Led platform migration serving 10M users",
            "Reduced deployment time by 80%",
        ],
        "persona_statement": "Senior engineering leader with platform expertise",
        "core_strengths": "- Platform engineering\n- Team leadership",
        "candidate_summary": "Experienced engineering leader",
    }


@pytest.fixture
def sample_mena_context():
    """Sample MENA context for non-MENA region."""
    return MenaContext(
        is_mena=False,
        region=None,
    )


@pytest.fixture
def sample_mena_context_saudi():
    """Sample MENA context for Saudi Arabia."""
    return MenaContext(
        is_mena=True,
        region="Saudi Arabia",
        confidence="high",
        use_arabic_greeting=True,
        formality_level="high",
        vision_references=["Vision 2030"],
    )


@pytest.fixture
def mock_llm_success_result():
    """Mock successful LLMResult with parsed JSON."""
    return LLMResult(
        content='{"linkedin_connection": {"message": "Hi Jane, great to connect!"}, "linkedin_inmail": {"subject": "Following up", "body": "Dear Jane..."}, "email": {"subject": "Application", "body": "Dear Jane, I am writing..."}}',
        parsed_json={
            "linkedin_connection": {"message": "Hi Jane, great to connect!"},
            "linkedin_inmail": {"subject": "Following up", "body": "Dear Jane, I recently applied..."},
            "email": {"subject": "Application follow-up", "body": "Dear Jane, I am writing to follow up..."},
        },
        backend="claude_cli",
        model="claude-opus-4-5-20251101",
        tier="high",
        duration_ms=1500,
        success=True,
        cost_usd=0.05,
    )


@pytest.fixture
def mock_llm_failure_result():
    """Mock failed LLMResult."""
    return LLMResult(
        content="",
        backend="claude_cli",
        model="claude-opus-4-5-20251101",
        tier="high",
        duration_ms=100,
        success=False,
        error="Claude CLI timeout",
    )


# =============================================================================
# Test ClaudeOutreachService Initialization
# =============================================================================


class TestClaudeOutreachServiceInit:
    """Tests for ClaudeOutreachService initialization."""

    def test_default_initialization(self):
        """Should initialize with default values."""
        service = ClaudeOutreachService()

        assert service.tier == "high"
        assert service.timeout == 300
        assert service.candidate_name == CANDIDATE_NAME
        assert service.calendly_link == CANDIDATE_CALENDLY

    def test_custom_timeout(self):
        """Should accept custom timeout."""
        service = ClaudeOutreachService(timeout=300)

        assert service.timeout == 300

    def test_custom_candidate_name(self):
        """Should accept custom candidate name."""
        service = ClaudeOutreachService(candidate_name="John Doe")

        assert service.candidate_name == "John Doe"
        assert service.signature == "Best regards,\nJohn Doe"

    def test_custom_calendly_link(self):
        """Should accept custom Calendly link."""
        service = ClaudeOutreachService(calendly_link="calendly.com/custom")

        assert service.calendly_link == "calendly.com/custom"


# =============================================================================
# Test generate_for_contact Method
# =============================================================================


class TestClaudeOutreachServiceGenerateForContact:
    """Tests for generate_for_contact method."""

    @pytest.mark.asyncio
    async def test_successful_generation(
        self, sample_contact, sample_job_context, mock_llm_success_result
    ):
        """Should generate outreach package on success."""
        service = ClaudeOutreachService()

        with patch.object(
            service, "_parse_outreach_result"
        ) as mock_parse, patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            # Setup mocks
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_success_result
            mock_llm_class.return_value = mock_llm_instance

            expected_package = OutreachPackage(
                contact_name="Jane Smith",
                contact_role="Engineering Manager",
                contact_type="hiring_manager",
                linkedin_connection="Hi Jane!",
                linkedin_connection_chars=10,
                linkedin_inmail_subject="Subject",
                linkedin_inmail_body="Body",
                linkedin_inmail_chars=4,
                email_subject="Email Subject",
                email_body="Email body",
                email_words=2,
                mena_context=None,
                generation_cost_usd=0.05,
                generation_time_ms=1500,
                model_used="claude-opus-4-5-20251101",
                generated_at="2024-01-01T00:00:00",
            )
            mock_parse.return_value = expected_package

            result = await service.generate_for_contact(
                contact=sample_contact,
                job_context=sample_job_context,
            )

        assert result == expected_package
        mock_llm_instance.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_high_tier(
        self, sample_contact, sample_job_context, mock_llm_success_result
    ):
        """Should use high tier for outreach generation."""
        service = ClaudeOutreachService()

        with patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_success_result
            mock_llm_class.return_value = mock_llm_instance

            await service.generate_for_contact(
                contact=sample_contact,
                job_context=sample_job_context,
            )

        # Verify UnifiedLLM was created with high tier
        mock_llm_class.assert_called_once()
        call_kwargs = mock_llm_class.call_args[1]
        assert call_kwargs["tier"] == "high"
        assert call_kwargs["step_name"] == "outreach_generation"

    @pytest.mark.asyncio
    async def test_returns_fallback_on_failure(
        self, sample_contact, sample_job_context, mock_llm_failure_result
    ):
        """Should return fallback package when LLM fails."""
        service = ClaudeOutreachService()

        with patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_failure_result
            mock_llm_class.return_value = mock_llm_instance

            result = await service.generate_for_contact(
                contact=sample_contact,
                job_context=sample_job_context,
            )

        assert result.model_used == "fallback"
        assert result.contact_name == "Jane Smith"

    @pytest.mark.asyncio
    async def test_detects_mena_region_when_not_provided(
        self, sample_contact, sample_job_context, mock_llm_success_result
    ):
        """Should detect MENA region if not provided."""
        service = ClaudeOutreachService()
        sample_job_context["location"] = "Riyadh, Saudi Arabia"

        with patch(
            "src.services.claude_outreach_service.detect_mena_region"
        ) as mock_detect, patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            mock_detect.return_value = MenaContext(
                is_mena=True, region="Saudi Arabia"
            )
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_success_result
            mock_llm_class.return_value = mock_llm_instance

            await service.generate_for_contact(
                contact=sample_contact,
                job_context=sample_job_context,
            )

        mock_detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_provided_mena_context(
        self, sample_contact, sample_job_context, mock_llm_success_result, sample_mena_context_saudi
    ):
        """Should use provided MENA context without detecting."""
        service = ClaudeOutreachService()

        with patch(
            "src.services.claude_outreach_service.detect_mena_region"
        ) as mock_detect, patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_success_result
            mock_llm_class.return_value = mock_llm_instance

            await service.generate_for_contact(
                contact=sample_contact,
                job_context=sample_job_context,
                mena_context=sample_mena_context_saudi,
            )

        # Should not call detect_mena_region when context is provided
        mock_detect.assert_not_called()


# =============================================================================
# Test _parse_outreach_result Method
# =============================================================================


class TestClaudeOutreachServiceParseResult:
    """Tests for _parse_outreach_result method."""

    def test_parses_valid_result(self, sample_mena_context):
        """Should parse valid LLMResult correctly."""
        service = ClaudeOutreachService()

        result = LLMResult(
            content="",
            parsed_json={
                "linkedin_connection": {"message": "Hi Jane, great to connect!"},
                "linkedin_inmail": {"subject": "Following up", "body": "Dear Jane..."},
                "email": {"subject": "Application", "body": "Dear Jane, I am writing..."},
            },
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="high",
            duration_ms=1500,
            success=True,
            cost_usd=0.05,
        )

        package = service._parse_outreach_result(
            result=result,
            contact_name="Jane Smith",
            contact_role="Engineering Manager",
            contact_type="hiring_manager",
            mena_context=sample_mena_context,
            duration_ms=1500,
        )

        assert package.contact_name == "Jane Smith"
        assert package.linkedin_connection == "Hi Jane, great to connect!"
        assert package.linkedin_inmail_subject == "Following up"
        assert package.email_subject == "Application"
        assert package.model_used == "claude-opus-4-5-20251101"
        assert package.generation_cost_usd == 0.05

    def test_parses_content_when_no_parsed_json(self, sample_mena_context):
        """Should parse content when parsed_json is None."""
        service = ClaudeOutreachService()

        result = LLMResult(
            content='{"linkedin_connection": {"message": "Hi!"}, "linkedin_inmail": {"subject": "Sub", "body": "Body"}, "email": {"subject": "Email", "body": "Email body"}}',
            parsed_json=None,
            backend="langchain",
            model="gpt-4o",
            tier="high",
            duration_ms=2000,
            success=True,
        )

        package = service._parse_outreach_result(
            result=result,
            contact_name="Jane",
            contact_role="Manager",
            contact_type="peer",
            mena_context=sample_mena_context,
            duration_ms=2000,
        )

        assert package.linkedin_connection == "Hi!"
        assert package.model_used == "gpt-4o"

    def test_returns_fallback_on_parse_error(self, sample_mena_context):
        """Should return fallback package when parsing fails."""
        service = ClaudeOutreachService()

        result = LLMResult(
            content="invalid json {{{",
            parsed_json=None,
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="high",
            duration_ms=1000,
            success=True,
        )

        package = service._parse_outreach_result(
            result=result,
            contact_name="Jane",
            contact_role="Manager",
            contact_type="peer",
            mena_context=sample_mena_context,
            duration_ms=1000,
        )

        assert package.model_used == "fallback"


# =============================================================================
# Test _create_fallback_package Method
# =============================================================================


class TestClaudeOutreachServiceFallbackPackage:
    """Tests for _create_fallback_package method."""

    def test_creates_fallback_with_contact_info(self, sample_mena_context):
        """Should create fallback with correct contact info."""
        service = ClaudeOutreachService()

        package = service._create_fallback_package(
            contact_name="Jane Smith",
            contact_role="Engineering Manager",
            contact_type="hiring_manager",
            mena_context=sample_mena_context,
            error="Test error",
            duration_ms=100,
        )

        assert package.contact_name == "Jane Smith"
        assert package.contact_role == "Engineering Manager"
        assert package.contact_type == "hiring_manager"
        assert package.model_used == "fallback"

    def test_fallback_includes_signature(self, sample_mena_context):
        """Should include signature in fallback messages."""
        service = ClaudeOutreachService()

        package = service._create_fallback_package(
            contact_name="Jane",
            contact_role="Manager",
            contact_type="peer",
            mena_context=sample_mena_context,
            error="Error",
            duration_ms=0,
        )

        assert CANDIDATE_NAME in package.linkedin_connection
        assert CANDIDATE_NAME in package.linkedin_inmail_body


# =============================================================================
# Test generate_batch Method
# =============================================================================


class TestClaudeOutreachServiceGenerateBatch:
    """Tests for generate_batch method."""

    @pytest.mark.asyncio
    async def test_generates_for_multiple_contacts(
        self, sample_job_context, mock_llm_success_result
    ):
        """Should generate outreach for multiple contacts."""
        service = ClaudeOutreachService()
        contacts = [
            {"name": "Jane", "role": "Manager", "contact_type": "hiring_manager"},
            {"name": "Bob", "role": "Engineer", "contact_type": "peer"},
        ]

        with patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_success_result
            mock_llm_class.return_value = mock_llm_instance

            results = await service.generate_batch(
                contacts=contacts,
                job_context=sample_job_context,
                max_concurrent=2,
            )

        assert len(results) == 2
        assert all(isinstance(r, OutreachPackage) for r in results)

    @pytest.mark.asyncio
    async def test_handles_exceptions_in_batch(
        self, sample_job_context, mock_llm_success_result
    ):
        """Should handle exceptions and return fallback for failed items."""
        service = ClaudeOutreachService()
        contacts = [
            {"name": "Jane", "role": "Manager", "contact_type": "hiring_manager"},
            {"name": "Bob", "role": "Engineer", "contact_type": "peer"},
        ]

        call_count = 0

        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")
            return OutreachPackage(
                contact_name="Bob",
                contact_role="Engineer",
                contact_type="peer",
                linkedin_connection="Hi!",
                linkedin_connection_chars=3,
                linkedin_inmail_subject="Sub",
                linkedin_inmail_body="Body",
                linkedin_inmail_chars=4,
                email_subject="Email",
                email_body="Email body",
                email_words=2,
                mena_context=None,
                generation_cost_usd=0.05,
                generation_time_ms=1000,
                model_used="claude-opus-4-5-20251101",
                generated_at="2024-01-01",
            )

        with patch.object(service, "generate_for_contact", side_effect=mock_generate):
            results = await service.generate_batch(
                contacts=contacts,
                job_context=sample_job_context,
            )

        assert len(results) == 2
        # First result should be fallback due to exception
        assert results[0].model_used == "fallback"
        # Second result should be successful
        assert results[1].model_used == "claude-opus-4-5-20251101"


# =============================================================================
# Test OutreachPackage
# =============================================================================


class TestOutreachPackage:
    """Tests for OutreachPackage dataclass."""

    def test_to_dict(self, sample_mena_context):
        """Should convert to dictionary correctly."""
        package = OutreachPackage(
            contact_name="Jane",
            contact_role="Manager",
            contact_type="hiring_manager",
            linkedin_connection="Hi Jane!",
            linkedin_connection_chars=10,
            linkedin_inmail_subject="Subject",
            linkedin_inmail_body="Body",
            linkedin_inmail_chars=4,
            email_subject="Email Subject",
            email_body="Email body",
            email_words=2,
            mena_context=sample_mena_context,
            generation_cost_usd=0.05,
            generation_time_ms=1500,
            model_used="claude-opus-4-5-20251101",
            generated_at="2024-01-01T00:00:00",
        )

        d = package.to_dict()

        assert d["contact_name"] == "Jane"
        assert d["linkedin_connection"]["message"] == "Hi Jane!"
        assert d["linkedin_connection"]["char_count"] == 10
        assert d["metadata"]["model_used"] == "claude-opus-4-5-20251101"
        assert d["metadata"]["is_mena"] is False


# =============================================================================
# Test Convenience Function
# =============================================================================


class TestGenerateOutreachWithClaude:
    """Tests for generate_outreach_with_claude convenience function."""

    @pytest.mark.asyncio
    async def test_creates_service_and_calls_generate(
        self, sample_contact, sample_job_context, mock_llm_success_result
    ):
        """Should create service and call generate_for_contact."""
        with patch(
            "src.services.claude_outreach_service.UnifiedLLM"
        ) as mock_llm_class:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.invoke.return_value = mock_llm_success_result
            mock_llm_class.return_value = mock_llm_instance

            result = await generate_outreach_with_claude(
                contact=sample_contact,
                job_context=sample_job_context,
                timeout=120,
            )

        assert isinstance(result, OutreachPackage)

    @pytest.mark.asyncio
    async def test_uses_provided_timeout(self, sample_contact, sample_job_context):
        """Should use provided timeout."""
        with patch.object(
            ClaudeOutreachService, "__init__", return_value=None
        ) as mock_init, patch.object(
            ClaudeOutreachService, "generate_for_contact", new_callable=AsyncMock
        ) as mock_generate:
            mock_generate.return_value = MagicMock()

            await generate_outreach_with_claude(
                contact=sample_contact,
                job_context=sample_job_context,
                timeout=300,
            )

        mock_init.assert_called_once_with(timeout=300)
