from __future__ import annotations

import pytest

from src.preenrich.blueprint_models import JDFactsExtractionOutput
from src.preenrich.stages.jd_facts import _normalize_extraction_payload, _supplement_minimum_content_lists


def _payload() -> dict:
    return {
        "title": "Head of Engineering",
        "company": "Acme",
        "location": "Remote (EU)",
        "remote_policy": "fully_remote",
        "role_category": "head_of_engineering",
        "seniority_level": "director",
        "competency_weights": {"delivery": 25, "process": 15, "architecture": 20, "leadership": 40},
        "responsibilities": ["Build the team", "Set engineering culture", "Architect scalable systems"],
        "qualifications": ["10+ years engineering", "Leadership experience", "Distributed systems experience"],
        "nice_to_haves": ["Startup experience"],
        "technical_skills": ["Python", "AWS"],
        "soft_skills": ["Leadership", "Communication"],
        "implied_pain_points": ["No engineering function exists"],
        "success_metrics": ["Team hired"],
        "top_keywords": [
            "python",
            "aws",
            "engineering leadership",
            "system design",
            "hiring",
            "mentoring",
            "roadmap execution",
            "b2b saas",
            "remote",
            "ci/cd",
        ],
        "industry_background": "B2B SaaS",
        "years_experience_required": 10,
        "education_requirements": "BS in CS or equivalent",
        "ideal_candidate_profile": {
            "identity_statement": "A builder-leader who can scale engineering execution.",
            "archetype": "builder_founder",
            "key_traits": ["builder", "systems thinker", "team scaler"],
            "experience_profile": "10+ years engineering, 5+ years leadership",
            "culture_signals": ["fast-paced", "autonomous"],
        },
        "salary_range": "$180k - $220k",
        "application_url": "https://example.com/apply",
        "remote_location_detail": {
            "remote_anywhere": False,
            "remote_regions": ["EU"],
            "timezone_expectations": ["CET overlap"],
            "travel_expectation": None,
            "onsite_expectation": None,
            "location_constraints": ["EU"],
            "relocation_support": None,
            "primary_locations": ["Remote (EU)"],
            "secondary_locations": [],
            "geo_scope": "region",
            "work_authorization_notes": None,
        },
        "expectations": {
            "explicit_outcomes": ["Build the team"],
            "delivery_expectations": ["Ship the roadmap"],
            "leadership_expectations": ["Hire engineers"],
            "communication_expectations": ["Partner with executives"],
            "collaboration_expectations": ["Work with product"],
            "first_90_day_expectations": ["Assess gaps"],
        },
        "identity_signals": {
            "primary_identity": "builder-founder engineering leader",
            "alternate_identities": ["player-coach"],
            "identity_evidence": ["Build from scratch"],
            "career_stage_signals": ["zero-to-one leadership"],
        },
        "skill_dimension_profile": {
            "communication_skills": ["Executive communication"],
            "leadership_skills": ["Hiring", "Mentoring"],
            "delivery_skills": ["Roadmap execution"],
            "architecture_skills": ["System design"],
            "process_skills": ["CI/CD"],
            "stakeholder_skills": ["CEO partnership"],
        },
        "team_context": {
            "team_size": "0-10",
            "reporting_to": "CEO",
            "org_scope": "Engineering",
            "management_scope": "Direct manager",
        },
        "weighting_profiles": {
            "expectation_weights": {
                "delivery": 30,
                "communication": 15,
                "leadership": 30,
                "collaboration": 10,
                "strategic_scope": 15,
            },
            "operating_style_weights": {
                "autonomy": 25,
                "ambiguity": 20,
                "pace": 20,
                "process_rigor": 15,
                "stakeholder_exposure": 20,
            },
        },
        "operating_signals": ["fast-paced startup", "high ownership"],
        "ambiguity_signals": ["team size not explicit"],
        "language_requirements": {
            "required_languages": ["English"],
            "preferred_languages": ["German"],
            "fluency_expectations": ["Professional fluency"],
            "language_notes": None,
        },
        "company_description": "Growth-stage B2B SaaS company.",
        "role_description": "Own the engineering function.",
        "residual_context": None,
        "analysis_metadata": {
            "overall_confidence": "high",
            "field_confidence": {
                "role_category": "high",
                "seniority_level": "high",
                "ideal_candidate_profile": "high",
                "rich_contract": "medium",
            },
            "inferred_fields": ["ideal_candidate_profile"],
            "ambiguities": ["team size inferred"],
            "source_coverage": {
                "used_structured_sections": True,
                "used_raw_excerpt": True,
                "tail_coverage": "full",
                "truncation_risk": "low",
            },
            "quality_checks": {
                "competency_weights_sum_100": True,
                "weighting_profile_sums_valid": True,
                "top_keywords_ranked": True,
                "duplicate_list_items_removed": True,
            },
        },
    }


