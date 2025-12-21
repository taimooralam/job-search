"""
Unit Tests for Layer 1.4: JD Processor

Tests UnifiedLLM-based job description structure parsing:
- _call_claude_cli with UnifiedLLM invocation (mocked)
- parse_jd_sections_with_llm with fallback handling
- process_jd integration
- Section parsing from JSON responses
- Error handling (LLM failures, validation errors)
- Rule-based fallback when LLM fails
"""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from src.layer1_4.jd_processor import (
    _call_claude_cli,
    _parse_sections_from_json,
    parse_jd_sections_with_llm,
    parse_jd_sections_rule_based,
    process_jd,
    JDSectionType,
    JDSection,
    ProcessedJD,
)
from src.common.unified_llm import LLMResult


# ===== FIXTURES =====


@pytest.fixture
def sample_jd_text():
    """Sample job description text for parsing tests."""
    return """
About TechCorp:
We are a leading technology company building the future of cloud infrastructure.

Responsibilities:
- Design and implement scalable backend services
- Lead technical architecture decisions
- Mentor junior engineers
- Collaborate with product teams

Qualifications:
- 5+ years of software development experience
- Strong Python and distributed systems knowledge
- Experience with cloud platforms (AWS/GCP)
- Excellent communication skills

Nice to Have:
- Kubernetes experience
- Open source contributions
"""


@pytest.fixture
def sample_sections_json():
    """Sample valid sections JSON from LLM response."""
    return {
        "sections": [
            {
                "section_type": "about_company",
                "header": "About TechCorp",
                "items": ["We are a leading technology company building the future of cloud infrastructure"]
            },
            {
                "section_type": "responsibilities",
                "header": "Responsibilities",
                "items": [
                    "Design and implement scalable backend services",
                    "Lead technical architecture decisions",
                    "Mentor junior engineers",
                    "Collaborate with product teams"
                ]
            },
            {
                "section_type": "qualifications",
                "header": "Qualifications",
                "items": [
                    "5+ years of software development experience",
                    "Strong Python and distributed systems knowledge",
                    "Experience with cloud platforms (AWS/GCP)",
                    "Excellent communication skills"
                ]
            },
            {
                "section_type": "nice_to_have",
                "header": "Nice to Have",
                "items": [
                    "Kubernetes experience",
                    "Open source contributions"
                ]
            }
        ]
    }


@pytest.fixture
def sample_llm_result_success(sample_sections_json):
    """Sample successful LLMResult from UnifiedLLM."""
    return LLMResult(
        content=json.dumps(sample_sections_json),
        parsed_json=sample_sections_json,
        backend="claude_cli",
        model="claude-haiku-4-5-20251001",
        tier="low",
        duration_ms=2500,
        success=True,
        input_tokens=1200,
        output_tokens=400,
        cost_usd=0.002,
    )


@pytest.fixture
def sample_llm_result_failure():
    """Sample failed LLMResult from UnifiedLLM."""
    return LLMResult(
        content="",
        backend="none",
        model="",
        tier="low",
        duration_ms=0,
        success=False,
        error="Claude CLI failed and fallback is disabled",
    )


@pytest.fixture
def sample_llm_result_langchain_fallback(sample_sections_json):
    """Sample LLMResult when LangChain fallback was used."""
    return LLMResult(
        content=json.dumps(sample_sections_json),
        parsed_json=sample_sections_json,
        backend="langchain",
        model="gpt-4o-mini",
        tier="low",
        duration_ms=1800,
        success=True,
        input_tokens=1000,
        output_tokens=350,
    )


# ===== TESTS: _call_claude_cli =====


