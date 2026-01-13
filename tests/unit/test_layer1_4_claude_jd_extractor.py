"""
Unit Tests for Layer 1.4: Claude JD Extractor

Tests UnifiedLLM-based job description extraction with fallback support:
- ExtractionResult dataclass validation
- UnifiedLLM invocation (mocked)
- JSON parsing from LLM output
- Pydantic schema validation
- Batch extraction with concurrency
- Log callback functionality
- Error handling (LLM failures, validation errors)
"""

import json
import asyncio
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from src.layer1_4.claude_jd_extractor import (
    ClaudeJDExtractor,
    ExtractionResult,
    extract_jd_with_claude,
)
from src.common.unified_llm import LLMResult


# ===== FIXTURES =====

@pytest.fixture
def sample_job_data():
    """Sample job data for extraction tests."""
    return {
        "job_id": "test_claude_001",
        "title": "Senior Engineering Manager",
        "company": "AI Startup Inc",
        "job_description": """
        Senior Engineering Manager - AI Platform

        We're looking for a Senior Engineering Manager to lead our AI platform team.

        Responsibilities:
        - Lead a team of 8-10 ML engineers
        - Drive technical architecture decisions for AI infrastructure
        - Partner with product on roadmap prioritization
        - Establish engineering best practices and processes

        Requirements:
        - 8+ years software engineering experience
        - 3+ years managing engineering teams
        - Experience with ML systems and infrastructure
        - Strong background in Python, TensorFlow/PyTorch
        """
    }


@pytest.fixture
def sample_extracted_jd():
    """Sample valid extracted JD matching ExtractedJD schema."""
    return {
        "title": "Senior Engineering Manager",
        "company": "AI Startup Inc",
        "location": "Remote",
        "remote_policy": "fully_remote",
        "role_category": "engineering_manager",
        "seniority_level": "senior",
        "competency_weights": {
            "delivery": 25,
            "process": 20,
            "architecture": 25,
            "leadership": 30
        },
        "responsibilities": [
            "Lead a team of 8-10 ML engineers",
            "Drive technical architecture decisions",
            "Partner with product on roadmap",
            "Establish engineering best practices"
        ],
        "qualifications": [
            "8+ years software engineering experience",
            "3+ years managing engineering teams",
            "Experience with ML systems"
        ],
        "nice_to_haves": ["Previous AI startup experience"],
        "technical_skills": ["Python", "TensorFlow", "PyTorch", "ML Infrastructure"],
        "soft_skills": ["Leadership", "Communication", "Strategic Thinking"],
        "implied_pain_points": [
            "Team needs experienced technical leadership",
            "AI infrastructure needs scaling"
        ],
        "success_metrics": [
            "Team velocity increases by 30%",
            "ML platform uptime above 99.9%"
        ],
        "top_keywords": [
            "Engineering Manager", "AI", "ML", "Python", "TensorFlow",
            "PyTorch", "Infrastructure", "Leadership", "Team Management",
            "Technical Architecture", "Platform", "Remote", "Senior",
            "ML Engineers", "Best Practices"
        ],
        "industry_background": "AI/ML",
        "years_experience_required": 8,
        "education_requirements": None
    }


@pytest.fixture
def sample_cli_output(sample_extracted_jd):
    """Sample Claude CLI JSON output (legacy format, for _parse_cli_output tests)."""
    return json.dumps({
        "result": json.dumps(sample_extracted_jd),
        "model": "claude-opus-4-5-20251101",
        "cost": {
            "input_tokens": 1500,
            "output_tokens": 800,
            "total_cost_usd": 0.05
        },
        "duration_ms": 5200
    })


@pytest.fixture
def sample_llm_result_success(sample_extracted_jd):
    """Sample successful LLMResult from UnifiedLLM."""
    return LLMResult(
        content=json.dumps(sample_extracted_jd),
        parsed_json=sample_extracted_jd,
        backend="claude_cli",
        model="claude-opus-4-5-20251101",
        tier="middle",
        duration_ms=5200,
        success=True,
        input_tokens=1500,
        output_tokens=800,
        cost_usd=0.05,
    )


@pytest.fixture
def sample_llm_result_failure():
    """Sample failed LLMResult from UnifiedLLM."""
    return LLMResult(
        content="",
        backend="none",
        model="",
        tier="middle",
        duration_ms=0,
        success=False,
        error="Claude CLI failed and fallback is disabled",
    )


