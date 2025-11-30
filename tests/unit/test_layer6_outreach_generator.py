"""
Unit tests for Layer 6b: Outreach Generator (Phase 9)

Tests verify:
1. Packaging logic (2 packages per contact: LinkedIn + Email)
2. Constraint preservation (LinkedIn ≤550 chars, email subject ≤100 chars)
3. Content constraints (no emojis, no placeholders except [Your Name], LinkedIn closing line)
4. Field mapping correctness
5. Primary and secondary contact handling
"""

import pytest
from unittest.mock import Mock, patch
from typing import List, Dict, Any

from src.common.state import JobState, Contact, OutreachPackage
from src.layer6.outreach_generator import (
    OutreachGenerator,
    outreach_generator_node,
)


# ===== FIXTURES =====

@pytest.fixture
def sample_contact() -> Contact:
    """Sample enriched contact from Layer 5 (GAP-011: ≤300 chars)."""
    return {
        "name": "Jane Smith",
        "role": "VP Engineering",
        "linkedin_url": "https://linkedin.com/in/janesmith",
        "why_relevant": "Leads the engineering team and makes hiring decisions for senior roles",
        "recent_signals": ["Posted about scaling challenges", "Attended AWS re:Invent"],
        # GAP-011: LinkedIn message must be ≤300 chars with "Best. Taimoor Alam" signature
        "linkedin_message": "Hi Jane, Your scaling challenges post caught my eye. I reduced incidents 75% at AdTech Corp. Would love to discuss how I can help your team.\nBest. Taimoor Alam",
        "email_subject": "Solving scaling challenges - 75% incident reduction experience",
        "email_body": "Dear Jane,\n\nI noticed your recent posts about scaling challenges at TestCo. I've been in similar situations and achieved meaningful results.\n\nAt AdTech Corp, I reduced incident response time by 75% while scaling to 10M users. I'd love to explore how my experience could help your team.\n\nBest regards,\n[Your Name]",
        "reasoning": "Personalized for VP Engineering role with relevant metrics"
    }


@pytest.fixture
def sample_contacts_list() -> List[Contact]:
    """Multiple enriched contacts for testing (GAP-011: ≤300 chars)."""
    return [
        {
            "name": "Alice Johnson",
            "role": "Engineering Manager",
            "linkedin_url": "https://linkedin.com/in/alicejohnson",
            "why_relevant": "Manages the infrastructure team",
            "recent_signals": [],
            # GAP-011: LinkedIn message must be ≤300 chars
            "linkedin_message": "Hi Alice, I led infrastructure migrations at DataCorp with 75% latency reduction. Happy to share insights on your current challenges.\nBest. Taimoor Alam",
            "email_subject": "Infrastructure expertise - DataCorp migration lead",
            "email_body": "Dear Alice,\n\nI led infrastructure migrations at DataCorp with great results.\n\nBest,\n[Your Name]",
            "reasoning": "Engineering Manager fit"
        },
        {
            "name": "Bob Chen",
            "role": "Senior Recruiter",
            "linkedin_url": "https://linkedin.com/in/bobchen",
            "why_relevant": "Technical recruiter for engineering roles",
            "recent_signals": ["Hiring for 5 senior positions"],
            # GAP-011: LinkedIn message must be ≤300 chars
            "linkedin_message": "Hi Bob, Interested in the senior engineering role. My distributed systems background aligns well with what you're looking for.\nBest. Taimoor Alam",
            "email_subject": "Senior Engineering Role - Distributed Systems Expert",
            "email_body": "Dear Bob,\n\nI'm interested in the senior engineering position.\n\nBest,\n[Your Name]",
            "reasoning": "Recruiter contact"
        }
    ]


