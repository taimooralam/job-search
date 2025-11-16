"""
TDD Test for Layer 4: Opportunity Mapper

This test defines the expected behavior BEFORE implementation.

Layer 4 should:
1. Take pain points (from Layer 2)
2. Take company summary (from Layer 3)
3. Take candidate profile
4. Generate fit score (0-100)
5. Generate fit rationale (2-3 sentences explaining the match)
"""

from src.layer4.opportunity_mapper import opportunity_mapper_node
from src.common.state import JobState

# Sample state with outputs from Layer 2 and Layer 3
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

    # Candidate profile (simplified for today)
    "candidate_profile": """
Name: Senior Digital Marketing Professional
Experience: 8+ years in performance marketing, specializing in YouTube and video advertising
Key Skills: YouTube Ads, Google Analytics, Looker, Data Analysis, Creative Strategy, P&L Management
Notable Achievements:
- Scaled YouTube campaigns from $5M to $25M annually while improving ROAS by 40%
- Led cross-functional teams of 5-8 marketers and analysts
- Built data dashboards in Looker for real-time campaign optimization
- Managed P&L for $30M+ digital marketing budget
    """.strip(),

    # Layer 2 output (pain points)
    "pain_points": [
        "Need expert who can profitably scale YouTube campaigns to significant budgets ($20M+)",
        "Requires strong analytical capabilities with BI tools for data-driven decisions",
        "Must have proven P&L ownership and ability to hit aggressive growth targets",
        "Creative strategy expertise needed to drive high-performing ad content",
        "Looking for hands-on execution combined with strategic thinking"
    ],

    # Layer 3 output (company research)
    "company_summary": "Launch Potato is a digital media company based in Delray Beach, Florida, specializing in building scalable direct-to-consumer digital businesses. It is recognized as the fastest-growing company in South Florida, leveraging expertise in marketing, engineering, and data science.",
    "company_url": "https://launchpotato.com",

    # Fields to be filled by Layer 4
    "fit_score": None,
    "fit_rationale": None,

    # Other fields
    "cover_letter": None,
    "cv_path": None,
    "drive_folder_url": None,
    "sheet_row_id": None,
    "run_id": None,
    "created_at": None,
    "errors": None,
    "status": "processing"
}


def test_opportunity_mapper():
    """Test that Layer 4 generates fit score and rationale."""
    print("Testing Layer 4: Opportunity Mapper (TDD)\n")

    # Run the node
    updates = opportunity_mapper_node(sample_state)

    # ASSERTIONS: Define what we expect
    print("\n" + "="*60)
    print("TEST RESULTS")
    print("="*60)

    # Test 1: fit_score should be present
    assert updates.get("fit_score") is not None, "❌ fit_score is missing"
    print(f"✅ fit_score present: {updates['fit_score']}")

    # Test 2: fit_score should be between 0-100
    assert 0 <= updates["fit_score"] <= 100, f"❌ fit_score out of range: {updates['fit_score']}"
    print(f"✅ fit_score in valid range (0-100)")

    # Test 3: fit_rationale should be present
    assert updates.get("fit_rationale") is not None, "❌ fit_rationale is missing"
    print(f"✅ fit_rationale present")

    # Test 4: fit_rationale should be meaningful (at least 50 chars)
    assert len(updates["fit_rationale"]) >= 50, "❌ fit_rationale too short"
    print(f"✅ fit_rationale is meaningful ({len(updates['fit_rationale'])} chars)")

    # Test 5: Given strong candidate match, score should be high (>= 70)
    # This is a business logic test - the candidate profile matches well
    assert updates["fit_score"] >= 70, f"❌ Expected high score for strong match, got {updates['fit_score']}"
    print(f"✅ Score reflects strong candidate match (>= 70)")

    print("\n" + "="*60)
    print("ALL TESTS PASSED! ✅")
    print("="*60)

    print(f"\nFit Score: {updates['fit_score']}/100")
    print(f"\nFit Rationale:\n{updates['fit_rationale']}")
    print("\n" + "="*60)


if __name__ == "__main__":
    test_opportunity_mapper()
