"""Telegram interactive commands for LinkedIn Intelligence.

CLI script invoked by OpenClaw via subprocess:
    python3 telegram_commands.py /apply 3
    python3 telegram_commands.py /stats
    python3 telegram_commands.py /search "AI architect"

Each command prints its response to stdout (OpenClaw sends it to Telegram).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from bson import ObjectId

import mongo_store
from utils import setup_logging

logger = setup_logging("telegram-commands")


def get_today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def resolve_item(arg: str) -> dict | None:
    """Resolve an item by briefing index (number) or ObjectId."""
    db = mongo_store.get_db()
    if arg.isdigit():
        return db.linkedin_intel.find_one({
            "_briefing_index": int(arg),
            "_briefing_date": get_today_str(),
        })
    try:
        return db.linkedin_intel.find_one({"_id": ObjectId(arg)})
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_apply(arg: str) -> str:
    """Push a job to the pipeline."""
    item = resolve_item(arg)
    if not item:
        return f"Item {arg} not found. Use a briefing number or ObjectId."

    try:
        from pipeline_bridge import push_to_pipeline
        atlas_uri = os.environ.get("ATLAS_MONGODB_URI")
        if not atlas_uri:
            return "ATLAS_MONGODB_URI not configured. Cannot push to pipeline."

        result = push_to_pipeline(str(item["_id"]), atlas_uri=atlas_uri)
        if "error" in result:
            return f"Pipeline error: {result['error']}"

        # Trigger runner if configured
        runner_url = os.environ.get("RUNNER_URL")
        runner_secret = os.environ.get("RUNNER_API_SECRET")
        if runner_url and runner_secret:
            try:
                requests.post(
                    f"{runner_url}/api/jobs/run",
                    json={"job_id": result["job_id"], "level": "full", "debug": False},
                    headers={"X-API-Secret": runner_secret},
                    timeout=10,
                )
            except Exception as e:
                logger.warning("Runner trigger failed: %s", e)

        return (
            f"Pushed to pipeline:\n"
            f"  {result['role']} @ {result['company']}\n"
            f"  Job ID: {result['job_id']}\n"
            f"  Status: Pipeline triggered"
        )
    except Exception as e:
        logger.error("Apply failed: %s", e)
        return f"Apply failed: {e}"


def cmd_draft(arg: str) -> str:
    """Generate a draft for an item."""
    item = resolve_item(arg)
    if not item:
        return f"Item {arg} not found."

    db = mongo_store.get_db()
    existing = db.draft_content.find_one({"source_intel_id": item["_id"], "status": "draft"})
    if existing:
        content = existing.get("content", "")
        if isinstance(content, dict):
            return f"Existing post idea:\n  Hook: {content.get('hook', '')}\n  Angle: {content.get('angle', '')}"
        return f"Existing draft:\n{content}"

    return (
        f"No draft exists for: {item.get('title', 'Unknown')}\n"
        f"Run the evening analysis to generate drafts, or use the dashboard."
    )


def cmd_save(arg: str) -> str:
    """Bookmark an item."""
    item = resolve_item(arg)
    if not item:
        return f"Item {arg} not found."

    db = mongo_store.get_db()
    db.linkedin_intel.update_one(
        {"_id": item["_id"]},
        {"$set": {"acted_on": True, "acted_action": "saved", "acted_at": datetime.now(timezone.utc)}},
    )
    return f"Saved: {item.get('title', 'Unknown')[:60]}"


def cmd_detail(arg: str) -> str:
    """Full content of an item."""
    item = resolve_item(arg)
    if not item:
        return f"Item {arg} not found."

    lines = [
        f"{'=' * 40}",
        f"Title: {item.get('title', 'N/A')}",
        f"Type: {item.get('type', 'N/A')} | Score: {item.get('relevance_score', '?')}/10",
        f"Company: {item.get('company', item.get('author', 'N/A'))}",
        f"Location: {item.get('location', 'N/A')}",
    ]

    classification = item.get("classification", {})
    if classification:
        lines.append(f"Category: {classification.get('category', 'N/A')}")
        lines.append(f"Tags: {', '.join(classification.get('tags', []))}")
        lines.append(f"Reasoning: {classification.get('reasoning', 'N/A')}")

    edges = item.get("edge_opportunities", [])
    if edges:
        lines.append(f"Edge signals: {', '.join(edges)}")

    content = item.get("full_content") or item.get("content_preview", "")
    if content:
        lines.append(f"\n{content[:1500]}")

    if item.get("url"):
        lines.append(f"\n{item['url']}")

    return "\n".join(lines)


def cmd_skip(arg: str) -> str:
    """Mark as skipped."""
    item = resolve_item(arg)
    if not item:
        return f"Item {arg} not found."

    db = mongo_store.get_db()
    db.linkedin_intel.update_one(
        {"_id": item["_id"]},
        {"$set": {"acted_on": True, "acted_action": "skipped", "acted_at": datetime.now(timezone.utc)}},
    )
    return f"Skipped: {item.get('title', 'Unknown')[:60]}"


def cmd_lead(arg: str) -> str:
    """Move item to lead pipeline."""
    item = resolve_item(arg)
    if not item:
        return f"Item {arg} not found."

    db = mongo_store.get_db()
    db.lead_pipeline.insert_one({
        "source_intel_id": item["_id"],
        "title": item.get("title"),
        "company": item.get("company", item.get("author")),
        "url": item.get("url"),
        "relevance_score": item.get("relevance_score"),
        "classification": item.get("classification"),
        "status": "new",
        "created_at": datetime.now(timezone.utc),
    })
    db.linkedin_intel.update_one(
        {"_id": item["_id"]},
        {"$set": {"acted_on": True, "acted_action": "lead", "acted_at": datetime.now(timezone.utc)}},
    )
    return f"Added to lead pipeline: {item.get('title', 'Unknown')[:60]}"


def cmd_stats() -> str:
    """Today's intelligence stats."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    data = mongo_store.get_briefing_data(since)
    type_counts = data["type_counts"]

    daily_calls = mongo_store.get_today_call_count()
    cooldown = mongo_store.get_cooldown_state()
    status = "COOLDOWN" if cooldown else "OK"

    db = mongo_store.get_db()
    pending_drafts = db.draft_content.count_documents({"status": "draft"})
    acted = db.linkedin_intel.count_documents({"acted_on": True, "acted_at": {"$gte": since}})

    return (
        f"24h Stats:\n"
        f"  Total items: {data['total']}\n"
        f"  Jobs: {type_counts.get('job', 0)} | Posts: {type_counts.get('post', 0)}\n"
        f"  High-relevance (7+): {data['high_relevance']}\n"
        f"  Pending drafts: {pending_drafts}\n"
        f"  Acted on today: {acted}\n"
        f"  API calls: {daily_calls}/150 | Status: {status}"
    )


