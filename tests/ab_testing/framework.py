"""
A/B Testing Framework for Prompt Optimization.

This module provides the ABTestRunner class for running and comparing
prompt variants across different layers of the job intelligence pipeline.

Usage:
    runner = ABTestRunner(layer="layer4", issue="weak-grounding", test_jobs=[...])
    baseline = runner.run_baseline()
    enhanced = runner.run_enhanced(technique="anti-hallucination-guardrails")
    comparison = runner.compare(baseline, enhanced)
    runner.generate_analysis_report(comparison)
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path

from .scorers import (
    score_specificity,
    score_grounding,
    score_hallucinations,
    calculate_combined_score,
    ScoreResult,
)


@dataclass
class OutputResult:
    """Result from running a prompt on a single job."""
    job_id: str
    output_text: str
    specificity: ScoreResult
    grounding: ScoreResult
    hallucinations: ScoreResult
    combined_score: float
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ABTestResult:
    """Aggregated results from running a prompt variant."""
    version: str
    technique: Optional[str]
    timestamp: str
    outputs: List[OutputResult]
    avg_specificity: float
    avg_grounding: float
    avg_hallucinations: float
    avg_combined: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "technique": self.technique,
            "timestamp": self.timestamp,
            "outputs": [
                {
                    "job_id": o.job_id,
                    "output_text": o.output_text[:500] + "..." if len(o.output_text) > 500 else o.output_text,
                    "scores": {
                        "specificity": o.specificity.score,
                        "grounding": o.grounding.score,
                        "hallucinations": o.hallucinations.score,
                        "combined": o.combined_score,
                    },
                    "feedback": {
                        "specificity": o.specificity.feedback,
                        "grounding": o.grounding.feedback,
                        "hallucinations": o.hallucinations.feedback,
                    },
                }
                for o in self.outputs
            ],
            "averages": {
                "specificity": self.avg_specificity,
                "grounding": self.avg_grounding,
                "hallucinations": self.avg_hallucinations,
                "combined": self.avg_combined,
            },
            "metadata": self.metadata,
        }


@dataclass
class Comparison:
    """Comparison between baseline and enhanced prompt variants."""
    baseline_version: str
    enhanced_version: str
    specificity_delta: float
    grounding_delta: float
    hallucinations_delta: float
    combined_delta: float
    improvement_percentage: float
    meets_targets: Dict[str, bool]
    per_job_deltas: List[Dict[str, Any]]
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "baseline_version": self.baseline_version,
            "enhanced_version": self.enhanced_version,
            "deltas": {
                "specificity": self.specificity_delta,
                "grounding": self.grounding_delta,
                "hallucinations": self.hallucinations_delta,
                "combined": self.combined_delta,
            },
            "improvement_percentage": self.improvement_percentage,
            "meets_targets": self.meets_targets,
            "per_job_deltas": self.per_job_deltas,
            "recommendation": self.recommendation,
        }


class ABTestRunner:
    """
    Framework for running and comparing prompt A/B tests.

    Supports Layer 4 (Opportunity Mapper), Layer 6a (Cover Letter),
    and Layer 6b (CV Generator).
    """

    # Score targets for each metric (must meet or exceed)
    TARGETS = {
        "specificity": 7.0,
        "grounding": 8.0,
        "hallucinations": 9.0,  # Higher = fewer hallucinations
        "combined": 7.5,
    }

    def __init__(
        self,
        layer: str,
        issue: str,
        test_jobs: List[Dict[str, Any]],
        master_cv: str = "",
        reports_dir: str = "reports/prompt-ab",
    ):
        """
        Initialize ABTestRunner.

        Args:
            layer: Layer identifier (layer4, layer6a, layer6b)
            issue: Issue identifier (e.g., weak-grounding, no-cot)
            test_jobs: List of test job state dictionaries
            master_cv: Master CV text for hallucination checking
            reports_dir: Directory for saving results
        """
        self.layer = layer
        self.issue = issue
        self.test_jobs = test_jobs
        self.master_cv = master_cv
        self.reports_dir = Path(reports_dir) / layer / issue

        # Ensure reports directory exists
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Prompt generators (to be set based on layer)
        self._baseline_generator: Optional[Callable] = None
        self._enhanced_generator: Optional[Callable] = None

    def set_baseline_generator(self, generator: Callable[[Dict], str]) -> None:
        """
        Set the baseline prompt generator function.

        Args:
            generator: Function that takes job state and returns output text
        """
        self._baseline_generator = generator

    def set_enhanced_generator(self, generator: Callable[[Dict], str]) -> None:
        """
        Set the enhanced prompt generator function.

        Args:
            generator: Function that takes job state and returns output text
        """
        self._enhanced_generator = generator

    def _score_output(self, output_text: str, job_state: Dict[str, Any]) -> OutputResult:
        """
        Score a single output against all metrics.

        Args:
            output_text: The generated output text
            job_state: The job state used for generation

        Returns:
            OutputResult with all scores
        """
        specificity = score_specificity(output_text, job_state)
        grounding = score_grounding(output_text, job_state)
        hallucinations = score_hallucinations(output_text, self.master_cv, job_state)
        combined = calculate_combined_score(specificity, grounding, hallucinations)

        return OutputResult(
            job_id=job_state.get("job_id", "unknown"),
            output_text=output_text,
            specificity=specificity,
            grounding=grounding,
            hallucinations=hallucinations,
            combined_score=combined,
        )

    def run_baseline(self, version: str = "v1") -> ABTestResult:
        """
        Run baseline (status quo) prompt with all test jobs.

        Args:
            version: Version identifier for this run

        Returns:
            ABTestResult with all outputs and scores
        """
        if self._baseline_generator is None:
            raise ValueError("Baseline generator not set. Call set_baseline_generator() first.")

        outputs = []
        for job in self.test_jobs:
            output_text = self._baseline_generator(job)
            result = self._score_output(output_text, job)
            outputs.append(result)

        # Calculate averages
        avg_spec = sum(o.specificity.score for o in outputs) / len(outputs)
        avg_ground = sum(o.grounding.score for o in outputs) / len(outputs)
        avg_halluc = sum(o.hallucinations.score for o in outputs) / len(outputs)
        avg_combined = sum(o.combined_score for o in outputs) / len(outputs)

        result = ABTestResult(
            version=version,
            technique=None,
            timestamp=datetime.now().isoformat(),
            outputs=outputs,
            avg_specificity=round(avg_spec, 2),
            avg_grounding=round(avg_ground, 2),
            avg_hallucinations=round(avg_halluc, 2),
            avg_combined=round(avg_combined, 2),
            metadata={"layer": self.layer, "issue": self.issue, "type": "baseline"},
        )

        # Auto-save
        self.save_results(result, version)
        return result

    def run_enhanced(self, version: str = "v2", technique: Optional[str] = None) -> ABTestResult:
        """
        Run enhanced prompt with all test jobs.

        Args:
            version: Version identifier for this run
            technique: Name of the technique applied (from thoughts/*.md)

        Returns:
            ABTestResult with all outputs and scores
        """
        if self._enhanced_generator is None:
            raise ValueError("Enhanced generator not set. Call set_enhanced_generator() first.")

        outputs = []
        for job in self.test_jobs:
            output_text = self._enhanced_generator(job)
            result = self._score_output(output_text, job)
            outputs.append(result)

        # Calculate averages
        avg_spec = sum(o.specificity.score for o in outputs) / len(outputs)
        avg_ground = sum(o.grounding.score for o in outputs) / len(outputs)
        avg_halluc = sum(o.hallucinations.score for o in outputs) / len(outputs)
        avg_combined = sum(o.combined_score for o in outputs) / len(outputs)

        result = ABTestResult(
            version=version,
            technique=technique,
            timestamp=datetime.now().isoformat(),
            outputs=outputs,
            avg_specificity=round(avg_spec, 2),
            avg_grounding=round(avg_ground, 2),
            avg_hallucinations=round(avg_halluc, 2),
            avg_combined=round(avg_combined, 2),
            metadata={
                "layer": self.layer,
                "issue": self.issue,
                "type": "enhanced",
                "technique": technique,
            },
        )

        # Auto-save
        self.save_results(result, version)
        return result

    def compare(self, baseline: ABTestResult, enhanced: ABTestResult) -> Comparison:
        """
        Compare baseline vs enhanced results.

        Args:
            baseline: Baseline test results
            enhanced: Enhanced test results

        Returns:
            Comparison with deltas and recommendation
        """
        # Calculate deltas (positive = improvement)
        spec_delta = enhanced.avg_specificity - baseline.avg_specificity
        ground_delta = enhanced.avg_grounding - baseline.avg_grounding
        halluc_delta = enhanced.avg_hallucinations - baseline.avg_hallucinations
        combined_delta = enhanced.avg_combined - baseline.avg_combined

        # Calculate improvement percentage
        if baseline.avg_combined > 0:
            improvement_pct = (combined_delta / baseline.avg_combined) * 100
        else:
            improvement_pct = 0.0

        # Check if targets are met
        meets_targets = {
            "specificity": enhanced.avg_specificity >= self.TARGETS["specificity"],
            "grounding": enhanced.avg_grounding >= self.TARGETS["grounding"],
            "hallucinations": enhanced.avg_hallucinations >= self.TARGETS["hallucinations"],
            "combined": enhanced.avg_combined >= self.TARGETS["combined"],
        }

        # Per-job deltas
        per_job_deltas = []
        for base_out, enh_out in zip(baseline.outputs, enhanced.outputs):
            per_job_deltas.append({
                "job_id": base_out.job_id,
                "specificity_delta": round(enh_out.specificity.score - base_out.specificity.score, 2),
                "grounding_delta": round(enh_out.grounding.score - base_out.grounding.score, 2),
                "hallucinations_delta": round(enh_out.hallucinations.score - base_out.hallucinations.score, 2),
                "combined_delta": round(enh_out.combined_score - base_out.combined_score, 2),
            })

        # Generate recommendation
        all_targets_met = all(meets_targets.values())
        has_improvement = combined_delta > 0
        has_regression = any(d < -0.5 for d in [spec_delta, ground_delta, halluc_delta])

        if all_targets_met and has_improvement and not has_regression:
            recommendation = "ADOPT: All targets met with improvement and no regressions"
        elif has_improvement and not has_regression:
            missing = [k for k, v in meets_targets.items() if not v]
            recommendation = f"ITERATE: Improvement seen but targets not met for: {', '.join(missing)}"
        elif has_regression:
            regressed = []
            if spec_delta < -0.5:
                regressed.append("specificity")
            if ground_delta < -0.5:
                regressed.append("grounding")
            if halluc_delta < -0.5:
                regressed.append("hallucinations")
            recommendation = f"ROLLBACK: Regression detected in: {', '.join(regressed)}"
        else:
            recommendation = "NO CHANGE: No significant improvement or regression"

        comparison = Comparison(
            baseline_version=baseline.version,
            enhanced_version=enhanced.version,
            specificity_delta=round(spec_delta, 2),
            grounding_delta=round(ground_delta, 2),
            hallucinations_delta=round(halluc_delta, 2),
            combined_delta=round(combined_delta, 2),
            improvement_percentage=round(improvement_pct, 1),
            meets_targets=meets_targets,
            per_job_deltas=per_job_deltas,
            recommendation=recommendation,
        )

        # Save comparison
        self._save_comparison(comparison)
        return comparison

    def save_results(self, results: ABTestResult, version: str) -> Path:
        """
        Save test results to JSON file.

        Args:
            results: ABTestResult to save
            version: Version identifier

        Returns:
            Path to saved file
        """
        result_type = results.metadata.get("type", "unknown")
        filename = f"{result_type}-{version}.json"
        filepath = self.reports_dir / filename

        with open(filepath, "w") as f:
            json.dump(results.to_dict(), f, indent=2)

        return filepath

    def _save_comparison(self, comparison: Comparison) -> Path:
        """Save comparison to JSON file."""
        filename = f"comparison-{comparison.baseline_version}-vs-{comparison.enhanced_version}.json"
        filepath = self.reports_dir / filename

        with open(filepath, "w") as f:
            json.dump(comparison.to_dict(), f, indent=2)

        return filepath

    def generate_analysis_report(self, comparison: Comparison) -> str:
        """
        Generate markdown analysis report.

        Args:
            comparison: Comparison results

        Returns:
            Markdown report string
        """
        report = f"""## A/B Analysis: {self.layer} - {self.issue}

### Baseline ({comparison.baseline_version})
- **Scores**: Spec={comparison.specificity_delta + comparison.specificity_delta:.1f}, Ground={comparison.grounding_delta + comparison.grounding_delta:.1f}, Halluc={comparison.hallucinations_delta + comparison.hallucinations_delta:.1f}

### Enhanced ({comparison.enhanced_version})
- **Technique Applied**: {comparison.enhanced_version}
- **Improvement**: {comparison.improvement_percentage:+.1f}%

### Comparison
| Metric | Baseline | Enhanced | Delta | Target | Status |
|--------|----------|----------|-------|--------|--------|
| Specificity | - | - | {comparison.specificity_delta:+.2f} | {self.TARGETS['specificity']} | {'OK' if comparison.meets_targets['specificity'] else 'X'} |
| Grounding | - | - | {comparison.grounding_delta:+.2f} | {self.TARGETS['grounding']} | {'OK' if comparison.meets_targets['grounding'] else 'X'} |
| Hallucinations | - | - | {comparison.hallucinations_delta:+.2f} | {self.TARGETS['hallucinations']} | {'OK' if comparison.meets_targets['hallucinations'] else 'X'} |
| Combined | - | - | {comparison.combined_delta:+.2f} | {self.TARGETS['combined']} | {'OK' if comparison.meets_targets['combined'] else 'X'} |

### Verdict
**{comparison.recommendation}**

### Per-Job Analysis
"""
        for delta in comparison.per_job_deltas:
            report += f"- Job {delta['job_id']}: Combined {delta['combined_delta']:+.2f}\n"

        # Save report
        report_path = self.reports_dir / "analysis.md"
        with open(report_path, "w") as f:
            f.write(report)

        return report


# Helper function for creating mock generators (for testing)
def create_mock_generator(output_template: str) -> Callable[[Dict], str]:
    """
    Create a mock generator for testing.

    Args:
        output_template: Template string with {placeholders}

    Returns:
        Generator function
    """
    def generator(job_state: Dict) -> str:
        return output_template.format(
            company=job_state.get("company", "Company"),
            title=job_state.get("title", "Role"),
            **{k: v for k, v in job_state.items() if isinstance(v, str)}
        )
    return generator
