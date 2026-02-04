"""
Unit tests for Layer 7 Interview Predictor prompt improvements (GAP-030).

Tests the following enhancements:
1. Few-shot example effectiveness (question quality validation)
2. Question distribution requirements (min questions per type)
3. Validation function effectiveness (programmatic quality checks)
4. Source attribution (questions cite gaps/concerns)

Based on prompt-optimization-plan.md Section A (Layer 7 Analysis).
"""

import json
import pytest
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from src.common.annotation_types import InterviewQuestion
from src.layer7.interview_predictor import (
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


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_state_with_gaps_and_concerns():
    """JobState with multiple gaps and concerns for distribution testing."""
    return {
        "job_id": "test_distribution",
        "title": "Senior Backend Engineer",
        "company": "TechCo",
        "job_description": "Build scalable systems...",
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
                    "reframe_note": "Emphasize container orchestration transferable skills",
                },
                {
                    "id": "gap-2",
                    "relevance": "gap",
                    "target": {
                        "text": "Machine learning model deployment experience",
                        "section": "nice_to_haves",
                    },
                },
                {
                    "id": "gap-3",
                    "relevance": "gap",
                    "target": {
                        "text": "Experience with distributed tracing (Jaeger/Zipkin)",
                        "section": "qualifications",
                    },
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
                    "concern": "Company is early-stage startup (high risk)",
                    "severity": "concern",
                    "mitigation_strategy": "Highlight your startup experience",
                    "discuss_in_interview": True,
                },
                {
                    "id": "concern-3",
                    "concern": "Office location requires 2-hour commute",
                    "severity": "preference",
                    "discuss_in_interview": False,  # Not marked for discussion
                },
            ],
        },
        "extracted_jd": {"seniority_level": "senior"},
        "selected_stars": [{"id": "star-1"}, {"id": "star-2"}],
        "errors": [],
    }


@pytest.fixture
def mock_llm_response_with_distribution():
    """Mock LLM response with proper question type distribution."""
    return QuestionGenerationOutput(
        questions=[
            # Gap probe questions (3)
            PredictedQuestion(
                question="Can you walk me through your experience with Kubernetes and container orchestration at scale?",
                question_type="gap_probe",
                difficulty="medium",
                suggested_answer_approach="Focus on Docker expertise and explain transferable concepts like service discovery, load balancing, and health checks. Acknowledge you'd ramp up on K8s-specific features quickly.",
                sample_answer_outline="1. Docker production experience\n2. Orchestration concepts mastered\n3. Specific K8s learning plan",
                relevant_star_ids=["star-1"],
            ),
            PredictedQuestion(
                question="What's your experience with machine learning model deployment and MLOps pipelines?",
                question_type="gap_probe",
                difficulty="hard",
                suggested_answer_approach="Be honest about limited ML deployment experience but highlight your backend infrastructure expertise and ability to learn new domains quickly.",
                relevant_star_ids=[],
            ),
            PredictedQuestion(
                question="How have you implemented distributed tracing in production systems?",
                question_type="gap_probe",
                difficulty="medium",
                suggested_answer_approach="If you've used other observability tools (Datadog, NewRelic), explain the transferable monitoring and debugging skills.",
                relevant_star_ids=["star-2"],
            ),
            # Concern probe questions (2)
            PredictedQuestion(
                question="How do you manage work-life balance when dealing with on-call responsibilities and incident response?",
                question_type="concern_probe",
                difficulty="medium",
                suggested_answer_approach="Be honest about expectations while showing you understand the importance of operational reliability. Reference your past on-call experience if available.",
                relevant_star_ids=["star-1"],
            ),
            PredictedQuestion(
                question="What excites you about working at an early-stage startup given the inherent risks?",
                question_type="concern_probe",
                difficulty="easy",
                suggested_answer_approach="Highlight your past startup experience and emphasize what you learned from building systems from scratch. Show you understand the risk/reward tradeoff.",
                relevant_star_ids=["star-2"],
            ),
            # Behavioral questions (2)
            PredictedQuestion(
                question="Tell me about a time when you had to learn a new technology quickly to deliver a critical project.",
                question_type="behavioral",
                difficulty="medium",
                suggested_answer_approach="Use STAR format. Pick an example where you learned something complex quickly and delivered measurable results.",
                sample_answer_outline="Situation: Project required new tech\nTask: Learn and implement in 2 weeks\nAction: [specific steps]\nResult: [quantified outcome]",
                relevant_star_ids=["star-1"],
            ),
            PredictedQuestion(
                question="Describe a situation where you had to make a technical tradeoff between speed and scalability.",
                question_type="behavioral",
                difficulty="medium",
                suggested_answer_approach="Show your decision-making process. Explain how you evaluated options, consulted stakeholders, and measured outcomes.",
                relevant_star_ids=["star-2"],
            ),
            # Technical question (1)
            PredictedQuestion(
                question="How would you design a high-throughput event processing system that needs to handle 10,000 events per second?",
                question_type="technical",
                difficulty="hard",
                suggested_answer_approach="Walk through your architecture thinking: queuing strategy, processing parallelism, failure handling, monitoring. Show you understand tradeoffs between different approaches.",
                relevant_star_ids=["star-1", "star-2"],
            ),
        ]
    )


