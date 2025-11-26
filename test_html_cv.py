#!/usr/bin/env python3
"""
Quick test script to verify HTML CV generation works locally.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.layer6.html_cv_generator import HTMLCVGenerator
from src.common.state import JobState


def test_html_cv_generation():
    """Test HTML CV generation with mock data."""

    # Create mock state
    state = JobState(
        job_id="test-12345",
        title="Senior Software Engineer",
        company="TechCorp Inc",
        job_description="""
        We are seeking a Senior Software Engineer to join our team.

        Requirements:
        - 5+ years of Python development experience
        - Strong background in distributed systems
        - Experience with cloud platforms (AWS, GCP)
        - Excellent problem-solving skills
        - Leadership and mentoring experience

        Responsibilities:
        - Design and implement scalable backend services
        - Lead technical architecture decisions
        - Mentor junior engineers
        - Collaborate with product teams
        """,
        candidate_profile="""
        # Candidate Profile

        **Name:** John Doe
        **Email:** john.doe@example.com | **Phone:** +1-555-0123
        **Location:** San Francisco, CA

        ## Professional Summary
        Senior Software Engineer with 8+ years of experience building scalable systems.

        ## Education
        **B.S. Computer Science** - Stanford University (2015)
        **M.S. Computer Science** - MIT (2017)

        AWS Certified Solutions Architect
        """,
        all_stars=[
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
        ],
        fit_score=0.85,
        level=2
    )

    # Generate HTML CV
    print("=== Testing HTML CV Generation ===\n")
    generator = HTMLCVGenerator()

    try:
        html_path, reasoning = generator.generate_html_cv(state)
        print(f"✅ HTML CV generated successfully!")
        print(f"   Path: {html_path}")
        print(f"\n📄 CV Reasoning:\n{reasoning}\n")

        # Verify file exists
        if Path(html_path).exists():
            file_size = Path(html_path).stat().st_size
            print(f"✅ File exists: {file_size} bytes")

            # Show first few lines
            with open(html_path, 'r', encoding='utf-8') as f:
                first_lines = ''.join([f.readline() for _ in range(10)])
            print(f"\n📋 First 10 lines of HTML:\n{first_lines}")

            print(f"\n🌐 Open in browser:")
            print(f"   file://{Path(html_path).absolute()}")

            return True
        else:
            print(f"❌ File not found at {html_path}")
            return False

    except Exception as e:
        print(f"❌ Error generating HTML CV: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_html_cv_generation()
    sys.exit(0 if success else 1)
