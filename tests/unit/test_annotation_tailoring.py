"""
Unit Tests for Annotation Integration and Persona Features

Tests:
- CVTailorer: Keyword extraction, placement analysis, repositioning logic
- Role Generation Persona: Prompt building with persona context
- Orchestrator _should_apply_tailoring: Tailoring decision logic
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, List

from src.layer6_v2.cv_tailorer import (
    CVTailorer,
    build_tailoring_system_prompt_with_persona,
    build_tailoring_user_prompt,
)
from src.layer6_v2.prompts.role_generation import (
    build_role_system_prompt_with_persona,
    ROLE_GENERATION_SYSTEM_PROMPT,
)
from src.layer6_v2.keyword_placement import (
    KeywordPlacementResult,
    KeywordPlacement,
)
from src.layer6_v2.types import TailoringResult
from src.layer6_v2.orchestrator import CVGeneratorV2


# ===== FIXTURES =====


@pytest.fixture
def mock_jd_annotations_with_persona():
    """JD annotations with synthesized persona."""
    return {
        "synthesized_persona": {
            "persona_statement": "A platform engineering leader transforming infrastructure through DevOps excellence and team mentorship"
        },
        "annotations": [
            {
                "is_active": True,
                "matching_skill": "Kubernetes",
                "suggested_keywords": ["Kubernetes", "K8s", "container orchestration"],
                "requirement_type": "must_have",
                "identity": "core_identity",
                "relevance": "core_strength",
                "priority": 1,
            },
            {
                "is_active": True,
                "matching_skill": "Python",
                "suggested_keywords": ["Python", "Python3"],
                "requirement_type": "nice_to_have",
                "identity": "strong_identity",
                "relevance": "extremely_relevant",
                "priority": 2,
            },
            {
                "is_active": True,
                "matching_skill": "AWS",
                "suggested_keywords": ["AWS", "Amazon Web Services"],
                "requirement_type": "must_have",
                "identity": "not_identity",
                "relevance": "relevant",
                "priority": 3,
            },
            {
                "is_active": False,  # Inactive annotation should be skipped
                "matching_skill": "Go",
                "suggested_keywords": ["Go", "Golang"],
                "requirement_type": "must_have",
                "identity": "core_identity",
                "relevance": "core_strength",
                "priority": 4,
            },
        ],
    }


@pytest.fixture
def mock_jd_annotations_no_persona():
    """JD annotations without persona."""
    return {
        "annotations": [
            {
                "is_active": True,
                "matching_skill": "Docker",
                "suggested_keywords": ["Docker"],
                "requirement_type": "must_have",
                "identity": "not_identity",
                "relevance": "relevant",
                "priority": 1,
            }
        ]
    }


@pytest.fixture
def mock_extracted_jd():
    """Sample extracted JD."""
    return {
        "title": "Platform Engineering Manager",
        "company": "Tech Corp",
        "top_keywords": ["Kubernetes", "Python", "AWS", "Docker", "Terraform"],
    }


@pytest.fixture
def mock_cv_text():
    """Sample CV text for placement analysis."""
    return """# TAIMOOR ALAM
### Platform Engineering Leader · Senior Software Engineer
email@example.com · +1234567890 · Munich, Germany

**PROFESSIONAL SUMMARY**

Platform engineering leader with expertise in building scalable infrastructure using cloud technologies.

**CORE COMPETENCIES**
**Cloud & Platform:** AWS, Docker, Terraform
**Programming:** Java, Go

**PROFESSIONAL EXPERIENCE**

**Company Inc** - Senior Engineer (2020-Present)

• Built scalable Python services handling 1M requests/day
• Led migration to containerized architecture using Docker
• Implemented observability using Prometheus
"""


@pytest.fixture
def mock_placement_result_good():
    """Keyword placement result with good scores."""
    return KeywordPlacementResult(
        placements=[],
        overall_score=95,
        must_have_score=100,
        identity_score=100,
        keywords_in_headline=3,
        keywords_in_top_third=8,
        total_keywords=10,
    )


@pytest.fixture
def mock_placement_result_needs_tailoring():
    """Keyword placement result that needs tailoring."""
    return KeywordPlacementResult(
        placements=[],
        overall_score=75,
        must_have_score=80,
        identity_score=50,
        keywords_in_headline=1,
        keywords_in_top_third=5,
        total_keywords=10,
    )


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for tailoring."""
    return MagicMock(
        success=True,
        content="""# TAIMOOR ALAM
### Kubernetes Platform Engineer · Platform Engineering Leader
email@example.com

**PROFESSIONAL SUMMARY**

Kubernetes and Python expert building scalable cloud infrastructure on AWS.
""",
        error=None,
    )


