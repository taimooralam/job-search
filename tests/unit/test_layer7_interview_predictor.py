"""
Unit tests for Layer 7: Interview Question Predictor (Phase 7)

Tests question generation, gap/concern processing, and STAR linking
with mocked LLM responses.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.common.annotation_types import (
    ConcernAnnotation,
    InterviewPrep,
    InterviewQuestion,
    JDAnnotation,
)
from src.common.state import JobState
from src.layer7.interview_predictor import (
    DIFFICULTY_LEVELS,
    QUESTION_TYPES,
    InterviewPredictor,
    PredictedQuestion,
    QuestionGenerationOutput,
    predict_interview_questions,
)


# ===== MOCK LLM RESULT HELPER =====


@dataclass
class MockLLMResult:
    """Mock LLMResult for testing invoke_unified_sync."""

    success: bool = True
    error: Optional[str] = None
    parsed_json: Optional[Dict[str, Any]] = None
    content: str = ""
    backend: str = "test"
    model: str = "test-model"
    tier: str = "low"
    duration_ms: int = 100


def create_mock_llm_result(response: QuestionGenerationOutput) -> MockLLMResult:
    """Convert a QuestionGenerationOutput to a MockLLMResult."""
    return MockLLMResult(
        success=True,
        parsed_json=response.model_dump(),
        content=json.dumps(response.model_dump()),
    )


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
        "extracted_jd": {
            "seniority_level": "senior",
            "role_category": "staff_principal_engineer",
            "responsibilities": ["Design systems", "Lead team", "Write code"],
        },
        "jd_annotations": {
            "annotations": [
                {
                    "id": "gap-1",
                    "relevance": "gap",
                    "target": {
                        "text": "5+ years Kubernetes experience required",
                        "section": "qualifications",
                    },
                    "matching_skill": "Docker",
                    "reframe_note": "Emphasize container orchestration experience",
                },
                {
                    "id": "gap-2",
                    "relevance": "gap",
                    "target": {
                        "text": "Machine learning background preferred",
                        "section": "nice_to_haves",
                    },
                },
                {
                    "id": "strength-1",
                    "relevance": "core_strength",
                    "target": {"text": "Python expert", "section": "qualifications"},
                },
            ],
            "concerns": [
                {
                    "id": "concern-1",
                    "concern": "On-call rotation every 2 weeks",
                    "severity": "concern",
                    "mitigation_strategy": "Discuss work-life balance expectations",
                    "discuss_in_interview": True,
                },
                {
                    "id": "concern-2",
                    "concern": "Travel requirement 50%",
                    "severity": "preference",
                    "discuss_in_interview": False,
                },
            ],
        },
        "company_research": {
            "summary": "Test Corp is a leading tech company focusing on cloud solutions.",
        },
        "role_research": {
            "summary": "This role focuses on building scalable backend systems.",
        },
        "selected_stars": [
            {"id": "star-1"},
            {"id": "star-2"},
        ],
        "all_stars": [
            {"id": "star-1"},
            {"id": "star-2"},
            {"id": "star-3"},
        ],
        "errors": [],
        "status": "processing",
    }


@pytest.fixture
def empty_annotations_state():
    """JobState with no gaps or concerns."""
    return {
        "job_id": "test456",
        "title": "Junior Developer",
        "company": "Startup Inc",
        "job_description": "Entry level position...",
        "jd_annotations": {
            "annotations": [
                {
                    "id": "strength-1",
                    "relevance": "core_strength",
                    "target": {"text": "Python", "section": "qualifications"},
                },
            ],
            "concerns": [],
        },
        "extracted_jd": {"seniority_level": "junior"},
        "errors": [],
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM response with predicted questions."""
    return QuestionGenerationOutput(
        questions=[
            PredictedQuestion(
                question="Can you describe your experience with Kubernetes and container orchestration?",
                question_type="gap_probe",
                difficulty="medium",
                suggested_answer_approach="Focus on your Docker experience and explain how it transfers to Kubernetes concepts.",
                sample_answer_outline="1. Docker expertise\n2. Orchestration concepts\n3. Learning plan for K8s",
                relevant_star_ids=["star-1"],
            ),
            PredictedQuestion(
                question="Tell me about a time when you had to quickly learn a new technology.",
                question_type="behavioral",
                difficulty="easy",
                suggested_answer_approach="Use STAR format. Pick an example where you learned something complex quickly.",
                relevant_star_ids=["star-2"],
            ),
            PredictedQuestion(
                question="How do you approach work-life balance when there are on-call requirements?",
                question_type="concern_probe",
                difficulty="medium",
                suggested_answer_approach="Be honest about expectations while showing flexibility.",
                relevant_star_ids=[],
            ),
            PredictedQuestion(
                question="What experience do you have with machine learning concepts?",
                question_type="gap_probe",
                difficulty="hard",
                suggested_answer_approach="Acknowledge limited ML experience but highlight analytical skills and eagerness to learn.",
                relevant_star_ids=[],
            ),
        ]
    )


