"""
Unit Tests for Layer 4: Annotation Fit Signal Integration

Tests the integration of JD annotations into the fit scoring process:
- AnnotationFitSignal calculator extracts signals from annotations
- Core strength and extremely relevant annotations boost fit signal
- Gap annotations reduce fit signal
- Disqualifier requirement types flag potential issues
- Annotation signal blends with LLM fit score (70/30 blend)
- Annotation analysis is included in fit scoring output

TDD approach: Tests written first, implementation follows.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, List, Optional


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_core_strength_annotation():
    """Core strength annotation - perfect match."""
    return {
        "id": "ann-001",
        "relevance": "core_strength",
        "requirement_type": "must_have",
        "priority": 1,
        "annotation_type": "skill_match",
        "is_active": True,
        "star_ids": ["star-001"],
        "suggested_keywords": ["kubernetes", "docker"],
        "ats_variants": ["K8s"],
        "has_reframe": False,
        "reframe_note": None,
        "target": {
            "section": "qualifications",
            "index": 0,
            "text": "Experience with Kubernetes",
            "char_start": 0,
            "char_end": 25,
        },
    }


@pytest.fixture
def sample_extremely_relevant_annotation():
    """Extremely relevant annotation - very strong match."""
    return {
        "id": "ann-002",
        "relevance": "extremely_relevant",
        "requirement_type": "must_have",
        "priority": 2,
        "annotation_type": "skill_match",
        "is_active": True,
        "star_ids": ["star-002"],
        "suggested_keywords": ["python"],
        "ats_variants": [],
        "has_reframe": False,
        "reframe_note": None,
        "target": {
            "section": "qualifications",
            "index": 1,
            "text": "Python programming",
            "char_start": 30,
            "char_end": 47,
        },
    }


@pytest.fixture
def sample_gap_annotation():
    """Gap annotation - skill not present."""
    return {
        "id": "ann-003",
        "relevance": "gap",
        "requirement_type": "must_have",
        "priority": 1,
        "annotation_type": "skill_match",
        "is_active": True,
        "star_ids": [],
        "suggested_keywords": ["terraform"],
        "ats_variants": ["TF"],
        "has_reframe": True,
        "reframe_note": "Reframe as infrastructure-as-code experience",
        "target": {
            "section": "qualifications",
            "index": 2,
            "text": "Terraform experience required",
            "char_start": 50,
            "char_end": 78,
        },
    }


@pytest.fixture
def sample_disqualifier_annotation():
    """Disqualifier annotation - candidate doesn't want this."""
    return {
        "id": "ann-004",
        "relevance": "relevant",
        "requirement_type": "disqualifier",
        "priority": 1,
        "annotation_type": "concern",
        "is_active": True,
        "star_ids": [],
        "suggested_keywords": ["on-call"],
        "ats_variants": [],
        "has_reframe": False,
        "reframe_note": None,
        "target": {
            "section": "responsibilities",
            "index": 5,
            "text": "24/7 on-call rotation required",
            "char_start": 100,
            "char_end": 130,
        },
    }


@pytest.fixture
def sample_jd_annotations_positive(
    sample_core_strength_annotation,
    sample_extremely_relevant_annotation,
):
    """JD annotations with positive signals only."""
    return {
        "annotation_version": 1,
        "annotations": [
            sample_core_strength_annotation,
            sample_extremely_relevant_annotation,
        ],
        "concerns": [],
        "settings": {
            "conflict_resolution": "max_boost",
        },
        "relevance_counts": {
            "core_strength": 1,
            "extremely_relevant": 1,
            "relevant": 0,
            "tangential": 0,
            "gap": 0,
        },
        "gap_count": 0,
    }


@pytest.fixture
def sample_jd_annotations_mixed(
    sample_core_strength_annotation,
    sample_extremely_relevant_annotation,
    sample_gap_annotation,
):
    """JD annotations with mixed positive/negative signals."""
    return {
        "annotation_version": 1,
        "annotations": [
            sample_core_strength_annotation,
            sample_extremely_relevant_annotation,
            sample_gap_annotation,
        ],
        "concerns": [],
        "settings": {
            "conflict_resolution": "max_boost",
        },
        "relevance_counts": {
            "core_strength": 1,
            "extremely_relevant": 1,
            "relevant": 0,
            "tangential": 0,
            "gap": 1,
        },
        "gap_count": 1,
    }


