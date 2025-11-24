"""
Flask application for the Job Search UI.

Provides a table view of Level-2 MongoDB job data with:
- Free-text search
- Sortable columns
- Pagination (5/10/50/100 per page)
- Multi-select delete
- Status management

Stack: Flask + HTMX + Tailwind CSS (CDN)
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from pymongo import ASCENDING, DESCENDING, MongoClient

# Load environment variables
load_dotenv()

app = Flask(__name__)

# MongoDB configuration
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/jobs")

# Job status whitelist
JOB_STATUSES = [
    "not processed",
    "marked for applying",
    "to be deleted",
    "applied",
    "interview scheduled",
    "rejected",
    "offer received",
]


def get_db():
    """Get MongoDB database connection."""
    client = MongoClient(MONGO_URI)
    return client["jobs"]


def serialize_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Serialize a MongoDB job document for JSON response.

    Handles ObjectId conversion and date formatting.
    """
    result = {}
    for key, value in job.items():
        if key == "_id":
            result["_id"] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        else:
            result[key] = value
    return result


# ============================================================================
# API Endpoints
# ============================================================================

@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    """
    List jobs with search, sort, and pagination.

    Query Parameters:
        query: Free-text search (searches title, company, location)
        sort: Field to sort by (default: createdAt)
        direction: Sort direction - asc or desc (default: desc)
        page: Page number (default: 1)
        page_size: Items per page - 5, 10, 50, 100 (default: 10)

    Returns:
        JSON with jobs array and pagination metadata
    """
    db = get_db()
    collection = db["level-2"]

    # Parse query parameters
    search_query = request.args.get("query", "").strip()
    sort_field = request.args.get("sort", "createdAt")
    sort_direction = request.args.get("direction", "desc")
    page = max(1, int(request.args.get("page", 1)))
    page_size = int(request.args.get("page_size", 10))

    # Date range filters (MongoDB stores dates as ISO strings)
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    # Location filter (can be multiple values)
    locations = request.args.getlist("locations")

    # Validate page_size
    if page_size not in [5, 10, 50, 100]:
        page_size = 10

    # Build MongoDB query
    mongo_query: Dict[str, Any] = {}

    # Free-text search
    if search_query:
        # Search across multiple fields
        mongo_query["$or"] = [
            {"title": {"$regex": search_query, "$options": "i"}},
            {"company": {"$regex": search_query, "$options": "i"}},
            {"location": {"$regex": search_query, "$options": "i"}},
            {"jobId": {"$regex": search_query, "$options": "i"}},
        ]

    # Date range filter (ISO string comparison works lexicographically)
    if date_from or date_to:
        date_filter: Dict[str, str] = {}
        if date_from:
            # Convert YYYY-MM-DD to start of day ISO string
            date_filter["$gte"] = f"{date_from}T00:00:00.000Z"
        if date_to:
            # Convert YYYY-MM-DD to end of day ISO string
            date_filter["$lte"] = f"{date_to}T23:59:59.999Z"
        mongo_query["createdAt"] = date_filter

    # Location filter (multi-select)
    if locations:
        mongo_query["location"] = {"$in": locations}

    # Map frontend field names to MongoDB field names
    field_mapping = {
        "createdAt": "createdAt",
        "url": "url",
        "jobUrl": "url",  # Map jobUrl to url field
        "dedupeKey": "dedupeKey",
        "jobId": "jobId",
        "location": "location",
        "role": "title",
        "title": "title",
        "company": "company",
        "status": "status",
        "score": "score",
    }
    mongo_sort_field = field_mapping.get(sort_field, "createdAt")

    # Sort direction
    mongo_direction = DESCENDING if sort_direction == "desc" else ASCENDING

    # Count total matching documents
    total_count = collection.count_documents(mongo_query)

    # Calculate pagination
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    skip = (page - 1) * page_size

    # Fetch jobs with projection
    projection = {
        "_id": 1,
        "createdAt": 1,
        "url": 1,
        "jobUrl": 1,  # Legacy field - some docs may use this
        "dedupeKey": 1,
        "jobId": 1,
        "location": 1,
        "title": 1,
        "company": 1,
        "status": 1,
        "score": 1,
    }

    cursor = collection.find(mongo_query, projection)
    cursor = cursor.sort(mongo_sort_field, mongo_direction)
    cursor = cursor.skip(skip).limit(page_size)

    jobs = [serialize_job(job) for job in cursor]

    return jsonify({
        "jobs": jobs,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        }
    })


@app.route("/api/jobs/delete", methods=["POST"])
def delete_jobs():
    """
    Bulk delete jobs by ID.

    Request Body:
        job_ids: List of job _id strings to delete

    Returns:
        JSON with deleted_count
    """
    db = get_db()
    collection = db["level-2"]

    data = request.get_json()
    job_ids = data.get("job_ids", [])

    if not job_ids:
        return jsonify({"error": "No job_ids provided"}), 400

    # Convert string IDs to ObjectId
    object_ids = []
    for job_id in job_ids:
        try:
            object_ids.append(ObjectId(job_id))
        except Exception:
            # Skip invalid IDs
            continue

    if not object_ids:
        return jsonify({"error": "No valid job_ids provided"}), 400

    # Delete the jobs
    result = collection.delete_many({"_id": {"$in": object_ids}})

    return jsonify({
        "success": True,
        "deleted_count": result.deleted_count,
    })