# ===== TESTS: ExtractionResult Dataclass =====

class TestExtractionResult:
    """Test ExtractionResult dataclass functionality."""

    def test_successful_extraction_result(self, sample_extracted_jd):
        """Successful extraction creates valid result."""
        result = ExtractionResult(
            job_id="test_001",
            success=True,
            extracted_jd=sample_extracted_jd,
            error=None,
            model="claude-opus-4-5-20251101",
            duration_ms=5000,
            extracted_at="2024-01-01T00:00:00"
        )

        assert result.success is True
        assert result.extracted_jd == sample_extracted_jd
        assert result.error is None
        assert result.model == "claude-opus-4-5-20251101"

    def test_failed_extraction_result(self):
        """Failed extraction creates result with error."""
        result = ExtractionResult(
            job_id="test_002",
            success=False,
            extracted_jd=None,
            error="CLI timeout after 120s",
            model="claude-opus-4-5-20251101",
            duration_ms=120000,
            extracted_at="2024-01-01T00:00:00"
        )

        assert result.success is False
        assert result.extracted_jd is None
        assert "timeout" in result.error.lower()

    def test_to_dict_serialization(self, sample_extracted_jd):
        """to_dict() creates JSON-serializable dictionary."""
        result = ExtractionResult(
            job_id="test_003",
            success=True,
            extracted_jd=sample_extracted_jd,
            error=None,
            model="claude-opus-4-5-20251101",
            duration_ms=3000,
            extracted_at="2024-01-01T00:00:00"
        )

        result_dict = result.to_dict()
        # Should be JSON serializable
        json_str = json.dumps(result_dict)
        assert "test_003" in json_str
        assert "claude-opus" in json_str


# ===== TESTS: CLI Output Parsing =====

class TestCLIOutputParsing:
    """Test parsing of Claude CLI output."""

    def test_parses_valid_cli_output(self, sample_cli_output, sample_extracted_jd):
        """Valid CLI JSON output is parsed correctly."""
        extractor = ClaudeJDExtractor()
        parsed = extractor._parse_cli_output(sample_cli_output)

        assert parsed["role_category"] == "engineering_manager"
        assert parsed["competency_weights"]["leadership"] == 30
        assert len(parsed["top_keywords"]) == 15

    def test_handles_invalid_cli_json(self):
        """Invalid JSON raises ValueError."""
        extractor = ClaudeJDExtractor()

        with pytest.raises(ValueError) as exc_info:
            extractor._parse_cli_output("not valid json at all")

        assert "Failed to parse CLI output" in str(exc_info.value)

    def test_handles_missing_result_field(self):
        """Missing 'result' field raises ValueError."""
        extractor = ClaudeJDExtractor()
        cli_output = json.dumps({"model": "claude", "cost": {}})

        with pytest.raises(ValueError) as exc_info:
            extractor._parse_cli_output(cli_output)

        assert "result" in str(exc_info.value)

    def test_handles_invalid_result_json(self):
        """Invalid JSON in 'result' field raises ValueError."""
        extractor = ClaudeJDExtractor()
        cli_output = json.dumps({
            "result": "this is not valid json",
            "model": "claude"
        })

        with pytest.raises(ValueError) as exc_info:
            extractor._parse_cli_output(cli_output)

        assert "Failed to parse extraction result" in str(exc_info.value)


# ===== TESTS: Validation and Conversion =====