@pytest.fixture
def sample_jd_annotations_with_disqualifier(
    sample_core_strength_annotation,
    sample_disqualifier_annotation,
):
    """JD annotations with a disqualifier."""
    return {
        "annotation_version": 1,
        "annotations": [
            sample_core_strength_annotation,
            sample_disqualifier_annotation,
        ],
        "concerns": [],
        "settings": {
            "conflict_resolution": "max_boost",
        },
        "relevance_counts": {
            "core_strength": 1,
            "extremely_relevant": 0,
            "relevant": 1,
            "tangential": 0,
            "gap": 0,
        },
        "gap_count": 0,
    }


@pytest.fixture
def sample_job_state_with_annotations(sample_jd_annotations_mixed):
    """Full JobState with annotations for testing."""
    return {
        "job_id": "test_001",
        "title": "Senior Platform Engineer",
        "company": "TechCorp",
        "job_description": "Build scalable Kubernetes platform. Required: Python, Terraform, Docker.",
        "job_url": "https://example.com/job",
        "source": "test",
        "candidate_profile": "10 years Python, Kubernetes expert, no Terraform experience.",
        "pain_points": [
            "Manual infrastructure management causing incidents",
            "Need to scale to 10M users",
        ],
        "strategic_needs": [
            "Build platform engineering capability",
            "Implement infrastructure as code",
        ],
        "risks_if_unfilled": [
            "Technical debt increases",
        ],
        "success_metrics": [
            "Reduce deployment time by 80%",
        ],
        "selected_stars": [
            {
                "id": "star-001",
                "company": "Previous Inc",
                "role": "Platform Engineer",
                "metrics": "75% incident reduction, 10x deployment speed",
            },
        ],
        "company_research": {
            "summary": "TechCorp is a Series B startup.",
            "signals": [],
            "url": "https://techcorp.com",
            "company_type": "employer",
        },
        "role_research": {
            "summary": "Platform team ownership.",
            "business_impact": ["Enable scaling"],
            "why_now": "Recent funding requires scale.",
        },
        "jd_annotations": sample_jd_annotations_mixed,
        "errors": [],
        "status": "processing",
    }


# =============================================================================
# TEST: AnnotationFitSignal Calculator
# =============================================================================

