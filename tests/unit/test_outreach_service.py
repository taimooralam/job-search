"""
Unit tests for src/services/outreach_service.py

Tests the OutreachGenerationService for generating per-contact outreach messages
(LinkedIn connection requests and InMail messages) with tier-based model selection.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from bson import ObjectId

from src.services.outreach_service import (
    OutreachGenerationService,
    generate_outreach,
    CONNECTION_CHAR_LIMIT,
    INMAIL_MIN_CHARS,
    INMAIL_MAX_CHARS,
    CANDIDATE_CALENDLY,
    CANDIDATE_NAME,
    CANDIDATE_SIGNATURE,
)
from src.services.operation_base import OperationResult
from src.common.model_tiers import ModelTier


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_job_id():
    """Valid MongoDB ObjectId string."""
    return str(ObjectId())


@pytest.fixture
def sample_contact():
    """Sample contact from job document."""
    return {
        "name": "Jane Smith",
        "role": "Engineering Manager",
        "linkedin_url": "https://linkedin.com/in/janesmith",
        "contact_type": "hiring_manager",
        "why_relevant": "Directly manages the team this role joins",
        "recent_signals": ["Posted about scaling challenges"],
        "linkedin_connection_message": "",
        "linkedin_inmail_subject": "",
        "linkedin_inmail": "",
        "email_subject": "",
        "email_body": "",
        "reasoning": "Key hiring decision-maker",
        "already_applied_frame": "adding_context",
        "linkedin_message": "",
    }


@pytest.fixture
def sample_job_document(sample_job_id, sample_contact):
    """Sample job document from MongoDB with contacts."""
    return {
        "_id": ObjectId(sample_job_id),
        "title": "Senior Software Engineer",
        "company": "TechCorp",
        "job_description": "We need a senior engineer...",
        "extracted_jd": {
            "title": "Senior Software Engineer",
            "company": "TechCorp",
            "implied_pain_points": [
                "Team scaling challenges",
                "Technical debt in core systems",
            ],
        },
        "pain_points": [
            "Team scaling challenges",
            "Technical debt in core systems",
            "Need to improve deployment velocity",
        ],
        "company_research": {
            "summary": "TechCorp is a leading SaaS company...",
            "signals": [
                {
                    "type": "funding",
                    "description": "Series B funding of $50M",
                    "date": "2024-01",
                    "source": "https://techcrunch.com/...",
                },
                {
                    "type": "growth",
                    "description": "Expanding engineering team by 50%",
                    "date": "2024-03",
                    "source": "https://linkedin.com/...",
                },
            ],
        },
        "selected_stars": [
            {
                "id": "star_1",
                "company": "PreviousCorp",
                "situation": "Team needed to scale from 5 to 20 engineers",
                "action": ["Implemented hiring process", "Created onboarding program"],
                "result": ["Hired 15 engineers in 6 months", "90% retention rate"],
            },
        ],
        "primary_contacts": [sample_contact],
        "secondary_contacts": [
            {
                "name": "Bob Johnson",
                "role": "Senior Engineer",
                "linkedin_url": "https://linkedin.com/in/bobjohnson",
                "contact_type": "peer",
                "why_relevant": "Current team member",
                "recent_signals": [],
                "linkedin_connection_message": "",
                "linkedin_inmail": "",
                "reasoning": "Potential colleague",
            },
        ],
        "createdAt": datetime.utcnow(),
    }


@pytest.fixture
def mock_db_client():
    """Mock MongoDB client."""
    mock = MagicMock()
    return mock


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for connection message."""
    mock_response = MagicMock()
    mock_response.content = (
        f"Hi Jane, I noticed TechCorp is scaling - I led similar growth at "
        f"PreviousCorp (15 hires, 90% retention). Would love to connect! "
        f"{CANDIDATE_CALENDLY} {CANDIDATE_SIGNATURE}"
    )
    return mock_response


