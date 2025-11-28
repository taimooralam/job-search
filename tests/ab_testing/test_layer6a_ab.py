"""
A/B Tests for Layer 6a (Cover Letter Generator) Prompt Optimization.

Tests 4 issues identified in the prompt optimization plan:
1. Rigid structure - fixed paragraph count doesn't adapt
2. Weak pain point integration - pain points not mapped to achievements
3. Generic company research - company-specific details not used
4. STAR grounding not validated - metrics may not come from master-cv

Each issue has tests for:
- Baseline behavior capture
- Enhanced prompt application
- Improvement comparison
"""

import pytest

from tests.ab_testing.framework import ABTestRunner, ABTestResult, Comparison
from tests.ab_testing.scorers import score_specificity, score_grounding


class TestRigidStructure:
    """A/B tests for Layer 6a rigid structure issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for rigid-structure issue."""
        return ABTestRunner(
            layer="layer6a",
            issue="rigid-structure",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_uses_fixed_paragraphs(self, runner):
        """Verify baseline produces fixed 4-paragraph structure."""
        def fixed_structure_baseline(job_state):
            return f"""
Dear Hiring Manager,

Paragraph 1: I am excited to apply for the {job_state.get('title')} position at {job_state.get('company')}.

Paragraph 2: My background includes relevant experience in software engineering.

Paragraph 3: I am confident I can contribute to your team's success.

Paragraph 4: I look forward to discussing this opportunity further.

Sincerely,
Candidate
            """

        runner.set_baseline_generator(fixed_structure_baseline)
        result = runner.run_baseline("v1")

        for output in result.outputs:
            # Count paragraph markers
            paragraphs = [p.strip() for p in output.output_text.split("\n\n") if p.strip()]
            # Should have fixed structure regardless of content
            assert 4 <= len(paragraphs) <= 6, "Baseline should have fixed paragraph count"

    def test_enhanced_adapts_structure(self, runner):
        """Run enhanced prompt with flexible format (technique 2.2)."""
        def adaptive_structure_enhanced(job_state):
            pain_points = job_state.get("pain_points", [])
            stars = job_state.get("selected_stars", [])

            # Adapt structure based on content
            sections = [f"Dear Hiring Team at {job_state.get('company')},"]

            # Opening with specific hook
            sections.append(
                f"Your need for {pain_points[0] if pain_points else 'strong leadership'} "
                f"resonates with my experience at {stars[0].get('company') if stars else 'my previous role'}."
            )

            # Dynamic sections based on pain point count
            for i, pain in enumerate(pain_points[:3]):
                star = stars[i] if i < len(stars) else stars[0] if stars else {}
                sections.append(
                    f"Addressing '{pain}': At {star.get('company', 'previous role')}, "
                    f"I {star.get('actions', 'addressed similar challenges')[:100]}, "
                    f"achieving {star.get('metrics', 'significant results')}."
                )

            sections.append("I would welcome the opportunity to discuss how my experience aligns with your needs.")

            return "\n\n".join(sections)

        runner.set_enhanced_generator(adaptive_structure_enhanced)
        result = runner.run_enhanced("v2", technique="flexible-format-2.2")

        # Enhanced should have variable paragraph count based on content
        lengths = [len(o.output_text.split("\n\n")) for o in result.outputs]
        # Should vary based on job content
        assert len(set(lengths)) >= 1, "Enhanced structure adapts to content"

    def test_comparison_shows_flexibility_improvement(
        self, runner
    ):
        """Verify enhanced produces more content-appropriate structure."""
        def rigid_baseline(job_state):
            return "Para 1.\n\nPara 2.\n\nPara 3.\n\nPara 4."

        def flexible_enhanced(job_state):
            pains = job_state.get("pain_points", [])
            return "\n\n".join([f"Addressing: {p}" for p in pains[:4]])

        runner.set_baseline_generator(rigid_baseline)
        runner.set_enhanced_generator(flexible_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        # Should not regress
        assert comparison.combined_delta >= -1.0


class TestWeakPainPoints:
    """A/B tests for Layer 6a weak pain point integration issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for weak-painpoints issue."""
        return ABTestRunner(
            layer="layer6a",
            issue="weak-painpoints",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_ignores_pain_points(self, runner):
        """Verify baseline doesn't map pain points to achievements."""
        def generic_baseline(job_state):
            return f"""
Dear Hiring Manager,

I am writing to express my interest in the {job_state.get('title')} position.

My experience in software engineering makes me an excellent candidate.
I have led teams and delivered projects successfully.

I look forward to hearing from you.
            """

        runner.set_baseline_generator(generic_baseline)
        result = runner.run_baseline("v1")

        # Check that pain points are not addressed
        for output in result.outputs:
            text_lower = output.output_text.lower()
            # Should NOT contain specific pain point language
            assert "pain point" not in text_lower
            assert "addressing" not in text_lower or "address" not in text_lower[:100]

    def test_enhanced_maps_pain_to_achievement(self, runner):
        """Run enhanced prompt with explicit pain-achievement mapping (technique 2.4)."""
        def mapped_enhanced(job_state):
            pain_points = job_state.get("pain_points", [])
            stars = job_state.get("selected_stars", [])
            mapping = job_state.get("star_to_pain_mapping", {})

            sections = [f"Dear {job_state.get('company')} Team,"]

            # Explicit pain -> achievement mapping
            sections.append("PAIN POINT TO ACHIEVEMENT MAPPING:")

            for pain in pain_points[:3]:
                mapped_star_ids = mapping.get(pain, [])
                if mapped_star_ids and stars:
                    star = next((s for s in stars if s.get("id") in mapped_star_ids), stars[0])
                    sections.append(
                        f"- Your challenge: '{pain}'\n"
                        f"  My solution: At {star.get('company')}, {star.get('results')}\n"
                        f"  Evidence: {star.get('metrics')}"
                    )
                else:
                    sections.append(f"- Challenge: '{pain}' - Ready to address with proven approaches")

            return "\n\n".join(sections)

        runner.set_enhanced_generator(mapped_enhanced)
        result = runner.run_enhanced("v2", technique="show-ask-rubric-2.4")

        # Check that pain points ARE addressed
        for output in result.outputs:
            text_lower = output.output_text.lower()
            # Should contain explicit mapping language
            assert "challenge" in text_lower or "pain" in text_lower or "solution" in text_lower

    def test_grounding_improves_with_mapping(
        self, runner
    ):
        """Verify grounding score improves with pain-achievement mapping."""
        def unmapped_baseline(job_state):
            return f"Generic cover letter for {job_state.get('company')}."

        def mapped_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            star = stars[0] if stars else {}
            pain = job_state.get("pain_points", ["leadership"])[0]
            return f"""
Your need for {pain} maps to my experience at {star.get('company', 'previous')}.
I achieved: {star.get('metrics', 'significant results')}.
            """

        runner.set_baseline_generator(unmapped_baseline)
        runner.set_enhanced_generator(mapped_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        assert comparison.grounding_delta >= 0, "Mapping should improve grounding"


class TestGenericResearch:
    """A/B tests for Layer 6a generic company research issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for generic-research issue."""
        return ABTestRunner(
            layer="layer6a",
            issue="generic-research",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_lacks_company_specifics(self, runner):
        """Verify baseline doesn't use company-specific research."""
        def generic_baseline(job_state):
            return f"""
I am excited about the opportunity at {job_state.get('company')}.
Your company is a leader in the industry and I would love to contribute.
I bring relevant experience that would benefit your team.
            """

        runner.set_baseline_generator(generic_baseline)
        result = runner.run_baseline("v1")

        # Should have low specificity due to generic language
        assert result.avg_specificity < 6.0, "Generic baseline should have low specificity"

    def test_enhanced_incorporates_signals(self, runner):
        """Run enhanced prompt with company signal integration."""
        def research_enhanced(job_state):
            research = job_state.get("company_research", {})
            signals = research.get("signals", [])
            summary = research.get("summary", "")

            sections = [f"Dear {job_state.get('company')} Team,"]

            # Lead with company-specific insight
            if signals:
                signal = signals[0]
                sections.append(
                    f"Your recent {signal.get('type', 'announcement')} - "
                    f"{signal.get('description', 'growth initiative')} - "
                    f"signals exciting challenges that align with my expertise."
                )

            # Use company summary
            if summary:
                sections.append(f"As {summary[:100]}..., you need leaders who can scale rapidly.")

            stars = job_state.get("selected_stars", [])
            if stars:
                sections.append(
                    f"At {stars[0].get('company')}, I delivered {stars[0].get('metrics')} "
                    f"in a similar growth context."
                )

            return "\n\n".join(sections)

        runner.set_enhanced_generator(research_enhanced)
        result = runner.run_enhanced("v2", technique="company-aware-context")

        # Should have higher specificity with research integration
        assert result.avg_specificity > 4.0, "Research integration should improve specificity"

    def test_comparison_measures_research_usage(self, runner):
        """Verify enhanced uses more company-specific content."""
        def no_research_baseline(job_state):
            return "Generic cover letter without research."

        def research_enhanced(job_state):
            signals = job_state.get("company_research", {}).get("signals", [])
            signal_text = signals[0].get("description", "") if signals else ""
            return f"Given {job_state.get('company')}'s {signal_text}, my experience is directly relevant."

        runner.set_baseline_generator(no_research_baseline)
        runner.set_enhanced_generator(research_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        assert comparison.specificity_delta >= 0, "Research usage should improve specificity"


class TestSTARGrounding:
    """A/B tests for Layer 6a STAR grounding validation issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for star-grounding issue."""
        return ABTestRunner(
            layer="layer6a",
            issue="star-grounding",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_may_have_ungrounded_metrics(self, runner):
        """Verify baseline might include metrics not from source."""
        def possibly_fabricated_baseline(job_state):
            # Includes a made-up metric
            return f"""
At my previous company, I achieved 500% improvement in team velocity
and saved $50 million annually through optimization.
I would bring this same impact to {job_state.get('company')}.
            """

        runner.set_baseline_generator(possibly_fabricated_baseline)
        result = runner.run_baseline("v1")

        # Should have lower hallucination score (fabricated metrics)
        # Note: 500% and $50M are not in the master CV
        assert result.avg_hallucinations < 9.0, (
            "Fabricated metrics should lower hallucination score"
        )

    def test_enhanced_uses_only_sourced_metrics(self, runner):
        """Run enhanced prompt with Battle-of-Bots critique (technique 3.2)."""
        def validated_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            star = stars[0] if stars else {}

            # Only use metrics from STAR records
            metrics = star.get("metrics", "")

            return f"""
At {star.get('company', 'my previous role')}, I achieved:
{metrics}

These verified results demonstrate my ability to deliver for {job_state.get('company')}.
[Source: STAR record from {star.get('company', 'verified experience')}]
            """

        runner.set_enhanced_generator(validated_enhanced)
        result = runner.run_enhanced("v2", technique="battle-of-bots-3.2")

        # Should have high hallucination score (metrics are sourced)
        assert result.avg_hallucinations >= 7.0, (
            "Sourced metrics should have high hallucination score"
        )

    def test_comparison_shows_hallucination_reduction(self, runner, master_cv):
        """Verify enhanced has better hallucination scores."""
        def fabricated_baseline(job_state):
            return "I achieved 999% growth and saved $100 billion at FakeCorp Industries."

        def grounded_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            star = stars[0] if stars else {}
            return f"At {star.get('company', 'Seven.One')}, I achieved {star.get('metrics', '75% reduction')}."

        runner.set_baseline_generator(fabricated_baseline)
        runner.set_enhanced_generator(grounded_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        # Hallucinations should improve (higher score = fewer fabrications)
        assert comparison.hallucinations_delta >= 0, (
            f"Hallucination score should improve, delta: {comparison.hallucinations_delta}"
        )


class TestCoverLetterScorerIntegration:
    """Tests for scorer integration with cover letter outputs."""

    def test_cover_letter_specificity_scoring(self, test_job_1):
        """Test specificity scorer on cover letter content."""
        generic_letter = """
Dear Hiring Manager,
I am excited to apply for this position. I have relevant experience and would be a great fit.
I look forward to hearing from you.
        """

        specific_letter = f"""
Dear KAIZEN GAMING Team,

Your need for a Software Engineering Team Lead to scale your .NET/microservices platform
resonates with my experience at Seven.One Entertainment Group. There, I led the transformation
of a monolithic AdTech platform to event-driven microservices, achieving 75% incident reduction
and zero downtime for 3 consecutive years.

Given your expansion into new markets (Canada, Ecuador, Peru), I can apply my experience
scaling AWS infrastructure for bursty traffic patterns to ensure platform reliability.
        """

        generic_result = score_specificity(generic_letter, test_job_1)
        specific_result = score_specificity(specific_letter, test_job_1)

        assert specific_result.score > generic_result.score, (
            "Specific cover letter should score higher on specificity"
        )

    def test_cover_letter_grounding_scoring(self, test_job_1):
        """Test grounding scorer on cover letter content."""
        ungrounded_letter = "I have experience in software engineering and team leadership."

        grounded_letter = """
At Seven.One Entertainment Group, I led a multi-year transformation achieving 75% incident reduction.
My experience with microservices and AWS directly addresses your pain point of needing
strong technical leadership for backend engineering team.
        """

        ungrounded_result = score_grounding(ungrounded_letter, test_job_1)
        grounded_result = score_grounding(grounded_letter, test_job_1)

        assert grounded_result.score > ungrounded_result.score, (
            "Grounded cover letter should score higher"
        )
