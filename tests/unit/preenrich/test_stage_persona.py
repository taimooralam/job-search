"""
Tests for persona stage (T11).

Verifies:
- Sonnet default replaces Opus (DEFAULT_TIER == "balanced")
- Output schema identical to current persona_builder output
- Skip when no persona annotations
- Codex raises NotImplementedError
- Tier is configurable via StepConfig.model
"""

from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.preenrich.stages.persona import PersonaStage, DEFAULT_TIER
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
    def test_codex_raises_not_implemented(self):
        ctx = _make_ctx(provider="codex")
        with pytest.raises(NotImplementedError, match="codex provider"):
            PersonaStage().run(ctx)

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
