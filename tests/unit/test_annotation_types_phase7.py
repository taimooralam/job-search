"""
Unit tests for Phase 7 annotation types.

Tests the new Phase 7 types:
- InterviewQuestion
- InterviewPrep
- ApplicationOutcome
- OutcomeStatus
"""

import pytest
from datetime import datetime

from src.common.annotation_types import (
    InterviewQuestion,
    InterviewPrep,
    ApplicationOutcome,
    RELEVANCE_MULTIPLIERS,
    REQUIREMENT_MULTIPLIERS,
    PRIORITY_MULTIPLIERS,
)


# ===== INTERVIEW QUESTION TESTS =====


class TestInterviewQuestionType:
    """Test InterviewQuestion TypedDict structure."""

    def test_valid_interview_question(self):
        """Should accept valid interview question structure."""
        question: InterviewQuestion = {
            "question_id": "q1",
            "question": "Tell me about your experience with Kubernetes",
            "source_annotation_id": "ann-1",
            "source_type": "gap",
            "question_type": "gap_probe",
            "difficulty": "medium",
            "suggested_answer_approach": "Focus on Docker experience",
            "sample_answer_outline": "1. Docker\n2. Learning K8s",
            "relevant_star_ids": ["star-1"],
            "practice_status": "not_started",
            "user_notes": None,
            "created_at": "2024-01-15T10:00:00",
        }

        assert question["question_id"] == "q1"
        assert question["difficulty"] == "medium"
        assert question["source_type"] == "gap"

    def test_question_with_optional_fields(self):
        """Should accept question with None optional fields."""
        question: InterviewQuestion = {
            "question_id": "q2",
            "question": "Describe your project management approach",
            "source_annotation_id": "general",
            "source_type": "general",
            "question_type": "behavioral",
            "difficulty": "easy",
            "suggested_answer_approach": "Use STAR format",
            "sample_answer_outline": None,  # Optional
            "relevant_star_ids": [],
            "practice_status": "practiced",
            "user_notes": None,  # Optional
            "created_at": "2024-01-15T10:00:00",
        }

        assert question["sample_answer_outline"] is None
        assert question["user_notes"] is None
        assert len(question["relevant_star_ids"]) == 0

    def test_question_source_types(self):
        """Should support all valid source types."""
        valid_sources = ["gap", "concern", "general"]

        for source_type in valid_sources:
            question: InterviewQuestion = {
                "question_id": f"q-{source_type}",
                "question": "Test question",
                "source_annotation_id": "ann-1",
                "source_type": source_type,
                "question_type": "behavioral",
                "difficulty": "medium",
                "suggested_answer_approach": "Test approach",
                "sample_answer_outline": None,
                "relevant_star_ids": [],
                "practice_status": "not_started",
                "user_notes": None,
                "created_at": "2024-01-15T10:00:00",
            }
            assert question["source_type"] == source_type

    def test_question_difficulty_levels(self):
        """Should support all difficulty levels."""
        difficulties = ["easy", "medium", "hard"]

        for difficulty in difficulties:
            question: InterviewQuestion = {
                "question_id": f"q-{difficulty}",
                "question": "Test question",
                "source_annotation_id": "ann-1",
                "source_type": "general",
                "question_type": "technical",
                "difficulty": difficulty,
                "suggested_answer_approach": "Test",
                "sample_answer_outline": None,
                "relevant_star_ids": [],
                "practice_status": "not_started",
                "user_notes": None,
                "created_at": "2024-01-15T10:00:00",
            }
            assert question["difficulty"] == difficulty

    def test_question_types_supported(self):
        """Should support all question types."""
        question_types = [
            "gap_probe",
            "concern_probe",
            "behavioral",
            "technical",
            "situational",
        ]

        for q_type in question_types:
            question: InterviewQuestion = {
                "question_id": f"q-{q_type}",
                "question": "Test question",
                "source_annotation_id": "ann-1",
                "source_type": "general",
                "question_type": q_type,
                "difficulty": "medium",
                "suggested_answer_approach": "Test",
                "sample_answer_outline": None,
                "relevant_star_ids": [],
                "practice_status": "not_started",
                "user_notes": None,
                "created_at": "2024-01-15T10:00:00",
            }
            assert question["question_type"] == q_type

    def test_practice_status_values(self):
        """Should support all practice status values."""
        statuses = ["not_started", "practiced", "confident"]

        for status in statuses:
            question: InterviewQuestion = {
                "question_id": f"q-{status}",
                "question": "Test question",
                "source_annotation_id": "ann-1",
                "source_type": "general",
                "question_type": "behavioral",
                "difficulty": "medium",
                "suggested_answer_approach": "Test",
                "sample_answer_outline": None,
                "relevant_star_ids": [],
                "practice_status": status,
                "user_notes": "My notes" if status == "practiced" else None,
                "created_at": "2024-01-15T10:00:00",
            }
            assert question["practice_status"] == status


# ===== INTERVIEW PREP TESTS =====


