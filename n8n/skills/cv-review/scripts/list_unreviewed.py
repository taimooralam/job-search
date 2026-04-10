#!/usr/bin/env python3
"""List jobs with generated CVs but no review."""
import os
import sys

from pymongo import MongoClient


def main():
    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client.get_default_database()

    jobs = (
        db["level-2"]
        .find(
            {
                "cv_text": {"$exists": True, "$ne": ""},
                "cv_review": {"$exists": False},
            },
            {"company": 1, "title": 1, "location": 1, "createdAt": 1},
        )
        .sort("createdAt", -1)
        .limit(20)
    )

    count = 0
    for job in jobs:
        count += 1
        company = job.get("company", "?")
        title = job.get("title", "?")
        location = job.get("location", "?")
        print(f"{job['_id']} | {company} — {title} ({location})")

    if count == 0:
        print("All CVs have been reviewed!")
    else:
        print(f"\n{count} unreviewed CV(s)")


if __name__ == "__main__":
    main()
