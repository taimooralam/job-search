"""
Pipeline Performance Benchmarks (GAP-042).

Tests execution time of individual pipeline layers and full pipeline.
Run with: pytest tests/benchmarks/test_pipeline_benchmarks.py -v

Target Latencies (documented in __init__.py):
- These tests verify performance stays within acceptable bounds
- Failures indicate potential regressions
"""

import pytest
import time
from unittest.mock import MagicMock, patch
from typing import Dict, Any

# ===== TARGET LATENCIES (in seconds) =====
TARGETS = {
    "layer_1_4_jd_extractor": 3.0,
    "layer_2_pain_point_miner": 5.0,
    "layer_3_company_researcher": 8.0,  # With FireCrawl
    "layer_3_5_role_researcher": 3.0,
    "layer_4_opportunity_mapper": 3.0,
    "layer_5_people_mapper": 10.0,  # With FireCrawl
    "layer_6_cv_generator": 15.0,
    "layer_7_output_publisher": 2.0,
    "full_pipeline": 60.0,
    "pdf_generation": 5.0,
    "mongodb_query": 0.1,  # 100ms
}


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state() -> Dict[str, Any]:
    """Sample JobState for benchmark testing."""
    return {
        "job_id": "bench_test_123",
        "title": "Senior Engineering Manager",
        "company": "TechCorp",
        "job_description": """
        We are seeking a Senior Engineering Manager to lead a team of 8-12 engineers.

        Key Responsibilities:
        - Lead agile delivery of core platform features
        - Establish engineering processes (CI/CD, code review, testing)
        - Design system architecture for multi-tenant SaaS platform
        - Mentor junior engineers and build high-performing teams
        - Collaborate with product and design on roadmap
        - Drive technical decisions and architecture reviews
        - Manage hiring and team growth

        Requirements:
        - 7+ years software engineering experience
        - 3+ years engineering management experience
        - Experience with cloud platforms (AWS, GCP, Azure)
        - Strong system design and architecture skills
        - Track record of shipping products at scale
        """,
        "job_url": "https://example.com/jobs/123",
        "source": "benchmark",
        "candidate_profile": """
        PROFESSIONAL SUMMARY
        Engineering leader with 10+ years experience building high-performance teams.
        Track record of scaling teams from 5 to 30+ engineers while maintaining velocity.

        EXPERIENCE
        Engineering Manager - DataCorp (2019-Present)
        - Led team of 12 engineers delivering cloud-native platform
        - Reduced AWS costs by 75% ($3M annually)
        - Improved deployment frequency 300%

        Senior Software Engineer - TechStartup (2015-2019)
        - Built microservices architecture serving 10M daily requests
        - Implemented CI/CD pipeline reducing deploy time from 4hrs to 15min
        - Mentored 5 junior engineers

        EDUCATION
        MS Computer Science - MIT
        BS Computer Science - Stanford
        """,
        "pain_points": [
            "Team velocity has decreased 40% over past 6 months",
            "No standardized engineering processes causing quality issues",
            "System architecture cannot scale beyond current 10K users"
        ],
        "strategic_needs": [
            "Build engineering culture of quality and velocity",
            "Establish clear career progression framework"
        ],
        "risks_if_unfilled": [
            "Feature releases will continue to slip",
            "Top engineers may leave due to lack of growth opportunities"
        ],
        "success_metrics": [
            "Deployment frequency: 3x increase within 6 months",
            "Team growth: 8 to 15 engineers within 12 months",
            "Platform uptime: Maintain 99.9% SLA"
        ],
        "selected_stars": [
            {
                "company": "DataCorp",
                "role": "Engineering Manager",
                "period": "2019-Present",
                "situation": "Inherited team with declining velocity",
                "task": "Transform team culture and processes",
                "actions": "Implemented agile practices, CI/CD, code review",
                "results": "300% deployment frequency improvement",
                "metrics": "75% cost reduction ($3M saved)"
            }
        ],
        "company_research": {
            "summary": "TechCorp is a growing SaaS company in the B2B space",
            "signals": [
                {"type": "funding", "description": "Series B $50M raised", "date": "2024-06"},
                {"type": "growth", "description": "Team doubled in 12 months", "date": "2024-01"}
            ]
        },
        "role_research": {
            "summary": "Strategic hire to scale engineering organization",
            "business_impact": ["Enable product roadmap execution", "Support 10x user growth"],
            "why_now": "Current EM leaving, critical to maintain momentum"
        },
        "run_id": "bench_run_001",
        "errors": []
    }


@pytest.fixture
def mock_llm():
    """Mock LLM that returns quickly for benchmarking."""
    mock = MagicMock()
    mock.invoke.return_value = MagicMock(
        content="""
        **REASONING:**
        Analyzing candidate fit for role...

        **SCORE:** 85

        **RATIONALE:** At DataCorp, candidate demonstrated strong leadership by reducing AWS costs by 75%,
        saving $3M annually. This directly addresses the cost optimization pain point. Built and led team
        of 12 engineers with 300% deployment frequency improvement.
        """
    )
    return mock


# ===== BENCHMARK UTILITIES =====

class BenchmarkResult:
    """Container for benchmark results."""

    def __init__(self, name: str, duration: float, target: float):
        self.name = name
        self.duration = duration
        self.target = target
        self.passed = duration <= target
        self.margin_pct = ((target - duration) / target) * 100

    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} {self.name}: {self.duration:.3f}s (target: {self.target}s, margin: {self.margin_pct:+.1f}%)"


def run_benchmark(name: str, func, target: float, iterations: int = 1) -> BenchmarkResult:
    """Run a benchmark and return results."""
    durations = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = time.perf_counter() - start
        durations.append(elapsed)

    avg_duration = sum(durations) / len(durations)
    return BenchmarkResult(name, avg_duration, target)