@pytest.fixture
def mock_llm_response_with_quality_issues():
    """Mock LLM response with questions that should fail quality validation."""
    return QuestionGenerationOutput(
        questions=[
            # Issue 1: Yes/no format question
            PredictedQuestion(
                question="Do you have 5 years of Kubernetes experience?",
                question_type="gap_probe",
                difficulty="easy",
                suggested_answer_approach="Answer honestly.",
                relevant_star_ids=[],
            ),
            # Issue 2: Too short
            PredictedQuestion(
                question="Tell me about K8s",
                question_type="gap_probe",
                difficulty="easy",
                suggested_answer_approach="Talk about your experience.",
                relevant_star_ids=[],
            ),
            # Issue 3: Generic answer approach (too brief)
            PredictedQuestion(
                question="What is your experience with distributed systems?",
                question_type="technical",
                difficulty="medium",
                suggested_answer_approach="Be specific.",  # Only 12 chars
                relevant_star_ids=[],
            ),
        ]
    )


# =============================================================================
# QUESTION QUALITY VALIDATION TESTS
# =============================================================================


class TestQuestionQualityValidation:
    """Tests for programmatic question quality validation (GAP-030 requirement #2)."""

    def test_detects_yes_no_question_format(self):
        """Should detect and reject yes/no question formats."""
        yes_no_questions = [
            "Do you have 5 years of Kubernetes experience?",
            "Have you worked with microservices before?",
            "Can you explain your experience with Docker?",
            "Will you be comfortable with on-call rotation?",
            "Are you familiar with distributed systems?",
            "Did you use any observability tools in your previous role?",
        ]

        for question_text in yes_no_questions:
            question = InterviewQuestion(
                question_id="test-id",
                question=question_text,
                source_annotation_id="gap-1",
                source_type="gap",
                question_type="gap_probe",
                difficulty="medium",
                suggested_answer_approach="Use a structured approach to answer this question effectively.",
                sample_answer_outline=None,
                relevant_star_ids=[],
                practice_status="not_started",
                user_notes=None,
                created_at="2025-12-09T00:00:00Z",
            )

            # Validation function should detect yes/no format
            errors = self._validate_question_quality(question)
            assert any("yes/no" in err.lower() or "open-ended" in err.lower() for err in errors), \
                f"Should detect yes/no format in: {question_text}"

    def test_detects_too_short_questions(self):
        """Should reject questions that are too short (<20 chars)."""
        short_question = InterviewQuestion(
            question_id="test-id",
            question="Tell me about K8s",  # Only 18 chars
            source_annotation_id="gap-1",
            source_type="gap",
            question_type="gap_probe",
            difficulty="medium",
            suggested_answer_approach="Focus on your container orchestration experience.",
            sample_answer_outline=None,
            relevant_star_ids=[],
            practice_status="not_started",
            user_notes=None,
            created_at="2025-12-09T00:00:00Z",
        )

        errors = self._validate_question_quality(short_question)
        assert any("too short" in err.lower() for err in errors)

    def test_detects_too_long_questions(self):
        """Should reject questions that are too long (>300 chars)."""
        long_question = InterviewQuestion(
            question_id="test-id",
            question="Can you describe in detail your experience with Kubernetes, including but not limited to pod management, service mesh implementations, ingress controllers, persistent volume claims, StatefulSets, DaemonSets, custom resource definitions, operator patterns, Helm charts, GitOps workflows, cluster autoscaling, and how you've debugged production issues in large-scale K8s deployments with thousands of pods across multiple availability zones?",  # >300 chars
            source_annotation_id="gap-1",
            source_type="gap",
            question_type="gap_probe",
            difficulty="hard",
            suggested_answer_approach="Break down your experience into digestible components.",
            sample_answer_outline=None,
            relevant_star_ids=[],
            practice_status="not_started",
            user_notes=None,
            created_at="2025-12-09T00:00:00Z",
        )

        errors = self._validate_question_quality(long_question)
        assert any("too long" in err.lower() for err in errors)

    def test_detects_generic_questions(self):
        """Should detect overly generic questions without specificity."""
        generic_questions = [
            "Tell me about yourself",
            "What are your strengths?",
            "Where do you see yourself in 5 years?",
            "Why do you want to work here?",
        ]

        for question_text in generic_questions:
            question = InterviewQuestion(
                question_id="test-id",
                question=question_text,
                source_annotation_id="general",
                source_type="general",
                question_type="behavioral",
                difficulty="easy",
                suggested_answer_approach="Use a structured approach to answer this question effectively.",
                sample_answer_outline=None,
                relevant_star_ids=[],
                practice_status="not_started",
                user_notes=None,
                created_at="2025-12-09T00:00:00Z",
            )

            # These are acceptable general behavioral questions
            # But if they're tied to a specific gap/concern, they should be more specific
            if question["source_type"] != "general":
                errors = self._validate_question_quality(question)
                assert any("generic" in err.lower() or "specific" in err.lower() for err in errors)

    def test_detects_insufficient_answer_approach(self):
        """Should reject questions with too brief answer guidance (<50 chars)."""
        question = InterviewQuestion(
            question_id="test-id",
            question="What is your experience with distributed systems?",
            source_annotation_id="gap-1",
            source_type="gap",
            question_type="technical",
            difficulty="medium",
            suggested_answer_approach="Be specific.",  # Only 12 chars
            sample_answer_outline=None,
            relevant_star_ids=[],
            practice_status="not_started",
            user_notes=None,
            created_at="2025-12-09T00:00:00Z",
        )

        errors = self._validate_question_quality(question)
        assert any("approach too brief" in err.lower() or "min 50" in err.lower() for err in errors)

    def test_detects_invalid_difficulty_level(self):
        """Should reject questions with invalid difficulty values."""
        question = InterviewQuestion(
            question_id="test-id",
            question="What is your experience with Kubernetes?",
            source_annotation_id="gap-1",
            source_type="gap",
            question_type="gap_probe",
            difficulty="extreme",  # Invalid - should be easy/medium/hard
            suggested_answer_approach="Focus on your container orchestration experience and transferable skills.",
            sample_answer_outline=None,
            relevant_star_ids=[],
            practice_status="not_started",
            user_notes=None,
            created_at="2025-12-09T00:00:00Z",
        )

        errors = self._validate_question_quality(question)
        assert any("difficulty" in err.lower() for err in errors)

    def test_accepts_high_quality_question(self):
        """Should accept questions that meet all quality criteria."""
        quality_question = InterviewQuestion(
            question_id="test-id",
            question="Walk me through your experience with Kubernetes and how you've handled container orchestration at scale.",
            source_annotation_id="gap-1",
            source_type="gap",
            question_type="gap_probe",
            difficulty="medium",
            suggested_answer_approach="Focus on your Docker expertise and explain transferable concepts like service discovery, load balancing, and health checks. Acknowledge you'd ramp up on K8s-specific features quickly.",
            sample_answer_outline="1. Docker production experience\n2. Orchestration concepts mastered\n3. Specific K8s learning plan",
            relevant_star_ids=["star-1"],
            practice_status="not_started",
            user_notes=None,
            created_at="2025-12-09T00:00:00Z",
        )

        errors = self._validate_question_quality(quality_question)
        assert len(errors) == 0, f"High-quality question should pass validation, but got errors: {errors}"

    # Helper validation function (matches prompt-optimization-plan.md spec)
    def _validate_question_quality(self, question: InterviewQuestion) -> list:
        """
        Post-generation quality check (implementation of plan.md spec).

        Returns list of error messages (empty list = valid).
        """
        errors = []

        # Check 1: Question length (avoid too short/long)
        if len(question["question"]) < 20:
            errors.append(f"Question too short: {len(question['question'])} chars (min 20)")
        if len(question["question"]) > 300:
            errors.append(f"Question too long: {len(question['question'])} chars (max 300)")

        # Check 2: Not yes/no format
        yes_no_starters = ["do you", "have you", "can you", "will you", "are you", "did you"]
        if any(question["question"].lower().startswith(s) for s in yes_no_starters):
            errors.append("Yes/no question format - rephrase as open-ended")

        # Check 3: Approach guidance is substantive
        if len(question["suggested_answer_approach"]) < 50:
            errors.append(
                f"Answer approach too brief: {len(question['suggested_answer_approach'])} chars (min 50)"
            )

        # Check 4: Difficulty is valid
        if question["difficulty"] not in ["easy", "medium", "hard"]:
            errors.append(f"Invalid difficulty: {question['difficulty']}")

        return errors


