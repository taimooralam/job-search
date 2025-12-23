"""
Unit tests for src/services/job_ingest_service.py

Tests the IngestService class that handles:
- Deduplication via dedupeKey
- Quick scoring (Claude CLI or OpenRouter)
- Incremental fetching via last_fetch_at state
- Run history storage (limited to 50 runs)
- MongoDB insertion
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from bson import ObjectId

from src.services.job_ingest_service import IngestService, IngestResult
from src.services.job_sources import JobData


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Mock MongoDB database with collections."""
    mock_level2 = MagicMock()
    mock_system_state = MagicMock()

    mock_db_instance = MagicMock()
    mock_db_instance.__getitem__.side_effect = lambda name: {
        "level-2": mock_level2,
        "system_state": mock_system_state,
    }[name]

    return {
        "db": mock_db_instance,
        "level2": mock_level2,
        "system_state": mock_system_state,
    }


@pytest.fixture
def sample_jobs():
    """Sample JobData objects for testing."""
    return [
        JobData(
            company="TechCorp",
            title="Senior Python Developer",
            location="Remote",
            url="https://example.com/job1",
            description="Great opportunity for senior Python developer",
            salary="$120k-150k",
            job_type="Full-time",
            posted_date=datetime.utcnow(),
            source_id="job_001",
        ),
        JobData(
            company="StartupCo",
            title="Staff Engineer",
            location="Worldwide",
            url="https://example.com/job2",
            description="Lead engineering initiatives at fast-growing startup",
            salary="$150k-180k",
            job_type="Full-time",
            posted_date=datetime.utcnow(),
            source_id="job_002",
        ),
        JobData(
            company="BigTech Inc",
            title="Engineering Manager",
            location="Remote (US)",
            url="https://example.com/job3",
            description="Manage a team of 10 engineers",
            salary="$180k-220k",
            job_type="Full-time",
            posted_date=datetime.utcnow(),
            source_id="job_003",
        ),
    ]


# =============================================================================
# HAPPY PATH TESTS - IngestService Initialization
# =============================================================================


class TestIngestServiceInitialization:
    """Tests for IngestService initialization."""

    def test_init_with_claude_scorer(self, mock_db):
        """Should initialize with Claude scorer by default."""
        # Act
        service = IngestService(mock_db["db"], use_claude_scorer=True)

        # Assert
        assert service.db == mock_db["db"]
        assert service.use_claude_scorer is True
        assert service._scorer is None  # Lazy init

    def test_init_with_openrouter_scorer(self, mock_db):
        """Should initialize with OpenRouter scorer."""
        # Act
        service = IngestService(mock_db["db"], use_claude_scorer=False)

        # Assert
        assert service.use_claude_scorer is False


# =============================================================================
# HAPPY PATH TESTS - State Management
# =============================================================================


class TestIngestServiceStateManagement:
    """Tests for ingestion state management."""

    def test_get_last_fetch_timestamp_exists(self, mock_db):
        """Should retrieve last fetch timestamp when state exists."""
        # Arrange
        service = IngestService(mock_db["db"])
        last_fetch = datetime(2025, 1, 15, 10, 0, 0)
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "last_fetch_at": last_fetch,
        }

        # Act
        result = service.get_last_fetch_timestamp("himalayas_auto")

        # Assert
        assert result == last_fetch
        mock_db["system_state"].find_one.assert_called_once_with(
            {"_id": "ingest_himalayas_auto"}
        )

    def test_get_last_fetch_timestamp_not_exists(self, mock_db):
        """Should return None when no state exists."""
        # Arrange
        service = IngestService(mock_db["db"])
        mock_db["system_state"].find_one.return_value = None

        # Act
        result = service.get_last_fetch_timestamp("new_source")

        # Assert
        assert result is None

    def test_update_last_fetch_timestamp(self, mock_db):
        """Should update last fetch timestamp and stats."""
        # Arrange
        service = IngestService(mock_db["db"])
        timestamp = datetime.utcnow()
        stats = {
            "fetched": 50,
            "ingested": 25,
            "duplicates_skipped": 10,
            "below_threshold": 15,
        }

        # Act
        service.update_last_fetch_timestamp(
            source="himalayas_auto",
            timestamp=timestamp,
            stats=stats,
        )

        # Assert
        mock_db["system_state"].update_one.assert_called()
        call_args = mock_db["system_state"].update_one.call_args_list

        # First call: update timestamp and stats
        assert call_args[0][0][0] == {"_id": "ingest_himalayas_auto"}
        update_doc = call_args[0][0][1]["$set"]
        assert update_doc["last_fetch_at"] == timestamp
        assert update_doc["last_run_stats"] == stats

    def test_update_adds_to_run_history(self, mock_db):
        """Should add run to history with $slice to keep last 50."""
        # Arrange
        service = IngestService(mock_db["db"])
        timestamp = datetime.utcnow()
        stats = {"fetched": 10, "ingested": 5}

        # Act
        service.update_last_fetch_timestamp(
            source="himalayas_auto",
            timestamp=timestamp,
            stats=stats,
        )

        # Assert - Second call should be for run_history
        call_args = mock_db["system_state"].update_one.call_args_list
        assert len(call_args) == 2

        # Verify run_history update
        history_update = call_args[1][0][1]["$push"]["run_history"]
        assert history_update["$slice"] == -50  # Keep last 50 runs
        assert len(history_update["$each"]) == 1
        assert history_update["$each"][0]["stats"] == stats


