"""
Phase 5: Integration A/B Testing with Actual LLM Calls

This script runs the enhanced prompts against real LLM endpoints and measures
actual performance improvements using the A/B testing scoring framework.

Usage:
    source .venv/bin/activate
    python scripts/run_integration_ab_tests.py

Output:
    - Console output with scores for each layer
    - Final analysis report saved to reports/prompt-ab/integration-final.md
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.ab_testing.scorers import (
    score_specificity,
    score_grounding,
    score_hallucinations,
    calculate_combined_score,
    ScoreResult,
)


@dataclass
class IntegrationTestResult:
    """Result from running an integration test."""
    layer: str
    job_id: str
    output_text: str
    specificity: ScoreResult
    grounding: ScoreResult
    hallucinations: ScoreResult
    combined: float
    execution_time_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class LayerSummary:
    """Summary of results for a layer."""
    layer: str
    tests_run: int
    avg_specificity: float
    avg_grounding: float
    avg_hallucinations: float
    avg_combined: float
    meets_targets: Dict[str, bool] = field(default_factory=dict)
    results: List[IntegrationTestResult] = field(default_factory=list)


# Targets from QUICK_START.md
TARGETS = {
    "specificity": 7.0,
    "grounding": 8.0,
    "hallucinations": 9.0,
    "combined": 7.5,
}


def load_fixtures() -> Dict[str, Any]:
    """Load test fixtures."""
    fixtures_dir = Path(__file__).parent.parent / "tests" / "ab_testing" / "fixtures"

    # Load test job 1 (real from MongoDB)
    test_job_path = fixtures_dir / "test_job_1.json"
    with open(test_job_path) as f:
        test_job_1 = json.load(f)

    # Load master CV (MongoDB first, then file fallback)
    master_cv = ""

    # Try MongoDB first if enabled
    try:
        from src.common.config import Config
        if Config.USE_MASTER_CV_MONGODB:
            from src.layer6_v2.cv_loader import CVLoader
            loader = CVLoader(use_mongodb=True)
            candidate = loader.load()
            if candidate:
                content = "\n\n".join(
                    role.raw_content for role in candidate.roles if role.raw_content
                )
                if content:
                    master_cv = content
    except Exception:
        pass

    # File fallback if MongoDB didn't work
    if not master_cv:
        master_cv_path = Path(__file__).parent.parent / "master-cv.md"
        if master_cv_path.exists():
            master_cv = master_cv_path.read_text()

    # Try structured roles directory as last resort
    if not master_cv:
        roles_dir = Path(__file__).parent.parent / "data" / "master-cv" / "roles"
        if roles_dir.exists():
            texts = [f.read_text() for f in sorted(roles_dir.glob("*.md"))]
            if texts:
                master_cv = "\n\n".join(texts)

    return {
        "test_job_1": test_job_1,
        "master_cv": master_cv,
    }


def run_layer4_integration(job_state: Dict[str, Any], master_cv: str) -> IntegrationTestResult:
    """Run Layer 4 integration test with actual LLM call."""
    import time
    from src.layer4.opportunity_mapper import opportunity_mapper_node

    start_time = time.time()

    try:
        # Run the opportunity mapper node
        result = opportunity_mapper_node(job_state)
        execution_time = (time.time() - start_time) * 1000

        # Extract output text (fit_rationale)
        output_text = result.get("fit_rationale", "")
        fit_score = result.get("fit_score", 0)
        fit_category = result.get("fit_category", "unknown")

        # Combine into readable output
        full_output = f"Score: {fit_score}/100\nCategory: {fit_category}\n\nRationale:\n{output_text}"

        # Score the output
        specificity = score_specificity(output_text, job_state)
        grounding = score_grounding(output_text, job_state)
        hallucinations = score_hallucinations(output_text, master_cv, job_state)
        combined = calculate_combined_score(specificity, grounding, hallucinations)

        return IntegrationTestResult(
            layer="layer4",
            job_id=job_state.get("job_id", "unknown"),
            output_text=full_output,
            specificity=specificity,
            grounding=grounding,
            hallucinations=hallucinations,
            combined=combined,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        return IntegrationTestResult(
            layer="layer4",
            job_id=job_state.get("job_id", "unknown"),
            output_text="",
            specificity=ScoreResult(score=0, details={}, feedback="Error"),
            grounding=ScoreResult(score=0, details={}, feedback="Error"),
            hallucinations=ScoreResult(score=0, details={}, feedback="Error"),
            combined=0,
            error=str(e),
        )


def run_layer6a_integration(job_state: Dict[str, Any], master_cv: str) -> IntegrationTestResult:
    """Run Layer 6a integration test with actual LLM call."""
    import time
    from src.layer6.cover_letter_generator import CoverLetterGenerator

    start_time = time.time()

    try:
        # Add fit score/rationale if missing (from Layer 4)
        if not job_state.get("fit_rationale"):
            job_state["fit_score"] = 85
            job_state["fit_rationale"] = "Strong fit based on leadership experience."

        # Create generator and run (correct method name)
        generator = CoverLetterGenerator()
        cover_letter = generator.generate_cover_letter(job_state)
        execution_time = (time.time() - start_time) * 1000

        # Score the output
        specificity = score_specificity(cover_letter, job_state)
        grounding = score_grounding(cover_letter, job_state)
        hallucinations = score_hallucinations(cover_letter, master_cv, job_state)
        combined = calculate_combined_score(specificity, grounding, hallucinations)

        return IntegrationTestResult(
            layer="layer6a",
            job_id=job_state.get("job_id", "unknown"),
            output_text=cover_letter,
            specificity=specificity,
            grounding=grounding,
            hallucinations=hallucinations,
            combined=combined,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        return IntegrationTestResult(
            layer="layer6a",
            job_id=job_state.get("job_id", "unknown"),
            output_text="",
            specificity=ScoreResult(score=0, details={}, feedback="Error"),
            grounding=ScoreResult(score=0, details={}, feedback="Error"),
            hallucinations=ScoreResult(score=0, details={}, feedback="Error"),
            combined=0,
            error=str(e),
        )


def run_layer6b_integration(job_state: Dict[str, Any], master_cv: str) -> IntegrationTestResult:
    """Run Layer 6b integration test with actual LLM call."""
    import time
    from src.layer6.cv_generator import CVGenerator

    start_time = time.time()

    try:
        # Add required fields if missing
        if not job_state.get("fit_rationale"):
            job_state["fit_score"] = 85
            job_state["fit_rationale"] = "Strong fit based on leadership experience."

        # Create generator
        generator = CVGenerator()

        # Run competency mix analysis (the enhanced part)
        competency_result = generator._analyze_competency_mix(
            job_state.get("job_description", ""),
            job_state.get("title", ""),
        )
        execution_time = (time.time() - start_time) * 1000

        # Handle Pydantic model - convert to dict if needed
        if hasattr(competency_result, "model_dump"):
            competency_dict = competency_result.model_dump()
        elif hasattr(competency_result, "dict"):
            competency_dict = competency_result.dict()
        else:
            competency_dict = {"result": str(competency_result)}

        # Format as readable output
        output_text = f"Competency Mix Analysis:\n{json.dumps(competency_dict, indent=2)}"

        # For scoring, we'll use the reasoning field
        reasoning = competency_dict.get("reasoning", "") if isinstance(competency_dict, dict) else str(competency_result)

        # Score the output
        specificity = score_specificity(reasoning, job_state)
        grounding = score_grounding(reasoning, job_state)
        hallucinations = score_hallucinations(reasoning, master_cv, job_state)
        combined = calculate_combined_score(specificity, grounding, hallucinations)

        return IntegrationTestResult(
            layer="layer6b",
            job_id=job_state.get("job_id", "unknown"),
            output_text=output_text,
            specificity=specificity,
            grounding=grounding,
            hallucinations=hallucinations,
            combined=combined,
            execution_time_ms=execution_time,
        )

    except Exception as e:
        return IntegrationTestResult(
            layer="layer6b",
            job_id=job_state.get("job_id", "unknown"),
            output_text="",
            specificity=ScoreResult(score=0, details={}, feedback="Error"),
            grounding=ScoreResult(score=0, details={}, feedback="Error"),
            hallucinations=ScoreResult(score=0, details={}, feedback="Error"),
            combined=0,
            error=str(e),
        )


def summarize_layer_results(results: List[IntegrationTestResult], layer: str) -> LayerSummary:
    """Summarize results for a layer."""
    if not results:
        return LayerSummary(
            layer=layer,
            tests_run=0,
            avg_specificity=0,
            avg_grounding=0,
            avg_hallucinations=0,
            avg_combined=0,
        )

    valid_results = [r for r in results if not r.error]

    if not valid_results:
        return LayerSummary(
            layer=layer,
            tests_run=len(results),
            avg_specificity=0,
            avg_grounding=0,
            avg_hallucinations=0,
            avg_combined=0,
            results=results,
        )

    avg_spec = sum(r.specificity.score for r in valid_results) / len(valid_results)
    avg_ground = sum(r.grounding.score for r in valid_results) / len(valid_results)
    avg_halluc = sum(r.hallucinations.score for r in valid_results) / len(valid_results)
    avg_combined = sum(r.combined for r in valid_results) / len(valid_results)

    meets_targets = {
        "specificity": avg_spec >= TARGETS["specificity"],
        "grounding": avg_ground >= TARGETS["grounding"],
        "hallucinations": avg_halluc >= TARGETS["hallucinations"],
        "combined": avg_combined >= TARGETS["combined"],
    }

    return LayerSummary(
        layer=layer,
        tests_run=len(results),
        avg_specificity=round(avg_spec, 2),
        avg_grounding=round(avg_ground, 2),
        avg_hallucinations=round(avg_halluc, 2),
        avg_combined=round(avg_combined, 2),
        meets_targets=meets_targets,
        results=results,
    )


def generate_final_report(summaries: List[LayerSummary]) -> str:
    """Generate final markdown report."""
    report = """# Phase 5: Integration Testing - Final Analysis

