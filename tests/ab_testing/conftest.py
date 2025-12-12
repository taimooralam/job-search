"""
Shared fixtures for A/B testing.

Provides test jobs, master CV, and pre-configured ABTestRunners
for each layer.
"""

import json
import pytest
from pathlib import Path
from typing import List, Dict, Any

from .framework import ABTestRunner, create_mock_generator
from .scorers import score_specificity, score_grounding, score_hallucinations


# Path to fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def master_cv() -> str:
    """Load master CV for hallucination checking (MongoDB or file)."""
    from src.common.config import Config

    # Try MongoDB first if enabled
    if Config.USE_MASTER_CV_MONGODB:
        try:
            from src.layer6_v2.cv_loader import CVLoader
            loader = CVLoader(use_mongodb=True)
            candidate = loader.load()
            if candidate:
                content = "\n\n".join(
                    role.raw_content for role in candidate.roles if role.raw_content
                )
                if content:
                    return content
        except Exception:
            pass

    # File fallback: try legacy master-cv.md
    master_cv_path = Path(__file__).parent.parent.parent / "master-cv.md"
    if master_cv_path.exists():
        return master_cv_path.read_text()

    # Try structured roles directory
    roles_dir = Path(__file__).parent.parent.parent / "data" / "master-cv" / "roles"
    if roles_dir.exists():
        texts = [f.read_text() for f in sorted(roles_dir.glob("*.md"))]
        if texts:
            return "\n\n".join(texts)

    return ""


@pytest.fixture
def test_job_1() -> Dict[str, Any]:
    """
    Load test job 1: Kaizen Gaming - Software Engineering Team Lead.

    Real job from MongoDB with complete state data including:
    - Pain points from Layer 2
    - STAR selections from Layer 2.5
    - Company research from Layer 3
    """
    fixture_path = FIXTURES_DIR / "test_job_1.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def test_job_2() -> Dict[str, Any]:
    """
    Load test job 2: FinTech Compliance role (synthetic).

    Designed to test different pain point patterns:
    - Regulatory compliance focus
    - Security and audit trails
    - Data privacy requirements
    """
    # Synthetic job for diversity
    return {
        "job_id": "synthetic_fintech_001",
        "title": "Engineering Lead - Compliance Platform",
        "company": "FinSecure Technologies",
        "job_description": """
We are seeking an Engineering Lead to build and scale our compliance automation platform.

Key Responsibilities:
- Lead a team of 6 engineers building SOC2 compliance tooling
- Architect audit trail systems processing millions of events daily
- Ensure GDPR/CCPA compliance across data pipelines
- Implement security-first engineering practices

Requirements:
- 7+ years software engineering with security focus
- Experience with compliance frameworks (SOC2, ISO27001, GDPR)
- Strong background in event-driven architectures
- Leadership experience with cross-functional teams
        """,
        "job_url": "https://example.com/fintech-compliance-lead",
        "source": "linkedin",
        "score": 65,
        "pain_points": [
            "Manual compliance reporting taking 40+ hours per audit",
            "Lack of real-time visibility into compliance status",
            "Security incidents not detected until post-mortem",
            "Data privacy violations due to inadequate controls"
        ],
        "strategic_needs": [
            "Achieve SOC2 Type II certification within 6 months",
            "Reduce audit preparation time by 80%",
            "Implement zero-trust security architecture"
        ],
        "risks_if_unfilled": [
            "Failed compliance audits risking enterprise contracts",
            "Regulatory fines for data privacy violations",
            "Competitive disadvantage in enterprise market"
        ],
        "success_metrics": [
            "SOC2 certification achieved within timeline",
            "90% reduction in audit preparation time",
            "Zero compliance violations in first year"
        ],
        "company_research": {
            "summary": "FinSecure Technologies is a Series B fintech startup providing compliance automation for financial services.",
            "signals": [
                {"type": "funding", "description": "Raised $40M Series B", "date": "2024"},
                {"type": "partnership", "description": "Partnership with major banks", "date": "2024"}
            ],
            "url": "https://finsecure.example.com"
        },
        "selected_stars": [
            {
                "id": "star_gdpr",
                "company": "Seven.One Entertainment Group",
                "role": "Technical Lead",
                "period": "2020-Present",
                "domain_areas": "Compliance, GDPR, Security",
                "situation": "Needed GDPR/TCF compliance for AdTech platform handling millions of users",
                "task": "Lead development of compliant consent management platform",
                "actions": "Designed TCF-compliant CMP, passed BLM regulatory audits, implemented consent flows",
                "results": "Preserved 30M euro revenue, became first movers in EU compliance",
                "metrics": "100% audit pass rate, 30M euro protected, zero compliance violations",
                "keywords": "GDPR, TCF, compliance, CMP, audit, regulatory"
            }
        ],
        "star_to_pain_mapping": {
            "Manual compliance reporting taking 40+ hours per audit": ["star_gdpr"]
        },
        "candidate_profile": "Engineering leader with compliance and security experience",
        "fit_score": None,
        "fit_rationale": None,
        "errors": [],
        "status": "pending"
    }


