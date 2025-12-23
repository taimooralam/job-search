"""
Tests for JobIngestService.

Tests job ingestion logic including deduplication, scoring, and state management.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from bson import ObjectId

from src.services.job_ingest_service import IngestService, IngestResult
from src.services.job_sources import JobData


@pytest.fixture
def mock_db():
    """Create a mock MongoDB database."""
    db = MagicMock()
    db["level-2"] = MagicMock()
    db["system_state"] = MagicMock()
    return db


@pytest.fixture
def sample_jobs():
    """Create sample JobData objects."""
    return [
        JobData(
            title="Senior ML Engineer",
            company="Acme AI",
            location="Remote",
            url="https://example.com/job1",
            description="Build ML pipelines.",
            salary="$150k-$200k",
            job_type="Full-time",
            posted_date=datetime.utcnow(),
            source_id="job-001",
        ),
        JobData(
            title="Staff Engineer",
            company="TechCorp",
            location="Remote - Worldwide",
            url="https://example.com/job2",
            description="Lead technical initiatives.",
            salary=None,
            job_type="Full-time",
            posted_date=datetime.utcnow() - timedelta(hours=2),
            source_id="job-002",
        ),
    ]


class TestIngestResult:
    """Test IngestResult dataclass."""

    def test_to_dict(self):
        result = IngestResult(
            success=True,
            source="himalayas_auto",
            fetched=10,
            ingested=5,
            duplicates_skipped=3,
            below_threshold=2,
            duration_ms=1500,
            incremental=True,
            last_fetch_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["source"] == "himalayas_auto"
        assert d["stats"]["fetched"] == 10
        assert d["stats"]["ingested"] == 5
        assert d["incremental"] is True
        assert "2025-01-01" in d["last_fetch_at"]


class TestIngestService:
    """Test IngestService class."""

    def test_generate_dedupe_key(self, mock_db, sample_jobs):
        """Test deduplication key generation."""
        service = IngestService(mock_db, use_claude_scorer=False)

        job = sample_jobs[0]
        key = service.generate_dedupe_key(job, "himalayas_auto")

        assert key == "acme ai|senior ml engineer|remote|himalayas_auto"

    def test_get_last_fetch_timestamp_exists(self, mock_db):
        """Test retrieving existing timestamp."""
        mock_db["system_state"].find_one.return_value = {
            "_id": "ingest_himalayas_auto",
            "last_fetch_at": datetime(2025, 1, 1, 12, 0, 0),
        }

        service = IngestService(mock_db, use_claude_scorer=False)
        ts = service.get_last_fetch_timestamp("himalayas_auto")

        assert ts == datetime(2025, 1, 1, 12, 0, 0)
        mock_db["system_state"].find_one.assert_called_with({"_id": "ingest_himalayas_auto"})

    def test_get_last_fetch_timestamp_not_exists(self, mock_db):
        """Test retrieving timestamp when none exists."""
        mock_db["system_state"].find_one.return_value = None

        service = IngestService(mock_db, use_claude_scorer=False)
        ts = service.get_last_fetch_timestamp("himalayas_auto")

        assert ts is None

    def test_update_last_fetch_timestamp(self, mock_db):
        """Test updating timestamp."""
        service = IngestService(mock_db, use_claude_scorer=False)
        now = datetime.utcnow()

        service.update_last_fetch_timestamp(
            "himalayas_auto",
            now,
            stats={"fetched": 10, "ingested": 5},
        )

        mock_db["system_state"].update_one.assert_called_once()
        call_args = mock_db["system_state"].update_one.call_args
        assert call_args[0][0] == {"_id": "ingest_himalayas_auto"}
        assert call_args[1]["upsert"] is True

    def test_create_job_document(self, mock_db, sample_jobs):
        """Test job document creation."""
        service = IngestService(mock_db, use_claude_scorer=False)
        job = sample_jobs[0]

        doc = service.create_job_document(job, "himalayas_auto", 85, "Good match")

        assert doc["company"] == "Acme AI"
        assert doc["title"] == "Senior ML Engineer"
        assert doc["source"] == "himalayas_auto"
        assert doc["auto_discovered"] is True
        assert doc["quick_score"] == 85
        assert doc["tier"] == "A"
        assert doc["status"] == "not processed"
        assert "dedupeKey" in doc
        assert "createdAt" in doc

    @pytest.mark.asyncio
    async def test_ingest_jobs_skip_duplicates(self, mock_db, sample_jobs):
        """Test that duplicate jobs are skipped."""
        # Setup: First job is duplicate, second is new
        def find_one_side_effect(query):
            if "dedupeKey" in query:
                dedupe_key = query["dedupeKey"]
                if "acme ai" in dedupe_key:
                    return {"_id": "existing"}  # Duplicate
                return None  # Not duplicate
            return None

        mock_db["level-2"].find_one.side_effect = find_one_side_effect
        mock_db["level-2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        service = IngestService(mock_db, use_claude_scorer=False)

        result = await service.ingest_jobs(
            jobs=sample_jobs,
            source_name="himalayas_auto",
            skip_scoring=True,
            incremental=False,
        )

        assert result.duplicates_skipped == 1
        assert result.ingested == 1

    @pytest.mark.asyncio
    async def test_ingest_jobs_below_threshold(self, mock_db, sample_jobs):
        """Test that low-scoring jobs are skipped."""
        mock_db["level-2"].find_one.return_value = None  # No duplicates

        service = IngestService(mock_db, use_claude_scorer=False)

        with patch.object(service, "_score_job", new=AsyncMock(return_value=(50, "Weak fit"))):
            result = await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="himalayas_auto",
                score_threshold=70,
            )

        assert result.below_threshold == 2
        assert result.ingested == 0
        mock_db["level-2"].insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_jobs_incremental_filtering(self, mock_db):
        """Test incremental filtering by timestamp."""
        # Create fresh jobs with specific timestamps
        last_fetch_time = datetime.utcnow() - timedelta(hours=1)
        new_job = JobData(
            title="New Job",
            company="NewCorp",
            location="Remote",
            url="https://example.com/new",
            description="New job posted recently.",
            posted_date=datetime.utcnow(),  # Newer than last_fetch
            source_id="new-001",
        )
        old_job = JobData(
            title="Old Job",
            company="OldCorp",
            location="Remote",
            url="https://example.com/old",
            description="Old job posted before last fetch.",
            posted_date=datetime.utcnow() - timedelta(hours=3),  # Older than last_fetch
            source_id="old-001",
        )

        mock_db["level-2"].find_one.return_value = None
        mock_db["level-2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        service = IngestService(mock_db, use_claude_scorer=False)

        # Mock the get_last_fetch_timestamp method directly
        with patch.object(service, "get_last_fetch_timestamp", return_value=last_fetch_time):
            result = await service.ingest_jobs(
                jobs=[new_job, old_job],
                source_name="himalayas_auto",
                incremental=True,
                skip_scoring=True,
            )

        # Only 1 job should be processed (the newer one)
        assert result.fetched == 1  # After filtering
        assert result.ingested == 1

    @pytest.mark.asyncio
    async def test_ingest_jobs_updates_state(self, mock_db, sample_jobs):
        """Test that state is updated after ingestion."""
        mock_db["level-2"].find_one.return_value = None
        mock_db["level-2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        service = IngestService(mock_db, use_claude_scorer=False)

        with patch.object(service, "_score_job", new=AsyncMock(return_value=(80, "Good"))):
            await service.ingest_jobs(
                jobs=sample_jobs,
                source_name="himalayas_auto",
                skip_scoring=True,
            )

        # State should be updated
        mock_db["system_state"].update_one.assert_called()

    @pytest.mark.asyncio
    async def test_score_job_openrouter_fallback(self, mock_db, sample_jobs):
        """Test OpenRouter scorer fallback."""
        service = IngestService(mock_db, use_claude_scorer=False)
        # Force the scorer to be "openrouter"
        service._scorer = "openrouter"

        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.return_value = (75, "Good fit")

            score, rationale = await service._score_job(sample_jobs[0])

            assert score == 75
            mock_scorer.assert_called_once()

    @pytest.mark.asyncio
    async def test_score_job_claude_scorer(self, mock_db, sample_jobs):
        """Test Claude CLI scorer."""
        service = IngestService(mock_db, use_claude_scorer=True)

        # Create mock scorer instance and set it directly
        mock_scorer_instance = MagicMock()
        mock_scorer_instance.score_job = AsyncMock(return_value=(85, "Strong fit"))
        service._scorer = mock_scorer_instance

        score, rationale = await service._score_job(sample_jobs[0])

        assert score == 85
        mock_scorer_instance.score_job.assert_called_once()


class TestIngestServiceIntegration:
    """Integration-style tests (still mocked, but testing full flow)."""

    @pytest.fixture
    def mock_db_integration(self):
        """Create a mock MongoDB database for integration tests."""
        db = MagicMock()
        db["level-2"] = MagicMock()
        db["system_state"] = MagicMock()
        return db

    @pytest.fixture
    def integration_jobs(self):
        """Create sample JobData objects for integration tests."""
        return [
            JobData(
                title="Senior ML Engineer",
                company="Acme AI",
                location="Remote",
                url="https://example.com/job1",
                description="Build ML pipelines.",
                posted_date=datetime.utcnow(),
                source_id="job-001",
            ),
            JobData(
                title="Staff Engineer",
                company="TechCorp",
                location="Remote",
                url="https://example.com/job2",
                description="Lead initiatives.",
                posted_date=datetime.utcnow(),
                source_id="job-002",
            ),
        ]

    @pytest.mark.asyncio
    async def test_full_ingestion_flow(self, mock_db_integration, integration_jobs):
        """Test complete ingestion flow."""
        mock_db_integration["system_state"].find_one.return_value = None  # No previous state
        mock_db_integration["level-2"].find_one.return_value = None  # No duplicates
        mock_db_integration["level-2"].insert_one.return_value = MagicMock(inserted_id=ObjectId())

        service = IngestService(mock_db_integration, use_claude_scorer=False)
        # Force OpenRouter scorer
        service._scorer = "openrouter"

        with patch("src.services.quick_scorer.quick_score_job") as mock_scorer:
            mock_scorer.return_value = (80, "Good fit")

            result = await service.ingest_jobs(
                jobs=integration_jobs,
                source_name="himalayas_auto",
                score_threshold=70,
                incremental=False,
            )

        assert result.success is True
        assert result.fetched == 2
        assert result.ingested == 2
        assert len(result.ingested_jobs) == 2
        assert result.duration_ms >= 0
