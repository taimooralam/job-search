"""
Proxy Pool Module — Rotating validated free proxies for LinkedIn scraping.

Architecture:
  - Validation is decoupled from usage via a separate cron job
  - scout_proxy_refresh_cron.py runs every 20 min: fetches, validates, saves cache
  - Scout cron just loads the pre-validated cache file — instant startup
  - ProxyPool provides round-robin get_proxy() and mark_failed() for removal

Sources (fetched by refresh cron):
  - proxifly/free-proxy-list (every ~5 min)
  - TheSpeedX/PROXY-List
  - jetkai/proxy-list (hourly)
  - vakhov/fresh-proxy-list (every 5-20 min)
  - komutan234/Proxy-List-Free (every 1-2 min)
  - iplocate/free-proxy-list (every 30 min)
"""

import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# CDN sources — raw text, one "ip:port" per line
PROXY_SOURCES = [
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    "https://vakhov.github.io/fresh-proxy-list/http.txt",
    "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
]

# Validation target — test against LinkedIn directly so only HTTPS-capable proxies pass
VALIDATION_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=test&start=0"
VALIDATION_TIMEOUT = 8  # seconds — must be enough for LinkedIn HTTPS round-trip
FETCH_TIMEOUT = 15  # seconds for fetching the proxy list

# Default path — resolved relative to project root
_DEFAULT_CACHE_PATH = Path(__file__).parent.parent.parent / "data" / "scout" / "proxies.json"


def _default_cache_path() -> Path:
    return _DEFAULT_CACHE_PATH


def _parse_proxy_lines(text: str) -> List[str]:
    """Parse proxy lines — handles both 'ip:port' and 'http://ip:port' formats."""
    proxies = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Already a full URL (proxifly format)
        if line.startswith("http://") or line.startswith("https://"):
            proxies.append(line)
            continue
        # Plain ip:port format (TheSpeedX format)
        parts = line.split(":")
        if len(parts) == 2:
            ip, port = parts[0].strip(), parts[1].strip()
            if ip and port.isdigit():
                proxies.append(f"http://{ip}:{port}")
    return proxies


def _validate_proxy(proxy_url: str) -> Optional[str]:
    """Test a single proxy against LinkedIn HTTPS. Returns the proxy URL if working, else None.

    Only proxies that return 200 from LinkedIn are accepted — this filters out
    Chinese proxies (451 redirect), blocked proxies (403), and flaky ones.
    """
    try:
        resp = requests.get(
            VALIDATION_URL,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=VALIDATION_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            return proxy_url
    except Exception:
        pass
    return None


def fetch_candidates() -> List[str]:
    """Fetch proxy candidates from all CDN sources, deduplicated and shuffled."""
    all_proxies: List[str] = []

    for url in PROXY_SOURCES:
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT)
            resp.raise_for_status()
            proxies = _parse_proxy_lines(resp.text)
            logger.info(f"ProxyPool: fetched {len(proxies)} candidates from {url}")
            all_proxies.extend(proxies)
        except Exception as e:
            logger.warning(f"ProxyPool: failed to fetch from {url}: {e}")
            continue

    # Deduplicate and shuffle to avoid geographic clustering
    unique = list(dict.fromkeys(all_proxies))
    random.shuffle(unique)
    return unique


def validate_parallel(candidates: List[str], max_workers: int = 50) -> List[str]:
    """Validate proxy candidates in parallel. Returns working proxies."""
    working: List[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {
            executor.submit(_validate_proxy, p): p for p in candidates
        }
        for future in as_completed(future_to_proxy):
            result = future.result()
            if result is not None:
                working.append(result)

    return working


def save_cache(proxies: List[str], cache_path: Optional[Path] = None) -> None:
    """Persist validated proxy list to cache file."""
    path = cache_path or _default_cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(proxies, f)
        logger.info(f"ProxyPool: saved {len(proxies)} proxies to {path}")
    except IOError as e:
        logger.warning(f"ProxyPool: failed to save cache: {e}")


class ProxyPool:
    """Round-robin rotating proxy pool — loads pre-validated proxies from cache.

    Usage:
        pool = ProxyPool()
        count = pool.initialize()          # loads from cache (written by refresh cron)
        proxy = pool.get_proxy()           # {"http": "...", "https": "..."}
        pool.mark_failed("http://ip:port") # removes from pool
    """

    def __init__(self, cache_path: Optional[str] = None) -> None:
        self._cache_path = Path(cache_path) if cache_path else _default_cache_path()
        self._pool: List[str] = []
        self._index: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> int:
        """Load pre-validated proxies from cache. Returns count of proxies.

        The cache is maintained by a separate refresh cron job. This method
        loads whatever is in the cache regardless of age — the refresh cron
        is responsible for keeping it fresh.
        """
        cached = self._load_cache()
        if cached:
            self._pool = cached
            logger.info(f"ProxyPool: loaded {len(self._pool)} proxies from cache")
            return len(self._pool)

        logger.warning("ProxyPool: no cached proxies found — will use direct requests")
        self._pool = []
        return 0

    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Return the next proxy in round-robin order.

        Returns a requests-compatible dict:
            {"http": "http://ip:port", "https": "http://ip:port"}

        Returns None (fall back to direct) if pool is exhausted.
        """
        if not self._pool:
            logger.debug("ProxyPool: pool empty, using direct connection")
            return None

        # Wrap index around pool size
        self._index = self._index % len(self._pool)
        url = self._pool[self._index]
        self._index += 1
        return {"http": url, "https": url}

    def mark_failed(self, proxy_url: str) -> None:
        """Remove a proxy that returned 429 or failed from the pool."""
        before = len(self._pool)
        self._pool = [p for p in self._pool if p != proxy_url]
        after = len(self._pool)
        if before != after:
            logger.debug(f"ProxyPool: removed failed proxy {proxy_url} ({after} remaining)")
            # Reset index so it doesn't go out of bounds
            if self._index >= len(self._pool):
                self._index = 0

    @property
    def size(self) -> int:
        """Number of proxies currently in the pool."""
        return len(self._pool)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_cache(self) -> Optional[List[str]]:
        """Load validated proxies from cache file.

        Returns list of proxy URLs, or None if cache is missing/corrupt.
        """
        if not self._cache_path.exists():
            return None

        try:
            with open(self._cache_path, "r") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"ProxyPool: cache read error ({e})")

        return None
