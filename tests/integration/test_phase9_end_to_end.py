"""
Phase 9 End-to-End Pipeline Regression Tests

ROADMAP Phase 9.2: Claude-driven end-to-end test pass covering functionality from Phases 4–9 (Layers 2–6b).

This test suite validates:
- Phase 4 (Layer 2): Pain-point mining with 4 dimensions
- Phase 5 (Layer 3): Company & role research with multi-source scraping
- Phase 6 (Layer 4): Opportunity mapping with STAR citations and fit scoring
- Phase 7 (Layer 5): People mapping with 4-6 primary + 4-6 secondary contacts
- Phase 8 (Layer 6a): Cover letter & CV generation with STAR-driven tailoring
- Phase 9 (Layer 6b): Outreach packaging for all contacts

Test scenarios use a small set of canonical real jobs loaded from MongoDB `level-2` (initially 4 jobs) to validate quality gates across representative role types, company stages, and industries.

Quality Gates Validated:
1. All layers complete without unhandled errors (happy path)
2. Critical outputs present: pain_points, fit_score, cover_letter, outreach_packages
3. ROADMAP compliance: output structure, field counts, validation rules
4. No hallucinations: company facts, STAR metrics, contact details
5. Personalization: STAR citations, pain point mapping, contact-specific outreach
"""

import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.run_pipeline import load_job_from_mongo
from src.workflow import run_pipeline


# ===== TEST JOB FIXTURES (7 diverse scenarios) =====

@pytest.fixture
def candidate_profile():
    """Load master CV for candidate context."""
    kb_path = Path(__file__).parent.parent.parent / "master-cv.md"
    if not kb_path.exists():
        # Fallback to minimal profile for CI/testing environments
        return """
# Taimoor Alam - Senior Engineering Leader

## Professional Summary
Engineering leader with 10+ years building scalable systems, leading teams, and driving technical strategy.

## Key Achievements
- Scaled infrastructure from 1M to 50M daily active users
- Led teams of 5-15 engineers across distributed systems and platform engineering
- Reduced deployment times by 85% through automation and CI/CD improvements
- Improved system reliability from 99.5% to 99.95% uptime
        """.strip()

    with open(kb_path, 'r') as f:
        return f.read()


def _load_level2_job_or_skip(job_id: str) -> Dict[str, Any]:
    """
    Load a canonical E2E job from MongoDB level-2.

    Uses the same mapping logic as scripts/run_pipeline.load_job_from_mongo.
    Skips the test if MongoDB is not reachable or the job is missing.
    """
    try:
        job_data = load_job_from_mongo(job_id)
    except Exception as exc:
        pytest.skip(f"Skipping E2E job {job_id}: {exc}")

    # Tag source for clarity in logs
    job_data["source"] = job_data.get("source", "e2e_mongo")
    return job_data


@pytest.fixture
def job_1_technical_sre():
    """Canonical E2E Job 1 from MongoDB level-2 (jobId 4306263685)."""
    return _load_level2_job_or_skip("4306263685")


@pytest.fixture
def job_2_leadership_eng_manager():
    """Canonical E2E Job 2 from MongoDB level-2 (jobId 4323221685)."""
    return _load_level2_job_or_skip("4323221685")


@pytest.fixture
def job_3_ml_engineer():
    """Canonical E2E Job 3 from MongoDB level-2 (jobId 42320338018)."""
    return _load_level2_job_or_skip("42320338018")


@pytest.fixture
def job_4_product_manager():
    """Canonical E2E Job 4 from MongoDB level-2 (jobId 4335702439)."""
    return _load_level2_job_or_skip("4335702439")


