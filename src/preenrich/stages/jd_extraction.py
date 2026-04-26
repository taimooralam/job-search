"""
jd_extraction stage — thin adapter over src/layer1_4/claude_jd_extractor.JDExtractor.

Provider routing (Phase 2b):
    "codex" (default) — uses _call_llm_with_fallback with gpt-5.4 primary + claude-haiku-4-5 fallback
    "claude"           — direct JDExtractor (Claude CLI) path, kept for manual override / testing

Defaults are read from StageContext.config, which is populated by get_stage_step_config().
Per-stage env overrides: PREENRICH_PROVIDER_JD_EXTRACTION, PREENRICH_MODEL_JD_EXTRACTION,
PREENRICH_FALLBACK_MODEL_JD_EXTRACTION.

Validates the extraction output with Pydantic before emitting the patch.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from src.preenrich.stages.base import StageBase, _call_llm_with_fallback
from src.preenrich.types import StageContext, StageResult

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

_CODEX_SYSTEM = (
    "You are a structured data extractor. "
    "Return ONLY valid JSON with no prose, no markdown fences, no explanations. "
    "Match the schema exactly."
)

_CODEX_PROMPT_TEMPLATE = """{system}

Extract structured information from the job description below.

Job Title: {title}
Company: {company}

Job Description:
{description}