# ===== SCHEMA VALIDATION TESTS =====


class TestPredictedQuestionSchema:
    """Test Pydantic schema validation."""

    def test_valid_schema(self):
        """Valid question should pass schema validation."""
        question = PredictedQuestion(
            question="Tell me about yourself",
            question_type="behavioral",
            difficulty="easy",
            suggested_answer_approach="Use a structured introduction.",
            relevant_star_ids=["star-1"],
        )
        assert question.question == "Tell me about yourself"
        assert question.difficulty == "easy"

    def test_optional_fields(self):
        """Optional fields should work."""
        question = PredictedQuestion(
            question="Technical question",
            question_type="technical",
            difficulty="hard",
            suggested_answer_approach="Focus on fundamentals.",
        )
        assert question.sample_answer_outline is None
        assert question.relevant_star_ids == []


class TestQuestionGenerationOutputSchema:
    """Test output schema validation."""

    def test_valid_output(self, mock_llm_response):
        """Valid output should pass validation."""
        assert len(mock_llm_response.questions) == 4

    def test_empty_questions(self):
        """Empty questions list should be valid."""
        output = QuestionGenerationOutput(questions=[])
        assert len(output.questions) == 0


# ===== INTERVIEW PREDICTOR TESTS =====


class TestInterviewPredictor:
    """Test InterviewPredictor class."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_with_gaps(self, mock_invoke, sample_job_state, mock_llm_response):
        """Should generate questions from gaps and concerns."""
        # Setup mock LLM
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state)

        # Verify result structure
        assert "predicted_questions" in result
        assert "gap_summary" in result
        assert "concerns_summary" in result
        assert "company_context" in result
        assert "role_context" in result
        assert "generated_at" in result
        assert "generated_by" in result

        # Verify questions were generated
        assert len(result["predicted_questions"]) == 4

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_extracts_gaps(self, mock_invoke, sample_job_state, mock_llm_response):
        """Should correctly extract gaps from annotations."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()

        # Count gaps in test data
        annotations = sample_job_state["jd_annotations"]["annotations"]
        expected_gaps = len([a for a in annotations if a.get("relevance") == "gap"])
        assert expected_gaps == 2

        result = predictor.predict_questions(sample_job_state)
        assert result["gap_summary"]  # Should have gap summary

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_extracts_concerns(self, mock_invoke, sample_job_state, mock_llm_response):
        """Should correctly extract concerns marked for interview."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()

        # Count interview concerns in test data
        concerns = sample_job_state["jd_annotations"]["concerns"]
        expected_concerns = len([c for c in concerns if c.get("discuss_in_interview")])
        assert expected_concerns == 1

        result = predictor.predict_questions(sample_job_state)
        assert result["concerns_summary"]

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_empty_annotations(self, mock_invoke, empty_annotations_state, mock_llm_response):
        """Should handle empty gaps/concerns gracefully."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(empty_annotations_state)

        # Should still generate questions (general behavioral)
        assert "predicted_questions" in result

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_no_annotations(self, mock_invoke, mock_llm_response):
        """Should handle missing jd_annotations field."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        state = {
            "job_id": "test789",
            "title": "Developer",
            "company": "Company",
            "job_description": "Job desc",
            # No jd_annotations field
        }

        predictor = InterviewPredictor()
        result = predictor.predict_questions(state)

        # Should return valid result even without annotations
        assert "predicted_questions" in result
        assert result["gap_summary"] == "No significant skill gaps identified."
        assert result["concerns_summary"] == "No significant concerns flagged for discussion."

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_max_limit(self, mock_invoke, sample_job_state):
        """Should respect max_questions limit."""
        # Create response with many questions
        many_questions = QuestionGenerationOutput(
            questions=[
                PredictedQuestion(
                    question=f"Question {i}",
                    question_type="behavioral",
                    difficulty="medium",
                    suggested_answer_approach="Approach",
                )
                for i in range(20)
            ]
        )

        mock_invoke.return_value = create_mock_llm_result(many_questions)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state, max_questions=5)

        # Should be limited to 5 questions
        assert len(result["predicted_questions"]) == 5

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_predict_questions_llm_error(self, mock_invoke, sample_job_state):
        """Should handle LLM errors gracefully."""
        mock_invoke.return_value = MockLLMResult(success=False, error="API Error")

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state)

        # Should return valid result with empty questions
        assert "predicted_questions" in result
        assert len(result["predicted_questions"]) == 0

    def test_get_seniority_level(self, sample_job_state):
        """Should extract seniority level from state."""
        predictor = InterviewPredictor()
        level = predictor._get_seniority_level(sample_job_state)
        assert level == "senior"

    def test_get_seniority_level_default(self):
        """Should default to senior when not specified."""
        predictor = InterviewPredictor()
        level = predictor._get_seniority_level({})
        assert level == "senior"

    def test_build_gap_summary_with_gaps(self):
        """Should build summary from gaps."""
        predictor = InterviewPredictor()
        gaps = [
            {"target": {"text": "Kubernetes experience"}, "relevance": "gap"},
            {"target": {"text": "ML background"}, "relevance": "gap"},
        ]
        summary = predictor._build_gap_summary(gaps)
        assert "Kubernetes" in summary
        assert "ML" in summary

    def test_build_gap_summary_empty(self):
        """Should return default message for empty gaps."""
        predictor = InterviewPredictor()
        summary = predictor._build_gap_summary([])
        assert summary == "No significant skill gaps identified."

    def test_build_concerns_summary_with_concerns(self):
        """Should build summary from concerns."""
        predictor = InterviewPredictor()
        concerns = [
            {"concern": "On-call rotation", "discuss_in_interview": True},
            {"concern": "Travel requirement", "discuss_in_interview": True},
        ]
        summary = predictor._build_concerns_summary(concerns)
        assert "On-call" in summary
        assert "Travel" in summary

    def test_build_concerns_summary_empty(self):
        """Should return default message for empty concerns."""
        predictor = InterviewPredictor()
        summary = predictor._build_concerns_summary([])
        assert summary == "No significant concerns flagged for discussion."

    def test_extract_company_context_with_research(self, sample_job_state):
        """Should extract company context from research."""
        predictor = InterviewPredictor()
        context = predictor._extract_company_context(sample_job_state)
        assert "Test Corp" in context or "tech company" in context

    def test_extract_company_context_fallback(self):
        """Should fallback to company name when no research."""
        predictor = InterviewPredictor()
        context = predictor._extract_company_context({"company": "FallbackCo"})
        assert "FallbackCo" in context

    def test_extract_role_context_with_research(self, sample_job_state):
        """Should extract role context from research."""
        predictor = InterviewPredictor()
        context = predictor._extract_role_context(sample_job_state)
        assert "backend" in context.lower() or "scalable" in context.lower()

    def test_determine_source_type(self):
        """Should correctly map question types to source types."""
        predictor = InterviewPredictor()

        assert predictor._determine_source_type("gap_probe") == "gap"
        assert predictor._determine_source_type("concern_probe") == "concern"
        assert predictor._determine_source_type("behavioral") == "general"
        assert predictor._determine_source_type("technical") == "general"


# ===== HELPER FUNCTION TESTS =====


class TestPredictInterviewQuestionsHelper:
    """Test the predict_interview_questions helper function."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_helper_function(self, mock_invoke, sample_job_state, mock_llm_response):
        """Helper function should work correctly."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        result = predict_interview_questions(sample_job_state)

        assert "predicted_questions" in result
        assert len(result["predicted_questions"]) > 0

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_helper_function_with_options(self, mock_invoke, sample_job_state, mock_llm_response):
        """Helper function should pass options correctly."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        result = predict_interview_questions(
            sample_job_state, max_questions=3, model="gpt-4"
        )

        assert len(result["predicted_questions"]) == 3


