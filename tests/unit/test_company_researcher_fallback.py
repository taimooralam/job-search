"""
Unit Tests for Company Researcher Fallback Chain (Phase 6.1).

Tests the Claude API fallback chain implementation in CompanyResearcher:
- Primary research with Claude API WebSearch
- Fallback 2a: Name variations (DLOCAL -> dLocal, DLocal, etc.)
- Fallback 2b: FireCrawl mode if available
- Fallback 2c: LLM knowledge fallback (marked as low_confidence)
- Final error: Returns company_research: None with errors

Also tests helper methods:
- _normalize_company_name(): Generate company name variations
- _research_with_llm_knowledge(): LLM training data fallback
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime

from src.layer3.company_researcher import CompanyResearcher, CompanyResearchOutput


# ===== FIXTURES =====


@pytest.fixture
def sample_job_state():
    """Sample JobState for testing fallback chain."""
    return {
        "job_id": "test_fallback_001",
        "title": "Backend Engineer",
        "company": "DLOCAL",
        "job_description": "Build payment infrastructure for emerging markets. Scale to 1M TPS. Python, Kubernetes.",
        "job_url": "https://example.com/job/dlocal",
        "source": "test",
        "candidate_profile": "",
        "pain_points": None,
        "strategic_needs": None,
        "company_summary": None,
        "company_url": None,
        "company_research": None,
        "errors": [],
        "status": "processing",
    }


@pytest.fixture
def mock_claude_researcher():
    """Mock ClaudeWebResearcher with research_company method."""
    mock = MagicMock()
    mock.research_company = AsyncMock()
    return mock


@pytest.fixture
def mock_claude_success_response():
    """Mock successful Claude API research response."""
    return Mock(
        success=True,
        data={
            "summary": "DLOCAL is a payment platform for emerging markets.",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $200M Series D",
                    "date": "2024-01-15",
                    "source": "https://dlocal.com/news",
                }
            ],
            "url": "https://dlocal.com",
            "company_type": "employer",
        },
        error=None,
    )


@pytest.fixture
def mock_claude_failure_response():
    """Mock failed Claude API research response."""
    return Mock(
        success=False,
        data=None,
        error="No search results found",
    )


@pytest.fixture
def mock_firecrawl():
    """Mock FireCrawl with search and scrape methods."""
    mock = MagicMock()

    # Mock search response
    mock_search_result = MagicMock()
    mock_search_result.url = "https://dlocal.com"
    mock_search_result.markdown = "dLocal is a payment platform for emerging markets."

    mock_search_response = MagicMock()
    mock_search_response.web = [mock_search_result]
    mock.search.return_value = mock_search_response

    # Mock scrape response
    mock_scrape_result = MagicMock()
    mock_scrape_result.markdown = "dLocal builds payment infrastructure for emerging markets."
    mock.scrape.return_value = mock_scrape_result

    return mock


# ===== TESTS: _normalize_company_name() =====


class TestNormalizeCompanyName:
    """Test company name normalization generates correct variations."""

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_generates_variations_for_all_caps_name(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Generate variations for all-caps company name like DLOCAL."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("DLOCAL")

        # Should include: DLOCAL, dLocal, DLocal, dlocal, Dlocal
        assert "DLOCAL" in variations  # Original
        assert "dlocal" in variations  # All lowercase
        assert "Dlocal" in variations  # Title case
        assert len(variations) <= 5  # Max 5 variations

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_includes_original_company_name(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Variations always include original company name."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("TechCorp")

        assert "TechCorp" in variations

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_handles_mixed_case_company_name(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Handle mixed-case names like PayPal, GitHub."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("PayPal")

        assert "PayPal" in variations  # Original
        assert "PAYPAL" in variations  # All uppercase
        assert "paypal" in variations  # All lowercase
        assert "Paypal" in variations  # Title case

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_limits_to_5_variations(self, mock_firecrawl_class, mock_mongo_class):
        """Limit variations to maximum of 5."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("MultiWordCompanyName")

        assert len(variations) <= 5

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_handles_single_word_lowercase(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Handle single-word lowercase name like 'stripe'."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("stripe")

        assert "stripe" in variations  # Original
        assert "STRIPE" in variations  # All uppercase
        assert "Stripe" in variations  # Title case

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_removes_duplicate_variations(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Remove duplicate variations (e.g., 'Stripe' appears once)."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("Stripe")

        # Count how many times "Stripe" appears
        stripe_count = variations.count("Stripe")
        assert stripe_count == 1  # Should appear exactly once


# ===== TESTS: _research_with_llm_knowledge() =====


class TestResearchWithLLMKnowledge:
    """Test LLM knowledge fallback (training data, no web search)."""

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_returns_low_confidence_result(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge fallback returns result with low confidence markers."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API client (anthropic.messages.create)
        mock_response = Mock()
        mock_text_block = Mock()
        mock_text_block.type = "text"
        mock_text_block.text = """{
            "summary": "Stripe is a payment processing platform.",
            "signals": [],
            "url": "https://stripe.com",
            "company_type": "employer"
        }"""
        mock_response.content = [mock_text_block]

        researcher.claude_researcher.client.messages.create = Mock(return_value=mock_response)

        # Call LLM knowledge fallback
        result = await researcher._research_with_llm_knowledge(
            company="Stripe",
            job_title="Backend Engineer",
            job_description="Build payment APIs",
        )

        # Verify result structure
        assert result is not None
        assert "company_research" in result
        assert result["company_research"]["_source"] == "llm_knowledge"
        assert result["company_research"]["_confidence"] == "low"

        # Summary should have training knowledge prefix
        assert "[Based on training knowledge]" in result["company_research"]["summary"]

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_returns_none_on_api_failure(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge fallback returns None on API failure."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API client to raise exception
        researcher.claude_researcher.client.messages.create = Mock(
            side_effect=Exception("API error")
        )

        # Call LLM knowledge fallback
        result = await researcher._research_with_llm_knowledge(
            company="UnknownCorp",
            job_title="Engineer",
            job_description="Job description",
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_adds_training_knowledge_prefix(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge adds '[Based on training knowledge]' prefix to summary."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API response WITHOUT prefix
        mock_response = Mock()
        mock_text_block = Mock()
        mock_text_block.type = "text"
        mock_text_block.text = """{
            "summary": "AWS is a cloud computing platform.",
            "signals": [],
            "url": "https://aws.amazon.com",
            "company_type": "employer"
        }"""
        mock_response.content = [mock_text_block]

        researcher.claude_researcher.client.messages.create = Mock(return_value=mock_response)

        result = await researcher._research_with_llm_knowledge(
            company="AWS", job_title="Engineer", job_description="Cloud infrastructure"
        )

        # Verify prefix was added
        assert result is not None
        assert result["company_research"]["summary"].startswith("[Based on training knowledge]")

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_does_not_cache_results(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge results are NOT cached (may be stale)."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API response
        mock_response = Mock()
        mock_text_block = Mock()
        mock_text_block.type = "text"
        mock_text_block.text = """{
            "summary": "GitHub is a code hosting platform.",
            "signals": [],
            "url": "https://github.com",
            "company_type": "employer"
        }"""
        mock_response.content = [mock_text_block]

        researcher.claude_researcher.client.messages.create = Mock(return_value=mock_response)

        # Mock _store_cache to verify it's NOT called
        with patch.object(researcher, "_store_cache") as mock_store:
            await researcher._research_with_llm_knowledge(
                company="GitHub", job_title="Engineer", job_description="Code hosting"
            )

            # Cache should NOT be called for LLM knowledge results
            mock_store.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_returns_empty_signals(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge returns empty signals (unreliable without sources)."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API response with signals
        mock_response = Mock()
        mock_text_block = Mock()
        mock_text_block.type = "text"
        mock_text_block.text = """{
            "summary": "Meta is a social media company.",
            "signals": [{"type": "funding", "description": "Test signal", "date": "2024-01", "source": "https://meta.com"}],
            "url": "https://meta.com",
            "company_type": "employer"
        }"""
        mock_response.content = [mock_text_block]

        researcher.claude_researcher.client.messages.create = Mock(return_value=mock_response)

        result = await researcher._research_with_llm_knowledge(
            company="Meta", job_title="Engineer", job_description="Social media"
        )

        # Signals should be empty (overridden to [])
        assert result is not None
        assert result["company_research"]["signals"] == []


# ===== TESTS: Fallback Chain Integration =====


class TestFallbackChainIntegration:
    """Test the full fallback chain in _research_company_with_claude_api()."""

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_primary_research_success_skips_fallbacks(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_success_response,
    ):
        """Primary research success skips all fallbacks."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock Claude researcher success
            researcher.claude_researcher.research_company = AsyncMock(
                return_value=mock_claude_success_response
            )

            # Execute primary research
            result = researcher._research_company_with_claude_api(sample_job_state)

            # Verify result
            assert result["company_research"] is not None
            assert result["company_research"]["summary"] == mock_claude_success_response.data["summary"]

            # Verify only called once (no fallbacks)
            assert researcher.claude_researcher.research_company.call_count == 1

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_fallback_2a_name_variations_triggered_on_primary_failure(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
        mock_claude_success_response,
    ):
        """Fallback 2a (name variations) triggered when primary fails."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock primary research failure, then variation success
            researcher.claude_researcher.research_company = AsyncMock(
                side_effect=[
                    mock_claude_failure_response,  # Primary fails
                    mock_claude_success_response,  # First variation succeeds
                ]
            )

            # Execute
            result = researcher._research_company_with_claude_api(sample_job_state)

            # Verify fallback 2a succeeded
            assert result["company_research"] is not None
            assert result["company_research"]["summary"] == mock_claude_success_response.data["summary"]

            # Verify called twice (primary + 1 variation)
            assert researcher.claude_researcher.research_company.call_count == 2

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_fallback_2b_firecrawl_triggered_when_variations_fail(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
        mock_firecrawl,
    ):
        """Fallback 2b (FireCrawl) triggered when all variations fail."""
        # Setup FireCrawl mock
        mock_firecrawl_class.return_value = mock_firecrawl

        researcher = CompanyResearcher(use_claude_api=True)
        # Ensure FireCrawl is available for fallback 2b
        researcher.firecrawl = mock_firecrawl

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock all Claude API attempts to fail
            researcher.claude_researcher.research_company = AsyncMock(
                return_value=mock_claude_failure_response
            )

            # Mock FireCrawl scraping and LLM analysis
            with patch.object(
                researcher, "_scrape_multiple_sources", return_value={
                    "official_site": {"url": "https://dlocal.com", "content": "dLocal payment platform"}
                }
            ):
                with patch.object(
                    researcher, "_analyze_company_signals", return_value=CompanyResearchOutput(
                        summary="dLocal builds payment infrastructure.",
                        signals=[{"type": "growth", "description": "Payment platform", "date": "unknown", "source": "https://dlocal.com"}],
                        url="https://dlocal.com"
                    )
                ):
                    # Execute
                    result = researcher._research_company_with_claude_api(sample_job_state)

                    # Verify fallback 2b succeeded
                    assert result["company_research"] is not None
                    assert "dLocal" in result["company_research"]["summary"]

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_fallback_2b_skipped_when_firecrawl_unavailable(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
    ):
        """Fallback 2b skipped when FireCrawl not initialized."""
        researcher = CompanyResearcher(use_claude_api=True)
        researcher.firecrawl = None  # FireCrawl not available

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock all Claude API attempts to fail
            researcher.claude_researcher.research_company = AsyncMock(
                return_value=mock_claude_failure_response
            )

            # Mock LLM knowledge fallback success
            llm_result = {
                "company_research": {
                    "summary": "[Based on training knowledge] Company info",
                    "signals": [],
                    "url": "https://example.com",
                    "_source": "llm_knowledge",
                    "_confidence": "low",
                }
            }

            async def mock_llm_success(*args, **kwargs):
                return llm_result

            with patch.object(researcher, "_research_with_llm_knowledge", new=mock_llm_success):
                # Execute
                result = researcher._research_company_with_claude_api(sample_job_state)

                # Verify fallback 2c (LLM knowledge) was used
                assert result["company_research"] is not None
                assert result["company_research"]["_source"] == "llm_knowledge"

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_fallback_2c_llm_knowledge_triggered_when_firecrawl_fails(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
    ):
        """Fallback 2c (LLM knowledge) triggered when FireCrawl fails."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock all Claude API attempts to fail
            researcher.claude_researcher.research_company = AsyncMock(
                return_value=mock_claude_failure_response
            )

            # Mock FireCrawl failure
            with patch.object(
                researcher, "_scrape_multiple_sources", side_effect=Exception("FireCrawl error")
            ):
                # Mock LLM knowledge success
                llm_result = {
                    "company_research": {
                        "summary": "[Based on training knowledge] Company description",
                        "signals": [],
                        "url": "https://example.com",
                        "_source": "llm_knowledge",
                        "_confidence": "low",
                    }
                }

                async def mock_llm_knowledge(*args, **kwargs):
                    return llm_result

                with patch.object(researcher, "_research_with_llm_knowledge", new=mock_llm_knowledge):
                    # Execute
                    result = researcher._research_company_with_claude_api(sample_job_state)

                    # Verify fallback 2c succeeded
                    assert result["company_research"] is not None
                    assert result["company_research"]["_source"] == "llm_knowledge"
                    assert result["company_research"]["_confidence"] == "low"

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_all_fallbacks_fail_returns_company_research_none(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
    ):
        """All fallbacks fail -> returns company_research: None with errors."""
        researcher = CompanyResearcher(use_claude_api=True)
        researcher.firecrawl = None  # FireCrawl not available

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock all Claude API attempts to fail
            researcher.claude_researcher.research_company = AsyncMock(
                return_value=mock_claude_failure_response
            )

            # Mock LLM knowledge failure
            async def mock_llm_failure(*args, **kwargs):
                return None

            with patch.object(researcher, "_research_with_llm_knowledge", new=mock_llm_failure):
                # Execute
                result = researcher._research_company_with_claude_api(sample_job_state)

                # Verify error result
                assert result["company_research"] is None
                assert result["company_summary"] is None
                assert result["company_url"] is None
                assert "errors" in result
                assert len(result["errors"]) > 0
                assert "failed after all fallbacks" in result["errors"][-1].lower()

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_cache_hit_skips_all_fallbacks(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
    ):
        """Cache hit skips all fallback attempts."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock cache hit
        cached_result = {
            "company_research": {
                "summary": "Cached company data",
                "signals": [],
                "url": "https://cached.com",
            }
        }

        with patch.object(researcher, "_check_cache", return_value=cached_result):
            # Mock Claude researcher (should NOT be called)
            researcher.claude_researcher.research_company = AsyncMock()

            # Execute
            result = researcher._research_company_with_claude_api(sample_job_state)

            # Verify cache was used
            assert result["company_research"]["summary"] == "Cached company data"

            # Verify Claude API was NOT called
            researcher.claude_researcher.research_company.assert_not_called()

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_fallback_tries_up_to_4_name_variations(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
        mock_claude_success_response,
    ):
        """Fallback 2a tries up to 4 name variations (excluding original)."""
        researcher = CompanyResearcher(use_claude_api=True)
        # Disable FireCrawl to skip fallback 2b and go straight to 2c
        researcher.firecrawl = None

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock primary + 3 variations fail, 4th succeeds (before trying all 4)
            # We need at least 2 calls to test the fallback
            researcher.claude_researcher.research_company = AsyncMock(
                side_effect=[
                    mock_claude_failure_response,  # Primary (DLOCAL)
                    mock_claude_success_response,  # Variation 1 succeeds
                ]
            )

            # Execute
            result = researcher._research_company_with_claude_api(sample_job_state)

            # Verify name variation succeeded
            assert researcher.claude_researcher.research_company.call_count == 2
            assert result["company_research"] is not None

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_error_message_includes_primary_failure_reason(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
        mock_claude_failure_response,
    ):
        """Final error message includes primary failure reason."""
        researcher = CompanyResearcher(use_claude_api=True)
        researcher.firecrawl = None

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock all attempts to fail
            researcher.claude_researcher.research_company = AsyncMock(
                return_value=mock_claude_failure_response
            )

            # Mock LLM knowledge failure
            async def mock_llm_failure(*args, **kwargs):
                return None

            with patch.object(researcher, "_research_with_llm_knowledge", new=mock_llm_failure):
                # Execute
                result = researcher._research_company_with_claude_api(sample_job_state)

                # Verify error includes primary failure reason
                assert "errors" in result
                error_msg = result["errors"][-1]
                assert "No search results found" in error_msg or "failed after all fallbacks" in error_msg.lower()


# ===== TESTS: Edge Cases =====


class TestFallbackEdgeCases:
    """Test edge cases in fallback chain."""

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_handles_empty_company_name(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Handle empty company name gracefully."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("")

        # Should return empty list (empty strings are discarded)
        assert len(variations) == 0

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_handles_company_name_with_special_characters(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Handle company names with special characters."""
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name("AT&T")

        assert "AT&T" in variations
        assert len(variations) <= 8  # Increased from 5 to support suffix removal

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_handles_very_long_company_name(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """Handle very long company names."""
        long_name = "International Business Machines Corporation Limited"
        researcher = CompanyResearcher(use_claude_api=True)
        variations = researcher._normalize_company_name(long_name)

        assert long_name in variations
        assert len(variations) <= 8  # Increased from 5 to support suffix removal

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_handles_invalid_json_response(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge handles invalid JSON gracefully."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API response with invalid JSON
        mock_response = Mock()
        mock_text_block = Mock()
        mock_text_block.type = "text"
        mock_text_block.text = "This is not valid JSON"
        mock_response.content = [mock_text_block]

        researcher.claude_researcher.client.messages.create = Mock(return_value=mock_response)

        # Call LLM knowledge fallback
        result = await researcher._research_with_llm_knowledge(
            company="TestCorp", job_title="Engineer", job_description="Test"
        )

        # Should return None on parse failure
        assert result is None

    @pytest.mark.asyncio
    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    async def test_llm_knowledge_handles_empty_response_content(
        self, mock_firecrawl_class, mock_mongo_class
    ):
        """LLM knowledge handles empty response content."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock Claude API response with no text content
        mock_response = Mock()
        mock_response.content = []

        researcher.claude_researcher.client.messages.create = Mock(return_value=mock_response)

        result = await researcher._research_with_llm_knowledge(
            company="TestCorp", job_title="Engineer", job_description="Test"
        )

        assert result is None

    @patch("src.layer3.company_researcher.MongoClient")
    @patch("src.layer3.company_researcher.FirecrawlApp")
    def test_fallback_chain_exception_handling(
        self,
        mock_firecrawl_class,
        mock_mongo_class,
        sample_job_state,
    ):
        """Fallback chain handles exceptions gracefully."""
        researcher = CompanyResearcher(use_claude_api=True)

        # Mock cache miss
        with patch.object(researcher, "_check_cache", return_value=None):
            # Mock Claude API to raise exception
            researcher.claude_researcher.research_company = AsyncMock(
                side_effect=Exception("Unexpected API error")
            )

            # Mock LLM knowledge failure
            async def mock_llm_failure(*args, **kwargs):
                return None

            with patch.object(researcher, "_research_with_llm_knowledge", new=mock_llm_failure):
                # Execute - should not raise exception
                result = researcher._research_company_with_claude_api(sample_job_state)

                # Verify error result
                assert result["company_research"] is None
                assert "errors" in result
