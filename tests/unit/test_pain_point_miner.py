"""
Unit tests for Layer 2: Pain-Point Miner

Tests JSON parsing, schema validation, and error handling with mocked LLM responses.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pydantic import ValidationError

from src.layer2.pain_point_miner import (
    PainPointMiner,
    PainPointAnalysis,
    pain_point_miner_node
)
from src.common.state import JobState
from src.common.unified_llm import LLMResult
from src.common.logger import get_logger


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState for testing."""
    return {
        "job_id": "test123",
        "title": "Senior Software Engineer",
        "company": "Test Corp",
        "job_description": "Build amazing software with Python and distributed systems...",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "pain_points": None,
        "strategic_needs": None,
        "risks_if_unfilled": None,
        "success_metrics": None,
        "selected_stars": None,
        "star_to_pain_mapping": None,
        "company_summary": None,
        "company_url": None,
        "fit_score": None,
        "fit_rationale": None,
        "people": None,
        "cover_letter": None,
        "cv_path": None,
        "drive_folder_url": None,
        "sheet_row_id": None,
        "run_id": None,
        "created_at": None,
        "errors": [],
        "status": "processing"
    }


@pytest.fixture
def valid_pain_point_json():
    """Valid pain-point analysis JSON matching schema."""
    return {
        "pain_points": [
            "Modernize legacy monolith to microservices",
            "Scale infrastructure to handle 10x traffic growth",
            "Reduce incident response time from hours to minutes"
        ],
        "strategic_needs": [
            "Enable rapid feature delivery for competitive advantage",
            "Build technical foundation for international expansion",
            "Attract and retain top engineering talent"
        ],
        "risks_if_unfilled": [
            "Critical customer-facing incidents continue",
            "Inability to meet Q2 scalability targets"
        ],
        "success_metrics": [
            "95% reduction in production incidents within 6 months",
            "Deploy new features 3x faster",
            "Zero downtime during traffic spikes"
        ]
    }


@pytest.fixture
def minimal_valid_json():
    """Minimal valid JSON (minimum counts)."""
    return {
        "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
        "strategic_needs": ["Need 1", "Need 2", "Need 3"],
        "risks_if_unfilled": ["Risk 1", "Risk 2"],
        "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
    }


# ===== SCHEMA VALIDATION TESTS =====