Return ONLY valid JSON matching this schema:
{{
  "title": "string",
  "required_skills": ["string", ...],
  "responsibilities": ["string", ...],
  "qualifications": ["string", ...],
  "company_name": "string",
  "employment_type": "full_time|part_time|contract|freelance",
  "location": "string",
  "seniority_level": "senior|staff|principal|director|vp|c_level",
  "industry": "string",
  "salary_range": "string or null",
  "remote_policy": "fully_remote|hybrid|onsite|not_specified",
  "benefits": ["string", ...],
  "team_size": "string or null",
  "reporting_to": "string or null",
  "ideal_candidate_profile": {{
    "identity_statement": "string",
    "archetype": "technical_architect|people_leader|execution_driver|strategic_visionary|domain_expert|builder_founder|process_champion|hybrid_technical_leader",
    "key_traits": ["string", "string", "string"],
    "experience_profile": "string",
    "culture_signals": ["string", ...]
  }},
  "role_category": "engineering_manager|staff_principal_engineer|director_of_engineering|head_of_engineering|vp_engineering|cto|tech_lead|senior_engineer",
  "top_keywords": ["string", ...],
  "competency_weights": {{
    "delivery": 25,
    "process": 25,
    "architecture": 25,
    "leadership": 25
  }}
}}
"""


def _build_codex_prompt(title: str, company: str, description: str) -> str:
    """Build the Codex-idiomatic extraction prompt."""
    return _CODEX_PROMPT_TEMPLATE.format(
        system=_CODEX_SYSTEM,
        title=title,
        company=company,
        description=description[:8000],  # truncate for context window safety
    )


def _claude_invoker_for_jd(
    *,
    prompt: str,
    model: str,
    job_id: str,
    title: str,
    company: str,
    description: str,
) -> Dict[str, Any]:
    """
    Claude fallback for jd_extraction: uses JDExtractor (the existing production path).

    The prompt arg is ignored — JDExtractor builds its own prompt from title/company/description.
    model arg is ignored — JDExtractor uses its configured model/tier.
    """
    from src.common.state import ExtractedJD
    from src.layer1_4.claude_jd_extractor import JDExtractor

    extractor = JDExtractor()
    result = extractor.extract(
        job_id=job_id,
        title=title,
        company=company,
        job_description=description,
    )

    if not result.success or result.extracted_jd is None:
        raise ValueError(f"JDExtractor failed for job {job_id}: {result.error}")

    extracted_dict = result.extracted_jd
    if hasattr(extracted_dict, "model_dump"):
        extracted_dict = extracted_dict.model_dump()
    elif hasattr(extracted_dict, "dict"):
        extracted_dict = extracted_dict.dict()

    validated = ExtractedJD(**extracted_dict)
    if hasattr(validated, "model_dump"):
        return validated.model_dump()
    return validated.dict()


class JDExtractionStage:
    """
    Thin adapter over layer1_4.claude_jd_extractor.JDExtractor.

    Phase 2b: Codex (gpt-5.4) is the default primary provider. Claude (JDExtractor)
    is the automatic fallback on Codex failure or schema validation failure.
    Controlled by StageContext.config (populated by get_stage_step_config()).
    """

    name: str = "jd_extraction"
    dependencies: List[str] = ["jd_structure"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Extract structured JD fields from raw description text.

        Args:
            ctx: Stage context. config.provider determines routing:
                 "codex" (default) — Codex primary with Claude fallback
                 "claude"          — Direct Claude/JDExtractor path

        Returns:
            StageResult with output patch {"extracted_jd": <dict>},
            provider_used, model_used, provider_attempts, provider_fallback_reason.

        Raises:
            ValueError: If provider unsupported or extraction fails on both providers.
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            return self._run_codex_primary(ctx)
        elif provider == "claude":
            return self._run_claude(ctx)
        else:
            raise ValueError(
                f"Unsupported provider '{provider}' for jd_extraction. "
                "Valid values: 'claude', 'codex'."
            )

    def _run_codex_primary(self, ctx: StageContext) -> StageResult:
        """Run extraction with Codex as primary + Claude as automatic fallback."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        title = job_doc.get("title", "")
        company = job_doc.get("company", "")
        description = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or ""
        )

        primary_model = (
            ctx.config.primary_model
            if ctx.config and ctx.config.primary_model
            else "gpt-5.4"
        )
        fallback_model = (
            ctx.config.fallback_model
            if ctx.config and ctx.config.fallback_model
            else "claude-haiku-4-5"
        )

        prompt = _build_codex_prompt(title, company, description)

        def _invoker(*, prompt: str, model: str, job_id: str) -> Dict[str, Any]:
            return _claude_invoker_for_jd(
                prompt=prompt,
                model=model,
                job_id=job_id,
                title=title,
                company=company,
                description=description,
            )

        t0 = time.monotonic()
        output_dict, attempts = _call_llm_with_fallback(
            primary_provider="codex",
            primary_model=primary_model,
            fallback_provider="claude",
            fallback_model=fallback_model,
            prompt=prompt,
            job_id=job_id,
            schema=None,  # JDExtractor already validates; Codex output validated below
            claude_invoker=_invoker,
            tracer=ctx.tracer,
            stage_name=ctx.stage_name or self.name,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        # Determine which provider was actually used
        success_attempt = next(
            (a for a in reversed(attempts) if a["outcome"] == "success"), None
        )
        provider_used = success_attempt["provider"] if success_attempt else "codex"
        model_used = success_attempt["model"] if success_attempt else primary_model
        fallback_reason: Optional[str] = None
        if len(attempts) > 1:
            fallback_reason = attempts[0]["outcome"]

        # Validate output against ExtractedJD schema
        try:
            from src.common.state import ExtractedJD
            validated = ExtractedJD(**output_dict)
            if hasattr(validated, "model_dump"):
                output_data = validated.model_dump()
            else:
                output_data = validated.dict()
        except Exception:
            # If we got here from a successful extraction the dict may have
            # extra/missing optional fields — use as-is rather than fail.
            output_data = output_dict

        logger.debug(
            "jd_extraction: extracted for job %s via %s/%s (duration=%dms, fallback=%s)",
            job_id, provider_used, model_used, duration_ms, fallback_reason,
        )

        return StageResult(
            output={"extracted_jd": output_data},
            provider_used=provider_used,
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
            provider_attempts=attempts,
            provider_fallback_reason=fallback_reason,
        )

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run extraction directly via JDExtractor (Claude CLI / UnifiedLLM)."""
        from src.layer1_4.claude_jd_extractor import JDExtractor

        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        title = job_doc.get("title", "")
        company = job_doc.get("company", "")
        description = (
            job_doc.get("job_description")
            or job_doc.get("description")
            or ""
        )

        extractor = JDExtractor()

        t0 = time.monotonic()
        result = extractor.extract(
            job_id=job_id,
            title=title,
            company=company,
            job_description=description,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)

        if not result.success or result.extracted_jd is None:
            raise ValueError(
                f"JDExtractor failed for job {job_id}: {result.error}"
            )

        # Validate with Pydantic (ExtractedJD from state.py)
        from src.common.state import ExtractedJD

        extracted_dict = result.extracted_jd
        if hasattr(extracted_dict, "model_dump"):
            extracted_dict = extracted_dict.model_dump()
        elif hasattr(extracted_dict, "dict"):
            extracted_dict = extracted_dict.dict()

        # Pydantic validation — raises ValidationError on schema mismatch
        validated = ExtractedJD(**extracted_dict)
        if hasattr(validated, "model_dump"):
            output_data = validated.model_dump()
        else:
            output_data = validated.dict()

        logger.debug(
            "jd_extraction: extracted for job %s via claude (duration=%dms)",
            job_id, duration_ms,
        )

        return StageResult(
            output={"extracted_jd": output_data},
            provider_used="claude",
            model_used=getattr(result, "model", None),
            prompt_version=PROMPT_VERSION,
            tokens_input=result.input_tokens if hasattr(result, "input_tokens") else None,
            tokens_output=result.output_tokens if hasattr(result, "output_tokens") else None,
            cost_usd=result.cost_usd if hasattr(result, "cost_usd") else None,
            duration_ms=duration_ms,
        )


# Verify protocol compliance at import time
assert isinstance(JDExtractionStage(), StageBase), (
    "JDExtractionStage does not satisfy StageBase protocol"
)
