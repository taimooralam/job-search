"""
persona stage — adapter over src/common/persona_builder.PersonaBuilder.

Provider routing (Phase 2b):
    "codex" (default) — gpt-5.4 primary with claude-sonnet-4-5 fallback
    "claude"           — PersonaBuilder (Sonnet, downgraded from Opus per plan §4)

Default tier for Claude path: "balanced" (Sonnet) — main cost win vs Opus.
The model is configurable via StepConfig so the downgrade is reversible.

Dependencies: ["annotations"]
Output patch: {"jd_annotations": {... "synthesized_persona": {...}}}
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.preenrich.stages.base import StageBase, _call_llm_with_fallback
from src.preenrich.types import StageContext, StageResult
from src.common.persona_builder import PersonaBuilder, SynthesizedPersona

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"

# Default tier for persona synthesis — downgraded from Opus (quality) to Sonnet (balanced)
DEFAULT_TIER = "balanced"

_CODEX_SYSTEM = (
    "You are a talent acquisition specialist. "
    "Return ONLY valid JSON with no prose, no markdown fences."
)

_CODEX_PROMPT_TEMPLATE = """{system}

Synthesise a candidate persona from the job annotations below.

Job ID: {job_id}
Ideal Candidate Profile: {icp}

Annotations:
{annotations_text}

Return ONLY valid JSON matching this schema:
{{
  "persona_statement": "2-3 sentence description of the ideal candidate persona",
  "primary_identity": "single phrase (e.g. 'AI platform builder')",
  "secondary_identities": ["string", "string"],
  "source_annotations": ["annotation_id_1", "annotation_id_2"]
}}