@pytest.fixture
def sample_state_with_contacts(sample_contacts_list) -> JobState:
    """JobState with enriched contacts from Layer 5."""
    return {
        "job_id": "test123",
        "title": "Senior Software Engineer",
        "company": "TestCo",
        "job_description": "Build amazing software...",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "Experienced engineer...",
        "pain_points": ["Legacy system maintenance", "Scaling challenges"],
        "strategic_needs": None,
        "risks_if_unfilled": None,
        "success_metrics": None,
        "selected_stars": [],
        "star_to_pain_mapping": None,
        "all_stars": None,
        "company_research": None,
        "company_summary": None,
        "company_url": None,
        "role_research": None,
        "fit_score": 85,
        "fit_rationale": "Strong fit",
        "fit_category": "strong",
        "primary_contacts": sample_contacts_list[:2],  # 2 primary
        "secondary_contacts": [sample_contacts_list[1]],  # 1 secondary
        "people": sample_contacts_list,
        "outreach_packages": None,
        "cover_letter": None,
        "cv_path": None,
        "cv_reasoning": None,
        "drive_folder_url": None,
        "sheet_row_id": None,
        "run_id": "test-run-123",
        "created_at": "2025-01-18T12:00:00Z",
        "errors": [],
        "status": "processing"
    }


# ===== PACKAGING LOGIC TESTS =====

def test_generate_outreach_packages_creates_two_per_contact(sample_contact):
    """Test that each contact generates exactly 2 packages (LinkedIn + Email)."""
    generator = OutreachGenerator()

    packages = generator._create_packages_for_contact(sample_contact)

    assert len(packages) == 2
    assert packages[0]["channel"] == "linkedin"
    assert packages[1]["channel"] == "email"


def test_linkedin_package_structure(sample_contact):
    """Test LinkedIn package has correct structure and fields."""
    generator = OutreachGenerator()

    packages = generator._create_packages_for_contact(sample_contact)
    linkedin_pkg = packages[0]

    assert linkedin_pkg["contact_name"] == "Jane Smith"
    assert linkedin_pkg["contact_role"] == "VP Engineering"
    assert linkedin_pkg["linkedin_url"] == "https://linkedin.com/in/janesmith"
    assert linkedin_pkg["channel"] == "linkedin"
    assert linkedin_pkg["message"] == sample_contact["linkedin_message"]
    assert linkedin_pkg["subject"] is None  # LinkedIn has no subject
    assert "reasoning" in linkedin_pkg


def test_email_package_structure(sample_contact):
    """Test Email package has correct structure and fields."""
    generator = OutreachGenerator()

    packages = generator._create_packages_for_contact(sample_contact)
    email_pkg = packages[1]

    assert email_pkg["contact_name"] == "Jane Smith"
    assert email_pkg["contact_role"] == "VP Engineering"
    assert email_pkg["linkedin_url"] == "https://linkedin.com/in/janesmith"
    assert email_pkg["channel"] == "email"
    assert email_pkg["message"] == sample_contact["email_body"]
    assert email_pkg["subject"] == sample_contact["email_subject"]
    assert "reasoning" in email_pkg


def test_generate_outreach_packages_handles_multiple_contacts(sample_state_with_contacts):
    """Test generating packages for multiple contacts."""
    generator = OutreachGenerator()

    result = generator.generate_outreach_packages(sample_state_with_contacts)

    # 2 primary + 1 secondary = 3 contacts × 2 packages each = 6 packages
    assert len(result) == 6

    # Verify all packages have required fields
    for pkg in result:
        assert "contact_name" in pkg
        assert "contact_role" in pkg
        assert "linkedin_url" in pkg
        assert "channel" in pkg
        assert "message" in pkg
        assert "subject" in pkg or pkg["channel"] == "linkedin"
        assert "reasoning" in pkg


def test_generate_outreach_packages_includes_both_primary_and_secondary(sample_state_with_contacts):
    """Test that both primary and secondary contacts generate packages."""
    generator = OutreachGenerator()

    result = generator.generate_outreach_packages(sample_state_with_contacts)

    # Extract contact names from packages
    contact_names = {pkg["contact_name"] for pkg in result}

    # Should include contacts from both buckets
    assert "Alice Johnson" in contact_names  # Primary
    assert "Bob Chen" in contact_names  # Primary and Secondary


