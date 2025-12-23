"""
Unit Tests for Layer 5 Null Handling (Bugfix for NoneType.get() error)

Tests the defensive programming fixes for handling missing or None upstream data
from Layer 3 (Company Research) and Layer 2.5 (STAR Selector).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.layer5.people_mapper import (
    PeopleMapper,
    people_mapper_node,
    _safe_get_nested
)


# ===== FIXTURES =====

@pytest.fixture
def minimal_job_state():
    """Minimal JobState with only required fields."""
    return {
        "job_id": "test_minimal",
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable systems",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "Experienced engineer with 10 years in backend systems",
        "errors": [],
        "status": "processing"
    }


@pytest.fixture
def state_with_none_company_research(minimal_job_state):
    """JobState where company_research is explicitly None (Layer 3 failed)."""
    state = minimal_job_state.copy()
    state["company_research"] = None
    return state


@pytest.fixture
def state_with_missing_company_research(minimal_job_state):
    """JobState where company_research key is missing entirely."""
    # Don't add company_research key at all
    return minimal_job_state


@pytest.fixture
def state_with_partial_company_research(minimal_job_state):
    """JobState where company_research exists but is missing 'url' field."""
    state = minimal_job_state.copy()
    state["company_research"] = {
        "summary": "TechCorp is a SaaS company",
        "signals": []
        # 'url' key is missing
    }
    return state


# ===== TEST _safe_get_nested HELPER =====

class TestSafeGetNested:
    """Test the _safe_get_nested helper function."""

    def test_safe_get_nested_with_dict(self):
        """Test safe access on normal dict."""
        data = {"a": {"b": "value"}}
        assert _safe_get_nested(data, "a", "b") == "value"

    def test_safe_get_nested_with_none(self):
        """Test safe access on None object."""
        assert _safe_get_nested(None, "a", "b", default="fallback") == "fallback"

    def test_safe_get_nested_with_missing_key(self):
        """Test safe access on dict with missing key."""
        data = {"a": {}}
        assert _safe_get_nested(data, "a", "b", default="fallback") == "fallback"

    def test_safe_get_nested_with_none_intermediate(self):
        """Test safe access when intermediate value is None."""
        data = {"a": None}
        assert _safe_get_nested(data, "a", "b", default="fallback") == "fallback"

    def test_safe_get_nested_with_empty_dict(self):
        """Test safe access on empty dict."""
        assert _safe_get_nested({}, "a", default="fallback") == "fallback"

    def test_safe_get_nested_no_default(self):
        """Test safe access with no default specified."""
        assert _safe_get_nested(None, "a", "b") is None

    def test_safe_get_nested_single_key(self):
        """Test safe access with single key."""
        data = {"key": "value"}
        assert _safe_get_nested(data, "key") == "value"

    def test_safe_get_nested_triple_nested(self):
        """Test safe access with three levels of nesting."""
        data = {"a": {"b": {"c": "deep"}}}
        assert _safe_get_nested(data, "a", "b", "c") == "deep"

    def test_safe_get_nested_with_object_attribute(self):
        """Test safe access on object with attributes."""
        class MockObject:
            def __init__(self):
                self.field = "value"

        obj = {"outer": MockObject()}
        assert _safe_get_nested(obj, "outer", "field") == "value"


# ===== TEST NULL COMPANY_RESEARCH HANDLING =====

class TestNullCompanyResearchHandling:
    """Test that Layer 5 handles missing/None company_research gracefully."""

    @patch('src.layer5.people_mapper.ClaudeWebResearcher')
    @patch('src.layer5.people_mapper.invoke_unified_sync')
    @patch('src.layer5.people_mapper.PeopleMapper._generate_outreach_package')
    def test_handles_none_company_research(self, mock_outreach, mock_invoke, mock_claude_researcher_class, state_with_none_company_research):
        """Test that Layer 5 doesn't crash when company_research is None."""
        # Mock ClaudeWebResearcher to prevent real API calls
        mock_researcher = MagicMock()
        # Create mock research result that indicates failure
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "No company research available"
        async def mock_research_people(*args, **kwargs):
            return mock_result
        mock_researcher.research_people = mock_research_people
        mock_claude_researcher_class.return_value = mock_researcher

        # Mock LLM
        # mock_invoke is patched at function level

        # Mock outreach generation to avoid LLM calls
        mock_outreach.return_value = {
            "contact_name": "Test Contact",
            "contact_role": "Engineer",
            "linkedin_url": "https://linkedin.com/in/test",
            "linkedin_message": "Test message",
            "email_subject": "Test Subject",
            "email_body": "Test body",
            "why_relevant": "Test relevance",
            "recent_signals": [],
            "reasoning": "Test"
        }

        mapper = PeopleMapper()
        result = mapper.map_people(state_with_none_company_research)

        # Should not crash
        assert "primary_contacts" in result
        assert "secondary_contacts" in result

        # Should produce synthetic contacts (fallback)
        assert len(result["primary_contacts"]) >= 2
        assert len(result["secondary_contacts"]) >= 1

        # Should log warning but not error
        assert len(result.get("errors", [])) == 0

    @patch('src.layer5.people_mapper.ClaudeWebResearcher')
    @patch('src.layer5.people_mapper.invoke_unified_sync')
    @patch('src.layer5.people_mapper.PeopleMapper._generate_outreach_package')
    def test_handles_missing_company_research(self, mock_outreach, mock_invoke, mock_claude_researcher_class, state_with_missing_company_research):
        """Test that Layer 5 doesn't crash when company_research key is missing."""
        # Mock ClaudeWebResearcher to prevent real API calls
        mock_researcher = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        async def mock_research_people(*args, **kwargs):
            return mock_result
        mock_researcher.research_people = mock_research_people
        mock_claude_researcher_class.return_value = mock_researcher

        # Mock LLM
        # mock_invoke is patched at function level

        mock_outreach.return_value = {
            "contact_name": "Test Contact",
            "contact_role": "Engineer",
            "linkedin_url": "https://linkedin.com/in/test",
            "linkedin_message": "Test message",
            "email_subject": "Test Subject",
            "email_body": "Test body",
            "why_relevant": "Test relevance",
            "recent_signals": [],
            "reasoning": "Test"
        }

        mapper = PeopleMapper()
        result = mapper.map_people(state_with_missing_company_research)

        # Should not crash
        assert "primary_contacts" in result
        assert "secondary_contacts" in result

        # Should produce synthetic contacts (fallback)
        assert len(result["primary_contacts"]) >= 2

        # Should not have errors
        assert len(result.get("errors", [])) == 0

    @patch('src.layer5.people_mapper.ClaudeWebResearcher')
    @patch('src.layer5.people_mapper.invoke_unified_sync')
    @patch('src.layer5.people_mapper.PeopleMapper._generate_outreach_package')
    def test_handles_partial_company_research(self, mock_outreach, mock_invoke, mock_claude_researcher_class, state_with_partial_company_research):
        """Test that Layer 5 handles company_research missing 'url' field."""
        # Mock ClaudeWebResearcher to prevent real API calls
        mock_researcher = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        async def mock_research_people(*args, **kwargs):
            return mock_result
        mock_researcher.research_people = mock_research_people
        mock_claude_researcher_class.return_value = mock_researcher

        # Mock LLM
        # mock_invoke is patched at function level

        mock_outreach.return_value = {
            "contact_name": "Test Contact",
            "contact_role": "Engineer",
            "linkedin_url": "https://linkedin.com/in/test",
            "linkedin_message": "Test message",
            "email_subject": "Test Subject",
            "email_body": "Test body",
            "why_relevant": "Test relevance",
            "recent_signals": [],
            "reasoning": "Test"
        }

        mapper = PeopleMapper()
        result = mapper.map_people(state_with_partial_company_research)

        # Should not crash
        assert "primary_contacts" in result
        assert "secondary_contacts" in result

        # Should not have errors
        assert len(result.get("errors", [])) == 0


