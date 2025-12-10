"""
Unit Tests for CompanyResearchService (Phase 4).

Tests the button-triggered company research operation service:
- Service initialization and configuration
- Cache lookup (hit and miss)
- Research execution with mocked dependencies
- Error handling and result creation
- MongoDB persistence
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch, AsyncMock
from bson import ObjectId

from src.common.model_tiers import ModelTier
from src.services.company_research_service import (
    CompanyResearchService,
    COMPANY_CACHE_TTL_DAYS,
)
from src.services.operation_base import OperationResult


# ===== FIXTURES =====


@pytest.fixture
def sample_job_doc():
    """Sample MongoDB job document."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "description": "Build scalable systems for 10M users. Required: Python, AWS.",
        "url": "https://example.com/job/123",
        "source": "linkedin",
        "jd_text": "Build scalable systems for 10M users. Required: Python, AWS, Kubernetes.",
    }


@pytest.fixture
def sample_company_research():
    """Sample company research result."""
    return {
        "summary": "TechCorp builds enterprise cloud infrastructure.",
        "signals": [
            {
                "type": "funding",
                "description": "Raised $50M Series B",
                "date": "2024-01-15",
                "source": "https://techcorp.com/news",
            },
            {
                "type": "growth",
                "description": "Team grew 40%",
                "date": "2024-03-01",
                "source": "https://linkedin.com/techcorp",
            },
        ],
        "url": "https://techcorp.com",
        "company_type": "employer",
    }


@pytest.fixture
def sample_role_research():
    """Sample role research result."""
    return {
        "summary": "Senior engineer leads platform team.",
        "business_impact": [
            "Enable 10x user growth",
            "Reduce costs by 30%",
            "Accelerate feature delivery",
        ],
        "why_now": "Recent funding requires scaling infrastructure.",
    }


@pytest.fixture
def cached_research_doc(sample_company_research):
    """Cached research document from MongoDB."""
    return {
        "company_key": "techcorp",
        "company_name": "TechCorp",
        "company_research": sample_company_research,
        "cached_at": datetime.utcnow(),
    }


# ===== SERVICE INITIALIZATION TESTS =====


class TestCompanyResearchServiceInit:
    """Test service initialization."""

    def test_service_has_correct_operation_name(self):
        """Service has correct operation_name."""
        service = CompanyResearchService()
        assert service.operation_name == "research-company"

    def test_service_lazy_initializes_mongo_client(self):
        """MongoDB client is not created until accessed."""
        service = CompanyResearchService()
        assert service._mongo_client is None

    def test_service_lazy_initializes_researchers(self):
        """Researchers are not created until accessed."""
        service = CompanyResearchService()
        assert service._company_researcher is None
        assert service._role_researcher is None


# ===== CACHE TESTS =====


class TestCompanyResearchServiceCache:
    """Test cache functionality."""

    @patch.object(CompanyResearchService, "mongo_client", new_callable=lambda: MagicMock())
    def test_check_cache_returns_none_when_force_refresh(self, mock_mongo):
        """Cache check returns None when force_refresh=True."""
        service = CompanyResearchService()
        result = service._check_cache("TechCorp", force_refresh=True)
        assert result is None

    @patch.object(CompanyResearchService, "_get_cache_collection")
    def test_check_cache_returns_cached_data_when_valid(
        self, mock_get_collection, cached_research_doc
    ):
        """Cache check returns data when cache is valid."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = cached_research_doc
        mock_get_collection.return_value = mock_collection

        service = CompanyResearchService()
        result = service._check_cache("TechCorp", force_refresh=False)

        assert result is not None
        assert result["company_research"]["summary"] == cached_research_doc["company_research"]["summary"]
        mock_collection.find_one.assert_called_once_with({"company_key": "techcorp"})

    @patch.object(CompanyResearchService, "_get_cache_collection")
    def test_check_cache_returns_none_when_expired(
        self, mock_get_collection, cached_research_doc
    ):
        """Cache check returns None when cache is expired."""
        # Set cached_at to be older than TTL
        cached_research_doc["cached_at"] = datetime.utcnow() - timedelta(
            days=COMPANY_CACHE_TTL_DAYS + 1
        )

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = cached_research_doc
        mock_get_collection.return_value = mock_collection

        service = CompanyResearchService()
        result = service._check_cache("TechCorp", force_refresh=False)

        assert result is None

    @patch.object(CompanyResearchService, "_get_cache_collection")
    def test_check_cache_returns_none_when_not_found(self, mock_get_collection):
        """Cache check returns None when no cache entry exists."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_get_collection.return_value = mock_collection

        service = CompanyResearchService()
        result = service._check_cache("NewCompany", force_refresh=False)

        assert result is None