def cmd_search(query: str) -> str:
    """Manual keyword search in intel items."""
    db = mongo_store.get_db()
    results = list(db.linkedin_intel.find(
        {"$text": {"$search": query}},
        {"score": {"$meta": "textScore"}},
    ).sort([("score", {"$meta": "textScore"})]).limit(5))

    if not results:
        return f"No results for: {query}"

    lines = [f"Search results for '{query}':"]
    for i, r in enumerate(results, 1):
        score = r.get("relevance_score", "?")
        lines.append(f"{i}. [{score}/10] {r.get('title', 'Unknown')[:60]}")
        if r.get("company") or r.get("author"):
            lines.append(f"   {r.get('company') or r.get('author')}")
    return "\n".join(lines)


def cmd_pause() -> str:
    """Pause scraping for 24 hours."""
    mongo_store.set_cooldown(0, 24)  # status_code=0 means manual pause
    return "Scraping paused for 24 hours."


def cmd_resume() -> str:
    """Resume scraping by clearing cooldowns."""
    db = mongo_store.get_db()
    result = db.linkedin_sessions.delete_many({
        "type": "cooldown",
        "expires_at": {"$gt": datetime.now(timezone.utc)},
    })
    return f"Scraping resumed. Cleared {result.deleted_count} cooldown(s)."


def cmd_trends() -> str:
    """This week's trending keywords."""
    db = mongo_store.get_db()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    trends = list(db.linkedin_trends.find({"date": {"$gte": since}}).sort("date", -1).limit(10))

    if not trends:
        # Fallback: aggregate from intel items
        pipeline = [
            {"$match": {"scraped_at": {"$gte": since}}},
            {"$group": {"_id": "$search_keyword", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        kw_counts = list(db.linkedin_intel.aggregate(pipeline))
        if not kw_counts:
            return "No trend data available for the last 7 days."
        lines = ["Top keywords (7 days):"]
        for kw in kw_counts:
            lines.append(f"  {kw['_id']}: {kw['count']} items")
        return "\n".join(lines)

    lines = ["Trends (7 days):"]
    for t in trends:
        lines.append(f"  {t.get('period', '?')}: {t.get('keywords', [])}")
    return "\n".join(lines)


def cmd_next() -> str:
    """Next 3 unread high-relevance items."""
    db = mongo_store.get_db()
    items = list(db.linkedin_intel.find({
        "relevance_score": {"$gte": 7},
        "acted_on": {"$ne": True},
    }).sort("relevance_score", -1).limit(3))

    if not items:
        return "No unread high-relevance items."

    lines = ["Next up:"]
    for i, item in enumerate(items, 1):
        score = item.get("relevance_score", "?")
        title = item.get("title", "Unknown")[:50]
        company = item.get("company") or item.get("author", "")
        lines.append(f"[{i}] {score}/10 {title}")
        if company:
            lines.append(f"    {company}")
        lines.append(f"    /apply {i} | /detail {i} | /skip {i}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------

COMMANDS = {
    "/apply": ("arg", cmd_apply),
    "/draft": ("arg", cmd_draft),
    "/save": ("arg", cmd_save),
    "/detail": ("arg", cmd_detail),
    "/skip": ("arg", cmd_skip),
    "/lead": ("arg", cmd_lead),
    "/stats": ("none", cmd_stats),
    "/search": ("arg", cmd_search),
    "/pause": ("none", cmd_pause),
    "/resume": ("none", cmd_resume),
    "/trends": ("none", cmd_trends),
    "/next": ("none", cmd_next),
}


def dispatch(command: str, arg: str = "") -> str:
    """Dispatch a command and return the response text."""
    cmd_lower = command.lower()
    if cmd_lower not in COMMANDS:
        available = ", ".join(sorted(COMMANDS.keys()))
        return f"Unknown command: {command}\nAvailable: {available}"

    arg_type, handler = COMMANDS[cmd_lower]
    if arg_type == "arg":
        if not arg:
            return f"Usage: {command} <number or id>"
        return handler(arg)
    else:
        return handler()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 telegram_commands.py <command> [arg]")
        print(f"Commands: {', '.join(sorted(COMMANDS.keys()))}")
        sys.exit(1)

    command = sys.argv[1]
    arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    response = dispatch(command, arg)
    print(response)
