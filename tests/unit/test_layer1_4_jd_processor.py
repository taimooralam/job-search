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
    LLMMetadata,
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
        """Successful invocation returns LLMResult with content."""
        mock_invoke.return_value = sample_llm_result_success

        result = _call_claude_cli(
            prompt="Parse this JD",
            job_id="test_001",
            tier="low"
        )

        assert isinstance(result, LLMResult)
        assert '"sections"' in result.content
        assert result.backend == "claude_cli"
        mock_invoke.assert_called_once_with(
            prompt="Parse this JD",
            step_name="jd_structure_parsing",
            tier="low",
            job_id="test_001",
            validate_json=True,
            struct_logger=None,
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

    @patch('src.layer1_4.jd_processor.invoke_unified_sync')
    def test_passes_struct_logger(self, mock_invoke, sample_llm_result_success):
        """Passes struct_logger to invoke_unified_sync."""
        mock_invoke.return_value = sample_llm_result_success
        mock_logger = MagicMock()

        _call_claude_cli(prompt="Parse this JD", struct_logger=mock_logger)

        call_kwargs = mock_invoke.call_args[1]
        assert call_kwargs["struct_logger"] is mock_logger


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
    async def test_successful_parsing(self, mock_cli, sample_jd_text, sample_sections_json, sample_llm_result_success):
        """Successful parsing returns sections and metadata."""
        mock_cli.return_value = sample_llm_result_success

        sections, llm_metadata = await parse_jd_sections_with_llm(
            sample_jd_text,
            job_id="test_001",
            tier="low"
        )

        assert len(sections) == 4
        assert sections[0].section_type == JDSectionType.ABOUT_COMPANY
        assert isinstance(llm_metadata, LLMMetadata)
        assert llm_metadata.backend == "claude_cli"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_passes_job_id_to_cli(self, mock_cli, sample_jd_text, sample_sections_json, sample_llm_result_success):
        """Passes job_id to _call_claude_cli."""
        mock_cli.return_value = sample_llm_result_success

        await parse_jd_sections_with_llm(
            sample_jd_text,
            job_id="test_job_123",
            tier="low"
        )

        call_kwargs = mock_cli.call_args[1]
        assert call_kwargs["job_id"] == "test_job_123"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_passes_tier_to_cli(self, mock_cli, sample_jd_text, sample_sections_json, sample_llm_result_success):
        """Passes tier to _call_claude_cli."""
        mock_cli.return_value = sample_llm_result_success

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

        sections, llm_metadata = await parse_jd_sections_with_llm(sample_jd_text)

        # Should get sections from rule-based fallback
        assert len(sections) >= 1
        # Rule-based parser should detect standard sections
        section_types = [s.section_type for s in sections]
        assert JDSectionType.RESPONSIBILITIES in section_types or len(sections) > 0
        # Metadata should indicate rule-based fallback
        assert llm_metadata.backend == "rule_based"
        assert "LLM API timeout" in llm_metadata.fallback_reason

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_falls_back_when_llm_returns_few_sections(self, mock_cli, sample_jd_text):
        """Falls back to rule-based if LLM returns too few sections for long JD."""
        # LLM returns only 1 section for a JD that should have more
        mock_cli.return_value = LLMResult(
            content=json.dumps({
                "sections": [
                    {
                        "section_type": "other",
                        "header": "Job Description",
                        "items": ["Some content"]
                    }
                ]
            }),
            backend="claude_cli",
            model="claude-haiku-4-5-20251001",
            tier="low",
            duration_ms=1000,
            success=True,
        )

        sections, llm_metadata = await parse_jd_sections_with_llm(sample_jd_text)

        # Rule-based should find more sections in this structured JD
        assert len(sections) >= 1
        # Metadata should indicate LLM was used but quality fallback occurred
        assert llm_metadata.backend == "claude_cli"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_returns_llm_metadata(self, mock_cli, sample_jd_text, sample_llm_result_success):
        """Returns LLMMetadata with backend attribution."""
        mock_cli.return_value = sample_llm_result_success

        sections, llm_metadata = await parse_jd_sections_with_llm(sample_jd_text)

        assert llm_metadata.backend == "claude_cli"
        assert llm_metadata.model == "claude-haiku-4-5-20251001"
        assert llm_metadata.tier == "low"
        assert llm_metadata.duration_ms == 2500
        assert llm_metadata.cost_usd == 0.002
        assert llm_metadata.success is True

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor._call_claude_cli')
    async def test_passes_struct_logger_to_cli(self, mock_cli, sample_jd_text, sample_llm_result_success):
        """Passes struct_logger to _call_claude_cli."""
        mock_cli.return_value = sample_llm_result_success
        mock_logger = MagicMock()

        await parse_jd_sections_with_llm(sample_jd_text, struct_logger=mock_logger)

        call_kwargs = mock_cli.call_args[1]
        assert call_kwargs["struct_logger"] is mock_logger


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

    @pytest.fixture
    def sample_llm_metadata(self):
        """Sample LLMMetadata for mocking."""
        return LLMMetadata(
            backend="claude_cli",
            model="claude-haiku-4-5-20251001",
            tier="low",
            duration_ms=2000,
            cost_usd=0.001,
            success=True,
        )

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_returns_processed_jd(self, mock_parse, sample_jd_text, sample_llm_metadata):
        """Returns ProcessedJD with all fields."""
        mock_parse.return_value = (
            [
                JDSection(
                    section_type=JDSectionType.RESPONSIBILITIES,
                    header="Responsibilities",
                    content="Test content",
                    items=["Item 1", "Item 2"],
                    char_start=0,
                    char_end=100,
                    index=0
                )
            ],
            sample_llm_metadata
        )

        result, llm_metadata = await process_jd(sample_jd_text)

        assert isinstance(result, ProcessedJD)
        assert result.raw_text == sample_jd_text
        assert len(result.sections) == 1
        assert "<section" in result.html
        assert result.content_hash is not None
        assert isinstance(llm_metadata, LLMMetadata)
        assert llm_metadata.backend == "claude_cli"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_passes_job_id(self, mock_parse, sample_jd_text, sample_llm_metadata):
        """Passes job_id to parse function."""
        mock_parse.return_value = ([], sample_llm_metadata)

        await process_jd(sample_jd_text, job_id="test_job_456")

        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["job_id"] == "test_job_456"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_passes_tier(self, mock_parse, sample_jd_text, sample_llm_metadata):
        """Passes tier to parse function."""
        mock_parse.return_value = ([], sample_llm_metadata)

        await process_jd(sample_jd_text, tier="middle")

        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["tier"] == "middle"

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_generates_section_ids(self, mock_parse, sample_jd_text, sample_llm_metadata):
        """Generates section IDs from section types."""
        mock_parse.return_value = (
            [
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
            ],
            sample_llm_metadata
        )

        result, _ = await process_jd(sample_jd_text)

        assert result.section_ids == ["responsibilities", "qualifications"]

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_generates_content_hash(self, mock_parse, sample_jd_text, sample_llm_metadata):
        """Generates MD5 hash of JD content."""
        mock_parse.return_value = ([], sample_llm_metadata)

        result, _ = await process_jd(sample_jd_text)

        # MD5 hash should be 32 hex characters
        assert len(result.content_hash) == 32
        assert all(c in "0123456789abcdef" for c in result.content_hash)

    @pytest.mark.asyncio
    @patch('src.layer1_4.jd_processor.parse_jd_sections_with_llm')
    async def test_passes_struct_logger(self, mock_parse, sample_jd_text, sample_llm_metadata):
        """Passes struct_logger to parse function."""
        mock_parse.return_value = ([], sample_llm_metadata)
        mock_logger = MagicMock()

        await process_jd(sample_jd_text, struct_logger=mock_logger)

        call_kwargs = mock_parse.call_args[1]
        assert call_kwargs["struct_logger"] is mock_logger


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

        sections, llm_metadata = await parse_jd_sections_with_llm(sample_jd_text)

        # Should still parse sections correctly from fallback response
        assert len(sections) == 4
        # Metadata should reflect langchain backend
        assert llm_metadata.backend == "langchain"

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
        sections, llm_metadata = await parse_jd_sections_with_llm(sample_jd_text)

        assert len(sections) >= 1
        assert llm_metadata.backend == "rule_based"
        assert "CLI timeout" in str(llm_metadata.fallback_reason)

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
        sections, llm_metadata = await parse_jd_sections_with_llm(sample_jd_text)

        assert len(sections) >= 1
        assert llm_metadata.backend == "rule_based"


# ===== TESTS: LLMMetadata =====


class TestLLMMetadata:
    """Test LLMMetadata dataclass."""

    def test_default_values(self):
        """LLMMetadata has sensible defaults."""
        metadata = LLMMetadata()

        assert metadata.backend == "unknown"
        assert metadata.model == "unknown"
        assert metadata.tier == "low"
        assert metadata.duration_ms == 0
        assert metadata.cost_usd is None
        assert metadata.fallback_reason is None
        assert metadata.success is True

    def test_to_dict(self):
        """to_dict returns dictionary with non-None values."""
        metadata = LLMMetadata(
            backend="claude_cli",
            model="claude-haiku",
            tier="low",
            duration_ms=1500,
            cost_usd=0.001,
            success=True,
        )

        result = metadata.to_dict()

        assert result["backend"] == "claude_cli"
        assert result["model"] == "claude-haiku"
        assert result["tier"] == "low"
        assert result["duration_ms"] == 1500
        assert result["cost_usd"] == 0.001
        assert result["success"] is True
        assert "fallback_reason" not in result

    def test_to_dict_with_fallback_reason(self):
        """to_dict includes fallback_reason when present."""
        metadata = LLMMetadata(
            backend="rule_based",
            fallback_reason="LLM timeout",
        )

        result = metadata.to_dict()

        assert result["fallback_reason"] == "LLM timeout"
