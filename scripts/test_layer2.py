"""
Quick test script for Layer 2: Pain-Point Miner

Tests the pain point extraction on a sample job description.
"""

from src.layer2.pain_point_miner import pain_point_miner_node
from src.common.state import JobState

# Sample job data (simplified from your sample-dossier.txt)
sample_state: JobState = {
    "job_id": "4335713702",
    "title": "Senior Manager, YouTube Paid Performance",
    "company": "Launch Potato",
    "job_description": """
WHO ARE WE? Launch Potato is a profitable digital media company that reaches over 30M+ monthly visitors.
As The Discovery and Conversion Company, our mission is to connect consumers with the world's leading brands
through data-driven content and technology.

YOUR ROLE: You are a YouTube performance marketing expert who will take full ownership of Launch Potato's
YouTube business. You'll be responsible for significantly scaling one of our most important growth channels
while maintaining profitability. You'll combine hands-on campaign management with high-level strategy,
directly owning campaign execution, P&L, and growth targets.

MUST HAVE:
* Proven success profitably scaling new and existing brands on YouTube
* Strong analytical skills with proficiency in BI tools (Looker, Google Analytics, etc.)
* Strong understanding of best practices that drive high-performing creatives
* Demonstrated experience owning P&L and hitting aggressive growth + profitability goals
* Exceptional collaboration and proactive communication skills

EXPERIENCE: 6+ years managing and scaling a YouTube performance-based portfolio, with budgets of $20M+/year.
    """.strip(),
    "job_url": "https://www.linkedin.com/jobs/view/4335713702",
    "source": "linkedin",
    "candidate_profile": "",  # Not needed for this test

    # Optional fields (not filled yet)
    "pain_points": None,
    "company_summary": None,
    "company_url": None,
    "fit_score": None,
    "fit_rationale": None,
    "cover_letter": None,
    "cv_path": None,
    "drive_folder_url": None,
    "sheet_row_id": None,
    "run_id": None,
    "created_at": None,
    "errors": None,
    "status": "processing"
}

if __name__ == "__main__":
    print("Testing Layer 2: Pain-Point Miner\n")

    # Run the node
    updates = pain_point_miner_node(sample_state)

    # Check results
    if updates.get("pain_points"):
        print("\n✅ SUCCESS! Pain points extracted:")
        for i, point in enumerate(updates["pain_points"], 1):
            print(f"   {i}. {point}")
    else:
        print("\n❌ FAILED: No pain points extracted")
        if updates.get("errors"):
            print(f"   Errors: {updates['errors']}")
