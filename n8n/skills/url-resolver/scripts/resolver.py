"""URL Resolver — resolves direct application URLs for jobs in level-2.

Uses the OpenClaw agent (Sonnet) with web_fetch to discover ATS endpoints
(Greenhouse, Lever, Workday, etc.) and extract direct application URLs.

Usage:
    python3 resolver.py           # Full run: resolve + update MongoDB + notify
    python3 resolver.py --test    # 1 job, no DB write, prints output
    python3 resolver.py --dry-run # All jobs, no DB write, prints output
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlparse

# Ensure scripts/ is on the path for sibling imports
sys.path.insert(0, os.path.dirname(__file__))

import mongo_store
import notifier
from utils import load_config, setup_logging

logger = setup_logging("url-resolver")

OPENCLAW_BIN = "node"
OPENCLAW_SCRIPT = "/app/openclaw.mjs"
AGENT_ID = "url-resolver-sonnet"

# ── Firecrawl setup ──────────────────────────────────────────────
_firecrawl_app = None
_firecrawl_checked = False


def _get_firecrawl():
    """Lazy-init Firecrawl client. Returns None if unavailable."""
    global _firecrawl_app, _firecrawl_checked
    if _firecrawl_checked:
        return _firecrawl_app
    _firecrawl_checked = True

    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        logger.info("[firecrawl-fallback] FIRECRAWL_API_KEY not set — fallback disabled")
        return None

    try:
        from firecrawl import FirecrawlApp
        _firecrawl_app = FirecrawlApp(api_key=api_key)
        logger.info("[firecrawl-fallback] Firecrawl client initialized")
        return _firecrawl_app
    except ImportError:
        logger.warning("[firecrawl-fallback] firecrawl-py not installed — fallback disabled")
        return None


def build_prompt(job: dict, config: dict) -> str:
    """Build a concise prompt for the OpenClaw agent.

    Includes ATS hints to guide web_fetch attempts and minimize turns.
    """
    title = job.get("title", "Unknown")
    company = job.get("company", "Unknown")
    location = job.get("location", "")

    ats_domains = config["ats_domains"]
    blocked = config["blocked_domains"]

    # Build ATS hint list — common API patterns to try
    company_slug = company.lower().replace(" ", "").replace(".", "").replace(",", "")

    return f"""Find the direct job application URL for "{title}" at **{company}**{f' ({location})' if location else ''}.

CRITICAL: The URL MUST be for {company} specifically. Do NOT return URLs for other companies.

Strategy — try these in order using web_fetch:
1. boards-api.greenhouse.io/v1/boards/{company_slug}/jobs
2. jobs.lever.co/{company_slug}
3. {company_slug}.wd5.myworkdayjobs.com/en-US/careers (also try wd1, wd3)
4. The company website /careers page
5. If none work, try variations of the company name (e.g. with/without spaces, hyphens)

If you cannot find a URL specifically for {company}, return null. Do NOT guess or return a URL from a different company.

Blocked domains (NEVER return): {', '.join(blocked)}
Preferred ATS: {', '.join(ats_domains[:8])}