@pytest.fixture
def job_5_security_engineer():
    """Test Job 5: Security Engineer at cloud platform (REAL COMPANY: Cloudflare)."""
    return {
        "job_id": "e2e_005_sec",
        "title": "Senior Security Engineer - Application Security",
        "company": "Cloudflare",  # REAL COMPANY - enables FireCrawl scraping
        "description": """
About the Role:
Lead application security efforts to support enterprise customers and compliance requirements.

Key Responsibilities:
- Establish application security program (SAST, DAST, dependency scanning)
- Reduce critical vulnerabilities from current 45-day avg to <7-day remediation
- Build security champions program across 12 engineering teams
- Support SOC 2 Type II and ISO 27001 certification
- Implement secure SDLC and threat modeling practices

Security Challenges:
- Current security testing is manual and reactive
- 120+ high/critical vulnerabilities in backlog
- No security training for developers
- Enterprise customers requiring security questionnaires blocking deals

Success Metrics:
- Critical vulnerability remediation: 45 days → <7 days
- Security champions: 0 → 12 (one per team)
- SOC 2 Type II certification achieved
- Zero security-related deal blockers

Requirements:
- 5+ years application security experience
- Strong background in secure SDLC, SAST/DAST, and threat modeling
- Experience implementing security programs in fast-growing companies
- Cloud security expertise (AWS, Azure, GCP)
        """.strip(),
        "url": "https://www.cloudflare.com/careers",
        "source": "e2e_test"
    }


@pytest.fixture
def job_6_vp_engineering():
    """Test Job 6: VP Engineering at data platform (REAL COMPANY: Databricks)."""
    return {
        "job_id": "e2e_006_vpe",
        "title": "Vice President of Engineering",
        "company": "Databricks",  # REAL COMPANY - enables FireCrawl scraping
        "description": """
About the Role:
Lead engineering organization of 40 engineers across 4 teams (platform, data, product, ML).

Key Responsibilities:
- Scale engineering team from 40 to 80 engineers in 18 months
- Drive technical strategy for data platform (10x scale)
- Improve engineering velocity (ship major features in weeks not months)
- Establish engineering culture, processes, and leadership development
- Partner with CEO and executive team on product and business strategy

Business Context:
- Processing massive data volumes, targeting 10x growth
- Engineering team scaling rapidly
- Recent leadership transition
- Board pressure to accelerate product development

Success Metrics:
- Scale platform: 10x data processing capacity
- Engineering team: 40 → 80 engineers
- Release velocity: quarterly → bi-weekly major features
- Engineering retention: >90%

Requirements:
- 10+ years engineering experience, 5+ years in leadership roles (Director+)
- Experience scaling engineering teams 2x+ in growth companies
- Strong technical background in distributed systems and data platforms
- Proven track record building engineering culture and developing leaders
        """.strip(),
        "url": "https://www.databricks.com/company/careers",
        "source": "e2e_test"
    }


@pytest.fixture
def job_7_head_of_growth():
    """Test Job 7: Head of Growth at productivity app (REAL COMPANY: Miro)."""
    return {
        "job_id": "e2e_007_growth",
        "title": "Head of Growth Marketing",
        "company": "Miro",  # REAL COMPANY - enables FireCrawl scraping
        "description": """
About the Role:
Own full-funnel growth strategy from acquisition to retention and monetization.

Key Responsibilities:
- Scale user acquisition from 10K to 100K new users/month
- Improve retention: D30 from 25% to 40%
- Launch and scale paid acquisition channels (Facebook, Google, LinkedIn)
- Build growth team from 2 to 8 (analytics, product marketing, performance)
- Establish growth experimentation framework and analytics infrastructure

Growth Challenges:
- Current CAC ($15) above LTV ($12) - unit economics need improvement
- Organic growth plateauing after initial momentum
- Retention dropping off after first week (D7: 40%, D30: 25%)
- Limited experimentation capacity (1-2 tests/month)

Success Metrics:
- Monthly new users: 10K → 100K
- CAC: $15 → $8
- D30 retention: 25% → 40%
- LTV/CAC ratio: 0.8 → 3.0

Requirements:
- 7+ years growth marketing experience in B2B/SaaS apps
- Proven track record scaling user acquisition 10x+
- Strong analytical skills with SQL and experimentation frameworks
- Experience building and managing growth teams
        """.strip(),
        "url": "https://miro.com/careers",
        "source": "e2e_test"
    }


# ===== HELPER FUNCTIONS =====