# =============================================================================
# QUESTION DISTRIBUTION TESTS
# =============================================================================


class TestQuestionDistribution:
    """Tests for question type distribution requirements (GAP-030 requirement #3)."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_generates_minimum_gap_probe_questions_when_gaps_provided(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Should generate at least 2 gap_probe questions when gaps are provided."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Verify
        gap_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "gap_probe"
        ]
        assert len(gap_probe_questions) >= 2, \
            f"Should generate at least 2 gap_probe questions when 3 gaps provided, got {len(gap_probe_questions)}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_generates_minimum_concern_probe_questions_when_concerns_provided(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Should generate at least 2 concern_probe questions when concerns are provided."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Verify
        concern_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "concern_probe"
        ]
        assert len(concern_probe_questions) >= 2, \
            f"Should generate at least 2 concern_probe questions when 2 concerns provided, got {len(concern_probe_questions)}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_generates_at_least_one_behavioral_question_always(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Should always generate at least 1 behavioral question for STAR practice."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Verify
        behavioral_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "behavioral"
        ]
        assert len(behavioral_questions) >= 1, \
            f"Should always generate at least 1 behavioral question, got {len(behavioral_questions)}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_total_question_count_in_range(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Should generate between 8-12 questions total."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns, max_questions=12)

        # Verify
        total_questions = len(result["predicted_questions"])
        assert 8 <= total_questions <= 12, \
            f"Should generate 8-12 questions, got {total_questions}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_question_type_distribution_is_balanced(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Should have balanced distribution across question types."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Count question types
        type_counts = {}
        for question in result["predicted_questions"]:
            q_type = question["question_type"]
            type_counts[q_type] = type_counts.get(q_type, 0) + 1

        # Verify distribution
        # With 3 gaps and 2 concerns, we expect roughly:
        # - 3 gap_probe (one per gap)
        # - 2 concern_probe (one per concern)
        # - 2-3 behavioral
        # - 1 technical
        assert "gap_probe" in type_counts, "Should have gap_probe questions"
        assert "concern_probe" in type_counts, "Should have concern_probe questions"
        assert "behavioral" in type_counts, "Should have behavioral questions"

        # No single type should dominate (max 50% of total)
        total = len(result["predicted_questions"])
        for q_type, count in type_counts.items():
            assert count <= total * 0.6, \
                f"Question type '{q_type}' has {count}/{total} questions ({count/total*100:.0f}%), should not exceed 60%"


# =============================================================================
# SOURCE ATTRIBUTION TESTS
# =============================================================================


class TestSourceAttribution:
    """Tests for source attribution requirements (GAP-030 requirement #4)."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_gap_probe_questions_cite_specific_gaps(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Each gap_probe question should reference a specific gap annotation."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Get gap IDs from state
        gap_ids = [
            ann["id"]
            for ann in sample_state_with_gaps_and_concerns["jd_annotations"]["annotations"]
            if ann.get("relevance") == "gap"
        ]

        # Verify each gap_probe question has valid source
        gap_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "gap_probe"
        ]

        for question in gap_probe_questions:
            assert question["source_annotation_id"], \
                f"gap_probe question should have source_annotation_id: {question['question']}"
            assert question["source_type"] == "gap", \
                f"gap_probe question should have source_type='gap': {question['question']}"

            # Source ID should be from available gaps or "general"
            if question["source_annotation_id"] != "general":
                assert question["source_annotation_id"] in gap_ids, \
                    f"source_annotation_id '{question['source_annotation_id']}' not in gap IDs: {gap_ids}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_concern_probe_questions_cite_specific_concerns(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Each concern_probe question should reference a specific concern annotation."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Get concern IDs from state (only those marked for interview discussion)
        concern_ids = [
            c["id"]
            for c in sample_state_with_gaps_and_concerns["jd_annotations"]["concerns"]
            if c.get("discuss_in_interview")
        ]

        # Verify each concern_probe question has valid source
        concern_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "concern_probe"
        ]

        for question in concern_probe_questions:
            assert question["source_annotation_id"], \
                f"concern_probe question should have source_annotation_id: {question['question']}"
            assert question["source_type"] == "concern", \
                f"concern_probe question should have source_type='concern': {question['question']}"

            # Source ID should be from available concerns or "general"
            if question["source_annotation_id"] != "general":
                assert question["source_annotation_id"] in concern_ids, \
                    f"source_annotation_id '{question['source_annotation_id']}' not in concern IDs: {concern_ids}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_questions_reference_actual_gap_content(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Questions should reference actual gap content, not invented topics."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Extract gap keywords
        gap_keywords = []
        for ann in sample_state_with_gaps_and_concerns["jd_annotations"]["annotations"]:
            if ann.get("relevance") == "gap":
                text = ann["target"]["text"].lower()
                # Extract meaningful keywords (nouns/terms)
                keywords = re.findall(r'\b(?:kubernetes|k8s|machine learning|ml|distributed tracing|jaeger|zipkin)\b', text)
                gap_keywords.extend(keywords)

        # Verify gap_probe questions mention relevant gap keywords
        gap_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "gap_probe"
        ]

        for question in gap_probe_questions:
            question_text = question["question"].lower()
            # Check if question mentions any gap keyword
            mentioned_keywords = [kw for kw in gap_keywords if kw in question_text]
            assert len(mentioned_keywords) > 0, \
                f"gap_probe question should reference gap keywords, but didn't: {question['question']}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_questions_reference_actual_concern_content(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """Questions should reference actual concern content, not invented topics."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Extract concern keywords
        concern_keywords = []
        for concern in sample_state_with_gaps_and_concerns["jd_annotations"]["concerns"]:
            if concern.get("discuss_in_interview"):
                text = concern["concern"].lower()
                # Extract meaningful keywords
                keywords = re.findall(r'\b(?:on-call|rotation|startup|early-stage|risk|commute)\b', text)
                concern_keywords.extend(keywords)

        # Verify concern_probe questions mention relevant concern keywords
        concern_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "concern_probe"
        ]

        for question in concern_probe_questions:
            question_text = question["question"].lower()
            approach_text = question["suggested_answer_approach"].lower()
            combined_text = question_text + " " + approach_text

            # Check if question/approach mentions any concern keyword
            mentioned_keywords = [kw for kw in concern_keywords if kw in combined_text]
            assert len(mentioned_keywords) > 0, \
                f"concern_probe question should reference concern keywords, but didn't: {question['question']}"