# ===== CONSTRAINT PRESERVATION TESTS =====

def test_linkedin_message_length_preserved():
    """Test that LinkedIn messages ≤550 chars are preserved as-is."""
    generator = OutreachGenerator()

    # GAP-011: Create a valid 280-char message with proper closing
    closing = "\nBest. Taimoor Alam"
    message_body = "A" * 260
    linkedin_message = message_body + closing  # ~280 chars total, within 300 limit

    contact = {
        "name": "Test User",
        "role": "Engineer",
        "linkedin_url": "https://linkedin.com/in/test",
        "why_relevant": "Testing",
        "recent_signals": [],
        "linkedin_message": linkedin_message,
        "email_subject": "Test",
        "email_body": "Test body with [Your Name]",
        "reasoning": "Test"
    }

    packages = generator._create_packages_for_contact(contact)
    linkedin_pkg = [p for p in packages if p["channel"] == "linkedin"][0]

    # GAP-011: Message must be within 300 char limit
    assert len(linkedin_pkg["message"]) <= 300


def test_linkedin_message_at_boundary():
    """Test LinkedIn message exactly at 300 char boundary (GAP-011)."""
    generator = OutreachGenerator()

    # GAP-011: Create a message exactly 300 chars with proper closing
    closing = "\nBest. Taimoor Alam"  # 19 chars
    message_body = "A" * (300 - len(closing))
    linkedin_message = message_body + closing  # Exactly 300 chars

    contact = {
        "name": "Test User",
        "role": "Engineer",
        "linkedin_url": "https://linkedin.com/in/test",
        "why_relevant": "Testing",
        "recent_signals": [],
        "linkedin_message": linkedin_message,
        "email_subject": "Test",
        "email_body": "Test body with [Your Name]",
        "reasoning": "Test"
    }

    packages = generator._create_packages_for_contact(contact)
    linkedin_pkg = [p for p in packages if p["channel"] == "linkedin"][0]

    # GAP-011: Message should be exactly 300 chars (hard limit)
    assert len(linkedin_pkg["message"]) == 300


def test_email_subject_length_preserved():
    """Test that email subjects ≤100 chars are preserved."""
    generator = OutreachGenerator()

    # Use valid LinkedIn message with closing
    linkedin_message = "Hi there! Let's connect. Best. Taimoor Alam"

    contact = {
        "name": "Test User",
        "role": "Engineer",
        "linkedin_url": "https://linkedin.com/in/test",
        "why_relevant": "Testing",
        "recent_signals": [],
        "linkedin_message": linkedin_message,
        "email_subject": "A" * 95,  # 95 chars, within limit
        "email_body": "Test body with [Your Name]",
        "reasoning": "Test"
    }

    packages = generator._create_packages_for_contact(contact)
    email_pkg = [p for p in packages if p["channel"] == "email"][0]

    assert len(email_pkg["subject"]) == 95


def test_email_subject_at_boundary():
    """Test email subject exactly at 100 char boundary."""
    generator = OutreachGenerator()

    # Use valid LinkedIn message with closing
    linkedin_message = "Hi! Interested in the role. Best. Taimoor Alam"

    contact = {
        "name": "Test User",
        "role": "Engineer",
        "linkedin_url": "https://linkedin.com/in/test",
        "why_relevant": "Testing",
        "recent_signals": [],
        "linkedin_message": linkedin_message,
        "email_subject": "A" * 100,  # Exactly 100 chars
        "email_body": "Test body with [Your Name]",
        "reasoning": "Test"
    }

    packages = generator._create_packages_for_contact(contact)
    email_pkg = [p for p in packages if p["channel"] == "email"][0]

    assert len(email_pkg["subject"]) == 100


# ===== CONTENT CONSTRAINT TESTS =====

