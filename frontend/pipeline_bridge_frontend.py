"""Pipeline bridge helper for the frontend.

Converts intel docs to level-2 job docs. This is a standalone copy
that doesn't depend on VPS-side mongo_store imports.
"""

from datetime import datetime, timezone

from bson import ObjectId


def convert_intel_to_job_doc(intel_item: dict) -> dict:
    """Convert a LinkedIn intel item to a level-2 job document."""
    url = intel_item.get("url", "")
    job_id = ""
    if url:
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
