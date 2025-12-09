"""
Edge case tests for Layer 7: Interview Question Predictor.

Tests error handling, edge cases, and boundary conditions not covered
in the main test file.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.common.state import JobState
from src.layer7.interview_predictor import (
    InterviewPredictor,
    PredictedQuestion,
    QuestionGenerationOutput,
    predict_interview_questions,
)


# ===== FIXTURES =====


@pytest.fixture
def malformed_state():
    """JobState with malformed/missing fields."""
    return {
        "job_id": "malformed123",
        "title": "",  # Empty title
        "company": None,  # None company
        "job_description": None,
        # Missing extracted_jd
        # Missing jd_annotations
        # Missing company_research
        # Missing role_research
        "errors": [],
    }


@pytest.fixture
def large_annotations_state():
    """JobState with very large number of annotations."""
    annotations = [
        {
            "id": f"gap-{i}",
            "relevance": "gap",
            "target": {
                "text": f"Requirement {i}" * 100,  # Very long text
                "section": "qualifications",
            },
            "matching_skill": f"Skill {i}",
            "reframe_note": f"Reframe {i}" * 50,
        }
        for i in range(50)  # 50 gaps
    ]

    concerns = [
        {
            "id": f"concern-{i}",
            "concern": f"Concern {i}" * 100,  # Very long text
            "severity": "concern",
            "mitigation_strategy": f"Strategy {i}" * 50,
            "discuss_in_interview": True,
        }
        for i in range(30)  # 30 concerns
    ]

    return {
        "job_id": "large123",
        "title": "Senior Engineer",
        "company": "Test Corp",
        "job_description": "Job description",
        "jd_annotations": {
            "annotations": annotations,
            "concerns": concerns,
        },
        "extracted_jd": {"seniority_level": "senior"},
        "all_stars": [{"id": f"star-{i}"} for i in range(100)],  # 100 STARs
        "errors": [],
    }


@pytest.fixture
def special_characters_state():
    """JobState with special characters and unicode."""
    return {
        "job_id": "special123",
        "title": "Développeur Principal 🚀",
        "company": "Société Française & Co., Ltd. (東京)",
        "job_description": "Description with émojis 😀 and spécial çharacters",
        "jd_annotations": {
            "annotations": [
                {
                    "id": "ann-1",
                    "relevance": "gap",
                    "target": {
                        "text": "Required: C++ & Python (>= 3.8) with æ, ø, å",
                        "section": "qualifications",
                    },
                    "matching_skill": "Python 2.7",
                },
            ],
            "concerns": [
                {
                    "id": "concern-1",
                    "concern": "On-call 24/7 (週末を含む)",
                    "severity": "concern",
                    "mitigation_strategy": "Negotiate",
                    "discuss_in_interview": True,
                },
            ],
        },
        "extracted_jd": {"seniority_level": "senior"},
        "errors": [],
    }


# ===== ERROR HANDLING TESTS =====


class TestErrorHandling:
    """Test error handling in interview predictor."""

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_llm_timeout(self, mock_create_llm, malformed_state):
        """Should handle LLM timeout gracefully."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.side_effect = TimeoutError(
            "Request timeout"
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state)

        # Should return valid structure with empty questions
        assert "predicted_questions" in result
        assert len(result["predicted_questions"]) == 0
        assert result["generated_by"] == predictor.model

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_llm_rate_limit(self, mock_create_llm, malformed_state):
        """Should handle rate limiting gracefully."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.side_effect = Exception(
            "Rate limit exceeded"
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state)

        assert len(result["predicted_questions"]) == 0

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_llm_invalid_json(self, mock_create_llm, malformed_state):
        """Should handle invalid JSON from LLM."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.side_effect = (
            json.JSONDecodeError("Invalid", "", 0)
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state)

        assert len(result["predicted_questions"]) == 0

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_llm_empty_response(self, mock_create_llm, malformed_state):
        """Should handle empty LLM response."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(questions=[])
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state)

        assert len(result["predicted_questions"]) == 0

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_llm_malformed_questions(self, mock_create_llm, malformed_state):
        """Should handle malformed questions from LLM."""
        malformed_question = PredictedQuestion(
            question="",  # Empty question
            question_type="invalid_type",  # Invalid type
            difficulty="ultra_hard",  # Invalid difficulty
            suggested_answer_approach="",
        )

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(questions=[malformed_question])
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state)

        # Should still process but may normalize invalid values
        assert "predicted_questions" in result


# ===== EDGE CASE TESTS =====


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_empty_title_and_company(self, mock_create_llm, malformed_state):
        """Should handle empty title and None company."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(questions=[])
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state)

        # Should use fallback values
        assert result["company_context"]
        assert result["role_context"]

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_very_large_annotations_count(self, mock_create_llm, large_annotations_state):
        """Should handle very large number of annotations."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(
                questions=[
                    PredictedQuestion(
                        question=f"Question {i}",
                        question_type="gap_probe",
                        difficulty="medium",
                        suggested_answer_approach="Approach",
                    )
                    for i in range(15)
                ]
            )
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(large_annotations_state)

        # Should process without error
        assert len(result["predicted_questions"]) == 12  # Max default

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_special_characters_in_text(self, mock_create_llm, special_characters_state):
        """Should handle special characters and unicode."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(
                questions=[
                    PredictedQuestion(
                        question="What's your Python experience?",
                        question_type="gap_probe",
                        difficulty="medium",
                        suggested_answer_approach="Focus on version migration",
                    )
                ]
            )
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(special_characters_state)

        # Should process unicode correctly
        assert len(result["predicted_questions"]) == 1
        assert "🚀" in special_characters_state["title"]

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_zero_max_questions(self, mock_create_llm, malformed_state):
        """Should handle max_questions=0."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(
                questions=[
                    PredictedQuestion(
                        question="Test",
                        question_type="behavioral",
                        difficulty="easy",
                        suggested_answer_approach="Test",
                    )
                ]
            )
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state, max_questions=0)

        # Should return empty list
        assert len(result["predicted_questions"]) == 0

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_negative_max_questions(self, mock_create_llm, malformed_state):
        """Should handle negative max_questions."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(questions=[])
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state, max_questions=-5)

        # Should handle gracefully (treat as 0 or positive)
        assert "predicted_questions" in result

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_very_large_max_questions(self, mock_create_llm, malformed_state):
        """Should handle very large max_questions."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(
                questions=[
                    PredictedQuestion(
                        question=f"Q{i}",
                        question_type="behavioral",
                        difficulty="medium",
                        suggested_answer_approach="A",
                    )
                    for i in range(5)
                ]
            )
        )
        mock_create_llm.return_value = mock_llm

        predictor = InterviewPredictor()
        result = predictor.predict_questions(malformed_state, max_questions=1000)

        # Should be limited by LLM output
        assert len(result["predicted_questions"]) == 5

    def test_format_gaps_with_missing_fields(self):
        """Should handle gaps with missing fields."""
        predictor = InterviewPredictor()

        gaps = [
            {"relevance": "gap"},  # Missing target
            {"relevance": "gap", "target": {}},  # Empty target
            {"relevance": "gap", "target": {"text": "Only text"}},  # Partial target
        ]

        result = predictor._format_gaps_for_prompt(gaps)

        # Should not crash, may return formatted or empty
        assert isinstance(result, str)

    def test_format_concerns_with_missing_fields(self):
        """Should handle concerns with missing fields."""
        predictor = InterviewPredictor()

        concerns = [
            {"discuss_in_interview": True},  # Missing concern
            {"concern": "", "discuss_in_interview": True},  # Empty concern
            {
                "concern": "Test",
                "discuss_in_interview": True,
            },  # Missing severity
        ]

        result = predictor._format_concerns_for_prompt(concerns)

        # Should not crash
        assert isinstance(result, str)

    def test_get_source_annotation_ids_empty(self):
        """Should handle empty gaps and concerns."""
        predictor = InterviewPredictor()

        result = predictor._get_source_annotation_ids([], [])

        assert result == ["general"]

    def test_get_source_annotation_ids_no_ids(self):
        """Should handle gaps/concerns without id field."""
        predictor = InterviewPredictor()

        gaps = [{"relevance": "gap"}]  # No id
        concerns = [{"concern": "Test"}]  # No id

        result = predictor._get_source_annotation_ids(gaps, concerns)

        assert result == ["general"]


# ===== SENIORITY LEVEL TESTS =====


class TestSeniorityLevel:
    """Test seniority level extraction and handling."""

    def test_all_seniority_levels(self):
        """Should handle all seniority levels."""
        predictor = InterviewPredictor()

        levels = [
            "entry",
            "junior",
            "mid",
            "senior",
            "staff",
            "principal",
            "executive",
        ]

        for level in levels:
            state = {
                "extracted_jd": {"seniority_level": level},
            }
            result = predictor._get_seniority_level(state)
            assert result == level

    def test_missing_extracted_jd(self):
        """Should default to senior when extracted_jd missing."""
        predictor = InterviewPredictor()
        result = predictor._get_seniority_level({})
        assert result == "senior"

    def test_missing_seniority_level(self):
        """Should default to senior when seniority_level missing."""
        predictor = InterviewPredictor()
        state = {"extracted_jd": {}}
        result = predictor._get_seniority_level(state)
        assert result == "senior"


# ===== SUMMARY BUILDING TESTS =====


class TestSummaryBuilding:
    """Test summary building edge cases."""

    def test_gap_summary_very_long_text(self):
        """Should truncate very long gap texts."""
        predictor = InterviewPredictor()

        gaps = [
            {
                "target": {"text": "A" * 500},  # 500 chars
                "relevance": "gap",
            }
        ]

        summary = predictor._build_gap_summary(gaps)

        # Should be truncated to 100 chars per gap
        assert len(summary) < 200  # 100 + overhead

    def test_concern_summary_very_long_text(self):
        """Should truncate very long concern texts."""
        predictor = InterviewPredictor()

        concerns = [
            {"concern": "B" * 500, "discuss_in_interview": True}  # 500 chars
        ]

        summary = predictor._build_concerns_summary(concerns)

        # Should be truncated to 100 chars per concern
        assert len(summary) < 200

    def test_gap_summary_with_none_text(self):
        """Should handle None text in gaps."""
        predictor = InterviewPredictor()

        gaps = [
            {"target": {"text": None}, "relevance": "gap"},
            {"target": {}, "relevance": "gap"},  # Missing text
        ]

        summary = predictor._build_gap_summary(gaps)

        # Should not crash
        assert isinstance(summary, str)

    def test_concern_summary_with_none_text(self):
        """Should handle None text in concerns."""
        predictor = InterviewPredictor()

        concerns = [
            {"concern": None, "discuss_in_interview": True},
            {"discuss_in_interview": True},  # Missing concern
        ]

        summary = predictor._build_concerns_summary(concerns)

        # Should not crash
        assert isinstance(summary, str)


# ===== CONTEXT EXTRACTION TESTS =====


class TestContextExtraction:
    """Test context extraction edge cases."""

    def test_company_context_very_long(self):
        """Should truncate very long company summaries."""
        predictor = InterviewPredictor()

        state = {
            "company_research": {"summary": "A" * 1000},  # 1000 chars
            "company": "Test Corp",
        }

        context = predictor._extract_company_context(state)

        # Should be truncated to 500 chars
        assert len(context) <= 500

    def test_role_context_very_long(self):
        """Should truncate very long role summaries."""
        predictor = InterviewPredictor()

        state = {
            "role_research": {"summary": "B" * 1000},  # 1000 chars
        }

        context = predictor._extract_role_context(state)

        # Should be truncated to 500 chars
        assert len(context) <= 500

    def test_role_context_fallback_to_responsibilities(self):
        """Should use responsibilities when role_research missing."""
        predictor = InterviewPredictor()

        state = {
            "extracted_jd": {
                "responsibilities": ["Lead team", "Design systems", "Write code"]
            },
            "title": "Senior Engineer",
        }

        context = predictor._extract_role_context(state)

        # Should contain responsibilities
        assert "Lead team" in context

    def test_role_context_fallback_to_title(self):
        """Should use title when everything else missing."""
        predictor = InterviewPredictor()

        state = {"title": "Software Engineer"}

        context = predictor._extract_role_context(state)

        assert "Software Engineer" in context


# ===== HELPER FUNCTION EDGE CASES =====


class TestHelperFunctionEdgeCases:
    """Test predict_interview_questions helper function edge cases."""

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_helper_with_custom_model(self, mock_create_llm):
        """Helper should pass custom model correctly."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(questions=[])
        )
        mock_create_llm.return_value = mock_llm

        state = {"job_id": "test", "title": "Engineer", "company": "Co"}

        result = predict_interview_questions(state, model="custom-model")

        # Should have called with custom model
        assert result["generated_by"] == "custom-model"

    @patch("src.layer7.interview_predictor.create_tracked_llm")
    def test_helper_with_max_questions(self, mock_create_llm):
        """Helper should pass max_questions correctly."""
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = (
            QuestionGenerationOutput(
                questions=[
                    PredictedQuestion(
                        question=f"Q{i}",
                        question_type="behavioral",
                        difficulty="medium",
                        suggested_answer_approach="A",
                    )
                    for i in range(10)
                ]
            )
        )
        mock_create_llm.return_value = mock_llm

        state = {"job_id": "test", "title": "Engineer", "company": "Co"}

        result = predict_interview_questions(state, max_questions=5)

        # Should be limited to 5
        assert len(result["predicted_questions"]) == 5