# ===== QUESTION FORMAT TESTS =====


class TestInterviewQuestionFormat:
    """Test InterviewQuestion output format."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_question_has_required_fields(self, mock_invoke, sample_job_state, mock_llm_response):
        """Generated questions should have all required fields."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state)

        for question in result["predicted_questions"]:
            assert "question_id" in question
            assert "question" in question
            assert "question_type" in question
            assert "difficulty" in question
            assert "suggested_answer_approach" in question
            assert "practice_status" in question
            assert "created_at" in question

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_question_has_valid_difficulty(self, mock_invoke, sample_job_state, mock_llm_response):
        """Questions should have valid difficulty levels."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state)

        for question in result["predicted_questions"]:
            assert question["difficulty"] in DIFFICULTY_LEVELS

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_question_has_uuid(self, mock_invoke, sample_job_state, mock_llm_response):
        """Questions should have valid UUID ids."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state)

        for question in result["predicted_questions"]:
            # Should be valid UUID format
            uuid.UUID(question["question_id"])

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_question_default_practice_status(self, mock_invoke, sample_job_state, mock_llm_response):
        """Questions should default to not_started practice status."""
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response)

        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_job_state)

        for question in result["predicted_questions"]:
            assert question["practice_status"] == "not_started"


# ===== CONSTANTS TESTS =====


class TestConstants:
    """Test module constants."""

    def test_question_types_defined(self):
        """Question types should be defined."""
        assert "gap_probe" in QUESTION_TYPES
        assert "concern_probe" in QUESTION_TYPES
        assert "behavioral" in QUESTION_TYPES
        assert "technical" in QUESTION_TYPES
        assert "situational" in QUESTION_TYPES

    def test_difficulty_levels_defined(self):
        """Difficulty levels should be defined."""
        assert "easy" in DIFFICULTY_LEVELS
        assert "medium" in DIFFICULTY_LEVELS
        assert "hard" in DIFFICULTY_LEVELS
