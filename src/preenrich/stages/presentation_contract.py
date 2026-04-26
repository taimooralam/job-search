"""Guarded iteration-4.2.2 presentation_contract slice."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, List

from src.preenrich.blueprint_config import (
    current_git_sha,
    presentation_contract_cv_shape_expectations_enabled,
    presentation_contract_dimension_weights_enabled,
    presentation_contract_document_expectations_enabled,
    presentation_contract_emphasis_rules_enabled,
    presentation_contract_ideal_candidate_enabled,
    presentation_contract_merged_prompt_enabled,
)
from src.preenrich.blueprint_models import (
    APPLIES_TO_ENUM_VERSION,
    DIMENSION_ENUM_VERSION,
    RULE_TYPE_ENUM_VERSION,
    CvShapeExpectationsDoc,
    DocumentExpectationsDoc,
    ExperienceDimensionWeightsDoc,
    IdealCandidatePresentationModelDoc,
    PresentationContractDoc,
    PromptMetadata,
    TruthConstrainedEmphasisRulesDoc,
    build_truth_constrained_emphasis_rules_compact,
    normalize_cv_shape_expectations_payload,
    normalize_document_expectations_payload,
    normalize_experience_dimension_weights_payload,
    normalize_ideal_candidate_payload,
    normalize_truth_constrained_emphasis_rules_payload,
)
from src.preenrich.blueprint_prompts import (
    PROMPT_VERSIONS,
    build_p_cv_shape_expectations,
    build_p_document_and_cv_shape,
    build_p_document_expectations,
    build_p_emphasis_rules,
    build_p_experience_dimension_weights,
    build_p_ideal_candidate,
)
from src.preenrich.stages.base import _invoke_codex_json_traced
from src.preenrich.types import ArtifactWrite, StageContext, StageResult

PROMPT_VERSION = "presentation_contract@v4.2.6"
STAGE_VERSION = "presentation_contract.v4.2.6"

_MANDATORY_EMPHASIS_TOPICS = [
    "title_inflation",
    "ai_claims",
    "leadership_scope",
    "architecture_claims",
    "domain_expertise",
    "stakeholder_management_claims",
    "metrics_scale_claims",
    "credibility_ladder_degradation",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.2:
        return "low"
    return "unresolved"


def _job_id(ctx: StageContext) -> str:
    return str(ctx.job_doc.get("job_id") or ctx.job_doc.get("_id") or "presentation-contract")


def _level2_job_id(ctx: StageContext) -> str:
    return str(ctx.job_doc.get("_id") or ctx.job_doc.get("job_id") or "presentation-contract")


def _jd_excerpt(ctx: StageContext, *, limit: int = 1800) -> str:
    description = str(ctx.job_doc.get("description") or "").strip()
    if description:
        return description[:limit]
    outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
    merged_view = ((outputs.get("jd_facts") or {}).get("merged_view") or {})
    pieces = [
        str(merged_view.get("title") or ctx.job_doc.get("title") or "").strip(),
        "\n".join(list(merged_view.get("responsibilities") or [])[:6]),
        "\n".join(list(merged_view.get("qualifications") or [])[:6]),
    ]
    return "\n".join(piece for piece in pieces if piece)[:limit]


def _prompt_metadata(*, prompt_id: str, ctx: StageContext) -> PromptMetadata:
    return PromptMetadata(
        prompt_id=prompt_id,
        prompt_version=PROMPT_VERSIONS[prompt_id],
        prompt_file_path=str(__file__).replace("stages/presentation_contract.py", "blueprint_prompts.py"),
        git_sha=current_git_sha(),
        provider=ctx.config.provider or "codex",
        model=ctx.config.primary_model,
        transport_used=ctx.config.transport or "none",
        fallback_provider=ctx.config.fallback_provider,
        fallback_transport=ctx.config.fallback_transport,
    )


def _first_text(items: Any) -> str | None:
    if isinstance(items, str):
        text = items.strip()
        return text or None
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _ai_intensity(classification: dict[str, Any]) -> str:
    return str(((classification.get("ai_taxonomy") or {}).get("intensity")) or "unknown").strip().lower() or "unknown"


def _role_family(classification: dict[str, Any], title: str) -> str:
    category = str(classification.get("primary_role_category") or "").strip().lower()
    title_lower = title.lower()
    if category in {"ai_architect", "staff_principal_engineer"} or "architect" in title_lower:
        return "architecture_first"
    if category in {"engineering_manager", "senior_manager", "director", "head_of_engineering"} or any(
        token in title_lower for token in ("manager", "director", "head", "vp")
    ):
        return "leadership_first"
    if any(token in title_lower for token in ("platform", "infrastructure", "sre")):
        return "platform_first"
    if any(token in title_lower for token in ("transform", "greenfield", "first ai")):
        return "transformation_first"
    if _ai_intensity(classification) == "core" and any(token in title_lower for token in ("ai", "ml", "machine learning", "llm")):
        return "ai_first"
    return "delivery_first"


def _ats_pressure(application_profile: dict[str, Any]) -> tuple[str, str, list[str]]:
    vendor = str(application_profile.get("ats_vendor") or application_profile.get("portal_family") or "unknown").strip().lower()
    if vendor == "workday":
        return "high", "top_heavy", ["single_column", "no_tables_in_experience", "plain_bullets", "ascii_safe"]
    if vendor == "taleo":
        return "extreme", "top_heavy", ["single_column", "no_tables_in_experience", "plain_bullets", "ascii_safe"]
    if vendor == "greenhouse":
        return "standard", "top_heavy", ["single_column", "no_tables_in_experience", "plain_bullets"]
    if vendor == "lever":
        return "standard", "balanced", ["single_column", "no_tables_in_experience", "plain_bullets"]
    return "standard", "balanced", ["single_column", "no_tables_in_experience", "plain_bullets"]


def _role_thesis_priors(
    *,
    classification: dict[str, Any],
    jd_facts: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    application_profile: dict[str, Any],
) -> dict[str, Any]:
    title = str(jd_facts.get("title") or "").strip()
    goal = _role_family(classification, title)
    ai_intensity = _ai_intensity(classification)
    ats_pressure, keyword_bias, format_rules = _ats_pressure(application_profile)
    header_density = "proof_dense" if goal in {"architecture_first", "ai_first", "platform_first"} else "balanced"
    ai_policy = {
        "core": "required",
        "significant": "required",
        "adjacent": "optional",
        "none": "discouraged",
    }.get(ai_intensity, "embedded_only")
    section_order = ["header", "summary", "key_achievements", "core_competencies", "experience", "education"]
    if ai_policy in {"required", "optional", "embedded_only"}:
        section_order.insert(4, "ai_highlights")
    if goal in {"architecture_first", "platform_first"}:
        section_order.insert(5, "projects")
    target_roles = list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"])
    proof_order = {
        "architecture_first": ["architecture", "metric", "ai", "leadership"],
        "platform_first": ["architecture", "reliability", "metric", "leadership"],
        "leadership_first": ["leadership", "metric", "stakeholder", "architecture"],
        "ai_first": ["ai", "metric", "architecture", "leadership"],
        "transformation_first": ["leadership", "stakeholder", "metric", "architecture"],
        "delivery_first": ["metric", "architecture", "leadership", "stakeholder"],
    }.get(goal, ["metric", "architecture", "leadership", "stakeholder"])
    return {
        "goal": goal,
        "header_density": header_density,
        "section_order": section_order,
        "ai_section_policy": ai_policy,
        "ats_pressure": ats_pressure,
        "keyword_placement_bias": keyword_bias,
        "format_rules": format_rules,
        "proof_order": proof_order,
        "target_roles": target_roles,
    }


def _evaluator_axis_summary(stakeholder_surface: dict[str, Any]) -> list[dict[str, Any]]:
    roles = list(stakeholder_surface.get("evaluator_coverage_target") or [])
    real_records = list(stakeholder_surface.get("real_stakeholders") or [])
    inferred = list(stakeholder_surface.get("inferred_stakeholder_personas") or [])
    rows: list[dict[str, Any]] = []
    for role in roles:
        matching = [item for item in real_records if item.get("stakeholder_type") == role]
        if not matching:
            matching = [item for item in inferred if item.get("persona_type") == role]
        selected = (matching[0] if matching else {}) or {}
        surface = (selected.get("cv_preference_surface") if isinstance(selected, dict) else {}) or {}
        reject_signals = selected.get("likely_reject_signals") if isinstance(selected, dict) else []
        rows.append(
            {
                "role": role,
                "top_review_objectives": list(surface.get("review_objectives") or [])[:4],
                "top_preferred_evidence_types": list(surface.get("preferred_evidence_types") or [])[:4],
                "reject_signals": [item.get("bullet") for item in (reject_signals or [])[:3] if isinstance(item, dict)],
                "ai_section_preference": surface.get("ai_section_preference") or "unresolved",
            }
        )
    return rows


def _proof_order_candidates(pain_point_intelligence: dict[str, Any], priors: dict[str, Any]) -> list[str]:
    proof_map = list(pain_point_intelligence.get("proof_map") or [])
    counts: dict[str, int] = {}
    for item in proof_map:
        if not isinstance(item, dict):
            continue
        proof_type = str(item.get("preferred_proof_type") or "").strip().lower()
        if proof_type:
            counts[proof_type] = counts.get(proof_type, 0) + 1
    if counts:
        return [key for key, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    return list(priors["proof_order"])


def _proof_category_frequencies(pain_point_intelligence: dict[str, Any], priors: dict[str, Any]) -> dict[str, int]:
    proof_map = list(pain_point_intelligence.get("proof_map") or [])
    counts: dict[str, int] = {}
    for item in proof_map:
        if not isinstance(item, dict):
            continue
        proof_type = str(item.get("preferred_proof_type") or "").strip().lower()
        if proof_type:
            counts[proof_type] = counts.get(proof_type, 0) + 1
    if counts:
        return counts
    return {key: 1 for key in priors["proof_order"]}


def _normalized_title_candidates(jd_facts: dict[str, Any], classification: dict[str, Any]) -> list[str]:
    title = str(jd_facts.get("title") or jd_facts.get("normalized_title") or "").strip()
    normalized_title = str(jd_facts.get("normalized_title") or "").strip()
    candidates: list[str] = []
    for item in (title, normalized_title):
        if item and item not in candidates:
            candidates.append(item)
    category = str(classification.get("primary_role_category") or "").strip().lower()
    if category == "ai_architect":
        for item in ("AI Architect", "Principal AI Architect", "Architect, AI Platforms"):
            if item not in candidates and (not title or "architect" in title.lower()):
                candidates.append(item)
    elif category in {"engineering_manager", "director", "head_of_engineering"}:
        for item in ("Engineering Leader", "Engineering Manager"):
            if item not in candidates and (not title or any(token in title.lower() for token in ("manager", "director", "head"))):
                candidates.append(item)
    return candidates[:5]


def _signal_priority_defaults(role_family: str) -> tuple[list[str], list[str], list[str]]:
    must_by_family = {
        "architecture_first": ["architecture_judgment", "ownership_scope", "production_impact"],
        "platform_first": ["platform_reliability", "ownership_scope", "production_impact"],
        "leadership_first": ["leadership_scope", "stakeholder_alignment", "production_impact"],
        "ai_first": ["ai_depth", "architecture_judgment", "production_impact"],
        "transformation_first": ["leadership_scope", "stakeholder_alignment", "delivery_rigor"],
        "delivery_first": ["production_impact", "ownership_scope", "delivery_rigor"],
    }
    should_by_family = {
        "architecture_first": ["ai_depth", "platform_reliability", "stakeholder_alignment"],
        "platform_first": ["architecture_judgment", "delivery_rigor", "stakeholder_alignment"],
        "leadership_first": ["ownership_scope", "architecture_judgment", "domain_context"],
        "ai_first": ["platform_reliability", "ownership_scope", "domain_context"],
        "transformation_first": ["architecture_judgment", "production_impact", "domain_context"],
        "delivery_first": ["architecture_judgment", "stakeholder_alignment", "domain_context"],
    }
    deemphasize_by_family = {
        "architecture_first": ["tool_listing", "generic_leadership_claim"],
        "platform_first": ["tool_listing", "generic_leadership_claim"],
        "leadership_first": ["tool_listing"],
        "ai_first": ["tool_listing", "generic_leadership_claim"],
        "transformation_first": ["tool_listing"],
        "delivery_first": ["tool_listing"],
    }
    return (
        list(must_by_family.get(role_family, ["ownership_scope", "production_impact"])),
        list(should_by_family.get(role_family, ["role_fit", "domain_context"])),
        list(deemphasize_by_family.get(role_family, ["tool_listing"])),
    )


def _proof_category_to_signal_tag(proof_category: str) -> str:
    mapping = {
        "architecture": "architecture_judgment",
        "metric": "production_impact",
        "ai": "ai_depth",
        "leadership": "leadership_scope",
        "stakeholder": "stakeholder_alignment",
        "reliability": "platform_reliability",
        "domain": "domain_context",
        "process": "delivery_rigor",
        "scale": "ownership_scope",
        "compliance": "delivery_rigor",
    }
    return mapping.get(proof_category, "role_fit")


def _tone_profile_from_document(document_expectations: dict[str, Any]) -> dict[str, Any]:
    tone = dict((document_expectations.get("tone_posture") or {}))
    return {
        "primary_tone": tone.get("primary_tone") or "balanced",
        "hype_tolerance": tone.get("hype_tolerance") or "medium",
        "narrative_tolerance": tone.get("narrative_tolerance") or "medium",
        "formality": tone.get("formality") or "neutral",
    }


def _stakeholder_signal_biases(stakeholder_surface: dict[str, Any]) -> dict[str, list[str]]:
    signal_map = {
        "named_systems": "architecture_judgment",
        "metrics": "production_impact",
        "ownership_scope": "ownership_scope",
        "stakeholder_management": "stakeholder_alignment",
    }
    preferences: dict[str, list[str]] = {}
    for record in list(stakeholder_surface.get("real_stakeholders") or []) + list(stakeholder_surface.get("inferred_stakeholder_personas") or []):
        if not isinstance(record, dict):
            continue
        role = str(record.get("stakeholder_type") or record.get("persona_type") or "").strip()
        if not role:
            continue
        surface = dict(record.get("cv_preference_surface") or {})
        mapped = [
            signal_map.get(str(item).strip().lower())
            for item in list(surface.get("preferred_evidence_types") or []) + list(surface.get("preferred_signal_order") or [])
        ]
        preferences[role] = [item for item in mapped if item]
    return preferences


def _ideal_candidate_priors(
    *,
    priors: dict[str, Any],
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
    document_expectations: dict[str, Any],
    cv_shape_expectations: dict[str, Any],
) -> dict[str, Any]:
    role_family = str(priors.get("goal") or "delivery_first")
    must_signal, should_signal, de_emphasize = _signal_priority_defaults(role_family)
    proof_order = list(document_expectations.get("proof_order") or priors.get("proof_order") or [])
    acceptable_titles = _normalized_title_candidates(jd_facts, classification)
    stakeholder_biases = _stakeholder_signal_biases(stakeholder_surface)
    proof_map = list(pain_point_intelligence.get("proof_map") or [])
    proof_markers = []
    for item in proof_map[:4]:
        if not isinstance(item, dict):
            continue
        proof_markers.append(
            {
                "proof_category": str(item.get("preferred_proof_type") or "metric").strip().lower(),
                "marker": str(item.get("preferred_evidence_shape") or "").strip(),
                "bad_patterns": list(item.get("bad_proof_patterns") or []),
            }
        )
    return {
        "role_family": role_family,
        "acceptable_titles": acceptable_titles,
        "must_signal_defaults": must_signal,
        "should_signal_defaults": should_signal,
        "de_emphasize_defaults": de_emphasize,
        "proof_order": proof_order,
        "proof_to_signal_map": {item: _proof_category_to_signal_tag(item) for item in proof_order},
        "stakeholder_signal_biases": stakeholder_biases,
        "title_strategy": cv_shape_expectations.get("title_strategy") or "closest_truthful",
        "tone_profile": _tone_profile_from_document(document_expectations),
        "proof_markers": proof_markers,
        "seed_archetype": ((jd_facts.get("ideal_candidate_profile") or {}).get("archetype") if isinstance(jd_facts.get("ideal_candidate_profile"), dict) else None),
    }


_DIMENSION_ORDER = [
    "hands_on_implementation",
    "architecture_system_design",
    "leadership_enablement",
    "tools_technology_stack",
    "methodology_operating_model",
    "business_impact",
    "stakeholder_communication",
    "ai_ml_depth",
    "domain_context",
    "quality_risk_reliability",
    "delivery_execution_pace",
    "platform_scaling_change",
]
_DIMENSION_SIGNAL_TAG_MAP = {
    "architecture_judgment": "architecture_system_design",
    "hands_on_implementation": "hands_on_implementation",
    "production_impact": "business_impact",
    "ai_depth": "ai_ml_depth",
    "leadership_scope": "leadership_enablement",
    "stakeholder_alignment": "stakeholder_communication",
    "domain_context": "domain_context",
    "delivery_rigor": "delivery_execution_pace",
    "platform_reliability": "quality_risk_reliability",
    "ownership_scope": "platform_scaling_change",
    "role_fit": "hands_on_implementation",
    "recognizable_title": "tools_technology_stack",
}
_PROOF_CATEGORY_DIMENSION_MAP = {
    "metric": "business_impact",
    "architecture": "architecture_system_design",
    "leadership": "leadership_enablement",
    "domain": "domain_context",
    "reliability": "quality_risk_reliability",
    "ai": "ai_ml_depth",
    "stakeholder": "stakeholder_communication",
    "process": "methodology_operating_model",
    "compliance": "quality_risk_reliability",
    "scale": "platform_scaling_change",
}
_ROLE_FAMILY_WEIGHT_PRIORS = {
    "ai_first": {
        "hands_on_implementation": 16,
        "architecture_system_design": 15,
        "leadership_enablement": 5,
        "tools_technology_stack": 8,
        "methodology_operating_model": 6,
        "business_impact": 10,
        "stakeholder_communication": 6,
        "ai_ml_depth": 22,
        "domain_context": 4,
        "quality_risk_reliability": 3,
        "delivery_execution_pace": 3,
        "platform_scaling_change": 2,
    },
    "architecture_first": {
        "hands_on_implementation": 13,
        "architecture_system_design": 22,
        "leadership_enablement": 6,
        "tools_technology_stack": 6,
        "methodology_operating_model": 6,
        "business_impact": 12,
        "stakeholder_communication": 7,
        "ai_ml_depth": 10,
        "domain_context": 4,
        "quality_risk_reliability": 5,
        "delivery_execution_pace": 5,
        "platform_scaling_change": 4,
    },
    "platform_first": {
        "hands_on_implementation": 13,
        "architecture_system_design": 18,
        "leadership_enablement": 6,
        "tools_technology_stack": 6,
        "methodology_operating_model": 8,
        "business_impact": 8,
        "stakeholder_communication": 6,
        "ai_ml_depth": 8,
        "domain_context": 4,
        "quality_risk_reliability": 10,
        "delivery_execution_pace": 5,
        "platform_scaling_change": 8,
    },
    "leadership_first": {
        "hands_on_implementation": 8,
        "architecture_system_design": 10,
        "leadership_enablement": 20,
        "tools_technology_stack": 4,
        "methodology_operating_model": 10,
        "business_impact": 14,
        "stakeholder_communication": 12,
        "ai_ml_depth": 4,
        "domain_context": 4,
        "quality_risk_reliability": 4,
        "delivery_execution_pace": 6,
        "platform_scaling_change": 4,
    },
    "transformation_first": {
        "hands_on_implementation": 8,
        "architecture_system_design": 12,
        "leadership_enablement": 16,
        "tools_technology_stack": 4,
        "methodology_operating_model": 10,
        "business_impact": 14,
        "stakeholder_communication": 12,
        "ai_ml_depth": 6,
        "domain_context": 4,
        "quality_risk_reliability": 4,
        "delivery_execution_pace": 4,
        "platform_scaling_change": 6,
    },
    "delivery_first": {
        "hands_on_implementation": 18,
        "architecture_system_design": 15,
        "leadership_enablement": 6,
        "tools_technology_stack": 8,
        "methodology_operating_model": 8,
        "business_impact": 12,
        "stakeholder_communication": 6,
        "ai_ml_depth": 8,
        "domain_context": 4,
        "quality_risk_reliability": 5,
        "delivery_execution_pace": 6,
        "platform_scaling_change": 4,
    },
}
_AI_INTENSITY_CAPS = {
    "core": 40,
    "significant": 28,
    "adjacent": 15,
    "none": 5,
    "unknown": 10,
    "unresolved": 10,
}
_LEADERSHIP_CAPS = {
    "junior": {"none": 5, "partial": 8, "strong": 10},
    "mid": {"none": 8, "partial": 12, "strong": 15},
    "senior": {"none": 10, "partial": 18, "strong": 25},
    "principal": {"none": 15, "partial": 25, "strong": 35},
    "staff_plus": {"none": 15, "partial": 25, "strong": 35},
    "manager": {"none": 15, "partial": 25, "strong": 35},
    "director_plus": {"none": 15, "partial": 30, "strong": 45},
}
_ARCHITECTURE_CAPS = {
    "architecture_first": {"none": 15, "partial": 25, "strong": 40},
    "platform_first": {"none": 15, "partial": 25, "strong": 40},
    "ai_first": {"none": 12, "partial": 22, "strong": 35},
    "delivery_first": {"none": 10, "partial": 18, "strong": 28},
    "leadership_first": {"none": 10, "partial": 18, "strong": 25},
    "transformation_first": {"none": 10, "partial": 20, "strong": 30},
}


def _normalized_dimension_weights(weights: dict[str, Any] | None) -> dict[str, int]:
    normalized = {dimension: 0 for dimension in _DIMENSION_ORDER}
    for dimension, value in dict(weights or {}).items():
        if dimension in normalized:
            normalized[dimension] = int(value)
    return normalized


def _dimension_tail_fill(
    weights: dict[str, int],
    *,
    total: int = 100,
    skip_add_dimensions: set[str] | None = None,
) -> dict[str, int]:
    normalized = _normalized_dimension_weights(weights)
    blocked = set(skip_add_dimensions or set())
    current_total = sum(normalized.values())
    if current_total == total:
        return normalized
    if current_total <= 0:
        for dimension in ("hands_on_implementation", "architecture_system_design", "business_impact"):
            normalized[dimension] += 1
        current_total = sum(normalized.values())
    if current_total > total:
        for dimension in sorted(normalized, key=lambda item: (-normalized[item], _DIMENSION_ORDER.index(item))):
            if current_total <= total:
                break
            removable = min(normalized[dimension], current_total - total)
            normalized[dimension] -= removable
            current_total -= removable
    else:
        tail_order = [
            "tools_technology_stack",
            "methodology_operating_model",
            "domain_context",
            "delivery_execution_pace",
            "quality_risk_reliability",
            "platform_scaling_change",
            "hands_on_implementation",
            "business_impact",
            "stakeholder_communication",
            "architecture_system_design",
            "ai_ml_depth",
            "leadership_enablement",
        ]
        tail_order = [item for item in tail_order if item not in blocked] or [item for item in _DIMENSION_ORDER if item not in blocked] or list(_DIMENSION_ORDER)
        idx = 0
        while current_total < total:
            normalized[tail_order[idx % len(tail_order)]] += 1
            current_total += 1
            idx += 1
    return normalized


def _record_dimension_event(
    events: list[dict[str, Any]],
    *,
    kind: str,
    from_value: int | str | None,
    to_value: int | str | None,
    reason: str,
    path: str,
) -> None:
    events.append({"kind": kind, "from": from_value, "to": to_value, "reason": reason, "path": path})


def _apply_dimension_cap(
    weights: dict[str, int],
    *,
    dimension: str,
    cap: int,
    reason: str,
    events: list[dict[str, Any]],
) -> None:
    current = int(weights.get(dimension, 0))
    if current <= cap:
        return
    weights[dimension] = cap
    _record_dimension_event(
        events,
        kind="cap_clamp",
        from_value=current,
        to_value=cap,
        reason=reason,
        path=dimension,
    )


def _boost_dimension_floor(
    weights: dict[str, int],
    *,
    dimension: str,
    floor: int,
    reason: str,
    events: list[dict[str, Any]],
) -> None:
    current = int(weights.get(dimension, 0))
    if current >= floor:
        return
    weights[dimension] = floor
    _record_dimension_event(
        events,
        kind="floor_boost",
        from_value=current,
        to_value=floor,
        reason=reason,
        path=dimension,
    )


def _soften_dimension_ceiling(
    weights: dict[str, int],
    *,
    dimension: str,
    ceiling: int,
    reason: str,
    events: list[dict[str, Any]],
) -> None:
    current = int(weights.get(dimension, 0))
    if current <= ceiling:
        return
    weights[dimension] = ceiling
    _record_dimension_event(
        events,
        kind="soft_ceiling",
        from_value=current,
        to_value=ceiling,
        reason=reason,
        path=dimension,
    )


def _seniority_band(jd_facts: dict[str, Any]) -> str:
    raw = str(jd_facts.get("seniority_level") or jd_facts.get("seniority") or "").strip().lower()
    if raw in {"junior", "entry"}:
        return "junior"
    if raw in {"mid", "mid_level"}:
        return "mid"
    if raw in {"senior", "lead"}:
        return "senior"
    if raw in {"principal", "staff", "distinguished"}:
        return "principal"
    if raw in {"manager"}:
        return "manager"
    if raw in {"director", "head", "vp", "vice_president"}:
        return "director_plus"
    return "staff_plus" if "principal" in raw or "staff" in raw else "senior"


def _ai_intensity_cap(ai_intensity: str) -> int:
    return _AI_INTENSITY_CAPS.get(ai_intensity, _AI_INTENSITY_CAPS["unknown"])


def _leadership_dimension_cap(
    *,
    seniority_band: str,
    leadership_evidence_band: str,
    direct_reports: int,
) -> int:
    base_cap = int(
        (_LEADERSHIP_CAPS.get(str(seniority_band or "senior"), _LEADERSHIP_CAPS["senior"])).get(
            str(leadership_evidence_band or "none"),
            18,
        )
    )
    if str(seniority_band or "senior") in {"junior", "mid", "senior"} and int(direct_reports or 0) <= 0:
        return min(base_cap, 5)
    return base_cap


def _architecture_evidence_band(
    *,
    role_family: str,
    role_profile: dict[str, Any],
    company_profile: dict[str, Any],
    jd_facts: dict[str, Any],
) -> str:
    mandate_text = " ".join(str(item) for item in list(role_profile.get("mandate") or []))
    keywords = " ".join(str(item) for item in list(jd_facts.get("responsibilities") or []))
    combined = f"{mandate_text} {keywords}".lower()
    scale_signals = " ".join(str(item) for item in list(company_profile.get("scale_signals") or []))
    strong_tokens = ("architecture", "design authority", "platform strategy", "technical direction")
    partial_tokens = ("system design", "platform", "scaling", "design")
    if any(token in combined for token in strong_tokens):
        return "strong"
    if role_family in {"architecture_first", "platform_first"} and any(token in f"{combined} {scale_signals}".lower() for token in partial_tokens):
        return "partial"
    return "none"


def _leadership_evidence_band(
    *,
    jd_facts: dict[str, Any],
    stakeholder_surface: dict[str, Any],
) -> str:
    team_context = str((jd_facts.get("team_context") or {}).get("scope") or jd_facts.get("team_context") or "")
    target_roles = set(stakeholder_surface.get("evaluator_coverage_target") or [])
    leadership_tokens = ("lead", "mentor", "coach", "hire", "manage", "director", "head")
    if any(token in team_context.lower() for token in leadership_tokens):
        return "strong"
    if {"skip_level_leader", "executive_sponsor"} & target_roles:
        return "partial"
    return "none"


def _dimension_pressure_for_role(role: str, stakeholder_surface: dict[str, Any]) -> dict[str, int]:
    pressure = {dimension: 0 for dimension in _DIMENSION_ORDER}
    records = list(stakeholder_surface.get("real_stakeholders") or []) + list(
        stakeholder_surface.get("inferred_stakeholder_personas") or []
    )
    signal_map = {
        "named_systems": "architecture_system_design",
        "metrics": "business_impact",
        "ownership_scope": "platform_scaling_change",
        "decision_tradeoffs": "architecture_system_design",
        "team_outcomes": "leadership_enablement",
        "product_outcomes": "business_impact",
        "scale_markers": "quality_risk_reliability",
    }
    for record in records:
        if not isinstance(record, dict):
            continue
        record_role = str(record.get("stakeholder_type") or record.get("persona_type") or "").strip()
        if record_role != role:
            continue
        surface = dict(record.get("cv_preference_surface") or {})
        for item in list(surface.get("preferred_evidence_types") or []) + list(surface.get("preferred_signal_order") or []):
            dimension = signal_map.get(str(item).strip().lower())
            if dimension:
                pressure[dimension] += 4
        ai_pref = str(surface.get("ai_section_preference") or "").strip().lower()
        if ai_pref == "dedicated_if_core":
            pressure["ai_ml_depth"] += 3
        elif ai_pref == "discouraged":
            pressure["ai_ml_depth"] -= 2
    return pressure


def _proof_category_dimension_pressure(pain_point_intelligence: dict[str, Any]) -> dict[str, int]:
    pressure = {dimension: 0 for dimension in _DIMENSION_ORDER}
    for item in list(pain_point_intelligence.get("proof_map") or []):
        if not isinstance(item, dict):
            continue
        proof_type = str(item.get("preferred_proof_type") or "").strip().lower()
        dimension = _PROOF_CATEGORY_DIMENSION_MAP.get(proof_type)
        if dimension:
            pressure[dimension] += 4
    return pressure


def _experience_dimension_priors(
    *,
    priors: dict[str, Any],
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
    document_expectations: dict[str, Any],
    cv_shape_expectations: dict[str, Any],
    ideal_candidate: dict[str, Any],
) -> dict[str, Any]:
    role_family = str(priors.get("goal") or "delivery_first")
    overall_priors = _normalized_dimension_weights(_ROLE_FAMILY_WEIGHT_PRIORS.get(role_family, _ROLE_FAMILY_WEIGHT_PRIORS["delivery_first"]))
    ai_cap = _ai_intensity_cap(_ai_intensity(classification))
    architecture_band = _architecture_evidence_band(
        role_family=role_family,
        role_profile=(research.get("role_profile") or {}),
        company_profile=(research.get("company_profile") or {}),
        jd_facts=jd_facts,
    )
    leadership_band = _leadership_evidence_band(jd_facts=jd_facts, stakeholder_surface=stakeholder_surface)
    evaluator_pressure = {
        role: _dimension_pressure_for_role(role, stakeholder_surface)
        for role in list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"])
    }
    proof_pressure = _proof_category_dimension_pressure(pain_point_intelligence)
    must_signal_dimensions = [
        _DIMENSION_SIGNAL_TAG_MAP.get(signal.get("tag"))
        for signal in list(ideal_candidate.get("must_signal") or [])
        if isinstance(signal, dict)
    ]
    return {
        "role_family": role_family,
        "role_family_weight_priors": overall_priors,
        "evaluator_dimension_pressure": evaluator_pressure,
        "proof_category_dimension_pressure": proof_pressure,
        "proof_category_dimension_map": dict(_PROOF_CATEGORY_DIMENSION_MAP),
        "ai_intensity_cap": ai_cap,
        "architecture_evidence_band": architecture_band,
        "leadership_evidence_band": leadership_band,
        "seniority_band": _seniority_band(jd_facts),
        "direct_reports": _leadership_direct_reports(jd_facts),
        "target_roles": list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
        "document_focus_categories": [
            item
            for entry in list(cv_shape_expectations.get("section_emphasis") or [])
            if isinstance(entry, dict)
            for item in list(entry.get("focus_categories") or [])
        ],
        "must_signal_dimensions": [item for item in must_signal_dimensions if item],
        "ideal_de_emphasize_dimensions": [
            _DIMENSION_SIGNAL_TAG_MAP.get(signal.get("tag"))
            for signal in list(ideal_candidate.get("de_emphasize") or [])
            if isinstance(signal, dict) and _DIMENSION_SIGNAL_TAG_MAP.get(signal.get("tag"))
        ],
        "title_strategy": cv_shape_expectations.get("title_strategy"),
        "dimension_enum_version": DIMENSION_ENUM_VERSION,
    }


def _default_experience_dimension_weights(
    *,
    priors: dict[str, Any],
    preflight_summary: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    research: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
) -> dict[str, Any]:
    stakeholder_status = str(stakeholder_surface.get("status") or "unresolved")
    research_status = str(research.get("status") or "unresolved")
    defaults_applied: list[str] = []
    unresolved_markers: list[str] = []
    status = "completed"
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"} or research_status in {"partial", "unresolved"}:
        status = "partial"
        defaults_applied.append("role_family_dimension_weights_default")
        unresolved_markers.append("thin_upstream_dimension_weights")
    overall = _dimension_tail_fill(priors.get("role_family_weight_priors") or {})
    variants: dict[str, dict[str, int] | None] = {}
    for role in priors.get("target_roles") or ["recruiter", "hiring_manager"]:
        variant = _normalized_dimension_weights(overall)
        for dimension, pressure in (priors.get("evaluator_dimension_pressure") or {}).get(role, {}).items():
            variant[dimension] = max(0, variant.get(dimension, 0) + pressure)
        variants[role] = _dimension_tail_fill(variant)
    confidence = {
        "score": 0.78 if status == "completed" else 0.58,
        "band": "high" if status == "completed" else "medium",
        "basis": "Deterministic role-family priors with stakeholder and proof-map pressure.",
    }
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"}:
        confidence["score"] = min(float(confidence["score"]), 0.79)
        confidence["band"] = "medium"
    return {
        "status": "inferred_only" if stakeholder_status in {"inferred_only", "no_research"} else status,
        "source_scope": "jd_plus_research_plus_stakeholder" if stakeholder_status == "completed" else "jd_plus_research",
        "dimension_enum_version": DIMENSION_ENUM_VERSION,
        "overall_weights": overall,
        "stakeholder_variant_weights": variants,
        "minimum_visible_dimensions": [
            dimension
            for dimension, _weight in sorted(overall.items(), key=lambda item: (-item[1], item[0]))[:3]
        ],
        "overuse_risks": [
            {
                "dimension": "leadership_enablement",
                "reason": "seniority_mismatch",
                "threshold": 18,
                "mitigation": "proof_first",
            }
        ],
        "rationale": "Experience-dimension salience defaulted from role-family priors plus available stakeholder and proof-map pressure.",
        "unresolved_markers": unresolved_markers,
        "defaults_applied": defaults_applied,
        "normalization_events": [],
        "confidence": confidence,
        "evidence": [
            {
                "claim": "Default weight priors are grounded in role family, stakeholder coverage, and proof-map pressure.",
                "source_ids": [
                    "classification.primary_role_category",
                    "stakeholder_surface.evaluator_coverage_target",
                    "pain_point_intelligence.proof_map",
                ],
            }
        ],
        "notes": [],
        "debug_context": {
            "input_summary": {
                **preflight_summary,
                "pain_point_intelligence_status": str(pain_point_intelligence.get("status") or "unresolved"),
            },
            "role_family_weight_priors": priors.get("role_family_weight_priors") or {},
            "evaluator_dimension_pressure": priors.get("evaluator_dimension_pressure") or {},
            "ai_intensity_cap": priors.get("ai_intensity_cap"),
            "architecture_evidence_band": priors.get("architecture_evidence_band") or "none",
            "leadership_evidence_band": priors.get("leadership_evidence_band") or "none",
            "defaults_applied": defaults_applied,
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
        "fail_open_reason": "thin_upstream" if defaults_applied else None,
    }


def _validate_experience_dimension_weights(
    payload: dict[str, Any],
    *,
    evaluator_coverage_target: list[str],
    ai_intensity: str,
    priors: dict[str, Any],
    document_expectations: dict[str, Any],
    cv_shape_expectations: dict[str, Any],
    ideal_candidate: dict[str, Any],
    allow_fail_open_rebalance: bool = False,
) -> ExperienceDimensionWeightsDoc:
    working = dict(payload)
    events = list(working.get("normalization_events") or [])
    weights = _normalized_dimension_weights(working.get("overall_weights") or {})

    proof_pressure = dict(priors.get("proof_category_dimension_pressure") or {})
    for dimension, amount in proof_pressure.items():
        if amount:
            weights[dimension] = max(0, weights.get(dimension, 0) + amount)

    for dimension in priors.get("must_signal_dimensions") or []:
        _boost_dimension_floor(
            weights,
            dimension=dimension,
            floor=10,
            reason="must_signal_floor",
            events=events,
        )
    for dimension in priors.get("ideal_de_emphasize_dimensions") or []:
        _soften_dimension_ceiling(
            weights,
            dimension=dimension,
            ceiling=5,
            reason="de_emphasize_ceiling",
            events=events,
        )

    _apply_dimension_cap(
        weights,
        dimension="ai_ml_depth",
        cap=int(priors.get("ai_intensity_cap") or _ai_intensity_cap(ai_intensity)),
        reason=f"ai_intensity_{ai_intensity}",
        events=events,
    )
    architecture_cap = int(
        (_ARCHITECTURE_CAPS.get(str(priors.get("role_family") or "delivery_first"), _ARCHITECTURE_CAPS["delivery_first"])).get(
            str(priors.get("architecture_evidence_band") or "none"),
            18,
        )
    )
    _apply_dimension_cap(
        weights,
        dimension="architecture_system_design",
        cap=architecture_cap,
        reason=f"architecture_evidence_{priors.get('architecture_evidence_band') or 'none'}",
        events=events,
    )
    leadership_cap = _leadership_dimension_cap(
        seniority_band=str(priors.get("seniority_band") or "senior"),
        leadership_evidence_band=str(priors.get("leadership_evidence_band") or "none"),
        direct_reports=int(priors.get("direct_reports") or 0),
    )
    _apply_dimension_cap(
        weights,
        dimension="leadership_enablement",
        cap=leadership_cap,
        reason=f"leadership_band_{priors.get('leadership_evidence_band') or 'none'}",
        events=events,
    )
    weights = _dimension_tail_fill(
        weights,
        skip_add_dimensions={"ai_ml_depth", "architecture_system_design", "leadership_enablement"},
    )
    focus_dimensions = {
        _PROOF_CATEGORY_DIMENSION_MAP[item]
        for entry in list(cv_shape_expectations.get("section_emphasis") or [])
        if isinstance(entry, dict)
        for item in list(entry.get("focus_categories") or [])
        if item in _PROOF_CATEGORY_DIMENSION_MAP
    }
    proof_ladder_dimensions = [
        _PROOF_CATEGORY_DIMENSION_MAP[proof_category]
        for step in list(ideal_candidate.get("proof_ladder") or [])[:2]
        if isinstance(step, dict)
        for proof_category in [str(step.get("proof_category") or "").strip().lower()]
        if proof_category in _PROOF_CATEGORY_DIMENSION_MAP
    ]
    if allow_fail_open_rebalance:
        for dimension in sorted(focus_dimensions):
            _boost_dimension_floor(
                weights,
                dimension=dimension,
                floor=6,
                reason="section_focus_floor",
                events=events,
            )
        for dimension in proof_ladder_dimensions:
            _boost_dimension_floor(
                weights,
                dimension=dimension,
                floor=6,
                reason="proof_ladder_floor",
                events=events,
            )
        weights = _dimension_tail_fill(
            weights,
            skip_add_dimensions={"ai_ml_depth", "architecture_system_design", "leadership_enablement"},
        )

    variants: dict[str, dict[str, int] | None] = {}
    for role, raw_variant in dict(working.get("stakeholder_variant_weights") or {}).items():
        if role not in set(evaluator_coverage_target):
            _record_dimension_event(
                events,
                kind="variant_suppressed",
                from_value=role,
                to_value=None,
                reason="coverage_target_excludes_role",
                path=f"stakeholder_variant_weights.{role}",
            )
            continue
        variant = _normalized_dimension_weights(raw_variant or weights)
        for dimension, pressure in (priors.get("evaluator_dimension_pressure") or {}).get(role, {}).items():
            if pressure:
                variant[dimension] = max(0, variant.get(dimension, 0) + pressure)
        _apply_dimension_cap(
            variant,
            dimension="ai_ml_depth",
            cap=int(priors.get("ai_intensity_cap") or _ai_intensity_cap(ai_intensity)),
            reason=f"ai_intensity_{ai_intensity}",
            events=events,
        )
        _apply_dimension_cap(
            variant,
            dimension="architecture_system_design",
            cap=architecture_cap,
            reason=f"architecture_evidence_{priors.get('architecture_evidence_band') or 'none'}",
            events=events,
        )
        _apply_dimension_cap(
            variant,
            dimension="leadership_enablement",
            cap=leadership_cap,
            reason=f"leadership_band_{priors.get('leadership_evidence_band') or 'none'}",
            events=events,
        )
        variants[role] = _dimension_tail_fill(
            variant,
            skip_add_dimensions={"ai_ml_depth", "architecture_system_design", "leadership_enablement"},
        )

    working["overall_weights"] = weights
    working["stakeholder_variant_weights"] = variants
    if not working.get("minimum_visible_dimensions"):
        working["minimum_visible_dimensions"] = [
            item for item, _weight in sorted(weights.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
        ]
    working["normalization_events"] = events
    if working.get("defaults_applied"):
        confidence = dict(working.get("confidence") or {})
        confidence["band"] = "medium" if str(confidence.get("band") or "").strip().lower() == "high" else (confidence.get("band") or "medium")
        try:
            confidence["score"] = min(float(confidence.get("score") or 0.79), 0.79)
        except Exception:
            confidence["score"] = 0.79
        working["confidence"] = confidence
    doc = ExperienceDimensionWeightsDoc.model_validate(
        working,
        context={"evaluator_coverage_target": evaluator_coverage_target},
    )
    if not allow_fail_open_rebalance:
        for dimension in focus_dimensions:
            if doc.overall_weights.get(dimension, 0) <= 5:
                raise ValueError(f"dimension weights contradict section_emphasis focus category: {dimension}")
        for dimension in proof_ladder_dimensions:
            if doc.overall_weights.get(dimension, 0) <= 5:
                raise ValueError(f"dimension weights contradict proof_ladder top rung: {dimension}")
    return doc


def _mark_dimension_weights_defaults_applied(
    doc: ExperienceDimensionWeightsDoc,
    *,
    default_id: str,
    unresolved_marker: str,
) -> ExperienceDimensionWeightsDoc:
    return doc.model_copy(
        update={
            "status": doc.status if doc.status in {"inferred_only", "failed_terminal"} else "partial",
            "defaults_applied": list(dict.fromkeys([*(doc.defaults_applied or []), default_id])),
            "unresolved_markers": list(dict.fromkeys([*(doc.unresolved_markers or []), unresolved_marker])),
            "confidence": doc.confidence.model_copy(
                update={
                    "band": "medium" if doc.confidence.band == "high" else doc.confidence.band,
                    "score": min(doc.confidence.score, 0.79),
                }
            ),
            "debug_context": doc.debug_context.model_copy(
                update={
                    "defaults_applied": list(dict.fromkeys([*(doc.debug_context.defaults_applied or []), default_id]))
                }
            ),
        }
    )


def _caps_for_sparse_upstream(stakeholder_surface: dict[str, Any], confidence: dict[str, Any]) -> dict[str, Any]:
    status = str(stakeholder_surface.get("status") or "unresolved")
    if status not in {"inferred_only", "no_research", "unresolved"}:
        return confidence
    score = min(float(confidence.get("score") or 0.0), 0.79)
    band = "medium" if score >= 0.5 else "low" if score >= 0.2 else "unresolved"
    return {
        **confidence,
        "score": score,
        "band": band,
    }


def _default_document_expectations(
    *,
    priors: dict[str, Any],
    preflight_summary: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
    ai_intensity: str,
) -> dict[str, Any]:
    stakeholder_status = str(stakeholder_surface.get("status") or "unresolved")
    status = "completed"
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"} or not list(pain_point_intelligence.get("proof_map") or []):
        status = "partial"
    target_roles = list(priors["target_roles"])
    if stakeholder_status in {"no_research", "unresolved"}:
        target_roles = [role for role in target_roles if role in {"recruiter", "hiring_manager"}] or ["recruiter", "hiring_manager"]
    audience_variants = {
        role: {
            "tilt": ["clarity_first", "evidence_first"] if role != "recruiter" else ["clarity_first", "keyword_visible"],
            "must_see": ["role_fit", "ownership_scope"] if role == "recruiter" else ["ownership_scope", "production_impact"],
            "risky_signals": ["tool_list_cv", "generic_mission_restatement"] if role == "recruiter" else ["hype_header", "ai_claims_without_evidence"],
            "rationale": f"{role} lens defaulted from role-family priors because upstream evidence was thin.",
        }
        for role in target_roles
    }
    confidence = _caps_for_sparse_upstream(
        stakeholder_surface,
        {"score": 0.74 if status == "completed" else 0.58, "band": "high" if status == "completed" else "medium", "basis": "Role-family priors plus available evaluator and research signals."},
    )
    return {
        "status": "inferred_only" if stakeholder_status in {"inferred_only", "no_research", "unresolved"} else status,
        "primary_document_goal": priors["goal"],
        "secondary_document_goals": [],
        "audience_variants": audience_variants,
        "proof_order": list(_proof_order_candidates(pain_point_intelligence, priors)),
        "anti_patterns": ["tool_list_cv", "hype_header", "ai_claims_without_evidence"],
        "tone_posture": {
            "primary_tone": "architect_first" if priors["goal"] in {"architecture_first", "platform_first"} else "leader_first" if priors["goal"] == "leadership_first" else "evidence_first",
            "hype_tolerance": "low",
            "narrative_tolerance": "medium",
            "formality": "neutral",
        },
        "density_posture": {
            "overall_density": "high" if priors["goal"] in {"architecture_first", "ai_first", "platform_first"} else "medium",
            "header_density": priors["header_density"],
            "section_density_bias": [{"section_id": "summary", "bias": "medium"}],
        },
        "keyword_balance": {
            "target_keyword_pressure": "high" if priors["ats_pressure"] in {"high", "extreme"} else "medium",
            "ats_mirroring_bias": "aggressive" if priors["ats_pressure"] in {"high", "extreme"} else "balanced",
            "semantic_expansion_bias": "balanced",
        },
        "unresolved_markers": [] if status == "completed" else ["fail_open_role_family_defaults"],
        "rationale": f"Candidate-agnostic thesis defaulted from {priors['goal']} role-family priors with ai_intensity={ai_intensity}.",
        "debug_context": {
            "input_summary": preflight_summary,
            "defaults_applied": ["role_family_document_expectations_default"] if status != "completed" else [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
        "confidence": confidence,
        "evidence": [
            {
                "claim": "Default document thesis is derived from classification, stakeholder surface, and ATS posture priors.",
                "source_ids": ["classification.primary_role_category", "stakeholder_surface.evaluator_coverage_target", "research_enrichment.application_profile.portal_family"],
            }
        ],
    }


def _default_cv_shape_expectations(
    *,
    priors: dict[str, Any],
    preflight_summary: dict[str, Any],
    document_expectations: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    ai_intensity: str,
) -> dict[str, Any]:
    stakeholder_status = str(stakeholder_surface.get("status") or "unresolved")
    status = "completed" if stakeholder_status == "completed" else "partial"
    confidence = _caps_for_sparse_upstream(
        stakeholder_surface,
        {"score": 0.76 if status == "completed" else 0.56, "band": "high" if status == "completed" else "medium", "basis": "Role-family priors plus thesis alignment."},
    )
    section_order = list(priors["section_order"])
    section_emphasis = [
        {
            "section_id": "summary",
            "emphasis": "highlight",
            "focus_categories": document_expectations.get("proof_order", [])[:2] or ["metric", "architecture"],
            "length_bias": "short",
            "ordering_bias": "outcome_first",
            "rationale": "Summary should establish role-fit and proof posture quickly.",
        },
        {
            "section_id": "key_achievements",
            "emphasis": "highlight",
            "focus_categories": document_expectations.get("proof_order", [])[:3] or ["metric", "architecture", "leadership"],
            "length_bias": "medium",
            "ordering_bias": "outcome_first",
            "rationale": "Key achievements carry the condensed proof ladder.",
        },
        {
            "section_id": "experience",
            "emphasis": "highlight",
            "focus_categories": document_expectations.get("proof_order", [])[:4] or ["metric", "architecture", "leadership", "stakeholder"],
            "length_bias": "long",
            "ordering_bias": "outcome_first",
            "rationale": "Experience is the main proof surface for this role class.",
        },
    ]
    if "core_competencies" in section_order:
        section_emphasis.append(
            {
                "section_id": "core_competencies",
                "emphasis": "balanced",
                "focus_categories": ["architecture", "ai"] if ai_intensity in {"core", "significant"} else ["architecture", "metric"],
                "length_bias": "medium",
                "ordering_bias": "tech_first",
                "rationale": "Competencies support ATS parseability without dominating the document.",
            }
        )
    if "ai_highlights" in section_order:
        section_emphasis.append(
            {
                "section_id": "ai_highlights",
                "emphasis": "balanced",
                "focus_categories": ["ai", "metric"],
                "length_bias": "medium",
                "ordering_bias": "outcome_first",
                "rationale": "AI highlights are visible when the AI intensity warrants explicit signaling.",
            }
        )
    return {
        "status": "inferred_only" if stakeholder_status in {"inferred_only", "no_research", "unresolved"} else status,
        "title_strategy": "closest_truthful",
        "header_shape": {
            "density": (((document_expectations.get("density_posture") or {}).get("header_density")) or priors["header_density"]),
            "include_elements": ["name", "current_or_target_title", "links", "proof_line"],
            "proof_line_policy": "required" if priors["header_density"] == "proof_dense" else "optional",
            "differentiator_line_policy": "optional",
        },
        "section_order": section_order,
        "section_emphasis": section_emphasis,
        "ai_section_policy": priors["ai_section_policy"],
        "counts": {
            "key_achievements_min": 3,
            "key_achievements_max": 5,
            "core_competencies_min": 6,
            "core_competencies_max": 10,
            "summary_sentences_min": 2,
            "summary_sentences_max": 4,
        },
        "ats_envelope": {
            "pressure": priors["ats_pressure"],
            "format_rules": priors["format_rules"],
            "keyword_placement_bias": priors["keyword_placement_bias"],
        },
        "evidence_density": "high" if priors["goal"] in {"architecture_first", "ai_first", "platform_first"} else "medium",
        "seniority_signal_strength": "high" if priors["goal"] in {"architecture_first", "leadership_first", "transformation_first"} else "medium",
        "compression_rules": [
            "compress_core_competencies_first",
            "compress_certifications_second",
            "compress_projects_third",
        ],
        "omission_rules": [
            "omit_publications_if_unused_in_role_family",
            "omit_awards_if_unused_in_role_family",
        ] + (["omit_ai_highlights_if_policy_discouraged"] if priors["ai_section_policy"] == "discouraged" else []),
        "unresolved_markers": [] if status == "completed" else ["fail_open_role_family_shape_defaults"],
        "rationale": "Concrete CV shape mirrors the document thesis and conservative ATS posture priors.",
        "debug_context": {
            "input_summary": preflight_summary,
            "defaults_applied": ["role_family_cv_shape_default"] if status != "completed" else [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
        "confidence": confidence,
        "evidence": [
            {
                "claim": "Default CV shape is derived from document thesis, AI intensity, and ATS posture priors.",
                "source_ids": ["document_expectations.primary_document_goal", "classification.ai_taxonomy.intensity", "research_enrichment.application_profile.portal_family"],
            }
        ],
    }


def _ideal_identity_seed(jd_facts: dict[str, Any], priors: dict[str, Any]) -> str:
    ideal_profile = jd_facts.get("ideal_candidate_profile") or {}
    if isinstance(ideal_profile, dict):
        for key in ("identity_statement", "summary"):
            value = _first_text(ideal_profile.get(key))
            if value:
                return value[:120]
        archetype = _first_text(ideal_profile.get("archetype"))
        if archetype:
            return archetype.replace("_", " ")[:120]
    role_family = str(priors.get("role_family") or priors.get("goal") or "delivery_first").replace("_", " ")
    return f"{role_family} operator for role-fit and delivery credibility"[:120]


def _default_ideal_candidate_presentation_model(
    *,
    priors: dict[str, Any],
    preflight_summary: dict[str, Any],
    jd_facts: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
    document_expectations: dict[str, Any],
    cv_shape_expectations: dict[str, Any],
) -> dict[str, Any]:
    stakeholder_status = str(stakeholder_surface.get("status") or "unresolved")
    proof_order = list(document_expectations.get("proof_order") or priors.get("proof_order") or ["metric"])
    title_strategy = str(cv_shape_expectations.get("title_strategy") or "closest_truthful")
    acceptable_titles = list(priors.get("acceptable_titles") or [str(jd_facts.get("title") or "Candidate")])
    must_signal = list(priors.get("must_signal_defaults") or [])
    should_signal = list(priors.get("should_signal_defaults") or [])
    de_emphasize = list(priors.get("de_emphasize_defaults") or [])
    confidence = _caps_for_sparse_upstream(
        stakeholder_surface,
        {
            "score": 0.74 if stakeholder_status == "completed" and pain_point_intelligence.get("status") == "completed" else 0.56,
            "band": "high" if stakeholder_status == "completed" and pain_point_intelligence.get("status") == "completed" else "medium",
            "basis": "Ideal-candidate framing defaulted from upstream role-family, proof-map, and stakeholder priors.",
        },
    )
    status = "completed"
    defaults_applied: list[str] = []
    unresolved_markers: list[str] = []
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"} or not list(pain_point_intelligence.get("proof_map") or []):
        status = "partial"
        defaults_applied = ["role_family_ideal_candidate_default"]
        unresolved_markers = ["fail_open_role_family_ideal_candidate_defaults"]
    stakeholder_preferences = priors.get("stakeholder_signal_biases") or {}
    audience_variants = {}
    for role in list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]):
        must_land = stakeholder_preferences.get(role) or must_signal[:2]
        audience_variants[role] = {
            "tilt": ["clarity_first", "keyword_visible"] if role == "recruiter" else ["evidence_first", "architect_first"],
            "must_land": must_land[:3],
            "de_emphasize": de_emphasize[:2],
            "rationale": f"{role} framing defaulted from stakeholder coverage and role-family priors.",
        }
    proof_ladder = [
        {
            "proof_category": proof_category,
            "signal_tag": _proof_category_to_signal_tag(proof_category),
            "rationale": f"Lead with {proof_category} proof because it is upstream-prioritized for this role.",
            "evidence_refs": [{"source": f"pain_point_intelligence.proof_map:{index + 1}"}],
        }
        for index, proof_category in enumerate(proof_order[:4])
    ]
    credibility_markers = [
        {
            "marker": "named_systems" if item["proof_category"] == "architecture" else "metrics" if item["proof_category"] == "metric" else "ownership_scope",
            "proof_category": item["proof_category"],
            "rationale": item.get("marker") or f"{item['proof_category']} proof should be concrete and recruiter-visible.",
            "evidence_refs": [{"source": f"pain_point_intelligence.proof_map:{index + 1}"}],
        }
        for index, item in enumerate(list(priors.get("proof_markers") or [])[:4])
    ]
    if not credibility_markers:
        credibility_markers = [
            {
                "marker": "ownership_scope",
                "proof_category": proof_ladder[0]["proof_category"] if proof_ladder else "metric",
                "rationale": "Fallback framing should still signal believable ownership scope.",
                "evidence_refs": [{"source": "document_expectations.proof_order"}],
            }
        ]
    risk_flags = [
        {
            "flag": "generic_ai_claim",
            "severity": "high" if "ai" in proof_order else "medium",
            "rationale": "Avoid unsupported AI positioning that outruns the proof ladder.",
            "evidence_refs": [{"source": "classification.ai_taxonomy.intensity"}],
        },
        {
            "flag": "tool_listing_without_proof",
            "severity": "medium",
            "rationale": "Do not let tool lists displace scope and production evidence.",
            "evidence_refs": [{"source": "stakeholder_surface.evaluator_coverage_target"}],
        },
    ]
    return {
        "status": "inferred_only" if stakeholder_status in {"inferred_only", "no_research"} else status,
        "visible_identity": _ideal_identity_seed(jd_facts, priors),
        "acceptable_titles": acceptable_titles,
        "title_strategy": title_strategy,
        "must_signal": [
            {
                "tag": tag,
                "proof_category": proof_order[min(index, len(proof_order) - 1)] if proof_order else None,
                "rationale": f"{tag.replace('_', ' ')} is part of the default framing for this role family.",
                "evidence_refs": [{"source": "jd_facts.merged_view.ideal_candidate_profile"}],
            }
            for index, tag in enumerate(must_signal[:4])
        ],
        "should_signal": [
            {
                "tag": tag,
                "proof_category": proof_order[min(index, len(proof_order) - 1)] if proof_order else None,
                "rationale": f"{tag.replace('_', ' ')} is useful but secondary for this evaluator surface.",
                "evidence_refs": [{"source": "document_expectations.audience_variants"}],
            }
            for index, tag in enumerate(should_signal[:4])
        ],
        "de_emphasize": [
            {
                "tag": tag,
                "proof_category": "process",
                "rationale": f"{tag.replace('_', ' ')} should not outrun stronger proof.",
                "evidence_refs": [{"source": "document_expectations.anti_patterns"}],
            }
            for tag in de_emphasize[:3]
        ],
        "proof_ladder": proof_ladder,
        "tone_profile": _tone_profile_from_document(document_expectations),
        "credibility_markers": credibility_markers,
        "risk_flags": risk_flags,
        "audience_variants": audience_variants,
        "confidence": confidence,
        "defaults_applied": defaults_applied,
        "unresolved_markers": unresolved_markers,
        "evidence_refs": [
            {"source": "jd_facts.merged_view.ideal_candidate_profile"},
            {"source": "pain_point_intelligence.proof_map"},
            {"source": "stakeholder_surface.evaluator_coverage_target"},
        ],
        "debug_context": {
            "input_summary": preflight_summary,
            "defaults_applied": defaults_applied,
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
        },
    }


def _merge_debug_context(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key in ("defaults_applied", "normalization_events", "richer_output_retained", "rejected_output", "retry_events"):
        values = list(merged.get(key) or [])
        values.extend(list((updates or {}).get(key) or []))
        merged[key] = values
    merged["input_summary"] = {**dict(merged.get("input_summary") or {}), **dict((updates or {}).get("input_summary") or {})}
    return merged


def _merge_dimension_debug_context(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key in (
        "defaults_applied",
        "normalization_events",
        "richer_output_retained",
        "rejected_output",
        "retry_events",
    ):
        values = list(merged.get(key) or [])
        values.extend(list((updates or {}).get(key) or []))
        merged[key] = values
    merged["input_summary"] = {**dict(merged.get("input_summary") or {}), **dict((updates or {}).get("input_summary") or {})}
    merged["role_family_weight_priors"] = {
        **dict(merged.get("role_family_weight_priors") or {}),
        **dict((updates or {}).get("role_family_weight_priors") or {}),
    }
    merged["evaluator_dimension_pressure"] = {
        **dict(merged.get("evaluator_dimension_pressure") or {}),
        **dict((updates or {}).get("evaluator_dimension_pressure") or {}),
    }
    for key in ("ai_intensity_cap", "architecture_evidence_band", "leadership_evidence_band"):
        if key in updates and updates.get(key) is not None:
            merged[key] = updates.get(key)
    return merged


def _emphasis_rule_id(topic_family: str, applies_to_kind: str, applies_to: str, condition: str) -> str:
    digest = hashlib.sha1(
        f"{topic_family}|{applies_to_kind}|{applies_to}|{condition.strip().lower()}".encode("utf-8")
    ).hexdigest()[:6]
    topic = topic_family.replace("-", "_")
    target = applies_to.replace("-", "_").replace(":", "_")[:24] or applies_to_kind
    return f"tcer_{topic}_{target}_{digest}"[:64]


def _make_emphasis_rule(
    *,
    topic_family: str,
    rule_type: str,
    applies_to_kind: str,
    applies_to: str,
    condition: str,
    action: str,
    basis: str,
    evidence_refs: list[str],
    precedence: int | None = None,
    cap_value: int | None = None,
    confidence_score: float = 0.72,
    confidence_basis: str,
) -> dict[str, Any]:
    clean_condition = " ".join(condition.strip().split())[:240]
    clean_action = " ".join(action.strip().split())[:240]
    clean_basis = " ".join(basis.strip().split())[:200]
    payload = {
        "rule_id": _emphasis_rule_id(topic_family, applies_to_kind, applies_to, clean_condition),
        "rule_type": rule_type,
        "topic_family": topic_family,
        "applies_to_kind": applies_to_kind,
        "applies_to": applies_to,
        "condition": clean_condition,
        "action": clean_action,
        "basis": clean_basis,
        "evidence_refs": list(dict.fromkeys(evidence_refs)),
        "precedence": precedence if precedence is not None else {
            "allowed_if_evidenced": 20,
            "prefer_softened_form": 50,
            "omit_if_weak": 65,
            "require_credibility_marker": 70,
            "require_proof_for_emphasis": 70,
            "suppress_audience_variant_signal": 75,
            "forbid_without_direct_proof": 80,
            "cap_dimension_weight": 80,
            "never_infer_from_job_only": 85,
        }.get(rule_type, 50),
        "confidence": {
            "score": confidence_score,
            "band": _band(confidence_score),
            "basis": confidence_basis,
        },
    }
    if cap_value is not None:
        payload["cap_value"] = cap_value
    return payload


def _leadership_direct_reports(jd_facts: dict[str, Any]) -> int:
    team_context = jd_facts.get("team_context") or {}
    if isinstance(team_context, dict):
        raw = team_context.get("direct_reports")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
        text = str(raw or "").strip()
        if text.isdigit():
            return int(text)
    return 0


def _bucket_emphasis_rules(rules: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, Any] = {
        "global_rules": [],
        "section_rules": {},
        "allowed_if_evidenced": [],
        "downgrade_rules": [],
        "omit_rules": [],
    }
    for rule in rules:
        rule_type = str(rule.get("rule_type") or "")
        if rule_type == "allowed_if_evidenced":
            buckets["allowed_if_evidenced"].append(rule)
        elif rule_type in {"prefer_softened_form", "suppress_audience_variant_signal"}:
            buckets["downgrade_rules"].append(rule)
        elif rule_type in {"omit_if_weak", "forbid_without_direct_proof", "never_infer_from_job_only"}:
            buckets["omit_rules"].append(rule)
        elif rule.get("applies_to_kind") == "section" and rule_type in {"require_credibility_marker", "require_proof_for_emphasis"}:
            buckets["section_rules"].setdefault(str(rule.get("applies_to")), []).append(rule)
        else:
            buckets["global_rules"].append(rule)
    return buckets


def _clamp_emphasis_rule_confidences(
    rules: list[dict[str, Any]],
    *,
    max_band: str,
    max_score: float,
) -> list[dict[str, Any]]:
    band_rank = {"unresolved": 0, "low": 1, "medium": 2, "high": 3}
    normalized_max_band = str(max_band or "medium").strip().lower() or "medium"
    adjusted: list[dict[str, Any]] = []
    for item in rules:
        rule = dict(item)
        rule_conf = dict(rule.get("confidence") or {})
        rule_band = str(rule_conf.get("band") or _band(float(rule_conf.get("score") or 0.0))).strip().lower()
        if band_rank.get(rule_band, 0) > band_rank.get(normalized_max_band, 0):
            rule_conf["band"] = normalized_max_band
            try:
                rule_conf["score"] = min(float(rule_conf.get("score") or max_score), float(max_score))
            except Exception:
                rule_conf["score"] = float(max_score)
        rule["confidence"] = rule_conf
        adjusted.append(rule)
    return adjusted


def _flatten_emphasis_rule_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rules = list(payload.get("global_rules") or []) + list(payload.get("allowed_if_evidenced") or []) + list(payload.get("downgrade_rules") or []) + list(payload.get("omit_rules") or [])
    for bucket in (payload.get("section_rules") or {}).values():
        rules.extend(list(bucket or []))
    return [dict(rule) for rule in rules if isinstance(rule, dict)]


def _topic_family_counts(rules: list[dict[str, Any]]) -> dict[str, int]:
    counts = {family: 0 for family in _MANDATORY_EMPHASIS_TOPICS}
    for rule in rules:
        family = str(rule.get("topic_family") or "")
        if family in counts:
            counts[family] += 1
    return counts


def _topic_coverage_entries(
    rules: list[dict[str, Any]],
    *,
    defaulted_families: set[str],
    defaulted_all: bool,
) -> list[dict[str, Any]]:
    counts = _topic_family_counts(rules)
    all_families = list(_MANDATORY_EMPHASIS_TOPICS)
    extras = sorted(
        {
            str(rule.get("topic_family") or "")
            for rule in rules
            if str(rule.get("topic_family") or "") and str(rule.get("topic_family") or "") not in all_families
        }
    )
    all_families.extend(extras)
    entries: list[dict[str, Any]] = []
    for family in all_families:
        entries.append(
            {
                "topic_family": family,
                "rule_count": counts.get(family, 0),
                "source": "default" if defaulted_all or family in defaulted_families else "llm",
            }
        )
    return entries


def _merge_emphasis_debug_context(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key in (
        "defaults_applied",
        "normalization_events",
        "richer_output_retained",
        "rejected_output",
        "retry_events",
        "forbidden_claim_pattern_examples",
        "conflict_resolution_log",
    ):
        values = list(merged.get(key) or [])
        values.extend(list((updates or {}).get(key) or []))
        merged[key] = values
    merged["input_summary"] = {**dict(merged.get("input_summary") or {}), **dict((updates or {}).get("input_summary") or {})}
    for key in (
        "role_family_emphasis_rule_priors",
        "title_safety_envelope",
        "ai_claim_envelope",
        "leadership_claim_envelope",
        "architecture_claim_envelope",
    ):
        merged[key] = {**dict(merged.get(key) or {}), **dict((updates or {}).get(key) or {})}
    return merged


def _mark_emphasis_defaults_applied(
    doc: TruthConstrainedEmphasisRulesDoc,
    *,
    default_id: str,
    unresolved_marker: str,
    fail_open_reason: str | None = None,
) -> TruthConstrainedEmphasisRulesDoc:
    payload = doc.model_dump()
    payload["status"] = doc.status if doc.status in {"inferred_only", "failed_terminal"} else "partial"
    payload["defaults_applied"] = list(dict.fromkeys([*(doc.defaults_applied or []), default_id]))
    payload["unresolved_markers"] = list(dict.fromkeys([*(doc.unresolved_markers or []), unresolved_marker]))
    payload["confidence"] = {
        **doc.confidence.model_dump(),
        "band": "medium" if doc.confidence.band == "high" else doc.confidence.band,
        "score": min(doc.confidence.score, 0.79),
    }
    payload["debug_context"] = {
        **doc.debug_context.model_dump(),
        "defaults_applied": list(dict.fromkeys([*(doc.debug_context.defaults_applied or []), default_id])),
    }
    if fail_open_reason:
        payload["fail_open_reason"] = fail_open_reason
    adjusted_rules = _clamp_emphasis_rule_confidences(
        _flatten_emphasis_rule_dicts(payload),
        max_band=str(payload["confidence"]["band"]),
        max_score=float(payload["confidence"]["score"]),
    )
    payload.update(_bucket_emphasis_rules(adjusted_rules))
    return TruthConstrainedEmphasisRulesDoc.model_validate(payload)


def _emphasis_rule_priors(
    *,
    priors: dict[str, Any],
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
    document_expectations: dict[str, Any],
    cv_shape_expectations: dict[str, Any],
    ideal_candidate: dict[str, Any],
    experience_dimension_weights: dict[str, Any],
) -> dict[str, Any]:
    role_family = str(priors.get("goal") or "delivery_first")
    ai_intensity = _ai_intensity(classification)
    ai_cap = int(
        (((experience_dimension_weights.get("debug_context") or {}).get("ai_intensity_cap")) or _ai_intensity_cap(ai_intensity))
    )
    leadership_band = str(
        (((experience_dimension_weights.get("debug_context") or {}).get("leadership_evidence_band")) or _leadership_evidence_band(jd_facts=jd_facts, stakeholder_surface=stakeholder_surface))
    )
    architecture_band = str(
        (((experience_dimension_weights.get("debug_context") or {}).get("architecture_evidence_band")) or _architecture_evidence_band(
            role_family=role_family,
            role_profile=(research.get("role_profile") or {}),
            company_profile=(research.get("company_profile") or {}),
            jd_facts=jd_facts,
        ))
    )
    direct_reports = _leadership_direct_reports(jd_facts)
    seniority = _seniority_band(jd_facts)
    leadership_cap = _leadership_dimension_cap(
        seniority_band=seniority,
        leadership_evidence_band=leadership_band,
        direct_reports=direct_reports,
    )
    section_order = list(cv_shape_expectations.get("section_order") or priors.get("section_order") or ["header", "summary", "experience"])
    proof_order = list(document_expectations.get("proof_order") or priors.get("proof_order") or ["metric", "architecture", "stakeholder"])
    acceptable_titles = list(ideal_candidate.get("acceptable_titles") or _normalized_title_candidates(jd_facts, classification))
    base_refs = ["document_expectations.proof_order", "cv_shape_expectations.title_strategy", "ideal_candidate_presentation_model.acceptable_titles"]
    rules_by_topic: dict[str, list[dict[str, Any]]] = {
        "title_inflation": [
            _make_emphasis_rule(
                topic_family="title_inflation",
                rule_type="forbid_without_direct_proof",
                applies_to_kind="global",
                applies_to="global",
                condition="Requested title exceeds acceptable_titles or title_strategy envelope.",
                action="Do not authorize titles outside acceptable_titles; use closest truthful framing.",
                basis="Title claims must stay within the truthful title envelope.",
                evidence_refs=base_refs,
                confidence_score=0.82,
                confidence_basis="Peer title strategy and acceptable_titles define the safe envelope.",
            )
        ],
        "ai_claims": [
            _make_emphasis_rule(
                topic_family="ai_claims",
                rule_type="forbid_without_direct_proof" if ai_intensity in {"none", "adjacent"} else "allowed_if_evidenced",
                applies_to_kind="section",
                applies_to="summary",
                condition="AI depth is weak, adjacent, or absent in upstream evidence." if ai_intensity in {"none", "adjacent"} else "AI depth is supported but must remain evidence-bound.",
                action="Do not lead the summary with AI depth claims without direct proof." if ai_intensity in {"none", "adjacent"} else "Allow AI depth framing only when direct proof is available and truthful.",
                basis="AI claim policy must track classification intensity and 4.2.5 caps.",
                evidence_refs=["classification.ai_taxonomy.intensity", "experience_dimension_weights.overall_weights.ai_ml_depth"],
                confidence_score=0.78,
                confidence_basis="Classification AI intensity plus dimension-weight cap defines the AI claim envelope.",
            )
        ],
        "leadership_scope": [
            _make_emphasis_rule(
                topic_family="leadership_scope",
                rule_type="cap_dimension_weight",
                applies_to_kind="dimension",
                applies_to="leadership_enablement",
                condition="Leadership scope evidence is limited by seniority or direct-report envelope.",
                action="Cap leadership framing to the evidence band and require direct proof for stronger leadership claims.",
                basis="Leadership claims must not outrun the leadership evidence envelope.",
                evidence_refs=["jd_facts.merged_view.team_context", "experience_dimension_weights.debug_context.leadership_evidence_band"],
                cap_value=leadership_cap,
                confidence_score=0.76,
                confidence_basis="Leadership cap derived from seniority, direct reports, and 4.2.5 leadership band.",
            )
        ],
        "architecture_claims": [
            _make_emphasis_rule(
                topic_family="architecture_claims",
                rule_type="prefer_softened_form" if architecture_band != "strong" else "allowed_if_evidenced",
                applies_to_kind="proof",
                applies_to="architecture",
                condition="Architecture authority is only partially grounded." if architecture_band != "strong" else "Architecture framing is grounded in upstream mandate and proof.",
                action="Use conservative architecture wording unless named-system proof is direct." if architecture_band != "strong" else "Architecture claims are permitted when anchored to direct proof.",
                basis="Architecture claim posture must track the architecture evidence band.",
                evidence_refs=["research_enrichment.role_profile.mandate", "pain_point_intelligence.proof_map"],
                confidence_score=0.74,
                confidence_basis="Role mandate and proof map define the architecture claim band.",
            )
        ],
        "domain_expertise": [
            _make_emphasis_rule(
                topic_family="domain_expertise",
                rule_type="never_infer_from_job_only",
                applies_to_kind="proof",
                applies_to="domain",
                condition="Domain expertise is not directly evidenced beyond the JD context.",
                action="Do not infer deep domain expertise from job fit alone.",
                basis="Domain claims require more than JD-only inference.",
                evidence_refs=["jd_facts.merged_view.qualifications", "research_enrichment.role_profile.summary"],
                confidence_score=0.7,
                confidence_basis="Domain claims need explicit upstream evidence beyond the JD.",
            )
        ],
        "stakeholder_management_claims": [
            _make_emphasis_rule(
                topic_family="stakeholder_management_claims",
                rule_type="prefer_softened_form",
                applies_to_kind="proof",
                applies_to="stakeholder",
                condition="Stakeholder-management evidence is indirect or inferred.",
                action="Use conservative stakeholder-language unless direct cross-functional proof is visible.",
                basis="Stakeholder claims should not outrun the evaluator surface.",
                evidence_refs=["stakeholder_surface.evaluator_coverage_target", "pain_point_intelligence.proof_map"],
                confidence_score=0.7,
                confidence_basis="Stakeholder surface and proof map determine safe stakeholder framing.",
            )
        ],
        "metrics_scale_claims": [
            _make_emphasis_rule(
                topic_family="metrics_scale_claims",
                rule_type="omit_if_weak",
                applies_to_kind="proof",
                applies_to="metric",
                condition="Metric or scale proof is weak, generic, or lacks scope.",
                action="Omit metric-led claims until direct scope and scale proof exists.",
                basis="Fabricated metrics and scale are not permitted.",
                evidence_refs=["pain_point_intelligence.proof_map", "document_expectations.anti_patterns"],
                confidence_score=0.76,
                confidence_basis="Proof-map quality and anti-pattern priors define metric safety.",
            )
        ],
        "credibility_ladder_degradation": [
            _make_emphasis_rule(
                topic_family="credibility_ladder_degradation",
                rule_type="require_credibility_marker",
                applies_to_kind="section",
                applies_to="experience" if "experience" in section_order else "summary",
                condition="Every high-emphasis claim needs at least one credibility marker.",
                action="Require named systems, scoped metrics, or ownership markers before emphasis is increased.",
                basis="Emphasis must degrade gracefully when proof is thin.",
                evidence_refs=["ideal_candidate_presentation_model.credibility_markers", "pain_point_intelligence.proof_map"],
                confidence_score=0.73,
                confidence_basis="Credibility ladder rules are anchored to the proof ladder and evidence map.",
            )
        ],
    }
    if "ai_highlights" in section_order and ai_intensity in {"none", "adjacent"}:
        rules_by_topic["ai_claims"].append(
            _make_emphasis_rule(
                topic_family="ai_claims",
                rule_type="forbid_without_direct_proof",
                applies_to_kind="section",
                applies_to="ai_highlights",
                condition="AI highlights would overstate AI depth for adjacent or non-AI roles.",
                action="Do not surface a dedicated AI highlights section without direct proof.",
                basis="Low-AI roles must fail closed on dedicated AI depth framing.",
                evidence_refs=["classification.ai_taxonomy.intensity", "cv_shape_expectations.ai_section_policy"],
                confidence_score=0.79,
                confidence_basis="AI section policy and intensity define whether a dedicated AI section is safe.",
            )
        )
    reflected_targets = {
        (rule.get("applies_to_kind"), rule.get("applies_to"))
        for rules in rules_by_topic.values()
        for rule in rules
        if isinstance(rule, dict)
    }
    for signal in list(ideal_candidate.get("de_emphasize") or []):
        if not isinstance(signal, dict):
            continue
        proof_category = str(signal.get("proof_category") or "").strip().lower()
        signal_tag = str(signal.get("tag") or "").strip().lower()
        dimension = _DIMENSION_SIGNAL_TAG_MAP.get(signal_tag)
        evidence_refs = [
            "ideal_candidate_presentation_model.de_emphasize",
            "experience_dimension_weights.overall_weights",
        ]
        if proof_category and ("proof", proof_category) not in reflected_targets:
            rules_by_topic["credibility_ladder_degradation"].append(
                _make_emphasis_rule(
                    topic_family="credibility_ladder_degradation",
                    rule_type="prefer_softened_form",
                    applies_to_kind="proof",
                    applies_to=proof_category,
                    condition=f"{signal_tag or proof_category} should stay secondary unless direct proof is strong.",
                    action="Prefer softened wording or omit the claim when supporting proof is thin.",
                    basis="4.2.4 de-emphasize signals must remain visible in claim-policy rules.",
                    evidence_refs=evidence_refs,
                    confidence_score=0.69,
                    confidence_basis="De-emphasize priors should degrade unsupported proof-led framing.",
                )
            )
            reflected_targets.add(("proof", proof_category))
        elif dimension and ("dimension", dimension) not in reflected_targets:
            rules_by_topic["credibility_ladder_degradation"].append(
                _make_emphasis_rule(
                    topic_family="credibility_ladder_degradation",
                    rule_type="prefer_softened_form",
                    applies_to_kind="dimension",
                    applies_to=dimension,
                    condition=f"{signal_tag or dimension} should remain de-emphasized unless direct proof improves.",
                    action="Soften framing and avoid over-indexing on this dimension when evidence is weak.",
                    basis="4.2.4 de-emphasize signals must remain visible in claim-policy rules.",
                    evidence_refs=evidence_refs,
                    confidence_score=0.69,
                    confidence_basis="De-emphasize priors should degrade unsupported dimension-led framing.",
                )
            )
            reflected_targets.add(("dimension", dimension))
    forbidden_patterns = [
        {
            "pattern_id": "buzzword_10x",
            "pattern": "10x",
            "pattern_kind": "substring",
            "reason": "Reject inflated performance language that implies unsupported superiority.",
            "example": "10x engineer",
            "evidence_refs": ["document_expectations.anti_patterns"],
            "confidence": {"score": 0.72, "band": "medium", "basis": "Buzzword-stacking anti-pattern prior."},
        },
        {
            "pattern_id": "visionary_hype",
            "pattern": "(?:strategic\\s+)?visionary",
            "pattern_kind": "regex_safe",
            "reason": "Reject inflated leadership wording without direct proof.",
            "example": "strategic visionary",
            "evidence_refs": ["document_expectations.anti_patterns"],
            "confidence": {"score": 0.7, "band": "medium", "basis": "Leadership-overclaim anti-pattern prior."},
        },
        {
            "pattern_id": "thought_leader",
            "pattern": "thought leader",
            "pattern_kind": "substring",
            "reason": "Reject status language that implies external authority without evidence.",
            "example": "thought leader in AI",
            "evidence_refs": ["document_expectations.anti_patterns"],
            "confidence": {"score": 0.69, "band": "medium", "basis": "External-authority anti-pattern prior."},
        },
    ]
    ladder = [item for item in (proof_order[:3] or ["metric", "architecture", "stakeholder"]) if item]
    fallback_rule_id = rules_by_topic["metrics_scale_claims"][0]["rule_id"]
    ladders = [
        {
            "ladder_id": f"{role_family}_all_ladder",
            "applies_to_audience": "all",
            "ladder": ladder if len(ladder) >= 2 else ["metric", "architecture"],
            "fallback_rule_id": fallback_rule_id,
            "rationale": "Degrade emphasis from strongest proof to safer adjacent proof when evidence is thin.",
            "evidence_refs": ["document_expectations.proof_order", "pain_point_intelligence.proof_map"],
            "confidence": {"score": 0.71, "band": "medium", "basis": "Role-family credibility ladder prior."},
        }
    ]
    return {
        "role_family": role_family,
        "target_roles": list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
        "proof_order": proof_order,
        "section_order": section_order,
        "rules_by_topic": rules_by_topic,
        "forbidden_claim_patterns": forbidden_patterns,
        "credibility_ladder_rules": ladders,
        "title_safety_envelope": {
            "title_strategy": cv_shape_expectations.get("title_strategy") or "closest_truthful",
            "acceptable_titles": acceptable_titles,
        },
        "ai_claim_envelope": {
            "ai_intensity": ai_intensity,
            "ai_section_policy": cv_shape_expectations.get("ai_section_policy"),
            "ai_intensity_cap": ai_cap,
        },
        "leadership_claim_envelope": {
            "seniority": seniority,
            "direct_reports": direct_reports,
            "leadership_evidence_band": leadership_band,
        },
        "architecture_claim_envelope": {
            "architecture_evidence_band": architecture_band,
        },
        "role_family_emphasis_rule_priors": {
            family: [rule["rule_id"] for rule in rules]
            for family, rules in rules_by_topic.items()
        },
    }


def _default_truth_constrained_emphasis_rules(
    *,
    priors: dict[str, Any],
    preflight_summary: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    research: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
) -> dict[str, Any]:
    stakeholder_status = str(stakeholder_surface.get("status") or "unresolved")
    role_profile_status = str(((research.get("role_profile") or {}).get("status")) or research.get("status") or "unresolved")
    proof_map_size = len(list(pain_point_intelligence.get("proof_map") or []))
    status = "completed"
    defaults_applied: list[str] = []
    unresolved_markers: list[str] = []
    fail_open_reason = None
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"}:
        status = "inferred_only" if stakeholder_status in {"inferred_only", "no_research"} else "partial"
        defaults_applied.append("thin_stakeholder_emphasis_defaults")
        unresolved_markers.append("thin_stakeholder_surface")
        fail_open_reason = "thin_stakeholder"
    elif role_profile_status in {"partial", "unresolved"}:
        status = "partial"
        defaults_applied.append("partial_role_profile_emphasis_defaults")
        unresolved_markers.append("partial_role_profile")
        fail_open_reason = "thin_research"
    elif proof_map_size < 3:
        status = "partial"
        defaults_applied.append("thin_proof_map_emphasis_defaults")
        unresolved_markers.append("thin_proof_map")
        fail_open_reason = "thin_pain_point_intelligence"
    all_rules = [rule for rules in priors.get("rules_by_topic", {}).values() for rule in rules]
    buckets = _bucket_emphasis_rules(all_rules)
    confidence = _caps_for_sparse_upstream(
        stakeholder_surface,
        {
            "score": 0.78 if status == "completed" else 0.58,
            "band": "high" if status == "completed" else "medium",
            "basis": "Deterministic emphasis-rule priors built from peer contracts and upstream envelopes.",
        },
    )
    return {
        "status": status,
        "source_scope": "jd_plus_research_plus_stakeholder" if stakeholder_status == "completed" else "jd_plus_research",
        "rule_type_enum_version": RULE_TYPE_ENUM_VERSION,
        "applies_to_enum_version": APPLIES_TO_ENUM_VERSION,
        "global_rules": buckets["global_rules"],
        "section_rules": buckets["section_rules"],
        "allowed_if_evidenced": buckets["allowed_if_evidenced"],
        "downgrade_rules": buckets["downgrade_rules"],
        "omit_rules": buckets["omit_rules"],
        "forbidden_claim_patterns": list(priors.get("forbidden_claim_patterns") or []),
        "credibility_ladder_rules": list(priors.get("credibility_ladder_rules") or []),
        "topic_coverage": _topic_coverage_entries(
            all_rules,
            defaulted_families=set(_MANDATORY_EMPHASIS_TOPICS),
            defaulted_all=True,
        ),
        "rationale": "Truth-constrained emphasis rules defaulted deterministically from peer-owned presentation contracts and evidence envelopes.",
        "unresolved_markers": unresolved_markers,
        "defaults_applied": defaults_applied,
        "normalization_events": [],
        "confidence": confidence,
        "evidence": [
            {
                "claim": "Emphasis rules are bounded by title, AI, leadership, architecture, and proof envelopes from the parent presentation contract.",
                "source_ids": [
                    "document_expectations.proof_order",
                    "cv_shape_expectations.ai_section_policy",
                    "ideal_candidate_presentation_model.acceptable_titles",
                    "experience_dimension_weights.overall_weights",
                ],
            }
        ],
        "notes": ["Rules describe claim policy only, never candidate truth or CV prose."],
        "debug_context": {
            "input_summary": preflight_summary,
            "role_family_emphasis_rule_priors": priors.get("role_family_emphasis_rule_priors") or {},
            "title_safety_envelope": priors.get("title_safety_envelope") or {},
            "ai_claim_envelope": priors.get("ai_claim_envelope") or {},
            "leadership_claim_envelope": priors.get("leadership_claim_envelope") or {},
            "architecture_claim_envelope": priors.get("architecture_claim_envelope") or {},
            "forbidden_claim_pattern_examples": [
                entry.get("example") for entry in list(priors.get("forbidden_claim_patterns") or []) if entry.get("example")
            ],
            "defaults_applied": defaults_applied,
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
            "conflict_resolution_log": [],
        },
        "fail_open_reason": fail_open_reason,
    }


def _validate_truth_constrained_emphasis_rules(
    payload: dict[str, Any],
    *,
    evaluator_coverage_target: list[str],
    stakeholder_status: str,
    ai_intensity: str,
    priors: dict[str, Any],
    document_expectations: dict[str, Any],
    cv_shape_expectations: dict[str, Any],
    ideal_candidate: dict[str, Any],
    experience_dimension_weights: dict[str, Any],
) -> TruthConstrainedEmphasisRulesDoc:
    working = dict(payload)
    debug_context = _merge_emphasis_debug_context(
        {
            "input_summary": {},
            "defaults_applied": [],
            "normalization_events": [],
            "richer_output_retained": [],
            "rejected_output": [],
            "retry_events": [],
            "conflict_resolution_log": [],
            "role_family_emphasis_rule_priors": priors.get("role_family_emphasis_rule_priors") or {},
            "title_safety_envelope": priors.get("title_safety_envelope") or {},
            "ai_claim_envelope": priors.get("ai_claim_envelope") or {},
            "leadership_claim_envelope": priors.get("leadership_claim_envelope") or {},
            "architecture_claim_envelope": priors.get("architecture_claim_envelope") or {},
            "forbidden_claim_pattern_examples": [
                entry.get("example") for entry in list(priors.get("forbidden_claim_patterns") or []) if entry.get("example")
            ],
        },
        working.get("debug_context") or {},
    )
    rules = _flatten_emphasis_rule_dicts(working)
    defaulted_families: set[str] = set()

    if stakeholder_status in {"inferred_only", "no_research", "unresolved"}:
        filtered_rules: list[dict[str, Any]] = []
        for rule in rules:
            if rule.get("applies_to_kind") == "audience_variant":
                debug_context["conflict_resolution_log"] = list(debug_context.get("conflict_resolution_log") or []) + [
                    {
                        "rule_id": rule.get("rule_id"),
                        "topic_family": rule.get("topic_family"),
                        "applies_to_kind": rule.get("applies_to_kind"),
                        "applies_to": rule.get("applies_to"),
                        "conflict_source": "stakeholder_surface",
                        "resolution": "suppressed",
                        "note": "audience-variant rules dropped because stakeholder evidence was thin",
                    }
                ]
                continue
            filtered_rules.append(rule)
        rules = filtered_rules
        working["unresolved_markers"] = list(dict.fromkeys([*list(working.get("unresolved_markers") or []), "thin_stakeholder_surface"]))
        working["defaults_applied"] = list(dict.fromkeys([*list(working.get("defaults_applied") or []), "thin_stakeholder_emphasis_defaults"]))
        working["status"] = "inferred_only" if stakeholder_status in {"inferred_only", "no_research"} else "partial"
        working["fail_open_reason"] = working.get("fail_open_reason") or "thin_stakeholder"

    missing_families = [family for family, count in _topic_family_counts(rules).items() if count < 1]
    for family in missing_families:
        rules.extend(list((priors.get("rules_by_topic") or {}).get(family) or []))
        defaulted_families.add(family)
    if missing_families:
        working["defaults_applied"] = list(dict.fromkeys([*list(working.get("defaults_applied") or []), "mandatory_topic_coverage_default_filled"]))
        working["status"] = "partial" if working.get("status") == "completed" else working.get("status")
        working["fail_open_reason"] = working.get("fail_open_reason") or "mandatory_topic_coverage_default_filled"

    filtered_rules = []
    overuse_dimensions = {
        str(item.get("dimension"))
        for item in list(experience_dimension_weights.get("overuse_risks") or [])
        if isinstance(item, dict) and item.get("dimension")
    }
    for rule in rules:
        suppress_reason = None
        conflict_source = None
        if rule.get("topic_family") == "title_inflation" and rule.get("rule_type") == "allowed_if_evidenced":
            suppress_reason = "title_inflation_detected"
            conflict_source = "title_strategy"
        elif rule.get("topic_family") == "ai_claims" and ai_intensity in {"none", "adjacent"} and rule.get("rule_type") == "allowed_if_evidenced":
            suppress_reason = "ai_authorization_above_intensity"
            conflict_source = "ai_section_policy"
        elif rule.get("topic_family") == "leadership_scope":
            leadership_env = priors.get("leadership_claim_envelope") or {}
            if (
                str(leadership_env.get("seniority") or "").strip().lower() in {"junior", "mid", "senior"}
                and int(leadership_env.get("direct_reports") or 0) <= 0
                and rule.get("rule_type") == "allowed_if_evidenced"
            ):
                suppress_reason = "leadership_authorization_above_envelope"
                conflict_source = "must_signal"
        elif rule.get("rule_type") == "cap_dimension_weight":
            applies_to = str(rule.get("applies_to") or "")
            current_weight = int((experience_dimension_weights.get("overall_weights") or {}).get(applies_to) or 0)
            cap_value = int(rule.get("cap_value") or 0)
            if cap_value < current_weight and applies_to not in overuse_dimensions:
                suppress_reason = "dimension_cap_without_overuse_risk"
                conflict_source = "dimension_weights"
        if suppress_reason and conflict_source:
            debug_context["conflict_resolution_log"] = list(debug_context.get("conflict_resolution_log") or []) + [
                {
                    "rule_id": rule.get("rule_id"),
                    "topic_family": rule.get("topic_family"),
                    "applies_to_kind": rule.get("applies_to_kind"),
                    "applies_to": rule.get("applies_to"),
                    "conflict_source": conflict_source,
                    "resolution": "suppressed",
                    "note": suppress_reason,
                }
            ]
            working["status"] = "partial"
            working["fail_open_reason"] = working.get("fail_open_reason") or suppress_reason
            continue
        filtered_rules.append(rule)
    rules = filtered_rules

    if len(list(working.get("forbidden_claim_patterns") or [])) < 2:
        working["forbidden_claim_patterns"] = list(priors.get("forbidden_claim_patterns") or [])
        working["defaults_applied"] = list(dict.fromkeys([*list(working.get("defaults_applied") or []), "forbidden_pattern_priors_default"]))
        working["status"] = "partial" if working.get("status") == "completed" else working.get("status")
    if not list(working.get("credibility_ladder_rules") or []):
        working["credibility_ladder_rules"] = list(priors.get("credibility_ladder_rules") or [])
        working["defaults_applied"] = list(dict.fromkeys([*list(working.get("defaults_applied") or []), "credibility_ladder_priors_default"]))
        working["status"] = "partial" if working.get("status") == "completed" else working.get("status")

    existing_allowed_targets = {
        str(rule.get("applies_to") or "")
        for rule in rules
        if rule.get("rule_type") == "allowed_if_evidenced" and rule.get("applies_to_kind") == "proof"
    }
    should_signal_proofs = {
        str(signal.get("proof_category") or "").strip().lower()
        for signal in list(ideal_candidate.get("should_signal") or [])
        if isinstance(signal, dict) and signal.get("proof_category")
    }
    for proof_category in sorted(should_signal_proofs):
        if proof_category in existing_allowed_targets:
            continue
        if any(
            rule.get("rule_type") == "omit_if_weak"
            and rule.get("applies_to_kind") == "proof"
            and str(rule.get("applies_to") or "") == proof_category
            for rule in rules
        ):
            rules.append(
                _make_emphasis_rule(
                    topic_family="credibility_ladder_degradation",
                    rule_type="allowed_if_evidenced",
                    applies_to_kind="proof",
                    applies_to=proof_category,
                    condition=f"{proof_category} claims stay optional until direct proof is available.",
                    action="Allow this proof category only when direct evidence is visible and truthful.",
                    basis="Should-signal proof categories need an explicit evidentiary escape hatch.",
                    evidence_refs=[
                        "ideal_candidate_presentation_model.should_signal",
                        "pain_point_intelligence.proof_map",
                    ],
                    confidence_score=0.68,
                    confidence_basis="Should-signal proof categories remain conditional on direct proof.",
                )
            )
            working["defaults_applied"] = list(
                dict.fromkeys([*list(working.get("defaults_applied") or []), "should_signal_companion_default"])
            )
            working["status"] = "partial" if working.get("status") == "completed" else working.get("status")

    buckets = _bucket_emphasis_rules(rules)
    working.update(buckets)
    confidence = dict(working.get("confidence") or {})
    if list(working.get("defaults_applied") or []):
        confidence["band"] = "medium" if str(confidence.get("band") or "").strip().lower() == "high" else (confidence.get("band") or "medium")
        try:
            confidence["score"] = min(float(confidence.get("score") or 0.79), 0.79)
        except Exception:
            confidence["score"] = 0.79
    working["confidence"] = confidence
    adjusted_rules = _clamp_emphasis_rule_confidences(
        _flatten_emphasis_rule_dicts(working),
        max_band=str(confidence.get("band") or "medium"),
        max_score=float(confidence.get("score") or 0.79),
    )
    buckets = _bucket_emphasis_rules(adjusted_rules)
    working.update(buckets)
    working["topic_coverage"] = _topic_coverage_entries(
        adjusted_rules,
        defaulted_families=defaulted_families,
        defaulted_all=False,
    )
    debug_context["defaults_applied"] = list(dict.fromkeys([*list(debug_context.get("defaults_applied") or []), *list(working.get("defaults_applied") or [])]))
    working["debug_context"] = debug_context
    doc = TruthConstrainedEmphasisRulesDoc.model_validate(working)
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"} and doc.confidence.band == "high":
        doc = _mark_emphasis_defaults_applied(
            doc,
            default_id="thin_stakeholder_emphasis_defaults",
            unresolved_marker="thin_stakeholder_surface",
            fail_open_reason="thin_stakeholder",
        )
    return doc


def _apply_emphasis_dimension_caps(
    dimension_weights: ExperienceDimensionWeightsDoc,
    emphasis_rules: TruthConstrainedEmphasisRulesDoc,
    *,
    evaluator_coverage_target: list[str],
) -> tuple[ExperienceDimensionWeightsDoc, TruthConstrainedEmphasisRulesDoc]:
    cap_rules = [
        rule
        for rule in (
            list(emphasis_rules.global_rules)
            + list(emphasis_rules.allowed_if_evidenced)
            + list(emphasis_rules.downgrade_rules)
            + list(emphasis_rules.omit_rules)
            + [item for bucket in emphasis_rules.section_rules.values() for item in bucket]
        )
        if rule.rule_type == "cap_dimension_weight" and rule.cap_value is not None
    ]
    if not cap_rules:
        return dimension_weights, emphasis_rules
    overall = _normalized_dimension_weights(dimension_weights.overall_weights)
    variants = {role: (_normalized_dimension_weights(weights) if isinstance(weights, dict) else None) for role, weights in dimension_weights.stakeholder_variant_weights.items()}
    capped_dimensions: set[str] = set()
    normalization_events = [event.model_dump(by_alias=True) for event in dimension_weights.normalization_events]
    conflict_entries = list(emphasis_rules.debug_context.conflict_resolution_log)
    changed = False
    for rule in cap_rules:
        current = int(overall.get(rule.applies_to, 0))
        if current <= int(rule.cap_value or 0):
            continue
        overall[rule.applies_to] = int(rule.cap_value or 0)
        capped_dimensions.add(rule.applies_to)
        changed = True
        normalization_events.append(
            {
                "kind": "cap_clamp",
                "from": current,
                "to": int(rule.cap_value or 0),
                "reason": f"truth_constrained_emphasis_rules:{rule.rule_id}",
                "path": rule.applies_to,
            }
        )
        conflict_entries.append(
            {
                "rule_id": rule.rule_id,
                "topic_family": rule.topic_family,
                "applies_to_kind": rule.applies_to_kind,
                "applies_to": rule.applies_to,
                "conflict_source": "dimension_weights",
                "resolution": "downgraded",
                "note": f"clamped dimension weight from {current} to {rule.cap_value}",
            }
        )
        for role, weights in variants.items():
            if not isinstance(weights, dict):
                continue
            if int(weights.get(rule.applies_to, 0)) > int(rule.cap_value or 0):
                weights[rule.applies_to] = int(rule.cap_value or 0)
                variants[role] = _dimension_tail_fill(weights, skip_add_dimensions={rule.applies_to})
    if not changed:
        return dimension_weights, emphasis_rules
    overall = _dimension_tail_fill(overall, skip_add_dimensions=capped_dimensions)
    updated_dimension_payload = dimension_weights.model_dump()
    updated_dimension_payload["overall_weights"] = overall
    updated_dimension_payload["stakeholder_variant_weights"] = variants
    updated_dimension_payload["normalization_events"] = normalization_events
    updated_dimension = ExperienceDimensionWeightsDoc.model_validate(
        updated_dimension_payload,
        context={"evaluator_coverage_target": evaluator_coverage_target},
    )
    updated_emphasis_payload = emphasis_rules.model_dump()
    updated_emphasis_payload["debug_context"] = {
        **emphasis_rules.debug_context.model_dump(),
        "conflict_resolution_log": conflict_entries,
    }
    updated_emphasis = TruthConstrainedEmphasisRulesDoc.model_validate(updated_emphasis_payload)
    return updated_dimension, updated_emphasis


def _validate_document_expectations(
    payload: dict[str, Any],
    *,
    evaluator_coverage_target: list[str],
    stakeholder_status: str,
) -> DocumentExpectationsDoc:
    doc = DocumentExpectationsDoc.model_validate(
        payload,
        context={"evaluator_coverage_target": evaluator_coverage_target},
    )
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"} and doc.confidence.band == "high":
        doc.confidence.band = "medium"
        doc.confidence.score = min(doc.confidence.score, 0.79)
    return doc


def _validate_cv_shape_expectations(
    payload: dict[str, Any],
    *,
    ai_intensity: str,
    document_header_density: str,
) -> CvShapeExpectationsDoc:
    return CvShapeExpectationsDoc.model_validate(
        payload,
        context={
            "ai_intensity": ai_intensity,
            "document_header_density": document_header_density,
        },
    )


def _validate_ideal_candidate(
    payload: dict[str, Any],
    *,
    evaluator_coverage_target: list[str],
    expected_title_strategy: str,
    stakeholder_status: str,
) -> IdealCandidatePresentationModelDoc:
    candidate_payload = dict(payload)
    defaults_applied = list(candidate_payload.get("defaults_applied") or [])
    confidence_payload = dict(candidate_payload.get("confidence") or {}) if isinstance(candidate_payload.get("confidence"), dict) else {}
    if defaults_applied:
        candidate_payload["status"] = (
            candidate_payload.get("status")
            if candidate_payload.get("status") in {"inferred_only", "failed_terminal"}
            else "partial"
        )
        score = confidence_payload.get("score")
        try:
            numeric_score = float(score)
        except Exception:
            numeric_score = 0.79
        confidence_payload["band"] = "medium" if str(confidence_payload.get("band") or "").strip().lower() == "high" else (confidence_payload.get("band") or "medium")
        confidence_payload["score"] = min(numeric_score, 0.79)
        candidate_payload["confidence"] = confidence_payload
    doc = IdealCandidatePresentationModelDoc.model_validate(
        candidate_payload,
        context={
            "evaluator_coverage_target": evaluator_coverage_target,
            "expected_title_strategy": expected_title_strategy,
        },
    )
    if stakeholder_status in {"inferred_only", "no_research", "unresolved"} and doc.confidence.band == "high":
        doc.confidence.band = "medium"
        doc.confidence.score = min(doc.confidence.score, 0.79)
    return doc


def _mark_document_defaults_applied(
    doc: DocumentExpectationsDoc,
    *,
    default_id: str,
    unresolved_marker: str,
) -> DocumentExpectationsDoc:
    return doc.model_copy(
        update={
            "status": doc.status if doc.status in {"inferred_only", "failed_terminal"} else "partial",
            "unresolved_markers": list(dict.fromkeys([*(doc.unresolved_markers or []), unresolved_marker])),
            "debug_context": doc.debug_context.model_copy(
                update={
                    "defaults_applied": list(
                        dict.fromkeys([*(doc.debug_context.defaults_applied or []), default_id])
                    )
                }
            ),
        }
    )


def _mark_cv_shape_defaults_applied(
    shape: CvShapeExpectationsDoc,
    *,
    default_id: str,
    unresolved_marker: str,
) -> CvShapeExpectationsDoc:
    return shape.model_copy(
        update={
            "status": shape.status if shape.status in {"inferred_only", "failed_terminal"} else "partial",
            "unresolved_markers": list(dict.fromkeys([*(shape.unresolved_markers or []), unresolved_marker])),
            "debug_context": shape.debug_context.model_copy(
                update={
                    "defaults_applied": list(
                        dict.fromkeys([*(shape.debug_context.defaults_applied or []), default_id])
                    )
                }
            ),
        }
    )


def _mark_ideal_candidate_defaults_applied(
    doc: IdealCandidatePresentationModelDoc,
    *,
    default_id: str,
    unresolved_marker: str,
) -> IdealCandidatePresentationModelDoc:
    return doc.model_copy(
        update={
            "status": doc.status if doc.status in {"inferred_only", "failed_terminal"} else "partial",
            "defaults_applied": list(dict.fromkeys([*(doc.defaults_applied or []), default_id])),
            "unresolved_markers": list(dict.fromkeys([*(doc.unresolved_markers or []), unresolved_marker])),
            "confidence": doc.confidence.model_copy(
                update={
                    "band": "medium" if doc.confidence.band == "high" else doc.confidence.band,
                    "score": min(doc.confidence.score, 0.79),
                }
            ),
            "debug_context": doc.debug_context.model_copy(
                update={
                    "defaults_applied": list(
                        dict.fromkeys([*(doc.debug_context.defaults_applied or []), default_id])
                    )
                }
            ),
        }
    )


def _emphasis_rule_records(doc: TruthConstrainedEmphasisRulesDoc) -> list[dict[str, Any]]:
    return _flatten_emphasis_rule_dicts(doc.model_dump(by_alias=True))


def _de_emphasize_reflection_missing_count(
    *,
    ideal_candidate: IdealCandidatePresentationModelDoc,
    emphasis_rules: TruthConstrainedEmphasisRulesDoc,
) -> int:
    rules = _emphasis_rule_records(emphasis_rules)
    missing = 0
    for signal in ideal_candidate.de_emphasize:
        reflected = any(
            rule.get("rule_type") in {"prefer_softened_form", "omit_if_weak"}
            and (
                (signal.proof_category and rule.get("applies_to_kind") == "proof" and rule.get("applies_to") == signal.proof_category)
                or (
                    _DIMENSION_SIGNAL_TAG_MAP.get(signal.tag)
                    and rule.get("applies_to_kind") == "dimension"
                    and rule.get("applies_to") == _DIMENSION_SIGNAL_TAG_MAP.get(signal.tag)
                )
            )
            for rule in rules
        )
        if not reflected:
            missing += 1
    return missing


def _dimension_caps_honored(
    *,
    dimension_weights: ExperienceDimensionWeightsDoc,
    emphasis_rules: TruthConstrainedEmphasisRulesDoc,
) -> bool:
    for rule in _emphasis_rule_records(emphasis_rules):
        if rule.get("rule_type") != "cap_dimension_weight":
            continue
        cap_value = rule.get("cap_value")
        applies_to = str(rule.get("applies_to") or "")
        if cap_value is None or not applies_to:
            continue
        if int(dimension_weights.overall_weights.get(applies_to, 0)) > int(cap_value):
            return False
        for variant in dimension_weights.stakeholder_variant_weights.values():
            if isinstance(variant, dict) and int(variant.get(applies_to, 0)) > int(cap_value):
                return False
    return True


def _forbidden_pattern_proof_order_safe(
    *,
    document_expectations: DocumentExpectationsDoc,
    emphasis_rules: TruthConstrainedEmphasisRulesDoc,
) -> bool:
    top_proofs = [item for item in document_expectations.proof_order[:2] if item]
    for pattern in emphasis_rules.forbidden_claim_patterns:
        lowered = pattern.pattern.lower()
        if any(proof in lowered for proof in top_proofs):
            return False
    return True


def _emit_emphasis_consistency_events(ctx: StageContext, emphasis_rules: TruthConstrainedEmphasisRulesDoc) -> None:
    source_map = {
        "title_strategy": "cv_shape_expectations",
        "ai_section_policy": "cv_shape_expectations",
        "must_signal": "ideal_candidate",
        "dimension_weights": "dimension_weights",
    }
    for entry in emphasis_rules.debug_context.conflict_resolution_log:
        conflict_source = source_map.get(entry.conflict_source)
        if not conflict_source:
            continue
        ctx.tracer.record_event(
            "scout.preenrich.presentation_contract.consistency.emphasis_rules",
            {
                "job_id": _job_id(ctx),
                "stage_name": ctx.stage_name or "presentation_contract",
                "conflict_source": conflict_source,
                "rule_id": entry.rule_id,
                "topic_family": entry.topic_family,
                "applies_to_kind": entry.applies_to_kind,
                "applies_to": entry.applies_to,
                "resolution": entry.resolution,
            },
        )


def _build_emphasis_trace_output(
    *,
    emphasis_rules: TruthConstrainedEmphasisRulesDoc,
    document_expectations: DocumentExpectationsDoc,
    cv_shape_expectations: CvShapeExpectationsDoc,
    ideal_candidate: IdealCandidatePresentationModelDoc,
    dimension_weights: ExperienceDimensionWeightsDoc,
    prompt_metadata_entry: PromptMetadata | None,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research: dict[str, Any],
    stakeholder_surface: dict[str, Any],
    pain_point_intelligence: dict[str, Any],
    llm_call_schema_valid: bool,
    cross_validator_violations: list[str],
) -> dict[str, Any]:
    compact = build_truth_constrained_emphasis_rules_compact(emphasis_rules)
    coverage_map = dict(compact.get("topic_coverage") or {})
    missing_families = [
        family for family in _MANDATORY_EMPHASIS_TOPICS if int(coverage_map.get(family) or 0) < 1
    ]
    normalization_events = list(emphasis_rules.normalization_events or [])
    rejected_output = list(emphasis_rules.debug_context.rejected_output or [])
    candidate_leakage_detected = any(
        "candidate_leakage" in str(item.reason or "")
        for item in rejected_output
    ) or any(
        event.kind in {"candidate_leakage", "candidate_leakage_detected"}
        for event in normalization_events
    )
    return {
        "status": emphasis_rules.status,
        "source_scope": emphasis_rules.source_scope,
        "rule_type_enum_version": emphasis_rules.rule_type_enum_version,
        "applies_to_enum_version": emphasis_rules.applies_to_enum_version,
        "prompt_version": prompt_metadata_entry.prompt_version if prompt_metadata_entry else emphasis_rules.prompt_version,
        "prompt_git_sha": prompt_metadata_entry.git_sha if prompt_metadata_entry else None,
        "global_rules_count": compact.get("global_rules_count"),
        "section_rule_count": compact.get("section_rule_count"),
        "section_rule_coverage_section_ids": compact.get("section_rule_coverage_section_ids"),
        "allowed_if_evidenced_count": compact.get("allowed_if_evidenced_count"),
        "downgrade_rules_count": compact.get("downgrade_rules_count"),
        "omit_rules_count": compact.get("omit_rules_count"),
        "forbidden_claim_patterns_count": compact.get("forbidden_claim_patterns_count"),
        "credibility_ladder_rules_count": compact.get("credibility_ladder_rules_count"),
        "rule_topic_coverage_count": len(
            [family for family in _MANDATORY_EMPHASIS_TOPICS if int(coverage_map.get(family) or 0) >= 1]
        ),
        "mandatory_topic_families_missing": missing_families,
        "title_strategy_conflict_count": compact.get("title_strategy_conflict_count"),
        "ai_section_policy_conflict_count": compact.get("ai_section_policy_conflict_count"),
        "dimension_weight_conflict_count": compact.get("dimension_weight_conflict_count"),
        "must_signal_contradiction_count": compact.get("must_signal_contradiction_count"),
        "de_emphasize_reflection_missing_count": _de_emphasize_reflection_missing_count(
            ideal_candidate=ideal_candidate,
            emphasis_rules=emphasis_rules,
        ),
        "normalization_events_count": len(normalization_events),
        "defaults_applied_count": compact.get("defaults_applied_count"),
        "rejected_output_count": len(rejected_output),
        "cross_validator_violations_count": len(cross_validator_violations),
        "duplicate_rules_collapsed_count": sum(
            1 for event in normalization_events if event.kind == "duplicate_collapsed"
        ),
        "confidence.band": emphasis_rules.confidence.band,
        "confidence.score": emphasis_rules.confidence.score,
        "jd_facts_available": bool(jd_facts),
        "classification_available": bool(classification),
        "research_enrichment_available": bool(research),
        "stakeholder_surface_available": bool(stakeholder_surface),
        "pain_point_intelligence_available": bool(pain_point_intelligence),
        "peer_document_expectations_available": bool(document_expectations.model_dump()),
        "peer_cv_shape_expectations_available": bool(cv_shape_expectations.model_dump()),
        "peer_ideal_candidate_available": bool(ideal_candidate.model_dump()),
        "peer_dimension_weights_available": bool(dimension_weights.model_dump()),
        "llm_call_schema_valid": llm_call_schema_valid,
        "fail_open_reason": (
            emphasis_rules.fail_open_reason
            if emphasis_rules.status in {"partial", "inferred_only", "unresolved", "failed_terminal"}
            else None
        ),
        "title_strategy_matches_peer": compact.get("title_strategy_conflict_count", 0) == 0
        and str((emphasis_rules.debug_context.title_safety_envelope or {}).get("title_strategy") or "")
        == cv_shape_expectations.title_strategy,
        "ai_section_policy_consistent": compact.get("ai_section_policy_conflict_count", 0) == 0,
        "dimension_caps_honored": _dimension_caps_honored(
            dimension_weights=dimension_weights,
            emphasis_rules=emphasis_rules,
        ),
        "mandatory_topic_coverage_complete": not missing_families,
        "candidate_leakage_detected": candidate_leakage_detected,
        "forbidden_pattern_proof_order_safe": _forbidden_pattern_proof_order_safe(
            document_expectations=document_expectations,
            emphasis_rules=emphasis_rules,
        ),
    }


def _extract_subpayload(raw: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    candidate = raw.get(key)
    return dict(candidate) if isinstance(candidate, dict) else dict(raw)


def _repair_prompt(prompt: str, reason: str) -> str:
    return "\n".join(
        [
            prompt,
            "",
            "Schema repair retry:",
            f"- Previous output failed deterministic validation: {reason}",
            "- Keep the same semantic intent.",
            "- Do not add candidate-specific details.",
            "- Use only canonical enums and canonical field names.",
            "- Return valid JSON only.",
        ]
    )


class PresentationContractStage:
    name: str = "presentation_contract"
    dependencies: List[str] = ["jd_facts", "classification", "research_enrichment", "stakeholder_surface", "pain_point_intelligence"]

    def _invoke_prompt(self, *, ctx: StageContext, prompt: str, substage: str, job_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        payload, attempt = _invoke_codex_json_traced(
            prompt=prompt,
            model=ctx.config.primary_model or "gpt-5.4",
            job_id=job_id,
            tracer=ctx.tracer,
            stage_name=ctx.stage_name or self.name,
            substage=substage,
            codex_cwd=ctx.config.codex_workdir,
            reasoning_effort=ctx.config.reasoning_effort,
        )
        return payload, attempt

    def run(self, ctx: StageContext) -> StageResult:
        outputs = ((ctx.job_doc.get("pre_enrichment") or {}).get("outputs") or {})
        jd_facts = (outputs.get("jd_facts") or {}).get("merged_view") or {}
        classification = outputs.get("classification") or {}
        research = outputs.get("research_enrichment") or {}
        stakeholder_surface = outputs.get("stakeholder_surface") or {}
        pain_point_intelligence = outputs.get("pain_point_intelligence") or {}
        job_inference = outputs.get("job_inference") or {}
        company_profile = research.get("company_profile") or {}
        role_profile = research.get("role_profile") or {}
        application_profile = research.get("application_profile") or outputs.get("application_surface") or {}
        jd_excerpt = _jd_excerpt(ctx)

        preflight_span = ctx.tracer.start_substage_span(
            ctx.stage_name or self.name,
            "preflight",
            {"job_id": _job_id(ctx), "stage_name": ctx.stage_name or self.name},
        )
        priors = _role_thesis_priors(
            classification=classification,
            jd_facts=jd_facts,
            stakeholder_surface=stakeholder_surface,
            application_profile=application_profile,
        )
        preflight = {
            "role_thesis_priors": priors,
            "evaluator_axis_summary": _evaluator_axis_summary(stakeholder_surface),
            "proof_order_candidates": _proof_order_candidates(pain_point_intelligence, priors),
            "ats_envelope_profile": {
                "pressure": priors["ats_pressure"],
                "keyword_placement_bias": priors["keyword_placement_bias"],
                "format_rules": priors["format_rules"],
            },
        }
        preflight_summary = {
            "role_family": str(classification.get("primary_role_category") or "unknown"),
            "seniority": str(jd_facts.get("seniority_level") or "unknown"),
            "ai_intensity": _ai_intensity(classification),
            "evaluator_roles_in_scope": list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
            "proof_category_frequencies": _proof_category_frequencies(pain_point_intelligence, priors),
            "top_keywords_top10": list(jd_facts.get("top_keywords") or [])[:10],
            "company_identity_band": str(((company_profile.get("identity_confidence") or {}).get("band")) or "unresolved"),
            "research_status": str(research.get("status") or "unresolved"),
            "stakeholder_surface_status": str(stakeholder_surface.get("status") or "unresolved"),
        }
        ctx.tracer.end_span(preflight_span, output={"status": "completed", "target_roles": len(preflight_summary["evaluator_roles_in_scope"])})

        stakeholder_status = str(stakeholder_surface.get("status") or "unresolved")
        ai_intensity = _ai_intensity(classification)
        allowed_company_names = [str(company_profile.get("canonical_name") or ctx.job_doc.get("company") or "").strip()]
        allowed_company_domain = str(company_profile.get("canonical_domain") or "").strip() or None

        default_document = _default_document_expectations(
            priors=priors,
            preflight_summary=preflight_summary,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            ai_intensity=ai_intensity,
        )
        default_shape = _default_cv_shape_expectations(
            priors=priors,
            preflight_summary=preflight_summary,
            document_expectations=default_document,
            stakeholder_surface=stakeholder_surface,
            ai_intensity=ai_intensity,
        )

        prompt_metadata: dict[str, PromptMetadata] = {}
        raw_debug: dict[str, Any] = {
            "preflight": preflight,
            "raw_outputs": {},
        }
        unresolved_questions: list[str] = []
        document_defaulted = False
        cv_shape_defaulted = False
        ideal_candidate_defaulted = False
        dimension_weights_defaulted = False
        notes: list[str] = [
            "presentation_contract now ships 4.2.2 document/shape, 4.2.4 ideal-candidate framing, 4.2.5 experience-dimension weights, and 4.2.6 truth-constrained emphasis rules.",
        ]

        document_payload = dict(default_document)
        shape_payload = dict(default_shape)
        ideal_candidate_priors = _ideal_candidate_priors(
            priors=priors,
            jd_facts=jd_facts,
            classification=classification,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=default_document,
            cv_shape_expectations=default_shape,
        )
        default_ideal_candidate = _default_ideal_candidate_presentation_model(
            priors=ideal_candidate_priors,
            preflight_summary=preflight_summary,
            jd_facts=jd_facts,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=default_document,
            cv_shape_expectations=default_shape,
        )
        ideal_candidate_payload = dict(default_ideal_candidate)
        dimension_weight_priors = _experience_dimension_priors(
            priors=priors,
            jd_facts=jd_facts,
            classification=classification,
            research=research,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=default_document,
            cv_shape_expectations=default_shape,
            ideal_candidate=default_ideal_candidate,
        )
        default_dimension_weights = _default_experience_dimension_weights(
            priors=dimension_weight_priors,
            preflight_summary=preflight_summary,
            stakeholder_surface=stakeholder_surface,
            research=research,
            pain_point_intelligence=pain_point_intelligence,
        )
        dimension_weights_payload = dict(default_dimension_weights)
        dimension_weights_from_merged = False
        bootstrap_emphasis_priors = _emphasis_rule_priors(
            priors=priors,
            jd_facts=jd_facts,
            classification=classification,
            research=research,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=default_document,
            cv_shape_expectations=default_shape,
            ideal_candidate=default_ideal_candidate,
            experience_dimension_weights=default_dimension_weights,
        )
        default_emphasis_rules = _default_truth_constrained_emphasis_rules(
            priors=bootstrap_emphasis_priors,
            preflight_summary=preflight_summary,
            stakeholder_surface=stakeholder_surface,
            research=research,
            pain_point_intelligence=pain_point_intelligence,
        )
        emphasis_rules_payload = dict(default_emphasis_rules)
        emphasis_rules_from_merged = False

        if presentation_contract_merged_prompt_enabled():
            prompt_metadata["document_and_cv_shape"] = _prompt_metadata(prompt_id="document_and_cv_shape", ctx=ctx)
            merged_prompt = build_p_document_and_cv_shape(
                preflight=preflight,
                experience_dimension_priors=dimension_weight_priors,
                emphasis_rule_priors=bootstrap_emphasis_priors if presentation_contract_emphasis_rules_enabled() else None,
                jd_excerpt=jd_excerpt,
                classification_excerpt={"primary_role_category": classification.get("primary_role_category"), "tone_family": classification.get("tone_family"), "ai_taxonomy": classification.get("ai_taxonomy") or {}},
                research_excerpt={"company_profile": company_profile, "role_profile": role_profile, "application_profile": application_profile},
                stakeholder_surface_excerpt={"status": stakeholder_status, "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [], "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or []},
                pain_point_excerpt={"status": pain_point_intelligence.get("status"), "proof_map": pain_point_intelligence.get("proof_map") or []},
                job_inference_excerpt=(job_inference.get("semantic_role_model") or {}),
            )
            merged_raw, _ = self._invoke_prompt(
                ctx=ctx,
                prompt=merged_prompt,
                substage="document_and_cv_shape",
                job_id=f"{_job_id(ctx)}:presentation_contract:merged",
            )
            raw_debug["raw_outputs"]["document_and_cv_shape"] = merged_raw
            if isinstance(merged_raw, dict):
                document_payload = _extract_subpayload(merged_raw, "document_expectations") or document_payload
                shape_payload = _extract_subpayload(merged_raw, "cv_shape_expectations") or shape_payload
                if presentation_contract_dimension_weights_enabled():
                    dimension_weights_payload = (
                        _extract_subpayload(merged_raw, "experience_dimension_weights")
                        or dimension_weights_payload
                    )
                    if isinstance(merged_raw.get("experience_dimension_weights"), dict):
                        dimension_weights_from_merged = True
                        prompt_metadata["experience_dimension_weights"] = prompt_metadata[
                            "document_and_cv_shape"
                        ].model_copy(update={"prompt_id": "experience_dimension_weights"})
                if presentation_contract_emphasis_rules_enabled():
                    emphasis_rules_payload = (
                        _extract_subpayload(merged_raw, "truth_constrained_emphasis_rules")
                        or emphasis_rules_payload
                    )
                    if isinstance(merged_raw.get("truth_constrained_emphasis_rules"), dict):
                        emphasis_rules_from_merged = True
                        prompt_metadata["emphasis_rules"] = prompt_metadata[
                            "document_and_cv_shape"
                        ].model_copy(update={"prompt_id": "emphasis_rules"})

        if presentation_contract_document_expectations_enabled() and not presentation_contract_merged_prompt_enabled():
            prompt_metadata["document_expectations"] = _prompt_metadata(prompt_id="document_expectations", ctx=ctx)
            doc_prompt = build_p_document_expectations(
                preflight=preflight,
                jd_excerpt=jd_excerpt,
                classification_excerpt={"primary_role_category": classification.get("primary_role_category"), "tone_family": classification.get("tone_family"), "ai_taxonomy": classification.get("ai_taxonomy") or {}},
                research_excerpt={"company_profile": company_profile, "role_profile": role_profile, "application_profile": application_profile},
                stakeholder_surface_excerpt={"status": stakeholder_status, "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [], "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or []},
                pain_point_excerpt={"status": pain_point_intelligence.get("status"), "proof_map": pain_point_intelligence.get("proof_map") or []},
                job_inference_excerpt=(job_inference.get("semantic_role_model") or {}),
            )
            raw_doc, _ = self._invoke_prompt(
                ctx=ctx,
                prompt=doc_prompt,
                substage="document_expectations",
                job_id=f"{_job_id(ctx)}:presentation_contract:document_expectations",
            )
            raw_debug["raw_outputs"]["document_expectations"] = raw_doc
            if isinstance(raw_doc, dict):
                document_payload = _extract_subpayload(raw_doc, "document_expectations")

        normalized_document = normalize_document_expectations_payload(
            document_payload,
            evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
            allowed_company_names=allowed_company_names,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
        )
        normalized_document["debug_context"] = _merge_debug_context(
            default_document.get("debug_context") or {},
            normalized_document.get("debug_context") or {},
        )
        normalized_document["debug_context"]["input_summary"] = preflight_summary

        try:
            document_expectations = _validate_document_expectations(
                normalized_document,
                evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                stakeholder_status=stakeholder_status,
            )
        except Exception as exc:
            normalized_document["debug_context"]["retry_events"] = list(normalized_document["debug_context"].get("retry_events") or []) + [
                {"repair_reason": str(exc), "repair_attempt": 1}
            ]
            if presentation_contract_document_expectations_enabled() and not presentation_contract_merged_prompt_enabled():
                repair_prompt = _repair_prompt(doc_prompt, str(exc))
                repaired_doc, _ = self._invoke_prompt(
                    ctx=ctx,
                    prompt=repair_prompt,
                    substage="schema_repair",
                    job_id=f"{_job_id(ctx)}:presentation_contract:document_expectations:repair",
                )
                raw_debug["raw_outputs"]["document_expectations_repair"] = repaired_doc
                if isinstance(repaired_doc, dict):
                    normalized_document = normalize_document_expectations_payload(
                        _extract_subpayload(repaired_doc, "document_expectations"),
                        evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                        allowed_company_names=allowed_company_names,
                        allowed_company_domain=allowed_company_domain,
                        jd_excerpt=jd_excerpt,
                    )
                    normalized_document["debug_context"] = _merge_debug_context(default_document.get("debug_context") or {}, normalized_document.get("debug_context") or {})
                    normalized_document["debug_context"]["input_summary"] = preflight_summary
                    normalized_document["debug_context"]["retry_events"] = [{"repair_reason": str(exc), "repair_attempt": 1}]
                    try:
                        document_expectations = _validate_document_expectations(
                            normalized_document,
                            evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                            stakeholder_status=stakeholder_status,
                        )
                    except Exception as repair_exc:
                        notes.append(f"document_expectations fell back to role-family defaults after schema repair failed: {repair_exc}")
                        document_defaulted = True
                        document_expectations = _validate_document_expectations(
                            default_document,
                            evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                            stakeholder_status=stakeholder_status,
                        )
                else:
                    notes.append(f"document_expectations fell back to role-family defaults after schema repair returned no payload: {exc}")
                    document_defaulted = True
                    document_expectations = _validate_document_expectations(
                        default_document,
                        evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                        stakeholder_status=stakeholder_status,
                    )
            else:
                notes.append(f"document_expectations defaulted because deterministic validation failed: {exc}")
                document_defaulted = True
                document_expectations = _validate_document_expectations(
                    default_document,
                    evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                    stakeholder_status=stakeholder_status,
                )
        if document_defaulted:
            document_expectations = _mark_document_defaults_applied(
                document_expectations,
                default_id="role_family_document_expectations_default",
                unresolved_marker="schema_defaulted_document_expectations",
            )

        if presentation_contract_cv_shape_expectations_enabled() and not presentation_contract_merged_prompt_enabled():
            prompt_metadata["cv_shape_expectations"] = _prompt_metadata(prompt_id="cv_shape_expectations", ctx=ctx)
            shape_prompt = build_p_cv_shape_expectations(
                preflight=preflight,
                document_expectations=document_expectations.model_dump(),
                classification_excerpt={"primary_role_category": classification.get("primary_role_category"), "tone_family": classification.get("tone_family"), "ai_taxonomy": classification.get("ai_taxonomy") or {}},
                stakeholder_surface_excerpt={"status": stakeholder_status, "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [], "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or []},
                pain_point_excerpt={"status": pain_point_intelligence.get("status"), "proof_map": pain_point_intelligence.get("proof_map") or []},
            )
            raw_shape, _ = self._invoke_prompt(
                ctx=ctx,
                prompt=shape_prompt,
                substage="cv_shape_expectations",
                job_id=f"{_job_id(ctx)}:presentation_contract:cv_shape_expectations",
            )
            raw_debug["raw_outputs"]["cv_shape_expectations"] = raw_shape
            if isinstance(raw_shape, dict):
                shape_payload = _extract_subpayload(raw_shape, "cv_shape_expectations")

        normalized_shape = normalize_cv_shape_expectations_payload(
            shape_payload,
            allowed_company_names=allowed_company_names,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
        )
        normalized_shape["header_shape"] = {
            **dict(normalized_shape.get("header_shape") or {}),
            "density": (((normalized_shape.get("header_shape") or {}).get("density")) or document_expectations.density_posture.header_density),
        }
        normalized_shape["debug_context"] = _merge_debug_context(
            default_shape.get("debug_context") or {},
            normalized_shape.get("debug_context") or {},
        )
        normalized_shape["debug_context"]["input_summary"] = preflight_summary

        try:
            cv_shape_expectations = _validate_cv_shape_expectations(
                normalized_shape,
                ai_intensity=ai_intensity,
                document_header_density=document_expectations.density_posture.header_density,
            )
        except Exception as exc:
            normalized_shape["debug_context"]["retry_events"] = list(normalized_shape["debug_context"].get("retry_events") or []) + [
                {"repair_reason": str(exc), "repair_attempt": 1}
            ]
            if presentation_contract_cv_shape_expectations_enabled() and not presentation_contract_merged_prompt_enabled():
                repair_prompt = _repair_prompt(shape_prompt, str(exc))
                repaired_shape, _ = self._invoke_prompt(
                    ctx=ctx,
                    prompt=repair_prompt,
                    substage="schema_repair",
                    job_id=f"{_job_id(ctx)}:presentation_contract:cv_shape_expectations:repair",
                )
                raw_debug["raw_outputs"]["cv_shape_expectations_repair"] = repaired_shape
                if isinstance(repaired_shape, dict):
                    normalized_shape = normalize_cv_shape_expectations_payload(
                        _extract_subpayload(repaired_shape, "cv_shape_expectations"),
                        allowed_company_names=allowed_company_names,
                        allowed_company_domain=allowed_company_domain,
                        jd_excerpt=jd_excerpt,
                    )
                    normalized_shape["header_shape"] = {
                        **dict(normalized_shape.get("header_shape") or {}),
                        "density": (((normalized_shape.get("header_shape") or {}).get("density")) or document_expectations.density_posture.header_density),
                    }
                    normalized_shape["debug_context"] = _merge_debug_context(default_shape.get("debug_context") or {}, normalized_shape.get("debug_context") or {})
                    normalized_shape["debug_context"]["input_summary"] = preflight_summary
                    normalized_shape["debug_context"]["retry_events"] = [{"repair_reason": str(exc), "repair_attempt": 1}]
                    try:
                        cv_shape_expectations = _validate_cv_shape_expectations(
                            normalized_shape,
                            ai_intensity=ai_intensity,
                            document_header_density=document_expectations.density_posture.header_density,
                        )
                    except Exception as repair_exc:
                        notes.append(f"cv_shape_expectations fell back to role-family defaults after schema repair failed: {repair_exc}")
                        cv_shape_defaulted = True
                        cv_shape_expectations = _validate_cv_shape_expectations(
                            _default_cv_shape_expectations(
                                priors=priors,
                                preflight_summary=preflight_summary,
                                document_expectations=document_expectations.model_dump(),
                                stakeholder_surface=stakeholder_surface,
                                ai_intensity=ai_intensity,
                            ),
                            ai_intensity=ai_intensity,
                            document_header_density=document_expectations.density_posture.header_density,
                        )
                else:
                    notes.append(f"cv_shape_expectations fell back to role-family defaults after schema repair returned no payload: {exc}")
                    cv_shape_defaulted = True
                    cv_shape_expectations = _validate_cv_shape_expectations(
                        _default_cv_shape_expectations(
                            priors=priors,
                            preflight_summary=preflight_summary,
                            document_expectations=document_expectations.model_dump(),
                            stakeholder_surface=stakeholder_surface,
                            ai_intensity=ai_intensity,
                        ),
                        ai_intensity=ai_intensity,
                        document_header_density=document_expectations.density_posture.header_density,
                    )
            else:
                notes.append(f"cv_shape_expectations defaulted because deterministic validation failed: {exc}")
                cv_shape_defaulted = True
                cv_shape_expectations = _validate_cv_shape_expectations(
                    _default_cv_shape_expectations(
                        priors=priors,
                        preflight_summary=preflight_summary,
                        document_expectations=document_expectations.model_dump(),
                        stakeholder_surface=stakeholder_surface,
                        ai_intensity=ai_intensity,
                    ),
                    ai_intensity=ai_intensity,
                    document_header_density=document_expectations.density_posture.header_density,
                )
        if cv_shape_defaulted:
            cv_shape_expectations = _mark_cv_shape_defaults_applied(
                cv_shape_expectations,
                default_id="role_family_cv_shape_default",
                unresolved_marker="schema_defaulted_cv_shape_expectations",
            )

        ideal_candidate_priors = _ideal_candidate_priors(
            priors=priors,
            jd_facts=jd_facts,
            classification=classification,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=document_expectations.model_dump(),
            cv_shape_expectations=cv_shape_expectations.model_dump(),
        )
        default_ideal_candidate = _default_ideal_candidate_presentation_model(
            priors=ideal_candidate_priors,
            preflight_summary=preflight_summary,
            jd_facts=jd_facts,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=document_expectations.model_dump(),
            cv_shape_expectations=cv_shape_expectations.model_dump(),
        )

        ideal_candidate_span = ctx.tracer.start_substage_span(
            ctx.stage_name or self.name,
            "ideal_candidate",
            {
                "job_id": _job_id(ctx),
                "stage_name": ctx.stage_name or self.name,
                "title_strategy": cv_shape_expectations.title_strategy,
                "role_family": ideal_candidate_priors.get("role_family"),
                "stakeholder_status": stakeholder_status,
            },
        )
        if presentation_contract_ideal_candidate_enabled():
            prompt_metadata["ideal_candidate"] = _prompt_metadata(prompt_id="ideal_candidate", ctx=ctx)
            ideal_prompt = build_p_ideal_candidate(
                preflight=preflight,
                ideal_candidate_priors=ideal_candidate_priors,
                document_expectations=document_expectations.model_dump(),
                cv_shape_expectations=cv_shape_expectations.model_dump(),
                jd_excerpt=jd_excerpt,
                classification_excerpt={
                    "primary_role_category": classification.get("primary_role_category"),
                    "tone_family": classification.get("tone_family"),
                    "ai_taxonomy": classification.get("ai_taxonomy") or {},
                },
                research_excerpt={
                    "company_profile": company_profile,
                    "role_profile": role_profile,
                    "application_profile": application_profile,
                },
                stakeholder_surface_excerpt={
                    "status": stakeholder_status,
                    "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [],
                    "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or [],
                },
                pain_point_excerpt={
                    "status": pain_point_intelligence.get("status"),
                    "proof_map": pain_point_intelligence.get("proof_map") or [],
                },
                ideal_candidate_profile_seed=(jd_facts.get("ideal_candidate_profile") or {}),
            )
            raw_ideal_candidate, _ = self._invoke_prompt(
                ctx=ctx,
                prompt=ideal_prompt,
                substage="ideal_candidate",
                job_id=f"{_job_id(ctx)}:presentation_contract:ideal_candidate",
            )
            raw_debug["raw_outputs"]["ideal_candidate"] = raw_ideal_candidate
            if isinstance(raw_ideal_candidate, dict):
                ideal_candidate_payload = _extract_subpayload(raw_ideal_candidate, "ideal_candidate_presentation_model") or ideal_candidate_payload
        else:
            notes.append("ideal_candidate_presentation_model used deterministic fallback because PREENRICH_PRESENTATION_CONTRACT_IDEAL_CANDIDATE_ENABLED=false.")
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.ideal_candidate.fail_open",
                {
                    "reason": "flag_disabled",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        normalized_ideal_candidate = normalize_ideal_candidate_payload(
            ideal_candidate_payload,
            evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
            expected_title_strategy=cv_shape_expectations.title_strategy,
            allowed_company_names=allowed_company_names,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
        )
        normalized_ideal_candidate["debug_context"] = _merge_debug_context(
            default_ideal_candidate.get("debug_context") or {},
            normalized_ideal_candidate.get("debug_context") or {},
        )
        normalized_ideal_candidate["debug_context"]["input_summary"] = preflight_summary

        try:
            ideal_candidate = _validate_ideal_candidate(
                normalized_ideal_candidate,
                evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                expected_title_strategy=cv_shape_expectations.title_strategy,
                stakeholder_status=stakeholder_status,
            )
        except Exception as exc:
            normalized_ideal_candidate["debug_context"]["retry_events"] = list(normalized_ideal_candidate["debug_context"].get("retry_events") or []) + [
                {"repair_reason": str(exc), "repair_attempt": 1}
            ]
            if presentation_contract_ideal_candidate_enabled():
                repair_prompt = _repair_prompt(ideal_prompt, str(exc))
                repaired_ideal, _ = self._invoke_prompt(
                    ctx=ctx,
                    prompt=repair_prompt,
                    substage="ideal_candidate.schema_repair",
                    job_id=f"{_job_id(ctx)}:presentation_contract:ideal_candidate:repair",
                )
                raw_debug["raw_outputs"]["ideal_candidate_repair"] = repaired_ideal
                if isinstance(repaired_ideal, dict):
                    normalized_ideal_candidate = normalize_ideal_candidate_payload(
                        _extract_subpayload(repaired_ideal, "ideal_candidate_presentation_model"),
                        evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                        expected_title_strategy=cv_shape_expectations.title_strategy,
                        allowed_company_names=allowed_company_names,
                        allowed_company_domain=allowed_company_domain,
                        jd_excerpt=jd_excerpt,
                    )
                    normalized_ideal_candidate["debug_context"] = _merge_debug_context(
                        default_ideal_candidate.get("debug_context") or {},
                        normalized_ideal_candidate.get("debug_context") or {},
                    )
                    normalized_ideal_candidate["debug_context"]["input_summary"] = preflight_summary
                    normalized_ideal_candidate["debug_context"]["retry_events"] = [{"repair_reason": str(exc), "repair_attempt": 1}]
                    try:
                        ideal_candidate = _validate_ideal_candidate(
                            normalized_ideal_candidate,
                            evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                            expected_title_strategy=cv_shape_expectations.title_strategy,
                            stakeholder_status=stakeholder_status,
                        )
                    except Exception as repair_exc:
                        notes.append(f"ideal_candidate_presentation_model fell back to role-family defaults after schema repair failed: {repair_exc}")
                        ideal_candidate_defaulted = True
                        ideal_candidate = _validate_ideal_candidate(
                            default_ideal_candidate,
                            evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                            expected_title_strategy=cv_shape_expectations.title_strategy,
                            stakeholder_status=stakeholder_status,
                        )
                else:
                    notes.append(f"ideal_candidate_presentation_model fell back to role-family defaults after schema repair returned no payload: {exc}")
                    ideal_candidate_defaulted = True
                    ideal_candidate = _validate_ideal_candidate(
                        default_ideal_candidate,
                        evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                        expected_title_strategy=cv_shape_expectations.title_strategy,
                        stakeholder_status=stakeholder_status,
                    )
            else:
                notes.append(f"ideal_candidate_presentation_model defaulted because deterministic validation failed: {exc}")
                ideal_candidate_defaulted = True
                ideal_candidate = _validate_ideal_candidate(
                    default_ideal_candidate,
                    evaluator_coverage_target=list(stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]),
                    expected_title_strategy=cv_shape_expectations.title_strategy,
                    stakeholder_status=stakeholder_status,
                )
        if ideal_candidate_defaulted:
            ideal_candidate = _mark_ideal_candidate_defaults_applied(
                ideal_candidate,
                default_id="role_family_ideal_candidate_default",
                unresolved_marker="schema_defaulted_ideal_candidate",
            )
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.ideal_candidate.fail_open",
                {
                    "reason": "schema_defaulted",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        ctx.tracer.end_span(
            ideal_candidate_span,
            output={
                "status": ideal_candidate.status,
                "title_strategy": ideal_candidate.title_strategy,
                "acceptable_titles_count": len(ideal_candidate.acceptable_titles),
                "proof_ladder_length": len(ideal_candidate.proof_ladder),
                "must_signal_count": len(ideal_candidate.must_signal),
                "should_signal_count": len(ideal_candidate.should_signal),
                "de_emphasize_count": len(ideal_candidate.de_emphasize),
                "audience_variant_count": len(ideal_candidate.audience_variants),
                "credibility_marker_count": len(ideal_candidate.credibility_markers),
                "risk_flags_count": len(ideal_candidate.risk_flags),
                "defaults_applied_count": len(ideal_candidate.defaults_applied),
                "confidence_band": ideal_candidate.confidence.band,
            },
        )
        if ideal_candidate.defaults_applied and not ideal_candidate_defaulted:
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.ideal_candidate.fail_open",
                {
                    "reason": "role_family_defaults",
                    "defaults_applied": list(ideal_candidate.defaults_applied),
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        dimension_weight_priors = _experience_dimension_priors(
            priors=priors,
            jd_facts=jd_facts,
            classification=classification,
            research=research,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=document_expectations.model_dump(),
            cv_shape_expectations=cv_shape_expectations.model_dump(),
            ideal_candidate=ideal_candidate.model_dump(),
        )
        default_dimension_weights = _default_experience_dimension_weights(
            priors=dimension_weight_priors,
            preflight_summary=preflight_summary,
            stakeholder_surface=stakeholder_surface,
            research=research,
            pain_point_intelligence=pain_point_intelligence,
        )
        dimension_weights_span = ctx.tracer.start_substage_span(
            ctx.stage_name or self.name,
            "dimension_weights",
            {
                "job_id": _job_id(ctx),
                "stage_name": ctx.stage_name or self.name,
                "role_family": dimension_weight_priors.get("role_family"),
                "dimension_enum_version": DIMENSION_ENUM_VERSION,
                "ai_intensity_cap": dimension_weight_priors.get("ai_intensity_cap"),
                "stakeholder_status": stakeholder_status,
            },
        )
        if presentation_contract_dimension_weights_enabled() and not dimension_weights_from_merged:
            prompt_metadata["experience_dimension_weights"] = _prompt_metadata(
                prompt_id="experience_dimension_weights",
                ctx=ctx,
            )
            dimension_prompt = build_p_experience_dimension_weights(
                preflight=preflight,
                experience_dimension_priors=dimension_weight_priors,
                document_expectations=document_expectations.model_dump(),
                cv_shape_expectations=cv_shape_expectations.model_dump(),
                ideal_candidate_presentation_model=ideal_candidate.model_dump(),
                jd_excerpt=jd_excerpt,
                classification_excerpt={
                    "primary_role_category": classification.get("primary_role_category"),
                    "tone_family": classification.get("tone_family"),
                    "ai_taxonomy": classification.get("ai_taxonomy") or {},
                },
                research_excerpt={
                    "company_profile": company_profile,
                    "role_profile": role_profile,
                    "application_profile": application_profile,
                },
                stakeholder_surface_excerpt={
                    "status": stakeholder_status,
                    "evaluator_coverage_target": stakeholder_surface.get("evaluator_coverage_target") or [],
                    "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or [],
                },
                pain_point_excerpt={
                    "status": pain_point_intelligence.get("status"),
                    "proof_map": pain_point_intelligence.get("proof_map") or [],
                    "bad_proof_patterns": pain_point_intelligence.get("bad_proof_patterns") or [],
                },
                truth_constraints_excerpt={},
            )
            raw_dimension_weights, _ = self._invoke_prompt(
                ctx=ctx,
                prompt=dimension_prompt,
                substage="dimension_weights",
                job_id=f"{_job_id(ctx)}:presentation_contract:dimension_weights",
            )
            raw_debug["raw_outputs"]["experience_dimension_weights"] = raw_dimension_weights
            if isinstance(raw_dimension_weights, dict):
                dimension_weights_payload = (
                    _extract_subpayload(raw_dimension_weights, "experience_dimension_weights")
                    or dimension_weights_payload
                )
        elif not presentation_contract_dimension_weights_enabled():
            notes.append(
                "experience_dimension_weights used deterministic fallback because "
                "PREENRICH_PRESENTATION_CONTRACT_DIMENSION_WEIGHTS_ENABLED=false."
            )
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.dimension_weights.fail_open",
                {
                    "reason": "flag_disabled",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        normalized_dimension_weights = normalize_experience_dimension_weights_payload(
            dimension_weights_payload,
            evaluator_coverage_target=list(
                stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
            ),
            allowed_company_names=allowed_company_names,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
        )
        normalized_dimension_weights["debug_context"] = _merge_dimension_debug_context(
            default_dimension_weights.get("debug_context") or {},
            normalized_dimension_weights.get("debug_context") or {},
        )
        normalized_dimension_weights["debug_context"]["input_summary"] = {
            **preflight_summary,
            "pain_point_intelligence_status": str(pain_point_intelligence.get("status") or "unresolved"),
        }
        try:
            dimension_weights = _validate_experience_dimension_weights(
                normalized_dimension_weights,
                evaluator_coverage_target=list(
                    stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
                ),
                ai_intensity=ai_intensity,
                priors=dimension_weight_priors,
                document_expectations=document_expectations.model_dump(),
                cv_shape_expectations=cv_shape_expectations.model_dump(),
                ideal_candidate=ideal_candidate.model_dump(),
            )
        except Exception as exc:
            normalized_dimension_weights["debug_context"]["retry_events"] = list(
                normalized_dimension_weights["debug_context"].get("retry_events") or []
            ) + [{"repair_reason": str(exc), "repair_attempt": 1}]
            if presentation_contract_dimension_weights_enabled():
                repair_prompt = _repair_prompt(dimension_prompt, str(exc))
                repaired_dimension_weights, _ = self._invoke_prompt(
                    ctx=ctx,
                    prompt=repair_prompt,
                    substage="dimension_weights.schema_repair",
                    job_id=f"{_job_id(ctx)}:presentation_contract:dimension_weights:repair",
                )
                raw_debug["raw_outputs"]["experience_dimension_weights_repair"] = repaired_dimension_weights
                if isinstance(repaired_dimension_weights, dict):
                    normalized_dimension_weights = normalize_experience_dimension_weights_payload(
                        _extract_subpayload(repaired_dimension_weights, "experience_dimension_weights"),
                        evaluator_coverage_target=list(
                            stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
                        ),
                        allowed_company_names=allowed_company_names,
                        allowed_company_domain=allowed_company_domain,
                        jd_excerpt=jd_excerpt,
                    )
                    normalized_dimension_weights["debug_context"] = _merge_dimension_debug_context(
                        default_dimension_weights.get("debug_context") or {},
                        normalized_dimension_weights.get("debug_context") or {},
                    )
                    normalized_dimension_weights["debug_context"]["input_summary"] = {
                        **preflight_summary,
                        "pain_point_intelligence_status": str(pain_point_intelligence.get("status") or "unresolved"),
                    }
                    normalized_dimension_weights["debug_context"]["retry_events"] = [
                        {"repair_reason": str(exc), "repair_attempt": 1}
                    ]
                    try:
                        dimension_weights = _validate_experience_dimension_weights(
                            normalized_dimension_weights,
                            evaluator_coverage_target=list(
                                stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
                            ),
                            ai_intensity=ai_intensity,
                            priors=dimension_weight_priors,
                            document_expectations=document_expectations.model_dump(),
                            cv_shape_expectations=cv_shape_expectations.model_dump(),
                            ideal_candidate=ideal_candidate.model_dump(),
                        )
                    except Exception as repair_exc:
                        notes.append(
                            "experience_dimension_weights fell back to role-family defaults after "
                            f"schema repair failed: {repair_exc}"
                        )
                        dimension_weights_defaulted = True
                        dimension_weights = _validate_experience_dimension_weights(
                            default_dimension_weights,
                            evaluator_coverage_target=list(
                                stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
                            ),
                            ai_intensity=ai_intensity,
                            priors=dimension_weight_priors,
                            document_expectations=document_expectations.model_dump(),
                            cv_shape_expectations=cv_shape_expectations.model_dump(),
                            ideal_candidate=ideal_candidate.model_dump(),
                            allow_fail_open_rebalance=True,
                        )
                else:
                    notes.append(
                        "experience_dimension_weights fell back to role-family defaults after "
                        f"schema repair returned no payload: {exc}"
                    )
                    dimension_weights_defaulted = True
                    dimension_weights = _validate_experience_dimension_weights(
                        default_dimension_weights,
                        evaluator_coverage_target=list(
                            stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
                        ),
                        ai_intensity=ai_intensity,
                        priors=dimension_weight_priors,
                        document_expectations=document_expectations.model_dump(),
                        cv_shape_expectations=cv_shape_expectations.model_dump(),
                        ideal_candidate=ideal_candidate.model_dump(),
                        allow_fail_open_rebalance=True,
                    )
            else:
                notes.append(f"experience_dimension_weights defaulted because deterministic validation failed: {exc}")
                dimension_weights_defaulted = True
                dimension_weights = _validate_experience_dimension_weights(
                    default_dimension_weights,
                    evaluator_coverage_target=list(
                        stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
                    ),
                    ai_intensity=ai_intensity,
                    priors=dimension_weight_priors,
                    document_expectations=document_expectations.model_dump(),
                    cv_shape_expectations=cv_shape_expectations.model_dump(),
                    ideal_candidate=ideal_candidate.model_dump(),
                    allow_fail_open_rebalance=True,
                )
        if dimension_weights_defaulted:
            dimension_weights = _mark_dimension_weights_defaults_applied(
                dimension_weights,
                default_id="role_family_dimension_weights_default",
                unresolved_marker="schema_defaulted_dimension_weights",
            )
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.dimension_weights.fail_open",
                {
                    "reason": "schema_defaulted",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        evaluator_roles = list(
            stakeholder_surface.get("evaluator_coverage_target") or ["recruiter", "hiring_manager"]
        )
        emphasis_rule_priors = _emphasis_rule_priors(
            priors=priors,
            jd_facts=jd_facts,
            classification=classification,
            research=research,
            stakeholder_surface=stakeholder_surface,
            pain_point_intelligence=pain_point_intelligence,
            document_expectations=document_expectations.model_dump(),
            cv_shape_expectations=cv_shape_expectations.model_dump(),
            ideal_candidate=ideal_candidate.model_dump(),
            experience_dimension_weights=dimension_weights.model_dump(),
        )
        default_emphasis_rules = _default_truth_constrained_emphasis_rules(
            priors=emphasis_rule_priors,
            preflight_summary=preflight_summary,
            stakeholder_surface=stakeholder_surface,
            research=research,
            pain_point_intelligence=pain_point_intelligence,
        )
        if not presentation_contract_emphasis_rules_enabled():
            emphasis_rules_payload = dict(default_emphasis_rules)

        emphasis_rules_defaulted = False
        emphasis_llm_schema_valid = False
        cross_validator_violations: list[str] = []
        emphasis_rules_span = ctx.tracer.start_substage_span(
            ctx.stage_name or self.name,
            "emphasis_rules",
            {
                "job_id": _job_id(ctx),
                "stage_name": ctx.stage_name or self.name,
                "role_family": emphasis_rule_priors.get("role_family"),
                "rule_type_enum_version": RULE_TYPE_ENUM_VERSION,
                "applies_to_enum_version": APPLIES_TO_ENUM_VERSION,
                "stakeholder_status": stakeholder_status,
                "merged_prompt_mode": presentation_contract_merged_prompt_enabled(),
            },
        )
        emphasis_prompt = ""
        if presentation_contract_emphasis_rules_enabled() and not emphasis_rules_from_merged:
            prompt_metadata["emphasis_rules"] = _prompt_metadata(prompt_id="emphasis_rules", ctx=ctx)
            emphasis_prompt = build_p_emphasis_rules(
                preflight=preflight,
                emphasis_rule_priors=emphasis_rule_priors,
                document_expectations=document_expectations.model_dump(),
                cv_shape_expectations=cv_shape_expectations.model_dump(),
                ideal_candidate_presentation_model=ideal_candidate.model_dump(),
                experience_dimension_weights=dimension_weights.model_dump(),
                jd_excerpt=jd_excerpt,
                classification_excerpt={
                    "primary_role_category": classification.get("primary_role_category"),
                    "tone_family": classification.get("tone_family"),
                    "ai_taxonomy": classification.get("ai_taxonomy") or {},
                },
                research_excerpt={
                    "company_profile": company_profile,
                    "role_profile": role_profile,
                    "application_profile": application_profile,
                },
                stakeholder_surface_excerpt={
                    "status": stakeholder_status,
                    "evaluator_coverage_target": evaluator_roles,
                    "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or [],
                },
                pain_point_excerpt={
                    "status": pain_point_intelligence.get("status"),
                    "proof_map": pain_point_intelligence.get("proof_map") or [],
                    "bad_proof_patterns": pain_point_intelligence.get("bad_proof_patterns") or [],
                },
            )
            raw_emphasis_rules, _ = self._invoke_prompt(
                ctx=ctx,
                prompt=emphasis_prompt,
                substage="emphasis_rules",
                job_id=f"{_job_id(ctx)}:presentation_contract:emphasis_rules",
            )
            raw_debug["raw_outputs"]["truth_constrained_emphasis_rules"] = raw_emphasis_rules
            if isinstance(raw_emphasis_rules, dict):
                emphasis_rules_payload = (
                    _extract_subpayload(raw_emphasis_rules, "truth_constrained_emphasis_rules")
                    or emphasis_rules_payload
                )
        elif not presentation_contract_emphasis_rules_enabled():
            notes.append(
                "truth_constrained_emphasis_rules used deterministic fallback because "
                "PREENRICH_PRESENTATION_CONTRACT_EMPHASIS_RULES_ENABLED=false."
            )
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.emphasis_rules.fail_open",
                {
                    "reason": "defaults_only",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        normalized_emphasis_rules = normalize_truth_constrained_emphasis_rules_payload(
            emphasis_rules_payload,
            evaluator_coverage_target=evaluator_roles,
            allowed_company_names=allowed_company_names,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
            coverage_source=(
                "merged"
                if emphasis_rules_from_merged
                else ("default" if not presentation_contract_emphasis_rules_enabled() else "llm")
            ),
        )
        normalized_emphasis_rules["debug_context"] = _merge_emphasis_debug_context(
            default_emphasis_rules.get("debug_context") or {},
            normalized_emphasis_rules.get("debug_context") or {},
        )
        normalized_emphasis_rules["debug_context"]["input_summary"] = {
            **preflight_summary,
            "pain_point_intelligence_status": str(pain_point_intelligence.get("status") or "unresolved"),
        }
        try:
            emphasis_rules = _validate_truth_constrained_emphasis_rules(
                normalized_emphasis_rules,
                evaluator_coverage_target=evaluator_roles,
                stakeholder_status=stakeholder_status,
                ai_intensity=ai_intensity,
                priors=emphasis_rule_priors,
                document_expectations=document_expectations.model_dump(),
                cv_shape_expectations=cv_shape_expectations.model_dump(),
                ideal_candidate=ideal_candidate.model_dump(),
                experience_dimension_weights=dimension_weights.model_dump(),
            )
            emphasis_llm_schema_valid = presentation_contract_emphasis_rules_enabled()
        except Exception as exc:
            normalized_emphasis_rules["debug_context"]["retry_events"] = list(
                normalized_emphasis_rules["debug_context"].get("retry_events") or []
            ) + [{"repair_reason": str(exc), "repair_attempt": 1}]
            if presentation_contract_emphasis_rules_enabled():
                repair_prompt = _repair_prompt(
                    emphasis_prompt
                    or build_p_emphasis_rules(
                        preflight=preflight,
                        emphasis_rule_priors=emphasis_rule_priors,
                        document_expectations=document_expectations.model_dump(),
                        cv_shape_expectations=cv_shape_expectations.model_dump(),
                        ideal_candidate_presentation_model=ideal_candidate.model_dump(),
                        experience_dimension_weights=dimension_weights.model_dump(),
                        jd_excerpt=jd_excerpt,
                        classification_excerpt={
                            "primary_role_category": classification.get("primary_role_category"),
                            "tone_family": classification.get("tone_family"),
                            "ai_taxonomy": classification.get("ai_taxonomy") or {},
                        },
                        research_excerpt={
                            "company_profile": company_profile,
                            "role_profile": role_profile,
                            "application_profile": application_profile,
                        },
                        stakeholder_surface_excerpt={
                            "status": stakeholder_status,
                            "evaluator_coverage_target": evaluator_roles,
                            "evaluator_coverage": stakeholder_surface.get("evaluator_coverage") or [],
                        },
                        pain_point_excerpt={
                            "status": pain_point_intelligence.get("status"),
                            "proof_map": pain_point_intelligence.get("proof_map") or [],
                            "bad_proof_patterns": pain_point_intelligence.get("bad_proof_patterns") or [],
                        },
                    ),
                    str(exc),
                )
                repaired_emphasis_rules, _ = self._invoke_prompt(
                    ctx=ctx,
                    prompt=repair_prompt,
                    substage="emphasis_rules.schema_repair",
                    job_id=f"{_job_id(ctx)}:presentation_contract:emphasis_rules:repair",
                )
                raw_debug["raw_outputs"]["truth_constrained_emphasis_rules_repair"] = repaired_emphasis_rules
                if isinstance(repaired_emphasis_rules, dict):
                    normalized_emphasis_rules = normalize_truth_constrained_emphasis_rules_payload(
                        _extract_subpayload(repaired_emphasis_rules, "truth_constrained_emphasis_rules"),
                        evaluator_coverage_target=evaluator_roles,
                        allowed_company_names=allowed_company_names,
                        allowed_company_domain=allowed_company_domain,
                        jd_excerpt=jd_excerpt,
                        coverage_source="llm",
                    )
                    normalized_emphasis_rules["debug_context"] = _merge_emphasis_debug_context(
                        default_emphasis_rules.get("debug_context") or {},
                        normalized_emphasis_rules.get("debug_context") or {},
                    )
                    normalized_emphasis_rules["debug_context"]["input_summary"] = {
                        **preflight_summary,
                        "pain_point_intelligence_status": str(pain_point_intelligence.get("status") or "unresolved"),
                    }
                    normalized_emphasis_rules["debug_context"]["retry_events"] = [
                        {"repair_reason": str(exc), "repair_attempt": 1}
                    ]
                    try:
                        emphasis_rules = _validate_truth_constrained_emphasis_rules(
                            normalized_emphasis_rules,
                            evaluator_coverage_target=evaluator_roles,
                            stakeholder_status=stakeholder_status,
                            ai_intensity=ai_intensity,
                            priors=emphasis_rule_priors,
                            document_expectations=document_expectations.model_dump(),
                            cv_shape_expectations=cv_shape_expectations.model_dump(),
                            ideal_candidate=ideal_candidate.model_dump(),
                            experience_dimension_weights=dimension_weights.model_dump(),
                        )
                        emphasis_llm_schema_valid = True
                    except Exception as repair_exc:
                        notes.append(
                            "truth_constrained_emphasis_rules fell back to role-family defaults after "
                            f"schema repair failed: {repair_exc}"
                        )
                        emphasis_rules_defaulted = True
                        emphasis_rules = _validate_truth_constrained_emphasis_rules(
                            default_emphasis_rules,
                            evaluator_coverage_target=evaluator_roles,
                            stakeholder_status=stakeholder_status,
                            ai_intensity=ai_intensity,
                            priors=emphasis_rule_priors,
                            document_expectations=document_expectations.model_dump(),
                            cv_shape_expectations=cv_shape_expectations.model_dump(),
                            ideal_candidate=ideal_candidate.model_dump(),
                            experience_dimension_weights=dimension_weights.model_dump(),
                        )
                else:
                    notes.append(
                        "truth_constrained_emphasis_rules fell back to role-family defaults after "
                        f"schema repair returned no payload: {exc}"
                    )
                    emphasis_rules_defaulted = True
                    emphasis_rules = _validate_truth_constrained_emphasis_rules(
                        default_emphasis_rules,
                        evaluator_coverage_target=evaluator_roles,
                        stakeholder_status=stakeholder_status,
                        ai_intensity=ai_intensity,
                        priors=emphasis_rule_priors,
                        document_expectations=document_expectations.model_dump(),
                        cv_shape_expectations=cv_shape_expectations.model_dump(),
                        ideal_candidate=ideal_candidate.model_dump(),
                        experience_dimension_weights=dimension_weights.model_dump(),
                    )
            else:
                notes.append(
                    "truth_constrained_emphasis_rules defaulted because deterministic validation failed: "
                    f"{exc}"
                )
                emphasis_rules_defaulted = True
                emphasis_rules = _validate_truth_constrained_emphasis_rules(
                    default_emphasis_rules,
                    evaluator_coverage_target=evaluator_roles,
                    stakeholder_status=stakeholder_status,
                    ai_intensity=ai_intensity,
                    priors=emphasis_rule_priors,
                    document_expectations=document_expectations.model_dump(),
                    cv_shape_expectations=cv_shape_expectations.model_dump(),
                    ideal_candidate=ideal_candidate.model_dump(),
                    experience_dimension_weights=dimension_weights.model_dump(),
                )
        if emphasis_rules_defaulted:
            emphasis_rules = _mark_emphasis_defaults_applied(
                emphasis_rules,
                default_id="role_family_emphasis_rules_default",
                unresolved_marker="schema_defaulted_emphasis_rules",
                fail_open_reason="schema_repair_exhausted",
            )
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.emphasis_rules.fail_open",
                {
                    "reason": "schema_repair_exhausted",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        dimension_weights, emphasis_rules = _apply_emphasis_dimension_caps(
            dimension_weights,
            emphasis_rules,
            evaluator_coverage_target=evaluator_roles,
        )

        sub_statuses = {
            document_expectations.status,
            cv_shape_expectations.status,
            ideal_candidate.status,
            dimension_weights.status,
            emphasis_rules.status,
        }
        if "failed_terminal" in sub_statuses:
            top_status = "failed_terminal"
        elif "partial" in sub_statuses or "inferred_only" in sub_statuses:
            top_status = "partial"
        elif "unresolved" in sub_statuses:
            top_status = "unresolved"
        else:
            top_status = "completed"

        if not list(pain_point_intelligence.get("proof_map") or []):
            unresolved_questions.append("pain_point_intelligence proof_map absent or thin; proof_order defaulted from role-family priors.")
        if stakeholder_status in {"inferred_only", "no_research", "unresolved"}:
            unresolved_questions.append("stakeholder_surface evidence was thin; audience variants and confidence were conservatively capped.")
        if ideal_candidate.defaults_applied:
            unresolved_questions.append("ideal_candidate_presentation_model used deterministic defaults for some framing decisions.")
        if dimension_weights.defaults_applied:
            unresolved_questions.append("experience_dimension_weights used deterministic defaults for some salience decisions.")
        if emphasis_rules.defaults_applied:
            unresolved_questions.append("truth_constrained_emphasis_rules used deterministic defaults for some claim-policy decisions.")

        artifact_kwargs = {
            "job_id": _job_id(ctx),
            "level2_job_id": _level2_job_id(ctx),
            "input_snapshot_id": ctx.input_snapshot_id,
            "prompt_versions": {key: value.prompt_version for key, value in prompt_metadata.items()},
            "prompt_metadata": prompt_metadata,
            "status": top_status,
            "document_expectations": document_expectations,
            "cv_shape_expectations": cv_shape_expectations,
            "ideal_candidate_presentation_model": ideal_candidate,
            "experience_dimension_weights": dimension_weights,
            "truth_constrained_emphasis_rules": emphasis_rules,
            "debug": raw_debug,
            "unresolved_questions": list(dict.fromkeys(unresolved_questions)),
            "notes": notes,
            "timing": {"generated_at": _now_iso()},
            "usage": {"provider": ctx.config.provider, "model": ctx.config.primary_model},
        }
        cross_validate_span = ctx.tracer.start_substage_span(
            ctx.stage_name or self.name,
            "emphasis_rules.cross_validate",
            {
                "job_id": _job_id(ctx),
                "stage_name": ctx.stage_name or self.name,
                "invariants_checked_count": 14,
            },
        )
        try:
            artifact = PresentationContractDoc(**artifact_kwargs)
            ctx.tracer.end_span(
                cross_validate_span,
                output={
                    "resolution": "passed",
                    "invariants_checked_count": 14,
                    "invariants_violated_count": 0,
                    "violated_invariants": [],
                },
            )
        except Exception as exc:
            cross_validator_violations = ["parent_cross_validation"]
            ctx.tracer.end_span(
                cross_validate_span,
                output={
                    "resolution": "parent_fallback",
                    "invariants_checked_count": 14,
                    "invariants_violated_count": 1,
                    "violated_invariants": cross_validator_violations,
                },
            )
            notes.append(f"presentation_contract cross-validation fell back to deterministic defaults: {exc}")
            dimension_weights = _mark_dimension_weights_defaults_applied(
                _validate_experience_dimension_weights(
                    default_dimension_weights,
                    evaluator_coverage_target=evaluator_roles,
                    ai_intensity=ai_intensity,
                    priors=dimension_weight_priors,
                    document_expectations=document_expectations.model_dump(),
                    cv_shape_expectations=cv_shape_expectations.model_dump(),
                    ideal_candidate=ideal_candidate.model_dump(),
                    allow_fail_open_rebalance=True,
                ),
                default_id="cross_validator_dimension_weights_default",
                unresolved_marker="cross_validated_dimension_weights_default",
            )
            dimension_weights_defaulted = True
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.dimension_weights.fail_open",
                {
                    "reason": "cross_validator_defaulted",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )
            emphasis_rule_priors = _emphasis_rule_priors(
                priors=priors,
                jd_facts=jd_facts,
                classification=classification,
                research=research,
                stakeholder_surface=stakeholder_surface,
                pain_point_intelligence=pain_point_intelligence,
                document_expectations=document_expectations.model_dump(),
                cv_shape_expectations=cv_shape_expectations.model_dump(),
                ideal_candidate=ideal_candidate.model_dump(),
                experience_dimension_weights=dimension_weights.model_dump(),
            )
            default_emphasis_rules = _default_truth_constrained_emphasis_rules(
                priors=emphasis_rule_priors,
                preflight_summary=preflight_summary,
                stakeholder_surface=stakeholder_surface,
                research=research,
                pain_point_intelligence=pain_point_intelligence,
            )
            emphasis_rules = _mark_emphasis_defaults_applied(
                _validate_truth_constrained_emphasis_rules(
                    default_emphasis_rules,
                    evaluator_coverage_target=evaluator_roles,
                    stakeholder_status=stakeholder_status,
                    ai_intensity=ai_intensity,
                    priors=emphasis_rule_priors,
                    document_expectations=document_expectations.model_dump(),
                    cv_shape_expectations=cv_shape_expectations.model_dump(),
                    ideal_candidate=ideal_candidate.model_dump(),
                    experience_dimension_weights=dimension_weights.model_dump(),
                ),
                default_id="cross_validator_emphasis_rules_default",
                unresolved_marker="cross_validated_emphasis_rules_default",
                fail_open_reason="cross_invariant_suppressed",
            )
            emphasis_rules_defaulted = True
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.emphasis_rules.fail_open",
                {
                    "reason": "cross_invariant_suppressed",
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )
            dimension_weights, emphasis_rules = _apply_emphasis_dimension_caps(
                dimension_weights,
                emphasis_rules,
                evaluator_coverage_target=evaluator_roles,
            )
            sub_statuses = {
                document_expectations.status,
                cv_shape_expectations.status,
                ideal_candidate.status,
                dimension_weights.status,
                emphasis_rules.status,
            }
            if "failed_terminal" in sub_statuses:
                top_status = "failed_terminal"
            elif "partial" in sub_statuses or "inferred_only" in sub_statuses:
                top_status = "partial"
            elif "unresolved" in sub_statuses:
                top_status = "unresolved"
            else:
                top_status = "completed"
            artifact_kwargs["status"] = top_status
            artifact_kwargs["experience_dimension_weights"] = dimension_weights
            artifact_kwargs["truth_constrained_emphasis_rules"] = emphasis_rules
            artifact_kwargs["notes"] = notes
            artifact = PresentationContractDoc(**artifact_kwargs)

        if dimension_weights.defaults_applied and not dimension_weights_defaulted:
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.dimension_weights.fail_open",
                {
                    "reason": "role_family_defaults",
                    "defaults_applied": list(dimension_weights.defaults_applied),
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        normalizer_conflicts = [
            entry for entry in emphasis_rules.debug_context.conflict_resolution_log if entry.conflict_source == "normalizer"
        ]
        duplicate_rules_collapsed_count = sum(
            1 for event in emphasis_rules.normalization_events if event.kind == "duplicate_collapsed"
        )
        if normalizer_conflicts or duplicate_rules_collapsed_count:
            conflict_span = ctx.tracer.start_substage_span(
                ctx.stage_name or self.name,
                "emphasis_rules.rule_conflict_resolution",
                {
                    "job_id": _job_id(ctx),
                    "stage_name": ctx.stage_name or self.name,
                    "conflict_count": len(normalizer_conflicts),
                    "duplicate_rules_collapsed_count": duplicate_rules_collapsed_count,
                },
            )
            ctx.tracer.end_span(
                conflict_span,
                output={
                    "status": "completed",
                    "conflict_count": len(normalizer_conflicts),
                    "suppressed_count": len(
                        [entry for entry in normalizer_conflicts if entry.resolution == "suppressed"]
                    ),
                    "retained_count": len(
                        [entry for entry in normalizer_conflicts if entry.resolution == "retained"]
                    ),
                    "duplicate_rules_collapsed_count": duplicate_rules_collapsed_count,
                },
            )

        _emit_emphasis_consistency_events(ctx, emphasis_rules)

        ctx.tracer.end_span(
            dimension_weights_span,
            output={
                "status": dimension_weights.status,
                "dimension_enum_version": dimension_weights.dimension_enum_version,
                "overall_weight_sum": sum(dimension_weights.overall_weights.values()),
                "stakeholder_variant_count": len(
                    [value for value in dimension_weights.stakeholder_variant_weights.values() if value]
                ),
                "minimum_visible_dimensions_count": len(dimension_weights.minimum_visible_dimensions),
                "overuse_risks_count": len(dimension_weights.overuse_risks),
                "defaults_applied_count": len(dimension_weights.defaults_applied),
                "normalization_events_count": len(dimension_weights.normalization_events),
                "confidence_band": dimension_weights.confidence.band,
                "title_strategy": cv_shape_expectations.title_strategy,
            },
        )

        ctx.tracer.end_span(
            emphasis_rules_span,
            output=_build_emphasis_trace_output(
                emphasis_rules=emphasis_rules,
                document_expectations=document_expectations,
                cv_shape_expectations=cv_shape_expectations,
                ideal_candidate=ideal_candidate,
                dimension_weights=dimension_weights,
                prompt_metadata_entry=prompt_metadata.get("emphasis_rules"),
                jd_facts=jd_facts,
                classification=classification,
                research=research,
                stakeholder_surface=stakeholder_surface,
                pain_point_intelligence=pain_point_intelligence,
                llm_call_schema_valid=emphasis_llm_schema_valid,
                cross_validator_violations=cross_validator_violations,
            ),
        )
        if emphasis_rules.defaults_applied and not emphasis_rules_defaulted:
            ctx.tracer.record_event(
                "scout.preenrich.presentation_contract.emphasis_rules.fail_open",
                {
                    "reason": "role_family_defaults",
                    "defaults_applied": list(emphasis_rules.defaults_applied),
                    "stage_name": ctx.stage_name or self.name,
                    "job_id": _job_id(ctx),
                },
            )

        stage_output = artifact.model_dump()
        stage_output["trace_ref"] = {"trace_id": ctx.tracer.trace_id, "trace_url": ctx.tracer.trace_url}
        return StageResult(
            stage_output=stage_output,
            artifact_writes=[
                ArtifactWrite(
                    collection="presentation_contract",
                    unique_filter={
                        "job_id": artifact.job_id,
                        "input_snapshot_id": artifact.input_snapshot_id,
                    },
                    document=stage_output,
                    ref_name="presentation_contract",
                )
            ],
            provider_used=ctx.config.provider,
            model_used=ctx.config.primary_model,
            prompt_version=PROMPT_VERSION,
        )
