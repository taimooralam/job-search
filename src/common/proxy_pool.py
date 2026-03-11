"""
Proxy Pool Module — Rotating free proxies for LinkedIn scraping.

Source: proxifly/free-proxy-list on GitHub (HTTPS-capable proxies).

Strategy per request:
  1. Try proxy #1 (random from pool)
  2. If fails → try proxy #2 (different random)
  3. If fails → fall back to direct request (no proxy)
  4. Log all failures to proxy_analytics.jsonl

Cache: proxy list is cached locally for 1 hour to avoid hammering the API.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

PROXIFLY_URL = (
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/"
    "proxies/protocols/http/data.json"
)

CACHE_MAX_AGE = 3600  # 1 hour in seconds
PROXY_TIMEOUT = 10  # seconds per proxy attempt


def _get_cache_path() -> Path:
    """Get path for the local proxy cache file."""
    from src.common.scout_queue import get_queue_dir
    return get_queue_dir() / "proxies.json"


def _get_analytics_path() -> Path:
    """Get path for the proxy analytics file."""
    from src.common.scout_queue import get_queue_dir
    return get_queue_dir() / "proxy_analytics.jsonl"


def load_proxy_pool() -> List[str]:
    """Fetch HTTPS-capable proxies from proxifly, with 1h local cache.

    Returns:
        List of proxy URLs (e.g., ["http://1.2.3.4:8080", ...]),
        sorted by score descending. Returns empty list on failure.
    """
    cache_path = _get_cache_path()

    # Check cache freshness
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_MAX_AGE:
            try:
                with open(cache_path, "r") as f:
                    cached = json.load(f)
                if cached:
                    logger.debug(f"Using cached proxy pool ({len(cached)} proxies, {int(age)}s old)")
                    return cached
            except (json.JSONDecodeError, IOError):
                pass

    # Fetch fresh list
    try:
        resp = requests.get(PROXIFLY_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch proxy list: {e}")
        # Try stale cache
        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    # Filter for HTTPS-capable, extract URLs, sort by score
    proxies = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if not entry.get("protocols", {}).get("https"):
            continue
        ip = entry.get("ip")
        port = entry.get("port")
        if ip and port:
            score = entry.get("score", 0)
            proxies.append((score, f"http://{ip}:{port}"))

    proxies.sort(reverse=True)  # highest score first
    proxy_urls = [url for _, url in proxies]

    # Cache
    try:
        with open(cache_path, "w") as f:
            json.dump(proxy_urls, f)
    except IOError as e:
        logger.warning(f"Failed to cache proxy list: {e}")

    logger.info(f"Loaded {len(proxy_urls)} HTTPS proxies from proxifly")
    return proxy_urls


def get_random_proxy(pool: List[str]) -> Optional[str]:
    """Pick a random proxy from the pool.

    Args:
        pool: List of proxy URLs

    Returns:
        Random proxy URL, or None if pool is empty
    """
    if not pool:
        return None
    return random.choice(pool)


def _make_proxy_dict(proxy_url: str) -> Dict[str, str]:
    """Build requests-compatible proxy dict."""
    return {"http": proxy_url, "https": proxy_url}


def log_proxy_failure(proxy_url: str, error: str, target_url: str, fell_back_to: str = ""):
    """Log a proxy failure to the analytics file.

    Args:
        proxy_url: The proxy that failed
        error: Error type/message
        target_url: The URL we were trying to fetch
        fell_back_to: What we fell back to ("proxy_2" or "direct")
    """
    analytics_path = _get_analytics_path()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "proxy": proxy_url,
        "error": str(error)[:200],
        "target_url": target_url[:200],
        "fell_back_to": fell_back_to,
    }
    try:
        with open(analytics_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except IOError:
        pass  # Best-effort analytics


def fetch_with_proxy(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = PROXY_TIMEOUT,
    pool: Optional[List[str]] = None,
    **kwargs: Any,
) -> requests.Response:
    """Fetch URL with proxy rotation and direct fallback.

    Strategy:
    1. Try random proxy #1
    2. On failure → try random proxy #2
    3. On failure → fall back to direct (no proxy)
    4. Raises if direct also fails

    Args:
        url: Target URL
        headers: Request headers
        timeout: Per-request timeout in seconds
        pool: Proxy pool (if None, loads fresh)
        **kwargs: Additional args passed to requests.get()

    Returns:
        Response object

    Raises:
        requests.RequestException: If all attempts fail (including direct)
    """
    if pool is None:
        pool = load_proxy_pool()

    proxy_errors = (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ConnectionError,
    )

    used_proxies = set()

    # Attempt 1: proxy #1
    if pool:
        proxy1 = get_random_proxy(pool)
        if proxy1:
            used_proxies.add(proxy1)
            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    proxies=_make_proxy_dict(proxy1),
                    **kwargs,
                )
                return resp
            except proxy_errors as e:
                log_proxy_failure(proxy1, type(e).__name__, url, fell_back_to="proxy_2")
                logger.debug(f"Proxy #1 failed ({proxy1}): {e}")

    # Attempt 2: proxy #2 (different from #1)
    remaining = [p for p in pool if p not in used_proxies]
    if remaining:
        proxy2 = random.choice(remaining)
        try:
            resp = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                proxies=_make_proxy_dict(proxy2),
                **kwargs,
            )
            return resp
        except proxy_errors as e:
            log_proxy_failure(proxy2, type(e).__name__, url, fell_back_to="direct")
            logger.debug(f"Proxy #2 failed ({proxy2}): {e}")

    # Attempt 3: direct (no proxy)
    logger.debug(f"Falling back to direct request for {url}")
    return requests.get(
        url,
        headers=headers,
        timeout=timeout,
        **kwargs,
    )
