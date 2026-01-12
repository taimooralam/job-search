"""
Unit tests for JobSearchService.

Tests the core job search service with mocked MongoDB and job sources.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from bson import ObjectId

from src.services.job_search_service import JobSearchService, SearchResult
from src.common.job_search_config import JobSearchConfig
from src.services.job_sources import JobData


@pytest.fixture
def mock_db():
    """Create a mock MongoDB database."""
    db = MagicMock()
    db["job_search_cache"] = MagicMock()
    db["job_search_index"] = MagicMock()
    db["level-2"] = MagicMock()
    return db


@pytest.fixture
def mock_search_repository():
    """Create a mock JobSearchRepositoryInterface."""
    mock = MagicMock()
    # Cache operations
    mock.cache_find_one.return_value = None
    mock.cache_upsert.return_value = True
    mock.cache_delete_all.return_value = 0
    mock.cache_count.return_value = 0
    # Index operations
    mock.index_find.return_value = []
    mock.index_find_one.return_value = None
    mock.index_find_by_ids.return_value = []
    mock.index_upsert.return_value = MagicMock(upserted_id=None)
    mock.index_update_one.return_value = 0
    mock.index_count.return_value = 0
    mock.index_aggregate.return_value = []
    return mock


@pytest.fixture
def mock_job_repository():
    """Create a mock JobRepositoryInterface."""
    mock = MagicMock()
    mock.find_one.return_value = None
    mock.insert_one.return_value = MagicMock(upserted_id=ObjectId())
    return mock


@pytest.fixture
def service(mock_db, mock_search_repository, mock_job_repository):
    """Create a JobSearchService instance with mocked repositories."""
    with patch.object(JobSearchService, '_ensure_indexes'):
        return JobSearchService(
            mock_db,
            search_repository=mock_search_repository,
            job_repository=mock_job_repository,
        )


class TestJobSearchService:
    """Tests for JobSearchService class."""

    def test_init(self, mock_db):
        """Test service initialization."""
        with patch.object(JobSearchService, '_ensure_indexes'):
            service = JobSearchService(mock_db)

        assert service.db == mock_db
        assert service.config is not None
        assert "indeed" in service.sources
        assert "bayt" in service.sources
        assert "himalayas" in service.sources

    def test_generate_cache_key_deterministic(self, service):
        """Test that cache key generation is deterministic."""
        params = {
            "job_titles": ["Senior Software Engineer", "Staff Engineer"],
            "regions": ["gulf", "worldwide_remote"],
            "sources": ["indeed", "bayt"],
            "remote_only": False,
        }

        key1 = service._generate_cache_key(params)
        key2 = service._generate_cache_key(params)

        assert key1 == key2
        assert len(key1) == 32  # SHA256 truncated to 32 chars

    def test_generate_cache_key_order_independent(self, service):
        """Test that cache key is independent of list order."""
        params1 = {
            "job_titles": ["A", "B"],
            "regions": ["gulf", "worldwide_remote"],
            "sources": ["indeed", "bayt"],
            "remote_only": False,
        }
        params2 = {
            "job_titles": ["B", "A"],  # Different order
            "regions": ["worldwide_remote", "gulf"],  # Different order
            "sources": ["bayt", "indeed"],  # Different order
            "remote_only": False,
        }

        key1 = service._generate_cache_key(params1)
        key2 = service._generate_cache_key(params2)

        assert key1 == key2

    def test_generate_cache_key_case_insensitive(self, service):
        """Test that cache key is case insensitive for job titles."""
        params1 = {"job_titles": ["SENIOR ENGINEER"], "regions": [], "sources": [], "remote_only": False}
        params2 = {"job_titles": ["senior engineer"], "regions": [], "sources": [], "remote_only": False}

        key1 = service._generate_cache_key(params1)
        key2 = service._generate_cache_key(params2)

        assert key1 == key2

    def test_generate_dedupe_key(self, service):
        """Test deduplication key generation - new format: source|normalized_fields."""
        job = {
            "company": "Acme Corp",
            "title": "Software Engineer",
            "location": "Dubai, UAE",
        }

        key = service._generate_dedupe_key(job, "indeed")

        # New format: source|company|title|location (all normalized - no special chars)
        assert key == "indeed|acmecorp|softwareengineer|dubaiuae"

    def test_check_cache_found(self, service, mock_search_repository):
        """Test cache lookup when entry exists."""
        cache_key = "abc123"
        mock_entry = {
            "cache_key": cache_key,
            "expires_at": datetime.utcnow() + timedelta(hours=1),
            "job_ids": [ObjectId()],
        }
        mock_search_repository.cache_find_one.return_value = mock_entry

        result = service._check_cache(cache_key)

        assert result == mock_entry
        mock_search_repository.cache_find_one.assert_called_once()

    def test_check_cache_not_found(self, service, mock_search_repository):
        """Test cache lookup when entry doesn't exist."""
        mock_search_repository.cache_find_one.return_value = None

        result = service._check_cache("nonexistent")

        assert result is None

    def test_derive_tier(self, service):
        """Test tier derivation from score."""
        assert service._derive_tier(90) == "Tier A"
        assert service._derive_tier(85) == "Tier A"
        assert service._derive_tier(80) == "Tier B+"
        assert service._derive_tier(70) == "Tier B+"
        assert service._derive_tier(60) == "Tier B"
        assert service._derive_tier(55) == "Tier B"
        assert service._derive_tier(50) == "Tier C"
        assert service._derive_tier(None) == "Unscored"


