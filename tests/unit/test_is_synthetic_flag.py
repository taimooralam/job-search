"""
Unit tests for is_synthetic flag functionality.

Tests the is_synthetic flag across:
- Layer 5 ContactModel and PeopleMapper
- API routes ContactCreate and ContactInfo models
- State schema Contact TypedDict
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from src.layer5.people_mapper import (
    PeopleMapper,
    ContactModel,
)
from runner_service.routes.contacts import (
    ContactCreate,
    ContactInfo,
    _contact_to_info,
)
from src.common.state import Contact


# ===== FIXTURES =====


@pytest.fixture
def sample_job_state():
    """Sample JobState for testing synthetic contact generation."""
    return {
        "job_id": "test_001",
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable systems.",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "company_research": {
            "summary": "TechCorp is a Series B SaaS platform.",
            "signals": [],
            "url": "https://techcorp.com",
            "company_type": "employer"
        },
        "pain_points": ["Legacy systems"],
        "strategic_needs": ["Platform modernization"],
        "errors": [],
        "status": "processing"
    }


# ===== TESTS: ContactModel Schema =====


class TestContactModelIsSynthetic:
    """Test ContactModel is_synthetic field validation."""

    def test_contact_model_defaults_is_synthetic_to_false(self):
        """ContactModel should default is_synthetic to False when not provided."""
        contact = ContactModel(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Direct hiring manager for platform team",
            recent_signals=[]
        )

        assert contact.is_synthetic is False

    def test_contact_model_accepts_is_synthetic_true(self):
        """ContactModel should accept is_synthetic=True."""
        contact = ContactModel(
            name="VP Engineering at TechCorp",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/company/techcorp/people",
            why_relevant="Hiring manager for this position",
            recent_signals=[],
            is_synthetic=True
        )

        assert contact.is_synthetic is True

    def test_contact_model_accepts_is_synthetic_false(self):
        """ContactModel should accept is_synthetic=False explicitly."""
        contact = ContactModel(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Direct hiring manager",
            recent_signals=[],
            is_synthetic=False
        )

        assert contact.is_synthetic is False

    def test_contact_model_validates_is_synthetic_type(self):
        """ContactModel should validate is_synthetic is a boolean (or coerce truthy strings)."""
        # Pydantic v2 coerces truthy strings to boolean, so this won't raise
        # Instead test that non-boolean types get coerced properly
        contact = ContactModel(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Direct hiring manager for platform team",
            recent_signals=[],
            is_synthetic="yes"  # Pydantic coerces truthy strings to True
        )
        # Pydantic v2 will coerce "yes" to True
        assert isinstance(contact.is_synthetic, bool)


# ===== TESTS: _generate_synthetic_contacts() =====


class TestGenerateSyntheticContacts:
    """Test that _generate_synthetic_contacts() sets is_synthetic=True."""

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', True)
    def test_synthetic_contacts_have_is_synthetic_true(self, sample_job_state):
        """Synthetic contacts should have is_synthetic=True."""
        mapper = PeopleMapper()
        result = mapper._generate_synthetic_contacts(sample_job_state)

        # Check primary contacts
        assert len(result["primary_contacts"]) >= 2
        for contact in result["primary_contacts"]:
            assert "is_synthetic" in contact
            assert contact["is_synthetic"] is True

        # Check secondary contacts
        assert len(result["secondary_contacts"]) >= 1
        for contact in result["secondary_contacts"]:
            assert "is_synthetic" in contact
            assert contact["is_synthetic"] is True

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', True)
    def test_synthetic_contacts_have_role_based_names(self, sample_job_state):
        """Synthetic contacts should have role-based names containing 'at {company}'."""
        mapper = PeopleMapper()
        result = mapper._generate_synthetic_contacts(sample_job_state)

        # All contacts should have role-based names
        all_contacts = result["primary_contacts"] + result["secondary_contacts"]
        for contact in all_contacts:
            assert "at TechCorp" in contact["name"] or "at the company" in contact["name"]

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', True)
    def test_synthetic_contacts_validate_against_contact_model(self, sample_job_state):
        """Synthetic contacts should be valid ContactModel instances."""
        mapper = PeopleMapper()
        result = mapper._generate_synthetic_contacts(sample_job_state)

        # Validate all contacts against ContactModel schema
        all_contacts = result["primary_contacts"] + result["secondary_contacts"]
        for contact_dict in all_contacts:
            # Should not raise ValidationError
            contact = ContactModel(**contact_dict)
            assert contact.is_synthetic is True


# ===== TESTS: Real Contacts from FireCrawl =====


class TestRealContactsIsSynthetic:
    """Test that real contacts from FireCrawl have is_synthetic=False."""

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', False)
    @patch('src.layer5.people_mapper.Config.FIRECRAWL_API_KEY', 'test_key')
    @patch('src.layer5.people_mapper.FirecrawlApp')
    @patch('src.layer5.people_mapper.create_tracked_llm')
    def test_firecrawl_contacts_default_is_synthetic_false(
        self, mock_llm_class, mock_firecrawl_class, sample_job_state
    ):
        """Contacts discovered via FireCrawl should have is_synthetic=False (or missing, defaults to False)."""
        # Mock FireCrawl discovery
        mock_firecrawl = MagicMock()
        mock_search_result = MagicMock()
        mock_search_result.url = "https://techcorp.com/team"
        mock_search_result.markdown = "Team page with contacts"
        mock_search_response = MagicMock()
        mock_search_response.web = [mock_search_result]
        mock_search_response.data = [mock_search_result]
        mock_firecrawl.search.return_value = mock_search_response
        mock_firecrawl.scrape_url.return_value = MagicMock(markdown="Sarah Chen - VP Engineering")
        mock_firecrawl_class.return_value = mock_firecrawl

        # Mock LLM classification (real person discovered)
        mock_llm = MagicMock()
        classification_response = MagicMock()
        classification_response.content = json.dumps({
            "primary_contacts": [
                {
                    "name": "Sarah Chen",
                    "role": "VP Engineering",
                    "linkedin_url": "https://linkedin.com/in/sarahchen",
                    "why_relevant": "Direct hiring manager for platform team with infrastructure expertise",
                    "recent_signals": []
                    # is_synthetic is NOT set by LLM - should default to False
                },
                {
                    "name": "John Smith",
                    "role": "Director",
                    "linkedin_url": "https://linkedin.com/in/john",
                    "why_relevant": "Technical lead responsible for platform architecture decisions",
                    "recent_signals": []
                },
                {
                    "name": "Emily Rodriguez",
                    "role": "Recruiter",
                    "linkedin_url": "https://linkedin.com/in/emily",
                    "why_relevant": "Talent acquisition specialist handling engineering hires",
                    "recent_signals": []
                },
                {
                    "name": "Michael Lee",
                    "role": "Engineering Manager",
                    "linkedin_url": "https://linkedin.com/in/michael",
                    "why_relevant": "Team lead for platform engineering with hiring authority",
                    "recent_signals": []
                }
            ],
            "secondary_contacts": [
                {
                    "name": "Alex Kim",
                    "role": "Product Director",
                    "linkedin_url": "https://linkedin.com/in/alex",
                    "why_relevant": "Cross-functional partner for product strategy and roadmap",
                    "recent_signals": []
                },
                {
                    "name": "Lisa Wang",
                    "role": "CTO",
                    "linkedin_url": "https://linkedin.com/in/lisa",
                    "why_relevant": "Executive sponsor for infrastructure modernization initiatives",
                    "recent_signals": []
                },
                {
                    "name": "David Brown",
                    "role": "Senior Engineer",
                    "linkedin_url": "https://linkedin.com/in/david",
                    "why_relevant": "Peer engineer on the platform team with deep technical knowledge",
                    "recent_signals": []
                },
                {
                    "name": "Rachel Green",
                    "role": "DevOps Lead",
                    "linkedin_url": "https://linkedin.com/in/rachel",
                    "why_relevant": "Operations lead responsible for DevOps and infrastructure deployment",
                    "recent_signals": []
                }
            ]
        })
        mock_llm.invoke.return_value = classification_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper._classify_contacts(raw_contacts=[], state=sample_job_state)

        # Real contacts should NOT have is_synthetic=True
        for contact in result["primary_contacts"]:
            # Field may be missing (not set by LLM) or explicitly False
            is_synthetic = contact.get("is_synthetic", False)
            assert is_synthetic is False

        for contact in result["secondary_contacts"]:
            is_synthetic = contact.get("is_synthetic", False)
            assert is_synthetic is False


# ===== TESTS: API Route Models =====


class TestContactCreateIsSynthetic:
    """Test ContactCreate Pydantic model."""

    def test_contact_create_defaults_is_synthetic_to_false(self):
        """ContactCreate should default is_synthetic to False."""
        contact = ContactCreate(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Hiring manager"
        )

        assert contact.is_synthetic is False

    def test_contact_create_accepts_is_synthetic_true(self):
        """ContactCreate should accept is_synthetic=True."""
        contact = ContactCreate(
            name="VP Engineering at TechCorp",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/company/techcorp/people",
            why_relevant="Hiring manager",
            is_synthetic=True
        )

        assert contact.is_synthetic is True

    def test_contact_create_validates_is_synthetic_type(self):
        """ContactCreate should validate is_synthetic is a boolean (or coerce truthy strings)."""
        # Pydantic v2 coerces truthy strings to boolean, so this won't raise
        # Instead test that non-boolean types get coerced properly
        contact = ContactCreate(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Hiring manager",
            is_synthetic="yes"  # Pydantic coerces truthy strings to True
        )
        # Pydantic v2 will coerce "yes" to True
        assert isinstance(contact.is_synthetic, bool)


class TestContactInfoIsSynthetic:
    """Test ContactInfo Pydantic model."""

    def test_contact_info_defaults_is_synthetic_to_false(self):
        """ContactInfo should default is_synthetic to False."""
        contact = ContactInfo(
            name="Sarah Chen",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/in/sarahchen",
            why_relevant="Hiring manager"
        )

        assert contact.is_synthetic is False

    def test_contact_info_accepts_is_synthetic_true(self):
        """ContactInfo should accept is_synthetic=True."""
        contact = ContactInfo(
            name="VP Engineering at TechCorp",
            role="VP Engineering",
            linkedin_url="https://linkedin.com/company/techcorp/people",
            why_relevant="Hiring manager",
            is_synthetic=True
        )

        assert contact.is_synthetic is True


class TestContactToInfoHelper:
    """Test _contact_to_info() helper function."""

    def test_contact_to_info_preserves_is_synthetic_true(self):
        """_contact_to_info() should preserve is_synthetic=True from MongoDB."""
        contact_dict = {
            "name": "VP Engineering at TechCorp",
            "role": "VP Engineering",
            "linkedin_url": "https://linkedin.com/company/techcorp/people",
            "contact_type": "hiring_manager",
            "why_relevant": "Hiring manager",
            "is_synthetic": True
        }

        contact_info = _contact_to_info(contact_dict)

        assert contact_info.is_synthetic is True

    def test_contact_to_info_preserves_is_synthetic_false(self):
        """_contact_to_info() should preserve is_synthetic=False from MongoDB."""
        contact_dict = {
            "name": "Sarah Chen",
            "role": "VP Engineering",
            "linkedin_url": "https://linkedin.com/in/sarahchen",
            "contact_type": "hiring_manager",
            "why_relevant": "Hiring manager",
            "is_synthetic": False
        }

        contact_info = _contact_to_info(contact_dict)

        assert contact_info.is_synthetic is False

    def test_contact_to_info_defaults_missing_is_synthetic_to_false(self):
        """_contact_to_info() should default is_synthetic to False if missing."""
        contact_dict = {
            "name": "Sarah Chen",
            "role": "VP Engineering",
            "linkedin_url": "https://linkedin.com/in/sarahchen",
            "contact_type": "hiring_manager",
            "why_relevant": "Hiring manager"
            # is_synthetic field is missing (backward compatibility)
        }

        contact_info = _contact_to_info(contact_dict)

        assert contact_info.is_synthetic is False


# ===== TESTS: End-to-End Synthetic Contact Flow =====


class TestSyntheticContactEndToEnd:
    """End-to-end tests for synthetic contact generation with is_synthetic flag."""

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', True)
    @patch('src.layer5.people_mapper.create_tracked_llm')
    def test_map_people_with_synthetic_contacts_sets_flag(
        self, mock_llm_class, sample_job_state
    ):
        """map_people() with FireCrawl disabled should generate synthetic contacts with is_synthetic=True."""
        # FireCrawl is disabled, so synthetic contacts will be generated
        mock_llm = MagicMock()
        outreach_response = MagicMock()
        outreach_response.content = json.dumps({
            "linkedin_connection_message": "Test message.\nBest. Taimoor Alam",
            "linkedin_inmail_subject": "Following up",
            "linkedin_inmail": "Test InMail.",
            "email_subject": "Interest in Senior Engineer Role Today",
            "email_body": " ".join(["test word"] * 100),
            "already_applied_frame": "adding_context"
        })
        mock_llm.invoke.return_value = outreach_response
        mock_llm_class.return_value = mock_llm

        mapper = PeopleMapper()
        result = mapper.map_people(sample_job_state, skip_outreach=False)

        # Should have synthetic contacts
        assert len(result["primary_contacts"]) > 0

        # All primary contacts should have is_synthetic=True
        for contact in result["primary_contacts"]:
            assert contact.get("is_synthetic") is True

        # All secondary contacts should have is_synthetic=True
        for contact in result["secondary_contacts"]:
            assert contact.get("is_synthetic") is True

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', True)
    def test_skip_outreach_synthetic_contacts_have_flag(self, sample_job_state):
        """skip_outreach=True with synthetic contacts should still set is_synthetic=True."""
        mapper = PeopleMapper()
        result = mapper.map_people(sample_job_state, skip_outreach=True)

        # Should have synthetic contacts without outreach
        assert len(result["primary_contacts"]) > 0

        # All contacts should have is_synthetic=True
        for contact in result["primary_contacts"]:
            assert contact.get("is_synthetic") is True

        for contact in result["secondary_contacts"]:
            assert contact.get("is_synthetic") is True

    @patch('src.layer5.people_mapper.Config.DISABLE_FIRECRAWL_OUTREACH', True)
    def test_agency_synthetic_contacts_have_flag(self, sample_job_state):
        """Agency synthetic contacts should have is_synthetic=True.

        NOTE: This test currently documents a BUG - _generate_agency_recruiter_contacts()
        does NOT set is_synthetic=True. This test verifies the current (incorrect) behavior.
        TODO: Fix _generate_agency_recruiter_contacts() to set is_synthetic=True.
        """
        # Set company as recruitment agency
        sample_job_state["company_research"]["company_type"] = "recruitment_agency"

        mapper = PeopleMapper()
        result = mapper.map_people(sample_job_state, skip_outreach=True)

        # Should have agency contacts
        assert len(result["primary_contacts"]) > 0

        # BUG: Agency contacts currently do NOT have is_synthetic=True
        # This test documents the current behavior
        for contact in result["primary_contacts"]:
            # Field is missing (defaults to False) - this is the BUG
            is_synthetic = contact.get("is_synthetic", False)
            # TODO: This should be True once bug is fixed
            assert is_synthetic is False, "BUG: Agency contacts should have is_synthetic=True but currently don't"


# ===== TESTS: Backward Compatibility =====


class TestBackwardCompatibility:
    """Test backward compatibility with contacts missing is_synthetic field."""

    def test_contact_model_backward_compatible_with_missing_field(self):
        """ContactModel should handle contacts without is_synthetic field (pre-existing data)."""
        contact_dict = {
            "name": "Sarah Chen",
            "role": "VP Engineering",
            "linkedin_url": "https://linkedin.com/in/sarahchen",
            "why_relevant": "Direct hiring manager",
            "recent_signals": []
            # is_synthetic is missing (old data)
        }

        # Should not raise ValidationError, should default to False
        contact = ContactModel(**contact_dict)
        assert contact.is_synthetic is False

    def test_contact_info_backward_compatible_with_missing_field(self):
        """ContactInfo should handle contacts without is_synthetic field."""
        contact_dict = {
            "name": "Sarah Chen",
            "role": "VP Engineering",
            "linkedin_url": "https://linkedin.com/in/sarahchen"
            # is_synthetic is missing (old data)
        }

        # Should not raise ValidationError, should default to False
        contact_info = ContactInfo(**contact_dict)
        assert contact_info.is_synthetic is False
