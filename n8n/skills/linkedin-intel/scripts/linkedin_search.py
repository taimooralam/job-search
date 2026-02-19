"""LinkedIn scraper — the core data collection script.

Uses the `linkedin-api` library with cookie-based auth to search for
jobs and posts based on the day's rotation schedule. All calls are
gated through SafetyManager for rate limiting and account protection.

Content search (Phase 2) uses the pdf-service Playwright endpoint
because the Voyager GraphQL API returns null entityResults for content.

Typical invocation (via cron at 3 AM Mon-Sat):
    python3 linkedin_search.py

Test mode (validate cookies + 1 search call):
    python3 linkedin_search.py --test
"""

import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from linkedin_api import Linkedin

import mongo_store
from linkedin_cookies import get_linkedin_auth, load_cookies, validate_cookies
from safety_manager import SafetyManager
from utils import generate_dedupe_hash, load_config, setup_logging

logger = setup_logging("linkedin-search")


def get_todays_categories() -> tuple[list[str], dict]:
    """Return today's keyword categories and depth settings from rotation schedule."""
    schedule = load_config("rotation-schedule")
    day = datetime.now(timezone.utc).strftime("%A").lower()
    day_config = schedule["schedule"].get(day)

    if not day_config:
        return [], {}

    depth = schedule["depth_settings"][day_config["depth"]]
    return day_config["categories"], depth


def _extract_company_name(job_detail: dict) -> str:
    """Extract company name from get_job() response's nested companyDetails."""
    cd = job_detail.get("companyDetails", {})
    for key, val in cd.items():
        if isinstance(val, dict):
            res = val.get("companyResolutionResult", {})
            if isinstance(res, dict) and res.get("name"):
                return res["name"]
    return ""


