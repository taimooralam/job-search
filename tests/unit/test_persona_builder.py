"""
Unit tests for PersonaBuilder module.

Tests persona synthesis from identity annotations and prompt injection.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.common.persona_builder import (
    PersonaBuilder,
    SynthesizedPersona,
    get_persona_guidance,
    IDENTITY_STRENGTH_ORDER,
)


# ===== Fixtures =====


@pytest.fixture
def builder():
    """Create a PersonaBuilder instance."""
    return PersonaBuilder()


@pytest.fixture
def sample_core_identity_annotation():
    """Create a sample core_identity annotation."""
    return {
        "id": "ann1",
        "target": {"text": "solutions architect experience"},
        "matching_skill": "Solutions Architect",
        "identity": "core_identity",
        "is_active": True,
    }


@pytest.fixture
def sample_strong_identity_annotation():
    """Create a sample strong_identity annotation."""
    return {
        "id": "ann2",
        "target": {"text": "team leadership"},
        "matching_skill": "Team Leadership",
        "identity": "strong_identity",
        "is_active": True,
    }


@pytest.fixture
def sample_developing_annotation():
    """Create a sample developing annotation."""
    return {
        "id": "ann3",
        "target": {"text": "cloud migration"},
        "matching_skill": "Cloud Migration",
        "identity": "developing",
        "is_active": True,
    }


@pytest.fixture
def sample_not_identity_annotation():
    """Create a sample not_identity annotation."""
    return {
        "id": "ann4",
        "target": {"text": "data engineering"},
        "matching_skill": "Data Engineering",
        "identity": "not_identity",
        "is_active": True,
    }


@pytest.fixture
def sample_inactive_annotation():
    """Create a sample inactive annotation."""
    return {
        "id": "ann5",
        "target": {"text": "machine learning"},
        "matching_skill": "Machine Learning",
        "identity": "core_identity",
        "is_active": False,  # Inactive - should be ignored
    }


@pytest.fixture
def sample_jd_annotations_with_synthesized():
    """Create sample jd_annotations with stored synthesized persona."""
    return {
        "annotations": [],
        "synthesized_persona": {
            "persona_statement": "A solutions architect who leads engineering teams through complex cloud transformations",
            "is_user_edited": False,
            "updated_at": datetime.utcnow(),
        },
    }


# ===== Test SynthesizedPersona dataclass =====


class TestSynthesizedPersona:
    """Tests for SynthesizedPersona dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary for MongoDB storage."""
        persona = SynthesizedPersona(
            persona_statement="A solutions architect",
            primary_identity="Solutions Architect",
            secondary_identities=["Team Leadership"],
            source_annotations=["ann1", "ann2"],
            is_user_edited=True,
            synthesized_at=datetime(2025, 1, 1, 12, 0, 0),
        )

        result = persona.to_dict()

        assert result["persona_statement"] == "A solutions architect"
        assert result["primary_identity"] == "Solutions Architect"
        assert result["secondary_identities"] == ["Team Leadership"]
        assert result["source_annotations"] == ["ann1", "ann2"]
        assert result["is_user_edited"] is True
        assert result["synthesized_at"] == datetime(2025, 1, 1, 12, 0, 0)

    def test_from_dict(self):
        """Test creation from dictionary (MongoDB document)."""
        data = {
            "persona_statement": "A solutions architect",
            "primary_identity": "Solutions Architect",
            "secondary_identities": ["Team Leadership"],
            "source_annotations": ["ann1", "ann2"],
            "is_user_edited": True,
            "synthesized_at": datetime(2025, 1, 1, 12, 0, 0),
        }

        persona = SynthesizedPersona.from_dict(data)

        assert persona.persona_statement == "A solutions architect"
        assert persona.primary_identity == "Solutions Architect"
        assert persona.secondary_identities == ["Team Leadership"]
        assert persona.source_annotations == ["ann1", "ann2"]
        assert persona.is_user_edited is True
        assert persona.synthesized_at == datetime(2025, 1, 1, 12, 0, 0)

    def test_from_dict_with_missing_fields(self):
        """Test creation from partial dictionary with defaults."""
        data = {
            "persona_statement": "A solutions architect",
        }

        persona = SynthesizedPersona.from_dict(data)

        assert persona.persona_statement == "A solutions architect"
        assert persona.primary_identity == ""
        assert persona.secondary_identities == []
        assert persona.source_annotations == []
        assert persona.is_user_edited is False
        assert persona.synthesized_at is None


# ===== Test PersonaBuilder extraction methods =====


class TestPersonaBuilderExtraction:
    """Tests for PersonaBuilder annotation extraction methods."""

    def test_extract_identity_annotations_no_annotations(self, builder):
        """Test extraction with no annotations returns empty groups."""
        jd_annotations = {"annotations": []}

        grouped = builder._extract_identity_annotations(jd_annotations)

        assert grouped["core_identity"] == []
        assert grouped["strong_identity"] == []
        assert grouped["developing"] == []

    def test_extract_identity_annotations_groups_by_strength(
        self,
        builder,
        sample_core_identity_annotation,
        sample_strong_identity_annotation,
        sample_developing_annotation,
    ):
        """Test extraction groups annotations by identity strength."""
        jd_annotations = {
            "annotations": [
                sample_core_identity_annotation,
                sample_strong_identity_annotation,
                sample_developing_annotation,
            ]
        }

        grouped = builder._extract_identity_annotations(jd_annotations)

        assert len(grouped["core_identity"]) == 1
        assert len(grouped["strong_identity"]) == 1
        assert len(grouped["developing"]) == 1
        assert grouped["core_identity"][0]["matching_skill"] == "Solutions Architect"

    def test_extract_identity_annotations_ignores_inactive(
        self, builder, sample_inactive_annotation
    ):
        """Test extraction ignores inactive annotations."""
        jd_annotations = {"annotations": [sample_inactive_annotation]}

        grouped = builder._extract_identity_annotations(jd_annotations)

        assert grouped["core_identity"] == []
        assert grouped["strong_identity"] == []
        assert grouped["developing"] == []

    def test_extract_identity_annotations_ignores_not_identity(
        self, builder, sample_not_identity_annotation
    ):
        """Test extraction ignores not_identity and peripheral annotations."""
        jd_annotations = {"annotations": [sample_not_identity_annotation]}

        grouped = builder._extract_identity_annotations(jd_annotations)

        # not_identity is not in the grouped dict keys
        assert grouped["core_identity"] == []
        assert grouped["strong_identity"] == []
        assert grouped["developing"] == []


class TestPersonaBuilderTextExtraction:
    """Tests for PersonaBuilder text extraction from annotations."""

    def test_get_identity_text_prefers_matching_skill(self, builder):
        """Test that matching_skill is preferred over target text."""
        annotation = {
            "target": {"text": "We need someone with solutions architect experience"},
            "matching_skill": "Solutions Architect",
        }

        result = builder._get_identity_text(annotation)

        assert result == "Solutions Architect"

    def test_get_identity_text_falls_back_to_target(self, builder):
        """Test fallback to target text when no matching_skill."""
        annotation = {
            "target": {"text": "cloud expertise"},
            "matching_skill": "",
        }

        result = builder._get_identity_text(annotation)

        assert result == "cloud expertise"

    def test_get_identity_text_truncates_long_text(self, builder):
        """Test that long target text is truncated."""
        long_text = "This is a very long text that exceeds the fifty character limit and should be truncated"
        annotation = {
            "target": {"text": long_text},
            "matching_skill": "",
        }

        result = builder._get_identity_text(annotation)

        assert len(result) == 50  # 47 chars + "..."
        assert result.endswith("...")


class TestPersonaBuilderContextBuilding:
    """Tests for PersonaBuilder identity context building."""

    def test_build_identity_context_empty(self, builder):
        """Test building context with no annotations."""
        grouped = {"core_identity": [], "strong_identity": [], "developing": []}

        result = builder._build_identity_context(grouped)

        assert result == ""

    def test_build_identity_context_with_core_only(
        self, builder, sample_core_identity_annotation
    ):
        """Test building context with only core identity."""
        grouped = {
            "core_identity": [sample_core_identity_annotation],
            "strong_identity": [],
            "developing": [],
        }

        result = builder._build_identity_context(grouped)

        assert "Primary (core identity): Solutions Architect" in result

    def test_build_identity_context_with_all_levels(
        self,
        builder,
        sample_core_identity_annotation,
        sample_strong_identity_annotation,
        sample_developing_annotation,
    ):
        """Test building context with all identity levels."""
        grouped = {
            "core_identity": [sample_core_identity_annotation],
            "strong_identity": [sample_strong_identity_annotation],
            "developing": [sample_developing_annotation],
        }

        result = builder._build_identity_context(grouped)

        assert "Primary (core identity): Solutions Architect" in result
        assert "Secondary (strong identity): Team Leadership" in result
        assert "Developing: Cloud Migration" in result


class TestPersonaBuilderHasAnnotations:
    """Tests for has_identity_annotations method."""

    def test_has_identity_annotations_with_none(self, builder):
        """Test returns False when no annotations."""
        jd_annotations = {"annotations": []}

        result = builder.has_identity_annotations(jd_annotations)

        assert result is False

    def test_has_identity_annotations_with_core(
        self, builder, sample_core_identity_annotation
    ):
        """Test returns True when core_identity annotation exists."""
        jd_annotations = {"annotations": [sample_core_identity_annotation]}

        result = builder.has_identity_annotations(jd_annotations)

        assert result is True

    def test_has_identity_annotations_only_not_identity(
        self, builder, sample_not_identity_annotation
    ):
        """Test returns False when only not_identity annotations exist."""
        jd_annotations = {"annotations": [sample_not_identity_annotation]}

        result = builder.has_identity_annotations(jd_annotations)

        assert result is False

    def test_has_identity_annotations_only_inactive(
        self, builder, sample_inactive_annotation
    ):
        """Test returns False when only inactive annotations exist."""
        jd_annotations = {"annotations": [sample_inactive_annotation]}

        result = builder.has_identity_annotations(jd_annotations)

        assert result is False


# ===== Test PersonaBuilder synthesis (mocked LLM) =====


class TestPersonaBuilderSynthesis:
    """Tests for PersonaBuilder.synthesize() with mocked LLM."""

    @pytest.mark.asyncio
    async def test_synthesize_returns_none_for_no_annotations(self, builder):
        """Test synthesize returns None when no identity annotations."""
        jd_annotations = {"annotations": []}

        result = await builder.synthesize(jd_annotations)

        assert result is None

    @pytest.mark.asyncio
    async def test_synthesize_returns_none_for_only_not_identity(
        self, builder, sample_not_identity_annotation
    ):
        """Test synthesize returns None when only not_identity annotations."""
        jd_annotations = {"annotations": [sample_not_identity_annotation]}

        result = await builder.synthesize(jd_annotations)

        assert result is None

    @pytest.mark.asyncio
    async def test_synthesize_calls_llm_with_core_identity(
        self, builder, sample_core_identity_annotation
    ):
        """Test synthesize calls LLM and returns SynthesizedPersona."""
        jd_annotations = {"annotations": [sample_core_identity_annotation]}

        # Mock the LLM
        mock_response = MagicMock()
        mock_response.content = "A solutions architect who designs elegant systems"

        with patch(
            "src.common.persona_builder.create_tracked_cheap_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create_llm.return_value = mock_llm

            result = await builder.synthesize(jd_annotations)

        assert result is not None
        assert result.persona_statement == "A solutions architect who designs elegant systems"
        assert result.primary_identity == "Solutions Architect"
        assert result.is_user_edited is False
        assert "ann1" in result.source_annotations

    @pytest.mark.asyncio
    async def test_synthesize_strips_quotes_from_response(
        self, builder, sample_core_identity_annotation
    ):
        """Test synthesize strips surrounding quotes from LLM response."""
        jd_annotations = {"annotations": [sample_core_identity_annotation]}

        # Mock the LLM with quoted response
        mock_response = MagicMock()
        mock_response.content = '"A solutions architect who designs elegant systems"'

        with patch(
            "src.common.persona_builder.create_tracked_cheap_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create_llm.return_value = mock_llm

            result = await builder.synthesize(jd_annotations)

        assert result.persona_statement == "A solutions architect who designs elegant systems"

    @pytest.mark.asyncio
    async def test_synthesize_prioritizes_core_over_strong(
        self,
        builder,
        sample_core_identity_annotation,
        sample_strong_identity_annotation,
    ):
        """Test synthesize uses core_identity as primary_identity when both exist."""
        jd_annotations = {
            "annotations": [
                sample_strong_identity_annotation,  # Added first
                sample_core_identity_annotation,   # Core should be primary
            ]
        }

        mock_response = MagicMock()
        mock_response.content = "A solutions architect and team leader"

        with patch(
            "src.common.persona_builder.create_tracked_cheap_llm"
        ) as mock_create_llm:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_response)
            mock_create_llm.return_value = mock_llm

            result = await builder.synthesize(jd_annotations)

        # Primary identity should be from core_identity, not strong_identity
        assert result.primary_identity == "Solutions Architect"
        assert "Team Leadership" in result.secondary_identities


# ===== Test get_persona_for_prompt =====


class TestGetPersonaForPrompt:
    """Tests for get_persona_for_prompt functionality."""

    def test_get_persona_for_prompt_with_stored_persona(
        self, builder, sample_jd_annotations_with_synthesized
    ):
        """Test returns formatted persona when stored."""
        result = builder.get_persona_for_prompt(sample_jd_annotations_with_synthesized)

        assert "CANDIDATE PERSONA:" in result
        assert "solutions architect" in result.lower()

    def test_get_persona_for_prompt_without_persona(self, builder):
        """Test returns empty string when no stored persona."""
        jd_annotations = {"annotations": []}

        result = builder.get_persona_for_prompt(jd_annotations)

        assert result == ""

    def test_get_persona_for_prompt_with_empty_statement(self, builder):
        """Test returns empty string when persona_statement is empty."""
        jd_annotations = {
            "synthesized_persona": {"persona_statement": ""},
        }

        result = builder.get_persona_for_prompt(jd_annotations)

        assert result == ""


class TestGetFullPersonaGuidance:
    """Tests for get_full_persona_guidance method."""

    def test_get_full_persona_guidance_with_stored_persona(
        self, builder, sample_jd_annotations_with_synthesized
    ):
        """Test returns full guidance with framing instructions."""
        result = builder.get_full_persona_guidance(
            sample_jd_annotations_with_synthesized
        )

        assert "CANDIDATE PERSONA:" in result
        assert "central theme" in result
        assert "narrative" in result

    def test_get_full_persona_guidance_without_persona(self, builder):
        """Test returns empty string when no stored persona."""
        jd_annotations = {"annotations": []}

        result = builder.get_full_persona_guidance(jd_annotations)

        assert result == ""


# ===== Test convenience function =====


class TestGetPersonaGuidanceConvenience:
    """Tests for the get_persona_guidance convenience function."""

    def test_convenience_function_with_none(self):
        """Test returns empty string when jd_annotations is None."""
        result = get_persona_guidance(None)

        assert result == ""

    def test_convenience_function_with_stored_persona(
        self, sample_jd_annotations_with_synthesized
    ):
        """Test returns formatted persona when stored."""
        result = get_persona_guidance(sample_jd_annotations_with_synthesized)

        assert "CANDIDATE PERSONA:" in result

    def test_convenience_function_without_persona(self):
        """Test returns empty string when no persona."""
        jd_annotations = {"annotations": []}

        result = get_persona_guidance(jd_annotations)

        assert result == ""


# ===== Test identity strength ordering =====


class TestIdentityStrengthOrder:
    """Tests for identity strength ordering constants."""

    def test_identity_strength_order(self):
        """Test that identity levels are in correct order (strongest first)."""
        assert IDENTITY_STRENGTH_ORDER == ["core_identity", "strong_identity", "developing"]

    def test_core_identity_is_strongest(self):
        """Test that core_identity is the first/strongest."""
        assert IDENTITY_STRENGTH_ORDER[0] == "core_identity"

    def test_developing_is_weakest_included(self):
        """Test that developing is the last included identity."""
        assert IDENTITY_STRENGTH_ORDER[-1] == "developing"