@app.route("/api/jobs/status", methods=["POST"])
def update_job_status():
    """
    Update job status.

    Request Body:
        job_id: Job _id string
        status: New status value (from whitelist)

    Returns:
        JSON with updated job or error
    """
    db = get_db()
    collection = db["level-2"]

    data = request.get_json()
    job_id = data.get("job_id")
    new_status = data.get("status")

    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    if not new_status:
        return jsonify({"error": "status is required"}), 400

    if new_status not in JOB_STATUSES:
        return jsonify({
            "error": f"Invalid status. Must be one of: {', '.join(JOB_STATUSES)}"
        }), 400

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job_id format"}), 400

    # Update the job
    result = collection.update_one(
        {"_id": object_id},
        {"$set": {"status": new_status}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": new_status,
    })


@app.route("/api/jobs/statuses", methods=["GET"])
def get_statuses():
    """Return the list of valid job statuses."""
    return jsonify({"statuses": JOB_STATUSES})


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """
    Get a single job by ID.

    Returns:
        JSON with full job document
    """
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job_id format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({"job": serialize_job(job)})


@app.route("/api/jobs/<job_id>", methods=["PUT"])
def update_job(job_id: str):
    """
    Update a job's editable fields.

    Request Body:
        Any editable fields: status, remarks, notes, etc.

    Returns:
        JSON with updated job
    """
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job_id format"}), 400

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Whitelist of editable fields
    editable_fields = ["status", "remarks", "notes", "priority"]
    update_data = {}

    for field in editable_fields:
        if field in data:
            # Validate status if provided
            if field == "status" and data[field] not in JOB_STATUSES:
                return jsonify({
                    "error": f"Invalid status. Must be one of: {', '.join(JOB_STATUSES)}"
                }), 400
            update_data[field] = data[field]

    if not update_data:
        return jsonify({"error": "No valid fields to update"}), 400

    # Add updated_at timestamp
    update_data["updatedAt"] = datetime.utcnow()

    # Update the job
    result = collection.update_one(
        {"_id": object_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404

    # Return updated job
    job = collection.find_one({"_id": object_id})
    return jsonify({
        "success": True,
        "job": serialize_job(job)
    })


@app.route("/api/locations", methods=["GET"])
def get_locations():
    """
    Get unique locations from the database with counts.

    Returns:
        JSON with locations array sorted by count descending
    """
    db = get_db()
    collection = db["level-2"]

    # Use aggregation to get unique locations with counts
    pipeline = [
        {"$match": {"location": {"$exists": True, "$ne": None, "$ne": ""}}},
        {"$group": {"_id": "$location", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$project": {"location": "$_id", "count": 1, "_id": 0}},
    ]

    locations = list(collection.aggregate(pipeline))

    return jsonify({"locations": locations})


@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Get database statistics."""
    db = get_db()

    level1_count = db["level-1"].count_documents({})
    level2_count = db["level-2"].count_documents({})

    # Count by status
    status_counts = {}
    for status in JOB_STATUSES:
        count = db["level-2"].count_documents({"status": status})
        if count > 0:
            status_counts[status] = count

    # Count jobs without status
    no_status_count = db["level-2"].count_documents({
        "$or": [
            {"status": {"$exists": False}},
            {"status": None},
            {"status": ""}
        ]
    })
    if no_status_count > 0:
        status_counts["(no status)"] = no_status_count

    return jsonify({
        "level1_count": level1_count,
        "level2_count": level2_count,
        "status_counts": status_counts,
    })


# ============================================================================
# HTML Routes (HTMX-powered)
# ============================================================================

@app.route("/")
def index():
    """Render the main job table page."""
    return render_template("index.html", statuses=JOB_STATUSES)


@app.route("/partials/job-rows", methods=["GET"])
def job_rows_partial():
    """
    HTMX partial: Return only the table rows for job data.

    Used for HTMX-powered search, sort, and pagination updates.
    """
    # Reuse the list_jobs logic
    response = list_jobs()
    data = response.get_json()

    return render_template(
        "partials/job_rows.html",
        jobs=data["jobs"],
        pagination=data["pagination"],
        statuses=JOB_STATUSES,
        current_sort=request.args.get("sort", "createdAt"),
        current_direction=request.args.get("direction", "desc"),
        current_query=request.args.get("query", ""),
        current_page_size=int(request.args.get("page_size", 10)),
        current_date_from=request.args.get("date_from", ""),
        current_date_to=request.args.get("date_to", ""),
        current_locations=request.args.getlist("locations"),
    )


@app.route("/partials/pagination", methods=["GET"])
def pagination_partial():
    """HTMX partial: Return pagination controls."""
    response = list_jobs()
    data = response.get_json()

    return render_template(
        "partials/pagination.html",
        pagination=data["pagination"],
        current_sort=request.args.get("sort", "createdAt"),
        current_direction=request.args.get("direction", "desc"),
        current_query=request.args.get("query", ""),
        current_page_size=int(request.args.get("page_size", 10)),
    )


@app.route("/job/<job_id>")
def job_detail(job_id: str):
    """Render the job detail page."""
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return render_template("error.html", error="Invalid job ID format"), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return render_template("error.html", error="Job not found"), 404

    return render_template(
        "job_detail.html",
        job=serialize_job(job),
        statuses=JOB_STATUSES
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    print(f"Starting Job Search UI on http://localhost:{port}")
    print(f"MongoDB URI: {MONGO_URI[:30]}...")

    app.run(host="0.0.0.0", port=port, debug=debug)
