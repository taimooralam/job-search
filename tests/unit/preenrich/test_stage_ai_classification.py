"""
Tests for ai_classification stage.

Verifies:
- Provider routing (claude succeeds, codex raises NotImplementedError)
- Patch shape matches full_extraction_service field shape
- Stage satisfies StageBase protocol
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.preenrich.stages.ai_classification import AIClassificationStage
from src.preenrich.types import StageContext, StageResult, StepConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_ctx(provider: str = "claude", job_doc: Optional[Dict[str, Any]] = None) -> StageContext:
    if job_doc is None:
        job_doc = {
            "_id": "test_job_001",
            "title": "Senior AI Engineer",
            "company": "Acme Corp",
            "description": "Build LLM-powered systems for enterprise workflows.",
            "extracted_jd": {"role_category": "ai_engineering", "top_keywords": ["LLM", "Python"]},
        }
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:abc123",
        company_checksum="sha256:def456",
        input_snapshot_id="sha256:abc123",
        attempt_number=1,
        config=StepConfig(provider=provider),
    )


@dataclass
class _MockAIResult:
    is_ai_job: bool = True
    ai_categories: List[str] = field(default_factory=lambda: ["genai_llm", "agentic_ai"])
    ai_category_count: int = 2
    ai_rationale: Optional[str] = "Strong AI focus"
    ai_classified_at: Optional[str] = "2026-04-17T12:00:00"


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestAIClassificationStageProtocol:
    def test_has_name(self):
        stage = AIClassificationStage()
        assert stage.name == "ai_classification"

    def test_has_dependencies(self):
        stage = AIClassificationStage()
        assert stage.dependencies == ["jd_extraction"]

    def test_has_run_method(self):
        stage = AIClassificationStage()
        assert callable(stage.run)


class TestAIClassificationStageProviderRouting:
    def test_unsupported_provider_raises_value_error(self):
        stage = AIClassificationStage()
        ctx = _make_ctx(provider="openai")
        with pytest.raises(ValueError, match="Unsupported provider"):
            stage.run(ctx)


def _make_codex_result_ai(success: bool, result=None, error=None):
    from dataclasses import dataclass

    @dataclass
    class _CR:
        success: bool
        result: Optional[dict]
        error: Optional[str]
        model: str = "gpt-5.4-mini"
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

    return _CR(success=success, result=result, error=error)


class TestAIClassificationCodexProvider:
    @patch("src.preenrich.stages.base.CodexCLI")
    def test_codex_happy_path(self, mock_codex_cls):
        """
        Codex provider happy path:
          - provider_used="codex"
          - provider_attempts length 1
          - patch contains is_ai_job, ai_categories, ai_category_count
        """
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result_ai(
            success=True,
            result={"is_ai_job": True, "categories": ["genai_llm"], "rationale": "Strong AI focus"},
        )
        mock_codex_cls.return_value = mock_cli

        stage = AIClassificationStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4-mini"
        ctx.config.fallback_model = "claude-haiku-4-5"
        result = stage.run(ctx)

        assert result.provider_used == "codex"
        assert len(result.provider_attempts) == 1
        assert result.provider_attempts[0]["outcome"] == "success"
        assert result.output["is_ai_job"] is True
        assert "genai_llm" in result.output["ai_categories"]
        assert result.provider_fallback_reason is None

    @patch("src.preenrich.stages.base.CodexCLI")
    @patch("src.preenrich.stages.ai_classification.classify_job_document_llm")
    def test_codex_subprocess_fail_triggers_fallback(self, mock_classify, mock_codex_cls):
        """
        Codex subprocess fail → Claude fallback:
          - provider_used="claude"
          - provider_attempts length 2
          - provider_fallback_reason="error_subprocess"
        """
        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result_ai(
            success=False, error="codex failed"
        )
        mock_codex_cls.return_value = mock_cli

        mock_classify.return_value = _MockAIResult(
            is_ai_job=True,
            ai_categories=["agentic_ai"],
            ai_category_count=1,
            ai_rationale="Agentic AI",
        )

        stage = AIClassificationStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4-mini"
        ctx.config.fallback_model = "claude-haiku-4-5"
        result = stage.run(ctx)

        assert result.provider_used == "claude"
        assert len(result.provider_attempts) == 2
        assert result.provider_attempts[0]["outcome"] == "error_subprocess"
        assert result.provider_attempts[1]["outcome"] == "success"
        assert result.provider_fallback_reason == "error_subprocess"


class TestAIClassificationStageClaudeProvider:
    @patch("src.preenrich.stages.ai_classification.classify_job_document_llm")
    def test_patch_shape_matches_full_extraction_service(self, mock_classify):
        """Verify patch contains all fields written by full_extraction_service._persist_results()."""
        mock_classify.return_value = _MockAIResult()
        stage = AIClassificationStage()
        ctx = _make_ctx(provider="claude")

        result = stage.run(ctx)

        assert isinstance(result, StageResult)
        # Top-level legacy fields (matching full_extraction_service._persist_results)
        assert "is_ai_job" in result.output
        assert "ai_categories" in result.output
        assert "ai_category_count" in result.output
        assert "ai_rationale" in result.output
        assert "ai_classified_at" in result.output
        # Consolidated sub-doc for preenrich consumers
        assert "ai_classification" in result.output
        ai_cls = result.output["ai_classification"]
        assert ai_cls["is_ai_job"] is True
        assert "genai_llm" in ai_cls["ai_categories"]

    @patch("src.preenrich.stages.ai_classification.classify_job_document_llm")
    def test_values_match_classifier_output(self, mock_classify):
        mock_classify.return_value = _MockAIResult(
            is_ai_job=False,
            ai_categories=[],
            ai_category_count=0,
            ai_rationale="No AI content",
        )
        stage = AIClassificationStage()
        ctx = _make_ctx(provider="claude")

        result = stage.run(ctx)

        assert result.output["is_ai_job"] is False
        assert result.output["ai_categories"] == []
        assert result.output["ai_category_count"] == 0

    @patch("src.preenrich.stages.ai_classification.classify_job_document_llm")
    def test_provider_used_is_claude(self, mock_classify):
        mock_classify.return_value = _MockAIResult()
        stage = AIClassificationStage()
        ctx = _make_ctx(provider="claude")

        result = stage.run(ctx)

        assert result.provider_used == "claude"

    @patch("src.preenrich.stages.ai_classification.classify_job_document_llm")
    def test_classifier_exception_raises_value_error(self, mock_classify):
        mock_classify.side_effect = RuntimeError("LLM timeout")
        stage = AIClassificationStage()
        ctx = _make_ctx(provider="claude")

        with pytest.raises(ValueError, match="AI classification failed"):
            stage.run(ctx)

    @patch("src.preenrich.stages.ai_classification.classify_job_document_llm")
    def test_enriched_doc_includes_extracted_jd(self, mock_classify):
        """Verify the stage passes extracted_jd to classifier (matching full_extraction_service)."""
        mock_classify.return_value = _MockAIResult()
        stage = AIClassificationStage()
        ctx = _make_ctx(provider="claude")

        stage.run(ctx)

        call_arg = mock_classify.call_args[0][0]
        assert "extracted_jd" in call_arg
        assert call_arg["extracted_jd"]["role_category"] == "ai_engineering"
