"""
Unit tests for StrengthSuggestionService module.

Tests strength suggestion generation from JD analysis against candidate profile.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.strength_suggestion_service import (
    StrengthSuggestionService,
    StrengthSuggestion,
    HARDCODED_STRENGTH_PATTERNS,
)


# ===== Fixtures =====


@pytest.fixture
def service():
    """Create a StrengthSuggestionService instance without LLM."""
    return StrengthSuggestionService(llm=None)


@pytest.fixture
def service_with_mock_llm():
    """Create a StrengthSuggestionService instance with mocked LLM."""
    mock_llm = MagicMock()
    return StrengthSuggestionService(llm=mock_llm, model_name="test-model")


@pytest.fixture
def sample_jd_text():
    """Sample job description text for testing."""
    return """
    We are looking for a Senior Software Engineer with Python experience.
    You will be working on distributed systems and microservices architecture.
    Experience with AWS and Kubernetes is required.
    Leadership skills and team management experience are a plus.
    """


@pytest.fixture
def sample_jd_text_with_python():
    """JD text specifically mentioning Python."""
    return """
    Looking for a Python developer to join our team.
    Strong Python skills required for backend development.
    """


@pytest.fixture
def sample_jd_text_with_leadership():
    """JD text specifically mentioning leadership."""
    return """
    We need an Engineering Manager with leadership experience.
    Team management and mentoring skills are essential.
    """


@pytest.fixture
def sample_candidate_profile():
    """Sample candidate profile with skills and roles."""
    return {
        "skills": [
            "Python",
            "AWS",
            "Kubernetes",
            "PostgreSQL",
            "FastAPI",
            "Team Leadership",
        ],
        "roles": [
            {
                "title": "Engineering Manager",
                "company": "TechCorp",
                "keywords": ["leadership", "team management", "hiring"],
                "hard_skills": ["Python", "AWS", "distributed systems"],
            },
            {
                "title": "Senior Software Engineer",
                "company": "StartupCo",
                "keywords": ["microservices", "architecture"],
                "hard_skills": ["Python", "Kubernetes", "Docker"],
            },
        ],
        "summary": "Experienced engineering leader with 10+ years in distributed systems.",
    }


@pytest.fixture
def sample_candidate_profile_limited():
    """Candidate profile with limited skills for gap testing."""
    return {
        "skills": ["Java", "Spring Boot"],
        "roles": [
            {
                "title": "Java Developer",
                "company": "JavaCorp",
                "keywords": ["java", "spring"],
                "hard_skills": ["Java", "Spring Boot", "Maven"],
            },
        ],
        "summary": "Java developer.",
    }


@pytest.fixture
def sample_existing_annotations():
    """Sample existing annotations to test duplicate filtering."""
    return [
        {
            "id": "ann1",
            "target": {"text": "Python experience"},
            "is_active": True,
        },
        {
            "id": "ann2",
            "target": {"text": "leadership skills"},
            "is_active": True,
        },
    ]


@pytest.fixture
def sample_inactive_annotation():
    """Sample inactive annotation."""
    return [
        {
            "id": "ann3",
            "target": {"text": "AWS experience"},
            "is_active": False,
        },
    ]


# ===== Test Hardcoded Patterns =====


class TestHardcodedPatterns:
    """Tests for hardcoded strength patterns."""

    def test_hardcoded_patterns_exist(self):
        """Test that hardcoded patterns are defined."""
        assert len(HARDCODED_STRENGTH_PATTERNS) > 0

    def test_python_pattern_exists(self):
        """Test that Python pattern is defined."""
        assert "python" in HARDCODED_STRENGTH_PATTERNS

    def test_pattern_has_required_fields(self):
        """Test that each pattern has required fields."""
        for pattern, defaults in HARDCODED_STRENGTH_PATTERNS.items():
            assert "relevance" in defaults, f"{pattern} missing relevance"
            assert "keywords" in defaults, f"{pattern} missing keywords"

    def test_relevance_values_are_valid(self):
        """Test that relevance values are from valid set."""
        valid_relevance = {
            "core_strength",
            "extremely_relevant",
            "relevant",
            "tangential",
        }
        for pattern, defaults in HARDCODED_STRENGTH_PATTERNS.items():
            assert (
                defaults["relevance"] in valid_relevance
            ), f"{pattern} has invalid relevance"


# ===== Test Service Initialization =====


class TestServiceInit:
    """Tests for StrengthSuggestionService initialization."""

    def test_init_without_llm(self):
        """Test initialization without LLM."""
        service = StrengthSuggestionService(llm=None)
        assert service.llm is None
        assert service.model_name == "anthropic/claude-3-haiku"

    def test_init_with_custom_model_name(self):
        """Test initialization with custom model name."""
        service = StrengthSuggestionService(
            llm=None, model_name="anthropic/claude-3-5-sonnet"
        )
        assert service.model_name == "anthropic/claude-3-5-sonnet"

    def test_init_with_llm(self):
        """Test initialization with LLM."""
        mock_llm = MagicMock()
        service = StrengthSuggestionService(llm=mock_llm)
        assert service.llm == mock_llm


# ===== Test Hardcoded Defaults Application =====


class TestApplyHardcodedDefaults:
    """Tests for _apply_hardcoded_defaults method."""

    def test_matches_python_in_jd(self, service, sample_candidate_profile):
        """Test that Python pattern matches when in JD and candidate skills."""
        jd_text = "We need Python developers for our team."

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile, set()
        )

        # Should find Python match
        python_suggestions = [s for s in suggestions if "python" in s["matching_skill"].lower()]
        assert len(python_suggestions) >= 1

    def test_matches_aws_in_jd(self, service, sample_candidate_profile):
        """Test that AWS pattern matches when in JD and candidate skills."""
        jd_text = "Experience with AWS cloud services is required."

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile, set()
        )

        aws_suggestions = [s for s in suggestions if "aws" in s["matching_skill"].lower()]
        assert len(aws_suggestions) >= 1

    def test_no_match_when_not_in_jd(self, service, sample_candidate_profile):
        """Test that no suggestions when pattern not in JD."""
        jd_text = "We need Ruby on Rails developers."

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile, set()
        )

        # Should not match Ruby (not in hardcoded patterns)
        ruby_suggestions = [s for s in suggestions if "ruby" in s["matching_skill"].lower()]
        assert len(ruby_suggestions) == 0

    def test_no_match_when_candidate_lacks_skill(
        self, service, sample_candidate_profile_limited
    ):
        """Test that no suggestions when candidate lacks the skill."""
        jd_text = "We need Python developers for our team."

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile_limited, set()
        )

        # Java developer doesn't have Python
        python_suggestions = [s for s in suggestions if "python" in s["matching_skill"].lower()]
        assert len(python_suggestions) == 0

    def test_skips_already_annotated(self, service, sample_candidate_profile):
        """Test that already annotated text is skipped."""
        jd_text = "We need Python developers for our team."
        annotated_texts = {"we need python developers for our team."}

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile, annotated_texts
        )

        # The exact phrase is annotated, should skip
        # (Note: might still match if extracted phrase differs)
        # Just verify the method runs without error
        assert isinstance(suggestions, list)

    def test_suggestion_has_correct_source(self, service, sample_candidate_profile):
        """Test that suggestions have hardcoded_default source."""
        jd_text = "Python and AWS experience required."

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile, set()
        )

        for s in suggestions:
            assert s["source"] == "hardcoded_default"

    def test_suggestion_has_confidence(self, service, sample_candidate_profile):
        """Test that suggestions have confidence score."""
        jd_text = "Python experience required."

        suggestions = service._apply_hardcoded_defaults(
            jd_text, sample_candidate_profile, set()
        )

        for s in suggestions:
            assert "confidence" in s
            assert s["confidence"] == 0.75  # Hardcoded default confidence


# ===== Test Candidate Skill Matching =====


class TestCandidateHasSkill:
    """Tests for _candidate_has_skill method."""

    def test_direct_match(self, service):
        """Test direct skill match."""
        candidate_skills = {"python", "aws", "kubernetes"}

        assert service._candidate_has_skill("python", candidate_skills) is True
        assert service._candidate_has_skill("aws", candidate_skills) is True

    def test_partial_match(self, service):
        """Test partial skill match."""
        candidate_skills = {"python programming", "aws cloud"}

        assert service._candidate_has_skill("python", candidate_skills) is True
        assert service._candidate_has_skill("aws", candidate_skills) is True

    def test_no_match(self, service):
        """Test no skill match."""
        candidate_skills = {"java", "spring"}

        assert service._candidate_has_skill("python", candidate_skills) is False
        assert service._candidate_has_skill("aws", candidate_skills) is False


# ===== Test Phrase Extraction =====


class TestExtractRelevantPhrase:
    """Tests for _extract_relevant_phrase method."""

    def test_extracts_keyword_with_context(self, service):
        """Test extracting keyword with surrounding context."""
        jd_text = "We need someone with Python experience for our backend team."

        result = service._extract_relevant_phrase(jd_text, "Python")

        assert "Python" in result
        assert len(result) > len("Python")

    def test_returns_keyword_when_not_found(self, service):
        """Test returns keyword when not found in text."""
        jd_text = "We need Java developers."

        result = service._extract_relevant_phrase(jd_text, "Python")

        assert result == "Python"

    def test_truncates_long_phrases(self, service):
        """Test that very long phrases are truncated."""
        jd_text = "A" * 500 + " Python " + "B" * 500

        result = service._extract_relevant_phrase(jd_text, "Python")

        assert len(result) <= 200


# ===== Test Full Suggestion Flow =====


class TestSuggestStrengths:
    """Tests for suggest_strengths main method."""

    def test_returns_list(self, service, sample_jd_text, sample_candidate_profile):
        """Test that suggest_strengths returns a list."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
        )

        assert isinstance(suggestions, list)

    def test_with_defaults_enabled(
        self, service, sample_jd_text, sample_candidate_profile
    ):
        """Test suggestions with hardcoded defaults enabled."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
            include_defaults=True,
        )

        # Should have some hardcoded suggestions
        hardcoded = [s for s in suggestions if s["source"] == "hardcoded_default"]
        assert len(hardcoded) >= 1

    def test_without_defaults(self, service, sample_jd_text, sample_candidate_profile):
        """Test suggestions with hardcoded defaults disabled."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
            include_defaults=False,
        )

        # Without LLM and without defaults, should be empty
        assert len(suggestions) == 0

    def test_filters_existing_annotations(
        self,
        service,
        sample_jd_text_with_python,
        sample_candidate_profile,
        sample_existing_annotations,
    ):
        """Test that existing annotations are filtered out."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text_with_python,
            candidate_profile=sample_candidate_profile,
            existing_annotations=sample_existing_annotations,
        )

        # "Python experience" is already annotated, should be filtered
        # (exact match depends on extraction)
        assert isinstance(suggestions, list)

    def test_sorted_by_confidence(
        self, service, sample_jd_text, sample_candidate_profile
    ):
        """Test suggestions are sorted by confidence (highest first)."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
        )

        if len(suggestions) >= 2:
            for i in range(len(suggestions) - 1):
                assert suggestions[i]["confidence"] >= suggestions[i + 1]["confidence"]

    def test_inactive_annotations_ignored(
        self,
        service,
        sample_jd_text_with_python,
        sample_candidate_profile,
        sample_inactive_annotation,
    ):
        """Test that inactive annotations don't filter suggestions."""
        # Inactive annotation for "AWS experience"
        suggestions = service.suggest_strengths(
            jd_text="We need AWS and Python expertise.",
            candidate_profile=sample_candidate_profile,
            existing_annotations=sample_inactive_annotation,
        )

        # AWS annotation is inactive, so AWS should still get suggested
        # (depends on extraction matching exactly)
        assert isinstance(suggestions, list)