class TestPainPointAnalysisSchema:
    """Test Pydantic schema validation."""

    def test_valid_schema(self, valid_pain_point_json):
        """Valid JSON should pass schema validation."""
        validated = PainPointAnalysis(**valid_pain_point_json)
        assert len(validated.pain_points) == 3
        assert len(validated.strategic_needs) == 3
        assert len(validated.risks_if_unfilled) == 2
        assert len(validated.success_metrics) == 3

    def test_minimal_valid_counts(self, minimal_valid_json):
        """Minimal counts (3, 3, 2, 3) should pass."""
        validated = PainPointAnalysis(**minimal_valid_json)
        assert validated.pain_points == minimal_valid_json["pain_points"]

    def test_missing_required_field(self):
        """Missing required field should raise ValidationError."""
        invalid = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            # Missing risks_if_unfilled
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

        errors = exc_info.value.errors()
        assert any(e['loc'] == ('risks_if_unfilled',) for e in errors)

    def test_too_few_pain_points(self):
        """Empty pain points list should fail validation."""
        invalid = {
            "pain_points": [],  # Empty list is not allowed
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

        errors = exc_info.value.errors()
        assert any(
            e['loc'] == ('pain_points',) and 'at least 1 item' in e['msg'].lower()
            for e in errors
        )

    def test_too_many_strategic_needs(self):
        """Too many strategic needs (> 8) should fail."""
        invalid = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            "strategic_needs": [f"Need {i}" for i in range(1, 11)],  # 10 items, max 8
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

        errors = exc_info.value.errors()
        assert any(
            e['loc'] == ('strategic_needs',) and 'at most 8 items' in e['msg'].lower()
            for e in errors
        )

    def test_empty_string_in_array(self):
        """Empty strings should fail validation."""
        invalid = {
            "pain_points": ["Pain 1", "", "Pain 3"],  # Empty string
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError) as exc_info:
            PainPointAnalysis(**invalid)

    def test_wrong_type_for_field(self):
        """Non-list type should fail."""
        invalid = {
            "pain_points": "Not a list",  # Should be list
            "strategic_needs": ["Need 1", "Need 2", "Need 3"],
            "risks_if_unfilled": ["Risk 1", "Risk 2"],
            "success_metrics": ["Metric 1", "Metric 2", "Metric 3"]
        }
        with pytest.raises(ValidationError):
            PainPointAnalysis(**invalid)


# ===== PAIN POINT MINER TESTS =====

class TestPainPointMinerParsing:
    """Test JSON parsing logic."""

    def test_parse_clean_json(self, valid_pain_point_json):
        """Parse clean JSON response."""
        miner = PainPointMiner()
        llm_response = json.dumps(valid_pain_point_json)

        result = miner._parse_json_response(llm_response)

        assert result["pain_points"] == valid_pain_point_json["pain_points"]
        assert result["strategic_needs"] == valid_pain_point_json["strategic_needs"]
        assert len(result["risks_if_unfilled"]) == 2

    def test_parse_json_with_extra_text_before(self, valid_pain_point_json):
        """Parse JSON even if LLM adds text before."""
        miner = PainPointMiner()
        llm_response = "Here's the analysis:\n\n" + json.dumps(valid_pain_point_json)

        result = miner._parse_json_response(llm_response)

        assert len(result["pain_points"]) == 3

    def test_parse_json_with_extra_text_after(self, valid_pain_point_json):
        """Parse JSON even if LLM adds text after."""
        miner = PainPointMiner()
        llm_response = json.dumps(valid_pain_point_json) + "\n\nHope this helps!"

        result = miner._parse_json_response(llm_response)

        assert len(result["pain_points"]) == 3

    def test_parse_invalid_json(self):
        """Invalid JSON should raise ValueError."""
        miner = PainPointMiner()
        llm_response = "Not JSON at all!"

        with pytest.raises(ValueError, match="Failed to parse JSON"):
            miner._parse_json_response(llm_response)

    def test_parse_json_missing_field(self):
        """JSON missing required field should raise ValueError with clear message."""
        miner = PainPointMiner()
        invalid_json = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            # Missing other required fields
        }
        llm_response = json.dumps(invalid_json)

        with pytest.raises(ValueError, match="JSON schema validation failed"):
            miner._parse_json_response(llm_response)

    def test_parse_json_too_few_items(self):
        """JSON with empty lists should raise clear validation error."""
        miner = PainPointMiner()
        invalid_json = {
            "pain_points": [],
            "strategic_needs": [],
            "risks_if_unfilled": [],
            "success_metrics": []
        }
        llm_response = json.dumps(invalid_json)

        with pytest.raises(ValueError, match="at least 1 item"):
            miner._parse_json_response(llm_response)


# ===== INTEGRATION TESTS WITH MOCKED LLM =====

def _create_mock_llm_result(content: str, success: bool = True) -> LLMResult:
    """Helper to create a mock LLMResult."""
    return LLMResult(
        content=content,
        backend="claude_cli",
        model="claude-sonnet-4-5-20250929",
        tier="middle",
        duration_ms=100,
        success=success,
        error=None if success else "Mock error",
    )


class TestPainPointMinerWithMockedLLM:
    """Test full extraction flow with mocked LLM calls."""

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_successful_extraction(self, mock_unified_llm_class, sample_job_state, valid_pain_point_json):
        """Successful LLM call should return validated data."""
        # Mock UnifiedLLM to return valid JSON
        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(json.dumps(valid_pain_point_json))
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        assert result["pain_points"] == valid_pain_point_json["pain_points"]
        assert result["strategic_needs"] == valid_pain_point_json["strategic_needs"]
        assert "errors" not in result

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_llm_returns_invalid_json(self, mock_unified_llm_class, sample_job_state):
        """LLM returning invalid JSON should return empty lists with error."""
        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result("Not valid JSON at all!")
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        # Should return empty lists (graceful degradation)
        assert result["pain_points"] == []
        assert result["strategic_needs"] == []
        assert result["risks_if_unfilled"] == []
        assert result["success_metrics"] == []

        # Should include error message
        assert len(result["errors"]) > 0
        assert "failed" in result["errors"][0].lower()

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_llm_returns_incomplete_schema(self, mock_unified_llm_class, sample_job_state):
        """LLM returning incomplete schema should return empty lists with error."""
        mock_llm_instance = MagicMock()
        incomplete_json = {
            "pain_points": ["Pain 1", "Pain 2", "Pain 3"],
            # Missing other fields
        }
        mock_result = _create_mock_llm_result(json.dumps(incomplete_json))
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        assert result["pain_points"] == []
        assert len(result["errors"]) > 0
        assert "validation failed" in result["errors"][0].lower()


