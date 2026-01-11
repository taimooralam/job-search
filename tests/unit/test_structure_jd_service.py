"""
Unit tests for src/services/structure_jd_service.py

Tests the StructureJDService for structuring job descriptions
into annotatable HTML sections with LLM or rule-based processing.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from bson import ObjectId

from src.services.structure_jd_service import StructureJDService, structure_jd
from src.services.operation_base import OperationResult
from src.common.model_tiers import ModelTier
from src.layer1_4 import LLMMetadata


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_job_id():
    """Valid MongoDB ObjectId string."""
    return str(ObjectId())


@pytest.fixture
def sample_job_document(sample_job_id):
    """Sample job document from MongoDB."""
    return {
        "_id": ObjectId(sample_job_id),
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": """
About TechCorp:
We are a leading technology company building the future of cloud infrastructure.

Responsibilities:
- Design and implement scalable backend services
- Lead technical architecture decisions
- Mentor junior engineers
- Collaborate with product teams

Qualifications:
- 5+ years of software development experience
- Strong Python and distributed systems knowledge
- Experience with cloud platforms (AWS/GCP)
- Excellent communication skills

Nice to Have:
- Kubernetes experience
- Open source contributions
        """,
        "jd_annotations": {},
        "createdAt": datetime.utcnow(),
    }


@pytest.fixture
def mock_processed_jd():
    """Sample ProcessedJD result."""
    return {
        "raw_text": "Sample JD text",
        "html": "<div class='jd-processed'><section>...</section></div>",
        "sections": [
            {
                "section_type": "about_company",
                "header": "About TechCorp",
                "content": "We are a leading...",
                "items": ["We are a leading technology company"],
                "char_start": 0,
                "char_end": 100,
                "index": 0,
            },
            {
                "section_type": "responsibilities",
                "header": "Responsibilities",
                "content": "Design and implement...",
                "items": [
                    "Design and implement scalable backend services",
                    "Lead technical architecture decisions",
                ],
                "char_start": 100,
                "char_end": 300,
                "index": 1,
            },
            {
                "section_type": "qualifications",
                "header": "Qualifications",
                "content": "5+ years...",
                "items": [
                    "5+ years of software development experience",
                    "Strong Python knowledge",
                ],
                "char_start": 300,
                "char_end": 500,
                "index": 2,
            },
        ],
        "section_ids": ["about_company", "responsibilities", "qualifications"],
        "content_hash": "abc123def456",
    }


@pytest.fixture
def mock_db_client():
    """Mock MongoDB client."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_job_repository():
    """Mock job repository for level-2 operations."""
    from src.common.repositories.base import WriteResult
    mock_repo = MagicMock()
    mock_repo.find_one.return_value = None
    mock_repo.update_one.return_value = WriteResult(
        matched_count=1, modified_count=1, atlas_success=True
    )
    return mock_repo


@pytest.fixture
def sample_llm_metadata():
    """Sample LLMMetadata for mocking."""
    return LLMMetadata(
        backend="claude_cli",
        model="claude-haiku-4-5-20251001",
        tier="low",
        duration_ms=2000,
        cost_usd=0.002,
        success=True,
    )


@pytest.fixture
def sample_rule_based_metadata():
    """Sample LLMMetadata for rule-based fallback."""
    return LLMMetadata(
        backend="rule_based",
        model="rule_based",
        tier="low",
        duration_ms=0,
        cost_usd=0.0,
        success=True,
    )


# =============================================================================
# Test StructureJDService Initialization
# =============================================================================


class TestStructureJDServiceInit:
    """Tests for StructureJDService initialization."""

    def test_operation_name_is_structure_jd(self):
        """Should have correct operation_name."""
        service = StructureJDService()
        assert service.operation_name == "structure-jd"

    def test_accepts_db_client(self, mock_db_client):
        """Should accept optional db_client."""
        service = StructureJDService(db_client=mock_db_client)
        assert service._db_client is mock_db_client

    def test_db_client_defaults_to_none(self):
        """Should default db_client to None."""
        service = StructureJDService()
        assert service._db_client is None


# =============================================================================
# Test _get_job Method
# =============================================================================


