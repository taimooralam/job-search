"""
Telegram Notification Module

Lightweight, non-blocking Telegram notifications for pipeline events.
Uses bot API directly — no external library needed (requests already in deps).

Environment variables:
    TELEGRAM_BOT_TOKEN: Bot API token
    TELEGRAM_CHAT_ID: Target chat ID
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """Send a message via Telegram Bot API.

    Args:
        message: Message text (HTML or plain)
        parse_mode: Parse mode (HTML or Markdown)

    Returns:
        True if sent successfully, False otherwise
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.debug("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        else:
            logger.warning(f"Telegram API error: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


def notify_cron_complete(
    searched: int,
    scored: int,
    new_after_dedup: int,
    inserted: int,
    queued: int,
    failed: int = 0,
) -> bool:
    """Notify about scout cron completion.

    Args:
        searched: Total jobs searched
        scored: Jobs with score > 0
        new_after_dedup: New jobs after MongoDB dedup
        inserted: Jobs inserted into MongoDB
        queued: Jobs queued for pipeline
        failed: Queue failures

    Returns:
        True if sent
    """
    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    status = "&#9888;" if failed > 0 else "&#9989;"

    lines = [
        f"{status} <b>Scout Cron Complete</b> ({now})",
        f"Searched: {searched} | Scored: {scored}",
        f"New: {new_after_dedup} | Inserted: {inserted}",
        f"Queued: {queued}",
    ]
    if failed > 0:
        lines.append(f"Queue failures: {failed}")

    return send_telegram("\n".join(lines))


def notify_pipeline_complete(
    job_id: str,
    company: str,
    role: str,
    duration_s: float,
    operation: str = "batch-pipeline",
    location: str = "",
    job_url: str = "",
) -> bool:
    """Notify about pipeline completion.

    Args:
        job_id: MongoDB job ID
        company: Company name
        role: Job title
        duration_s: Duration in seconds
        operation: Operation type
        location: Job location
        job_url: LinkedIn job URL

    Returns:
        True if sent
    """
    minutes = int(duration_s // 60)
    seconds = int(duration_s % 60)
    duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

    lines = [
        "&#9989; <b>Pipeline Complete</b>",
        f"<b>{company}</b> — {role}",
    ]
    if location:
        lines.append(location)
    lines.append(f"Duration: {duration_str} | Op: {operation}")
    if job_url:
        lines.append(job_url)
    return send_telegram("\n".join(lines))


def notify_pipeline_failed(
    job_id: str,
    company: str,
    role: str,
    error: str,
    run_id: Optional[str] = None,
    operation: str = "batch-pipeline",
) -> bool:
    """Notify about pipeline failure.

    Args:
        job_id: MongoDB job ID
        company: Company name
        role: Job title
        error: Error message
        run_id: Operation run ID for log lookup
        operation: Operation type

    Returns:
        True if sent
    """
    # Truncate error for Telegram
    error_short = error[:150] + "..." if len(error) > 150 else error

    lines = [
        "&#10060; <b>Pipeline Failed</b>",
        f"<b>{company}</b> — {role}",
        f"Error: <code>{error_short}</code>",
        f"Op: {operation}",
    ]
    if run_id:
        lines.append(f"Run: <code>{run_id[:16]}</code>")

    return send_telegram("\n".join(lines))
