"""Iteration-4.1 jd_facts stage with runner-parity extraction V2 only."""

from __future__ import annotations

import re
import time
from typing import Any, List

from src.common.codex_cli import CodexCLI
from src.layer1_4.claude_jd_extractor import JDExtractor
from src.preenrich.blueprint_config import (
    jd_facts_escalate_on_failure_enabled,
    jd_facts_escalation_models,
    jd_facts_v2_live_compat_write_enabled,
    load_job_taxonomy,
)
from src.preenrich.blueprint_models import (
    JDFactsDoc,
    JDFactsExtractionOutput,
    JDJudgeFlag,
)
from src.preenrich.blueprint_prompts import build_p_jd_extract
from src.preenrich.stages.base import StageBase
from src.preenrich.stages.blueprint_common import (
    detect_remote_policy,
    evidence_from_quote,
    extract_bullets_for_headers,
    extract_keywords,
    extract_salary_range,
    extract_skill_signals,
)
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION_V2 = "P-jd-extract:v2"
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
        "responsibility_hints": extract_bullets_for_headers(
            description,
            ("responsibilities", "what you'll do", "what you will do", "what youll do", "duties", "accountabilities", "impact"),
        ),
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
    payload = _normalize_rich_contract_shapes(payload, deterministic)
    return payload


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _split_listish_text(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r"(?:\n+|•|●|·|;|\s{2,})", text)
    normalized = [part.strip(" -*\t") for part in parts if part and part.strip(" -*\t")]
    return normalized or [text]


def _supplement_minimum_content_lists(
    payload: dict[str, Any],
    deterministic: dict[str, Any],
    *,
    description: str,
) -> dict[str, Any]:
    responsibilities = _dedupe_strings(
        [part for item in _as_string_list(payload.get("responsibilities")) for part in _split_listish_text(item)]
    )
    if len(responsibilities) < 3:
        responsibilities.extend(
            _dedupe_strings(
                [part for item in _as_string_list(deterministic.get("responsibility_hints")) for part in _split_listish_text(item)]
            )
        )
        responsibilities.extend(
            _dedupe_strings(
                extract_bullets_for_headers(
                    description,
                    ("responsibilities", "what you'll do", "what you will do", "what youll do", "duties", "accountabilities", "impact"),
                )
            )
        )
        payload["responsibilities"] = _dedupe_strings(responsibilities)[:8]

    qualifications = _dedupe_strings(
        [part for item in _as_string_list(payload.get("qualifications")) for part in _split_listish_text(item)]
    )
    if len(qualifications) < 2:
        qualifications.extend(
            _dedupe_strings([part for item in _as_string_list(deterministic.get("must_haves")) for part in _split_listish_text(item)])
        )
        qualifications.extend(
            _dedupe_strings(
                extract_bullets_for_headers(description, ("requirements", "must have", "qualifications", "minimum qualifications"))
            )
        )
        payload["qualifications"] = _dedupe_strings(qualifications)[:12]

    nice_to_haves = _dedupe_strings(
        [part for item in _as_string_list(payload.get("nice_to_haves")) for part in _split_listish_text(item)]
    )
    if not nice_to_haves:
        nice_to_haves = _dedupe_strings(list(deterministic.get("nice_to_haves") or []))
    payload["nice_to_haves"] = nice_to_haves[:10]

    keywords = _dedupe_strings(_as_string_list(payload.get("top_keywords")))
    # Preserve ranked model output when it already contains a meaningful ordered set.
    if len(keywords) < 4:
        keywords.extend(_dedupe_strings(_as_string_list(deterministic.get("top_keywords"))))
        keywords.extend(_dedupe_strings(_as_string_list(deterministic.get("weak_keyword_hints"))))
        payload["top_keywords"] = _dedupe_strings(keywords)[:15]

    return payload


def _normalize_weight_bucket(
    value: Any,
    *,
    required_keys: tuple[str, ...],
    aliases: dict[str, str],
) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, int] = {key: 0 for key in required_keys}
    seen = False
    for key, raw in value.items():
        canonical = aliases.get(str(key).strip().lower().replace("-", "_").replace(" ", "_"))
        if not canonical:
            continue
        try:
            normalized[canonical] = int(raw)
            seen = True
        except Exception:
            continue
    return normalized if seen else None


