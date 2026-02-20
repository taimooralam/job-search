"""LinkedIn Intelligence Pipeline — scrape, classify, draft.

Single-process pipeline that runs all three stages:
  1. Scrape: Search LinkedIn for posts via Playwright (pdf-service)
  2. Classify: Score each post with Claude Haiku for relevance
  3. Draft: Generate comment/post-idea drafts for high-scoring posts

Typical invocation (via cron at 3 AM Mon-Sat):
    python3 linkedin_search.py

Test mode (1 category, 2 keywords, then classify + draft):
    python3 linkedin_search.py --test

Scrape only (skip classify + draft):
    python3 linkedin_search.py --scrape-only
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests

import mongo_store
from linkedin_cookies import load_cookies, validate_cookies
from safety_manager import SafetyManager
from utils import generate_dedupe_hash, load_config, setup_logging

logger = setup_logging("linkedin-search")

MAX_POSTS_PER_RUN = 50


def get_todays_categories() -> tuple[list[str], dict]:
    """Return today's keyword categories and depth settings from rotation schedule."""
    schedule = load_config("rotation-schedule")
    day = datetime.now(timezone.utc).strftime("%A").lower()
    day_config = schedule["schedule"].get(day)

    if not day_config:
        return [], {}

    depth = schedule["depth_settings"][day_config["depth"]]
    return day_config["categories"], depth


def search_content(keywords: str, cookies: list[dict], safety: SafetyManager) -> list[dict]:
    """Search LinkedIn posts via Playwright-rendered page (pdf-service).

    The Voyager GraphQL API returns null entityResult for content searches.
    Instead, we ask pdf-service to render the search page in a real browser
    and extract post data from the DOM.
    """
    allowed, reason = safety.can_make_call()
    if not allowed:
        logger.warning("Skipping content search for '%s': %s", keywords, reason)
        return []

    safety.record_call()
    url = (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={quote(keywords)}&origin=SWITCH_SEARCH_VERTICAL"
        f"&sortBy=%22date_posted%22"
    )

    pdf_svc = os.environ.get("PDF_SERVICE_URL", "http://pdf-service:8001")
    try:
        resp = requests.post(
            f"{pdf_svc}/scrape-linkedin",
            json={"url": url, "cookies": cookies, "scroll_count": 2},
            timeout=90,
        )
        safety.wait_between_calls()
    except requests.RequestException as e:
        logger.error("PDF service unreachable: %s", e)
        return []

    if resp.status_code != 200:
        logger.warning("Scrape failed (%d): %s", resp.status_code, resp.text[:200])
        return []

    raw_posts = resp.json().get("results", [])
    items = []
    for post in raw_posts:
        text = post.get("text", "")
        # Strip LinkedIn accessibility prefix ("Feed post\n...") from title
        title_text = text
        for prefix in ("Feed post\n", "Feed post "):
            if title_text.startswith(prefix):
                title_text = title_text[len(prefix):]
                break
        item = {
            "source": "linkedin",
            "type": "post",
            "title": (title_text[:120].split("\n")[0].strip())[:200],
            "author": post.get("author", ""),
            "url": post.get("url", ""),
            "content_preview": text[:500],
            "full_content": text,
            "raw_data": post,
            "search_keyword": keywords,
        }
        item["dedupe_hash"] = generate_dedupe_hash(item["source"], item["url"], item["title"])
        items.append(item)

    logger.info("Content search '%s': %d posts found via Playwright", keywords, len(items))
    return items


