"""
TDD Test for Layer 6: Outreach & CV Generator

This test defines the expected behavior BEFORE implementation.

Layer 6 should:
1. Take all previous layer outputs (pain points, company summary, fit analysis)
2. Generate a simple 3-paragraph cover letter (outreach)
3. Generate a tailored CV (.docx file) with job-specific content
4. Return cover_letter text and cv_path
"""

import os
from src.layer6.generator import generator_node
from src.common.state import JobState

# Sample state with outputs from all previous layers
sample_state: JobState = {
    "job_id": "4335713702",
    "title": "Senior Manager, YouTube Paid Performance",
    "company": "Launch Potato",
    "job_description": """
WHO ARE WE? Launch Potato is a profitable digital media company that reaches over 30M+ monthly visitors.

YOUR ROLE: You are a YouTube performance marketing expert who will take full ownership of Launch Potato's
YouTube business. You'll be responsible for significantly scaling one of our most important growth channels
while maintaining profitability.

MUST HAVE:
* Proven success profitably scaling new and existing brands on YouTube
* Strong analytical skills with proficiency in BI tools (Looker, Google Analytics, etc.)
* Strong understanding of best practices that drive high-performing creatives
* Demonstrated experience owning P&L and hitting aggressive growth + profitability goals

EXPERIENCE: 6+ years managing and scaling a YouTube performance-based portfolio, with budgets of $20M+/year.
    """.strip(),
    "job_url": "https://www.linkedin.com/jobs/view/4335713702",
    "source": "linkedin",

    # Candidate profile
    "candidate_profile": """
Name: Alex Thompson
Email: alex.thompson@email.com
Phone: (555) 123-4567
LinkedIn: linkedin.com/in/alexthompson

Experience: 8+ years in performance marketing, specializing in YouTube and video advertising
Key Skills: YouTube Ads, Google Analytics, Looker, Data Analysis, Creative Strategy, P&L Management

Notable Achievements:
- Scaled YouTube campaigns from $5M to $25M annually while improving ROAS by 40%
- Led cross-functional teams of 5-8 marketers and analysts
- Built data dashboards in Looker for real-time campaign optimization
- Managed P&L for $30M+ digital marketing budget

Work History:
- Senior Performance Marketing Manager, TechCorp (2019-Present)
- Performance Marketing Lead, AdVenture Co (2016-2019)
- Digital Marketing Analyst, MediaHub (2014-2016)

Education:
- MBA, Marketing, State University (2014)
- BS, Business Administration, City College (2012)
    """.strip(),

    # Layer 2 output
    "pain_points": [
        "Need expert who can profitably scale YouTube campaigns to significant budgets ($20M+)",
        "Requires strong analytical capabilities with BI tools for data-driven decisions",
        "Must have proven P&L ownership and ability to hit aggressive growth targets",
        "Creative strategy expertise needed to drive high-performing ad content",
        "Looking for hands-on execution combined with strategic thinking"
    ],

    # Layer 3 output
    "company_summary": "Launch Potato is a digital media company based in Delray Beach, Florida, specializing in building scalable direct-to-consumer digital businesses. It is recognized as the fastest-growing company in South Florida, leveraging expertise in marketing, engineering, and data science.",
    "company_url": "https://launchpotato.com",

    # Layer 4 output
    "fit_score": 95,
    "fit_rationale": "The candidate is an exceptional fit for the Senior Manager, YouTube Paid Performance role at Launch Potato. They have over 8 years of relevant experience, including scaling YouTube campaigns from $5M to $25M, which aligns with the company's need for expertise in managing significant budgets.",

    # Fields to be filled by Layer 6
    "cover_letter": None,
    "cv_path": None,

    # Other fields
    "drive_folder_url": None,
    "sheet_row_id": None,
    "run_id": None,
    "created_at": None,
    "errors": None,
    "status": "processing"
}


def test_generator():
    """Test that Layer 6 generates cover letter and CV."""
    print("Testing Layer 6: Outreach & CV Generator (TDD)\n")

    # Run the node
    updates = generator_node(sample_state)

    # ASSERTIONS: Define what we expect
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)

    # Test 1: cover_letter should be present
    assert updates.get("cover_letter") is not None, "❌ cover_letter is missing"
    print(f"✅ cover_letter present")

    # Test 2: cover_letter should be meaningful (at least 200 chars for 3 paragraphs)
    assert len(updates["cover_letter"]) >= 200, f"❌ cover_letter too short ({len(updates['cover_letter'])} chars)"
    print(f"✅ cover_letter is meaningful ({len(updates['cover_letter'])} chars)")

    # Test 3: cover_letter should mention the company name
    assert "Launch Potato" in updates["cover_letter"], "❌ cover_letter doesn't mention company"
    print(f"✅ cover_letter mentions company name")

    # Test 4: cover_letter should mention the role
    assert "YouTube" in updates["cover_letter"] or "Senior Manager" in updates["cover_letter"], \
        "❌ cover_letter doesn't mention role"
    print(f"✅ cover_letter mentions the role")

    # Test 5: cv_path should be present
    assert updates.get("cv_path") is not None, "❌ cv_path is missing"
    print(f"✅ cv_path present: {updates['cv_path']}")

    # Test 6: CV file should actually exist
    assert os.path.exists(updates["cv_path"]), f"❌ CV file doesn't exist at {updates['cv_path']}"
    print(f"✅ CV file exists at path")

    # Test 7: CV file should be a .docx file
    assert updates["cv_path"].endswith('.docx'), f"❌ CV is not a .docx file: {updates['cv_path']}"
    print(f"✅ CV is .docx format")

    # Test 8: CV file should have content (size > 5KB, typical for a .docx)
    file_size = os.path.getsize(updates["cv_path"])
    assert file_size > 5000, f"❌ CV file too small ({file_size} bytes), likely empty"
    print(f"✅ CV file has content ({file_size:,} bytes)")

    print("\n" + "="*60)
    print("ALL TESTS PASSED! ✅")
    print("="*60)

    print(f"\n📄 Cover Letter Preview (first 300 chars):")
    print(updates["cover_letter"][:300] + "...\n")

    print(f"📋 CV Generated: {updates['cv_path']}")
    print("="*60)

    # Cleanup: remove test CV file
    if os.path.exists(updates["cv_path"]):
        os.remove(updates["cv_path"])
        print(f"\n🧹 Cleaned up test CV file")


if __name__ == "__main__":
    test_generator()