# =============================================================================
# HAPPY PATH TESTS - Deduplication
# =============================================================================


class TestIngestServiceDeduplication:
    """Tests for job deduplication logic."""

    def test_generate_dedupe_key(self, mock_db, sample_jobs):
        """Should generate consistent dedupe key."""
        # Arrange
        service = IngestService(mock_db["db"])
        job = sample_jobs[0]

        # Act
        key = service.generate_dedupe_key(job, "himalayas_auto")

        # Assert
        assert key == "techcorp|senior python developer|remote|himalayas_auto"
        assert key.islower()  # Normalized to lowercase

    def test_generate_dedupe_key_handles_special_chars(self, mock_db):
        """Should normalize special characters in dedupe key."""
        # Arrange
        service = IngestService(mock_db["db"])
        job = JobData(
            company="Tech, Inc.",
            title="Senior Engineer / Manager",
            location="San Francisco, CA",
            url="https://example.com/job",
            description="Test",
            posted_date=datetime.utcnow(),
        )

        # Act
        key = service.generate_dedupe_key(job, "test_source")

        # Assert
        assert "tech, inc." in key
        assert "senior engineer / manager" in key
        assert "san francisco, ca" in key


# =============================================================================
# HAPPY PATH TESTS - Job Document Creation
# =============================================================================


class TestIngestServiceDocumentCreation:
    """Tests for MongoDB document creation."""

    def test_create_job_document(self, mock_db, sample_jobs):
        """Should create properly formatted job document."""
        # Arrange
        service = IngestService(mock_db["db"])
        job = sample_jobs[0]

        # Act
        doc = service.create_job_document(
            job=job,
            source_name="himalayas_auto",
            score=85,
            rationale="Strong match for senior Python role",
        )

        # Assert
        assert doc["company"] == "TechCorp"
        assert doc["title"] == "Senior Python Developer"
        assert doc["location"] == "Remote"
        assert doc["jobUrl"] == "https://example.com/job1"
        assert doc["description"] == "Great opportunity for senior Python developer"
        assert doc["status"] == "not processed"
        assert doc["source"] == "himalayas_auto"
        assert doc["auto_discovered"] is True
        assert doc["quick_score"] == 85
        assert doc["quick_score_rationale"] == "Strong match for senior Python role"
        assert doc["tier"] == "A"  # Score 85 = Tier A
        assert "createdAt" in doc
        assert "dedupeKey" in doc

    def test_create_job_document_derives_tier_from_score(self, mock_db, sample_jobs):
        """Should derive correct tier based on score."""
        # Arrange
        service = IngestService(mock_db["db"])
        job = sample_jobs[0]

        # Test different score tiers (based on actual derive_tier_from_score function)
        test_cases = [
            (95, "A"),  # 80+ = A tier
            (85, "A"),  # 80+ = A tier
            (75, "B"),  # 60-79 = B tier
            (65, "B"),  # 60-79 = B tier
            (50, "C"),  # 40-59 = C tier
            (35, "D"),  # < 40 = D tier
        ]

        for score, expected_tier in test_cases:
            # Act
            doc = service.create_job_document(
                job=job,
                source_name="test",
                score=score,
                rationale="test",
            )

            # Assert
            assert doc["tier"] == expected_tier, f"Score {score} should map to tier {expected_tier}"


# =============================================================================
# HAPPY PATH TESTS - Job Ingestion
# =============================================================================