class TestValidationAndConversion:
    """Test schema validation and conversion to ExtractedJD."""

    def test_validates_and_converts_valid_data(self, sample_extracted_jd):
        """Valid data passes validation and converts correctly."""
        extractor = ClaudeJDExtractor()
        validated = extractor._validate_and_convert(sample_extracted_jd)

        assert validated["role_category"] == "engineering_manager"
        assert validated["competency_weights"]["delivery"] == 25
        assert len(validated["responsibilities"]) >= 1

    def test_normalizes_enum_values(self):
        """Enum values are normalized (case, underscores)."""
        extractor = ClaudeJDExtractor()
        data = {
            "title": "Test",
            "company": "Test Co",
            "role_category": "Engineering Manager",  # Should become engineering_manager
            "seniority_level": "SENIOR",  # Should become senior
            "remote_policy": "fully-remote",  # Should become fully_remote
            "competency_weights": {"delivery": 25, "process": 25, "architecture": 25, "leadership": 25},
            "responsibilities": ["Resp 1", "Resp 2", "Resp 3"],  # Min 3 required
            "qualifications": ["Qual 1", "Qual 2"],  # Min 2 required
            "technical_skills": ["Python"],
            "soft_skills": ["Leadership"],
            "top_keywords": ["k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9", "k10", "k11", "k12", "k13", "k14", "k15"],
        }

        validated = extractor._validate_and_convert(data)
        assert validated["role_category"] == "engineering_manager"
        assert validated["seniority_level"] == "senior"
        assert validated["remote_policy"] == "fully_remote"

    def test_invalid_competency_weights_fails(self):
        """Competency weights not summing to 100 fail validation."""
        extractor = ClaudeJDExtractor()
        data = {
            "title": "Test",
            "company": "Test Co",
            "role_category": "engineering_manager",
            "seniority_level": "senior",
            "competency_weights": {"delivery": 50, "process": 50, "architecture": 50, "leadership": 50},  # Sum = 200
            "responsibilities": ["Test"],
            "qualifications": ["Test"],
            "technical_skills": ["Python"],
            "soft_skills": ["Leadership"],
            "top_keywords": ["k"] * 15,
        }

        with pytest.raises(ValueError) as exc_info:
            extractor._validate_and_convert(data)

        assert "validation failed" in str(exc_info.value).lower()


# ===== TESTS: Full Extraction Flow (UnifiedLLM Mocked) =====

class TestExtraction:
    """Test full extraction flow with mocked UnifiedLLM."""

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_successful_extraction(self, mock_invoke, sample_job_data, sample_llm_result_success):
        """Successful extraction returns valid ExtractionResult."""
        mock_invoke.return_value = sample_llm_result_success

        extractor = ClaudeJDExtractor(model="claude-opus-4-5-20251101")
        result = extractor.extract(
            job_id=sample_job_data["job_id"],
            title=sample_job_data["title"],
            company=sample_job_data["company"],
            job_description=sample_job_data["job_description"]
        )

        assert result.success is True
        assert result.job_id == "test_claude_001"
        assert result.extracted_jd["role_category"] == "engineering_manager"
        assert result.error is None

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_llm_error_returns_failure(self, mock_invoke, sample_job_data, sample_llm_result_failure):
        """LLM error (when fallback disabled) returns failed ExtractionResult."""
        mock_invoke.return_value = sample_llm_result_failure

        extractor = ClaudeJDExtractor()
        result = extractor.extract(
            job_id=sample_job_data["job_id"],
            title=sample_job_data["title"],
            company=sample_job_data["company"],
            job_description=sample_job_data["job_description"]
        )

        assert result.success is False
        assert result.extracted_jd is None
        assert "failed" in result.error.lower() or "disabled" in result.error.lower()

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_llm_timeout_returns_failure(self, mock_invoke, sample_job_data):
        """LLM timeout returns failed ExtractionResult."""
        mock_invoke.return_value = LLMResult(
            content="",
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=120000,
            success=False,
            error="CLI timeout after 120s",
        )

        extractor = ClaudeJDExtractor(timeout=120)
        result = extractor.extract(
            job_id=sample_job_data["job_id"],
            title=sample_job_data["title"],
            company=sample_job_data["company"],
            job_description=sample_job_data["job_description"]
        )

        assert result.success is False
        assert "timeout" in result.error.lower()
        assert result.duration_ms >= 0

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_invalid_json_response_returns_failure(self, mock_invoke, sample_job_data):
        """Invalid JSON from LLM returns failed ExtractionResult after validation."""
        # LLM returns success but with invalid/unparseable content
        mock_invoke.return_value = LLMResult(
            content="not json inside",
            parsed_json=None,  # JSON parsing failed
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=5000,
            success=True,  # LLM call succeeded, but content is not valid JSON
        )

        extractor = ClaudeJDExtractor()
        result = extractor.extract(
            job_id=sample_job_data["job_id"],
            title=sample_job_data["title"],
            company=sample_job_data["company"],
            job_description=sample_job_data["job_description"]
        )

        assert result.success is False
        assert result.extracted_jd is None
        # Error should mention parsing or JSON
        assert "parse" in result.error.lower() or "json" in result.error.lower()

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_fallback_to_langchain_on_cli_failure(self, mock_invoke, sample_job_data, sample_extracted_jd):
        """When CLI fails but fallback succeeds, extraction succeeds with fallback model."""
        # Simulate successful fallback to LangChain
        mock_invoke.return_value = LLMResult(
            content=json.dumps(sample_extracted_jd),
            parsed_json=sample_extracted_jd,
            backend="langchain",  # Fallback was used
            model="gpt-4o",
            tier="middle",
            duration_ms=3000,
            success=True,
        )

        extractor = ClaudeJDExtractor()
        result = extractor.extract(
            job_id=sample_job_data["job_id"],
            title=sample_job_data["title"],
            company=sample_job_data["company"],
            job_description=sample_job_data["job_description"]
        )

        assert result.success is True
        assert result.model == "gpt-4o"  # Fallback model was used
        assert result.extracted_jd["role_category"] == "engineering_manager"


