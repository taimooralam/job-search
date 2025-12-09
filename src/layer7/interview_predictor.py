"""
Interview Question Predictor (Phase 7).

Generates likely interview questions from JD gaps and concerns.
Uses gap annotations and concern annotations as source material.

Key Features:
- Questions grounded in actual gaps (anti-hallucination)
- STAR story linking for answer preparation
- Difficulty classification for practice prioritization
- Sample answer outlines (not full answers - user should prep)

Usage:
    from src.layer7.interview_predictor import InterviewPredictor, predict_interview_questions

    # Via class
    predictor = InterviewPredictor()
    interview_prep = predictor.predict_questions(job_state)

    # Via helper function
    interview_prep = predict_interview_questions(job_state)
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.common.annotation_types import (
    ConcernAnnotation,
    InterviewPrep,
    InterviewQuestion,
    JDAnnotation,
)
from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.state import JobState

logger = logging.getLogger(__name__)


# =============================================================================
# QUESTION TYPES
# =============================================================================

QUESTION_TYPES = {
    "gap_probe": "Question that probes a skill/experience gap",
    "concern_probe": "Question that addresses a red flag or concern",
    "behavioral": "Behavioral question (STAR format expected)",
    "technical": "Technical deep-dive question",
    "situational": "Hypothetical situation question",
}

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]


# =============================================================================
# PYDANTIC SCHEMAS FOR STRUCTURED OUTPUT
# =============================================================================


class PredictedQuestion(BaseModel):
    """Single predicted interview question."""

    question: str = Field(description="The interview question text")
    question_type: str = Field(
        description="Question type: gap_probe, concern_probe, behavioral, technical, situational"
    )
    difficulty: str = Field(description="Difficulty level: easy, medium, hard")
    suggested_answer_approach: str = Field(
        description="2-3 sentence guidance on how to approach answering"
    )
    sample_answer_outline: Optional[str] = Field(
        default=None, description="Brief bullet point outline for answer structure"
    )
    relevant_star_ids: List[str] = Field(
        default_factory=list, description="IDs of relevant STAR stories from candidate profile"
    )


class QuestionGenerationOutput(BaseModel):
    """Output from LLM question generation."""

    questions: List[PredictedQuestion] = Field(
        description="List of predicted interview questions"
    )


# =============================================================================
# PROMPTS
# =============================================================================

QUESTION_GENERATION_SYSTEM_PROMPT = """You are an expert interview coach who predicts likely interview questions based on job requirements and candidate gaps.

## Your Task
Analyze the provided gaps (skills/experience the candidate lacks) and concerns (red flags or mismatches) to predict 8-12 interview questions the candidate is likely to face.

## CRITICAL Anti-Hallucination Rules
1. ONLY generate questions based on the provided gaps and concerns - do NOT invent new topics
2. Each question MUST directly relate to a specific gap or concern provided
3. If there are no gaps or concerns, generate general behavioral questions based on the role requirements
4. Do NOT assume skills or experiences not mentioned in the context

## Question Types
- gap_probe: Questions that dig into skill/experience gaps
- concern_probe: Questions addressing specific concerns or red flags
- behavioral: Standard "Tell me about a time..." questions
- technical: Deep-dive technical questions
- situational: "What would you do if..." hypothetical scenarios

## Difficulty Levels
- easy: Straightforward questions with obvious preparation path
- medium: Requires thoughtful preparation and examples
- hard: Complex questions requiring nuanced answers or addressing weaknesses