# ===== JOB STATE BUILDING TESTS =====


class TestBuildJobState:
    """Test JobState building from MongoDB document."""

    def test_build_job_state_extracts_required_fields(self, sample_job_doc):
        """JobState is built with required fields from job doc."""
        service = CompanyResearchService()
        state = service._build_job_state(sample_job_doc)

        assert state["job_id"] == str(sample_job_doc["_id"])
        assert state["title"] == sample_job_doc["title"]
        assert state["company"] == sample_job_doc["company"]
        assert state["job_url"] == sample_job_doc["url"]
        assert state["source"] == sample_job_doc["source"]

    def test_build_job_state_prefers_jd_text_over_description(self, sample_job_doc):
        """JobState prefers jd_text over description for job_description."""
        service = CompanyResearchService()
        state = service._build_job_state(sample_job_doc)

        assert state["job_description"] == sample_job_doc["jd_text"]

    def test_build_job_state_falls_back_to_description(self, sample_job_doc):
        """JobState falls back to description when jd_text missing."""
        del sample_job_doc["jd_text"]
        service = CompanyResearchService()
        state = service._build_job_state(sample_job_doc)

        assert state["job_description"] == sample_job_doc["description"]


# ===== EXECUTE TESTS =====


class TestCompanyResearchServiceExecute:
    """Test execute() method."""

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "_fetch_job")
    async def test_execute_returns_error_when_job_not_found(self, mock_fetch):
        """Execute returns error result when job not found."""
        mock_fetch.return_value = None

        service = CompanyResearchService()
        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.BALANCED,
            force_refresh=False,
        )

        assert result.success is False
        assert "Job not found" in result.error

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "_fetch_job")
    async def test_execute_returns_error_when_no_company_name(
        self, mock_fetch, sample_job_doc
    ):
        """Execute returns error when job has no company name."""
        sample_job_doc["company"] = ""
        mock_fetch.return_value = sample_job_doc

        service = CompanyResearchService()
        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.BALANCED,
        )

        assert result.success is False
        assert "no company name" in result.error.lower()

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "_fetch_job")
    @patch.object(CompanyResearchService, "_check_cache")
    async def test_execute_returns_cached_data_on_cache_hit(
        self, mock_cache, mock_fetch, sample_job_doc, sample_company_research
    ):
        """Execute returns cached data when cache hit."""
        mock_fetch.return_value = sample_job_doc
        mock_cache.return_value = {"company_research": sample_company_research}

        service = CompanyResearchService()
        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.BALANCED,
            force_refresh=False,
        )

        assert result.success is True
        assert result.data["from_cache"] is True
        assert result.data["company_research"] == sample_company_research
        assert result.cost_usd == 0.0  # No cost for cached data

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "_fetch_job")
    @patch.object(CompanyResearchService, "_check_cache")
    @patch.object(CompanyResearchService, "_persist_research")
    @patch.object(CompanyResearchService, "persist_run")
    @patch.object(CompanyResearchService, "company_researcher", new_callable=lambda: MagicMock())
    @patch.object(CompanyResearchService, "role_researcher", new_callable=lambda: MagicMock())
    async def test_execute_calls_researchers_on_cache_miss(
        self,
        mock_role_researcher,
        mock_company_researcher,
        mock_persist_run,
        mock_persist_research,
        mock_cache,
        mock_fetch,
        sample_job_doc,
        sample_company_research,
        sample_role_research,
    ):
        """Execute calls researchers when cache miss."""
        mock_fetch.return_value = sample_job_doc
        mock_cache.return_value = None  # Cache miss

        # Mock company researcher
        mock_company_researcher.research_company.return_value = {
            "company_research": sample_company_research,
            "scraped_job_posting": "Job posting content",
        }

        # Mock role researcher
        mock_role_researcher.research_role.return_value = {
            "role_research": sample_role_research,
        }

        service = CompanyResearchService()
        service._company_researcher = mock_company_researcher
        service._role_researcher = mock_role_researcher

        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.BALANCED,
            force_refresh=False,
        )

        assert result.success is True
        assert result.data["from_cache"] is False
        assert result.data["company_research"] == sample_company_research
        assert result.data["role_research"] == sample_role_research

        # Verify researchers were called
        mock_company_researcher.research_company.assert_called_once()
        mock_role_researcher.research_role.assert_called_once()

        # Verify persistence was called
        mock_persist_research.assert_called_once()
        mock_persist_run.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "_fetch_job")
    @patch.object(CompanyResearchService, "_check_cache")
    @patch.object(CompanyResearchService, "_persist_research")
    @patch.object(CompanyResearchService, "persist_run")
    @patch.object(CompanyResearchService, "company_researcher", new_callable=lambda: MagicMock())
    @patch.object(CompanyResearchService, "role_researcher", new_callable=lambda: MagicMock())
    async def test_execute_skips_role_research_for_recruitment_agency(
        self,
        mock_role_researcher,
        mock_company_researcher,
        mock_persist_run,
        mock_persist_research,
        mock_cache,
        mock_fetch,
        sample_job_doc,
    ):
        """Execute skips role research for recruitment agencies."""
        mock_fetch.return_value = sample_job_doc
        mock_cache.return_value = None

        agency_research = {
            "summary": "TechStaff is a recruitment agency.",
            "signals": [],
            "url": "https://techstaff.com",
            "company_type": "recruitment_agency",
        }

        mock_company_researcher.research_company.return_value = {
            "company_research": agency_research,
        }

        service = CompanyResearchService()
        service._company_researcher = mock_company_researcher
        service._role_researcher = mock_role_researcher

        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.BALANCED,
        )

        assert result.success is True
        assert result.data["company_type"] == "recruitment_agency"

        # Role researcher should NOT be called for agencies
        mock_role_researcher.research_role.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "_fetch_job")
    @patch.object(CompanyResearchService, "_check_cache")
    @patch.object(CompanyResearchService, "persist_run")
    @patch.object(CompanyResearchService, "company_researcher", new_callable=lambda: MagicMock())
    async def test_execute_handles_researcher_exception(
        self,
        mock_company_researcher,
        mock_persist_run,
        mock_cache,
        mock_fetch,
        sample_job_doc,
    ):
        """Execute handles exceptions from researchers gracefully."""
        mock_fetch.return_value = sample_job_doc
        mock_cache.return_value = None

        mock_company_researcher.research_company.side_effect = Exception("FireCrawl error")

        service = CompanyResearchService()
        service._company_researcher = mock_company_researcher

        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.BALANCED,
        )

        assert result.success is False
        assert "FireCrawl error" in result.error
        mock_persist_run.assert_called_once()


