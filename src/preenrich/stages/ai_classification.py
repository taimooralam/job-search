"""
ai_classification stage — thin adapter over src/services/ai_classifier_llm.

Provider routing (Phase 2b):
    "codex" (default) — gpt-5.4-mini primary with claude-haiku-4-5 fallback
    "claude"           — direct classify_job_document_llm path

Dependencies: ["jd_extraction"]
Output patch: {"is_ai_job": bool, "ai_categories": list, "ai_category_count": int,
               "ai_rationale": str|None, "ai_classified_at": str|None,
               "ai_classification": {...}}
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.preenrich.stages.base import StageBase, _call_llm_with_fallback
from src.preenrich.types import StageContext, StageResult
from src.services.ai_classifier_llm import classify_job_document_llm

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

_CODEX_SYSTEM = (
    "You are a technical recruiter specialised in AI/ML roles. "
    "Return ONLY valid JSON with no prose, no markdown fences."
)

_CODEX_PROMPT_TEMPLATE = """{system}

Classify whether this job is relevant to an AI/LLM infrastructure engineer.

Job Title: {title}
Company: {company}

Description:
{description}

{extracted_jd_section}

Return ONLY valid JSON:
{{
  "is_ai_job": true,
  "categories": ["ai_general", "genai_llm"],
  "rationale": "1-2 sentence explanation"
}}

Valid categories: ai_general, genai_llm, agentic_ai, rag_retrieval, mlops_llmops, fine_tuning, ai_governance, prompt_engineering, data_science

Rules:
- AUTOMATIC is_ai_job=true if title contains: AI, Gen AI, GenAI, LLM, Machine Learning, ML
- Choose 0-3 most relevant categories
- If not an AI job, return empty categories
"""


def _build_ai_class_codex_prompt(
    title: str,
    company: str,
    description: str,
    extracted_jd: Optional[Dict[str, Any]],
) -> str:
    extracted_section = ""
    if extracted_jd:
        parts = []
        for key in ("technical_skills", "top_keywords", "responsibilities", "qualifications"):
            val = extracted_jd.get(key)
            if isinstance(val, list) and val:
                parts.append(f"{key.replace('_', ' ').title()}: {', '.join(str(v) for v in val[:15])}")
        if parts:
            extracted_section = "Extracted JD:\n" + "\n".join(parts)

    return _CODEX_PROMPT_TEMPLATE.format(
        system=_CODEX_SYSTEM,
        title=title,
        company=company,
        description=description[:6000],
        extracted_jd_section=extracted_section,
    )


def _parse_codex_classification(
    output_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalise the Codex output dict into the expected patch shape."""
    is_ai = bool(output_dict.get("is_ai_job", False))
    categories = output_dict.get("categories", []) or []
    rationale = output_dict.get("rationale") or None

    return {
        "is_ai_job": is_ai,
        "ai_categories": categories,
        "ai_category_count": len(categories),
        "ai_rationale": rationale,
        "ai_classified_at": None,
    }


