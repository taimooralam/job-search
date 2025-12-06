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

# Import version (from parent directory)
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from version import __version__
    APP_VERSION = __version__
except ImportError:
    APP_VERSION = "dev"

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


# Context processor to inject version into all templates
@app.context_processor
def inject_version():
    """Inject version info into all templates."""
    return {"version": APP_VERSION}


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

    # GAP-007 Fix: Handle mixed types (strings from n8n, Date objects from other sources)
    # We parse the filter values to datetime objects and will use aggregation with $toDate
    # to normalize the MongoDB field before comparison.
    date_filter_from: Optional[datetime] = None
    date_filter_to: Optional[datetime] = None

    def parse_datetime_filter(dt_str: str, is_end_of_day: bool = False) -> Optional[datetime]:
        """
        Parse date/datetime string to Python datetime for MongoDB comparison.

        Args:
            dt_str: ISO datetime string (with 'T') or date string (YYYY-MM-DD)
            is_end_of_day: If True and dt_str is date-only, use 23:59:59.999999

        Returns:
            datetime object for MongoDB query, or None if parsing fails
        """
        try:
            if 'T' in dt_str:
                # Full ISO datetime: 2025-11-30T14:30:00.000Z or 2025-11-30T14:30:00.709Z
                clean_str = dt_str.replace('Z', '').replace('+00:00', '')
                # Handle milliseconds that may not be exactly 6 digits
                # Python 3.9 fromisoformat is strict about microsecond format
                if '.' in clean_str:
                    base, frac = clean_str.rsplit('.', 1)
                    # Pad or truncate to 6 digits for microseconds
                    frac = frac[:6].ljust(6, '0')
                    clean_str = f"{base}.{frac}"
                return datetime.fromisoformat(clean_str)
            else:
                # Date only: 2025-11-30
                if is_end_of_day:
                    return datetime.fromisoformat(f"{dt_str}T23:59:59.999999")
                else:
                    return datetime.fromisoformat(f"{dt_str}T00:00:00")
        except (ValueError, AttributeError) as e:
            app.logger.warning(f"Failed to parse datetime filter '{dt_str}': {e}")
            return None

    if effective_from:
        date_filter_from = parse_datetime_filter(effective_from, is_end_of_day=False)
    if effective_to:
        date_filter_to = parse_datetime_filter(effective_to, is_end_of_day=True)

    # Location filter (multi-select)
    if locations:
        and_conditions.append({"location": {"$in": locations}})

    # Status filter (multi-select with default exclusions)
    # Note: null/missing status means "not processed"
    # Deduplicate statuses to avoid issues with repeated URL params
    if statuses:
        statuses = list(set(statuses))  # Remove duplicates
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
    sort_order = -1 if sort_direction == "desc" else 1

    # Projection for returned fields
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

    # GAP-007: Use aggregation pipeline for date filtering to handle mixed types
    # MongoDB $toDate normalizes both ISO strings AND Date objects to Date objects
    # This allows hour-level granularity regardless of how createdAt was stored
    use_aggregation = date_filter_from is not None or date_filter_to is not None

    if use_aggregation:
        # Build aggregation pipeline
        pipeline: List[Dict[str, Any]] = []

        # Stage 1: Initial match (non-date filters) - use index if available
        if mongo_query:
            pipeline.append({"$match": mongo_query})

        # Stage 2: Add normalized date field using $toDate
        # $toDate handles: ISO strings, Date objects, timestamps, ObjectIds
        pipeline.append({
            "$addFields": {
                "_normalizedDate": {
                    "$cond": {
                        "if": {"$eq": [{"$type": "$createdAt"}, "string"]},
                        "then": {"$toDate": "$createdAt"},
                        "else": "$createdAt"  # Already a Date object
                    }
                }
            }
        })

        # Stage 3: Filter by normalized date
        date_match: Dict[str, Any] = {}
        if date_filter_from:
            date_match["$gte"] = date_filter_from
        if date_filter_to:
            date_match["$lte"] = date_filter_to
        pipeline.append({"$match": {"_normalizedDate": date_match}})

        # Stage 4: Count total (for pagination) - use $facet for efficiency
        # Note: We use inclusion projection only. The _normalizedDate temp field
        # is automatically excluded since it's not in the projection dict.
        # MongoDB doesn't allow mixing inclusion and exclusion in $project.
        pipeline.append({
            "$facet": {
                "metadata": [{"$count": "total"}],
                "data": [
                    {"$sort": {mongo_sort_field: sort_order}},
                    {"$skip": (page - 1) * page_size},
                    {"$limit": page_size},
                    {"$project": projection}
                ]
            }
        })

        # Execute aggregation with error handling
        try:
            result = list(collection.aggregate(pipeline))
            if result:
                metadata = result[0].get("metadata", [])
                total_count = metadata[0]["total"] if metadata else 0
                jobs_raw = result[0].get("data", [])
            else:
                total_count = 0
                jobs_raw = []
        except Exception as e:
            app.logger.error(f"MongoDB aggregation failed: {e}")
            return jsonify({
                "error": "Database query failed",
                "message": str(e),
                "jobs": [],
                "pagination": {"current_page": 1, "page_size": page_size, "total_count": 0, "total_pages": 1}
            }), 500

        jobs = [serialize_job(job) for job in jobs_raw]
    else:
        # No date filtering - use simpler find() query (more efficient)
        total_count = collection.count_documents(mongo_query)

        skip = (page - 1) * page_size
        cursor = collection.find(mongo_query, projection)
        cursor = cursor.sort(mongo_sort_field, mongo_direction)
        cursor = cursor.skip(skip).limit(page_size)

        jobs = [serialize_job(job) for job in cursor]

    # Calculate pagination
    total_pages = max(1, (total_count + page_size - 1) // page_size)

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

    # GAP-064: Build update data with appliedOn timestamp when status is "applied"
    update_data = {"status": new_status}
    if new_status == "applied":
        update_data["appliedOn"] = datetime.utcnow()
    elif new_status != "applied":
        # Clear appliedOn if status changed FROM applied to something else
        update_data["appliedOn"] = None

    # Update the job
    result = collection.update_one(
        {"_id": object_id},
        {"$set": update_data}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "success": True,
        "job_id": job_id,
        "status": new_status,
        "appliedOn": update_data.get("appliedOn").isoformat() if update_data.get("appliedOn") else None,
    })