def test_jd_facts_rich_contract_model_validates():
    model = JDFactsExtractionOutput.model_validate(_payload())
    assert model.remote_location_detail is not None
    assert model.language_requirements is not None
    assert model.analysis_metadata is not None
    assert model.company_description == "Growth-stage B2B SaaS company."
    assert model.role_description == "Own the engineering function."
    assert model.residual_context is None


def test_jd_facts_weighting_profiles_must_sum_to_100():
    payload = _payload()
    payload["weighting_profiles"]["expectation_weights"]["delivery"] = 35
    with pytest.raises(ValueError, match="must sum to 100"):
        JDFactsExtractionOutput.model_validate(payload)


def test_jd_facts_company_role_and_residual_fields_accept_only_string_or_null():
    payload = _payload()
    payload["company_description"] = ["not", "allowed"]
    with pytest.raises(ValueError):
        JDFactsExtractionOutput.model_validate(payload)


def test_jd_facts_taxonomy_bound_fields_reject_unknown_labels():
    payload = _payload()
    payload["role_category"] = "made_up_role"
    with pytest.raises(ValueError):
        JDFactsExtractionOutput.model_validate(payload)


def test_jd_facts_normalizes_remote_geo_scope_aliases():
    payload = _payload()
    payload["remote_location_detail"]["geo_scope"] = "city_region"
    normalized = _normalize_extraction_payload(payload, {})
    model = JDFactsExtractionOutput.model_validate(normalized)
    assert model.remote_location_detail is not None
    assert model.remote_location_detail.geo_scope == "region"


def test_jd_facts_normalizes_salary_object_and_truncates_culture_signals():
    payload = _payload()
    payload["salary_range"] = {"text": "Competitive Salary", "min": None, "max": None, "period": "annual"}
    payload["ideal_candidate_profile"]["culture_signals"] = ["hybrid", "enterprise", "collaborative", "delivery", "responsible ai"]
    normalized = _normalize_extraction_payload(payload, {})
    model = JDFactsExtractionOutput.model_validate(normalized)
    assert model.salary_range == "Competitive Salary"
    assert model.ideal_candidate_profile is not None
    assert len(model.ideal_candidate_profile.culture_signals) == 4


def test_jd_facts_supplements_thin_live_lists_from_deterministic_evidence():
    payload = _payload()
    payload["responsibilities"] = ["Design and implement LLM and NLP use cases for business applications"]
    payload["qualifications"] = ["10+ years engineering"]
    payload["top_keywords"] = ["python", "aws"]
    deterministic = {
        "responsibility_hints": [
            "Lead AI engineering team and set technical direction",
            "Partner with senior leadership on AI roadmap",
            "Evaluate AI frameworks and third-party services",
        ],
        "must_haves": ["Leadership experience", "Distributed systems experience"],
        "top_keywords": ["python", "aws", "llm", "ai", "rag", "terraform", "kubernetes", "mentoring", "leadership", "system design"],
        "weak_keyword_hints": ["remote", "delivery"],
        "nice_to_haves": ["Startup experience"],
    }
    normalized = _supplement_minimum_content_lists(payload, deterministic, description="")
    model = JDFactsExtractionOutput.model_validate(normalized)
    assert len(model.responsibilities) >= 3
    assert len(model.qualifications) >= 2
    assert len(model.top_keywords) >= 10