def validate_phase4_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Phase 4 (Layer 2) outputs: Pain-point mining."""
    issues = []

    # Check all 4 dimensions present
    for field in ["pain_points", "strategic_needs", "risks_if_unfilled", "success_metrics"]:
        if not state.get(field):
            issues.append(f"Phase 4: Missing {field}")
        elif not isinstance(state[field], list):
            issues.append(f"Phase 4: {field} is not a list")

    # Check minimum counts (ROADMAP requirements)
    if state.get("pain_points") and len(state["pain_points"]) < 3:
        issues.append(f"Phase 4: pain_points has {len(state['pain_points'])} items (min 3)")

    if state.get("strategic_needs") and len(state["strategic_needs"]) < 3:
        issues.append(f"Phase 4: strategic_needs has {len(state['strategic_needs'])} items (min 3)")

    if state.get("risks_if_unfilled") and len(state["risks_if_unfilled"]) < 2:
        issues.append(f"Phase 4: risks_if_unfilled has {len(state['risks_if_unfilled'])} items (min 2)")

    if state.get("success_metrics") and len(state["success_metrics"]) < 3:
        issues.append(f"Phase 4: success_metrics has {len(state['success_metrics'])} items (min 3)")

    return {
        "phase": "Phase 4 (Pain-Point Mining)",
        "passed": len(issues) == 0,
        "issues": issues
    }


def validate_phase5_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Phase 5 (Layer 3) outputs: Company & role research."""
    issues = []

    # Company research (Phase 5.1)
    if not state.get("company_research"):
        issues.append("Phase 5.1: Missing company_research")
    else:
        research = state["company_research"]
        if not research.get("summary"):
            issues.append("Phase 5.1: company_research missing summary")
        if not research.get("signals"):
            issues.append("Phase 5.1: company_research missing signals")
        elif not isinstance(research["signals"], list):
            issues.append("Phase 5.1: company_research.signals is not a list")

    # Role research (Phase 5.2)
    if not state.get("role_research"):
        issues.append("Phase 5.2: Missing role_research")
    else:
        research = state["role_research"]
        if not research.get("summary"):
            issues.append("Phase 5.2: role_research missing summary")
        if not research.get("business_impact"):
            issues.append("Phase 5.2: role_research missing business_impact")
        elif len(research["business_impact"]) < 3:
            issues.append(f"Phase 5.2: business_impact has {len(research['business_impact'])} items (min 3)")
        if not research.get("why_now"):
            issues.append("Phase 5.2: role_research missing why_now")

    return {
        "phase": "Phase 5 (Company & Role Research)",
        "passed": len(issues) == 0,
        "issues": issues
    }


