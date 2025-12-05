"""
Unit tests for VariantParser.

Tests the parsing of enhanced role files with achievement variants.
"""

import pytest
from pathlib import Path
from textwrap import dedent

from src.layer6_v2.variant_parser import (
    VariantParser,
    Achievement,
    AchievementVariant,
    EnhancedRoleData,
    RoleMetadata,
    SelectionGuide,
    parse_role_file,
    parse_all_roles,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_enhanced_content():
    """Sample enhanced role file content for testing."""
    return dedent("""
    # Test Company

    **Role**: Senior Software Engineer
    **Location**: Munich, DE
    **Period**: 2020–Present
    **Is Current**: true
    **Career Stage**: Senior (Position 1 of 3)
    **Duration**: 4 years

    ---

    ## Design Notes

    Testing variant selection approach.

    ---

    ## Achievements

    ### Achievement 1: Platform Modernization

    **Core Fact**: Led migration of legacy monolith to microservices architecture, reducing incidents by 75% and achieving zero downtime.

    **Variants**:
    - **Technical**: Architected microservices migration using Kubernetes and AWS Lambda, reducing incidents by 75%
    - **Architecture**: Designed distributed system architecture handling 10M requests/day with zero downtime
    - **Impact**: Reduced operational incidents by 75% through platform modernization initiative
    - **Leadership**: Led 12-person team through 18-month platform transformation
    - **Short**: Microservices migration—75% fewer incidents, zero downtime

    **Keywords**: microservices, Kubernetes, AWS Lambda, architecture, migration

    **Interview Defensibility**: Can explain migration strategy, Kubernetes patterns, incident metrics

    ---

    ### Achievement 2: Observability Pipeline

    **Core Fact**: Built real-time observability pipeline processing billions of events daily.

    **Variants**:
    - **Technical**: Architected event streaming pipeline using OpenSearch, processing billions of daily events
    - **Impact**: Enabled 10x cost reduction through real-time debugging capabilities
    - **Short**: Observability pipeline—billions of events, 10x cost savings

    **Keywords**: observability, OpenSearch, event streaming, monitoring

    **Interview Defensibility**: Can explain pipeline architecture and cost optimization

    **Business Context**: Legacy systems had no visibility into production issues.

    ---

    ## Skills

    **Hard Skills**: Python, TypeScript, Kubernetes, AWS, Docker, PostgreSQL

    **Soft Skills**: Leadership, Communication, Mentoring, Strategic Planning

    ---

    ## Selection Guide by JD Type

    | JD Emphasis | Recommended Achievements |
    |-------------|-------------------------|
    | Backend/Infrastructure | 1, 2 |
    | Leadership/Management | 1 |
    | DevOps/SRE | 2 |

    ---
    """).strip()


@pytest.fixture
def sample_legacy_content():
    """Sample legacy format role file content."""
    return dedent("""
    # Legacy Company

    **Role**: Software Engineer
    **Location**: Berlin, DE
    **Period**: 2018–2020
    **Is Current**: false
    **Career Stage**: Mid (Position 2 of 3)

    ---

    ## Achievements

    • Built REST API serving 1M users daily
    • Implemented CI/CD pipeline reducing deployment time by 80%
    • Led team of 5 engineers on payment integration project

    ---

    ## Skills

    **Hard Skills**: Python, Flask, PostgreSQL

    **Soft Skills**: Teamwork, Problem Solving
    """).strip()


@pytest.fixture
def parser():
    """Create a VariantParser instance."""
    return VariantParser()


@pytest.fixture
def temp_role_file(tmp_path, sample_enhanced_content):
    """Create a temporary role file for testing."""
    role_file = tmp_path / "01_test_company.md"
    role_file.write_text(sample_enhanced_content)
    return role_file


@pytest.fixture
def temp_legacy_file(tmp_path, sample_legacy_content):
    """Create a temporary legacy role file for testing."""
    role_file = tmp_path / "02_legacy_company.md"
    role_file.write_text(sample_legacy_content)
    return role_file


# ============================================================================
# TESTS: ENHANCED FORMAT PARSING
# ============================================================================

class TestVariantParserEnhancedFormat:
    """Tests for parsing enhanced format role files."""

    def test_parse_role_file_returns_enhanced_role_data(self, parser, temp_role_file):
        """Parser should return an EnhancedRoleData object."""
        result = parser.parse_role_file(temp_role_file)
        assert isinstance(result, EnhancedRoleData)

    def test_parse_role_metadata(self, parser, temp_role_file):
        """Parser should extract role metadata correctly."""
        result = parser.parse_role_file(temp_role_file)

        assert result.metadata.company == "Test Company"
        assert result.metadata.title == "Senior Software Engineer"
        assert result.metadata.location == "Munich, DE"
        assert result.metadata.period == "2020–Present"
        assert result.metadata.is_current is True
        assert "Senior" in result.metadata.career_stage

    def test_parse_achievements_count(self, parser, temp_role_file):
        """Parser should extract correct number of achievements."""
        result = parser.parse_role_file(temp_role_file)
        assert len(result.achievements) == 2

    def test_parse_achievement_title(self, parser, temp_role_file):
        """Parser should extract achievement titles correctly."""
        result = parser.parse_role_file(temp_role_file)

        assert result.achievements[0].title == "Platform Modernization"
        assert result.achievements[1].title == "Observability Pipeline"

    def test_parse_achievement_core_fact(self, parser, temp_role_file):
        """Parser should extract core facts correctly."""
        result = parser.parse_role_file(temp_role_file)

        assert "microservices" in result.achievements[0].core_fact.lower()
        assert "75%" in result.achievements[0].core_fact

    def test_parse_achievement_variants(self, parser, temp_role_file):
        """Parser should extract all variants for an achievement."""
        result = parser.parse_role_file(temp_role_file)
        achievement1 = result.achievements[0]

        assert len(achievement1.variants) == 5
        assert "Technical" in achievement1.variants
        assert "Architecture" in achievement1.variants
        assert "Impact" in achievement1.variants
        assert "Leadership" in achievement1.variants
        assert "Short" in achievement1.variants

    def test_parse_variant_content(self, parser, temp_role_file):
        """Parser should extract variant text correctly."""
        result = parser.parse_role_file(temp_role_file)
        technical_variant = result.achievements[0].variants["Technical"]

        assert isinstance(technical_variant, AchievementVariant)
        assert "Kubernetes" in technical_variant.text
        assert "75%" in technical_variant.text

    def test_parse_achievement_keywords(self, parser, temp_role_file):
        """Parser should extract keywords for each achievement."""
        result = parser.parse_role_file(temp_role_file)

        keywords = result.achievements[0].keywords
        assert "microservices" in keywords
        assert "Kubernetes" in keywords
        assert "AWS Lambda" in keywords

    def test_parse_interview_defensibility(self, parser, temp_role_file):
        """Parser should extract interview defensibility notes."""
        result = parser.parse_role_file(temp_role_file)

        defensibility = result.achievements[0].interview_defensibility
        assert "migration strategy" in defensibility.lower() or "kubernetes" in defensibility.lower()

    def test_parse_business_context(self, parser, temp_role_file):
        """Parser should extract business context when present."""
        result = parser.parse_role_file(temp_role_file)

        # Achievement 2 has business context
        assert "legacy" in result.achievements[1].business_context.lower()

    def test_parse_hard_skills(self, parser, temp_role_file):
        """Parser should extract hard skills."""
        result = parser.parse_role_file(temp_role_file)

        assert "Python" in result.hard_skills
        assert "Kubernetes" in result.hard_skills
        assert "AWS" in result.hard_skills

    def test_parse_soft_skills(self, parser, temp_role_file):
        """Parser should extract soft skills."""
        result = parser.parse_role_file(temp_role_file)

        assert "Leadership" in result.soft_skills
        assert "Mentoring" in result.soft_skills

    def test_parse_selection_guide(self, parser, temp_role_file):
        """Parser should extract selection guide mappings."""
        result = parser.parse_role_file(temp_role_file)

        assert result.selection_guide is not None
        assert "Backend/Infrastructure" in result.selection_guide.mappings

        backend_achievements = result.selection_guide.get_recommended("Backend/Infrastructure")
        assert "achievement_1" in backend_achievements
        assert "achievement_2" in backend_achievements

    def test_all_keywords_property(self, parser, temp_role_file):
        """Parser should aggregate all keywords from all achievements."""
        result = parser.parse_role_file(temp_role_file)

        all_keywords = result.all_keywords
        assert "microservices" in all_keywords
        assert "observability" in all_keywords

    def test_total_variants_property(self, parser, temp_role_file):
        """Parser should calculate total variants correctly."""
        result = parser.parse_role_file(temp_role_file)

        # Achievement 1 has 5 variants, Achievement 2 has 3 variants
        assert result.total_variants == 8


# ============================================================================
# TESTS: LEGACY FORMAT FALLBACK
# ============================================================================

class TestVariantParserLegacyFormat:
    """Tests for parsing legacy format role files."""

    def test_detects_legacy_format(self, parser, temp_legacy_file):
        """Parser should detect legacy format and fall back gracefully."""
        result = parser.parse_role_file(temp_legacy_file)
        assert isinstance(result, EnhancedRoleData)

    def test_legacy_achievements_have_original_variant(self, parser, temp_legacy_file):
        """Legacy achievements should have 'Original' variant."""
        result = parser.parse_role_file(temp_legacy_file)

        for achievement in result.achievements:
            assert "Original" in achievement.variants
            assert achievement.variants["Original"].text == achievement.core_fact

    def test_legacy_metadata_parsed(self, parser, temp_legacy_file):
        """Legacy format should still parse metadata."""
        result = parser.parse_role_file(temp_legacy_file)

        assert result.metadata.company == "Legacy Company"
        assert result.metadata.is_current is False

    def test_legacy_skills_parsed(self, parser, temp_legacy_file):
        """Legacy format should still parse skills."""
        result = parser.parse_role_file(temp_legacy_file)

        assert "Python" in result.hard_skills
        assert "Teamwork" in result.soft_skills


# ============================================================================
# TESTS: ACHIEVEMENT HELPER METHODS
# ============================================================================

class TestAchievementMethods:
    """Tests for Achievement class methods."""

    def test_get_variant_returns_correct_variant(self, parser, temp_role_file):
        """get_variant should return the requested variant type."""
        result = parser.parse_role_file(temp_role_file)
        achievement = result.achievements[0]

        technical = achievement.get_variant("Technical")
        assert technical is not None
        assert technical.variant_type == "Technical"

    def test_get_variant_fallback(self, parser, temp_role_file):
        """get_variant should fall back to Technical if requested type not found."""
        result = parser.parse_role_file(temp_role_file)
        achievement = result.achievements[0]

        # Request a non-existent variant type
        variant = achievement.get_variant("NonExistent")
        assert variant is not None
        assert variant.variant_type == "Technical"

    def test_has_all_standard_variants(self, parser, temp_role_file):
        """has_all_standard_variants should return True when all present."""
        result = parser.parse_role_file(temp_role_file)

        # Achievement 1 has all 5 standard variants
        assert result.achievements[0].has_all_standard_variants is True

        # Achievement 2 has only 3 variants
        assert result.achievements[1].has_all_standard_variants is False

    def test_variant_word_count(self, parser, temp_role_file):
        """AchievementVariant should calculate word count."""
        result = parser.parse_role_file(temp_role_file)
        short_variant = result.achievements[0].variants["Short"]

        assert short_variant.word_count > 0
        assert short_variant.word_count < 20  # Short variants are concise


# ============================================================================
# TESTS: ENHANCED ROLE DATA METHODS
# ============================================================================

class TestEnhancedRoleDataMethods:
    """Tests for EnhancedRoleData class methods."""

    def test_get_achievement_by_id(self, parser, temp_role_file):
        """get_achievement_by_id should return correct achievement."""
        result = parser.parse_role_file(temp_role_file)

        achievement = result.get_achievement_by_id("achievement_1")
        assert achievement is not None
        assert achievement.title == "Platform Modernization"

    def test_get_achievement_by_number(self, parser, temp_role_file):
        """get_achievement_by_number should return correct achievement."""
        result = parser.parse_role_file(temp_role_file)

        achievement = result.get_achievement_by_number(2)
        assert achievement is not None
        assert achievement.title == "Observability Pipeline"

    def test_to_dict_serialization(self, parser, temp_role_file):
        """to_dict should produce valid dictionary representation."""
        result = parser.parse_role_file(temp_role_file)
        data = result.to_dict()

        assert "id" in data
        assert "metadata" in data
        assert "achievements" in data
        assert "hard_skills" in data
        assert data["achievement_count"] == 2


# ============================================================================
# TESTS: SELECTION GUIDE
# ============================================================================

class TestSelectionGuide:
    """Tests for SelectionGuide class."""

    def test_get_recommended_exact_match(self, parser, temp_role_file):
        """get_recommended should return achievements for exact match."""
        result = parser.parse_role_file(temp_role_file)
        guide = result.selection_guide

        recommendations = guide.get_recommended("DevOps/SRE")
        assert "achievement_2" in recommendations

    def test_get_recommended_partial_match(self, parser, temp_role_file):
        """get_recommended should work with partial matches."""
        result = parser.parse_role_file(temp_role_file)
        guide = result.selection_guide

        # "backend" should match "Backend/Infrastructure"
        recommendations = guide.get_recommended("backend")
        assert len(recommendations) > 0

    def test_get_recommended_no_match(self, parser, temp_role_file):
        """get_recommended should return empty list for no match."""
        result = parser.parse_role_file(temp_role_file)
        guide = result.selection_guide

        recommendations = guide.get_recommended("NonExistentCategory")
        assert recommendations == []


# ============================================================================
# TESTS: ERROR HANDLING
# ============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    def test_file_not_found(self, parser):
        """Parser should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parser.parse_role_file(Path("/nonexistent/path.md"))

    def test_empty_file(self, parser, tmp_path):
        """Parser should handle empty files gracefully."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        result = parser.parse_role_file(empty_file)
        assert result.achievement_count == 0


# ============================================================================
# TESTS: CONVENIENCE FUNCTIONS
# ============================================================================

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_parse_role_file_function(self, temp_role_file):
        """parse_role_file convenience function should work."""
        result = parse_role_file(temp_role_file)
        assert isinstance(result, EnhancedRoleData)

    def test_parse_all_roles_function(self, tmp_path, sample_enhanced_content, sample_legacy_content):
        """parse_all_roles should parse all files in directory."""
        # Create multiple role files
        (tmp_path / "01_role.md").write_text(sample_enhanced_content)
        (tmp_path / "02_role.md").write_text(sample_legacy_content)

        roles = parse_all_roles(tmp_path)
        assert len(roles) == 2
        assert "01_role" in roles
        assert "02_role" in roles


# ============================================================================
# TESTS: REAL ROLE FILES (INTEGRATION)
# ============================================================================

class TestRealRoleFiles:
    """Integration tests with actual role files."""

    @pytest.fixture
    def real_roles_dir(self):
        """Get path to real role files."""
        return Path("data/master-cv/roles")

    @pytest.mark.skipif(
        not Path("data/master-cv/roles").exists(),
        reason="Real role files not available"
    )
    def test_parse_real_role_file(self, parser, real_roles_dir):
        """Parser should successfully parse real enhanced role files."""
        # Try to parse the first role file found
        role_files = list(real_roles_dir.glob("*.md"))
        if not role_files:
            pytest.skip("No role files found")

        result = parser.parse_role_file(role_files[0])
        assert result.achievement_count > 0
        assert result.total_variants > 0

    @pytest.mark.skipif(
        not Path("data/master-cv/roles").exists(),
        reason="Real role files not available"
    )
    def test_parse_all_real_roles(self, parser, real_roles_dir):
        """Parser should successfully parse all real role files."""
        roles = parser.parse_all_roles(real_roles_dir)
        assert len(roles) >= 1

        # Verify each role has achievements
        for role_id, role_data in roles.items():
            assert role_data.achievement_count > 0, f"{role_id} has no achievements"
