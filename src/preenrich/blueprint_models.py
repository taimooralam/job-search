"""Pydantic models for iteration-4.1/4.2 blueprint artifacts and snapshot allow-list."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from src.layer1_4.claude_jd_extractor import (
    ExtractedJDModel,
    RoleCategory,
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


def _coerce_enum_choice(
    value: Any,
    *,
    allowed: set[str],
    default: str,
    aliases: dict[str, str] | None = None,
) -> str:
    normalized = _normalize_slug(value) if value is not None else default
    if not isinstance(normalized, str):
        return default
    if aliases and normalized in aliases:
        normalized = aliases[normalized]
    return normalized if normalized in allowed else default


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


def _coerce_source_entry_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, SourceEntry):
        return item.model_dump()
    if isinstance(item, str):
        source_id = item.strip()
        if not source_id:
            return None
        return {"source_id": source_id, "source_type": "unknown", "trust_tier": "tertiary"}
    if not isinstance(item, dict):
        return None
    payload = dict(item)
    source_id = _coerce_text(payload.get("source_id") or payload.get("id") or payload.get("source"))
    url = _coerce_text(payload.get("url") or payload.get("href"))
    title = _coerce_text(payload.get("title") or payload.get("label"))
    relevance = _coerce_text(payload.get("relevance") or payload.get("notes") or payload.get("basis"))
    if not source_id:
        source_id = _coerce_text(payload.get("source_ids"))
    if not source_id and url:
        source_id = f"src_{_normalize_slug(title or url) or 'unknown'}"
    if not source_id:
        return None
    trust_tier = _coerce_enum_choice(
        payload.get("trust_tier"),
        allowed={"primary", "secondary", "tertiary"},
        default="tertiary",
    )
    return {
        "source_id": source_id,
        "url": url,
        "source_type": _coerce_text(payload.get("source_type")) or "unknown",
        "fetched_at": _coerce_text(payload.get("fetched_at") or payload.get("observed_at") or payload.get("date")),
        "trust_tier": trust_tier,
        "title": title,
        "domain": _coerce_text(payload.get("domain")),
        "relevance": relevance,
    }


def _coerce_source_entries(value: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _coerce_list(value):
        payload = _coerce_source_entry_payload(item)
        source_id = payload.get("source_id") if isinstance(payload, dict) else None
        if not payload or not isinstance(source_id, str) or source_id in seen:
            continue
        seen.add(source_id)
        entries.append(payload)
    return entries


def _coerce_evidence_entry_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, EvidenceEntry):
        return item.model_dump()
    if not isinstance(item, dict):
        claim = _coerce_text(item)
        return {"claim": claim, "source_ids": []} if claim else None
    payload = dict(item)
    claim = _coerce_text(payload.get("claim") or payload.get("text") or payload.get("summary") or payload.get("description"))
    if not claim:
        return None
    return {
        "claim": claim,
        "source_ids": _normalize_string_list(payload.get("source_ids")),
        "excerpt": _coerce_text(payload.get("excerpt")),
        "basis": _coerce_text(payload.get("basis")),
    }


def _coerce_evidence_entries(value: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in _coerce_list(value):
        payload = _coerce_evidence_entry_payload(item)
        if not payload:
            continue
        key = (payload["claim"], tuple(payload.get("source_ids") or []))
        if key in seen:
            continue
        seen.add(key)
        entries.append(payload)
    return entries


def _coerce_guidance_bullet_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, GuidanceBullet):
        return item.model_dump()
    if not isinstance(item, dict):
        bullet = _coerce_text(item)
        return {"bullet": bullet, "basis": None, "source_ids": []} if bullet else None
    payload = dict(item)
    bullet = _coerce_text(payload.get("bullet") or payload.get("text") or payload.get("summary") or payload.get("claim"))
    if not bullet:
        return None
    return {
        "bullet": bullet,
        "basis": _coerce_text(payload.get("basis") or payload.get("reason") or payload.get("notes")),
        "source_ids": _normalize_string_list(payload.get("source_ids")),
    }


def _coerce_guidance_avoid_bullet_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, GuidanceAvoidBullet):
        return item.model_dump()
    if not isinstance(item, dict):
        bullet = _coerce_text(item)
        return {"bullet": bullet, "reason": None, "source_ids": []} if bullet else None
    payload = dict(item)
    bullet = _coerce_text(payload.get("bullet") or payload.get("text") or payload.get("summary") or payload.get("claim"))
    if not bullet:
        return None
    return {
        "bullet": bullet,
        "reason": _coerce_text(payload.get("reason") or payload.get("basis") or payload.get("notes")),
        "source_ids": _normalize_string_list(payload.get("source_ids")),
    }


def _coerce_guidance_bullets(value: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in _coerce_list(value):
        payload = _coerce_guidance_bullet_payload(item)
        if not payload:
            continue
        key = (payload["bullet"], tuple(payload.get("source_ids") or []))
        if key in seen:
            continue
        seen.add(key)
        entries.append(payload)
    return entries


def _coerce_guidance_avoid_bullets(value: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for item in _coerce_list(value):
        payload = _coerce_guidance_avoid_bullet_payload(item)
        if not payload:
            continue
        key = (payload["bullet"], tuple(payload.get("source_ids") or []))
        if key in seen:
            continue
        seen.add(key)
        entries.append(payload)
    return entries


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
    normalized["canonical_name"] = _coerce_text(raw.get("canonical_name")) or _coerce_text(raw.get("company_name")) or _coerce_text(raw.get("company"))
    normalized["canonical_domain"] = _coerce_text(raw.get("canonical_domain")) or _coerce_text(raw.get("company_domain"))
    normalized["canonical_url"] = _coerce_text(raw.get("canonical_url")) or _coerce_text(raw.get("company_url"))
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
    normalized["sources"] = _coerce_source_entries(raw.get("sources"))
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))
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
    allowed_keys = {
        "summary",
        "url",
        "signals",
        "canonical_name",
        "canonical_domain",
        "canonical_url",
        "identity_confidence",
        "identity_basis",
        "identity_detail",
        "company_type",
        "mission_summary",
        "mission_detail",
        "product_summary",
        "product_detail",
        "business_model",
        "business_model_detail",
        "customers_and_market",
        "scale_signals",
        "funding_signals",
        "ai_data_platform_maturity",
        "team_org_signals",
        "recent_signals",
        "role_relevant_signals",
        "signals_rich",
        "recent_signals_rich",
        "role_relevant_signals_rich",
        "sources",
        "evidence",
        "confidence",
        "status",
    }
    return {key: normalized.get(key) for key in allowed_keys}


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
    normalized["matched_signal_classes"] = _normalize_string_list(raw.get("matched_signal_classes"))
    normalized["source_trail"] = _normalize_string_list(raw.get("source_trail"))
    normalized["working_style_signals"] = _normalize_string_list(raw.get("working_style_signals"))
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["sources"] = _coerce_source_entries(raw.get("sources"))
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))
    normalized["likely_priorities"] = _coerce_guidance_bullets(raw.get("likely_priorities"))
    normalized["avoid_points"] = _coerce_guidance_avoid_bullets(raw.get("avoid_points") or raw.get("likely_reject_signals"))
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
    normalized.pop("evidence", None)
    normalized.pop("status", None)
    normalized["review_objectives"] = _normalize_string_list(raw.get("review_objectives"))
    normalized["preferred_signal_order"] = _normalize_string_list(raw.get("preferred_signal_order"))
    normalized["preferred_header_bias"] = _normalize_string_list(raw.get("preferred_header_bias"))
    normalized["preferred_tone"] = _normalize_string_list(raw.get("preferred_tone"))
    normalized["preferred_evidence_types"] = _normalize_string_list(raw.get("preferred_evidence_types"))
    normalized["title_match_preference"] = _coerce_enum_choice(
        raw.get("title_match_preference"),
        allowed={"strict", "moderate", "lenient", "unresolved"},
        default="unresolved",
        aliases={
            "high": "strict",
            "exact": "strict",
            "strong": "strict",
            "medium": "moderate",
            "balanced": "moderate",
            "normal": "moderate",
            "low": "lenient",
            "loose": "lenient",
            "flexible": "lenient",
        },
    )
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
    nested_cv_surface_evidence = _coerce_evidence_entries(cv_surface.get("evidence")) if isinstance(cv_surface, dict) else []
    normalized["cv_preference_surface"] = (
        normalize_cv_preference_surface_payload(cv_surface) if isinstance(cv_surface, dict) else None
    )
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["likely_priorities"] = _coerce_guidance_bullets(raw.get("likely_priorities"))
    normalized["likely_reject_signals"] = _coerce_guidance_avoid_bullets(raw.get("likely_reject_signals"))
    normalized["sources"] = _coerce_source_entries(raw.get("sources"))
    root_evidence = _coerce_evidence_entries(raw.get("evidence"))
    normalized["evidence"] = root_evidence + [entry for entry in nested_cv_surface_evidence if entry not in root_evidence]
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
    normalized["emitted_because"] = _coerce_enum_choice(
        raw.get("emitted_because"),
        allowed={"no_real_candidate", "real_search_disabled", "real_ambiguous", "coverage_gap_despite_real"},
        default="coverage_gap_despite_real",
        aliases={
            "coverage_gap_despite_no_real_candidate": "no_real_candidate",
            "coverage_gap_despite_no_real_candidates": "no_real_candidate",
            "missing_coverage_types_in_input_context": "coverage_gap_despite_real",
            "missing_coverage_type_in_input_context": "coverage_gap_despite_real",
            "no_real_candidates": "no_real_candidate",
            "real_search_failed": "real_search_disabled",
            "real_candidates_ambiguous": "real_ambiguous",
        },
    )
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
    normalized["likely_priorities"] = _coerce_guidance_bullets(raw.get("likely_priorities"))
    normalized["likely_reject_signals"] = _coerce_guidance_avoid_bullets(raw.get("likely_reject_signals"))
    normalized["sources"] = _coerce_source_entries(raw.get("sources"))
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="inferred_stakeholder_persona_normalized")
    return normalized


def normalize_search_journal_entry_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    raw_outcome = _normalize_slug(raw.get("outcome") or "miss")
    if raw_outcome in {"hit", "miss", "ambiguous", "rejected_fabrication"}:
        outcome = raw_outcome
    elif isinstance(raw_outcome, str) and "cross_company" in raw_outcome:
        outcome = "rejected_fabrication"
    elif isinstance(raw_outcome, str) and "ambiguous" in raw_outcome:
        outcome = "ambiguous"
    elif isinstance(raw_outcome, str) and any(token in raw_outcome for token in {"no_named", "no_person", "no_people"}):
        outcome = "miss"
    elif isinstance(raw_outcome, str) and any(token in raw_outcome for token in {"hit", "found", "resolved"}):
        outcome = "hit"
    else:
        outcome = "miss"
    step = _normalize_slug(raw.get("step") or "discovery")
    intent = _normalize_slug(raw.get("intent"))
    if step in {"preflight", "discovery", "profile", "personas"}:
        normalized_step = step
    elif any(token in (step or "") for token in ("persona", "coverage")) or any(token in (intent or "") for token in ("persona", "coverage")):
        normalized_step = "personas"
    elif "profile" in (step or "") or "profile" in (intent or ""):
        normalized_step = "profile"
    elif any(token in (step or "") for token in ("preflight", "setup", "bootstrap")):
        normalized_step = "preflight"
    else:
        # Search-journal drift is usually a discovery substep label rather than a real stage change.
        normalized_step = "discovery"
    return {
        "step": normalized_step,
        "query": _coerce_text(raw.get("query")),
        "intent": _coerce_text(raw.get("intent")),
        "source_type": _coerce_text(raw.get("source_type")),
        "outcome": outcome,
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


PresentationContractStatus = Literal["completed", "partial", "inferred_only", "unresolved", "failed_terminal"]
TitleStrategyEnum = Literal["exact_match", "closest_truthful", "functional_label", "unresolved"]
PrimaryDocumentGoal = Literal[
    "architecture_first",
    "delivery_first",
    "leadership_first",
    "ai_first",
    "platform_first",
    "transformation_first",
    "balanced",
    "unresolved",
]
PresentationSectionId = Literal[
    "header",
    "summary",
    "key_achievements",
    "core_competencies",
    "ai_highlights",
    "experience",
    "education",
    "certifications",
    "projects",
    "publications",
    "awards",
]
DocumentSectionIdEnum = PresentationSectionId
ProofCategory = Literal["metric", "architecture", "leadership", "domain", "reliability", "ai", "stakeholder", "process", "compliance", "scale"]
ProofType = ProofCategory
DocumentAntiPatternId = Literal[
    "tool_list_cv",
    "hype_header",
    "metrics_without_scope",
    "scope_without_metrics",
    "titles_without_proof",
    "ai_claims_without_evidence",
    "buzzword_stacking",
    "narrative_only_summary",
    "skill_cloud_without_ordering",
    "generic_mission_restatement",
]
CompressionRuleId = Literal[
    "compress_core_competencies_first",
    "compress_certifications_second",
    "compress_projects_third",
]
OmissionRuleId = Literal[
    "omit_publications_if_unused_in_role_family",
    "omit_awards_if_unused_in_role_family",
    "omit_ai_highlights_if_policy_discouraged",
    "omit_projects_if_experience_is_dominant",
]
RuleTypeEnum = Literal[
    "allowed_if_evidenced",
    "prefer_softened_form",
    "omit_if_weak",
    "forbid_without_direct_proof",
    "never_infer_from_job_only",
    "cap_dimension_weight",
    "require_credibility_marker",
    "require_proof_for_emphasis",
    "suppress_audience_variant_signal",
]
RuleTopicFamily = Literal[
    "title_inflation",
    "ai_claims",
    "leadership_scope",
    "architecture_claims",
    "domain_expertise",
    "stakeholder_management_claims",
    "metrics_scale_claims",
    "credibility_ladder_degradation",
    "tooling_inflation",
    "process_methodology_claims",
    "compliance_regulatory_claims",
    "keyword_stuffing",
    "narrative_overreach",
    "audience_variant_specific_softening",
]
AppliesToKindEnum = Literal["section", "proof", "dimension", "audience_variant", "global"]
ExperienceDimension = Literal[
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
ExperienceDimensionSourceScope = Literal["jd_only", "jd_plus_research", "jd_plus_research_plus_stakeholder"]
AudienceVariantKey = EvaluatorRole
OveruseRiskReason = Literal[
    "weak_evidence",
    "stakeholder_reject",
    "role_adjacent",
    "seniority_mismatch",
    "keyword_inflation",
    "saturation",
    "ats_keyword_inflation",
]

DIMENSION_ENUM_VERSION = "v1"
RULE_TYPE_ENUM_VERSION = "v1"
APPLIES_TO_ENUM_VERSION = "v1"

_PRESENTATION_SECTION_IDS = {
    "header",
    "summary",
    "key_achievements",
    "core_competencies",
    "ai_highlights",
    "experience",
    "education",
    "certifications",
    "projects",
    "publications",
    "awards",
}
_PROOF_CATEGORIES = {"metric", "architecture", "leadership", "domain", "reliability", "ai", "stakeholder", "process", "compliance", "scale"}
_DOCUMENT_GOALS = {
    "architecture_first",
    "delivery_first",
    "leadership_first",
    "ai_first",
    "platform_first",
    "transformation_first",
    "balanced",
    "unresolved",
}
_ANTI_PATTERN_IDS = {
    "tool_list_cv",
    "hype_header",
    "metrics_without_scope",
    "scope_without_metrics",
    "titles_without_proof",
    "ai_claims_without_evidence",
    "buzzword_stacking",
    "narrative_only_summary",
    "skill_cloud_without_ordering",
    "generic_mission_restatement",
}
_COMPRESSION_RULE_IDS = {
    "compress_core_competencies_first",
    "compress_certifications_second",
    "compress_projects_third",
}
_OMISSION_RULE_IDS = {
    "omit_publications_if_unused_in_role_family",
    "omit_awards_if_unused_in_role_family",
    "omit_ai_highlights_if_policy_discouraged",
    "omit_projects_if_experience_is_dominant",
}
_EXPERIENCE_DIMENSIONS = {
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
}
_EXPERIENCE_DIMENSION_ORDER = [
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
_EXPERIENCE_DIMENSION_ALIASES = {
    "hands_on": "hands_on_implementation",
    "implementation": "hands_on_implementation",
    "system_design": "architecture_system_design",
    "systems_design": "architecture_system_design",
    "architecture": "architecture_system_design",
    "leadership": "leadership_enablement",
    "technology_stack": "tools_technology_stack",
    "tools_stack": "tools_technology_stack",
    "methodology": "methodology_operating_model",
    "operating_model": "methodology_operating_model",
    "impact": "business_impact",
    "stakeholder": "stakeholder_communication",
    "communication": "stakeholder_communication",
    "ai": "ai_ml_depth",
    "ml": "ai_ml_depth",
    "domain": "domain_context",
    "quality_reliability": "quality_risk_reliability",
    "reliability": "quality_risk_reliability",
    "delivery": "delivery_execution_pace",
    "execution_pace": "delivery_execution_pace",
    "scaling_change": "platform_scaling_change",
    "platform_scaling": "platform_scaling_change",
}
_EXPERIENCE_SOURCE_SCOPES = {"jd_only", "jd_plus_research", "jd_plus_research_plus_stakeholder"}
_OVERUSE_RISK_REASONS = {
    "weak_evidence",
    "stakeholder_reject",
    "role_adjacent",
    "seniority_mismatch",
    "keyword_inflation",
    "saturation",
    "ats_keyword_inflation",
}
_RULE_TYPES = {
    "allowed_if_evidenced",
    "prefer_softened_form",
    "omit_if_weak",
    "forbid_without_direct_proof",
    "never_infer_from_job_only",
    "cap_dimension_weight",
    "require_credibility_marker",
    "require_proof_for_emphasis",
    "suppress_audience_variant_signal",
}
_RULE_TYPE_PRECEDENCE = {
    "allowed_if_evidenced": 20,
    "prefer_softened_form": 50,
    "omit_if_weak": 65,
    "require_credibility_marker": 70,
    "require_proof_for_emphasis": 70,
    "suppress_audience_variant_signal": 75,
    "forbid_without_direct_proof": 80,
    "never_infer_from_job_only": 85,
    "cap_dimension_weight": 80,
}
_RULE_TOPIC_FAMILIES = {
    "title_inflation",
    "ai_claims",
    "leadership_scope",
    "architecture_claims",
    "domain_expertise",
    "stakeholder_management_claims",
    "metrics_scale_claims",
    "credibility_ladder_degradation",
    "tooling_inflation",
    "process_methodology_claims",
    "compliance_regulatory_claims",
    "keyword_stuffing",
    "narrative_overreach",
    "audience_variant_specific_softening",
}
_MANDATORY_RULE_TOPIC_FAMILIES = [
    "title_inflation",
    "ai_claims",
    "leadership_scope",
    "architecture_claims",
    "domain_expertise",
    "stakeholder_management_claims",
    "metrics_scale_claims",
    "credibility_ladder_degradation",
]
_APPLIES_TO_KINDS = {"section", "proof", "dimension", "audience_variant", "global"}
_EMPHASIS_RULE_SOURCE_SCOPES = {"jd_only", "jd_plus_research", "jd_plus_research_plus_stakeholder"}
_EMPHASIS_PATTERN_KINDS = {"substring", "regex_safe"}
_EMPHASIS_FAIL_OPEN_REASONS = {
    "jd_only_fallback",
    "thin_research",
    "thin_stakeholder",
    "thin_pain_point_intelligence",
    "mandatory_topic_coverage_default_filled",
    "schema_repair_exhausted",
    "cross_invariant_suppressed",
    "title_inflation_detected",
    "ai_authorization_above_intensity",
    "leadership_authorization_above_envelope",
    "candidate_leakage_detected",
    "llm_terminal_failure",
    "defaults_only",
}
_EMPHASIS_NORMALIZATION_KINDS = {
    "alias_mapped",
    "enum_clamp",
    "candidate_leakage",
    "conflict_suppressed",
    "conflict_downgraded",
    "conflict_retained",
    "duplicate_collapsed",
    "precedence_assigned",
    "id_renormalized",
}
_TITLE_LEVEL_TOKENS = {
    "vp",
    "vice_president",
    "head",
    "director",
    "principal",
    "staff",
    "lead",
    "senior",
    "manager",
}
_HEADER_DENSITIES = {"compact", "balanced", "proof_dense"}
_AI_SECTION_POLICY_ALLOWED = {
    "core": {"required", "optional"},
    "significant": {"required", "optional", "embedded_only"},
    "adjacent": {"optional", "embedded_only"},
    "none": {"embedded_only", "discouraged"},
    "unknown": {"optional", "embedded_only"},
    "unresolved": {"optional", "embedded_only"},
}
_FIRST_PERSON_PATTERN = re.compile(r"\b(i|my|mine|we|our|ours|me|us)\b", re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_ACHIEVEMENT_NUMBER_PATTERN = re.compile(r"(\b\d+(?:\.\d+)?%|\$\d[\d,]*(?:\.\d+)?|\b\d+x\b)", re.IGNORECASE)
_PRESENTATION_ALLOWED_PROPER_NOUNS = {
    "ats",
    "cv",
    "jd",
    "linkedin",
    "workday",
    "greenhouse",
    "lever",
    "taleo",
    "amazon web services",
    "aws",
    "kubernetes",
    "machine learning",
    "ml",
    "ai",
}


def _normalize_presentation_section_ids(value: Any) -> list[str]:
    return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in _PRESENTATION_SECTION_IDS]


def _normalize_proof_categories(value: Any) -> list[str]:
    return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in _PROOF_CATEGORIES]


def _normalize_anti_pattern_ids(value: Any) -> list[str]:
    return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in _ANTI_PATTERN_IDS]


def _normalize_compression_rule_ids(value: Any) -> list[str]:
    return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in _COMPRESSION_RULE_IDS]


def _normalize_omission_rule_ids(value: Any) -> list[str]:
    return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in _OMISSION_RULE_IDS]


def _normalize_experience_dimension(value: Any) -> str | None:
    normalized = _normalize_slug(value)
    if not isinstance(normalized, str) or not normalized:
        return None
    normalized = _EXPERIENCE_DIMENSION_ALIASES.get(normalized, normalized)
    return normalized if normalized in _EXPERIENCE_DIMENSIONS else None


def _normalize_experience_dimension_list(value: Any) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for item in _coerce_list(value):
        normalized = _normalize_experience_dimension(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
    return items


def _normalize_experience_source_scope(value: Any, *, default: str = "jd_only") -> str:
    normalized = _normalize_slug(value)
    return normalized if normalized in _EXPERIENCE_SOURCE_SCOPES else default


def _normalize_overuse_risk_reason(value: Any) -> str:
    normalized = _normalize_slug(value)
    return normalized if normalized in _OVERUSE_RISK_REASONS else "weak_evidence"


def _normalize_title_strategy(value: Any, *, default: str = "unresolved") -> str:
    normalized = _normalize_slug(value)
    return normalized if normalized in {"exact_match", "closest_truthful", "functional_label", "unresolved"} else default


def _normalize_rule_type(value: Any) -> str | None:
    normalized = _normalize_slug(value)
    return normalized if normalized in _RULE_TYPES else None


def _normalize_rule_topic_family(value: Any) -> str | None:
    normalized = _normalize_slug(value)
    return normalized if normalized in _RULE_TOPIC_FAMILIES else None


def _normalize_applies_to_kind(value: Any) -> str | None:
    normalized = _normalize_slug(value)
    return normalized if normalized in _APPLIES_TO_KINDS else None


def _normalize_emphasis_source_scope(value: Any, *, default: str = "jd_only") -> str:
    normalized = _normalize_slug(value)
    return normalized if normalized in _EMPHASIS_RULE_SOURCE_SCOPES else default


def _normalize_emphasis_fail_open_reason(value: Any) -> str | None:
    normalized = _normalize_slug(value)
    return normalized if normalized in _EMPHASIS_FAIL_OPEN_REASONS else None


def _normalize_rule_precedence(value: Any, *, rule_type: str | None = None) -> int:
    if isinstance(value, bool):
        value = None
    if isinstance(value, int):
        numeric = value
    elif isinstance(value, float):
        numeric = int(value) if value.is_integer() else _RULE_TYPE_PRECEDENCE.get(rule_type or "", 50)
    else:
        text = _coerce_text(value)
        if text and re.fullmatch(r"\d+(?:\.0+)?", text):
            numeric = int(float(text))
        else:
            numeric = _RULE_TYPE_PRECEDENCE.get(rule_type or "", 50)
    return max(0, min(100, numeric))


def _normalize_emphasis_evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for item in _coerce_list(value):
        if isinstance(item, dict):
            text = _coerce_text(item.get("source") or item.get("ref") or item.get("path"))
        else:
            text = _coerce_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append(text)
    return refs


def _canonical_emphasis_text(value: Any, *, limit: int) -> str | None:
    text = _coerce_text(value)
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _canonical_rule_condition(value: Any) -> str:
    text = _canonical_emphasis_text(value, limit=240) or ""
    return re.sub(r"\s+", " ", text.lower()).strip()


def _derive_emphasis_rule_id(
    *,
    topic_family: str,
    applies_to_kind: str,
    applies_to: str,
    condition: str,
) -> str:
    topic = re.sub(r"[^a-z0-9_]+", "_", topic_family.lower()).strip("_")
    target = re.sub(r"[^a-z0-9_]+", "_", applies_to.lower()).strip("_")[:24] or applies_to_kind
    digest = hashlib.sha1(
        f"{topic_family}|{applies_to_kind}|{applies_to}|{_canonical_rule_condition(condition)}".encode("utf-8")
    ).hexdigest()[:6]
    return f"tcer_{topic}_{target}_{digest}"[:64]


def _is_regex_safe_pattern(pattern: str) -> bool:
    if not pattern:
        return False
    if re.search(r"\(\?(?!:)", pattern):
        return False
    if re.search(r"\\[1-9]", pattern):
        return False
    if pattern.count("|") > 3:
        return False
    if re.search(r"\((?!\?:)", pattern):
        return False
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def _normalize_emphasis_pattern_kind(value: Any) -> str:
    normalized = _normalize_slug(value)
    return normalized if normalized in _EMPHASIS_PATTERN_KINDS else "substring"


def _resolve_applies_to_value(
    applies_to: Any,
    *,
    applies_to_kind: str,
) -> str | None:
    text = _coerce_text(applies_to)
    if not text:
        return None
    if applies_to_kind == "section":
        normalized = _normalize_slug(text)
        return normalized if normalized in _PRESENTATION_SECTION_IDS else None
    if applies_to_kind == "proof":
        normalized = _normalize_slug(text)
        return normalized if normalized in _PROOF_CATEGORIES else None
    if applies_to_kind == "dimension":
        return _normalize_experience_dimension(text)
    if applies_to_kind == "audience_variant":
        normalized = _normalize_audience_role_key(text)
        return normalized or None
    if applies_to_kind == "global":
        return "global" if _normalize_slug(text) == "global" else None
    return None


def _infer_applies_to_pair(value: Any) -> tuple[str | None, str | None]:
    text = _coerce_text(value)
    if not text:
        return None, None
    if ":" in text:
        raw_kind, raw_value = text.split(":", 1)
        kind = _normalize_applies_to_kind(raw_kind)
        resolved = _resolve_applies_to_value(raw_value, applies_to_kind=kind or "")
        if kind and resolved:
            return kind, resolved
    candidates: list[tuple[str, str]] = []
    section = _resolve_applies_to_value(text, applies_to_kind="section")
    if section:
        candidates.append(("section", section))
    proof = _resolve_applies_to_value(text, applies_to_kind="proof")
    if proof:
        candidates.append(("proof", proof))
    dimension = _resolve_applies_to_value(text, applies_to_kind="dimension")
    if dimension:
        candidates.append(("dimension", dimension))
    audience = _resolve_applies_to_value(text, applies_to_kind="audience_variant")
    if audience:
        candidates.append(("audience_variant", audience))
    if _normalize_slug(text) == "global":
        candidates.append(("global", "global"))
    if len(candidates) == 1:
        return candidates[0]
    return None, None


def _normalize_audience_role_key(value: Any) -> str:
    normalized = _normalize_slug(value)
    return normalized if isinstance(normalized, str) and normalized in {
        "recruiter",
        "hiring_manager",
        "skip_level_leader",
        "peer_technical",
        "cross_functional_partner",
        "executive_sponsor",
    } else ""


def _allowed_ai_section_policies(ai_intensity: str | None) -> set[str]:
    normalized = _normalize_slug(ai_intensity) if ai_intensity else "unknown"
    return _AI_SECTION_POLICY_ALLOWED.get(normalized or "unknown", {"optional", "embedded_only"})


def _debug_append_event(container: dict[str, Any], key: str, entry: Any) -> None:
    bucket = container.setdefault(key, [])
    if isinstance(bucket, list):
        bucket.append(entry)


def _clean_debug_context(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    cleaned = dict(raw)
    cleaned.setdefault("input_summary", {})
    cleaned.setdefault("defaults_applied", [])
    cleaned.setdefault("normalization_events", [])
    cleaned.setdefault("richer_output_retained", [])
    cleaned.setdefault("rejected_output", [])
    cleaned.setdefault("retry_events", [])
    cleaned_retained_output: list[Any] = []
    for entry in cleaned.get("richer_output_retained") or []:
        if isinstance(entry, dict):
            normalized_entry = dict(entry)
            if not normalized_entry.get("key") and normalized_entry.get("field"):
                normalized_entry["key"] = normalized_entry.pop("field")
            cleaned_retained_output.append(
                {
                    "key": normalized_entry.get("key"),
                    "value": normalized_entry.get("value"),
                    "note": normalized_entry.get("note") or normalized_entry.get("reason"),
                }
            )
        elif isinstance(entry, str):
            cleaned_retained_output.append({"key": entry, "value": None, "note": None})
        else:
            cleaned_retained_output.append(entry)
    cleaned["richer_output_retained"] = cleaned_retained_output
    cleaned_rejected_output: list[Any] = []
    for entry in cleaned.get("rejected_output") or []:
        if isinstance(entry, dict):
            normalized_entry = dict(entry)
            if not normalized_entry.get("path") and normalized_entry.get("field"):
                normalized_entry["path"] = normalized_entry.pop("field")
            cleaned_rejected_output.append(
                {
                    "path": normalized_entry.get("path"),
                    "reason": normalized_entry.get("reason"),
                }
            )
        else:
            cleaned_rejected_output.append(entry)
    cleaned["rejected_output"] = cleaned_rejected_output
    return cleaned


def _candidate_leakage_reason(
    text: str,
    *,
    allowed_company_names: set[str],
    allowed_company_domain: str | None,
    jd_excerpt: str,
    enforce_proper_noun_rule: bool = True,
) -> str | None:
    text.lower()
    if _FIRST_PERSON_PATTERN.search(text):
        return "candidate_leakage_first_person"
    for url in _URL_PATTERN.findall(text):
        if allowed_company_domain and allowed_company_domain in url.lower():
            continue
        return "candidate_leakage_url"
    achievement_match = _ACHIEVEMENT_NUMBER_PATTERN.search(text)
    if achievement_match and achievement_match.group(1).lower() not in jd_excerpt.lower():
        return "candidate_leakage_achievement_number"
    if enforce_proper_noun_rule:
        noun_pairs = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text)
        for noun_pair in noun_pairs:
            if noun_pair.lower() in allowed_company_names or noun_pair.lower() in _PRESENTATION_ALLOWED_PROPER_NOUNS:
                continue
            return "candidate_leakage_proper_noun"
    return None


def _strip_candidate_leakage(
    value: Any,
    *,
    path: str,
    debug_context: dict[str, Any],
    allowed_company_names: set[str],
    allowed_company_domain: str | None,
    jd_excerpt: str,
    enforce_proper_noun_rule: bool = True,
) -> Any:
    if isinstance(value, str):
        reason = _candidate_leakage_reason(
            value,
            allowed_company_names=allowed_company_names,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
            enforce_proper_noun_rule=enforce_proper_noun_rule,
        )
        if reason:
            _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": reason})
            return None
        return value
    if isinstance(value, list):
        sanitized = []
        for index, item in enumerate(value):
            stripped = _strip_candidate_leakage(
                item,
                path=f"{path}[{index}]",
                debug_context=debug_context,
                allowed_company_names=allowed_company_names,
                allowed_company_domain=allowed_company_domain,
                jd_excerpt=jd_excerpt,
                enforce_proper_noun_rule=enforce_proper_noun_rule,
            )
            if stripped not in (None, "", [], {}):
                sanitized.append(stripped)
        return sanitized
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, item in value.items():
            stripped = _strip_candidate_leakage(
                item,
                path=f"{path}.{key}" if path else str(key),
                debug_context=debug_context,
                allowed_company_names=allowed_company_names,
                allowed_company_domain=allowed_company_domain,
                jd_excerpt=jd_excerpt,
                enforce_proper_noun_rule=enforce_proper_noun_rule,
            )
            if stripped not in (None, "", [], {}):
                sanitized_dict[key] = stripped
        return sanitized_dict
    return value


def _coerce_presentation_evidence_ref_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, PresentationEvidenceRefDoc):
        return item.model_dump()
    if isinstance(item, EvidenceRef):
        return {
            "source": _coerce_text(getattr(item, "source", None)),
            "locator": _coerce_text(getattr(item, "locator", None)),
            "quote": _coerce_text(getattr(item, "quote", None)),
        }
    if isinstance(item, str):
        text = item.strip()
        return {"source": text} if text else None
    if not isinstance(item, dict):
        return None
    source = _coerce_text(item.get("source") or item.get("source_ref") or item.get("ref") or item.get("path"))
    if not source:
        return None
    return {
        "source": source,
        "locator": _coerce_text(item.get("locator") or item.get("path")),
        "quote": _coerce_text(item.get("quote") or item.get("excerpt")),
    }


def _coerce_presentation_evidence_refs(value: Any) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = set()
    for item in _coerce_list(value):
        payload = _coerce_presentation_evidence_ref_payload(item)
        if not payload:
            continue
        key = (payload["source"], payload.get("locator"))
        if key in seen:
            continue
        seen.add(key)
        refs.append(payload)
    return refs


class AudienceVariantDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tilt: list[str] = Field(default_factory=list)
    must_see: list[str] = Field(default_factory=list)
    risky_signals: list[str] = Field(default_factory=list)
    rationale: str | None = None

    @field_validator("tilt", "must_see", "risky_signals", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("tilt", "must_see", "risky_signals")
    @classmethod
    def reject_section_ids(cls, value: list[str]) -> list[str]:
        for item in value:
            if _normalize_slug(item) in _PRESENTATION_SECTION_IDS:
                raise ValueError("audience variant fields must use abstract signal tags, not canonical CV section ids")
        return value


class TonePostureDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_tone: Literal["evidence_first", "operator_first", "architect_first", "leader_first", "balanced"] = "balanced"
    hype_tolerance: Literal["low", "medium", "high"] = "medium"
    narrative_tolerance: Literal["low", "medium", "high"] = "medium"
    formality: Literal["informal", "neutral", "formal"] = "neutral"


class SectionDensityBiasDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: PresentationSectionId
    bias: Literal["low", "medium", "high"]

    @field_validator("section_id", mode="before")
    @classmethod
    def normalize_section_id(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _PRESENTATION_SECTION_IDS:
            raise ValueError("section_density_bias.section_id must be a canonical section id")
        return normalized


class DensityPostureDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_density: Literal["low", "medium", "high"] = "medium"
    header_density: Literal["compact", "balanced", "proof_dense"] = "balanced"
    section_density_bias: list[SectionDensityBiasDoc] = Field(default_factory=list)


class KeywordBalanceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_keyword_pressure: Literal["low", "medium", "high", "extreme"] = "medium"
    ats_mirroring_bias: Literal["conservative", "balanced", "aggressive"] = "balanced"
    semantic_expansion_bias: Literal["narrow", "balanced", "broad"] = "balanced"


class PresentationInputSummaryDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_family: str | None = None
    seniority: str | None = None
    ai_intensity: str | None = None
    evaluator_roles_in_scope: list[EvaluatorRole] = Field(default_factory=list)
    proof_category_frequencies: dict[str, int] = Field(default_factory=dict)
    top_keywords_top10: list[str] = Field(default_factory=list)
    company_identity_band: str | None = None
    research_status: str | None = None
    stakeholder_surface_status: str | None = None
    pain_point_intelligence_status: str | None = None

    @field_validator("evaluator_roles_in_scope", mode="before")
    @classmethod
    def normalize_roles(cls, value: Any) -> list[str]:
        return [item for item in (_normalize_audience_role_key(item) for item in _normalize_string_list(value)) if item]

    @field_validator("top_keywords_top10", mode="before")
    @classmethod
    def normalize_keywords(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)[:10]


class PresentationRetainedFieldDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    note: str | None = None


class PresentationRejectedFieldDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class PresentationRetryEventDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repair_reason: str
    repair_attempt: int
    note: str | None = None


class PresentationSubdocDebug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_summary: PresentationInputSummaryDoc = Field(default_factory=PresentationInputSummaryDoc)
    defaults_applied: list[str] = Field(default_factory=list)
    normalization_events: list[str] = Field(default_factory=list)
    richer_output_retained: list[PresentationRetainedFieldDoc] = Field(default_factory=list)
    rejected_output: list[PresentationRejectedFieldDoc] = Field(default_factory=list)
    retry_events: list[PresentationRetryEventDoc] = Field(default_factory=list)

    @field_validator("defaults_applied", "normalization_events", mode="before")
    @classmethod
    def normalize_debug_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class DocumentExpectationsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PresentationContractStatus = "unresolved"
    primary_document_goal: PrimaryDocumentGoal = "unresolved"
    secondary_document_goals: list[PrimaryDocumentGoal] = Field(default_factory=list)
    audience_variants: dict[EvaluatorRole, AudienceVariantDoc] = Field(default_factory=dict)
    proof_order: list[ProofCategory] = Field(default_factory=list)
    anti_patterns: list[DocumentAntiPatternId] = Field(default_factory=list)
    tone_posture: TonePostureDoc = Field(default_factory=TonePostureDoc)
    density_posture: DensityPostureDoc = Field(default_factory=DensityPostureDoc)
    keyword_balance: KeywordBalanceDoc = Field(default_factory=KeywordBalanceDoc)
    unresolved_markers: list[str] = Field(default_factory=list)
    rationale: str | None = None
    debug_context: PresentationSubdocDebug = Field(default_factory=PresentationSubdocDebug)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    evidence: list[EvidenceEntry] = Field(default_factory=list)

    @field_validator("secondary_document_goals", mode="before")
    @classmethod
    def normalize_secondary_goals(cls, value: Any) -> list[str]:
        values = [_normalize_slug(item) for item in _normalize_string_list(value)]
        return [item for item in values if item in _DOCUMENT_GOALS]

    @field_validator("proof_order", mode="before")
    @classmethod
    def normalize_proof_order(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _PROOF_CATEGORIES]
        if invalid:
            raise ValueError(f"proof_order contains non-canonical proof categories: {invalid}")
        return items

    @field_validator("anti_patterns", mode="before")
    @classmethod
    def normalize_anti_patterns(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _ANTI_PATTERN_IDS]
        if invalid:
            raise ValueError(f"anti_patterns contains non-canonical ids: {invalid}")
        return items

    @field_validator("audience_variants", mode="before")
    @classmethod
    def normalize_audience_variants(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, entry in value.items():
            role = _normalize_audience_role_key(key)
            if role:
                normalized[role] = entry
        return normalized

    @field_validator("audience_variants")
    @classmethod
    def validate_audience_variants(cls, value: dict[str, AudienceVariantDoc], info: ValidationInfo) -> dict[str, AudienceVariantDoc]:
        allowed_roles = {item for item in _normalize_string_list((info.context or {}).get("evaluator_coverage_target")) if item}
        if allowed_roles:
            invalid = sorted(role for role in value if role not in allowed_roles)
            if invalid:
                raise ValueError(f"audience_variants keys must be a subset of evaluator_coverage_target: {invalid}")
        return value

    @field_validator("unresolved_markers", mode="before")
    @classmethod
    def normalize_markers(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class HeaderShapeDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    density: Literal["compact", "balanced", "proof_dense"] = "balanced"
    include_elements: list[
        Literal[
            "name",
            "current_or_target_title",
            "tagline",
            "location",
            "links",
            "proof_line",
            "differentiator_line",
        ]
    ] = Field(default_factory=list)
    proof_line_policy: Literal["required", "optional", "omit"] = "optional"
    differentiator_line_policy: Literal["required", "optional", "omit"] = "optional"

    @field_validator("include_elements", mode="before")
    @classmethod
    def normalize_include_elements(cls, value: Any) -> list[str]:
        allowed = {
            "name",
            "current_or_target_title",
            "tagline",
            "location",
            "links",
            "proof_line",
            "differentiator_line",
        }
        return [item for item in (_normalize_slug(item) for item in _normalize_string_list(value)) if item in allowed]


class SectionEmphasisDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: PresentationSectionId
    emphasis: Literal["highlight", "balanced", "secondary", "compress", "omit"] = "balanced"
    focus_categories: list[ProofCategory] = Field(default_factory=list)
    length_bias: Literal["short", "medium", "long"] = "medium"
    ordering_bias: Literal["outcome_first", "scope_first", "tech_first", "narrative_first"] = "outcome_first"
    rationale: str | None = None

    @field_validator("section_id", mode="before")
    @classmethod
    def normalize_section_id(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _PRESENTATION_SECTION_IDS:
            raise ValueError("section_emphasis.section_id must be a canonical section id")
        return normalized

    @field_validator("focus_categories", mode="before")
    @classmethod
    def normalize_focus_categories(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _PROOF_CATEGORIES]
        if invalid:
            raise ValueError(f"focus_categories contains non-canonical proof categories: {invalid}")
        return items


class CvShapeCountsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_achievements_min: int = 0
    key_achievements_max: int = 0
    core_competencies_min: int = 0
    core_competencies_max: int = 0
    summary_sentences_min: int = 0
    summary_sentences_max: int = 0

    @model_validator(mode="after")
    def validate_ranges(self) -> "CvShapeCountsDoc":
        ranges = (
            ("key_achievements", self.key_achievements_min, self.key_achievements_max, 10),
            ("core_competencies", self.core_competencies_min, self.core_competencies_max, 14),
            ("summary_sentences", self.summary_sentences_min, self.summary_sentences_max, 8),
        )
        for label, minimum, maximum, upper in ranges:
            if minimum < 0 or maximum < 0 or minimum > upper or maximum > upper:
                raise ValueError(f"{label} counts must be within 0-{upper}")
            if minimum > maximum:
                raise ValueError(f"{label}_min must be <= {label}_max")
        return self


class ATSEnvelopeDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pressure: Literal["standard", "high", "extreme"] = "standard"
    format_rules: list[str] = Field(default_factory=list)
    keyword_placement_bias: Literal["top_heavy", "balanced", "bottom_heavy"] = "balanced"

    @field_validator("format_rules", mode="before")
    @classmethod
    def normalize_format_rules(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class CvShapeExpectationsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PresentationContractStatus = "unresolved"
    title_strategy: Literal["exact_match", "closest_truthful", "functional_label", "unresolved"] = "unresolved"
    header_shape: HeaderShapeDoc = Field(default_factory=HeaderShapeDoc)
    section_order: list[PresentationSectionId] = Field(default_factory=list)
    section_emphasis: list[SectionEmphasisDoc] = Field(default_factory=list)
    ai_section_policy: Literal["required", "optional", "discouraged", "embedded_only"] = "embedded_only"
    counts: CvShapeCountsDoc = Field(default_factory=CvShapeCountsDoc)
    ats_envelope: ATSEnvelopeDoc = Field(default_factory=ATSEnvelopeDoc)
    evidence_density: Literal["low", "medium", "high"] = "medium"
    seniority_signal_strength: Literal["low", "medium", "high"] = "medium"
    compression_rules: list[CompressionRuleId] = Field(default_factory=list)
    omission_rules: list[OmissionRuleId] = Field(default_factory=list)
    unresolved_markers: list[str] = Field(default_factory=list)
    rationale: str | None = None
    debug_context: PresentationSubdocDebug = Field(default_factory=PresentationSubdocDebug)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    evidence: list[EvidenceEntry] = Field(default_factory=list)

    @field_validator("section_order", mode="before")
    @classmethod
    def normalize_section_order(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _PRESENTATION_SECTION_IDS]
        if invalid:
            raise ValueError(f"section_order contains non-canonical section ids: {invalid}")
        return items

    @field_validator("compression_rules", mode="before")
    @classmethod
    def normalize_compression_rules(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _COMPRESSION_RULE_IDS]
        if invalid:
            raise ValueError(f"compression_rules contains non-canonical ids: {invalid}")
        return items

    @field_validator("omission_rules", mode="before")
    @classmethod
    def normalize_omission_rules(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _OMISSION_RULE_IDS]
        if invalid:
            raise ValueError(f"omission_rules contains non-canonical ids: {invalid}")
        return items

    @field_validator("unresolved_markers", mode="before")
    @classmethod
    def normalize_markers(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("header_shape")
    @classmethod
    def validate_header_density(cls, value: HeaderShapeDoc, info: ValidationInfo) -> HeaderShapeDoc:
        expected = _normalize_slug((info.context or {}).get("document_header_density"))
        if expected and value.density != expected:
            raise ValueError("header_shape.density must match document_expectations.density_posture.header_density")
        return value

    @field_validator("ai_section_policy")
    @classmethod
    def validate_ai_section_policy(cls, value: str, info: ValidationInfo) -> str:
        ai_intensity = (info.context or {}).get("ai_intensity")
        allowed = _allowed_ai_section_policies(ai_intensity)
        if value not in allowed:
            raise ValueError(f"ai_section_policy={value} is incompatible with ai_intensity={ai_intensity}")
        return value

    @model_validator(mode="after")
    def validate_structure(self) -> "CvShapeExpectationsDoc":
        if self.section_order:
            if self.section_order[0] != "header":
                raise ValueError("section_order must begin with header")
            for required in ("summary", "experience"):
                if required not in self.section_order:
                    raise ValueError(f"section_order must include {required}")
        section_set = set(self.section_order)
        for entry in self.section_emphasis:
            if entry.section_id not in section_set:
                raise ValueError("section_emphasis.section_id must be a subset of section_order")
        return self


IdealCandidateSignalTag = Literal[
    "role_fit",
    "recognizable_title",
    "ownership_scope",
    "architecture_judgment",
    "hands_on_implementation",
    "production_impact",
    "ai_depth",
    "leadership_scope",
    "stakeholder_alignment",
    "domain_context",
    "delivery_rigor",
    "platform_reliability",
    "generic_leadership_claim",
    "tool_listing",
]
CredibilityMarkerId = Literal[
    "named_systems",
    "metrics",
    "ownership_scope",
    "cross_functional_influence",
    "production_scale",
    "ai_application",
    "platform_governance",
    "domain_recognition",
]
IdealCandidateRiskFlagId = Literal[
    "title_inflation",
    "generic_ai_claim",
    "leadership_overclaim",
    "domain_overclaim",
    "tool_listing_without_proof",
    "stakeholder_guessing",
]

_IDEAL_CANDIDATE_SIGNAL_TAGS = {
    "role_fit",
    "recognizable_title",
    "ownership_scope",
    "architecture_judgment",
    "hands_on_implementation",
    "production_impact",
    "ai_depth",
    "leadership_scope",
    "stakeholder_alignment",
    "domain_context",
    "delivery_rigor",
    "platform_reliability",
    "generic_leadership_claim",
    "tool_listing",
}
_IDEAL_CANDIDATE_CREDIBILITY_MARKERS = {
    "named_systems",
    "metrics",
    "ownership_scope",
    "cross_functional_influence",
    "production_scale",
    "ai_application",
    "platform_governance",
    "domain_recognition",
}
_IDEAL_CANDIDATE_RISK_FLAGS = {
    "title_inflation",
    "generic_ai_claim",
    "leadership_overclaim",
    "domain_overclaim",
    "tool_listing_without_proof",
    "stakeholder_guessing",
}


class PresentationEvidenceRefDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    locator: str | None = None
    quote: str | None = None

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("evidence_refs.source is required")
        return text

    @field_validator("locator", "quote", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        return _coerce_text(value)


class IdealCandidateSignalDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: IdealCandidateSignalTag
    proof_category: ProofCategory | None = None
    rationale: str | None = None
    evidence_refs: list[PresentationEvidenceRefDoc] = Field(default_factory=list)

    @field_validator("tag", mode="before")
    @classmethod
    def normalize_tag(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _IDEAL_CANDIDATE_SIGNAL_TAGS:
            raise ValueError("ideal candidate signal tag must be canonical")
        return normalized

    @field_validator("proof_category", mode="before")
    @classmethod
    def normalize_proof_category(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        normalized = _normalize_slug(value)
        if normalized not in _PROOF_CATEGORIES:
            raise ValueError("ideal candidate signal proof_category must be canonical")
        return normalized

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_evidence_refs(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_presentation_evidence_refs(value)


class ProofLadderStepDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proof_category: ProofCategory
    signal_tag: IdealCandidateSignalTag
    rationale: str | None = None
    evidence_refs: list[PresentationEvidenceRefDoc] = Field(default_factory=list)

    @field_validator("proof_category", mode="before")
    @classmethod
    def normalize_proof_category(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _PROOF_CATEGORIES:
            raise ValueError("proof_ladder.proof_category must be canonical")
        return normalized

    @field_validator("signal_tag", mode="before")
    @classmethod
    def normalize_signal_tag(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _IDEAL_CANDIDATE_SIGNAL_TAGS:
            raise ValueError("proof_ladder.signal_tag must be canonical")
        return normalized

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_evidence_refs(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_presentation_evidence_refs(value)


class CredibilityMarkerDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marker: CredibilityMarkerId
    proof_category: ProofCategory | None = None
    rationale: str | None = None
    evidence_refs: list[PresentationEvidenceRefDoc] = Field(default_factory=list)

    @field_validator("marker", mode="before")
    @classmethod
    def normalize_marker(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _IDEAL_CANDIDATE_CREDIBILITY_MARKERS:
            raise ValueError("credibility marker must be canonical")
        return normalized

    @field_validator("proof_category", mode="before")
    @classmethod
    def normalize_proof_category(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        normalized = _normalize_slug(value)
        if normalized not in _PROOF_CATEGORIES:
            raise ValueError("credibility marker proof_category must be canonical")
        return normalized

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_evidence_refs(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_presentation_evidence_refs(value)


class IdealCandidateRiskFlagDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: IdealCandidateRiskFlagId
    severity: Literal["low", "medium", "high"] = "medium"
    rationale: str | None = None
    evidence_refs: list[PresentationEvidenceRefDoc] = Field(default_factory=list)

    @field_validator("flag", mode="before")
    @classmethod
    def normalize_flag(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _IDEAL_CANDIDATE_RISK_FLAGS:
            raise ValueError("ideal candidate risk flag must be canonical")
        return normalized

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: Any) -> str:
        return _coerce_enum_choice(value, allowed={"low", "medium", "high"}, default="medium")

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_evidence_refs(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_presentation_evidence_refs(value)


class IdealCandidateAudienceVariantDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tilt: list[str] = Field(default_factory=list)
    must_land: list[IdealCandidateSignalTag] = Field(default_factory=list)
    de_emphasize: list[IdealCandidateSignalTag] = Field(default_factory=list)
    rationale: str | None = None

    @field_validator("tilt", mode="before")
    @classmethod
    def normalize_tilt(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("must_land", "de_emphasize", mode="before")
    @classmethod
    def normalize_signal_lists(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _IDEAL_CANDIDATE_SIGNAL_TAGS]
        if invalid:
            raise ValueError(f"ideal candidate audience signals must be canonical: {invalid}")
        return items

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value: Any) -> str | None:
        return _coerce_text(value)


class IdealCandidatePresentationModelDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PresentationContractStatus = "unresolved"
    visible_identity: str | None = None
    acceptable_titles: list[str] = Field(default_factory=list)
    title_strategy: Literal["exact_match", "closest_truthful", "functional_label", "unresolved"] = "unresolved"
    must_signal: list[IdealCandidateSignalDoc] = Field(default_factory=list)
    should_signal: list[IdealCandidateSignalDoc] = Field(default_factory=list)
    de_emphasize: list[IdealCandidateSignalDoc] = Field(default_factory=list)
    proof_ladder: list[ProofLadderStepDoc] = Field(default_factory=list)
    tone_profile: TonePostureDoc = Field(default_factory=TonePostureDoc)
    credibility_markers: list[CredibilityMarkerDoc] = Field(default_factory=list)
    risk_flags: list[IdealCandidateRiskFlagDoc] = Field(default_factory=list)
    audience_variants: dict[EvaluatorRole, IdealCandidateAudienceVariantDoc] = Field(default_factory=dict)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    defaults_applied: list[str] = Field(default_factory=list)
    unresolved_markers: list[str] = Field(default_factory=list)
    evidence_refs: list[PresentationEvidenceRefDoc] = Field(default_factory=list)
    debug_context: PresentationSubdocDebug = Field(default_factory=PresentationSubdocDebug)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return _coerce_enum_choice(
            value,
            allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
            default="unresolved",
        )

    @field_validator("visible_identity", mode="before")
    @classmethod
    def normalize_visible_identity(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("acceptable_titles", mode="before")
    @classmethod
    def normalize_acceptable_titles(cls, value: Any) -> list[str]:
        titles = []
        seen: set[str] = set()
        for item in _normalize_string_list(value):
            cleaned = item.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            titles.append(cleaned)
        return titles[:5]

    @field_validator("audience_variants", mode="before")
    @classmethod
    def normalize_audience_variants(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, entry in value.items():
            role = _normalize_audience_role_key(key)
            if role:
                normalized[role] = entry
        return normalized

    @field_validator("audience_variants")
    @classmethod
    def validate_audience_variants(cls, value: dict[str, IdealCandidateAudienceVariantDoc], info: ValidationInfo) -> dict[str, IdealCandidateAudienceVariantDoc]:
        allowed_roles = {item for item in _normalize_string_list((info.context or {}).get("evaluator_coverage_target")) if item}
        if allowed_roles:
            invalid = sorted(role for role in value if role not in allowed_roles)
            if invalid:
                raise ValueError(f"ideal candidate audience_variants keys must be a subset of evaluator_coverage_target: {invalid}")
        return value

    @field_validator("title_strategy")
    @classmethod
    def validate_title_strategy(cls, value: str, info: ValidationInfo) -> str:
        expected = _normalize_slug((info.context or {}).get("expected_title_strategy"))
        if expected and value != expected:
            raise ValueError("ideal candidate title_strategy must match cv_shape_expectations.title_strategy")
        return value

    @field_validator("defaults_applied", "unresolved_markers", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_evidence_refs(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_presentation_evidence_refs(value)

    @model_validator(mode="after")
    def validate_structure(self) -> "IdealCandidatePresentationModelDoc":
        if not self.acceptable_titles:
            raise ValueError("ideal candidate acceptable_titles must not be empty")
        seen_titles: set[str] = set()
        for title in self.acceptable_titles:
            lowered = title.lower()
            if lowered in seen_titles:
                raise ValueError("ideal candidate acceptable_titles must be unique")
            seen_titles.add(lowered)
        seen_categories: set[str] = set()
        for step in self.proof_ladder:
            if step.proof_category in seen_categories:
                raise ValueError("ideal candidate proof_ladder proof categories must be unique")
            seen_categories.add(step.proof_category)
        if self.status in {"completed", "partial", "inferred_only"} and not self.proof_ladder:
            raise ValueError("ideal candidate proof_ladder must not be empty when status is not unresolved")
        if self.defaults_applied and self.confidence.band == "high":
            raise ValueError("ideal candidate confidence may not remain high when defaults_applied is non-empty")
        return self


class ExperienceDimensionNormalizationEventDoc(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: str
    from_value: int | str | None = Field(default=None, alias="from")
    to_value: int | str | None = Field(default=None, alias="to")
    reason: str
    path: str | None = None

    @field_validator("kind", "reason", "path", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        return _coerce_text(value)


class ExperienceDimensionOveruseRiskDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ExperienceDimension
    reason: OveruseRiskReason = "weak_evidence"
    threshold: int = 0
    mitigation: Literal["softened_form", "omit", "proof_first"] = "proof_first"

    @field_validator("dimension", mode="before")
    @classmethod
    def normalize_dimension(cls, value: Any) -> str:
        normalized = _normalize_experience_dimension(value)
        if not normalized:
            raise ValueError("overuse_risks[].dimension must be a canonical experience dimension")
        return normalized

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return _normalize_overuse_risk_reason(value)

    @field_validator("threshold", mode="before")
    @classmethod
    def normalize_threshold(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("overuse_risks[].threshold must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError("overuse_risks[].threshold must be an integer")
            return int(value)
        text = _coerce_text(value)
        if text and re.fullmatch(r"\d+(?:\.0+)?", text):
            return int(float(text))
        raise ValueError("overuse_risks[].threshold must be an integer")

    @model_validator(mode="after")
    def validate_threshold(self) -> "ExperienceDimensionOveruseRiskDoc":
        if self.threshold < 0 or self.threshold > 100:
            raise ValueError("overuse_risks[].threshold must be within 0-100")
        return self


class ExperienceDimensionWeightsDebug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_summary: PresentationInputSummaryDoc = Field(default_factory=PresentationInputSummaryDoc)
    role_family_weight_priors: dict[str, int] = Field(default_factory=dict)
    evaluator_dimension_pressure: dict[EvaluatorRole, dict[str, int]] = Field(default_factory=dict)
    ai_intensity_cap: int | None = None
    architecture_evidence_band: Literal["none", "partial", "strong"] = "none"
    leadership_evidence_band: Literal["none", "partial", "strong"] = "none"
    defaults_applied: list[str] = Field(default_factory=list)
    normalization_events: list[ExperienceDimensionNormalizationEventDoc] = Field(default_factory=list)
    richer_output_retained: list[PresentationRetainedFieldDoc] = Field(default_factory=list)
    rejected_output: list[PresentationRejectedFieldDoc] = Field(default_factory=list)
    retry_events: list[PresentationRetryEventDoc] = Field(default_factory=list)

    @field_validator("defaults_applied", mode="before")
    @classmethod
    def normalize_defaults(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class ExperienceDimensionWeightsDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PresentationContractStatus = "unresolved"
    source_scope: ExperienceDimensionSourceScope = "jd_only"
    dimension_enum_version: str = DIMENSION_ENUM_VERSION
    prompt_version: str | None = None
    prompt_metadata: PromptMetadata | None = None
    overall_weights: dict[str, int] = Field(default_factory=dict)
    stakeholder_variant_weights: dict[EvaluatorRole, dict[str, int] | None] = Field(default_factory=dict)
    minimum_visible_dimensions: list[ExperienceDimension] = Field(default_factory=list)
    overuse_risks: list[ExperienceDimensionOveruseRiskDoc] = Field(default_factory=list)
    rationale: str | None = None
    unresolved_markers: list[str] = Field(default_factory=list)
    defaults_applied: list[str] = Field(default_factory=list)
    normalization_events: list[ExperienceDimensionNormalizationEventDoc] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    debug_context: ExperienceDimensionWeightsDebug = Field(default_factory=ExperienceDimensionWeightsDebug)
    fail_open_reason: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return _coerce_enum_choice(
            value,
            allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
            default="unresolved",
        )

    @field_validator("source_scope", mode="before")
    @classmethod
    def normalize_source_scope(cls, value: Any) -> str:
        return _normalize_experience_source_scope(value, default="jd_only")

    @field_validator("dimension_enum_version", mode="before")
    @classmethod
    def normalize_dimension_version(cls, value: Any) -> str:
        return _coerce_text(value) or DIMENSION_ENUM_VERSION

    @field_validator("prompt_version", "rationale", "fail_open_reason", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("minimum_visible_dimensions", mode="before")
    @classmethod
    def normalize_minimum_visible_dimensions(cls, value: Any) -> list[str]:
        return _normalize_experience_dimension_list(value)

    @field_validator("unresolved_markers", "defaults_applied", "notes", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("overall_weights", mode="before")
    @classmethod
    def normalize_overall_weights(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("overall_weights must be a mapping")
        return value

    @field_validator("stakeholder_variant_weights", mode="before")
    @classmethod
    def normalize_variant_weights(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            role = _normalize_audience_role_key(key)
            if role:
                normalized[role] = item
        return normalized

    @field_validator("overall_weights", "stakeholder_variant_weights")
    @classmethod
    def validate_weight_maps(cls, value: Any, info: ValidationInfo) -> Any:
        def _validate_map(weight_map: dict[str, Any], *, path: str) -> dict[str, int]:
            normalized: dict[str, int] = {}
            for raw_key, raw_value in (weight_map or {}).items():
                dimension = _normalize_experience_dimension(raw_key)
                if not dimension:
                    raise ValueError(f"{path} contains non-canonical experience dimension: {raw_key}")
                if isinstance(raw_value, bool):
                    raise ValueError(f"{path}.{dimension} must be a non-negative integer")
                if isinstance(raw_value, int):
                    numeric = raw_value
                elif isinstance(raw_value, float):
                    if not raw_value.is_integer():
                        raise ValueError(f"{path}.{dimension} must be a non-negative integer")
                    numeric = int(raw_value)
                else:
                    text = _coerce_text(raw_value)
                    if not text or not re.fullmatch(r"\d+(?:\.0+)?", text):
                        raise ValueError(f"{path}.{dimension} must be a non-negative integer")
                    numeric = int(float(text))
                if numeric < 0:
                    raise ValueError(f"{path}.{dimension} must be non-negative")
                normalized[dimension] = numeric
            return normalized

        field_name = info.field_name or ""
        if field_name == "overall_weights":
            return _validate_map(value, path="overall_weights")
        validated_variants: dict[str, dict[str, int] | None] = {}
        for role, weight_map in (value or {}).items():
            if weight_map is None:
                validated_variants[role] = None
                continue
            if not isinstance(weight_map, dict):
                raise ValueError(f"stakeholder_variant_weights.{role} must be a mapping or null")
            validated_variants[role] = _validate_map(weight_map, path=f"stakeholder_variant_weights.{role}")
        return validated_variants

    @field_validator("stakeholder_variant_weights")
    @classmethod
    def validate_variant_keys(cls, value: dict[str, dict[str, int] | None], info: ValidationInfo) -> dict[str, dict[str, int] | None]:
        allowed_roles = {item for item in _normalize_string_list((info.context or {}).get("evaluator_coverage_target")) if item}
        if allowed_roles:
            invalid = sorted(role for role in value if role not in allowed_roles)
            if invalid:
                raise ValueError(
                    "stakeholder_variant_weights keys must be a subset of evaluator_coverage_target: "
                    f"{invalid}"
                )
        return value

    @model_validator(mode="after")
    def validate_structure(self) -> "ExperienceDimensionWeightsDoc":
        if self.dimension_enum_version != DIMENSION_ENUM_VERSION:
            raise ValueError("dimension_enum_version must match the canonical version")
        if not self.overall_weights:
            raise ValueError("overall_weights must not be empty")
        if sum(self.overall_weights.values()) != 100:
            raise ValueError("overall_weights must sum to 100")
        for role, variant in self.stakeholder_variant_weights.items():
            if variant is None:
                continue
            if sum(variant.values()) != 100:
                raise ValueError(f"stakeholder_variant_weights.{role} must sum to 100")
        if len(self.minimum_visible_dimensions) > 5:
            raise ValueError("minimum_visible_dimensions may contain at most 5 dimensions")
        missing_minimum = [item for item in self.minimum_visible_dimensions if item not in self.overall_weights]
        if missing_minimum:
            raise ValueError(f"minimum_visible_dimensions must exist in overall_weights: {missing_minimum}")
        if self.defaults_applied and self.confidence.band == "high":
            raise ValueError("dimension weights confidence may not remain high when defaults_applied is non-empty")
        return self


def _confidence_band_rank(value: str | None) -> int:
    return {"unresolved": 0, "low": 1, "medium": 2, "high": 3}.get(str(value or "").strip().lower(), 0)


class NormalizationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: str
    path: str | None = None
    from_value: str | int | None = Field(default=None, alias="from")
    to_value: str | int | None = Field(default=None, alias="to")
    reason: str

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _EMPHASIS_NORMALIZATION_KINDS:
            raise ValueError("normalization event kind must be canonical")
        return normalized

    @field_validator("path", "reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        return _canonical_emphasis_text(value, limit=160)

    @field_validator("from_value", "to_value", mode="before")
    @classmethod
    def normalize_values(cls, value: Any) -> str | int | None:
        if isinstance(value, int):
            return value
        return _canonical_emphasis_text(value, limit=160)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_type: RuleTypeEnum
    topic_family: RuleTopicFamily
    applies_to_kind: AppliesToKindEnum
    applies_to: str
    condition: str
    action: str
    basis: str
    evidence_refs: list[str] = Field(default_factory=list)
    precedence: int = 0
    cap_value: int | None = None
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("rule_id", mode="before")
    @classmethod
    def normalize_rule_id(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("rule_id is required")
        text = re.sub(r"[^a-z0-9_]+", "_", text.strip().lower()).strip("_")
        if not text:
            raise ValueError("rule_id is required")
        return text[:64]

    @field_validator("rule_type", mode="before")
    @classmethod
    def normalize_rule_type_field(cls, value: Any) -> str:
        normalized = _normalize_rule_type(value)
        if not normalized:
            raise ValueError("rule_type must be canonical")
        return normalized

    @field_validator("topic_family", mode="before")
    @classmethod
    def normalize_topic_family(cls, value: Any) -> str:
        normalized = _normalize_rule_topic_family(value)
        if not normalized:
            raise ValueError("topic_family must be canonical")
        return normalized

    @field_validator("applies_to_kind", mode="before")
    @classmethod
    def normalize_applies_to_kind_field(cls, value: Any) -> str:
        normalized = _normalize_applies_to_kind(value)
        if not normalized:
            raise ValueError("applies_to_kind must be canonical")
        return normalized

    @field_validator("condition", "action", mode="before")
    @classmethod
    def normalize_rule_text(cls, value: Any) -> str:
        text = _canonical_emphasis_text(value, limit=240)
        if not text:
            raise ValueError("condition and action are required")
        return text

    @field_validator("basis", mode="before")
    @classmethod
    def normalize_basis(cls, value: Any) -> str:
        text = _canonical_emphasis_text(value, limit=200)
        if not text:
            raise ValueError("basis is required")
        return text

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_evidence_refs(cls, value: Any) -> list[str]:
        return _normalize_emphasis_evidence_refs(value)

    @field_validator("precedence", mode="before")
    @classmethod
    def normalize_precedence(cls, value: Any, info: ValidationInfo) -> int:
        data = info.data if isinstance(info.data, dict) else {}
        return _normalize_rule_precedence(value, rule_type=str(data.get("rule_type") or ""))

    @field_validator("cap_value", mode="before")
    @classmethod
    def normalize_cap_value(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("cap_value must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        text = _coerce_text(value)
        if text and re.fullmatch(r"\d+(?:\.0+)?", text):
            return int(float(text))
        raise ValueError("cap_value must be an integer")

    @field_validator("applies_to")
    @classmethod
    def validate_applies_to(cls, value: str, info: ValidationInfo) -> str:
        data = info.data if isinstance(info.data, dict) else {}
        kind = str(data.get("applies_to_kind") or "")
        resolved = _resolve_applies_to_value(value, applies_to_kind=kind)
        if not resolved:
            raise ValueError("applies_to must resolve inside the enum surface for applies_to_kind")
        return resolved

    @model_validator(mode="after")
    def validate_rule(self) -> "Rule":
        if not self.evidence_refs:
            raise ValueError("rules require evidence_refs")
        if self.applies_to_kind == "global" and self.applies_to != "global":
            raise ValueError("global rules must use applies_to='global'")
        if self.rule_type == "cap_dimension_weight":
            if self.applies_to_kind != "dimension":
                raise ValueError("cap_dimension_weight rules must target a dimension")
            if self.cap_value is None or self.cap_value < 0 or self.cap_value > 100:
                raise ValueError("cap_dimension_weight rules require cap_value within 0-100")
        elif self.cap_value is not None:
            raise ValueError("cap_value is only valid for cap_dimension_weight rules")
        if self.rule_type == "suppress_audience_variant_signal" and self.applies_to_kind != "audience_variant":
            raise ValueError("suppress_audience_variant_signal rules must target an audience_variant")
        return self


class ForbiddenClaimPattern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    pattern: str
    pattern_kind: Literal["substring", "regex_safe"] = "substring"
    reason: str
    example: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("pattern_id", mode="before")
    @classmethod
    def normalize_pattern_id(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("pattern_id is required")
        return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")[:64]

    @field_validator("pattern", mode="before")
    @classmethod
    def normalize_pattern(cls, value: Any) -> str:
        text = _canonical_emphasis_text(value, limit=160)
        if not text:
            raise ValueError("pattern is required")
        return text

    @field_validator("pattern_kind", mode="before")
    @classmethod
    def normalize_pattern_kind_field(cls, value: Any) -> str:
        return _normalize_emphasis_pattern_kind(value)

    @field_validator("reason", "example", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str | None:
        return _canonical_emphasis_text(value, limit=200 if value is not None else 200)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_pattern_evidence(cls, value: Any) -> list[str]:
        return _normalize_emphasis_evidence_refs(value)

    @model_validator(mode="after")
    def validate_pattern(self) -> "ForbiddenClaimPattern":
        if not self.evidence_refs:
            raise ValueError("forbidden_claim_patterns require evidence_refs")
        if self.pattern_kind == "regex_safe" and not _is_regex_safe_pattern(self.pattern):
            raise ValueError("regex_safe forbidden_claim_patterns must pass the bounded regex check")
        return self


class CredibilityLadderRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ladder_id: str
    applies_to_audience: AudienceVariantKey | Literal["all"] = "all"
    ladder: list[ProofType] = Field(default_factory=list)
    fallback_rule_id: str
    rationale: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("ladder_id", "fallback_rule_id", mode="before")
    @classmethod
    def normalize_ids(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("ladder ids must be populated")
        return re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")[:64]

    @field_validator("applies_to_audience", mode="before")
    @classmethod
    def normalize_applies_to_audience(cls, value: Any) -> str:
        text = _normalize_slug(value)
        if text == "all":
            return "all"
        normalized = _normalize_audience_role_key(text)
        if not normalized:
            raise ValueError("credibility ladder audience must be canonical or 'all'")
        return normalized

    @field_validator("ladder", mode="before")
    @classmethod
    def normalize_ladder(cls, value: Any) -> list[str]:
        return _normalize_proof_categories(value)

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_ladder_rationale(cls, value: Any) -> str | None:
        return _canonical_emphasis_text(value, limit=200)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_ladder_refs(cls, value: Any) -> list[str]:
        return _normalize_emphasis_evidence_refs(value)

    @model_validator(mode="after")
    def validate_ladder(self) -> "CredibilityLadderRule":
        if len(self.ladder) < 2 or len(self.ladder) > 5:
            raise ValueError("credibility ladders must contain 2-5 proof types")
        if len(self.ladder) != len(set(self.ladder)):
            raise ValueError("credibility ladders must use unique proof types")
        if not self.evidence_refs:
            raise ValueError("credibility ladders require evidence_refs")
        return self


class TopicCoverageEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_family: RuleTopicFamily
    rule_count: int = 0
    source: Literal["llm", "default", "merged"] = "llm"

    @field_validator("topic_family", mode="before")
    @classmethod
    def normalize_topic_family_field(cls, value: Any) -> str:
        normalized = _normalize_rule_topic_family(value)
        if not normalized:
            raise ValueError("topic_coverage.topic_family must be canonical")
        return normalized

    @field_validator("rule_count", mode="before")
    @classmethod
    def normalize_rule_count(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("topic_coverage.rule_count must be an integer")
        if isinstance(value, int):
            return value
        text = _coerce_text(value)
        if text and text.isdigit():
            return int(text)
        raise ValueError("topic_coverage.rule_count must be an integer")


class EmphasisConflictLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    topic_family: RuleTopicFamily
    applies_to_kind: AppliesToKindEnum
    applies_to: str
    conflict_source: str
    resolution: Literal["suppressed", "downgraded", "retained", "overridden_by_defaults"]
    note: str | None = None

    @field_validator("rule_id", "conflict_source", "note", mode="before")
    @classmethod
    def normalize_conflict_text(cls, value: Any) -> str | None:
        return _canonical_emphasis_text(value, limit=160)

    @field_validator("topic_family", mode="before")
    @classmethod
    def normalize_conflict_topic_family(cls, value: Any) -> str:
        normalized = _normalize_rule_topic_family(value)
        if not normalized:
            raise ValueError("conflict topic_family must be canonical")
        return normalized

    @field_validator("applies_to_kind", mode="before")
    @classmethod
    def normalize_conflict_kind(cls, value: Any) -> str:
        normalized = _normalize_applies_to_kind(value)
        if not normalized:
            raise ValueError("conflict applies_to_kind must be canonical")
        return normalized

    @field_validator("applies_to")
    @classmethod
    def normalize_conflict_applies_to(cls, value: str, info: ValidationInfo) -> str:
        data = info.data if isinstance(info.data, dict) else {}
        kind = str(data.get("applies_to_kind") or "")
        resolved = _resolve_applies_to_value(value, applies_to_kind=kind)
        if not resolved:
            raise ValueError("conflict applies_to must resolve")
        return resolved


class TruthConstrainedEmphasisRulesDebug(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_summary: PresentationInputSummaryDoc = Field(default_factory=PresentationInputSummaryDoc)
    role_family_emphasis_rule_priors: dict[str, Any] = Field(default_factory=dict)
    title_safety_envelope: dict[str, Any] = Field(default_factory=dict)
    ai_claim_envelope: dict[str, Any] = Field(default_factory=dict)
    leadership_claim_envelope: dict[str, Any] = Field(default_factory=dict)
    architecture_claim_envelope: dict[str, Any] = Field(default_factory=dict)
    forbidden_claim_pattern_examples: list[str] = Field(default_factory=list)
    defaults_applied: list[str] = Field(default_factory=list)
    normalization_events: list[NormalizationEvent] = Field(default_factory=list)
    richer_output_retained: list[PresentationRetainedFieldDoc] = Field(default_factory=list)
    rejected_output: list[PresentationRejectedFieldDoc] = Field(default_factory=list)
    retry_events: list[PresentationRetryEventDoc] = Field(default_factory=list)
    conflict_resolution_log: list[EmphasisConflictLogEntry] = Field(default_factory=list)

    @field_validator("forbidden_claim_pattern_examples", "defaults_applied", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class TruthConstrainedEmphasisRulesDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PresentationContractStatus = "unresolved"
    source_scope: ExperienceDimensionSourceScope = "jd_only"
    rule_type_enum_version: str = RULE_TYPE_ENUM_VERSION
    applies_to_enum_version: str = APPLIES_TO_ENUM_VERSION
    prompt_version: str | None = None
    prompt_metadata: PromptMetadata | None = None
    global_rules: list[Rule] = Field(default_factory=list)
    section_rules: dict[DocumentSectionIdEnum, list[Rule]] = Field(default_factory=dict)
    allowed_if_evidenced: list[Rule] = Field(default_factory=list)
    downgrade_rules: list[Rule] = Field(default_factory=list)
    omit_rules: list[Rule] = Field(default_factory=list)
    forbidden_claim_patterns: list[ForbiddenClaimPattern] = Field(default_factory=list)
    credibility_ladder_rules: list[CredibilityLadderRule] = Field(default_factory=list)
    topic_coverage: list[TopicCoverageEntry] = Field(default_factory=list)
    rationale: str | None = None
    unresolved_markers: list[str] = Field(default_factory=list)
    defaults_applied: list[str] = Field(default_factory=list)
    normalization_events: list[NormalizationEvent] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    debug_context: TruthConstrainedEmphasisRulesDebug = Field(default_factory=TruthConstrainedEmphasisRulesDebug)
    fail_open_reason: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return _coerce_enum_choice(
            value,
            allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
            default="unresolved",
        )

    @field_validator("source_scope", mode="before")
    @classmethod
    def normalize_source_scope(cls, value: Any) -> str:
        return _normalize_emphasis_source_scope(value, default="jd_only")

    @field_validator("rule_type_enum_version", mode="before")
    @classmethod
    def normalize_rule_version(cls, value: Any) -> str:
        return _coerce_text(value) or RULE_TYPE_ENUM_VERSION

    @field_validator("applies_to_enum_version", mode="before")
    @classmethod
    def normalize_applies_version(cls, value: Any) -> str:
        return _coerce_text(value) or APPLIES_TO_ENUM_VERSION

    @field_validator("prompt_version", "rationale", "fail_open_reason", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _canonical_emphasis_text(value, limit=800 if value is not None else 800)

    @field_validator("unresolved_markers", "defaults_applied", "notes", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("section_rules", mode="before")
    @classmethod
    def normalize_section_rules(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, bucket in value.items():
            section = _normalize_slug(key)
            if section in _PRESENTATION_SECTION_IDS:
                normalized[section] = bucket
        return normalized

    @field_validator("fail_open_reason")
    @classmethod
    def validate_fail_open_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_emphasis_fail_open_reason(value)
        if not normalized:
            raise ValueError("fail_open_reason must be canonical when populated")
        return normalized

    @model_validator(mode="after")
    def validate_structure(self) -> "TruthConstrainedEmphasisRulesDoc":
        if self.rule_type_enum_version != RULE_TYPE_ENUM_VERSION:
            raise ValueError("rule_type_enum_version must match the canonical version")
        if self.applies_to_enum_version != APPLIES_TO_ENUM_VERSION:
            raise ValueError("applies_to_enum_version must match the canonical version")
        seen_rule_ids: set[str] = set()
        all_rules = list(self.global_rules) + list(self.allowed_if_evidenced) + list(self.downgrade_rules) + list(self.omit_rules)
        for section_id, bucket in self.section_rules.items():
            if section_id not in _PRESENTATION_SECTION_IDS:
                raise ValueError(f"section_rules contains unknown section: {section_id}")
            for rule in bucket:
                if rule.applies_to_kind != "section" or rule.applies_to != section_id:
                    raise ValueError(f"section_rules[{section_id}] must contain section-scoped rules only")
                all_rules.append(rule)
        for rule in all_rules:
            if rule.rule_id in seen_rule_ids:
                raise ValueError(f"truth_constrained_emphasis_rules rule_id must be unique: {rule.rule_id}")
            seen_rule_ids.add(rule.rule_id)
            if _confidence_band_rank(rule.confidence.band) > _confidence_band_rank(self.confidence.band):
                raise ValueError("truth_constrained_emphasis_rules rule confidence may not exceed document confidence")
        coverage = {entry.topic_family: entry.rule_count for entry in self.topic_coverage}
        for family in _MANDATORY_RULE_TOPIC_FAMILIES:
            if coverage.get(family, 0) < 1 and self.status in {"completed", "partial", "inferred_only"}:
                raise ValueError(f"truth_constrained_emphasis_rules missing mandatory topic coverage: {family}")
        if self.status in {"completed", "partial", "inferred_only"}:
            if len(self.forbidden_claim_patterns) < 2:
                raise ValueError("truth_constrained_emphasis_rules requires at least two forbidden_claim_patterns")
            if len(self.credibility_ladder_rules) < 1:
                raise ValueError("truth_constrained_emphasis_rules requires at least one credibility_ladder_rule")
        ladder_ids = {rule.rule_id for rule in all_rules}
        for ladder_rule in self.credibility_ladder_rules:
            if ladder_rule.fallback_rule_id not in ladder_ids:
                raise ValueError("credibility_ladder_rules fallback_rule_id must resolve inside the artifact")
        if self.defaults_applied and self.confidence.band == "high":
            raise ValueError("emphasis rules confidence may not remain high when defaults_applied is non-empty")
        return self


def _iter_truth_constrained_rules(doc: TruthConstrainedEmphasisRulesDoc) -> list[Rule]:
    rules = list(doc.global_rules) + list(doc.allowed_if_evidenced) + list(doc.downgrade_rules) + list(doc.omit_rules)
    for bucket in doc.section_rules.values():
        rules.extend(bucket)
    return rules


class PresentationContractDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    input_snapshot_id: str | None = None
    stage_version: str = "presentation_contract.v4.2.6"
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    prompt_metadata: dict[str, PromptMetadata] = Field(default_factory=dict)
    status: PresentationContractStatus = "unresolved"
    document_expectations: DocumentExpectationsDoc
    cv_shape_expectations: CvShapeExpectationsDoc
    ideal_candidate_presentation_model: IdealCandidatePresentationModelDoc
    experience_dimension_weights: ExperienceDimensionWeightsDoc
    truth_constrained_emphasis_rules: TruthConstrainedEmphasisRulesDoc
    debug: dict[str, Any] = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    timing: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    cache_refs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("unresolved_questions", "notes", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def validate_cross_subdocument_invariants(self) -> "PresentationContractDoc":
        if self.cv_shape_expectations.header_shape.density != self.document_expectations.density_posture.header_density:
            raise ValueError("cv_shape_expectations.header_shape.density must equal document_expectations.density_posture.header_density")
        if self.ideal_candidate_presentation_model.title_strategy != self.cv_shape_expectations.title_strategy:
            raise ValueError("ideal_candidate_presentation_model.title_strategy must equal cv_shape_expectations.title_strategy")
        if self.experience_dimension_weights.dimension_enum_version != DIMENSION_ENUM_VERSION:
            raise ValueError("experience_dimension_weights.dimension_enum_version must equal the canonical version")
        if sum(self.experience_dimension_weights.overall_weights.values()) != 100:
            raise ValueError("experience_dimension_weights.overall_weights must sum to 100")
        for role, variant in self.experience_dimension_weights.stakeholder_variant_weights.items():
            if variant is None:
                continue
            if sum(variant.values()) != 100:
                raise ValueError(f"experience_dimension_weights stakeholder variant must sum to 100: {role}")
        signal_dimension_map = {
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
        }
        for signal in self.ideal_candidate_presentation_model.must_signal:
            dimension = signal_dimension_map.get(signal.tag)
            if not dimension:
                continue
            if self.experience_dimension_weights.overall_weights.get(dimension, 0) < 10:
                if not self.experience_dimension_weights.unresolved_markers:
                    raise ValueError(
                        "experience_dimension_weights must keep ideal_candidate must-signal dimensions at >=10 "
                        f"or record unresolved markers: {dimension}"
                    )
        for signal in self.ideal_candidate_presentation_model.de_emphasize:
            dimension = signal_dimension_map.get(signal.tag)
            if not dimension:
                continue
            if self.experience_dimension_weights.overall_weights.get(dimension, 0) > 5:
                mitigated = any(risk.dimension == dimension for risk in self.experience_dimension_weights.overuse_risks)
                if not mitigated:
                    raise ValueError(
                        "experience_dimension_weights must flag an overuse risk when a de-emphasized "
                        f"dimension stays above 5: {dimension}"
                    )
        emphasis = self.truth_constrained_emphasis_rules
        emphasis_rules = _iter_truth_constrained_rules(emphasis)
        title_strategy = self.cv_shape_expectations.title_strategy
        title_envelope = dict(emphasis.debug_context.title_safety_envelope or {})
        envelope_title_strategy = _normalize_title_strategy(title_envelope.get("title_strategy"), default="")
        if envelope_title_strategy and envelope_title_strategy != title_strategy:
            raise ValueError("truth_constrained_emphasis_rules title envelope must match cv_shape_expectations.title_strategy")
        acceptable_titles = {item.lower() for item in self.ideal_candidate_presentation_model.acceptable_titles}
        envelope_titles = {str(item).strip().lower() for item in list(title_envelope.get("acceptable_titles") or []) if str(item).strip()}
        if envelope_titles and not envelope_titles.issubset(acceptable_titles):
            raise ValueError("truth_constrained_emphasis_rules title envelope must stay within acceptable_titles")
        ai_envelope = dict(emphasis.debug_context.ai_claim_envelope or {})
        ai_intensity = str(ai_envelope.get("ai_intensity") or emphasis.debug_context.input_summary.ai_intensity or "").strip().lower()
        ai_cap = ai_envelope.get("ai_intensity_cap")
        leadership_envelope = dict(emphasis.debug_context.leadership_claim_envelope or {})
        top_proofs = list(self.document_expectations.proof_order[:2])
        allowed_proof_rules = [
            rule
            for rule in emphasis_rules
            if rule.rule_type == "allowed_if_evidenced" and rule.applies_to_kind == "proof"
        ]
        for rule in emphasis_rules:
            if rule.applies_to_kind == "section" and rule.applies_to not in self.cv_shape_expectations.section_order:
                raise ValueError("truth_constrained_emphasis_rules section rules must target sections in cv_shape_expectations.section_order")
            if rule.topic_family == "title_inflation":
                if title_strategy != self.ideal_candidate_presentation_model.title_strategy:
                    raise ValueError("truth_constrained_emphasis_rules title rules require matching peer title strategies")
                lower_text = f"{rule.condition} {rule.action}".lower()
                title_tokens = [token for token in _TITLE_LEVEL_TOKENS if token in lower_text]
                if title_tokens and acceptable_titles:
                    permitted = " ".join(self.ideal_candidate_presentation_model.acceptable_titles).lower()
                    if any(token not in permitted for token in title_tokens):
                        raise ValueError("truth_constrained_emphasis_rules may not authorize title inflation past acceptable_titles")
            if rule.topic_family == "ai_claims":
                if ai_intensity in {"none", "adjacent"} and rule.rule_type == "allowed_if_evidenced":
                    raise ValueError("truth_constrained_emphasis_rules may not authorize AI claims when ai_intensity is none/adjacent")
                if rule.rule_type == "cap_dimension_weight" and rule.applies_to == "ai_ml_depth" and ai_cap is not None and rule.cap_value is not None:
                    if int(rule.cap_value) > int(ai_cap):
                        raise ValueError("truth_constrained_emphasis_rules may not cap ai_ml_depth above the AI envelope")
            if rule.rule_type == "cap_dimension_weight":
                current_weight = self.experience_dimension_weights.overall_weights.get(rule.applies_to, 0)
                overuse_flagged = any(risk.dimension == rule.applies_to for risk in self.experience_dimension_weights.overuse_risks)
                if rule.cap_value is None:
                    raise ValueError("cap_dimension_weight rules must include cap_value")
                if rule.cap_value < current_weight and not overuse_flagged:
                    raise ValueError("cap_dimension_weight rules may only clamp below current weight when 4.2.5 also flagged overuse risk")
            if rule.topic_family == "leadership_scope" and leadership_envelope:
                seniority = str(leadership_envelope.get("seniority") or "").strip().lower()
                direct_reports = int(leadership_envelope.get("direct_reports") or 0)
                if seniority in {"junior", "mid", "senior_ic"} and direct_reports <= 0 and rule.rule_type == "allowed_if_evidenced":
                    raise ValueError("truth_constrained_emphasis_rules may not authorize leadership scope above the envelope")
        for pattern in emphasis.forbidden_claim_patterns:
            lowered = pattern.pattern.lower()
            for proof in top_proofs:
                if proof in lowered:
                    raise ValueError("forbidden_claim_patterns must not suppress the top two proof categories outright")
        must_signal_proofs = {signal.proof_category for signal in self.ideal_candidate_presentation_model.must_signal if signal.proof_category}
        should_signal_proofs = {signal.proof_category for signal in self.ideal_candidate_presentation_model.should_signal if signal.proof_category}
        for rule in emphasis_rules:
            if rule.applies_to_kind == "proof" and rule.applies_to in must_signal_proofs and rule.rule_type in {"omit_if_weak", "forbid_without_direct_proof"}:
                if not emphasis.unresolved_markers:
                    raise ValueError("truth_constrained_emphasis_rules may not suppress must_signal proof categories without unresolved_markers")
            if rule.applies_to_kind == "proof" and rule.applies_to in should_signal_proofs and rule.rule_type == "omit_if_weak":
                companion = any(
                    allowed.applies_to_kind == "proof" and allowed.applies_to == rule.applies_to
                    for allowed in allowed_proof_rules
                )
                if not companion:
                    raise ValueError("truth_constrained_emphasis_rules should_signal omissions require an allowed_if_evidenced companion")
        for signal in self.ideal_candidate_presentation_model.de_emphasize:
            reflected = any(
                rule.rule_type in {"prefer_softened_form", "omit_if_weak"}
                and (
                    (signal.proof_category and rule.applies_to_kind == "proof" and rule.applies_to == signal.proof_category)
                    or (signal_dimension_map.get(signal.tag) and rule.applies_to_kind == "dimension" and rule.applies_to == signal_dimension_map.get(signal.tag))
                )
                for rule in emphasis_rules
            )
            if not reflected:
                raise ValueError("truth_constrained_emphasis_rules must reflect ideal_candidate de_emphasize signals")
        return self


def normalize_document_expectations_payload(
    payload: dict[str, Any] | None,
    *,
    evaluator_coverage_target: list[str] | None = None,
    allowed_company_names: list[str] | None = None,
    allowed_company_domain: str | None = None,
    jd_excerpt: str = "",
) -> dict[str, Any]:
    raw = dict(payload or {})
    debug_context = _clean_debug_context(raw.get("debug_context"))
    normalized = {}

    primary_goal = raw.get("primary_document_goal", raw.get("goal"))
    if primary_goal != raw.get("primary_document_goal") and primary_goal is not None:
        _debug_append_event(debug_context, "normalization_events", "alias:goal->primary_document_goal")
    normalized["primary_document_goal"] = _coerce_enum_choice(
        primary_goal,
        allowed=_DOCUMENT_GOALS,
        default="unresolved",
    )

    secondary_goals = raw.get("secondary_document_goals", raw.get("secondary_goals"))
    if secondary_goals is not None and secondary_goals != raw.get("secondary_document_goals"):
        _debug_append_event(debug_context, "normalization_events", "alias:secondary_goals->secondary_document_goals")
    normalized["secondary_document_goals"] = [
        item for item in (_normalize_slug(goal) for goal in _normalize_string_list(secondary_goals)) if item in _DOCUMENT_GOALS
    ][:2]

    audience_variants_raw = raw.get("audience_variants") or raw.get("audiences") or {}
    if audience_variants_raw is not raw.get("audience_variants") and audience_variants_raw:
        _debug_append_event(debug_context, "normalization_events", "alias:audiences->audience_variants")
    audience_variants: dict[str, Any] = {}
    if isinstance(audience_variants_raw, dict):
        for key, entry in audience_variants_raw.items():
            role = _normalize_audience_role_key(key)
            if not role:
                _debug_append_event(debug_context, "rejected_output", {"path": f"audience_variants.{key}", "reason": "invalid_evaluator_role"})
                continue
            entry_dict = dict(entry) if isinstance(entry, dict) else {"must_see": entry}
            if entry_dict.get("communication_style_tag") and not entry_dict.get("tilt"):
                entry_dict["tilt"] = [entry_dict.get("communication_style_tag")]
                _debug_append_event(debug_context, "normalization_events", f"mapped:audience_variants.{role}.communication_style_tag->tilt")
            audience_variants[role] = {
                "tilt": _normalize_string_list(entry_dict.get("tilt")),
                "must_see": _normalize_string_list(entry_dict.get("must_see")),
                "risky_signals": _normalize_string_list(entry_dict.get("risky_signals")),
                "rationale": _coerce_text(entry_dict.get("rationale")),
            }
            for extra_key in sorted(set(entry_dict.keys()) - {"tilt", "must_see", "risky_signals", "rationale", "communication_style_tag"}):
                _debug_append_event(
                    debug_context,
                    "richer_output_retained",
                    {"key": f"audience_variants.{role}.{extra_key}", "value": entry_dict.get(extra_key), "note": "unmapped audience variant field retained"},
                )
    normalized["audience_variants"] = audience_variants

    normalized["proof_order"] = _normalize_proof_categories(raw.get("proof_order") or raw.get("proof_categories"))
    if raw.get("proof_categories") is not None and raw.get("proof_order") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:proof_categories->proof_order")
    invalid_proof_categories = [
        item for item in (_normalize_slug(item) for item in _normalize_string_list(raw.get("proof_order") or raw.get("proof_categories"))) if item and item not in _PROOF_CATEGORIES
    ]
    for invalid in invalid_proof_categories:
        _debug_append_event(debug_context, "rejected_output", {"path": "proof_order", "reason": f"invalid_proof_category:{invalid}"})

    normalized["anti_patterns"] = _normalize_anti_pattern_ids(raw.get("anti_patterns"))
    for invalid in [
        item for item in (_normalize_slug(item) for item in _normalize_string_list(raw.get("anti_patterns"))) if item and item not in _ANTI_PATTERN_IDS
    ]:
        _debug_append_event(debug_context, "rejected_output", {"path": "anti_patterns", "reason": f"invalid_anti_pattern:{invalid}"})

    normalized["tone_posture"] = {
        "primary_tone": _coerce_enum_choice(
            (raw.get("tone_posture") or {}).get("primary_tone"),
            allowed={"evidence_first", "operator_first", "architect_first", "leader_first", "balanced"},
            default="balanced",
        ),
        "hype_tolerance": _coerce_enum_choice(
            (raw.get("tone_posture") or {}).get("hype_tolerance"),
            allowed={"low", "medium", "high"},
            default="medium",
        ),
        "narrative_tolerance": _coerce_enum_choice(
            (raw.get("tone_posture") or {}).get("narrative_tolerance"),
            allowed={"low", "medium", "high"},
            default="medium",
        ),
        "formality": _coerce_enum_choice(
            (raw.get("tone_posture") or {}).get("formality"),
            allowed={"informal", "neutral", "formal"},
            default="neutral",
        ),
    }

    density_raw = raw.get("density_posture") or {}
    section_density_bias_raw = density_raw.get("section_density_bias") or []
    density_bias: list[dict[str, Any]] = []
    for index, item in enumerate(_coerce_list(section_density_bias_raw)):
        if not isinstance(item, dict):
            continue
        section_id = _normalize_slug(item.get("section_id"))
        if section_id not in _PRESENTATION_SECTION_IDS:
            _debug_append_event(debug_context, "rejected_output", {"path": f"density_posture.section_density_bias[{index}].section_id", "reason": "invalid_section_id"})
            continue
        density_bias.append(
            {
                "section_id": section_id,
                "bias": _coerce_enum_choice(item.get("bias"), allowed={"low", "medium", "high"}, default="medium"),
            }
        )
    normalized["density_posture"] = {
        "overall_density": _coerce_enum_choice(density_raw.get("overall_density"), allowed={"low", "medium", "high"}, default="medium"),
        "header_density": _coerce_enum_choice(density_raw.get("header_density"), allowed=_HEADER_DENSITIES, default="balanced"),
        "section_density_bias": density_bias,
    }

    keyword_raw = raw.get("keyword_balance") or {}
    normalized["keyword_balance"] = {
        "target_keyword_pressure": _coerce_enum_choice(
            keyword_raw.get("target_keyword_pressure"),
            allowed={"low", "medium", "high", "extreme"},
            default="medium",
        ),
        "ats_mirroring_bias": _coerce_enum_choice(
            keyword_raw.get("ats_mirroring_bias"),
            allowed={"conservative", "balanced", "aggressive"},
            default="balanced",
        ),
        "semantic_expansion_bias": _coerce_enum_choice(
            keyword_raw.get("semantic_expansion_bias"),
            allowed={"narrow", "balanced", "broad"},
            default="balanced",
        ),
    }

    normalized["status"] = _coerce_enum_choice(
        raw.get("status"),
        allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
        default="unresolved",
    )
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["rationale"] = _coerce_text(raw.get("rationale"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="document_expectations_normalized")
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))

    allowed_company_name_set = {item.lower() for item in _normalize_string_list(allowed_company_names)}
    candidate_stripped = _strip_candidate_leakage(
        normalized,
        path="document_expectations",
        debug_context=debug_context,
        allowed_company_names=allowed_company_name_set,
        allowed_company_domain=allowed_company_domain,
        jd_excerpt=jd_excerpt,
    )
    normalized = candidate_stripped if isinstance(candidate_stripped, dict) else normalized
    if debug_context.get("rejected_output"):
        normalized["status"] = "partial"
    normalized["debug_context"] = debug_context

    known_keys = {
        "status",
        "primary_document_goal",
        "goal",
        "secondary_document_goals",
        "secondary_goals",
        "audience_variants",
        "audiences",
        "proof_order",
        "proof_categories",
        "anti_patterns",
        "tone_posture",
        "density_posture",
        "keyword_balance",
        "unresolved_markers",
        "rationale",
        "debug_context",
        "confidence",
        "evidence",
    }
    for extra_key in sorted(set(raw.keys()) - known_keys):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": extra_key, "value": raw.get(extra_key), "note": "unknown top-level document expectations field retained"},
        )
    if evaluator_coverage_target:
        normalized["debug_context"]["input_summary"] = {
            **dict(normalized["debug_context"].get("input_summary") or {}),
            "evaluator_roles_in_scope": [item for item in evaluator_coverage_target if item in {
                "recruiter",
                "hiring_manager",
                "skip_level_leader",
                "peer_technical",
                "cross_functional_partner",
                "executive_sponsor",
            }],
        }
    return normalized


def normalize_cv_shape_expectations_payload(
    payload: dict[str, Any] | None,
    *,
    allowed_company_names: list[str] | None = None,
    allowed_company_domain: str | None = None,
    jd_excerpt: str = "",
) -> dict[str, Any]:
    raw = dict(payload or {})
    debug_context = _clean_debug_context(raw.get("debug_context"))
    normalized = {}

    normalized["status"] = _coerce_enum_choice(
        raw.get("status"),
        allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
        default="unresolved",
    )
    normalized["title_strategy"] = _coerce_enum_choice(
        raw.get("title_strategy"),
        allowed={"exact_match", "closest_truthful", "functional_label", "unresolved"},
        default="unresolved",
    )
    header_raw = raw.get("header_shape") or {}
    normalized["header_shape"] = {
        "density": _coerce_enum_choice(header_raw.get("density"), allowed=_HEADER_DENSITIES, default="balanced"),
        "include_elements": [
            item for item in (_normalize_slug(item) for item in _normalize_string_list(header_raw.get("include_elements"))) if item in {
                "name",
                "current_or_target_title",
                "tagline",
                "location",
                "links",
                "proof_line",
                "differentiator_line",
            }
        ],
        "proof_line_policy": _coerce_enum_choice(header_raw.get("proof_line_policy"), allowed={"required", "optional", "omit"}, default="optional"),
        "differentiator_line_policy": _coerce_enum_choice(
            header_raw.get("differentiator_line_policy"),
            allowed={"required", "optional", "omit"},
            default="optional",
        ),
    }

    section_order_raw = raw.get("section_order")
    if section_order_raw is None and isinstance(raw.get("shape"), dict):
        section_order_raw = raw.get("shape", {}).get("sections")
        if section_order_raw is not None:
            _debug_append_event(debug_context, "normalization_events", "alias:shape.sections->section_order")
    if section_order_raw is None:
        section_order_raw = raw.get("order")
        if section_order_raw is not None:
            _debug_append_event(debug_context, "normalization_events", "alias:order->section_order")
    normalized["section_order"] = _normalize_presentation_section_ids(section_order_raw)
    for invalid in [
        item for item in (_normalize_slug(item) for item in _normalize_string_list(section_order_raw)) if item and item not in _PRESENTATION_SECTION_IDS
    ]:
        _debug_append_event(debug_context, "rejected_output", {"path": "section_order", "reason": f"invalid_section_id:{invalid}"})

    emphasis_raw = raw.get("section_emphasis") or []
    emphasis_entries: list[dict[str, Any]] = []
    if isinstance(emphasis_raw, dict):
        _debug_append_event(debug_context, "normalization_events", "coerced:section_emphasis_map->list")
        emphasis_raw = [
            {"section_id": key, **(value if isinstance(value, dict) else {"emphasis": value})}
            for key, value in emphasis_raw.items()
        ]
    for index, item in enumerate(_coerce_list(emphasis_raw)):
        if not isinstance(item, dict):
            continue
        section_id = _normalize_slug(item.get("section_id") or item.get("section"))
        if section_id not in _PRESENTATION_SECTION_IDS:
            _debug_append_event(debug_context, "rejected_output", {"path": f"section_emphasis[{index}].section_id", "reason": "invalid_section_id"})
            continue
        focus_categories = _normalize_proof_categories(item.get("focus_categories") or item.get("categories"))
        invalid_categories = [
            cat for cat in (_normalize_slug(cat) for cat in _normalize_string_list(item.get("focus_categories") or item.get("categories"))) if cat and cat not in _PROOF_CATEGORIES
        ]
        for invalid in invalid_categories:
            _debug_append_event(debug_context, "rejected_output", {"path": f"section_emphasis[{index}].focus_categories", "reason": f"invalid_proof_category:{invalid}"})
        emphasis_entries.append(
            {
                "section_id": section_id,
                "emphasis": _coerce_enum_choice(
                    item.get("emphasis"),
                    allowed={"highlight", "balanced", "secondary", "compress", "omit"},
                    default="balanced",
                ),
                "focus_categories": focus_categories,
                "length_bias": _coerce_enum_choice(item.get("length_bias"), allowed={"short", "medium", "long"}, default="medium"),
                "ordering_bias": _coerce_enum_choice(
                    item.get("ordering_bias"),
                    allowed={"outcome_first", "scope_first", "tech_first", "narrative_first"},
                    default="outcome_first",
                ),
                "rationale": _coerce_text(item.get("rationale")),
            }
        )
        for extra_key in sorted(set(item.keys()) - {"section_id", "section", "emphasis", "focus_categories", "categories", "length_bias", "ordering_bias", "rationale"}):
            _debug_append_event(
                debug_context,
                "richer_output_retained",
                {"key": f"section_emphasis[{index}].{extra_key}", "value": item.get(extra_key), "note": "unmapped section emphasis field retained"},
            )
    normalized["section_emphasis"] = emphasis_entries

    ai_policy = raw.get("ai_section_policy", raw.get("ai_policy"))
    if ai_policy is not None and ai_policy != raw.get("ai_section_policy"):
        _debug_append_event(debug_context, "normalization_events", "alias:ai_policy->ai_section_policy")
    normalized["ai_section_policy"] = _coerce_enum_choice(
        ai_policy,
        allowed={"required", "optional", "discouraged", "embedded_only"},
        default="embedded_only",
    )

    counts_raw = raw.get("counts") or {}
    normalized["counts"] = {
        "key_achievements_min": int(counts_raw.get("key_achievements_min") or 0),
        "key_achievements_max": int(counts_raw.get("key_achievements_max") or 0),
        "core_competencies_min": int(counts_raw.get("core_competencies_min") or 0),
        "core_competencies_max": int(counts_raw.get("core_competencies_max") or 0),
        "summary_sentences_min": int(counts_raw.get("summary_sentences_min") or 0),
        "summary_sentences_max": int(counts_raw.get("summary_sentences_max") or 0),
    }

    ats_raw = raw.get("ats_envelope") or {}
    normalized["ats_envelope"] = {
        "pressure": _coerce_enum_choice(ats_raw.get("pressure"), allowed={"standard", "high", "extreme"}, default="standard"),
        "format_rules": _normalize_string_list(ats_raw.get("format_rules")),
        "keyword_placement_bias": _coerce_enum_choice(
            ats_raw.get("keyword_placement_bias"),
            allowed={"top_heavy", "balanced", "bottom_heavy"},
            default="balanced",
        ),
    }

    normalized["evidence_density"] = _coerce_enum_choice(raw.get("evidence_density"), allowed={"low", "medium", "high"}, default="medium")
    normalized["seniority_signal_strength"] = _coerce_enum_choice(raw.get("seniority_signal_strength"), allowed={"low", "medium", "high"}, default="medium")
    normalized["compression_rules"] = _normalize_compression_rule_ids(raw.get("compression_rules"))
    normalized["omission_rules"] = _normalize_omission_rule_ids(raw.get("omission_rules"))
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["rationale"] = _coerce_text(raw.get("rationale"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="cv_shape_expectations_normalized")
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))

    for invalid in [
        item for item in (_normalize_slug(item) for item in _normalize_string_list(raw.get("compression_rules"))) if item and item not in _COMPRESSION_RULE_IDS
    ]:
        _debug_append_event(debug_context, "rejected_output", {"path": "compression_rules", "reason": f"invalid_rule_id:{invalid}"})
    for invalid in [
        item for item in (_normalize_slug(item) for item in _normalize_string_list(raw.get("omission_rules"))) if item and item not in _OMISSION_RULE_IDS
    ]:
        _debug_append_event(debug_context, "rejected_output", {"path": "omission_rules", "reason": f"invalid_rule_id:{invalid}"})

    allowed_company_name_set = {item.lower() for item in _normalize_string_list(allowed_company_names)}
    candidate_stripped = _strip_candidate_leakage(
        normalized,
        path="cv_shape_expectations",
        debug_context=debug_context,
        allowed_company_names=allowed_company_name_set,
        allowed_company_domain=allowed_company_domain,
        jd_excerpt=jd_excerpt,
    )
    normalized = candidate_stripped if isinstance(candidate_stripped, dict) else normalized
    if debug_context.get("rejected_output"):
        normalized["status"] = "partial"
    normalized["debug_context"] = debug_context

    known_keys = {
        "status",
        "title_strategy",
        "header_shape",
        "section_order",
        "shape",
        "order",
        "section_emphasis",
        "ai_section_policy",
        "ai_policy",
        "counts",
        "ats_envelope",
        "evidence_density",
        "seniority_signal_strength",
        "compression_rules",
        "omission_rules",
        "unresolved_markers",
        "rationale",
        "debug_context",
        "confidence",
        "evidence",
    }
    for extra_key in sorted(set(raw.keys()) - known_keys):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": extra_key, "value": raw.get(extra_key), "note": "unknown top-level cv shape field retained"},
        )
    return normalized


def normalize_ideal_candidate_payload(
    payload: dict[str, Any] | None,
    *,
    evaluator_coverage_target: list[str] | None = None,
    expected_title_strategy: str | None = None,
    allowed_company_names: list[str] | None = None,
    allowed_company_domain: str | None = None,
    jd_excerpt: str = "",
) -> dict[str, Any]:
    raw = dict(payload or {})
    debug_context = _clean_debug_context(raw.get("debug_context"))
    initial_rejected_count = len(debug_context.get("rejected_output") or [])
    normalized: dict[str, Any] = {}

    normalized["status"] = _coerce_enum_choice(
        raw.get("status"),
        allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
        default="unresolved",
    )
    normalized["visible_identity"] = _coerce_text(raw.get("visible_identity") or raw.get("identity") or raw.get("framing_label"))
    if raw.get("identity") is not None and raw.get("visible_identity") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:identity->visible_identity")
    if raw.get("framing_label") is not None and raw.get("visible_identity") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:framing_label->visible_identity")

    acceptable_titles_raw = raw.get("acceptable_titles") or raw.get("titles") or raw.get("title_options")
    if acceptable_titles_raw is raw.get("titles"):
        _debug_append_event(debug_context, "normalization_events", "alias:titles->acceptable_titles")
    if acceptable_titles_raw is raw.get("title_options"):
        _debug_append_event(debug_context, "normalization_events", "alias:title_options->acceptable_titles")
    acceptable_titles: list[str] = []
    seen_titles: set[str] = set()
    allowed_company_name_set = {item.lower() for item in _normalize_string_list(allowed_company_names)}
    for index, item in enumerate(_normalize_string_list(acceptable_titles_raw)):
        cleaned = _strip_candidate_leakage(
            item,
            path=f"ideal_candidate_presentation_model.acceptable_titles[{index}]",
            debug_context=debug_context,
            allowed_company_names=allowed_company_name_set,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
            enforce_proper_noun_rule=False,
        )
        title = _coerce_text(cleaned)
        if not title:
            continue
        lowered = title.lower()
        if lowered in seen_titles:
            continue
        seen_titles.add(lowered)
        acceptable_titles.append(title)
    normalized["acceptable_titles"] = acceptable_titles[:5]

    normalized["title_strategy"] = _coerce_enum_choice(
        raw.get("title_strategy"),
        allowed={"exact_match", "closest_truthful", "functional_label", "unresolved"},
        default=_normalize_slug(expected_title_strategy) if expected_title_strategy else "unresolved",
    )

    def _normalize_signal_entries(value: Any, *, path: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for index, item in enumerate(_coerce_list(value)):
            payload_item = item if isinstance(item, dict) else {"tag": item}
            tag = _normalize_slug(payload_item.get("tag") or payload_item.get("signal") or payload_item.get("label"))
            if tag not in _IDEAL_CANDIDATE_SIGNAL_TAGS:
                _debug_append_event(debug_context, "rejected_output", {"path": f"{path}[{index}].tag", "reason": f"invalid_signal_tag:{tag}"})
                continue
            proof_category = _normalize_slug(payload_item.get("proof_category"))
            if proof_category and proof_category not in _PROOF_CATEGORIES:
                _debug_append_event(
                    debug_context,
                    "rejected_output",
                    {"path": f"{path}[{index}].proof_category", "reason": f"invalid_proof_category:{proof_category}"},
                )
                proof_category = None
            rationale = _strip_candidate_leakage(
                _coerce_text(payload_item.get("rationale")),
                path=f"{path}[{index}].rationale",
                debug_context=debug_context,
                allowed_company_names=allowed_company_name_set,
                allowed_company_domain=allowed_company_domain,
                jd_excerpt=jd_excerpt,
                enforce_proper_noun_rule=False,
            )
            entries.append(
                {
                    "tag": tag,
                    "proof_category": proof_category,
                    "rationale": rationale,
                    "evidence_refs": _coerce_presentation_evidence_refs(payload_item.get("evidence_refs") or payload_item.get("evidence")),
                }
            )
        return entries

    normalized["must_signal"] = _normalize_signal_entries(raw.get("must_signal") or raw.get("must_have_signals"), path="ideal_candidate_presentation_model.must_signal")
    if raw.get("must_have_signals") is not None and raw.get("must_signal") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:must_have_signals->must_signal")
    normalized["should_signal"] = _normalize_signal_entries(raw.get("should_signal") or raw.get("secondary_signals"), path="ideal_candidate_presentation_model.should_signal")
    if raw.get("secondary_signals") is not None and raw.get("should_signal") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:secondary_signals->should_signal")
    normalized["de_emphasize"] = _normalize_signal_entries(raw.get("de_emphasize") or raw.get("downplay"), path="ideal_candidate_presentation_model.de_emphasize")
    if raw.get("downplay") is not None and raw.get("de_emphasize") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:downplay->de_emphasize")

    proof_ladder_entries: list[dict[str, Any]] = []
    for index, item in enumerate(_coerce_list(raw.get("proof_ladder") or raw.get("proof_order_with_signals"))):
        payload_item = item if isinstance(item, dict) else {"proof_category": item}
        proof_category = _normalize_slug(payload_item.get("proof_category") or payload_item.get("category"))
        signal_tag = _normalize_slug(payload_item.get("signal_tag") or payload_item.get("signal") or payload_item.get("tag"))
        if proof_category not in _PROOF_CATEGORIES:
            _debug_append_event(debug_context, "rejected_output", {"path": f"proof_ladder[{index}].proof_category", "reason": f"invalid_proof_category:{proof_category}"})
            continue
        if signal_tag not in _IDEAL_CANDIDATE_SIGNAL_TAGS:
            _debug_append_event(debug_context, "rejected_output", {"path": f"proof_ladder[{index}].signal_tag", "reason": f"invalid_signal_tag:{signal_tag}"})
            continue
        rationale = _strip_candidate_leakage(
            _coerce_text(payload_item.get("rationale")),
            path=f"ideal_candidate_presentation_model.proof_ladder[{index}].rationale",
            debug_context=debug_context,
            allowed_company_names=allowed_company_name_set,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
            enforce_proper_noun_rule=False,
        )
        proof_ladder_entries.append(
            {
                "proof_category": proof_category,
                "signal_tag": signal_tag,
                "rationale": rationale,
                "evidence_refs": _coerce_presentation_evidence_refs(payload_item.get("evidence_refs") or payload_item.get("evidence")),
            }
        )
    normalized["proof_ladder"] = proof_ladder_entries

    tone_raw = raw.get("tone_profile") or raw.get("tone") or {}
    if raw.get("tone") is not None and raw.get("tone_profile") is None:
        _debug_append_event(debug_context, "normalization_events", "alias:tone->tone_profile")
    normalized["tone_profile"] = {
        "primary_tone": _coerce_enum_choice(
            tone_raw.get("primary_tone"),
            allowed={"evidence_first", "operator_first", "architect_first", "leader_first", "balanced"},
            default="balanced",
        ),
        "hype_tolerance": _coerce_enum_choice(tone_raw.get("hype_tolerance"), allowed={"low", "medium", "high"}, default="medium"),
        "narrative_tolerance": _coerce_enum_choice(tone_raw.get("narrative_tolerance"), allowed={"low", "medium", "high"}, default="medium"),
        "formality": _coerce_enum_choice(tone_raw.get("formality"), allowed={"informal", "neutral", "formal"}, default="neutral"),
    }

    credibility_markers: list[dict[str, Any]] = []
    for index, item in enumerate(_coerce_list(raw.get("credibility_markers"))):
        payload_item = item if isinstance(item, dict) else {"marker": item}
        marker = _normalize_slug(payload_item.get("marker") or payload_item.get("tag"))
        proof_category = _normalize_slug(payload_item.get("proof_category"))
        if marker not in _IDEAL_CANDIDATE_CREDIBILITY_MARKERS:
            _debug_append_event(debug_context, "rejected_output", {"path": f"credibility_markers[{index}].marker", "reason": f"invalid_credibility_marker:{marker}"})
            continue
        if proof_category and proof_category not in _PROOF_CATEGORIES:
            _debug_append_event(debug_context, "rejected_output", {"path": f"credibility_markers[{index}].proof_category", "reason": f"invalid_proof_category:{proof_category}"})
            proof_category = None
        credibility_markers.append(
            {
                "marker": marker,
                "proof_category": proof_category,
                "rationale": _strip_candidate_leakage(
                    _coerce_text(payload_item.get("rationale")),
                    path=f"ideal_candidate_presentation_model.credibility_markers[{index}].rationale",
                    debug_context=debug_context,
                    allowed_company_names=allowed_company_name_set,
                    allowed_company_domain=allowed_company_domain,
                    jd_excerpt=jd_excerpt,
                    enforce_proper_noun_rule=False,
                ),
                "evidence_refs": _coerce_presentation_evidence_refs(payload_item.get("evidence_refs") or payload_item.get("evidence")),
            }
        )
    normalized["credibility_markers"] = credibility_markers

    risk_flags: list[dict[str, Any]] = []
    for index, item in enumerate(_coerce_list(raw.get("risk_flags") or raw.get("guardrails"))):
        payload_item = item if isinstance(item, dict) else {"flag": item}
        flag = _normalize_slug(payload_item.get("flag") or payload_item.get("risk_id"))
        if flag not in _IDEAL_CANDIDATE_RISK_FLAGS:
            _debug_append_event(debug_context, "rejected_output", {"path": f"risk_flags[{index}].flag", "reason": f"invalid_risk_flag:{flag}"})
            continue
        risk_flags.append(
            {
                "flag": flag,
                "severity": _coerce_enum_choice(payload_item.get("severity"), allowed={"low", "medium", "high"}, default="medium"),
                "rationale": _strip_candidate_leakage(
                    _coerce_text(payload_item.get("rationale")),
                    path=f"ideal_candidate_presentation_model.risk_flags[{index}].rationale",
                    debug_context=debug_context,
                    allowed_company_names=allowed_company_name_set,
                    allowed_company_domain=allowed_company_domain,
                    jd_excerpt=jd_excerpt,
                    enforce_proper_noun_rule=False,
                ),
                "evidence_refs": _coerce_presentation_evidence_refs(payload_item.get("evidence_refs") or payload_item.get("evidence")),
            }
        )
    normalized["risk_flags"] = risk_flags

    audience_variants_raw = raw.get("audience_variants") or raw.get("audiences") or {}
    if audience_variants_raw is raw.get("audiences"):
        _debug_append_event(debug_context, "normalization_events", "alias:audiences->audience_variants")
    audience_variants: dict[str, Any] = {}
    if isinstance(audience_variants_raw, dict):
        for key, entry in audience_variants_raw.items():
            role = _normalize_audience_role_key(key)
            if not role:
                _debug_append_event(debug_context, "rejected_output", {"path": f"audience_variants.{key}", "reason": "invalid_evaluator_role"})
                continue
            payload_item = entry if isinstance(entry, dict) else {"must_land": entry}
            must_land = [item for item in (_normalize_slug(item) for item in _normalize_string_list(payload_item.get("must_land") or payload_item.get("must_see"))) if item in _IDEAL_CANDIDATE_SIGNAL_TAGS]
            de_emphasize = [item for item in (_normalize_slug(item) for item in _normalize_string_list(payload_item.get("de_emphasize") or payload_item.get("downplay"))) if item in _IDEAL_CANDIDATE_SIGNAL_TAGS]
            audience_variants[role] = {
                "tilt": _normalize_string_list(payload_item.get("tilt")),
                "must_land": must_land,
                "de_emphasize": de_emphasize,
                "rationale": _strip_candidate_leakage(
                    _coerce_text(payload_item.get("rationale")),
                    path=f"ideal_candidate_presentation_model.audience_variants.{role}.rationale",
                    debug_context=debug_context,
                    allowed_company_names=allowed_company_name_set,
                    allowed_company_domain=allowed_company_domain,
                    jd_excerpt=jd_excerpt,
                    enforce_proper_noun_rule=False,
                ),
            }
    normalized["audience_variants"] = audience_variants

    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="ideal_candidate_normalized")
    normalized["defaults_applied"] = _normalize_string_list(raw.get("defaults_applied"))
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["evidence_refs"] = _coerce_presentation_evidence_refs(raw.get("evidence_refs") or raw.get("evidence"))
    normalized["debug_context"] = debug_context

    visible_identity = normalized.get("visible_identity")
    if visible_identity:
        stripped_identity = _strip_candidate_leakage(
            visible_identity,
            path="ideal_candidate_presentation_model.visible_identity",
            debug_context=debug_context,
            allowed_company_names=allowed_company_name_set,
            allowed_company_domain=allowed_company_domain,
            jd_excerpt=jd_excerpt,
            enforce_proper_noun_rule=False,
        )
        normalized["visible_identity"] = _coerce_text(stripped_identity)

    if len(debug_context.get("rejected_output") or []) > initial_rejected_count:
        normalized["status"] = "partial"

    known_keys = {
        "status",
        "visible_identity",
        "identity",
        "framing_label",
        "acceptable_titles",
        "titles",
        "title_options",
        "title_strategy",
        "must_signal",
        "must_have_signals",
        "should_signal",
        "secondary_signals",
        "de_emphasize",
        "downplay",
        "proof_ladder",
        "proof_order_with_signals",
        "tone_profile",
        "tone",
        "credibility_markers",
        "risk_flags",
        "guardrails",
        "audience_variants",
        "audiences",
        "confidence",
        "defaults_applied",
        "unresolved_markers",
        "evidence_refs",
        "evidence",
        "debug_context",
    }
    for extra_key in sorted(set(raw.keys()) - known_keys):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": extra_key, "value": raw.get(extra_key), "note": "unknown top-level ideal candidate field retained"},
        )

    if evaluator_coverage_target:
        normalized["debug_context"]["input_summary"] = {
            **dict(normalized["debug_context"].get("input_summary") or {}),
            "evaluator_roles_in_scope": [item for item in evaluator_coverage_target if item in {
                "recruiter",
                "hiring_manager",
                "skip_level_leader",
                "peer_technical",
                "cross_functional_partner",
                "executive_sponsor",
            }],
        }
    return normalized


PainSourceScope = Literal["jd_only", "jd_plus_research", "supplemental_web"]
PainPointStatus = Literal["completed", "partial", "unresolved"]
PainCategoryEnum = Literal["technical", "business", "delivery", "org", "stakeholder", "application"]
StrategicNeedCategoryEnum = Literal["technical", "business", "delivery", "org", "stakeholder", "application"]
RiskCategoryEnum = Literal["technical", "business", "delivery", "org", "stakeholder", "application"]
SuccessMetricKindEnum = Literal["outcome", "leading", "lagging", "qualitative"]
SuccessMetricHorizonEnum = Literal["30_day", "90_day", "6_month", "12_month", "multi_year"]
SearchTermIntent = Literal["retrieval", "disambiguation", "ats"]

_PAIN_CATEGORIES = {"technical", "business", "delivery", "org", "stakeholder", "application"}
_PAIN_SOURCE_SCOPES = {"jd_only", "jd_plus_research", "supplemental_web"}
_PAIN_STATUSES = {"completed", "partial", "unresolved"}
_SUCCESS_METRIC_KINDS = {"outcome", "leading", "lagging", "qualitative"}
_SUCCESS_METRIC_HORIZONS = {"30_day", "90_day", "6_month", "12_month", "multi_year"}
_SEARCH_TERM_INTENTS = {"retrieval", "disambiguation", "ats"}
_GENERIC_PAIN_STOPLIST = {
    "team player",
    "strong communicator",
    "passionate about",
    "fast paced environment",
    "fast-paced environment",
    "rockstar",
    "ninja",
}
_PAIN_FAIL_OPEN_REASONS = {
    "jd_only_fallback",
    "thin_research",
    "schema_repair_exhausted",
    "supplemental_web_unavailable",
    "llm_terminal_failure",
}
_RECOVERABLE_PAIN_REPAIR_REASONS = {
    "missing_evidence_ref",
    "duplicate_pain_id",
    "proof_map_orphan_fk",
    "enum_drift",
    "cross_category_duplication",
}


def _normalize_pain_category(value: Any, *, default: str = "business") -> str:
    return _coerce_enum_choice(value, allowed=_PAIN_CATEGORIES, default=default)


def _normalize_pain_source_scope(value: Any, *, default: str = "jd_only") -> str:
    return _coerce_enum_choice(value, allowed=_PAIN_SOURCE_SCOPES, default=default)


def _normalize_search_term_intent(value: Any) -> str:
    return _coerce_enum_choice(value, allowed=_SEARCH_TERM_INTENTS, default="retrieval")


def _normalize_metric_kind(value: Any) -> str:
    return _coerce_enum_choice(value, allowed=_SUCCESS_METRIC_KINDS, default="qualitative")


def _normalize_metric_horizon(value: Any) -> str | None:
    text = _coerce_text(value)
    if text is None:
        return None
    return _coerce_enum_choice(text, allowed=_SUCCESS_METRIC_HORIZONS, default="90_day")


def _normalize_evidence_refs(value: Any) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for item in _coerce_list(value):
        if isinstance(item, dict):
            source_ids = _normalize_string_list(item.get("source_ids"))
            if source_ids:
                for source_id in source_ids:
                    normalized = f"source:{source_id}"
                    if normalized not in seen:
                        seen.add(normalized)
                        refs.append(normalized)
                continue
            candidate = _coerce_text(item.get("evidence_ref") or item.get("ref") or item.get("path") or item.get("source"))
        else:
            candidate = _coerce_text(item)
        if not candidate:
            continue
        normalized = candidate.strip()
        if normalized.startswith("source:") or normalized.startswith("artifact:"):
            pass
        elif normalized.startswith("src_") or normalized.startswith("jd:") or normalized.startswith("supp:"):
            normalized = f"source:{normalized}"
        else:
            normalized = f"artifact:{normalized}"
        if normalized not in seen:
            seen.add(normalized)
            refs.append(normalized)
    return refs


def _statement_key(value: str | None) -> str:
    text = (value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _pain_id(category: str, statement: str) -> str:
    digest = hashlib.sha256(f"{category}|{_statement_key(statement)}".encode("utf-8")).hexdigest()[:8]
    return f"p_{category}_{digest}"


def _evidence_path_exists(path: str, inputs: dict[str, Any]) -> bool:
    current: Any = inputs
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return False
            current = current[part]
            continue
        if isinstance(current, list) and part.endswith("]") and "[" in part:
            key, index_text = part[:-1].split("[", 1)
            if key:
                return False
            try:
                index = int(index_text)
            except Exception:
                return False
            if index < 0 or index >= len(current):
                return False
            current = current[index]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except Exception:
                return False
            if index < 0 or index >= len(current):
                return False
            current = current[index]
            continue
        return False
    return True


def pain_input_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _coerce_dimension_weight_value(
    value: Any,
    *,
    path: str,
    debug_context: dict[str, Any],
    normalization_events: list[dict[str, Any]],
) -> int | None:
    if isinstance(value, bool):
        _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": "non_integer_value"})
        return None
    if isinstance(value, int):
        if value < 0:
            _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": "negative_weight"})
            return None
        return value
    if isinstance(value, float):
        if value < 0:
            _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": "negative_weight"})
            return None
        if not value.is_integer():
            _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": "non_integer_value"})
            return None
        numeric = int(value)
        normalization_events.append(
            {"kind": "float_to_int", "from": value, "to": numeric, "reason": "float_looking_integer", "path": path}
        )
        return numeric
    text = _coerce_text(value)
    if not text:
        return None
    if re.fullmatch(r"\d+", text):
        return int(text)
    if re.fullmatch(r"\d+\.0+", text):
        numeric = int(float(text))
        normalization_events.append(
            {"kind": "float_string_to_int", "from": text, "to": numeric, "reason": "float_looking_integer", "path": path}
        )
        return numeric
    if re.fullmatch(r"\d+\.\d+", text):
        _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": "non_integer_value"})
        return None
    _debug_append_event(debug_context, "rejected_output", {"path": path, "reason": "non_integer_value"})
    return None


def _normalize_dimension_weight_map_payload(
    raw_map: Any,
    *,
    path: str,
    debug_context: dict[str, Any],
    normalization_events: list[dict[str, Any]],
) -> dict[str, int]:
    if not isinstance(raw_map, dict):
        return {}
    normalized: dict[str, int] = {}
    for raw_key, raw_value in raw_map.items():
        dimension = _normalize_experience_dimension(raw_key)
        if not dimension:
            _debug_append_event(debug_context, "rejected_output", {"path": f"{path}.{raw_key}", "reason": "unknown_dimension"})
            continue
        numeric = _coerce_dimension_weight_value(
            raw_value,
            path=f"{path}.{dimension}",
            debug_context=debug_context,
            normalization_events=normalization_events,
        )
        if numeric is None:
            continue
        normalized[dimension] = numeric
    return normalized


def _normalize_dimension_overuse_risk_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, ExperienceDimensionOveruseRiskDoc):
        return item.model_dump(by_alias=True)
    if not isinstance(item, dict):
        return None
    dimension = _normalize_experience_dimension(item.get("dimension") or item.get("applies_to"))
    if not dimension:
        return None
    return {
        "dimension": dimension,
        "reason": _normalize_overuse_risk_reason(item.get("reason")),
        "threshold": item.get("threshold"),
        "mitigation": _coerce_enum_choice(
            item.get("mitigation"),
            allowed={"softened_form", "omit", "proof_first"},
            default="proof_first",
        ),
    }


def _normalize_dimension_normalization_event_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, ExperienceDimensionNormalizationEventDoc):
        return item.model_dump(by_alias=True)
    if isinstance(item, str):
        text = _coerce_text(item)
        if not text:
            return None
        return {"kind": text, "from": None, "to": None, "reason": text, "path": None}
    if not isinstance(item, dict):
        return None
    return {
        "kind": _coerce_text(item.get("kind")) or "normalization",
        "from": item.get("from") if "from" in item else item.get("from_value"),
        "to": item.get("to") if "to" in item else item.get("to_value"),
        "reason": _coerce_text(item.get("reason")) or "normalization",
        "path": _coerce_text(item.get("path")),
    }


def normalize_experience_dimension_weights_payload(
    payload: dict[str, Any] | None,
    *,
    evaluator_coverage_target: list[str] | None = None,
    allowed_company_names: list[str] | None = None,
    allowed_company_domain: str | None = None,
    jd_excerpt: str = "",
) -> dict[str, Any]:
    raw = dict(payload or {})
    debug_context = _clean_debug_context(raw.get("debug_context"))
    normalization_events: list[dict[str, Any]] = []
    normalized: dict[str, Any] = {}
    allowed_company_name_set = {item.lower() for item in _normalize_string_list(allowed_company_names)}

    normalized["status"] = _coerce_enum_choice(
        raw.get("status"),
        allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
        default="unresolved",
    )
    normalized["source_scope"] = _normalize_experience_source_scope(
        raw.get("source_scope") or raw.get("scope"),
        default="jd_only",
    )
    if raw.get("scope") is not None and raw.get("source_scope") is None:
        normalization_events.append(
            {"kind": "alias", "from": "scope", "to": "source_scope", "reason": "alias_scope", "path": "source_scope"}
        )
    normalized["dimension_enum_version"] = _coerce_text(raw.get("dimension_enum_version")) or DIMENSION_ENUM_VERSION
    normalized["prompt_version"] = _coerce_text(raw.get("prompt_version"))
    normalized["prompt_metadata"] = raw.get("prompt_metadata")
    normalized["overall_weights"] = _normalize_dimension_weight_map_payload(
        raw.get("overall_weights") or raw.get("weights") or raw.get("overall"),
        path="overall_weights",
        debug_context=debug_context,
        normalization_events=normalization_events,
    )
    if raw.get("weights") is not None and raw.get("overall_weights") is None:
        normalization_events.append(
            {"kind": "alias", "from": "weights", "to": "overall_weights", "reason": "alias_weights", "path": "overall_weights"}
        )
    if raw.get("overall") is not None and raw.get("overall_weights") is None:
        normalization_events.append(
            {"kind": "alias", "from": "overall", "to": "overall_weights", "reason": "alias_overall", "path": "overall_weights"}
        )

    variant_weights_raw = raw.get("stakeholder_variant_weights") or raw.get("audience_variant_weights") or raw.get("variants") or {}
    if raw.get("audience_variant_weights") is not None and raw.get("stakeholder_variant_weights") is None:
        normalization_events.append(
            {"kind": "alias", "from": "audience_variant_weights", "to": "stakeholder_variant_weights", "reason": "alias_variant_weights", "path": "stakeholder_variant_weights"}
        )
    normalized_variants: dict[str, dict[str, int] | None] = {}
    if isinstance(variant_weights_raw, dict):
        for raw_key, weight_map in variant_weights_raw.items():
            role = _normalize_audience_role_key(raw_key)
            if not role:
                _debug_append_event(debug_context, "rejected_output", {"path": f"stakeholder_variant_weights.{raw_key}", "reason": "invalid_evaluator_role"})
                continue
            if weight_map is None:
                normalized_variants[role] = None
                continue
            normalized_variants[role] = _normalize_dimension_weight_map_payload(
                weight_map,
                path=f"stakeholder_variant_weights.{role}",
                debug_context=debug_context,
                normalization_events=normalization_events,
            )
    normalized["stakeholder_variant_weights"] = normalized_variants
    normalized["minimum_visible_dimensions"] = _normalize_experience_dimension_list(
        raw.get("minimum_visible_dimensions") or raw.get("minimum_visible") or raw.get("minimum_visible_experience_dimensions")
    )[:5]
    normalized["overuse_risks"] = [
        entry
        for entry in (_normalize_dimension_overuse_risk_payload(item) for item in _coerce_list(raw.get("overuse_risks")))
        if entry
    ]
    normalized["rationale"] = _coerce_text(raw.get("rationale"))
    normalized["unresolved_markers"] = _normalize_string_list(raw.get("unresolved_markers"))
    normalized["defaults_applied"] = _normalize_string_list(raw.get("defaults_applied"))
    normalized["normalization_events"] = [
        event
        for event in (
            _normalize_dimension_normalization_event_payload(item) for item in _coerce_list(raw.get("normalization_events"))
        )
        if event
    ] + normalization_events
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="experience_dimension_weights_normalized")
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))
    normalized["notes"] = _normalize_string_list(raw.get("notes"))
    normalized["fail_open_reason"] = _coerce_text(raw.get("fail_open_reason"))

    known_keys = {
        "status",
        "source_scope",
        "scope",
        "dimension_enum_version",
        "prompt_version",
        "prompt_metadata",
        "overall_weights",
        "weights",
        "overall",
        "stakeholder_variant_weights",
        "audience_variant_weights",
        "variants",
        "minimum_visible_dimensions",
        "minimum_visible",
        "minimum_visible_experience_dimensions",
        "overuse_risks",
        "rationale",
        "unresolved_markers",
        "defaults_applied",
        "normalization_events",
        "confidence",
        "evidence",
        "notes",
        "debug_context",
        "fail_open_reason",
    }
    for extra_key in sorted(set(raw.keys()) - known_keys):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": extra_key, "value": raw.get(extra_key), "note": "unknown top-level dimension weights field retained"},
        )

    candidate_stripped = _strip_candidate_leakage(
        normalized,
        path="experience_dimension_weights",
        debug_context=debug_context,
        allowed_company_names=allowed_company_name_set,
        allowed_company_domain=allowed_company_domain,
        jd_excerpt=jd_excerpt,
        enforce_proper_noun_rule=False,
    )
    normalized = candidate_stripped if isinstance(candidate_stripped, dict) else normalized
    if debug_context.get("rejected_output"):
        normalized["status"] = "partial"

    debug_context["defaults_applied"] = list(
        dict.fromkeys([*list(debug_context.get("defaults_applied") or []), *list(normalized.get("defaults_applied") or [])])
    )
    debug_context["normalization_events"] = [
        _normalize_dimension_normalization_event_payload(item)
        for item in normalized.get("normalization_events") or []
        if _normalize_dimension_normalization_event_payload(item)
    ]
    if evaluator_coverage_target:
        summary = dict(debug_context.get("input_summary") or {})
        summary["evaluator_roles_in_scope"] = [
            item
            for item in evaluator_coverage_target
            if item in {
                "recruiter",
                "hiring_manager",
                "skip_level_leader",
                "peer_technical",
                "cross_functional_partner",
                "executive_sponsor",
            }
        ]
        debug_context["input_summary"] = summary
    normalized["debug_context"] = debug_context
    return normalized


def _restrictive_rule_rank(rule_type: str) -> int:
    return {
        "allowed_if_evidenced": 0,
        "prefer_softened_form": 1,
        "require_credibility_marker": 1,
        "require_proof_for_emphasis": 1,
        "omit_if_weak": 2,
        "suppress_audience_variant_signal": 2,
        "forbid_without_direct_proof": 3,
        "cap_dimension_weight": 3,
        "never_infer_from_job_only": 4,
    }.get(rule_type, 0)


def _normalize_emphasis_rule_payload(
    item: Any,
    *,
    bucket_hint: str | None,
    section_id: str | None,
    debug_context: dict[str, Any],
    normalization_events: list[dict[str, Any]],
    allowed_company_names: set[str],
    allowed_company_domain: str | None,
    jd_excerpt: str,
) -> dict[str, Any] | None:
    if isinstance(item, Rule):
        payload = item.model_dump()
    elif isinstance(item, dict):
        payload = dict(item)
    else:
        text = _canonical_emphasis_text(item, limit=240)
        if not text:
            return None
        _debug_append_event(
            debug_context,
            "rejected_output",
            {"path": bucket_hint or "rule", "reason": "rule_entries_must_be_objects"},
        )
        return None

    rule_type = _normalize_rule_type(payload.get("rule_type"))
    if not rule_type and bucket_hint in {"allowed_if_evidenced", "downgrade_rules", "omit_rules"}:
        rule_type = {
            "allowed_if_evidenced": "allowed_if_evidenced",
            "downgrade_rules": "prefer_softened_form",
            "omit_rules": "omit_if_weak",
        }[bucket_hint]
        normalization_events.append(
            {"kind": "precedence_assigned", "from": bucket_hint, "to": rule_type, "reason": "bucket_default_rule_type", "path": bucket_hint}
        )
    if not rule_type:
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "invalid_rule_type"})
        return None

    topic_family = _normalize_rule_topic_family(payload.get("topic_family"))
    if not topic_family:
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "invalid_topic_family"})
        return None

    raw_applies_to_kind = payload.get("applies_to_kind")
    raw_applies_to = payload.get("applies_to")
    applies_to_kind = _normalize_applies_to_kind(raw_applies_to_kind)
    applies_to = None
    if section_id:
        applies_to_kind = "section"
        applies_to = section_id
    elif applies_to_kind:
        applies_to = _resolve_applies_to_value(raw_applies_to, applies_to_kind=applies_to_kind)
    elif raw_applies_to not in (None, ""):
        inferred_kind, inferred_value = _infer_applies_to_pair(raw_applies_to)
        if inferred_kind and inferred_value:
            applies_to_kind, applies_to = inferred_kind, inferred_value
            normalization_events.append(
                {
                    "kind": "alias_mapped",
                    "from": _canonical_emphasis_text(raw_applies_to, limit=80),
                    "to": f"{applies_to_kind}:{applies_to}",
                    "reason": "applies_to_inferred",
                    "path": bucket_hint or "rule.applies_to",
                }
            )
    if not applies_to_kind and not raw_applies_to and bucket_hint == "global_rules":
        applies_to_kind = "global"
        applies_to = "global"
    if applies_to_kind == "global" and not applies_to:
        applies_to = "global"
    if not applies_to_kind or not applies_to:
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "applies_to_kind_value_mismatch"})
        return None

    evidence_refs = _normalize_emphasis_evidence_refs(payload.get("evidence_refs") or payload.get("source_refs"))
    if not evidence_refs:
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "missing_evidence_refs"})
        return None

    condition = _canonical_emphasis_text(payload.get("condition"), limit=240)
    action = _canonical_emphasis_text(payload.get("action"), limit=240)
    basis = _canonical_emphasis_text(payload.get("basis") or payload.get("rationale"), limit=200)
    if not condition or not action or not basis:
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "missing_required_rule_text"})
        return None

    cap_value = payload.get("cap_value") if payload.get("cap_value") is not None else payload.get("cap")
    precedence = _normalize_rule_precedence(payload.get("precedence"), rule_type=rule_type)
    if payload.get("precedence") in (None, ""):
        normalization_events.append(
            {
                "kind": "precedence_assigned",
                "from": None,
                "to": precedence,
                "reason": "default_from_rule_type",
                "path": bucket_hint or "rule.precedence",
            }
        )

    rule_id = _coerce_text(payload.get("rule_id"))
    derived_rule_id = _derive_emphasis_rule_id(
        topic_family=topic_family,
        applies_to_kind=applies_to_kind,
        applies_to=applies_to,
        condition=condition,
    )
    if not rule_id:
        rule_id = derived_rule_id
        normalization_events.append(
            {
                "kind": "id_renormalized",
                "from": None,
                "to": rule_id,
                "reason": "derived_rule_id",
                "path": bucket_hint or "rule.rule_id",
            }
        )
    else:
        normalized_rule_id = re.sub(r"[^a-z0-9_]+", "_", rule_id.lower()).strip("_")[:64]
        if normalized_rule_id != rule_id:
            normalization_events.append(
                {
                    "kind": "id_renormalized",
                    "from": rule_id,
                    "to": normalized_rule_id,
                    "reason": "normalized_rule_id",
                    "path": bucket_hint or "rule.rule_id",
                }
            )
        rule_id = normalized_rule_id

    normalized = {
        "rule_id": rule_id,
        "rule_type": rule_type,
        "topic_family": topic_family,
        "applies_to": applies_to,
        "applies_to_kind": applies_to_kind,
        "condition": condition,
        "action": action,
        "basis": basis,
        "evidence_refs": evidence_refs,
        "precedence": precedence,
        "cap_value": cap_value,
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="emphasis_rule_normalized"),
    }
    for extra_key in sorted(set(payload.keys()) - {"rule_id", "rule_type", "topic_family", "applies_to", "applies_to_kind", "condition", "action", "basis", "rationale", "evidence_refs", "source_refs", "precedence", "cap_value", "cap", "confidence"}):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": f"{bucket_hint or 'rule'}.{extra_key}", "value": payload.get(extra_key), "note": "unknown rule field retained"},
        )
    candidate_stripped = _strip_candidate_leakage(
        normalized,
        path=f"truth_constrained_emphasis_rules.{bucket_hint or 'rule'}",
        debug_context=debug_context,
        allowed_company_names=allowed_company_names,
        allowed_company_domain=allowed_company_domain,
        jd_excerpt=jd_excerpt,
        enforce_proper_noun_rule=True,
    )
    normalized = candidate_stripped if isinstance(candidate_stripped, dict) else normalized
    if not all(normalized.get(field) for field in ("condition", "action", "basis")):
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "candidate_leakage"})
        return None
    if rule_type == "cap_dimension_weight" and _resolve_applies_to_value(applies_to, applies_to_kind=applies_to_kind or "") != applies_to:
        _debug_append_event(debug_context, "rejected_output", {"path": bucket_hint or "rule", "reason": "cap_dimension_weight_unknown_dimension"})
        return None
    return normalized


def _normalize_forbidden_claim_pattern_payload(
    item: Any,
    *,
    debug_context: dict[str, Any],
    normalization_events: list[dict[str, Any]],
    allowed_company_names: set[str],
    allowed_company_domain: str | None,
    jd_excerpt: str,
) -> dict[str, Any] | None:
    payload = item.model_dump() if isinstance(item, ForbiddenClaimPattern) else dict(item or {}) if isinstance(item, dict) else {}
    pattern = _canonical_emphasis_text(payload.get("pattern"), limit=160)
    reason = _canonical_emphasis_text(payload.get("reason"), limit=200)
    if not pattern or not reason:
        return None
    pattern_kind = _normalize_emphasis_pattern_kind(payload.get("pattern_kind"))
    if pattern_kind == "regex_safe" and not _is_regex_safe_pattern(pattern):
        _debug_append_event(debug_context, "rejected_output", {"path": "forbidden_claim_patterns", "reason": "regex_outside_whitelist"})
        return None
    pattern_id = _coerce_text(payload.get("pattern_id")) or re.sub(r"[^a-z0-9_]+", "_", pattern.lower()).strip("_")[:64]
    if not payload.get("pattern_id"):
        normalization_events.append(
            {"kind": "id_renormalized", "from": None, "to": pattern_id, "reason": "derived_pattern_id", "path": "forbidden_claim_patterns.pattern_id"}
        )
    example = _canonical_emphasis_text(payload.get("example"), limit=160)
    normalized = {
        "pattern_id": pattern_id,
        "pattern": pattern,
        "pattern_kind": pattern_kind,
        "reason": reason,
        "example": example,
        "evidence_refs": _normalize_emphasis_evidence_refs(payload.get("evidence_refs") or payload.get("source_refs")),
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="forbidden_claim_pattern_normalized"),
    }
    candidate_stripped = _strip_candidate_leakage(
        normalized,
        path="truth_constrained_emphasis_rules.forbidden_claim_patterns",
        debug_context=debug_context,
        allowed_company_names=allowed_company_names,
        allowed_company_domain=allowed_company_domain,
        jd_excerpt=jd_excerpt,
        enforce_proper_noun_rule=True,
    )
    normalized = candidate_stripped if isinstance(candidate_stripped, dict) else normalized
    if not normalized.get("pattern") or not normalized.get("reason"):
        _debug_append_event(debug_context, "rejected_output", {"path": "forbidden_claim_patterns", "reason": "candidate_leakage"})
        return None
    if not normalized.get("evidence_refs"):
        _debug_append_event(debug_context, "rejected_output", {"path": "forbidden_claim_patterns", "reason": "missing_evidence_refs"})
        return None
    return normalized


def _normalize_credibility_ladder_payload(
    item: Any,
    *,
    debug_context: dict[str, Any],
) -> dict[str, Any] | None:
    payload = item.model_dump() if isinstance(item, CredibilityLadderRule) else dict(item or {}) if isinstance(item, dict) else {}
    ladder = _normalize_proof_categories(payload.get("ladder") or payload.get("proof_chain"))
    if len(ladder) < 2:
        return None
    normalized = {
        "ladder_id": _coerce_text(payload.get("ladder_id") or payload.get("id") or "credibility_ladder") or "credibility_ladder",
        "applies_to_audience": _coerce_text(payload.get("applies_to_audience") or payload.get("audience") or "all") or "all",
        "ladder": ladder,
        "fallback_rule_id": _coerce_text(payload.get("fallback_rule_id")),
        "rationale": _canonical_emphasis_text(payload.get("rationale"), limit=200),
        "evidence_refs": _normalize_emphasis_evidence_refs(payload.get("evidence_refs") or payload.get("source_refs")),
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="credibility_ladder_normalized"),
    }
    if not normalized["fallback_rule_id"] or not normalized["evidence_refs"]:
        _debug_append_event(debug_context, "rejected_output", {"path": "credibility_ladder_rules", "reason": "missing_required_ladder_fields"})
        return None
    return normalized


def _collapse_emphasis_rule_conflicts(
    rules: list[dict[str, Any]],
    *,
    normalization_events: list[dict[str, Any]],
    conflict_log: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    duplicate_groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for rule in sorted(
        rules,
        key=lambda item: (
            str(item.get("topic_family") or ""),
            str(item.get("applies_to_kind") or ""),
            str(item.get("applies_to") or ""),
            _canonical_rule_condition(item.get("condition")),
            str(item.get("rule_id") or ""),
        ),
    ):
        key = (
            str(rule.get("topic_family") or ""),
            str(rule.get("applies_to_kind") or ""),
            str(rule.get("applies_to") or ""),
            _canonical_rule_condition(rule.get("condition")),
        )
        existing = duplicate_groups.get(key)
        if not existing:
            duplicate_groups[key] = dict(rule)
            continue
        merged_refs = list(dict.fromkeys([*(existing.get("evidence_refs") or []), *(rule.get("evidence_refs") or [])]))
        if int(rule.get("precedence") or 0) > int(existing.get("precedence") or 0):
            existing.update(rule)
        existing["evidence_refs"] = merged_refs
        normalization_events.append(
            {
                "kind": "duplicate_collapsed",
                "from": str(rule.get("rule_id") or ""),
                "to": str(existing.get("rule_id") or ""),
                "reason": "duplicate_rule_key",
                "path": f"{existing.get('topic_family')}:{existing.get('applies_to_kind')}:{existing.get('applies_to')}",
            }
        )

    conflict_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for rule in duplicate_groups.values():
        key = (
            str(rule.get("topic_family") or ""),
            str(rule.get("applies_to_kind") or ""),
            str(rule.get("applies_to") or ""),
        )
        conflict_groups.setdefault(key, []).append(rule)

    resolved: list[dict[str, Any]] = []
    for key, entries in conflict_groups.items():
        if len(entries) == 1:
            resolved.extend(entries)
            continue
        ranked = sorted(
            entries,
            key=lambda item: (
                int(item.get("precedence") or 0),
                _restrictive_rule_rank(str(item.get("rule_type") or "")),
                str(item.get("rule_id") or ""),
            ),
            reverse=True,
        )
        winner = ranked[0]
        resolved.append(winner)
        for loser in ranked[1:]:
            normalization_events.append(
                {
                    "kind": "conflict_suppressed",
                    "from": str(loser.get("rule_id") or ""),
                    "to": str(winner.get("rule_id") or ""),
                    "reason": "higher_precedence_or_more_restrictive_rule_retained",
                    "path": ":".join(key),
                }
            )
            conflict_log.append(
                {
                    "rule_id": str(loser.get("rule_id") or ""),
                    "topic_family": str(loser.get("topic_family") or ""),
                    "applies_to_kind": str(loser.get("applies_to_kind") or ""),
                    "applies_to": str(loser.get("applies_to") or ""),
                    "conflict_source": "normalizer",
                    "resolution": "suppressed",
                    "note": f"retained {winner.get('rule_id')}",
                }
            )
            conflict_log.append(
                {
                    "rule_id": str(winner.get("rule_id") or ""),
                    "topic_family": str(winner.get("topic_family") or ""),
                    "applies_to_kind": str(winner.get("applies_to_kind") or ""),
                    "applies_to": str(winner.get("applies_to") or ""),
                    "conflict_source": "normalizer",
                    "resolution": "retained",
                    "note": f"suppressed {loser.get('rule_id')}",
                }
            )
    return resolved


def _emphasis_topic_coverage_entries(
    rules: list[dict[str, Any]],
    *,
    source: str,
) -> list[dict[str, Any]]:
    counts = {family: 0 for family in _RULE_TOPIC_FAMILIES}
    for rule in rules:
        family = str(rule.get("topic_family") or "")
        if family in counts:
            counts[family] += 1
    return [
        {"topic_family": family, "rule_count": counts[family], "source": source}
        for family in sorted(_RULE_TOPIC_FAMILIES)
    ]


def normalize_truth_constrained_emphasis_rules_payload(
    payload: dict[str, Any] | None,
    *,
    evaluator_coverage_target: list[str] | None = None,
    allowed_company_names: list[str] | None = None,
    allowed_company_domain: str | None = None,
    jd_excerpt: str = "",
    coverage_source: str = "llm",
) -> dict[str, Any]:
    raw = dict(payload or {})
    debug_context = _clean_debug_context(raw.get("debug_context"))
    normalization_events: list[dict[str, Any]] = []
    for item in _coerce_list(raw.get("normalization_events")):
        if isinstance(item, dict):
            normalization_events.append(dict(item))
            continue
        note = _canonical_emphasis_text(item, limit=160)
        if note:
            debug_context.setdefault("richer_output_retained", []).append(
                {
                    "key": "normalization_events[]",
                    "value": note,
                    "note": "freeform_normalization_event_retained",
                }
            )
    allowed_company_name_set = {item.lower() for item in _normalize_string_list(allowed_company_names)}
    normalized: dict[str, Any] = {
        "status": _coerce_enum_choice(
            raw.get("status"),
            allowed={"completed", "partial", "inferred_only", "unresolved", "failed_terminal"},
            default="unresolved",
        ),
        "source_scope": _normalize_emphasis_source_scope(raw.get("source_scope") or raw.get("scope"), default="jd_only"),
        "rule_type_enum_version": _coerce_text(raw.get("rule_type_enum_version")) or RULE_TYPE_ENUM_VERSION,
        "applies_to_enum_version": _coerce_text(raw.get("applies_to_enum_version")) or APPLIES_TO_ENUM_VERSION,
        "prompt_version": _coerce_text(raw.get("prompt_version")),
        "prompt_metadata": raw.get("prompt_metadata"),
        "rationale": _canonical_emphasis_text(raw.get("rationale"), limit=800),
        "unresolved_markers": _normalize_string_list(raw.get("unresolved_markers"))[:12],
        "defaults_applied": _normalize_string_list(raw.get("defaults_applied")),
        "confidence": _coerce_confidence_payload(raw.get("confidence"), fallback_basis="truth_constrained_emphasis_rules_normalized"),
        "evidence": _coerce_evidence_entries(raw.get("evidence")),
        "notes": _normalize_string_list(raw.get("notes")),
        "fail_open_reason": _normalize_emphasis_fail_open_reason(raw.get("fail_open_reason")),
    }
    if raw.get("scope") is not None and raw.get("source_scope") is None:
        normalization_events.append(
            {"kind": "alias_mapped", "from": "scope", "to": "source_scope", "reason": "alias_scope", "path": "source_scope"}
        )

    raw_rule_entries: list[dict[str, Any]] = []
    for bucket_name in ("global_rules", "allowed_if_evidenced", "downgrade_rules", "omit_rules"):
        for item in _coerce_list(raw.get(bucket_name)):
            normalized_rule = _normalize_emphasis_rule_payload(
                item,
                bucket_hint=bucket_name,
                section_id=None,
                debug_context=debug_context,
                normalization_events=normalization_events,
                allowed_company_names=allowed_company_name_set,
                allowed_company_domain=allowed_company_domain,
                jd_excerpt=jd_excerpt,
            )
            if normalized_rule:
                raw_rule_entries.append(normalized_rule)

    section_rules_raw = raw.get("section_rules") or {}
    if isinstance(section_rules_raw, dict):
        for section_key, bucket in section_rules_raw.items():
            section_id = _normalize_slug(section_key)
            if section_id not in _PRESENTATION_SECTION_IDS:
                _debug_append_event(debug_context, "rejected_output", {"path": f"section_rules.{section_key}", "reason": "invalid_section_id"})
                continue
            for item in _coerce_list(bucket):
                normalized_rule = _normalize_emphasis_rule_payload(
                    item,
                    bucket_hint=f"section_rules.{section_id}",
                    section_id=section_id,
                    debug_context=debug_context,
                    normalization_events=normalization_events,
                    allowed_company_names=allowed_company_name_set,
                    allowed_company_domain=allowed_company_domain,
                    jd_excerpt=jd_excerpt,
                )
                if normalized_rule:
                    raw_rule_entries.append(normalized_rule)

    alias_buckets = [
        ("rules", "global_rules"),
        ("rule_set", "global_rules"),
        ("mandatory_rules", "omit_rules"),
        ("conditional_rules", "allowed_if_evidenced"),
        ("softeners", "downgrade_rules"),
        ("downgrades", "downgrade_rules"),
    ]
    for alias, bucket_name in alias_buckets:
        if alias not in raw:
            continue
        normalization_events.append(
            {"kind": "alias_mapped", "from": alias, "to": bucket_name, "reason": "bucket_alias", "path": bucket_name}
        )
        for item in _coerce_list(raw.get(alias)):
            normalized_rule = _normalize_emphasis_rule_payload(
                item,
                bucket_hint=bucket_name,
                section_id=None,
                debug_context=debug_context,
                normalization_events=normalization_events,
                allowed_company_names=allowed_company_name_set,
                allowed_company_domain=allowed_company_domain,
                jd_excerpt=jd_excerpt,
            )
            if normalized_rule:
                raw_rule_entries.append(normalized_rule)

    conflict_log: list[dict[str, Any]] = list(debug_context.get("conflict_resolution_log") or [])
    resolved_rules = _collapse_emphasis_rule_conflicts(
        raw_rule_entries,
        normalization_events=normalization_events,
        conflict_log=conflict_log,
    )

    section_rules: dict[str, list[dict[str, Any]]] = {}
    normalized["global_rules"] = []
    normalized["allowed_if_evidenced"] = []
    normalized["downgrade_rules"] = []
    normalized["omit_rules"] = []
    for rule in resolved_rules:
        rule_type = str(rule.get("rule_type") or "")
        if rule_type == "allowed_if_evidenced":
            normalized["allowed_if_evidenced"].append(rule)
        elif rule_type in {"prefer_softened_form", "suppress_audience_variant_signal"}:
            normalized["downgrade_rules"].append(rule)
        elif rule_type in {"omit_if_weak", "forbid_without_direct_proof", "never_infer_from_job_only"}:
            normalized["omit_rules"].append(rule)
        elif rule.get("applies_to_kind") == "section" and rule_type in {"require_credibility_marker", "require_proof_for_emphasis"}:
            section_rules.setdefault(str(rule.get("applies_to")), []).append(rule)
        else:
            normalized["global_rules"].append(rule)
    normalized["section_rules"] = section_rules

    normalized["forbidden_claim_patterns"] = [
        entry
        for entry in (
            _normalize_forbidden_claim_pattern_payload(
                item,
                debug_context=debug_context,
                normalization_events=normalization_events,
                allowed_company_names=allowed_company_name_set,
                allowed_company_domain=allowed_company_domain,
                jd_excerpt=jd_excerpt,
            )
            for item in _coerce_list(
                raw.get("forbidden_claim_patterns") or raw.get("forbidden_patterns") or raw.get("forbidden_phrases")
            )
        )
        if entry
    ]
    if raw.get("forbidden_patterns") is not None and raw.get("forbidden_claim_patterns") is None:
        normalization_events.append(
            {
                "kind": "alias_mapped",
                "from": "forbidden_patterns",
                "to": "forbidden_claim_patterns",
                "reason": "bucket_alias",
                "path": "forbidden_claim_patterns",
            }
        )
    normalized["credibility_ladder_rules"] = [
        entry
        for entry in (
            _normalize_credibility_ladder_payload(item, debug_context=debug_context)
            for item in _coerce_list(
                raw.get("credibility_ladder_rules") or raw.get("credibility_chain") or raw.get("proof_chain")
            )
        )
        if entry
    ]
    if raw.get("credibility_chain") is not None and raw.get("credibility_ladder_rules") is None:
        normalization_events.append(
            {
                "kind": "alias_mapped",
                "from": "credibility_chain",
                "to": "credibility_ladder_rules",
                "reason": "bucket_alias",
                "path": "credibility_ladder_rules",
            }
        )
    normalized["topic_coverage"] = [
        entry
        for entry in (
            dict(item)
            for item in (
                raw.get("topic_coverage")
                or _emphasis_topic_coverage_entries(
                    [
                        *list(normalized.get("global_rules") or []),
                        *list(normalized.get("allowed_if_evidenced") or []),
                        *list(normalized.get("downgrade_rules") or []),
                        *list(normalized.get("omit_rules") or []),
                        *[rule for bucket in (normalized.get("section_rules") or {}).values() for rule in bucket],
                    ],
                    source=coverage_source,
                )
            )
        )
        if isinstance(entry, dict)
    ]
    normalized["normalization_events"] = [event for event in normalization_events if isinstance(event, dict)]

    known_keys = {
        "status",
        "source_scope",
        "scope",
        "rule_type_enum_version",
        "applies_to_enum_version",
        "prompt_version",
        "prompt_metadata",
        "global_rules",
        "section_rules",
        "allowed_if_evidenced",
        "downgrade_rules",
        "omit_rules",
        "rules",
        "rule_set",
        "mandatory_rules",
        "conditional_rules",
        "softeners",
        "downgrades",
        "forbidden_claim_patterns",
        "forbidden_patterns",
        "forbidden_phrases",
        "credibility_ladder_rules",
        "credibility_chain",
        "proof_chain",
        "topic_coverage",
        "rationale",
        "unresolved_markers",
        "defaults_applied",
        "normalization_events",
        "confidence",
        "evidence",
        "notes",
        "debug_context",
        "fail_open_reason",
    }
    for extra_key in sorted(set(raw.keys()) - known_keys):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": extra_key, "value": raw.get(extra_key), "note": "unknown top-level emphasis-rules field retained"},
        )

    debug_context["defaults_applied"] = list(dict.fromkeys([*list(debug_context.get("defaults_applied") or []), *normalized["defaults_applied"]]))
    debug_context["normalization_events"] = [
        event for event in (dict(item) for item in normalized["normalization_events"]) if isinstance(event, dict)
    ]
    debug_context["conflict_resolution_log"] = conflict_log
    debug_context["forbidden_claim_pattern_examples"] = [
        entry.get("example")
        for entry in normalized["forbidden_claim_patterns"]
        if isinstance(entry, dict) and entry.get("example")
    ]
    if evaluator_coverage_target:
        summary = dict(debug_context.get("input_summary") or {})
        summary["evaluator_roles_in_scope"] = [item for item in evaluator_coverage_target if _normalize_audience_role_key(item)]
        debug_context["input_summary"] = summary
    if debug_context.get("rejected_output"):
        normalized["status"] = "partial"
    normalized["debug_context"] = debug_context
    return normalized


def build_pain_point_intelligence_compact(doc: dict[str, Any] | "PainPointIntelligenceDoc" | None) -> dict[str, Any]:
    payload = doc.model_dump() if isinstance(doc, PainPointIntelligenceDoc) else dict(doc or {})
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    payload.get("stage_output") if isinstance(payload.get("stage_output"), dict) else {}
    trace_ref = payload.get("trace_ref") if isinstance(payload.get("trace_ref"), dict) else {}
    fail_open_reason = payload.get("fail_open_reason")
    return {
        "status": payload.get("status"),
        "source_scope": payload.get("source_scope"),
        "pains_count": len(payload.get("pain_points") or []),
        "strategic_needs_count": len(payload.get("strategic_needs") or []),
        "risks_count": len(payload.get("risks_if_unfilled") or []),
        "success_metrics_count": len(payload.get("success_metrics") or []),
        "proof_map_size": len(payload.get("proof_map") or []),
        "high_urgency_pains_count": sum(
            1 for item in (payload.get("pain_points") or []) if isinstance(item, dict) and item.get("urgency") == "high"
        ),
        "unresolved_questions_count": len(payload.get("unresolved_questions") or []),
        "confidence": {
            "score": confidence.get("score"),
            "band": confidence.get("band"),
        },
        "prompt_version": payload.get("prompt_version"),
        "pain_input_hash": payload.get("pain_input_hash"),
        "fail_open_reason": fail_open_reason,
        "trace_ref": trace_ref,
        "artifact_ref": "__ref__:pain_point_intelligence.id" if payload else None,
    }


def build_ideal_candidate_presentation_compact(doc: dict[str, Any] | "IdealCandidatePresentationModelDoc" | None) -> dict[str, Any]:
    payload = doc.model_dump() if isinstance(doc, IdealCandidatePresentationModelDoc) else dict(doc or {})
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    return {
        "status": payload.get("status"),
        "acceptable_titles_count": len(payload.get("acceptable_titles") or []),
        "must_signal_count": len(payload.get("must_signal") or []),
        "should_signal_count": len(payload.get("should_signal") or []),
        "de_emphasize_count": len(payload.get("de_emphasize") or []),
        "proof_ladder_length": len(payload.get("proof_ladder") or []),
        "audience_variant_count": len(payload.get("audience_variants") or {}),
        "credibility_marker_count": len(payload.get("credibility_markers") or []),
        "risk_flag_count": len(payload.get("risk_flags") or []),
        "defaults_applied_count": len(payload.get("defaults_applied") or []),
        "unresolved_markers_count": len(payload.get("unresolved_markers") or []),
        "title_strategy": payload.get("title_strategy"),
        "confidence": {
            "score": confidence.get("score"),
            "band": confidence.get("band"),
        },
        "artifact_ref": "__ref__:presentation_contract.id" if payload else None,
    }


def build_experience_dimension_weights_compact(
    doc: dict[str, Any] | "ExperienceDimensionWeightsDoc" | None,
) -> dict[str, Any]:
    payload = doc.model_dump(by_alias=True) if isinstance(doc, ExperienceDimensionWeightsDoc) else dict(doc or {})
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    overall = payload.get("overall_weights") if isinstance(payload.get("overall_weights"), dict) else {}
    sorted_weights = sorted(
        [
            {"dimension": dimension, "weight": weight}
            for dimension, weight in overall.items()
            if isinstance(weight, int) and weight > 0
        ],
        key=lambda item: (-item["weight"], item["dimension"]),
    )
    variants = payload.get("stakeholder_variant_weights") if isinstance(payload.get("stakeholder_variant_weights"), dict) else {}
    return {
        "status": payload.get("status"),
        "confidence_band": confidence.get("band"),
        "dimension_enum_version": payload.get("dimension_enum_version"),
        "overall_top3": sorted_weights[:3],
        "overall_weight_sum": sum(weight.get("weight", 0) for weight in sorted_weights),
        "non_zero_dimension_count": len(sorted_weights),
        "stakeholder_variant_count": sum(1 for value in variants.values() if isinstance(value, dict) and value),
        "minimum_visible_dimensions_count": len(payload.get("minimum_visible_dimensions") or []),
        "overuse_risks_count": len(payload.get("overuse_risks") or []),
        "ai_ml_depth_weight": overall.get("ai_ml_depth"),
        "architecture_weight": overall.get("architecture_system_design"),
        "leadership_weight": overall.get("leadership_enablement"),
        "business_impact_weight": overall.get("business_impact"),
        "defaults_applied_count": len(payload.get("defaults_applied") or []),
        "normalization_events_count": len(payload.get("normalization_events") or []),
        "artifact_ref": "__ref__:presentation_contract.id" if payload else None,
    }


def build_truth_constrained_emphasis_rules_compact(
    doc: dict[str, Any] | "TruthConstrainedEmphasisRulesDoc" | None,
) -> dict[str, Any]:
    payload = doc.model_dump(by_alias=True) if isinstance(doc, TruthConstrainedEmphasisRulesDoc) else dict(doc or {})
    confidence = payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
    section_rules = payload.get("section_rules") if isinstance(payload.get("section_rules"), dict) else {}
    topic_coverage = payload.get("topic_coverage") if isinstance(payload.get("topic_coverage"), list) else []
    coverage_map: dict[str, int] = {}
    for entry in topic_coverage:
        if not isinstance(entry, dict):
            continue
        family = str(entry.get("topic_family") or "")
        if family:
            try:
                coverage_map[family] = int(entry.get("rule_count") or 0)
            except Exception:
                coverage_map[family] = 0
    conflict_log = payload.get("debug_context", {}).get("conflict_resolution_log") if isinstance(payload.get("debug_context"), dict) else []
    return {
        "status": payload.get("status"),
        "confidence_band": confidence.get("band"),
        "rule_type_enum_version": payload.get("rule_type_enum_version"),
        "applies_to_enum_version": payload.get("applies_to_enum_version"),
        "global_rules_count": len(payload.get("global_rules") or []),
        "section_rule_count": sum(len(bucket or []) for bucket in section_rules.values()),
        "section_rule_coverage_section_ids": sorted(section_rules.keys()),
        "allowed_if_evidenced_count": len(payload.get("allowed_if_evidenced") or []),
        "downgrade_rules_count": len(payload.get("downgrade_rules") or []),
        "omit_rules_count": len(payload.get("omit_rules") or []),
        "forbidden_claim_patterns_count": len(payload.get("forbidden_claim_patterns") or []),
        "credibility_ladder_rules_count": len(payload.get("credibility_ladder_rules") or []),
        "topic_coverage": coverage_map,
        "title_strategy_conflict_count": sum(1 for item in conflict_log if isinstance(item, dict) and item.get("conflict_source") == "title_strategy"),
        "ai_section_policy_conflict_count": sum(1 for item in conflict_log if isinstance(item, dict) and item.get("conflict_source") == "ai_section_policy"),
        "dimension_weight_conflict_count": sum(1 for item in conflict_log if isinstance(item, dict) and item.get("conflict_source") == "dimension_weights"),
        "must_signal_contradiction_count": sum(1 for item in conflict_log if isinstance(item, dict) and item.get("conflict_source") == "must_signal"),
        "defaults_applied_count": len(payload.get("defaults_applied") or []),
        "normalization_events_count": len(payload.get("normalization_events") or []),
        "unresolved_markers_count": len(payload.get("unresolved_markers") or []),
        "artifact_ref": "__ref__:presentation_contract.id" if payload else None,
    }


class PainRetainedFieldDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    note: str | None = None


class PainRejectedFieldDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    reason: str


class PainPointDebugContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_bag_counts: dict[str, int] = Field(default_factory=dict)
    deterministic_validator_diffs: list[str] = Field(default_factory=list)
    llm_request_ids: list[str] = Field(default_factory=list)
    retry_reasons: list[str] = Field(default_factory=list)
    supplemental_web_queries: list[str] | None = None
    normalization_events: list[str] = Field(default_factory=list)
    richer_output_retained: list[PainRetainedFieldDoc] = Field(default_factory=list)
    rejected_output: list[PainRejectedFieldDoc] = Field(default_factory=list)
    defaults_applied: list[str] = Field(default_factory=list)
    retry_events: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator(
        "deterministic_validator_diffs",
        "llm_request_ids",
        "retry_reasons",
        "supplemental_web_queries",
        "normalization_events",
        "defaults_applied",
        mode="before",
    )
    @classmethod
    def normalize_debug_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class SearchTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    intent: SearchTermIntent = "retrieval"
    source_basis: str | None = None

    @field_validator("term", mode="before")
    @classmethod
    def normalize_term(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("search_terms[].term is required")
        return text

    @field_validator("intent", mode="before")
    @classmethod
    def normalize_intent(cls, value: Any) -> str:
        return _normalize_search_term_intent(value)


class PainPointEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pain_id: str
    category: PainCategoryEnum
    statement: str
    why_now: str | None = None
    source_scope: PainSourceScope = "jd_only"
    evidence_refs: list[str] = Field(default_factory=list)
    urgency: Literal["low", "medium", "high"] = "medium"
    related_stakeholders: list[EvaluatorRole] = Field(default_factory=list)
    likely_proof_targets: list[ProofCategory] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("pain_id", mode="before")
    @classmethod
    def normalize_pain_id(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("pain_id is required")
        return _normalize_slug(text) or text

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        return _normalize_pain_category(value)

    @field_validator("statement", "why_now", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str | None:
        return _coerce_text(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        return _normalize_evidence_refs(value)

    @field_validator("related_stakeholders", mode="before")
    @classmethod
    def normalize_roles(cls, value: Any) -> list[str]:
        return [item for item in (_normalize_audience_role_key(item) for item in _normalize_string_list(value)) if item]

    @field_validator("likely_proof_targets", mode="before")
    @classmethod
    def normalize_proof_targets(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _PROOF_CATEGORIES]
        if invalid:
            raise ValueError(f"likely_proof_targets contains invalid proof categories: {invalid}")
        return items

    @field_validator("source_scope", mode="before")
    @classmethod
    def normalize_source_scope(cls, value: Any) -> str:
        return _normalize_pain_source_scope(value)

    @field_validator("urgency", mode="before")
    @classmethod
    def normalize_urgency(cls, value: Any) -> str:
        return _coerce_enum_choice(value, allowed={"low", "medium", "high"}, default="medium")

    @model_validator(mode="after")
    def validate_entry(self) -> "PainPointEntry":
        if not self.statement:
            raise ValueError("pain statement is required")
        if len(self.statement) > 240:
            raise ValueError("pain statement exceeds 240 chars")
        if not self.evidence_refs:
            raise ValueError("pain entries require evidence_refs")
        return self


class StrategicNeedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: StrategicNeedCategoryEnum = "business"
    statement: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        return _normalize_pain_category(value)

    @field_validator("statement", mode="before")
    @classmethod
    def normalize_statement(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("strategic need statement is required")
        return text

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        return _normalize_evidence_refs(value)

    @model_validator(mode="after")
    def validate_entry(self) -> "StrategicNeedEntry":
        if not self.evidence_refs:
            raise ValueError("strategic needs require evidence_refs")
        return self


class RiskEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: RiskCategoryEnum = "delivery"
    statement: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Any) -> str:
        return _normalize_pain_category(value, default="delivery")

    @field_validator("statement", mode="before")
    @classmethod
    def normalize_statement(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("risk statement is required")
        return text

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        return _normalize_evidence_refs(value)

    @model_validator(mode="after")
    def validate_entry(self) -> "RiskEntry":
        if not self.evidence_refs:
            raise ValueError("risk entries require evidence_refs")
        return self


class SuccessMetricEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    metric_kind: SuccessMetricKindEnum = "qualitative"
    horizon: SuccessMetricHorizonEnum | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("statement", mode="before")
    @classmethod
    def normalize_statement(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("success metric statement is required")
        return text

    @field_validator("metric_kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: Any) -> str:
        return _normalize_metric_kind(value)

    @field_validator("horizon", mode="before")
    @classmethod
    def normalize_horizon(cls, value: Any) -> str | None:
        return _normalize_metric_horizon(value)

    @field_validator("evidence_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        return _normalize_evidence_refs(value)

    @model_validator(mode="after")
    def validate_entry(self) -> "SuccessMetricEntry":
        if not self.evidence_refs:
            raise ValueError("success metrics require evidence_refs")
        return self


class ProofMapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pain_id: str
    preferred_proof_type: ProofCategory
    preferred_evidence_shape: str
    bad_proof_patterns: list[str] = Field(default_factory=list)
    affected_document_sections: list[PresentationSectionId] = Field(default_factory=list)
    rationale: str
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)

    @field_validator("pain_id", mode="before")
    @classmethod
    def normalize_pain_id(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("proof_map[].pain_id is required")
        return _normalize_slug(text) or text

    @field_validator("preferred_proof_type", mode="before")
    @classmethod
    def normalize_proof_type(cls, value: Any) -> str:
        normalized = _normalize_slug(value)
        if normalized not in _PROOF_CATEGORIES:
            raise ValueError("preferred_proof_type must be a canonical proof category")
        return normalized

    @field_validator("preferred_evidence_shape", "rationale", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        text = _coerce_text(value)
        if not text:
            raise ValueError("proof_map text fields are required")
        return text

    @field_validator("bad_proof_patterns", mode="before")
    @classmethod
    def normalize_bad_patterns(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("affected_document_sections", mode="before")
    @classmethod
    def normalize_sections(cls, value: Any) -> list[str]:
        items = [_normalize_slug(item) for item in _normalize_string_list(value)]
        invalid = [item for item in items if item not in _PRESENTATION_SECTION_IDS]
        if invalid:
            raise ValueError(f"affected_document_sections contains invalid section ids: {invalid}")
        return items

    @model_validator(mode="after")
    def validate_entry(self) -> "ProofMapEntry":
        if len(self.preferred_evidence_shape) > 160:
            raise ValueError("preferred_evidence_shape exceeds 160 chars")
        if len(self.rationale) > 300:
            raise ValueError("proof_map rationale exceeds 300 chars")
        return self


class PainPointIntelligenceCompactDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PainPointStatus = "unresolved"
    source_scope: PainSourceScope = "jd_only"
    pains_count: int = 0
    strategic_needs_count: int = 0
    risks_count: int = 0
    success_metrics_count: int = 0
    proof_map_size: int = 0
    high_urgency_pains_count: int = 0
    unresolved_questions_count: int = 0
    confidence: dict[str, Any] = Field(default_factory=dict)
    prompt_version: str | None = None
    pain_input_hash: str | None = None
    fail_open_reason: str | None = None
    trace_ref: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: str | None = None


class PainPointIntelligenceDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    level2_job_id: str
    input_snapshot_id: str | None = None
    pain_input_hash: str
    prompt_version: str
    prompt_metadata: PromptMetadata | None = None
    provider_used: str | None = None
    model_used: str | None = None
    transport_used: str = "none"
    status: PainPointStatus = "unresolved"
    source_scope: PainSourceScope = "jd_only"
    pain_points: list[PainPointEntry] = Field(default_factory=list)
    strategic_needs: list[StrategicNeedEntry] = Field(default_factory=list)
    risks_if_unfilled: list[RiskEntry] = Field(default_factory=list)
    success_metrics: list[SuccessMetricEntry] = Field(default_factory=list)
    proof_map: list[ProofMapEntry] = Field(default_factory=list)
    search_terms: list[SearchTerm] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    sources: list[SourceEntry] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    confidence: ConfidenceDoc = Field(default_factory=ConfidenceDoc)
    cache_refs: dict[str, Any] = Field(default_factory=dict)
    timing: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    debug_context: PainPointDebugContext | None = None
    fail_open_reason: Literal[
        "jd_only_fallback",
        "thin_research",
        "schema_repair_exhausted",
        "supplemental_web_unavailable",
        "llm_terminal_failure",
    ] | None = None
    trace_ref: dict[str, Any] = Field(default_factory=dict)

    @field_validator("unresolved_questions", mode="before")
    @classmethod
    def normalize_unresolved(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)[:12]

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return _coerce_enum_choice(value, allowed=_PAIN_STATUSES, default="unresolved")

    @field_validator("source_scope", mode="before")
    @classmethod
    def normalize_source_scope(cls, value: Any) -> str:
        return _normalize_pain_source_scope(value)

    @field_validator("fail_open_reason", mode="before")
    @classmethod
    def normalize_fail_open_reason(cls, value: Any) -> str | None:
        text = _coerce_text(value)
        if not text:
            return None
        normalized = _normalize_slug(text)
        return normalized if normalized in _PAIN_FAIL_OPEN_REASONS else None

    @model_validator(mode="after")
    def validate_doc(self) -> "PainPointIntelligenceDoc":
        pain_ids = [item.pain_id for item in self.pain_points]
        if len(pain_ids) != len(set(pain_ids)):
            raise ValueError("pain_ids must be unique")
        known_ids = set(pain_ids)
        for item in self.proof_map:
            if item.pain_id not in known_ids:
                raise ValueError(f"proof_map pain_id does not resolve: {item.pain_id}")
        seen_statements: dict[str, str] = {}
        for bucket_name, entries in (
            ("pain_points", self.pain_points),
            ("strategic_needs", self.strategic_needs),
            ("risks_if_unfilled", self.risks_if_unfilled),
            ("success_metrics", self.success_metrics),
        ):
            for entry in entries:
                statement = getattr(entry, "statement", None)
                key = _statement_key(statement)
                if not key:
                    continue
                previous = seen_statements.get(key)
                if previous and previous != bucket_name:
                    raise ValueError(f"cross-category duplicate statement detected: {statement}")
                seen_statements[key] = bucket_name
        return self


def _normalize_pain_entry_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, PainPointEntry):
        return item.model_dump()
    if not isinstance(item, dict):
        statement = _coerce_text(item)
        if not statement:
            return None
        category = _normalize_pain_category("business")
        return {
            "pain_id": _pain_id(category, statement),
            "category": category,
            "statement": statement,
            "why_now": None,
            "source_scope": "jd_only",
            "evidence_refs": [],
            "urgency": "medium",
            "related_stakeholders": [],
            "likely_proof_targets": [],
            "confidence": _coerce_confidence_payload(None, fallback_basis="pain_point_normalized"),
        }
    payload = dict(item)
    statement = _coerce_text(payload.get("statement") or payload.get("pain") or payload.get("text") or payload.get("description"))
    if not statement:
        return None
    category = _normalize_pain_category(payload.get("category"), default="business")
    evidence_refs = _normalize_evidence_refs(payload.get("evidence_refs") or payload.get("source_refs") or payload.get("source_ids"))
    return {
        "pain_id": _coerce_text(payload.get("pain_id") or payload.get("id")) or _pain_id(category, statement),
        "category": category,
        "statement": statement,
        "why_now": _coerce_text(payload.get("why_now") or payload.get("urgency_context") or payload.get("context")),
        "source_scope": _normalize_pain_source_scope(payload.get("source_scope"), default="jd_only"),
        "evidence_refs": evidence_refs,
        "urgency": _coerce_enum_choice(payload.get("urgency"), allowed={"low", "medium", "high"}, default="medium"),
        "related_stakeholders": [item for item in (_normalize_audience_role_key(role) for role in _normalize_string_list(payload.get("related_stakeholders"))) if item],
        "likely_proof_targets": _normalize_proof_categories(payload.get("likely_proof_targets") or payload.get("proof_types")),
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="pain_point_normalized"),
    }


def _normalize_strategic_need_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, StrategicNeedEntry):
        return item.model_dump()
    statement = _coerce_text(item.get("statement") if isinstance(item, dict) else item)
    if not statement:
        statement = _coerce_text((item or {}).get("need") if isinstance(item, dict) else None)
    if not statement:
        return None
    payload = dict(item) if isinstance(item, dict) else {}
    return {
        "category": _normalize_pain_category(payload.get("category"), default="business"),
        "statement": statement,
        "evidence_refs": _normalize_evidence_refs(payload.get("evidence_refs") or payload.get("source_ids")),
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="strategic_need_normalized"),
    }


def _normalize_risk_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, RiskEntry):
        return item.model_dump()
    payload = dict(item) if isinstance(item, dict) else {}
    statement = _coerce_text(payload.get("statement") or payload.get("risk") or payload.get("text") or item)
    if not statement:
        return None
    return {
        "category": _normalize_pain_category(payload.get("category"), default="delivery"),
        "statement": statement,
        "evidence_refs": _normalize_evidence_refs(payload.get("evidence_refs") or payload.get("source_ids")),
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="risk_normalized"),
    }


def _normalize_success_metric_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, SuccessMetricEntry):
        return item.model_dump()
    payload = dict(item) if isinstance(item, dict) else {}
    statement = _coerce_text(payload.get("statement") or payload.get("metric") or payload.get("text") or item)
    if not statement:
        return None
    return {
        "statement": statement,
        "metric_kind": _normalize_metric_kind(payload.get("metric_kind") or payload.get("kind")),
        "horizon": _normalize_metric_horizon(payload.get("horizon")),
        "evidence_refs": _normalize_evidence_refs(payload.get("evidence_refs") or payload.get("source_ids")),
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="success_metric_normalized"),
    }


def _normalize_proof_map_payload(item: Any, *, debug_context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if isinstance(item, ProofMapEntry):
        return item.model_dump()
    if not isinstance(item, dict):
        return None
    payload = dict(item)
    pain_id = _coerce_text(payload.get("pain_id") or payload.get("pain_ref"))
    if not pain_id:
        return None
    def _clip_text(value: Any, *, limit: int) -> str | None:
        text = _coerce_text(value)
        if not text:
            return None
        canonical = re.sub(r"\s+", " ", text).strip()
        if len(canonical) <= limit:
            return canonical
        clipped = canonical[:limit].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0].rstrip()
        return clipped or canonical[:limit].rstrip()

    preferred_evidence_shape_raw = _coerce_text(
        payload.get("preferred_evidence_shape") or payload.get("evidence_shape") or payload.get("shape")
    )
    preferred_evidence_shape = _clip_text(preferred_evidence_shape_raw, limit=160)
    if (
        preferred_evidence_shape_raw
        and preferred_evidence_shape
        and preferred_evidence_shape != re.sub(r"\s+", " ", preferred_evidence_shape_raw).strip()
        and debug_context is not None
    ):
        _debug_append_event(
            debug_context,
            "normalization_events",
            "proof_map.preferred_evidence_shape truncated to 160 chars",
        )
    rationale_raw = _coerce_text(payload.get("rationale"))
    rationale = _clip_text(rationale_raw, limit=300)
    if rationale_raw and rationale and rationale != re.sub(r"\s+", " ", rationale_raw).strip() and debug_context is not None:
        _debug_append_event(
            debug_context,
            "normalization_events",
            "proof_map.rationale truncated to 300 chars",
        )
    return {
        "pain_id": pain_id,
        "preferred_proof_type": _coerce_text(payload.get("preferred_proof_type") or payload.get("proof_type")),
        "preferred_evidence_shape": preferred_evidence_shape,
        "bad_proof_patterns": _normalize_string_list(payload.get("bad_proof_patterns") or payload.get("anti_patterns")),
        "affected_document_sections": _normalize_presentation_section_ids(payload.get("affected_document_sections") or payload.get("sections")),
        "rationale": rationale,
        "confidence": _coerce_confidence_payload(payload.get("confidence"), fallback_basis="proof_map_normalized"),
    }


def _normalize_search_term_payload(item: Any) -> dict[str, Any] | None:
    if isinstance(item, SearchTerm):
        return item.model_dump()
    if isinstance(item, str):
        term = item.strip()
        if not term:
            return None
        return {"term": term, "intent": "retrieval", "source_basis": None}
    if not isinstance(item, dict):
        return None
    term = _coerce_text(item.get("term") or item.get("query") or item.get("text"))
    if not term:
        return None
    return {
        "term": term,
        "intent": _normalize_search_term_intent(item.get("intent")),
        "source_basis": _coerce_text(item.get("source_basis") or item.get("basis")),
    }


def normalize_pain_point_intelligence_payload(
    payload: dict[str, Any] | None,
    *,
    jd_excerpt: str = "",
) -> dict[str, Any]:
    raw = dict(payload or {})
    debug_context = _clean_debug_context(raw.get("debug_context"))
    normalized: dict[str, Any] = {}
    normalized["job_id"] = _coerce_text(raw.get("job_id"))
    normalized["level2_job_id"] = _coerce_text(raw.get("level2_job_id"))
    normalized["input_snapshot_id"] = _coerce_text(raw.get("input_snapshot_id"))
    normalized["status"] = _coerce_enum_choice(raw.get("status"), allowed=_PAIN_STATUSES, default="unresolved")
    normalized["source_scope"] = _normalize_pain_source_scope(raw.get("source_scope"), default="jd_only")
    normalized["pain_points"] = [
        payload
        for payload in (_normalize_pain_entry_payload(item) for item in _coerce_list(raw.get("pain_points") or raw.get("pains")))
        if payload
    ]
    normalized["strategic_needs"] = [
        payload
        for payload in (_normalize_strategic_need_payload(item) for item in _coerce_list(raw.get("strategic_needs") or raw.get("needs")))
        if payload
    ]
    normalized["risks_if_unfilled"] = [
        payload
        for payload in (_normalize_risk_payload(item) for item in _coerce_list(raw.get("risks_if_unfilled") or raw.get("risks")))
        if payload
    ]
    normalized["success_metrics"] = [
        payload
        for payload in (_normalize_success_metric_payload(item) for item in _coerce_list(raw.get("success_metrics")))
        if payload
    ]
    normalized["proof_map"] = [
        payload
        for payload in (_normalize_proof_map_payload(item, debug_context=debug_context) for item in _coerce_list(raw.get("proof_map")))
        if payload
    ]
    normalized["search_terms"] = [
        payload
        for payload in (_normalize_search_term_payload(item) for item in _coerce_list(raw.get("search_terms")))
        if payload
    ]
    normalized["unresolved_questions"] = _normalize_string_list(raw.get("unresolved_questions"))[:12]
    normalized["sources"] = _coerce_source_entries(raw.get("sources"))
    normalized["evidence"] = _coerce_evidence_entries(raw.get("evidence"))
    normalized["confidence"] = _coerce_confidence_payload(raw.get("confidence"), fallback_basis="pain_point_intelligence_normalized")
    normalized["cache_refs"] = _coerce_detail_dict(raw.get("cache_refs"))
    normalized["timing"] = _coerce_detail_dict(raw.get("timing"))
    normalized["usage"] = _coerce_detail_dict(raw.get("usage"))
    normalized["prompt_version"] = _coerce_text(raw.get("prompt_version")) or "pain_point_intelligence@v4.2.3"
    normalized["pain_input_hash"] = _coerce_text(raw.get("pain_input_hash")) or ""
    normalized["provider_used"] = _coerce_text(raw.get("provider_used"))
    normalized["model_used"] = _coerce_text(raw.get("model_used"))
    normalized["transport_used"] = _coerce_text(raw.get("transport_used")) or "none"
    normalized["fail_open_reason"] = _coerce_text(raw.get("fail_open_reason"))

    known_keys = {
        "status",
        "source_scope",
        "job_id",
        "level2_job_id",
        "input_snapshot_id",
        "pain_points",
        "pains",
        "strategic_needs",
        "needs",
        "risks_if_unfilled",
        "risks",
        "success_metrics",
        "proof_map",
        "search_terms",
        "unresolved_questions",
        "sources",
        "evidence",
        "confidence",
        "cache_refs",
        "timing",
        "usage",
        "debug_context",
        "pain_input_hash",
        "prompt_version",
        "provider_used",
        "model_used",
        "transport_used",
        "fail_open_reason",
    }
    for extra_key in sorted(set(raw.keys()) - known_keys):
        _debug_append_event(
            debug_context,
            "richer_output_retained",
            {"key": extra_key, "value": raw.get(extra_key), "note": "unknown top-level pain-point field retained"},
        )

    allowed_company_name_set: set[str] = set()
    candidate_stripped = _strip_candidate_leakage(
        normalized,
        path="pain_point_intelligence",
        debug_context=debug_context,
        allowed_company_names=allowed_company_name_set,
        allowed_company_domain=None,
        jd_excerpt=jd_excerpt,
        enforce_proper_noun_rule=False,
    )
    normalized = candidate_stripped if isinstance(candidate_stripped, dict) else normalized
    if debug_context.get("rejected_output"):
        normalized["status"] = "partial"
    normalized["debug_context"] = debug_context
    return normalized


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
    presentation_contract: dict[str, Any] = Field(default_factory=dict)
    presentation_contract_compact: dict[str, Any] = Field(default_factory=dict)
    pain_point_intelligence_compact: dict[str, Any] = Field(default_factory=dict)
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