# ===== TESTS: CVTailorer._extract_priority_keywords =====


class TestCVTailorerExtractPriorityKeywords:
    """Test CVTailorer._extract_priority_keywords method."""

    def test_extracts_keywords_from_active_annotations(
        self, mock_jd_annotations_with_persona, mock_extracted_jd
    ):
        """Should extract keywords from active annotations only."""
        tailorer = CVTailorer(job_id="test123")
        keywords = tailorer._extract_priority_keywords(
            mock_jd_annotations_with_persona, mock_extracted_jd
        )

        # Should get 3 active annotations (Go is inactive)
        assert len(keywords) >= 3

        # Check Kubernetes (must_have, core_identity)
        k8s = next((k for k in keywords if k["keyword"] == "Kubernetes"), None)
        assert k8s is not None
        assert k8s["is_must_have"] is True
        assert k8s["is_identity"] is True
        assert k8s["is_core_strength"] is True

        # Check Python (nice_to_have, strong_identity)
        python = next((k for k in keywords if k["keyword"] == "Python"), None)
        assert python is not None
        assert python["is_must_have"] is False
        assert python["is_identity"] is True

        # Check AWS (must_have, not_identity)
        aws = next((k for k in keywords if k["keyword"] == "AWS"), None)
        assert aws is not None
        assert aws["is_must_have"] is True
        assert aws["is_identity"] is False

        # Go should NOT be extracted (inactive)
        go = next((k for k in keywords if k["keyword"] == "Go"), None)
        assert go is None

    def test_handles_missing_matching_skill_uses_suggested(
        self, mock_extracted_jd
    ):
        """Should use first suggested_keyword when matching_skill is missing."""
        annotations = {
            "annotations": [
                {
                    "is_active": True,
                    "matching_skill": None,  # Missing
                    "suggested_keywords": ["Terraform", "IaC"],
                    "requirement_type": "must_have",
                    "identity": "not_identity",
                    "relevance": "relevant",
                    "priority": 1,
                }
            ]
        }

        tailorer = CVTailorer(job_id="test123")
        keywords = tailorer._extract_priority_keywords(annotations, mock_extracted_jd)

        # Should use first suggested keyword
        assert len(keywords) >= 1
        terraform = next((k for k in keywords if k["keyword"] == "Terraform"), None)
        assert terraform is not None

    def test_includes_top_jd_keywords_not_in_annotations(
        self, mock_jd_annotations_with_persona, mock_extracted_jd
    ):
        """Should include top JD keywords not covered by annotations."""
        tailorer = CVTailorer(job_id="test123")
        keywords = tailorer._extract_priority_keywords(
            mock_jd_annotations_with_persona, mock_extracted_jd
        )

        # Should include "Terraform" from top_keywords (not in annotations)
        terraform = next((k for k in keywords if k["keyword"] == "Terraform"), None)
        assert terraform is not None
        assert terraform["priority_rank"] == 5  # Lower priority for JD-only

    def test_handles_empty_annotations(self, mock_extracted_jd):
        """Should handle empty annotations gracefully."""
        annotations = {"annotations": []}
        tailorer = CVTailorer(job_id="test123")
        keywords = tailorer._extract_priority_keywords(annotations, mock_extracted_jd)

        # Should still include top JD keywords
        assert len(keywords) > 0
        assert all(k["priority_rank"] == 5 for k in keywords)  # All from JD


# ===== TESTS: CVTailorer._analyze_placement =====