# ===== TEST UPSTREAM DEPENDENCY VALIDATION =====

class TestUpstreamDependencyValidation:
    """Test validation of critical upstream dependencies."""

    def test_fails_without_company(self, minimal_job_state):
        """Test that Layer 5 fails gracefully when company is missing."""
        state = minimal_job_state.copy()
        del state["company"]

        mapper = PeopleMapper()
        result = mapper.map_people(state)

        # Should return error
        assert len(result["errors"]) > 0
        assert "company" in result["errors"][0]

        # Should return empty contacts
        assert result["primary_contacts"] == []
        assert result["secondary_contacts"] == []

    def test_fails_without_title(self, minimal_job_state):
        """Test that Layer 5 fails gracefully when title is missing."""
        state = minimal_job_state.copy()
        del state["title"]

        mapper = PeopleMapper()
        result = mapper.map_people(state)

        # Should return error
        assert len(result["errors"]) > 0
        assert "title" in result["errors"][0]

        # Should return empty contacts
        assert result["primary_contacts"] == []
        assert result["secondary_contacts"] == []

    def test_fails_without_job_id(self, minimal_job_state):
        """Test that Layer 5 fails gracefully when job_id is missing."""
        state = minimal_job_state.copy()
        del state["job_id"]

        mapper = PeopleMapper()
        result = mapper.map_people(state)

        # Should return error
        assert len(result["errors"]) > 0
        assert "job_id" in result["errors"][0]

        # Should return empty contacts
        assert result["primary_contacts"] == []

    @patch('src.layer5.people_mapper.ClaudeWebResearcher')
    @patch('src.layer5.people_mapper.invoke_unified_sync')
    @patch('src.layer5.people_mapper.PeopleMapper._generate_outreach_package')
    def test_warns_on_missing_optional_fields(self, mock_outreach, mock_invoke, mock_claude_researcher, minimal_job_state, caplog):
        """Test that Layer 5 logs warnings for missing optional fields but continues."""
        # Mock ClaudeWebResearcher
        mock_researcher = MagicMock()
        mock_claude_researcher.return_value = mock_researcher

        # Mock LLM
        # mock_invoke is patched at function level

        # Remove all optional fields
        state = minimal_job_state.copy()
        # pain_points, company_research, role_research, selected_stars already missing

        mock_outreach.return_value = {
            "contact_name": "Test Contact",
            "contact_role": "Engineer",
            "linkedin_url": "https://linkedin.com/in/test",
            "linkedin_message": "Test message",
            "email_subject": "Test Subject",
            "email_body": "Test body",
            "why_relevant": "Test relevance",
            "recent_signals": [],
            "reasoning": "Test"
        }

        mapper = PeopleMapper()
        result = mapper.map_people(state)

        # Should still produce output
        assert len(result["primary_contacts"]) >= 2

        # Should not error out
        assert len(result.get("errors", [])) == 0