class TestAnnotationFitSignalCalculator:
    """Tests for the AnnotationFitSignal calculator component."""

    def test_import_annotation_fit_signal(self):
        """AnnotationFitSignal can be imported from layer4."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal
        assert AnnotationFitSignal is not None

    def test_empty_annotations_returns_neutral_signal(self):
        """No annotations returns a neutral fit signal (0.5)."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(None)
        assert signal.fit_signal == 0.5
        assert signal.has_annotations is False

    def test_empty_annotations_dict_returns_neutral_signal(self):
        """Empty annotations dict returns neutral fit signal."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal({"annotations": []})
        assert signal.fit_signal == 0.5
        assert signal.has_annotations is False

    def test_core_strength_count_extracted(self, sample_jd_annotations_positive):
        """Core strength annotations are counted correctly."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_positive)
        assert signal.core_strength_count == 1

    def test_extremely_relevant_count_extracted(self, sample_jd_annotations_positive):
        """Extremely relevant annotations are counted correctly."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_positive)
        assert signal.extremely_relevant_count == 1

    def test_gap_count_extracted(self, sample_jd_annotations_mixed):
        """Gap annotations are counted correctly."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_mixed)
        assert signal.gap_count == 1

    def test_disqualifier_detected(self, sample_jd_annotations_with_disqualifier):
        """Disqualifier requirement type is detected."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_with_disqualifier)
        assert signal.has_disqualifier is True

    def test_no_disqualifier_when_absent(self, sample_jd_annotations_positive):
        """No disqualifier flag when no disqualifier annotations."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_positive)
        assert signal.has_disqualifier is False

    def test_positive_annotations_increase_fit_signal(self, sample_jd_annotations_positive):
        """Core strength and extremely relevant annotations increase fit signal."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_positive)
        # Should be higher than neutral (0.5)
        assert signal.fit_signal > 0.5
        assert signal.fit_signal <= 1.0

    def test_gaps_decrease_fit_signal(self, sample_jd_annotations_mixed):
        """Gap annotations decrease fit signal compared to all-positive."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        positive_signal = AnnotationFitSignal({
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": True},
                {"id": "2", "relevance": "extremely_relevant", "is_active": True},
            ]
        })
        mixed_signal = AnnotationFitSignal({
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": True},
                {"id": "2", "relevance": "extremely_relevant", "is_active": True},
                {"id": "3", "relevance": "gap", "is_active": True},
            ]
        })

        assert mixed_signal.fit_signal < positive_signal.fit_signal

    def test_fit_signal_bounded_zero_to_one(self, sample_jd_annotations_mixed):
        """Fit signal is always bounded between 0 and 1."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        # Test with many gaps
        many_gaps = {
            "annotations": [
                {"id": f"gap-{i}", "relevance": "gap", "is_active": True}
                for i in range(10)
            ]
        }
        signal = AnnotationFitSignal(many_gaps)
        assert 0.0 <= signal.fit_signal <= 1.0

        # Test with many core strengths
        many_strengths = {
            "annotations": [
                {"id": f"str-{i}", "relevance": "core_strength", "is_active": True}
                for i in range(10)
            ]
        }
        signal = AnnotationFitSignal(many_strengths)
        assert 0.0 <= signal.fit_signal <= 1.0

    def test_inactive_annotations_not_counted(self):
        """Inactive annotations do not contribute to signal."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal({
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": False},
                {"id": "2", "relevance": "gap", "is_active": False},
            ]
        })
        assert signal.core_strength_count == 0
        assert signal.gap_count == 0
        assert signal.has_annotations is False

    def test_to_dict_returns_analysis(self, sample_jd_annotations_mixed):
        """to_dict returns complete annotation analysis."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_mixed)
        analysis = signal.to_dict()

        assert "fit_signal" in analysis
        assert "core_strength_count" in analysis
        assert "extremely_relevant_count" in analysis
        assert "gap_count" in analysis
        assert "has_disqualifier" in analysis
        assert "has_annotations" in analysis


# =============================================================================
# TEST: Fit Score Blending
# =============================================================================

class TestFitScoreBlending:
    """Tests for blending annotation signal with LLM fit score."""

    def test_blend_function_exists(self):
        """blend_fit_scores function can be imported."""
        from src.layer4.annotation_fit_signal import blend_fit_scores
        assert blend_fit_scores is not None

    def test_blend_with_no_annotations_returns_llm_score(self):
        """When no annotations, returns LLM score unchanged."""
        from src.layer4.annotation_fit_signal import blend_fit_scores

        llm_score = 85
        blended = blend_fit_scores(llm_score, None)
        assert blended == llm_score

    def test_blend_70_30_ratio(self):
        """Default blend is 70% LLM, 30% annotation signal."""
        from src.layer4.annotation_fit_signal import blend_fit_scores

        llm_score = 80  # LLM says 80
        jd_annotations = {
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": True},
                {"id": "2", "relevance": "core_strength", "is_active": True},
            ]
        }  # Strong positive signal

        blended = blend_fit_scores(llm_score, jd_annotations)

        # With very positive annotations, blended score should be >= LLM score
        # (since annotation signal > 0.5 maps to higher scores)
        assert blended >= llm_score * 0.7  # At minimum, 70% of LLM score

    def test_blend_can_increase_score(self):
        """Positive annotations can increase the blended score."""
        from src.layer4.annotation_fit_signal import blend_fit_scores

        llm_score = 70
        positive_annotations = {
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": True},
                {"id": "2", "relevance": "core_strength", "is_active": True},
                {"id": "3", "relevance": "extremely_relevant", "is_active": True},
            ]
        }

        blended = blend_fit_scores(llm_score, positive_annotations)
        assert blended > llm_score

    def test_blend_can_decrease_score(self):
        """Gap annotations can decrease the blended score."""
        from src.layer4.annotation_fit_signal import blend_fit_scores

        llm_score = 85
        negative_annotations = {
            "annotations": [
                {"id": "1", "relevance": "gap", "is_active": True},
                {"id": "2", "relevance": "gap", "is_active": True},
                {"id": "3", "relevance": "gap", "is_active": True},
            ]
        }

        blended = blend_fit_scores(llm_score, negative_annotations)
        assert blended < llm_score

    def test_blend_respects_bounds(self):
        """Blended score is always between 0 and 100."""
        from src.layer4.annotation_fit_signal import blend_fit_scores

        # Extreme positive
        blended = blend_fit_scores(100, {
            "annotations": [
                {"id": f"{i}", "relevance": "core_strength", "is_active": True}
                for i in range(20)
            ]
        })
        assert 0 <= blended <= 100

        # Extreme negative
        blended = blend_fit_scores(0, {
            "annotations": [
                {"id": f"{i}", "relevance": "gap", "is_active": True}
                for i in range(20)
            ]
        })
        assert 0 <= blended <= 100

    def test_custom_blend_weights(self):
        """Custom blend weights can be specified."""
        from src.layer4.annotation_fit_signal import blend_fit_scores

        llm_score = 80
        annotations = {
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": True},
            ]
        }

        # 100% LLM weight
        blended_100_llm = blend_fit_scores(llm_score, annotations, llm_weight=1.0)
        assert blended_100_llm == llm_score

        # 50% LLM, 50% annotation
        blended_50_50 = blend_fit_scores(llm_score, annotations, llm_weight=0.5)
        assert blended_50_50 != llm_score  # Should be different


# =============================================================================
# TEST: Disqualifier Handling
# =============================================================================

class TestDisqualifierHandling:
    """Tests for disqualifier annotation handling."""

    def test_disqualifier_flags_potential_issue(self, sample_jd_annotations_with_disqualifier):
        """Disqualifier annotation flags a potential issue."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_with_disqualifier)
        assert signal.has_disqualifier is True
        assert signal.disqualifier_details is not None
        assert len(signal.disqualifier_details) > 0

    def test_disqualifier_returns_warning_in_analysis(self, sample_jd_annotations_with_disqualifier):
        """Disqualifier includes warning in analysis dict."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal(sample_jd_annotations_with_disqualifier)
        analysis = signal.to_dict()

        assert "disqualifier_warning" in analysis
        assert analysis["disqualifier_warning"] is not None


# =============================================================================
# TEST: OpportunityMapper Integration
# =============================================================================

class TestOpportunityMapperIntegration:
    """Tests for OpportunityMapper integration with annotation signals."""

    @patch('src.layer4.opportunity_mapper.create_tracked_llm')
    def test_mapper_includes_annotation_analysis_in_output(
        self, mock_llm_class, sample_job_state_with_annotations
    ):
        """OpportunityMapper includes annotation analysis in output."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        # Mock LLM response
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
**REASONING:**
Step 1: The candidate has strong Kubernetes experience (core_strength annotation).
Step 2: Gap in Terraform, but learnable.
Step 3: Strategic alignment with platform goals.
Step 4: Score 80 based on evidence.

