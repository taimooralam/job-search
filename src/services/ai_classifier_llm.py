"""
LLM-Based AI Job Classifier

Replaces regex-based classification with Haiku LLM for semantic understanding
of AI job relevance. Uses the candidate's Commander-4 project as context to assess
whether a role is relevant to their AI/LLM infrastructure experience.

Called at extraction time (per-job), NOT at ingest time (regex is kept for bulk).
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.common.ai_classifier import AIClassification
from src.common.unified_llm import invoke_unified_sync

logger = logging.getLogger(__name__)

# Valid categories — same as regex classifier for backward compatibility
VALID_CATEGORIES = {
    "ai_general", "genai_llm", "agentic_ai", "rag_retrieval",
    "mlops_llmops", "fine_tuning", "ai_governance", "prompt_engineering",
    "data_science",
}

# ── AI project context (loaded once) ────────────────────
_ai_project_context: Optional[str] = None


def _load_ai_project_context() -> str:
    """Load AI project summary for candidate AI profile."""
    global _ai_project_context
    if _ai_project_context is not None:
        return _ai_project_context

    project_path = Path(__file__).parent.parent.parent / "data" / "master-cv" / "projects" / "commander4.md"
    try:
        _ai_project_context = project_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"AI project file not found at {project_path}")
        _ai_project_context = (
            "Candidate leads Commander-4 (Joyia), an enterprise AI workflow platform at "
            "ProSiebenSat.1 serving 2,000 users with 42 plugins — hybrid retrieval, "
            "document ingestion, structured outputs, and semantic caching."
        )
    return _ai_project_context


# ── Prompts ──────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a technical recruiter specialized in AI/ML roles.

Classify whether this job is relevant to a candidate with AI/LLM infrastructure experience:
- LLM gateways and multi-provider routing
- Semantic caching and vector databases
- MLOps / LLMOps pipelines
- Agentic AI frameworks (LangGraph, LangChain)
- RAG systems and embeddings

Be inclusive but honest. A role doesn't need to be "AI Engineer" to be relevant — platform engineering roles that involve AI infrastructure, backend roles building LLM features, or architect roles overseeing AI adoption all count.

Respond with ONLY valid JSON, no markdown fences."""

USER_PROMPT_TEMPLATE = """Classify this job for AI relevance.

=== JOB ===
Title: {title}
Company: {company}

Description:
{description}

{extracted_jd_section}

=== CANDIDATE AI PROFILE ===
{lantern_context}

=== OUTPUT FORMAT ===
Return JSON:
{{
  "is_ai_job": true/false,
  "categories": ["category1", "category2"],
  "rationale": "1-2 sentence explanation"
}}

Valid categories: ai_general, genai_llm, agentic_ai, rag_retrieval, mlops_llmops, fine_tuning, ai_governance, prompt_engineering, data_science

Rules:
- AUTOMATIC: If the job title contains any of these terms, ALWAYS classify as is_ai_job=true: "AI", "Gen AI", "GenAI", "Generative AI", "Agentic AI", "AGI", "LLM", "Machine Learning", "ML"
- For other titles, "is_ai_job" = true only if the role has meaningful AI/ML relevance (not just mentioning "AI" in passing in the description)
- Choose 0-3 most relevant categories
- If not an AI job, return empty categories and explain why"""


# ── Dataclass ────────────────────────────────────────────────

@dataclass
class AIClassificationLLM(AIClassification):
    """Extended classification result with LLM rationale."""
    ai_rationale: Optional[str] = None
    ai_classified_at: Optional[datetime] = None


# ── Core functions ───────────────────────────────────────────

def _build_extracted_jd_section(extracted_jd: Optional[Dict[str, Any]]) -> str:
    """Build extracted JD section for the prompt if available."""
    if not extracted_jd:
        return ""

    parts = []
    for key in ("technical_skills", "top_keywords", "responsibilities", "qualifications"):
        val = extracted_jd.get(key)
        if isinstance(val, list) and val:
            parts.append(f"{key.replace('_', ' ').title()}: {', '.join(str(v) for v in val[:20])}")
        elif val:
            parts.append(f"{key.replace('_', ' ').title()}: {val}")

    if not parts:
        return ""
    return "Extracted JD:\n" + "\n".join(parts)


def _parse_llm_response(content: str) -> Dict[str, Any]:
    """Parse LLM JSON response with fallback handling."""
    # Strip markdown fences if present
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (fences)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse LLM classification response: {content[:200]}")
        return {"is_ai_job": False, "categories": [], "rationale": "Parse error"}

    return data


def classify_job_llm(
    title: str,
    company: str,
    description: str,
    extracted_jd: Optional[Dict[str, Any]] = None,
) -> AIClassificationLLM:
    """
    Classify a job using Haiku LLM for semantic AI relevance.

    Args:
        title: Job title
        company: Company name
        description: Full job description text
        extracted_jd: Structured JD data (skills, responsibilities, etc.)

    Returns:
        AIClassificationLLM with is_ai_job, categories, rationale
    """
    lantern_context = _load_ai_project_context()
    extracted_jd_section = _build_extracted_jd_section(extracted_jd)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=title or "Unknown",
        company=company or "Unknown",
        description=description or "No description available",
        extracted_jd_section=extracted_jd_section,
        lantern_context=lantern_context,
    )

    try:
        result = invoke_unified_sync(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            step_name="ai_classification",
            validate_json=True,
        )

        if not result.success:
            logger.error(f"AI classification LLM failed: {result.error}")
            return AIClassificationLLM(
                is_ai_job=False, ai_categories=[], ai_category_count=0,
                ai_rationale=f"LLM error: {result.error}",
            )

        data = _parse_llm_response(result.content)

        is_ai_job = bool(data.get("is_ai_job", False))
        raw_categories = data.get("categories", [])
        # Filter to valid categories only
        categories = [c for c in raw_categories if c in VALID_CATEGORIES]
        rationale = data.get("rationale", "")

        return AIClassificationLLM(
            is_ai_job=is_ai_job,
            ai_categories=categories,
            ai_category_count=len(categories),
            ai_rationale=rationale,
            ai_classified_at=datetime.utcnow(),
        )

    except Exception as e:
        logger.error(f"AI classification failed: {e}")
        return AIClassificationLLM(
            is_ai_job=False, ai_categories=[], ai_category_count=0,
            ai_rationale=f"Classification error: {str(e)}",
        )


def classify_job_document_llm(doc: Dict[str, Any]) -> AIClassificationLLM:
    """
    Classify a MongoDB document using LLM. Convenience wrapper.

    Args:
        doc: MongoDB job document with title, company, description/job_description, extracted_jd

    Returns:
        AIClassificationLLM result
    """
    return classify_job_llm(
        title=doc.get("title", ""),
        company=doc.get("company", ""),
        description=doc.get("job_description") or doc.get("description", ""),
        extracted_jd=doc.get("extracted_jd"),
    )
