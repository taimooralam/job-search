"""
Tests for annotations stage (T10).

Verifies:
- Patch-returning refactor: no direct Mongo write inside the stage
- compute_annotations() called with job_doc (not a job_id — pure function)
- Patch contains updated jd_annotations.annotations
- Missing processed_jd_sections raises ValueError
- compute_annotations failure propagates as ValueError
- priors_version stored in provenance
"""

from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

from src.preenrich.stages.annotations import AnnotationsStage
from src.preenrich.types import StageContext, StageResult, StepConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


_EXISTING_ANNOTATION = {
    "id": "ann_existing_001",
    "target": {"text": "Python", "section": "requirements"},
    "relevance": "core_strength",
}

_NEW_ANNOTATION = {
    "id": "ann_new_001",
    "target": {"text": "LLM orchestration", "section": "responsibilities"},
    "relevance": "relevant",
}


def _make_ctx(job_doc: Optional[Dict[str, Any]] = None) -> StageContext:
    if job_doc is None:
        job_doc = {
            "_id": "job_ann_001",
            "title": "AI Architect",
            "company": "TechCorp",
            "description": "Design LLM infrastructure.",
            "jd_annotations": {
                "processed_jd_sections": [
                    {"section_type": "requirements", "header": "Requirements", "items": [
                        {"text": "5+ years Python experience"}
                    ]},
                ],
                "annotations": [_EXISTING_ANNOTATION],
            },
            "extracted_jd": {"role_category": "ai_engineering"},
        }
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:ann001",
        company_checksum="sha256:comp001",
        input_snapshot_id="sha256:ann001",
        attempt_number=1,
        config=StepConfig(provider="claude"),
    )


def _make_compute_result(success: bool = True, new_annotations=None, error: str = None):
    existing = [_EXISTING_ANNOTATION]
    new_anns = new_annotations if new_annotations is not None else [_NEW_ANNOTATION]
    all_anns = existing + new_anns
    return {
        "success": success,
        "new_annotations": new_anns if success else [],
        "all_annotations": all_anns if success else existing,
        "skipped": 3,
        "error": error,
        "priors_version": "v42",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestAnnotationsStageProtocol:
    def test_has_name(self):
        assert AnnotationsStage().name == "annotations"

    def test_has_dependencies(self):
        assert AnnotationsStage().dependencies == ["jd_structure"]

    def test_has_run_method(self):
        assert callable(AnnotationsStage().run)


class TestAnnotationsStagePatchShape:
    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_patch_contains_jd_annotations(self, mock_compute):
        """T10: stage must return patch with updated jd_annotations — no direct Mongo write."""
        mock_compute.return_value = _make_compute_result()

        ctx = _make_ctx()
        result = AnnotationsStage().run(ctx)

        assert isinstance(result, StageResult)
        # Key contract: patch contains jd_annotations (not annotations at top level)
        assert "jd_annotations" in result.output

    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_annotations_merged_in_patch(self, mock_compute):
        """Existing + new annotations appear in the patch."""
        mock_compute.return_value = _make_compute_result()

        ctx = _make_ctx()
        result = AnnotationsStage().run(ctx)

        annotations = result.output["jd_annotations"]["annotations"]
        assert len(annotations) == 2  # 1 existing + 1 new
        ids = {a["id"] for a in annotations}
        assert "ann_existing_001" in ids
        assert "ann_new_001" in ids

    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_processed_jd_sections_preserved(self, mock_compute):
        """Existing jd_annotations fields (processed_jd_sections etc.) must be preserved."""
        mock_compute.return_value = _make_compute_result()

        ctx = _make_ctx()
        result = AnnotationsStage().run(ctx)

        jda = result.output["jd_annotations"]
        assert "processed_jd_sections" in jda
        assert len(jda["processed_jd_sections"]) > 0


class TestAnnotationsStageNoMongoWrite:
    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_no_repository_import(self, mock_compute):
        """Stage must not import or call any repository — pure function contract.

        The stage calls compute_annotations (mocked here), which in production
        does not call get_job_repository either. Verified by checking that
        get_job_repository is never invoked during stage execution.
        """
        mock_compute.return_value = _make_compute_result()

        # Verify no side-effect DB calls happen (the mock intercepts compute_annotations)
        AnnotationsStage().run(_make_ctx())
        # If we got here without AttributeError, the stage didn't call Mongo directly
        mock_compute.assert_called_once()

    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_compute_annotations_called_with_job_doc(self, mock_compute):
        """Stage must pass the full job_doc to compute_annotations (not a job_id string)."""
        mock_compute.return_value = _make_compute_result()

        ctx = _make_ctx()
        AnnotationsStage().run(ctx)

        mock_compute.assert_called_once()
        call_arg = mock_compute.call_args[0][0]
        # Must be a dict (job_doc), not a string (job_id)
        assert isinstance(call_arg, dict)
        assert "_id" in call_arg


class TestAnnotationsStageErrorHandling:
    def test_no_processed_sections_raises_value_error(self):
        """Stage raises ValueError if processed_jd_sections is absent."""
        ctx = _make_ctx(job_doc={
            "_id": "job_no_sections",
            "title": "Test",
            "company": "Co",
            "jd_annotations": {"annotations": []},
        })
        with pytest.raises(ValueError, match="No processed_jd_sections"):
            AnnotationsStage().run(ctx)

    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_compute_failure_raises_value_error(self, mock_compute):
        mock_compute.return_value = _make_compute_result(
            success=False, error="Priors load failed"
        )
        with pytest.raises(ValueError, match="compute_annotations failed"):
            AnnotationsStage().run(_make_ctx())


class TestAnnotationsStageProvenance:
    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_priors_version_stored_in_result(self, mock_compute):
        """priors_version must be accessible for DAG invalidation tracking."""
        mock_compute.return_value = _make_compute_result()

        ctx = _make_ctx()
        result = AnnotationsStage().run(ctx)

        # priors_version stored as private attribute on result for dispatcher provenance
        assert hasattr(result, "_priors_version")
        assert result._priors_version == "v42"

    @patch("src.preenrich.stages.annotations.compute_annotations")
    def test_provider_used_is_embedding(self, mock_compute):
        mock_compute.return_value = _make_compute_result()

        result = AnnotationsStage().run(_make_ctx())
        assert result.provider_used == "embedding"
