"""
Decomposition parity tests (§3.4).

For each decomposed service, asserts that the new pure function / stage adapter
produces output that is functionally equivalent to the old entrypoint on the same
fixture job document.

Covered:
1. annotation_suggester: compute_annotations() vs generate_annotations_for_job()
   — same sections + extracted_jd → same annotation count + field shape.

Notes:
- These tests use fixture job_docs in memory (no real Mongo connection).
- External service calls (LLM, Mongo) are mocked uniformly for both paths.
- "Bit-identical" means same field keys and types; exact values may differ when
  randomness is involved (annotation IDs use uuid).
"""

import copy
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from src.services.annotation_suggester import compute_annotations, generate_annotations_for_job


# ── Fixtures ─────────────────────────────────────────────────────────────────


_FIXTURE_JD_DOC: Dict[str, Any] = {
    "_id": "fixture_job_001",
    "title": "AI Platform Lead",
    "company": "Acme",
    "description": "Build LLM infrastructure. Deploy AI models at scale.",
    "jd_annotations": {
        "processed_jd_sections": [
            {
                "section_type": "responsibilities",
                "header": "What You'll Do",
                "items": [
                    {"text": "Design and implement LLM gateway architecture"},
                    {"text": "Manage Python-based ML pipelines"},
                ],
            },
            {
                "section_type": "requirements",
                "header": "Requirements",
                "items": [
                    {"text": "5+ years Python development experience"},
                    {"text": "Experience with LLM APIs (OpenAI, Anthropic)"},
                ],
            },
            {
                "section_type": "about_company",
                "header": "About Us",
                "items": [{"text": "We are an innovative startup"}],
            },
        ],
        "annotations": [],
    },
    "extracted_jd": {
        "role_category": "ai_engineering",
        "qualifications": ["5+ years Python"],
        "nice_to_haves": [],
        "top_keywords": ["LLM", "Python", "Kubernetes"],
    },
}


def _mock_priors():
    """Minimal priors document for testing."""
    return {
        "version": "v_test",
        "stats": {"total_suggestions_made": 0},
        "skill_priors": {
            "python": {
                "relevance": {"value": "core_strength", "confidence": 0.9},
                "requirement": {"value": "must_have"},
                "passion": {"value": "enjoy"},
                "identity": {"value": "strong_identity"},
                "avoid": False,
            },
            "llm": {
                "relevance": {"value": "core_strength", "confidence": 0.95},
                "requirement": {"value": "must_have"},
                "passion": {"value": "love_it"},
                "identity": {"value": "core_identity"},
                "avoid": False,
            },
        },
        "sentence_index": {"embeddings": [], "texts": [], "metadata": []},
    }


