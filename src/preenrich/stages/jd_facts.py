"""Iteration-4.1 jd_facts stage with runner-parity extraction V2 behind flags."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from src.common.codex_cli import CodexCLI
from src.layer1_4.claude_jd_extractor import JDExtractor
from src.preenrich.blueprint_config import (
    jd_facts_escalate_on_failure_enabled,
    jd_facts_escalation_model,
    jd_facts_v2_enabled,
    jd_facts_v2_live_compat_write_enabled,
)
from src.preenrich.blueprint_models import (
    JDFactsDoc,
    JDFactsExtractionOutput,
    JDJudgeAddition,
    JDJudgeFlag,
)
from src.preenrich.blueprint_prompts import build_p_jd_extract, build_p_jd_judge
from src.preenrich.stages.base import StageBase, _call_llm_with_fallback
from src.preenrich.stages.blueprint_common import (
    detect_remote_policy,
    evidence_from_quote,
    extract_bullets_for_headers,
    extract_keywords,
    extract_salary_range,
    extract_skill_signals,
)
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION_V1 = "P-jd-judge:v1"
PROMPT_VERSION_V2 = "P-jd-extract:v1"
EXTRACTOR_VERSION_V1 = "jd-facts.det.v1"
EXTRACTOR_VERSION_V2 = "jd-facts.det.v2"
_ANCHOR_FIELDS = ("title", "company", "location", "remote_policy", "salary_range", "application_url")
_REQUIRED_FIELDS_FOR_ESCALATION = (
    "role_category",
    "seniority_level",
    "competency_weights",
    "responsibilities",
    "qualifications",
    "top_keywords",
    "ideal_candidate_profile",
)


def _description(job_doc: dict[str, Any]) -> str:
    return str(job_doc.get("description") or job_doc.get("job_description") or "")


def _locator_for_match(text: str, pattern: str) -> str | None:
    if not pattern:
        return None
    match = re.search(pattern, text or "", re.IGNORECASE)
    if not match:
        return None
    return f"char:{match.start()}-{match.end()}"


def _deterministic_extract(job_doc: dict[str, Any]) -> dict[str, Any]:
    description = _description(job_doc)
    hard_skills, soft_skills = extract_skill_signals(description)
    location = job_doc.get("location") or "Not specified"
    return {
        "title": {"value": job_doc.get("title"), "locator": None},
        "company": {"value": job_doc.get("company"), "locator": None},
        "location": {
            "value": location,
            "locator": _locator_for_match(description, re.escape(str(job_doc.get("location") or ""))) if job_doc.get("location") else None,
        },
        "remote_policy": {
            "value": detect_remote_policy(description, job_doc.get("location")),
            "locator": _locator_for_match(description, r"(remote|hybrid|on-?site)"),
        },
        "salary_range": {
            "value": extract_salary_range(description),
            "locator": _locator_for_match(description, r"[$€£]\s?\d[\d,]*(?:\s?[-–]\s?[$€£]?\d[\d,]*)?"),
        },
        "must_haves": extract_bullets_for_headers(description, ("requirements", "must have", "qualifications")),
        "nice_to_haves": extract_bullets_for_headers(description, ("nice to have", "preferred", "bonus")),
        "technical_skills": hard_skills,
        "soft_skills": soft_skills,
        "top_keywords": extract_keywords(description),
        "weak_keyword_hints": extract_keywords(description, limit=10),
        "application_url": {
            "value": job_doc.get("application_url") or job_doc.get("jobUrl") or job_doc.get("job_url"),
            "locator": _locator_for_match(description, r"https?://\S+"),
        },
    }


def _normalize_section_name(section: dict[str, Any]) -> str:
    return " ".join(
        str(section.get(key) or "")
        for key in ("section_type", "header", "title", "label", "name")
    ).strip().lower()


def _extract_section_text(section: dict[str, Any]) -> str:
    content = section.get("content")
    if isinstance(content, list):
        return "\n".join(str(item) for item in content if item)
    if content:
        return str(content)
    for key in ("text", "body", "markdown", "html"):
        if section.get(key):
            return str(section[key])
    return ""


def _compact_raw_jd(text: str, *, limit: int = 8000) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    head = max(int(limit * 0.6), 2000)
    tail = max(limit - head - 64, 1200)
    return f"{cleaned[:head].rstrip()}\n\n[... middle truncated for extraction parity ...]\n\n{cleaned[-tail:].lstrip()}"


def _get_processed_sections(job_doc: dict[str, Any]) -> list[dict[str, Any]]:
    pre = (job_doc.get("pre_enrichment") or {}).get("outputs") or {}
    candidates = (
        pre.get("jd_structure", {}).get("processed_jd_sections"),
        job_doc.get("processed_jd_sections"),
        (job_doc.get("jd_annotations") or {}).get("processed_jd_sections"),
    )
    for value in candidates:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _package_structured_sections(job_doc: dict[str, Any]) -> dict[str, Any]:
    sections = _get_processed_sections(job_doc)
    packaged: dict[str, list[str] | bool] = {
        "responsibilities": [],
        "requirements": [],
        "preferred_qualifications": [],
        "about_company": [],
        "other_sections": [],
        "used_processed_jd_sections": bool(sections),
    }
    for section in sections:
        name = _normalize_section_name(section)
        text = _extract_section_text(section).strip()
        if not text:
            continue
        bucket = "other_sections"
        if any(token in name for token in ("respons", "what_you", "what_youll", "duties", "impact", "deliver")):
            bucket = "responsibilities"
        elif any(token in name for token in ("require", "qualif", "must", "minimum")):
            bucket = "requirements"
        elif any(token in name for token in ("preferred", "bonus", "nice")):
            bucket = "preferred_qualifications"
        elif any(token in name for token in ("about", "company", "who we are", "mission")):
            bucket = "about_company"
        casted = packaged[bucket]
        assert isinstance(casted, list)
        casted.append(text[:1500])
    return packaged


def _normalize_extraction_payload(raw_output: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw_output or {})
    if "company" not in payload and payload.get("company_name"):
        payload["company"] = payload.pop("company_name")
    if "qualifications" not in payload and payload.get("required_qualifications"):
        payload["qualifications"] = payload["required_qualifications"]
    if "responsibilities" not in payload and payload.get("key_responsibilities"):
        payload["responsibilities"] = payload["key_responsibilities"]
    for field in _ANCHOR_FIELDS:
        det_value = deterministic.get(field)
        if isinstance(det_value, dict):
            det_value = det_value.get("value")
        if payload.get(field) in (None, "", []):
            payload[field] = det_value
    if not payload.get("technical_skills"):
        payload["technical_skills"] = list(deterministic.get("technical_skills") or [])
    if not payload.get("soft_skills"):
        payload["soft_skills"] = list(deterministic.get("soft_skills") or [])
    if not payload.get("nice_to_haves"):
        payload["nice_to_haves"] = list(deterministic.get("nice_to_haves") or [])
    if not payload.get("top_keywords"):
        payload["top_keywords"] = list(deterministic.get("top_keywords") or [])
    if not payload.get("qualifications"):
        payload["qualifications"] = list(deterministic.get("must_haves") or [])
    return payload


def _needs_escalation(extraction: JDFactsExtractionOutput, title: str) -> bool:
    lowered = title.lower()
    role = extraction.role_category.value
    seniority = extraction.seniority_level.value
    if any(token in lowered for token in ("chief", "cto")) and role != "cto":
        return True
    if "vp" in lowered and role != "vp_engineering":
        return True
    if "director" in lowered and seniority not in {"director", "vp", "c_level"}:
        return True
    if any(token in lowered for token in ("staff", "principal")) and seniority not in {"staff", "principal"}:
        return True
    return False


def _conflict_flag(field: str, deterministic_value: Any, proposed_value: Any, locator: str | None = None) -> JDJudgeFlag:
    return JDJudgeFlag(
        field=field,
        deterministic_value=deterministic_value,
        proposed_value=proposed_value,
        severity="warn",
        reasoning="LLM proposed overwrite of deterministic anchor field",
        evidence_span=evidence_from_quote("job_description", str(proposed_value or ""), locator),
    )


def _finalize_extraction(extraction: JDFactsExtractionOutput, deterministic: dict[str, Any]) -> tuple[JDFactsExtractionOutput, list[JDJudgeFlag], dict[str, str]]:
    payload = extraction.model_dump()
    flags: list[JDJudgeFlag] = []
    provenance: dict[str, str] = {key: "llm_extract" for key in payload.keys()}

    for field in _ANCHOR_FIELDS:
        det_meta = deterministic.get(field)
        det_value = det_meta.get("value") if isinstance(det_meta, dict) else det_meta
        if det_value in (None, "", []):
            continue
        current = payload.get(field)
        should_override = field in {"title", "company", "application_url", "salary_range"}
        if field == "location":
            should_override = det_value not in (None, "", "Not specified")
        if field == "remote_policy":
            should_override = det_value != "not_specified"
        if should_override and current not in (None, "", det_value):
            flags.append(_conflict_flag(field, det_value, current, det_meta.get("locator") if isinstance(det_meta, dict) else None))
        if should_override:
            payload[field] = det_value
            provenance[field] = "deterministic"

    finalized = JDFactsExtractionOutput.model_validate(payload)
    for field, value in finalized.model_dump().items():
        provenance.setdefault(field, "llm_extract" if value not in (None, "", []) else "fallback_default")
    return finalized, flags, provenance


def _invoke_codex_json(*, prompt: str, model: str, job_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    t0 = time.monotonic()
    cli = CodexCLI(model=model)
    result = cli.invoke(prompt, job_id=job_id, validate_json=True)
    duration_ms = int((time.monotonic() - t0) * 1000)
    attempt = {
        "provider": "codex",
        "model": model,
        "outcome": "success" if result.success else "error_subprocess",
        "error": result.error,
        "duration_ms": duration_ms,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
    }
    return (result.result or None), attempt


def _invoke_runner_fallback(*, ctx: StageContext, deterministic: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    t0 = time.monotonic()
    extractor = JDExtractor()
    result = extractor.extract(
        job_id=str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "unknown"),
        title=str(ctx.job_doc.get("title") or ""),
        company=str(ctx.job_doc.get("company") or ""),
        job_description=_description(ctx.job_doc),
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    if not result.success or result.extracted_jd is None:
        raise RuntimeError(result.error or "runner fallback extraction failed")
    payload = dict(result.extracted_jd)
    payload["salary_range"] = (deterministic.get("salary_range") or {}).get("value")
    payload["application_url"] = (deterministic.get("application_url") or {}).get("value")
    return payload, {
        "provider": "claude",
        "model": result.model or (ctx.config.fallback_model if ctx.config else None),
        "outcome": "success",
        "error": None,
        "duration_ms": duration_ms,
        "input_tokens": None,
        "output_tokens": None,
    }


def _validate_llm_output(raw_output: dict[str, Any], deterministic: dict[str, Any]) -> JDFactsExtractionOutput:
    payload = _normalize_extraction_payload(raw_output, deterministic)
    return JDFactsExtractionOutput.model_validate(payload)


def _judge_additions(ctx: StageContext, deterministic: dict[str, Any]) -> tuple[list[JDJudgeAddition], list[JDJudgeFlag], dict[str, bool]]:
    provider = ctx.config.provider if ctx.config else "none"
    if provider == "none":
        return [], [], {}

    prompt = build_p_jd_judge(
        description=_description(ctx.job_doc),
        deterministic=deterministic,
    )
    output, _attempts = _call_llm_with_fallback(
        primary_provider="codex",
        primary_model=ctx.config.primary_model or "gpt-5.4-mini",
        fallback_provider=ctx.config.fallback_provider or "claude",
        fallback_model=ctx.config.fallback_model or "claude-haiku-4-5",
        prompt=prompt,
        job_id=str(ctx.job_doc.get("_id", "unknown")),
        schema=None,
        claude_invoker=lambda **_: {"additions": [], "flags": [], "confirmations": {}},
    )

    additions: list[JDJudgeAddition] = []
    flags: list[JDJudgeFlag] = []
    confirmations = dict(output.get("confirmations") or {})
    for item in output.get("additions", []) or []:
        field = str(item.get("field") or "")
        if not field or field in deterministic:
            if field in deterministic and item.get("value") != deterministic[field]:
                flags.append(
                    JDJudgeFlag(
                        field=field,
                        deterministic_value=deterministic[field],
                        proposed_value=item.get("value"),
                        severity="warn",
                        reasoning="LLM proposed overwrite of deterministic field",
                        evidence_span=evidence_from_quote("job_description", str(item.get("evidence_span", {}).get("quote") or "")),
                    )
                )
            continue
        evidence = item.get("evidence_span") or {}
        if not evidence.get("quote"):
            continue
        additions.append(
            JDJudgeAddition(
                field=field,
                value=item.get("value"),
                confidence=str(item.get("confidence") or "high"),
                evidence_span=evidence_from_quote("job_description", str(evidence.get("quote") or ""), str(evidence.get("locator") or "")),
            )
        )
    for item in output.get("flags", []) or []:
        flags.append(
            JDJudgeFlag(
                field=str(item.get("field") or ""),
                deterministic_value=item.get("deterministic_value"),
                proposed_value=item.get("proposed_value"),
                severity=str(item.get("severity") or "warn"),
                reasoning=str(item.get("reasoning") or "flagged by judge"),
                evidence_span=evidence_from_quote(
                    "job_description",
                    str((item.get("evidence_span") or {}).get("quote") or ""),
                    str((item.get("evidence_span") or {}).get("locator") or ""),
                ),
            )
        )
    return additions, flags, confirmations


class JDFactsStage:
    name: str = "jd_facts"
    dependencies: List[str] = ["jd_structure"]

    def _run_v1(self, ctx: StageContext) -> StageResult:
        deterministic = _deterministic_extract(ctx.job_doc)
        additions, flags, confirmations = _judge_additions(ctx, deterministic)

        merged_view: Dict[str, Any] = {}
        provenance: Dict[str, str] = {}
        for key, value in deterministic.items():
            merged_value = value.get("value") if isinstance(value, dict) and "value" in value else value
            merged_view[key] = merged_value
            provenance[key] = "deterministic"
        for addition in additions:
            if addition.field not in merged_view:
                merged_view[addition.field] = addition.value
                provenance[addition.field] = "llm_addition"

        extracted_jd = {
            "title": merged_view.get("title"),
            "company_name": merged_view.get("company"),
            "location": merged_view.get("location"),
            "remote_policy": merged_view.get("remote_policy"),
            "salary_range": merged_view.get("salary_range"),
            "qualifications": merged_view.get("must_haves", []),
            "nice_to_haves": merged_view.get("nice_to_haves", []),
            "technical_skills": merged_view.get("technical_skills", []),
            "soft_skills": merged_view.get("soft_skills", []),
            "top_keywords": merged_view.get("top_keywords", []),
        }

        artifact = JDFactsDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_text_hash=ctx.jd_checksum,
            extractor_version=EXTRACTOR_VERSION_V1,
            judge_prompt_version=PROMPT_VERSION_V1,
            deterministic=deterministic,
            llm_additions=additions,
            llm_flags=flags,
            confirmations=confirmations,
            merged_view=merged_view,
            provenance=provenance,
        )
        return StageResult(
            output={"extracted_jd": extracted_jd},
            stage_output=artifact.model_dump(),
            artifact_writes=[
                ArtifactWrite(
                    collection="jd_facts",
                    unique_filter={
                        "job_id": artifact.job_id,
                        "jd_text_hash": artifact.jd_text_hash,
                        "extractor_version": artifact.extractor_version,
                        "judge_prompt_version": artifact.judge_prompt_version,
                    },
                    document=artifact.model_dump(),
                    ref_name="jd_facts",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION_V1,
        )

    def _run_v2(self, ctx: StageContext) -> StageResult:
        deterministic = _deterministic_extract(ctx.job_doc)
        structured_sections = _package_structured_sections(ctx.job_doc)
        prompt = build_p_jd_extract(
            title=str(ctx.job_doc.get("title") or ""),
            company=str(ctx.job_doc.get("company") or ""),
            deterministic_hints=deterministic,
            structured_sections=structured_sections,
            raw_jd_excerpt=_compact_raw_jd(_description(ctx.job_doc)),
        )
        attempts: list[dict[str, Any]] = []
        extraction: JDFactsExtractionOutput | None = None
        provider_used = "none"
        model_used = None
        fallback_reason = None

        primary_model = ctx.config.primary_model or "gpt-5.4-mini"
        job_id = str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "unknown")

        raw_output, primary_attempt = _invoke_codex_json(prompt=prompt, model=primary_model, job_id=job_id)
        attempts.append(primary_attempt)

        try:
            if raw_output is None:
                raise RuntimeError(primary_attempt.get("error") or "primary codex call failed")
            extraction = _validate_llm_output(raw_output, deterministic)
            if _needs_escalation(extraction, str(ctx.job_doc.get("title") or "")) and jd_facts_escalate_on_failure_enabled():
                raise RuntimeError("extraction ambiguity requires escalation")
            provider_used = "codex"
            model_used = primary_model
        except Exception as primary_error:
            fallback_reason = primary_attempt.get("outcome") if primary_attempt.get("outcome") != "success" else "error_schema"
            if jd_facts_escalate_on_failure_enabled():
                escalation_model = jd_facts_escalation_model()
                escalated_output, escalated_attempt = _invoke_codex_json(prompt=prompt, model=escalation_model, job_id=job_id)
                attempts.append(escalated_attempt)
                try:
                    if escalated_output is None:
                        raise RuntimeError(escalated_attempt.get("error") or "escalation codex call failed")
                    extraction = _validate_llm_output(escalated_output, deterministic)
                    provider_used = "codex"
                    model_used = escalation_model
                except Exception:
                    runner_payload, runner_attempt = _invoke_runner_fallback(ctx=ctx, deterministic=deterministic)
                    attempts.append(runner_attempt)
                    extraction = _validate_llm_output(runner_payload, deterministic)
                    provider_used = "claude"
                    model_used = runner_attempt["model"]
            else:
                runner_payload, runner_attempt = _invoke_runner_fallback(ctx=ctx, deterministic=deterministic)
                attempts.append(runner_attempt)
                extraction = _validate_llm_output(runner_payload, deterministic)
                provider_used = "claude"
                model_used = runner_attempt["model"]
            if extraction is None:
                raise RuntimeError(f"jd_facts V2 extraction failed for job {job_id}: {primary_error}") from primary_error

        assert extraction is not None
        finalized, conflict_flags, provenance = _finalize_extraction(extraction, deterministic)
        compat_projection = finalized.to_compat_projection()
        merged_view = finalized.model_dump()
        llm_flags = conflict_flags + [
            JDJudgeFlag(
                field="extraction_mode",
                deterministic_value=primary_model,
                proposed_value=model_used,
                severity="info",
                reasoning="Escalated extraction model selected" if model_used and model_used != primary_model else "Primary extraction model succeeded",
                evidence_span=evidence_from_quote("job_description", str(ctx.job_doc.get("title") or "")),
            )
        ]
        artifact = JDFactsDoc(
            job_id=str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id")),
            level2_job_id=str(ctx.job_doc.get("_id")),
            jd_text_hash=ctx.jd_checksum,
            extractor_version=EXTRACTOR_VERSION_V2,
            judge_prompt_version=PROMPT_VERSION_V2,
            deterministic=deterministic,
            llm_additions=[],
            llm_flags=llm_flags,
            confirmations={"used_processed_jd_sections": bool(structured_sections.get("used_processed_jd_sections"))},
            extraction=finalized,
            merged_view=merged_view,
            provenance=provenance,
        )

        output: dict[str, Any] = {}
        if jd_facts_v2_live_compat_write_enabled():
            output["extracted_jd"] = compat_projection
            if finalized.salary_range:
                output["salary_range"] = finalized.salary_range

        return StageResult(
            output=output,
            stage_output=artifact.model_dump(),
            artifact_writes=[
                ArtifactWrite(
                    collection="jd_facts",
                    unique_filter={
                        "job_id": artifact.job_id,
                        "jd_text_hash": artifact.jd_text_hash,
                        "extractor_version": artifact.extractor_version,
                        "judge_prompt_version": artifact.judge_prompt_version,
                    },
                    document=artifact.model_dump(),
                    ref_name="jd_facts",
                )
            ],
            provider_used=provider_used,
            model_used=model_used,
            prompt_version=PROMPT_VERSION_V2,
            provider_attempts=attempts,
            provider_fallback_reason=fallback_reason,
        )

    def run(self, ctx: StageContext) -> StageResult:
        if jd_facts_v2_enabled():
            return self._run_v2(ctx)
        return self._run_v1(ctx)


assert isinstance(JDFactsStage(), StageBase)
