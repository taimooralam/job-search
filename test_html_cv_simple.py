#!/usr/bin/env python3
"""
Simple test script to verify HTML CV generation without LLM calls.
Tests the HTML building logic directly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.layer6.html_cv_generator import HTMLCVGenerator
from src.common.state import JobState
from pydantic import BaseModel


class MockCompetencyMix(BaseModel):
    """Mock competency mix to bypass LLM calls."""
    technical: float = 0.6
    leadership: float = 0.3
    domain: float = 0.1


def test_html_cv_building():
    """Test HTML CV building logic directly without LLM calls."""

    # Create mock state
    state = JobState(
        job_id="test-12345",
        title="Senior Software Engineer",
        company="TechCorp Inc",
        job_description="Python development, distributed systems, cloud platforms",
        candidate_profile="""
        # Candidate Profile

        **Name:** John Doe
        **Email:** john.doe@example.com | **Phone:** +1-555-0123
        **Location:** San Francisco, CA

        ## Professional Summary
        Senior Software Engineer with 8+ years of experience.

        ## Education
        **B.S. Computer Science** - Stanford University (2015)
        **M.S. Computer Science** - MIT (2017)

        AWS Certified Solutions Architect
        """,
        fit_score=0.85,
        level=2
    )

    # Mock selected STARs (already scored and ranked)
    selected_stars = [
        {
            "id": "star-001",
            "role": "Lead Software Engineer",
            "company": "Previous Corp",
            "period": "2020-2024",
            "situation": "Legacy monolithic system causing scaling issues",
            "task": "Redesign architecture to support 10x traffic growth",
            "action": "Led team of 5 engineers to migrate to microservices architecture on AWS",
            "result": "Reduced latency by 60%, increased throughput by 10x, saved $2M in infrastructure costs",
            "competencies": ["system_design", "leadership", "cloud_architecture"]
        },
        {
            "id": "star-002",
            "role": "Software Engineer",
            "company": "StartupCo",
            "period": "2018-2020",
            "situation": "Manual deployment process causing frequent production incidents",
            "task": "Implement CI/CD pipeline and automated testing",
            "action": "Built Jenkins pipeline with automated tests, containerized all services with Docker",
            "result": "Deployment time reduced from 4 hours to 15 minutes, incidents decreased by 75%",
            "competencies": ["devops", "automation", "testing"]
        },
        {
            "id": "star-003",
            "role": "Junior Software Engineer",
            "company": "BigTech Corp",
            "period": "2016-2018",
            "situation": "Payment processing system had 30-second latency",
            "task": "Optimize payment flow to meet sub-second SLA",
            "action": "Implemented caching layer with Redis, optimized database queries, added async processing",
            "result": "Reduced latency from 30s to 500ms, processed 1M+ transactions daily",
            "competencies": ["performance_optimization", "backend_engineering", "databases"]
        }
    ]

    print("=== Testing HTML CV Building (Direct) ===\n")
    generator = HTMLCVGenerator()

    try:
        # Create mock competency mix
        competency_mix = MockCompetencyMix()

        # Call the HTML building method directly
        html_content = generator._build_html_cv(state, competency_mix, selected_stars)

        print(f"✅ HTML CV built successfully!")
        print(f"   Content length: {len(html_content)} characters")

        # Verify HTML structure
        checks = [
            ("<!DOCTYPE html>" in html_content, "HTML5 doctype"),
            ("John Doe" in html_content, "Candidate name"),
            ("john.doe@example.com" in html_content, "Contact info"),
            ("Professional Summary" in html_content, "Summary section"),
            ("Key Achievements" in html_content, "Achievements section"),
            ("Professional Experience" in html_content, "Experience section"),
            ("Lead Software Engineer" in html_content, "First STAR role"),
            ("Previous Corp" in html_content, "First STAR company"),
            ("2020-2024" in html_content, "First STAR period"),
            ("Education & Certifications" in html_content, "Education section"),
            ("Stanford University" in html_content, "Education details"),
            ("contenteditable=\"true\"" in html_content, "Editable attributes"),
            ("<style>" in html_content, "Embedded CSS"),
            ("@media print" in html_content, "Print styles"),
        ]

        print("\n✅ Structure checks:")
        all_passed = True
        for passed, description in checks:
            status = "✅" if passed else "❌"
            print(f"   {status} {description}")
            if not passed:
                all_passed = False

        # Save HTML to test file
        output_path = Path("test_output_cv.html")
        output_path.write_text(html_content, encoding='utf-8')
        print(f"\n📄 HTML saved to: {output_path.absolute()}")
        print(f"🌐 Open in browser: file://{output_path.absolute()}")

        return all_passed

    except Exception as e:
        print(f"❌ Error building HTML CV: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_html_cv_building()
    sys.exit(0 if success else 1)
