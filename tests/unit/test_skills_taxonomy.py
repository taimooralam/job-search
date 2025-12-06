"""
Unit tests for the Skills Taxonomy Module.

Tests the role-based skills taxonomy system that replaces
LLM-generated categories with pre-defined, curated sections.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.layer6_v2.skills_taxonomy import (
    SkillsTaxonomy,
    TaxonomyBasedSkillsGenerator,
    create_taxonomy_generator,
)
from src.layer6_v2.types import (
    TaxonomySection,
    RoleSkillsTaxonomy,
    SectionScore,
    SkillScore,
    SkillEvidence,
    SkillsSection,
)


class TestSkillsTaxonomy:
    """Tests for SkillsTaxonomy class."""

    @pytest.fixture
    def taxonomy(self):
        """Load the actual taxonomy file."""
        return SkillsTaxonomy()

    def test_load_taxonomy_success(self, taxonomy):
        """Test taxonomy loads successfully."""
        assert taxonomy is not None
        roles = taxonomy.get_available_roles()
        assert len(roles) >= 6  # At least 6 target roles

    def test_get_available_roles(self, taxonomy):
        """Test getting available role categories."""
        roles = taxonomy.get_available_roles()
        assert "engineering_manager" in roles
        assert "staff_principal_engineer" in roles
        assert "director_of_engineering" in roles
        assert "head_of_engineering" in roles
        assert "cto" in roles
        assert "tech_lead" in roles

    def test_get_role_taxonomy_engineering_manager(self, taxonomy):
        """Test getting taxonomy for engineering manager."""
        role_taxonomy = taxonomy.get_role_taxonomy("engineering_manager")

        assert role_taxonomy.role_category == "engineering_manager"
        assert role_taxonomy.display_name == "Engineering Manager"
        assert len(role_taxonomy.sections) >= 4
        assert role_taxonomy.max_sections == 4
        assert role_taxonomy.lax_multiplier == 1.3

    def test_get_role_taxonomy_sections_have_required_fields(self, taxonomy):
        """Test that each section has all required fields."""
        role_taxonomy = taxonomy.get_role_taxonomy("engineering_manager")

        for section in role_taxonomy.sections:
            assert section.name, "Section must have a name"
            assert section.priority >= 1, "Section must have a priority"
            assert len(section.skills) > 0, "Section must have skills"
            assert len(section.jd_signals) > 0, "Section must have JD signals"

    def test_get_role_taxonomy_unknown_role_fallback(self, taxonomy):
        """Test that unknown role falls back to default."""
        role_taxonomy = taxonomy.get_role_taxonomy("unknown_role_xyz")

        # Should fall back to engineering_manager
        assert role_taxonomy.role_category == "engineering_manager"

    def test_skill_matches_direct(self, taxonomy):
        """Test direct skill matching."""
        assert taxonomy.skill_matches("AWS", "aws")
        assert taxonomy.skill_matches("aws", "AWS")
        assert taxonomy.skill_matches("TypeScript", "typescript")

    def test_skill_matches_alias(self, taxonomy):
        """Test alias-based skill matching."""
        # DDD should match Domain-Driven Design
        assert taxonomy.skill_matches("DDD", "domain-driven design")
        assert taxonomy.skill_matches("Domain-Driven Design", "ddd")

    def test_get_skill_aliases(self, taxonomy):
        """Test getting aliases for a skill."""
        aliases = taxonomy.get_skill_aliases("aws lambda")
        assert "Lambda" in aliases or "AWS Lambda" in aliases


class TestTaxonomyBasedSkillsGenerator:
    """Tests for TaxonomyBasedSkillsGenerator class."""

    @pytest.fixture
    def taxonomy(self):
        """Load the actual taxonomy."""
        return SkillsTaxonomy()

    @pytest.fixture
    def skill_whitelist(self):
        """Sample skill whitelist."""
        return {
            "hard_skills": [
                "TypeScript", "Python", "AWS", "AWS Lambda", "Terraform",
                "Microservices", "Event-Driven Architecture", "Docker",
                "CI/CD", "MongoDB", "REST API"
            ],
            "soft_skills": [
                "Technical Leadership", "Mentoring", "Team Building",
                "Hiring & Interviewing", "Stakeholder Management", "Agile"
            ],
        }

    @pytest.fixture
    def generator(self, taxonomy, skill_whitelist):
        """Create a generator instance."""
        return TaxonomyBasedSkillsGenerator(
            taxonomy=taxonomy,
            skill_whitelist=skill_whitelist,
            lax_mode=True,
        )

    @pytest.fixture
    def sample_bullets(self):
        """Sample experience bullets for testing."""
        return [
            "Led a team of 10 engineers to modernize legacy platform using TypeScript and AWS Lambda",
            "Architected event-driven microservices handling 50M daily events using EventBridge",
            "Mentored 5 junior engineers, achieving 100% promotion rate within 2 years",
            "Implemented CI/CD pipeline reducing deployment time by 70%",
            "Built scalable REST APIs using Python and MongoDB serving 1M users",
            "Drove adoption of Domain-Driven Design across 3 product teams",
            "Hired and onboarded 8 engineers while maintaining team velocity",
        ]

    def test_generator_initialization(self, generator):
        """Test generator initializes correctly."""
        assert generator is not None
        assert generator._lax_mode is True

    def test_skill_in_whitelist_direct(self, generator):
        """Test whitelist check with direct match."""
        assert generator._skill_in_whitelist("TypeScript")
        assert generator._skill_in_whitelist("Python")
        assert generator._skill_in_whitelist("Technical Leadership")

    def test_skill_not_in_whitelist(self, generator):
        """Test whitelist check with non-existent skill."""
        assert not generator._skill_in_whitelist("Java")
        assert not generator._skill_in_whitelist("React")
        assert not generator._skill_in_whitelist("PHP")

    def test_skill_matches_jd_direct(self, generator):
        """Test JD keyword matching with direct match."""
        jd_keywords = {"typescript", "aws", "microservices"}
        assert generator._skill_matches_jd("TypeScript", jd_keywords)
        assert generator._skill_matches_jd("AWS", jd_keywords)

    def test_skill_matches_jd_substring(self, generator):
        """Test JD keyword matching with substring."""
        jd_keywords = {"aws lambda", "event-driven architecture"}
        assert generator._skill_matches_jd("AWS Lambda", jd_keywords)
        assert generator._skill_matches_jd("AWS", jd_keywords)  # substring match

    def test_find_skill_evidence_direct_mention(self, generator, sample_bullets):
        """Test finding evidence with direct skill mention."""
        evidence = generator._find_skill_evidence(
            "TypeScript", sample_bullets, ["Company A"] * len(sample_bullets)
        )
        assert evidence is not None
        assert evidence.skill == "TypeScript"
        assert len(evidence.evidence_bullets) > 0

    def test_find_skill_evidence_pattern_match(self, generator, sample_bullets):
        """Test finding evidence with pattern matching."""
        evidence = generator._find_skill_evidence(
            "Hiring & Interviewing", sample_bullets, ["Company A"] * len(sample_bullets)
        )
        assert evidence is not None
        assert len(evidence.evidence_bullets) > 0
        # Should match "Hired and onboarded" bullet

    def test_find_skill_evidence_no_match(self, generator, sample_bullets):
        """Test no evidence found for non-mentioned skill."""
        evidence = generator._find_skill_evidence(
            "Java", sample_bullets, ["Company A"] * len(sample_bullets)
        )
        assert evidence is None

    def test_select_sections_returns_correct_count(self, generator, taxonomy):
        """Test that section selection respects max_sections."""
        role_taxonomy = taxonomy.get_role_taxonomy("engineering_manager")

        jd_keywords = ["technical leadership", "aws", "agile", "team management"]
        jd_responsibilities = ["Lead engineering team", "Drive technical excellence"]

        selected = generator._select_sections(
            role_taxonomy=role_taxonomy,
            jd_keywords=jd_keywords,
            jd_responsibilities=jd_responsibilities,
        )

        assert len(selected) <= role_taxonomy.max_sections
        assert len(selected) >= 3  # MIN_SECTIONS

    def test_generate_sections_integration(self, generator, sample_bullets):
        """Integration test for full section generation."""
        extracted_jd = {
            "role_category": "engineering_manager",
            "top_keywords": ["technical leadership", "aws", "microservices", "team"],
            "technical_skills": ["TypeScript", "Python", "AWS"],
            "responsibilities": [
                "Lead and mentor a team of engineers",
                "Drive technical architecture decisions",
            ],
        }

        role_companies = ["Company A"] * len(sample_bullets)

        sections = generator.generate_sections(
            extracted_jd=extracted_jd,
            experience_bullets=sample_bullets,
            role_companies=role_companies,
        )

        assert len(sections) >= 1
        assert all(isinstance(s, SkillsSection) for s in sections)

        # Check that sections have skills
        for section in sections:
            assert section.category  # Has a name
            assert len(section.skills) > 0  # Has skills

    def test_lax_mode_generates_more_skills(self, taxonomy, skill_whitelist, sample_bullets):
        """Test that lax mode generates more skills."""
        lax_generator = TaxonomyBasedSkillsGenerator(
            taxonomy=taxonomy,
            skill_whitelist=skill_whitelist,
            lax_mode=True,
        )
        strict_generator = TaxonomyBasedSkillsGenerator(
            taxonomy=taxonomy,
            skill_whitelist=skill_whitelist,
            lax_mode=False,
        )

        extracted_jd = {
            "role_category": "engineering_manager",
            "top_keywords": ["leadership", "aws"],
            "technical_skills": ["TypeScript"],
            "responsibilities": [],
        }
        role_companies = ["Company A"] * len(sample_bullets)

        lax_sections = lax_generator.generate_sections(
            extracted_jd, sample_bullets, role_companies
        )
        strict_sections = strict_generator.generate_sections(
            extracted_jd, sample_bullets, role_companies
        )

        lax_total = sum(s.skill_count for s in lax_sections)
        strict_total = sum(s.skill_count for s in strict_sections)

        # Lax mode should generate at least as many skills
        assert lax_total >= strict_total


class TestTaxonomyTypes:
    """Tests for taxonomy-related type classes."""

    def test_taxonomy_section_to_dict(self):
        """Test TaxonomySection serialization."""
        section = TaxonomySection(
            name="Technical Leadership",
            priority=1,
            description="Leadership skills",
            skills=["Technical Vision", "Mentoring"],
            jd_signals=["lead", "mentor"],
        )

        data = section.to_dict()
        assert data["name"] == "Technical Leadership"
        assert data["priority"] == 1
        assert len(data["skills"]) == 2

    def test_role_skills_taxonomy_all_skills(self):
        """Test RoleSkillsTaxonomy.all_skills property."""
        sections = [
            TaxonomySection(
                name="Leadership",
                priority=1,
                description="",
                skills=["A", "B"],
                jd_signals=[],
            ),
            TaxonomySection(
                name="Technical",
                priority=2,
                description="",
                skills=["C", "D"],
                jd_signals=[],
            ),
        ]

        taxonomy = RoleSkillsTaxonomy(
            role_category="test",
            display_name="Test",
            sections=sections,
        )

        all_skills = taxonomy.all_skills
        assert len(all_skills) == 4
        assert "A" in all_skills
        assert "D" in all_skills

    def test_section_score_calculation(self):
        """Test SectionScore auto-calculation."""
        section = TaxonomySection(
            name="Test", priority=1, description="", skills=[], jd_signals=[]
        )

        score = SectionScore(
            section=section,
            jd_keyword_score=0.8,
            responsibility_score=0.6,
            priority_score=1.0,
        )

        # Expected: 0.5 * 0.8 + 0.3 * 0.6 + 0.2 * 1.0 = 0.4 + 0.18 + 0.2 = 0.78
        assert abs(score.total_score - 0.78) < 0.01

    def test_skill_score_calculation(self):
        """Test SkillScore auto-calculation."""
        score = SkillScore(
            skill="TypeScript",
            jd_match_score=1.0,
            evidence_score=0.5,
            recency_score=0.8,
        )

        # Expected: 0.4 * 1.0 + 0.3 * 0.5 + 0.3 * 0.8 = 0.4 + 0.15 + 0.24 = 0.79
        assert abs(score.total_score - 0.79) < 0.01


class TestAntiHallucination:
    """Tests for anti-hallucination measures."""

    @pytest.fixture
    def taxonomy(self):
        return SkillsTaxonomy()

    @pytest.fixture
    def limited_whitelist(self):
        """Whitelist with only a few skills."""
        return {
            "hard_skills": ["Python", "AWS"],
            "soft_skills": ["Mentoring"],
        }

    def test_non_whitelist_skills_excluded(self, taxonomy, limited_whitelist):
        """Test that skills not in whitelist are excluded."""
        generator = TaxonomyBasedSkillsGenerator(
            taxonomy=taxonomy,
            skill_whitelist=limited_whitelist,
            lax_mode=True,
        )

        # Java is not in whitelist
        assert not generator._skill_in_whitelist("Java")
        assert not generator._skill_in_whitelist("React")
        assert not generator._skill_in_whitelist("TypeScript")

    def test_no_evidence_skills_excluded(self, taxonomy):
        """Test that skills without evidence are excluded."""
        whitelist = {
            "hard_skills": ["TypeScript", "Java"],  # Java in whitelist
            "soft_skills": [],
        }

        generator = TaxonomyBasedSkillsGenerator(
            taxonomy=taxonomy,
            skill_whitelist=whitelist,
            lax_mode=True,
        )

        # Bullets that mention TypeScript but not Java
        bullets = ["Built platform using TypeScript"]
        companies = ["Company A"]

        # TypeScript should have evidence
        ts_evidence = generator._find_skill_evidence("TypeScript", bullets, companies)
        assert ts_evidence is not None

        # Java should NOT have evidence even though it's in whitelist
        java_evidence = generator._find_skill_evidence("Java", bullets, companies)
        assert java_evidence is None


class TestCreateTaxonomyGenerator:
    """Tests for the factory function."""

    def test_create_taxonomy_generator(self):
        """Test factory function creates generator correctly."""
        whitelist = {
            "hard_skills": ["Python"],
            "soft_skills": ["Leadership"],
        }

        generator = create_taxonomy_generator(
            skill_whitelist=whitelist,
            lax_mode=True,
        )

        assert isinstance(generator, TaxonomyBasedSkillsGenerator)
        assert generator._lax_mode is True
