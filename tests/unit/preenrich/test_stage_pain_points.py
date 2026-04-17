"""
Tests for pain_points stage (T9).

Quality-gate: patch shape unchanged vs pre-refactor output from full_extraction_service.
Verifies:
- Provider routing
- Patch shape matches full_extraction_service._persist_results() fields
- Missing JD text raises ValueError
- PainPointMiner exception propagates as ValueError
"""

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
    def test_codex_raises_not_implemented(self):
        ctx = _make_ctx(provider="codex")
        with pytest.raises(NotImplementedError, match="codex provider"):
            PainPointsStage().run(ctx)

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
