"""
Tests for preenrich_shadow_diff.py — Phase 3 parity diff report.

Validates:
- _is_schema_valid: correct type checks per stage
- _jaccard_keys: dict and list Jaccard similarity
- _extract_text_from_field: nested dot-path extraction
- _diff_stage:
    - jobs with matching live+shadow fields -> schema valid -> PASS
    - jobs with divergent text (mocked low cosine) -> FAIL gate
    - jobs with no shadow data -> sample_size=0, passes_gate=False
- _render_markdown: produces valid Markdown with gate column
- Embedding cache: used for repeated texts (mock API called once)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from bson import ObjectId

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _job_with_shadow(
    stage_name: str,
    shadow_output: Any,
    live_value: Any,
    field_key: str,
    cosine_override: float = 0.95,
) -> Dict[str, Any]:
    """Build a job document that simulates a shadow-replayed result."""
    return {
        "_id": ObjectId(),
        "lifecycle": "completed",
        "company": "TestCo",
        "title": "AI Lead",
        field_key: live_value,
        "selected_at": datetime.now(timezone.utc),
        "pre_enrichment": {
            "shadow_legacy_fields": {field_key: shadow_output},
            "stages": {
                stage_name: {
                    "status": "completed",
                    "shadow_output": {field_key: shadow_output},
                    "cost_usd": 0.001,
                    "duration_ms": 50,
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# _is_schema_valid
# ---------------------------------------------------------------------------

class TestIsSchemaValid:
    def test_persona_valid_dict(self):
        from scripts.preenrich_shadow_diff import _is_schema_valid
        assert _is_schema_valid("persona", {"summary": "Senior eng."}) is True

    def test_persona_invalid_none(self):
        from scripts.preenrich_shadow_diff import _is_schema_valid
        assert _is_schema_valid("persona", None) is False

    def test_pain_points_valid_list(self):
        from scripts.preenrich_shadow_diff import _is_schema_valid
        assert _is_schema_valid("pain_points", [{"description": "scaling"}]) is True

    def test_pain_points_invalid_dict(self):
        from scripts.preenrich_shadow_diff import _is_schema_valid
        assert _is_schema_valid("pain_points", {"description": "scaling"}) is False

    def test_jd_extraction_valid_dict(self):
        from scripts.preenrich_shadow_diff import _is_schema_valid
        assert _is_schema_valid("jd_extraction", {"summary": "ML role"}) is True

    def test_jd_structure_valid_list(self):
        from scripts.preenrich_shadow_diff import _is_schema_valid
        assert _is_schema_valid("jd_structure", ["section1"]) is True


# ---------------------------------------------------------------------------
# _jaccard_keys
# ---------------------------------------------------------------------------

class TestJaccardKeys:
    def test_identical_dicts(self):
        from scripts.preenrich_shadow_diff import _jaccard_keys
        a = {"x": 1, "y": 2}
        b = {"x": 3, "y": 4}
        assert _jaccard_keys(a, b) == 1.0

    def test_disjoint_dicts(self):
        from scripts.preenrich_shadow_diff import _jaccard_keys
        a = {"x": 1}
        b = {"y": 2}
        assert _jaccard_keys(a, b) == 0.0

    def test_partial_overlap_dicts(self):
        from scripts.preenrich_shadow_diff import _jaccard_keys
        a = {"x": 1, "y": 2}
        b = {"x": 1, "z": 3}
        score = _jaccard_keys(a, b)
        assert abs(score - 1 / 3) < 0.01

    def test_lists_same_length(self):
        from scripts.preenrich_shadow_diff import _jaccard_keys
        assert _jaccard_keys(["a", "b"], ["c", "d"]) == 1.0

    def test_lists_different_length(self):
        from scripts.preenrich_shadow_diff import _jaccard_keys
        score = _jaccard_keys(["a", "b", "c"], ["x"])
        assert abs(score - 1 / 3) < 0.01

    def test_empty_dicts(self):
        from scripts.preenrich_shadow_diff import _jaccard_keys
        assert _jaccard_keys({}, {}) == 1.0


# ---------------------------------------------------------------------------
# _extract_text_from_field
# ---------------------------------------------------------------------------

class TestExtractTextField:
    def test_nested_dict(self):
        from scripts.preenrich_shadow_diff import _extract_text_from_field
        value = {"summary": "We build AI."}
        assert _extract_text_from_field(value, "summary") == "We build AI."

    def test_list_first_element_subpath(self):
        from scripts.preenrich_shadow_diff import _extract_text_from_field
        value = [{"description": "scale fast"}, {"description": "other"}]
        assert _extract_text_from_field(value, "description") == "scale fast"

    def test_missing_key_returns_empty(self):
        from scripts.preenrich_shadow_diff import _extract_text_from_field
        value = {"other_key": "value"}
        assert _extract_text_from_field(value, "summary") == ""

    def test_none_value_returns_empty(self):
        from scripts.preenrich_shadow_diff import _extract_text_from_field
        assert _extract_text_from_field(None, "summary") == ""


# ---------------------------------------------------------------------------
# _diff_stage: schema validity + gate
# ---------------------------------------------------------------------------

class TestDiffStage:
    def _no_embedding(self, texts, cache, api_key):
        """Stub that returns zero vectors (no cosine computed)."""
        return [[] for _ in texts]

    def test_pass_gate_when_schema_valid(self):
        """Jobs with valid shadow output -> schema validity 100% -> PASS."""
        from scripts.preenrich_shadow_diff import _diff_stage

        jobs = [
            _job_with_shadow(
                "persona",
                {"summary": "Senior ML engineer."},
                {"summary": "Senior ML engineer."},
                "persona",
            )
        ]

        with patch("scripts.preenrich_shadow_diff._embed_texts", self._no_embedding):
            result = _diff_stage("persona", jobs, {}, "")

        assert result["sample_size"] == 1
        assert result["schema_validity_pct"] == 100.0
        assert result["passes_gate"] is True

    def test_fail_gate_when_schema_invalid(self):
        """Jobs with null shadow output -> schema validity 0% -> FAIL."""
        from scripts.preenrich_shadow_diff import _diff_stage

        job = _job_with_shadow("persona", None, {"summary": "x"}, "persona")
        # Manually set shadow_output to exist but with None value
        job["pre_enrichment"]["stages"]["persona"]["shadow_output"] = {"persona": None}
        job["pre_enrichment"]["shadow_legacy_fields"]["persona"] = None

        with patch("scripts.preenrich_shadow_diff._embed_texts", self._no_embedding):
            result = _diff_stage("persona", [job], {}, "")

        assert result["schema_validity_pct"] == 0.0
        assert result["passes_gate"] is False

    def test_fail_gate_on_low_cosine(self):
        """Low cosine parity (mocked) causes gate FAIL."""
        from scripts.preenrich_shadow_diff import _diff_stage

        jobs = [
            _job_with_shadow(
                "persona",
                {"summary": "Shadow text completely different."},
                {"summary": "Live text about ML systems."},
                "persona",
            )
        ]

        # Return orthogonal vectors: cosine = 0
        def _low_cosine(texts, cache, api_key):
            vecs = [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ]
            return vecs[: len(texts)]

        with patch("scripts.preenrich_shadow_diff._embed_texts", _low_cosine):
            result = _diff_stage("persona", jobs, {}, "fake-key")

        assert result["cosine_mean"] is not None
        assert result["cosine_mean"] < 0.85
        assert result["passes_gate"] is False

    def test_pass_gate_on_high_cosine(self):
        """High cosine parity (mocked) does not block gate."""
        from scripts.preenrich_shadow_diff import _diff_stage

        jobs = [
            _job_with_shadow(
                "persona",
                {"summary": "Very similar text here."},
                {"summary": "Very similar text here."},
                "persona",
            )
        ]

        def _high_cosine(texts, cache, api_key):
            return [[1.0, 0.0], [1.0, 0.0]]

        with patch("scripts.preenrich_shadow_diff._embed_texts", _high_cosine):
            result = _diff_stage("persona", jobs, {}, "fake-key")

        assert result["passes_gate"] is True

    def test_no_shadow_data_returns_zero_sample(self):
        """Jobs without shadow data -> sample_size=0, passes_gate=False."""
        from scripts.preenrich_shadow_diff import _diff_stage

        job = {
            "_id": ObjectId(),
            "lifecycle": "completed",
            "persona": {"summary": "live text"},
            "pre_enrichment": {"stages": {}, "shadow_legacy_fields": {}},
        }

        with patch("scripts.preenrich_shadow_diff._embed_texts", self._no_embedding):
            result = _diff_stage("persona", [job], {}, "")

        assert result["sample_size"] == 0
        assert result["passes_gate"] is False
        assert "no shadow data" in result["gate_reason"]

    def test_embedding_cache_reused(self):
        """Repeated texts hit cache; API called only for unique texts."""
        from scripts.preenrich_shadow_diff import _embed_texts, _text_hash

        shared_text = "same text both times"
        api_call_count = {"n": 0}

        def _mock_openai_create(model, input):  # noqa: A002
            api_call_count["n"] += 1
            mock_data = [MagicMock(embedding=[0.1, 0.2]) for _ in input]
            mock_resp = MagicMock()
            mock_resp.data = mock_data
            return mock_resp

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = _mock_openai_create

        cache: Dict[str, List[float]] = {}

        with patch("openai.OpenAI", return_value=mock_client):
            # First call — should hit API
            _embed_texts([shared_text], cache, "fake-key")
            first_count = api_call_count["n"]

            # Second call — should use cache
            _embed_texts([shared_text], cache, "fake-key")
            second_count = api_call_count["n"]

        assert first_count == 1
        assert second_count == first_count, "Second call should have used cache, not called API"
        assert _text_hash(shared_text) in cache


# ---------------------------------------------------------------------------
# _render_markdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def _sample_result(self, stage: str, passes: bool) -> Dict[str, Any]:
        return {
            "stage": stage,
            "sample_size": 10,
            "schema_validity_pct": 100.0 if passes else 80.0,
            "cosine_mean": 0.92 if passes else 0.70,
            "cosine_p50": 0.93,
            "cosine_p5": 0.88,
            "structural_jaccard_mean": 0.95,
            "cost_usd_mean": 0.0005,
            "duration_ms_mean": 120.0,
            "passes_gate": passes,
            "gate_reason": "PASS" if passes else "cosine_mean=0.70 < 0.85",
            "top_divergence": [],
        }

    def test_overall_pass_header(self):
        from scripts.preenrich_shadow_diff import _render_markdown
        results = [self._sample_result("persona", True)]
        md = _render_markdown(results, overall_pass=True, generated_at="2026-04-17", limit=20, since=None)
        assert "**PASS**" in md

    def test_overall_fail_header(self):
        from scripts.preenrich_shadow_diff import _render_markdown
        results = [self._sample_result("persona", False)]
        md = _render_markdown(results, overall_pass=False, generated_at="2026-04-17", limit=20, since=None)
        assert "**FAIL**" in md

    def test_stage_row_in_table(self):
        from scripts.preenrich_shadow_diff import _render_markdown
        results = [self._sample_result("persona", True)]
        md = _render_markdown(results, overall_pass=True, generated_at="2026-04-17", limit=20, since=None)
        assert "persona" in md
        assert "PASS" in md

    def test_fail_stage_shows_reason(self):
        from scripts.preenrich_shadow_diff import _render_markdown
        results = [self._sample_result("persona", False)]
        md = _render_markdown(results, overall_pass=False, generated_at="2026-04-17", limit=20, since=None)
        assert "cosine_mean=0.70 < 0.85" in md

    def test_divergence_cases_section(self):
        from scripts.preenrich_shadow_diff import _render_markdown
        result = self._sample_result("persona", False)
        result["top_divergence"] = [
            {"job_id": "abc123", "stage": "persona", "field": "persona.summary", "cosine": 0.42}
        ]
        md = _render_markdown([result], overall_pass=False, generated_at="2026-04-17", limit=20, since=None)
        assert "abc123" in md
        assert "Top 5 Divergence" in md