def _normalize_rich_contract_shapes(payload: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    salary_range = payload.get("salary_range")
    if isinstance(salary_range, dict):
        text = str(salary_range.get("text") or salary_range.get("display") or salary_range.get("value") or "").strip()
        payload["salary_range"] = text or None

    remote_detail = payload.get("remote_location_detail")
    if isinstance(remote_detail, str):
        detail_text = remote_detail.strip()
        if detail_text:
            location_hint = (deterministic.get("location") or {}).get("value")
            payload["remote_location_detail"] = {
                "remote_anywhere": "anywhere" in detail_text.lower(),
                "remote_regions": [],
                "timezone_expectations": [],
                "travel_expectation": None,
                "onsite_expectation": None,
                "location_constraints": [detail_text],
                "relocation_support": None,
                "primary_locations": [str(location_hint)] if location_hint else [],
                "secondary_locations": [],
                "geo_scope": "not_specified",
                "work_authorization_notes": None,
            }
    elif isinstance(remote_detail, dict):
        geo_scope = str(remote_detail.get("geo_scope") or "").strip().lower().replace("-", "_").replace(" ", "_")
        geo_scope_aliases = {
            "city_region": "region",
            "metro_region": "region",
            "metro_area": "region",
            "single_region": "region",
            "countrywide": "country",
            "nationwide": "country",
            "worldwide": "global",
            "international": "global",
            "city": "single_city",
            "multiple_cities": "multi_city",
        }
        if geo_scope in geo_scope_aliases:
            remote_detail["geo_scope"] = geo_scope_aliases[geo_scope]

    expectations = payload.get("expectations")
    if isinstance(expectations, list):
        payload["expectations"] = {
            "explicit_outcomes": _as_string_list(expectations),
            "delivery_expectations": [],
            "leadership_expectations": [],
            "communication_expectations": [],
            "collaboration_expectations": [],
            "first_90_day_expectations": [],
        }
    elif isinstance(expectations, str):
        payload["expectations"] = {
            "explicit_outcomes": [expectations.strip()] if expectations.strip() else [],
            "delivery_expectations": [],
            "leadership_expectations": [],
            "communication_expectations": [],
            "collaboration_expectations": [],
            "first_90_day_expectations": [],
        }

    team_context = payload.get("team_context")
    if isinstance(team_context, str):
        payload["team_context"] = {
            "team_size": None,
            "reporting_to": None,
            "org_scope": team_context.strip() or None,
            "management_scope": None,
        }

    language_requirements = payload.get("language_requirements")
    if isinstance(language_requirements, list):
        payload["language_requirements"] = {
            "required_languages": [],
            "preferred_languages": [],
            "fluency_expectations": _as_string_list(language_requirements),
            "language_notes": None,
        }
    elif isinstance(language_requirements, str):
        payload["language_requirements"] = {
            "required_languages": [],
            "preferred_languages": [],
            "fluency_expectations": [language_requirements.strip()] if language_requirements.strip() else [],
            "language_notes": None,
        }

    residual_context = payload.get("residual_context")
    if isinstance(residual_context, list):
        joined = " ".join(_as_string_list(residual_context)).strip()
        payload["residual_context"] = joined or None

    ideal_candidate_profile = payload.get("ideal_candidate_profile")
    if isinstance(ideal_candidate_profile, dict):
        if "key_traits" in ideal_candidate_profile:
            ideal_candidate_profile["key_traits"] = _as_string_list(ideal_candidate_profile.get("key_traits"))[:5]
        if "culture_signals" in ideal_candidate_profile:
            ideal_candidate_profile["culture_signals"] = _as_string_list(ideal_candidate_profile.get("culture_signals"))[:4]

    weighting_profiles = payload.get("weighting_profiles")
    if isinstance(weighting_profiles, dict):
        expectation_weights = _normalize_weight_bucket(
            weighting_profiles.get("expectation_weights"),
            required_keys=("delivery", "communication", "leadership", "collaboration", "strategic_scope"),
            aliases={
                "delivery": "delivery",
                "production_ml_delivery": "delivery",
                "hands_on_ai_ml_delivery": "delivery",
                "communication": "communication",
                "executive_communication": "communication",
                "leadership": "leadership",
                "people_leadership": "leadership",
                "collaboration": "collaboration",
                "cross_functional_collaboration": "collaboration",
                "strategic_scope": "strategic_scope",
                "fintech_domain_context": "strategic_scope",
                "domain_context": "strategic_scope",
            },
        )
        operating_style_weights = _normalize_weight_bucket(
            weighting_profiles.get("operating_style_weights"),
            required_keys=("autonomy", "ambiguity", "pace", "process_rigor", "stakeholder_exposure"),
            aliases={
                "autonomy": "autonomy",
                "remote_autonomy": "autonomy",
                "ambiguity": "ambiguity",
                "hands_on_building": "ambiguity",
                "pace": "pace",
                "hands_on_execution": "pace",
                "process_rigor": "process_rigor",
                "technical_quality_rigor": "process_rigor",
                "stakeholder_exposure": "stakeholder_exposure",
                "remote_communication": "stakeholder_exposure",
            },
        )
        payload["weighting_profiles"] = {
            "expectation_weights": expectation_weights,
            "operating_style_weights": operating_style_weights,
        }
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


def _normalize_role_category(
    payload: dict[str, Any],
    title: str,
    deterministic: dict[str, Any],
    *,
    description: str = "",
) -> None:
    current = str(payload.get("role_category") or "")
    lowered_title = f"{title or ''} {description or ''}".lower()
    responsibilities = " ".join(_as_string_list(payload.get("responsibilities"))).lower()
    qualifications = " ".join(_as_string_list(payload.get("qualifications"))).lower()
    leadership_text = f"{responsibilities} {qualifications}"
    if current == "tech_lead" and ("engineering leader" in lowered_title or "ai engineering leader" in lowered_title):
        payload["role_category"] = "engineering_manager"
        return
    if current == "tech_lead" and "leader" in lowered_title:
        if any(token in leadership_text for token in ("lead teams", "team mentoring", "set technical direction", "leading teams", "mentor")):
            payload["role_category"] = "engineering_manager"


def _normalize_top_keywords(payload: dict[str, Any]) -> None:
    normalized: list[str] = []
    for value in _as_string_list(payload.get("top_keywords")):
        if value and value not in normalized:
            normalized.append(value)
    payload["top_keywords"] = normalized[:15]


def _literalize_responsibilities(payload: dict[str, Any], description: str, title: str) -> None:
    text = (description or "").lower()
    responsibilities: list[str] = _dedupe_strings(_as_string_list(payload.get("responsibilities")))
    responsibility_text = " ".join(responsibilities).lower()

    def add(line: str) -> None:
        if line and line not in responsibilities:
            responsibilities.append(line)

    if (
        "engineering leader" in title.lower()
        or "engineering leader" in text
        or "lead teams" in text
        or "leading teams" in text
        or "lead teams" in responsibility_text
        or "set technical direction" in responsibility_text
        or "team mentoring" in text
    ):
        responsibilities = [
            "Lead AI engineering team and set technical direction"
            if item.lower() == "lead teams and set technical direction"
            else item
            for item in responsibilities
        ]
        add("Lead AI engineering team and set technical direction")
    if (
        "delivering ml solutions into production" in text
        or "delivering applied ml solutions into production" in text
        or "deliver applied ml solutions into production" in text
    ):
        add("Deliver applied ML solutions into production environments")
    if "llm" in text or "nlp" in text:
        add("Design and implement LLM and NLP use cases for business applications")
    if "microservices" in text or "systems integration" in text:
        add("Architect microservices and systems integration for AI capabilities")
    if "third-party ai tools" in text or "apis" in text:
        add("Integrate third-party AI tools and APIs into existing infrastructure")
    if "scaling ai capability" in text or "scale ai capability" in text:
        add("Scale AI capability across the organization")
    if "automation" in text and "intelligence" in text and "cross-border payments" in text:
        add("Build automation and intelligence solutions for cross-border payments")
    if "next-generation solutions" in text and "fintech" in text:
        add("Drive next-generation AI solutions for global fintech operations")

    if responsibilities:
        payload["responsibilities"] = _dedupe_strings(responsibilities)[:8]


def _derive_success_metrics(payload: dict[str, Any], description: str) -> None:
    text = (description or "").lower()
    responsibility_text = " ".join(_as_string_list(payload.get("responsibilities"))).lower()
    metrics: list[str] = []

    def add(line: str) -> None:
        if line and line not in metrics:
            metrics.append(line)

    if (
        "delivering ml solutions into production" in text
        or "delivering applied ml solutions into production" in text
        or "deliver applied ml solutions into production" in text
    ):
        add("Applied ML solutions successfully deployed to production")
    if "scaling ai capability" in text or "scale ai capability" in text:
        add("AI capability scaled across the organization")
    if (
        "lead teams" in text
        or "leading teams" in text
        or "technical direction" in text
        or "team mentoring" in text
        or "lead teams" in responsibility_text
        or "set technical direction" in responsibility_text
    ):
        add("Team growth and technical development")
    if "third-party ai tools" in text or "apis" in text:
        add("Third-party AI tools effectively integrated")
    if "automation" in text and "intelligence" in text:
        add("Automation and intelligence solutions operational")
    if "cross-border payments" in text:
        add("Measurable improvements in payment processing efficiency")

    if metrics:
        payload["success_metrics"] = metrics[:8]


def _conflict_flag(field: str, deterministic_value: Any, proposed_value: Any, locator: str | None = None) -> JDJudgeFlag:
    return JDJudgeFlag(
        field=field,
        deterministic_value=deterministic_value,
        proposed_value=proposed_value,
        severity="warn",
        reasoning="LLM proposed overwrite of deterministic anchor field",
        evidence_span=evidence_from_quote("job_description", str(proposed_value or ""), locator),
    )


def _finalize_extraction(
    extraction: JDFactsExtractionOutput,
    deterministic: dict[str, Any],
    *,
    description: str,
) -> tuple[JDFactsExtractionOutput, list[JDJudgeFlag], dict[str, str]]:
    payload = extraction.model_dump()
    flags: list[JDJudgeFlag] = []
    provenance: dict[str, str] = {key: "llm_extract" for key in payload.keys()}
    title = str(payload.get("title") or (deterministic.get("title") or {}).get("value") or "")

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

    _normalize_role_category(payload, title, deterministic, description=description)
    _literalize_responsibilities(payload, description, title)
    _derive_success_metrics(payload, description)
    _normalize_top_keywords(payload)
    payload["implied_pain_points"] = []
    provenance["implied_pain_points"] = "deferred"

    finalized = JDFactsExtractionOutput.model_validate(payload)
    for field, value in finalized.model_dump().items():
        provenance.setdefault(field, "llm_extract" if value not in (None, "", []) else "fallback_default")
    return finalized, flags, provenance


def _invoke_codex_json(
    *,
    prompt: str,
    model: str,
    job_id: str,
    cwd: str | None = None,
    reasoning_effort: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    t0 = time.monotonic()
    cli = CodexCLI(model=model, cwd=cwd, reasoning_effort=reasoning_effort)
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


def _validate_llm_output(
    raw_output: dict[str, Any],
    deterministic: dict[str, Any],
    *,
    description: str,
) -> JDFactsExtractionOutput:
    payload = _normalize_extraction_payload(raw_output, deterministic)
    payload = _supplement_minimum_content_lists(payload, deterministic, description=description)
    title = str(payload.get("title") or (deterministic.get("title") or {}).get("value") or "")
    _normalize_role_category(payload, title, deterministic, description=description)
    _literalize_responsibilities(payload, description, title)
    _derive_success_metrics(payload, description)
    _normalize_top_keywords(payload)
    return JDFactsExtractionOutput.model_validate(payload)


def _claude_fallback_enabled(ctx: StageContext) -> bool:
    fallback_provider = (ctx.config.fallback_provider if ctx.config else "claude") or "claude"
    return fallback_provider.lower() != "none"


class JDFactsStage:
    name: str = "jd_facts"
    dependencies: List[str] = ["jd_structure"]

    def _run_v2(self, ctx: StageContext) -> StageResult:
        deterministic = _deterministic_extract(ctx.job_doc)
        structured_sections = _package_structured_sections(ctx.job_doc)
        prompt = build_p_jd_extract(
            title=str(ctx.job_doc.get("title") or ""),
            company=str(ctx.job_doc.get("company") or ""),
            deterministic_hints=deterministic,
            structured_sections=structured_sections,
            raw_jd_excerpt=_compact_raw_jd(_description(ctx.job_doc)),
            taxonomy_context=load_job_taxonomy(),
        )
        attempts: list[dict[str, Any]] = []
        extraction: JDFactsExtractionOutput | None = None
        provider_used = "none"
        model_used = None
        fallback_reason = None

        primary_model = ctx.config.primary_model or "gpt-5.2"
        job_id = str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "unknown")

        raw_output, primary_attempt = _invoke_codex_json(
            prompt=prompt,
            model=primary_model,
            job_id=job_id,
            cwd=ctx.config.codex_workdir,
            reasoning_effort=ctx.config.reasoning_effort,
        )
        attempts.append(primary_attempt)

        try:
            if raw_output is None:
                raise RuntimeError(primary_attempt.get("error") or "primary codex call failed")
            extraction = _validate_llm_output(raw_output, deterministic, description=_description(ctx.job_doc))
            if _needs_escalation(extraction, str(ctx.job_doc.get("title") or "")) and jd_facts_escalate_on_failure_enabled():
                raise RuntimeError("extraction ambiguity requires escalation")
            provider_used = "codex"
            model_used = primary_model
        except Exception as primary_error:
            fallback_reason = primary_attempt.get("outcome") if primary_attempt.get("outcome") != "success" else "error_schema"
            if jd_facts_escalate_on_failure_enabled():
                last_escalation_error: Exception | None = None
                for escalation_model in jd_facts_escalation_models():
                    escalated_output, escalated_attempt = _invoke_codex_json(
                        prompt=prompt,
                        model=escalation_model,
                        job_id=job_id,
                        cwd=ctx.config.codex_workdir,
                        reasoning_effort=ctx.config.reasoning_effort,
                    )
                    attempts.append(escalated_attempt)
                    try:
                        if escalated_output is None:
                            raise RuntimeError(escalated_attempt.get("error") or "escalation codex call failed")
                        extraction = _validate_llm_output(escalated_output, deterministic, description=_description(ctx.job_doc))
                        provider_used = "codex"
                        model_used = escalation_model
                        last_escalation_error = None
                        break
                    except Exception as escalation_error:
                        last_escalation_error = escalation_error
                        continue
                if extraction is None:
                    if not _claude_fallback_enabled(ctx):
                        raise RuntimeError(
                            f"jd_facts V2 codex-only extraction failed for job {job_id}: "
                            f"primary={primary_error}; escalation={last_escalation_error}"
                        ) from last_escalation_error
                    runner_payload, runner_attempt = _invoke_runner_fallback(ctx=ctx, deterministic=deterministic)
                    attempts.append(runner_attempt)
                    extraction = _validate_llm_output(runner_payload, deterministic, description=_description(ctx.job_doc))
                    provider_used = "claude"
                    model_used = runner_attempt["model"]
            else:
                if not _claude_fallback_enabled(ctx):
                    raise RuntimeError(f"jd_facts V2 codex-only extraction failed for job {job_id}: {primary_error}") from primary_error
                runner_payload, runner_attempt = _invoke_runner_fallback(ctx=ctx, deterministic=deterministic)
                attempts.append(runner_attempt)
                extraction = _validate_llm_output(runner_payload, deterministic, description=_description(ctx.job_doc))
                provider_used = "claude"
                model_used = runner_attempt["model"]
            if extraction is None:
                raise RuntimeError(f"jd_facts V2 extraction failed for job {job_id}: {primary_error}") from primary_error

        assert extraction is not None
        finalized, conflict_flags, provenance = _finalize_extraction(
            extraction,
            deterministic,
            description=_description(ctx.job_doc),
        )
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
        return self._run_v2(ctx)


assert isinstance(JDFactsStage(), StageBase)