**Date**: {date}
**Status**: COMPLETE

---

## Executive Summary

This report presents the results of running the enhanced prompts against actual LLM
endpoints using the A/B testing scoring framework.

### Overall Results

| Layer | Specificity | Grounding | Hallucinations | Combined | Status |
|-------|-------------|-----------|----------------|----------|--------|
""".format(date=datetime.now().strftime("%Y-%m-%d %H:%M"))

    all_targets_met = True
    for summary in summaries:
        status = "PASS" if all(summary.meets_targets.values()) else "NEEDS WORK"
        if not all(summary.meets_targets.values()):
            all_targets_met = False

        report += f"| {summary.layer} | {summary.avg_specificity:.1f} | {summary.avg_grounding:.1f} | {summary.avg_hallucinations:.1f} | {summary.avg_combined:.1f} | {status} |\n"

    report += f"""
### Target Thresholds

| Metric | Target | Rationale |
|--------|--------|-----------|
| Specificity | {TARGETS['specificity']}+ | Less generic, more concrete |
| Grounding | {TARGETS['grounding']}+ | Evidence-based claims |
| Hallucinations | {TARGETS['hallucinations']}+ | No fabricated info |
| Combined | {TARGETS['combined']}+ | Overall quality |

---

## Detailed Results by Layer

