"""
T8 — jd_extraction stage adapter.

Validates:
- Claude path succeeds and returns StageResult with extracted_jd
- Codex primary path happy: provider_used="codex", provider_attempts length 1
- Codex schema-fail path: provider_used="claude", provider_attempts length 2, fallback_reason set
- Unknown provider raises ValueError
- Stage satisfies StageBase protocol
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.preenrich.types import StageContext, StepConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ctx(provider="claude") -> StageContext:
    return StageContext(
        job_doc={
            "_id": "job_ext_1",
            "title": "ML Engineer",
            "company": "TestCo",
            "description": "We are hiring ML engineers with Python experience.",
        },
        jd_checksum="sha256:abc",
        company_checksum="sha256:co",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(provider=provider, prompt_version="v1"),
    )


@dataclass
class _FakeExtractionResult:
    success: bool
    extracted_jd: Optional[dict]
    error: Optional[str] = None
    model: Optional[str] = "claude-haiku-4-5"
    input_tokens: Optional[int] = 100
    output_tokens: Optional[int] = 200
    cost_usd: Optional[float] = 0.001


# ---------------------------------------------------------------------------
# Claude path
# ---------------------------------------------------------------------------


def test_jd_extraction_claude_success():
    """Claude path returns StageResult with extracted_jd patch."""
    from src.preenrich.stages.jd_extraction import JDExtractionStage

    extracted_data = {
        "title": "ML Engineer",
        "required_skills": ["Python"],
        "responsibilities": [],
        "qualifications": [],
        "company_name": "TestCo",
        "employment_type": "full_time",
        "location": "Remote",
        "seniority_level": "senior",
        "industry": "Technology",
    }

    fake_result = _FakeExtractionResult(
        success=True,
        extracted_jd=extracted_data,
    )

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = fake_result

    # Mock ExtractedJD to pass validation
    class _FakeValidated:
        def model_dump(self):
            return extracted_data

    with patch("src.layer1_4.claude_jd_extractor.JDExtractor", return_value=mock_extractor), \
         patch("src.common.state.ExtractedJD", return_value=_FakeValidated()):
        stage = JDExtractionStage()
        ctx = _make_ctx(provider="claude")
        result = stage.run(ctx)

    assert result is not None
    assert "extracted_jd" in result.output
    assert result.provider_used == "claude"
    assert result.prompt_version == "v1"


def test_jd_extraction_claude_failure_raises():
    """Claude path raises ValueError when extraction fails."""
    from src.preenrich.stages.jd_extraction import JDExtractionStage

    fake_result = _FakeExtractionResult(
        success=False,
        extracted_jd=None,
        error="LLM timeout",
    )

    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = fake_result

    with patch("src.layer1_4.claude_jd_extractor.JDExtractor", return_value=mock_extractor):
        stage = JDExtractionStage()
        ctx = _make_ctx(provider="claude")
        with pytest.raises(ValueError, match="JDExtractor failed"):
            stage.run(ctx)


# ---------------------------------------------------------------------------
# Codex primary path (Phase 2b)
# ---------------------------------------------------------------------------


def _make_codex_result(success: bool, result=None, error=None):
    @dataclass
    class _CR:
        success: bool
        result: Optional[dict]
        error: Optional[str]
        model: str = "gpt-5.4"
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

    return _CR(success=success, result=result, error=error)


_EXTRACTED_JD_DATA = {
    "title": "ML Engineer",
    "required_skills": ["Python"],
    "responsibilities": [],
    "qualifications": [],
    "company_name": "TestCo",
    "employment_type": "full_time",
    "location": "Remote",
    "seniority_level": "senior",
    "industry": "Technology",
}


@patch("src.preenrich.stages.base.CodexCLI")
def test_jd_extraction_codex_happy_path(mock_codex_cls):
    """
    Codex provider happy path:
      - provider_used="codex"
      - provider_attempts length 1
      - extracted_jd in output
    """
    from src.preenrich.stages.jd_extraction import JDExtractionStage

    mock_cli = MagicMock()
    mock_cli.invoke.return_value = _make_codex_result(
        success=True, result=dict(_EXTRACTED_JD_DATA)
    )
    mock_codex_cls.return_value = mock_cli

    class _FakeValidated:
        def model_dump(self):
            return dict(_EXTRACTED_JD_DATA)

    with patch("src.common.state.ExtractedJD", return_value=_FakeValidated()):
        stage = JDExtractionStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4"
        ctx.config.fallback_model = "claude-haiku-4-5"
        result = stage.run(ctx)

    assert result.provider_used == "codex"
    assert len(result.provider_attempts) == 1
    assert result.provider_attempts[0]["outcome"] == "success"
    assert "extracted_jd" in result.output
    assert result.provider_fallback_reason is None


@patch("src.preenrich.stages.base.CodexCLI")
def test_jd_extraction_codex_subprocess_fail_triggers_fallback(mock_codex_cls):
    """
    Codex subprocess fail → Claude fallback → provider_used="claude",
    provider_attempts length 2, provider_fallback_reason set.
    """
    from src.preenrich.stages.jd_extraction import JDExtractionStage

    mock_cli = MagicMock()
    mock_cli.invoke.return_value = _make_codex_result(
        success=False, error="codex exec failed"
    )
    mock_codex_cls.return_value = mock_cli

    # Mock the Claude fallback (_claude_invoker_for_jd)
    with patch(
        "src.preenrich.stages.jd_extraction._claude_invoker_for_jd",
        return_value=dict(_EXTRACTED_JD_DATA),
    ):
        with patch("src.common.state.ExtractedJD") as mock_ejd:
            class _FakeValidated:
                def model_dump(self):
                    return dict(_EXTRACTED_JD_DATA)
            mock_ejd.return_value = _FakeValidated()

            stage = JDExtractionStage()
            ctx = _make_ctx(provider="codex")
            ctx.config.primary_model = "gpt-5.4"
            ctx.config.fallback_model = "claude-haiku-4-5"
            result = stage.run(ctx)

    assert result.provider_used == "claude"
    assert len(result.provider_attempts) == 2
    assert result.provider_attempts[0]["outcome"] == "error_subprocess"
    assert result.provider_attempts[1]["outcome"] == "success"
    assert result.provider_fallback_reason == "error_subprocess"


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


def test_jd_extraction_unknown_provider_raises():
    """Unknown provider raises ValueError."""
    from src.preenrich.stages.jd_extraction import JDExtractionStage

    stage = JDExtractionStage()
    ctx = _make_ctx(provider="openai")

    with pytest.raises(ValueError, match="Unsupported provider"):
        stage.run(ctx)


# ---------------------------------------------------------------------------
# StageBase protocol
# ---------------------------------------------------------------------------


def test_jd_extraction_satisfies_stage_base():
    """JDExtractionStage satisfies StageBase protocol."""
    from src.preenrich.stages.jd_extraction import JDExtractionStage
    from src.preenrich.stages.base import StageBase

    stage = JDExtractionStage()
    assert isinstance(stage, StageBase)
    assert stage.name == "jd_extraction"
    assert "jd_structure" in stage.dependencies