class TestJobSearchServiceActions:
    """Tests for job action methods."""

    def test_get_job_found(self, service, mock_search_repository):
        """Test getting a job by ID."""
        job_id = str(ObjectId())
        mock_job = {
            "_id": ObjectId(job_id),
            "title": "Engineer",
            "company": "Tech Co",
        }
        mock_search_repository.index_find_one.return_value = mock_job

        result = service.get_job(job_id)

        assert result is not None
        assert result["job_id"] == job_id
        assert result["title"] == "Engineer"

    def test_get_job_not_found(self, service, mock_search_repository):
        """Test getting a non-existent job."""
        mock_search_repository.index_find_one.return_value = None

        result = service.get_job(str(ObjectId()))

        assert result is None

    def test_hide_job_success(self, service, mock_search_repository):
        """Test hiding a job."""
        job_id = str(ObjectId())
        mock_search_repository.index_update_one.return_value = 1  # modified_count

        result = service.hide_job(job_id)

        assert result["success"] is True
        assert result["job_id"] == job_id
        assert result["hidden"] is True

    def test_hide_job_not_found(self, service, mock_search_repository):
        """Test hiding a non-existent job."""
        mock_search_repository.index_update_one.return_value = 0  # modified_count

        result = service.hide_job(str(ObjectId()))

        assert result["success"] is False
        assert "error" in result

    def test_unhide_job_success(self, service, mock_search_repository):
        """Test unhiding a job."""
        job_id = str(ObjectId())
        mock_search_repository.index_update_one.return_value = 1  # modified_count

        result = service.unhide_job(job_id)

        assert result["success"] is True
        assert result["hidden"] is False

    def test_promote_job_success(self, service, mock_search_repository, mock_job_repository):
        """Test promoting a job to level-2."""
        job_id = str(ObjectId())
        level2_id = ObjectId()

        mock_job = {
            "_id": ObjectId(job_id),
            "title": "Engineer",
            "company": "Tech Co",
            "location": "Dubai",
            "url": "https://example.com",
            "description": "...",
            "dedupeKey": "tech co|engineer|dubai|indeed",
            "source": "indeed",
            "quick_score": 85,
            "quick_score_rationale": "Good match",
            "promoted_to_level2": False,
        }
        mock_search_repository.index_find_one.return_value = mock_job
        mock_job_repository.insert_one.return_value = MagicMock(upserted_id=level2_id)

        result = service.promote_job(job_id)

        assert result["success"] is True
        assert result["index_job_id"] == job_id
        assert result["level2_job_id"] == str(level2_id)
        mock_job_repository.insert_one.assert_called_once()
        mock_search_repository.index_update_one.assert_called_once()

    def test_promote_job_already_promoted(self, service, mock_search_repository):
        """Test promoting an already promoted job."""
        job_id = str(ObjectId())
        level2_id = ObjectId()

        mock_job = {
            "_id": ObjectId(job_id),
            "promoted_to_level2": True,
            "promoted_job_id": level2_id,
        }
        mock_search_repository.index_find_one.return_value = mock_job

        result = service.promote_job(job_id)

        assert result["success"] is False
        assert "already promoted" in result["error"]

    def test_promote_job_not_found(self, service, mock_search_repository):
        """Test promoting a non-existent job."""
        mock_search_repository.index_find_one.return_value = None

        result = service.promote_job(str(ObjectId()))

        assert result["success"] is False
        assert "not found" in result["error"]


class TestJobSearchServiceCache:
    """Tests for cache management methods."""

    def test_clear_cache(self, service, mock_search_repository):
        """Test clearing the cache."""
        mock_search_repository.cache_delete_all.return_value = 10  # deleted_count

        result = service.clear_cache()

        assert result["success"] is True
        assert result["cleared_count"] == 10

    def test_get_cache_stats(self, service, mock_search_repository):
        """Test getting cache statistics."""
        # Mock count to be called twice (total, then active)
        mock_search_repository.cache_count.side_effect = [15, 10]  # total, active

        result = service.get_cache_stats()

        assert result["total_entries"] == 15
        assert result["active_entries"] == 10
        assert result["expired_entries"] == 5

    def test_get_index_stats(self, service, mock_search_repository):
        """Test getting index statistics."""
        # Mock count to be called multiple times
        mock_search_repository.index_count.side_effect = [100, 20, 5, 30]

        result = service.get_index_stats()

        assert result["total_jobs"] == 100
        assert result["promoted"] == 20
        assert result["hidden"] == 5
        assert result["scored"] == 30
        assert result["active"] == 95  # 100 - 5 hidden