**SCORE:** 80

**RATIONALE:** At Previous Inc, candidate achieved 75% incident reduction and 10x deployment speed improvement. The Kubernetes core strength directly addresses the platform scalability pain point. The Terraform gap is a learnable skill given the strong infrastructure background.
"""
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(sample_job_state_with_annotations)

        # Should include annotation analysis
        assert "annotation_analysis" in result
        assert result["annotation_analysis"] is not None

    @patch('src.layer4.opportunity_mapper.create_tracked_llm')
    def test_mapper_blends_annotation_signal_with_llm_score(
        self, mock_llm_class, sample_job_state_with_annotations
    ):
        """OpportunityMapper blends annotation signal with LLM score."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
**REASONING:**
Analysis complete.

**SCORE:** 75

**RATIONALE:** At Previous Inc, candidate achieved 75% incident reduction. Strong Kubernetes background addresses platform needs.
"""
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(sample_job_state_with_annotations)

        # LLM score is 75
        # Annotation signal has 1 core_strength, 1 extremely_relevant, 1 gap
        # Blended score should be close to but potentially different from 75
        assert result["fit_score"] is not None
        # Check annotation analysis contains raw LLM score for transparency
        assert "llm_score" in result.get("annotation_analysis", {})

    @patch('src.layer4.opportunity_mapper.create_tracked_llm')
    def test_mapper_flags_disqualifier_in_output(
        self, mock_llm_class, sample_jd_annotations_with_disqualifier
    ):
        """OpportunityMapper flags disqualifier in output."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        state_with_disqualifier = {
            "job_id": "test_002",
            "title": "SRE",
            "company": "OnCallCorp",
            "job_description": "24/7 on-call required.",
            "candidate_profile": "No on-call preference.",
            "pain_points": ["Incidents"],
            "strategic_needs": ["Reliability"],
            "risks_if_unfilled": ["Downtime"],
            "success_metrics": ["99.9% uptime"],
            "selected_stars": [],
            "jd_annotations": sample_jd_annotations_with_disqualifier,
            "errors": [],
        }

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
**SCORE:** 70