class TestInterviewPrepType:
    """Test InterviewPrep TypedDict structure."""

    def test_valid_interview_prep(self):
        """Should accept valid interview prep structure."""
        prep: InterviewPrep = {
            "predicted_questions": [],
            "gap_summary": "Key gaps: Kubernetes, ML",
            "concerns_summary": "Key concerns: On-call rotation",
            "company_context": "Tech company focusing on cloud",
            "role_context": "Backend engineering role",
            "generated_at": "2024-01-15T10:00:00",
            "generated_by": "gpt-4",
        }

        assert prep["generated_by"] == "gpt-4"
        assert "Kubernetes" in prep["gap_summary"]

    def test_prep_with_questions(self):
        """Should accept prep with multiple questions."""
        questions: list[InterviewQuestion] = [
            {
                "question_id": "q1",
                "question": "Question 1",
                "source_annotation_id": "ann-1",
                "source_type": "gap",
                "question_type": "gap_probe",
                "difficulty": "hard",
                "suggested_answer_approach": "Approach 1",
                "sample_answer_outline": None,
                "relevant_star_ids": ["star-1"],
                "practice_status": "not_started",
                "user_notes": None,
                "created_at": "2024-01-15T10:00:00",
            },
            {
                "question_id": "q2",
                "question": "Question 2",
                "source_annotation_id": "ann-2",
                "source_type": "concern",
                "question_type": "concern_probe",
                "difficulty": "medium",
                "suggested_answer_approach": "Approach 2",
                "sample_answer_outline": "Sample",
                "relevant_star_ids": [],
                "practice_status": "not_started",
                "user_notes": None,
                "created_at": "2024-01-15T10:00:00",
            },
        ]

        prep: InterviewPrep = {
            "predicted_questions": questions,
            "gap_summary": "Gaps identified",
            "concerns_summary": "Concerns flagged",
            "company_context": "Company info",
            "role_context": "Role info",
            "generated_at": "2024-01-15T10:00:00",
            "generated_by": "claude-opus",
        }

        assert len(prep["predicted_questions"]) == 2
        assert prep["predicted_questions"][0]["question_id"] == "q1"
        assert prep["predicted_questions"][1]["source_type"] == "concern"

    def test_prep_empty_questions(self):
        """Should accept prep with no questions."""
        prep: InterviewPrep = {
            "predicted_questions": [],
            "gap_summary": "No gaps identified",
            "concerns_summary": "No concerns",
            "company_context": "Company context",
            "role_context": "Role context",
            "generated_at": "2024-01-15T10:00:00",
            "generated_by": "gpt-3.5-turbo",
        }

        assert len(prep["predicted_questions"]) == 0


# ===== APPLICATION OUTCOME TESTS =====