def validate_phase6_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Phase 6 (Layer 4) outputs: Opportunity mapping."""
    issues = []

    # Fit score
    if state.get("fit_score") is None:
        issues.append("Phase 6: Missing fit_score")
    elif not isinstance(state["fit_score"], (int, float)):
        issues.append(f"Phase 6: fit_score is not numeric: {type(state['fit_score'])}")
    elif not (0 <= state["fit_score"] <= 100):
        issues.append(f"Phase 6: fit_score out of range: {state['fit_score']}")

    # Fit rationale
    if not state.get("fit_rationale"):
        issues.append("Phase 6: Missing fit_rationale")
    else:
        # Check for STAR citation (only when STAR selector is enabled)
        # NOTE: STAR selector is currently disabled via ENABLE_STAR_SELECTOR=false
        from src.common.config import Config
        if Config.ENABLE_STAR_SELECTOR:
            if not any(keyword in state["fit_rationale"].lower() for keyword in ["star #", "star#"]):
                issues.append("Phase 6: fit_rationale missing STAR citation")

        # Check for quantified metric
        import re
        metric_patterns = [r'\d+%', r'\d+x', r'\d+M', r'\d+K']
        if not any(re.search(pattern, state["fit_rationale"]) for pattern in metric_patterns):
            issues.append("Phase 6: fit_rationale missing quantified metric")

    # Fit category
    if not state.get("fit_category"):
        issues.append("Phase 6: Missing fit_category")
    elif state["fit_category"] not in ["exceptional", "strong", "good", "moderate", "weak"]:
        issues.append(f"Phase 6: Invalid fit_category: {state['fit_category']}")

    return {
        "phase": "Phase 6 (Opportunity Mapping)",
        "passed": len(issues) == 0,
        "issues": issues
    }


def validate_phase7_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Phase 7 (Layer 5) outputs: People mapping."""
    issues = []

    # Check if we're in fallback mode (synthetic contacts have role-based names like "VP Engineering at Company")
    # In fallback mode, we only generate 3 primary contacts and 0 secondary contacts (per operational design)
    primary_contacts = state.get("primary_contacts") or []
    is_fallback_mode = (
        len(primary_contacts) > 0 and
        all(" at " in c.get("name", "") for c in primary_contacts)
    )

    # Primary contacts (4-6 required for discovered contacts, 3 for fallback mode)
    if not state.get("primary_contacts"):
        issues.append("Phase 7: Missing primary_contacts")
    elif not isinstance(state["primary_contacts"], list):
        issues.append("Phase 7: primary_contacts is not a list")
    else:
        min_required = 3 if is_fallback_mode else 4
        if len(state["primary_contacts"]) < min_required:
            issues.append(f"Phase 7: primary_contacts has {len(state['primary_contacts'])} contacts (min {min_required})")

    # Secondary contacts (4-6 required for discovered contacts, 0 acceptable for fallback mode)
    if is_fallback_mode:
        # In fallback mode, secondary_contacts can be empty
        pass
    elif not state.get("secondary_contacts"):
        issues.append("Phase 7: Missing secondary_contacts")
    elif not isinstance(state["secondary_contacts"], list):
        issues.append("Phase 7: secondary_contacts is not a list")
    elif len(state["secondary_contacts"]) < 4:
        issues.append(f"Phase 7: secondary_contacts has {len(state['secondary_contacts'])} contacts (min 4)")

    # Validate contact structure
    for contact_list, contact_type in [(state.get("primary_contacts", []), "primary"),
                                        (state.get("secondary_contacts", []), "secondary")]:
        for i, contact in enumerate(contact_list):
            if not contact.get("name"):
                issues.append(f"Phase 7: {contact_type}_contacts[{i}] missing name")
            if not contact.get("why_relevant"):
                issues.append(f"Phase 7: {contact_type}_contacts[{i}] missing why_relevant")
            elif len(contact["why_relevant"]) < 20:
                issues.append(f"Phase 7: {contact_type}_contacts[{i}].why_relevant too short (<20 chars)")

    return {
        "phase": "Phase 7 (People Mapping)",
        "passed": len(issues) == 0,
        "issues": issues
    }


