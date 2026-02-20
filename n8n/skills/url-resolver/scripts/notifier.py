"""Telegram notification for URL Resolver results.

Sends a summary of resolved URLs after each resolver run.
"""

import os
import sys

import requests

from utils import setup_logging

logger = setup_logging("url-resolver-notify")


def send_summary(results: list[dict]) -> bool:
    """Send a Telegram summary of URL resolution results.

    Args:
        results: List of dicts with keys: title, company, url, confidence, status, error
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False

    resolved = [r for r in results if r["status"] == "resolved"]
    failed = [r for r in results if r["status"] == "failed"]
    skipped = [r for r in results if r["status"] == "skipped"]
    fc_credits = sum(
        1 for r in results if r.get("resolution_method") == "firecrawl"
    )

    summary_parts = [
        f"Resolved: {len(resolved)}",
        f"Failed: {len(failed)}",
        f"Skipped: {len(skipped)}",
    ]
    if fc_credits:
        summary_parts.append(f"Firecrawl credits: {fc_credits}")

    lines = [
        "🔗 URL Resolver Summary",
        "",
        " | ".join(summary_parts),
    ]

    if resolved:
        lines.append("")
        lines.append("✅ Resolved:")
        for r in resolved:
            conf = r.get("confidence", 0)
            method = r.get("resolution_method", "agent")
            method_tag = " [FC]" if method == "firecrawl" else ""
            lines.append(f"• {r['title']} @ {r['company']}{method_tag}")
            lines.append(f"  {r['url']} ({conf:.0%})")

    if failed:
        lines.append("")
        lines.append("❌ Failed:")
        for r in failed:
            method = r.get("resolution_method", "agent")
            method_tag = " [FC]" if method == "firecrawl" else ""
            lines.append(f"• {r['title']} @ {r['company']}{method_tag}: {r.get('error', 'unknown')}")

    message = "\n".join(lines)

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        resp = requests.post(api_url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Notification sent successfully")
            return True
        else:
            logger.error("Telegram API error: %d — %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Failed to send notification: %s", e)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick test with dummy data
    test_results = [
        {
            "title": "Enterprise Architect",
            "company": "Acme Corp",
            "url": "https://boards.greenhouse.io/acme/jobs/12345",
            "confidence": 0.92,
            "status": "resolved",
        },
        {
            "title": "Solutions Architect",
            "company": "Beta Inc",
            "url": None,
            "confidence": 0,
            "status": "failed",
            "error": "no ATS URL found",
        },
    ]

    if "--test" in sys.argv:
        # Print instead of sending
        resolved = [r for r in test_results if r["status"] == "resolved"]
        failed = [r for r in test_results if r["status"] == "failed"]
        print(f"Would send: {len(resolved)} resolved, {len(failed)} failed")
        for r in test_results:
            print(f"  {r['status']}: {r['title']} @ {r['company']}")
    else:
        send_summary(test_results)