def test_validates_no_emojis_in_linkedin_message():
    """Test validation rejects emojis in LinkedIn messages."""
    generator = OutreachGenerator()

    message_with_emoji = "Hi there! 🚀 Let's connect and discuss opportunities 🎯"

    with pytest.raises(ValueError, match="emojis"):
        generator._validate_content_constraints(message_with_emoji, "linkedin")


def test_validates_no_emojis_in_email():
    """Test validation rejects emojis in email messages."""
    generator = OutreachGenerator()

    message_with_emoji = "Dear Hiring Manager,\n\nExcited to apply! 😊\n\nBest regards"

    with pytest.raises(ValueError, match="emojis"):
        generator._validate_content_constraints(message_with_emoji, "email")


def test_allows_your_name_placeholder():
    """Test that [Your Name] placeholder is allowed."""
    generator = OutreachGenerator()

    message = "Best regards,\n[Your Name]"

    # Should not raise
    generator._validate_content_constraints(message, "email")


def test_rejects_disallowed_placeholders():
    """Test validation rejects placeholders other than [Your Name]."""
    generator = OutreachGenerator()

    message_with_placeholder = "Hi [Contact Name], I'm interested in [Company Name]"

    with pytest.raises(ValueError, match="placeholder"):
        generator._validate_content_constraints(message_with_placeholder, "linkedin")


def test_linkedin_message_requires_closing_line():
    """Test that LinkedIn messages must end with signature (GAP-011)."""
    generator = OutreachGenerator()

    message_without_closing = "Hi Jane, I have relevant experience. Let's chat!"

    with pytest.raises(ValueError, match='LinkedIn message must end with signature'):
        generator._validate_linkedin_closing(message_without_closing)


def test_linkedin_message_accepts_valid_closing():
    """Test that valid LinkedIn signature is accepted (GAP-011)."""
    generator = OutreachGenerator()

    # GAP-011: New format with signature only (≤300 chars)
    message_with_closing = "Hi Jane, I have relevant experience. Would love to connect.\nBest. Taimoor Alam"

    # Should not raise
    generator._validate_linkedin_closing(message_with_closing)


def test_linkedin_message_accepts_alternate_closing_format():
    """Test alternate valid closing formats (GAP-011)."""
    generator = OutreachGenerator()

    # GAP-011: Just needs "best" and "taimoor" in message
    message = "Great to connect! Let's discuss.\nBest. Taimoor Alam"

    # Should not raise
    generator._validate_linkedin_closing(message)


# ===== EDGE CASES =====

def test_handles_empty_contact_list():
    """Test handling of empty contact lists."""
    generator = OutreachGenerator()

    state = {
        "primary_contacts": [],
        "secondary_contacts": [],
    }

    result = generator.generate_outreach_packages(state)

    assert result == []


def test_handles_contacts_without_outreach_fields():
    """Test graceful handling of contacts missing outreach fields."""
    generator = OutreachGenerator()

    incomplete_contact = {
        "name": "Test User",
        "role": "Engineer",
        "linkedin_url": "https://linkedin.com/in/test",
        "why_relevant": "Testing",
        "recent_signals": [],
        # Missing: linkedin_message, email_subject, email_body, reasoning
    }

    # Should skip contacts without outreach fields (or raise clear error)
    with pytest.raises(KeyError):
        generator._create_packages_for_contact(incomplete_contact)


def test_handles_none_contact_lists():
    """Test handling when contact lists are None."""
    generator = OutreachGenerator()

    state = {
        "primary_contacts": None,
        "secondary_contacts": None,
    }

    result = generator.generate_outreach_packages(state)

    assert result == []


# ===== NODE FUNCTION TESTS =====

def test_outreach_generator_node_returns_packages(sample_state_with_contacts):
    """Test that node function returns outreach_packages in state update."""
    result = outreach_generator_node(sample_state_with_contacts)

    assert "outreach_packages" in result
    assert isinstance(result["outreach_packages"], list)
    assert len(result["outreach_packages"]) > 0


