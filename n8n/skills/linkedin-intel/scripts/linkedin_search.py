"""LinkedIn scraper — the core data collection script.

Uses the `linkedin-api` library with cookie-based auth to search for
jobs and posts based on the day's rotation schedule. All calls are
gated through SafetyManager for rate limiting and account protection.

Typical invocation (via cron at 3 AM Mon-Sat):
    python3 linkedin_search.py

Test mode (validate cookies + 1 search call):
    python3 linkedin_search.py --test
"""

import sys
import uuid
from datetime import datetime, timezone

from linkedin_api import Linkedin

import mongo_store
from linkedin_cookies import get_linkedin_auth, validate_cookies
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


def search_posts(api: Linkedin, keywords: str, limit: int, safety: SafetyManager) -> list[dict]:
    """Search LinkedIn posts/content with safety gating."""
    allowed, reason = safety.can_make_call()
    if not allowed:
        logger.warning("Skipping post search for '%s': %s", keywords, reason)
        return []

    try:
        safety.record_call()
        results = api.search(
            params={"keywords": keywords, "origin": "GLOBAL_SEARCH_HEADER"},
            limit=limit,
        )
        safety.wait_between_calls()

        items = []
        for result in results:
            # linkedin-api returns mixed types — filter for content
            entity_type = result.get("type", "")
            if entity_type not in ("CONTENT", "POST"):
                continue

            title = result.get("title", {}).get("text", "") if isinstance(result.get("title"), dict) else str(result.get("title", ""))
            author = result.get("subtitle", {}).get("text", "") if isinstance(result.get("subtitle"), dict) else ""

            item = {
                "source": "linkedin",
                "type": "post",
                "title": title[:200],
                "author": author,
                "url": result.get("navigationUrl", ""),
                "content_preview": result.get("summary", {}).get("text", "")[:500] if isinstance(result.get("summary"), dict) else "",
                "engagement": result.get("socialActivityCountsInsight", {}),
                "raw_data": result,
                "search_keyword": keywords,
            }
            item["dedupe_hash"] = generate_dedupe_hash(item["source"], item["url"], item["title"])
            items.append(item)
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

    for category in categories:
        keywords = keywords_config.get(category, [])[:max_kw_per_cat]
        logger.info("Category '%s': %d keywords", category, len(keywords))

        for kw in keywords:
            # Check safety before each keyword batch
            allowed, reason = safety.can_make_call()
            if not allowed:
                logger.warning("Stopping: %s", reason)
                break

            # Search jobs
            jobs = search_jobs(api, kw, results_per_kw, safety)
            for item in jobs:
                item["category"] = category
                result = mongo_store.store_intel_item(item)
                stats[result] = stats.get(result, 0) + 1
                stats["total_found"] += 1

            # Search posts
            posts = search_posts(api, kw, results_per_kw, safety)
            for item in posts:
                item["category"] = category
                result = mongo_store.store_intel_item(item)
                stats[result] = stats.get(result, 0) + 1
                stats["total_found"] += 1

        else:
            continue
        break  # Break outer loop if inner loop was stopped by safety

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