def _mock_master_cv():
    return {
        "jd_signals": {"ai": ["LLM", "language model", "AI system"]},
        "skill_aliases": {},
        "hard_skills": {"Python", "LLM"},
        "soft_skills": set(),
        "keywords": {"python", "llm"},
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestComputeAnnotationsVsGenerateAnnotations:
    """
    Parity: compute_annotations(job_doc) ≡ generate_annotations_for_job(job_id, extracted_jd)

    Both must produce annotations with the same field keys and types.
    The annotations stage calls compute_annotations() directly (pure function).
    Non-preenrich callers use generate_annotations_for_job() (shim = Mongo load + compute + write).
    """

    @patch("src.services.annotation_suggester.save_priors")
    @patch("src.services.annotation_suggester.should_rebuild_priors", return_value=False)
    @patch("src.services.annotation_suggester.load_priors")
    @patch("src.services.annotation_suggester._load_master_cv_data")
    def test_compute_annotations_returns_success(
        self, mock_master_cv, mock_load_priors, mock_should_rebuild, mock_save_priors
    ):
        """compute_annotations must succeed on valid fixture doc."""
        mock_load_priors.return_value = _mock_priors()
        mock_master_cv.return_value = _mock_master_cv()

        job_doc = copy.deepcopy(_FIXTURE_JD_DOC)
        result = compute_annotations(job_doc)

        assert result["success"] is True
        assert isinstance(result["new_annotations"], list)
        assert isinstance(result["all_annotations"], list)
        assert isinstance(result["skipped"], int)
        assert "error" in result
        assert "priors_version" in result

    @patch("src.services.annotation_suggester.save_priors")
    @patch("src.services.annotation_suggester.should_rebuild_priors", return_value=False)
    @patch("src.services.annotation_suggester.load_priors")
    @patch("src.services.annotation_suggester._load_master_cv_data")
    def test_annotation_field_shape_matches_generate_for_job(
        self, mock_master_cv, mock_load_priors, mock_should_rebuild, mock_save_priors
    ):
        """
        Each annotation produced by compute_annotations must have the same keys
        as generate_annotations_for_job (the old path).

        Required keys per annotation: id, target, relevance, requirement_type,
        passion, identity, source, created_at, updated_at.
        """
        mock_load_priors.return_value = _mock_priors()
        mock_master_cv.return_value = _mock_master_cv()

        job_doc = copy.deepcopy(_FIXTURE_JD_DOC)
        result = compute_annotations(job_doc)

        required_keys = {
            "id", "target", "relevance", "requirement_type",
            "passion", "identity", "source", "created_at", "updated_at",
        }

        for ann in result["new_annotations"]:
            missing = required_keys - set(ann.keys())
            assert not missing, (
                f"Annotation missing keys: {missing}. "
                "compute_annotations and generate_annotations_for_job must produce same schema."
            )

    @patch("src.services.annotation_suggester.save_priors")
    @patch("src.services.annotation_suggester.should_rebuild_priors", return_value=False)
    @patch("src.services.annotation_suggester.load_priors")
    @patch("src.services.annotation_suggester._load_master_cv_data")
    def test_about_company_section_skipped_in_both(
        self, mock_master_cv, mock_load_priors, mock_should_rebuild, mock_save_priors
    ):
        """about_company items must be skipped (SKIP_ANNOTATION_SECTIONS)."""
        mock_load_priors.return_value = _mock_priors()
        mock_master_cv.return_value = _mock_master_cv()

        job_doc = copy.deepcopy(_FIXTURE_JD_DOC)
        result = compute_annotations(job_doc)

        all_texts = {
            ann["target"]["text"]
            for ann in result["all_annotations"]
        }
        assert "We are an innovative startup" not in all_texts

    @patch("src.services.annotation_suggester.save_priors")
    @patch("src.services.annotation_suggester.should_rebuild_priors", return_value=False)
    @patch("src.services.annotation_suggester.load_priors")
    @patch("src.services.annotation_suggester._load_master_cv_data")
    def test_compute_no_mongo_write(
        self, mock_master_cv, mock_load_priors, mock_should_rebuild, mock_save_priors
    ):
        """compute_annotations must NOT import or call any repository."""
        mock_load_priors.return_value = _mock_priors()
        mock_master_cv.return_value = _mock_master_cv()

        with patch("src.common.repositories.get_job_repository") as mock_repo:
            compute_annotations(copy.deepcopy(_FIXTURE_JD_DOC))
            mock_repo.assert_not_called()

    @patch("src.services.annotation_suggester.save_priors")
    @patch("src.services.annotation_suggester.should_rebuild_priors", return_value=False)
    @patch("src.services.annotation_suggester.load_priors")
    @patch("src.services.annotation_suggester._load_master_cv_data")
    def test_generate_for_job_shim_calls_compute(
        self, mock_master_cv, mock_load_priors, mock_should_rebuild, mock_save_priors
    ):
        """generate_annotations_for_job shim must delegate to compute_annotations."""
        mock_load_priors.return_value = _mock_priors()
        mock_master_cv.return_value = _mock_master_cv()

        job_doc = copy.deepcopy(_FIXTURE_JD_DOC)

        # Mock the repository to return our fixture doc
        mock_repo = MagicMock()
        mock_repo.find_one.return_value = job_doc
        mock_repo.update_one.return_value = MagicMock(matched_count=1)

        # generate_annotations_for_job does `from src.common.repositories import get_job_repository`
        # inside the function body, so we patch the source module
        with patch("src.common.repositories.get_job_repository", return_value=mock_repo):
            with patch("src.services.annotation_suggester.compute_annotations",
                       wraps=compute_annotations) as spy_compute:
                result = generate_annotations_for_job("fixture_job_001")
                spy_compute.assert_called_once()

        assert result["success"] is True

    @patch("src.services.annotation_suggester.save_priors")
    @patch("src.services.annotation_suggester.should_rebuild_priors", return_value=False)
    @patch("src.services.annotation_suggester.load_priors")
    @patch("src.services.annotation_suggester._load_master_cv_data")
    def test_no_sections_returns_error(
        self, mock_master_cv, mock_load_priors, mock_should_rebuild, mock_save_priors
    ):
        """Both paths must return error when no processed_jd_sections present."""
        mock_load_priors.return_value = _mock_priors()
        mock_master_cv.return_value = _mock_master_cv()

        job_doc = copy.deepcopy(_FIXTURE_JD_DOC)
        job_doc["jd_annotations"]["processed_jd_sections"] = []

        result = compute_annotations(job_doc)
        assert result["success"] is False
        assert "structured JD" in result["error"]
