"""
Unit tests for CVGenerationService.

Tests the CV generation service that wraps Layer 6 V2 orchestrator
and CoverLetterGenerator for button-triggered generation with tier-based
model selection.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from src.services.cv_generation_service import CVGenerationService
from src.services.operation_base import OperationResult
from src.common.model_tiers import ModelTier


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db_client():
    """Create a mock MongoDB client."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_collection = MagicMock()

    mock_client.__getitem__ = MagicMock(return_value=mock_db)
    mock_db.__getitem__ = MagicMock(return_value=mock_collection)

    return mock_client


@pytest.fixture
def service(mock_db_client):
    """Create a CVGenerationService with mocked DB."""
    return CVGenerationService(db_client=mock_db_client)


@pytest.fixture
def sample_job():
    """Sample job document from MongoDB."""
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "title": "Engineering Manager",
        "company": "Test Corp",
        "jd_text": "We are looking for an Engineering Manager to lead...",
        "extracted_jd": {
            "title": "Engineering Manager",
            "company": "Test Corp",
            "role_category": "engineering_manager",
            "seniority_level": "senior",
            "top_keywords": ["Python", "Kubernetes", "Leadership"],
            "implied_pain_points": ["Scale team", "Improve delivery"],
            "success_metrics": ["Team velocity", "Retention"],
            "technical_skills": ["Python", "AWS"],
            "soft_skills": ["Leadership"],
            "responsibilities": ["Lead team of 10 engineers"],
            "qualifications": ["5+ years experience"],
            "nice_to_haves": ["MBA"],
            "competency_weights": {
                "delivery": 30,
                "process": 20,
                "architecture": 25,
                "leadership": 25,
            },
        },
        "jd_annotations": {
            "annotations": [
                {"id": "ann1", "text": "Python", "relevance": "core_strength"}
            ]
        },
        "fit_score": 85,
        "fit_rationale": "Strong leadership and technical background.",
        "location": "Munich, DE",
        # Fields for cover letter generation
        "pain_points": ["Scale engineering team", "Improve delivery velocity"],
        "strategic_needs": ["Build platform team", "Establish SRE practices"],
        "selected_stars": [
            {
                "id": "star1",
                "company": "Previous Corp",
                "role": "Tech Lead",
                "situation": "Team needed to scale",
                "task": "Lead hiring and onboarding",
                "actions": "Implemented structured interview process",
                "results": "Grew team from 5 to 15 engineers",
                "metrics": "3x team growth in 12 months",
            }
        ],
        "company_research": {
            "summary": "Test Corp is a growing tech company.",
            "signals": [{"type": "funding", "description": "Series B raised"}],
            "url": "https://testcorp.com",
        },
        "role_research": {
            "summary": "Engineering Manager to lead platform team.",
            "business_impact": ["Drive platform reliability", "Reduce incidents"],
            "why_now": "Company expanding after Series B",
        },
        "candidate_profile": "# John Doe\nExperienced Engineering Manager...",
    }


@pytest.fixture
def sample_cv_result():
    """Sample result from CVGeneratorV2."""
    return {
        "cv_text": "# JOHN DOE\n\n## Professional Summary\n\nExperienced...",
        "cv_path": "outputs/test_corp/cv_engineering_manager.md",
        "cv_reasoning": "Generated CV with focus on leadership...",
        "cv_grade_result": {
            "composite_score": 8.7,
            "passed": True,
            "dimension_scores": [],
        },
        "errors": None,
    }


# ============================================================================
# TEST CLASS: CVGenerationService
# ============================================================================


class TestCVGenerationServiceInit:
    """Tests for CVGenerationService initialization."""

    def test_creates_with_default_db_client(self):
        """Should create service without explicit DB client."""
        service = CVGenerationService()
        assert service._db_client is None

    def test_creates_with_provided_db_client(self, mock_db_client):
        """Should use provided DB client."""
        service = CVGenerationService(db_client=mock_db_client)
        assert service._db_client is mock_db_client

    def test_operation_name_is_set(self, service):
        """Should have correct operation_name."""
        assert service.operation_name == "generate-cv"