def test_outreach_generator_node_updates_state(sample_state_with_contacts):
    """Test that node function returns valid state update."""
    result = outreach_generator_node(sample_state_with_contacts)

    # Should return dict with outreach_packages key
    assert isinstance(result, dict)
    assert "outreach_packages" in result


def test_outreach_generator_node_preserves_contact_count(sample_state_with_contacts):
    """Test that all contacts get packages (2 per contact)."""
    result = outreach_generator_node(sample_state_with_contacts)

    packages = result["outreach_packages"]

    # 2 primary + 1 secondary = 3 contacts × 2 = 6 packages
    expected_count = (
        len(sample_state_with_contacts.get("primary_contacts", [])) +
        len(sample_state_with_contacts.get("secondary_contacts", []))
    ) * 2

    assert len(packages) == expected_count


# ===== INTEGRATION TESTS =====

def test_full_pipeline_integration(sample_state_with_contacts):
    """Integration test: Full pipeline from state to packages."""
    generator = OutreachGenerator()

    packages = generator.generate_outreach_packages(sample_state_with_contacts)

    # Verify all packages are valid OutreachPackage TypedDicts
    for pkg in packages:
        assert isinstance(pkg["contact_name"], str)
        assert isinstance(pkg["contact_role"], str)
        assert isinstance(pkg["linkedin_url"], str)
        assert pkg["channel"] in ["linkedin", "email"]
        assert isinstance(pkg["message"], str)
        assert pkg["subject"] is None or isinstance(pkg["subject"], str)
        assert isinstance(pkg["reasoning"], str)


def test_packages_maintain_contact_identity(sample_state_with_contacts):
    """Test that packages correctly identify their source contact."""
    generator = OutreachGenerator()

    packages = generator.generate_outreach_packages(sample_state_with_contacts)

    # Group packages by contact
    contacts_in_packages = {pkg["contact_name"] for pkg in packages}

    # Should match original contacts
    original_contacts = (
        sample_state_with_contacts.get("primary_contacts", []) +
        sample_state_with_contacts.get("secondary_contacts", [])
    )
    original_names = {c["name"] for c in original_contacts}

    assert contacts_in_packages == original_names


# ===== MASTER-CV.MD GROUNDING TESTS (Phase 9 Enhancement) =====