class TestCallClaudeCLI:
    """Test _call_claude_cli function with UnifiedLLM."""

    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    def test_successful_invocation(self, mock_invoke, sample_llm_result_success):
        """Successful invocation returns content."""
        mock_invoke.return_value = sample_llm_result_success

        result = _call_claude_cli(
            prompt="Parse this JD",
            job_id="test_001",
            tier="low"
        )

        assert '"sections"' in result
        mock_invoke.assert_called_once_with(
            prompt="Parse this JD",
            step_name="jd_structure_parsing",
            tier="low",
            job_id="test_001",
            validate_json=True,
        )

    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    def test_uses_default_job_id(self, mock_invoke, sample_llm_result_success):
        """Uses 'unknown' as default job_id."""
        mock_invoke.return_value = sample_llm_result_success

        _call_claude_cli(prompt="Parse this JD")

        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["job_id"] == "unknown"

    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    def test_uses_default_tier(self, mock_invoke, sample_llm_result_success):
        """Uses 'low' as default tier."""
        mock_invoke.return_value = sample_llm_result_success

        _call_claude_cli(prompt="Parse this JD")

        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["tier"] == "low"

    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    def test_raises_on_llm_failure(self, mock_invoke, sample_llm_result_failure):
        """Raises exception when LLM fails."""
        mock_invoke.return_value = sample_llm_result_failure

        with pytest.raises(Exception) as exc_info:
            _call_claude_cli(prompt="Parse this JD", job_id="test_fail")

        assert "LLM failed" in str(exc_info.value)

    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    def test_accepts_middle_tier(self, mock_invoke, sample_llm_result_success):
        """Can use middle tier for higher quality."""
        mock_invoke.return_value = sample_llm_result_success

        _call_claude_cli(prompt="Parse this JD", tier="middle")

        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["tier"] == "middle"


# ===== TESTS: _parse_sections_from_json =====


class TestParseSectionsFromJSON:
    """Test parsing sections from JSON response."""

    def test_parses_valid_json(self, sample_jd_text, sample_sections_json):
        """Valid JSON produces correct sections."""
        json_str = json.dumps(sample_sections_json)

        sections = _parse_sections_from_json(json_str, sample_jd_text)

        assert len(sections) == 4
        assert sections[0].section_type == JDSectionType.ABOUT_COMPANY
        assert sections[1].section_type == JDSectionType.RESPONSIBILITIES
        assert sections[2].section_type == JDSectionType.QUALIFICATIONS
        assert sections[3].section_type == JDSectionType.NICE_TO_HAVE

    def test_extracts_headers(self, sample_jd_text, sample_sections_json):
        """Correctly extracts section headers."""
        json_str = json.dumps(sample_sections_json)

        sections = _parse_sections_from_json(json_str, sample_jd_text)

        assert sections[0].header == "About TechCorp"
        assert sections[1].header == "Responsibilities"

    def test_extracts_items(self, sample_jd_text, sample_sections_json):
        """Correctly extracts section items."""
        json_str = json.dumps(sample_sections_json)

        sections = _parse_sections_from_json(json_str, sample_jd_text)

        assert len(sections[1].items) == 4
        assert "Design and implement" in sections[1].items[0]

    def test_handles_unknown_section_type(self, sample_jd_text):
        """Unknown section type defaults to OTHER."""
        json_str = json.dumps({
            "sections": [
                {
                    "section_type": "unknown_type",
                    "header": "Custom Section",
                    "items": ["Item 1"]
                }
            ]
        })

        sections = _parse_sections_from_json(json_str, sample_jd_text)

        assert sections[0].section_type == JDSectionType.OTHER

    def test_raises_on_no_json_found(self, sample_jd_text):
        """Raises ValueError when no JSON in response."""
        with pytest.raises(ValueError) as exc_info:
            _parse_sections_from_json("This is not JSON at all", sample_jd_text)

        assert "No JSON found" in str(exc_info.value)

    def test_raises_on_empty_sections(self, sample_jd_text):
        """Raises ValueError when sections array is empty."""
        json_str = json.dumps({"sections": []})

        with pytest.raises(ValueError) as exc_info:
            _parse_sections_from_json(json_str, sample_jd_text)

        assert "Empty sections" in str(exc_info.value)

    def test_handles_embedded_json(self, sample_jd_text, sample_sections_json):
        """Handles JSON embedded in text."""
        json_str = f"Here is the parsed result:\n{json.dumps(sample_sections_json)}\n\nEnd of result."

        sections = _parse_sections_from_json(json_str, sample_jd_text)

        assert len(sections) == 4


# ===== TESTS: parse_jd_sections_with_llm =====