# ===== TESTS: CLI Availability Check =====

class TestCLIAvailability:
    """Test Claude CLI availability check via UnifiedLLM."""

    @patch('src.common.unified_llm.UnifiedLLM')
    def test_cli_available_returns_true(self, mock_unified_llm_class):
        """Returns True when CLI is available."""
        mock_instance = MagicMock()
        mock_instance.check_cli_available.return_value = True
        mock_unified_llm_class.return_value = mock_instance

        extractor = ClaudeJDExtractor()
        assert extractor.check_cli_available() is True

    @patch('src.common.unified_llm.UnifiedLLM')
    def test_cli_unavailable_returns_false(self, mock_unified_llm_class):
        """Returns False when CLI is not available."""
        mock_instance = MagicMock()
        mock_instance.check_cli_available.return_value = False
        mock_unified_llm_class.return_value = mock_instance

        extractor = ClaudeJDExtractor()
        assert extractor.check_cli_available() is False

    @patch('src.common.unified_llm.UnifiedLLM')
    def test_cli_not_found_returns_false(self, mock_unified_llm_class):
        """Returns False when CLI binary not found."""
        mock_instance = MagicMock()
        mock_instance.check_cli_available.return_value = False
        mock_unified_llm_class.return_value = mock_instance

        extractor = ClaudeJDExtractor()
        assert extractor.check_cli_available() is False

    @patch('src.common.unified_llm.UnifiedLLM')
    def test_cli_timeout_returns_false(self, mock_unified_llm_class):
        """Returns False when CLI check times out."""
        mock_instance = MagicMock()
        mock_instance.check_cli_available.return_value = False
        mock_unified_llm_class.return_value = mock_instance

        extractor = ClaudeJDExtractor()
        assert extractor.check_cli_available() is False


# ===== TESTS: Log Callback =====

class TestLogCallback:
    """Test log callback functionality."""

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_custom_log_callback_is_called(self, mock_invoke, sample_job_data, sample_llm_result_success):
        """Custom log callback receives log events."""
        mock_invoke.return_value = sample_llm_result_success

        log_events = []

        def capture_log(job_id, level, data):
            log_events.append((job_id, level, data))

        extractor = ClaudeJDExtractor(log_callback=capture_log)
        extractor.extract(
            job_id=sample_job_data["job_id"],
            title=sample_job_data["title"],
            company=sample_job_data["company"],
            job_description=sample_job_data["job_description"]
        )

        # Should have at least start and completion logs
        assert len(log_events) >= 2
        assert log_events[0][0] == sample_job_data["job_id"]
        assert "info" in [e[1] for e in log_events]


# ===== TESTS: Batch Extraction =====

