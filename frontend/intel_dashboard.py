"""Intel Dashboard Blueprint — LinkedIn Intelligence visualization.

Provides dashboard, opportunities, drafts, and health views
backed by VPS MongoDB via IntelRepository.

Blueprint prefix: /dashboard
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
from flask import Blueprint, jsonify, render_template, request

logger = logging.getLogger(__name__)

intel_bp = Blueprint("intel", __name__, url_prefix="/dashboard")


def get_repo():
    """Lazy import to avoid startup failures if MONGODB_URI is not set."""
    try:
        from repositories.intel_repository import IntelRepository
    except ImportError:
        from frontend.repositories.intel_repository import IntelRepository
    return IntelRepository.get_instance()


def get_job_repo():
    """Get Atlas job repository for pipeline pushes."""
    try:
        from repositories.config import get_job_repository
    except ImportError:
        from frontend.repositories.config import get_job_repository
    return get_job_repository()


def get_discovery_repo():
    """Get the discovery/debug repository with explicit Mongo precedence."""
    try:
        from repositories.discovery_repository import DiscoveryRepository
    except ImportError:
        from frontend.repositories.discovery_repository import DiscoveryRepository
    return DiscoveryRepository.get_instance()


# ------------------------------------------------------------------
# Main dashboard
# ------------------------------------------------------------------

@intel_bp.route("")
def dashboard():
    """Main dashboard page with stat cards and overview."""
    try:
        repo = get_repo()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        stats = repo.get_stats(since)
        top_opps = repo.get_top_opportunities(since, min_score=7, limit=10)
        recent_sessions = repo.get_recent_sessions(limit=5)
        health = repo.get_cookie_health()
        return render_template(
            "intel_dashboard.html",
            stats=stats,
            opportunities=top_opps,
            sessions=recent_sessions,
            health=health,
        )
    except Exception as e:
        logger.error("Dashboard error: %s", e)
        return render_template("intel_dashboard.html", error=str(e), stats=None)


@intel_bp.route("/stats")
def stats_partial():
    """HTMX partial: stat cards (auto-refresh every 60s)."""
    try:
        repo = get_repo()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        stats = repo.get_stats(since)
        return render_template("partials/intel/stat_cards.html", stats=stats)
    except Exception as e:
        return f'<div class="text-red-400 text-sm">Stats unavailable: {e}</div>'


# ------------------------------------------------------------------
# Opportunities
# ------------------------------------------------------------------

@intel_bp.route("/opportunities")
def opportunities():
    """Full opportunities page."""
    try:
        repo = get_repo()
        filters = _parse_filters()
        sort_field = request.args.get("sort", "scraped_at")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        items, total = repo.get_intel_items(
            filters=filters, sort_field=sort_field, page=page, per_page=per_page
        )
        total_pages = max(1, (total + per_page - 1) // per_page)
        return render_template(
            "intel_opportunities.html",
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            filters=filters or {},
        )
    except Exception as e:
        logger.error("Opportunities error: %s", e)
        return render_template(
            "intel_opportunities.html",
            error=str(e),
            items=[],
            total=0,
            page=1,
            per_page=20,
            total_pages=1,
            filters={},
        )


@intel_bp.route("/opportunities/rows")
def opportunities_rows():
    """HTMX partial: table rows for pagination/filter."""
    try:
        repo = get_repo()
        filters = _parse_filters()
        sort_field = request.args.get("sort", "scraped_at")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        items, total = repo.get_intel_items(
            filters=filters, sort_field=sort_field, page=page, per_page=per_page
        )
        total_pages = max(1, (total + per_page - 1) // per_page)
        return render_template(
            "partials/intel/opportunities_table.html",
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )
    except Exception as e:
        return f'<div class="text-red-400 text-sm">Error: {e}</div>'


@intel_bp.route("/opportunities/<item_id>")
def opportunity_detail(item_id):
    """HTMX partial: item detail modal content."""
    try:
        repo = get_repo()
        item = repo.get_item_detail(item_id)
        if not item:
            return '<div class="text-red-400">Item not found</div>', 404
        return render_template("partials/intel/opportunity_detail.html", item=item)
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


@intel_bp.route("/opportunities/<item_id>/pipeline", methods=["POST"])
def push_to_pipeline(item_id):
    """Push an intel item to the job pipeline."""
    try:
        repo = get_repo()
        item = repo.get_item_detail(item_id)
        if not item:
            return jsonify({"error": "Item not found"}), 404

        # Convert to job doc
        from pipeline_bridge_frontend import convert_intel_to_job_doc
        job_doc = convert_intel_to_job_doc(item)

        # Insert into Atlas
        job_repo = get_job_repo()
        job_repo.collection.insert_one(job_doc)

        # Mark intel item
        repo.mark_pushed_to_pipeline(item_id, job_doc["job_id"])

        # Trigger runner (best-effort)
        _trigger_runner(job_doc["job_id"])

        return render_template(
            "partials/intel/opportunity_detail.html",
            item=item,
            toast="Pushed to pipeline successfully",
        )
    except Exception as e:
        logger.error("Pipeline push error: %s", e)
        return jsonify({"error": str(e)}), 500


@intel_bp.route("/opportunities/<item_id>/action", methods=["POST"])
def item_action(item_id):
    """Mark saved/skipped/acted."""
    try:
        repo = get_repo()
        action = request.form.get("action", "saved")
        repo.update_item_action(item_id, action)
        item = repo.get_item_detail(item_id)
        return render_template(
            "partials/intel/opportunity_detail.html",
            item=item,
            toast=f"Marked as {action}",
        )
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


# ------------------------------------------------------------------
# Scrape runs
# ------------------------------------------------------------------

@intel_bp.route("/scrape-runs")
def scrape_runs():
    """HTMX partial: session history table."""
    try:
        repo = get_repo()
        sessions = repo.get_session_history(days=7)
        return render_template("partials/intel/scrape_runs.html", sessions=sessions)
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


# ------------------------------------------------------------------
# Drafts
# ------------------------------------------------------------------

@intel_bp.route("/drafts")
def drafts():
    """Full drafts page."""
    try:
        repo = get_repo()
        draft_list = repo.get_drafts(status="draft", limit=20)
        return render_template("intel_drafts.html", drafts=draft_list)
    except Exception as e:
        logger.error("Drafts error: %s", e)
        return render_template("intel_drafts.html", error=str(e), drafts=[])


@intel_bp.route("/drafts/rows")
def drafts_rows():
    """HTMX partial: draft list."""
    try:
        repo = get_repo()
        status = request.args.get("status", "draft")
        draft_list = repo.get_drafts(status=status, limit=20)
        return render_template("partials/intel/draft_queue.html", drafts=draft_list)
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


@intel_bp.route("/drafts/<draft_id>/approve", methods=["POST"])
def approve_draft(draft_id):
    """Approve a draft."""
    try:
        repo = get_repo()
        repo.update_draft(draft_id, {"status": "approved"})
        draft = repo.get_draft(draft_id)
        return render_template("partials/intel/draft_queue.html", drafts=[draft] if draft else [], toast="Draft approved")
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


@intel_bp.route("/drafts/<draft_id>/skip", methods=["POST"])
def skip_draft(draft_id):
    """Skip a draft."""
    try:
        repo = get_repo()
        repo.update_draft(draft_id, {"status": "skipped"})
        return '<div class="text-gray-500 text-sm py-2">Draft skipped</div>'
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


@intel_bp.route("/drafts/<draft_id>/edit", methods=["POST"])
def edit_draft(draft_id):
    """Update draft text."""
    try:
        repo = get_repo()
        new_content = request.form.get("content", "")
        repo.update_draft(draft_id, {"content": new_content})
        draft = repo.get_draft(draft_id)
        return render_template("partials/intel/draft_queue.html", drafts=[draft] if draft else [], toast="Draft updated")
    except Exception as e:
        return f'<div class="text-red-400">Error: {e}</div>'


@intel_bp.route("/drafts/<draft_id>/regenerate", methods=["POST"])
def regenerate_draft(draft_id):
    """Regenerate a draft using Anthropic API."""
    try:
        repo = get_repo()
        draft = repo.get_draft(draft_id)
        if not draft:
            return '<div class="text-red-400">Draft not found</div>', 404

        # Get source item
        source_id = draft.get("source_intel_id")
        item = repo.get_item_detail(source_id) if source_id else None

        new_content = _regenerate_with_anthropic(draft, item)
        repo.update_draft(draft_id, {"content": new_content, "regenerated": True})
        draft = repo.get_draft(draft_id)
        return render_template("partials/intel/draft_queue.html", drafts=[draft] if draft else [], toast="Draft regenerated")
    except Exception as e:
        logger.error("Regenerate error: %s", e)
        return f'<div class="text-red-400">Regeneration failed: {e}</div>'


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@intel_bp.route("/health")
def health():
    """HTMX partial: API usage + cookie health."""
    try:
        repo = get_repo()
        usage = repo.get_api_usage(days=7)
        cookie = repo.get_cookie_health()
        return render_template("partials/intel/health_panel.html", usage=usage, cookie=cookie)
    except Exception as e:
        return f'<div class="text-red-400">Health data unavailable: {e}</div>'


# ------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------

@intel_bp.route("/discovery")
def discovery_dashboard():
    """Full discovery/debug page for discovery plus native scrape state."""
    try:
        repo = get_discovery_repo()
        filters = _parse_discovery_filters()
        return render_template(
            "intel_discovery.html",
            heartbeat=repo.get_pipeline_heartbeat(),
            results=repo.search_hits_page(**filters),
            filters=filters,
            search_runs=repo.get_recent_search_runs(limit=8),
            scrape_runs=repo.get_recent_scrape_runs(limit=8),
            selector_runs=repo.get_recent_selector_runs(limit=8),
            queue=repo.get_queue_snapshot(),
            failures=repo.get_recent_failures(limit=5),
            langfuse=repo.get_langfuse_panel(),
        )
    except Exception as e:
        logger.error("Discovery dashboard error: %s", e)
        return render_template(
            "intel_discovery.html",
            error=str(e),
            heartbeat=None,
            results={"hits": [], "page": {}, "filters": {}},
            filters=_parse_discovery_filters(),
            search_runs=[],
            scrape_runs=[],
            selector_runs=[],
            queue={},
            failures=[],
            langfuse={},
        )


@intel_bp.route("/discovery/heartbeat")
@intel_bp.route("/discovery/stats")
def discovery_stats():
    """HTMX partial: discovery heartbeat cards."""
    try:
        repo = get_discovery_repo()
        return render_template(
            "partials/intel/discovery_stat_cards.html",
            heartbeat=repo.get_pipeline_heartbeat(),
        )
    except Exception as e:
        return f'<div class="text-red-400 text-sm">Discovery stats unavailable: {e}</div>'


@intel_bp.route("/discovery/results")
@intel_bp.route("/discovery/rows")
def discovery_rows():
    """HTMX partial: filtered discovery results."""
    try:
        repo = get_discovery_repo()
        filters = _parse_discovery_filters()
        return render_template(
            "partials/intel/discovery_table.html",
            results=repo.search_hits_page(**filters),
        )
    except Exception as e:
        return f'<div class="text-red-400 text-sm">Discovery rows unavailable: {e}</div>'


@intel_bp.route("/discovery/peek/<hit_id>")
def discovery_peek(hit_id):
    """HTMX partial: one discovery quick-peek panel."""
    try:
        repo = get_discovery_repo()
        hit = repo.get_hit_peek(hit_id)
        if not hit:
            return '<div class="text-red-400">Discovery hit not found</div>', 404
        return render_template("partials/intel/discovery_peek.html", hit=hit)
    except Exception as e:
        return f'<div class="text-red-400">Discovery peek unavailable: {e}</div>'


@intel_bp.route("/discovery/runs")
def discovery_runs():
    """HTMX partial: recent search and scrape runs."""
    try:
        repo = get_discovery_repo()
        return render_template(
            "partials/intel/discovery_run_list.html",
            search_runs=repo.get_recent_search_runs(limit=8),
            scrape_runs=repo.get_recent_scrape_runs(limit=8),
            selector_runs=repo.get_recent_selector_runs(limit=8),
        )
    except Exception as e:
        return f'<div class="text-red-400 text-sm">Discovery runs unavailable: {e}</div>'


@intel_bp.route("/discovery/<hit_id>")
def discovery_detail(hit_id):
    """HTMX partial: one discovery detail panel."""
    try:
        repo = get_discovery_repo()
        hit = repo.get_hit_detail(hit_id)
        if not hit:
            return '<div class="text-red-400">Discovery hit not found</div>', 404
        return render_template("partials/intel/discovery_detail.html", hit=hit)
    except Exception as e:
        return f'<div class="text-red-400">Discovery detail unavailable: {e}</div>'


@intel_bp.route("/discovery/queue")
def discovery_queue():
    """HTMX partial: queue snapshot, failures, and Langfuse info."""
    try:
        repo = get_discovery_repo()
        return render_template(
            "partials/intel/discovery_queue_panel.html",
            queue=repo.get_queue_snapshot(),
            failures=repo.get_recent_failures(limit=5),
            langfuse=repo.get_langfuse_panel(),
        )
    except Exception as e:
        return f'<div class="text-red-400 text-sm">Discovery queue unavailable: {e}</div>'


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_filters() -> dict:
    """Parse filter params from request args."""
    filters = {}
    if request.args.get("type"):
        filters["type"] = request.args["type"]
    if request.args.get("min_score"):
        filters["min_score"] = int(request.args["min_score"])
    if request.args.get("category"):
        filters["category"] = request.args["category"]
    if request.args.get("search"):
        filters["search"] = request.args["search"]
    if request.args.get("days"):
        days = int(request.args["days"])
        filters["since"] = datetime.now(timezone.utc) - timedelta(days=days)
    return filters


def _parse_discovery_filters() -> dict[str, object]:
    """Parse discovery page filters from request args."""
    failures_only = request.args.get("failures_only", "").lower() in {"1", "true", "yes", "on"}
    limit = request.args.get("limit", "25")
    try:
        parsed_limit = int(limit)
    except ValueError:
        parsed_limit = 25
    return {
        "query_text": request.args.get("q", "").strip() or None,
        "window": request.args.get("window", "24h"),
        "profile": request.args.get("profile", "").strip() or None,
        "region": request.args.get("region", "").strip() or None,
        "scrape_status": request.args.get("scrape_status", "").strip() or None,
        "main_decision": request.args.get("main_decision", "").strip() or None,
        "pool_status": request.args.get("pool_status", "").strip() or None,
        "failures_only": failures_only,
        "cursor": request.args.get("cursor", "").strip() or None,
        "limit": parsed_limit,
    }


def _trigger_runner(job_id: str) -> None:
    """Best-effort trigger of the pipeline runner."""
    runner_url = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
    runner_secret = os.getenv("RUNNER_API_SECRET", "")
    try:
        requests.post(
            f"{runner_url}/api/jobs/run",
            json={"job_id": job_id, "level": "full", "debug": False},
            headers={"X-API-Secret": runner_secret} if runner_secret else {},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Runner trigger failed (non-fatal): %s", e)


def _regenerate_with_anthropic(draft: dict, source_item: dict | None) -> str:
    """Regenerate a draft using the Anthropic Python SDK."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Add it to requirements.txt")

    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    draft_type = draft.get("draft_type", draft.get("type", "comment"))
    source_title = draft.get("source_title", "")
    source_content = ""
    if source_item:
        source_content = source_item.get("content_preview", "")[:1000]

    if draft_type == "comment":
        prompt = (
            f"Write a LinkedIn comment (max 150 words) about: {source_title}\n"
            f"Context: {source_content}\n"
            f"Tone: authoritative enterprise architect, practical, no generic praise."
        )
    else:
        prompt = (
            f"Generate a LinkedIn post idea as JSON with keys: title, hook, angle, outline (list), cta.\n"
            f"Inspired by: {source_title}\n"
            f"Context: {source_content}"
        )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