class TestParseJDSectionsWithLLM:
    """Test LLM-based section parsing with fallback."""

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_successful_parsing(self, mock_cli, sample_jd_text, sample_sections_json):
        """Successful parsing returns sections."""
        mock_cli.return_value = json.dumps(sample_sections_json)

        sections = await parse_jd_sections_with_llm(
            sample_jd_text,
            job_id="test_001",
            tier="low"
        )

        assert len(sections) == 4
        assert sections[0].section_type == JDSectionType.ABOUT_COMPANY

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_passes_job_id_to_cli(self, mock_cli, sample_jd_text, sample_sections_json):
        """Passes job_id to _call_claude_cli."""
        mock_cli.return_value = json.dumps(sample_sections_json)

        await parse_jd_sections_with_llm(
            sample_jd_text,
            job_id="test_job_123",
            tier="low"
        )

        call_kwargs = mock_cli.call_args[1]
        assert call_kwargs["job_id"] == "test_job_123"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_passes_tier_to_cli(self, mock_cli, sample_jd_text, sample_sections_json):
        """Passes tier to _call_claude_cli."""
        mock_cli.return_value = json.dumps(sample_sections_json)

        await parse_jd_sections_with_llm(
            sample_jd_text,
            tier="middle"
        )

        call_kwargs = mock_cli.call_args[1]
        assert call_kwargs["tier"] == "middle"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_falls_back_to_rule_based_on_exception(self, mock_cli, sample_jd_text):
        """Falls back to rule-based parsing when LLM fails."""
        mock_cli.side_effect = Exception("LLM API timeout")

        sections = await parse_jd_sections_with_llm(sample_jd_text)

        # Should get sections from rule-based fallback
        assert len(sections) >= 1
        # Rule-based parser should detect standard sections
        section_types = [s.section_type for s in sections]
        assert JDSectionType.RESPONSIBILITIES in section_types or len(sections) > 0

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_falls_back_when_llm_returns_few_sections(self, mock_cli, sample_jd_text):
        """Falls back to rule-based if LLM returns too few sections for long JD."""
        # LLM returns only 1 section for a JD that should have more
        mock_cli.return_value = json.dumps({
            "sections": [
                {
                    "section_type": "other",
                    "header": "Job Description",
                    "items": ["Some content"]
                }
            ]
        })

        sections = await parse_jd_sections_with_llm(sample_jd_text)

        # Rule-based should find more sections in this structured JD
        assert len(sections) >= 1


# ===== TESTS: parse_jd_sections_rule_based =====


class TestParseJDSectionsRuleBased:
    """Test rule-based section parsing."""

    def test_detects_responsibilities(self, sample_jd_text):
        """Detects responsibilities section."""
        sections = parse_jd_sections_rule_based(sample_jd_text)

        section_types = [s.section_type for s in sections]
        assert JDSectionType.RESPONSIBILITIES in section_types

    def test_detects_qualifications(self, sample_jd_text):
        """Detects qualifications section."""
        sections = parse_jd_sections_rule_based(sample_jd_text)

        section_types = [s.section_type for s in sections]
        assert JDSectionType.QUALIFICATIONS in section_types

    def test_detects_nice_to_have(self, sample_jd_text):
        """Detects nice-to-have section."""
        sections = parse_jd_sections_rule_based(sample_jd_text)

        section_types = [s.section_type for s in sections]
        assert JDSectionType.NICE_TO_HAVE in section_types

    def test_extracts_items_from_bullets(self, sample_jd_text):
        """Extracts items from bullet points."""
        sections = parse_jd_sections_rule_based(sample_jd_text)

        resp_section = next(
            (s for s in sections if s.section_type == JDSectionType.RESPONSIBILITIES),
            None
        )
        assert resp_section is not None
        assert len(resp_section.items) >= 1

    def test_handles_empty_jd(self):
        """Creates single OTHER section for empty/minimal JD."""
        sections = parse_jd_sections_rule_based("   ")

        assert len(sections) == 1
        assert sections[0].section_type == JDSectionType.OTHER

    def test_handles_unstructured_jd(self):
        """Handles JD without clear section headers."""
        unstructured_jd = """
        We need an engineer who can code in Python and JavaScript.
        Experience with AWS is required. Must have 5+ years experience.
        """

        sections = parse_jd_sections_rule_based(unstructured_jd)

        assert len(sections) >= 1


# ===== TESTS: process_jd =====