class TestIngestServiceIngestion:
    """Tests for the main ingest_jobs method."""

    @pytest.mark.asyncio
    async def test_ingest_jobs_success(self, mock_db, sample_jobs):
        """Should ingest jobs successfully with scoring."""
        # Arrange
        service = IngestService(mock_db["db"], use_claude_scorer=False)

        # Mock find_one to return None (no duplicates)
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None  # No previous state

        # Mock insert_one to return inserted ID
        mock_result = MagicMock()
        mock_result.inserted_id = ObjectId()
        mock_db["level2"].insert_one.return_value = mock_result

        # Mock quick_score_job at the right path
        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.return_value = (85, "Great fit")

            # Act
            result = await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="himalayas_auto",
                score_threshold=70,
                skip_scoring=False,
                incremental=False,
            )

        # Assert
        assert result.success is True
        assert result.fetched == 3
        assert result.ingested == 3
        assert result.duplicates_skipped == 0
        assert result.below_threshold == 0
        assert result.errors == 0
        assert len(result.ingested_jobs) == 3

    @pytest.mark.asyncio
    async def test_ingest_jobs_skip_scoring(self, mock_db, sample_jobs):
        """Should skip LLM scoring when skip_scoring=True."""
        # Arrange
        service = IngestService(mock_db["db"])
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None  # No previous state
        mock_db["level2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        # Act
        result = await service.ingest_jobs(
            jobs=sample_jobs,
            source_name="test",
            skip_scoring=True,
            incremental=False,  # Disable incremental to avoid posted_date comparison
        )

        # Assert
        assert result.success is True
        assert result.ingested == 3
        # All jobs should have default score of 75
        for job in result.ingested_jobs:
            assert job["score"] == 75

    @pytest.mark.asyncio
    async def test_ingest_jobs_skips_duplicates(self, mock_db, sample_jobs):
        """Should skip jobs that already exist (duplicate dedupeKey)."""
        # Arrange
        service = IngestService(mock_db["db"])

        # Mock find_one to return existing job for first job
        def find_one_side_effect(query):
            # system_state queries return None
            if "_id" in query and query["_id"].startswith("ingest_"):
                return None
            # level2 queries - first job is duplicate
            if "techcorp" in query.get("dedupeKey", "").lower():
                return {"_id": ObjectId()}  # Duplicate found
            return None

        mock_db["level2"].find_one.side_effect = find_one_side_effect
        mock_db["system_state"].find_one.side_effect = find_one_side_effect
        mock_db["level2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        # Act
        result = await service.ingest_jobs(
            jobs=sample_jobs,
            source_name="test",
            skip_scoring=True,
            incremental=False,
        )

        # Assert
        assert result.duplicates_skipped == 1
        assert result.ingested == 2  # Only 2 inserted

    @pytest.mark.asyncio
    async def test_ingest_jobs_filters_below_threshold(self, mock_db, sample_jobs):
        """Should skip jobs below score threshold."""
        # Arrange
        service = IngestService(mock_db["db"], use_claude_scorer=False)
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None
        mock_db["level2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        # Mock scorer to return varying scores
        scores = [85, 65, 75]  # Second job below threshold
        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.side_effect = [(score, "test") for score in scores]

            # Act
            result = await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="test",
                score_threshold=70,  # Job with score 65 should be skipped
                incremental=False,
            )

        # Assert
        assert result.below_threshold == 1
        assert result.ingested == 2

    @pytest.mark.asyncio
    async def test_ingest_jobs_incremental_filtering(self, mock_db, sample_jobs):
        """Should filter jobs by posted_date in incremental mode."""
        # Arrange
        service = IngestService(mock_db["db"])
        last_fetch = datetime.utcnow() - timedelta(days=1)

        # Set posted_date on jobs (one old, two new)
        sample_jobs[0].posted_date = datetime.utcnow() - timedelta(days=2)  # Old
        sample_jobs[1].posted_date = datetime.utcnow()  # New
        sample_jobs[2].posted_date = datetime.utcnow()  # New

        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_test",
            "last_fetch_at": last_fetch,
        }
        mock_db["level2"].find_one.return_value = None
        mock_db["level2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        # Act
        result = await service.ingest_jobs(
            jobs=sample_jobs,
            source_name="test",
            skip_scoring=True,
            incremental=True,
        )

        # Assert
        assert result.fetched == 2  # Only 2 jobs newer than last_fetch
        assert result.ingested == 2


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestIngestServiceErrorHandling:
    """Tests for error handling in ingestion."""

    @pytest.mark.asyncio
    async def test_ingest_jobs_handles_insert_error(self, mock_db, sample_jobs):
        """Should continue processing when one job fails to insert."""
        # Arrange
        service = IngestService(mock_db["db"])
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None

        # First insert succeeds, second fails, third succeeds
        insert_results = [
            MagicMock(inserted_id=ObjectId()),
            Exception("Insert failed"),
            MagicMock(inserted_id=ObjectId()),
        ]

        mock_db["level2"].insert_one.side_effect = insert_results

        # Act
        result = await service.ingest_jobs(
            jobs=sample_jobs,
            source_name="test",
            skip_scoring=True,
            incremental=False,
        )

        # Assert
        assert result.ingested == 2  # 2 successful
        assert result.errors == 1  # 1 failed

    @pytest.mark.asyncio
    async def test_ingest_jobs_handles_scoring_error(self, mock_db, sample_jobs):
        """Should skip job when scoring fails."""
        # Arrange
        service = IngestService(mock_db["db"], use_claude_scorer=False)
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None
        mock_db["level2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        # Mock scorer to fail on second job
        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.side_effect = [
                (85, "test"),
                Exception("Scoring failed"),
                (75, "test"),
            ]

            # Act
            result = await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="test",
                skip_scoring=False,
                incremental=False,
            )

        # Assert
        assert result.errors == 1


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestIngestServiceEdgeCases:
    """Tests for edge cases in ingestion."""

    @pytest.mark.asyncio
    async def test_ingest_jobs_empty_list(self, mock_db):
        """Should handle empty job list gracefully."""
        # Arrange
        service = IngestService(mock_db["db"])

        # Act
        result = await service.ingest_jobs(
            jobs=[],
            source_name="test",
        )

        # Assert
        assert result.success is True
        assert result.fetched == 0
        assert result.ingested == 0

    @pytest.mark.asyncio
    async def test_ingest_jobs_all_duplicates(self, mock_db, sample_jobs):
        """Should handle case where all jobs are duplicates."""
        # Arrange
        service = IngestService(mock_db["db"])

        # All jobs already exist
        mock_db["level2"].find_one.return_value = {"_id": ObjectId()}
        mock_db["system_state"].find_one.return_value = None

        # Act
        result = await service.ingest_jobs(
            jobs=sample_jobs,
            source_name="test",
            skip_scoring=True,
            incremental=False,
        )

        # Assert
        assert result.duplicates_skipped == 3
        assert result.ingested == 0

    @pytest.mark.asyncio
    async def test_ingest_jobs_all_below_threshold(self, mock_db, sample_jobs):
        """Should handle case where all jobs score below threshold."""
        # Arrange
        service = IngestService(mock_db["db"], use_claude_scorer=False)
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None

        # All jobs score low
        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.return_value = (50, "Low score")

            # Act
            result = await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="test",
                score_threshold=70,
                incremental=False,
            )

        # Assert
        assert result.below_threshold == 3
        assert result.ingested == 0

    @pytest.mark.asyncio
    async def test_ingest_jobs_none_score(self, mock_db, sample_jobs):
        """Should handle None score from scorer."""
        # Arrange
        service = IngestService(mock_db["db"], use_claude_scorer=False)
        mock_db["level2"].find_one.return_value = None
        mock_db["system_state"].find_one.return_value = None

        # Scorer returns None
        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.return_value = (None, "No score")

            # Act
            result = await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="test",
                incremental=False,
            )

        # Assert
        assert result.below_threshold == 3
        assert result.ingested == 0