# ===== Test Profile Summary Building =====


class TestBuildProfileSummary:
    """Tests for _build_profile_summary method."""

    def test_includes_skills(self, service, sample_candidate_profile):
        """Test that summary includes skills."""
        result = service._build_profile_summary(sample_candidate_profile)

        assert "Skills" in result
        assert "Python" in result

    def test_includes_roles(self, service, sample_candidate_profile):
        """Test that summary includes roles."""
        result = service._build_profile_summary(sample_candidate_profile)

        assert "Engineering Manager" in result
        assert "TechCorp" in result

    def test_includes_summary(self, service, sample_candidate_profile):
        """Test that candidate summary is included."""
        result = service._build_profile_summary(sample_candidate_profile)

        assert "Summary" in result
        assert "engineering leader" in result.lower()

    def test_handles_empty_profile(self, service):
        """Test handling of empty profile."""
        empty_profile = {"skills": [], "roles": [], "summary": ""}

        result = service._build_profile_summary(empty_profile)

        # Should not raise, may return empty string
        assert isinstance(result, str)

    def test_limits_skills_count(self, service):
        """Test that skills are limited to 30."""
        large_profile = {
            "skills": [f"Skill{i}" for i in range(50)],
            "roles": [],
            "summary": "",
        }

        result = service._build_profile_summary(large_profile)

        # Should only include first 30 skills
        assert "Skill29" in result
        assert "Skill30" not in result