# ===== PERSISTENCE TESTS =====


class TestCompanyResearchServicePersistence:
    """Test MongoDB persistence."""

    @patch.object(CompanyResearchService, "_get_jobs_collection")
    def test_persist_research_updates_mongodb(
        self, mock_get_collection, sample_company_research, sample_role_research
    ):
        """Persist research updates MongoDB document."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)
        mock_get_collection.return_value = mock_collection

        service = CompanyResearchService()
        result = service._persist_research(
            job_id="507f1f77bcf86cd799439011",
            company_research=sample_company_research,
            role_research=sample_role_research,
            scraped_job_posting="Job content",
        )

        assert result is True
        mock_collection.update_one.assert_called_once()

        # Verify update document contains expected fields
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert "company_research" in update_doc
        assert "role_research" in update_doc
        assert "company_summary" in update_doc  # Legacy field
        assert "scraped_job_posting" in update_doc

    @patch.object(CompanyResearchService, "_get_jobs_collection")
    def test_persist_research_handles_exception(self, mock_get_collection):
        """Persist research handles exceptions gracefully."""
        mock_collection = MagicMock()
        mock_collection.update_one.side_effect = Exception("MongoDB error")
        mock_get_collection.return_value = mock_collection

        service = CompanyResearchService()
        result = service._persist_research(
            job_id="507f1f77bcf86cd799439011",
            company_research={"summary": "test"},
            role_research=None,
        )

        assert result is False


# ===== RESULT CREATION TESTS =====


class TestCompanyResearchServiceResults:
    """Test OperationResult creation."""

    def test_create_success_result(self, sample_company_research, sample_role_research):
        """Service creates correct success result."""
        service = CompanyResearchService()
        run_id = service.create_run_id()

        result = service.create_success_result(
            run_id=run_id,
            data={
                "company_research": sample_company_research,
                "role_research": sample_role_research,
                "from_cache": False,
            },
            cost_usd=0.05,
            duration_ms=1500,
            input_tokens=3000,
            output_tokens=2000,
            model_used="gpt-4o-mini",
        )

        assert result.success is True
        assert result.run_id == run_id
        assert result.operation == "research-company"
        assert result.data["company_research"] == sample_company_research
        assert result.cost_usd == 0.05
        assert result.model_used == "gpt-4o-mini"

    def test_create_error_result(self):
        """Service creates correct error result."""
        service = CompanyResearchService()
        run_id = service.create_run_id()

        result = service.create_error_result(
            run_id=run_id,
            error="Test error message",
            duration_ms=100,
        )

        assert result.success is False
        assert result.error == "Test error message"
        assert result.data == {}

    def test_run_id_format(self):
        """Run ID has correct format."""
        service = CompanyResearchService()
        run_id = service.create_run_id()

        assert run_id.startswith("op_research-company_")
        assert len(run_id) == len("op_research-company_") + 12


# ===== TIER COST ESTIMATION TESTS =====


class TestCompanyResearchServiceCost:
    """Test cost estimation."""

    def test_estimate_cost_fast_tier(self):
        """Fast tier has lowest cost."""
        service = CompanyResearchService()
        cost = service.estimate_cost(
            tier=ModelTier.FAST,
            input_tokens=5000,
            output_tokens=3000,
        )

        assert cost > 0
        assert cost < 0.01  # Fast tier should be very cheap

    def test_estimate_cost_quality_tier(self):
        """Quality tier has higher cost."""
        service = CompanyResearchService()
        cost_fast = service.estimate_cost(
            tier=ModelTier.FAST,
            input_tokens=5000,
            output_tokens=3000,
        )
        cost_quality = service.estimate_cost(
            tier=ModelTier.QUALITY,
            input_tokens=5000,
            output_tokens=3000,
        )

        assert cost_quality > cost_fast

    def test_get_model_returns_analytical_model(self):
        """Get model returns analytical model for research operation."""
        service = CompanyResearchService()
        model = service.get_model(ModelTier.BALANCED)

        # Research uses analytical model (gpt-4o-mini for balanced)
        assert model == "gpt-4o-mini"


# ===== INTEGRATION-LIKE TESTS (WITH MOCKS) =====


class TestCompanyResearchServiceIntegration:
    """Integration-style tests with mocked external dependencies."""

    @pytest.mark.asyncio
    @patch.object(CompanyResearchService, "mongo_client", new_callable=lambda: MagicMock())
    @patch("src.services.company_research_service.CompanyResearcher")
    @patch("src.services.company_research_service.RoleResearcher")
    async def test_full_research_flow(
        self,
        MockRoleResearcher,
        MockCompanyResearcher,
        mock_mongo,
        sample_job_doc,
        sample_company_research,
        sample_role_research,
    ):
        """Test full research flow with mocked dependencies."""
        # Setup MongoDB mocks
        mock_jobs_collection = MagicMock()
        mock_jobs_collection.find_one.return_value = sample_job_doc
        mock_jobs_collection.update_one.return_value = MagicMock(modified_count=1)

        mock_cache_collection = MagicMock()
        mock_cache_collection.find_one.return_value = None  # Cache miss

        mock_operation_runs = MagicMock()

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(
            side_effect=lambda key: {
                "level-2": mock_jobs_collection,
                "company_cache": mock_cache_collection,
                "operation_runs": mock_operation_runs,
            }.get(key, MagicMock())
        )

        mock_mongo.__getitem__ = MagicMock(return_value=mock_db)

        # Setup researcher mocks
        mock_company_researcher = MagicMock()
        mock_company_researcher.research_company.return_value = {
            "company_research": sample_company_research,
            "scraped_job_posting": "Job content",
        }
        MockCompanyResearcher.return_value = mock_company_researcher

        mock_role_researcher = MagicMock()
        mock_role_researcher.research_role.return_value = {
            "role_research": sample_role_research,
        }
        MockRoleResearcher.return_value = mock_role_researcher

        # Execute
        service = CompanyResearchService()
        service._mongo_client = mock_mongo

        result = await service.execute(
            job_id=str(sample_job_doc["_id"]),
            tier=ModelTier.BALANCED,
            force_refresh=False,
        )

        # Assertions
        assert result.success is True
        assert result.operation == "research-company"
        assert result.data["company_research"]["summary"] == sample_company_research["summary"]
        assert result.data["role_research"]["summary"] == sample_role_research["summary"]
        assert result.data["from_cache"] is False
        assert result.data["signals_count"] == 2
        assert result.cost_usd > 0
        assert result.duration_ms >= 0  # Can be 0 in fast mocked tests