def search_jobs(api: Linkedin, keywords: str, limit: int, safety: SafetyManager) -> list[dict]:
    """Search LinkedIn jobs with safety gating.

    Enriches each result with a get_job() call to fetch company name,
    location, and description (search_jobs only returns title + URN).
    """
    allowed, reason = safety.can_make_call()
    if not allowed:
        logger.warning("Skipping job search for '%s': %s", keywords, reason)
        return []

    try:
        safety.record_call()
        results = api.search_jobs(keywords=keywords, limit=limit)
        safety.wait_between_calls()

        items = []
        for job in results:
            job_id = job.get("entityUrn", "").split(":")[-1]
            if not job_id:
                continue

            # Enrich with full job details (company, location, description)
            company = ""
            location = ""
            description = ""
            allowed, reason = safety.can_make_call()
            if allowed:
                try:
                    safety.record_call()
                    detail = api.get_job(job_id)
                    safety.wait_between_calls()
                    company = _extract_company_name(detail)
                    location = detail.get("formattedLocation", "")
                    description = detail.get("description", {}).get("text", "") if isinstance(detail.get("description"), dict) else ""
                except Exception as e:
                    logger.warning("Failed to enrich job %s: %s", job_id, e)

            item = {
                "source": "linkedin",
                "type": "job",
                "title": job.get("title", ""),
                "company": company,
                "url": f"https://www.linkedin.com/jobs/view/{job_id}",
                "location": location,
                "content_preview": description[:500] if description else job.get("title", ""),
                "full_content": description,
                "raw_data": job,
                "search_keyword": keywords,
            }
            item["dedupe_hash"] = generate_dedupe_hash(item["source"], item["url"], item["title"])
            items.append(item)
        return items

    except Exception as e:
        _handle_api_error(e, safety)
        return []


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
        item = {
            "source": "linkedin",
            "type": "post",
            "title": (text[:120].split("\n")[0])[:200],
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


def harvest_feed_posts(api: Linkedin, all_keywords: list[str], limit: int, safety: SafetyManager) -> list[dict]:
    """Harvest relevant posts from the user's LinkedIn feed.

    The linkedin-api library doesn't support keyword-based content search
    (the GraphQL endpoint returns null entityResult for content type).
    Instead, we fetch the user's feed and filter by relevance keywords.

    This is actually higher quality — feed posts come from connections and
    followed topics, which are pre-filtered by LinkedIn's algorithm.
    """
    allowed, reason = safety.can_make_call()
    if not allowed:
        logger.warning("Skipping feed harvest: %s", reason)
        return []

    try:
        safety.record_call()
        posts = api.get_feed_posts(limit=limit)
        safety.wait_between_calls()

        # Build keyword set for matching (lowercase)
        kw_set = set()
        for kw in all_keywords:
            for word in kw.lower().split():
                if len(word) > 3:  # Skip short words like "AI" handled separately
                    kw_set.add(word)
        # Add key terms that might be split
        kw_set.update(["architect", "architecture", "togaf", "enterprise", "digital",
                        "transformation", "governance", "agentic", "multi-agent",
                        "platform", "modernization", "microservices", "cloud"])
        # Short but important terms checked separately
        short_terms = {"ai", "cto", "vp", "ml"}

        items = []
        for post in posts:
            content = post.get("content", "")
            if not content or len(content) < 50:
                continue

            content_lower = content.lower()
            matched = [kw for kw in kw_set if kw in content_lower]
            matched += [t for t in short_terms if f" {t} " in f" {content_lower} "]

            if len(matched) < 2:
                continue  # Require at least 2 keyword matches for relevance

            author = post.get("author_name", "Unknown")
            url = post.get("url", "")
            title = content[:120].split("\n")[0]  # First line as title

            item = {
                "source": "linkedin",
                "type": "post",
                "title": title,
                "author": author,
                "url": url,
                "content_preview": content[:500],
                "full_content": content,
                "matched_keywords": matched[:10],
                "raw_data": {k: v for k, v in post.items() if k != "old"},  # Skip bulky raw data
                "search_keyword": "feed_harvest",
            }
            item["dedupe_hash"] = generate_dedupe_hash(item["source"], item["url"], item["title"])
            items.append(item)
            logger.info("Feed post matched (%d keywords): %s by %s", len(matched), title[:60], author)

        logger.info("Feed harvest: %d posts fetched, %d matched keywords", len(posts), len(items))
        return items

    except Exception as e:
        _handle_api_error(e, safety)
        return []


def _handle_api_error(error: Exception, safety: SafetyManager) -> None:
    """Extract status code from API errors and trigger safety handling."""
    error_str = str(error)
    for code in (429, 403, 401):
        if str(code) in error_str:
            safety.handle_error(code)
            return
    logger.error("LinkedIn API error: %s", error)


def run_search(test_mode: bool = False) -> dict:
    """Execute the full search cycle.

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

    # Authenticate
    auth = get_linkedin_auth()
    api = Linkedin("", "", cookies=auth)
    logger.info("LinkedIn API initialized with cookie auth")

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
    results_per_kw = depth.get("results_per_keyword", 25)
    max_kw_per_cat = depth.get("max_keywords_per_category", 10)

    logger.info(
        "Search plan: categories=%s, results_per_kw=%d, max_kw_per_cat=%d",
        categories, results_per_kw, max_kw_per_cat,
    )

    # In test mode, do minimal work
    if test_mode:
        categories = categories[:1]
        max_kw_per_cat = 1
        results_per_kw = 5
        logger.info("TEST MODE: reduced to 1 category, 1 keyword, 5 results")

    stats = {"inserted": 0, "duplicate": 0, "errors": 0, "total_found": 0}

    # Collect all keywords across today's categories for feed filtering
    all_keywords = []
    for category in categories:
        all_keywords.extend(keywords_config.get(category, [])[:max_kw_per_cat])

    # Phase 1: Search jobs by keyword
    for category in categories:
        keywords = keywords_config.get(category, [])[:max_kw_per_cat]
        logger.info("Category '%s': %d keywords", category, len(keywords))

        for kw in keywords:
            allowed, reason = safety.can_make_call()
            if not allowed:
                logger.warning("Stopping job search: %s", reason)
                break

            jobs = search_jobs(api, kw, results_per_kw, safety)
            for item in jobs:
                item["category"] = category
                result = mongo_store.store_intel_item(item)
                stats[result] = stats.get(result, 0) + 1
                stats["total_found"] += 1
        else:
            continue
        break

    # Phase 2: Search posts by keyword (via pdf-service Playwright scrape)
    content_keywords = ["AI architect", "enterprise architecture", "agentic AI",
                        "digital transformation", "TOGAF", "platform engineering"]
    if test_mode:
        content_keywords = content_keywords[:2]
    for ckw in content_keywords:
        allowed, _ = safety.can_make_call()
        if not allowed:
            break
        posts = search_content(ckw, playwright_cookies, safety)
        for item in posts:
            item["category"] = "content_search"
            result = mongo_store.store_intel_item(item)
            stats[result] = stats.get(result, 0) + 1
            stats["total_found"] += 1

    # Phase 3: Harvest feed posts (single API call, keyword-filtered)
    feed_limit = 10 if test_mode else 50
    feed_posts = harvest_feed_posts(api, all_keywords, feed_limit, safety)
    for item in feed_posts:
        item["category"] = "feed"
        result = mongo_store.store_intel_item(item)
        stats[result] = stats.get(result, 0) + 1
        stats["total_found"] += 1

    # Log session
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
    logger.info("Session complete: %s", stats)
    logger.info("Session details: %s", summary)

    return session


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LinkedIn Intelligence Scraper")
    parser.add_argument("--test", action="store_true", help="Test mode: 1 keyword, minimal calls")
    args = parser.parse_args()

    result = run_search(test_mode=args.test)
    if "error" in result:
        sys.exit(1)