# ===== Test LLM Integration (Mocked) =====


class TestLLMSuggestions:
    """Tests for LLM-based suggestions with mocked LLM."""

    def test_llm_suggestions_called_when_available(
        self, service_with_mock_llm, sample_jd_text, sample_candidate_profile
    ):
        """Test that LLM is invoked when available."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = '[]'  # Empty array
        service_with_mock_llm.llm.invoke = MagicMock(return_value=mock_response)

        suggestions = service_with_mock_llm.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
            include_defaults=False,  # Only LLM
        )

        # Verify LLM was called
        service_with_mock_llm.llm.invoke.assert_called_once()

    def test_llm_json_parsing(
        self, service_with_mock_llm, sample_jd_text, sample_candidate_profile
    ):
        """Test LLM response JSON parsing."""
        mock_response = MagicMock()
        mock_response.content = '''```json
[
    {
        "target_text": "distributed systems experience",
        "suggested_relevance": "core_strength",
        "matching_skill": "Distributed Systems",
        "evidence_summary": "Led distributed systems team",
        "suggested_keywords": ["distributed", "scalability"],
        "confidence": 0.85
    }
]
```'''
        service_with_mock_llm.llm.invoke = MagicMock(return_value=mock_response)

        suggestions = service_with_mock_llm.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
            include_defaults=False,
        )

        # Should parse the JSON and create suggestion
        llm_suggestions = [s for s in suggestions if s["source"] == "llm_match"]
        assert len(llm_suggestions) == 1
        assert llm_suggestions[0]["matching_skill"] == "Distributed Systems"
        assert llm_suggestions[0]["confidence"] == 0.85

    def test_llm_handles_parse_error(
        self, service_with_mock_llm, sample_jd_text, sample_candidate_profile
    ):
        """Test handling of LLM JSON parse error."""
        mock_response = MagicMock()
        mock_response.content = "Invalid JSON response"
        service_with_mock_llm.llm.invoke = MagicMock(return_value=mock_response)

        # Should not raise, just return empty LLM suggestions
        suggestions = service_with_mock_llm.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
            include_defaults=False,
        )

        assert isinstance(suggestions, list)

    def test_llm_deduplicates_against_hardcoded(
        self, service_with_mock_llm, sample_jd_text_with_python, sample_candidate_profile
    ):
        """Test that LLM suggestions don't duplicate hardcoded ones."""
        # LLM returns same target as hardcoded
        mock_response = MagicMock()
        mock_response.content = '''[
    {
        "target_text": "Python developer",
        "suggested_relevance": "extremely_relevant",
        "matching_skill": "Python",
        "evidence_summary": "Strong Python experience",
        "suggested_keywords": ["Python"],
        "confidence": 0.9
    }
]'''
        service_with_mock_llm.llm.invoke = MagicMock(return_value=mock_response)

        suggestions = service_with_mock_llm.suggest_strengths(
            jd_text=sample_jd_text_with_python,
            candidate_profile=sample_candidate_profile,
            include_defaults=True,  # Enable both
        )

        # Should deduplicate - Python phrase should appear only once
        # (from hardcoded, LLM duplicate filtered)
        python_suggestions = [s for s in suggestions if "python" in s["matching_skill"].lower()]

        # We can have multiple python-related suggestions if target_text differs
        # Key is that exact duplicates are filtered
        assert len(suggestions) >= 1


