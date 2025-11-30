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

import logging
import os
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List, Optional

import requests
from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import ConfigurationError, ServerSelectionTimeoutError

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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
flask_secret_key = os.getenv("FLASK_SECRET_KEY")

if not flask_secret_key:
    # In production (Vercel), this is a critical error
    if os.getenv("VERCEL") == "1":
        raise RuntimeError(
            "CRITICAL: FLASK_SECRET_KEY not set in Vercel environment variables. "
            "Sessions will be invalidated on every cold start. "
            "Set FLASK_SECRET_KEY in Vercel dashboard: Settings → Environment Variables"
        )
    else:
        # Local development: Generate random key with warning
        print("⚠️  WARNING: FLASK_SECRET_KEY not set. Generating random key (sessions will not persist between restarts)")
        flask_secret_key = os.urandom(24).hex()

app.secret_key = flask_secret_key

# Cookie security settings
app.config["SESSION_COOKIE_HTTPONLY"] = True

# Detect HTTPS: Vercel sets VERCEL=1 and uses HTTPS by default
is_production = os.getenv("VERCEL") == "1" or os.getenv("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_SECURE"] = is_production

# SameSite policy: Use "None" for HTTPS (required for fetch POST), "Lax" for HTTP
# Note: SameSite=None REQUIRES Secure=True (only works on HTTPS)
if is_production:
    app.config["SESSION_COOKIE_SAMESITE"] = "None"  # Required for fetch POST on HTTPS
else:
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # For local development (HTTP)

app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 31  # 31 days