class TestCVGenerationServiceGetModel:
    """Tests for model selection based on tier."""

    def test_get_model_fast_tier(self, service):
        """FAST tier should return gpt-4o-mini for complex tasks."""
        model = service.get_model(ModelTier.FAST)
        assert model == "gpt-4o-mini"

    def test_get_model_balanced_tier(self, service):
        """BALANCED tier should return gpt-4o for complex tasks."""
        model = service.get_model(ModelTier.BALANCED)
        assert model == "gpt-4o"

    def test_get_model_quality_tier(self, service):
        """QUALITY tier should return claude-sonnet for complex tasks."""
        model = service.get_model(ModelTier.QUALITY)
        assert model == "claude-opus-4-5-20251101"


class TestCVGenerationServiceFetchJob:
    """Tests for job fetching from MongoDB."""

    def test_fetch_job_returns_document(self, service, mock_db_client, sample_job):
        """Should return job document when found."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        result = service._fetch_job(str(sample_job["_id"]))

        assert result == sample_job
        mock_collection.find_one.assert_called_once()

    def test_fetch_job_returns_none_for_not_found(self, service, mock_db_client):
        """Should return None when job not found."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        result = service._fetch_job("507f1f77bcf86cd799439011")

        assert result is None

    def test_fetch_job_returns_none_for_invalid_id(self, service):
        """Should return None for invalid ObjectId format."""
        result = service._fetch_job("invalid-id-format")
        assert result is None


class TestCVGenerationServiceValidateJob:
    """Tests for job data validation."""

    def test_validate_job_passes_with_extracted_jd(self, service, sample_job):
        """Should pass validation when extracted_jd present."""
        error = service._validate_job_data(sample_job)
        assert error is None

    def test_validate_job_passes_with_jd_text(self, service):
        """Should pass validation when jd_text present but no extracted_jd."""
        job = {
            "_id": ObjectId(),
            "title": "Manager",
            "company": "Test",
            "jd_text": "Some job description text",
        }
        error = service._validate_job_data(job)
        assert error is None

    def test_validate_job_passes_with_description(self, service):
        """Should pass validation when description present."""
        job = {
            "_id": ObjectId(),
            "description": "Job description here",
        }
        error = service._validate_job_data(job)
        assert error is None

    def test_validate_job_fails_without_jd(self, service):
        """Should fail validation when no JD text found."""
        job = {
            "_id": ObjectId(),
            "title": "Manager",
            "company": "Test",
        }
        error = service._validate_job_data(job)
        assert error is not None
        assert "job description" in error.lower()


class TestCVGenerationServiceBuildState:
    """Tests for JobState building."""

    def test_build_state_includes_basic_fields(self, service, sample_job):
        """Should include job_id, title, company in state."""
        state = service._build_state(sample_job, use_annotations=True)

        assert state["job_id"] == str(sample_job["_id"])
        assert state["title"] == "Engineering Manager"
        assert state["company"] == "Test Corp"

    def test_build_state_includes_extracted_jd(self, service, sample_job):
        """Should include extracted_jd in state."""
        state = service._build_state(sample_job, use_annotations=True)

        assert "extracted_jd" in state
        assert state["extracted_jd"]["role_category"] == "engineering_manager"

    def test_build_state_includes_annotations_when_enabled(self, service, sample_job):
        """Should include jd_annotations when use_annotations=True."""
        state = service._build_state(sample_job, use_annotations=True)

        assert "jd_annotations" in state
        assert len(state["jd_annotations"]["annotations"]) == 1

    def test_build_state_excludes_annotations_when_disabled(self, service, sample_job):
        """Should exclude jd_annotations when use_annotations=False."""
        state = service._build_state(sample_job, use_annotations=False)

        assert "jd_annotations" not in state

    def test_build_state_includes_fit_score(self, service, sample_job):
        """Should include fit_score if present."""
        state = service._build_state(sample_job, use_annotations=False)

        assert state["fit_score"] == 85

    def test_build_state_uses_fallback_jd_text(self, service):
        """Should use jd_text as job_description fallback."""
        job = {
            "_id": ObjectId(),
            "title": "Manager",
            "company": "Test",
            "jd_text": "JD text content here",
        }
        state = service._build_state(job, use_annotations=False)

        assert state["job_description"] == "JD text content here"


