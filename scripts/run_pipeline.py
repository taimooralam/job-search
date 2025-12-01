"""
CLI Entry Point: Run Job Intelligence Pipeline

Usage:
    python scripts/run_pipeline.py --job-id 4335713702
    python scripts/run_pipeline.py --job-id 4335713702 --profile custom-profile.md
"""

import argparse
import sys
from pathlib import Path
from pymongo import MongoClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.workflow import run_pipeline
from src.common.config import Config
from src.common.tiering import resolve_tier, get_tier_config, ProcessingTier


def load_candidate_profile(profile_path: str) -> str:
    """Load candidate profile from markdown file."""
    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"Candidate profile not found: {profile_path}")

    with open(path, 'r') as f:
        return f.read()


def load_job_from_mongo(job_id: str) -> dict:
    """
    Load job data from MongoDB.

    Args:
        job_id: MongoDB ObjectId as string (e.g., "691356b0d156e3f08a0bdb3c")

    Returns:
        Dict with job data
    """
    from bson import ObjectId

    # Connect to MongoDB
    client = MongoClient(Config.MONGODB_URI)
    db = client['jobs']

    # Try to convert job_id to ObjectId
    try:
        object_id = ObjectId(job_id)
    except Exception as e:
        raise ValueError(f"Invalid ObjectId format: {job_id}. Error: {e}")

    # Search in level-2 first (filtered/scored jobs), then level-1
    job = None
    collection_name = None

    for coll_name in ['level-2', 'level-1']:
        job = db[coll_name].find_one({"_id": object_id})
        if job:
            collection_name = coll_name
            break

    if not job:
        raise ValueError(
            f"Job {job_id} not found in MongoDB. "
            f"Available collections: level-1 ({db['level-1'].count_documents({})} jobs), "
            f"level-2 ({db['level-2'].count_documents({})} jobs)"
        )

    print(f"  ✓ Found job in collection: {collection_name}")

    # Extract relevant fields (matching your schema)
    job_data = {
        "job_id": str(job.get("_id", "")),  # Use MongoDB _id
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "description": job.get("job_description", ""),
        "url": job.get("jobURL", ""),
        "source": job.get("source", "mongodb"),
        "score": job.get("score")  # Include existing score if available
    }

    return job_data


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Run job intelligence pipeline on a single job"
    )
    parser.add_argument(
        "--job-id",
        required=True,
        help="LinkedIn job ID to process"
    )
    parser.add_argument(
        "--profile",
        default=Config.CANDIDATE_PROFILE_PATH,
        help="Path to candidate profile markdown file"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Use hardcoded test data instead of MongoDB"
    )
    parser.add_argument(
        "--tier",
        default="auto",
        choices=["auto", "A", "B", "C", "D"],
        help="Processing tier: auto (recommended), A (gold), B (silver), C (bronze), D (skip)"
    )

    args = parser.parse_args()

    try:
        # Validate configuration before starting
        print("🔍 Validating configuration...")
        Config.validate()
        print("✅ Configuration valid\n")

        # Load candidate profile
        print(f"Loading candidate profile from: {args.profile}")
        candidate_profile = load_candidate_profile(args.profile)
        print(f"✓ Loaded profile ({len(candidate_profile)} chars)\n")

        # Load job data
        if args.test:
            print(f"Using test data for job {args.job_id}...")
            # Hardcoded test data (Launch Potato - YouTube role from sample-dossier.txt)
            job_data = {
                "job_id": args.job_id,
                "title": "Senior Manager, YouTube Paid Performance",
                "company": "Launch Potato",
                "description": """
WHO ARE WE?

Launch Potato is a digital media company with a portfolio of brands and technologies. As The Discovery and Conversion Company, LaunchPotato is a leading connector of advertisers to customers at all parts of the consumer journey, from awareness to consideration to purchase.

The company is headquartered in vibrant downtown Delray Beach, Florida, with a unique international team across over a dozen countries. LaunchPotato's success comes from a diverse, energetic culture and high-performing, entrepreneurial team.

WHO ARE WE LOOKING FOR?

We're looking for a YouTube performance marketing expert who will take full ownership of Launch Potato's YouTube business. You will be responsible for significantly scaling one of our most important growth channels while maintaining profitability.

This role requires someone who can combine hands-on campaign management with high-level strategy. You'll directly own campaign execution, P&L, and growth targets.

YOUR ROLE:

* Own the entire YouTube advertising P&L - from daily optimizations to quarterly planning
* Scale campaigns profitably from current spend to $20M+ annually
* Develop and execute creative testing strategies to improve performance
* Build and manage relationships with Google/YouTube reps
* Analyze performance data and translate insights into action
* Collaborate cross-functionally with creative, analytics, and product teams
* Mentor junior team members on YouTube best practices

MUST HAVE:

* Proven success profitably scaling new and existing brands on YouTube
* Strong analytical skills with proficiency in BI tools like Looker, Google Analytics
* Demonstrated understanding of best practices that drive high-performing creatives
* Demonstrated experience owning P&L and hitting aggressive growth + profitability goals
* Exceptional collaboration and proactive communication skills
* Willingness to work in an office environment in Delray Beach, FL

EXPERIENCE:

6+ years managing and scaling a YouTube performance-based portfolio, with budgets of $20M+/year.
                """.strip(),
                "url": "https://www.linkedin.com/jobs/view/4335713702",
                "source": "test"
            }
            print(f"✓ Test data loaded: {job_data['title']} at {job_data['company']}\n")
        else:
            print(f"Loading job {args.job_id} from MongoDB...")
            job_data = load_job_from_mongo(args.job_id)
            print(f"✓ Loaded job: {job_data['title']} at {job_data['company']}\n")

        # Resolve processing tier
        existing_score = job_data.get("score")
        tier = resolve_tier(args.tier, existing_score)
        tier_config = get_tier_config(tier)
        print(f"🎯 Processing Tier: {tier.value} ({tier_config.description})")
        print(f"   CV Model: {tier_config.cv_model}")
        print(f"   Research Model: {tier_config.research_model}")
        print(f"   Max Contacts: {tier_config.max_contacts}")
        print(f"   Estimated Cost: ${tier_config.estimated_cost_usd:.2f}\n")

        # Run pipeline with tier configuration
        final_state = run_pipeline(job_data, candidate_profile, tier_config=tier_config)

        # Print final results
        print("\n" + "="*70)
        print("📊 FINAL RESULTS")
        print("="*70)

        # Pain Point Analysis (4 Dimensions)
        print(f"\n📋 Pain Point Analysis (4 Dimensions):")

        print("\n  A. Pain Points:")
        if final_state.get("pain_points"):
            for i, point in enumerate(final_state["pain_points"], 1):
                print(f"    {i}. {point}")
        else:
            print("    None extracted")

        print("\n  B. Strategic Needs:")
        if final_state.get("strategic_needs"):
            for i, need in enumerate(final_state["strategic_needs"], 1):
                print(f"    {i}. {need}")
        else:
            print("    None extracted")

        print("\n  C. Risks if Unfilled:")
        if final_state.get("risks_if_unfilled"):
            for i, risk in enumerate(final_state["risks_if_unfilled"], 1):
                print(f"    {i}. {risk}")
        else:
            print("    None extracted")

        print("\n  D. Success Metrics:")
        if final_state.get("success_metrics"):
            for i, metric in enumerate(final_state["success_metrics"], 1):
                print(f"    {i}. {metric}")
        else:
            print("    None extracted")

        print(f"\n⭐ Selected STAR Achievements (Layer 2.5):")
        if final_state.get("selected_stars"):
            for i, star in enumerate(final_state["selected_stars"], 1):
                print(f"  {i}. {star['company']} - {star['role'][:50]}...")
                print(f"     Metrics: {star['metrics'][:80]}...")
        else:
            print("  None selected")

        print(f"\n🏢 Company Summary:")
        print(f"  {final_state.get('company_summary', 'None')}")

        print(f"\n🎯 Fit Analysis:")
        print(f"  Score: {final_state.get('fit_score', 'N/A')}/100")
        print(f"  Rationale: {final_state.get('fit_rationale', 'None')}")

        print(f"\n👥 Key Contacts (Layer 5):")
        if final_state.get("people"):
            for i, person in enumerate(final_state["people"], 1):
                print(f"  {i}. {person['name']} - {person['role']}")
                print(f"     LinkedIn: {person['linkedin_url'][:60]}...")
        else:
            print("  None identified")

        print(f"\n📄 Cover Letter:")
        if final_state.get("cover_letter"):
            print(f"  Generated ({len(final_state['cover_letter'])} chars)")
            print(f"\n  Preview:")
            print(f"  {final_state['cover_letter'][:200]}...")
        else:
            print(f"  Not generated")

        print(f"\n📋 CV:")
        print(f"  {final_state.get('cv_path', 'Not generated')}")

        print(f"\n📁 Outputs:")
        print(f"  Drive Folder: {final_state.get('drive_folder_url', 'None')}")
        print(f"  Sheets Row: {final_state.get('sheet_row_id', 'None')}")

        if final_state.get("errors"):
            print(f"\n⚠️  Warnings:")
            for error in final_state["errors"]:
                print(f"  - {error}")

        print("="*70)
        print("\n✅ Pipeline complete!")

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
