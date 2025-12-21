"""
Unit Tests for Layer 6 V2 Phase 3: Per-Role Generator

Tests:
- Types: GeneratedBullet, RoleBullets, CareerContext
- RoleGenerator: LLM response parsing and validation
- RoleQA: Hallucination detection and ATS keyword checking
- Prompts: Role generation prompt building
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    QAResult,
    ATSResult,
    CareerContext,
)
from src.layer6_v2.cv_loader import RoleData
from src.layer6_v2.role_generator import (
    RoleGenerator,
    GeneratedBulletModel,
    RoleBulletsResponseModel,
    generate_all_roles_sequential,
)
from src.layer6_v2.role_qa import RoleQA, run_qa_on_all_roles
from src.layer6_v2.prompts.role_generation import (
    ROLE_GENERATION_SYSTEM_PROMPT,
    build_role_generation_user_prompt,
)
from src.common.state import ExtractedJD


# ===== FIXTURES =====

@pytest.fixture
def sample_role_data():
    """Sample RoleData for testing."""
    return RoleData(
        id="01_test_company",
        company="Test Company",
        title="Technical Lead",
        location="Munich, DE",
        period="2020–Present",
        start_year=2020,
        end_year=None,
        is_current=True,
        duration_years=4,
        industry="AdTech",
        team_size="10+",
        primary_competencies=["leadership", "architecture"],
        keywords=["AWS", "DDD", "microservices"],
        achievements=[
            "Led team of 10 engineers to deliver critical platform migration",
            "Reduced incident rate by 75% through architectural improvements",
            "Implemented observability pipeline processing 1B events daily",
            "Mentored 5 senior engineers, promoting 2 to lead positions",
        ],
        hard_skills=["Python", "AWS", "Kubernetes"],
        soft_skills=["Leadership", "Mentoring"],
    )


@pytest.fixture
def sample_extracted_jd():
    """Sample ExtractedJD for testing."""
    return ExtractedJD(
        title="Engineering Manager",
        company="Target Company",
        location="Berlin, DE",
        remote_policy="hybrid",
        role_category="engineering_manager",
        seniority_level="director",
        competency_weights={
            "delivery": 25,
            "process": 20,
            "architecture": 25,
            "leadership": 30,
        },
        responsibilities=[
            "Lead engineering team of 8-12 engineers",
            "Drive technical strategy and architecture decisions",
        ],
        qualifications=[
            "5+ years leading engineering teams",
            "Experience with cloud platforms (AWS/GCP)",
        ],
        nice_to_haves=["AdTech experience"],
        technical_skills=["Python", "AWS", "Kubernetes", "microservices"],
        soft_skills=["Leadership", "Communication"],
        implied_pain_points=[
            "Need strong technical leadership",
            "Scaling challenges with current architecture",
        ],
        success_metrics=["Team velocity improvement", "Reduced incident rate"],
        top_keywords=[
            "leadership", "AWS", "Python", "microservices", "team",
            "architecture", "DevOps", "agile", "mentoring", "scaling",
            "incident", "observability", "engineering", "strategy", "cloud"
        ],
        industry_background="AdTech",
        years_experience_required=8,
        education_requirements="BS in CS or equivalent",
    )


@pytest.fixture
def sample_career_context():
    """Sample CareerContext for testing."""
    return CareerContext.build(
        role_index=0,
        total_roles=6,
        is_current=True,
        target_role_category="engineering_manager",
    )


@pytest.fixture
def sample_generated_bullets():
    """Sample generated bullets for testing."""
    return [
        GeneratedBullet(
            text="Led team of 10 engineers to successfully deliver critical platform migration ahead of schedule",
            source_text="Led team of 10 engineers to deliver critical platform migration",
            source_metric="10",
            jd_keyword_used="team",
            pain_point_addressed="Need strong technical leadership",
        ),
        GeneratedBullet(
            text="Reduced production incident rate by 75% through implementing architectural improvements",
            source_text="Reduced incident rate by 75% through architectural improvements",
            source_metric="75%",
            jd_keyword_used="incident",
            pain_point_addressed="Scaling challenges",
        ),
    ]


@pytest.fixture
def sample_role_bullets(sample_role_data, sample_generated_bullets):
    """Sample RoleBullets for testing."""
    return RoleBullets(
        role_id=sample_role_data.id,
        company=sample_role_data.company,
        title=sample_role_data.title,
        period=sample_role_data.period,
        bullets=sample_generated_bullets,
        keywords_integrated=["team", "incident"],
    )


# ===== TESTS: GeneratedBullet =====

class TestGeneratedBullet:
    """Test GeneratedBullet dataclass."""

    def test_creates_with_required_fields(self):
        """Creates GeneratedBullet with required fields."""
        bullet = GeneratedBullet(
            text="Led team of 10 engineers",
            source_text="Led team of 10 engineers",
        )
        assert bullet.text == "Led team of 10 engineers"
        assert bullet.source_text == "Led team of 10 engineers"
        assert bullet.source_metric is None
        assert bullet.jd_keyword_used is None

    def test_calculates_word_count(self):
        """Calculates word count automatically."""
        bullet = GeneratedBullet(
            text="Led team of 10 engineers to deliver",
            source_text="source",
        )
        assert bullet.word_count == 7

    def test_to_dict(self):
        """Converts to dictionary correctly."""
        bullet = GeneratedBullet(
            text="Test bullet text",
            source_text="Source text",
            source_metric="75%",
            jd_keyword_used="leadership",
            pain_point_addressed="Need leader",
        )
        d = bullet.to_dict()
        assert d["text"] == "Test bullet text"
        assert d["source_metric"] == "75%"
        assert d["jd_keyword_used"] == "leadership"


# ===== TESTS: RoleBullets =====

class TestRoleBullets:
    """Test RoleBullets dataclass."""

    def test_calculates_total_word_count(self, sample_generated_bullets):
        """Calculates total word count across bullets."""
        role_bullets = RoleBullets(
            role_id="test",
            company="Test Co",
            title="Lead",
            period="2020-2024",
            bullets=sample_generated_bullets,
        )
        # Word counts: 14 + 11 = 25 (approximate)
        assert role_bullets.word_count > 0

    def test_bullet_count_property(self, sample_generated_bullets):
        """Returns bullet count via property."""
        role_bullets = RoleBullets(
            role_id="test",
            company="Test Co",
            title="Lead",
            period="2020-2024",
            bullets=sample_generated_bullets,
        )
        assert role_bullets.bullet_count == 2

    def test_bullet_texts_property(self, sample_generated_bullets):
        """Returns list of bullet texts."""
        role_bullets = RoleBullets(
            role_id="test",
            company="Test Co",
            title="Lead",
            period="2020-2024",
            bullets=sample_generated_bullets,
        )
        texts = role_bullets.bullet_texts
        assert len(texts) == 2
        assert "Led team of 10" in texts[0]

    def test_qa_passed_property_no_qa(self, sample_generated_bullets):
        """Returns True when no QA has been run."""
        role_bullets = RoleBullets(
            role_id="test",
            company="Test Co",
            title="Lead",
            period="2020-2024",
            bullets=sample_generated_bullets,
        )
        assert role_bullets.qa_passed is True

    def test_qa_passed_property_with_result(self, sample_generated_bullets):
        """Returns QA result when available."""
        role_bullets = RoleBullets(
            role_id="test",
            company="Test Co",
            title="Lead",
            period="2020-2024",
            bullets=sample_generated_bullets,
            qa_result=QAResult(
                passed=False,
                flagged_bullets=["test"],
                issues=["issue"],
                verified_metrics=[],
                confidence=0.5,
            ),
        )
        assert role_bullets.qa_passed is False


# ===== TESTS: CareerContext =====

class TestCareerContext:
    """Test CareerContext dataclass."""

    def test_builds_recent_career_stage(self):
        """Builds 'recent' stage for current role."""
        ctx = CareerContext.build(
            role_index=0,
            total_roles=6,
            is_current=True,
            target_role_category="engineering_manager",
        )
        assert ctx.career_stage == "recent"
        assert "MAXIMUM emphasis" in ctx.emphasis_guidance

    def test_builds_mid_career_stage(self):
        """Builds 'mid-career' stage for roles 1-2."""
        ctx = CareerContext.build(
            role_index=2,
            total_roles=6,
            is_current=False,
            target_role_category="engineering_manager",
        )
        assert ctx.career_stage == "mid-career"
        assert "MODERATE detail" in ctx.emphasis_guidance

    def test_builds_early_career_stage(self):
        """Builds 'early' stage for roles 3+."""
        ctx = CareerContext.build(
            role_index=4,
            total_roles=6,
            is_current=False,
            target_role_category="staff_principal_engineer",
        )
        assert ctx.career_stage == "early"
        assert "BRIEF summary" in ctx.emphasis_guidance

    def test_ic_emphasis_for_staff_role(self):
        """Uses IC emphasis for staff/principal roles."""
        ctx = CareerContext.build(
            role_index=0,
            total_roles=1,
            is_current=True,
            target_role_category="staff_principal_engineer",
        )
        assert "technical depth" in ctx.emphasis_guidance.lower()

    def test_leadership_emphasis_for_manager_role(self):
        """Uses leadership emphasis for manager roles."""
        ctx = CareerContext.build(
            role_index=0,
            total_roles=1,
            is_current=True,
            target_role_category="engineering_manager",
        )
        assert "leadership" in ctx.emphasis_guidance.lower()


# ===== TESTS: Role Generation Prompts =====

class TestRoleGenerationPrompts:
    """Test prompt building."""

    def test_system_prompt_has_anti_hallucination(self):
        """System prompt includes anti-hallucination rules."""
        assert "ANTI-HALLUCINATION" in ROLE_GENERATION_SYSTEM_PROMPT
        assert "ONLY use achievements" in ROLE_GENERATION_SYSTEM_PROMPT
        assert "EXACT" in ROLE_GENERATION_SYSTEM_PROMPT

    def test_system_prompt_has_output_format(self):
        """System prompt includes JSON output format."""
        assert "bullets" in ROLE_GENERATION_SYSTEM_PROMPT
        assert "source_text" in ROLE_GENERATION_SYSTEM_PROMPT
        assert "source_metric" in ROLE_GENERATION_SYSTEM_PROMPT

    def test_user_prompt_includes_role_data(
        self, sample_role_data, sample_extracted_jd, sample_career_context
    ):
        """User prompt includes role information."""
        prompt = build_role_generation_user_prompt(
            role=sample_role_data,
            extracted_jd=sample_extracted_jd,
            career_context=sample_career_context,
        )
        assert sample_role_data.company in prompt
        assert sample_role_data.title in prompt
        assert "Led team of 10" in prompt

    def test_user_prompt_includes_jd_keywords(
        self, sample_role_data, sample_extracted_jd, sample_career_context
    ):
        """User prompt includes JD keywords."""
        prompt = build_role_generation_user_prompt(
            role=sample_role_data,
            extracted_jd=sample_extracted_jd,
            career_context=sample_career_context,
        )
        assert "AWS" in prompt
        assert "leadership" in prompt

    def test_user_prompt_includes_career_context(
        self, sample_role_data, sample_extracted_jd, sample_career_context
    ):
        """User prompt includes career context guidance."""
        prompt = build_role_generation_user_prompt(
            role=sample_role_data,
            extracted_jd=sample_extracted_jd,
            career_context=sample_career_context,
        )
        assert "Career Stage" in prompt
        assert "recent" in prompt


# ===== TESTS: RoleGenerator Response Parsing =====

class TestRoleGeneratorParsing:
    """Test RoleGenerator response parsing and validation."""

    def test_parses_valid_json_response(self, sample_role_data):
        """Parses valid JSON response correctly."""
        response = json.dumps({
            "bullets": [
                {
                    "text": "Led team of 10 engineers to deliver platform migration",
                    "source_text": "Led team of 10 engineers to deliver critical platform migration",
                    "source_metric": "10",
                    "jd_keyword_used": "team",
                    "pain_point_addressed": None,
                }
            ],
            "total_word_count": 9,
            "keywords_integrated": ["team"],
        })

        generator = RoleGenerator()
        result = generator._parse_response(response, sample_role_data)

        assert result.bullet_count == 1
        assert "Led team" in result.bullets[0].text
        assert result.keywords_integrated == ["team"]

    def test_handles_markdown_wrapped_json(self, sample_role_data):
        """Handles JSON wrapped in markdown code blocks."""
        response = """```json
{
    "bullets": [
        {
            "text": "Reduced incident rate by 75%",
            "source_text": "Reduced incident rate by 75%",
            "source_metric": "75%",
            "jd_keyword_used": null,
            "pain_point_addressed": null
        }
    ],
    "total_word_count": 5,
    "keywords_integrated": []
}
```"""

        generator = RoleGenerator()
        result = generator._parse_response(response, sample_role_data)

        assert result.bullet_count == 1
        assert "75%" in result.bullets[0].source_metric

    def test_raises_on_invalid_json(self, sample_role_data):
        """Raises ValueError on invalid JSON."""
        generator = RoleGenerator()

        with pytest.raises(ValueError) as exc_info:
            generator._parse_response("not valid json", sample_role_data)

        assert "No JSON found" in str(exc_info.value)

    def test_validates_bullet_text_length(self, sample_role_data):
        """Validates minimum bullet text length."""
        response = json.dumps({
            "bullets": [
                {
                    "text": "Too short",  # Less than 20 chars
                    "source_text": "Source text here",
                }
            ],
            "total_word_count": 2,
            "keywords_integrated": [],
        })

        generator = RoleGenerator()

        with pytest.raises(ValueError) as exc_info:
            generator._parse_response(response, sample_role_data)

        assert "validation failed" in str(exc_info.value).lower()


# ===== TESTS: RoleQA Metric Extraction =====

class TestRoleQAMetricExtraction:
    """Test metric extraction from text."""

    def test_extracts_percentages(self):
        """Extracts percentage metrics."""
        qa = RoleQA()
        metrics = qa._extract_metrics("Reduced errors by 75% and improved uptime to 99.9%")
        assert "75" in metrics
        assert "99.9" in metrics

    def test_extracts_multipliers(self):
        """Extracts multiplier metrics."""
        qa = RoleQA()
        metrics = qa._extract_metrics("Achieved 10x improvement in performance")
        assert "10" in metrics

    def test_extracts_dollar_amounts(self):
        """Extracts dollar amounts."""
        qa = RoleQA()
        metrics = qa._extract_metrics("Generated $5M in revenue savings")
        assert "5" in metrics

    def test_extracts_counts(self):
        """Extracts count metrics."""
        qa = RoleQA()
        metrics = qa._extract_metrics("Processed 1000000 requests per day")
        assert "1000000" in metrics

    def test_extracts_team_sizes(self):
        """Extracts team size metrics."""
        qa = RoleQA()
        metrics = qa._extract_metrics("Led team of 15 engineers")
        assert "15" in metrics


# ===== TESTS: RoleQA Hallucination Detection =====

class TestRoleQAHallucinationDetection:
    """Test hallucination detection."""

    def test_passes_when_metrics_match(self, sample_role_bullets, sample_role_data):
        """Passes when all metrics are in source."""
        qa = RoleQA()
        result = qa.check_hallucination(sample_role_bullets, sample_role_data)

        assert result.passed is True
        assert result.confidence > 0.5

    def test_flags_invented_metrics(self, sample_role_data):
        """Flags bullets with invented metrics."""
        fake_bullets = RoleBullets(
            role_id="test",
            company="Test",
            title="Lead",
            period="2020-2024",
            bullets=[
                GeneratedBullet(
                    text="Improved performance by 95%",  # 95% not in source
                    source_text="Reduced incident rate by 75%",
                    source_metric="95%",
                )
            ],
        )

        qa = RoleQA()
        result = qa.check_hallucination(fake_bullets, sample_role_data)

        assert len(result.issues) > 0
        assert "95" in str(result.issues)

    def test_metric_tolerance_allows_close_matches(self, sample_role_data):
        """Metric tolerance allows close numeric matches."""
        # Source has "75%", test with "73%" which is within 15% tolerance
        bullets = RoleBullets(
            role_id="test",
            company="Test",
            title="Lead",
            period="2020-2024",
            bullets=[
                GeneratedBullet(
                    text="Reduced incident rate by approximately 73%",
                    source_text="Reduced incident rate by 75%",
                    source_metric="73%",
                )
            ],
        )

        qa = RoleQA(metric_tolerance=0.15)
        result = qa.check_hallucination(bullets, sample_role_data)

        # Should pass because 73 is within 15% of 75
        assert result.passed is True


# ===== TESTS: RoleQA ATS Keyword Coverage =====

class TestRoleQAATSKeywords:
    """Test ATS keyword coverage checking."""

    def test_finds_present_keywords(self, sample_role_bullets):
        """Finds keywords present in bullets."""
        target_keywords = ["team", "incident", "AWS"]

        qa = RoleQA()
        result = qa.check_ats_keywords(sample_role_bullets, target_keywords)

        assert "team" in result.keywords_found
        assert "incident" in result.keywords_found

    def test_reports_missing_keywords(self, sample_role_bullets):
        """Reports keywords not found in bullets."""
        target_keywords = ["team", "incident", "blockchain", "quantum"]

        qa = RoleQA()
        result = qa.check_ats_keywords(sample_role_bullets, target_keywords)

        assert "blockchain" in result.keywords_missing
        assert "quantum" in result.keywords_missing

    def test_calculates_coverage_ratio(self, sample_role_bullets):
        """Calculates correct coverage ratio."""
        target_keywords = ["team", "incident", "AWS", "python"]  # 2/4 found

        qa = RoleQA()
        result = qa.check_ats_keywords(sample_role_bullets, target_keywords)

        assert result.coverage_ratio == 0.5

    def test_case_insensitive_matching(self, sample_role_bullets):
        """Matches keywords case-insensitively."""
        target_keywords = ["TEAM", "Incident"]

        qa = RoleQA()
        result = qa.check_ats_keywords(sample_role_bullets, target_keywords)

        assert len(result.keywords_found) == 2

    def test_generates_suggestions(self, sample_role_bullets):
        """Generates suggestions for missing keywords."""
        target_keywords = ["missing1", "missing2", "missing3", "team"]

        qa = RoleQA()
        result = qa.check_ats_keywords(sample_role_bullets, target_keywords)

        assert len(result.suggestions) > 0
        assert "Consider integrating" in result.suggestions[0]


# ===== TESTS: Integration =====

class TestPhase3Integration:
    """Integration tests for Phase 3 components."""

    @pytest.mark.asyncio
    @patch('src.layer6_v2.role_generator.UnifiedLLM')
    async def test_generator_with_mocked_llm(
        self, mock_unified_llm_class, sample_role_data, sample_extracted_jd
    ):
        """RoleGenerator works with mocked LLM."""
        # Mock LLM response - need to mock the invoke method properly
        from unittest.mock import AsyncMock
        from src.common.unified_llm import LLMResult

        # Create mock LLM instance
        mock_llm = MagicMock()
        json_content = json.dumps({
            "bullets": [
                {
                    "text": "Led team of 10 engineers to deliver platform migration",
                    "source_text": "Led team of 10 engineers to deliver critical platform migration",
                    "source_metric": "10",
                    "jd_keyword_used": "team",
                    "pain_point_addressed": None,
                }
            ],
            "total_word_count": 9,
            "keywords_integrated": ["team"],
        })
        mock_llm.invoke = AsyncMock(return_value=LLMResult(
            content=json_content,
            backend="claude_cli",
            model="claude-opus-4",
            tier="primary",
            duration_ms=100,
            success=True,
            error=None
        ))
        mock_unified_llm_class.return_value = mock_llm

        generator = RoleGenerator()
        result = await generator.generate(sample_role_data, sample_extracted_jd)

        assert result.bullet_count == 1
        assert result.company == "Test Company"
        mock_llm.invoke.assert_called_once()

    def test_qa_result_serialization(self, sample_role_bullets, sample_role_data):
        """QA results serialize correctly."""
        qa = RoleQA()
        qa_result = qa.check_hallucination(sample_role_bullets, sample_role_data)
        ats_result = qa.check_ats_keywords(sample_role_bullets, ["team", "AWS"])

        # Update role bullets with results
        sample_role_bullets.qa_result = qa_result
        sample_role_bullets.ats_result = ats_result

        # Serialize
        d = sample_role_bullets.to_dict()

        assert d["qa_result"]["passed"] is True
        assert "coverage_ratio" in d["ats_result"]

    def test_pydantic_validation_catches_short_bullets(self):
        """Pydantic model catches short bullet text."""
        with pytest.raises(ValueError):
            GeneratedBulletModel(
                text="Short",  # Too short
                source_text="Valid source text here",
            )

    def test_pydantic_validation_catches_empty_source(self):
        """Pydantic model catches empty source text."""
        with pytest.raises(ValueError):
            GeneratedBulletModel(
                text="This is a valid bullet text with enough words",
                source_text="",  # Empty
            )


# ===== TESTS: Variant-Based Generation =====

class TestVariantBasedGeneration:
    """Tests for variant-based bullet generation."""

    @pytest.fixture
    def sample_role_with_variants(self):
        """Sample RoleData with enhanced variant data."""
        from src.layer6_v2.cv_loader import CVLoader

        loader = CVLoader(use_enhanced=True)
        if not loader.metadata_path.exists():
            pytest.skip("Real master-cv data not available")

        loader.load()
        return loader.get_current_role()

    @pytest.fixture
    def sample_extracted_jd(self):
        """Sample extracted JD for testing."""
        return {
            "role_category": "tech_lead",
            "top_keywords": ["aws", "microservices", "kubernetes", "leadership", "architecture"],
            "technical_skills": ["AWS", "TypeScript", "Kubernetes"],
            "soft_skills": ["leadership", "communication"],
            "implied_pain_points": [
                "Need to modernize legacy systems",
                "Scale infrastructure",
            ],
        }

    def test_generate_from_variants_returns_role_bullets(
        self, sample_role_with_variants, sample_extracted_jd
    ):
        """generate_from_variants returns RoleBullets with selected variants."""
        generator = RoleGenerator()
        result = generator.generate_from_variants(
            role=sample_role_with_variants,
            extracted_jd=sample_extracted_jd,
            target_bullet_count=5,
        )

        assert result is not None
        assert isinstance(result, RoleBullets)
        assert result.bullet_count == 5
        assert result.word_count > 0

    def test_generate_from_variants_has_traceability(
        self, sample_role_with_variants, sample_extracted_jd
    ):
        """Generated bullets have source traceability."""
        generator = RoleGenerator()
        result = generator.generate_from_variants(
            role=sample_role_with_variants,
            extracted_jd=sample_extracted_jd,
            target_bullet_count=3,
        )

        for bullet in result.bullets:
            assert bullet.text  # Has generated text
            assert bullet.source_text  # Has source text for traceability

    def test_generate_from_variants_extracts_metrics(
        self, sample_role_with_variants, sample_extracted_jd
    ):
        """Variant generation extracts metrics from bullet text."""
        generator = RoleGenerator()
        result = generator.generate_from_variants(
            role=sample_role_with_variants,
            extracted_jd=sample_extracted_jd,
            target_bullet_count=5,
        )

        # At least some bullets should have extracted metrics
        bullets_with_metrics = [b for b in result.bullets if b.source_metric]
        assert len(bullets_with_metrics) >= 1

    def test_generate_from_variants_returns_none_without_variants(self, sample_extracted_jd):
        """Returns None when role has no variant data."""
        role_without_variants = RoleData(
            id="test",
            company="Test",
            title="Engineer",
            location="Test",
            period="2020-2024",
            start_year=2020,
            end_year=2024,
            is_current=False,
            duration_years=4,
            industry="Tech",
            team_size="5",
            primary_competencies=[],
            keywords=[],
            achievements=["Simple bullet point"],
            # No enhanced_data
        )

        generator = RoleGenerator()
        result = generator.generate_from_variants(
            role=role_without_variants,
            extracted_jd=sample_extracted_jd,
        )

        assert result is None

    def test_generate_from_variants_integrates_keywords(
        self, sample_role_with_variants, sample_extracted_jd
    ):
        """Variant generation tracks integrated keywords."""
        generator = RoleGenerator()
        result = generator.generate_from_variants(
            role=sample_role_with_variants,
            extracted_jd=sample_extracted_jd,
            target_bullet_count=5,
        )

        assert len(result.keywords_integrated) > 0

    @pytest.mark.asyncio
    async def test_generate_with_variant_fallback_uses_variants(
        self, sample_role_with_variants, sample_extracted_jd
    ):
        """generate_with_variant_fallback uses variants when available."""
        generator = RoleGenerator()
        result = await generator.generate_with_variant_fallback(
            role=sample_role_with_variants,
            extracted_jd=sample_extracted_jd,
            target_bullet_count=3,
            prefer_variants=True,
        )

        assert result is not None
        assert result.bullet_count == 3

    def test_extract_metric_finds_percentages(self):
        """_extract_metric finds percentage values."""
        generator = RoleGenerator()

        assert generator._extract_metric("Reduced errors by 75%") == "75%"
        assert generator._extract_metric("Improved to 99.9%") == "99.9%"

    def test_extract_metric_finds_currency(self):
        """_extract_metric finds currency values."""
        generator = RoleGenerator()

        assert generator._extract_metric("Protected €30M revenue") == "€30M"
        assert generator._extract_metric("Saved $5K monthly") == "$5K"

    def test_extract_metric_finds_multipliers(self):
        """_extract_metric finds multiplier values."""
        generator = RoleGenerator()

        assert generator._extract_metric("Achieved 10x improvement") == "10x"
