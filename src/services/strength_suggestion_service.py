"""
Strength Suggestion Service for JD Annotation System.

Analyzes job description requirements against candidate's master-cv profile
to suggest annotation strengths (skills the candidate HAS that match the JD).

This is the inverse of gap analysis - focusing on what to highlight, not what's missing.
"""

import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


class StrengthSuggestion(TypedDict):
    """A single strength suggestion for annotation creation."""

    target_text: str  # Text from JD to annotate
    target_section: Optional[str]  # JD section if known
    suggested_relevance: str  # core_strength, extremely_relevant, etc.
    suggested_requirement: str  # must_have, nice_to_have, etc.
    suggested_passion: Optional[str]  # love_it, enjoy, neutral, etc.
    suggested_identity: Optional[str]  # core_identity, strong_identity, etc.
    matching_skill: str  # Candidate skill that matches
    matching_role: Optional[str]  # Role where skill was used
    evidence_summary: Optional[str]  # Brief evidence from master-cv
    reframe_note: Optional[str]  # How to position the match
    suggested_keywords: List[str]  # ATS keywords to include
    confidence: float  # 0.0-1.0 confidence
    source: str  # "llm_match" | "hardcoded_default"


# Hardcoded defaults for common skill patterns
# These provide instant suggestions without LLM for frequently-encountered skills
HARDCODED_STRENGTH_PATTERNS: Dict[str, Dict[str, Any]] = {
    "distributed systems": {
        "relevance": "core_strength",
        "passion": "love_it",
        "identity": "core_identity",
        "keywords": ["distributed systems", "microservices", "scalability"],
    },
    "python": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["Python", "python3", "FastAPI", "Django"],
    },
    "leadership": {
        "relevance": "core_strength",
        "passion": "enjoy",
        "identity": "core_identity",
        "keywords": ["leadership", "team lead", "mentoring", "coaching"],
    },
    "aws": {
        "relevance": "extremely_relevant",
        "passion": "neutral",
        "identity": "strong_identity",
        "keywords": ["AWS", "Amazon Web Services", "cloud", "EC2", "S3"],
    },
    "kubernetes": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["Kubernetes", "K8s", "container orchestration", "Docker"],
    },
    "machine learning": {
        "relevance": "extremely_relevant",
        "passion": "love_it",
        "identity": "developing",
        "keywords": ["machine learning", "ML", "AI", "deep learning"],
    },
    "data engineering": {
        "relevance": "core_strength",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["data engineering", "ETL", "data pipelines", "Spark"],
    },
    "agile": {
        "relevance": "relevant",
        "passion": "neutral",
        "identity": "peripheral",
        "keywords": ["Agile", "Scrum", "Kanban", "sprint"],
    },
    "ci/cd": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["CI/CD", "continuous integration", "deployment", "DevOps"],
    },
    "typescript": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["TypeScript", "JavaScript", "Node.js", "React"],
    },
    "team management": {
        "relevance": "core_strength",
        "passion": "enjoy",
        "identity": "core_identity",
        "keywords": ["team management", "people management", "team lead"],
    },
    "engineering manager": {
        "relevance": "core_strength",
        "passion": "love_it",
        "identity": "core_identity",
        "keywords": ["engineering manager", "EM", "tech lead", "manager"],
    },
    "architecture": {
        "relevance": "core_strength",
        "passion": "love_it",
        "identity": "core_identity",
        "keywords": ["architecture", "system design", "technical architecture"],
    },
    "stakeholder": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["stakeholder management", "cross-functional", "collaboration"],
    },
    "postgresql": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["PostgreSQL", "Postgres", "SQL", "database"],
    },
    "mongodb": {
        "relevance": "extremely_relevant",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["MongoDB", "NoSQL", "document database"],
    },
    "fastapi": {
        "relevance": "extremely_relevant",
        "passion": "love_it",
        "identity": "strong_identity",
        "keywords": ["FastAPI", "Python API", "REST API"],
    },
    "hiring": {
        "relevance": "core_strength",
        "passion": "enjoy",
        "identity": "strong_identity",
        "keywords": ["hiring", "recruiting", "talent acquisition", "interviewing"],
    },
    "mentoring": {
        "relevance": "core_strength",
        "passion": "love_it",
        "identity": "core_identity",
        "keywords": ["mentoring", "coaching", "career development"],
    },
}


