"""Pydantic models for iteration-4.1 blueprint artifacts and snapshot allow-list."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.layer1_4.claude_jd_extractor import (
    CandidateArchetype,
    CompetencyWeightsModel,
    ExtractedJDModel,
    IdealCandidateProfileModel,
    RemotePolicy,
    RoleCategory,
    SeniorityLevel,
)


class EvidenceRef(BaseModel):
    source: str
    locator: str | None = None
    quote: str | None = None


class DeterministicField(BaseModel):
    value: Any
    locator: str | None = None


class JDJudgeAddition(BaseModel):
    field: str
    value: Any
    evidence_span: EvidenceRef
    confidence: Literal["high", "medium", "low"] = "high"


class JDJudgeFlag(BaseModel):
    field: str
    deterministic_value: Any | None = None
    proposed_value: Any | None = None
    severity: Literal["info", "warn", "blocking"] = "warn"
    reasoning: str
    evidence_span: EvidenceRef
    confidence: Literal["high", "medium", "low"] = "medium"


def _normalize_slug(value: Any) -> Any:
    if hasattr(value, "value"):
        value = getattr(value, "value")
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.startswith("rolecategory."):
        return normalized.split(".", 1)[1]
    if normalized.startswith("senioritylevel."):
        return normalized.split(".", 1)[1]
    if normalized.startswith("candidatearchetype."):
        return normalized.split(".", 1)[1]
    return normalized


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        items = [str(item).strip() for item in value]
    return [item for item in items if item]


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        items = _normalize_string_list(value)
        return "\n".join(items) if items else None
    if isinstance(value, dict):
        if value.get("name") and value.get("value"):
            return f"{str(value.get('name')).strip()}: {str(value.get('value')).strip()}".strip(": ") or None
        for key in ("text", "summary", "value", "description", "bullet", "reason", "title", "label", "basis"):
            candidate = _coerce_text(value.get(key))
            if candidate:
                return candidate
        return None
    text = str(value).strip()
    return text or None


def _coerce_detail_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = _coerce_text(value)
    return {"text": text} if text else {}


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _coerce_rich_entry(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        return dict(item)
    if isinstance(item, CompanySignal):
        return item.model_dump()
    text = _coerce_text(item)
    if not text:
        return None
    return {"text": text, "description": text}


def _coerce_confidence_payload(value: Any, *, fallback_basis: str | None = None) -> dict[str, Any]:
    if isinstance(value, ConfidenceDoc):
        return value.model_dump()
    if isinstance(value, dict):
        payload = dict(value)
        nested_confidence = payload.get("confidence")
        nested_evidence = payload.get("evidence")
        score = payload.get("score")
        band = payload.get("band")
        if isinstance(nested_confidence, dict):
            score = nested_confidence.get("score", score)
            band = nested_confidence.get("band", band)
        elif isinstance(nested_confidence, (int, float)) and score is None:
            score = nested_confidence
        basis = (
            _coerce_text(payload.get("basis"))
            or _coerce_text(payload.get("text"))
            or _coerce_text(payload.get("summary"))
            or _coerce_text(payload.get("description"))
        )
        evidence_summary = (
            _coerce_text(payload.get("evidence_summary"))
            or basis
            or _coerce_text(payload.get("evidence_basis"))
            or _coerce_text(nested_evidence)
        )
        unresolved_items = payload.get("unresolved_items")
        sanitized = {
            "score": score if score is not None else 0.0,
            "band": _normalize_slug(band) if band is not None else "unresolved",
            "basis": basis or fallback_basis or "No supporting evidence available.",
            "evidence_summary": evidence_summary,
            "unresolved_items": unresolved_items if unresolved_items is not None else [],
        }
        if sanitized["band"] not in {"high", "medium", "low", "unresolved"}:
            sanitized["band"] = "unresolved"
        return sanitized
    if isinstance(value, (int, float)):
        score = max(0.0, min(1.0, float(value)))
        if score >= 0.8:
            band = "high"
        elif score >= 0.5:
            band = "medium"
        elif score >= 0.2:
            band = "low"
        else:
            band = "unresolved"
        return {"score": score, "band": band, "basis": fallback_basis or "numeric_confidence"}
    basis = _coerce_text(value)
    if basis:
        return {"score": 0.5, "band": "medium", "basis": basis}
    return {"score": 0.0, "band": "unresolved", "basis": fallback_basis or "No supporting evidence available."}


def _coerce_company_signal(item: Any) -> dict[str, Any] | None:
    if isinstance(item, CompanySignal):
        return item.model_dump()
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return {"type": "other", "description": text, "source_ids": []}
    if not isinstance(item, dict):
        text = _coerce_text(item)
        if not text:
            return None
        return {"type": "other", "description": text, "source_ids": []}
    payload = dict(item)
    raw_type = _normalize_slug(payload.get("type") or payload.get("name") or "other")
    allowed_types = {
        "funding",
        "acquisition",
        "leadership_change",
        "product_launch",
        "partnership",
        "growth",
        "layoff",
        "regulatory",
        "ai_initiative",
        "customer_win",
        "other",
    }
    signal_type = raw_type if raw_type in allowed_types else "other"
    description = _coerce_text(payload.get("description"))
    value_text = _coerce_text(payload.get("value"))
    name_text = _coerce_text(payload.get("name"))
    if not description:
        if name_text and value_text:
            description = f"{name_text}: {value_text}"
        else:
            description = value_text or name_text
    if not description:
        return None
    source_ids = _normalize_string_list(payload.get("source_ids"))
    if not source_ids and isinstance(payload.get("evidence"), list):
        for evidence in payload.get("evidence") or []:
            if isinstance(evidence, dict):
                source_ids.extend(_normalize_string_list(evidence.get("source_ids")))
    return {
        "type": signal_type,
        "description": description,
        "date": _coerce_text(payload.get("date")),
        "source_ids": list(dict.fromkeys(source_ids)),
        "business_context": _coerce_text(payload.get("business_context") or payload.get("basis") or payload.get("evidence")),
    }


def normalize_application_surface_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    application = dict(raw.get("application_profile") or raw)
    debug_context = {
        key: value
        for key, value in raw.items()
        if key not in {"application_profile"} and value not in (None, [], {}, "")
    }
    status = _normalize_slug(application.get("status") or application.get("resolution_status") or "unresolved")
    if status not in {"resolved", "partial", "unresolved", "ambiguous", "skipped"}:
        status = "unresolved"
    resolution_status = _normalize_slug(application.get("resolution_status") or status)
    if resolution_status not in {"resolved", "partial", "unresolved", "ambiguous"}:
        resolution_status = "partial" if status == "partial" else "unresolved"
    ui_actionability = _normalize_slug(application.get("ui_actionability") or "unknown")
    ui_actionability = {
        "applyable": "ready",
        "actionable": "ready",
        "applyable_with_caution": "caution",
        "not_actionable": "blocked",
    }.get(ui_actionability, ui_actionability)
    if ui_actionability not in {"ready", "caution", "blocked", "unknown"}:
        ui_actionability = "unknown"
    form_fetch_status = _normalize_slug(application.get("form_fetch_status") or "not_attempted")
    form_fetch_status = {
        "unavailable": "not_attempted",
        "unknown": "not_attempted",
        "not_fetched": "not_attempted",
    }.get(form_fetch_status, form_fetch_status)
    if form_fetch_status not in {"fetched", "blocked", "not_attempted"}:
        form_fetch_status = "not_attempted"
    stale_signal = _normalize_slug(application.get("stale_signal") or "unknown")
    stale_signal = {"stale": "likely_stale", "inactive": "likely_stale"}.get(stale_signal, stale_signal)
    if stale_signal not in {"active", "likely_stale", "closed", "unknown"}:
        stale_signal = "unknown"
    closed_signal = _normalize_slug(application.get("closed_signal") or "unknown")
    closed_signal = {"active": "open", "inactive": "closed"}.get(closed_signal, closed_signal)
    if closed_signal not in {"open", "closed", "unknown"}:
        closed_signal = "unknown"
    apply_instruction_lines = _normalize_string_list(application.get("apply_instructions"))
    apply_instructions = _coerce_text(application.get("apply_instructions"))
    if not apply_instructions and apply_instruction_lines:
        apply_instructions = "\n".join(apply_instruction_lines)
    geo_normalization = application.get("geo_normalization")
    if isinstance(geo_normalization, str):
        geo_normalization = {"raw": geo_normalization}
    elif not isinstance(geo_normalization, dict):
        geo_normalization = {}
    duplicate_signal = application.get("duplicate_signal")
    if duplicate_signal is None:
        duplicate_signal = {}
    elif isinstance(duplicate_signal, list):
        duplicate_signal = {"duplicates": _normalize_string_list(duplicate_signal)}
    elif not isinstance(duplicate_signal, dict):
        duplicate_signal = {"raw": _coerce_text(duplicate_signal)}
    normalized = dict(application)
    normalized.update(
        {
            "status": status,
            "resolution_status": resolution_status,
            "ui_actionability": ui_actionability,
            "form_fetch_status": form_fetch_status,
            "stale_signal": stale_signal,
            "closed_signal": closed_signal,
            "duplicate_signal": duplicate_signal,
            "geo_normalization": geo_normalization,
            "apply_instructions": apply_instructions,
            "apply_instruction_lines": apply_instruction_lines,
            "resolution_confidence": _coerce_confidence_payload(
                application.get("resolution_confidence") or application.get("confidence"),
                fallback_basis="application_surface_normalized",
            ),
            "confidence": _coerce_confidence_payload(
                application.get("confidence") or application.get("resolution_confidence"),
                fallback_basis="application_surface_normalized",
            ),
            "debug_context": debug_context or application.get("debug_context") or {},
        }
    )
    return normalized


def normalize_company_profile_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    signals_input = raw.get("signals") if raw.get("signals") is not None else raw.get("signals_rich")
    recent_signals_input = raw.get("recent_signals") if raw.get("recent_signals") is not None else raw.get("recent_signals_rich")
    role_relevant_input = (
        raw.get("role_relevant_signals")
        if raw.get("role_relevant_signals") is not None
        else raw.get("role_relevant_signals_rich")
    )
    signals_raw = _coerce_list(signals_input)
    recent_signals_raw = _coerce_list(recent_signals_input)
    role_relevant_raw = _coerce_list(role_relevant_input)
    normalized = dict(raw)
    normalized["summary"] = _coerce_text(raw.get("summary"))
    normalized["mission_summary"] = _coerce_text(raw.get("mission_summary"))
    normalized["product_summary"] = _coerce_text(raw.get("product_summary"))
    normalized["business_model"] = _coerce_text(raw.get("business_model"))
    normalized["canonical_name"] = _coerce_text(raw.get("canonical_name"))
    normalized["canonical_domain"] = _coerce_text(raw.get("canonical_domain"))
    normalized["canonical_url"] = _coerce_text(raw.get("canonical_url"))
    normalized["url"] = _coerce_text(raw.get("url")) or normalized.get("canonical_url")
    normalized["identity_basis"] = _coerce_text(raw.get("identity_basis"))
    normalized["identity_confidence"] = _coerce_confidence_payload(
        raw.get("identity_confidence") or raw.get("confidence"),
        fallback_basis="company_profile_normalized",
    )
    normalized["confidence"] = _coerce_confidence_payload(
        raw.get("confidence") or raw.get("identity_confidence"),
        fallback_basis="company_profile_normalized",
    )
    normalized["signals"] = [item for item in (_coerce_company_signal(entry) for entry in signals_raw) if item]
    normalized["recent_signals"] = [item for item in (_coerce_company_signal(entry) for entry in recent_signals_raw) if item]
    normalized["role_relevant_signals"] = [item for item in (_coerce_company_signal(entry) for entry in role_relevant_raw) if item]
    normalized["signals_rich"] = [item for item in (_coerce_rich_entry(entry) for entry in signals_raw) if item]
    normalized["recent_signals_rich"] = [item for item in (_coerce_rich_entry(entry) for entry in recent_signals_raw) if item]
    normalized["role_relevant_signals_rich"] = [item for item in (_coerce_rich_entry(entry) for entry in role_relevant_raw) if item]
    normalized["identity_detail"] = _coerce_detail_dict(raw.get("identity_detail") or raw.get("canonical_name"))
    normalized["mission_detail"] = _coerce_detail_dict(raw.get("mission_detail") or raw.get("mission_summary"))
    normalized["product_detail"] = _coerce_detail_dict(raw.get("product_detail") or raw.get("product_summary"))
    normalized["business_model_detail"] = _coerce_detail_dict(raw.get("business_model_detail") or raw.get("business_model"))
    company_type = _normalize_slug(raw.get("company_type"))
    normalized["company_type"] = company_type if company_type in {"employer", "recruitment_agency", "unknown"} else "unknown"
    normalized["customers_and_market"] = _coerce_detail_dict(raw.get("customers_and_market"))
    scale_signals_raw = raw.get("scale_signals")
    normalized["scale_signals"] = (
        dict(scale_signals_raw)
        if isinstance(scale_signals_raw, dict)
        else {"items": scale_signals_raw}
        if isinstance(scale_signals_raw, list) and scale_signals_raw
        else {}
    )
    normalized["ai_data_platform_maturity"] = _coerce_detail_dict(raw.get("ai_data_platform_maturity"))
    team_org_raw = raw.get("team_org_signals")
    normalized["team_org_signals"] = (
        dict(team_org_raw)
        if isinstance(team_org_raw, dict)
        else {"items": team_org_raw}
        if isinstance(team_org_raw, list) and team_org_raw
        else {}
    )
    funding_raw = raw.get("funding_signals")
    normalized["funding_signals"] = funding_raw if isinstance(funding_raw, list) else []
    normalized["status"] = _normalize_slug(raw.get("status") or ("completed" if normalized.get("summary") else "partial"))
    if normalized["status"] not in {"completed", "partial", "unresolved", "no_research"}:
        normalized["status"] = "partial"
    return normalized


def normalize_role_profile_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = dict(raw)
    normalized["summary"] = _coerce_text(raw.get("summary"))
    normalized["role_summary"] = _coerce_text(raw.get("role_summary")) or normalized.get("summary")
    normalized["why_now"] = _coerce_text(raw.get("why_now"))
    normalized["company_context_alignment"] = _coerce_text(raw.get("company_context_alignment"))
    normalized["summary_detail"] = _coerce_detail_dict(raw.get("summary"))
    normalized["role_summary_detail"] = _coerce_detail_dict(raw.get("role_summary"))
    normalized["why_now_detail"] = _coerce_detail_dict(raw.get("why_now"))
    normalized["company_context_alignment_detail"] = _coerce_detail_dict(raw.get("company_context_alignment"))
    normalized["mandate"] = _normalize_string_list(raw.get("mandate"))
    normalized["business_impact"] = _normalize_string_list(raw.get("business_impact"))
    normalized["success_metrics"] = _normalize_string_list(raw.get("success_metrics"))
    collaboration_raw = raw.get("collaboration_map")
    if isinstance(collaboration_raw, list):
        normalized["collaboration_map"] = [item for item in collaboration_raw if isinstance(item, dict)]
    elif isinstance(collaboration_raw, dict):
        normalized["collaboration_map"] = [dict(collaboration_raw)]
    else:
        normalized["collaboration_map"] = []
    reporting_line_raw = raw.get("reporting_line")
    normalized["reporting_line"] = dict(reporting_line_raw) if isinstance(reporting_line_raw, dict) else {}
    org_placement_raw = raw.get("org_placement")
    normalized["org_placement"] = dict(org_placement_raw) if isinstance(org_placement_raw, dict) else {}
    normalized["interview_themes"] = _normalize_string_list(raw.get("interview_themes"))
    normalized["evaluation_signals"] = _normalize_string_list(raw.get("evaluation_signals"))
    normalized["risk_landscape"] = _normalize_string_list(raw.get("risk_landscape"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="role_profile_normalized")
    normalized["status"] = _normalize_slug(raw.get("status") or ("completed" if normalized.get("summary") else "partial"))
    if normalized["status"] not in {"completed", "partial", "unresolved", "no_research"}:
        normalized["status"] = "partial"
    return normalized


def normalize_stakeholder_record_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = dict(raw)
    normalized.pop("title", None)
    normalized.pop("company", None)
    normalized.pop("relationship", None)
    normalized["current_title"] = _coerce_text(raw.get("current_title") or raw.get("title"))
    normalized["current_company"] = _coerce_text(raw.get("current_company") or raw.get("company"))
    normalized["relationship_to_role"] = _coerce_text(raw.get("relationship_to_role") or raw.get("relationship"))
    normalized["identity_basis"] = _coerce_text(raw.get("identity_basis"))
    normalized["evidence_basis"] = _coerce_text(raw.get("evidence_basis"))
    normalized["identity_confidence"] = _coerce_confidence_payload(
        raw.get("identity_confidence") or raw.get("confidence"),
        fallback_basis="stakeholder_identity_normalized",
    )
    normalized["confidence"] = _coerce_confidence_payload(
        raw.get("confidence") or raw.get("identity_confidence"),
        fallback_basis="stakeholder_confidence_normalized",
    )
    return normalized


def normalize_public_professional_decision_style_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = {
        "evidence_preference": _normalize_slug(raw.get("evidence_preference") or "unresolved"),
        "risk_posture": _normalize_slug(raw.get("risk_posture") or "unresolved"),
        "speed_vs_rigor": _normalize_slug(raw.get("speed_vs_rigor") or "unresolved"),
        "communication_style": _normalize_slug(raw.get("communication_style") or "unresolved"),
        "authority_orientation": _normalize_slug(raw.get("authority_orientation") or "unresolved"),
        "technical_vs_business_bias": _normalize_slug(raw.get("technical_vs_business_bias") or "unresolved"),
    }
    defaults = {
        "evidence_preference": {"metrics_and_systems", "scope_and_ownership", "narrative_and_impact", "unresolved"},
        "risk_posture": {"quality_first", "speed_first", "balanced", "unresolved"},
        "speed_vs_rigor": {"speed_first", "balanced", "rigor_first", "unresolved"},
        "communication_style": {"concise_substantive", "narrative", "formal", "hype_averse", "unresolved"},
        "authority_orientation": {"credibility_over_title", "title_sensitive", "unresolved"},
        "technical_vs_business_bias": {"technical_first", "balanced", "business_first", "unresolved"},
    }
    for key, allowed in defaults.items():
        if normalized[key] not in allowed:
            normalized[key] = "unresolved"
    return normalized


def normalize_cv_preference_surface_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = dict(raw)
    normalized["review_objectives"] = _normalize_string_list(raw.get("review_objectives"))
    normalized["preferred_signal_order"] = _normalize_string_list(raw.get("preferred_signal_order"))
    normalized["preferred_header_bias"] = _normalize_string_list(raw.get("preferred_header_bias"))
    normalized["preferred_tone"] = _normalize_string_list(raw.get("preferred_tone"))
    normalized["preferred_evidence_types"] = _normalize_string_list(raw.get("preferred_evidence_types"))
    normalized["title_match_preference"] = _normalize_slug(raw.get("title_match_preference") or "unresolved")
    normalized["keyword_bias"] = _normalize_slug(raw.get("keyword_bias") or "unresolved")
    normalized["ai_section_preference"] = _normalize_slug(raw.get("ai_section_preference") or "unresolved")
    normalized["evidence_basis"] = _coerce_text(raw.get("evidence_basis"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="cv_preference_surface_normalized")
    return normalized


def normalize_stakeholder_evaluation_profile_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = dict(raw)
    if raw.get("stakeholder_record_snapshot") and isinstance(raw.get("stakeholder_record_snapshot"), dict):
        normalized["stakeholder_record_snapshot"] = normalize_stakeholder_record_payload(raw.get("stakeholder_record_snapshot"))
    normalized["stakeholder_type"] = _normalize_slug(raw.get("stakeholder_type") or "hiring_manager")
    normalized["role_in_process"] = _coerce_text(raw.get("role_in_process"))
    style = raw.get("public_professional_decision_style")
    normalized["public_professional_decision_style"] = (
        normalize_public_professional_decision_style_payload(style) if isinstance(style, dict) else None
    )
    cv_surface = raw.get("cv_preference_surface")
    normalized["cv_preference_surface"] = (
        normalize_cv_preference_surface_payload(cv_surface) if isinstance(cv_surface, dict) else None
    )
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="stakeholder_evaluation_profile_normalized")
    normalized["status"] = _normalize_slug(raw.get("status") or "partial")
    if normalized["status"] not in {"completed", "partial", "identity_only"}:
        normalized["status"] = "partial"
    return normalized


def normalize_inferred_stakeholder_persona_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    normalized = dict(raw)
    normalized["persona_type"] = _normalize_slug(raw.get("persona_type"))
    normalized["coverage_gap"] = _normalize_slug(raw.get("coverage_gap") or raw.get("persona_type"))
    normalized["role_in_process"] = _coerce_text(raw.get("role_in_process"))
    normalized["emitted_because"] = _normalize_slug(raw.get("emitted_because") or "coverage_gap_despite_real")
    normalized["trigger_basis"] = _normalize_string_list(raw.get("trigger_basis"))
    style = raw.get("public_professional_decision_style")
    normalized["public_professional_decision_style"] = (
        normalize_public_professional_decision_style_payload(style) if isinstance(style, dict) else None
    )
    cv_surface = raw.get("cv_preference_surface")
    normalized["cv_preference_surface"] = (
        normalize_cv_preference_surface_payload(cv_surface) if isinstance(cv_surface, dict) else None
    )
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["evidence_basis"] = _coerce_text(raw.get("evidence_basis")) or "inferred persona from role and company context"
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="inferred_stakeholder_persona_normalized")
    return normalized


def normalize_search_journal_entry_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    outcome = _normalize_slug(raw.get("outcome") or "miss")
    outcome_aliases = {
        "hit_but_no_named_people": "miss",
        "hit_no_named_people": "miss",
        "no_named_people": "miss",
        "no_named_person": "miss",
        "named_people_ambiguous": "ambiguous",
        "cross_company_candidate": "rejected_fabrication",
    }
    return {
        "step": _normalize_slug(raw.get("step") or "discovery"),
        "query": _coerce_text(raw.get("query")),
        "intent": _coerce_text(raw.get("intent")),
        "source_type": _coerce_text(raw.get("source_type")),
        "outcome": outcome_aliases.get(outcome, outcome),
        "source_ids": _normalize_string_list(raw.get("source_ids")),
        "notes": _coerce_text(raw.get("notes")),
    }


class RemoteLocationDetail(BaseModel):
    remote_anywhere: bool | None = None
    remote_regions: list[str] = Field(default_factory=list)
    timezone_expectations: list[str] = Field(default_factory=list)
    travel_expectation: str | None = None
    onsite_expectation: str | None = None
    location_constraints: list[str] = Field(default_factory=list)
    relocation_support: str | None = None
    primary_locations: list[str] = Field(default_factory=list)
    secondary_locations: list[str] = Field(default_factory=list)
    geo_scope: Literal["single_city", "multi_city", "country", "region", "global", "not_specified"] | None = None
    work_authorization_notes: str | None = None

    @field_validator(
        "remote_regions",
        "timezone_expectations",
        "location_constraints",
        "primary_locations",
        "secondary_locations",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class Expectations(BaseModel):
    explicit_outcomes: list[str] = Field(default_factory=list)
    delivery_expectations: list[str] = Field(default_factory=list)
    leadership_expectations: list[str] = Field(default_factory=list)
    communication_expectations: list[str] = Field(default_factory=list)
    collaboration_expectations: list[str] = Field(default_factory=list)
    first_90_day_expectations: list[str] = Field(default_factory=list)

    @field_validator(
        "explicit_outcomes",
        "delivery_expectations",
        "leadership_expectations",
        "communication_expectations",
        "collaboration_expectations",
        "first_90_day_expectations",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class IdentitySignals(BaseModel):
    primary_identity: str | None = None
    alternate_identities: list[str] = Field(default_factory=list)
    identity_evidence: list[str] = Field(default_factory=list)
    career_stage_signals: list[str] = Field(default_factory=list)

    @field_validator("alternate_identities", "identity_evidence", "career_stage_signals", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class SkillDimensionProfile(BaseModel):
    communication_skills: list[str] = Field(default_factory=list)
    leadership_skills: list[str] = Field(default_factory=list)
    delivery_skills: list[str] = Field(default_factory=list)
    architecture_skills: list[str] = Field(default_factory=list)
    process_skills: list[str] = Field(default_factory=list)
    stakeholder_skills: list[str] = Field(default_factory=list)

    @field_validator(
        "communication_skills",
        "leadership_skills",
        "delivery_skills",
        "architecture_skills",
        "process_skills",
        "stakeholder_skills",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class TeamContext(BaseModel):
    team_size: str | None = None
    reporting_to: str | None = None
    org_scope: str | None = None
    management_scope: str | None = None


class ExpectationWeights(BaseModel):
    delivery: int
    communication: int
    leadership: int
    collaboration: int
    strategic_scope: int

    @field_validator("delivery", "communication", "leadership", "collaboration", "strategic_scope", mode="before")
    @classmethod
    def normalize_ints(cls, value: Any) -> int:
        return int(value)

    @field_validator("strategic_scope")
    @classmethod
    def validate_sum(cls, value: int, info: Any) -> int:
        data = info.data
        total = value
        for key in ("delivery", "communication", "leadership", "collaboration"):
            total += int(data.get(key, 0))
        if total != 100:
            raise ValueError("weighting_profiles.expectation_weights must sum to 100")
        return value


class OperatingStyleWeights(BaseModel):
    autonomy: int
    ambiguity: int
    pace: int
    process_rigor: int
    stakeholder_exposure: int

    @field_validator("autonomy", "ambiguity", "pace", "process_rigor", "stakeholder_exposure", mode="before")
    @classmethod
    def normalize_ints(cls, value: Any) -> int:
        return int(value)

    @field_validator("stakeholder_exposure")
    @classmethod
    def validate_sum(cls, value: int, info: Any) -> int:
        data = info.data
        total = value
        for key in ("autonomy", "ambiguity", "pace", "process_rigor"):
            total += int(data.get(key, 0))
        if total != 100:
            raise ValueError("weighting_profiles.operating_style_weights must sum to 100")
        return value


class WeightingProfiles(BaseModel):
    expectation_weights: ExpectationWeights | None = None
    operating_style_weights: OperatingStyleWeights | None = None


class LanguageRequirements(BaseModel):
    required_languages: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    fluency_expectations: list[str] = Field(default_factory=list)
    language_notes: str | None = None

    @field_validator("required_languages", "preferred_languages", "fluency_expectations", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class AnalysisFieldConfidence(BaseModel):
    role_category: Literal["high", "medium", "low"] | None = None
    seniority_level: Literal["high", "medium", "low"] | None = None
    ideal_candidate_profile: Literal["high", "medium", "low"] | None = None
    rich_contract: Literal["high", "medium", "low"] | None = None


class AnalysisSourceCoverage(BaseModel):
    used_structured_sections: bool | None = None
    used_raw_excerpt: bool | None = None
    tail_coverage: Literal["full", "partial", "unknown"] | None = None
    truncation_risk: Literal["none", "low", "medium", "high"] | None = None


class AnalysisQualityChecks(BaseModel):
    competency_weights_sum_100: bool | None = None
    weighting_profile_sums_valid: bool | None = None
    top_keywords_ranked: bool | None = None
    duplicate_list_items_removed: bool | None = None


class AnalysisMetadata(BaseModel):
    overall_confidence: Literal["high", "medium", "low"] | None = None
    field_confidence: AnalysisFieldConfidence | None = None
    inferred_fields: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    source_coverage: AnalysisSourceCoverage | None = None
    quality_checks: AnalysisQualityChecks | None = None

    @field_validator("inferred_fields", "ambiguities", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class JDFactsExtractionOutput(ExtractedJDModel):
    """Runner-parity extraction output with preenrich-only transport extras."""

    salary_range: str | None = None
    application_url: str | None = None
    remote_location_detail: RemoteLocationDetail | None = None
    expectations: Expectations | None = None
    identity_signals: IdentitySignals | None = None
    skill_dimension_profile: SkillDimensionProfile | None = None
    team_context: TeamContext | None = None
    weighting_profiles: WeightingProfiles | None = None
    operating_signals: list[str] = Field(default_factory=list)
    ambiguity_signals: list[str] = Field(default_factory=list)
    language_requirements: LanguageRequirements | None = None
    analysis_metadata: AnalysisMetadata | None = None
    company_description: str | None = None
    role_description: str | None = None
    residual_context: str | None = None

    @field_validator("role_category", mode="before")
    @classmethod
    def normalize_role_category(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("seniority_level", mode="before")
    @classmethod
    def normalize_seniority_level(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("remote_policy", mode="before")
    @classmethod
    def normalize_remote_policy(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("responsibilities", "qualifications", "nice_to_haves", "technical_skills", "soft_skills", "implied_pain_points", "success_metrics", "top_keywords", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("operating_signals", "ambiguity_signals", mode="before")
    @classmethod
    def normalize_rich_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("ideal_candidate_profile", mode="before")
    @classmethod
    def normalize_ideal_candidate_profile(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "archetype" in payload:
            payload["archetype"] = _normalize_slug(payload["archetype"])
        for key in ("key_traits", "culture_signals"):
            if key in payload:
                payload[key] = _normalize_string_list(payload[key])
        return payload

    def to_compat_projection(self) -> dict[str, Any]:
        """Compatibility projection for level-2.extracted_jd consumers."""
        extracted = self.to_extracted_jd()
        extracted["company_name"] = self.company
        extracted["required_qualifications"] = list(self.qualifications)
        extracted["key_responsibilities"] = list(self.responsibilities)
        if self.salary_range:
            extracted["salary"] = self.salary_range
        return extracted


class JDFactsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_text_hash: str
    extractor_version: str
    judge_prompt_version: str
    deterministic: dict[str, Any] = Field(default_factory=dict)
    llm_additions: list[JDJudgeAddition] = Field(default_factory=list)
    llm_flags: list[JDJudgeFlag] = Field(default_factory=list)
    confirmations: dict[str, bool] = Field(default_factory=dict)
    extraction: JDFactsExtractionOutput | None = None
    merged_view: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, str] = Field(default_factory=dict)


class ClassificationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_matches: list[str] = Field(default_factory=list)
    responsibility_matches: list[str] = Field(default_factory=list)
    qualification_matches: list[str] = Field(default_factory=list)
    keyword_matches: list[str] = Field(default_factory=list)
    competency_anchor_match: dict[str, int] = Field(default_factory=dict)
    archetype_matches: list[str] = Field(default_factory=list)
    section_refs: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        alias_map = {
            "title": "title_matches",
            "responsibilities": "responsibility_matches",
            "qualifications": "qualification_matches",
            "keywords": "keyword_matches",
            "archetype": "archetype_matches",
        }
        for source_key, target_key in alias_map.items():
            if target_key not in payload and source_key in payload:
                payload[target_key] = payload.pop(source_key)
        return payload

    @field_validator(
        "title_matches",
        "responsibility_matches",
        "qualification_matches",
        "keyword_matches",
        "archetype_matches",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class JdFactsAgreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agrees: bool
    jd_facts_role_category: str | None = None
    reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_agreement_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if "agrees" in payload:
            return payload

        agreement_signals = []
        for key in ("overall", "role_category", "title", "seniority_level"):
            marker = payload.get(key)
            if isinstance(marker, bool):
                agreement_signals.append(marker)
        agrees = payload.get("overall")
        if not isinstance(agrees, bool):
            agrees = any(agreement_signals)
        return {
            "agrees": bool(agrees),
            "jd_facts_role_category": payload.get("jd_facts_role_category"),
            "reason": payload.get("reason") or "llm_structured_agreement",
        }

    @field_validator("jd_facts_role_category", mode="before")
    @classmethod
    def normalize_role(cls, value: Any) -> Any:
        return _normalize_slug(value)


class PreScoreEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: RoleCategory
    score: float
    matched_signal_count: int = 0
    evidence: ClassificationEvidence = Field(default_factory=ClassificationEvidence)


class AITaxonomyDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_ai_job: bool = False
    primary_specialization: str | None = None
    secondary_specializations: list[str] = Field(default_factory=list)
    intensity: Literal["none", "adjacent", "significant", "core"] = "none"
    scope_tags: list[str] = Field(default_factory=list)
    legacy_ai_categories: list[str] = Field(default_factory=list)
    rationale: str | None = None

    @field_validator("primary_specialization", mode="before")
    @classmethod
    def normalize_specialization(cls, value: Any) -> Any:
        return _normalize_slug(value)

    @field_validator("secondary_specializations", "scope_tags", "legacy_ai_categories", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ClassificationDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_role_category: RoleCategory
    secondary_role_categories: list[str] = Field(default_factory=list)
    search_profiles: list[str] = Field(default_factory=list)
    selector_profiles: list[str] = Field(default_factory=list)
    tone_family: str
    taxonomy_version: str
    ambiguity_score: float = 0.0
    confidence: Literal["high", "medium", "low"] = "low"
    reason_codes: list[str] = Field(default_factory=list)
    evidence: ClassificationEvidence = Field(default_factory=ClassificationEvidence)
    jd_facts_agreement: JdFactsAgreement = Field(
        default_factory=lambda: JdFactsAgreement(agrees=False, jd_facts_role_category=None, reason="missing_jd_facts_role_category")
    )
    pre_score: list[PreScoreEntry] = Field(default_factory=list)
    decision_path: str = "heuristic"
    model_used: str | None = None
    provider_used: str | None = None
    prompt_version: str | None = None
    ai_taxonomy: AITaxonomyDoc = Field(default_factory=AITaxonomyDoc)
    ai_relevance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: Any) -> str:
        if isinstance(value, (int, float)):
            score = float(value)
            if score >= 0.8:
                return "high"
            if score >= 0.5:
                return "medium"
            return "low"
        normalized = _normalize_slug(value)
        if normalized in {"high", "medium", "low"}:
            return normalized
        return "low"

    @field_validator("ambiguity_score", mode="before")
    @classmethod
    def normalize_ambiguity_score(cls, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.0

    @field_validator("decision_path", mode="before")
    @classmethod
    def normalize_decision_path(cls, value: Any) -> str:
        if isinstance(value, list):
            items = _normalize_string_list(value)
            return " | ".join(items)
        text = _coerce_text(value)
        return text or "heuristic"

    @field_validator("secondary_role_categories", mode="before")
    @classmethod
    def normalize_secondary_categories(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("reason_codes", mode="before")
    @classmethod
    def normalize_reason_codes(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("ai_relevance", mode="before")
    @classmethod
    def normalize_ai_relevance(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            text = _coerce_text(value)
            return {"rationale": text} if text else {}
        payload = dict(value)
        if "is_ai_job" not in payload and "relevant" in payload:
            payload["is_ai_job"] = bool(payload.get("relevant"))
        if "categories" in payload:
            payload["categories"] = _normalize_string_list(payload.get("categories"))
        return payload

    @model_validator(mode="after")
    def sync_ai_relevance(self) -> "ClassificationDoc":
        if "is_ai_job" not in self.ai_relevance:
            self.ai_relevance["is_ai_job"] = bool(self.ai_taxonomy.is_ai_job)
        if "categories" not in self.ai_relevance:
            self.ai_relevance["categories"] = list(self.ai_taxonomy.legacy_ai_categories or [])
        if "rationale" not in self.ai_relevance:
            self.ai_relevance["rationale"] = self.ai_taxonomy.rationale
        return self


class ConfidenceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = 0.0
    band: Literal["high", "medium", "low", "unresolved"] = "unresolved"
    basis: str = "No supporting evidence available."
    evidence_summary: str | None = None
    unresolved_items: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.0

    @field_validator("unresolved_items", mode="before")
    @classmethod
    def normalize_unresolved_items(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("evidence_summary", mode="after")
    @classmethod
    def sync_evidence_summary(cls, value: str | None, info: Any) -> str:
        if value:
            return value
        basis = str(info.data.get("basis") or "").strip()
        return basis or "No supporting evidence available."


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    url: str | None = None
    source_type: str = "unknown"
    fetched_at: str | None = None
    trust_tier: Literal["primary", "secondary", "tertiary"] = "tertiary"
    title: str | None = None
    domain: str | None = None
    relevance: str | None = None


class EvidenceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    source_ids: list[str] = Field(default_factory=list)
    excerpt: str | None = None
    basis: str | None = None

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_source_ids(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("excerpt")
    @classmethod
    def validate_excerpt_length(cls, value: str | None) -> str | None:
        if value and len(value) > 240:
            raise ValueError("evidence excerpts must be <= 240 characters")
        return value


class CompanySignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "funding",
        "acquisition",
        "leadership_change",
        "product_launch",
        "partnership",
        "growth",
        "layoff",
        "regulatory",
        "ai_initiative",
        "customer_win",
        "other",
    ] = "other"
    description: str
    date: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    business_context: str | None = None

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_signal_sources(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    url: str | None = None
    signals: list[CompanySignal] = Field(default_factory=list)
    canonical_name: str | None = None
    canonical_domain: str | None = None
    canonical_url: str | None = None
    identity_confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    identity_basis: str | None = None
    identity_detail: dict[str, Any] = Field(default_factory=dict)
    company_type: Literal["employer", "recruitment_agency", "unknown"] = "unknown"
    mission_summary: str | None = None
    mission_detail: dict[str, Any] = Field(default_factory=dict)
    product_summary: str | None = None
    product_detail: dict[str, Any] = Field(default_factory=dict)
    business_model: str | None = None
    business_model_detail: dict[str, Any] = Field(default_factory=dict)
    customers_and_market: dict[str, Any] = Field(default_factory=dict)
    scale_signals: dict[str, Any] = Field(default_factory=dict)
    funding_signals: list[dict[str, Any]] = Field(default_factory=list)
    ai_data_platform_maturity: dict[str, Any] = Field(default_factory=dict)
    team_org_signals: dict[str, Any] = Field(default_factory=dict)
    recent_signals: list[CompanySignal] = Field(default_factory=list)
    role_relevant_signals: list[CompanySignal] = Field(default_factory=list)
    signals_rich: list[dict[str, Any]] = Field(default_factory=list)
    recent_signals_rich: list[dict[str, Any]] = Field(default_factory=list)
    role_relevant_signals_rich: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    status: Literal["completed", "partial", "unresolved", "no_research"] = "unresolved"

    @model_validator(mode="after")
    def sync_company_urls(self) -> "CompanyProfile":
        if not self.url:
            self.url = self.canonical_url
        if not self.canonical_url:
            self.canonical_url = self.url
        return self


class RoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str | None = None
    summary_detail: dict[str, Any] = Field(default_factory=dict)
    role_summary: str | None = None
    role_summary_detail: dict[str, Any] = Field(default_factory=dict)
    mandate: list[str] = Field(default_factory=list)
    business_impact: list[str] = Field(default_factory=list)
    why_now: str | None = None
    why_now_detail: dict[str, Any] = Field(default_factory=dict)
    success_metrics: list[str] = Field(default_factory=list)
    collaboration_map: list[dict[str, Any]] = Field(default_factory=list)
    reporting_line: dict[str, Any] = Field(default_factory=dict)
    org_placement: dict[str, Any] = Field(default_factory=dict)
    interview_themes: list[str] = Field(default_factory=list)
    evaluation_signals: list[str] = Field(default_factory=list)
    risk_landscape: list[str] = Field(default_factory=list)
    company_context_alignment: str | None = None
    company_context_alignment_detail: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    status: Literal["completed", "partial", "unresolved", "no_research"] = "unresolved"

    @field_validator(
        "mandate",
        "business_impact",
        "success_metrics",
        "interview_themes",
        "evaluation_signals",
        "risk_landscape",
        mode="before",
    )
    @classmethod
    def normalize_role_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def sync_summary_aliases(self) -> "RoleProfile":
        if not self.summary:
            self.summary = self.role_summary
        if not self.role_summary:
            self.role_summary = self.summary
        return self


class GuidanceBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullet: str
    basis: str | None = None
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_bullet_sources(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class GuidanceActionBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullet: str
    dimension: Literal["opening_angle", "value_signal", "credibility_marker", "what_to_skip", "cta", "logistics"] | None = None
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_action_sources(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class GuidanceAvoidBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullet: str
    reason: str | None = None
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_avoid_sources(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class InitialOutreachGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what_they_likely_care_about: list[GuidanceBullet] = Field(default_factory=list)
    initial_cold_interaction_guidance: list[GuidanceActionBullet] = Field(default_factory=list)
    avoid_in_initial_contact: list[GuidanceAvoidBullet] = Field(default_factory=list)
    confidence_and_basis: ConfidenceDoc = Field(default_factory=ConfidenceDoc)


class ApplicationSurfaceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["resolved", "partial", "unresolved", "ambiguous", "skipped"] = "unresolved"
    job_url: str | None = None
    application_url: str | None = None
    canonical_application_url: str | None = None
    redirect_chain: list[str] = Field(default_factory=list)
    last_verified_at: str | None = None
    final_http_status: int | str | None = "unknown"
    resolution_method: str | None = None
    resolution_confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    resolution_status: Literal["resolved", "partial", "unresolved", "ambiguous"] = "unresolved"
    resolution_note: str | None = None
    ui_actionability: Literal["ready", "caution", "blocked", "unknown"] = "unknown"
    portal_family: str | None = None
    ats_vendor: str | None = None
    is_direct_apply: bool | None = None
    account_creation_likely: bool | None = None
    multi_step_likely: bool | None = None
    form_fetch_status: Literal["fetched", "blocked", "not_attempted"] = "not_attempted"
    stale_signal: Literal["active", "likely_stale", "closed", "unknown"] = "unknown"
    closed_signal: Literal["open", "closed", "unknown"] = "unknown"
    duplicate_signal: dict[str, Any] = Field(default_factory=dict)
    geo_normalization: dict[str, Any] = Field(default_factory=dict)
    apply_instructions: str | None = None
    apply_instruction_lines: list[str] = Field(default_factory=list)
    apply_caveats: list[str] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    candidates: list[str] = Field(default_factory=list)
    friction_signals: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    debug_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("apply_instruction_lines", "apply_caveats", "candidates", "friction_signals", "notes", mode="before")
    @classmethod
    def normalize_application_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def sync_application_urls(self) -> "ApplicationSurfaceDoc":
        if not self.application_url:
            self.application_url = self.canonical_application_url
        if not self.apply_instruction_lines and self.apply_instructions:
            self.apply_instruction_lines = [self.apply_instructions]
        if not self.apply_instructions and self.apply_instruction_lines:
            self.apply_instructions = "\n".join(self.apply_instruction_lines)
        return self


class ApplicationProfile(ApplicationSurfaceDoc):
    model_config = ConfigDict(extra="forbid")


StakeholderType = Literal[
    "recruiter",
    "hiring_manager",
    "skip_level_leader",
    "peer_technical",
    "cross_functional_partner",
    "executive_sponsor",
    "unknown",
]
EvaluatorRole = Literal[
    "recruiter",
    "hiring_manager",
    "skip_level_leader",
    "peer_technical",
    "cross_functional_partner",
    "executive_sponsor",
]


class StakeholderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stakeholder_type: StakeholderType = "unknown"
    identity_status: Literal["resolved", "ambiguous", "unresolved"] = "unresolved"
    identity_confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    identity_basis: str | None = None
    matched_signal_classes: list[str] = Field(default_factory=list)
    candidate_rank: int | None = None
    name: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    profile_url: str | None = None
    source_trail: list[str] = Field(default_factory=list)
    function: str | None = None
    seniority: str | None = None
    relationship_to_role: str | None = None
    likely_influence: str | None = None
    public_professional_background: dict[str, Any] = Field(default_factory=dict)
    public_communication_signals: dict[str, Any] = Field(default_factory=dict)
    working_style_signals: list[str] = Field(default_factory=list)
    likely_priorities: list[GuidanceBullet] = Field(default_factory=list)
    initial_outreach_guidance: InitialOutreachGuidance | None = None
    avoid_points: list[GuidanceAvoidBullet] = Field(default_factory=list)
    evidence_basis: str | None = None
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    unresolved_markers: list[str] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)

    @field_validator(
        "matched_signal_classes",
        "source_trail",
        "working_style_signals",
        "unresolved_markers",
        mode="before",
    )
    @classmethod
    def normalize_stakeholder_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("profile_url")
    @classmethod
    def reject_constructed_profile_urls(cls, value: str | None) -> str | None:
        if value and "linkedin.com/in/" in value and value.endswith("/in/"):
            raise ValueError("constructed LinkedIn URLs are not allowed")
        return value

    @model_validator(mode="after")
    def sync_alias_fields(self) -> "StakeholderRecord":
        direct_signal_classes = {
            "jd_named_person",
            "ats_named_person",
            "official_team_page_named_person",
        }
        matched = set(self.matched_signal_classes or [])
        if self.identity_confidence.band in {"medium", "high"}:
            if not (matched & direct_signal_classes) and len(matched) < 2:
                raise ValueError(
                    "medium/high stakeholder identity requires a direct signal class or two distinct matched_signal_classes"
                )
        if self.initial_outreach_guidance is not None and self.identity_confidence.band in {"low", "unresolved"}:
            raise ValueError("outreach guidance requires medium or high stakeholder identity confidence")
        guidance = self.initial_outreach_guidance
        if guidance:
            if not self.likely_priorities:
                self.likely_priorities = list(guidance.what_they_likely_care_about)
            if not self.avoid_points:
                self.avoid_points = list(guidance.avoid_in_initial_contact)
            if not self.evidence_basis:
                self.evidence_basis = guidance.confidence_and_basis.evidence_summary
            self.confidence = guidance.confidence_and_basis
        elif self.confidence.band == "unresolved":
            self.confidence = self.identity_confidence
            if not self.evidence_basis:
                self.evidence_basis = self.identity_basis
        return self


class PublicProfessionalDecisionStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_preference: Literal["metrics_and_systems", "scope_and_ownership", "narrative_and_impact", "unresolved"] = "unresolved"
    risk_posture: Literal["quality_first", "speed_first", "balanced", "unresolved"] = "unresolved"
    speed_vs_rigor: Literal["speed_first", "balanced", "rigor_first", "unresolved"] = "unresolved"
    communication_style: Literal["concise_substantive", "narrative", "formal", "hype_averse", "unresolved"] = "unresolved"
    authority_orientation: Literal["credibility_over_title", "title_sensitive", "unresolved"] = "unresolved"
    technical_vs_business_bias: Literal["technical_first", "balanced", "business_first", "unresolved"] = "unresolved"


class CVPreferenceSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_objectives: list[str] = Field(default_factory=list)
    preferred_signal_order: list[str] = Field(default_factory=list)
    preferred_evidence_types: list[
        Literal[
            "named_systems",
            "scale_markers",
            "metrics",
            "ownership_scope",
            "decision_tradeoffs",
            "team_outcomes",
            "product_outcomes",
        ]
    ] = Field(default_factory=list)
    preferred_header_bias: list[str] = Field(default_factory=list)
    title_match_preference: Literal["strict", "moderate", "lenient", "unresolved"] = "unresolved"
    keyword_bias: Literal["high", "medium", "low", "unresolved"] = "unresolved"
    ai_section_preference: Literal["dedicated_if_core", "embedded_only", "discouraged", "unresolved"] = "unresolved"
    preferred_tone: list[str] = Field(default_factory=list)
    evidence_basis: str | None = None
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator(
        "review_objectives",
        "preferred_signal_order",
        "preferred_header_bias",
        "preferred_tone",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("preferred_evidence_types", mode="before")
    @classmethod
    def normalize_evidence_types(cls, value: Any) -> list[str]:
        allowed = {
            "named_systems",
            "scale_markers",
            "metrics",
            "ownership_scope",
            "decision_tradeoffs",
            "team_outcomes",
            "product_outcomes",
        }
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        return [item for item in items if item in allowed]

    @field_validator("preferred_signal_order")
    @classmethod
    def reject_cv_section_ids(cls, value: list[str]) -> list[str]:
        forbidden = {
            "title",
            "header",
            "summary",
            "key_achievements",
            "core_competencies",
            "ai_highlights",
            "experience",
            "education",
        }
        for item in value:
            normalized = _normalize_slug(item)
            if normalized in forbidden:
                raise ValueError("preferred_signal_order must use abstract signal categories, not CV section ids")
        return value


class StakeholderEvaluationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stakeholder_ref: str
    stakeholder_record_snapshot: StakeholderRecord
    stakeholder_type: EvaluatorRole
    role_in_process: str | None = None
    public_professional_decision_style: PublicProfessionalDecisionStyle | None = None
    cv_preference_surface: CVPreferenceSurface | None = None
    likely_priorities: list[GuidanceBullet] = Field(default_factory=list)
    likely_reject_signals: list[GuidanceAvoidBullet] = Field(default_factory=list)
    unresolved_markers: list[str] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    status: Literal["completed", "partial", "identity_only"] = "identity_only"

    @field_validator("unresolved_markers", mode="before")
    @classmethod
    def normalize_markers(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class InferredStakeholderPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_id: str
    persona_type: EvaluatorRole
    role_in_process: str | None = None
    emitted_because: Literal["no_real_candidate", "real_search_disabled", "real_ambiguous", "coverage_gap_despite_real"] = "coverage_gap_despite_real"
    trigger_basis: list[str] = Field(default_factory=list)
    coverage_gap: EvaluatorRole
    public_professional_decision_style: PublicProfessionalDecisionStyle | None = None
    cv_preference_surface: CVPreferenceSurface | None = None
    likely_priorities: list[GuidanceBullet] = Field(default_factory=list)
    likely_reject_signals: list[GuidanceAvoidBullet] = Field(default_factory=list)
    unresolved_markers: list[str] = Field(default_factory=list)
    evidence_basis: str
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("trigger_basis", "unresolved_markers", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("evidence_basis")
    @classmethod
    def require_inferred_label(cls, value: str) -> str:
        if "inferred" not in value.lower():
            raise ValueError('persona evidence_basis must contain the literal word "inferred"')
        return value

    @field_validator("confidence", mode="after")
    @classmethod
    def clamp_confidence_band(cls, value: ConfidenceDoc) -> ConfidenceDoc:
        if value.band == "high":
            value.band = "medium"
            if value.score > 0.79:
                value.score = 0.79
        return value


class EvaluatorCoverageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: EvaluatorRole
    required: bool = True
    status: Literal["real", "inferred", "uncovered"] = "uncovered"
    stakeholder_refs: list[str] = Field(default_factory=list)
    persona_refs: list[str] = Field(default_factory=list)
    coverage_confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("stakeholder_refs", "persona_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def validate_status_refs(self) -> "EvaluatorCoverageEntry":
        if self.status == "real":
            if not self.stakeholder_refs or self.persona_refs:
                raise ValueError("real coverage requires stakeholder_refs only")
        elif self.status == "inferred":
            if not self.persona_refs or self.stakeholder_refs:
                raise ValueError("inferred coverage requires persona_refs only")
        else:
            if self.stakeholder_refs or self.persona_refs:
                raise ValueError("uncovered coverage may not include stakeholder_refs or persona_refs")
        return self


class SearchJournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: Literal["preflight", "discovery", "profile", "personas"]
    query: str | None = None
    intent: str | None = None
    source_type: str | None = None
    outcome: Literal["hit", "miss", "ambiguous", "rejected_fabrication"] = "miss"
    source_ids: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("source_ids", mode="before")
    @classmethod
    def normalize_source_ids(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class StakeholderSurfaceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    research_enrichment_id: str | None = None
    input_snapshot_id: str | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    prompt_metadata: dict[str, PromptMetadata] = Field(default_factory=dict)
    status: Literal["completed", "partial", "inferred_only", "unresolved", "no_research", "failed_terminal"] = "unresolved"
    capability_flags: dict[str, Any] = Field(default_factory=dict)
    evaluator_coverage_target: list[EvaluatorRole] = Field(default_factory=list)
    evaluator_coverage: list[EvaluatorCoverageEntry] = Field(default_factory=list)
    real_stakeholders: list[StakeholderEvaluationProfile] = Field(default_factory=list)
    inferred_stakeholder_personas: list[InferredStakeholderPersona] = Field(default_factory=list)
    search_journal: list[SearchJournalEntry] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    unresolved_questions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    timing: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    cache_refs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("evaluator_coverage_target", mode="before")
    @classmethod
    def normalize_coverage_target(cls, value: Any) -> list[str]:
        allowed = {
            "recruiter",
            "hiring_manager",
            "skip_level_leader",
            "peer_technical",
            "cross_functional_partner",
            "executive_sponsor",
        }
        return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in allowed]

    @field_validator("unresolved_questions", "notes", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class PromptMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_id: str | None = None
    prompt_version: str
    prompt_file_path: str
    git_sha: str
    provider: str
    model: str | None = None
    transport_used: str = "none"
    fallback_provider: str | None = None
    fallback_transport: str | None = None


class ResearchEnrichmentDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    classification_id: str | None = None
    application_surface_id: str | None = None
    input_snapshot_id: str | None = None
    research_version: str = "research_enrichment.v4.1.3"
    research_input_hash: str
    prompt_version: str
    prompt_metadata: PromptMetadata | None = None
    provider_used: str | None = None
    model_used: str | None = None
    transport_used: str = "none"
    status: Literal["completed", "partial", "unresolved", "no_research", "failed_terminal"] = "unresolved"
    capability_flags: dict[str, Any] = Field(default_factory=dict)
    company_profile: CompanyProfile = Field(default_factory=CompanyProfile)
    role_profile: RoleProfile = Field(default_factory=RoleProfile)
    application_profile: ApplicationProfile = Field(default_factory=ApplicationProfile)
    stakeholder_intelligence: list[StakeholderRecord] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    notes: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    cache_refs: dict[str, Any] = Field(default_factory=dict)
    timing: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("notes", "unresolved_questions", mode="before")
    @classmethod
    def normalize_research_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class InferenceField(BaseModel):
    field: str
    value: Any
    confidence: Literal["high", "medium"] = "medium"
    evidence_spans: list[EvidenceRef] = Field(default_factory=list)


class JobInferenceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    research_enrichment_id: str | None = None
    prompt_version: str
    taxonomy_version: str
    primary_role_category: str
    tone_family: str
    semantic_role_model: dict[str, Any] = Field(default_factory=dict)
    company_model: dict[str, Any] = Field(default_factory=dict)
    qualifications: dict[str, Any] = Field(default_factory=dict)
    application_surface: ApplicationSurfaceDoc = Field(default_factory=ApplicationSurfaceDoc)
    inferences: list[InferenceField] = Field(default_factory=list)


class JobHypothesis(BaseModel):
    field: str
    value: Any
    confidence: Literal["low"] = "low"
    reasoning: str
    source_hints: list[str] = Field(default_factory=list)


class JobHypothesesDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    research_enrichment_id: str | None = None
    prompt_version: str
    taxonomy_version: str
    hypotheses: list[JobHypothesis] = Field(default_factory=list)


class GuidelineBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    bullets: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: list[EvidenceRef]) -> list[EvidenceRef]:
        if not value:
            raise ValueError("guideline blocks require evidence references")
        return value


class CVGuidelinesDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    jd_facts_id: str
    job_inference_id: str
    research_enrichment_id: str | None = None
    prompt_version: str
    title_guidance: GuidelineBlock
    identity_guidance: GuidelineBlock
    bullet_theme_guidance: GuidelineBlock
    ats_keyword_guidance: GuidelineBlock
    cover_letter_expectations: GuidelineBlock
    skills_guidance: list[GuidelineBlock] = Field(default_factory=list)
    challenges_guidance: list[GuidelineBlock] = Field(default_factory=list)


class JobBlueprintSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: dict[str, Any]
    application_surface: dict[str, Any]
    company_research: dict[str, Any]
    role_research: dict[str, Any]
    research: dict[str, Any] = Field(default_factory=dict)
    cv_guidelines: dict[str, Any]
    pain_points: list[str] = Field(default_factory=list)
    strategic_needs: list[str] = Field(default_factory=list)
    risks_if_unfilled: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    title_guidance: str | None = None
    identity_guidance: str | None = None
    bullet_guidance: list[str] = Field(default_factory=list)
    cover_letter_expectations: list[str] = Field(default_factory=list)


class JobBlueprintDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    blueprint_version: str
    taxonomy_version: str
    jd_facts_id: str
    job_inference_id: str
    research_enrichment_id: str | None = None
    application_surface: ApplicationSurfaceDoc
    cv_guidelines_id: str
    job_hypotheses_id: str | None = None
    snapshot: JobBlueprintSnapshot
    compatibility_projection: dict[str, Any] = Field(default_factory=dict)