class AIClassificationStage:
    """
    Thin adapter over src/services/ai_classifier_llm.classify_job_document_llm.

    Phase 2b: Codex gpt-5.4-mini is the default primary provider. Claude Haiku
    is the automatic fallback on Codex failure or schema validation failure.
    Controlled by StageContext.config (populated by get_stage_step_config()).
    """

    name: str = "ai_classification"
    dependencies: List[str] = ["jd_extraction"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Classify job document for AI/ML relevance.

        Args:
            ctx: Stage context. config.provider determines routing:
                 "codex" (default) — Codex primary with Claude fallback
                 "claude"          — Direct classify_job_document_llm path

        Returns:
            StageResult with output patch matching existing field shape from
            full_extraction_service._persist_results().

        Raises:
            ValueError: If unsupported provider or classification fails on both providers.
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            return self._run_codex_primary(ctx)
        elif provider == "claude":
            return self._run_claude(ctx)
        else:
            raise ValueError(
                f"Unsupported provider '{provider}' for ai_classification. "
                "Valid values: 'claude', 'codex'."
            )

    def _run_codex_primary(self, ctx: StageContext) -> StageResult:
        """Run classification with Codex as primary + Claude as automatic fallback."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        title = job_doc.get("title", "")
        company = job_doc.get("company", "")
        description = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or ""
        )
        extracted_jd = job_doc.get("extracted_jd")

        primary_model = (
            ctx.config.primary_model
            if ctx.config and ctx.config.primary_model
            else "gpt-5.4-mini"
        )
        fallback_model = (
            ctx.config.fallback_model
            if ctx.config and ctx.config.fallback_model
            else "claude-haiku-4-5"
        )

        prompt = _build_ai_class_codex_prompt(title, company, description, extracted_jd)

        def _invoker(*, prompt: str, model: str, job_id: str) -> Dict[str, Any]:
            enriched_doc = dict(job_doc)
            ai_result = classify_job_document_llm(enriched_doc)
            return {
                "is_ai_job": ai_result.is_ai_job,
                "categories": ai_result.ai_categories,
                "rationale": getattr(ai_result, "ai_rationale", None),
            }

        t0 = time.monotonic()
        output_dict, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model=primary_model,
            fallback_provider="claude",
            fallback_model=fallback_model,
            prompt=prompt,
            job_id=job_id,
            schema=None,
            claude_invoker=_invoker,
            tracer=ctx.tracer,
            stage_name=ctx.stage_name or self.name,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Normalise output to patch shape
        patch = _parse_codex_classification(output_dict)

        success_attempt = next(
            (a for a in reversed(attempts) if a["outcome"] == "success"), None
        )
        provider_used = success_attempt["provider"] if success_attempt else "codex"
        model_used = success_attempt["model"] if success_attempt else primary_model
        fallback_reason: Optional[str] = None
        if len(attempts) > 1:
            fallback_reason = attempts[0]["outcome"]

        # Add consolidated sub-doc
        patch["ai_classification"] = {
            "is_ai_job": patch["is_ai_job"],
            "ai_categories": patch["ai_categories"],
            "ai_category_count": patch["ai_category_count"],
            "ai_rationale": patch["ai_rationale"],
            "ai_classified_at": patch["ai_classified_at"],
        }

        logger.debug(
            "ai_classification: job %s classified via %s/%s "
            "(is_ai_job=%s, categories=%s, duration=%dms, fallback=%s)",
            job_id, provider_used, model_used,
            patch["is_ai_job"], patch["ai_categories"], duration_ms, fallback_reason,
        )

        return StageResult(
            output=patch,
            provider_used=provider_used,
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
            provider_attempts=attempts,
            provider_fallback_reason=fallback_reason,
        )

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run AI classification via classify_job_document_llm (Claude path)."""
        job_doc = ctx.job_doc

        enriched_doc = dict(job_doc)
        extracted_jd = job_doc.get("extracted_jd")
        if extracted_jd:
            enriched_doc["extracted_jd"] = extracted_jd

        t0 = time.monotonic()
        try:
            ai_result = classify_job_document_llm(enriched_doc)
        except Exception as exc:
            raise ValueError(
                f"AI classification failed for job {job_doc.get('_id', 'unknown')}: {exc}"
            ) from exc
        duration_ms = int((time.monotonic() - t0) * 1000)

        patch = {
            "is_ai_job": ai_result.is_ai_job,
            "ai_categories": ai_result.ai_categories,
            "ai_category_count": ai_result.ai_category_count,
            "ai_rationale": getattr(ai_result, "ai_rationale", None),
            "ai_classified_at": getattr(ai_result, "ai_classified_at", None),
            "ai_classification": {
                "is_ai_job": ai_result.is_ai_job,
                "ai_categories": ai_result.ai_categories,
                "ai_category_count": ai_result.ai_category_count,
                "ai_rationale": getattr(ai_result, "ai_rationale", None),
                "ai_classified_at": getattr(ai_result, "ai_classified_at", None),
            },
        }

        logger.debug(
            "ai_classification: job %s classified via claude "
            "(is_ai_job=%s, categories=%s, duration=%dms)",
            job_doc.get("_id", "unknown"),
            ai_result.is_ai_job,
            ai_result.ai_categories,
            duration_ms,
        )

        return StageResult(
            output=patch,
            provider_used="claude",
            model_used=None,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(AIClassificationStage(), StageBase), (
    "AIClassificationStage does not satisfy StageBase protocol"
)