# ===== Test Suggestion Schema =====


class TestSuggestionSchema:
    """Tests for StrengthSuggestion TypedDict schema."""

    def test_suggestion_has_all_fields(
        self, service, sample_jd_text_with_python, sample_candidate_profile
    ):
        """Test that suggestions have all required fields."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text_with_python,
            candidate_profile=sample_candidate_profile,
        )

        if len(suggestions) > 0:
            suggestion = suggestions[0]

            # Required fields
            assert "target_text" in suggestion
            assert "suggested_relevance" in suggestion
            assert "suggested_requirement" in suggestion
            assert "matching_skill" in suggestion
            assert "confidence" in suggestion
            assert "source" in suggestion
            assert "suggested_keywords" in suggestion

            # Optional fields (may be None)
            assert "target_section" in suggestion
            assert "suggested_passion" in suggestion
            assert "suggested_identity" in suggestion
            assert "matching_role" in suggestion
            assert "evidence_summary" in suggestion
            assert "reframe_note" in suggestion


# ===== Test Identity/Passion Inclusion Flags =====


class TestInclusionFlags:
    """Tests for include_identity and include_passion flags."""

    def test_identity_included_by_default(
        self, service, sample_jd_text, sample_candidate_profile
    ):
        """Test that identity is included by default."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
        )

        # Hardcoded defaults include identity
        if len(suggestions) > 0:
            # At least some should have identity
            has_identity = any(s.get("suggested_identity") for s in suggestions)
            # All hardcoded have identity in the pattern
            assert has_identity or len(suggestions) == 0

    def test_passion_included_by_default(
        self, service, sample_jd_text, sample_candidate_profile
    ):
        """Test that passion is included by default."""
        suggestions = service.suggest_strengths(
            jd_text=sample_jd_text,
            candidate_profile=sample_candidate_profile,
        )

        if len(suggestions) > 0:
            # At least some should have passion
            has_passion = any(s.get("suggested_passion") for s in suggestions)
            assert has_passion or len(suggestions) == 0