class TestCVGenerationServiceBuildEditorState:
    """Tests for CV editor state building."""

    def test_build_editor_state_returns_doc_structure(self, service):
        """Should return prosemirror doc structure."""
        state = service._build_cv_editor_state("# Heading\n\nSome text")

        assert "type" in state
        assert state["type"] == "doc"
        assert "content" in state

    def test_build_editor_state_handles_empty_text(self, service):
        """Should return empty doc for empty text."""
        state = service._build_cv_editor_state("")

        assert state == {"type": "doc", "content": []}

    def test_build_editor_state_handles_none(self, service):
        """Should handle None input."""
        state = service._build_cv_editor_state(None)

        assert state == {"type": "doc", "content": []}


class TestCVGenerationServicePersistResult:
    """Tests for persisting CV results to MongoDB."""

    def test_persist_result_updates_document(self, service, mock_db_client):
        """Should update job document with CV data."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        job_id = "507f1f77bcf86cd799439011"
        cv_text = "# CV Content"
        cv_editor_state = {"type": "doc", "content": []}
        cv_result = {"cv_path": "/path/to/cv.md", "cv_reasoning": "reasoning"}

        result = service._persist_cv_result(job_id, cv_text, cv_editor_state, cv_result)

        assert result is True
        mock_collection.update_one.assert_called_once()

        # Verify the update includes expected fields
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert update_doc["cv_text"] == cv_text
        assert update_doc["cv_editor_state"] == cv_editor_state
        assert update_doc["cv_path"] == "/path/to/cv.md"

    def test_persist_result_returns_false_on_no_update(self, service, mock_db_client):
        """Should return False when no document updated."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value.modified_count = 0
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        result = service._persist_cv_result(
            "507f1f77bcf86cd799439011",
            "cv text",
            {},
            {},
        )

        assert result is False

    def test_persist_result_returns_false_for_invalid_id(self, service):
        """Should return False for invalid job ID."""
        result = service._persist_cv_result("invalid-id", "cv text", {}, {})
        assert result is False