# =============================================================================
# RESULT MODEL TESTS
# =============================================================================


class TestIngestResult:
    """Tests for IngestResult dataclass."""

    def test_ingest_result_to_dict(self):
        """Should convert IngestResult to dictionary."""
        # Arrange
        result = IngestResult(
            success=True,
            source="himalayas_auto",
            fetched=50,
            ingested=25,
            duplicates_skipped=10,
            below_threshold=15,
            errors=0,
            duration_ms=5000,
            incremental=True,
            last_fetch_at=datetime(2025, 1, 15, 10, 0, 0),
            ingested_jobs=[
                {
                    "job_id": "123",
                    "title": "Engineer",
                    "company": "TestCorp",
                    "score": 85,
                    "tier": "A",
                }
            ],
        )

        # Act
        result_dict = result.to_dict()

        # Assert
        assert result_dict["success"] is True
        assert result_dict["source"] == "himalayas_auto"
        assert result_dict["incremental"] is True
        assert result_dict["stats"]["fetched"] == 50
        assert result_dict["stats"]["ingested"] == 25
        assert result_dict["last_fetch_at"] == "2025-01-15T10:00:00"
        assert len(result_dict["jobs"]) == 1
        assert result_dict["error"] is None

    def test_ingest_result_to_dict_with_error(self):
        """Should include error message in dict."""
        # Arrange
        result = IngestResult(
            success=False,
            source="test",
            error_message="MongoDB connection failed",
        )

        # Act
        result_dict = result.to_dict()

        # Assert
        assert result_dict["success"] is False
        assert result_dict["error"] == "MongoDB connection failed"
