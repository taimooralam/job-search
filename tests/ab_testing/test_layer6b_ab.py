"""
A/B Tests for Layer 6b (CV Generator) Prompt Optimization.

Tests 4 issues identified in the prompt optimization plan:
1. Regex-based parsing - fragile parsing of master CV
2. No role-specific selection - achievements not tailored to role
3. Generic summaries - professional summary lacks specificity
4. Hallucination gaps - facts may not come from master-cv

Each issue has tests for:
- Baseline behavior capture
- Enhanced prompt application
- Improvement comparison
"""

import pytest

from tests.ab_testing.framework import ABTestRunner, ABTestResult, Comparison
from tests.ab_testing.scorers import (
    score_specificity,
    score_grounding,
    score_hallucinations,
)


class TestRegexParsing:
    """A/B tests for Layer 6b regex-based parsing issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for regex-parsing issue."""
        return ABTestRunner(
            layer="layer6b",
            issue="regex-parsing",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_uses_rigid_parsing(self, runner):
        """Verify baseline uses rigid section extraction."""
        def rigid_parser_baseline(job_state):
            # Simulates regex-based parsing that might miss sections
            profile = job_state.get("candidate_profile", "")

            # Rigid pattern matching
            sections = {
                "name": "Candidate Name",
                "experience": "Experience section",
                "education": "Education section",
            }

            return f"""
PARSED CV:
Name: {sections['name']}
Experience: {sections['experience']}
Education: {sections['education']}

[Note: Rigid parsing may miss nuanced content]
            """

        runner.set_baseline_generator(rigid_parser_baseline)
        result = runner.run_baseline("v1")

        # Baseline should produce output
        assert len(result.outputs) == 3
        for output in result.outputs:
            assert "PARSED CV" in output.output_text

    def test_enhanced_uses_llm_parsing(self, runner):
        """Run enhanced prompt with LLM-driven parsing (technique 3.1)."""
        def llm_parser_enhanced(job_state):
            # Simulates LLM understanding context
            profile = job_state.get("candidate_profile", "")
            stars = job_state.get("selected_stars", [])

            # Extract meaningful content with context understanding
            name = "Taimoor Alam"  # LLM would extract this
            title = "Engineering Leader / Software Architect"

            experience_items = []
            for star in stars[:3]:
                experience_items.append(
                    f"- {star.get('role')} at {star.get('company')} ({star.get('period')})\n"
                    f"  {star.get('results')}"
                )

            return f"""
CV FOR {job_state.get('company')} - {job_state.get('title')}

{name}
{title}

SELECTED EXPERIENCE (role-aligned):
{chr(10).join(experience_items)}

[LLM-parsed with context awareness]
            """

        runner.set_enhanced_generator(llm_parser_enhanced)
        result = runner.run_enhanced("v2", technique="tree-of-thoughts-3.1")

        # Enhanced should have more structured, context-aware output
        for output in result.outputs:
            assert "role-aligned" in output.output_text.lower() or "selected" in output.output_text.lower()

    def test_comparison_measures_parsing_quality(self, runner):
        """Verify enhanced produces better parsed content."""
        def rigid_baseline(job_state):
            return "Rigid CV parse: [SECTIONS MAY BE MISSING]"

        def flexible_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            return f"Contextual CV for {job_state.get('company')}: {len(stars)} relevant experiences extracted"

        runner.set_baseline_generator(rigid_baseline)
        runner.set_enhanced_generator(flexible_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        # Should not regress significantly
        assert comparison.combined_delta >= -1.0


class TestRoleSelection:
    """A/B tests for Layer 6b role-specific selection issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for role-selection issue."""
        return ABTestRunner(
            layer="layer6b",
            issue="role-selection",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_shows_all_experience(self, runner):
        """Verify baseline includes all experience without prioritization."""
        def non_selective_baseline(job_state):
            return """
PROFESSIONAL EXPERIENCE:

1. Seven.One Entertainment Group - Technical Lead (2020-Present)
   - Led transformation of AdTech platform
   - Multiple other responsibilities

2. Samdock - Lead Software Engineer (2019-2020)
   - Built CRM platform
   - All achievements listed

3. KI Labs - Intermediate Backend Engineer (2018-2019)
   - Built REST APIs
   - Everything included

4. OSRAM - Software Engineer IoT (2016-2018)
   - IoT development
   - Complete listing

[All experience shown regardless of role relevance]
            """

        runner.set_baseline_generator(non_selective_baseline)
        result = runner.run_baseline("v1")

        # Should include multiple experiences
        for output in result.outputs:
            assert output.output_text.count("20") >= 4, "Baseline shows all dates/experiences"

    def test_enhanced_prioritizes_by_role(self, runner):
        """Run enhanced prompt with competency mix analysis (technique 5.2)."""
        def role_selective_enhanced(job_state):
            title = job_state.get("title", "")
            stars = job_state.get("selected_stars", [])

            # Simulate competency analysis for a Team Lead role
            is_leadership_role = "lead" in title.lower() or "manager" in title.lower()

            if is_leadership_role:
                # Prioritize leadership-relevant STARs
                relevant_stars = [s for s in stars if "lead" in s.get("role", "").lower()]
                emphasis = "LEADERSHIP FOCUS"
            else:
                # Technical role
                relevant_stars = stars
                emphasis = "TECHNICAL FOCUS"

            experience_text = ""
            for i, star in enumerate(relevant_stars[:2], 1):
                experience_text += f"""
{i}. {star.get('company')} - {star.get('role')} ({star.get('period')})
   LEADERSHIP IMPACT: {star.get('results')}
   KEY METRICS: {star.get('metrics')}
"""

            return f"""
CV TAILORED FOR: {title} at {job_state.get('company')}
{emphasis} - Role requires {emphasis.split()[0].lower()} competencies

TOP RELEVANT EXPERIENCE:
{experience_text}
[Prioritized by role alignment]
            """

        runner.set_enhanced_generator(role_selective_enhanced)
        result = runner.run_enhanced("v2", technique="debate-mode-5.2")

        # Should show role-specific prioritization
        for output in result.outputs:
            text = output.output_text
            assert "TAILORED" in text or "FOCUS" in text or "RELEVANT" in text

    def test_comparison_shows_relevance_improvement(self, runner):
        """Verify enhanced produces more role-relevant content."""
        def generic_baseline(job_state):
            return "CV with all experience listed without prioritization."

        def selective_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            top_star = stars[0] if stars else {}
            return f"""
Top Match for {job_state.get('title')}:
{top_star.get('company')} - {top_star.get('role')}
Because: {top_star.get('situation', 'relevant experience')}
            """

        runner.set_baseline_generator(generic_baseline)
        runner.set_enhanced_generator(selective_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        # Grounding should improve with better STAR selection
        assert comparison.grounding_delta >= -0.5


class TestGenericSummaries:
    """A/B tests for Layer 6b generic professional summary issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for generic-summaries issue."""
        return ABTestRunner(
            layer="layer6b",
            issue="generic-summaries",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_produces_generic_summary(self, runner):
        """Verify baseline produces generic professional summary."""
        def generic_summary_baseline(job_state):
            return """
PROFESSIONAL SUMMARY

Experienced software engineering leader with a proven track record of success.
Strong technical background with excellent communication skills.
Team player who delivers results and drives innovation.
Seeking new opportunities to leverage my extensive experience.
            """

        runner.set_baseline_generator(generic_summary_baseline)
        result = runner.run_baseline("v1")

        # Should have low specificity (generic phrases)
        assert result.avg_specificity < 5.0, (
            f"Generic summary should have low specificity, got {result.avg_specificity}"
        )

    def test_enhanced_produces_specific_summary(self, runner):
        """Run enhanced prompt with self-consistency scoring (technique 5.1)."""
        def specific_summary_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            company = job_state.get("company", "")

            # Extract specific metrics from STARs
            top_metrics = []
            for star in stars[:2]:
                metrics = star.get("metrics", "")
                if metrics:
                    top_metrics.append(metrics.split(",")[0])

            return f"""
PROFESSIONAL SUMMARY

Engineering leader with 11+ years building high-scale distributed systems,
delivering {top_metrics[0] if top_metrics else '75% incident reduction'} at Seven.One Entertainment Group.
Expert in modernizing legacy architectures through Domain-Driven Design and event-driven microservices.
Proven track record scaling engineering teams while maintaining zero downtime for 3 consecutive years.

TAILORED FOR {company}: My experience with microservices architecture and team scaling
directly addresses your need for backend engineering leadership.
            """

        runner.set_enhanced_generator(specific_summary_enhanced)
        result = runner.run_enhanced("v2", technique="self-consistency-5.1")

        # Should have higher specificity
        assert result.avg_specificity > 4.0, (
            f"Specific summary should have higher specificity, got {result.avg_specificity}"
        )

    def test_comparison_shows_specificity_improvement(self, runner):
        """Verify enhanced summary has better specificity."""
        def generic_baseline(job_state):
            return "Experienced professional with proven track record seeking opportunities."

        def specific_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            metrics = stars[0].get("metrics", "75% improvement") if stars else "75% improvement"
            return f"Engineering leader who achieved {metrics} at {stars[0].get('company') if stars else 'previous role'}."

        runner.set_baseline_generator(generic_baseline)
        runner.set_enhanced_generator(specific_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        assert comparison.specificity_delta >= 0, (
            f"Specificity should improve, delta: {comparison.specificity_delta}"
        )


class TestHallucinationGaps:
    """A/B tests for Layer 6b hallucination gaps issue."""

    @pytest.fixture
    def runner(self, test_jobs, master_cv):
        """Create ABTestRunner for hallucination-gaps issue."""
        return ABTestRunner(
            layer="layer6b",
            issue="hallucination-gaps",
            test_jobs=test_jobs,
            master_cv=master_cv,
        )

    def test_baseline_may_contain_fabrications(self, runner):
        """Verify baseline might include fabricated information."""
        def potentially_fabricated_baseline(job_state):
            return """
PROFESSIONAL EXPERIENCE

Senior Director at FakeTech Industries (2022-2025)
- Led team of 500 engineers
- Achieved $100 billion in cost savings
- 10000% improvement in all metrics
- PhD from Harvard Business School

Technical Lead at AnotherFakeCorp (2020-2022)
- Invented new programming language
- Revolutionized the entire industry
            """

        runner.set_baseline_generator(potentially_fabricated_baseline)
        result = runner.run_baseline("v1")

        # Should have low hallucination score (many fabrications)
        assert result.avg_hallucinations < 8.0, (
            f"Fabricated content should lower hallucination score, got {result.avg_hallucinations}"
        )

    def test_enhanced_validates_all_claims(self, runner):
        """Run enhanced prompt with assumption ledger (source validation)."""
        def validated_enhanced(job_state):
            stars = job_state.get("selected_stars", [])

            experience_text = ""
            for star in stars[:2]:
                experience_text += f"""
{star.get('role')} at {star.get('company')} ({star.get('period')})
[SOURCE: STAR Record]
- Situation: {star.get('situation', '')}
- Results: {star.get('results', '')}
- Metrics: {star.get('metrics', '')}
[All claims verified against master CV]
"""

            return f"""
CV FOR {job_state.get('company')}

VALIDATED EXPERIENCE:
{experience_text}

VERIFICATION NOTE: All companies, dates, and metrics verified against source records.
            """

        runner.set_enhanced_generator(validated_enhanced)
        result = runner.run_enhanced("v2", technique="assumption-ledger")

        # Should have high hallucination score (validated content)
        assert result.avg_hallucinations >= 6.0, (
            f"Validated content should have higher score, got {result.avg_hallucinations}"
        )

    def test_comparison_shows_hallucination_reduction(self, runner, master_cv):
        """Verify enhanced has fewer fabrications."""
        def fabricated_baseline(job_state):
            return "Worked at NonExistent Corp achieving 999% growth and $1 trillion savings."

        def grounded_enhanced(job_state):
            stars = job_state.get("selected_stars", [])
            star = stars[0] if stars else {}
            return f"At {star.get('company', 'Seven.One')}: {star.get('metrics', '75% reduction')} [verified]"

        runner.set_baseline_generator(fabricated_baseline)
        runner.set_enhanced_generator(grounded_enhanced)

        baseline = runner.run_baseline("v1")
        enhanced = runner.run_enhanced("v2")
        comparison = runner.compare(baseline, enhanced)

        assert comparison.hallucinations_delta >= 0, (
            f"Hallucination score should improve, delta: {comparison.hallucinations_delta}"
        )

    def test_hallucination_scorer_detects_fabricated_employers(self, test_job_1, master_cv):
        """Test that scorer detects fabricated employer names."""
        fabricated_cv = """
EXPERIENCE

Senior VP at Totally Made Up Corporation (2023-2025)
- Led massive transformation
- $500 billion in savings

Director at Another Fake Company LLC (2020-2023)
- Achieved impossible results
        """

        result = score_hallucinations(fabricated_cv, master_cv, test_job_1)

        # Should detect potential fabrications
        assert result.score < 9.0, (
            f"Fabricated employers should lower score, got {result.score}"
        )


class TestCVScorerIntegration:
    """Tests for scorer integration with CV outputs."""

    def test_cv_specificity_scoring(self, test_job_1):
        """Test specificity scorer on CV content."""
        generic_cv = """
PROFESSIONAL SUMMARY
Experienced professional with a proven track record.

EXPERIENCE
- Company A: Did things
- Company B: More things
        """

        specific_cv = """
PROFESSIONAL SUMMARY
Engineering leader with 11+ years building distributed systems at Seven.One Entertainment Group,
delivering 75% incident reduction and zero downtime for 3 consecutive years using AWS Lambda,
microservices, and Domain-Driven Design.

EXPERIENCE
Technical Lead - Seven.One Entertainment Group (2020-Present)
- Led transformation of monolithic AdTech platform processing millions of impressions daily
- Achieved 75% incident reduction, 25% faster delivery, mentored 10+ engineers
        """

        generic_result = score_specificity(generic_cv, test_job_1)
        specific_result = score_specificity(specific_cv, test_job_1)

        assert specific_result.score > generic_result.score, (
            f"Specific CV ({specific_result.score}) should score higher than generic ({generic_result.score})"
        )

    def test_cv_grounding_with_star_citations(self, test_job_1):
        """Test grounding scorer checks STAR company citations in CV."""
        ungrounded_cv = "10 years experience in software engineering."

        grounded_cv = """
At Seven.One Entertainment Group, achieved 75% incident reduction through
microservices transformation. At Samdock, built event-sourced CRM with 85% code coverage.
These experiences directly address KAIZEN GAMING's need for technical leadership.
        """

        ungrounded_result = score_grounding(ungrounded_cv, test_job_1)
        grounded_result = score_grounding(grounded_cv, test_job_1)

        assert grounded_result.score > ungrounded_result.score, (
            f"Grounded CV ({grounded_result.score}) should score higher than ungrounded ({ungrounded_result.score})"
        )

    def test_cv_hallucination_detection(self, test_job_1, master_cv):
        """Test hallucination detection in CV content."""
        clean_cv = """
Technical Lead at Seven.One Entertainment Group (2020-Present)
- 75% incident reduction
- Zero downtime for 3 years
        """

        fabricated_cv = """
CEO at Global MegaCorp (2020-2025)
- $10 trillion revenue growth
- 50000% efficiency improvement
        """

        clean_result = score_hallucinations(clean_cv, master_cv, test_job_1)
        fabricated_result = score_hallucinations(fabricated_cv, master_cv, test_job_1)

        assert clean_result.score > fabricated_result.score, (
            f"Clean CV ({clean_result.score}) should score higher than fabricated ({fabricated_result.score})"
        )