"""

    for summary in summaries:
        report += f"""### {summary.layer.upper()}

**Tests Run**: {summary.tests_run}

**Scores**:
- Specificity: {summary.avg_specificity:.1f}/10 {'✅' if summary.meets_targets.get('specificity') else '❌'} (target: {TARGETS['specificity']})
- Grounding: {summary.avg_grounding:.1f}/10 {'✅' if summary.meets_targets.get('grounding') else '❌'} (target: {TARGETS['grounding']})
- Hallucinations: {summary.avg_hallucinations:.1f}/10 {'✅' if summary.meets_targets.get('hallucinations') else '❌'} (target: {TARGETS['hallucinations']})
- Combined: {summary.avg_combined:.1f}/10 {'✅' if summary.meets_targets.get('combined') else '❌'} (target: {TARGETS['combined']})

"""

        # Add individual test results
        for result in summary.results:
            if result.error:
                report += f"""**Job {result.job_id}**: ERROR - {result.error}

"""
            else:
                report += f"""**Job {result.job_id}**:
- Execution Time: {result.execution_time_ms:.0f}ms
- Specificity: {result.specificity.score:.1f} ({result.specificity.feedback})
- Grounding: {result.grounding.score:.1f} ({result.grounding.feedback})
- Hallucinations: {result.hallucinations.score:.1f} ({result.hallucinations.feedback})

<details>
<summary>Output Preview (first 500 chars)</summary>

```
{result.output_text[:500]}...
```

</details>

"""

    report += """---

## Recommendations

"""

    if all_targets_met:
        report += """### Ready for Production Rollout

All layers meet or exceed target thresholds. The enhanced prompts are ready for
production deployment.

**Next Steps**:
1. Merge `prompt-optimisation` branch to `main`
2. Deploy to production environment
3. Monitor real-world performance metrics
4. Set up A/B testing in production for continuous improvement
"""
    else:
        report += """### Iteration Required

Some layers do not meet all target thresholds. Review the detailed results above
and iterate on the prompts that need improvement.

**Layers Requiring Attention**:
"""
        for summary in summaries:
            failed = [k for k, v in summary.meets_targets.items() if not v]
            if failed:
                report += f"- **{summary.layer}**: Improve {', '.join(failed)}\n"

        report += """
**Iteration Strategy**:
1. Focus on layers with lowest scores first
2. Review prompt techniques from `thoughts/*.md`
3. Re-run integration tests after changes
4. Maximum 3 iterations per layer
"""

    report += f"""
---