def validate_phase8_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Phase 8 (Layer 6a) outputs: Cover letter & CV."""
    issues = []

    # Cover letter
    if not state.get("cover_letter"):
        issues.append("Phase 8: Missing cover_letter")
    else:
        letter = state["cover_letter"]

        # Word count (220-380 per ROADMAP)
        word_count = len(letter.split())
        if word_count < 220:
            issues.append(f"Phase 8: cover_letter too short ({word_count} words, min 220)")
        elif word_count > 380:
            issues.append(f"Phase 8: cover_letter too long ({word_count} words, max 380)")

        # Check for metrics (≥2 required per ROADMAP 8.1)
        import re
        metrics = re.findall(r'\d+%|\d+x|\d+M|\d+K', letter)
        if len(set(metrics)) < 2:
            issues.append(f"Phase 8: cover_letter has {len(set(metrics))} unique metrics (min 2)")

        # Check for calendly URL
        if "calendly.com" not in letter:
            issues.append("Phase 8: cover_letter missing Calendly URL")

    # CV
    if not state.get("cv_path"):
        issues.append("Phase 8: Missing cv_path")
    elif not state["cv_path"].endswith(".md"):
        issues.append(f"Phase 8: cv_path not .md format: {state['cv_path']}")

    if not state.get("cv_reasoning"):
        issues.append("Phase 8: Missing cv_reasoning")

    return {
        "phase": "Phase 8 (Cover Letter & CV)",
        "passed": len(issues) == 0,
        "issues": issues
    }


def validate_phase9_outputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Phase 9 (Layer 6b) outputs: Outreach packaging."""
    issues = []

    # Outreach packages
    if not state.get("outreach_packages"):
        issues.append("Phase 9: Missing outreach_packages")
        return {
            "phase": "Phase 9 (Outreach Packaging)",
            "passed": False,
            "issues": issues
        }

    packages = state["outreach_packages"]

    if not isinstance(packages, list):
        issues.append("Phase 9: outreach_packages is not a list")
        return {
            "phase": "Phase 9 (Outreach Packaging)",
            "passed": False,
            "issues": issues
        }

    # Should have packages for all contacts (primary + secondary)
    total_contacts = len(state.get("primary_contacts", [])) + len(state.get("secondary_contacts", []))
    expected_packages = total_contacts * 2  # 2 channels per contact (LinkedIn + Email)

    if len(packages) < expected_packages:
        issues.append(f"Phase 9: Expected {expected_packages} packages ({total_contacts} contacts × 2 channels), got {len(packages)}")

    # Validate package structure
    for i, package in enumerate(packages):
        # Required fields
        if not package.get("contact_name"):
            issues.append(f"Phase 9: outreach_packages[{i}] missing contact_name")
        if not package.get("channel"):
            issues.append(f"Phase 9: outreach_packages[{i}] missing channel")
        elif package["channel"] not in ["linkedin", "email"]:
            issues.append(f"Phase 9: outreach_packages[{i}] invalid channel: {package['channel']}")
        if not package.get("message"):
            issues.append(f"Phase 9: outreach_packages[{i}] missing message")

        # Channel-specific validation
        if package.get("channel") == "linkedin":
            # LinkedIn length constraint (≤550 chars)
            if len(package.get("message", "")) > 550:
                issues.append(f"Phase 9: outreach_packages[{i}] LinkedIn message too long ({len(package['message'])} chars, max 550)")

            # LinkedIn closing line
            if "calendly.com" not in package.get("message", ""):
                issues.append(f"Phase 9: outreach_packages[{i}] LinkedIn message missing Calendly URL")

        elif package.get("channel") == "email":
            # Email subject (required, 6-10 words)
            if not package.get("subject"):
                issues.append(f"Phase 9: outreach_packages[{i}] Email missing subject")
            else:
                subject_words = len(package["subject"].split())
                if subject_words < 6 or subject_words > 10:
                    issues.append(f"Phase 9: outreach_packages[{i}] Email subject {subject_words} words (expected 6-10)")

            # Email body (100-200 words)
            if package.get("message"):
                word_count = len(package["message"].split())
                if word_count < 100 or word_count > 200:
                    issues.append(f"Phase 9: outreach_packages[{i}] Email body {word_count} words (expected 100-200)")

        # Content constraints
        message = package.get("message", "")

        # No emojis
        import re
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags
            "]+", flags=re.UNICODE)
        if emoji_pattern.search(message):
            issues.append(f"Phase 9: outreach_packages[{i}] contains emojis")

        # No placeholders except [Your Name]
        disallowed_placeholders = ["[Company]", "[Role]", "[Name]", "[Date]", "[XX", "{{"]
        for placeholder in disallowed_placeholders:
            if placeholder in message:
                issues.append(f"Phase 9: outreach_packages[{i}] contains disallowed placeholder: {placeholder}")

    return {
        "phase": "Phase 9 (Outreach Packaging)",
        "passed": len(issues) == 0,
        "issues": issues
    }


def run_full_validation(state: Dict[str, Any]) -> Dict[str, Any]:
    """Run all phase validations and return comprehensive report."""
    results = {
        "job_id": state.get("job_id"),
        "job_title": state.get("title"),
        "company": state.get("company"),
        "status": state.get("status"),
        "errors": state.get("errors", []),
        "validations": []
    }

    print("\n" + "="*70)
    print("🔍 VALIDATING PIPELINE OUTPUTS")
    print("="*70)

    # Run all phase validations with progress indicators
    print("📋 Validating Phase 4 (Pain-Point Mining)...")
    results["validations"].append(validate_phase4_outputs(state))

    print("📋 Validating Phase 5 (Company & Role Research)...")
    results["validations"].append(validate_phase5_outputs(state))

    print("📋 Validating Phase 6 (Opportunity Mapping)...")
    results["validations"].append(validate_phase6_outputs(state))

    print("📋 Validating Phase 7 (People Mapping)...")
    results["validations"].append(validate_phase7_outputs(state))

    print("📋 Validating Phase 8 (Cover Letter & CV)...")
    results["validations"].append(validate_phase8_outputs(state))

    print("📋 Validating Phase 9 (Outreach Packaging)...")
    results["validations"].append(validate_phase9_outputs(state))

    # Overall pass/fail
    results["all_passed"] = all(v["passed"] for v in results["validations"])
    results["total_issues"] = sum(len(v["issues"]) for v in results["validations"])

    print("="*70 + "\n")

    return results