@pytest.fixture
def mock_llm_inmail_response():
    """Mock LLM response for InMail message."""
    mock_response = MagicMock()
    mock_response.content = """{
        "subject": "Re: Engineering Growth",
        "body": "Hi Jane,\\n\\nI saw your post about TechCorp's scaling challenges. Having led similar growth at PreviousCorp - hiring 15 engineers in 6 months with 90% retention - I understand the complexities involved.\\n\\nI've just applied for the Senior Engineer role and would love to discuss how my experience could help your team.\\n\\nBest regards,\\nTaimoor"
    }"""
    return mock_response


# =============================================================================
# Test OutreachGenerationService Initialization
# =============================================================================


class TestOutreachGenerationServiceInit:
    """Tests for OutreachGenerationService initialization."""

    def test_operation_name_is_generate_outreach(self):
        """Should have correct operation_name."""
        service = OutreachGenerationService()
        assert service.operation_name == "generate-outreach"

    def test_accepts_db_client(self, mock_db_client):
        """Should accept optional db_client."""
        service = OutreachGenerationService(db_client=mock_db_client)
        assert service._db_client is mock_db_client

    def test_db_client_defaults_to_none(self):
        """Should default db_client to None."""
        service = OutreachGenerationService()
        assert service._db_client is None


# =============================================================================
# Test _get_contact Method
# =============================================================================


class TestOutreachGenerationServiceGetContact:
    """Tests for _get_contact method."""

    def test_extracts_primary_contact(self, sample_job_document, sample_contact):
        """Should extract primary contact by index."""
        service = OutreachGenerationService()
        contact = service._get_contact(sample_job_document, "primary", 0)

        assert contact is not None
        assert contact["name"] == sample_contact["name"]

    def test_extracts_secondary_contact(self, sample_job_document):
        """Should extract secondary contact by index."""
        service = OutreachGenerationService()
        contact = service._get_contact(sample_job_document, "secondary", 0)

        assert contact is not None
        assert contact["name"] == "Bob Johnson"

    def test_returns_none_for_invalid_index(self, sample_job_document):
        """Should return None for out-of-range index."""
        service = OutreachGenerationService()
        contact = service._get_contact(sample_job_document, "primary", 99)

        assert contact is None

    def test_returns_none_for_negative_index(self, sample_job_document):
        """Should return None for negative index."""
        service = OutreachGenerationService()
        contact = service._get_contact(sample_job_document, "primary", -1)

        assert contact is None

    def test_returns_none_for_empty_contacts(self, sample_job_id):
        """Should return None when contacts array is empty."""
        job = {"_id": ObjectId(sample_job_id), "primary_contacts": []}
        service = OutreachGenerationService()
        contact = service._get_contact(job, "primary", 0)

        assert contact is None

    def test_returns_none_for_missing_contacts(self, sample_job_id):
        """Should return None when contacts field is missing."""
        job = {"_id": ObjectId(sample_job_id)}
        service = OutreachGenerationService()
        contact = service._get_contact(job, "primary", 0)

        assert contact is None


# =============================================================================
# Test _build_outreach_context Method
# =============================================================================