# ===== TEST FORMAT FUNCTIONS WITH NULL DATA =====

class TestFormatFunctionsNullHandling:
    """Test that formatting functions handle null/missing data gracefully."""

    def test_format_company_research_with_none(self):
        """Test _format_company_research_summary with None."""
        mapper = PeopleMapper()
        result = mapper._format_company_research_summary(None)

        assert result == "No company research available."

    def test_format_company_research_with_empty_dict(self):
        """Test _format_company_research_summary with empty dict."""
        mapper = PeopleMapper()
        result = mapper._format_company_research_summary({})

        assert result == "No company research available."

    def test_format_company_research_with_missing_summary(self):
        """Test _format_company_research_summary with missing summary."""
        mapper = PeopleMapper()
        result = mapper._format_company_research_summary({"signals": []})

        # Should not crash
        assert isinstance(result, str)

    def test_format_company_research_with_missing_signals(self):
        """Test _format_company_research_summary with missing signals."""
        mapper = PeopleMapper()
        result = mapper._format_company_research_summary({"summary": "TechCorp is great"})

        assert "TechCorp is great" in result

    def test_format_role_research_with_none(self):
        """Test _format_role_research_summary with None."""
        mapper = PeopleMapper()
        result = mapper._format_role_research_summary(None)

        assert result == "No role research available."

    def test_format_role_research_with_empty_dict(self):
        """Test _format_role_research_summary with empty dict."""
        mapper = PeopleMapper()
        result = mapper._format_role_research_summary({})

        assert result == "No role research available."

    def test_format_role_research_with_missing_why_now(self):
        """Test _format_role_research_summary with missing why_now."""
        mapper = PeopleMapper()
        result = mapper._format_role_research_summary({"summary": "Role summary"})

        assert "Role summary" in result


# ===== TEST INTEGRATION WITH NODE FUNCTION =====

class TestNodeFunctionNullHandling:
    """Test people_mapper_node integration with null data."""

    @patch('src.layer5.people_mapper.ClaudeWebResearcher')
    @patch('src.layer5.people_mapper.invoke_unified_sync')
    @patch('src.layer5.people_mapper.PeopleMapper._generate_outreach_package')
    def test_node_handles_none_company_research(self, mock_outreach, mock_invoke, mock_claude_researcher, state_with_none_company_research):
        """Test that node function handles None company_research."""
        # Mock ClaudeWebResearcher
        mock_researcher = MagicMock()
        mock_claude_researcher.return_value = mock_researcher

        # Mock LLM
        # mock_invoke is patched at function level

        mock_outreach.return_value = {
            "contact_name": "Test Contact",
            "contact_role": "Engineer",
            "linkedin_url": "https://linkedin.com/in/test",
            "linkedin_message": "Test message",
            "email_subject": "Test Subject",
            "email_body": "Test body",
            "why_relevant": "Test relevance",
            "recent_signals": [],
            "reasoning": "Test"
        }

        result = people_mapper_node(state_with_none_company_research)

        # Should not crash
        assert "primary_contacts" in result
        # With proper mocks, should not have errors
        assert len(result.get("errors", [])) == 0
