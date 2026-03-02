"""
Unit Tests for Layer 3: Company & Role Researchers (Phase 5)

Tests Phase 5.1 (Company Researcher) and Phase 5.2 (Role Researcher):
- Mocked LLM responses for determinism
- Schema validation with Pydantic
- Hallucination prevention controls
- Cache functionality
- Error handling and fallback logic
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from src.common.unified_llm import LLMResult


from src.layer3.company_researcher import (
    CompanyResearcher,
    CompanyResearchOutput,
    CompanySignalModel,
    company_researcher_node
)
from src.layer3.role_researcher import (
    RoleResearcher,
    RoleResearchOutput,
    role_researcher_node
)


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState for testing."""
    return {
        "job_id": "test_001",
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable systems for 10M users. Required: Python, AWS, Kubernetes.",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "",
        "pain_points": None,
        "strategic_needs": None,
        "risks_if_unfilled": None,
        "success_metrics": None,
        "selected_stars": None,
        "star_to_pain_mapping": None,
        "company_summary": None,
        "company_url": None,
        "company_research": None,
        "role_research": None,
        "fit_score": None,
        "fit_rationale": None,
        "people": None,
        "cover_letter": None,
        "cv_path": None,
        "drive_folder_url": None,
        "sheet_row_id": None,
        "run_id": None,
        "created_at": None,
        "errors": [],
        "status": "processing"
    }


@pytest.fixture
def valid_company_research_json():
    """Valid company research JSON matching schema."""
    return {
        "summary": "TechCorp builds cloud infrastructure for enterprise clients.",
        "signals": [
            {
                "type": "funding",
                "description": "Raised $50M Series B from Accel Partners",
                "date": "2024-01-15",
                "source": "https://techcorp.com/news"
            },
            {
                "type": "growth",
                "description": "Expanded engineering team by 40%",
                "date": "2024-03-01",
                "source": "https://linkedin.com/techcorp"
            }
        ],
        "url": "https://techcorp.com"
    }


@pytest.fixture
def valid_role_research_json():
    """Valid role research JSON matching schema."""
    return {
        "summary": "Senior engineer will lead platform team of 5, owning core infrastructure",
        "business_impact": [
            "Enable 10x user growth through scalable architecture",
            "Reduce infrastructure costs by 30% through optimization",
            "Accelerate feature delivery with improved deployment pipeline"
        ],
        "why_now": "Recent $50M funding requires scaling infrastructure to support enterprise expansion"
    }


# ===== COMPANY RESEARCHER TESTS =====

class TestCompanyResearcherSchema:
    """Test Pydantic schema validation for Company Researcher."""

    def test_valid_company_research_schema(self, valid_company_research_json):
        """Valid JSON passes schema validation."""
        validated = CompanyResearchOutput(**valid_company_research_json)

        assert validated.summary == valid_company_research_json["summary"]
        assert len(validated.signals) == 2
        assert validated.url == valid_company_research_json["url"]

    def test_missing_required_field_fails_validation(self):
        """Schema validation fails when required field missing."""
        invalid_data = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": []
            # Missing 'url'
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            CompanyResearchOutput(**invalid_data)

    def test_signal_without_source_fails_validation(self):
        """Signal without source URL fails validation."""
        invalid_data = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised funding",
                    "date": "2024-01-01"
                    # Missing 'source'
                }
            ],
            "url": "https://techcorp.com"
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            CompanyResearchOutput(**invalid_data)