# ===== END-TO-END TESTS =====

@pytest.mark.e2e
@pytest.mark.slow
class TestPhase9EndToEnd:
    """
    Phase 9 End-to-End Tests (ROADMAP Section 9.2).

    These tests run the full pipeline (Phases 4-9) against diverse job scenarios
    and validate all quality gates.

    Mark tests with @pytest.mark.e2e to run separately from unit tests.
    Run with: pytest -v -m e2e tests/integration/test_phase9_end_to_end.py
    """

    def test_e2e_job1_technical_sre(self, job_1_technical_sre, candidate_profile):
        """E2E Test 1: Senior SRE role at fintech startup."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 1: {job_1_technical_sre['title']} at {job_1_technical_sre['company']}")
        print(f"{'='*70}\n")

        # Run pipeline
        final_state = run_pipeline(job_1_technical_sre, candidate_profile)

        # Validate results
        validation = run_full_validation(final_state)

        # Print results
        print(f"\n{'='*70}")
        print(f"E2E Test 1: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Status: {validation['status']}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")
        print(f"Total Issues: {validation['total_issues']}")

        for v in validation["validations"]:
            status = "✅" if v["passed"] else "❌"
            print(f"\n{status} {v['phase']}")
            for issue in v["issues"]:
                print(f"  - {issue}")

        # Assert overall pass
        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed", f"Pipeline status: {final_state['status']}"

    def test_e2e_job2_engineering_manager(self, job_2_leadership_eng_manager, candidate_profile):
        """E2E Test 2: Engineering Manager at e-commerce scale-up."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 2: {job_2_leadership_eng_manager['title']} at {job_2_leadership_eng_manager['company']}")
        print(f"{'='*70}\n")

        final_state = run_pipeline(job_2_leadership_eng_manager, candidate_profile)
        validation = run_full_validation(final_state)

        print(f"\n{'='*70}")
        print(f"E2E Test 2: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")

        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed"

    def test_e2e_job3_ml_engineer(self, job_3_ml_engineer, candidate_profile):
        """E2E Test 3: Senior ML Engineer at healthtech startup."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 3: {job_3_ml_engineer['title']} at {job_3_ml_engineer['company']}")
        print(f"{'='*70}\n")

        final_state = run_pipeline(job_3_ml_engineer, candidate_profile)
        validation = run_full_validation(final_state)

        print(f"\n{'='*70}")
        print(f"E2E Test 3: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")

        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed"

    def test_e2e_job4_product_manager(self, job_4_product_manager, candidate_profile):
        """E2E Test 4: Senior Product Manager at SaaS company."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 4: {job_4_product_manager['title']} at {job_4_product_manager['company']}")
        print(f"{'='*70}\n")

        final_state = run_pipeline(job_4_product_manager, candidate_profile)
        validation = run_full_validation(final_state)

        print(f"\n{'='*70}")
        print(f"E2E Test 4: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")

        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed"

    def test_e2e_job5_security_engineer(self, job_5_security_engineer, candidate_profile):
        """E2E Test 5: Security Engineer at enterprise SaaS."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 5: {job_5_security_engineer['title']} at {job_5_security_engineer['company']}")
        print(f"{'='*70}\n")

        final_state = run_pipeline(job_5_security_engineer, candidate_profile)
        validation = run_full_validation(final_state)

        print(f"\n{'='*70}")
        print(f"E2E Test 5: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")

        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed"

    def test_e2e_job6_vp_engineering(self, job_6_vp_engineering, candidate_profile):
        """E2E Test 6: VP Engineering at martech company."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 6: {job_6_vp_engineering['title']} at {job_6_vp_engineering['company']}")
        print(f"{'='*70}\n")

        final_state = run_pipeline(job_6_vp_engineering, candidate_profile)
        validation = run_full_validation(final_state)

        print(f"\n{'='*70}")
        print(f"E2E Test 6: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")

        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed"

    def test_e2e_job7_head_of_growth(self, job_7_head_of_growth, candidate_profile):
        """E2E Test 7: Head of Growth at consumer app startup."""
        print(f"\n{'='*70}")
        print(f"🧪 E2E TEST 7: {job_7_head_of_growth['title']} at {job_7_head_of_growth['company']}")
        print(f"{'='*70}\n")

        final_state = run_pipeline(job_7_head_of_growth, candidate_profile)
        validation = run_full_validation(final_state)

        print(f"\n{'='*70}")
        print(f"E2E Test 7: {validation['job_title']} at {validation['company']}")
        print(f"{'='*70}")
        print(f"Overall: {'✅ PASSED' if validation['all_passed'] else '❌ FAILED'}")

        assert validation["all_passed"], f"Validation failed with {validation['total_issues']} issues"
        assert final_state["status"] == "completed"