class TestCVGenerationServiceExecute:
    """Tests for the main execute method."""

    @pytest.mark.asyncio
    async def test_execute_returns_operation_result(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should return OperationResult on success."""
        # Setup mocks
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', return_value=sample_cv_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.QUALITY,
            )

        assert isinstance(result, OperationResult)
        assert result.success is True
        assert result.operation == "generate-cv"

    @pytest.mark.asyncio
    async def test_execute_includes_cv_text_in_data(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should include cv_text in result data."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', return_value=sample_cv_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.BALANCED,
            )

        assert "cv_text" in result.data
        assert result.data["cv_text"] == sample_cv_result["cv_text"]

    @pytest.mark.asyncio
    async def test_execute_includes_cv_editor_state_in_data(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should include cv_editor_state in result data."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', return_value=sample_cv_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
            )

        assert "cv_editor_state" in result.data
        assert "type" in result.data["cv_editor_state"]

    @pytest.mark.asyncio
    async def test_execute_returns_error_for_missing_job(
        self, service, mock_db_client
    ):
        """Should return error when job not found."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = None
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.FAST,
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_error_for_missing_jd(
        self, service, mock_db_client
    ):
        """Should return error when job has no JD."""
        job_without_jd = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "title": "Manager",
            "company": "Test",
        }
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = job_without_jd
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        result = await service.execute(
            job_id="507f1f77bcf86cd799439011",
            tier=ModelTier.FAST,
        )

        assert result.success is False
        assert "description" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_error_for_generator_errors(
        self, service, mock_db_client, sample_job
    ):
        """Should return error when CV generator fails."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        cv_result_with_error = {
            "cv_text": None,
            "errors": ["Generation failed: LLM timeout"],
        }

        with patch.object(service, '_generate_cv', return_value=cv_result_with_error):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
            )

        assert result.success is False
        assert "LLM timeout" in result.error

    @pytest.mark.asyncio
    async def test_execute_includes_model_used(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should include model_used in result."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', return_value=sample_cv_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.QUALITY,
            )

        assert result.model_used == "claude-opus-4-5-20251101"

    @pytest.mark.asyncio
    async def test_execute_includes_cost_estimate(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should include cost estimate in result."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', return_value=sample_cv_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
            )

        assert result.cost_usd > 0

    @pytest.mark.asyncio
    async def test_execute_includes_duration(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should include duration_ms in result."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', return_value=sample_cv_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
            )

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_passes_annotations_when_enabled(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should pass annotations to generator when use_annotations=True."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        generated_state = None

        def capture_generate(state, model, progress_callback=None):
            nonlocal generated_state
            generated_state = state
            return sample_cv_result

        with patch.object(service, '_generate_cv', side_effect=capture_generate):
            await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
                use_annotations=True,
            )

        assert "jd_annotations" in generated_state

    @pytest.mark.asyncio
    async def test_execute_excludes_annotations_when_disabled(
        self, service, mock_db_client, sample_job, sample_cv_result
    ):
        """Should not pass annotations when use_annotations=False."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        generated_state = None

        def capture_generate(state, model, progress_callback=None):
            nonlocal generated_state
            generated_state = state
            return sample_cv_result

        with patch.object(service, '_generate_cv', side_effect=capture_generate):
            await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
                use_annotations=False,
            )

        assert "jd_annotations" not in generated_state

    @pytest.mark.asyncio
    async def test_execute_handles_exception_gracefully(
        self, service, mock_db_client, sample_job
    ):
        """Should catch exceptions and return error result."""
        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(service, '_generate_cv', side_effect=RuntimeError("Unexpected error")):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
            )

        assert result.success is False
        assert "Unexpected error" in result.error