## Output Requirements
For each question provide:
1. The question text (clear, professional phrasing)
2. Question type (from types above)
3. Difficulty level (easy/medium/hard)
4. Suggested answer approach (2-3 sentences on how to prepare)
5. Sample answer outline (optional, brief bullet points if helpful)
6. Relevant STAR IDs (from the candidate's STAR stories list, if applicable)

Generate questions that:
- Cover the most significant gaps first
- Address concerns marked for interview discussion
- Include a mix of difficulty levels
- Are realistic for the role and seniority level"""

QUESTION_GENERATION_USER_PROMPT = """## Job Details
- Role: {role_title}
- Company: {company}
- Seniority: {seniority_level}

## Gaps to Address
{gaps_text}

## Concerns to Address
{concerns_text}

## Available STAR Stories for Answer Preparation
{stars_text}

## Instructions
Generate 8-12 interview questions that:
1. Probe the identified gaps
2. Address the listed concerns
3. Are appropriate for a {seniority_level} level role
4. Include a mix of easy, medium, and hard questions

Focus on questions the candidate can prepare for productively."""


# =============================================================================
# INTERVIEW PREDICTOR CLASS
# =============================================================================


class InterviewPredictor:
    """
    Predicts interview questions from gaps and concerns.

    Algorithm:
    1. Extract gap annotations (relevance="gap")
    2. Extract concerns marked for interview discussion
    3. For each gap/concern, generate 1-3 likely questions
    4. Link relevant STAR stories for answer preparation
    5. Classify difficulty and provide answer approach
    """

    def __init__(self, model: Optional[str] = None, temperature: float = 0.3):
        """
        Initialize the interview predictor.

        Args:
            model: LLM model to use (defaults to Config.DEFAULT_MODEL)
            temperature: Temperature for generation (default 0.3 for consistency)
        """
        self.model = model or Config.DEFAULT_MODEL
        self.temperature = temperature

    def predict_questions(
        self,
        state: JobState,
        max_questions: int = 12,
    ) -> InterviewPrep:
        """
        Generate interview questions from job state.

        Args:
            state: JobState with annotations, concerns, STARs
            max_questions: Maximum questions to generate (default 12)

        Returns:
            InterviewPrep with predicted questions
        """
        logger.info(f"Predicting interview questions for job: {state.get('job_id', 'unknown')}")

        # Extract gaps and concerns
        jd_annotations = state.get("jd_annotations") or {}
        annotations = jd_annotations.get("annotations", [])
        concerns = jd_annotations.get("concerns", [])

        gaps = [a for a in annotations if a.get("relevance") == "gap"]
        interview_concerns = [c for c in concerns if c.get("discuss_in_interview", False)]

        logger.info(f"Found {len(gaps)} gaps and {len(interview_concerns)} concerns to address")

        # Get available STARs for linking
        all_stars = state.get("all_stars") or state.get("selected_stars") or []
        star_ids = [s.get("id", "") for s in all_stars if s.get("id")]

        # Generate questions via LLM
        questions = self._generate_questions(
            gaps=gaps,
            concerns=interview_concerns,
            job_title=state.get("title", ""),
            company=state.get("company", ""),
            seniority_level=self._get_seniority_level(state),
            star_ids=star_ids,
            max_questions=max_questions,
        )

        # Build summaries
        gap_summary = self._build_gap_summary(gaps)
        concerns_summary = self._build_concerns_summary(interview_concerns)

        return InterviewPrep(
            predicted_questions=questions,
            gap_summary=gap_summary,
            concerns_summary=concerns_summary,
            company_context=self._extract_company_context(state),
            role_context=self._extract_role_context(state),
            generated_at=datetime.utcnow().isoformat(),
            generated_by=self.model,
        )

    def _get_seniority_level(self, state: JobState) -> str:
        """Extract seniority level from state or default to 'senior'."""
        extracted_jd = state.get("extracted_jd") or {}
        return extracted_jd.get("seniority_level", "senior")

    def _generate_questions(
        self,
        gaps: List[JDAnnotation],
        concerns: List[ConcernAnnotation],
        job_title: str,
        company: str,
        seniority_level: str,
        star_ids: List[str],
        max_questions: int,
    ) -> List[InterviewQuestion]:
        """Generate questions via LLM."""
        # Format gaps text
        gaps_text = self._format_gaps_for_prompt(gaps)
        concerns_text = self._format_concerns_for_prompt(concerns)
        stars_text = self._format_stars_for_prompt(star_ids)

        # Handle empty inputs
        if not gaps_text and not concerns_text:
            gaps_text = "No specific gaps identified. Generate general behavioral questions for the role."

        # Create LLM with structured output
        llm = create_tracked_llm(
            model=self.model,
            temperature=self.temperature,
            layer="layer7_interview_prep",
        )

        structured_llm = llm.with_structured_output(QuestionGenerationOutput)

        # Build messages
        system_msg = SystemMessage(content=QUESTION_GENERATION_SYSTEM_PROMPT)
        user_msg = HumanMessage(
            content=QUESTION_GENERATION_USER_PROMPT.format(
                role_title=job_title,
                company=company,
                seniority_level=seniority_level,
                gaps_text=gaps_text,
                concerns_text=concerns_text,
                stars_text=stars_text,
            )
        )

        try:
            result = structured_llm.invoke([system_msg, user_msg])

            # Convert to InterviewQuestion format
            questions = []
            source_annotation_ids = self._get_source_annotation_ids(gaps, concerns)

            for i, q in enumerate(result.questions[:max_questions]):
                question = InterviewQuestion(
                    question_id=str(uuid.uuid4()),
                    question=q.question,
                    source_annotation_id=source_annotation_ids[i % len(source_annotation_ids)]
                    if source_annotation_ids
                    else "",
                    source_type=self._determine_source_type(q.question_type),
                    question_type=q.question_type,
                    difficulty=q.difficulty if q.difficulty in DIFFICULTY_LEVELS else "medium",
                    suggested_answer_approach=q.suggested_answer_approach,
                    sample_answer_outline=q.sample_answer_outline,
                    relevant_star_ids=q.relevant_star_ids,
                    practice_status="not_started",
                    user_notes=None,
                    created_at=datetime.utcnow().isoformat(),
                )
                questions.append(question)

            logger.info(f"Generated {len(questions)} interview questions")
            return questions

        except Exception as e:
            logger.error(f"Failed to generate interview questions: {e}")
            # Return empty list on failure - don't crash the whole system
            return []

    def _format_gaps_for_prompt(self, gaps: List[JDAnnotation]) -> str:
        """Format gaps for inclusion in prompt."""
        if not gaps:
            return ""

        lines = []
        for i, gap in enumerate(gaps, 1):
            target = gap.get("target", {})
            text = target.get("text", "Unknown requirement")
            matching_skill = gap.get("matching_skill", "")
            reframe = gap.get("reframe_note", "")

            line = f"{i}. GAP: {text}"
            if matching_skill:
                line += f"\n   Closest Match: {matching_skill}"
            if reframe:
                line += f"\n   Mitigation: {reframe}"
            lines.append(line)

        return "\n".join(lines)

    def _format_concerns_for_prompt(self, concerns: List[ConcernAnnotation]) -> str:
        """Format concerns for inclusion in prompt."""
        if not concerns:
            return ""

        lines = []
        for i, concern in enumerate(concerns, 1):
            text = concern.get("concern", "Unknown concern")
            severity = concern.get("severity", "concern")
            mitigation = concern.get("mitigation_strategy", "")

            line = f"{i}. CONCERN ({severity}): {text}"
            if mitigation:
                line += f"\n   Mitigation Strategy: {mitigation}"
            lines.append(line)

        return "\n".join(lines)

    def _format_stars_for_prompt(self, star_ids: List[str]) -> str:
        """Format available STAR IDs for the prompt."""
        if not star_ids:
            return "No STAR stories available."

        return "Available STAR story IDs: " + ", ".join(star_ids[:20])  # Limit to avoid token bloat

    def _get_source_annotation_ids(
        self, gaps: List[JDAnnotation], concerns: List[ConcernAnnotation]
    ) -> List[str]:
        """Get annotation IDs to link questions to sources."""
        ids = []
        for gap in gaps:
            if gap.get("id"):
                ids.append(gap["id"])
        for concern in concerns:
            if concern.get("id"):
                ids.append(concern["id"])
        return ids if ids else ["general"]

    def _determine_source_type(self, question_type: str) -> str:
        """Determine source type from question type."""
        if question_type == "gap_probe":
            return "gap"
        elif question_type == "concern_probe":
            return "concern"
        else:
            return "general"

    def _build_gap_summary(self, gaps: List[JDAnnotation]) -> str:
        """Build a summary of gaps to address."""
        if not gaps:
            return "No significant skill gaps identified."

        gap_texts = []
        for gap in gaps[:5]:  # Top 5 gaps
            target = gap.get("target", {})
            text = target.get("text", "")
            if text:
                gap_texts.append(text[:100])  # Truncate long texts

        return f"Key gaps to address: {'; '.join(gap_texts)}"

    def _build_concerns_summary(self, concerns: List[ConcernAnnotation]) -> str:
        """Build a summary of concerns to address."""
        if not concerns:
            return "No significant concerns flagged for discussion."

        concern_texts = []
        for concern in concerns[:3]:  # Top 3 concerns
            text = concern.get("concern", "")
            if text:
                concern_texts.append(text[:100])

        return f"Key concerns to address: {'; '.join(concern_texts)}"

    def _extract_company_context(self, state: JobState) -> str:
        """Extract key company facts for interview context."""
        company_research = state.get("company_research") or {}
        company_summary = company_research.get("summary", "") or state.get("company_summary", "")

        if company_summary:
            return company_summary[:500]  # Truncate to reasonable length
        return f"Company: {state.get('company', 'Unknown')}"

    def _extract_role_context(self, state: JobState) -> str:
        """Extract key role insights for interview context."""
        role_research = state.get("role_research") or {}
        role_summary = role_research.get("summary", "")

        if role_summary:
            return role_summary[:500]

        # Fall back to extracted JD insights
        extracted_jd = state.get("extracted_jd") or {}
        responsibilities = extracted_jd.get("responsibilities", [])
        if responsibilities:
            return "Key responsibilities: " + "; ".join(responsibilities[:3])

        return f"Role: {state.get('title', 'Unknown')}"


# =============================================================================
# HELPER FUNCTION
# =============================================================================


def predict_interview_questions(
    state: JobState,
    max_questions: int = 12,
    model: Optional[str] = None,
) -> InterviewPrep:
    """
    Convenience function to predict interview questions from job state.

    Args:
        state: JobState with annotations and concerns
        max_questions: Maximum questions to generate
        model: Optional model override

    Returns:
        InterviewPrep with predicted questions
    """
    predictor = InterviewPredictor(model=model)
    return predictor.predict_questions(state, max_questions=max_questions)