def run_search(test_mode: bool = False) -> dict:
    """Execute the post search cycle.

    Searches LinkedIn for posts matching today's scheduled keyword categories.
    Keywords are derived from AI architect knowledge domains.

    Returns session summary dict.
    """
    session_id = str(uuid.uuid4())
    safety = SafetyManager()

    # Validate cookies first
    validation = validate_cookies()
    if not validation["valid"]:
        msg = f"Cookie validation failed: {validation}"
        logger.error(msg)
        safety._send_alert(f"🔴 LinkedIn Intel: {msg}")
        return {"error": msg}

    # Build Playwright-format cookies for content search (pdf-service)
    raw_cookies = load_cookies()
    playwright_cookies = [
        {"name": name, "value": value, "domain": ".linkedin.com", "path": "/"}
        for name, value in raw_cookies.items()
    ]

    # Get today's rotation
    categories, depth = get_todays_categories()
    if not categories:
        logger.info("No categories scheduled for today — skipping")
        return {"skipped": True, "reason": "No categories scheduled"}

    keywords_config = load_config("target-keywords")
    max_kw_per_cat = depth.get("max_keywords_per_category", 6)

    logger.info(
        "Search plan: categories=%s, max_kw_per_cat=%d",
        categories, max_kw_per_cat,
    )

    # In test mode, do minimal work
    if test_mode:
        categories = categories[:1]
        max_kw_per_cat = 2
        logger.info("TEST MODE: reduced to 1 category, 2 keywords")

    stats = {"inserted": 0, "duplicate": 0, "errors": 0, "total_found": 0}
    cap_reached = False

    # Search posts by keyword (via pdf-service Playwright scrape)
    for category in categories:
        if cap_reached:
            break
        keywords = keywords_config.get(category, [])[:max_kw_per_cat]
        logger.info("Category '%s': %d keywords", category, len(keywords))

        for kw in keywords:
            if cap_reached:
                break
            allowed, reason = safety.can_make_call()
            if not allowed:
                logger.warning("Stopping content search: %s", reason)
                cap_reached = True
                break

            posts = search_content(kw, playwright_cookies, safety)
            for item in posts:
                item["category"] = category
                result = mongo_store.store_intel_item(item)
                stats[result] = stats.get(result, 0) + 1
                stats["total_found"] += 1

            if stats["inserted"] >= MAX_POSTS_PER_RUN:
                logger.info("Global cap reached (%d/%d inserted) — stopping", stats["inserted"], MAX_POSTS_PER_RUN)
                cap_reached = True

    # Log scrape session
    summary = safety.get_session_summary()
    session = {
        "session_id": session_id,
        "started_at": safety.session_start,
        "completed_at": datetime.now(timezone.utc),
        "calls_made": safety.session_calls,
        "categories_searched": categories,
        "stats": stats,
        "is_test": test_mode,
        **summary,
    }
    mongo_store.log_session(session)
    logger.info("Scrape complete: %s", stats)
    logger.info("Scrape details: %s", summary)

    return session


def run_pipeline(test_mode: bool = False, scrape_only: bool = False) -> dict:
    """Execute the full pipeline: scrape → classify → draft.

    Returns combined results from all stages.
    """
    # Stage 1: Scrape
    logger.info("=" * 60)
    logger.info("STAGE 1: SCRAPE")
    logger.info("=" * 60)
    scrape_result = run_search(test_mode=test_mode)

    if "error" in scrape_result or scrape_only:
        return scrape_result

    # Stage 2: Classify
    logger.info("=" * 60)
    logger.info("STAGE 2: CLASSIFY (model: haiku)")
    logger.info("=" * 60)
    try:
        from classifier import classify_items
        classify_result = classify_items(test_mode=test_mode)
        logger.info("Classify result: %s", classify_result)
    except Exception as e:
        logger.error("Classification failed (non-fatal): %s", e)
        classify_result = {"classified": 0, "errors": 1, "error": str(e)}

    # Stage 3: Draft
    logger.info("=" * 60)
    logger.info("STAGE 3: DRAFT (model: haiku)")
    logger.info("=" * 60)
    try:
        from draft_generator import generate_drafts
        draft_result = generate_drafts(test_mode=test_mode)
        logger.info("Draft result: %s", draft_result)
    except Exception as e:
        logger.error("Draft generation failed (non-fatal): %s", e)
        draft_result = {"comments": 0, "post_ideas": 0, "errors": 1, "error": str(e)}

    combined = {
        "scrape": scrape_result.get("stats", {}),
        "classify": classify_result,
        "drafts": draft_result,
    }
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE: %s", combined)
    logger.info("=" * 60)

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LinkedIn Intelligence Pipeline")
    parser.add_argument("--test", action="store_true", help="Test mode: 1 category, 2 keywords")
    parser.add_argument("--scrape-only", action="store_true", help="Skip classify + draft stages")
    args = parser.parse_args()

    result = run_pipeline(test_mode=args.test, scrape_only=args.scrape_only)
    if "error" in result:
        sys.exit(1)