Return ONLY valid JSON (no markdown):
{{"application_url": "https://..." or null, "confidence": 0.0-1.0, "source": "brief description"}}"""


def resolve_with_agent(job: dict, config: dict) -> dict | None:
    """Use the OpenClaw Sonnet agent to find the application URL.

    The agent has web_fetch capability and can discover ATS endpoints
    by trying common patterns (Greenhouse API, Lever, Workday, etc.).

    Returns dict with: application_url, confidence, source
    Or None if resolution fails.
    """
    prompt = build_prompt(job, config)
    title = job.get("title", "Unknown")
    company = job.get("company", "Unknown")
    session_id = f"url-resolve-{job['_id']}"

    cmd = [
        OPENCLAW_BIN, OPENCLAW_SCRIPT, "agent",
        "--local",
        "--json",
        "--agent", AGENT_ID,
        "--session-id", session_id,
        "--thinking", "off",
        "--message", prompt,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 min max per job
        )

        output = result.stdout
        if not output:
            logger.error("Empty output from agent for %s @ %s", title, company)
            if result.stderr:
                logger.debug("Agent stderr: %s", result.stderr[:500])
            return None

        # Extract the last "text" field containing JSON from the agent output
        text_matches = re.findall(r'"text":\s*"((?:[^"\\]|\\.)*)"', output)
        if not text_matches:
            logger.error("No text fields found in agent output for %s @ %s", title, company)
            return None

        # Try each text match (from last to first) looking for valid JSON
        for text in reversed(text_matches):
            # Unescape JSON string
            text = text.encode().decode("unicode_escape")

            # Strip markdown code blocks if present
            if "```" in text:
                match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
                if match:
                    text = match.group(1).strip()

            # Try to find JSON object in the text
            json_match = re.search(r"\{[^{}]*\}", text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    if "application_url" in data:
                        logger.debug(
                            "Agent result for %s @ %s: %s",
                            title, company, json.dumps(data)[:300],
                        )
                        return data
                except json.JSONDecodeError:
                    continue

        logger.warning("Could not parse JSON from agent output for %s @ %s", title, company)
        logger.debug("Last text match: %s", text_matches[-1][:300] if text_matches else "none")
        return None

    except subprocess.TimeoutExpired:
        logger.error("Agent timed out for %s @ %s", title, company)
        return None
    except Exception as e:
        logger.error("Agent call failed for %s @ %s: %s", title, company, e)
        return None


def is_valid_url(url: str, config: dict) -> bool:
    """Validate that a resolved URL is acceptable (not blocked, not empty)."""
    if not url:
        return False

    blocked = config["blocked_domains"]
    for domain in blocked:
        if domain in url.lower():
            return False

    return url.startswith("http")


def _extract_search_results(response) -> list[dict]:
    """Normalize Firecrawl search response across SDK versions.

    v4.7 returns a list of dicts directly.
    v4.8+ returns an object with a .data attribute containing the list.
    """
    if isinstance(response, list):
        return response
    if hasattr(response, "data") and isinstance(response.data, list):
        return response.data
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return []


def resolve_with_firecrawl(job: dict, config: dict) -> dict | None:
    """Tier 2: Use Firecrawl search() to find ATS application URLs.

    Only called when the OpenClaw agent fails. Costs 1 Firecrawl credit per call.
    Scores results by matching URL domains against known ATS platforms.

    Returns dict with: application_url, confidence, source
    Or None if no suitable URL found.
    """
    if not config.get("firecrawl_enabled", False):
        return None

    app = _get_firecrawl()
    if not app:
        return None

    title = job.get("title", "Unknown")
    company = job.get("company", "Unknown")
    search_limit = config.get("firecrawl_search_limit", 3)
    ats_domains = set(config.get("ats_domains", []))
    blocked_domains = config.get("blocked_domains", [])

    company_slug = company.lower().replace(" ", "").replace(".", "").replace(",", "")
    query = f'"{company}" "{title}" apply careers'

    logger.info("[firecrawl-fallback] Searching: %s", query)

    try:
        response = app.search(query, limit=search_limit)
        results = _extract_search_results(response)

        if not results:
            logger.info("[firecrawl-fallback] No results for %s @ %s", title, company)
            return None

        best = None
        best_score = 0

        for item in results:
            url = item.get("url", "") if isinstance(item, dict) else getattr(item, "url", "")
            if not url:
                continue

            # Skip blocked domains
            if any(bd in url.lower() for bd in blocked_domains):
                continue

            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Score: ATS domain match → high confidence
            if any(ats in domain for ats in ats_domains):
                score = 0.9
            # Score: company slug in URL → medium confidence
            elif company_slug in url.lower():
                score = 0.7
            else:
                score = 0.3

            if score > best_score:
                best_score = score
                best = url

        if best and best_score >= config.get("confidence_threshold", 0.7):
            logger.info(
                "[firecrawl-fallback] Found: %s (score: %.2f) for %s @ %s",
                best, best_score, title, company,
            )
            return {
                "application_url": best,
                "confidence": best_score,
                "source": "firecrawl_search",
            }

        logger.info(
            "[firecrawl-fallback] No high-confidence result for %s @ %s (best: %.2f)",
            title, company, best_score,
        )
        return None

    except Exception as e:
        logger.error("[firecrawl-fallback] Search failed for %s @ %s: %s", title, company, e)
        return None


def resolve_jobs(
    test_mode: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """Main resolution loop.

    Args:
        test_mode: Process only 1 job, no DB writes, print output.
        dry_run: Process all jobs, no DB writes, print output.

    Returns:
        List of result dicts for notification.
    """
    config = load_config("ats-domains")
    limit = 1 if test_mode else config.get("batch_limit", 5)
    threshold = config.get("confidence_threshold", 0.7)
    delay_between_jobs = config.get("delay_between_jobs_s", 2)
    write_db = not test_mode and not dry_run

    logger.info(
        "Starting URL resolution (limit=%d, write_db=%s, threshold=%.2f)",
        limit, write_db, threshold,
    )

    jobs = mongo_store.get_jobs_needing_urls(limit=limit)
    if not jobs:
        logger.info("No jobs need URL resolution")
        return []

    results = []

    for i, job in enumerate(jobs):
        job_id = job["_id"]
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        current_url = job.get("application_url", "<none>")

        logger.info(
            "[%d/%d] Processing: %s @ %s (current: %s)",
            i + 1, len(jobs), title, company, current_url,
        )

        # ── Tier 1: OpenClaw agent (free — Sonnet + web_fetch) ────────
        extraction = resolve_with_agent(job, config)
        resolution_method = "agent"

        # ── Tier 2: Firecrawl fallback (1 credit per search) ─────────
        agent_failed = (
            not extraction
            or not extraction.get("application_url")
            or not is_valid_url(extraction.get("application_url", ""), config)
        )
        if agent_failed:
            logger.info(
                "Agent failed for %s @ %s — trying Firecrawl fallback",
                title, company,
            )
            fc_result = resolve_with_firecrawl(job, config)
            if fc_result:
                extraction = fc_result
                resolution_method = "firecrawl"

        # ── Evaluate result ──────────────────────────────────────────
        if not extraction:
            error = "agent and firecrawl returned no result"
            logger.warning("Resolution failed for %s @ %s", title, company)
            if write_db:
                mongo_store.increment_attempt(job_id, error)
            results.append({
                "title": title,
                "company": company,
                "url": None,
                "confidence": 0,
                "status": "failed",
                "error": error,
                "resolution_method": resolution_method,
            })
            if i < len(jobs) - 1:
                time.sleep(delay_between_jobs)
            continue

        url = extraction.get("application_url")
        confidence = extraction.get("confidence", 0)
        source = extraction.get("source", "")

        # Handle string confidence values (e.g. "high" -> 0.85)
        if isinstance(confidence, str):
            confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
            confidence = confidence_map.get(confidence.lower(), 0.5)

        # Validate
        if not is_valid_url(url, config):
            error = f"invalid or blocked URL: {url}"
            logger.warning("Invalid URL for %s @ %s: %s", title, company, url)
            if write_db:
                mongo_store.increment_attempt(job_id, error)
            results.append({
                "title": title,
                "company": company,
                "url": url,
                "confidence": confidence,
                "status": "failed",
                "error": error,
                "resolution_method": resolution_method,
            })
            if i < len(jobs) - 1:
                time.sleep(delay_between_jobs)
            continue

        if confidence < threshold:
            error = f"confidence {confidence:.2f} below threshold {threshold:.2f}"
            logger.warning(
                "Low confidence for %s @ %s: %.2f (URL: %s)",
                title, company, confidence, url,
            )
            if write_db:
                mongo_store.increment_attempt(job_id, error)
            results.append({
                "title": title,
                "company": company,
                "url": url,
                "confidence": confidence,
                "status": "failed",
                "error": error,
                "resolution_method": resolution_method,
            })
            if i < len(jobs) - 1:
                time.sleep(delay_between_jobs)
            continue

        # Success
        logger.info(
            "Resolved %s @ %s -> %s (confidence: %.2f, source: %s, method: %s)",
            title, company, url, confidence, source, resolution_method,
        )

        if test_mode or dry_run:
            print(f"\n{'='*60}")
            print(f"Job: {title} @ {company}")
            print(f"Resolved URL: {url}")
            print(f"Confidence: {confidence:.2f}")
            print(f"Source: {source}")
            print(f"Method: {resolution_method}")
            print(f"{'='*60}")

        if write_db:
            mongo_store.update_resolved_url(job_id, url, source, confidence)

        results.append({
            "title": title,
            "company": company,
            "url": url,
            "confidence": confidence,
            "status": "resolved",
            "resolution_method": resolution_method,
        })

        if i < len(jobs) - 1:
            time.sleep(delay_between_jobs)

    # Summary
    resolved = sum(1 for r in results if r["status"] == "resolved")
    failed = sum(1 for r in results if r["status"] == "failed")
    fc_used = sum(1 for r in results if r.get("resolution_method") == "firecrawl")
    fc_resolved = sum(
        1 for r in results
        if r.get("resolution_method") == "firecrawl" and r["status"] == "resolved"
    )
    logger.info(
        "Resolution complete: %d resolved, %d failed (firecrawl: %d used, %d resolved)",
        resolved, failed, fc_used, fc_resolved,
    )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Resolve application URLs for jobs")
    parser.add_argument(
        "--test", action="store_true",
        help="Process 1 job, no DB writes, print output",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Process all jobs, no DB writes, print output",
    )
    args = parser.parse_args()

    results = resolve_jobs(test_mode=args.test, dry_run=args.dry_run)

    # Send Telegram notification (only on real runs with results)
    if results and not args.test and not args.dry_run:
        notifier.send_summary(results)