class TestOutreachGenerationServiceBuildContext:
    """Tests for _build_outreach_context method."""

    def test_builds_context_with_all_fields(self, sample_job_document, sample_contact):
        """Should build context with all available fields."""
        service = OutreachGenerationService()
        context = service._build_outreach_context(sample_job_document, sample_contact)

        assert context["company"] == "TechCorp"
        assert context["role"] == "Senior Software Engineer"
        assert context["contact_name"] == "Jane Smith"
        assert context["contact_role"] == "Engineering Manager"
        assert context["contact_type"] == "hiring_manager"
        assert "Team scaling challenges" in context["pain_points"]

    def test_includes_company_signals(self, sample_job_document, sample_contact):
        """Should include company signals in context."""
        service = OutreachGenerationService()
        context = service._build_outreach_context(sample_job_document, sample_contact)

        assert "funding" in context["company_signals"].lower()
        assert "Series B" in context["company_signals"]

    def test_includes_achievements_from_stars(self, sample_job_document, sample_contact):
        """Should include achievements from selected STARs."""
        service = OutreachGenerationService()
        context = service._build_outreach_context(sample_job_document, sample_contact)

        assert "achievements" in context
        # Should include action and result from STAR
        assert "hiring" in context["achievements"].lower() or "engineers" in context["achievements"].lower()

    def test_handles_missing_pain_points(self, sample_job_document, sample_contact):
        """Should handle missing pain_points gracefully."""
        job = {**sample_job_document}
        del job["pain_points"]
        # Also remove from extracted_jd
        job["extracted_jd"] = {"title": "Test", "company": "Test"}

        service = OutreachGenerationService()
        context = service._build_outreach_context(job, sample_contact)

        assert "pain_points" in context
        assert context["pain_points"] == "Not available"

    def test_handles_missing_company_research(self, sample_job_document, sample_contact):
        """Should handle missing company_research gracefully."""
        job = {**sample_job_document}
        del job["company_research"]

        service = OutreachGenerationService()
        context = service._build_outreach_context(job, sample_contact)

        assert "company_signals" in context
        assert context["company_signals"] == "No recent signals available"


# =============================================================================
# Test _validate_connection_message Method
# =============================================================================


class TestOutreachGenerationServiceValidateConnection:
    """Tests for _validate_connection_message method."""

    def test_adds_signature_if_missing(self):
        """Should add signature if not present."""
        service = OutreachGenerationService()
        message = "Hi Jane, great to connect!"

        result = service._validate_connection_message(message)

        assert CANDIDATE_NAME in result
        assert result.endswith(CANDIDATE_SIGNATURE)

    def test_preserves_existing_signature(self):
        """Should not duplicate signature if present."""
        service = OutreachGenerationService()
        message = f"Hi Jane, great to connect! {CANDIDATE_SIGNATURE}"

        result = service._validate_connection_message(message)

        # Should only have one signature
        assert result.count(CANDIDATE_NAME) == 1

    def test_truncates_long_messages(self):
        """Should truncate messages exceeding character limit."""
        service = OutreachGenerationService()
        long_message = "A" * 400 + f" {CANDIDATE_SIGNATURE}"

        result = service._validate_connection_message(long_message)

        assert len(result) <= CONNECTION_CHAR_LIMIT

    def test_preserves_calendly_when_truncating(self):
        """Should try to preserve Calendly link when truncating."""
        service = OutreachGenerationService()
        # Message with Calendly but too long
        message = f"Hi Jane, {'A' * 200} {CANDIDATE_CALENDLY} {CANDIDATE_SIGNATURE}"

        result = service._validate_connection_message(message)

        # Message should be truncated but signature preserved
        assert len(result) <= CONNECTION_CHAR_LIMIT
        assert CANDIDATE_NAME in result


# =============================================================================
# Test Execute Method - Success Cases
# =============================================================================


