from __future__ import annotations

from src.preenrich.blueprint_models import (
    ApplicationProfile,
    ApplicationSurfaceDoc,
    CompanyProfile,
    RoleProfile,
    StakeholderRecord,
    normalize_application_surface_payload,
    normalize_company_profile_payload,
    normalize_role_profile_payload,
    normalize_stakeholder_record_payload,
)


def test_application_surface_normalization_accepts_partial_employer_portal_shape_drift():
    payload = normalize_application_surface_payload(
        {
            "job_url": "https://linkedin.com/jobs/view/4401620360",
            "canonical_application_url": "https://www.robsonbale.com/jobs/",
            "final_http_status": 200,
            "resolution_status": "partial",
            "ui_actionability": "applyable",
            "form_fetch_status": "unavailable",
            "stale_signal": None,
            "closed_signal": None,
            "duplicate_signal": None,
            "geo_normalization": "London Area, United Kingdom",
            "apply_instructions": ["Use the employer jobs portal.", "Search by title if needed."],
        }
    )
    doc = ApplicationSurfaceDoc.model_validate(payload)
    assert doc.canonical_application_url == "https://www.robsonbale.com/jobs/"
    assert doc.resolution_status == "partial"
    assert doc.ui_actionability == "ready"
    assert doc.form_fetch_status == "not_attempted"
    assert doc.stale_signal == "unknown"
    assert doc.closed_signal == "unknown"
    assert doc.duplicate_signal == {}
    assert doc.geo_normalization == {"raw": "London Area, United Kingdom"}
    assert doc.apply_instruction_lines == ["Use the employer jobs portal.", "Search by title if needed."]
    assert "Use the employer jobs portal." in (doc.apply_instructions or "")


def test_company_profile_normalization_preserves_rich_signal_shapes():
    payload = normalize_company_profile_payload(
        {
            "summary": {"text": "Robson Bale is a specialist recruiting firm focused on AI and data hiring."},
            "canonical_name": {"text": "Robson Bale"},
            "canonical_domain": {"value": "robsonbale.com"},
            "canonical_url": {"value": "https://www.robsonbale.com"},
            "identity_basis": {"text": "Official company site"},
            "signals": [
                {
                    "name": "growth",
                    "value": "Active hiring across AI engineering roles",
                    "confidence": {"score": 0.7, "band": "medium", "basis": "observed"},
                    "evidence": [{"source_ids": ["s1"]}],
                }
            ],
        }
    )
    profile = CompanyProfile.model_validate(payload)
    assert profile.summary == "Robson Bale is a specialist recruiting firm focused on AI and data hiring."
    assert profile.canonical_name == "Robson Bale"
    assert profile.canonical_domain == "robsonbale.com"
    assert profile.signals[0].description == "growth: Active hiring across AI engineering roles"
    assert profile.signals_rich[0]["name"] == "growth"
    assert profile.identity_detail


def test_role_profile_normalization_accepts_detail_wrappers():
    payload = normalize_role_profile_payload(
        {
            "summary": {"text": "Lead AI Engineer role spanning platform and delivery."},
            "role_summary": {"text": "Senior hands-on AI engineering leadership role."},
            "why_now": {"text": "The company is expanding AI delivery capacity."},
            "company_context_alignment": {"text": "The role supports a growing AI hiring and delivery practice."},
            "mandate": ["Lead AI delivery", "Own platform quality"],
        }
    )
    profile = RoleProfile.model_validate(payload)
    assert profile.summary == "Lead AI Engineer role spanning platform and delivery."
    assert profile.role_summary == "Senior hands-on AI engineering leadership role."
    assert profile.why_now == "The company is expanding AI delivery capacity."
    assert profile.company_context_alignment_detail["text"] == "The role supports a growing AI hiring and delivery practice."


def test_stakeholder_normalization_maps_alias_fields():
    payload = normalize_stakeholder_record_payload(
        {
            "stakeholder_type": "hiring_manager",
            "identity_status": "resolved",
            "identity_confidence": {"score": 0.8, "band": "high", "basis": "official team page"},
            "matched_signal_classes": ["official_team_page_named_person", "public_profile_function_match"],
            "name": "Jordan Smith",
            "title": "Engineering Manager",
            "company": "Acme",
            "relationship": "likely_hiring_manager",
        }
    )
    record = StakeholderRecord.model_validate(payload)
    assert record.current_title == "Engineering Manager"
    assert record.current_company == "Acme"
    assert record.relationship_to_role == "likely_hiring_manager"


def test_application_profile_merge_context_is_preserved():
    payload = normalize_application_surface_payload(
        {
            "application_profile": {
                "canonical_application_url": "https://www.robsonbale.com/jobs/",
                "status": "partial",
                "resolution_status": "partial",
            },
            "application_surface_artifact": {"status": "unresolved"},
            "job_document_hints": {"company": "Robson Bale"},
            "company_profile": {"canonical_domain": "robsonbale.com"},
        }
    )
    profile = ApplicationProfile.model_validate(payload)
    assert profile.canonical_application_url == "https://www.robsonbale.com/jobs/"
    assert profile.debug_context["application_surface_artifact"]["status"] == "unresolved"