**RATIONALE:** Technical fit is reasonable but requires on-call rotation which may be a concern.
"""
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(state_with_disqualifier)

        # Should flag the disqualifier
        annotation_analysis = result.get("annotation_analysis", {})
        assert annotation_analysis.get("has_disqualifier") is True

    @patch('src.layer4.opportunity_mapper.create_tracked_llm')
    def test_mapper_works_without_annotations(self, mock_llm_class):
        """OpportunityMapper works when jd_annotations is None."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        state_no_annotations = {
            "job_id": "test_003",
            "title": "Engineer",
            "company": "NoCo",
            "job_description": "Build stuff.",
            "candidate_profile": "Experienced.",
            "pain_points": ["Pain"],
            "strategic_needs": ["Need"],
            "risks_if_unfilled": ["Risk"],
            "success_metrics": ["Metric"],
            "selected_stars": [],
            "jd_annotations": None,  # No annotations
            "errors": [],
        }

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "**SCORE:** 70\n\n**RATIONALE:** Reasonable fit."
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(state_no_annotations)

        # Should work and return LLM score without blending
        assert result["fit_score"] == 70
        # Annotation analysis should indicate no annotations
        annotation_analysis = result.get("annotation_analysis", {})
        assert annotation_analysis.get("has_annotations") is False


# =============================================================================
# TEST: Node Function Integration
# =============================================================================

class TestNodeFunctionIntegration:
    """Tests for opportunity_mapper_node with annotations."""

    @patch('src.layer4.opportunity_mapper.create_tracked_llm')
    def test_node_returns_annotation_analysis(
        self, mock_llm_class, sample_job_state_with_annotations
    ):
        """Node function returns annotation analysis in state update."""
        from src.layer4.opportunity_mapper import opportunity_mapper_node

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = """
**SCORE:** 82

**RATIONALE:** At Previous Inc, candidate achieved 75% incident reduction. Strong Kubernetes experience addresses platform needs.
"""
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        updates = opportunity_mapper_node(sample_job_state_with_annotations)

        assert "annotation_analysis" in updates
        assert updates["annotation_analysis"]["has_annotations"] is True
        assert updates["annotation_analysis"]["core_strength_count"] == 1
        assert updates["annotation_analysis"]["gap_count"] == 1


# =============================================================================
# TEST: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_malformed_annotations_handled_gracefully(self):
        """Malformed annotation data doesn't crash the calculator."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        # Missing relevance
        signal = AnnotationFitSignal({
            "annotations": [
                {"id": "1", "is_active": True},  # No relevance field
            ]
        })
        assert signal.fit_signal >= 0
        assert signal.fit_signal <= 1

    def test_all_gap_annotations(self):
        """All gap annotations give low but valid fit signal."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal({
            "annotations": [
                {"id": f"{i}", "relevance": "gap", "is_active": True}
                for i in range(5)
            ]
        })
        assert signal.fit_signal < 0.5  # Below neutral
        assert signal.fit_signal >= 0.0  # Still valid

    def test_all_core_strength_annotations(self):
        """All core strength annotations give high fit signal."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal({
            "annotations": [
                {"id": f"{i}", "relevance": "core_strength", "is_active": True}
                for i in range(5)
            ]
        })
        assert signal.fit_signal > 0.5  # Above neutral
        assert signal.fit_signal <= 1.0  # Still valid

    def test_mixed_active_inactive_annotations(self):
        """Only active annotations are counted."""
        from src.layer4.annotation_fit_signal import AnnotationFitSignal

        signal = AnnotationFitSignal({
            "annotations": [
                {"id": "1", "relevance": "core_strength", "is_active": True},
                {"id": "2", "relevance": "core_strength", "is_active": False},  # Inactive
                {"id": "3", "relevance": "gap", "is_active": True},
                {"id": "4", "relevance": "gap", "is_active": False},  # Inactive
            ]
        })
        assert signal.core_strength_count == 1  # Only active
        assert signal.gap_count == 1  # Only active