class TestMasterCVGrounding:
    """Tests for master-cv.md company grounding validation in outreach."""

    @pytest.fixture
    def state_with_master_cv(self):
        """State with master-cv.md profile but no selected_stars."""
        return {
            "job_id": "test_master_cv",
            "company": "TechCorp",
            "title": "Senior Engineer",
            "candidate_profile": """
## Professional Experience

**Senior Platform Engineer** — AdTech Inc — San Francisco, CA
January 2020 - Present
- Led infrastructure modernization achieving 75% incident reduction
- Architected autoscaling solutions handling 100x traffic bursts

**Software Engineer** | FinTech Startup | Seattle, WA
2018 - 2019
- Built real-time payment processing system
- Reduced latency by 40% through optimization

## Education
Bachelor of Science, Computer Science — State University — 2017
""",
            "selected_stars": [],  # Empty - STAR selector disabled
            "primary_contacts": [
                {
                    "name": "Jane Smith",
                    "role": "VP Engineering",
                    "linkedin_url": "https://linkedin.com/in/janesmith",
                    "why_relevant": "Engineering leader",
                    "recent_signals": [],
                    "linkedin_message": "Hi Jane, I'm reaching out about the Senior Engineer role. At AdTech Inc, I led infrastructure modernization that achieved 75% incident reduction. I'd love to discuss how I can contribute to TechCorp.\n\nBest. Taimoor Alam",
                    "email_subject": "Senior Engineer with Proven Platform Scaling Experience",
                    "email_body": "Dear Jane, I'm excited about the Senior Engineer opportunity at TechCorp. " + "At AdTech Inc, I led a platform modernization initiative that reduced incidents by 75% and enabled the team to handle 100x traffic bursts. " * 4 + "I would welcome the chance to discuss how my experience aligns with your needs.",
                    "reasoning": "VP Engineering can evaluate technical fit"
                }
            ],
            "secondary_contacts": []
        }

    @pytest.fixture
    def state_with_selected_stars(self):
        """State with selected_stars (STAR selector enabled)."""
        return {
            "job_id": "test_stars",
            "company": "TechCorp",
            "title": "Senior Engineer",
            "candidate_profile": "",  # Not used when STARs available
            "selected_stars": [
                {"id": "1", "company": "AdTech Inc", "role": "Senior SRE"},
                {"id": "2", "company": "CloudCorp", "role": "Platform Engineer"}
            ],
            "primary_contacts": [
                {
                    "name": "John Doe",
                    "role": "Engineering Manager",
                    "linkedin_url": "https://linkedin.com/in/johndoe",
                    "why_relevant": "Direct hiring manager",
                    "recent_signals": [],
                    "linkedin_message": "Hi John, I'm interested in the Senior Engineer role. At AdTech Inc, I reduced incidents by 75%. " + "At CloudCorp, I built autoscaling systems. I'd love to discuss this opportunity.\n\nBest. Taimoor Alam",
                    "email_subject": "Platform Engineer with AdTech and CloudCorp Experience",
                    "email_body": "Dear John, I'm writing about the Senior Engineer role. " + "At AdTech Inc, I led infrastructure work reducing incidents by 75%. At CloudCorp, I built autoscaling systems. " * 3 + "I would appreciate the chance to discuss how my background fits.",
                    "reasoning": "Manager hiring for platform team"
                }
            ],
            "secondary_contacts": []
        }

    @pytest.fixture
    def state_without_company_mention(self):
        """State where outreach doesn't mention any company from profile."""
        return {
            "job_id": "test_no_company",
            "company": "TechCorp",
            "title": "Senior Engineer",
            "candidate_profile": """
## Professional Experience

**Senior Platform Engineer** — AdTech Inc — San Francisco, CA
- Led infrastructure modernization achieving 75% incident reduction
""",
            "selected_stars": [],
            "primary_contacts": [
                {
                    "name": "Bob Wilson",
                    "role": "CTO",
                    "linkedin_url": "https://linkedin.com/in/bobwilson",
                    "why_relevant": "Technical leader",
                    "recent_signals": [],
                    # This message doesn't mention AdTech Inc
                    "linkedin_message": "Hi Bob, I'm a senior engineer with experience in infrastructure. I've achieved significant incident reduction and built scalable systems. I'd love to discuss this role.\n\nBest. Taimoor Alam",
                    "email_subject": "Senior Engineer Interested in Platform Role",
                    "email_body": "Dear Bob, I'm writing about the Senior Engineer position. " + "I have extensive experience in platform engineering and infrastructure. " * 5 + "I would welcome the opportunity to discuss this further.",
                    "reasoning": "CTO can influence hiring"
                }
            ],
            "secondary_contacts": []
        }

    def test_validates_company_grounding_with_master_cv(self, state_with_master_cv, caplog):
        """Test that company grounding validation works with master-cv.md fallback."""
        import logging
        caplog.set_level(logging.INFO)

        generator = OutreachGenerator()

        packages = generator.generate_outreach_packages(state_with_master_cv)

        # Should generate packages successfully
        assert len(packages) == 2  # 1 contact × 2 channels

        # Should use master-cv.md fallback - check logger output
        assert "master-cv.md fallback" in caplog.text

    def test_validates_company_grounding_with_selected_stars(self, state_with_selected_stars, caplog):
        """Test that company grounding validation works with selected_stars."""
        import logging
        caplog.set_level(logging.INFO)

        generator = OutreachGenerator()

        packages = generator.generate_outreach_packages(state_with_selected_stars)

        # Should generate packages successfully
        assert len(packages) == 2

        # Should use STARs for grounding - check logger output
        assert "selected STAR" in caplog.text

    def test_warns_when_no_company_mentioned(self, state_without_company_mention, caplog):
        """Test that validation warns when outreach doesn't mention candidate's companies."""
        generator = OutreachGenerator()

        packages = generator.generate_outreach_packages(state_without_company_mention)

        # Should still generate packages (soft validation)
        assert len(packages) == 2

        # Should log warning about missing company mention
        assert "does not mention a company" in caplog.text

    def test_extracts_companies_from_em_dash_format(self):
        """Test company extraction from em-dash formatted profile."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
**Senior Engineer** — TechCorp Inc — San Francisco
**Lead Developer** — StartupXYZ — New York
"""
        companies = _extract_companies_from_profile(profile)
        assert "TechCorp Inc" in companies
        assert "StartupXYZ" in companies

    def test_extracts_companies_from_pipe_format(self):
        """Test company extraction from pipe-separated profile."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
Senior Engineer | MegaCorp | 2020 - Present
Software Developer | SmallCompany | 2018 - 2020
"""
        companies = _extract_companies_from_profile(profile)
        assert "MegaCorp" in companies
        assert "SmallCompany" in companies

    def test_skips_education_section_in_extraction(self):
        """Test that education section is skipped when extracting companies."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
## Professional Experience
**Engineer** — RealCompany — SF

## Education
Bachelor of Science — Stanford University — 2018
"""
        companies = _extract_companies_from_profile(profile)
        assert "RealCompany" in companies
        assert "Stanford University" not in companies

    def test_partial_company_name_matching(self, capsys):
        """Test that partial company names match in validation."""
        generator = OutreachGenerator()

        # Message mentions "FinTech" but profile has "FinTech Startup Inc"
        state = {
            "job_id": "test_partial",
            "company": "Target Co",
            "title": "Engineer",
            "candidate_profile": """
**Engineer** — FinTech Startup Inc — Seattle
""",
            "selected_stars": [],
            "primary_contacts": [
                {
                    "name": "Test Contact",
                    "role": "Manager",
                    "linkedin_url": "https://linkedin.com/in/test",
                    "why_relevant": "Hiring manager",
                    "recent_signals": [],
                    "linkedin_message": "At FinTech, I built payment systems. " * 3 + "\n\nBest. Taimoor Alam",
                    "email_subject": "Engineer with FinTech Payment Experience Interest",
                    "email_body": "I have extensive experience at FinTech building payment systems. " * 6,
                    "reasoning": "Direct manager"
                }
            ],
            "secondary_contacts": []
        }

        packages = generator.generate_outreach_packages(state)
        assert len(packages) == 2

        # Should NOT warn because "FinTech" is a partial match for "FinTech Startup Inc"
        captured = capsys.readouterr()
        assert "does not mention a company" not in captured.out

    def test_case_insensitive_company_matching(self, capsys):
        """Test that company matching is case-insensitive."""
        generator = OutreachGenerator()

        state = {
            "job_id": "test_case",
            "company": "Target Co",
            "title": "Engineer",
            "candidate_profile": """
**Engineer** — ACME Corporation — SF
""",
            "selected_stars": [],
            "primary_contacts": [
                {
                    "name": "Test Contact",
                    "role": "Manager",
                    "linkedin_url": "https://linkedin.com/in/test",
                    "why_relevant": "Hiring manager",
                    "recent_signals": [],
                    # Uses lowercase "acme"
                    "linkedin_message": "At acme, I built scalable systems. " * 3 + "\n\nBest. Taimoor Alam",
                    "email_subject": "Engineer from Acme with Platform Experience",
                    "email_body": "My experience at Acme includes building distributed systems. " * 5,
                    "reasoning": "Direct manager"
                }
            ],
            "secondary_contacts": []
        }

        packages = generator.generate_outreach_packages(state)
        assert len(packages) == 2

        # Should NOT warn because "acme" matches "ACME Corporation" (case-insensitive)
        captured = capsys.readouterr()
        assert "does not mention a company" not in captured.out
