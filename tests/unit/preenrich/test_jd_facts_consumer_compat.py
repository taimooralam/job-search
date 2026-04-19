from __future__ import annotations

from types import SimpleNamespace

from runner_service.utils.best_effort_dossier import generate_best_effort_dossier
from src.services.annotation_suggester import _infer_dimensions_from_extracted_jd
from src.services.cv_review_core import build_user_prompt


def _compat_projection() -> dict:
    return {
        "title": "Head of Engineering",
        "company": "Acme",
        "role_category": "head_of_engineering",
        "seniority_level": "director",
        "remote_policy": "fully_remote",
        "competency_weights": {"delivery": 25, "process": 15, "architecture": 20, "leadership": 40},
        "responsibilities": [
            "Build the engineering team from scratch",
            "Define engineering culture and hiring bar",
            "Architect scalable systems for 100x growth",
        ],
        "key_responsibilities": [
            "Build the engineering team from scratch",
            "Define engineering culture and hiring bar",
            "Architect scalable systems for 100x growth",
        ],
        "qualifications": [
            "10+ years software engineering experience",
            "5+ years leading engineering teams",
            "Strong Python background",
        ],
        "required_qualifications": [
            "10+ years software engineering experience",
            "5+ years leading engineering teams",
            "Strong Python background",
        ],
        "nice_to_haves": ["Startup experience"],
        "technical_skills": ["Python", "AWS", "Kubernetes"],
        "soft_skills": ["Leadership", "Communication"],
        "implied_pain_points": ["Need to build the team from scratch"],
        "success_metrics": ["Hire 10 engineers in 12 months"],
        "top_keywords": [
            "Head of Engineering",
            "Python",
            "AWS",
            "Kubernetes",
            "Scaling",
            "Architecture",
            "Leadership",
            "Hiring",
            "SaaS",
            "Remote",
        ],
        "years_experience_required": 10,
        "education_requirements": "BS in CS or equivalent",
        "ideal_candidate_profile": {
            "identity_statement": "A technical leader who can build a team and platform foundations from scratch.",
            "archetype": "builder_founder",
            "key_traits": ["systems thinker", "builder", "mentor"],
            "experience_profile": "10+ years engineering, 5+ years leadership",
            "culture_signals": ["fast-paced", "autonomous"],
        },
        "salary": "$180k - $220k",
    }


def test_cv_review_core_reads_runner_parity_projection():
    prompt = build_user_prompt(
        cv_text="CV text",
        extracted_jd=_compat_projection(),
        master_cv_text="Master CV",
        pain_points=["Need to build the team from scratch"],
        company_research={"summary": "Growth-stage SaaS company"},
    )
    assert "Company: Acme" in prompt
    assert "Role Category: head_of_engineering" in prompt
    assert "Implied Pain Points" in prompt


def test_annotation_suggester_dimension_inference_accepts_rich_projection():
    match_ctx = SimpleNamespace(type="hard_skill")
    dimensions = _infer_dimensions_from_extracted_jd(
        item_text="Strong Python background",
        section="requirements",
        extracted_jd=_compat_projection(),
        master_cv={"hard_skills": {"python", "aws"}, "soft_skills": {"leadership"}},
        match_ctx=match_ctx,
    )
    assert dimensions["relevance"] == "core_strength"
    assert dimensions["identity"] == "strong_identity"


def test_best_effort_dossier_accepts_alias_fields():
    text, flags = generate_best_effort_dossier(
        {
            "title": "Head of Engineering",
            "company": "Acme",
            "description": "Role description",
            "extracted_jd": _compat_projection(),
        }
    )
    assert flags["analysis"] is True
    assert "KEY RESPONSIBILITIES" in text
    assert "REQUIRED QUALIFICATIONS" in text
