from __future__ import annotations

from scripts.benchmark_extraction_4_1_1 import compare_extractions, run_benchmark


def _runner_payload() -> dict:
    return {
        "title": "Head of Engineering",
        "company": "Acme",
        "location": "Remote (EU)",
        "remote_policy": "fully_remote",
        "role_category": "head_of_engineering",
        "seniority_level": "director",
        "competency_weights": {"delivery": 25, "process": 15, "architecture": 20, "leadership": 40},
        "responsibilities": ["Build the team", "Scale the platform", "Partner with CEO"],
        "qualifications": ["10+ years engineering", "Leadership background"],
        "nice_to_haves": ["Startup experience"],
        "technical_skills": ["Python", "AWS", "Kubernetes"],
        "soft_skills": ["Leadership", "Communication"],
        "implied_pain_points": ["Need to build engineering foundations"],
        "success_metrics": ["Hire 10 engineers"],
        "top_keywords": ["Head of Engineering", "Python", "AWS", "Kubernetes", "Leadership", "Scaling", "Architecture", "Hiring", "Startup", "Remote"],
        "industry_background": "SaaS",
        "years_experience_required": 10,
        "education_requirements": "BS in CS or equivalent",
        "ideal_candidate_profile": {
            "identity_statement": "A technical leader who can build a team and platform foundations from scratch.",
            "archetype": "builder_founder",
            "key_traits": ["systems thinker", "builder", "mentor"],
            "experience_profile": "10+ years engineering, 5+ years leadership",
            "culture_signals": ["fast-paced", "autonomous"],
        },
    }


def test_compare_extractions_reports_schema_failure():
    runner = _runner_payload()
    candidate = {"title": "Head of Engineering"}
    comparison = compare_extractions(runner, candidate)
    assert comparison["schema_valid"] is False


def test_run_benchmark_passes_with_fixture_candidate():
    runner = _runner_payload()
    report, summary = run_benchmark(
        [
            {
                "_id": "job-1",
                "job_id": "job-1",
                "title": "Head of Engineering",
                "company": "Acme",
                "description": "Role description",
                "runner_extracted_jd": runner,
                "candidate_extracted_jd": dict(runner),
            }
        ],
        use_fixture_candidate=True,
    )
    assert len(report) == 1
    assert summary["schema_validity_pass_rate"] == 1.0
    assert summary["passes_thresholds"] is True
