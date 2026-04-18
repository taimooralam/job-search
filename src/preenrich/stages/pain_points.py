"""
pain_points stage — thin adapter over src/layer2/pain_point_miner.PainPointMiner.

Provider routing (Phase 2b):
    "codex" (default) — gpt-5.4 primary with claude-sonnet-4-5 fallback
    "claude"           — direct PainPointMiner path

Dependencies: ["jd_extraction"]
Output patch: {"pain_points": list, "strategic_needs": list,
               "risks_if_unfilled": list, "success_metrics": list}

The patch field names match those written by full_extraction_service._persist_results()
so existing consumers (cv_generation_service, company_research_service, etc.) are
unchanged.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.common.state import JobState
from src.layer2.pain_point_miner import PainPointMiner
from src.preenrich.stages.base import StageBase, _call_llm_with_fallback
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

_CODEX_SYSTEM = (
    "You are a strategic HR analyst. "
    "Return ONLY valid JSON with no prose, no markdown fences."
)

_CODEX_PROMPT_TEMPLATE = """{system}

Analyse the job description below and extract pain points, strategic needs, risks, and success metrics.

Job Title: {title}
Company: {company}

Job Description:
{description}

Return ONLY valid JSON matching this schema:
{{
  "pain_points": ["string describing a specific organisational pain", ...],
  "strategic_needs": ["string describing what the company strategically needs", ...],
  "risks_if_unfilled": ["string describing business risk if role stays unfilled", ...],
  "success_metrics": ["string describing how success is measured in this role", ...]
}}

Rules:
- pain_points: 3-6 specific pains implied by the JD (not generic "we need great talent")
- strategic_needs: 2-4 strategic requirements (technology, process, people)
- risks_if_unfilled: 2-4 business risks if the role is not filled
- success_metrics: 2-4 measurable outcomes for the role
"""


def _build_pain_points_codex_prompt(
    title: str,
    company: str,
    description: str,
) -> str:
    return _CODEX_PROMPT_TEMPLATE.format(
        system=_CODEX_SYSTEM,
        title=title,
        company=company,
        description=description[:8000],
    )


def _parse_codex_pain_points(output_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise Codex output into the expected patch shape."""
    return {
        "pain_points": output_dict.get("pain_points", []),
        "strategic_needs": output_dict.get("strategic_needs", []),
        "risks_if_unfilled": output_dict.get("risks_if_unfilled", []),
        "success_metrics": output_dict.get("success_metrics", []),
    }


class PainPointsStage:
    """
    Thin adapter over layer2.pain_point_miner.PainPointMiner.

    Phase 2b: Codex gpt-5.4 is the default primary provider. Claude Sonnet
    is the automatic fallback on Codex failure or schema validation failure.
    Controlled by StageContext.config (populated by get_stage_step_config()).
    """

    name: str = "pain_points"
    dependencies: List[str] = ["jd_extraction"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Extract pain points, strategic needs, risks and success metrics.

        Args:
            ctx: Stage context. config.provider determines routing:
                 "codex" (default) — Codex primary with Claude fallback
                 "claude"          — Direct PainPointMiner path

        Returns:
            StageResult with output patch matching existing field shape.

        Raises:
            ValueError: If unsupported provider or extraction fails on both providers.
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            return self._run_codex_primary(ctx)
        elif provider == "claude":
            return self._run_claude(ctx)
        else:
            raise ValueError(
                f"Unsupported provider '{provider}' for pain_points. "
                "Valid values: 'claude', 'codex'."
            )

    def _run_codex_primary(self, ctx: StageContext) -> StageResult:
        """Run pain point extraction with Codex as primary + Claude as fallback."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        title = job_doc.get("title", "")
        company = job_doc.get("firm") or job_doc.get("company", "")
        jd_text: str = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or job_doc.get("jd_text")
            or ""
        )

        if not jd_text.strip():
            raise ValueError(f"No JD text available for pain_points on job {job_id}")

        primary_model = (
            ctx.config.primary_model
            if ctx.config and ctx.config.primary_model
            else "gpt-5.4"
        )
        fallback_model = (
            ctx.config.fallback_model
            if ctx.config and ctx.config.fallback_model
            else "claude-sonnet-4-5"
        )

        prompt = _build_pain_points_codex_prompt(title, company, jd_text)

        def _invoker(*, prompt: str, model: str, job_id: str) -> Dict[str, Any]:
            return _claude_run_pain_points(job_doc, job_id, title, company, jd_text)

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
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        patch = _parse_codex_pain_points(output_dict)

        success_attempt = next(
            (a for a in reversed(attempts) if a["outcome"] == "success"), None
        )
        provider_used = success_attempt["provider"] if success_attempt else "codex"
        model_used = success_attempt["model"] if success_attempt else primary_model
        fallback_reason: Optional[str] = None
        if len(attempts) > 1:
            fallback_reason = attempts[0]["outcome"]

        logger.debug(
            "pain_points: job %s extracted %d pain points via %s/%s "
            "(duration=%dms, fallback=%s)",
            job_id, len(patch["pain_points"]),
            provider_used, model_used, duration_ms, fallback_reason,
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
        """Run pain point mining via PainPointMiner (Claude path)."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        title = job_doc.get("title", "")
        company = job_doc.get("firm") or job_doc.get("company", "")
        jd_text: str = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or job_doc.get("jd_text")
            or ""
        )

        if not jd_text.strip():
            raise ValueError(f"No JD text available for pain_points on job {job_id}")

        t0 = time.monotonic()
        try:
            result = _claude_run_pain_points(job_doc, job_id, title, company, jd_text)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(
                f"PainPointMiner failed for job {job_id}: {exc}"
            ) from exc
        duration_ms = int((time.monotonic() - t0) * 1000)

        patch = {
            "pain_points": result.get("pain_points", []),
            "strategic_needs": result.get("strategic_needs", []),
            "risks_if_unfilled": result.get("risks_if_unfilled", []),
            "success_metrics": result.get("success_metrics", []),
        }

        logger.debug(
            "pain_points: job %s extracted %d pain points via claude (duration=%dms)",
            job_id, len(patch["pain_points"]), duration_ms,
        )

        return StageResult(
            output=patch,
            provider_used="claude",
            model_used=None,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


def _claude_run_pain_points(
    job_doc: Dict[str, Any],
    job_id: str,
    title: str,
    company: str,
    jd_text: str,
) -> Dict[str, Any]:
    """Invoke PainPointMiner and return raw result dict."""
    state: JobState = {
        "job_id": job_id,
        "title": title,
        "company": company,
        "job_description": jd_text,
    }

    miner = PainPointMiner(use_enhanced_format=False)
    try:
        return miner.extract_pain_points(state)
    except Exception as exc:
        raise ValueError(f"PainPointMiner failed for job {job_id}: {exc}") from exc


# Verify protocol compliance at import time
assert isinstance(PainPointsStage(), StageBase), (
    "PainPointsStage does not satisfy StageBase protocol"
)