# ===== BENCHMARK TESTS =====

class TestMockedLayerBenchmarks:
    """
    Benchmark tests with mocked external dependencies.

    These tests verify that layer logic completes quickly when
    external calls (LLM, FireCrawl) are mocked.

    Note: These are UNIT benchmarks - they test code efficiency,
    not real API latencies. For real latencies, use integration benchmarks.
    """

    @pytest.mark.benchmark
    def test_pain_point_miner_processing_time(self, sample_job_state, mock_llm):
        """Pain point extraction should complete within target (mocked)."""
        with patch('src.layer2.pain_point_miner.create_tracked_llm', return_value=mock_llm):
            from src.layer2.pain_point_miner import PainPointMiner

            def run_layer():
                miner = PainPointMiner()
                miner.extract_pain_points(sample_job_state)

            result = run_benchmark(
                "layer_2_pain_point_miner (mocked)",
                run_layer,
                target=1.0,  # Mocked should be fast
                iterations=3
            )

            print(f"\n{result}")
            # Mocked layer should be very fast
            assert result.duration < 1.0, f"Mocked layer took {result.duration:.3f}s (expected <1s)"

    @pytest.mark.benchmark
    def test_opportunity_mapper_processing_time(self, sample_job_state, mock_llm):
        """Opportunity mapping should complete within target (mocked)."""
        with patch('src.layer4.opportunity_mapper.create_tracked_llm', return_value=mock_llm):
            from src.layer4.opportunity_mapper import OpportunityMapper

            def run_layer():
                mapper = OpportunityMapper()
                mapper.map_opportunity(sample_job_state)

            result = run_benchmark(
                "layer_4_opportunity_mapper (mocked)",
                run_layer,
                target=1.0,  # Mocked should be fast
                iterations=3
            )

            print(f"\n{result}")
            assert result.duration < 1.0, f"Mocked layer took {result.duration:.3f}s (expected <1s)"


class TestValidationBenchmarks:
    """Benchmark validation helper functions."""

    @pytest.mark.benchmark
    def test_rationale_validation_performance(self, sample_job_state):
        """Validation should be fast (no LLM calls)."""
        from src.layer4.opportunity_mapper import OpportunityMapper

        mapper = OpportunityMapper.__new__(OpportunityMapper)  # Skip __init__

        rationale = """
        At DataCorp, candidate reduced AWS costs by 75% ($3M annually),
        directly addressing the cost optimization pain point. Built and led team
        of 12 engineers achieving 300% deployment frequency improvement. This
        demonstrates strong alignment with the scaling and process improvement
        strategic needs. However, lacks specific experience in multi-tenant SaaS.
        """

        def run_validation():
            mapper._validate_rationale(
                rationale,
                selected_stars=sample_job_state.get("selected_stars"),
                pain_points=sample_job_state.get("pain_points")
            )

        result = run_benchmark(
            "rationale_validation",
            run_validation,
            target=0.01,  # 10ms target
            iterations=100
        )

        print(f"\n{result}")
        assert result.duration < 0.01, f"Validation took {result.duration:.3f}s (expected <10ms)"


class TestHTMLGenerationBenchmarks:
    """Benchmark HTML/PDF generation."""

    @pytest.mark.benchmark
    def test_dossier_html_generation(self, sample_job_state):
        """Dossier HTML generation should be fast."""
        from src.api.pdf_export import DossierPDFExporter

        exporter = DossierPDFExporter()

        def run_generation():
            exporter.build_dossier_html(sample_job_state)

        result = run_benchmark(
            "dossier_html_generation",
            run_generation,
            target=0.1,  # 100ms target
            iterations=10
        )

        print(f"\n{result}")
        assert result.duration < 0.1, f"HTML generation took {result.duration:.3f}s (expected <100ms)"


class TestDatabaseBenchmarks:
    """Benchmark database operations."""

    @pytest.mark.benchmark
    @pytest.mark.skip(reason="Requires live MongoDB connection")
    def test_mongodb_query_latency(self):
        """MongoDB queries should complete within 100ms."""
        from pymongo import MongoClient
        import os

        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client.job_search
        collection = db["level-2"]

        def run_query():
            # Simple find_one query
            collection.find_one({"status": "new"})

        result = run_benchmark(
            "mongodb_find_one",
            run_query,
            target=0.1,  # 100ms
            iterations=10
        )

        print(f"\n{result}")
        assert result.passed, f"MongoDB query took {result.duration:.3f}s (expected <100ms)"


# ===== BENCHMARK SUMMARY =====

def print_benchmark_summary(results: list):
    """Print summary of all benchmark results."""
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    for result in results:
        print(result)

    print("-" * 60)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    print("=" * 60)


# ===== TARGET LATENCIES DOCUMENTATION =====

def test_target_latencies_documented():
    """Verify all target latencies are documented."""
    expected_targets = [
        "layer_1_4_jd_extractor",
        "layer_2_pain_point_miner",
        "layer_3_company_researcher",
        "layer_3_5_role_researcher",
        "layer_4_opportunity_mapper",
        "layer_5_people_mapper",
        "layer_6_cv_generator",
        "layer_7_output_publisher",
        "full_pipeline",
        "pdf_generation",
        "mongodb_query",
    ]

    for target in expected_targets:
        assert target in TARGETS, f"Missing target latency for: {target}"
        assert TARGETS[target] > 0, f"Invalid target latency for {target}: {TARGETS[target]}"

    print("\n" + "=" * 60)
    print("TARGET LATENCIES (p95)")
    print("=" * 60)
    for name, target in sorted(TARGETS.items()):
        print(f"  {name}: {target}s")
    print("=" * 60)