class TestBatchExtraction:
    """Test batch extraction with concurrency control."""

    @pytest.mark.asyncio
    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    async def test_batch_extraction_returns_all_results(self, mock_invoke, sample_extracted_jd):
        """Batch extraction returns results for all jobs."""
        mock_invoke.return_value = LLMResult(
            content=json.dumps(sample_extracted_jd),
            parsed_json=sample_extracted_jd,
            backend="claude_cli",
            model="claude-opus-4-5-20251101",
            tier="middle",
            duration_ms=5000,
            success=True,
        )

        jobs = [
            {"job_id": "batch_001", "title": "EM 1", "company": "Co 1", "job_description": "Test JD 1"},
            {"job_id": "batch_002", "title": "EM 2", "company": "Co 2", "job_description": "Test JD 2"},
            {"job_id": "batch_003", "title": "EM 3", "company": "Co 3", "job_description": "Test JD 3"},
        ]

        extractor = ClaudeJDExtractor()
        results = await extractor.extract_batch(jobs, max_concurrent=2)

        assert len(results) == 3
        assert all(r.success for r in results)
        assert results[0].job_id == "batch_001"
        assert results[1].job_id == "batch_002"
        assert results[2].job_id == "batch_003"

    @pytest.mark.asyncio
    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    async def test_batch_extraction_handles_mixed_results(self, mock_invoke, sample_extracted_jd):
        """Batch extraction handles mix of success and failure."""
        # First call succeeds, second fails, third succeeds
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                return LLMResult(
                    content="",
                    backend="none",
                    model="",
                    tier="middle",
                    duration_ms=0,
                    success=False,
                    error="LLM call failed",
                )
            return LLMResult(
                content=json.dumps(sample_extracted_jd),
                parsed_json=sample_extracted_jd,
                backend="claude_cli",
                model="claude-opus-4-5-20251101",
                tier="middle",
                duration_ms=5000,
                success=True,
            )

        mock_invoke.side_effect = side_effect

        jobs = [
            {"job_id": "mix_001", "title": "EM 1", "company": "Co 1", "job_description": "Test JD 1"},
            {"job_id": "mix_002", "title": "EM 2", "company": "Co 2", "job_description": "Test JD 2"},
            {"job_id": "mix_003", "title": "EM 3", "company": "Co 3", "job_description": "Test JD 3"},
        ]

        extractor = ClaudeJDExtractor()
        results = await extractor.extract_batch(jobs, max_concurrent=1)

        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True


# ===== TESTS: Convenience Function =====

class TestConvenienceFunction:
    """Test the extract_jd_with_claude convenience function."""

    @patch('src.layer1_4.claude_jd_extractor.invoke_unified_sync')
    def test_convenience_function_works(self, mock_invoke, sample_llm_result_success):
        """Convenience function creates extractor and extracts."""
        mock_invoke.return_value = sample_llm_result_success

        result = extract_jd_with_claude(
            job_id="conv_001",
            title="Test Title",
            company="Test Co",
            job_description="Test JD content"
        )

        assert isinstance(result, ExtractionResult)
        assert result.job_id == "conv_001"


# ===== TESTS: Model Configuration =====

class TestModelConfiguration:
    """Test model configuration via constructor and env vars."""

    def test_default_model(self):
        """Default model is claude-opus-4-5-20251101."""
        extractor = ClaudeJDExtractor()
        assert "opus" in extractor.model.lower()

    def test_custom_model_override(self):
        """Custom model can be specified."""
        extractor = ClaudeJDExtractor(model="claude-sonnet-4-20250514")
        assert extractor.model == "claude-sonnet-4-20250514"

    @patch.dict('os.environ', {'CLAUDE_CODE_MODEL': 'claude-haiku-3-20240307'})
    def test_env_var_model(self):
        """Model from env var is used when no explicit model given."""
        extractor = ClaudeJDExtractor()
        assert extractor.model == "claude-haiku-3-20240307"

    @patch.dict('os.environ', {'CLAUDE_CODE_MODEL': 'env-model'})
    def test_explicit_model_overrides_env(self):
        """Explicit model parameter overrides env var."""
        extractor = ClaudeJDExtractor(model="explicit-model")
        assert extractor.model == "explicit-model"


# ===== TESTS: Prompt Building =====

class TestPromptBuilding:
    """Test prompt construction for CLI."""

    def test_prompt_includes_job_details(self):
        """Built prompt includes title, company, and JD."""
        extractor = ClaudeJDExtractor()
        prompt = extractor._build_prompt(
            title="Engineering Manager",
            company="TechCo",
            job_description="Lead a team of engineers..."
        )

        assert "Engineering Manager" in prompt
        assert "TechCo" in prompt
        assert "Lead a team" in prompt
        assert "JSON" in prompt  # Should request JSON output

    def test_prompt_truncates_long_jd(self):
        """Long JD is truncated to 12000 chars."""
        extractor = ClaudeJDExtractor()
        # Create a JD with a marker at position 12000 to verify truncation
        long_jd = "a" * 12000 + "MARKER_SHOULD_BE_TRUNCATED" + "b" * 7974  # 20000 total

        prompt = extractor._build_prompt(
            title="Test",
            company="Test Co",
            job_description=long_jd
        )

        # Verify truncation: first 12000 chars should be present
        assert "a" * 100 in prompt  # Beginning of JD is present
        # The marker and content after 12000 chars should be truncated
        assert "MARKER_SHOULD_BE_TRUNCATED" not in prompt
        assert "b" * 100 not in prompt
