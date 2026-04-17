"""
ai_classification stage — thin adapter over src/services/ai_classifier_llm.

Default provider: Claude Haiku (per plan §4).
Codex path raises NotImplementedError (Phase 6).

Dependencies: ["jd_extraction"]
Output patch: {"is_ai_job": bool, "ai_categories": list, "ai_category_count": int,
               "ai_rationale": str|None, "ai_classified_at": str|None,
               "ai_classification": {...}}
"""

import logging
import time
from typing import List

from src.preenrich.stages.base import StageBase
from src.preenrich.types import StageContext, StageResult
from src.services.ai_classifier_llm import classify_job_document_llm

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"


class AIClassificationStage:
    """
    Thin adapter over src/services/ai_classifier_llm.classify_job_document_llm.

    Claude Haiku is the default and only supported provider in Phase 2.
    Codex support is deferred to Phase 6 and raises NotImplementedError now.
    """

    name: str = "ai_classification"
    dependencies: List[str] = ["jd_extraction"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Classify job document for AI/ML relevance.

        Args:
            ctx: Stage context. config.provider must be "claude" or "codex".

        Returns:
            StageResult with output patch matching existing field shape from
            full_extraction_service._persist_results().

        Raises:
            NotImplementedError: If config.provider == "codex"
            ValueError: If unsupported provider
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            raise NotImplementedError(
                "codex provider pending Phase 6 cutover — use provider='claude'"
            )

        if provider != "claude":
            raise ValueError(
                f"Unsupported provider '{provider}' for ai_classification. "
                "Valid values: 'claude', 'codex' (pending)."
            )

        return self._run_claude(ctx)

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run AI classification via classify_job_document_llm."""
        job_doc = ctx.job_doc

        # Build enriched doc with extracted_jd if present (matches full_extraction_service pattern)
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

        # Build patch matching existing field shape written by full_extraction_service
        patch = {
            "is_ai_job": ai_result.is_ai_job,
            "ai_categories": ai_result.ai_categories,
            "ai_category_count": ai_result.ai_category_count,
            "ai_rationale": getattr(ai_result, "ai_rationale", None),
            "ai_classified_at": getattr(ai_result, "ai_classified_at", None),
            # Consolidated sub-doc for preenrich consumers
            "ai_classification": {
                "is_ai_job": ai_result.is_ai_job,
                "ai_categories": ai_result.ai_categories,
                "ai_category_count": ai_result.ai_category_count,
                "ai_rationale": getattr(ai_result, "ai_rationale", None),
                "ai_classified_at": getattr(ai_result, "ai_classified_at", None),
            },
        }

        logger.debug(
            "ai_classification: job %s classified (is_ai_job=%s, categories=%s, duration=%dms)",
            job_doc.get("_id", "unknown"),
            ai_result.is_ai_job,
            ai_result.ai_categories,
            duration_ms,
        )

        return StageResult(
            output=patch,
            provider_used="claude",
            model_used=None,  # classify_job_document_llm doesn't expose model used
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(AIClassificationStage(), StageBase), (
    "AIClassificationStage does not satisfy StageBase protocol"
)