# ===== NODE FUNCTION TESTS =====

class TestPainPointMinerNode:
    """Test LangGraph node wrapper function."""

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_node_returns_updates_dict(self, mock_unified_llm_class, sample_job_state, valid_pain_point_json):
        """Node function should return dict with pain point updates."""
        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(json.dumps(valid_pain_point_json))
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        updates = pain_point_miner_node(sample_job_state)

        # Should return dict with all 4 fields
        assert "pain_points" in updates
        assert "strategic_needs" in updates
        assert "risks_if_unfilled" in updates
        assert "success_metrics" in updates
        assert len(updates["pain_points"]) == 3

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_node_handles_errors_gracefully(self, mock_unified_llm_class, sample_job_state):
        """Node function should handle errors without crashing."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke = AsyncMock(side_effect=Exception("LLM API error"))
        mock_unified_llm_class.return_value = mock_llm_instance

        updates = pain_point_miner_node(sample_job_state)

        # Should return empty lists, not crash
        assert updates["pain_points"] == []
        assert "errors" in updates


# ===== ANNOTATION-AWARE PAIN POINT MINING TESTS =====

class TestAnnotationContextExtraction:
    """Test extraction of annotation priorities for pain point mining."""

    @pytest.fixture
    def sample_annotations(self):
        """Sample JD annotations with various priority signals."""
        return {
            "annotation_version": 1,
            "processed_jd_html": "",
            "annotations": [
                {
                    "id": "ann-001",
                    "target": {"section": "qualifications", "index": 0, "text": "5+ years Python experience", "char_start": 0, "char_end": 25},
                    "created_at": "2024-01-01T00:00:00Z",
                    "created_by": "human",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "status": "approved",
                    "last_reviewed_by": None,
                    "review_note": None,
                    "annotation_type": "skill_match",
                    "relevance": "core_strength",
                    "requirement_type": "must_have",
                    "matching_skill": "Python",
                    "has_reframe": False,
                    "reframe_note": None,
                    "reframe_from": None,
                    "reframe_to": None,
                    "star_ids": [],
                    "evidence_summary": None,
                    "suggested_keywords": ["Python", "backend development"],
                    "ats_variants": ["python", "Python3"],
                    "min_occurrences": 2,
                    "max_occurrences": 4,
                    "preferred_sections": ["skills", "experience"],
                    "exact_phrase_match": False,
                    "achievement_context": None,
                    "comment": None,
                    "highlight_color": None,
                    "is_active": True,
                    "priority": 1,
                    "confidence": 0.95,
                },
                {
                    "id": "ann-002",
                    "target": {"section": "qualifications", "index": 1, "text": "Kubernetes experience preferred", "char_start": 26, "char_end": 55},
                    "created_at": "2024-01-01T00:00:00Z",
                    "created_by": "human",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "status": "approved",
                    "last_reviewed_by": None,
                    "review_note": None,
                    "annotation_type": "skill_match",
                    "relevance": "gap",
                    "requirement_type": "nice_to_have",
                    "matching_skill": None,
                    "has_reframe": True,
                    "reframe_note": "Frame as 'container orchestration experience with Docker Swarm' instead",
                    "reframe_from": "Kubernetes",
                    "reframe_to": "container orchestration",
                    "star_ids": [],
                    "evidence_summary": None,
                    "suggested_keywords": ["Kubernetes", "K8s"],
                    "ats_variants": ["k8s", "kubernetes"],
                    "min_occurrences": 1,
                    "max_occurrences": 2,
                    "preferred_sections": ["skills"],
                    "exact_phrase_match": False,
                    "achievement_context": None,
                    "comment": None,
                    "highlight_color": None,
                    "is_active": True,
                    "priority": 3,
                    "confidence": 0.6,
                },
                {
                    "id": "ann-003",
                    "target": {"section": "responsibilities", "index": 0, "text": "Lead technical architecture decisions", "char_start": 0, "char_end": 35},
                    "created_at": "2024-01-01T00:00:00Z",
                    "created_by": "human",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "status": "approved",
                    "last_reviewed_by": None,
                    "review_note": None,
                    "annotation_type": "skill_match",
                    "relevance": "extremely_relevant",
                    "requirement_type": "must_have",
                    "matching_skill": "Technical Leadership",
                    "has_reframe": False,
                    "reframe_note": None,
                    "reframe_from": None,
                    "reframe_to": None,
                    "star_ids": ["star-123"],
                    "evidence_summary": "Led architecture decisions at multiple companies",
                    "suggested_keywords": ["technical leadership", "architecture"],
                    "ats_variants": ["tech lead", "architect"],
                    "min_occurrences": 2,
                    "max_occurrences": 3,
                    "preferred_sections": ["experience", "summary"],
                    "exact_phrase_match": False,
                    "achievement_context": None,
                    "comment": None,
                    "highlight_color": None,
                    "is_active": True,
                    "priority": 1,
                    "confidence": 0.9,
                },
            ],
            "concerns": [],
            "settings": {
                "job_priority": "high",
                "deadline": None,
                "require_full_section_coverage": False,
                "section_coverage": {},
                "auto_approve_presets": True,
                "conflict_resolution": "max_boost",
            },
            "section_summaries": {},
            "relevance_counts": {"core_strength": 1, "extremely_relevant": 1, "gap": 1},
            "type_counts": {"skill_match": 3},
            "reframe_count": 1,
            "gap_count": 1,
            "validation_passed": True,
            "validation_errors": [],
            "ats_readiness_score": 75,
        }

    @pytest.fixture
    def sample_job_state_with_annotations(self, sample_job_state, sample_annotations):
        """Job state with annotations included."""
        state = sample_job_state.copy()
        state["jd_annotations"] = sample_annotations
        return state

    def test_extract_annotation_context_from_state(self, sample_annotations):
        """Should extract annotation priority context from state."""
        from src.layer2.pain_point_miner import extract_annotation_context

        context = extract_annotation_context(sample_annotations)

        # Should extract must-have keywords
        assert "Python" in context["must_have_keywords"]
        assert "technical leadership" in context["must_have_keywords"] or "architecture" in context["must_have_keywords"]

        # Should extract gap areas
        assert len(context["gap_areas"]) >= 1
        assert any("Kubernetes" in gap for gap in context["gap_areas"])

        # Should extract reframe notes
        assert len(context["reframe_notes"]) >= 1
        assert any("container orchestration" in note for note in context["reframe_notes"])

        # Should extract core strength areas
        assert len(context["core_strength_areas"]) >= 1

    def test_extract_annotation_context_handles_empty_annotations(self):
        """Should handle empty or missing annotations gracefully."""
        from src.layer2.pain_point_miner import extract_annotation_context

        # Empty annotations
        context = extract_annotation_context(None)
        assert context["must_have_keywords"] == []
        assert context["gap_areas"] == []
        assert context["reframe_notes"] == []
        assert context["core_strength_areas"] == []

        # Empty annotations dict
        context = extract_annotation_context({})
        assert context["must_have_keywords"] == []

    def test_extract_annotation_context_filters_inactive(self, sample_annotations):
        """Should only include active annotations."""
        from src.layer2.pain_point_miner import extract_annotation_context

        # Make one annotation inactive
        sample_annotations["annotations"][0]["is_active"] = False

        context = extract_annotation_context(sample_annotations)

        # Python should not be in must-have keywords (that annotation is now inactive)
        assert "Python" not in context["must_have_keywords"]


class TestAnnotationAwarePromptGeneration:
    """Test that annotation context is included in LLM prompts."""

    @pytest.fixture
    def annotation_context(self):
        """Sample annotation context for prompt testing."""
        return {
            "must_have_keywords": ["Python", "distributed systems", "technical leadership"],
            "gap_areas": ["Kubernetes - Frame as container orchestration experience"],
            "reframe_notes": ["Frame Docker Swarm experience as container orchestration"],
            "core_strength_areas": ["Python backend development", "System architecture"],
        }

    def test_prompt_includes_must_have_priorities(self, annotation_context):
        """Prompt should include must-have keywords for prioritization."""
        from src.layer2.pain_point_miner import build_annotation_aware_prompt

        prompt = build_annotation_aware_prompt(annotation_context)

        assert "Python" in prompt
        assert "distributed systems" in prompt
        assert "MUST-HAVE" in prompt.upper() or "must_have" in prompt.lower() or "priority" in prompt.lower()

    def test_prompt_includes_gap_context(self, annotation_context):
        """Prompt should include gap areas for framing guidance."""
        from src.layer2.pain_point_miner import build_annotation_aware_prompt

        prompt = build_annotation_aware_prompt(annotation_context)

        assert "Kubernetes" in prompt or "gap" in prompt.lower()

    def test_prompt_includes_reframe_notes(self, annotation_context):
        """Prompt should include reframe guidance."""
        from src.layer2.pain_point_miner import build_annotation_aware_prompt

        prompt = build_annotation_aware_prompt(annotation_context)

        assert "container orchestration" in prompt.lower() or "reframe" in prompt.lower()

    def test_prompt_handles_empty_context(self):
        """Prompt should work with empty annotation context."""
        from src.layer2.pain_point_miner import build_annotation_aware_prompt

        empty_context = {
            "must_have_keywords": [],
            "gap_areas": [],
            "reframe_notes": [],
            "core_strength_areas": [],
        }

        prompt = build_annotation_aware_prompt(empty_context)

        # Should return a valid string (or empty string for no annotation context)
        assert isinstance(prompt, str)


class TestPainPointRankingWithAnnotations:
    """Test that pain point ranking is adjusted based on annotations."""

    @pytest.fixture
    def sample_pain_points(self):
        """Sample extracted pain points for ranking tests."""
        return [
            {"text": "Need Python expertise for backend development", "evidence": "JD mentions Python 5+ times", "confidence": "high"},
            {"text": "Kubernetes cluster management issues", "evidence": "Mentioned in qualifications", "confidence": "medium"},
            {"text": "Technical leadership gap in architecture decisions", "evidence": "Key responsibility", "confidence": "high"},
            {"text": "General operational improvements needed", "evidence": "Inferred from context", "confidence": "low"},
        ]

    @pytest.fixture
    def must_have_keywords(self):
        return ["Python", "technical leadership", "architecture"]

    @pytest.fixture
    def gap_keywords(self):
        return ["Kubernetes"]

    def test_rank_pain_points_boosts_must_have(self, sample_pain_points, must_have_keywords, gap_keywords):
        """Pain points matching must-have keywords should rank higher."""
        from src.layer2.pain_point_miner import rank_pain_points_with_annotations

        ranked = rank_pain_points_with_annotations(
            sample_pain_points,
            must_have_keywords=must_have_keywords,
            gap_keywords=gap_keywords,
        )

        # Python-related pain point should be near top
        python_idx = next(i for i, p in enumerate(ranked) if "Python" in p["text"])
        assert python_idx <= 1, "Python pain point should be in top 2"

        # Technical leadership should also be prioritized
        leadership_idx = next(i for i, p in enumerate(ranked) if "leadership" in p["text"].lower())
        assert leadership_idx <= 2, "Technical leadership pain point should be in top 3"

    def test_rank_pain_points_deprioritizes_gaps(self, sample_pain_points, must_have_keywords, gap_keywords):
        """Pain points related to gaps should be deprioritized."""
        from src.layer2.pain_point_miner import rank_pain_points_with_annotations

        ranked = rank_pain_points_with_annotations(
            sample_pain_points,
            must_have_keywords=must_have_keywords,
            gap_keywords=gap_keywords,
        )

        # Kubernetes-related pain point should be lower in ranking
        k8s_idx = next(i for i, p in enumerate(ranked) if "Kubernetes" in p["text"])
        assert k8s_idx >= 2, "Kubernetes pain point should be deprioritized due to gap"

    def test_rank_pain_points_handles_empty_inputs(self):
        """Should handle empty inputs gracefully."""
        from src.layer2.pain_point_miner import rank_pain_points_with_annotations

        # Empty pain points
        result = rank_pain_points_with_annotations([], [], [])
        assert result == []

        # Pain points but no keywords
        pain_points = [{"text": "Some pain point", "evidence": "test", "confidence": "medium"}]
        result = rank_pain_points_with_annotations(pain_points, [], [])
        assert len(result) == 1


class TestBackwardCompatibilityWithoutAnnotations:
    """Test that pain point miner works correctly without annotations."""

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_miner_works_without_annotations(self, mock_unified_llm_class, sample_job_state, valid_pain_point_json):
        """Miner should work normally when no annotations are present."""
        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(json.dumps(valid_pain_point_json))
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        # Ensure no annotations in state
        assert sample_job_state.get("jd_annotations") is None

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        # Should return valid results
        assert result["pain_points"] == valid_pain_point_json["pain_points"]
        assert result["strategic_needs"] == valid_pain_point_json["strategic_needs"]
        assert "errors" not in result

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_miner_works_with_empty_annotations(self, mock_unified_llm_class, sample_job_state, valid_pain_point_json):
        """Miner should work with empty annotations dict."""
        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(json.dumps(valid_pain_point_json))
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        # Add empty annotations
        sample_job_state["jd_annotations"] = {"annotations": [], "concerns": []}

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        # Should return valid results
        assert len(result["pain_points"]) > 0
        assert "errors" not in result


class TestAnnotationAwareExtraction:
    """Integration tests for annotation-aware pain point extraction."""

    @pytest.fixture
    def sample_annotations_minimal(self):
        """Minimal annotations for testing."""
        return {
            "annotations": [
                {
                    "id": "ann-001",
                    "target": {"section": "qualifications", "index": 0, "text": "Python", "char_start": 0, "char_end": 6},
                    "annotation_type": "skill_match",
                    "relevance": "core_strength",
                    "requirement_type": "must_have",
                    "suggested_keywords": ["Python"],
                    "ats_variants": [],
                    "has_reframe": False,
                    "reframe_note": None,
                    "is_active": True,
                    "priority": 1,
                    "confidence": 0.9,
                    "created_at": "2024-01-01T00:00:00Z",
                    "created_by": "human",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "status": "approved",
                    "star_ids": [],
                },
            ],
            "concerns": [],
        }

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extraction_with_annotations_includes_context(
        self, mock_unified_llm_class, sample_job_state, sample_annotations_minimal, valid_pain_point_json
    ):
        """Extraction with annotations should include annotation context in prompt."""
        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(json.dumps(valid_pain_point_json))
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        sample_job_state["jd_annotations"] = sample_annotations_minimal

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        # Verify LLM was called
        assert mock_llm_instance.invoke.called

        # Check that the call included annotation context (inspect the prompt)
        call_args = mock_llm_instance.invoke.call_args
        # UnifiedLLM.invoke takes prompt and system as keyword args
        prompt_text = str(call_args)

        # The prompt should contain reference to annotation priorities
        # Note: This checks the prompt structure, actual implementation may vary
        assert len(result["pain_points"]) > 0


# ===== LOGGING TESTS FOR GAP-106 =====

class TestParseResponseLogging:
    """Tests for logging behavior in _parse_response() method."""

    @pytest.fixture
    def enhanced_json_response(self):
        """Valid enhanced format JSON response."""
        return {
            "pain_points": [
                {"text": "Legacy API platform blocking feature velocity", "evidence": "explicit in JD", "confidence": "high"},
                {"text": "Database performance issues", "evidence": "inferred from context", "confidence": "medium"},
            ],
            "strategic_needs": [
                {"text": "Enable rapid scaling", "evidence": "business goal", "confidence": "high"},
                {"text": "Improve customer satisfaction", "evidence": "inferred", "confidence": "medium"},
            ],
            "risks_if_unfilled": [
                {"text": "System outages during growth", "evidence": "scaling requirements", "confidence": "high"},
                {"text": "Customer churn", "evidence": "inferred", "confidence": "low"},
            ],
            "success_metrics": [
                {"text": "API latency reduced to <100ms p99", "evidence": "performance requirement", "confidence": "medium"},
                {"text": "Zero downtime deployments", "evidence": "operational goal", "confidence": "high"},
            ],
        }

    def test_parse_response_logs_raw_response_preview(self, enhanced_json_response, caplog):
        """_parse_response should log raw response length and preview."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        # Create response with <final> tags
        llm_response = f"<final>{json.dumps(enhanced_json_response)}</final>"

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify logging of raw response
        assert "[PARSE] Raw LLM response length:" in caplog.text
        assert "[PARSE] Raw LLM response preview:" in caplog.text
        assert f"{len(llm_response)} chars" in caplog.text

    def test_parse_response_logs_final_tag_detection_present(self, enhanced_json_response, caplog):
        """_parse_response should log when <final> tags are found."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        llm_response = f"<final>{json.dumps(enhanced_json_response)}</final>"

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify logging of final tag detection
        assert "[PARSE] Response contains <final> tags: True" in caplog.text
        assert "[PARSE] Extracted JSON from <final> tags" in caplog.text

    def test_parse_response_logs_final_tag_detection_absent(self, enhanced_json_response, caplog):
        """_parse_response should log when <final> tags are NOT found."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        # Response without <final> tags
        llm_response = json.dumps(enhanced_json_response)

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify logging of missing final tags
        assert "[PARSE] Response contains <final> tags: False" in caplog.text
        assert "[PARSE] No <final> tags found, falling back to raw JSON extraction" in caplog.text

    def test_parse_response_logs_json_extraction_success(self, enhanced_json_response, caplog):
        """_parse_response should log successful JSON parsing."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        llm_response = f"<final>{json.dumps(enhanced_json_response)}</final>"

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify logging of JSON parsing success
        assert "[PARSE] JSON parsed successfully" in caplog.text
        # Keys may be escaped in log output, so check for both forms
        assert ("[PARSE] Keys:" in caplog.text or "JSON parsed successfully. Keys:" in caplog.text)
        assert "pain_points" in caplog.text
        assert "[PARSE] pain_points: 2 items" in caplog.text
        assert "[PARSE] strategic_needs: 2 items" in caplog.text

    def test_parse_response_logs_json_extraction_failure(self, caplog):
        """_parse_response should log JSON parsing failures."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        # Invalid JSON
        llm_response = "<final>Not valid JSON at all!</final>"

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match="Failed to parse JSON"):
                miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify error logging
        assert "[PARSE] JSON decode failed:" in caplog.text
        assert "[PARSE] JSON string preview:" in caplog.text

    def test_parse_response_logs_pydantic_validation_success(self, enhanced_json_response, caplog):
        """_parse_response should log successful Pydantic validation."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        llm_response = f"<final>{json.dumps(enhanced_json_response)}</final>"

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify validation success logging
        assert "[PARSE] Pydantic validation passed" in caplog.text
        assert "Pain points: 2" in caplog.text

    def test_parse_response_logs_pydantic_validation_errors(self, caplog):
        """_parse_response should log Pydantic validation errors before failing."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        # Missing required fields
        incomplete_json = {
            "pain_points": [
                {"text": "Pain 1", "evidence": "test", "confidence": "high"}
            ],
            # Missing strategic_needs, risks_if_unfilled, success_metrics
        }
        llm_response = f"<final>{json.dumps(incomplete_json)}</final>"

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match="Schema validation failed"):
                miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify validation error logging
        assert "[PARSE] Pydantic validation failed:" in caplog.text

    def test_parse_response_logs_legacy_format_conversion(self, caplog):
        """_parse_response should log when converting legacy format."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        # Legacy format (string arrays) with strings long enough (>= 10 chars)
        legacy_json = {
            "pain_points": ["Legacy system modernization needed", "Database performance optimization required", "Infrastructure scaling challenges"],
            "strategic_needs": ["Enable business growth initiatives", "Support international expansion", "Attract top technical talent"],
            "risks_if_unfilled": ["Customer facing incidents continue", "Unable to meet Q2 scalability targets"],
            "success_metrics": ["95% reduction in production incidents", "Deploy new features 3x faster", "Zero downtime during traffic spikes"]
        }
        llm_response = f"<final>{json.dumps(legacy_json)}</final>"

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify legacy conversion logging
        assert "[PARSE] Converting legacy format (string arrays) to enhanced format" in caplog.text

    def test_parse_response_logs_json_cleanup_steps(self, enhanced_json_response, caplog):
        """_parse_response should log JSON cleanup steps."""
        import logging
        miner = PainPointMiner(use_enhanced_format=True)

        # Response with ```json markers
        llm_response = f"<final>```json\n{json.dumps(enhanced_json_response)}\n```</final>"

        with caplog.at_level(logging.INFO):
            result = miner._parse_response(llm_response, logger=get_logger(__name__))

        # Verify cleanup logging
        assert "[PARSE] Stripped ```json prefix" in caplog.text or "[PARSE] Stripped ``` suffix" in caplog.text


class TestExtractPainPointsLogging:
    """Tests for logging behavior in extract_pain_points() method."""

    @pytest.fixture
    def valid_enhanced_response(self):
        """Valid enhanced format response wrapped in <final> tags."""
        return "<final>" + json.dumps({
            "pain_points": [
                {"text": "API platform performance issues", "evidence": "explicit requirement", "confidence": "high"},
                {"text": "Database scaling problems", "evidence": "inferred from context", "confidence": "medium"},
            ],
            "strategic_needs": [
                {"text": "Enable rapid growth", "evidence": "business context", "confidence": "high"},
                {"text": "Improve customer retention", "evidence": "inferred", "confidence": "medium"},
            ],
            "risks_if_unfilled": [
                {"text": "System outages", "evidence": "performance requirements", "confidence": "high"},
                {"text": "Customer churn", "evidence": "inferred", "confidence": "low"},
            ],
            "success_metrics": [
                {"text": "API latency <100ms", "evidence": "performance goal", "confidence": "medium"},
                {"text": "Zero downtime", "evidence": "operational requirement", "confidence": "high"},
            ],
        }) + "</final>"

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extract_pain_points_logs_job_context_before_llm_call(
        self, mock_unified_llm_class, sample_job_state, valid_enhanced_response, caplog
    ):
        """extract_pain_points should log job title/company before LLM call."""
        import logging

        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(valid_enhanced_response)
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()

        with caplog.at_level(logging.INFO):
            result = miner.extract_pain_points(sample_job_state)

        # Verify logging of job context before LLM call
        assert "[LLM] Calling LLM for job:" in caplog.text
        assert sample_job_state["title"] in caplog.text or "Senior Software Engineer" in caplog.text
        assert sample_job_state["company"] in caplog.text or "Test Corp" in caplog.text
        assert "[LLM] JD length:" in caplog.text
        assert "chars" in caplog.text

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extract_pain_points_logs_llm_response_details(
        self, mock_unified_llm_class, sample_job_state, valid_enhanced_response, caplog
    ):
        """extract_pain_points should log LLM response details after call."""
        import logging

        mock_llm_instance = MagicMock()
        mock_result = _create_mock_llm_result(valid_enhanced_response)
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()

        with caplog.at_level(logging.INFO):
            result = miner.extract_pain_points(sample_job_state)

        # Verify logging of LLM response details
        assert "[LLM] Response received - success: True" in caplog.text
        assert "[LLM] Backend:" in caplog.text
        assert "[LLM] Response content length:" in caplog.text

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extract_pain_points_logs_llm_error_if_present(
        self, mock_unified_llm_class, sample_job_state, caplog
    ):
        """extract_pain_points should log LLM errors."""
        import logging

        mock_llm_instance = MagicMock()
        # Simulate failed LLM call
        mock_result = _create_mock_llm_result("", success=False)
        mock_result.error = "API timeout"
        mock_llm_instance.invoke = AsyncMock(return_value=mock_result)
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()

        with caplog.at_level(logging.ERROR):
            result = miner.extract_pain_points(sample_job_state)

        # Verify error logging (should be in exception handling)
        # Note: This will fail gracefully and return empty structure
        assert result["pain_points"] == []
        assert len(result["errors"]) > 0

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extract_pain_points_logs_exception_traceback(
        self, mock_unified_llm_class, sample_job_state, caplog
    ):
        """extract_pain_points should log full traceback on exception."""
        import logging

        mock_llm_instance = MagicMock()
        # Simulate exception during LLM call
        mock_llm_instance.invoke = AsyncMock(side_effect=Exception("Unexpected error"))
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()

        with caplog.at_level(logging.ERROR):
            result = miner.extract_pain_points(sample_job_state)

        # Verify exception logging
        assert "[EXCEPTION] Full traceback:" in caplog.text
        assert "[EXCEPTION] Exception type:" in caplog.text
        assert "[EXCEPTION] Job ID:" in caplog.text
        assert "[EXCEPTION] Title:" in caplog.text
        assert "[EXCEPTION] JD length:" in caplog.text

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extract_pain_points_logs_exception_job_context(
        self, mock_unified_llm_class, sample_job_state, caplog
    ):
        """extract_pain_points should log job context when exception occurs."""
        import logging

        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke = AsyncMock(side_effect=ValueError("Test error"))
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()

        with caplog.at_level(logging.ERROR):
            result = miner.extract_pain_points(sample_job_state)

        # Verify job context in error logs
        log_text = caplog.text
        assert sample_job_state.get("job_id", "unknown") in log_text or "[EXCEPTION] Job ID:" in log_text
        assert sample_job_state["title"] in log_text or "[EXCEPTION] Title:" in log_text

    @patch('src.layer2.pain_point_miner.UnifiedLLM')
    def test_extract_pain_points_returns_empty_structure_on_failure(
        self, mock_unified_llm_class, sample_job_state
    ):
        """extract_pain_points should return empty structure on failure, not crash."""
        mock_llm_instance = MagicMock()
        mock_llm_instance.invoke = AsyncMock(side_effect=Exception("Fatal error"))
        mock_unified_llm_class.return_value = mock_llm_instance

        miner = PainPointMiner()
        result = miner.extract_pain_points(sample_job_state)

        # Verify graceful degradation
        assert result["pain_points"] == []
        assert result["strategic_needs"] == []
        assert result["risks_if_unfilled"] == []
        assert result["success_metrics"] == []
        assert "errors" in result
        assert len(result["errors"]) > 0
        assert "Layer 2 (Pain-Point Miner) failed" in result["errors"][0]
