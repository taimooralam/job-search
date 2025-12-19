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

    def test_extract_persona_annotations_no_annotations(self, builder):
        """Test extraction with no annotations returns empty groups."""
        jd_annotations = {"annotations": []}

        grouped = builder._extract_persona_annotations(jd_annotations)

        assert grouped["core_identity"] == []
        assert grouped["strong_identity"] == []
        assert grouped["developing"] == []

    def test_extract_persona_annotations_groups_by_strength(
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

        grouped = builder._extract_persona_annotations(jd_annotations)

        assert len(grouped["core_identity"]) == 1
        assert len(grouped["strong_identity"]) == 1
        assert len(grouped["developing"]) == 1
        assert grouped["core_identity"][0]["matching_skill"] == "Solutions Architect"

    def test_extract_persona_annotations_ignores_inactive(
        self, builder, sample_inactive_annotation
    ):
        """Test extraction ignores inactive annotations."""
        jd_annotations = {"annotations": [sample_inactive_annotation]}

        grouped = builder._extract_persona_annotations(jd_annotations)

        assert grouped["core_identity"] == []
        assert grouped["strong_identity"] == []
        assert grouped["developing"] == []

    def test_extract_persona_annotations_ignores_not_identity(
        self, builder, sample_not_identity_annotation
    ):
        """Test extraction ignores not_identity and peripheral annotations."""
        jd_annotations = {"annotations": [sample_not_identity_annotation]}

        grouped = builder._extract_persona_annotations(jd_annotations)

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
    """Tests for PersonaBuilder persona context building."""

    def test_build_persona_context_empty(self, builder):
        """Test building context with no annotations."""
        grouped = {
            "core_identity": [], "strong_identity": [], "developing": [],
            "love_it": [], "enjoy": [],
            "core_strength": [], "extremely_relevant": []
        }

        result = builder._build_persona_context(grouped)

        assert result == ""

    def test_build_persona_context_with_core_only(
        self, builder, sample_core_identity_annotation
    ):
        """Test building context with only core identity."""
        grouped = {
            "core_identity": [sample_core_identity_annotation],
            "strong_identity": [],
            "developing": [],
            "love_it": [], "enjoy": [],
            "core_strength": [], "extremely_relevant": []
        }

        result = builder._build_persona_context(grouped)

        assert "Core identity: Solutions Architect" in result

    def test_build_persona_context_with_all_levels(
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
            "love_it": [], "enjoy": [],
            "core_strength": [], "extremely_relevant": []
        }

        result = builder._build_persona_context(grouped)

        assert "Core identity: Solutions Architect" in result
        assert "Strong identity: Team Leadership" in result
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
        """Test synthesize calls Claude CLI and returns SynthesizedPersona."""
        jd_annotations = {"annotations": [sample_core_identity_annotation]}

        # Mock the Claude CLI
        mock_cli_result = MagicMock()
        mock_cli_result.success = True
        mock_cli_result.raw_result = "A solutions architect who designs elegant systems"

        with patch(
            "src.common.persona_builder.ClaudeCLI"
        ) as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.invoke.return_value = mock_cli_result
            mock_cli_class.return_value = mock_cli

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
        """Test synthesize strips surrounding quotes from Claude CLI response."""
        jd_annotations = {"annotations": [sample_core_identity_annotation]}

        # Mock the Claude CLI with quoted response
        mock_cli_result = MagicMock()
        mock_cli_result.success = True
        mock_cli_result.raw_result = '"A solutions architect who designs elegant systems"'

        with patch(
            "src.common.persona_builder.ClaudeCLI"
        ) as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.invoke.return_value = mock_cli_result
            mock_cli_class.return_value = mock_cli

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

        # Mock the Claude CLI
        mock_cli_result = MagicMock()
        mock_cli_result.success = True
        mock_cli_result.raw_result = "A solutions architect and team leader"

        with patch(
            "src.common.persona_builder.ClaudeCLI"
        ) as mock_cli_class:
            mock_cli = MagicMock()
            mock_cli.invoke.return_value = mock_cli_result
            mock_cli_class.return_value = mock_cli

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


# ===== Test SYNTHESIS_PROMPT Third-Person Instructions =====


class TestSynthesisPromptThirdPerson:
    """Tests for third-person absent voice in SYNTHESIS_PROMPT."""

    def test_prompt_contains_third_person_rules(self):
        """SYNTHESIS_PROMPT includes third-person absent voice instructions."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Check for key phrases in the critical section
        assert "THIRD-PERSON ABSENT VOICE" in prompt
        assert "NO pronouns" in prompt or "no pronouns" in prompt.lower()

    def test_prompt_lists_prohibited_pronouns(self):
        """SYNTHESIS_PROMPT explicitly lists prohibited pronouns."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should explicitly list the pronouns to avoid
        assert "I, my, me" in prompt or "I," in prompt
        assert "you, your" in prompt or "your" in prompt
        assert "we, our" in prompt or "our" in prompt

    def test_prompt_has_correct_examples(self):
        """SYNTHESIS_PROMPT includes correct third-person examples."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should have CORRECT examples section
        assert "CORRECT" in prompt

        # Check for valid third-person patterns in examples
        assert "who thrives" in prompt.lower() or "who transforms" in prompt.lower()
        assert "WHO" in prompt  # Should emphasize "who" clauses

    def test_prompt_has_incorrect_examples(self):
        """SYNTHESIS_PROMPT includes incorrect examples to avoid."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should have INCORRECT examples section
        assert "INCORRECT" in prompt or "NEVER" in prompt

    def test_prompt_emphasizes_who_clauses(self):
        """SYNTHESIS_PROMPT emphasizes using 'who' clauses."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should mention "who" as the connecting pattern
        assert '"who"' in prompt.lower() or "'who'" in prompt.lower() or "who clauses" in prompt.lower()

    def test_prompt_requires_start_with_a_or_an(self):
        """SYNTHESIS_PROMPT requires starting with 'A' or 'An'."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should specify starting with A/An
        assert '"A"' in prompt or '"An"' in prompt or "Start with" in prompt

    def test_prompt_correct_examples_have_no_pronouns(self):
        """SYNTHESIS_PROMPT's CORRECT examples use third-person absent voice."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Extract CORRECT examples section
        if "CORRECT examples" in prompt:
            correct_section_start = prompt.index("CORRECT examples")
            correct_section_end = prompt.index("INCORRECT", correct_section_start) if "INCORRECT" in prompt[correct_section_start:] else len(prompt)
            correct_section = prompt[correct_section_start:correct_section_end]

            # Check that CORRECT examples don't contain pronouns
            # (This is a basic check - the examples should demonstrate third-person)
            # We can verify specific patterns exist
            assert "who thrives" in correct_section.lower() or "who transforms" in correct_section.lower()

    def test_prompt_incorrect_examples_show_pronoun_violations(self):
        """SYNTHESIS_PROMPT's INCORRECT examples show pronoun violations."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Extract INCORRECT examples section
        if "INCORRECT examples" in prompt:
            incorrect_section_start = prompt.index("INCORRECT examples")
            # Find the end of incorrect section (next section or end)
            next_section_markers = ["===", "Return ONLY"]
            incorrect_section_end = len(prompt)
            for marker in next_section_markers:
                if marker in prompt[incorrect_section_start + 20:]:
                    end_idx = prompt.index(marker, incorrect_section_start + 20)
                    incorrect_section_end = min(incorrect_section_end, end_idx)
            incorrect_section = prompt[incorrect_section_start:incorrect_section_end]

            # INCORRECT examples should contain pronouns as anti-patterns
            # Check for at least one pronoun in the incorrect section
            has_pronoun = any(
                pronoun in incorrect_section.lower()
                for pronoun in ["i am", "my passion", "uses \"i\"", "uses \"my\""]
            )
            assert has_pronoun, "INCORRECT examples should show pronoun violations"

    def test_prompt_structure_has_critical_section(self):
        """SYNTHESIS_PROMPT has clearly marked critical section for third-person rules."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should have section markers
        assert "===" in prompt  # Section dividers
        assert "CRITICAL" in prompt  # Emphasis on importance

    def test_prompt_explains_third_person_absent_voice(self):
        """SYNTHESIS_PROMPT explains what third-person absent voice means."""
        from src.common.persona_builder import PersonaBuilder

        prompt = PersonaBuilder.SYNTHESIS_PROMPT

        # Should define the concept clearly
        assert "third-person absent" in prompt.lower()
        # Should explain it means no pronouns
        prompt_lower = prompt.lower()
        assert ("no pronouns" in prompt_lower or "without pronouns" in prompt_lower)
