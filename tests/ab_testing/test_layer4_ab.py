"""
A/B Tests for Layer 4 (Opportunity Mapper) Prompt Optimization.

Tests 4 issues identified in the prompt optimization plan:
1. Weak grounding - rationales don't cite specific evidence
2. No chain-of-thought - missing visible reasoning steps
3. Generic rationales - boilerplate passes validation
4. Context overload - irrelevant context cited

Each issue has tests for:
- Baseline behavior capture
- Enhanced prompt application
- Improvement comparison
"""

import pytest
from unittest.mock import MagicMock, patch

from tests.ab_testing.framework import ABTestRunner, ABTestResult, Comparison
from tests.ab_testing.scorers import score_specificity, score_grounding, score_hallucinations


class TestWeakGrounding:
    """A/B tests for Layer 4 weak grounding issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for weak-grounding issue."""
        return ABTestRunner(
            layer="layer4",
            issue="weak-grounding",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_captures_current_behavior(
        self, runner, test_jobs, mock_baseline_generator
    ):
        """Run baseline and verify outputs are captured."""
        runner.set_baseline_generator(mock_baseline_generator)
        result = runner.run_baseline("v1")

        assert isinstance(result, ABTestResult)
        assert len(result.outputs) == 3
        assert result.avg_specificity is not None
        assert result.avg_grounding is not None
        assert result.version == "v1"

    def test_baseline_detects_weak_grounding(
        self, runner, test_jobs, mock_baseline_generator
    ):
        """Verify baseline has low grounding score (problem exists)."""
        runner.set_baseline_generator(mock_baseline_generator)
        result = runner.run_baseline("v1")

        # Baseline should have weak grounding (generic text)
        assert result.avg_grounding < 7.0, (
            f"Baseline grounding should be low (<7.0), got {result.avg_grounding}"
        )

    def test_enhanced_applies_anti_hallucination_guardrails(
        self, runner, test_jobs, mock_enhanced_generator
    ):
        """Run enhanced prompt with anti-hallucination guardrails (technique 3.4)."""
        runner.set_enhanced_generator(mock_enhanced_generator)
        result = runner.run_enhanced("v2", technique="anti-hallucination-guardrails-3.4")

        assert result.technique == "anti-hallucination-guardrails-3.4"
        # Enhanced should have better grounding
        assert result.avg_grounding > 5.0

    def test_comparison_shows_grounding_improvement(
        self, runner, mock_baseline_generator, mock_enhanced_generator
    ):
        """Compare baseline vs enhanced and verify grounding improvement."""
        runner.set_baseline_generator(mock_baseline_generator)
        runner.set_enhanced_generator(mock_enhanced_generator)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2", technique="anti-hallucination-guardrails-3.4")
        comparison = runner.compare(baseline, enhanced)

        assert isinstance(comparison, Comparison)
        assert comparison.grounding_delta >= 0, (
            f"Grounding should not regress, delta: {comparison.grounding_delta}"
        )

    def test_analysis_report_generated(
        self, runner, mock_baseline_generator, mock_enhanced_generator
    ):
        """Verify analysis report is generated."""
        runner.set_baseline_generator(mock_baseline_generator)
        runner.set_enhanced_generator(mock_enhanced_generator)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        report = runner.generate_analysis_report(comparison)
        assert "A/B Analysis" in report
        assert "layer4" in report


class TestNoChainOfThought:
    """A/B tests for Layer 4 missing chain-of-thought issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for no-cot issue."""
        return ABTestRunner(
            layer="layer4",
            issue="no-cot",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_lacks_reasoning_steps(
        self, runner, mock_baseline_generator
    ):
        """Verify baseline lacks visible reasoning steps."""
        runner.set_baseline_generator(mock_baseline_generator)
        result = runner.run_baseline("v1")

        # Check outputs don't contain thinking/reasoning markers
        for output in result.outputs:
            text_lower = output.output_text.lower()
            has_reasoning = any(marker in text_lower for marker in [
                "thinking", "reasoning", "step 1", "first,", "analysis:"
            ])
            # Baseline should NOT have structured reasoning
            assert not has_reasoning, "Baseline should lack structured reasoning"

    def test_enhanced_includes_reasoning_blocks(self, runner, test_jobs, master_cv):
        """Run enhanced prompt with reasoning-first approach (technique 2.2)."""
        def enhanced_with_cot(job_state):
            stars = job_state.get("selected_stars", [])
            star = stars[0] if stars else {}
            return f"""
<thinking>
Step 1: Analyze job requirements
- Title: {job_state.get('title')}
- Key pain point: {job_state.get('pain_points', ['scaling'])[0]}

Step 2: Map to candidate experience
- Relevant STAR: {star.get('company', 'Previous')} - {star.get('situation', 'similar challenge')}

Step 3: Calculate fit score
- Pain point coverage: 80%
- STAR evidence: Strong

Step 4: Generate rationale
</thinking>

Based on systematic analysis, the candidate is a strong fit because:
1. Direct experience addressing "{job_state.get('pain_points', [''])[0]}" at {star.get('company', 'previous role')}
2. Achieved {star.get('metrics', 'significant improvements')}
3. Technical skills align with tech stack requirements

Fit Score: 8.5/10
Category: Strong Match
            """

        runner.set_enhanced_generator(enhanced_with_cot)
        result = runner.run_enhanced("v2", technique="reasoning-first-2.2")

        # Check outputs contain reasoning markers
        for output in result.outputs:
            text = output.output_text
            assert "<thinking>" in text or "Step 1" in text, (
                "Enhanced should include reasoning blocks"
            )

    def test_comparison_measures_reasoning_presence(
        self, runner, mock_baseline_generator
    ):
        """Verify comparison can detect reasoning improvement."""
        runner.set_baseline_generator(mock_baseline_generator)

        def enhanced_with_cot(job_state):
            return f"""
<thinking>
Analysis of {job_state.get('company')}:
1. Pain point: {job_state.get('pain_points', [''])[0]}
2. Match: Strong based on STAR evidence
</thinking>

Recommendation: Strong fit due to {job_state.get('selected_stars', [{}])[0].get('company', 'experience')}.
            """

        runner.set_enhanced_generator(enhanced_with_cot)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2", technique="reasoning-first-2.2")
        comparison = runner.compare(baseline, enhanced)

        # Enhanced should show improvement or maintain quality
        assert comparison.combined_delta >= -0.5, "Should not regress significantly"


class TestGenericRationales:
    """A/B tests for Layer 4 generic rationales issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for generic-rationales issue."""
        return ABTestRunner(
            layer="layer4",
            issue="generic-rationales",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_allows_generic_phrases(
        self, runner, mock_baseline_generator
    ):
        """Verify baseline contains generic boilerplate phrases."""
        runner.set_baseline_generator(mock_baseline_generator)
        result = runner.run_baseline("v1")

        generic_phrases = ["proven track record", "team player", "excellent communication"]

        for output in result.outputs:
            text_lower = output.output_text.lower()
            generic_count = sum(1 for p in generic_phrases if p in text_lower)
            # Baseline SHOULD have generic phrases (the problem we're fixing)
            assert generic_count > 0, "Baseline should contain generic phrases"

    def test_enhanced_eliminates_generic_phrases(
        self, runner, mock_enhanced_generator
    ):
        """Run enhanced prompt with constraint prompting (technique 3.5)."""
        runner.set_enhanced_generator(mock_enhanced_generator)
        result = runner.run_enhanced("v2", technique="constraint-prompting-3.5")

        generic_phrases = ["proven track record", "team player", "excellent communication",
                          "great fit", "excited to apply"]

        for output in result.outputs:
            text_lower = output.output_text.lower()
            generic_count = sum(1 for p in generic_phrases if p in text_lower)
            # Enhanced should have fewer/no generic phrases
            assert generic_count <= 1, (
                f"Enhanced should minimize generic phrases, found {generic_count}"
            )

    def test_specificity_score_improves(
        self, runner, mock_baseline_generator, mock_enhanced_generator
    ):
        """Verify specificity score improves with enhanced prompt."""
        runner.set_baseline_generator(mock_baseline_generator)
        runner.set_enhanced_generator(mock_enhanced_generator)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2", technique="constraint-prompting-3.5")
        comparison = runner.compare(baseline, enhanced)

        # Specificity should improve (fewer generic phrases)
        assert comparison.specificity_delta >= 0, (
            f"Specificity should improve, delta: {comparison.specificity_delta}"
        )


class TestContextOverload:
    """A/B tests for Layer 4 context overload issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for context-overload issue."""
        return ABTestRunner(
            layer="layer4",
            issue="context-overload",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_cites_excessive_context(
        self, runner
    ):
        """Verify baseline might cite too much irrelevant context."""
        def overloaded_baseline(job_state):
            # Simulates citing everything without prioritization
            all_stars = job_state.get("selected_stars", [])
            all_text = ""
            for star in all_stars:
                all_text += f"At {star.get('company')}, did {star.get('actions')}. "

            pains = job_state.get("pain_points", [])
            for pain in pains:
                all_text += f"Addresses: {pain}. "

            signals = job_state.get("company_research", {}).get("signals", [])
            for signal in signals:
                all_text += f"Company signal: {signal.get('description')}. "

            return f"Extensive background covering: {all_text}"

        runner.set_baseline_generator(overloaded_baseline)
        result = runner.run_baseline("v1")

        # Baseline outputs should be verbose
        for output in result.outputs:
            assert len(output.output_text) > 200, "Baseline should be verbose"

    def test_enhanced_prioritizes_context(self, runner):
        """Run enhanced prompt with context prioritization (technique 2.3)."""
        def focused_enhanced(job_state):
            # Only cite top 1-2 most relevant items
            stars = job_state.get("selected_stars", [])
            top_star = stars[0] if stars else {}
            top_pain = job_state.get("pain_points", [""])[0]

            return f"""
Most Relevant Match:
- Pain Point: {top_pain}
- Evidence: At {top_star.get('company', 'previous role')}, achieved {top_star.get('metrics', 'results')}

Fit Score: 8/10
Rationale: Direct experience addressing the top priority pain point with quantified results.
            """

        runner.set_enhanced_generator(focused_enhanced)
        result = runner.run_enhanced("v2", technique="context-prioritization-2.3")

        # Enhanced should be more focused
        for output in result.outputs:
            # Check for focused structure
            assert "Most Relevant" in output.output_text or "top" in output.output_text.lower()

    def test_comparison_measures_focus_improvement(
        self, runner
    ):
        """Verify enhanced output is more focused than baseline."""
        def verbose_baseline(job_state):
            return "Extensive " * 50 + f"fit for {job_state.get('company')} " * 10

        def focused_enhanced(job_state):
            return f"Top match: {job_state.get('selected_stars', [{}])[0].get('company', 'X')} - {job_state.get('pain_points', [''])[0]}"

        runner.set_baseline_generator(verbose_baseline)
        runner.set_enhanced_generator(focused_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")

        # Enhanced should have shorter, more focused output
        avg_baseline_len = sum(len(o.output_text) for o in baseline.outputs) / 3
        avg_enhanced_len = sum(len(o.output_text) for o in enhanced.outputs) / 3

        assert avg_enhanced_len < avg_baseline_len, (
            "Enhanced should be more concise than verbose baseline"
        )


class TestScorerIntegration:
    """Tests for scorer integration with Layer 4 outputs."""

    def test_specificity_scorer_detects_generic_text(self, test_job_1):
        """Test specificity scorer identifies generic language."""
        generic_text = "I have a proven track record and am a team player with excellent communication."

        result = score_specificity(generic_text, test_job_1)
        assert result.score < 5.0, "Generic text should score low on specificity"

    def test_specificity_scorer_rewards_specific_text(self, test_job_1):
        """Test specificity scorer rewards specific details."""
        specific_text = """
At Seven.One Entertainment Group, I led the transformation achieving 75% incident reduction.
Using AWS Lambda and microservices, we processed millions of events daily.
This directly addresses KAIZEN GAMING's need for scalable backend architecture.
        """

        result = score_specificity(specific_text, test_job_1)
        assert result.score >= 5.0, f"Specific text should score higher, got {result.score}"

    def test_grounding_scorer_requires_star_citations(self, test_job_1, master_cv):
        """Test grounding scorer checks for STAR company citations."""
        ungrounded_text = "I have experience with microservices and team leadership."
        grounded_text = "At Seven.One Entertainment Group, I achieved 75% incident reduction with microservices."

        ungrounded_result = score_grounding(ungrounded_text, test_job_1)
        grounded_result = score_grounding(grounded_text, test_job_1)

        assert grounded_result.score > ungrounded_result.score, (
            "Grounded text should score higher than ungrounded"
        )

    def test_hallucination_scorer_detects_unknown_companies(self, test_job_1, master_cv):
        """Test hallucination scorer flags unknown company names."""
        fabricated_text = "At FakeTech Industries, I achieved 500% improvement."

        result = score_hallucinations(fabricated_text, master_cv, test_job_1)
        # Should detect potential unknown company
        assert len(result.details.get("potential_unknown_companies", [])) > 0 or result.score < 9.0
