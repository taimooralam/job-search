"""
Tests for persona stage (T11).

Verifies:
- Sonnet default replaces Opus (DEFAULT_TIER == "balanced")
- Output schema identical to current persona_builder output
- Skip when no persona annotations
- Codex primary happy path: provider_used="codex", provider_attempts length 1
- Codex subprocess-fail path: fallback triggered, provider_fallback_reason set
- Tier is configurable via StepConfig.model
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.preenrich.stages.persona import DEFAULT_TIER, PersonaStage
from src.preenrich.types import StageContext, StageResult, StepConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_ctx(
    provider: str = "claude",
    model: Optional[str] = None,
    job_doc: Optional[Dict[str, Any]] = None,
) -> StageContext:
    if job_doc is None:
        job_doc = {
            "_id": "job_persona_001",
            "title": "AI Platform Lead",
            "company": "Nexus",
            "description": "Lead AI teams.",
            "jd_annotations": {
                "annotations": [
                    {
                        "id": "ann_001",
                        "target": {"text": "LLM infrastructure", "section": "responsibilities"},
                        "relevance": "core_strength",
                        "identity": "core_identity",
                        "passion": "love_it",
                    }
                ],
                "processed_jd_sections": [],
            },
            "extracted_jd": {"ideal_candidate_profile": {"summary": "AI leader"}},
        }
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:persona001",
        company_checksum="sha256:comp001",
        input_snapshot_id="sha256:persona001",
        attempt_number=1,
        config=StepConfig(provider=provider, model=model or ""),
    )


def _make_synthesized_persona():
    from src.common.persona_builder import SynthesizedPersona
    return SynthesizedPersona(
        persona_statement="An AI platform leader who builds transformative LLM systems.",
        primary_identity="LLM infrastructure expert",
        secondary_identities=["AI strategy leader"],
        source_annotations=["ann_001"],
        synthesized_at=datetime(2026, 4, 17, 12, 0, 0),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPersonaStageProtocol:
    def test_has_name(self):
        assert PersonaStage().name == "persona"

    def test_has_dependencies(self):
        assert PersonaStage().dependencies == ["annotations"]

    def test_has_run_method(self):
        assert callable(PersonaStage().run)


class TestPersonaStageDefaultTier:
    def test_default_tier_is_balanced_not_opus(self):
        """T11: Sonnet default replaces Opus — DEFAULT_TIER must be 'balanced'."""
        assert DEFAULT_TIER == "balanced", (
            f"Expected 'balanced' (Sonnet), got '{DEFAULT_TIER}'. "
            "This is the main cost win from plan §4 — do not change to 'quality' (Opus)."
        )


class TestPersonaStageProviderRouting:
    def test_unknown_provider_raises_value_error(self):
        ctx = _make_ctx(provider="gpt4")
        with pytest.raises(ValueError, match="Unsupported provider"):
            PersonaStage().run(ctx)


class TestPersonaStageSynthesis:
    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_skip_when_no_persona_annotations(self, mock_builder_cls):
        """Stage returns skipped result when no identity/passion/strength annotations."""
        mock_instance = MagicMock()
        mock_instance.has_persona_annotations.return_value = False
        mock_builder_cls.return_value = mock_instance

        ctx = _make_ctx()
        result = PersonaStage().run(ctx)

        assert isinstance(result, StageResult)
        assert result.skip_reason == "no_persona_annotations"
        assert result.output == {}

    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_synthesis_returns_none_marks_skipped(self, mock_builder_cls):
        mock_instance = MagicMock()
        mock_instance.has_persona_annotations.return_value = True
        # synthesize returns None (no good annotations after filtering)
        mock_instance.synthesize = AsyncMock(return_value=None)
        mock_builder_cls.return_value = mock_instance

        ctx = _make_ctx()
        result = PersonaStage().run(ctx)

        assert result.skip_reason == "synthesis_returned_none"

    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_output_schema_matches_persona_builder(self, mock_builder_cls):
        """T11: output schema identical to current persona_builder output (SynthesizedPersona.to_dict)."""
        persona = _make_synthesized_persona()
        mock_instance = MagicMock()
        mock_instance.has_persona_annotations.return_value = True
        mock_instance.synthesize = AsyncMock(return_value=persona)
        mock_builder_cls.return_value = mock_instance

        ctx = _make_ctx()
        result = PersonaStage().run(ctx)

        assert "jd_annotations" in result.output
        synthesized = result.output["jd_annotations"]["synthesized_persona"]

        # Match SynthesizedPersona.to_dict() keys
        assert "persona_statement" in synthesized
        assert "primary_identity" in synthesized
        assert "secondary_identities" in synthesized
        assert "source_annotations" in synthesized
        assert synthesized["persona_statement"] == persona.persona_statement

    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_tier_defaults_to_balanced(self, mock_builder_cls):
        """Verify DEFAULT_TIER 'balanced' is used when no model config override."""
        mock_instance = MagicMock()
        mock_instance.has_persona_annotations.return_value = True
        mock_instance.synthesize = AsyncMock(return_value=_make_synthesized_persona())
        mock_builder_cls.return_value = mock_instance

        ctx = _make_ctx(model=None)
        result = PersonaStage().run(ctx)

        assert result.model_used == "balanced"

    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_tier_configurable_via_step_config(self, mock_builder_cls):
        """Tier override via StepConfig.model (allows caller to restore Opus if needed)."""
        mock_instance = MagicMock()
        mock_instance.has_persona_annotations.return_value = True
        mock_instance.synthesize = AsyncMock(return_value=_make_synthesized_persona())
        mock_builder_cls.return_value = mock_instance

        ctx = _make_ctx(model="quality")  # Override to Opus
        result = PersonaStage().run(ctx)

        assert result.model_used == "quality"


# ---------------------------------------------------------------------------
# Codex provider tests (Phase 2b)
# ---------------------------------------------------------------------------


def _make_codex_result_persona(success: bool, result=None, error=None):
    @dataclass
    class _CR:
        success: bool
        result: Optional[dict]
        error: Optional[str]
        model: str = "gpt-5.4"
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None

    return _CR(success=success, result=result, error=error)


class TestPersonaCodexProvider:
    @patch("src.preenrich.stages.base.CodexCLI")
    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_codex_happy_path(self, mock_builder_cls, mock_codex_cls):
        """
        Codex provider happy path:
          - provider_used="codex"
          - provider_attempts length 1
          - jd_annotations.synthesized_persona in output
        """
        # PersonaBuilder.has_persona_annotations returns True
        mock_builder_instance = MagicMock()
        mock_builder_instance.has_persona_annotations.return_value = True
        mock_builder_cls.return_value = mock_builder_instance

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result_persona(
            success=True,
            result={
                "persona_statement": "An AI platform leader.",
                "primary_identity": "AI builder",
                "secondary_identities": ["ML architect"],
                "source_annotations": ["ann_001"],
            },
        )
        mock_codex_cls.return_value = mock_cli

        stage = PersonaStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4"
        ctx.config.fallback_model = "claude-sonnet-4-5"
        result = stage.run(ctx)

        assert result.provider_used == "codex"
        assert len(result.provider_attempts) == 1
        assert result.provider_attempts[0]["outcome"] == "success"
        assert "jd_annotations" in result.output
        assert "synthesized_persona" in result.output["jd_annotations"]
        assert result.provider_fallback_reason is None

    @patch("src.preenrich.stages.persona._claude_synthesize_persona")
    @patch("src.preenrich.stages.base.CodexCLI")
    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_codex_subprocess_fail_triggers_fallback(
        self, mock_builder_cls, mock_codex_cls, mock_claude_synth
    ):
        """
        Codex fail → Claude fallback:
          - provider_used="claude"
          - provider_attempts length 2
          - provider_fallback_reason="error_subprocess"
        """
        mock_builder_instance = MagicMock()
        mock_builder_instance.has_persona_annotations.return_value = True
        mock_builder_cls.return_value = mock_builder_instance

        mock_cli = MagicMock()
        mock_cli.invoke.return_value = _make_codex_result_persona(
            success=False, error="codex failed"
        )
        mock_codex_cls.return_value = mock_cli

        mock_claude_synth.return_value = {
            "persona_statement": "from claude",
            "primary_identity": "claude identity",
            "secondary_identities": [],
            "source_annotations": [],
            "synthesized_at": "2026-04-17T00:00:00",
        }

        stage = PersonaStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4"
        ctx.config.fallback_model = "claude-sonnet-4-5"
        result = stage.run(ctx)

        assert result.provider_used == "claude"
        assert len(result.provider_attempts) == 2
        assert result.provider_attempts[0]["outcome"] == "error_subprocess"
        assert result.provider_attempts[1]["outcome"] == "success"
        assert result.provider_fallback_reason == "error_subprocess"

    @patch("src.preenrich.stages.base.CodexCLI")
    @patch("src.preenrich.stages.persona.PersonaBuilder")
    def test_codex_no_annotations_skips(self, mock_builder_cls, mock_codex_cls):
        """Codex path: no persona annotations → skip_reason='no_persona_annotations'."""
        mock_builder_instance = MagicMock()
        mock_builder_instance.has_persona_annotations.return_value = False
        mock_builder_cls.return_value = mock_builder_instance

        stage = PersonaStage()
        ctx = _make_ctx(provider="codex")
        ctx.config.primary_model = "gpt-5.4"
        result = stage.run(ctx)

        assert result.skip_reason == "no_persona_annotations"
        assert result.output == {}