class TestOutreachGenerationServiceExecuteSuccess:
    """Tests for successful execute method calls."""

    @pytest.fixture
    def service_with_mocks(self, sample_job_document):
        """Service with mocked dependencies."""
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=sample_job_document)
        service._persist_outreach = MagicMock(return_value=True)
        return service

    @pytest.mark.asyncio
    async def test_returns_operation_result(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should return OperationResult."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert isinstance(result, OperationResult)

    @pytest.mark.asyncio
    async def test_success_true_on_valid_input(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should return success=True for valid inputs."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_generates_connection_message(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should generate connection message when requested."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert "message" in result.data
        assert result.data["message_type"] == "connection"
        assert result.data["subject"] is None  # Connection has no subject

    @pytest.mark.asyncio
    async def test_generates_inmail_message(
        self, service_with_mocks, sample_job_id, mock_llm_inmail_response
    ):
        """Execute should generate InMail message when requested."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_inmail_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="inmail",
            )

        assert "message" in result.data
        assert result.data["message_type"] == "inmail"
        assert result.data["subject"] is not None

    @pytest.mark.asyncio
    async def test_persists_result_to_db(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should persist result to MongoDB."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        service_with_mocks._persist_outreach.assert_called_once()

    @pytest.mark.asyncio
    async def test_includes_contact_info_in_result(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should include contact info in result data."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result.data["contact_name"] == "Jane Smith"
        assert result.data["contact_role"] == "Engineering Manager"
        assert result.data["contact_type"] == "primary"
        assert result.data["contact_index"] == 0

    @pytest.mark.asyncio
    async def test_includes_char_count(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should include char_count in result data."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert "char_count" in result.data
        assert result.data["char_count"] > 0

    @pytest.mark.asyncio
    async def test_estimates_cost(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should estimate cost."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result.cost_usd >= 0

    @pytest.mark.asyncio
    async def test_includes_model_used(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should include model_used in result."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result.model_used is not None
        # BALANCED tier uses complex model for outreach
        assert result.model_used == "gpt-4o"

    @pytest.mark.asyncio
    async def test_includes_duration_ms(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should include duration_ms in result."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_generates_unique_run_id(
        self, service_with_mocks, sample_job_id, mock_llm_response
    ):
        """Execute should generate unique run_id."""
        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result1 = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )
            result2 = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result1.run_id != result2.run_id
        assert result1.run_id.startswith("op_generate-outreach_")


# =============================================================================
# Test Execute Method - Error Cases
# =============================================================================


class TestOutreachGenerationServiceExecuteErrors:
    """Tests for execute method error handling."""

    @pytest.mark.asyncio
    async def test_returns_error_for_not_found_job(self, sample_job_id):
        """Execute should return error result for non-existent job."""
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=None)

        result = await service.execute(
            job_id=sample_job_id,
            contact_index=0,
            contact_type="primary",
            tier=ModelTier.BALANCED,
            message_type="connection",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_contact_index(self, sample_job_id, sample_job_document):
        """Execute should return error result for invalid contact index."""
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=sample_job_document)

        result = await service.execute(
            job_id=sample_job_id,
            contact_index=99,  # Invalid index
            contact_type="primary",
            tier=ModelTier.BALANCED,
            message_type="connection",
        )

        assert result.success is False
        assert "Contact not found" in result.error

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_contacts(self, sample_job_id):
        """Execute should return error when no contacts exist."""
        job = {"_id": ObjectId(sample_job_id), "title": "Test Job"}
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=job)

        result = await service.execute(
            job_id=sample_job_id,
            contact_index=0,
            contact_type="primary",
            tier=ModelTier.BALANCED,
            message_type="connection",
        )

        assert result.success is False
        assert "Contact not found" in result.error

    @pytest.mark.asyncio
    async def test_handles_llm_exception(self, sample_job_id, sample_job_document):
        """Execute should handle LLM exceptions gracefully."""
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=sample_job_document)

        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.side_effect = Exception("LLM API error")
            mock_create_llm.return_value = mock_llm

            result = await service.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        assert result.success is False
        assert "LLM API error" in result.error

    @pytest.mark.asyncio
    async def test_continues_on_persist_failure(
        self, sample_job_id, sample_job_document, mock_llm_response
    ):
        """Execute should succeed even if persistence fails."""
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=sample_job_document)
        service._persist_outreach = MagicMock(return_value=False)

        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_llm_response
            mock_create_llm.return_value = mock_llm

            result = await service.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        # Processing succeeded even though persistence failed
        assert result.success is True
        assert result.data.get("persisted") is False


# =============================================================================
# Test _persist_outreach Method
# =============================================================================


class TestOutreachGenerationServicePersistOutreach:
    """Tests for _persist_outreach method."""

    def test_updates_connection_message(self, sample_job_id):
        """Should update connection message in correct contact."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        service = OutreachGenerationService(db_client=mock_client)

        with patch.dict("os.environ", {"MONGO_DB_NAME": "jobs"}):
            result = service._persist_outreach(
                job_id=sample_job_id,
                contact_type="primary",
                contact_index=0,
                message_type="connection",
                message="Test message",
            )

        assert result is True
        mock_collection.update_one.assert_called_once()

        # Check update document
        call_args = mock_collection.update_one.call_args[0][1]
        assert "primary_contacts.0.linkedin_connection_message" in call_args["$set"]

    def test_updates_inmail_with_subject(self, sample_job_id):
        """Should update InMail message and subject."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        service = OutreachGenerationService(db_client=mock_client)

        with patch.dict("os.environ", {"MONGO_DB_NAME": "jobs"}):
            result = service._persist_outreach(
                job_id=sample_job_id,
                contact_type="primary",
                contact_index=0,
                message_type="inmail",
                message="InMail body",
                subject="InMail subject",
            )

        assert result is True

        # Check update document includes both message and subject
        call_args = mock_collection.update_one.call_args[0][1]
        assert "primary_contacts.0.linkedin_inmail" in call_args["$set"]
        assert "primary_contacts.0.linkedin_inmail_subject" in call_args["$set"]

    def test_updates_secondary_contact(self, sample_job_id):
        """Should update secondary contact correctly."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value = MagicMock(modified_count=1)

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        service = OutreachGenerationService(db_client=mock_client)

        with patch.dict("os.environ", {"MONGO_DB_NAME": "jobs"}):
            result = service._persist_outreach(
                job_id=sample_job_id,
                contact_type="secondary",
                contact_index=2,
                message_type="connection",
                message="Test message",
            )

        assert result is True

        # Check correct path used
        call_args = mock_collection.update_one.call_args[0][1]
        assert "secondary_contacts.2.linkedin_connection_message" in call_args["$set"]

    def test_returns_false_on_invalid_job_id(self):
        """Should return False for invalid job_id."""
        service = OutreachGenerationService()

        result = service._persist_outreach(
            job_id="invalid-id",
            contact_type="primary",
            contact_index=0,
            message_type="connection",
            message="Test",
        )

        assert result is False

    def test_returns_false_on_db_error(self, sample_job_id):
        """Should return False on database error."""
        mock_collection = MagicMock()
        mock_collection.update_one.side_effect = Exception("DB error")

        mock_db = MagicMock()
        mock_db.__getitem__.return_value = mock_collection

        mock_client = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        service = OutreachGenerationService(db_client=mock_client)

        with patch.dict("os.environ", {"MONGO_DB_NAME": "jobs"}):
            result = service._persist_outreach(
                job_id=sample_job_id,
                contact_type="primary",
                contact_index=0,
                message_type="connection",
                message="Test",
            )

        assert result is False


# =============================================================================
# Test Tier Selection
# =============================================================================


class TestOutreachGenerationServiceTierSelection:
    """Tests for tier-based model selection."""

    def test_fast_tier_uses_mini_model(self):
        """FAST tier should use gpt-4o-mini."""
        service = OutreachGenerationService()
        model = service.get_model(ModelTier.FAST)
        assert model == "gpt-4o-mini"

    def test_balanced_tier_uses_gpt4o_model(self):
        """BALANCED tier should use gpt-4o for complex tasks."""
        service = OutreachGenerationService()
        model = service.get_model(ModelTier.BALANCED)
        assert model == "gpt-4o"

    def test_quality_tier_uses_claude_model(self):
        """QUALITY tier should use Claude for complex tasks."""
        service = OutreachGenerationService()
        model = service.get_model(ModelTier.QUALITY)
        assert "claude" in model.lower()


# =============================================================================
# Test Convenience Function
# =============================================================================


class TestGenerateOutreachConvenienceFunction:
    """Tests for generate_outreach convenience function."""

    @pytest.mark.asyncio
    async def test_creates_service_and_executes(
        self, sample_job_id, sample_job_document, mock_llm_response
    ):
        """generate_outreach should create service and call execute."""
        with patch.object(
            OutreachGenerationService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="generate-outreach",
                data={"message": "Test"},
                cost_usd=0.01,
                duration_ms=100,
            )

            result = await generate_outreach(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="connection",
            )

        mock_execute.assert_called_once_with(
            job_id=sample_job_id,
            contact_index=0,
            contact_type="primary",
            tier=ModelTier.BALANCED,
            message_type="connection",
        )
        assert isinstance(result, OperationResult)

    @pytest.mark.asyncio
    async def test_uses_default_tier(self, sample_job_id):
        """generate_outreach should default to BALANCED tier."""
        with patch.object(
            OutreachGenerationService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="generate-outreach",
                data={"message": "Test"},
                cost_usd=0.01,
                duration_ms=100,
            )

            await generate_outreach(
                job_id=sample_job_id,
                contact_index=0,
            )

        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["tier"] == ModelTier.BALANCED

    @pytest.mark.asyncio
    async def test_uses_default_message_type(self, sample_job_id):
        """generate_outreach should default to connection message type."""
        with patch.object(
            OutreachGenerationService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="generate-outreach",
                data={"message": "Test"},
                cost_usd=0.01,
                duration_ms=100,
            )

            await generate_outreach(
                job_id=sample_job_id,
                contact_index=0,
            )

        call_kwargs = mock_execute.call_args[1]
        assert call_kwargs["message_type"] == "connection"

    @pytest.mark.asyncio
    async def test_passes_db_client_to_service(self, sample_job_id, mock_db_client):
        """generate_outreach should pass db_client to service."""
        with patch.object(
            OutreachGenerationService, "__init__", return_value=None
        ) as mock_init, patch.object(
            OutreachGenerationService, "execute", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = OperationResult(
                success=True,
                run_id="op_test",
                operation="generate-outreach",
                data={"message": "Test"},
                cost_usd=0.01,
                duration_ms=100,
            )

            await generate_outreach(
                job_id=sample_job_id,
                contact_index=0,
                db_client=mock_db_client,
            )

        mock_init.assert_called_once_with(db_client=mock_db_client)


# =============================================================================
# Test InMail JSON Parsing
# =============================================================================


class TestOutreachGenerationServiceInMailParsing:
    """Tests for InMail JSON parsing."""

    @pytest.fixture
    def service_with_mocks(self, sample_job_document):
        """Service with mocked job fetching."""
        service = OutreachGenerationService()
        service._fetch_job = MagicMock(return_value=sample_job_document)
        service._persist_outreach = MagicMock(return_value=True)
        return service

    @pytest.mark.asyncio
    async def test_parses_valid_json_response(
        self, service_with_mocks, sample_job_id
    ):
        """Should parse valid JSON response correctly."""
        mock_response = MagicMock()
        mock_response.content = '{"subject": "Test Subject", "body": "Test body message"}'

        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="inmail",
            )

        assert result.success is True
        assert result.data["subject"] == "Test Subject"
        assert result.data["message"] == "Test body message"

    @pytest.mark.asyncio
    async def test_handles_non_json_response(
        self, service_with_mocks, sample_job_id
    ):
        """Should handle non-JSON response gracefully."""
        mock_response = MagicMock()
        mock_response.content = "This is not JSON, just plain text message."

        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="inmail",
            )

        # Should succeed with fallback subject
        assert result.success is True
        assert result.data["message"] == "This is not JSON, just plain text message."
        assert result.data["subject"] is not None  # Fallback subject

    @pytest.mark.asyncio
    async def test_truncates_long_subject(
        self, service_with_mocks, sample_job_id
    ):
        """Should truncate subject if too long."""
        mock_response = MagicMock()
        mock_response.content = '{"subject": "This is a very long subject line that exceeds the maximum allowed length for InMail subjects", "body": "Test body"}'

        with patch(
            "src.common.llm_factory.create_tracked_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_response
            mock_create_llm.return_value = mock_llm

            result = await service_with_mocks.execute(
                job_id=sample_job_id,
                contact_index=0,
                contact_type="primary",
                tier=ModelTier.BALANCED,
                message_type="inmail",
            )

        assert result.success is True
        assert len(result.data["subject"]) <= 50
