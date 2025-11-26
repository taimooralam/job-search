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
from functools import wraps
from typing import Any, Dict, List, Optional

import requests
from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pymongo import ASCENDING, DESCENDING, MongoClient

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Import and register blueprints
try:
    from runner import runner_bp
    print(f"✅ Imported runner blueprint")
    app.register_blueprint(runner_bp)
    print(f"✅ Registered runner blueprint with prefix: {runner_bp.url_prefix}")

    # Count runner routes in app
    runner_routes = [str(rule) for rule in app.url_map.iter_rules() if 'runner' in str(rule)]
    print(f"✅ App now has {len(runner_routes)} runner routes")
    for route in runner_routes:
        print(f"   - {route}")
except Exception as e:
    print(f"❌ Error registering runner blueprint: {e}")
    import traceback
    traceback.print_exc()

# Session configuration
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV", "development") == "production"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 31  # 31 days

# Authentication configuration
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "change-me-in-production")

# MongoDB configuration
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/jobs")

# Job status whitelist
JOB_STATUSES = [
    "not processed",
    "marked for applying",
    "ready for applying",
    "to be deleted",
    "discarded",
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


def sanitize_for_path(text: str) -> str:
    """
    Sanitize text for use in filesystem paths.

    Removes special characters (except word chars, spaces, hyphens)
    and replaces spaces with underscores.

    Args:
        text: Raw text (company name, job title, etc.)

    Returns:
        Sanitized string safe for filesystem paths

    Example:
        >>> sanitize_for_path("Director of Engineering (Software)")
        "Director_of_Engineering__Software_"
    """
    import re
    # Remove special characters except word characters, spaces, and hyphens
    cleaned = re.sub(r'[^\w\s-]', '_', text)
    # Replace spaces with underscores
    return cleaned.replace(" ", "_")


# ============================================================================
# Authentication
# ============================================================================

def login_required(f):
    """
    Decorator to require authentication for routes.

    Redirects to login page if user is not authenticated.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# API Endpoints
# ============================================================================

@app.route("/api/jobs", methods=["GET"])
@login_required
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

    # Status filter (can be multiple values)
    # Default: exclude 'discarded', 'applied', 'interview scheduled'
    statuses = request.args.getlist("statuses")
    if not statuses:
        # If no statuses specified, use default exclusion list
        statuses = [s for s in JOB_STATUSES if s not in ["discarded", "applied", "interview scheduled"]]

    # Validate page_size
    if page_size not in [5, 10, 50, 100]:
        page_size = 10

    # Build MongoDB query
    mongo_query: Dict[str, Any] = {}
    and_conditions = []

    # Free-text search
    if search_query:
        # Search across multiple fields
        search_or = [
            {"title": {"$regex": search_query, "$options": "i"}},
            {"company": {"$regex": search_query, "$options": "i"}},
            {"location": {"$regex": search_query, "$options": "i"}},
            {"jobId": {"$regex": search_query, "$options": "i"}},
        ]
        and_conditions.append({"$or": search_or})

    # Date range filter - prefer datetime inputs for precision, fall back to date inputs
    datetime_from = request.args.get("datetime_from", "").strip()
    datetime_to = request.args.get("datetime_to", "").strip()

    # Use datetime inputs if available, otherwise use date inputs
    effective_from = datetime_from if datetime_from else date_from
    effective_to = datetime_to if datetime_to else date_to

    if effective_from or effective_to:
        date_filter: Dict[str, str] = {}
        if effective_from:
            # If already has time component, use as-is; otherwise append start of day
            if 'T' in effective_from:
                date_filter["$gte"] = effective_from
            else:
                date_filter["$gte"] = f"{effective_from}T00:00:00.000Z"
        if effective_to:
            # If already has time component, use as-is; otherwise append end of day
            if 'T' in effective_to:
                date_filter["$lte"] = effective_to
            else:
                date_filter["$lte"] = f"{effective_to}T23:59:59.999Z"
        and_conditions.append({"createdAt": date_filter})

    # Location filter (multi-select)
    if locations:
        and_conditions.append({"location": {"$in": locations}})

    # Status filter (multi-select with default exclusions)
    # Note: null/missing status means "not processed"
    if statuses:
        if "not processed" in statuses:
            # Include explicit "not processed" OR null/empty/missing status
            status_or = [
                {"status": {"$in": statuses}},
                {"status": {"$exists": False}},
                {"status": None},
                {"status": ""}
            ]
            and_conditions.append({"$or": status_or})
        else:
            # Only match exact status values
            and_conditions.append({"status": {"$in": statuses}})

    # Combine all conditions with $and if there are multiple
    if len(and_conditions) > 1:
        mongo_query["$and"] = and_conditions
    elif len(and_conditions) == 1:
        # If only one condition, use it directly
        mongo_query = and_conditions[0]

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
@login_required
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
@login_required
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
@login_required
def get_statuses():
    """Return the list of valid job statuses."""
    return jsonify({"statuses": JOB_STATUSES})


@app.route("/api/jobs/<job_id>", methods=["GET"])
@login_required
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
@login_required
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
    editable_fields = [
        "status", "remarks", "notes", "priority",
        "company", "title", "location", "score", "url", "jobUrl",
        "cover_letter"  # Added for Module 3: Cover Letter Editing
    ]
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
@login_required
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
@login_required
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


@app.route("/api/health", methods=["GET"])
@login_required
def get_health():
    """Get health status of all services."""
    health_data = {}

    # Check VPS Runner
    try:
        runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
        response = requests.get(f"{runner_url}/health", timeout=5)
        health_data["vps"] = {
            "status": "healthy" if response.status_code == 200 else "unhealthy",
            "url": runner_url
        }
    except Exception as e:
        health_data["vps"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check MongoDB
    try:
        db = get_db()
        # Try a simple operation
        db.command("ping")
        health_data["mongodb"] = {
            "status": "healthy",
            "uri": os.getenv("MONGODB_URI", "").split("@")[-1] if "@" in os.getenv("MONGODB_URI", "") else "local"
        }
    except Exception as e:
        health_data["mongodb"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check n8n (if configured)
    n8n_url = os.getenv("N8N_URL", "")
    if n8n_url:
        try:
            response = requests.get(f"{n8n_url}/healthz", timeout=5)
            health_data["n8n"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "url": n8n_url
            }
        except Exception as e:
            health_data["n8n"] = {
                "status": "unhealthy",
                "error": str(e)
            }

    return jsonify(health_data)


# ============================================================================
# Authentication Routes
# ============================================================================

@app.route("/login", methods=["GET", "POST"])
def login_page():
    """Handle login page and authentication."""
    if request.method == "GET":
        # Show login form
        return render_template("login.html", error=None)

    # Handle POST - check password
    password = request.form.get("password", "")
    if password == LOGIN_PASSWORD:
        session["authenticated"] = True
        session.permanent = True
        return redirect(url_for("index"))
    else:
        return render_template("login.html", error="Invalid password"), 401


@app.route("/logout", methods=["POST"])
def logout():
    """Handle logout."""
    session.clear()
    return redirect(url_for("login_page"))


# ============================================================================
# HTML Routes (HTMX-powered)
# ============================================================================

@app.route("/")
@login_required
def index():
    """Render the main job table page."""
    return render_template("index.html", statuses=JOB_STATUSES)


@app.route("/partials/job-rows", methods=["GET"])
@login_required
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
        current_statuses=request.args.getlist("statuses"),
    )


@app.route("/partials/pagination", methods=["GET"])
@login_required
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
@login_required
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

    # Backward compatibility: migrate old 'contacts' field to new format
    if job and 'contacts' in job and not job.get('primary_contacts') and not job.get('secondary_contacts'):
        # Split contacts: first 4 as primary, rest as secondary
        all_contacts = job.get('contacts', [])
        job['primary_contacts'] = all_contacts[:4]
        job['secondary_contacts'] = all_contacts[4:]

    # Load CV content from MongoDB (not filesystem)
    serialized_job = serialize_job(job)
    has_cv = False
    cv_content = None

    # Check if CV was generated by pipeline (stored in MongoDB)
    if job.get("cv_text"):
        has_cv = True
        cv_content = job.get("cv_text")  # Markdown CV from pipeline
        serialized_job["has_cv"] = True
        serialized_job["cv_content"] = cv_content

    return render_template(
        "job_detail.html",
        job=serialized_job,
        statuses=JOB_STATUSES
    )


@app.route("/api/jobs/<job_id>/cv")
@login_required
def get_job_cv(job_id: str):
    """Serve the HTML CV for a job."""
    from flask import send_file
    from pathlib import Path

    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Build CV path
    if not job.get("company") or not job.get("title"):
        return jsonify({"error": "Job missing company or title"}), 400

    company_clean = sanitize_for_path(job["company"])
    title_clean = sanitize_for_path(job["title"])
    cv_path = Path("../applications") / company_clean / title_clean / "CV.html"

    if not cv_path.exists():
        return jsonify({"error": "CV not found"}), 404

    return send_file(cv_path, mimetype="text/html")


@app.route("/api/jobs/<job_id>/cv", methods=["PUT"])
@login_required
def update_job_cv(job_id: str):
    """Update the Markdown CV content after editing."""
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Get updated Markdown content from request
    data = request.get_json()
    cv_text = data.get("cv_text")

    if not cv_text:
        return jsonify({"error": "Missing cv_text"}), 400

    # Save to MongoDB
    try:
        collection.update_one(
            {"_id": object_id},
            {"$set": {"cv_text": cv_text, "updatedAt": datetime.utcnow()}}
        )
        return jsonify({"success": True, "message": "CV updated successfully"})
    except Exception as e:
        return jsonify({"error": f"Failed to save CV: {str(e)}"}), 500


@app.route("/api/jobs/<job_id>/cv/pdf", methods=["POST"])
@login_required
def generate_cv_pdf(job_id: str):
    """Generate PDF from HTML CV."""
    from pathlib import Path

    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Build CV path
    if not job.get("company") or not job.get("title"):
        return jsonify({"error": "Job missing company or title"}), 400

    company_clean = sanitize_for_path(job["company"])
    title_clean = sanitize_for_path(job["title"])
    cv_html_path = Path("../applications") / company_clean / title_clean / "CV.html"
    cv_pdf_path = Path("../applications") / company_clean / title_clean / "CV.pdf"

    if not cv_html_path.exists():
        return jsonify({"error": "HTML CV not found"}), 404

    # Generate PDF using playwright
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            # Load the HTML file
            page.goto(f"file://{cv_html_path.absolute()}")

            # Generate PDF with print media
            page.pdf(
                path=str(cv_pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"}
            )

            browser.close()

        return jsonify({
            "success": True,
            "message": "PDF generated successfully",
            "pdf_path": str(cv_pdf_path)
        })
    except Exception as e:
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/api/jobs/<job_id>/cv/download")
@login_required
def download_cv_pdf(job_id: str):
    """Download the CV PDF."""
    from flask import send_file
    from pathlib import Path

    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Build PDF path
    if not job.get("company") or not job.get("title"):
        return jsonify({"error": "Job missing company or title"}), 400

    company_clean = sanitize_for_path(job["company"])
    title_clean = sanitize_for_path(job["title"])
    cv_pdf_path = Path("../applications") / company_clean / title_clean / "CV.pdf"

    if not cv_pdf_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    # Send file for download
    return send_file(
        cv_pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"CV_{company_clean}_{title_clean}.pdf"
    )


@app.route("/api/jobs/<job_id>/cover-letter/pdf", methods=["POST"])
@login_required
def generate_cover_letter_pdf(job_id: str):
    """Generate PDF from cover letter text."""
    from pathlib import Path
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_LEFT

    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Get cover letter text
    cover_letter = job.get("cover_letter")
    if not cover_letter:
        return jsonify({"error": "No cover letter found"}), 404

    # Build output path
    if not job.get("company") or not job.get("title"):
        return jsonify({"error": "Job missing company or title"}), 400

    company_clean = sanitize_for_path(job["company"])
    title_clean = sanitize_for_path(job["title"])

    # Use /tmp for serverless environments (Vercel), fallback to ../applications for local
    import tempfile
    is_serverless = os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")

    if is_serverless:
        # Write to /tmp in serverless environments
        pdf_path = Path(tempfile.gettempdir()) / f"cover_letter_{company_clean}_{title_clean}.pdf"
    else:
        # Write to applications directory locally
        output_dir = Path("../applications") / company_clean / title_clean
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "cover_letter.pdf"

    try:
        # Create PDF using ReportLab
        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            topMargin=1*inch,
            bottomMargin=1*inch,
            leftMargin=1*inch,
            rightMargin=1*inch
        )

        # Prepare styles
        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontSize=11,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=12
        )

        # Build content
        story = []

        # Split cover letter into paragraphs and escape HTML entities
        import html
        paragraphs = cover_letter.split('\n\n')
        for para in paragraphs:
            if para.strip():
                # Escape HTML entities to prevent ReportLab parsing issues
                safe_para = html.escape(para.strip())
                story.append(Paragraph(safe_para, body_style))
                story.append(Spacer(1, 12))

        # Build PDF
        doc.build(story)

        return jsonify({
            "success": True,
            "message": "Cover letter PDF generated successfully",
            "pdf_path": str(pdf_path)
        })

    except Exception as e:
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/api/jobs/<job_id>/cover-letter/download")
@login_required
def download_cover_letter_pdf(job_id: str):
    """Download the cover letter PDF."""
    from flask import send_file
    from pathlib import Path

    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Build PDF path
    if not job.get("company") or not job.get("title"):
        return jsonify({"error": "Job missing company or title"}), 400

    company_clean = sanitize_for_path(job["company"])
    title_clean = sanitize_for_path(job["title"])

    # Check /tmp first (serverless), then applications directory (local)
    import tempfile
    is_serverless = os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")

    if is_serverless:
        pdf_path = Path(tempfile.gettempdir()) / f"cover_letter_{company_clean}_{title_clean}.pdf"
    else:
        pdf_path = Path("../applications") / company_clean / title_clean / "cover_letter.pdf"

    if not pdf_path.exists():
        return jsonify({"error": "PDF not found. Generate it first."}), 404

    # Send file for download
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"CoverLetter_{company_clean}_{title_clean}.pdf"
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    print(f"Starting Job Search UI on http://localhost:{port}")
    print(f"MongoDB URI: {MONGO_URI[:30]}...")

    # Debug: Print registered routes
    print("\n🔍 Registered routes:")
    for rule in app.url_map.iter_rules():
        if 'runner' in str(rule):
            print(f"  ✅ {rule.methods} {rule}")
    print()

    app.run(host="0.0.0.0", port=port, debug=debug)
