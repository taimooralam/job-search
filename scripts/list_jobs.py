"""
List jobs from MongoDB database.

Usage:
    python scripts/list_jobs.py                    # List first 10 jobs
    python scripts/list_jobs.py --limit 50         # List 50 jobs
    python scripts/list_jobs.py --search "YouTube" # Search for jobs containing "YouTube"
    python scripts/list_jobs.py --company "Google" # Search by company name
"""

import argparse
import sys
from pathlib import Path
from pymongo import MongoClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.config import Config


def list_jobs(limit=10, search=None, company=None):
    """
    List jobs from MongoDB.

    Args:
        limit: Max number of jobs to return
        search: Search term for job title
        company: Filter by company name
    """
    # Connect to MongoDB
    client = MongoClient(Config.MONGODB_URI)

    # Use 'jobs' database with level-2 collection (scored jobs)
    db = client['jobs']

    # Check both collections
    level1_count = db['level-1'].count_documents({})
    level2_count = db['level-2'].count_documents({})

    print(f"📊 Database: jobs")
    print(f"   level-1 (all jobs): {level1_count:,} documents")
    print(f"   level-2 (scored): {level2_count:,} documents")
    print()

    # Use level-2 by default (scored jobs), fallback to level-1
    collection_name = 'level-2' if level2_count > 0 else 'level-1'
    collection = db[collection_name]

    # Build query
    query = {}
    if search:
        query["title"] = {"$regex": search, "$options": "i"}
    if company:
        query["company"] = {"$regex": company, "$options": "i"}

    # Find jobs
    jobs = collection.find(
        query,
        {"jobId": 1, "title": 1, "company": 1, "location": 1, "score": 1, "_id": 0}
    ).limit(limit)

    jobs_list = list(jobs)

    if not jobs_list:
        print("❌ No jobs found matching criteria.")
        return

    # Display results
    print(f"Showing jobs from: {collection_name}")
    print("="*110)
    print(f"{'JOB ID':<12} | {'SCORE':<6} | {'COMPANY':<22} | {'TITLE':<40} | {'LOCATION':<20}")
    print("="*110)

    for job in jobs_list:
        job_id = str(job.get("jobId", "N/A"))
        score = job.get("score", "N/A")
        score_str = f"{score}" if score != "N/A" else "N/A"
        company_name = job.get("company", "N/A")[:22]
        title = job.get("title", "N/A")[:40]
        location = job.get("location", "N/A")[:20]

        print(f"{job_id:<12} | {score_str:<6} | {company_name:<22} | {title:<40} | {location:<20}")

    print("="*110)
    print(f"\nShowing {len(jobs_list)} jobs")

    if len(jobs_list) > 0:
        print("\n💡 To process a job, run:")
        print(f"   python scripts/run_pipeline.py --job-id {jobs_list[0].get('jobId')}")


def main():
    parser = argparse.ArgumentParser(description="List jobs from MongoDB")
    parser.add_argument("--limit", type=int, default=10, help="Max number of jobs to show")
    parser.add_argument("--search", help="Search term for job title")
    parser.add_argument("--company", help="Filter by company name")

    args = parser.parse_args()

    try:
        list_jobs(limit=args.limit, search=args.search, company=args.company)
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
