"""Pipeline bridge: convert LinkedIn intel items to level-2 job documents.

Used by:
- Dashboard: POST /dashboard/opportunities/<id>/pipeline
- Telegram: /apply command
- Direct CLI: python3 pipeline_bridge.py --test <item_id>
"""

import os
import sys
from datetime import datetime, timezone

from bson import ObjectId

import mongo_store
from utils import setup_logging

logger = setup_logging("pipeline-bridge")


def convert_intel_to_job_doc(intel_item: dict) -> dict:
    """Convert a LinkedIn intel item to a level-2 job document format.

    Maps intel fields to the job pipeline schema expected by the
    Atlas MongoDB `level-2` collection.
    """
    # Extract job_id from URL or generate one
    url = intel_item.get("url", "")
    job_id = ""
    if url:
        # LinkedIn job URLs: /jobs/view/12345678/
        parts = [p for p in url.rstrip("/").split("/") if p]
        if parts:
            job_id = parts[-1]
    if not job_id or not job_id.isdigit():
        job_id = str(ObjectId())

    classification = intel_item.get("classification", {})
    score = intel_item.get("relevance_score", classification.get("relevance_score", 0))

    return {
        "job_id": job_id,
        "company": intel_item.get("company", intel_item.get("author", "Unknown")),
        "role": intel_item.get("title", ""),
        "job_url": url,
        "location": intel_item.get("location", ""),
        "description": intel_item.get("full_content", intel_item.get("content_preview", "")),
        "source": "linkedin_intel",
        "source_intel_id": str(intel_item["_id"]),
        "score": score,
        "tier": "Tier 1" if score >= 8 else "Tier 2",
        "created_at": datetime.now(timezone.utc),
        "status": "new",
        "pipeline_status": "pending",
        "edge_opportunities": intel_item.get("edge_opportunities", []),
    }


def push_to_pipeline(intel_item_id: str, atlas_uri: str | None = None) -> dict:
    """Full pipeline push: fetch intel item, convert, insert into Atlas.

    Returns result dict with job_id and status.
    """
    from pymongo import MongoClient

    # Fetch from VPS MongoDB
    db = mongo_store.get_db()
    if isinstance(intel_item_id, str):
        intel_item_id = ObjectId(intel_item_id)
    item = db.linkedin_intel.find_one({"_id": intel_item_id})
    if not item:
        return {"error": f"Intel item {intel_item_id} not found"}

    # Convert
    job_doc = convert_intel_to_job_doc(item)

    # Insert into Atlas
    uri = atlas_uri or os.environ.get("ATLAS_MONGODB_URI")
    if not uri:
        return {"error": "ATLAS_MONGODB_URI not set"}

    atlas_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        atlas_db = atlas_client["jobs"]
        atlas_db["level-2"].insert_one(job_doc)
        logger.info("Pushed to Atlas: job_id=%s, role=%s", job_doc["job_id"], job_doc["role"])

        # Mark intel item as pushed
        db.linkedin_intel.update_one(
            {"_id": item["_id"]},
            {"$set": {
                "acted_on": True,
                "acted_action": "pipeline",
                "pipeline_job_id": job_doc["job_id"],
                "acted_at": datetime.now(timezone.utc),
            }},
        )

        return {
            "job_id": job_doc["job_id"],
            "role": job_doc["role"],
            "company": job_doc["company"],
            "status": "pushed",
        }
    finally:
        atlas_client.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Pipeline bridge: intel → job doc")
    parser.add_argument("--test", metavar="ITEM_ID", help="Print job doc for an intel item (no insert)")
    parser.add_argument("--push", metavar="ITEM_ID", help="Actually push an intel item to Atlas")
    args = parser.parse_args()

    if args.test:
        oid = ObjectId(args.test)
        db = mongo_store.get_db()
        item = db.linkedin_intel.find_one({"_id": oid})
        if not item:
            print(f"Item {args.test} not found")
            sys.exit(1)
        doc = convert_intel_to_job_doc(item)
        # Make ObjectId serializable
        doc_str = {k: str(v) if isinstance(v, (ObjectId, datetime)) else v for k, v in doc.items()}
        print(json.dumps(doc_str, indent=2))
    elif args.push:
        result = push_to_pipeline(args.push)
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()