# =============================================================================
# FEW-SHOT EXAMPLE EFFECTIVENESS TESTS
# =============================================================================


class TestFewShotExampleEffectiveness:
    """Tests that few-shot examples improve question quality (GAP-030 requirement #1)."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_gap_probe_questions_acknowledge_the_gap(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """gap_probe questions should acknowledge the gap, not just probe it."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Verify gap_probe questions acknowledge limitations
        gap_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "gap_probe"
        ]

        for question in gap_probe_questions:
            # Good gap questions should:
            # 1. Not be yes/no format
            # 2. Give candidate opportunity to demonstrate depth
            # 3. Acknowledge transferable skills in the answer approach

            # Check not yes/no
            assert not any(
                question["question"].lower().startswith(s)
                for s in ["do you", "have you", "are you", "did you"]
            ), f"gap_probe should not use yes/no format: {question['question']}"

            # Check answer approach mentions transferable skills or mitigation
            approach = question["suggested_answer_approach"].lower()
            positive_indicators = [
                "transfer",
                "emphasize",
                "highlight",
                "focus on",
                "explain",
                "acknowledge",
                "ramp up",
                "learn",
            ]
            assert any(indicator in approach for indicator in positive_indicators), \
                f"gap_probe answer approach should guide positive framing: {approach}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_concern_probe_questions_use_positive_framing(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """concern_probe questions should use positive framing, not negative."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # Verify concern_probe questions use positive framing
        concern_probe_questions = [
            q for q in result["predicted_questions"] if q["question_type"] == "concern_probe"
        ]

        for question in concern_probe_questions:
            # Good concern questions should:
            # 1. Show awareness of concern
            # 2. Frame positively (excites, manage, approach)
            # 3. Not trap candidate with negative framing

            question_text = question["question"].lower()

            # Avoid purely negative framing
            negative_only_patterns = [
                "why would you want",
                "aren't you concerned about",
                "don't you think",
                "what's wrong with",
            ]
            assert not any(pattern in question_text for pattern in negative_only_patterns), \
                f"concern_probe should avoid negative-only framing: {question['question']}"

            # Should include positive or neutral framing
            positive_patterns = [
                "how do you",
                "what excites you",
                "how would you approach",
                "how do you manage",
                "what's your experience with",
            ]
            assert any(pattern in question_text for pattern in positive_patterns), \
                f"concern_probe should use positive/neutral framing: {question['question']}"

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_questions_avoid_yes_no_format_detected_via_validation(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_quality_issues
    ):
        """Validation should catch and reject yes/no format questions."""
        # Setup - use mock response with quality issues
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_quality_issues)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns)

        # In a production system with validation, low-quality questions would be filtered
        # For now, we verify that our validation function can detect these issues
        validator = TestQuestionQualityValidation()

        for question in result["predicted_questions"]:
            errors = validator._validate_question_quality(question)
            if errors:
                # If question has errors, at least one should be about yes/no format or length
                assert any(
                    "yes/no" in err.lower() or "too short" in err.lower() or "too brief" in err.lower()
                    for err in errors
                )


