"""
Tests for ATS Keyword Placement Validator.

Tests the KeywordPlacementValidator class which validates that annotated keywords
appear in optimal positions (top 1/3) of the CV for ATS optimization and
6-7 second recruiter scan.
"""

import pytest
from src.layer6_v2.keyword_placement import (
    KeywordPlacement,
    KeywordPlacementResult,
    KeywordPlacementValidator,
    extract_priority_keywords_from_annotations,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def validator():
    """Create a fresh KeywordPlacementValidator instance."""
    return KeywordPlacementValidator()


@pytest.fixture
def sample_cv_sections():
    """Sample CV sections for testing."""
    return {
        "headline": "Senior Engineering Manager | 15 Years Technology Leadership",
        "narrative": (
            "Experienced engineering leader with deep expertise in Python, "
            "Kubernetes, and AWS. Built and scaled teams from 5 to 50+ engineers "
            "while delivering platform modernization initiatives that reduced "
            "infrastructure costs by 40%."
        ),
        "competencies": [
            "Python",
            "Kubernetes",
            "AWS",
            "Team Leadership",
            "Agile Delivery",
            "System Architecture",
        ],
        "first_role_bullets": [
            "Led team of 15 engineers to deliver Kubernetes migration reducing deployment time by 60%",
            "Architected AWS-based microservices platform handling 1M+ daily transactions",
            "Implemented Python-based ML pipeline improving prediction accuracy by 25%",
        ],
    }


@pytest.fixture
def sample_priority_keywords():
    """Sample priority keywords from annotations."""
    return [
        {
            "keyword": "Python",
            "is_must_have": True,
            "is_identity": True,
            "is_core_strength": True,
            "priority_rank": 1,
        },
        {
            "keyword": "Kubernetes",
            "is_must_have": True,
            "is_identity": False,
            "is_core_strength": True,
            "priority_rank": 2,
        },
        {
            "keyword": "AWS",
            "is_must_have": False,
            "is_identity": False,
            "is_core_strength": True,
            "priority_rank": 3,
        },
        {
            "keyword": "Team Leadership",
            "is_must_have": True,
            "is_identity": True,
            "is_core_strength": False,
            "priority_rank": 4,
        },
    ]


@pytest.fixture
def sample_jd_annotations():
    """Sample JD annotations for extract_priority_keywords_from_annotations()."""
    return {
        "annotations": [
            {
                "id": "ann-1",
                "is_active": True,
                "matching_skill": "Python",
                "relevance": "core_strength",
                "requirement_type": "must_have",
                "identity": "core_identity",
                "priority": 1,
            },
            {
                "id": "ann-2",
                "is_active": True,
                "matching_skill": "Kubernetes",
                "relevance": "extremely_relevant",
                "requirement_type": "must_have",
                "identity": "peripheral",
                "priority": 2,
            },
            {
                "id": "ann-3",
                "is_active": True,
                "matching_skill": None,
                "suggested_keywords": ["Docker", "Container Orchestration"],
                "relevance": "relevant",
                "requirement_type": "nice_to_have",
                "identity": "peripheral",
                "priority": 3,
            },
            {
                "id": "ann-4",
                "is_active": False,  # Inactive - should be skipped
                "matching_skill": "Java",
                "relevance": "gap",
                "requirement_type": "must_have",
                "identity": "not_identity",
                "priority": 1,
            },
        ],
    }


# =============================================================================
# KeywordPlacement DATACLASS TESTS
# =============================================================================


class TestKeywordPlacement:
    """Tests for the KeywordPlacement dataclass."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        placement = KeywordPlacement(keyword="Python")

        assert placement.keyword == "Python"
        assert placement.priority_rank == 0
        assert placement.is_must_have is False
        assert placement.is_identity is False
        assert placement.is_core_strength is False
        assert placement.found_in_headline is False
        assert placement.found_in_narrative is False
        assert placement.found_in_competencies is False
        assert placement.found_in_first_role is False
        assert placement.first_occurrence_position == -1
        assert placement.total_occurrences == 0
        assert placement.occurrence_locations == []

    def test_is_in_top_third_headline(self):
        """Test is_in_top_third returns True when found in headline."""
        placement = KeywordPlacement(keyword="Python", found_in_headline=True)
        assert placement.is_in_top_third is True

    def test_is_in_top_third_narrative(self):
        """Test is_in_top_third returns True when found in narrative."""
        placement = KeywordPlacement(keyword="Python", found_in_narrative=True)
        assert placement.is_in_top_third is True

    def test_is_in_top_third_competencies(self):
        """Test is_in_top_third returns True when found in competencies."""
        placement = KeywordPlacement(keyword="Python", found_in_competencies=True)
        assert placement.is_in_top_third is True

    def test_is_in_top_third_first_role_only(self):
        """Test is_in_top_third returns False when only found in first role."""
        placement = KeywordPlacement(keyword="Python", found_in_first_role=True)
        assert placement.is_in_top_third is False

    def test_is_in_top_third_not_found(self):
        """Test is_in_top_third returns False when not found anywhere."""
        placement = KeywordPlacement(keyword="Python")
        assert placement.is_in_top_third is False

    def test_placement_score_headline_only(self):
        """Test placement score is 40 for headline only."""
        placement = KeywordPlacement(keyword="Python", found_in_headline=True)
        assert placement.placement_score == 40

    def test_placement_score_narrative_only(self):
        """Test placement score is 30 for narrative only."""
        placement = KeywordPlacement(keyword="Python", found_in_narrative=True)
        assert placement.placement_score == 30

    def test_placement_score_competencies_only(self):
        """Test placement score is 20 for competencies only."""
        placement = KeywordPlacement(keyword="Python", found_in_competencies=True)
        assert placement.placement_score == 20

    def test_placement_score_first_role_only(self):
        """Test placement score is 10 for first role only."""
        placement = KeywordPlacement(keyword="Python", found_in_first_role=True)
        assert placement.placement_score == 10

    def test_placement_score_all_locations(self):
        """Test placement score is capped at 100 when found everywhere."""
        placement = KeywordPlacement(
            keyword="Python",
            found_in_headline=True,
            found_in_narrative=True,
            found_in_competencies=True,
            found_in_first_role=True,
        )
        # 40 + 30 + 20 + 10 = 100
        assert placement.placement_score == 100

    def test_placement_score_multiple_locations(self):
        """Test placement score adds up correctly for multiple locations."""
        placement = KeywordPlacement(
            keyword="Python",
            found_in_narrative=True,
            found_in_competencies=True,
        )
        # 30 + 20 = 50
        assert placement.placement_score == 50

    def test_to_dict(self):
        """Test to_dict serialization."""
        placement = KeywordPlacement(
            keyword="Python",
            priority_rank=1,
            is_must_have=True,
            is_identity=True,
            is_core_strength=True,
            found_in_headline=True,
            found_in_narrative=True,
            total_occurrences=3,
            occurrence_locations=["headline", "narrative"],
        )

        result = placement.to_dict()

        assert result["keyword"] == "Python"
        assert result["priority_rank"] == 1
        assert result["is_must_have"] is True
        assert result["is_identity"] is True
        assert result["is_core_strength"] is True
        assert result["found_in_headline"] is True
        assert result["found_in_narrative"] is True
        assert result["found_in_competencies"] is False
        assert result["found_in_first_role"] is False
        assert result["is_in_top_third"] is True
        assert result["placement_score"] == 70  # 40 + 30
        assert result["total_occurrences"] == 3
        assert result["occurrence_locations"] == ["headline", "narrative"]


# =============================================================================
# KeywordPlacementResult DATACLASS TESTS
# =============================================================================


class TestKeywordPlacementResult:
    """Tests for the KeywordPlacementResult dataclass."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        result = KeywordPlacementResult()

        assert result.placements == []
        assert result.overall_score == 0
        assert result.must_have_score == 0
        assert result.identity_score == 0
        assert result.violations == []
        assert result.suggestions == []
        assert result.total_keywords == 0
        assert result.keywords_in_headline == 0
        assert result.keywords_in_narrative == 0
        assert result.keywords_in_top_third == 0
        assert result.keywords_buried == 0

    def test_passed_high_scores(self):
        """Test passed is True when scores meet thresholds."""
        result = KeywordPlacementResult(overall_score=85, must_have_score=95)
        assert result.passed is True

    def test_passed_low_overall_score(self):
        """Test passed is False when overall score is below 80."""
        result = KeywordPlacementResult(overall_score=75, must_have_score=95)
        assert result.passed is False

    def test_passed_low_must_have_score(self):
        """Test passed is False when must_have_score is below 90."""
        result = KeywordPlacementResult(overall_score=85, must_have_score=85)
        assert result.passed is False

    def test_passed_both_low(self):
        """Test passed is False when both scores are low."""
        result = KeywordPlacementResult(overall_score=60, must_have_score=70)
        assert result.passed is False

    def test_to_dict(self):
        """Test to_dict serialization."""
        placement = KeywordPlacement(
            keyword="Python",
            found_in_headline=True,
            is_must_have=True,
        )
        result = KeywordPlacementResult(
            placements=[placement],
            overall_score=85,
            must_have_score=100,
            identity_score=100,
            violations=["Test violation"],
            suggestions=["Test suggestion"],
            total_keywords=1,
            keywords_in_headline=1,
            keywords_in_top_third=1,
        )

        d = result.to_dict()

        assert d["overall_score"] == 85
        assert d["must_have_score"] == 100
        assert d["identity_score"] == 100
        assert d["passed"] is True
        assert len(d["violations"]) == 1
        assert len(d["suggestions"]) == 1
        assert len(d["placements"]) == 1
        assert d["placements"][0]["keyword"] == "Python"


# =============================================================================
# KeywordPlacementValidator TESTS
# =============================================================================


class TestKeywordPlacementValidator:
    """Tests for the KeywordPlacementValidator class."""

    def test_validate_all_keywords_found(
        self, validator, sample_cv_sections, sample_priority_keywords
    ):
        """Test validation when all keywords are found in optimal positions."""
        result = validator.validate(
            headline=sample_cv_sections["headline"],
            narrative=sample_cv_sections["narrative"],
            competencies=sample_cv_sections["competencies"],
            first_role_bullets=sample_cv_sections["first_role_bullets"],
            priority_keywords=sample_priority_keywords,
        )

        assert result.total_keywords == 4
        assert result.keywords_in_top_third == 4
        assert result.keywords_buried == 0
        assert result.must_have_score == 100
        assert result.overall_score > 0

    def test_validate_empty_keywords(self, validator, sample_cv_sections):
        """Test validation with empty keywords list."""
        result = validator.validate(
            headline=sample_cv_sections["headline"],
            narrative=sample_cv_sections["narrative"],
            competencies=sample_cv_sections["competencies"],
            first_role_bullets=sample_cv_sections["first_role_bullets"],
            priority_keywords=[],
        )

        assert result.total_keywords == 0
        assert result.overall_score == 100  # No keywords to check = pass
        assert result.passed is True

    def test_validate_missing_keyword(self, validator, sample_cv_sections):
        """Test validation when a must-have keyword is missing."""
        keywords = [
            {
                "keyword": "Java",  # Not in any section
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline=sample_cv_sections["headline"],
            narrative=sample_cv_sections["narrative"],
            competencies=sample_cv_sections["competencies"],
            first_role_bullets=sample_cv_sections["first_role_bullets"],
            priority_keywords=keywords,
        )

        assert result.total_keywords == 1
        assert result.keywords_in_top_third == 0
        assert result.keywords_buried == 1
        assert result.must_have_score == 0
        assert len(result.violations) > 0
        assert "Java" in result.violations[0]

    def test_validate_identity_not_in_headline(self, validator, sample_cv_sections):
        """Test validation when identity keyword is not in headline."""
        # Create a section where Docker is in narrative but not headline
        keywords = [
            {
                "keyword": "Docker",  # In first_role_bullets but not headline
                "is_must_have": False,
                "is_identity": True,
                "is_core_strength": False,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="Senior Engineering Manager",  # No Docker
            narrative="Experience with containerization",  # No Docker
            competencies=["Docker"],  # Docker here
            first_role_bullets=["Implemented Docker containers"],
            priority_keywords=keywords,
        )

        # Should generate violation for identity not in headline
        assert any("headline" in v.lower() for v in result.violations)

    def test_validate_fuzzy_matching(self, validator):
        """Test that fuzzy matching works (python matches Python3, Python)."""
        keywords = [
            {
                "keyword": "python",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="Senior Python3 Developer",  # Should match "python"
            narrative="Experience with Python programming",
            competencies=["Python"],
            first_role_bullets=["Built Python-based applications"],
            priority_keywords=keywords,
        )

        # Python should be found in all sections due to fuzzy matching
        assert result.placements[0].found_in_headline is True
        assert result.placements[0].found_in_narrative is True
        assert result.placements[0].found_in_competencies is True
        assert result.placements[0].found_in_first_role is True
        assert result.placements[0].total_occurrences >= 4

    def test_validate_case_insensitive(self, validator):
        """Test that matching is case insensitive."""
        keywords = [
            {
                "keyword": "KUBERNETES",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="kubernetes Expert",
            narrative="Experience with Kubernetes orchestration",
            competencies=["kubernetes"],
            first_role_bullets=[],
            priority_keywords=keywords,
        )

        assert result.placements[0].found_in_headline is True
        assert result.placements[0].found_in_narrative is True
        assert result.placements[0].found_in_competencies is True

    def test_validate_generates_suggestions_for_core_strength(self, validator):
        """Test that suggestions are generated for missing core strength keywords."""
        keywords = [
            {
                "keyword": "Terraform",  # Not in any section
                "is_must_have": False,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="Engineering Manager",
            narrative="Cloud infrastructure experience",
            competencies=["AWS", "GCP"],
            first_role_bullets=["Managed cloud deployments"],
            priority_keywords=keywords,
        )

        # Should generate suggestion for adding to competencies
        assert any("Terraform" in s for s in result.suggestions)

    def test_validate_empty_cv_sections(self, validator, sample_priority_keywords):
        """Test validation with empty CV sections."""
        result = validator.validate(
            headline="",
            narrative="",
            competencies=[],
            first_role_bullets=[],
            priority_keywords=sample_priority_keywords,
        )

        assert result.total_keywords == 4
        assert result.keywords_in_top_third == 0
        assert result.keywords_buried == 4
        assert result.overall_score == 0

    def test_validate_keyword_in_multiple_sections(self, validator):
        """Test that occurrences are counted across all sections."""
        keywords = [
            {
                "keyword": "Python",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="Python Developer",
            narrative="Expert in Python programming with Python best practices",
            competencies=["Python", "Python3"],
            first_role_bullets=["Python automation", "Python ML"],
            priority_keywords=keywords,
        )

        placement = result.placements[0]
        assert placement.found_in_headline is True
        assert placement.found_in_narrative is True
        assert placement.found_in_competencies is True
        assert placement.found_in_first_role is True
        assert placement.total_occurrences >= 6

    def test_validate_score_calculation(self, validator):
        """Test that overall score is calculated correctly."""
        # Two keywords: one perfect (100), one missing (0) -> average = 50
        keywords = [
            {
                "keyword": "Python",  # Will be found everywhere
                "is_must_have": True,
                "is_identity": True,
                "is_core_strength": True,
                "priority_rank": 1,
            },
            {
                "keyword": "Scala",  # Will not be found
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 2,
            },
        ]

        result = validator.validate(
            headline="Python Expert",
            narrative="Python experience",
            competencies=["Python"],
            first_role_bullets=["Python projects"],
            priority_keywords=keywords,
        )

        # Python gets 100 (40+30+20+10), Scala gets 0 -> average = 50
        assert result.overall_score == 50

    def test_validate_must_have_score_calculation(self, validator):
        """Test that must_have_score is calculated correctly."""
        keywords = [
            {
                "keyword": "Python",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
            {
                "keyword": "Java",  # Will not be found
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 2,
            },
            {
                "keyword": "Rust",  # Nice to have, not must have
                "is_must_have": False,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 3,
            },
        ]

        result = validator.validate(
            headline="Python Developer",
            narrative="Python experience",
            competencies=["Python"],
            first_role_bullets=[],
            priority_keywords=keywords,
        )

        # 1 of 2 must-haves in top third = 50%
        assert result.must_have_score == 50

    def test_validate_identity_score_calculation(self, validator):
        """Test that identity_score is calculated correctly."""
        keywords = [
            {
                "keyword": "Python",  # In headline
                "is_must_have": False,
                "is_identity": True,
                "is_core_strength": False,
                "priority_rank": 1,
            },
            {
                "keyword": "Docker",  # Not in headline
                "is_must_have": False,
                "is_identity": True,
                "is_core_strength": False,
                "priority_rank": 2,
            },
        ]

        result = validator.validate(
            headline="Python Developer",  # Python yes, Docker no
            narrative="Experience with Docker",
            competencies=["Docker"],
            first_role_bullets=[],
            priority_keywords=keywords,
        )

        # 1 of 2 identity keywords in headline = 50%
        assert result.identity_score == 50

    def test_validate_no_must_have_keywords(self, validator):
        """Test validation when there are no must-have keywords."""
        keywords = [
            {
                "keyword": "Python",
                "is_must_have": False,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="",
            narrative="",
            competencies=[],
            first_role_bullets=[],
            priority_keywords=keywords,
        )

        # No must-haves means 100% must_have_score
        assert result.must_have_score == 100

    def test_validate_no_identity_keywords(self, validator):
        """Test validation when there are no identity keywords."""
        keywords = [
            {
                "keyword": "Python",
                "is_must_have": False,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
        ]

        result = validator.validate(
            headline="",
            narrative="",
            competencies=[],
            first_role_bullets=[],
            priority_keywords=keywords,
        )

        # No identity keywords means 100% identity_score
        assert result.identity_score == 100

    def test_validate_skips_empty_keyword(self, validator):
        """Test that empty keywords are skipped."""
        keywords = [
            {
                "keyword": "",  # Empty keyword
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
            {
                "keyword": "Python",
                "is_must_have": False,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 2,
            },
        ]

        result = validator.validate(
            headline="Python Developer",
            narrative="",
            competencies=[],
            first_role_bullets=[],
            priority_keywords=keywords,
        )

        # Only Python should be counted, empty keyword skipped
        assert result.total_keywords == 1


# =============================================================================
# extract_priority_keywords_from_annotations TESTS
# =============================================================================


class TestExtractPriorityKeywordsFromAnnotations:
    """Tests for the extract_priority_keywords_from_annotations helper function."""

    def test_extract_with_matching_skill(self, sample_jd_annotations):
        """Test extraction when matching_skill is present."""
        keywords = extract_priority_keywords_from_annotations(sample_jd_annotations)

        # Should have 3 keywords (ann-4 is inactive)
        assert len(keywords) == 3

        # First keyword should be Python (priority 1)
        python_kw = keywords[0]
        assert python_kw["keyword"] == "Python"
        assert python_kw["is_must_have"] is True
        assert python_kw["is_identity"] is True
        assert python_kw["is_core_strength"] is True

    def test_extract_without_matching_skill(self, sample_jd_annotations):
        """Test extraction falls back to suggested_keywords when no matching_skill."""
        keywords = extract_priority_keywords_from_annotations(sample_jd_annotations)

        # Third annotation has no matching_skill, uses suggested_keywords
        docker_kw = [k for k in keywords if k["keyword"] == "Docker"]
        assert len(docker_kw) == 1
        assert docker_kw[0]["is_must_have"] is False
        assert docker_kw[0]["is_core_strength"] is False

    def test_extract_skips_inactive_annotations(self, sample_jd_annotations):
        """Test that inactive annotations are skipped."""
        keywords = extract_priority_keywords_from_annotations(sample_jd_annotations)

        # Java should not be in the list (inactive annotation)
        java_keywords = [k for k in keywords if k["keyword"] == "Java"]
        assert len(java_keywords) == 0

    def test_extract_sorted_by_priority(self, sample_jd_annotations):
        """Test that keywords are sorted by priority_rank."""
        keywords = extract_priority_keywords_from_annotations(sample_jd_annotations)

        # Should be sorted by priority: Python (1), Kubernetes (2), Docker (3)
        assert keywords[0]["keyword"] == "Python"
        assert keywords[0]["priority_rank"] == 1
        assert keywords[1]["keyword"] == "Kubernetes"
        assert keywords[1]["priority_rank"] == 2
        assert keywords[2]["keyword"] == "Docker"
        assert keywords[2]["priority_rank"] == 3

    def test_extract_empty_annotations(self):
        """Test extraction with empty annotations list."""
        annotations = {"annotations": []}
        keywords = extract_priority_keywords_from_annotations(annotations)
        assert keywords == []

    def test_extract_no_annotations_key(self):
        """Test extraction when annotations key is missing."""
        annotations = {}
        keywords = extract_priority_keywords_from_annotations(annotations)
        assert keywords == []

    def test_extract_identity_levels(self):
        """Test that identity levels are correctly mapped."""
        annotations = {
            "annotations": [
                {
                    "id": "1",
                    "is_active": True,
                    "matching_skill": "Leadership",
                    "relevance": "relevant",
                    "requirement_type": "neutral",
                    "identity": "core_identity",
                    "priority": 1,
                },
                {
                    "id": "2",
                    "is_active": True,
                    "matching_skill": "Management",
                    "relevance": "relevant",
                    "requirement_type": "neutral",
                    "identity": "strong_identity",
                    "priority": 2,
                },
                {
                    "id": "3",
                    "is_active": True,
                    "matching_skill": "Coding",
                    "relevance": "relevant",
                    "requirement_type": "neutral",
                    "identity": "peripheral",
                    "priority": 3,
                },
            ]
        }

        keywords = extract_priority_keywords_from_annotations(annotations)

        # core_identity and strong_identity map to is_identity=True
        assert keywords[0]["is_identity"] is True  # core_identity
        assert keywords[1]["is_identity"] is True  # strong_identity
        assert keywords[2]["is_identity"] is False  # peripheral

    def test_extract_relevance_to_core_strength(self):
        """Test that relevance levels are correctly mapped to is_core_strength."""
        annotations = {
            "annotations": [
                {
                    "id": "1",
                    "is_active": True,
                    "matching_skill": "Python",
                    "relevance": "core_strength",
                    "requirement_type": "neutral",
                    "identity": "peripheral",
                    "priority": 1,
                },
                {
                    "id": "2",
                    "is_active": True,
                    "matching_skill": "Java",
                    "relevance": "extremely_relevant",
                    "requirement_type": "neutral",
                    "identity": "peripheral",
                    "priority": 2,
                },
                {
                    "id": "3",
                    "is_active": True,
                    "matching_skill": "Ruby",
                    "relevance": "relevant",
                    "requirement_type": "neutral",
                    "identity": "peripheral",
                    "priority": 3,
                },
            ]
        }

        keywords = extract_priority_keywords_from_annotations(annotations)

        # core_strength and extremely_relevant map to is_core_strength=True
        assert keywords[0]["is_core_strength"] is True  # core_strength
        assert keywords[1]["is_core_strength"] is True  # extremely_relevant
        assert keywords[2]["is_core_strength"] is False  # relevant

    def test_extract_skips_annotation_without_keyword(self):
        """Test that annotations without keywords are skipped."""
        annotations = {
            "annotations": [
                {
                    "id": "1",
                    "is_active": True,
                    "matching_skill": None,
                    "suggested_keywords": [],  # No keywords
                    "relevance": "relevant",
                    "requirement_type": "must_have",
                    "identity": "peripheral",
                    "priority": 1,
                },
                {
                    "id": "2",
                    "is_active": True,
                    "matching_skill": "Python",
                    "relevance": "relevant",
                    "requirement_type": "neutral",
                    "identity": "peripheral",
                    "priority": 2,
                },
            ]
        }

        keywords = extract_priority_keywords_from_annotations(annotations)

        # Only Python should be extracted
        assert len(keywords) == 1
        assert keywords[0]["keyword"] == "Python"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestKeywordPlacementIntegration:
    """Integration tests combining extraction and validation."""

    def test_full_workflow(self, validator, sample_jd_annotations, sample_cv_sections):
        """Test the full workflow: extract keywords then validate."""
        # Extract keywords from annotations
        keywords = extract_priority_keywords_from_annotations(sample_jd_annotations)

        # Validate placement in CV
        result = validator.validate(
            headline=sample_cv_sections["headline"],
            narrative=sample_cv_sections["narrative"],
            competencies=sample_cv_sections["competencies"],
            first_role_bullets=sample_cv_sections["first_role_bullets"],
            priority_keywords=keywords,
        )

        # Python and Kubernetes should be found
        python_placement = [p for p in result.placements if p.keyword == "Python"][0]
        k8s_placement = [p for p in result.placements if p.keyword == "Kubernetes"][0]

        assert python_placement.is_in_top_third is True
        assert k8s_placement.is_in_top_third is True

        # Docker won't be found in sample_cv_sections
        docker_placement = [p for p in result.placements if p.keyword == "Docker"]
        if docker_placement:
            assert docker_placement[0].is_in_top_third is False

    def test_workflow_generates_actionable_violations(
        self, validator, sample_cv_sections
    ):
        """Test that the workflow generates actionable violations."""
        keywords = [
            {
                "keyword": "Terraform",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": False,
                "priority_rank": 1,
            },
            {
                "keyword": "Infrastructure as Code",
                "is_must_have": False,
                "is_identity": True,
                "is_core_strength": False,
                "priority_rank": 2,
            },
        ]

        result = validator.validate(
            headline=sample_cv_sections["headline"],
            narrative=sample_cv_sections["narrative"],
            competencies=sample_cv_sections["competencies"],
            first_role_bullets=sample_cv_sections["first_role_bullets"],
            priority_keywords=keywords,
        )

        # Should have violations for both missing keywords
        assert len(result.violations) >= 1
        assert any("Terraform" in v for v in result.violations)

        # Should have suggestions
        assert len(result.suggestions) >= 1