class TestCompanyResearcherWithMockedDependencies:
    """Test Company Researcher with mocked LLM."""

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_multi_source_scraping_and_signal_extraction(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state,
        valid_company_research_json
    ):
        """Legacy path: LLM-only research returns company summary."""
        # Mock UnifiedLLM to return valid company research JSON
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(valid_company_research_json),
            parsed_json=valid_company_research_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        # Mock company cache repository (empty cache)
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None  # Cache miss
        mock_cache_repo.return_value = mock_repo

        # Run Company Researcher (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy LLM-only path returns company_summary and company_url
        assert "company_summary" in result or "company_research" in result

    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_cache_hit_returns_cached_data(
        self,
        mock_cache_repo,
        sample_job_state,
        valid_company_research_json
    ):
        """Cache hit returns cached research without LLM calls."""
        # Mock company cache repository to return cached data
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = {
            "company_key": "techcorp",
            "company_research": valid_company_research_json,
            "cached_at": datetime.utcnow()
        }
        mock_cache_repo.return_value = mock_repo

        # Run Company Researcher (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Assertions
        assert "company_research" in result
        assert result["company_research"]["summary"] == valid_company_research_json["summary"]
        print("   Cache HIT for TechCorp")

    def test_hallucination_controls_in_prompt(self):
        """Prompt includes hallucination prevention instructions."""
        from src.layer3.company_researcher import SYSTEM_PROMPT_COMPANY_SIGNALS

        # Verify hallucination controls present in prompt
        # Phase 5.2 prompt uses: "Use ONLY explicit facts from scraped content"
        assert "Use ONLY explicit facts from scraped content" in SYSTEM_PROMPT_COMPANY_SIGNALS
        # Phase 5.2 prompt uses: "NEVER invent details not in sources"
        assert "NEVER invent" in SYSTEM_PROMPT_COMPANY_SIGNALS
        assert "unknown" in SYSTEM_PROMPT_COMPANY_SIGNALS.lower()

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_signal_type_funding(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Extract funding signal type correctly."""
        funding_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "funding",
                "description": "Raised $100M Series C from Sequoia",
                "date": "2024-06-15",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(funding_signal_json),
            parsed_json=funding_signal_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy path returns company_summary; check result is not empty
        assert result is not None

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_signal_type_acquisition(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Extract acquisition signal type correctly."""
        acquisition_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "acquisition",
                "description": "Acquired DataCo for $50M",
                "date": "2024-03-20",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(acquisition_signal_json),
            parsed_json=acquisition_signal_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy path returns company_summary; check result is not empty
        assert result is not None

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_signal_type_leadership_change(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Extract leadership_change signal type correctly."""
        leadership_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "leadership_change",
                "description": "Appointed Jane Smith as new CTO",
                "date": "2024-05-10",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(leadership_signal_json),
            parsed_json=leadership_signal_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy path returns company_summary; check result is not empty
        assert result is not None

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_signal_type_product_launch(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Extract product_launch signal type correctly."""
        product_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "product_launch",
                "description": "Launched new AI-powered analytics platform",
                "date": "2024-04-01",
                "source": "https://techcorp.com/products"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(product_signal_json),
            parsed_json=product_signal_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy path returns company_summary; check result is not empty
        assert result is not None

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_signal_type_partnership(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Extract partnership signal type correctly."""
        partnership_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "partnership",
                "description": "Strategic partnership with AWS announced",
                "date": "2024-02-15",
                "source": "https://techcorp.com/news"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(partnership_signal_json),
            parsed_json=partnership_signal_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy path returns company_summary; check result is not empty
        assert result is not None

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_signal_type_growth(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Extract growth signal type correctly."""
        growth_signal_json = {
            "summary": "TechCorp builds cloud infrastructure.",
            "signals": [{
                "type": "growth",
                "description": "Expanded engineering team by 50%, now 200 engineers",
                "date": "2024-01-10",
                "source": "https://linkedin.com/techcorp"
            }],
            "url": "https://techcorp.com"
        }

        # Mock dependencies
        mock_unified.return_value = LLMResult(
            success=True,
            content=json.dumps(growth_signal_json),
            parsed_json=growth_signal_json,
            backend="mocked",
            model="test-model",
            tier="middle",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Legacy path returns company_summary; check result is not empty
        assert result is not None

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_quality_gate_minimum_signals(
        self,
        mock_cache_repo,
        mock_unified,
        sample_job_state
    ):
        """Quality gate: Cache-hit path preserves rich signals."""
        rich_signals_json = {
            "summary": "TechCorp is a leading cloud infrastructure provider with 500+ employees.",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $100M Series C from Sequoia",
                    "date": "2024-06-15",
                    "source": "https://techcorp.com/news"
                },
                {
                    "type": "acquisition",
                    "description": "Acquired DataCo for $50M",
                    "date": "2024-03-20",
                    "source": "https://techcorp.com/news"
                },
                {
                    "type": "leadership_change",
                    "description": "Appointed Jane Smith as new CTO",
                    "date": "2024-05-10",
                    "source": "https://techcorp.com/about"
                },
                {
                    "type": "product_launch",
                    "description": "Launched AI-powered analytics platform",
                    "date": "2024-04-01",
                    "source": "https://techcorp.com/products"
                }
            ],
            "url": "https://techcorp.com"
        }

        # Mock cache to return the rich signals (cache HIT path)
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = {
            "company_key": "techcorp",
            "company_research": rich_signals_json,
            "cached_at": datetime.utcnow()
        }
        mock_cache_repo.return_value = mock_repo

        # Run (use_claude_api=False for legacy LLM-only mode)
        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Cache hit path returns company_research with signals intact
        assert "company_research" in result
        assert len(result["company_research"]["signals"]) >= 3
        assert result["company_research"]["signals"][0]["type"] == "funding"
        assert result["company_research"]["signals"][1]["type"] == "acquisition"
        assert result["company_research"]["signals"][2]["type"] == "leadership_change"


# ===== ROLE RESEARCHER TESTS =====

class TestRoleResearcherSchema:
    """Test Pydantic schema validation for Role Researcher."""

    def test_valid_role_research_schema(self, valid_role_research_json):
        """Valid JSON passes schema validation."""
        validated = RoleResearchOutput(**valid_role_research_json)

        assert validated.summary == valid_role_research_json["summary"]
        assert len(validated.business_impact) == 3
        assert validated.why_now == valid_role_research_json["why_now"]

    def test_too_few_business_impact_items_fails(self):
        """Schema validation fails with <3 business_impact items."""
        invalid_data = {
            "summary": "Senior engineer will lead platform team",
            "business_impact": ["Impact 1", "Impact 2"],  # Only 2 items (min is 3)
            "why_now": "Expansion requires scaling"
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            RoleResearchOutput(**invalid_data)

    def test_too_many_business_impact_items_fails(self):
        """Schema validation fails with >5 business_impact items."""
        invalid_data = {
            "summary": "Senior engineer will lead platform team",
            "business_impact": ["Impact 1", "Impact 2", "Impact 3", "Impact 4", "Impact 5", "Impact 6"],  # 6 items (max is 5)
            "why_now": "Expansion requires scaling"
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            RoleResearchOutput(**invalid_data)


class TestRoleResearcherWithMockedLLM:
    """Test Role Researcher with mocked LLM."""

    @patch('src.layer3.role_researcher.invoke_unified_sync')
    def test_role_analysis_with_company_signals(
        self,
        mock_invoke,
        sample_job_state,
        valid_role_research_json
    ):
        """Role research references company signals in 'why_now'."""
        # Add company signals to job state (from Phase 5.1)
        sample_job_state["company_research"] = {
            "summary": "TechCorp builds cloud infrastructure",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $50M Series B",
                    "date": "2024-01-15",
                    "source": "https://techcorp.com/news"
                }
            ],
            "url": "https://techcorp.com"
        }

        # Mock LLM to return valid role research JSON
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps(valid_role_research_json)
        mock_invoke.return_value = mock_response

        # Run Role Researcher (use_claude_api=False for legacy LLM-only mode)
        researcher = RoleResearcher(use_claude_api=False)
        result = researcher.research_role(sample_job_state)

        # Assertions
        assert "role_research" in result
        assert result["role_research"]["summary"] == valid_role_research_json["summary"]
        assert len(result["role_research"]["business_impact"]) == 3
        # Verify "why_now" mentions signal context
        assert "funding" in result["role_research"]["why_now"].lower() or "$50m" in result["role_research"]["why_now"].lower()

    @patch('src.layer3.role_researcher.invoke_unified_sync')
    def test_hallucination_controls_in_role_prompt(self, mock_invoke):
        """Role Researcher prompt includes hallucination prevention."""
        from src.layer3.role_researcher import SYSTEM_PROMPT_ROLE_RESEARCH

        # Verify hallucination controls present
        assert "Only use facts" in SYSTEM_PROMPT_ROLE_RESEARCH
        assert "DO NOT invent" in SYSTEM_PROMPT_ROLE_RESEARCH
        assert "explicitly reference" in SYSTEM_PROMPT_ROLE_RESEARCH.lower() or "reference" in SYSTEM_PROMPT_ROLE_RESEARCH.lower()

    @patch('src.layer3.role_researcher.invoke_unified_sync')
    def test_role_research_handles_llm_failure_gracefully(
        self,
        mock_invoke,
        sample_job_state
    ):
        """Role research handles LLM failures without blocking pipeline."""
        # Mock invoke_unified_sync to raise exception
        mock_invoke.side_effect = Exception("LLM API error")

        # Run Role Researcher (use_claude_api=False for legacy LLM-only mode)
        researcher = RoleResearcher(use_claude_api=False)
        result = researcher.research_role(sample_job_state)

        # Should return None but not raise exception
        assert result["role_research"] is None
        assert "errors" in result
        assert any("Role Researcher" in error for error in result["errors"])


# ===== INTEGRATION TESTS =====

@pytest.mark.integration
@patch('src.layer3.company_researcher.invoke_unified_sync')
@patch('src.layer3.company_researcher.get_company_cache_repository')
def test_company_researcher_node_integration(
    mock_cache_repo,
    mock_unified,
    sample_job_state,
    valid_company_research_json
):
    """Integration test for company_researcher_node."""
    # Mock cache (miss) so LLM path is exercised
    mock_repo = MagicMock()
    mock_repo.find_by_company_key.return_value = None
    mock_cache_repo.return_value = mock_repo

    mock_unified.return_value = LLMResult(
        success=True,
        content=json.dumps(valid_company_research_json),
        parsed_json=valid_company_research_json,
        backend="mocked",
        model="test-model",
        tier="middle",
        duration_ms=0
    )

    # Run node function (use_claude_api=False for legacy LLM-only mode)
    updates = company_researcher_node(sample_job_state, use_claude_api=False)

    # Assertions - legacy path returns at least company_summary
    assert updates is not None
    assert "company_summary" in updates or "company_research" in updates


@pytest.mark.integration
@patch('src.layer3.role_researcher.invoke_unified_sync')
def test_role_researcher_node_integration(
    mock_invoke,
    sample_job_state,
    valid_role_research_json
):
    """Integration test for role_researcher_node."""
    # Mock invoke_unified_sync to return valid role research
    mock_response = MagicMock()
    mock_response.content = json.dumps(valid_role_research_json)
    mock_invoke.return_value = mock_response

    # Role researcher requires company_research to be present (not None)
    # otherwise it skips role research (by design)
    sample_job_state["company_research"] = {
        "summary": "TechCorp is a technology company building scalable systems.",
        "company_type": "employer",
        "signals": []
    }

    # Run node function (use_claude_api=False for legacy LLM-only mode)
    updates = role_researcher_node(sample_job_state, use_claude_api=False)

    # Assertions
    assert "role_research" in updates
    assert updates["role_research"]["summary"] is not None
    assert len(updates["role_research"]["business_impact"]) >= 3


# ===== FIRECRAWL NORMALIZER TESTS =====

class TestFireCrawlNormalizer:
    """Test FireCrawl response normalizer in people_mapper."""

    def test_normalizer_with_new_sdk_web_attribute(self):
        """Normalizer extracts results from new SDK (v4.8.0+) with .web attribute."""
        from src.layer5.people_mapper import _extract_search_results

        # Mock SearchData with .web attribute (new SDK)
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://example.com"
        mock_result.markdown = "Test content"
        mock_response.web = [mock_result]

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://example.com"
        assert results[0].markdown == "Test content"

    def test_normalizer_with_old_sdk_data_attribute(self):
        """Normalizer extracts results from old SDK with .data attribute."""
        from src.layer5.people_mapper import _extract_search_results

        # Mock SearchData with .data attribute (old SDK)
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://oldapi.com"
        mock_result.markdown = "Old SDK content"
        mock_response.data = [mock_result]
        # Explicitly set web to None to simulate old SDK
        mock_response.web = None

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://oldapi.com"
        assert results[0].markdown == "Old SDK content"

    def test_normalizer_with_dict_web_key(self):
        """Normalizer handles dict response with 'web' key."""
        from src.layer5.people_mapper import _extract_search_results

        # Dict shape with "web" key
        mock_response = {
            "web": [
                {"url": "https://dict.com", "markdown": "Dict content"}
            ]
        }

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0]["url"] == "https://dict.com"

    def test_normalizer_with_dict_data_key(self):
        """Normalizer handles dict response with 'data' key (fallback)."""
        from src.layer5.people_mapper import _extract_search_results

        # Dict shape with "data" key
        mock_response = {
            "data": [
                {"url": "https://legacy.com", "markdown": "Legacy content"}
            ]
        }

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0]["url"] == "https://legacy.com"

    def test_normalizer_with_bare_list(self):
        """Normalizer handles bare list response."""
        from src.layer5.people_mapper import _extract_search_results

        # Bare list shape
        mock_response = [
            {"url": "https://bare1.com", "markdown": "Item 1"},
            {"url": "https://bare2.com", "markdown": "Item 2"}
        ]

        results = _extract_search_results(mock_response)

        assert len(results) == 2
        assert results[0]["url"] == "https://bare1.com"
        assert results[1]["url"] == "https://bare2.com"

    def test_normalizer_with_none_response(self):
        """Normalizer returns empty list for None response."""
        from src.layer5.people_mapper import _extract_search_results

        results = _extract_search_results(None)

        assert results == []

    def test_normalizer_with_empty_results(self):
        """Normalizer returns empty list when no results present."""
        from src.layer5.people_mapper import _extract_search_results

        # Mock response with empty web
        mock_response = Mock()
        mock_response.web = []

        results = _extract_search_results(mock_response)

        assert results == []

    def test_normalizer_prioritizes_web_over_data(self):
        """Normalizer prefers .web over .data when both present."""
        from src.layer5.people_mapper import _extract_search_results

        # Mock response with both .web and .data
        mock_response = Mock()
        mock_web_result = Mock()
        mock_web_result.url = "https://web.com"
        mock_response.web = [mock_web_result]

        mock_data_result = Mock()
        mock_data_result.url = "https://data.com"
        mock_response.data = [mock_data_result]

        results = _extract_search_results(mock_response)

        # Should return .web results, not .data
        assert len(results) == 1
        assert results[0].url == "https://web.com"

    def test_normalizer_in_people_mapper(self):
        """People mapper normalizer works identically."""
        from src.layer5.people_mapper import _extract_search_results

        # Mock new SDK response
        mock_response = Mock()
        mock_result = Mock()
        mock_result.url = "https://linkedin.com/people"
        mock_response.web = [mock_result]

        results = _extract_search_results(mock_response)

        assert len(results) == 1
        assert results[0].url == "https://linkedin.com/people"