class TestCVGenerationServiceRunId:
    """Tests for run ID generation."""

    def test_create_run_id_includes_operation_name(self, service):
        """Run ID should include operation name."""
        run_id = service.create_run_id()
        assert "generate-cv" in run_id

    def test_create_run_id_is_unique(self, service):
        """Run IDs should be unique."""
        ids = [service.create_run_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestCVGenerationServiceCostEstimate:
    """Tests for cost estimation."""

    def test_estimate_cost_fast_tier_is_cheapest(self, service):
        """FAST tier should be cheapest."""
        fast = service.estimate_cost(ModelTier.FAST, 1000, 500)
        balanced = service.estimate_cost(ModelTier.BALANCED, 1000, 500)
        quality = service.estimate_cost(ModelTier.QUALITY, 1000, 500)

        assert fast < balanced < quality

    def test_estimate_cost_scales_with_tokens(self, service):
        """Cost should scale with token count."""
        cost_1k = service.estimate_cost(ModelTier.FAST, 1000, 1000)
        cost_2k = service.estimate_cost(ModelTier.FAST, 2000, 2000)

        assert cost_2k == pytest.approx(cost_1k * 2)


class TestCVGenerationServiceCoverLetter:
    """Tests for cover letter generation integration."""

    def test_generate_cover_letter_calls_generator(self, service, sample_job):
        """Should call CoverLetterGenerator with state."""
        state = service._build_state(sample_job, use_annotations=True)

        with patch(
            "src.layer6.cover_letter_generator.CoverLetterGenerator"
        ) as MockGenerator:
            mock_instance = MockGenerator.return_value
            mock_instance.generate_cover_letter.return_value = "Cover letter text"

            result = service._generate_cover_letter(state)

            assert result == "Cover letter text"
            mock_instance.generate_cover_letter.assert_called_once_with(state)

    def test_generate_cover_letter_returns_none_on_value_error(self, service, sample_job):
        """Should return None when CoverLetterGenerator raises ValueError."""
        state = service._build_state(sample_job, use_annotations=True)

        with patch(
            "src.layer6.cover_letter_generator.CoverLetterGenerator"
        ) as MockGenerator:
            mock_instance = MockGenerator.return_value
            mock_instance.generate_cover_letter.side_effect = ValueError(
                "Validation failed"
            )

            result = service._generate_cover_letter(state)

            assert result is None

    def test_generate_cover_letter_returns_none_on_exception(self, service, sample_job):
        """Should return None when CoverLetterGenerator raises any exception."""
        state = service._build_state(sample_job, use_annotations=True)

        with patch(
            "src.layer6.cover_letter_generator.CoverLetterGenerator"
        ) as MockGenerator:
            mock_instance = MockGenerator.return_value
            mock_instance.generate_cover_letter.side_effect = RuntimeError("LLM failure")

            result = service._generate_cover_letter(state)

            assert result is None

    def test_build_state_includes_cover_letter_fields(self, service, sample_job):
        """Should include fields required for cover letter generation."""
        state = service._build_state(sample_job, use_annotations=True)

        assert state.get("pain_points") == sample_job["pain_points"]
        assert state.get("strategic_needs") == sample_job["strategic_needs"]
        assert state.get("selected_stars") == sample_job["selected_stars"]
        assert state.get("company_research") == sample_job["company_research"]
        assert state.get("role_research") == sample_job["role_research"]
        assert state.get("fit_rationale") == sample_job["fit_rationale"]
        assert state.get("candidate_profile") == sample_job["candidate_profile"]

    def test_build_state_loads_candidate_profile_from_file_when_missing(
        self, service, sample_job
    ):
        """Should load candidate_profile from file when not in MongoDB."""
        # Remove candidate_profile from job
        job_without_profile = {**sample_job}
        del job_without_profile["candidate_profile"]

        # Mock file loading
        with patch.object(
            service, "_load_candidate_profile", return_value="Profile from file"
        ):
            state = service._build_state(job_without_profile, use_annotations=True)
            assert state.get("candidate_profile") == "Profile from file"

    def test_load_candidate_profile_reads_from_config_path(self, service, tmp_path):
        """Should read candidate profile from configured path."""
        # Create a temp profile file
        profile_content = "My candidate profile\nWith multiple lines"
        profile_file = tmp_path / "test-cv.md"
        profile_file.write_text(profile_content)

        # Patch Config to point to our temp file
        with patch("src.common.config.Config.CANDIDATE_PROFILE_PATH", str(profile_file)):
            result = service._load_candidate_profile()
            assert result == profile_content

    def test_load_candidate_profile_returns_none_when_no_file(self, service, tmp_path):
        """Should return None when no profile file exists."""
        # Use a path that doesn't exist
        nonexistent_path = tmp_path / "does-not-exist.md"

        with patch(
            "src.common.config.Config.CANDIDATE_PROFILE_PATH", str(nonexistent_path)
        ):
            result = service._load_candidate_profile()
            # Should be None since neither config path nor fallback exists
            assert result is None


class TestCVGenerationServicePersistWithCoverLetter:
    """Tests for persisting CV results with cover letter."""

    def test_persist_result_includes_cover_letter(self, service, mock_db_client):
        """Should include cover_letter in MongoDB update when provided."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        job_id = "507f1f77bcf86cd799439011"
        cv_text = "# CV Content"
        cv_editor_state = {"type": "doc", "content": []}
        cv_result = {"cv_path": "/path/to/cv.md", "cv_reasoning": "reasoning"}
        cover_letter = "Dear Hiring Manager,\n\nThis is my cover letter."

        result = service._persist_cv_result(
            job_id, cv_text, cv_editor_state, cv_result, cover_letter
        )

        assert result is True
        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert update_doc["cover_letter"] == cover_letter
        assert "cover_letter_generated_at" in update_doc

    def test_persist_result_excludes_cover_letter_when_none(self, service, mock_db_client):
        """Should not include cover_letter in update when None."""
        mock_collection = MagicMock()
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        job_id = "507f1f77bcf86cd799439011"
        cv_text = "# CV Content"
        cv_editor_state = {"type": "doc", "content": []}
        cv_result = {"cv_path": "/path/to/cv.md", "cv_reasoning": "reasoning"}

        service._persist_cv_result(job_id, cv_text, cv_editor_state, cv_result, None)

        call_args = mock_collection.update_one.call_args
        update_doc = call_args[0][1]["$set"]
        assert "cover_letter" not in update_doc
        assert "cover_letter_generated_at" not in update_doc


class TestCVGenerationServiceIntegration:
    """Integration-style tests for complete execution flow."""

    @pytest.mark.asyncio
    async def test_full_execution_flow_success(
        self, mock_db_client, sample_job, sample_cv_result
    ):
        """Test complete successful execution flow."""
        service = CVGenerationService(db_client=mock_db_client)

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(
            service, "_generate_cv", return_value=sample_cv_result
        ), patch.object(service, "_generate_cover_letter", return_value="Cover letter text"):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.QUALITY,
                use_annotations=True,
            )

        # Verify complete result structure
        assert result.success is True
        assert result.operation == "generate-cv"
        assert result.run_id.startswith("op_generate-cv_")
        assert result.model_used == "claude-opus-4-5-20251101"
        assert result.cost_usd > 0
        assert result.duration_ms >= 0
        assert result.error is None

        # Verify data contains expected fields
        assert result.data["cv_text"] == sample_cv_result["cv_text"]
        assert "cv_editor_state" in result.data
        assert result.data["cv_path"] == sample_cv_result["cv_path"]
        assert result.data["cv_reasoning"] == sample_cv_result["cv_reasoning"]
        assert result.data["word_count"] > 0
        assert result.data["cover_letter"] == "Cover letter text"

    @pytest.mark.asyncio
    async def test_full_execution_flow_with_cover_letter_failure(
        self, mock_db_client, sample_job, sample_cv_result
    ):
        """Test that CV generation succeeds even when cover letter fails."""
        service = CVGenerationService(db_client=mock_db_client)

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(
            service, "_generate_cv", return_value=sample_cv_result
        ), patch.object(service, "_generate_cover_letter", return_value=None):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.QUALITY,
                use_annotations=True,
            )

        # CV generation should still succeed
        assert result.success is True
        assert result.data["cv_text"] == sample_cv_result["cv_text"]
        # Cover letter should be None
        assert result.data["cover_letter"] is None

    @pytest.mark.asyncio
    async def test_full_execution_includes_cover_letter_in_layer_status(
        self, mock_db_client, sample_job, sample_cv_result
    ):
        """Test that layer_status includes cover_letter status."""
        service = CVGenerationService(db_client=mock_db_client)

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_collection.update_one.return_value.modified_count = 1
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        with patch.object(
            service, "_generate_cv", return_value=sample_cv_result
        ), patch.object(service, "_generate_cover_letter", return_value="Cover letter text"):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.QUALITY,
            )

        layer_status = result.data["layer_status"]
        assert "cover_letter" in layer_status
        assert layer_status["cover_letter"]["status"] == "success"

    @pytest.mark.asyncio
    async def test_full_execution_flow_error(self, mock_db_client, sample_job):
        """Test complete error execution flow."""
        service = CVGenerationService(db_client=mock_db_client)

        mock_collection = MagicMock()
        mock_collection.find_one.return_value = sample_job
        mock_db_client.__getitem__.return_value.__getitem__.return_value = mock_collection

        cv_error_result = {
            "cv_text": None,
            "errors": ["Generator failed: Rate limit exceeded"],
        }

        with patch.object(service, "_generate_cv", return_value=cv_error_result):
            result = await service.execute(
                job_id=str(sample_job["_id"]),
                tier=ModelTier.FAST,
            )

        assert result.success is False
        assert result.operation == "generate-cv"
        assert "Rate limit exceeded" in result.error
        assert result.data == {}