class TestStructureJDServiceGetJob:
    """Tests for _get_job method."""

    def test_raises_on_invalid_job_id(self):
        """Should raise ValueError for invalid ObjectId."""
        service = StructureJDService()

        with pytest.raises(ValueError) as exc_info:
            service._get_job("invalid-id")

        assert "Invalid job ID format" in str(exc_info.value)

    def test_returns_job_document(self, sample_job_id, sample_job_document, mock_job_repository):
        """Should return job document for valid ID."""
        mock_job_repository.find_one.return_value = sample_job_document

        service = StructureJDService(job_repository=mock_job_repository)
        result = service._get_job(sample_job_id)

        assert result == sample_job_document

    def test_returns_none_for_not_found(self, sample_job_id, mock_db_client):
        """Should return None if job not found."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_db_client.__getitem__ = MagicMock(return_value=MagicMock())
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        service = StructureJDService(db_client=mock_db_client)

        with patch.dict("os.environ", {"MONGO_DB_NAME": "jobs"}):
            result = service._get_job(sample_job_id)

        assert result is None


# =============================================================================
# Test _get_jd_text Method
# =============================================================================


class TestStructureJDServiceGetJDText:
    """Tests for _get_jd_text method."""

    def test_extracts_from_job_description_field(self):
        """Should extract JD from job_description field."""
        service = StructureJDService()
        job = {"job_description": "Test JD content"}

        result = service._get_jd_text(job)
        assert result == "Test JD content"

    def test_extracts_from_jobDescription_field(self):
        """Should extract JD from jobDescription field."""
        service = StructureJDService()
        job = {"jobDescription": "Test JD content from camelCase"}

        result = service._get_jd_text(job)
        assert result == "Test JD content from camelCase"

    def test_extracts_from_description_field(self):
        """Should extract JD from description field."""
        service = StructureJDService()
        job = {"description": "Test JD from description"}

        result = service._get_jd_text(job)
        assert result == "Test JD from description"

    def test_extracts_from_jd_text_field(self):
        """Should extract JD from jd_text field."""
        service = StructureJDService()
        job = {"jd_text": "Test JD from jd_text"}

        result = service._get_jd_text(job)
        assert result == "Test JD from jd_text"

    def test_raises_on_empty_jd(self):
        """Should raise ValueError if no JD text found."""
        service = StructureJDService()
        job = {"title": "Job without JD"}

        with pytest.raises(ValueError) as exc_info:
            service._get_jd_text(job)

        assert "No job description text found" in str(exc_info.value)

    def test_raises_on_whitespace_only_jd(self):
        """Should raise ValueError if JD is whitespace only."""
        service = StructureJDService()
        job = {"job_description": "   \n\t  "}

        with pytest.raises(ValueError) as exc_info:
            service._get_jd_text(job)

        assert "No job description text found" in str(exc_info.value)

    def test_prefers_job_description_over_others(self):
        """Should prefer job_description field when multiple present."""
        service = StructureJDService()
        job = {
            "job_description": "Primary JD",
            "description": "Fallback JD",
        }

        result = service._get_jd_text(job)
        assert result == "Primary JD"


# =============================================================================
# Test Execute Method - Success Cases
# =============================================================================


class TestStructureJDServiceExecuteSuccess:
    """Tests for successful execute method calls."""

    @pytest.fixture
    def service_with_mocks(self, sample_job_document, mock_processed_jd, sample_llm_metadata):
        """Service with mocked dependencies."""
        service = StructureJDService()

        # Mock _get_job
        service._get_job = MagicMock(return_value=sample_job_document)

        # Mock _persist_result
        service._persist_result = MagicMock(return_value=True)

        return service

    @pytest.mark.asyncio
    async def test_returns_operation_result(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should return OperationResult."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            # Create mock ProcessedJD object
            mock_result = MagicMock()
            mock_result.raw_text = mock_processed_jd["raw_text"]
            mock_result.html = mock_processed_jd["html"]
            mock_result.sections = []
            mock_result.section_ids = mock_processed_jd["section_ids"]
            mock_result.content_hash = mock_processed_jd["content_hash"]
            # Return tuple (processed, llm_metadata)
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                    use_llm=True,
                )

        assert isinstance(result, OperationResult)

    @pytest.mark.asyncio
    async def test_success_true_on_valid_input(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should return success=True for valid job."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_uses_llm_when_requested(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should use LLM processing when use_llm=True."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                    use_llm=True,
                )

        mock_process.assert_called_once()
        call_kwargs = mock_process.call_args
        assert call_kwargs[1]["use_llm"] is True

    @pytest.mark.asyncio
    async def test_uses_rule_based_when_llm_disabled(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_rule_based_metadata
    ):
        """Execute should use rule-based processing when use_llm=False."""
        with patch(
            "src.services.structure_jd_service.process_jd_sync",
        ) as mock_process_sync:
            mock_result = MagicMock()
            mock_process_sync.return_value = (mock_result, sample_rule_based_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.FAST,
                    use_llm=False,
                )

        mock_process_sync.assert_called_once()
        assert result.data.get("used_llm") is False

    @pytest.mark.asyncio
    async def test_includes_section_count_in_response(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should include section_count in response data."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        assert "section_count" in result.data
        assert result.data["section_count"] == 3

    @pytest.mark.asyncio
    async def test_includes_section_types_in_response(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should include section_types in response data."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        assert "section_types" in result.data
        assert result.data["section_types"] == ["about_company", "responsibilities", "qualifications"]

    @pytest.mark.asyncio
    async def test_persists_result_to_db(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should persist result to MongoDB."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        service_with_mocks._persist_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_cost_from_llm_metadata(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should use cost from LLM metadata when available."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                    use_llm=True,
                )

        # Should use cost from LLMMetadata (0.002)
        assert result.cost_usd == 0.002

    @pytest.mark.asyncio
    async def test_zero_cost_for_rule_based(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_rule_based_metadata):
        """Execute should have zero cost for rule-based processing."""
        with patch(
            "src.services.structure_jd_service.process_jd_sync",
        ) as mock_process_sync:
            mock_result = MagicMock()
            mock_process_sync.return_value = (mock_result, sample_rule_based_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.FAST,
                    use_llm=False,
                )

        assert result.cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_includes_model_from_llm_metadata(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should include model_used from LLM metadata."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                    use_llm=True,
                )

        assert result.model_used is not None
        # Should use model from LLM metadata
        assert result.model_used == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_includes_duration_ms(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should include duration_ms in result."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_generates_unique_run_id(self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata):
        """Execute should generate unique run_id."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result1 = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )
                result2 = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        assert result1.run_id != result2.run_id
        assert result1.run_id.startswith("op_structure-jd_")

    @pytest.mark.asyncio
    async def test_includes_llm_metadata_in_response(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should include llm_metadata in response data."""
        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service_with_mocks.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        assert "llm_metadata" in result.data
        assert result.data["llm_metadata"]["backend"] == "claude_cli"
        assert result.data["llm_metadata"]["model"] == "claude-haiku-4-5-20251001"

    @pytest.mark.asyncio
    async def test_creates_struct_logger_with_job_id(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should create StructuredLogger with job_id."""
        with patch(
            "src.services.structure_jd_service.StructuredLogger"
        ) as mock_logger_class:
            mock_logger_instance = MagicMock()
            mock_logger_class.return_value = mock_logger_instance

            with patch(
                "src.services.structure_jd_service.process_jd",
                new_callable=AsyncMock,
            ) as mock_process:
                mock_result = MagicMock()
                mock_process.return_value = (mock_result, sample_llm_metadata)

                with patch(
                    "src.services.structure_jd_service.processed_jd_to_dict",
                    return_value=mock_processed_jd,
                ):
                    await service_with_mocks.execute(
                        job_id=sample_job_id,
                        tier=ModelTier.BALANCED,
                        use_llm=True,
                    )

        # Verify StructuredLogger was created with job_id
        mock_logger_class.assert_called_once_with(job_id=sample_job_id)

    @pytest.mark.asyncio
    async def test_passes_struct_logger_to_process_jd(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should pass struct_logger to process_jd."""
        mock_logger_instance = MagicMock()

        with patch(
            "src.services.structure_jd_service.StructuredLogger"
        ) as mock_logger_class:
            mock_logger_class.return_value = mock_logger_instance

            with patch(
                "src.services.structure_jd_service.process_jd",
                new_callable=AsyncMock,
            ) as mock_process:
                mock_result = MagicMock()
                mock_process.return_value = (mock_result, sample_llm_metadata)

                with patch(
                    "src.services.structure_jd_service.processed_jd_to_dict",
                    return_value=mock_processed_jd,
                ):
                    await service_with_mocks.execute(
                        job_id=sample_job_id,
                        tier=ModelTier.BALANCED,
                        use_llm=True,
                    )

        # Verify struct_logger was passed to process_jd
        call_kwargs = mock_process.call_args[1]
        assert call_kwargs["struct_logger"] is mock_logger_instance

    @pytest.mark.asyncio
    async def test_emits_llm_call_complete_for_rule_based_fallback(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_rule_based_metadata
    ):
        """Execute should emit llm_call_complete event when rule-based fallback occurs."""
        mock_logger_instance = MagicMock()

        with patch(
            "src.services.structure_jd_service.StructuredLogger"
        ) as mock_logger_class:
            mock_logger_class.return_value = mock_logger_instance

            with patch(
                "src.services.structure_jd_service.process_jd_sync"
            ) as mock_process_sync:
                mock_result = MagicMock()
                mock_process_sync.return_value = (mock_result, sample_rule_based_metadata)

                with patch(
                    "src.services.structure_jd_service.processed_jd_to_dict",
                    return_value=mock_processed_jd,
                ):
                    await service_with_mocks.execute(
                        job_id=sample_job_id,
                        tier=ModelTier.FAST,
                        use_llm=False,
                    )

        # Verify llm_call_complete event was emitted
        mock_logger_instance.emit.assert_called_once_with(
            event="llm_call_complete",
            step_name="jd_structure_parsing",
            backend="rule_based",
            model="rule_based",
            tier="low",
            duration_ms=0,
            cost_usd=0.0,
            status="complete",
            metadata={"is_rule_based": True},
        )

    @pytest.mark.asyncio
    async def test_emits_llm_call_complete_with_fallback_reason(
        self, service_with_mocks, sample_job_id, mock_processed_jd
    ):
        """Execute should include fallback_reason in event metadata when present."""
        mock_logger_instance = MagicMock()

        # Create metadata with fallback_reason
        rule_based_with_reason = LLMMetadata(
            backend="rule_based",
            model="rule_based",
            tier="low",
            duration_ms=0,
            cost_usd=0.0,
            success=True,
            fallback_reason="LLM API timeout",
        )

        with patch(
            "src.services.structure_jd_service.StructuredLogger"
        ) as mock_logger_class:
            mock_logger_class.return_value = mock_logger_instance

            with patch(
                "src.services.structure_jd_service.process_jd",
                new_callable=AsyncMock,
            ) as mock_process:
                mock_result = MagicMock()
                mock_process.return_value = (mock_result, rule_based_with_reason)

                with patch(
                    "src.services.structure_jd_service.processed_jd_to_dict",
                    return_value=mock_processed_jd,
                ):
                    await service_with_mocks.execute(
                        job_id=sample_job_id,
                        tier=ModelTier.BALANCED,
                        use_llm=True,
                    )

        # Verify event was emitted with fallback_reason in metadata
        mock_logger_instance.emit.assert_called_once()
        call_kwargs = mock_logger_instance.emit.call_args[1]
        assert call_kwargs["event"] == "llm_call_complete"
        assert call_kwargs["backend"] == "rule_based"
        assert "metadata" in call_kwargs
        assert call_kwargs["metadata"]["fallback_reason"] == "LLM API timeout"
        assert call_kwargs["metadata"]["is_rule_based"] is True

    @pytest.mark.asyncio
    async def test_does_not_emit_event_for_successful_llm_call(
        self, service_with_mocks, sample_job_id, mock_processed_jd, sample_llm_metadata
    ):
        """Execute should not emit event when LLM succeeds (UnifiedLLM emits it)."""
        mock_logger_instance = MagicMock()

        with patch(
            "src.services.structure_jd_service.StructuredLogger"
        ) as mock_logger_class:
            mock_logger_class.return_value = mock_logger_instance

            with patch(
                "src.services.structure_jd_service.process_jd",
                new_callable=AsyncMock,
            ) as mock_process:
                mock_result = MagicMock()
                # Successful LLM call - backend is NOT "rule_based"
                mock_process.return_value = (mock_result, sample_llm_metadata)

                with patch(
                    "src.services.structure_jd_service.processed_jd_to_dict",
                    return_value=mock_processed_jd,
                ):
                    await service_with_mocks.execute(
                        job_id=sample_job_id,
                        tier=ModelTier.BALANCED,
                        use_llm=True,
                    )

        # Verify NO event was emitted (UnifiedLLM handles it)
        mock_logger_instance.emit.assert_not_called()


# =============================================================================
# Test Execute Method - Error Cases
# =============================================================================


class TestStructureJDServiceExecuteErrors:
    """Tests for execute method error handling."""

    @pytest.mark.asyncio
    async def test_returns_error_for_not_found_job(self, sample_job_id):
        """Execute should return error result for non-existent job."""
        service = StructureJDService()
        service._get_job = MagicMock(return_value=None)

        result = await service.execute(
            job_id=sample_job_id,
            tier=ModelTier.BALANCED,
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_job_id(self):
        """Execute should return error result for invalid job_id."""
        service = StructureJDService()
        service._get_job = MagicMock(side_effect=ValueError("Invalid job ID format: bad-id"))

        result = await service.execute(
            job_id="bad-id",
            tier=ModelTier.BALANCED,
        )

        assert result.success is False
        assert "Invalid job ID" in result.error

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_jd_text(self, sample_job_id):
        """Execute should return error result when JD text is missing."""
        service = StructureJDService()
        service._get_job = MagicMock(return_value={"_id": sample_job_id, "title": "No JD"})

        result = await service.execute(
            job_id=sample_job_id,
            tier=ModelTier.BALANCED,
        )

        assert result.success is False
        assert "No job description text found" in result.error

    @pytest.mark.asyncio
    async def test_handles_processing_exception(self, sample_job_id, sample_job_document):
        """Execute should handle exceptions during processing."""
        service = StructureJDService()
        service._get_job = MagicMock(return_value=sample_job_document)

        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_process.side_effect = Exception("LLM API error")

            result = await service.execute(
                job_id=sample_job_id,
                tier=ModelTier.BALANCED,
            )

        assert result.success is False
        assert "LLM API error" in result.error

    @pytest.mark.asyncio
    async def test_continues_on_persist_failure(self, sample_job_id, sample_job_document, mock_processed_jd, sample_llm_metadata):
        """Execute should succeed even if persistence fails."""
        service = StructureJDService()
        service._get_job = MagicMock(return_value=sample_job_document)
        service._persist_result = MagicMock(return_value=False)

        with patch(
            "src.services.structure_jd_service.process_jd",
            new_callable=AsyncMock,
        ) as mock_process:
            mock_result = MagicMock()
            mock_process.return_value = (mock_result, sample_llm_metadata)

            with patch(
                "src.services.structure_jd_service.processed_jd_to_dict",
                return_value=mock_processed_jd,
            ):
                result = await service.execute(
                    job_id=sample_job_id,
                    tier=ModelTier.BALANCED,
                )

        # Processing succeeded even though persistence failed
        assert result.success is True
        assert result.data.get("persisted") is False


# =============================================================================
# Test _persist_result Method
# =============================================================================


class TestStructureJDServicePersistResult:
    """Tests for _persist_result method."""

    def test_updates_job_document(self, sample_job_id, mock_processed_jd, mock_job_repository):
        """Should update job document with processed JD."""
        from src.common.repositories.base import WriteResult
        mock_job_repository.find_one.return_value = {"jd_annotations": {}}
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )

        service = StructureJDService(job_repository=mock_job_repository)
        result = service._persist_result(sample_job_id, mock_processed_jd)

        assert result is True
        mock_job_repository.update_one.assert_called_once()

    def test_preserves_existing_annotations(self, sample_job_id, mock_processed_jd, mock_job_repository):
        """Should preserve existing annotations when updating."""
        from src.common.repositories.base import WriteResult
        existing_annotations = {
            "highlight_0": {"type": "highlight", "text": "important"},
            "annotation_version": 2,
        }

        mock_job_repository.find_one.return_value = {"jd_annotations": existing_annotations}
        mock_job_repository.update_one.return_value = WriteResult(
            matched_count=1, modified_count=1, atlas_success=True
        )

        service = StructureJDService(job_repository=mock_job_repository)
        service._persist_result(sample_job_id, mock_processed_jd)

        # Check that update preserved existing highlight
        call_args = mock_job_repository.update_one.call_args[0][1]
        updated_annotations = call_args["$set"]["jd_annotations"]
        assert "highlight_0" in updated_annotations
        # Version should be incremented from 2 to 3
        assert updated_annotations["annotation_version"] == 3

    def test_returns_false_on_invalid_job_id(self, mock_processed_jd):
        """Should return False for invalid job_id."""
        service = StructureJDService()

        result = service._persist_result("invalid-id", mock_processed_jd)

        assert result is False

    def test_returns_false_on_db_error(self, sample_job_id, mock_processed_jd):
        """Should return False on database error."""
        mock_collection = MagicMock()
        mock_collection.find_one.side_effect = Exception("DB connection lost")

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        service = StructureJDService(db_client=mock_client)

        with patch.dict("os.environ", {"MONGO_DB_NAME": "jobs"}):
            result = service._persist_result(sample_job_id, mock_processed_jd)

        assert result is False


# =============================================================================
# Test Tier Selection
# =============================================================================


class TestStructureJDServiceTierSelection:
    """Tests for tier-based model selection."""

    def test_fast_tier_uses_mini_model(self):
        """FAST tier should use gpt-4o-mini."""
        service = StructureJDService()
        model = service.get_model(ModelTier.FAST)
        assert model == "gpt-4o-mini"

    def test_balanced_tier_uses_mini_model(self):
        """BALANCED tier should use gpt-4o-mini for analytical tasks."""
        service = StructureJDService()
        model = service.get_model(ModelTier.BALANCED)
        assert model == "gpt-4o-mini"

    def test_quality_tier_uses_gpt4o_model(self):
        """QUALITY tier should use gpt-4o for analytical tasks."""
        service = StructureJDService()
        model = service.get_model(ModelTier.QUALITY)
        assert model == "gpt-4o"


# =============================================================================
# Test Convenience Function
# =============================================================================


class TestStructureJDConvenienceFunction:
    """Tests for structure_jd convenience function."""

    @pytest.mark.asyncio
    async def test_creates_service_and_executes(self, sample_job_id, sample_job_document, mock_processed_jd):
        """structure_jd should create service and call execute."""
        with patch.object(StructureJDService, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="structure-jd",
                data={},
                cost_usd=0.0,
                duration_ms=100,
            )

            result = await structure_jd(
                job_id=sample_job_id,
                tier=ModelTier.BALANCED,
                use_llm=True,
            )

        mock_execute.assert_called_once_with(
            job_id=sample_job_id,
            tier=ModelTier.BALANCED,
            use_llm=True,
        )
        assert isinstance(result, OperationResult)

    @pytest.mark.asyncio
    async def test_passes_db_client_to_service(self, sample_job_id, mock_db_client):
        """structure_jd should pass db_client to service."""
        with patch.object(
            StructureJDService, "__init__", return_value=None
        ) as mock_init, patch.object(
            StructureJDService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="structure-jd",
                data={},
                cost_usd=0.0,
                duration_ms=100,
            )

            await structure_jd(
                job_id=sample_job_id,
                db_client=mock_db_client,
            )

        mock_init.assert_called_once_with(db_client=mock_db_client)

    @pytest.mark.asyncio
    async def test_uses_default_tier(self, sample_job_id):
        """structure_jd should default to BALANCED tier."""
        with patch.object(StructureJDService, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="structure-jd",
                data={},
                cost_usd=0.0,
                duration_ms=100,
            )

            await structure_jd(job_id=sample_job_id)

        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["tier"] == ModelTier.BALANCED

    @pytest.mark.asyncio
    async def test_uses_default_use_llm(self, sample_job_id):
        """structure_jd should default to use_llm=True."""
        with patch.object(StructureJDService, "execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="structure-jd",
                data={},
                cost_usd=0.0,
                duration_ms=100,
            )

            await structure_jd(job_id=sample_job_id)

        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["use_llm"] is True
