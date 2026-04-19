"""Prompt builders for iteration-4.1 blueprint stages."""

from __future__ import annotations

import json
from typing import Any

from src.layer1_4.prompts import JD_EXTRACTION_SYSTEM_PROMPT
from src.preenrich.blueprint_config import taxonomy_version


def _reject_hypotheses_payload(prompt_name: str, payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, sort_keys=True, default=str).lower()
    if "job_hypotheses" in serialized:
        raise ValueError(f"{prompt_name} prompt payload must not reference job_hypotheses")


def _json_only_contract(name: str, schema_keys: list[str]) -> str:
    return (
        f"You are {name}. Return ONLY valid JSON. "
        "No prose. No markdown fences. No commentary. "
        f"Required top-level keys: {', '.join(schema_keys)}."
    )


def build_p_jd_judge(*, description: str, deterministic: dict[str, Any]) -> str:
    payload = {"description": description[:8000], "deterministic": deterministic}
    return "\n".join(
        [
            _json_only_contract("P-jd-judge", ["additions", "flags", "confirmations"]),
            "Review the raw job description against the deterministic extraction.",
            "Deterministic fields cannot be silently overwritten.",
            "Output additions only when they include evidence spans.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_jd_extract(
    *,
    title: str,
    company: str,
    deterministic_hints: dict[str, Any],
    structured_sections: dict[str, Any],
    raw_jd_excerpt: str,
) -> str:
    payload = {
        "title": title,
        "company": company,
        "deterministic_hints": deterministic_hints,
        "structured_sections": structured_sections,
        "raw_jd_excerpt": raw_jd_excerpt,
        "required_output_keys": [
            "title",
            "company",
            "location",
            "remote_policy",
            "role_category",
            "seniority_level",
            "competency_weights",
            "responsibilities",
            "qualifications",
            "nice_to_haves",
            "technical_skills",
            "soft_skills",
            "implied_pain_points",
            "success_metrics",
            "top_keywords",
            "years_experience_required",
            "education_requirements",
            "ideal_candidate_profile",
            "salary_range",
            "application_url",
        ],
    }
    _reject_hypotheses_payload("P-jd-extract", payload)
    return "\n".join(
        [
            _json_only_contract(
                "P-jd-extract",
                [
                    "title",
                    "company",
                    "location",
                    "remote_policy",
                    "role_category",
                    "seniority_level",
                    "competency_weights",
                    "responsibilities",
                    "qualifications",
                    "nice_to_haves",
                    "technical_skills",
                    "soft_skills",
                    "implied_pain_points",
                    "success_metrics",
                    "top_keywords",
                    "industry_background",
                    "years_experience_required",
                    "education_requirements",
                    "ideal_candidate_profile",
                    "salary_range",
                    "application_url",
                ],
            ),
            "Use the runner-era extraction contract as the quality baseline.",
            "Prefer the structured sections first, then use the raw JD excerpt to recover missing context.",
            "Do not silently drop tail-section evidence. Preserve ATS-critical terminology and the exact role-category taxonomy.",
            "Deterministic hints are anchors, not optional output fields. If they disagree with the JD, still emit your best extraction and make the disagreement obvious in the values.",
            JD_EXTRACTION_SYSTEM_PROMPT,
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_classify(*, jd_facts: dict[str, Any], taxonomy: dict[str, Any] | None = None) -> str:
    payload = {
        "taxonomy_version": taxonomy_version(),
        "jd_facts": jd_facts,
        "taxonomy": taxonomy or {},
    }
    return "\n".join(
        [
            _json_only_contract(
                "P-classify",
                [
                    "primary_role_category",
                    "secondary_role_categories",
                    "search_profiles",
                    "selector_profiles",
                    "tone_family",
                    "ambiguity_score",
                    "ai_relevance",
                ],
            ),
            "Classify the role using the canonical taxonomy.",
            f"taxonomy_version={taxonomy_version()}",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_research(*, jd_facts: dict[str, Any], identity: dict[str, Any]) -> str:
    payload = {"jd_facts": jd_facts, "identity": identity}
    return "\n".join(
        [
            _json_only_contract("P-research", ["status", "company_profile", "sources", "notes"]),
            "Synthesize public company and role research using the supplied evidence only.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_application_url(*, candidates: list[str], job_identity: dict[str, Any]) -> str:
    payload = {"candidates": candidates, "job_identity": job_identity}
    return "\n".join(
        [
            _json_only_contract("P-application-url", ["application_url", "status", "reason"]),
            "Choose the best direct apply URL from ambiguous candidates.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_role_model(
    *,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research_enrichment: dict[str, Any],
    application_surface: dict[str, Any],
) -> str:
    payload = {
        "jd_facts": jd_facts,
        "classification": classification,
        "research_enrichment": research_enrichment,
        "application_surface": application_surface,
    }
    return "\n".join(
        [
            _json_only_contract(
                "P-role-model",
                ["semantic_role_model", "company_model", "qualifications", "inferences"],
            ),
            "Produce evidence-backed role and company inferences. Do not invent hypotheses.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_hypotheses(
    *,
    jd_facts: dict[str, Any],
    classification: dict[str, Any],
    research_enrichment: dict[str, Any],
    application_surface: dict[str, Any],
) -> str:
    payload = {
        "jd_facts": jd_facts,
        "classification": classification,
        "research_enrichment": research_enrichment,
        "application_surface": application_surface,
    }
    return "\n".join(
        [
            _json_only_contract("P-hypotheses", ["hypotheses"]),
            "Produce speculative low-confidence hypotheses only. These are never used for prose generation.",
            json.dumps(payload, indent=2, default=str),
        ]
    )


def build_p_cv_guidelines(
    *,
    jd_facts: dict[str, Any],
    job_inference: dict[str, Any],
    research_enrichment: dict[str, Any],
) -> str:
    payload = {
        "jd_facts": jd_facts,
        "job_inference": job_inference,
        "research_enrichment": research_enrichment,
    }
    _reject_hypotheses_payload("P-cv-guidelines", payload)
    return "\n".join(
        [
            _json_only_contract(
                "P-cv-guidelines",
                [
                    "title_guidance",
                    "identity_guidance",
                    "bullet_theme_guidance",
                    "ats_keyword_guidance",
                    "cover_letter_expectations",
                ],
            ),
            "Produce guidance only. No prose CV output. Every block must include evidence_refs.",
            json.dumps(payload, indent=2, default=str),
        ]
    )