# Debug logging for session configuration
if os.getenv("VERCEL") == "1":
    print(f"🔍 Session Config: SECURE={app.config['SESSION_COOKIE_SECURE']}, SAMESITE={app.config['SESSION_COOKIE_SAMESITE']}")

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
    """
    Get MongoDB database connection with retry logic for DNS issues.

    Common after VPN disconnect: DNS servers may be temporarily unavailable.
    Retry with exponential backoff to allow DNS cache to flush.

    Returns:
        MongoDB database instance

    Raises:
        ConfigurationError: If MongoDB connection fails after retries
    """
    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            # Set shorter timeouts to fail fast (5s instead of 30s default)
            client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=5000,
                socketTimeoutMS=5000
            )

            # Test connection with ping
            client.admin.command('ping')

            return client["jobs"]

        except (ConfigurationError, ServerSelectionTimeoutError) as e:
            error_str = str(e)
            is_dns_error = (
                "DNS" in error_str or
                "resolution lifetime expired" in error_str or
                "getaddrinfo failed" in error_str
            )

            if is_dns_error:
                if attempt < max_retries - 1:
                    print(f"⚠️  DNS resolution failed (attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay}s...")
                    print(f"   Hint: Run 'sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder' to clear DNS cache")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"❌ MongoDB connection failed after {max_retries} attempts")
                    print(f"   Error: {e}")
                    print(f"   Troubleshooting:")
                    print(f"   1. Flush DNS cache: sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder")
                    print(f"   2. Change DNS servers to 8.8.8.8 (Google DNS) in System Settings")
                    print(f"   3. Verify MongoDB connection: mongosh \"$MONGODB_URI\" --eval \"db.adminCommand('ping')\"")
                    print(f"   4. Restart Flask app after fixing DNS")
                    raise
            else:
                # Non-DNS error, fail immediately
                raise

    raise ConfigurationError("MongoDB connection failed - DNS resolution issue")


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

    For API routes (/api/*): Returns JSON 401 if not authenticated
    For page routes: Redirects to login page if not authenticated
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            # For API endpoints, return JSON error instead of redirect
            if request.path.startswith('/api/'):
                return jsonify({"error": "Not authenticated"}), 401
            # For page routes, redirect to login
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


@app.route("/api/jobs/<job_id>/cv-editor/pdf", methods=["POST"])
@login_required
def generate_cv_pdf_from_editor(job_id: str):
    """
    Proxy PDF generation request to runner service (Phase 4).

    The runner service (VPS with Playwright installed) handles PDF generation.
    This endpoint proxies the request and streams the response back to the user.

    Returns:
        PDF file streamed from runner service
    """
    import requests
    from flask import send_file
    from io import BytesIO

    # Get runner service URL from environment
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    endpoint = f"{runner_url}/api/jobs/{job_id}/cv-editor/pdf"

    # Get authentication token for runner service
    # IMPORTANT: Must match runner service's RUNNER_API_SECRET env var
    runner_token = os.getenv("RUNNER_API_SECRET")
    headers = {}
    if runner_token:
        headers["Authorization"] = f"Bearer {runner_token}"
        logger.info(f"PDF generation request for job {job_id} - authentication configured")
    else:
        logger.warning(f"RUNNER_API_SECRET not set - runner service may reject request for job {job_id}")

    try:
        logger.info(f"Requesting PDF generation from {endpoint}")

        # Proxy request to runner service
        response = requests.post(
            endpoint,
            headers=headers,
            timeout=30,  # 30 second timeout for PDF generation
            stream=True
        )

        logger.info(f"Runner service responded with status {response.status_code}")

        if response.status_code == 401:
            logger.error(f"Authentication failed for job {job_id} - check RUNNER_API_SECRET configuration")
            return jsonify({
                "error": "Authentication failed. Please contact support.",
                "detail": "RUNNER_API_SECRET not configured correctly"
            }), 401

        if response.status_code != 200:
            # Try to get error message from runner
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", "PDF generation failed")
                logger.error(f"PDF generation failed for job {job_id}: {error_msg}")
            except:
                error_msg = f"PDF generation failed with status {response.status_code}"
                logger.error(f"PDF generation failed for job {job_id}: status {response.status_code}, body: {response.text[:200]}")

            return jsonify({"error": error_msg}), response.status_code

        # Extract filename from Content-Disposition header
        content_disposition = response.headers.get('Content-Disposition', '')
        filename = "CV.pdf"  # Default
        if 'filename=' in content_disposition:
            # Parse filename from header
            import re
            match = re.search(r'filename="?([^"]+)"?', content_disposition)
            if match:
                filename = match.group(1)

        logger.info(f"PDF generated successfully for job {job_id}, filename: {filename}")

        # Stream PDF back to user
        return send_file(
            BytesIO(response.content),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except requests.Timeout:
        logger.error(f"PDF generation timed out for job {job_id} after 30 seconds")
        return jsonify({
            "error": "PDF generation timed out (>30s). Please try again.",
            "detail": "The runner service took too long to respond"
        }), 504
    except requests.ConnectionError as e:
        logger.error(f"Failed to connect to runner service at {runner_url}: {str(e)}")
        return jsonify({
            "error": "PDF service unavailable. Please try again later.",
            "detail": f"Cannot connect to runner service at {runner_url}"
        }), 503
    except requests.RequestException as e:
        logger.error(f"Request to runner service failed for job {job_id}: {str(e)}")
        return jsonify({
            "error": "Failed to connect to runner service",
            "detail": str(e)
        }), 503
    except Exception as e:
        logger.exception(f"Unexpected error during PDF generation for job {job_id}")
        return jsonify({
            "error": f"PDF generation failed: {str(e)}",
            "detail": "An unexpected error occurred"
        }), 500


@app.route("/api/jobs/<job_id>/export-page-pdf", methods=["POST"])
@login_required
def export_job_page_to_pdf(job_id: str):
    """
    Export job posting URL to PDF (Bug #7 Phase 2).

    Proxies request to runner service which uses Playwright to capture the page.
    This allows users to save job postings that may disappear.

    Expected JSON body: {"url": "https://..."}

    Returns:
        PDF file streamed from runner service
    """
    import requests
    from flask import send_file
    from io import BytesIO

    # Get URL from request body
    data = request.get_json() or {}
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    if not url.startswith(('http://', 'https://')):
        return jsonify({'error': 'URL must start with http:// or https://'}), 400

    # Get runner service URL from environment
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    endpoint = f"{runner_url}/api/url-to-pdf"

    # Get authentication token for runner service
    runner_token = os.getenv("RUNNER_API_SECRET")
    headers = {'Content-Type': 'application/json'}
    if runner_token:
        headers["Authorization"] = f"Bearer {runner_token}"
        logger.info(f"URL-to-PDF request for job {job_id} - authentication configured")
    else:
        logger.warning(f"RUNNER_API_SECRET not set - runner service may reject request for job {job_id}")

    try:
        logger.info(f"Requesting URL-to-PDF from {endpoint} for URL: {url[:80]}...")

        # Proxy request to runner service
        response = requests.post(
            endpoint,
            headers=headers,
            json={'url': url},
            timeout=60,  # 60 second timeout for page load + PDF generation
            stream=True
        )

        logger.info(f"Runner service responded with status {response.status_code}")

        if response.status_code == 401:
            logger.error(f"Authentication failed for job {job_id} - check RUNNER_API_SECRET configuration")
            return jsonify({
                "error": "Authentication failed. Please contact support.",
                "detail": "RUNNER_API_SECRET not configured correctly"
            }), 401

        if response.status_code != 200:
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", "PDF generation failed")
                logger.error(f"URL-to-PDF failed for job {job_id}: {error_msg}")
            except:
                error_msg = f"PDF generation failed with status {response.status_code}"
                logger.error(f"URL-to-PDF failed for job {job_id}: status {response.status_code}")

            return jsonify({"error": error_msg}), response.status_code

        # Extract filename from Content-Disposition header
        content_disposition = response.headers.get('Content-Disposition', '')
        filename = "job_posting.pdf"
        if 'filename=' in content_disposition:
            import re
            match = re.search(r'filename="?([^"]+)"?', content_disposition)
            if match:
                filename = match.group(1)

        logger.info(f"URL-to-PDF generated successfully for job {job_id}, filename: {filename}")

        # Stream PDF back to user
        return send_file(
            BytesIO(response.content),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except requests.Timeout:
        logger.error(f"URL-to-PDF timed out for job {job_id} after 60 seconds")
        return jsonify({
            "error": "PDF generation timed out (>60s). The site may be slow.",
            "detail": "The runner service took too long to respond"
        }), 504
    except requests.ConnectionError as e:
        logger.error(f"Failed to connect to runner service at {runner_url}: {str(e)}")
        return jsonify({
            "error": "PDF service unavailable. Please try again later.",
            "detail": f"Cannot connect to runner service at {runner_url}"
        }), 503
    except Exception as e:
        logger.exception(f"Unexpected error during URL-to-PDF for job {job_id}")
        return jsonify({
            "error": f"PDF generation failed: {str(e)}",
            "detail": "An unexpected error occurred"
        }), 500


def build_pdf_html_template(
    content_html: str,
    font_family: str,
    font_size: int,
    line_height: float,
    header_text: str = "",
    footer_text: str = ""
) -> str:
    """
    Build complete HTML document for PDF generation with embedded styles.

    Includes:
    - Google Fonts link for font embedding
    - CSS styles for formatting
    - Header/footer if present
    - Content HTML from TipTap

    Args:
        content_html: HTML content from TipTap JSON
        font_family: Font family name (e.g., "Inter", "Merriweather")
        font_size: Font size in points
        line_height: Line height multiplier (e.g., 1.15, 1.5)
        header_text: Optional header text
        footer_text: Optional footer text

    Returns:
        Complete HTML document string
    """
    # Build Google Fonts URL (support multiple fonts)
    # Common Phase 2 fonts that need embedding
    all_fonts = [
        font_family,
        'Inter',  # Default body font
        'Roboto', 'Open Sans', 'Lato', 'Montserrat',  # Sans-serif
        'Merriweather', 'Playfair Display', 'Lora',  # Serif
    ]
    fonts_param = '|'.join(set(all_fonts))  # Deduplicate
    google_fonts_url = f"https://fonts.googleapis.com/css2?family={fonts_param.replace(' ', '+')}:wght@400;700&display=swap"

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CV</title>

    <!-- Google Fonts for embedding -->
    <link href="{google_fonts_url}" rel="stylesheet">

    <style>
        @page {{
            size: Letter;
            margin: 0;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: '{font_family}', sans-serif;
            font-size: {font_size}pt;
            line-height: {line_height};
            color: #1a1a1a;
            background: white;
        }}

        .page-container {{
            width: 100%;
            height: 100%;
            padding: 0;
            margin: 0;
        }}

        .header {{
            text-align: center;
            font-size: 9pt;
            color: #666;
            padding: 8px 0;
            border-bottom: 1px solid #ddd;
        }}

        .footer {{
            text-align: center;
            font-size: 9pt;
            color: #666;
            padding: 8px 0;
            border-top: 1px solid #ddd;
            position: fixed;
            bottom: 0;
            width: 100%;
        }}

        .content {{
            padding: 0;
        }}

        /* Typography */
        h1, h2, h3, h4, h5, h6 {{
            font-weight: 700;
            margin-top: 16px;
            margin-bottom: 8px;
        }}

        h1 {{ font-size: {font_size * 1.8}pt; }}
        h2 {{ font-size: {font_size * 1.5}pt; }}
        h3 {{ font-size: {font_size * 1.3}pt; }}

        p {{
            margin-bottom: 8px;
        }}

        ul, ol {{
            margin-left: 20px;
            margin-bottom: 8px;
        }}

        li {{
            margin-bottom: 4px;
        }}

        /* Preserve TipTap formatting */
        strong {{ font-weight: 700; }}
        em {{ font-style: italic; }}
        u {{ text-decoration: underline; }}

        mark {{
            background-color: #ffff00;
            padding: 2px 4px;
        }}

        /* Text alignment */
        .text-left {{ text-align: left; }}
        .text-center {{ text-align: center; }}
        .text-right {{ text-align: right; }}
        .text-justify {{ text-align: justify; }}
    </style>
</head>
<body>
    <div class="page-container">
        """

    # Add header if present
    if header_text:
        html += f"""
        <div class="header">
            {header_text}
        </div>
        """

    # Add main content
    html += f"""
        <div class="content">
            {content_html}
        </div>
        """

    # Add footer if present
    if footer_text:
        html += f"""
        <div class="footer">
            {footer_text}
        </div>
        """

    html += """
    </div>
</body>
</html>
    """

    return html


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
# CV Rich Text Editor API Endpoints
# ============================================================================

def tiptap_json_to_html(tiptap_content: dict) -> str:
    """
    Convert TipTap JSON to HTML for display compatibility.

    Args:
        tiptap_content: TipTap document JSON

    Returns:
        HTML string
    """
    if not tiptap_content or tiptap_content.get("type") != "doc":
        return ""

    html_parts = []

    def process_node(node):
        node_type = node.get("type")
        content = node.get("content", [])
        attrs = node.get("attrs", {})
        marks = node.get("marks", [])

        # Process text nodes
        if node_type == "text":
            text = node.get("text", "")
            # Apply marks (bold, italic, etc.)
            for mark in marks:
                mark_type = mark.get("type")
                if mark_type == "bold":
                    text = f"<strong>{text}</strong>"
                elif mark_type == "italic":
                    text = f"<em>{text}</em>"
                elif mark_type == "underline":
                    text = f"<u>{text}</u>"
                elif mark_type == "textStyle":
                    # Handle font family, font size, color
                    style_parts = []
                    mark_attrs = mark.get("attrs", {})
                    if mark_attrs.get("fontFamily"):
                        style_parts.append(f"font-family: {mark_attrs['fontFamily']}")
                    if mark_attrs.get("fontSize"):
                        style_parts.append(f"font-size: {mark_attrs['fontSize']}")
                    if mark_attrs.get("color"):
                        style_parts.append(f"color: {mark_attrs['color']}")
                    if style_parts:
                        text = f"<span style='{'; '.join(style_parts)}'>{text}</span>"
                elif mark_type == "highlight":
                    color = mark.get("attrs", {}).get("color", "yellow")
                    text = f"<mark style='background-color: {color}'>{text}</mark>"
            return text

        # Process block nodes
        elif node_type == "paragraph":
            inner_html = "".join(process_node(child) for child in content)
            text_align = attrs.get("textAlign", "left")
            if text_align != "left":
                style_attr = f' style="text-align: {text_align};"'
                return f"<p{style_attr}>{inner_html}</p>"
            return f"<p>{inner_html}</p>"

        elif node_type == "heading":
            level = attrs.get("level", 1)
            inner_html = "".join(process_node(child) for child in content)
            text_align = attrs.get("textAlign", "left")
            if text_align != "left":
                style_attr = f' style="text-align: {text_align};"'
                return f"<h{level}{style_attr}>{inner_html}</h{level}>"
            return f"<h{level}>{inner_html}</h{level}>"

        elif node_type == "bulletList":
            items_html = "".join(process_node(child) for child in content)
            return f"<ul>{items_html}</ul>"

        elif node_type == "orderedList":
            items_html = "".join(process_node(child) for child in content)
            return f"<ol>{items_html}</ol>"

        elif node_type == "listItem":
            inner_html = "".join(process_node(child) for child in content)
            return f"<li>{inner_html}</li>"

        elif node_type == "hardBreak":
            return "<br>"

        elif node_type == "horizontalRule":
            return "<hr>"

        else:
            # Unknown node type, process children
            return "".join(process_node(child) for child in content)

    # Process all top-level nodes
    for node in tiptap_content.get("content", []):
        html_parts.append(process_node(node))

    return "".join(html_parts)


@app.route("/api/jobs/<job_id>/cv-editor", methods=["GET"])
@login_required
def get_cv_editor_state(job_id: str):
    """
    Get CV editor state for a job.

    Returns:
        JSON with editor_state containing TipTap JSON document
    """
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    job = collection.find_one({"_id": object_id})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    editor_state = job.get("cv_editor_state")

    # Validate editor state structure
    is_valid_state = (
        editor_state
        and isinstance(editor_state, dict)
        and "content" in editor_state
        and isinstance(editor_state["content"], dict)
        and editor_state["content"].get("type") == "doc"
    )

    # If no valid editor state exists, migrate from cv_text (markdown)
    if not is_valid_state and job.get("cv_text"):
        editor_state = migrate_cv_text_to_editor_state(job.get("cv_text"))

        # Note: We don't persist the migrated state on GET to avoid unnecessary writes
        # Migration is cheap and happens on-demand
        # Persistence happens when user explicitly saves via PUT endpoint

    # If still no state, return default empty state (Phase 3 defaults)
    if not editor_state:
        editor_state = {
            "version": 1,
            "content": {
                "type": "doc",
                "content": []
            },
            "documentStyles": {
                "fontFamily": "Source Sans 3",  # Professional humanist sans for body
                "headingFont": "Playfair Display",  # Refined serif for headings
                "fontSize": 11,  # 11pt body text (professional resume standard)
                "lineHeight": 1.5,  # Improved readability spacing
                "margins": {
                    "top": 1.0,  # Standard 1-inch margins
                    "right": 1.0,
                    "bottom": 1.0,
                    "left": 1.0
                },
                "pageSize": "letter",
                "colorText": "#1f2a38",  # Near-black for better readability
                "colorMuted": "#4b5563",  # Muted gray for metadata
                "colorAccent": "#0f766e"  # Deep teal for headings/links
            }
        }

    return jsonify({
        "success": True,
        "editor_state": editor_state
    })


@app.route("/api/jobs/<job_id>/cv-editor", methods=["PUT"])
@login_required
def save_cv_editor_state(job_id: str):
    """
    Save CV editor state to MongoDB.

    Request Body:
        version: Editor state version (integer)
        content: TipTap JSON document
        documentStyles: Document-level styles

    Returns:
        JSON with success status and savedAt timestamp
    """
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    data = request.get_json()

    if not data or "content" not in data:
        return jsonify({"error": "Missing content in request body"}), 400

    # Add server timestamp
    data["lastSavedAt"] = datetime.utcnow()

    # Convert TipTap JSON to HTML for backward compatibility with cv_text field
    cv_html = tiptap_json_to_html(data["content"])

    # Update job document with both editor state and HTML representation
    result = collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "cv_editor_state": data,
                "cv_text": cv_html,  # Keep cv_text in sync with editor content
                "updatedAt": datetime.utcnow()
            }
        }
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "success": True,
        "savedAt": data["lastSavedAt"].isoformat()
    })


def migrate_cv_text_to_editor_state(cv_text: str) -> dict:
    """
    Migrate markdown CV text to TipTap editor state.

    Converts markdown to TipTap JSON, parsing line-by-line to handle:
    - Headings (# ## ###)
    - Bullet lists (-)
    - Bold/italic text (**)
    - Regular paragraphs

    Args:
        cv_text: Markdown CV content

    Returns:
        TipTap editor state dictionary
    """
    lines = cv_text.split('\n')
    content = []
    current_list = None
    i = 0

    def parse_inline_marks(text):
        """Parse bold and italic marks from text."""
        marks_content = []
        # Simple regex-based parsing for bold (**text**) and italic (*text*)
        import re

        # For now, just return plain text node
        # TODO: Implement proper inline mark parsing
        return [{"type": "text", "text": text}]

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            # Empty line closes current list
            if current_list:
                content.append(current_list)
                current_list = None
            i += 1
            continue

        # Heading level 1
        if line.startswith('# ') and not line.startswith('##'):
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "heading",
                "attrs": {"level": 1},
                "content": parse_inline_marks(line[2:].strip())
            })

        # Heading level 2
        elif line.startswith('## ') and not line.startswith('###'):
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "heading",
                "attrs": {"level": 2},
                "content": parse_inline_marks(line[3:].strip())
            })

        # Heading level 3
        elif line.startswith('### '):
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "heading",
                "attrs": {"level": 3},
                "content": parse_inline_marks(line[4:].strip())
            })

        # Bullet point
        elif line.startswith('- '):
            list_item = {
                "type": "listItem",
                "content": [{
                    "type": "paragraph",
                    "content": parse_inline_marks(line[2:].strip())
                }]
            }

            if current_list is None:
                current_list = {
                    "type": "bulletList",
                    "content": [list_item]
                }
            else:
                current_list["content"].append(list_item)

        # Regular paragraph
        else:
            if current_list:
                content.append(current_list)
                current_list = None
            content.append({
                "type": "paragraph",
                "content": parse_inline_marks(line)
            })

        i += 1

    # Close any open list at end
    if current_list:
        content.append(current_list)

    return {
        "version": 1,
        "content": {
            "type": "doc",
            "content": content
        },
        "documentStyles": {
            "fontFamily": "Source Sans 3",  # Professional humanist sans for body
            "headingFont": "Playfair Display",  # Refined serif for headings
            "fontSize": 11,  # 11pt body text (professional resume standard)
            "lineHeight": 1.5,  # Improved readability spacing
            "margins": {
                "top": 1.0,  # Standard 1-inch margins
                "right": 1.0,
                "bottom": 1.0,
                "left": 1.0
            },
            "pageSize": "letter",
            "colorText": "#1f2a38",  # Near-black for better readability
            "colorMuted": "#4b5563",  # Muted gray for metadata
            "colorAccent": "#0f766e"  # Deep teal for headings/links
        }
    }


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
