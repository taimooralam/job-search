"""
Tests for pain_points stage (T9).

Quality-gate: patch shape unchanged vs pre-refactor output from full_extraction_service.
Verifies:
- Provider routing
- Codex primary happy path: provider_used="codex", provider_attempts length 1
- Codex subprocess-fail path: fallback triggered, provider_fallback_reason set
- Patch shape matches full_extraction_service._persist_results() fields
- Missing JD text raises ValueError
- PainPointMiner exception propagates as ValueError
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.preenrich.stages.pain_points import PainPointsStage
from src.preenrich.types import StageContext, StageResult, StepConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_ctx(
    provider: str = "claude",
    job_doc: Optional[Dict[str, Any]] = None,
) -> StageContext:
    if job_doc is None:
        job_doc = {
            "_id": "job_pp_001",
            "title": "Head of AI",
            "company": "StartupCo",
            "description": "Lead AI strategy. Build LLM pipelines. Drive ROI.",
        }
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:pain001",
        company_checksum="sha256:comp001",
        input_snapshot_id="sha256:pain001",
        attempt_number=1,
        config=StepConfig(provider=provider),
    )


_MOCK_PAIN_POINTS_OUTPUT = {
    "pain_points": ["Slow time-to-insight", "High infrastructure costs"],
    "strategic_needs": ["AI governance framework", "ML platform"],
    "risks_if_unfilled": ["Competitive disadvantage"],
    "success_metrics": ["Reduce model latency by 50%"],
}


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPainPointsStageProtocol:
    def test_has_name(self):
        assert PainPointsStage().name == "pain_points"

    def test_has_dependencies(self):
        assert PainPointsStage().dependencies == ["jd_extraction"]

    def test_has_run_method(self):
        assert callable(PainPointsStage().run)


class TestPainPointsStageProviderRouting:
    def test_unknown_provider_raises_value_error(self):
        ctx = _make_ctx(provider="vertex")
        with pytest.raises(ValueError, match="Unsupported provider"):
            PainPointsStage().run(ctx)


class TestPainPointsStagePatchShape:
    @patch("src.preenrich.stages.pain_points.PainPointMiner")
    def test_patch_fields_match_full_extraction_service(self, mock_miner_cls):
        """
        T9: quality-gate — patch shape must match full_extraction_service._persist_results().

        pre-refactor shape:
            "pain_points": [...],
            "strategic_needs": [...],
            "risks_if_unfilled": [...],
            "success_metrics": [...],
        """
        mock_instance = MagicMock()
        mock_instance.extract_pain_points.return_value = dict(_MOCK_PAIN_POINTS_OUTPUT)
        mock_miner_cls.return_value = mock_instance

        ctx = _make_ctx()
        result = PainPointsStage().run(ctx)

        assert isinstance(result, StageResult)
        assert "pain_points" in result.output
        assert "strategic_needs" in result.output
        assert "risks_if_unfilled" in result.output
        assert "success_metrics" in result.output

    @patch("src.preenrich.stages.pain_points.PainPointMiner")
    def test_values_propagated_correctly(self, mock_miner_cls):
        mock_instance = MagicMock()
        mock_instance.extract_pain_points.return_value = dict(_MOCK_PAIN_POINTS_OUTPUT)
        mock_miner_cls.return_value = mock_instance

        ctx = _make_ctx()
        result = PainPointsStage().run(ctx)

        assert result.output["pain_points"] == _MOCK_PAIN_POINTS_OUTPUT["pain_points"]
        assert result.output["strategic_needs"] == _MOCK_PAIN_POINTS_OUTPUT["strategic_needs"]

    @patch("src.preenrich.stages.pain_points.PainPointMiner")
    def test_provider_used_is_claude(self, mock_miner_cls):
        mock_instance = MagicMock()
        mock_instance.extract_pain_points.return_value = dict(_MOCK_PAIN_POINTS_OUTPUT)
        mock_miner_cls.return_value = mock_instance

        result = PainPointsStage().run(_make_ctx())
        assert result.provider_used == "claude"

    @patch("src.preenrich.stages.pain_points.PainPointMiner")
    def test_miner_called_with_no_enhanced_format(self, mock_miner_cls):
        """Verify PainPointMiner instantiated with use_enhanced_format=False (matches service)."""
        mock_instance = MagicMock()
        mock_instance.extract_pain_points.return_value = dict(_MOCK_PAIN_POINTS_OUTPUT)
        mock_miner_cls.return_value = mock_instance

        PainPointsStage().run(_make_ctx())

        mock_miner_cls.assert_called_once()
        call_kwargs = mock_miner_cls.call_args[1]
        assert call_kwargs.get("use_enhanced_format") is False


class TestPainPointsStageErrorHandling:
    def test_missing_jd_text_raises_value_error(self):
        ctx = _make_ctx(job_doc={"_id": "job_no_jd", "title": "Test", "company": "Acme"})
        with pytest.raises(ValueError, match="No JD text"):
            PainPointsStage().run(ctx)

    @patch("src.preenrich.stages.pain_points.PainPointMiner")
    def test_miner_exception_propagates_as_value_error(self, mock_miner_cls):
        mock_instance = MagicMock()
        mock_instance.extract_pain_points.side_effect = RuntimeError("LLM timeout")
        mock_miner_cls.return_value = mock_instance

        ctx = _make_ctx()
        with pytest.raises(ValueError, match="PainPointMiner failed"):
            PainPointsStage().run(ctx)


# ---------------------------------------------------------------------------
# Codex provider tests (Phase 2b)
# ---------------------------------------------------------------------------


def _make_codex_result_pp(success: bool, result=None, error=None):
    @dataclass
    class _CR:
        success: bool
        result: Optional[dict]
        error: Optional[str]
        model: str = "gpt-5.4"
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

    return _CR(success=success, result=result, error=error)


class TestPainPointsCodexProvider:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_happy_path(self, mock_codex_cls):
        """
        Codex provider happy path:
          - provider_used="codex"
          - provider_attempts length 1
          - patch contains pain_points, strategic_needs, risks_if_unfilled, success_metrics
        """
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result_pp(
            success=True,
            result={
                "pain_points": ["High infra cost"],
                "strategic_needs": ["ML platform"],
                "risks_if_unfilled": ["Slow delivery"],
                "success_metrics": ["Reduce latency 50%"],
            },
        )
        mock_codex_cls.return_value = mock_cli

        stage = PainPointsStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4"
        ctx.config.fallback_model = "claude-sonnet-4-5"
        result = stage.run(ctx)

        assert result.provider_used == "codex"
        assert len(result.provider_attempts) == 1
        assert result.provider_attempts[0]["outcome"] == "success"
        assert "pain_points" in result.output
        assert result.provider_fallback_reason is None

    @patch("src.preenrich.stages.pain_points._claude_run_pain_points")
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_subprocess_fail_triggers_fallback(self, mock_codex_cls, mock_claude_pp):
        """
        Codex fail → Claude fallback:
          - provider_used="claude"
          - provider_attempts length 2
          - provider_fallback_reason="error_subprocess"
        """
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result_pp(
            success=False, error="codex failed"
        )
        mock_codex_cls.return_value = mock_cli

        mock_claude_pp.return_value = dict(_MOCK_PAIN_POINTS_OUTPUT)

        stage = PainPointsStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4"
        ctx.config.fallback_model = "claude-sonnet-4-5"
        result = stage.run(ctx)

        assert result.provider_used == "claude"
        assert len(result.provider_attempts) == 2
        assert result.provider_attempts[0]["outcome"] == "error_subprocess"
        assert result.provider_attempts[1]["outcome"] == "success"
        assert result.provider_fallback_reason == "error_subprocess"