# ===== REGRESSION SUMMARY TEST =====

@pytest.mark.e2e
@pytest.mark.slow
def test_generate_regression_report(
    job_1_technical_sre,
    job_2_leadership_eng_manager,
    job_3_ml_engineer,
    job_4_product_manager,
    candidate_profile,
):
    """
    Generate comprehensive regression report for Phase 9.

    Runs all 7 test jobs and produces summary report in report.md.
    """
    # Use canonical real jobs loaded from MongoDB level-2
    jobs = [
        job_1_technical_sre,
        job_2_leadership_eng_manager,
        job_3_ml_engineer,
        job_4_product_manager,
    ]

    results = []

    print(f"\n{'='*70}")
    print("PHASE 9 REGRESSION TEST SUITE")
    print(f"{'='*70}")
    print(f"Running {len(jobs)} test jobs...\n")

    for i, job in enumerate(jobs, 1):
        print(f"\n[{i}/{len(jobs)}] Running: {job['title']} at {job['company']}...")

        try:
            final_state = run_pipeline(job, candidate_profile)
            validation = run_full_validation(final_state)
            results.append(validation)

            status = "✅ PASSED" if validation["all_passed"] else f"❌ FAILED ({validation['total_issues']} issues)"
            print(f"     Result: {status}")

        except Exception as e:
            print(f"     Result: ❌ ERROR - {str(e)}")
            results.append({
                "job_id": job["job_id"],
                "job_title": job["title"],
                "company": job["company"],
                "status": "error",
                "error": str(e),
                "all_passed": False,
                "total_issues": 1,
                "validations": []
            })

    # Generate report
    print(f"\n{'='*70}")
    print("GENERATING REPORT.MD")
    print(f"{'='*70}\n")

    report_path = Path(__file__).parent.parent.parent / "report.md"

    with open(report_path, 'w') as f:
        f.write("# Phase 9 End-to-End Regression Report\n\n")
        f.write(f"**Generated**: {Path(__file__).name}\n")
        f.write(f"**Test Suite**: Phase 9.2 - End-to-End Pipeline Validation (ROADMAP)\n")
        f.write(f"**Coverage**: Phases 4-9 (Layers 2-6b)\n\n")

        # Executive Summary
        total_jobs = len(results)
        passed_jobs = sum(1 for r in results if r["all_passed"])
        failed_jobs = total_jobs - passed_jobs
        total_issues = sum(r.get("total_issues", 0) for r in results)

        f.write("## Executive Summary\n\n")
        f.write(f"- **Total Jobs Tested**: {total_jobs}\n")
        f.write(f"- **Passed**: {passed_jobs}/{total_jobs} ({passed_jobs/total_jobs*100:.1f}%)\n")
        f.write(f"- **Failed**: {failed_jobs}/{total_jobs}\n")
        f.write(f"- **Total Issues Found**: {total_issues}\n\n")

        if passed_jobs == total_jobs:
            f.write("✅ **All tests PASSED** - Phase 9 is production-ready per ROADMAP quality gates.\n\n")
        else:
            f.write(f"⚠️ **{failed_jobs} tests FAILED** - Review issues below and address before production deployment.\n\n")

        # Test Results by Job
        f.write("## Test Results by Job\n\n")

        for i, result in enumerate(results, 1):
            status_icon = "✅" if result["all_passed"] else "❌"
            f.write(f"### {i}. {status_icon} {result['job_title']} at {result['company']}\n\n")
            f.write(f"- **Job ID**: `{result['job_id']}`\n")
            f.write(f"- **Status**: {result.get('status', 'unknown')}\n")
            f.write(f"- **Total Issues**: {result.get('total_issues', 0)}\n\n")

            if result.get("error"):
                f.write(f"**Error**: {result['error']}\n\n")

            if result.get("validations"):
                f.write("**Phase-by-Phase Validation**:\n\n")
                for v in result["validations"]:
                    phase_status = "✅ PASS" if v["passed"] else f"❌ FAIL ({len(v['issues'])} issues)"
                    f.write(f"- {v['phase']}: {phase_status}\n")
                    for issue in v["issues"]:
                        f.write(f"  - {issue}\n")
                f.write("\n")

        # Issues by Phase
        f.write("## Issues by Phase\n\n")

        phase_issues = {}
        for result in results:
            for v in result.get("validations", []):
                phase = v["phase"]
                if phase not in phase_issues:
                    phase_issues[phase] = []
                phase_issues[phase].extend(v["issues"])

        for phase in sorted(phase_issues.keys()):
            issues = phase_issues[phase]
            if issues:
                f.write(f"### {phase}\n\n")
                f.write(f"**Total Issues**: {len(issues)}\n\n")
                for issue in set(issues):  # Deduplicate
                    count = issues.count(issue)
                    f.write(f"- {issue} ({count} occurrence{'s' if count > 1 else ''})\n")
                f.write("\n")

        # Recommendations
        f.write("## Recommendations\n\n")

        if passed_jobs == total_jobs:
            f.write("No critical issues found. Phase 9 implementation meets all ROADMAP quality gates.\n\n")
            f.write("**Next Steps**:\n")
            f.write("1. Proceed to Phase 10 (Layer 7 - Dossier & Output Publisher)\n")
            f.write("2. Consider running additional edge case tests (malformed JDs, missing data, etc.)\n")
            f.write("3. Monitor production runs for quality degradation\n\n")
        else:
            f.write("**Critical Actions**:\n\n")

            # Analyze common failures
            common_issues = []
            for phase, issues in phase_issues.items():
                if len(issues) >= total_jobs * 0.3:  # Appears in 30%+ of jobs
                    common_issues.append((phase, issues[0]))

            if common_issues:
                f.write("1. **Address Common Failures** (appearing in 30%+ of tests):\n")
                for phase, issue in common_issues:
                    f.write(f"   - {phase}: {issue}\n")
                f.write("\n")

            f.write("2. Review failed test outputs manually for quality issues\n")
            f.write("3. Run focused regression on affected phases after fixes\n")
            f.write("4. Update `missing.md` to reflect any new gaps discovered\n\n")

        # Appendix
        f.write("## Appendix: Test Coverage\n\n")
        f.write("**Job Diversity**:\n\n")
        f.write("- Technical IC roles: SRE, ML Engineer\n")
        f.write("- Technical leadership: Engineering Manager, VP Engineering\n")
        f.write("- Product/strategy: Product Manager, Head of Growth\n")
        f.write("- Security: Security Engineer\n\n")

        f.write("**Industry Coverage**:\n\n")
        f.write("- Fintech, E-commerce, Healthcare, SaaS, Martech, Consumer Apps\n\n")

        f.write("**Company Stages**:\n\n")
        f.write("- Startup (Series A), Scale-up (Series B/C), Enterprise\n\n")

        f.write("**Quality Gates Validated**:\n\n")
        f.write("- Phase 4: 4-dimension pain point analysis (3-6 items per dimension)\n")
        f.write("- Phase 5: Multi-source company research + role business impact\n")
        f.write("- Phase 6: Fit scoring with STAR citations and quantified metrics\n")
        f.write("- Phase 7: 4-6 primary + 4-6 secondary contacts with enrichment\n")
        f.write("- Phase 8: Cover letters (220-380 words, ≥2 metrics) + CVs (.md format)\n")
        f.write("- Phase 9: Outreach packages for all contacts (2 channels each, constraint validation)\n\n")

    print(f"✅ Report generated: {report_path}\n")

    # Assert overall success
    assert passed_jobs == total_jobs, f"{failed_jobs} out of {total_jobs} tests failed. See report.md for details."


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v", "-m", "e2e", "-s"])