class StrengthSuggestionService:
    """Service for generating strength suggestions from JD analysis."""

    def __init__(
        self,
        llm: Optional[ChatOpenAI] = None,
        model_name: str = "anthropic/claude-3-haiku",
    ):
        """Initialize the strength suggestion service.

        Args:
            llm: Optional pre-configured LLM instance
            model_name: Model name for new LLM instance if not provided
        """
        self.llm = llm
        self.model_name = model_name
        self._logger = logging.getLogger(self.__class__.__name__)

    def suggest_strengths(
        self,
        jd_text: str,
        candidate_profile: Dict[str, Any],
        existing_annotations: Optional[List[Dict[str, Any]]] = None,
        include_identity: bool = True,
        include_passion: bool = True,
        include_defaults: bool = True,
    ) -> List[StrengthSuggestion]:
        """
        Generate strength suggestions by matching JD requirements to candidate profile.

        Args:
            jd_text: The job description text
            candidate_profile: Dict with skills, roles, experience from master-cv
            existing_annotations: List of existing annotations to avoid duplicates
            include_identity: Whether to suggest identity levels
            include_passion: Whether to suggest passion levels
            include_defaults: Whether to apply hardcoded defaults

        Returns:
            List of StrengthSuggestion dicts
        """
        suggestions: List[StrengthSuggestion] = []
        existing_annotations = existing_annotations or []

        # Get already-annotated text spans to avoid duplicates
        annotated_texts = {
            ann.get("target", {}).get("text", "").lower()
            for ann in existing_annotations
            if ann.get("is_active", True)
        }

        # Phase 1: Apply hardcoded defaults (fast, no LLM)
        if include_defaults:
            default_suggestions = self._apply_hardcoded_defaults(
                jd_text, candidate_profile, annotated_texts
            )
            suggestions.extend(default_suggestions)
            self._logger.debug(f"Applied {len(default_suggestions)} hardcoded defaults")

        # Phase 2: LLM-based matching (if available)
        if self.llm:
            llm_suggestions = self._generate_llm_suggestions(
                jd_text,
                candidate_profile,
                annotated_texts,
                include_identity,
                include_passion,
            )
            # Deduplicate against hardcoded defaults
            existing_targets = {s["target_text"].lower() for s in suggestions}
            for llm_sug in llm_suggestions:
                if llm_sug["target_text"].lower() not in existing_targets:
                    suggestions.append(llm_sug)
            self._logger.debug(f"Added {len(llm_suggestions)} LLM suggestions")

        # Sort by confidence (highest first)
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)

        return suggestions

    def _apply_hardcoded_defaults(
        self,
        jd_text: str,
        candidate_profile: Dict[str, Any],
        annotated_texts: set,
    ) -> List[StrengthSuggestion]:
        """Match hardcoded patterns against JD and candidate skills."""
        suggestions = []
        jd_lower = jd_text.lower()

        # Extract candidate skills from profile
        candidate_skills = set()
        for skill in candidate_profile.get("skills", []):
            if isinstance(skill, str):
                candidate_skills.add(skill.lower())
            elif isinstance(skill, dict):
                candidate_skills.add(skill.get("name", "").lower())

        # Also check role keywords
        for role in candidate_profile.get("roles", []):
            for kw in role.get("keywords", []):
                candidate_skills.add(kw.lower())
            for skill in role.get("hard_skills", []):
                candidate_skills.add(skill.lower())

        for pattern, defaults in HARDCODED_STRENGTH_PATTERNS.items():
            # Check if pattern mentioned in JD
            if pattern not in jd_lower:
                continue

            # Check if candidate has this skill
            if not self._candidate_has_skill(pattern, candidate_skills):
                continue

            # Extract relevant phrase from JD
            target_text = self._extract_relevant_phrase(jd_text, pattern)

            # Skip if already annotated
            if target_text.lower() in annotated_texts:
                continue

            suggestions.append(
                StrengthSuggestion(
                    target_text=target_text,
                    target_section=None,
                    suggested_relevance=defaults["relevance"],
                    suggested_requirement="neutral",
                    suggested_passion=defaults.get("passion"),
                    suggested_identity=defaults.get("identity"),
                    matching_skill=pattern.title(),
                    matching_role=None,
                    evidence_summary=None,
                    reframe_note=None,
                    suggested_keywords=defaults.get("keywords", []),
                    confidence=0.75,  # Lower confidence for hardcoded
                    source="hardcoded_default",
                )
            )

        return suggestions

    def _candidate_has_skill(self, pattern: str, candidate_skills: set) -> bool:
        """Check if candidate has a skill matching the pattern."""
        pattern_lower = pattern.lower()

        # Direct match
        if pattern_lower in candidate_skills:
            return True

        # Partial match (e.g., "python" matches "python programming")
        for skill in candidate_skills:
            if pattern_lower in skill or skill in pattern_lower:
                return True

        return False

    def _extract_relevant_phrase(
        self, jd_text: str, keyword: str, context_chars: int = 80
    ) -> str:
        """Extract a phrase from JD containing the keyword with surrounding context."""
        jd_lower = jd_text.lower()
        idx = jd_lower.find(keyword.lower())

        if idx == -1:
            return keyword

        # Find sentence boundaries
        start = max(0, idx - context_chars)
        end = min(len(jd_text), idx + len(keyword) + context_chars)

        # Adjust to sentence/phrase boundaries
        while start > 0 and jd_text[start] not in ".!?\n":
            start -= 1
        if start > 0:
            start += 1  # Skip the punctuation

        while end < len(jd_text) and jd_text[end] not in ".!?\n":
            end += 1

        phrase = jd_text[start:end].strip()

        # Trim if too long
        if len(phrase) > 200:
            phrase = jd_text[idx : idx + len(keyword) + 50].strip()

        return phrase

    def _generate_llm_suggestions(
        self,
        jd_text: str,
        candidate_profile: Dict[str, Any],
        annotated_texts: set,
        include_identity: bool,
        include_passion: bool,
    ) -> List[StrengthSuggestion]:
        """Generate suggestions using LLM analysis."""
        if not self.llm:
            return []

        # Build profile summary
        profile_summary = self._build_profile_summary(candidate_profile)

        system_prompt = """You are an expert career advisor analyzing job requirements against a candidate's profile.

Your task is to identify STRENGTHS - requirements in the job description that the candidate CAN fulfill based on their experience.

For each strength match, provide:
1. target_text: The exact phrase from the JD that the candidate matches
2. suggested_relevance: One of: core_strength, extremely_relevant, relevant, tangential
3. matching_skill: The candidate's skill/experience that matches
4. evidence_summary: Brief evidence from their profile
5. suggested_keywords: ATS keywords to include
6. confidence: 0.0-1.0 how confident you are in this match"""

        if include_identity:
            system_prompt += """
7. suggested_identity: One of: core_identity (defines who they are), strong_identity, developing, peripheral, not_identity"""

        if include_passion:
            system_prompt += """
8. suggested_passion: One of: love_it, enjoy, neutral, tolerate, avoid"""

        system_prompt += """

Return a JSON array of strength matches. Only include strong matches (confidence > 0.6).
Do NOT include skills the candidate lacks - that's gap analysis, not strength analysis."""

        user_prompt = f"""## Job Description
{jd_text[:3000]}

## Candidate Profile
{profile_summary}

Identify the candidate's STRENGTHS that match this job description.
Return JSON array of matches."""

        try:
            response = self.llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )

            # Parse JSON response
            content = response.content

            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            matches = json.loads(content)

            suggestions = []
            for match in matches:
                target_text = match.get("target_text", "")

                # Skip if already annotated
                if target_text.lower() in annotated_texts:
                    continue

                suggestions.append(
                    StrengthSuggestion(
                        target_text=target_text,
                        target_section=None,
                        suggested_relevance=match.get("suggested_relevance", "relevant"),
                        suggested_requirement="neutral",
                        suggested_passion=match.get("suggested_passion")
                        if include_passion
                        else None,
                        suggested_identity=match.get("suggested_identity")
                        if include_identity
                        else None,
                        matching_skill=match.get("matching_skill", ""),
                        matching_role=None,
                        evidence_summary=match.get("evidence_summary"),
                        reframe_note=match.get("reframe_note"),
                        suggested_keywords=match.get("suggested_keywords", []),
                        confidence=float(match.get("confidence", 0.7)),
                        source="llm_match",
                    )
                )

            return suggestions

        except Exception as e:
            self._logger.error(f"LLM suggestion failed: {e}")
            return []

    def _build_profile_summary(self, candidate_profile: Dict[str, Any]) -> str:
        """Build a concise profile summary for LLM context."""
        lines = []

        # Skills
        skills = candidate_profile.get("skills", [])
        if skills:
            skill_names = [
                s if isinstance(s, str) else s.get("name", "") for s in skills[:30]
            ]
            lines.append(f"**Skills**: {', '.join(skill_names)}")

        # Roles/Experience
        roles = candidate_profile.get("roles", [])
        for role in roles[:5]:
            role_name = role.get("title", role.get("name", "Unknown"))
            company = role.get("company", "")
            keywords = role.get("keywords", [])[:10]
            lines.append(f"**{role_name}** at {company}: {', '.join(keywords)}")

        # Summary if available
        summary = candidate_profile.get("summary", "")
        if summary:
            lines.append(f"**Summary**: {summary[:500]}")

        return "\n".join(lines)