@app.route("/api/jobs/score", methods=["POST"])
@login_required
def update_job_score():
    """
    Update job score (GAP-067).

    Request Body:
        job_id: Job _id string
        score: New score value (0-100) or null to clear

    Returns:
        JSON with updated job or error
    """
    db = get_db()
    collection = db["level-2"]

    data = request.get_json()
    job_id = data.get("job_id")
    new_score = data.get("score")

    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    # Validate score (can be null to clear, or 0-100)
    if new_score is not None:
        try:
            new_score = int(new_score)
            if new_score < 0 or new_score > 100:
                return jsonify({"error": "Score must be between 0 and 100"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Score must be a number"}), 400

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job_id format"}), 400

    # Update the job score
    result = collection.update_one(
        {"_id": object_id},
        {"$set": {"score": new_score}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "success": True,
        "job_id": job_id,
        "score": new_score,
    })


@app.route("/api/jobs/status/bulk", methods=["POST"])
@login_required
def update_jobs_status_bulk():
    """
    Update status for multiple jobs at once.

    Request Body:
        job_ids: List of job _id strings
        status: New status value (from whitelist)

    Returns:
        JSON with count of updated jobs or error
    """
    db = get_db()
    collection = db["level-2"]

    data = request.get_json()
    job_ids = data.get("job_ids", [])
    new_status = data.get("status")

    if not job_ids or not isinstance(job_ids, list):
        return jsonify({"error": "job_ids array is required"}), 400

    if not new_status:
        return jsonify({"error": "status is required"}), 400

    if new_status not in JOB_STATUSES:
        return jsonify({
            "error": f"Invalid status. Must be one of: {', '.join(JOB_STATUSES)}"
        }), 400

    # Convert to ObjectIds
    try:
        object_ids = [ObjectId(jid) for jid in job_ids]
    except Exception:
        return jsonify({"error": "Invalid job_id format in array"}), 400

    # GAP-064: Build update data with appliedOn timestamp when status is "applied"
    update_data = {"status": new_status}
    applied_on = None
    if new_status == "applied":
        applied_on = datetime.utcnow()
        update_data["appliedOn"] = applied_on
    else:
        # Clear appliedOn if status changed FROM applied to something else
        update_data["appliedOn"] = None

    # Bulk update
    result = collection.update_many(
        {"_id": {"$in": object_ids}},
        {"$set": update_data}
    )

    return jsonify({
        "success": True,
        "updated_count": result.modified_count,
        "status": new_status,
        "appliedOn": applied_on.isoformat() if applied_on else None,
    })


@app.route("/api/jobs/statuses", methods=["GET"])
@login_required
def get_statuses():
    """Return the list of valid job statuses."""
    return jsonify({"statuses": JOB_STATUSES})


@app.route("/api/jobs/import-linkedin", methods=["POST"])
@login_required
def import_linkedin_job():
    """
    Import a job from LinkedIn by job ID or URL (GAP-065).

    Proxies to VPS runner service to avoid Vercel's timeout limits.

    Request body:
        job_id_or_url: LinkedIn job ID or URL

    Returns:
        JSON with imported job data including MongoDB _id, title, company, and score
    """
    data = request.get_json()
    job_id_or_url = data.get("job_id_or_url", "").strip()

    if not job_id_or_url:
        return jsonify({"error": "job_id_or_url is required"}), 400

    # Proxy to VPS runner service (no timeout limits, stable IP)
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    runner_token = os.getenv("RUNNER_TOKEN", "")

    try:
        logger.info(f"Proxying LinkedIn import to runner: {job_id_or_url}")
        response = requests.post(
            f"{runner_url}/jobs/import-linkedin",
            json={"job_id_or_url": job_id_or_url},
            headers={
                "Authorization": f"Bearer {runner_token}",
                "Content-Type": "application/json",
            },
            timeout=60,  # Allow up to 60 seconds for scraping + scoring
        )

        # Forward the response from runner service
        if response.status_code == 200:
            result = response.json()
            return jsonify(result), 200
        else:
            # Try to get error message from runner
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", f"Runner error: {response.status_code}")
            except Exception:
                error_msg = f"Runner returned status {response.status_code}"

            logger.warning(f"Runner import failed: {error_msg}")
            return jsonify({"error": error_msg}), response.status_code

    except requests.exceptions.Timeout:
        logger.error("Runner service timeout during LinkedIn import")
        return jsonify({"error": "Import timed out. The job may be taking too long to scrape."}), 504

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to runner service")
        return jsonify({"error": "Cannot connect to import service. Please try again later."}), 503

    except Exception as e:
        logger.exception(f"Unexpected error proxying LinkedIn import: {e}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


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


@app.route("/api/dashboard/application-stats", methods=["GET"])
@login_required
def get_application_stats():
    """
    Get job application statistics for dashboard progress bars.

    Returns counts of jobs with status='applied' broken down by time periods:
    - Today (since midnight UTC)
    - This week (last 7 days)
    - This month (last 30 days)
    - Total all time

    Returns:
        JSON with application counts
    """
    db = get_db()
    collection = db["level-2"]

    from datetime import datetime, timedelta

    now = datetime.utcnow()

    # Calculate time boundaries
    today_start = datetime(now.year, now.month, now.day)  # Midnight today UTC
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # GAP-064: Use appliedOn timestamp for accurate application stats
    # appliedOn = when user marked job as "applied" (correct semantic)
    # pipeline_run_at = when pipeline processed (incorrect for this metric)

    # Base query: status = 'applied' and appliedOn exists
    base_query = {
        "status": "applied",
        "appliedOn": {"$exists": True, "$ne": None}
    }

    # Count jobs applied today
    today_query = {**base_query, "appliedOn": {"$gte": today_start}}
    today_count = collection.count_documents(today_query)

    # Count jobs applied this week (last 7 days)
    week_query = {**base_query, "appliedOn": {"$gte": week_start}}
    week_count = collection.count_documents(week_query)

    # Count jobs applied this month (last 30 days)
    month_query = {**base_query, "appliedOn": {"$gte": month_start}}
    month_count = collection.count_documents(month_query)

    # Fallback: Count jobs that were marked applied BEFORE this fix (no appliedOn)
    # These are legacy records - show them in total but not in time-based counts
    legacy_applied = collection.count_documents({
        "status": "applied",
        "$or": [
            {"appliedOn": {"$exists": False}},
            {"appliedOn": None}
        ]
    })

    # Count total jobs applied (all time)
    total_count = collection.count_documents({"status": "applied"})

    return jsonify({
        "success": True,
        "stats": {
            "today": today_count,
            "week": week_count,
            "month": month_count,
            "total": total_count,
            "legacy_without_timestamp": legacy_applied  # Jobs applied before GAP-064 fix
        }
    })


@app.route("/health", methods=["GET"])
def public_health_check():
    """
    Public health endpoint for external monitoring (GAP-037).

    No authentication required - used by UptimeRobot, load balancers, etc.
    Returns minimal info to avoid exposing sensitive data.
    """
    # Quick MongoDB check
    try:
        db.command("ping")
        mongo_status = "connected"
    except Exception:
        mongo_status = "disconnected"

    # Quick VPS Runner check
    try:
        runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
        response = requests.get(f"{runner_url}/health", timeout=3)
        runner_status = "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        runner_status = "unreachable"

    overall = "healthy" if mongo_status == "connected" and runner_status == "healthy" else "degraded"

    return jsonify({
        "status": overall,
        "version": APP_VERSION,
        "services": {
            "mongodb": mongo_status,
            "runner": runner_status
        }
    })


@app.route("/api/health", methods=["GET"])
@login_required
def get_health():
    """
    Get health status of all services (Gap #13).

    Returns detailed health info including:
    - MongoDB connection status
    - VPS Runner status with capacity metrics
    - PDF Service status (via runner)
    - n8n status (if configured)
    """
    health_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "version": APP_VERSION,
        "overall": "healthy"  # Will be set to "degraded" or "unhealthy" if issues found
    }
    has_critical_failure = False
    has_degraded = False

    # Check VPS Runner (includes PDF service health)
    try:
        runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
        response = requests.get(f"{runner_url}/health", timeout=5)
        if response.status_code == 200:
            runner_data = response.json()
            health_data["runner"] = {
                "status": "healthy",
                "url": runner_url,
                "active_runs": runner_data.get("active_runs", 0),
                "max_concurrency": runner_data.get("max_concurrency", 3),
                "capacity_percent": int((runner_data.get("active_runs", 0) / max(runner_data.get("max_concurrency", 3), 1)) * 100)
            }
            # Check if runner is at capacity (degraded state)
            if health_data["runner"]["capacity_percent"] >= 100:
                health_data["runner"]["status"] = "busy"
                has_degraded = True
        else:
            health_data["runner"] = {
                "status": "unhealthy",
                "url": runner_url,
                "error": f"HTTP {response.status_code}"
            }
            has_critical_failure = True
    except requests.exceptions.Timeout:
        health_data["runner"] = {
            "status": "unhealthy",
            "url": os.getenv("RUNNER_URL", "http://72.61.92.76:8000"),
            "error": "Connection timeout"
        }
        has_critical_failure = True
    except Exception as e:
        health_data["runner"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        has_critical_failure = True

    # Check MongoDB
    try:
        db = get_db()
        # Try a simple operation with timeout
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
        has_critical_failure = True

    # Check n8n (if configured) - non-critical service
    n8n_url = os.getenv("N8N_URL", "")
    if n8n_url:
        try:
            response = requests.get(f"{n8n_url}/healthz", timeout=5)
            health_data["n8n"] = {
                "status": "healthy" if response.status_code == 200 else "degraded",
                "url": n8n_url
            }
            if response.status_code != 200:
                has_degraded = True
        except Exception as e:
            health_data["n8n"] = {
                "status": "degraded",
                "error": str(e)
            }
            has_degraded = True

    # Determine overall status
    if has_critical_failure:
        health_data["overall"] = "unhealthy"
    elif has_degraded:
        health_data["overall"] = "degraded"
    else:
        health_data["overall"] = "healthy"

    return jsonify(health_data)


@app.route("/partials/service-health", methods=["GET"])
@login_required
def service_health_partial():
    """HTMX partial: Return service health status indicators (Gap #13)."""
    response = get_health()
    health_data = response.get_json()

    return render_template(
        "partials/service_health.html",
        health=health_data
    )


@app.route("/api/pipeline-runs", methods=["GET"])
@login_required
def get_pipeline_runs():
    """
    Get pipeline run history (GAP-043).

    Query params:
    - job_id: Filter by job ID
    - limit: Max runs to return (default 50)
    - status: Filter by status (processing, completed, failed, partial)

    Returns list of pipeline runs sorted by created_at desc.
    """
    try:
        # Parse query params
        job_id = request.args.get("job_id")
        limit = min(int(request.args.get("limit", 50)), 200)  # Cap at 200
        status = request.args.get("status")

        # Build query
        query = {}
        if job_id:
            query["job_id"] = job_id
        if status:
            query["status"] = status

        # Fetch runs
        runs = list(
            db.pipeline_runs.find(query)
            .sort("created_at", DESCENDING)
            .limit(limit)
        )

        # Format for JSON
        formatted_runs = []
        for run in runs:
            formatted_runs.append({
                "run_id": run.get("run_id"),
                "job_id": run.get("job_id"),
                "job_title": run.get("job_title", ""),
                "company": run.get("company", ""),
                "status": run.get("status", "unknown"),
                "fit_score": run.get("fit_score"),
                "fit_category": run.get("fit_category"),
                "duration_ms": run.get("duration_ms"),
                "total_cost_usd": run.get("total_cost_usd"),
                "errors": run.get("errors", []),
                "trace_url": run.get("trace_url"),
                "created_at": run.get("created_at").isoformat() if run.get("created_at") else None,
                "updated_at": run.get("updated_at").isoformat() if run.get("updated_at") else None,
            })

        return jsonify({
            "runs": formatted_runs,
            "count": len(formatted_runs),
            "query": query,
        })

    except Exception as e:
        logger.error(f"Failed to fetch pipeline runs: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/metrics", methods=["GET"])
@login_required
def get_metrics():
    """
    Get unified metrics from all infrastructure components (Gap OB-1).

    Returns aggregated metrics from:
    - Token trackers (BG-1)
    - Rate limiters (BG-2)
    - Circuit breakers (CB-1)
    """
    try:
        from src.common.metrics import get_metrics_collector

        collector = get_metrics_collector()
        snapshot = collector.get_snapshot()
        return jsonify(snapshot.to_dict())
    except ImportError:
        # Metrics module not available, return empty
        return jsonify({
            "error": "Metrics module not available",
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }), 500


@app.route("/partials/metrics-dashboard", methods=["GET"])
@login_required
def metrics_dashboard_partial():
    """HTMX partial: Return metrics dashboard widget (Gap OB-1)."""
    try:
        from src.common.metrics import get_metrics_collector

        collector = get_metrics_collector()
        snapshot = collector.get_snapshot()
        return render_template(
            "partials/metrics_dashboard.html",
            metrics=snapshot.to_dict()
        )
    except ImportError:
        return render_template(
            "partials/metrics_dashboard.html",
            metrics=None,
            error="Metrics module not available"
        )
    except Exception as e:
        return render_template(
            "partials/metrics_dashboard.html",
            metrics=None,
            error=str(e)
        )


@app.route("/partials/budget-monitor", methods=["GET"])
@login_required
def budget_monitor_partial():
    """HTMX partial: Return budget monitoring widget (Gap #14).

    Proxies to VPS runner service which has access to the metrics module.
    Falls back to local import for local development.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    budget = None
    error = None

    # Try VPS runner first (production path)
    try:
        response = requests.get(f"{runner_url}/api/metrics/budget", timeout=5)
        if response.status_code == 200:
            budget = response.json()
            if "error" in budget:
                error = budget.get("error")
                budget = None
            logger.debug(f"Budget metrics from VPS: {budget}")
        else:
            logger.warning(f"VPS budget endpoint returned {response.status_code}")
            error = f"VPS returned {response.status_code}"
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS budget endpoint unavailable: {e}")
        # Fall back to local import (for local development)
        try:
            from src.common.metrics import get_metrics_collector
            collector = get_metrics_collector()
            budget = collector.get_budget_metrics().to_dict()
        except ImportError:
            error = "Metrics module not available (VPS unreachable, local import failed)"
        except Exception as ex:
            error = str(ex)

    return render_template(
        "partials/budget_monitor.html",
        budget=budget,
        error=error
    )


@app.route("/api/budget", methods=["GET"])
@login_required
def get_budget():
    """API endpoint: Return budget metrics as JSON (Gap #14).

    Proxies to VPS runner service.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")

    try:
        response = requests.get(f"{runner_url}/api/metrics/budget", timeout=5)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({
                "error": f"VPS returned {response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }), response.status_code
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS budget endpoint unavailable: {e}")
        # Fall back to local
        try:
            from src.common.metrics import get_metrics_collector
            collector = get_metrics_collector()
            return jsonify(collector.get_budget_metrics().to_dict())
        except ImportError:
            return jsonify({
                "error": "Metrics module not available",
                "timestamp": datetime.utcnow().isoformat(),
            }), 500
        except Exception as ex:
            return jsonify({
                "error": str(ex),
                "timestamp": datetime.utcnow().isoformat(),
            }), 500


@app.route("/api/firecrawl/credits", methods=["GET"])
@login_required
def get_firecrawl_credits():
    """API endpoint: Return FireCrawl credit usage as JSON (GAP-070).

    Proxies to VPS runner service which has access to the rate limiter.
    Falls back to local import for local development.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")

    try:
        response = requests.get(f"{runner_url}/firecrawl/credits", timeout=5)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({
                "error": f"VPS returned {response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }), response.status_code
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS FireCrawl credits endpoint unavailable: {e}")
        # Fall back to local rate limiter
        try:
            from src.common.rate_limiter import get_rate_limiter
            limiter = get_rate_limiter("firecrawl")
            stats = limiter.get_stats()
            remaining = limiter.get_remaining_daily() or 0
            daily_limit = limiter.daily_limit or 600
            used_today = stats.requests_today
            used_percent = (used_today / daily_limit * 100) if daily_limit > 0 else 0

            if used_percent >= 100:
                status = "exhausted"
            elif used_percent >= 90:
                status = "critical"
            elif used_percent >= 80:
                status = "warning"
            else:
                status = "healthy"

            return jsonify({
                "provider": "firecrawl",
                "daily_limit": daily_limit,
                "used_today": used_today,
                "remaining": remaining,
                "used_percent": round(used_percent, 1),
                "requests_this_minute": stats.requests_this_minute,
                "requests_per_minute_limit": limiter.requests_per_minute,
                "last_request_at": stats.last_request_at.isoformat() if stats.last_request_at else None,
                "daily_reset_at": stats.daily_reset_at.isoformat() if stats.daily_reset_at else None,
                "status": status,
            })
        except ImportError:
            return jsonify({
                "error": "Rate limiter module not available",
                "timestamp": datetime.utcnow().isoformat(),
            }), 500
        except Exception as ex:
            return jsonify({
                "error": str(ex),
                "timestamp": datetime.utcnow().isoformat(),
            }), 500


@app.route("/partials/firecrawl-credits", methods=["GET"])
@login_required
def firecrawl_credits_partial():
    """HTMX partial: Return FireCrawl credits widget (GAP-070)."""
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    credits = None
    error = None

    try:
        response = requests.get(f"{runner_url}/firecrawl/credits", timeout=5)
        if response.status_code == 200:
            credits = response.json()
        else:
            error = f"VPS returned {response.status_code}"
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS FireCrawl credits unavailable: {e}")
        # Fall back to local
        try:
            from src.common.rate_limiter import get_rate_limiter
            limiter = get_rate_limiter("firecrawl")
            stats = limiter.get_stats()
            remaining = limiter.get_remaining_daily() or 0
            daily_limit = limiter.daily_limit or 600
            used_today = stats.requests_today
            used_percent = (used_today / daily_limit * 100) if daily_limit > 0 else 0

            if used_percent >= 100:
                status = "exhausted"
            elif used_percent >= 90:
                status = "critical"
            elif used_percent >= 80:
                status = "warning"
            else:
                status = "healthy"

            credits = {
                "provider": "firecrawl",
                "daily_limit": daily_limit,
                "used_today": used_today,
                "remaining": remaining,
                "used_percent": round(used_percent, 1),
                "status": status,
            }
        except Exception as ex:
            error = str(ex)

    return render_template(
        "partials/firecrawl_credits.html",
        credits=credits,
        error=error,
    )


@app.route("/partials/alert-history", methods=["GET"])
@login_required
def alert_history_partial():
    """HTMX partial: Return alert history widget (Gap OB-2).

    Proxies to VPS runner service which has access to the alerting module.
    Falls back to local import for local development.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    alerts = None
    stats = None
    error = None

    # Try VPS runner first (production path)
    try:
        response = requests.get(f"{runner_url}/api/metrics/alerts?limit=20", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                error = data.get("error")
            else:
                alerts = data.get("alerts", [])
                stats = data.get("stats", {})
            logger.debug(f"Alert history from VPS: {len(alerts or [])} alerts")
        else:
            logger.warning(f"VPS alerts endpoint returned {response.status_code}")
            error = f"VPS returned {response.status_code}"
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS alerts endpoint unavailable: {e}")
        # Fall back to local import (for local development)
        try:
            from src.common.alerting import get_alert_manager
            manager = get_alert_manager()
            alerts = [a.to_dict() for a in manager.get_history(limit=20)]
            stats = manager.get_stats()
        except ImportError:
            error = "Alerting module not available (VPS unreachable, local import failed)"
        except Exception as ex:
            error = str(ex)

    return render_template(
        "partials/alert_history.html",
        alerts=alerts,
        stats=stats,
        error=error
    )


@app.route("/api/alerts", methods=["GET"])
@login_required
def get_alerts():
    """API endpoint: Return alert history as JSON (Gap OB-2).

    Proxies to VPS runner service.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    limit = request.args.get("limit", 50, type=int)
    level = request.args.get("level")
    source = request.args.get("source")

    # Build query string
    params = [f"limit={limit}"]
    if level:
        params.append(f"level={level}")
    if source:
        params.append(f"source={source}")
    query_string = "&".join(params)

    try:
        response = requests.get(f"{runner_url}/api/metrics/alerts?{query_string}", timeout=5)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({
                "error": f"VPS returned {response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }), response.status_code
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS alerts endpoint unavailable: {e}")
        # Fall back to local
        try:
            from src.common.alerting import get_alert_manager
            manager = get_alert_manager()
            alerts = manager.get_history(limit=limit)
            if level:
                alerts = [a for a in alerts if a.level.value == level]
            if source:
                alerts = [a for a in alerts if a.source == source]
            return jsonify({
                "alerts": [a.to_dict() for a in alerts],
                "stats": manager.get_stats(),
                "timestamp": datetime.utcnow().isoformat(),
            })
        except ImportError:
            return jsonify({
                "error": "Alerting module not available",
                "timestamp": datetime.utcnow().isoformat(),
            }), 500
        except Exception as ex:
            return jsonify({
                "error": str(ex),
                "timestamp": datetime.utcnow().isoformat(),
            }), 500


@app.route("/partials/cost-trends", methods=["GET"])
@login_required
def cost_trends_partial():
    """HTMX partial: Return cost trends sparkline widget (Gap #15).

    Proxies to VPS runner service which has access to the metrics module.
    Falls back to local import for local development.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    period = request.args.get("period", "hourly")
    count = request.args.get("count", 24, type=int)

    costs = None
    sparkline_svg = None
    summary = None
    error = None

    # Try VPS runner first (production path)
    try:
        response = requests.get(
            f"{runner_url}/api/metrics/cost-history?period={period}&count={count}",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                error = data.get("error")
            else:
                costs = data.get("costs", [])
                sparkline_svg = data.get("sparkline_svg", "")
                summary = data.get("summary", {})
            logger.debug(f"Cost history from VPS: {len(costs or [])} data points")
        else:
            logger.warning(f"VPS cost-history endpoint returned {response.status_code}")
            error = f"VPS returned {response.status_code}"
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS cost-history endpoint unavailable: {e}")
        # Fall back to local import (for local development)
        try:
            from src.common.metrics import get_metrics_collector
            collector = get_metrics_collector()
            history = collector.get_cost_history(period=period, count=count)
            costs = history["costs"]
            sparkline_svg = history["sparkline_svg"]
            summary = history["summary"]
        except ImportError:
            error = "Metrics module not available (VPS unreachable, local import failed)"
        except Exception as ex:
            error = str(ex)

    return render_template(
        "partials/cost_trends.html",
        period=period,
        costs=costs,
        sparkline_svg=sparkline_svg,
        summary=summary,
        error=error
    )


@app.route("/api/cost-history", methods=["GET"])
@login_required
def get_cost_history():
    """API endpoint: Return cost history as JSON (Gap #15).

    Proxies to VPS runner service.
    """
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    period = request.args.get("period", "hourly")
    count = request.args.get("count", 24, type=int)

    try:
        response = requests.get(
            f"{runner_url}/api/metrics/cost-history?period={period}&count={count}",
            timeout=5
        )
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({
                "error": f"VPS returned {response.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
            }), response.status_code
    except requests.exceptions.RequestException as e:
        logger.warning(f"VPS cost-history endpoint unavailable: {e}")
        # Fall back to local
        try:
            from src.common.metrics import get_metrics_collector
            collector = get_metrics_collector()
            history = collector.get_cost_history(period=period, count=count)
            history["timestamp"] = datetime.utcnow().isoformat()
            return jsonify(history)
        except ImportError:
            return jsonify({
                "error": "Metrics module not available",
                "timestamp": datetime.utcnow().isoformat(),
            }), 500
        except Exception as ex:
            return jsonify({
                "error": str(ex),
            "timestamp": datetime.utcnow().isoformat(),
        }), 500


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
# API Documentation
# ============================================================================

@app.route("/api-docs")
@app.route("/api/docs")
def api_docs():
    """Serve Swagger UI for API documentation."""
    return render_template("api_docs.html")


@app.route("/api/openapi.yaml")
def openapi_spec():
    """Serve the OpenAPI specification file."""
    return app.send_static_file("openapi.yaml")


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
    try:
        # Reuse the list_jobs logic
        response = list_jobs()

        # Handle tuple response (error case returns (response, status_code))
        if isinstance(response, tuple):
            json_response, status_code = response
            if status_code >= 400:
                # Return error as HTML for HTMX
                error_data = json_response.get_json()
                error_msg = error_data.get("message", error_data.get("error", "Unknown error"))
                return f'<tr><td colspan="8" class="px-4 py-8 text-center text-red-500">Error: {error_msg}</td></tr>', status_code
            data = json_response.get_json()
        else:
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
    except Exception as e:
        # Catch any unexpected errors and return them as HTML
        import traceback
        error_details = f"{type(e).__name__}: {str(e)}"
        app.logger.error(f"job_rows_partial error: {error_details}\n{traceback.format_exc()}")
        return f'<tr><td colspan="8" class="px-4 py-8 text-center text-red-500">Unexpected error: {error_details}</td></tr>', 500


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


@app.route("/partials/application-stats", methods=["GET"])
@login_required
def application_stats_partial():
    """HTMX partial: Return application statistics progress bars."""
    response = get_application_stats()
    data = response.get_json()

    return render_template(
        "partials/application_stats.html",
        stats=data.get("stats", {"today": 0, "week": 0, "month": 0, "total": 0})
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
    # GAP-009 Fix: Check both cv_text (markdown) AND cv_editor_state (TipTap JSON)
    if job.get("cv_text") or job.get("cv_editor_state"):
        has_cv = True
        cv_content = job.get("cv_text")  # Markdown CV from pipeline (may be None if only editor state exists)
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
    Generate PDF from CV editor state via runner service proxy.

    The runner service fetches CV from MongoDB and proxies to the internal PDF service.
    Architecture: Frontend → Runner (port 8000) → PDF Service (internal port 8001)

    Returns:
        PDF file streamed from runner service
    """
    import requests
    from flask import send_file
    from io import BytesIO

    # Get runner service URL (runner handles MongoDB fetch + PDF service proxy)
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    endpoint = f"{runner_url}/api/jobs/{job_id}/cv-editor/pdf"

    # Get authentication token for runner service
    runner_token = os.getenv("RUNNER_API_SECRET")
    headers = {}
    if runner_token:
        headers["Authorization"] = f"Bearer {runner_token}"
        logger.info(f"PDF generation request for job {job_id} - authentication configured")
    else:
        logger.warning(f"RUNNER_API_SECRET not set - runner service may reject request for job {job_id}")

    try:
        logger.info(f"Requesting PDF generation from {endpoint}")

        # Send request to runner service (runner fetches from MongoDB and proxies to PDF service)
        response = requests.post(
            endpoint,
            headers=headers,
            timeout=60,  # 60 second timeout for PDF generation
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
            "detail": "The PDF service took too long to respond"
        }), 504
    except requests.ConnectionError as e:
        logger.error(f"Failed to connect to PDF service at {pdf_service_url}: {str(e)}")
        return jsonify({
            "error": "PDF service unavailable. Please try again later.",
            "detail": f"Cannot connect to PDF service at {pdf_service_url}"
        }), 503
    except requests.RequestException as e:
        logger.error(f"Request to PDF service failed for job {job_id}: {str(e)}")
        return jsonify({
            "error": "Failed to connect to PDF service",
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


@app.route("/api/jobs/<job_id>/export-dossier-pdf", methods=["GET"])
@login_required
def export_dossier_pdf(job_id: str):
    """
    Export complete job dossier as PDF (GAP-033).

    Generates a comprehensive PDF document containing:
    - Company research
    - Role analysis
    - Pain points (4 dimensions)
    - Fit analysis (score + rationale)
    - Contact list
    - Outreach materials
    - CV reasoning

    Returns:
        PDF file for download
    """
    from io import BytesIO
    from flask import send_file

    # Add src to path for pdf_export import
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        # 1. Fetch job state from MongoDB
        job_doc = collection.find_one({"_id": ObjectId(job_id)})
        if not job_doc:
            return jsonify({"error": "Job not found"}), 404

        # Convert ObjectId to string for JSON compatibility
        job_doc["_id"] = str(job_doc["_id"])

        # 2. Generate PDF using DossierPDFExporter
        from src.api.pdf_export import DossierPDFExporter

        # Get PDF service URL from runner proxy
        runner_url = os.getenv("RUNNER_URL", "http://localhost:8000")
        pdf_service_url = f"{runner_url}/proxy/pdf"

        exporter = DossierPDFExporter(pdf_service_url=pdf_service_url)

        try:
            pdf_bytes = exporter.export_to_pdf(job_doc)
        except Exception as pdf_error:
            logger.error(f"PDF export failed for job {job_id}: {pdf_error}")
            return jsonify({
                "error": "PDF generation failed",
                "detail": str(pdf_error)
            }), 500

        # 3. Generate filename
        company = job_doc.get("company", "Unknown")
        title = job_doc.get("title", "Job")

        def slugify(text: str) -> str:
            import re
            text = text.lower()
            text = re.sub(r'[^a-z0-9]+', '-', text)
            return text.strip('-')

        filename = f"dossier-{slugify(company)}-{slugify(title)}.pdf"

        # 4. Return PDF for download
        logger.info(f"Dossier PDF exported successfully for job {job_id}")
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.exception(f"Unexpected error exporting dossier PDF for job {job_id}")
        return jsonify({
            "error": f"Dossier export failed: {str(e)}",
            "detail": "An unexpected error occurred"
        }), 500


@app.route("/api/jobs/<job_id>/meta-prompt", methods=["GET"])
@login_required
def get_meta_prompt(job_id: str):
    """
    Generate meta prompt for Claude Code application review.

    Creates a comprehensive prompt containing:
    - Complete job dossier (pain points, opportunity mapper, company research)
    - Generated CV text
    - Multi-step reasoning instructions for Claude

    Returns:
        JSON with the meta prompt string
    """
    try:
        # Fetch job state from MongoDB
        job_doc = collection.find_one({"_id": ObjectId(job_id)})
        if not job_doc:
            return jsonify({"error": "Job not found"}), 404

        # Generate the meta prompt
        prompt = _build_meta_prompt(job_doc)

        return jsonify({"prompt": prompt})

    except Exception as e:
        logger.exception(f"Error generating meta prompt for job {job_id}")
        return jsonify({
            "error": f"Meta prompt generation failed: {str(e)}"
        }), 500


def _build_meta_prompt(job_doc: dict) -> str:
    """
    Build the comprehensive meta prompt for Claude Code review.

    Includes all dossier data and CV with multi-step reasoning instructions.
    """
    company = job_doc.get("company", "Unknown Company")
    title = job_doc.get("title", "Unknown Role")
    location = job_doc.get("location", "")
    url = job_doc.get("url", "")

    # Extract all dossier sections
    extracted_jd = job_doc.get("extracted_jd", {})
    pain_points = job_doc.get("pain_points", [])
    opportunity_map = job_doc.get("opportunity_map", {})
    company_research = job_doc.get("company_research", {})
    fit_score = job_doc.get("fit_score", {})
    contacts = job_doc.get("contacts", [])
    cv_text = job_doc.get("cv_text", "")
    cv_reasoning = job_doc.get("cv_reasoning", "")
    outreach = job_doc.get("outreach", {})

    # Format sections
    sections = []

    # Header
    sections.append(f"""# Claude Code Application Review Request

## Target Position
- **Company:** {company}
- **Role:** {title}
- **Location:** {location}
- **URL:** {url}

---""")

    # Job Description Analysis
    if extracted_jd:
        sections.append(f"""## Job Description Intelligence

**Role Category:** {extracted_jd.get('role_category', 'N/A')}
**Seniority Level:** {extracted_jd.get('seniority_level', 'N/A')}

### Top Keywords
{_format_list(extracted_jd.get('top_keywords', []))}

### Technical Skills Required
{_format_list(extracted_jd.get('technical_skills', []))}

### Soft Skills Required
{_format_list(extracted_jd.get('soft_skills', []))}

### Implied Pain Points (from JD)
{_format_list(extracted_jd.get('implied_pain_points', []))}

### Success Metrics
{_format_list(extracted_jd.get('success_metrics', []))}

---""")

    # Pain Points (detailed)
    if pain_points:
        sections.append(f"""## Detailed Pain Point Analysis

{_format_pain_points(pain_points)}

---""")

    # Opportunity Map
    if opportunity_map:
        sections.append(f"""## Opportunity Mapping

### Company Pain Points
{_format_list(opportunity_map.get('company_pain_points', []))}

### Role Pain Points
{_format_list(opportunity_map.get('role_pain_points', []))}

### Growth Opportunities
{_format_list(opportunity_map.get('growth_opportunities', []))}

### Cultural Signals
{_format_list(opportunity_map.get('cultural_signals', []))}

---""")

    # Company Research
    if company_research:
        sections.append(f"""## Company Research

**Industry:** {company_research.get('industry', 'N/A')}
**Size:** {company_research.get('company_size', 'N/A')}
**Stage:** {company_research.get('funding_stage', 'N/A')}

### Recent News
{_format_list(company_research.get('recent_news', []))}

### Tech Stack
{_format_list(company_research.get('tech_stack', []))}

### Culture Signals
{_format_list(company_research.get('culture_signals', []))}

---""")

    # Fit Score
    if fit_score:
        sections.append(f"""## Fit Analysis

**Overall Score:** {fit_score.get('score', 'N/A')}/100
**Confidence:** {fit_score.get('confidence', 'N/A')}

### Rationale
{fit_score.get('rationale', 'N/A')}

### Strengths
{_format_list(fit_score.get('strengths', []))}

### Gaps
{_format_list(fit_score.get('gaps', []))}

---""")

    # Contacts
    if contacts:
        sections.append(f"""## People Mapper (Contacts)

{_format_contacts(contacts)}

---""")

    # CV
    if cv_text:
        sections.append(f"""## Generated CV

```
{cv_text}
```

### CV Generation Reasoning
{cv_reasoning if cv_reasoning else 'N/A'}

---""")

    # Outreach
    if outreach:
        sections.append(f"""## Outreach Draft

**Subject:** {outreach.get('subject', 'N/A')}

### Email Body
{outreach.get('body', 'N/A')}

---""")

    # Multi-step reasoning instructions
    sections.append("""## Your Task: Deep Application Review

Using extended thinking and high reasoning, please perform the following analysis:

### Step 1: Pain Point Assessment
- Review the extracted pain points and opportunity mapping
- Are there any missed pain points based on the JD?
- How well does the CV address each pain point?
- Suggest improvements to pain point coverage

### Step 2: CV Optimization Analysis
- Review the generated CV against ATS best practices
- Check keyword coverage and density
- Assess STAR format compliance in each bullet
- Identify any weak bullets that could be strengthened
- Check for authenticity - does it sound genuine or over-optimized?

### Step 3: Differentiation Strategy
- What makes this candidate unique for this specific role?
- What stories/achievements should be emphasized more?
- Are there any red flags a recruiter might notice?
- How does the career narrative flow?

### Step 4: Application Strategy
- Based on the contacts, who should be reached out to first?
- What's the best approach for each contact?
- What customizations would make this application stand out?
- What interview questions should the candidate prepare for?

### Step 5: Killer Application Recommendations
Provide specific, actionable recommendations to create a killer job application that:
1. Sounds authentic and genuine (not over-optimized)
2. Directly addresses the company's pain points
3. Demonstrates clear value proposition
4. Tells a compelling career story
5. Is memorable and differentiated from other applicants

### Output Format
Please provide:
1. **Executive Summary** (2-3 sentences on overall application strength)
2. **Critical Improvements** (top 3 changes that would have the biggest impact)
3. **CV Rewrite Suggestions** (specific bullet rewrites if needed)
4. **Outreach Strategy** (who to contact, what to say)
5. **Interview Preparation** (likely questions based on the application)

Be specific and actionable. Reference exact bullets or sections when making suggestions.""")

    return "\n\n".join(sections)


def _format_list(items: list) -> str:
    """Format a list as bullet points."""
    if not items:
        return "- None specified"
    return "\n".join(f"- {item}" for item in items)


def _format_pain_points(pain_points: list) -> str:
    """Format pain points with details."""
    if not pain_points:
        return "No pain points extracted."

    lines = []
    for i, pp in enumerate(pain_points, 1):
        if isinstance(pp, dict):
            lines.append(f"**{i}. {pp.get('category', 'Pain Point')}**")
            lines.append(f"   - Description: {pp.get('description', 'N/A')}")
            lines.append(f"   - Evidence: {pp.get('evidence', 'N/A')}")
            lines.append(f"   - Severity: {pp.get('severity', 'N/A')}")
        else:
            lines.append(f"- {pp}")
    return "\n".join(lines)


def _format_contacts(contacts: list) -> str:
    """Format contacts list."""
    if not contacts:
        return "No contacts identified."

    lines = []
    for i, contact in enumerate(contacts, 1):
        if isinstance(contact, dict):
            lines.append(f"**{i}. {contact.get('name', 'Unknown')}**")
            lines.append(f"   - Title: {contact.get('title', 'N/A')}")
            lines.append(f"   - Company: {contact.get('company', 'N/A')}")
            lines.append(f"   - LinkedIn: {contact.get('linkedin', 'N/A')}")
            lines.append(f"   - Relevance: {contact.get('relevance', 'N/A')}")
        else:
            lines.append(f"- {contact}")
    return "\n".join(lines)


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
                "colorAccent": "#475569"  # slate-600 - professional dark blue-gray
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
        """Parse bold and italic marks from text.

        GAP-012 Fix: Properly parse **bold** and *italic* markdown to TipTap marks.

        Supports:
        - **bold** → text with bold mark
        - *italic* → text with italic mark
        - ***bold+italic*** → text with both marks
        - Mixed text like "Hello **world** and *universe*"
        """
        import re

        if not text:
            return []

        result = []

        # Regex pattern for bold (**text**), italic (*text*), or bold+italic (***text***)
        # Order matters: check *** first, then **, then *
        pattern = r'(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*([^*]+?)\*)'

        last_end = 0
        for match in re.finditer(pattern, text):
            # Add any plain text before this match
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    result.append({"type": "text", "text": plain_text})

            # Determine which group matched
            if match.group(2):  # ***bold+italic***
                result.append({
                    "type": "text",
                    "text": match.group(2),
                    "marks": [{"type": "bold"}, {"type": "italic"}]
                })
            elif match.group(3):  # **bold**
                result.append({
                    "type": "text",
                    "text": match.group(3),
                    "marks": [{"type": "bold"}]
                })
            elif match.group(4):  # *italic*
                result.append({
                    "type": "text",
                    "text": match.group(4),
                    "marks": [{"type": "italic"}]
                })

            last_end = match.end()

        # Add any remaining plain text after the last match
        if last_end < len(text):
            remaining = text[last_end:]
            if remaining:
                result.append({"type": "text", "text": remaining})

        # If no matches found, return the original text as plain
        if not result:
            result.append({"type": "text", "text": text})

        return result

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
            "colorAccent": "#475569"  # slate-600 - professional dark blue-gray
        }
    }


# ============================================================================
# Contact Management API
# ============================================================================

@app.route("/api/jobs/<job_id>/contacts/<contact_type>/<int:contact_index>", methods=["DELETE"])
@login_required
def delete_contact(job_id: str, contact_type: str, contact_index: int):
    """
    Delete a contact from a job by type and index.

    Args:
        job_id: MongoDB ObjectId string
        contact_type: Either 'primary' or 'secondary'
        contact_index: Zero-based index of contact in the array

    Returns:
        JSON with success status
    """
    db = get_db()
    collection = db["level-2"]

    # Validate contact_type
    if contact_type not in ["primary", "secondary"]:
        return jsonify({"error": "Invalid contact type. Must be 'primary' or 'secondary'"}), 400

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    # Get the job first to validate the contact exists
    job = collection.find_one({"_id": object_id})
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Determine the field name
    field_name = f"{contact_type}_contacts"
    contacts = job.get(field_name, [])

    if contact_index < 0 or contact_index >= len(contacts):
        return jsonify({"error": f"Contact index {contact_index} out of range"}), 400

    # Get the contact name for the response
    contact_name = contacts[contact_index].get("name", "Unknown")

    # Remove the contact using MongoDB $unset + $pull pattern
    # First, set the element to null, then pull all nulls
    result = collection.update_one(
        {"_id": object_id},
        {"$unset": {f"{field_name}.{contact_index}": 1}}
    )

    if result.modified_count > 0:
        # Now pull the null value
        collection.update_one(
            {"_id": object_id},
            {"$pull": {field_name: None}}
        )

        # Update timestamp
        collection.update_one(
            {"_id": object_id},
            {"$set": {"updatedAt": datetime.utcnow()}}
        )

    return jsonify({
        "success": True,
        "message": f"Contact '{contact_name}' removed",
        "deletedIndex": contact_index,
        "contactType": contact_type
    })


@app.route("/api/jobs/<job_id>/contacts", methods=["POST"])
@login_required
def import_contacts(job_id: str):
    """
    Import contacts to a job (append to existing contacts).

    Request Body:
        contacts: Array of contact objects
        contact_type: 'primary' or 'secondary' (default: 'secondary')

    Each contact object should have:
        - name (required): Contact name
        - title/role (required): Job title/role
        - linkedin_url (required): LinkedIn profile URL
        - email (optional): Contact email
        - phone (optional): Contact phone
        - relevance/why_relevant (optional): Why this contact is relevant

    Returns:
        JSON with success status and import count
    """
    db = get_db()
    collection = db["level-2"]

    try:
        object_id = ObjectId(job_id)
    except Exception:
        return jsonify({"error": "Invalid job ID format"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    contacts = data.get("contacts", [])
    contact_type = data.get("contact_type", "secondary")

    if not contacts:
        return jsonify({"error": "No contacts provided"}), 400

    if contact_type not in ["primary", "secondary"]:
        return jsonify({"error": "Invalid contact type. Must be 'primary' or 'secondary'"}), 400

    # Validate and normalize contacts
    valid_contacts = []
    for contact in contacts:
        # Check required fields
        if not contact.get("name"):
            continue
        if not contact.get("title") and not contact.get("role"):
            continue
        if not contact.get("linkedin_url"):
            continue

        # Normalize to our schema
        normalized = {
            "name": contact.get("name"),
            "role": contact.get("title") or contact.get("role"),
            "linkedin_url": contact.get("linkedin_url"),
            "why_relevant": contact.get("why_relevant") or contact.get("relevance") or "Imported contact",
            "source": "manual_import",
            "imported_at": datetime.utcnow().isoformat()
        }

        # Optional fields
        if contact.get("email"):
            normalized["email"] = contact.get("email")
        if contact.get("phone"):
            normalized["phone"] = contact.get("phone")

        valid_contacts.append(normalized)

    if not valid_contacts:
        return jsonify({"error": "No valid contacts found. Each contact requires name, title/role, and linkedin_url"}), 400

    # Get job to verify it exists
    job = collection.find_one({"_id": object_id})
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Append to existing contacts using $push with $each
    field_name = f"{contact_type}_contacts"

    result = collection.update_one(
        {"_id": object_id},
        {
            "$push": {field_name: {"$each": valid_contacts}},
            "$set": {"updatedAt": datetime.utcnow()}
        }
    )

    return jsonify({
        "success": True,
        "message": f"Imported {len(valid_contacts)} contacts",
        "importedCount": len(valid_contacts),
        "contactType": contact_type
    })


@app.route("/api/jobs/<job_id>/contacts/prompt", methods=["GET"])
@login_required
def get_firecrawl_prompt(job_id: str):
    """
    Generate a FireCrawl contact discovery prompt for Claude Code.

    Returns a prompt that users can copy and paste into Claude Code
    to discover contacts using the FireCrawl MCP tool.

    Returns:
        JSON with the generated prompt
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

    company = job.get("company", "the company")
    title = job.get("title", "the role")

    prompt = f"""Find contacts at {company} for the {title} role using FireCrawl MCP.

Instructions:
1. Use mcp__firecrawl__firecrawl_search with these parameters:
   Query: "{company} {title} (hiring manager OR recruiter OR team lead) site:linkedin.com"
   Limit: 5

2. Extract contacts using this schema:
{{
  "name": "string",
  "title": "string",
  "linkedin_url": "string",
  "email": "string (if found)",
  "phone": "string (if found)",
  "relevance": "hiring_manager | recruiter | team_lead | other"
}}

3. Return results as JSON array
4. Paste the JSON below to import into job-search

Expected format:
[
  {{
    "name": "Jane Doe",
    "title": "Hiring Manager",
    "linkedin_url": "https://linkedin.com/in/janedoe",
    "email": "jane@company.com",
    "relevance": "hiring_manager"
  }}
]"""

    return jsonify({
        "success": True,
        "prompt": prompt,
        "company": company,
        "title": title
    })


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