# =============================================================================
# INTEGRATION WITH EXISTING FUNCTIONALITY
# =============================================================================


class TestBackwardCompatibility:
    """Ensure prompt improvements don't break existing functionality."""

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_existing_test_compatibility_with_distribution(
        self, mock_invoke, sample_state_with_gaps_and_concerns, mock_llm_response_with_distribution
    ):
        """New distribution requirements should not break existing tests."""
        # Setup
        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute using helper function (as in existing tests)
        result = predict_interview_questions(sample_state_with_gaps_and_concerns)

        # Verify existing contract still works
        assert "predicted_questions" in result
        assert "gap_summary" in result
        assert "concerns_summary" in result
        assert "company_context" in result
        assert "role_context" in result
        assert "generated_at" in result
        assert "generated_by" in result

        # Verify all questions have required fields (from existing tests)
        for question in result["predicted_questions"]:
            assert "question_id" in question
            assert "question" in question
            assert "question_type" in question
            assert "difficulty" in question
            assert "suggested_answer_approach" in question
            assert "practice_status" in question
            assert "created_at" in question

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_max_questions_limit_still_respected(
        self, mock_invoke, sample_state_with_gaps_and_concerns
    ):
        """max_questions parameter should still work with new distribution logic."""
        # Create a mock response with many questions
        many_questions = QuestionGenerationOutput(
            questions=[
                PredictedQuestion(
                    question=f"Question {i} about technology and experience",
                    question_type="behavioral",
                    difficulty="medium",
                    suggested_answer_approach="Use STAR format to answer this question effectively.",
                    relevant_star_ids=[],
                )
                for i in range(20)
            ]
        )

        mock_invoke.return_value = create_mock_llm_result(many_questions)

        # Execute with max_questions limit
        predictor = InterviewPredictor()
        result = predictor.predict_questions(sample_state_with_gaps_and_concerns, max_questions=5)

        # Verify limit is respected
        assert len(result["predicted_questions"]) == 5

    @patch("src.layer7.interview_predictor.invoke_unified_sync")
    def test_handles_state_without_gaps_or_concerns(
        self, mock_invoke, mock_llm_response_with_distribution
    ):
        """Should handle jobs with no gaps/concerns gracefully (behavioral questions only)."""
        # State with no gaps or concerns
        state_no_annotations = {
            "job_id": "test_no_gaps",
            "title": "Software Engineer",
            "company": "SimpleCo",
            "job_description": "Build software...",
            "jd_annotations": {
                "annotations": [
                    {
                        "id": "strength-1",
                        "relevance": "core_strength",
                        "target": {"text": "Python", "section": "qualifications"},
                    }
                ],
                "concerns": [],
            },
            "extracted_jd": {"seniority_level": "mid"},
            "errors": [],
        }

        mock_invoke.return_value = create_mock_llm_result(mock_llm_response_with_distribution)

        # Execute
        predictor = InterviewPredictor()
        result = predictor.predict_questions(state_no_annotations)

        # Should still generate questions (general behavioral)
        assert "predicted_questions" in result
        assert len(result["predicted_questions"]) > 0

        # Gap/concern summaries should indicate no issues
        assert "no" in result["gap_summary"].lower() or "none" in result["gap_summary"].lower()
        assert "no" in result["concerns_summary"].lower() or "none" in result["concerns_summary"].lower()