class TestJobSearchServiceQuery:
    """Tests for index query methods."""

    def test_query_index_basic(self, service, mock_search_repository):
        """Test basic index query."""
        mock_jobs = [
            {"_id": ObjectId(), "title": "Engineer", "company": "Tech"},
        ]
        mock_search_repository.index_find.return_value = mock_jobs
        mock_search_repository.index_count.return_value = 1
        mock_search_repository.index_aggregate.return_value = []

        result = service.query_index()

        assert len(result["jobs"]) == 1
        assert result["total"] == 1
        assert "facets" in result
        assert "pagination" in result

    def test_query_index_with_filters(self, service, mock_search_repository):
        """Test index query with filters."""
        mock_search_repository.index_find.return_value = []
        mock_search_repository.index_count.return_value = 0
        mock_search_repository.index_aggregate.return_value = []

        result = service.query_index(
            sources=["indeed"],
            regions=["gulf"],
            remote_only=True,
            min_score=70,
        )

        # Check that index_find was called with filters
        call_args = mock_search_repository.index_find.call_args
        filter_query = call_args[0][0]

        assert filter_query["source"] == {"$in": ["indeed"]}
        assert filter_query["region"] == {"$in": ["gulf"]}
        assert filter_query["is_remote"] is True
        assert filter_query["quick_score"] == {"$gte": 70}

    def test_query_index_pagination(self, service, mock_search_repository):
        """Test index query pagination."""
        mock_search_repository.index_find.return_value = []
        mock_search_repository.index_count.return_value = 100
        mock_search_repository.index_aggregate.return_value = []

        result = service.query_index(offset=20, limit=10)

        assert result["pagination"]["offset"] == 20
        assert result["pagination"]["limit"] == 10
        assert result["pagination"]["has_more"] is True

        # Check that index_find was called with correct skip/limit
        call_args = mock_search_repository.index_find.call_args
        assert call_args[1]["skip"] == 20
        assert call_args[1]["limit"] == 10

    def test_query_index_limit_capped(self, service, mock_search_repository):
        """Test that query limit is capped at 100."""
        mock_search_repository.index_find.return_value = []
        mock_search_repository.index_count.return_value = 0
        mock_search_repository.index_aggregate.return_value = []

        result = service.query_index(limit=200)  # Try to request 200

        # Check that index_find was called with capped limit
        call_args = mock_search_repository.index_find.call_args
        assert call_args[1]["limit"] == 100  # Should be capped at 100


@pytest.mark.asyncio
class TestJobSearchServiceSearch:
    """Tests for the main search method."""

    async def test_search_cache_hit(self, service, mock_search_repository):
        """Test search with cache hit."""
        job_ids = [ObjectId(), ObjectId()]
        mock_cache_entry = {
            "cache_key": "abc123",
            "job_ids": job_ids,
            "results_by_source": {"indeed": 2},
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
        mock_jobs = [
            {"_id": job_ids[0], "title": "Job 1"},
            {"_id": job_ids[1], "title": "Job 2"},
        ]

        mock_search_repository.cache_find_one.return_value = mock_cache_entry
        mock_search_repository.index_find_by_ids.return_value = mock_jobs

        result = await service.search(
            job_titles=["senior_swe"],
            regions=["gulf"],
            sources=["indeed"],
        )

        assert result.success is True
        assert result.cache_hit is True
        assert result.total_results == 2

    async def test_search_fresh(self, service, mock_search_repository):
        """Test fresh search (no cache)."""
        mock_search_repository.cache_find_one.return_value = None

        # Mock the source fetch
        mock_job = JobData(
            title="Engineer",
            company="Tech",
            location="Dubai",
            description="...",
            url="https://example.com",
        )

        with patch.object(service.sources["indeed"], "fetch_jobs", return_value=[mock_job]):
            # Mock upsert
            mock_search_repository.index_upsert.return_value = MagicMock(
                upserted_id=ObjectId()
            )
            mock_search_repository.index_find_by_ids.return_value = [
                {"_id": ObjectId(), "title": "Engineer", "company": "Tech"},
            ]

            result = await service.search(
                job_titles=["senior_swe"],
                regions=["gulf"],
                sources=["indeed"],
                use_cache=False,
            )

            assert result.success is True
            assert result.cache_hit is False

    async def test_search_error_handling(self, service, mock_search_repository):
        """Test search error handling."""
        mock_search_repository.cache_find_one.return_value = None

        with patch.object(service.sources["indeed"], "fetch_jobs", side_effect=Exception("Network error")):
            result = await service.search(
                job_titles=["senior_swe"],
                regions=["gulf"],
                sources=["indeed"],
            )

            # Should still succeed, just with empty results from that source
            assert result.success is True