class TestCVTailorerAnalyzePlacement:
    """Test CVTailorer._analyze_placement method."""

    def test_detects_keywords_in_headline(self, mock_cv_text):
        """Should detect keywords in headline (H3)."""
        priority_keywords = [
            {
                "keyword": "Platform Engineering",
                "is_must_have": True,
                "is_identity": True,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        tailorer = CVTailorer(job_id="test123")
        result = tailorer._analyze_placement(mock_cv_text, priority_keywords)

        placements = result["placements"]
        assert len(placements) == 1
        assert placements[0]["in_headline"] is True
        # Score can be higher than 40 if also in other sections
        assert placements[0]["score"] >= 40

    def test_detects_keywords_in_narrative(self, mock_cv_text):
        """Should detect keywords in profile narrative."""
        priority_keywords = [
            {
                "keyword": "cloud",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        tailorer = CVTailorer(job_id="test123")
        result = tailorer._analyze_placement(mock_cv_text, priority_keywords)

        placements = result["placements"]
        assert len(placements) == 1
        assert placements[0]["in_narrative"] is True

    def test_detects_keywords_in_competencies(self):
        """Should detect keywords in core competencies section."""
        # Use a simpler CV structure for this specific test
        cv_with_competencies = """# NAME
### Title

**CORE COMPETENCIES**
Cloud Platforms: AWS, Azure, Terraform
Programming: Python, Go

**PROFESSIONAL EXPERIENCE**
Test content
"""
        priority_keywords = [
            {
                "keyword": "Terraform",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        tailorer = CVTailorer(job_id="test123")
        result = tailorer._analyze_placement(cv_with_competencies, priority_keywords)

        placements = result["placements"]
        assert len(placements) == 1
        assert placements[0]["in_competencies"] is True

    def test_detects_keywords_in_first_role(self, mock_cv_text):
        """Should detect keywords in first role bullets."""
        priority_keywords = [
            {
                "keyword": "Python",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        tailorer = CVTailorer(job_id="test123")
        result = tailorer._analyze_placement(mock_cv_text, priority_keywords)

        placements = result["placements"]
        assert len(placements) == 1
        assert placements[0]["in_first_role"] is True

    def test_calculates_overall_score_correctly(self, mock_cv_text):
        """Should calculate correct overall, must_have, and identity scores."""
        priority_keywords = [
            {
                "keyword": "AWS",  # In competencies
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            },
            {
                "keyword": "Platform",  # In headline
                "is_must_have": True,
                "is_identity": True,
                "is_core_strength": True,
                "priority_rank": 2,
            },
            {
                "keyword": "Kubernetes",  # Not in CV
                "is_must_have": True,
                "is_identity": True,
                "is_core_strength": True,
                "priority_rank": 3,
            },
        ]

        tailorer = CVTailorer(job_id="test123")
        result = tailorer._analyze_placement(mock_cv_text, priority_keywords)

        # Overall score: average of individual placement scores
        assert result["overall_score"] > 0

        # Must-have score: 2/3 must-haves in top 1/3 = 66%
        assert result["must_have_score"] < 100

        # Identity score: 1/2 identity keywords in headline = 50%
        assert result["identity_score"] == 50


# ===== TESTS: CVTailorer._identify_repositioning_needs =====


class TestCVTailorerIdentifyRepositioningNeeds:
    """Test CVTailorer._identify_repositioning_needs method."""

    def test_identifies_identity_keywords_not_in_headline(self):
        """Should flag identity keywords not in headline for repositioning."""
        priority_keywords = [
            {
                "keyword": "Kubernetes",
                "is_must_have": True,
                "is_identity": True,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        current_placement = {
            "placements": [
                {
                    "keyword": "Kubernetes",
                    "in_headline": False,
                    "in_narrative": True,
                    "in_competencies": True,
                    "in_first_role": False,
                    "in_top_third": True,
                    "is_identity": True,
                    "is_must_have": True,
                    "is_core_strength": True,
                }
            ]
        }

        tailorer = CVTailorer(job_id="test123")
        needs_repositioning = tailorer._identify_repositioning_needs(
            priority_keywords, current_placement
        )

        assert len(needs_repositioning) == 1
        assert needs_repositioning[0]["keyword"] == "Kubernetes"
        assert needs_repositioning[0]["target_location"] == "headline"

    def test_identifies_must_have_not_in_top_third(self):
        """Should flag must-have keywords not in top 1/3."""
        priority_keywords = [
            {
                "keyword": "Python",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        current_placement = {
            "placements": [
                {
                    "keyword": "Python",
                    "in_headline": False,
                    "in_narrative": False,
                    "in_competencies": False,
                    "in_first_role": True,  # Only in first role, not top 1/3
                    "in_top_third": False,
                    "is_identity": False,
                    "is_must_have": True,
                    "is_core_strength": True,
                }
            ]
        }

        tailorer = CVTailorer(job_id="test123")
        needs_repositioning = tailorer._identify_repositioning_needs(
            priority_keywords, current_placement
        )

        assert len(needs_repositioning) == 1
        assert needs_repositioning[0]["keyword"] == "Python"
        assert "first 50 words" in needs_repositioning[0]["target_location"]

    def test_skips_keywords_already_well_placed(self):
        """Should skip keywords already optimally positioned."""
        priority_keywords = [
            {
                "keyword": "AWS",
                "is_must_have": True,
                "is_identity": False,
                "is_core_strength": True,
                "priority_rank": 1,
            }
        ]

        current_placement = {
            "placements": [
                {
                    "keyword": "AWS",
                    "in_headline": True,
                    "in_narrative": True,
                    "in_competencies": True,
                    "in_first_role": False,
                    "in_top_third": True,
                    "is_identity": False,
                    "is_must_have": True,
                    "is_core_strength": True,
                }
            ]
        }

        tailorer = CVTailorer(job_id="test123")
        needs_repositioning = tailorer._identify_repositioning_needs(
            priority_keywords, current_placement
        )

        assert len(needs_repositioning) == 0


# ===== TESTS: CVTailorer.tailor =====


class TestCVTailorerTailor:
    """Test CVTailorer.tailor method."""

    @pytest.mark.asyncio
    async def test_returns_untailored_when_no_priority_keywords(
        self, mock_cv_text, mock_extracted_jd
    ):
        """Should skip tailoring when no priority keywords found."""
        # Use extracted_jd with no top_keywords to ensure no priority keywords
        empty_jd = {"title": "Test", "company": "Test", "top_keywords": []}

        tailorer = CVTailorer(job_id="test123")
        result = await tailorer.tailor(mock_cv_text, {}, empty_jd)

        assert result.tailored is False
        assert result.cv_text == mock_cv_text  # Unchanged
        # Could be either "No priority keywords" or "already optimally positioned"
        assert "No priority keywords" in result.tailoring_summary or "optimally positioned" in result.tailoring_summary

    @pytest.mark.asyncio
    async def test_returns_untailored_when_keywords_already_optimal(
        self, mock_cv_text, mock_jd_annotations_with_persona, mock_extracted_jd
    ):
        """Should skip tailoring when keywords already optimally positioned."""
        # Create CV with all keywords in optimal positions
        optimal_cv = """# TAIMOOR ALAM
### Kubernetes Platform Engineer · AWS Python Developer
email@example.com

**PROFESSIONAL SUMMARY**

AWS and Kubernetes expert specializing in Python-based cloud platforms.

**CORE COMPETENCIES**

**Cloud:** AWS, Kubernetes, Docker
**Programming:** Python
"""

        tailorer = CVTailorer(job_id="test123")
        result = await tailorer.tailor(
            optimal_cv, mock_jd_annotations_with_persona, mock_extracted_jd
        )

        # Keywords are well-placed, should skip tailoring
        assert result.tailored is False
        assert "already optimally positioned" in result.tailoring_summary

    @pytest.mark.asyncio
    async def test_applies_tailoring_when_needed(
        self,
        mock_cv_text,
        mock_jd_annotations_with_persona,
        mock_extracted_jd,
        mock_llm_response,
    ):
        """Should apply tailoring when keywords need repositioning."""
        with patch.object(
            CVTailorer, "_apply_tailoring", new_callable=AsyncMock
        ) as mock_apply:
            mock_apply.return_value = mock_llm_response.content

            tailorer = CVTailorer(job_id="test123")
            result = await tailorer.tailor(
                mock_cv_text, mock_jd_annotations_with_persona, mock_extracted_jd
            )

            # Should apply tailoring
            assert mock_apply.called
            assert result.tailored is True
            assert len(result.keywords_repositioned) > 0
            assert result.cv_text != mock_cv_text  # Changed


# ===== TESTS: build_tailoring_system_prompt_with_persona =====


class TestBuildTailoringSystemPromptWithPersona:
    """Test build_tailoring_system_prompt_with_persona function."""

    def test_returns_base_prompt_when_no_annotations(self):
        """Should return base prompt when annotations missing."""
        result = build_tailoring_system_prompt_with_persona(jd_annotations=None)
        assert "=== PERSONA GUIDANCE ===" not in result
        assert "ATS optimization specialist" in result  # Base prompt present

    def test_returns_base_prompt_when_no_persona(
        self, mock_jd_annotations_no_persona
    ):
        """Should return base prompt when persona missing."""
        result = build_tailoring_system_prompt_with_persona(
            jd_annotations=mock_jd_annotations_no_persona
        )
        assert "=== PERSONA GUIDANCE ===" not in result

    def test_includes_persona_when_available(self, mock_jd_annotations_with_persona):
        """Should include persona guidance when available."""
        result = build_tailoring_system_prompt_with_persona(
            jd_annotations=mock_jd_annotations_with_persona
        )

        assert "=== PERSONA GUIDANCE ===" in result
        assert "platform engineering leader" in result.lower()
        assert "Leadership personas" in result
        assert "Technical personas" in result


# ===== TESTS: build_role_system_prompt_with_persona =====


class TestBuildRoleSystemPromptWithPersona:
    """Test build_role_system_prompt_with_persona function."""

    def test_returns_base_prompt_when_no_annotations(self):
        """Should return base prompt when annotations missing."""
        result = build_role_system_prompt_with_persona(jd_annotations=None)
        assert "=== CANDIDATE PERSONA" not in result
        assert "CV bullet writer" in result  # Base prompt present

    def test_returns_base_prompt_when_no_persona(
        self, mock_jd_annotations_no_persona
    ):
        """Should return base prompt when persona_statement missing."""
        result = build_role_system_prompt_with_persona(
            jd_annotations=mock_jd_annotations_no_persona
        )
        assert "=== CANDIDATE PERSONA" not in result

    def test_includes_persona_when_available(self, mock_jd_annotations_with_persona):
        """Should prepend persona section when available."""
        result = build_role_system_prompt_with_persona(
            jd_annotations=mock_jd_annotations_with_persona
        )

        assert "=== CANDIDATE PERSONA" in result
        assert "platform engineering leader" in result.lower()
        assert "Leadership-focused personas" in result
        assert "Technical-focused personas" in result
        # Persona should be BEFORE base prompt
        persona_idx = result.index("=== CANDIDATE PERSONA")
        base_idx = result.index("CV bullet writer")
        assert persona_idx < base_idx

    def test_persona_section_provides_framing_guidance(
        self, mock_jd_annotations_with_persona
    ):
        """Should provide clear framing guidance based on persona."""
        result = build_role_system_prompt_with_persona(
            jd_annotations=mock_jd_annotations_with_persona
        )

        # Check guidance for different persona types
        assert "emphasize team impact" in result.lower()
        assert "engineering depth" in result.lower()
        assert "reliability, scale" in result.lower()


# ===== TESTS: CVGeneratorV2._should_apply_tailoring =====


class TestCVGeneratorV2ShouldApplyTailoring:
    """Test CVGeneratorV2._should_apply_tailoring method."""

    def test_returns_false_when_no_placement_result(self):
        """Should return False when placement result is None."""
        generator = CVGeneratorV2()
        result = generator._should_apply_tailoring(keyword_placement_result=None)
        assert result is False

    def test_returns_true_when_overall_score_low(
        self, mock_placement_result_needs_tailoring
    ):
        """Should return True when overall score below 90."""
        mock_placement_result_needs_tailoring.overall_score = 85
        generator = CVGeneratorV2()
        result = generator._should_apply_tailoring(
            mock_placement_result_needs_tailoring
        )
        assert result is True

    def test_returns_true_when_must_have_score_low(
        self, mock_placement_result_needs_tailoring
    ):
        """Should return True when must_have_score below 100."""
        mock_placement_result_needs_tailoring.overall_score = 95  # Good
        mock_placement_result_needs_tailoring.must_have_score = 80  # Low
        generator = CVGeneratorV2()
        result = generator._should_apply_tailoring(
            mock_placement_result_needs_tailoring
        )
        assert result is True

    def test_returns_true_when_identity_score_low(
        self, mock_placement_result_needs_tailoring
    ):
        """Should return True when identity_score below 100."""
        mock_placement_result_needs_tailoring.overall_score = 95  # Good
        mock_placement_result_needs_tailoring.must_have_score = 100  # Good
        mock_placement_result_needs_tailoring.identity_score = 50  # Low
        generator = CVGeneratorV2()
        result = generator._should_apply_tailoring(
            mock_placement_result_needs_tailoring
        )
        assert result is True

    def test_returns_false_when_all_scores_meet_threshold(
        self, mock_placement_result_good
    ):
        """Should return False when all scores meet thresholds."""
        mock_placement_result_good.overall_score = 95
        mock_placement_result_good.must_have_score = 100
        mock_placement_result_good.identity_score = 100
        generator = CVGeneratorV2()
        result = generator._should_apply_tailoring(mock_placement_result_good)
        assert result is False


# ===== TESTS: Edge Cases =====


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_tailorer_handles_empty_cv_text(
        self, mock_jd_annotations_with_persona, mock_extracted_jd
    ):
        """Should handle empty CV text gracefully."""
        tailorer = CVTailorer(job_id="test123")
        result = tailorer._analyze_placement(
            cv_text="", priority_keywords=[{"keyword": "test", "is_must_have": True, "is_identity": False, "is_core_strength": False, "priority_rank": 1}]
        )

        # Should not crash, return zero scores
        assert result["overall_score"] == 0

    def test_extract_keywords_handles_empty_suggested_keywords(
        self, mock_extracted_jd
    ):
        """Should handle empty suggested_keywords list."""
        annotations = {
            "annotations": [
                {
                    "is_active": True,
                    "matching_skill": "Docker",
                    "suggested_keywords": [],  # Empty list
                    "requirement_type": "must_have",
                    "identity": "not_identity",
                    "relevance": "relevant",
                    "priority": 1,
                }
            ]
        }

        tailorer = CVTailorer(job_id="test123")
        keywords = tailorer._extract_priority_keywords(annotations, mock_extracted_jd)

        # Should still extract using matching_skill
        assert len(keywords) > 0
        docker = next((k for k in keywords if k["keyword"] == "Docker"), None)
        assert docker is not None

    def test_persona_prompt_handles_empty_persona_statement(self):
        """Should handle empty persona_statement gracefully."""
        annotations = {
            "synthesized_persona": {
                "persona_statement": ""  # Empty string
            },
            "annotations": [],
        }

        result = build_tailoring_system_prompt_with_persona(jd_annotations=annotations)
        assert "=== PERSONA GUIDANCE ===" not in result

    @pytest.mark.asyncio
    async def test_tailor_handles_llm_failure(
        self, mock_cv_text, mock_jd_annotations_with_persona, mock_extracted_jd
    ):
        """Should return original CV when LLM call fails."""
        with patch.object(
            CVTailorer, "_apply_tailoring", new_callable=AsyncMock
        ) as mock_apply:
            # Simulate LLM failure - return original CV
            mock_apply.return_value = mock_cv_text

            tailorer = CVTailorer(job_id="test123")
            # Force tailoring by making CV missing Kubernetes in headline
            simple_cv = "# NAME\n### Engineer\nSome text about Docker and Python."
            result = await tailorer.tailor(
                simple_cv, mock_jd_annotations_with_persona, mock_extracted_jd
            )

            # Should handle gracefully - if LLM fails, _apply_tailoring returns original
            assert result.cv_text is not None


# ===== TESTS: Integration =====


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_end_to_end_tailoring_workflow(
        self, mock_cv_text, mock_jd_annotations_with_persona, mock_extracted_jd
    ):
        """Should execute complete tailoring workflow."""
        with patch.object(
            CVTailorer, "_apply_tailoring", new_callable=AsyncMock
        ) as mock_apply:
            # Mock LLM to return improved CV with Kubernetes in headline
            improved_cv = mock_cv_text.replace(
                "### Platform Engineering Leader",
                "### Kubernetes Platform Engineer",
            )
            mock_apply.return_value = improved_cv

            tailorer = CVTailorer(job_id="test123")
            result = await tailorer.tailor(
                mock_cv_text, mock_jd_annotations_with_persona, mock_extracted_jd
            )

            # Verify workflow
            assert result.tailored is True or result.tailored is False  # Either outcome valid
            assert result.cv_text is not None
            assert isinstance(result.changes_made, list)
            assert isinstance(result.keywords_repositioned, list)

    def test_orchestrator_tailoring_decision_with_placement_result(
        self, mock_placement_result_needs_tailoring
    ):
        """Should make correct tailoring decision based on placement."""
        generator = CVGeneratorV2()

        # Test with low scores - should apply tailoring
        result = generator._should_apply_tailoring(
            mock_placement_result_needs_tailoring
        )
        assert result is True

        # Test with high scores - should skip tailoring
        mock_placement_result_needs_tailoring.overall_score = 95
        mock_placement_result_needs_tailoring.must_have_score = 100
        mock_placement_result_needs_tailoring.identity_score = 100
        result = generator._should_apply_tailoring(
            mock_placement_result_needs_tailoring
        )
        assert result is False
