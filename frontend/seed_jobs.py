"""
Seed script to populate sample jobs for demo purposes.

Usage:
    python -m frontend.seed_jobs              # Add 20 sample jobs
    python -m frontend.seed_jobs --count 50   # Add 50 sample jobs
    python -m frontend.seed_jobs --clear      # Clear all jobs first, then seed
"""

import argparse
import os
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# Sample data for generating realistic job listings
COMPANIES = [
    "Google", "Meta", "Amazon", "Microsoft", "Apple", "Netflix", "Stripe",
    "Airbnb", "Uber", "Lyft", "Spotify", "Twitter", "LinkedIn", "Salesforce",
    "Adobe", "Oracle", "IBM", "Intel", "NVIDIA", "Cisco", "VMware",
    "Shopify", "Square", "Coinbase", "Robinhood", "Plaid", "Figma",
    "Notion", "Slack", "Zoom", "Atlassian", "Datadog", "Snowflake",
]

ROLES = [
    "Senior Software Engineer",
    "Staff Software Engineer",
    "Principal Engineer",
    "Engineering Manager",
    "Director of Engineering",
    "VP of Engineering",
    "Site Reliability Engineer",
    "DevOps Engineer",
    "Platform Engineer",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Data Engineer",
    "ML Engineer",
    "Solutions Architect",
    "Technical Program Manager",
    "Product Manager",
    "Engineering Lead",
    "Cloud Architect",
    "Security Engineer",
]

LOCATIONS = [
    "San Francisco, CA",
    "New York, NY",
    "Seattle, WA",
    "Austin, TX",
    "Boston, MA",
    "Los Angeles, CA",
    "Chicago, IL",
    "Denver, CO",
    "Miami, FL",
    "Remote",
    "Remote (US)",
    "Hybrid - San Francisco",
    "Hybrid - New York",
    "London, UK",
    "Toronto, Canada",
    "Berlin, Germany",
    "Singapore",
    "Sydney, Australia",
]

STATUSES = [
    "not processed",
    "not processed",
    "not processed",
    "not processed",  # Weighted more heavily
    "marked for applying",
    "marked for applying",
    "applied",
    "interview scheduled",
    "to be deleted",
]


def generate_job_id() -> str:
    """Generate a realistic job ID."""
    prefix = random.choice(["JOB", "REQ", "POS", ""])
    number = random.randint(100000, 999999)
    return f"{prefix}{number}" if prefix else str(number)


def generate_dedupe_key(company: str, role: str) -> str:
    """Generate a dedupe key from company and role."""
    company_slug = company.lower().replace(" ", "-")
    role_slug = role.lower().replace(" ", "-")[:30]
    return f"{company_slug}_{role_slug}_{random.randint(1000, 9999)}"


def generate_job_url(company: str, job_id: str) -> str:
    """Generate a realistic job URL."""
    company_domain = company.lower().replace(" ", "")
    return f"https://careers.{company_domain}.com/jobs/{job_id}"


def generate_sample_job() -> dict:
    """Generate a single sample job document."""
    company = random.choice(COMPANIES)
    role = random.choice(ROLES)
    job_id = generate_job_id()

    # Random date in the last 30 days
    days_ago = random.randint(0, 30)
    created_at = datetime.utcnow() - timedelta(days=days_ago)

    return {
        "jobId": job_id,
        "title": role,
        "company": company,
        "location": random.choice(LOCATIONS),
        "jobUrl": generate_job_url(company, job_id),
        "dedupeKey": generate_dedupe_key(company, role),
        "createdAt": created_at,
        "status": random.choice(STATUSES),
        "score": random.choice([None, None, random.randint(40, 95)]),  # Some jobs without scores
        "description": f"We are looking for a {role} to join our team at {company}. "
                      f"This is an exciting opportunity to work on challenging problems.",
        "source": "seed_script",
    }


def seed_jobs(count: int = 20, clear: bool = False) -> None:
    """
    Seed the database with sample jobs.

    Args:
        count: Number of jobs to create
        clear: If True, clear existing jobs first
    """
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017/jobs")
    client = MongoClient(mongo_uri)
    db = client["jobs"]
    collection = db["level-2"]

    if clear:
        result = collection.delete_many({})
        print(f"Cleared {result.deleted_count} existing jobs")

    # Generate and insert jobs
    jobs = [generate_sample_job() for _ in range(count)]

    result = collection.insert_many(jobs)
    print(f"Inserted {len(result.inserted_ids)} sample jobs into level-2 collection")

    # Show sample
    print("\nSample jobs:")
    for job in jobs[:3]:
        print(f"  - {job['company']}: {job['title']} ({job['location']})")

    # Show collection stats
    total = collection.count_documents({})
    print(f"\nTotal jobs in level-2: {total}")


def main():
    parser = argparse.ArgumentParser(description="Seed sample jobs for demo")
    parser.add_argument("--count", type=int, default=20, help="Number of jobs to create")
    parser.add_argument("--clear", action="store_true", help="Clear existing jobs first")

    args = parser.parse_args()

    seed_jobs(count=args.count, clear=args.clear)


if __name__ == "__main__":
    main()
