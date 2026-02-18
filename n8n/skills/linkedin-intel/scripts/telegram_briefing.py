"""Morning Telegram briefing — sends a daily intelligence summary.

Aggregates the last 24h of scraped data from MongoDB and formats it
into a structured Telegram message with stats, top jobs, engagement
targets, and health metrics.

Typical invocation (via cron at 7 AM daily):
    python3 telegram_briefing.py

Test mode (print to stdout, don't send):
    python3 telegram_briefing.py --test
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

import mongo_store
from utils import setup_logging

logger = setup_logging("telegram-briefing")


def compile_briefing() -> str:
    """Build the briefing message from the last 24h of data."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    data = mongo_store.get_briefing_data(since)
    drafts = mongo_store.get_drafts_for_briefing(since)

    date_str = datetime.now(timezone.utc).strftime("%A, %b %d")
    type_counts = data["type_counts"]
    jobs_count = type_counts.get("job", 0)
    posts_count = type_counts.get("post", 0) + type_counts.get("article", 0)
    opps_count = type_counts.get("opportunity", 0)

    lines = [
        f"📊 Morning Intelligence — {date_str}",
        "",
        f"Last 24h: {data['total']} new ({jobs_count} jobs, {posts_count} posts, {opps_count} opportunities)",
        f"High-relevance: {data['high_relevance']} items (score >= 7)",
    ]

    # Top jobs
    if data["top_jobs"]:
        lines.append("")
        lines.append("🎯 Top Jobs:")
        for i, job in enumerate(data["top_jobs"][:5], 1):
            score = job.get("relevance_score", "?")
            lines.append(f"{i}. {job.get('title', 'Unknown')} @ {job.get('company', 'Unknown')} — {score}/10")
            if job.get("url"):
                lines.append(f"   {job['url']}")

    # Posts to engage
    if data["posts_to_engage"]:
        lines.append("")
        lines.append("💬 Posts to Engage:")
        for i, post in enumerate(data["posts_to_engage"][:5], 1):
            preview = post.get("content_preview", "")[:80]
            lines.append(f"{i}. {post.get('author', 'Unknown')}: \"{preview}...\"")

            # Find matching draft comment
            matching_draft = next(
                (d for d in drafts if d.get("source_intel_id") == post["_id"] and d.get("type") == "comment"),
                None,
            )
            if matching_draft:
                draft_preview = matching_draft.get("content", "")[:100]
                lines.append(f"   💡 Draft: \"{draft_preview}...\"")

            if post.get("url"):
                lines.append(f"   {post['url']}")

    # Post ideas
    post_ideas = [d for d in drafts if d.get("type") == "post_idea"]
    if post_ideas:
        lines.append("")
        lines.append("✍️ Post Ideas:")
        for idea in post_ideas[:3]:
            content = idea.get("content", {})
            if isinstance(content, dict):
                lines.append(f"• {content.get('hook', 'No hook')}")
                lines.append(f"  Angle: {content.get('angle', '')}")

    # Health metrics
    lines.append("")
    lines.append("─────────────────")
    try:
        daily_calls = mongo_store.get_today_call_count()
        cooldown = mongo_store.get_cooldown_state()
        cookie_status = "⚠️ cooldown active" if cooldown else "✅ OK"
        lines.append(f"Health: {daily_calls}/150 API | Status: {cookie_status}")
    except Exception:
        lines.append("Health: unable to fetch metrics")

    return "\n".join(lines)


def send_briefing(message: str) -> bool:
    """Send the briefing via Telegram Bot API."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Briefing sent successfully")
            return True
        else:
            logger.error("Telegram API error: %d — %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Failed to send briefing: %s", e)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send daily Telegram briefing")
    parser.add_argument("--test", action="store_true", help="Print briefing to stdout instead of sending")
    args = parser.parse_args()

    briefing = compile_briefing()

    if args.test:
        print(briefing)
    else:
        success = send_briefing(briefing)
        if not success:
            sys.exit(1)