class TestApplicationOutcomeType:
    """Test ApplicationOutcome TypedDict structure."""

    def test_valid_outcome_not_applied(self):
        """Should accept valid not_applied outcome."""
        outcome: ApplicationOutcome = {
            "status": "not_applied",
            "applied_at": None,
            "applied_via": None,
            "response_at": None,
            "response_type": None,
            "screening_at": None,
            "interview_at": None,
            "interview_rounds": 0,
            "offer_at": None,
            "offer_details": None,
            "final_status_at": None,
            "notes": None,
            "days_to_response": None,
            "days_to_interview": None,
            "days_to_offer": None,
        }

        assert outcome["status"] == "not_applied"
        assert outcome["interview_rounds"] == 0

    def test_valid_outcome_applied(self):
        """Should accept valid applied outcome."""
        outcome: ApplicationOutcome = {
            "status": "applied",
            "applied_at": "2024-01-15T10:00:00",
            "applied_via": "linkedin",
            "response_at": None,
            "response_type": None,
            "screening_at": None,
            "interview_at": None,
            "interview_rounds": 0,
            "offer_at": None,
            "offer_details": None,
            "final_status_at": None,
            "notes": "Applied via LinkedIn Easy Apply",
            "days_to_response": None,
            "days_to_interview": None,
            "days_to_offer": None,
        }

        assert outcome["status"] == "applied"
        assert outcome["applied_via"] == "linkedin"
        assert outcome["applied_at"] is not None

    def test_valid_outcome_interview_scheduled(self):
        """Should accept valid interview scheduled outcome."""
        outcome: ApplicationOutcome = {
            "status": "interview_scheduled",
            "applied_at": "2024-01-15T10:00:00",
            "applied_via": "website",
            "response_at": "2024-01-20T10:00:00",
            "response_type": "interest",
            "screening_at": "2024-01-22T10:00:00",
            "interview_at": "2024-01-25T10:00:00",
            "interview_rounds": 1,
            "offer_at": None,
            "offer_details": None,
            "final_status_at": None,
            "notes": "First round technical interview",
            "days_to_response": 5,
            "days_to_interview": 10,
            "days_to_offer": None,
        }

        assert outcome["status"] == "interview_scheduled"
        assert outcome["interview_rounds"] == 1
        assert outcome["days_to_response"] == 5
        assert outcome["days_to_interview"] == 10

    def test_valid_outcome_offer_received(self):
        """Should accept valid offer received outcome."""
        outcome: ApplicationOutcome = {
            "status": "offer_received",
            "applied_at": "2024-01-15T10:00:00",
            "applied_via": "referral",
            "response_at": "2024-01-18T10:00:00",
            "response_type": "interest",
            "screening_at": "2024-01-20T10:00:00",
            "interview_at": "2024-01-25T10:00:00",
            "interview_rounds": 3,
            "offer_at": "2024-02-10T10:00:00",
            "offer_details": "$150k base, equity, remote",
            "final_status_at": None,
            "notes": "Negotiating offer",
            "days_to_response": 3,
            "days_to_interview": 10,
            "days_to_offer": 26,
        }

        assert outcome["status"] == "offer_received"
        assert outcome["interview_rounds"] == 3
        assert outcome["offer_details"] is not None
        assert outcome["days_to_offer"] == 26

    def test_valid_outcome_rejected(self):
        """Should accept valid rejected outcome."""
        outcome: ApplicationOutcome = {
            "status": "rejected",
            "applied_at": "2024-01-15T10:00:00",
            "applied_via": "linkedin",
            "response_at": "2024-01-20T10:00:00",
            "response_type": "rejection",
            "screening_at": None,
            "interview_at": None,
            "interview_rounds": 0,
            "offer_at": None,
            "offer_details": None,
            "final_status_at": "2024-01-20T10:00:00",
            "notes": "Not selected for interview",
            "days_to_response": 5,
            "days_to_interview": None,
            "days_to_offer": None,
        }

        assert outcome["status"] == "rejected"
        assert outcome["response_type"] == "rejection"
        assert outcome["final_status_at"] is not None

    def test_outcome_status_values(self):
        """Should support all outcome status values."""
        valid_statuses = [
            "not_applied",
            "applied",
            "response_received",
            "screening_scheduled",
            "interview_scheduled",
            "interviewing",
            "offer_received",
            "offer_accepted",
            "rejected",
            "withdrawn",
        ]

        for status in valid_statuses:
            outcome: ApplicationOutcome = {
                "status": status,
                "applied_at": None,
                "applied_via": None,
                "response_at": None,
                "response_type": None,
                "screening_at": None,
                "interview_at": None,
                "interview_rounds": 0,
                "offer_at": None,
                "offer_details": None,
                "final_status_at": None,
                "notes": None,
                "days_to_response": None,
                "days_to_interview": None,
                "days_to_offer": None,
            }
            assert outcome["status"] == status

    def test_outcome_applied_via_values(self):
        """Should support all applied_via values."""
        valid_sources = ["linkedin", "website", "email", "referral"]

        for source in valid_sources:
            outcome: ApplicationOutcome = {
                "status": "applied",
                "applied_at": "2024-01-15T10:00:00",
                "applied_via": source,
                "response_at": None,
                "response_type": None,
                "screening_at": None,
                "interview_at": None,
                "interview_rounds": 0,
                "offer_at": None,
                "offer_details": None,
                "final_status_at": None,
                "notes": None,
                "days_to_response": None,
                "days_to_interview": None,
                "days_to_offer": None,
            }
            assert outcome["applied_via"] == source


# ===== MULTIPLIER CONSTANTS TESTS =====


class TestMultiplierConstants:
    """Test boost calculation constants."""

    def test_relevance_multipliers_defined(self):
        """Relevance multipliers should be defined correctly."""
        assert RELEVANCE_MULTIPLIERS["core_strength"] == 3.0
        assert RELEVANCE_MULTIPLIERS["extremely_relevant"] == 2.0
        assert RELEVANCE_MULTIPLIERS["relevant"] == 1.5
        assert RELEVANCE_MULTIPLIERS["tangential"] == 1.0
        assert RELEVANCE_MULTIPLIERS["gap"] == 0.3

    def test_requirement_multipliers_defined(self):
        """Requirement multipliers should be defined correctly."""
        assert REQUIREMENT_MULTIPLIERS["must_have"] == 1.5
        assert REQUIREMENT_MULTIPLIERS["nice_to_have"] == 1.0
        assert REQUIREMENT_MULTIPLIERS["disqualifier"] == 0.0
        assert REQUIREMENT_MULTIPLIERS["neutral"] == 1.0

    def test_priority_multipliers_defined(self):
        """Priority multipliers should be defined correctly."""
        assert PRIORITY_MULTIPLIERS[1] == 1.5
        assert PRIORITY_MULTIPLIERS[2] == 1.3
        assert PRIORITY_MULTIPLIERS[3] == 1.0
        assert PRIORITY_MULTIPLIERS[4] == 0.8
        assert PRIORITY_MULTIPLIERS[5] == 0.6

    def test_multipliers_are_positive_or_zero(self):
        """All multipliers should be >= 0."""
        for value in RELEVANCE_MULTIPLIERS.values():
            assert value >= 0

        for value in REQUIREMENT_MULTIPLIERS.values():
            assert value >= 0

        for value in PRIORITY_MULTIPLIERS.values():
            assert value >= 0