Rules:
- persona_statement: grounded in the annotations, speaks to the role's core needs
- primary_identity: concise and memorable, max 8 words
- secondary_identities: 1-3 secondary facets of the candidate's identity
- source_annotations: IDs of annotations that drove the synthesis
"""


def _build_persona_codex_prompt(
    job_id: str,
    jd_annotations: Dict[str, Any],
    icp: Optional[Any],
) -> str:
    annotations = jd_annotations.get("annotations", [])
    ann_lines = []
    for ann in annotations[:20]:  # truncate
        ann_id = ann.get("id", "?")
        text = ""
        target = ann.get("target", {})
        if isinstance(target, dict):
            text = target.get("text", "")
        elif isinstance(target, str):
            text = target
        relevance = ann.get("relevance", "")
        identity = ann.get("identity", "")
        passion = ann.get("passion", "")
        ann_lines.append(
            f"- [{ann_id}] {text!r} | relevance={relevance} identity={identity} passion={passion}"
        )

    annotations_text = "\n".join(ann_lines) if ann_lines else "(none)"
    icp_str = str(icp) if icp else "Not provided"

    return _CODEX_PROMPT_TEMPLATE.format(
        system=_CODEX_SYSTEM,
        job_id=job_id,
        icp=icp_str[:500],
        annotations_text=annotations_text,
    )


def _parse_codex_persona(output_dict: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    """Normalise Codex persona output into SynthesizedPersona.to_dict() shape."""
    from datetime import datetime
    return {
        "persona_statement": output_dict.get("persona_statement", ""),
        "primary_identity": output_dict.get("primary_identity", ""),
        "secondary_identities": output_dict.get("secondary_identities", []),
        "source_annotations": output_dict.get("source_annotations", []),
        "synthesized_at": datetime.utcnow().isoformat(),
    }


class PersonaStage:
    """
    Adapter over common.persona_builder.PersonaBuilder.

    Phase 2b: Codex gpt-5.4 is the default primary provider. Claude Sonnet
    is the automatic fallback on Codex failure or schema validation failure.

    The synthesized persona is embedded back into jd_annotations.synthesized_persona,
    matching the field shape written by full_extraction_service._persist_persona().
    """

    name: str = "persona"
    dependencies: List[str] = ["annotations"]

    def run(self, ctx: StageContext) -> StageResult:
        """
        Synthesize persona from identity/passion/strength annotations.

        Args:
            ctx: Stage context. config.provider determines routing:
                 "codex" (default) — Codex primary with Claude fallback
                 "claude"          — PersonaBuilder path (balanced tier)

        Returns:
            StageResult with output patch {"jd_annotations": {...}} where
            jd_annotations.synthesized_persona is the SynthesizedPersona dict.
            If no persona-relevant annotations exist, returns a skipped result.

        Raises:
            ValueError: If unsupported provider or synthesis fails on both providers.
        """
        provider = ctx.config.provider if ctx.config else "claude"

        if provider == "codex":
            return self._run_codex_primary(ctx)
        elif provider == "claude":
            return self._run_claude(ctx)
        else:
            raise ValueError(
                f"Unsupported provider '{provider}' for persona. "
                "Valid values: 'claude', 'codex'."
            )

    def _run_codex_primary(self, ctx: StageContext) -> StageResult:
        """Run persona synthesis with Codex as primary + Claude as fallback."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))
        jd_annotations = job_doc.get("jd_annotations", {}) or {}

        # Check for persona-relevant annotations (same gate as Claude path)
        builder = PersonaBuilder()
        if not builder.has_persona_annotations(jd_annotations):
            logger.info(
                "persona: no persona-relevant annotations for job %s — skipping synthesis",
                job_id,
            )
            return StageResult(
                output={},
                provider_used="codex",
                model_used=ctx.config.primary_model if ctx.config else "gpt-5.4",
                prompt_version=PROMPT_VERSION,
                skip_reason="no_persona_annotations",
            )

        extracted_jd = job_doc.get("extracted_jd") or {}
        icp = extracted_jd.get("ideal_candidate_profile") if extracted_jd else None

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

        prompt = _build_persona_codex_prompt(job_id, jd_annotations, icp)

        def _invoker(*, prompt: str, model: str, job_id: str) -> Dict[str, Any]:
            return _claude_synthesize_persona(jd_annotations, job_id, icp, tier=DEFAULT_TIER)

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

        persona_dict = _parse_codex_persona(output_dict, job_id)

        success_attempt = next(
            (a for a in reversed(attempts) if a["outcome"] == "success"), None
        )
        provider_used = success_attempt["provider"] if success_attempt else "codex"
        model_used = success_attempt["model"] if success_attempt else primary_model
        fallback_reason: Optional[str] = None
        if len(attempts) > 1:
            fallback_reason = attempts[0]["outcome"]

        updated_jd_annotations = dict(jd_annotations)
        updated_jd_annotations["synthesized_persona"] = persona_dict

        logger.debug(
            "persona: synthesised for job %s via %s/%s (duration=%dms, fallback=%s): %s...",
            job_id, provider_used, model_used, duration_ms, fallback_reason,
            persona_dict.get("persona_statement", "")[:60],
        )

        return StageResult(
            output={"jd_annotations": updated_jd_annotations},
            provider_used=provider_used,
            model_used=model_used,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
            provider_attempts=attempts,
            provider_fallback_reason=fallback_reason,
        )

    def _run_claude(self, ctx: StageContext) -> StageResult:
        """Run persona synthesis via PersonaBuilder (Claude path)."""
        job_doc = ctx.job_doc
        job_id = str(job_doc.get("_id", "unknown"))

        # Use configured tier (model field carries the tier name for ClaudeCLI)
        tier = DEFAULT_TIER
        if ctx.config and ctx.config.model:
            tier = ctx.config.model

        jd_annotations = job_doc.get("jd_annotations", {})

        builder = PersonaBuilder()

        # Check if there are annotations to build a persona from
        if not builder.has_persona_annotations(jd_annotations):
            logger.info(
                "persona: no persona-relevant annotations for job %s — skipping synthesis",
                job_id,
            )
            return StageResult(
                output={},
                provider_used="claude",
                model_used=tier,
                prompt_version=PROMPT_VERSION,
                skip_reason="no_persona_annotations",
            )

        extracted_jd = job_doc.get("extracted_jd") or {}
        icp = extracted_jd.get("ideal_candidate_profile") if extracted_jd else None

        t0 = time.monotonic()
        try:
            persona_dict = _claude_synthesize_persona(jd_annotations, job_id, icp, tier=tier)
        except Exception as exc:
            raise ValueError(f"PersonaBuilder failed for job {job_id}: {exc}") from exc
        duration_ms = int((time.monotonic() - t0) * 1000)

        if not persona_dict:
            return StageResult(
                output={},
                provider_used="claude",
                model_used=tier,
                prompt_version=PROMPT_VERSION,
                skip_reason="synthesis_returned_none",
                duration_ms=duration_ms,
            )

        updated_jd_annotations = dict(jd_annotations)
        updated_jd_annotations["synthesized_persona"] = persona_dict

        logger.debug(
            "persona: synthesised for job %s via claude (tier=%s, duration=%dms): %s...",
            job_id, tier, duration_ms,
            persona_dict.get("persona_statement", "")[:60],
        )

        return StageResult(
            output={"jd_annotations": updated_jd_annotations},
            provider_used="claude",
            model_used=tier,
            prompt_version=PROMPT_VERSION,
            duration_ms=duration_ms,
        )


def _claude_synthesize_persona(
    jd_annotations: Dict[str, Any],
    job_id: str,
    icp: Optional[Any],
    tier: str = DEFAULT_TIER,
) -> Optional[Dict[str, Any]]:
    """
    Invoke PersonaBuilder.synthesize() and return persona as dict.

    Handles async/sync event loop conflict by running in a ThreadPoolExecutor
    when an event loop is already running.

    Returns None if synthesis returns no persona.
    """
    builder = PersonaBuilder()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    builder.synthesize(jd_annotations, job_id, ideal_candidate_profile=icp),
                )
                persona = future.result()
        else:
            persona = loop.run_until_complete(
                builder.synthesize(jd_annotations, job_id, ideal_candidate_profile=icp)
            )
    except RuntimeError:
        persona = asyncio.run(
            builder.synthesize(jd_annotations, job_id, ideal_candidate_profile=icp)
        )

    if persona is None:
        return None

    return persona.to_dict()


# Verify protocol compliance at import time
assert isinstance(PersonaStage(), StageBase), (
    "PersonaStage does not satisfy StageBase protocol"
)