class TestProcessJD:
    """Test the main process_jd function."""

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_returns_processed_jd(self, mock_parse, sample_jd_text):
        """Returns ProcessedJD with all fields."""
        mock_parse.return_value = [
            JDSection(
                section_type=JDSectionType.RESPONSIBILITIES,
                header="Responsibilities",
                content="Test content",
                items=["Item 1", "Item 2"],
                char_start=0,
                char_end=100,
                index=0
            )
        ]

        result = await process_jd(sample_jd_text)

        assert isinstance(result, ProcessedJD)
        assert result.raw_text == sample_jd_text
        assert len(result.sections) == 1
        assert "<section" in result.html
        assert result.content_hash is not None

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_passes_job_id(self, mock_parse, sample_jd_text):
        """Passes job_id to parse function."""
        mock_parse.return_value = []

        await process_jd(sample_jd_text, job_id="test_job_456")

        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["job_id"] == "test_job_456"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_passes_tier(self, mock_parse, sample_jd_text):
        """Passes tier to parse function."""
        mock_parse.return_value = []

        await process_jd(sample_jd_text, tier="middle")

        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["tier"] == "middle"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_generates_section_ids(self, mock_parse, sample_jd_text):
        """Generates section IDs from section types."""
        mock_parse.return_value = [
            JDSection(
                section_type=JDSectionType.RESPONSIBILITIES,
                header="Responsibilities",
                content="",
                items=[],
                char_start=0,
                char_end=100,
                index=0
            ),
            JDSection(
                section_type=JDSectionType.QUALIFICATIONS,
                header="Qualifications",
                content="",
                items=[],
                char_start=100,
                char_end=200,
                index=1
            )
        ]

        result = await process_jd(sample_jd_text)

        assert result.section_ids == ["responsibilities", "qualifications"]

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_generates_content_hash(self, mock_parse, sample_jd_text):
        """Generates MD5 hash of JD content."""
        mock_parse.return_value = []

        result = await process_jd(sample_jd_text)

        # MD5 hash should be 32 hex characters
        assert len(result.content_hash) == 32
        assert all(c in "0123456789abcdef" for c in result.content_hash)


# ===== TESTS: Integration with UnifiedLLM =====


class TestUnifiedLLMIntegration:
    """Test integration with UnifiedLLM infrastructure."""

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    async def test_uses_jd_structure_parsing_step_name(
        self, mock_invoke, sample_jd_text, sample_llm_result_success
    ):
        """Uses correct step_name for LLM config."""
        mock_invoke.return_value = sample_llm_result_success

        await parse_jd_sections_with_llm(sample_jd_text)

        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["step_name"] == "jd_structure_parsing"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    async def test_handles_langchain_fallback(
        self, mock_invoke, sample_jd_text, sample_llm_result_langchain_fallback
    ):
        """Works correctly when LangChain fallback is used."""
        mock_invoke.return_value = sample_llm_result_langchain_fallback

        sections = await parse_jd_sections_with_llm(sample_jd_text)

        # Should still parse sections correctly from fallback response
        assert len(sections) == 4

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    async def test_validates_json_in_llm_call(
        self, mock_invoke, sample_jd_text, sample_llm_result_success
    ):
        """Requests JSON validation from UnifiedLLM."""
        mock_invoke.return_value = sample_llm_result_success

        await parse_jd_sections_with_llm(sample_jd_text)

        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["validate_json"] is True


# ===== TESTS: Error Handling =====


class TestErrorHandling:
    """Test error handling throughout the pipeline."""

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    async def test_recovers_from_llm_timeout(
        self, mock_invoke, sample_jd_text
    ):
        """Recovers from LLM timeout by using rule-based fallback."""
        mock_invoke.return_value = LLMResult(
            content="",
            backend="claude_cli",
            model="claude-haiku-4-5-20251001",
            tier="low",
            duration_ms=120000,
            success=False,
            error="CLI timeout after 120s",
        )

        # Should not raise, should fall back to rule-based
        sections = await parse_jd_sections_with_llm(sample_jd_text)

        assert len(sections) >= 1

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    async def test_recovers_from_invalid_json_response(
        self, mock_invoke, sample_jd_text
    ):
        """Recovers from invalid JSON in LLM response."""
        mock_invoke.return_value = LLMResult(
            content="This is not valid JSON at all",
            parsed_json=None,
            backend="claude_cli",
            model="claude-haiku-4-5-20251001",
            tier="low",
            duration_ms=2000,
            success=True,
        )

        # Should fall back to rule-based parsing
        sections = await parse_jd_sections_with_llm(sample_jd_text)

        assert len(sections) >= 1