@pytest.fixture
def test_job_3() -> Dict[str, Any]:
    """
    Load test job 3: Enterprise Infrastructure role (synthetic).

    Designed to test architecture-focused requirements:
    - Legacy migration
    - Cost optimization
    - Scale challenges
    """
    return {
        "job_id": "synthetic_enterprise_001",
        "title": "Principal Engineer - Platform Infrastructure",
        "company": "GlobalTech Enterprise",
        "job_description": """
Join our platform team to lead the modernization of our core infrastructure.

Key Responsibilities:
- Architect migration from on-premise to hybrid cloud (AWS/Azure)
- Optimize cloud costs while improving performance
- Scale platform to support 10x user growth
- Mentor team of 12 engineers across 3 regions

Requirements:
- 10+ years distributed systems experience
- Expert-level AWS and/or Azure knowledge
- Experience with large-scale migrations
- Strong track record of cost optimization
        """,
        "job_url": "https://example.com/enterprise-principal",
        "source": "linkedin",
        "score": 75,
        "pain_points": [
            "Legacy on-premise infrastructure limiting agility",
            "Cloud costs growing 30% YoY without performance gains",
            "Single points of failure causing outages",
            "12-month feature release cycles blocking innovation"
        ],
        "strategic_needs": [
            "Complete cloud migration within 18 months",
            "Reduce cloud spend by 40% through optimization",
            "Achieve 99.99% platform availability"
        ],
        "risks_if_unfilled": [
            "Competitors outpacing with faster feature delivery",
            "Mounting technical debt blocking strategic initiatives",
            "Key engineering talent leaving for modern stacks"
        ],
        "success_metrics": [
            "Migration completed on schedule and budget",
            "40% cloud cost reduction achieved",
            "Release cycles reduced to 2 weeks"
        ],
        "company_research": {
            "summary": "GlobalTech Enterprise is a Fortune 500 company modernizing their technology infrastructure.",
            "signals": [
                {"type": "strategy", "description": "Cloud-first initiative announced", "date": "2024"},
                {"type": "acquisition", "description": "Acquired cloud consulting firm", "date": "2024"}
            ],
            "url": "https://globaltech.example.com"
        },
        "selected_stars": [
            {
                "id": "star_architecture",
                "company": "Seven.One Entertainment Group",
                "role": "Technical Lead",
                "period": "2020-Present",
                "domain_areas": "Architecture, AWS, Microservices",
                "situation": "Monolithic AdTech platform needed modernization",
                "task": "Lead transformation to event-driven microservices on AWS",
                "actions": "Architected migration, implemented DDD, built observability pipeline",
                "results": "75% incident reduction, zero downtime for 3 years",
                "metrics": "75% incident reduction, 10x cost savings on observability, 25% faster delivery",
                "keywords": "AWS, microservices, architecture, migration, DDD"
            }
        ],
        "star_to_pain_mapping": {
            "Legacy on-premise infrastructure limiting agility": ["star_architecture"]
        },
        "candidate_profile": "Architecture expert with cloud migration experience",
        "fit_score": None,
        "fit_rationale": None,
        "errors": [],
        "status": "pending"
    }


@pytest.fixture
def test_jobs(test_job_1, test_job_2, test_job_3) -> List[Dict[str, Any]]:
    """Load all 3 test jobs."""
    return [test_job_1, test_job_2, test_job_3]


@pytest.fixture
def ab_runner_layer4(test_jobs, master_cv) -> ABTestRunner:
    """ABTestRunner configured for Layer 4 (Opportunity Mapper)."""
    return ABTestRunner(
        layer="layer4",
        issue="test",
        test_jobs=test_jobs,
        master_cv=master_cv,
    )


@pytest.fixture
def ab_runner_layer6a(test_jobs, master_cv) -> ABTestRunner:
    """ABTestRunner configured for Layer 6a (Cover Letter)."""
    return ABTestRunner(
        layer="layer6a",
        issue="test",
        test_jobs=test_jobs,
        master_cv=master_cv,
    )


@pytest.fixture
def ab_runner_layer6b(test_jobs, master_cv) -> ABTestRunner:
    """ABTestRunner configured for Layer 6b (CV Generator)."""
    return ABTestRunner(
        layer="layer6b",
        issue="test",
        test_jobs=test_jobs,
        master_cv=master_cv,
    )


@pytest.fixture
def mock_baseline_generator():
    """Mock generator producing generic baseline output."""
    def generator(job_state: Dict) -> str:
        return f"""
Based on my review, I believe I would be a great fit for this role at {job_state.get('company', 'the company')}.

I have extensive experience in software engineering and have a proven track record of success.
I am a team player with excellent communication skills and am excited to apply for this opportunity.

I have worked at several companies and delivered results. My background makes me well-suited
for the {job_state.get('title', 'position')}.
        """
    return generator


@pytest.fixture
def mock_enhanced_generator():
    """Mock generator producing specific enhanced output."""
    def generator(job_state: Dict) -> str:
        stars = job_state.get("selected_stars", [])
        star_company = stars[0].get("company", "Previous Company") if stars else "Previous Company"
        star_metrics = stars[0].get("metrics", "significant improvements") if stars else "significant improvements"
        pain_points = job_state.get("pain_points", [])
        first_pain = pain_points[0] if pain_points else "team leadership"

        return f"""
At {star_company}, I directly addressed challenges similar to {job_state.get('company')}'s need for {first_pain}.

My specific results included: {star_metrics}

For {job_state.get('company')}, I would apply these learnings to:
1. Address the pain point of {first_pain} using proven approaches from {star_company}
2. Leverage my experience with microservices and AWS to improve scalability
3. Apply DDD principles to improve team velocity by 25%

This makes me specifically qualified for {job_state.get('title')} given {job_state.get('company')}'s
current growth trajectory and technical challenges.
        """
    return generator


# Scorer fixtures for direct testing
@pytest.fixture
def scorer_specificity():
    """Specificity scorer function."""
    return score_specificity


@pytest.fixture
def scorer_grounding():
    """Grounding scorer function."""
    return score_grounding


@pytest.fixture
def scorer_hallucinations():
    """Hallucinations scorer function."""
    return score_hallucinations