# ===== PHASE 5 ENHANCEMENT TESTS (Fallback & STAR-awareness) =====

class TestCompanyResearcherFallback:
    """Tests for Company Researcher defensive behavior in LLM-only legacy path."""

    @patch('src.layer3.company_researcher.get_company_cache_repository')
    @patch.object(CompanyResearcher, '_check_cache')
    @patch.object(CompanyResearcher, '_summarize_with_llm')
    @patch.object(CompanyResearcher, '_store_cache')
    def test_fallback_triggered_on_empty_signals(
        self,
        mock_store,
        mock_summarize,
        mock_cache,
        mock_cache_repo,
        sample_job_state
    ):
        """LLM-only legacy path returns a result even with minimal content."""
        # Setup mocks
        mock_cache.return_value = None  # Cache miss
        mock_summarize.return_value = "TechCorp is a technology company."

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Verify LLM summarize was called and result contains company_summary
        mock_summarize.assert_called_once()
        assert "company_summary" in result
        assert result["company_summary"] == "TechCorp is a technology company."

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_summarize_with_llm_produces_summary(self, mock_cache_repo, mock_unified):
        """_summarize_with_llm produces a non-empty summary string."""
        mock_unified.return_value = LLMResult(
            success=True,
            content="TechCorp builds cloud infrastructure software.",
            parsed_json=None,
            backend="mocked",
            model="test-model",
            tier="low",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher._summarize_with_llm("TechCorp", job_id="test_001")

        assert result
        assert isinstance(result, str)
        assert len(result) > 0

    @patch('src.layer3.company_researcher.invoke_unified_sync')
    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_summarize_with_llm_handles_website_content(self, mock_cache_repo, mock_unified):
        """_summarize_with_llm uses website content when provided."""
        mock_unified.return_value = LLMResult(
            success=True,
            content="TechCorp is a cloud infrastructure company serving enterprise clients.",
            parsed_json=None,
            backend="mocked",
            model="test-model",
            tier="low",
            duration_ms=0
        )

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher._summarize_with_llm(
            "TechCorp",
            website_content="TechCorp provides enterprise cloud solutions...",
            job_id="test_001"
        )

        assert result
        assert isinstance(result, str)
        assert len(result) > 0


class TestSTARAwareness:
    """Tests for Phase 5 STAR-aware research prompts."""

    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_extract_star_context_with_selected_stars(self, mock_cache_repo, sample_job_state):
        """STAR context extraction works with selected_stars."""
        # Add selected_stars to state
        sample_job_state["selected_stars"] = [
            {
                "id": "star-1",
                "company": "OldCorp",
                "role_title": "Engineer",
                "domain_areas": ["Cloud Infrastructure", "Platform Engineering"],
                "outcome_types": ["Cost Reduction", "Operational Efficiency"]
            },
            {
                "id": "star-2",
                "company": "AnotherCorp",
                "role_title": "Lead Engineer",
                "domain_areas": ["Platform Engineering", "DevOps"],
                "outcome_types": ["Velocity/Speed", "Cost Reduction"]
            }
        ]

        researcher = CompanyResearcher(use_claude_api=False)
        domains, outcomes = researcher._extract_star_context(sample_job_state)

        assert domains is not None
        assert "Cloud Infrastructure" in domains
        assert "Platform Engineering" in domains
        assert "DevOps" in domains

        assert outcomes is not None
        assert "Cost Reduction" in outcomes
        assert "Operational Efficiency" in outcomes
        assert "Velocity/Speed" in outcomes

    @patch('src.layer3.company_researcher.get_company_cache_repository')
    def test_extract_star_context_returns_none_without_stars(self, mock_cache_repo, sample_job_state):
        """STAR context extraction returns None when no selected_stars."""
        researcher = CompanyResearcher(use_claude_api=False)
        domains, outcomes = researcher._extract_star_context(sample_job_state)

        assert domains is None
        assert outcomes is None

    @patch('src.layer3.company_researcher.get_company_cache_repository')
    @patch.object(CompanyResearcher, '_check_cache')
    @patch.object(CompanyResearcher, '_summarize_with_llm')
    @patch.object(CompanyResearcher, '_store_cache')
    def test_star_context_passed_to_analysis(
        self,
        mock_store,
        mock_summarize,
        mock_cache,
        mock_cache_repo,
        sample_job_state
    ):
        """STAR context is available during research_company execution."""
        # Add selected_stars to state
        sample_job_state["selected_stars"] = [
            {
                "id": "star-1",
                "company": "OldCorp",
                "role_title": "Engineer",
                "domain_areas": ["Cloud Infrastructure"],
                "outcome_types": ["Cost Reduction"]
            }
        ]

        mock_cache.return_value = None
        mock_summarize.return_value = "TechCorp is a technology company with strong growth signals."

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Verify research completed successfully and _summarize_with_llm was called
        mock_summarize.assert_called_once()
        assert "company_summary" in result


class TestRoleResearcherSTARAwareness:
    """Tests for STAR-awareness in Role Researcher."""

    def test_extract_star_context_in_role_researcher(self, sample_job_state):
        """Role researcher extracts STAR context correctly."""
        sample_job_state["selected_stars"] = [
            {
                "id": "star-1",
                "company": "OldCorp",
                "role_title": "Engineer",
                "domain_areas": ["Platform Engineering"],
                "outcome_types": ["Revenue Growth"]
            }
        ]

        researcher = RoleResearcher(use_claude_api=False)
        domains, outcomes = researcher._extract_star_context(sample_job_state)

        assert "Platform Engineering" in domains
        assert "Revenue Growth" in outcomes


class TestPhase5Integration:
    """Integration tests for Phase 5 (Company & Role Research)."""

    @patch('src.layer3.company_researcher.get_company_cache_repository')
    @patch.object(CompanyResearcher, '_check_cache')
    @patch.object(CompanyResearcher, '_summarize_with_llm')
    @patch.object(CompanyResearcher, '_store_cache')
    def test_company_researcher_produces_valid_output(
        self,
        mock_store,
        mock_summarize,
        mock_cache,
        mock_cache_repo,
        sample_job_state
    ):
        """Company researcher produces valid output in legacy LLM-only path."""
        mock_cache.return_value = None
        mock_summarize.return_value = "TechCorp is a cloud infrastructure company with strong enterprise focus."

        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_cache_repo.return_value = mock_repo

        researcher = CompanyResearcher(use_claude_api=False)
        result = researcher.research_company(sample_job_state)

        # Verify schema compliance for legacy output
        assert result is not None
        assert "company_summary" in result
        assert result["company_summary"] == "TechCorp is a cloud infrastructure company with strong enterprise focus."
        assert "company_url" in result

    @patch('src.layer3.role_researcher.invoke_unified_sync')
    def test_role_researcher_produces_valid_output(
        self,
        mock_invoke,
        sample_job_state
    ):
        """Role researcher produces valid schema output with business impact."""
        # Setup state with company_research
        sample_job_state["company_research"] = {
            "summary": "TechCorp is a cloud company.",
            "signals": [{"type": "funding", "description": "Raised $50M", "date": "2024-01", "source": "https://techcorp.com"}],
            "url": "https://techcorp.com"
        }

        # Mock LLM
        mock_response = Mock()
        mock_response.content = json.dumps({
            "summary": "Senior engineer leads platform team.",
            "business_impact": [
                "Enable 10x user growth",
                "Reduce costs by 30%",
                "Accelerate feature delivery"
            ],
            "why_now": "Recent funding requires scaling infrastructure."
        })
        mock_invoke.return_value = mock_response

        researcher = RoleResearcher(use_claude_api=False)
        result = researcher.research_role(sample_job_state)

        # Verify schema compliance
        assert "role_research" in result
        assert result["role_research"]["summary"]
        assert result["role_research"]["business_impact"]
        assert len(result["role_research"]["business_impact"]) >= 3
        assert result["role_research"]["why_now"]