*Generated by Phase 5 Integration Testing*
*Report created: {datetime.now().isoformat()}*
"""

    return report


def main():
    """Run Phase 5 integration tests."""
    print("=" * 60)
    print("Phase 5: Integration A/B Testing with Actual LLM Calls")
    print("=" * 60)
    print()

    # Load fixtures
    print("Loading test fixtures...")
    fixtures = load_fixtures()
    test_job = fixtures["test_job_1"]
    master_cv = fixtures["master_cv"]
    print(f"  - Test job: {test_job.get('title')} at {test_job.get('company')}")
    print(f"  - Master CV: {len(master_cv)} characters")
    print()

    summaries = []

    # Layer 4: Opportunity Mapper
    print("-" * 60)
    print("Running Layer 4 (Opportunity Mapper) Integration Test...")
    print("-" * 60)
    layer4_result = run_layer4_integration(test_job.copy(), master_cv)

    if layer4_result.error:
        print(f"  ERROR: {layer4_result.error}")
    else:
        print(f"  Execution Time: {layer4_result.execution_time_ms:.0f}ms")
        print(f"  Specificity: {layer4_result.specificity.score:.1f}/10")
        print(f"  Grounding: {layer4_result.grounding.score:.1f}/10")
        print(f"  Hallucinations: {layer4_result.hallucinations.score:.1f}/10")
        print(f"  Combined: {layer4_result.combined:.1f}/10")

    layer4_summary = summarize_layer_results([layer4_result], "layer4")
    summaries.append(layer4_summary)
    print()

    # Update job_state with Layer 4 results for Layer 6
    if not layer4_result.error:
        test_job["fit_score"] = 85
        test_job["fit_rationale"] = layer4_result.output_text

    # Layer 6a: Cover Letter Generator
    print("-" * 60)
    print("Running Layer 6a (Cover Letter Generator) Integration Test...")
    print("-" * 60)
    layer6a_result = run_layer6a_integration(test_job.copy(), master_cv)

    if layer6a_result.error:
        print(f"  ERROR: {layer6a_result.error}")
    else:
        print(f"  Execution Time: {layer6a_result.execution_time_ms:.0f}ms")
        print(f"  Specificity: {layer6a_result.specificity.score:.1f}/10")
        print(f"  Grounding: {layer6a_result.grounding.score:.1f}/10")
        print(f"  Hallucinations: {layer6a_result.hallucinations.score:.1f}/10")
        print(f"  Combined: {layer6a_result.combined:.1f}/10")

    layer6a_summary = summarize_layer_results([layer6a_result], "layer6a")
    summaries.append(layer6a_summary)
    print()

    # Layer 6b: CV Generator (Competency Mix Analysis)
    print("-" * 60)
    print("Running Layer 6b (CV Generator - Competency Mix) Integration Test...")
    print("-" * 60)
    layer6b_result = run_layer6b_integration(test_job.copy(), master_cv)

    if layer6b_result.error:
        print(f"  ERROR: {layer6b_result.error}")
    else:
        print(f"  Execution Time: {layer6b_result.execution_time_ms:.0f}ms")
        print(f"  Specificity: {layer6b_result.specificity.score:.1f}/10")
        print(f"  Grounding: {layer6b_result.grounding.score:.1f}/10")
        print(f"  Hallucinations: {layer6b_result.hallucinations.score:.1f}/10")
        print(f"  Combined: {layer6b_result.combined:.1f}/10")

    layer6b_summary = summarize_layer_results([layer6b_result], "layer6b")
    summaries.append(layer6b_summary)
    print()

    # Generate final report
    print("=" * 60)
    print("Generating Final Analysis Report...")
    print("=" * 60)

    report = generate_final_report(summaries)

    # Save report
    reports_dir = Path(__file__).parent.parent / "reports" / "prompt-ab"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "integration-final.md"

    with open(report_path, "w") as f:
        f.write(report)

    print(f"Report saved to: {report_path}")
    print()

    # Print summary
    print("=" * 60)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 60)
    print()
    print(f"{'Layer':<12} {'Spec':>8} {'Ground':>8} {'Halluc':>8} {'Combined':>10} {'Status':>10}")
    print("-" * 60)

    all_pass = True
    for summary in summaries:
        status = "PASS" if all(summary.meets_targets.values()) else "NEEDS WORK"
        if not all(summary.meets_targets.values()):
            all_pass = False
        print(f"{summary.layer:<12} {summary.avg_specificity:>8.1f} {summary.avg_grounding:>8.1f} {summary.avg_hallucinations:>8.1f} {summary.avg_combined:>10.1f} {status:>10}")

    print("-" * 60)
    print(f"Targets:     {TARGETS['specificity']:>8.1f} {TARGETS['grounding']:>8.1f} {TARGETS['hallucinations']:>8.1f} {TARGETS['combined']:>10.1f}")
    print()

    if all_pass:
        print("ALL LAYERS PASS INTEGRATION TESTING")
        print("Ready for production rollout!")
    else:
        print("SOME LAYERS NEED ITERATION")
        print("See report for details.")

    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())
