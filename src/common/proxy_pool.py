"""
Proxy Pool Module — Rotating validated free proxies for LinkedIn scraping.

Sources:
  - Primary:  https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt
  - Fallback: https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt

Strategy:
  - Fetch ~50 candidate proxies from CDN text sources (no scraping, plain GET)
  - Validate in parallel (up to 20 workers) by testing against httpbin.org/ip
  - Cache validated pool to data/scout/proxies.json for 30 minutes
  - Provide round-robin get_proxy() and mark_failed() for removal of bad proxies
  - Fall back to direct (no proxy) if pool is exhausted
"""

import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# CDN sources — raw text, one "ip:port" per line
PROXY_SOURCES = [
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
]

# Validation target — fast, lightweight, returns JSON with "origin" key
VALIDATION_URL = "http://httpbin.org/ip"
VALIDATION_TIMEOUT = 3  # seconds — slow proxies are useless
FETCH_TIMEOUT = 15  # seconds for fetching the proxy list

CACHE_MAX_AGE_SECONDS = 1800  # 30 minutes

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
    """Test a single proxy against httpbin. Returns the proxy URL if working, else None."""
    try:
        resp = requests.get(
            VALIDATION_URL,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=VALIDATION_TIMEOUT,
        )
        if resp.status_code == 200:
            return proxy_url
    except Exception:
        pass
    return None


class ProxyPool:
    """Round-robin rotating proxy pool with validation and caching.

    Usage:
        pool = ProxyPool()
        count = pool.initialize()          # fetches, validates, caches
        proxy = pool.get_proxy()           # {"http": "...", "https": "..."}
        pool.mark_failed("http://ip:port") # removes from pool
    """

    def __init__(
        self,
        cache_path: Optional[str] = None,
        min_proxies: int = 10,
        validate_count: int = 0,  # 0 = test all candidates
    ) -> None:
        self._cache_path = Path(cache_path) if cache_path else _default_cache_path()
        self._min_proxies = min_proxies
        self._validate_count = validate_count
        self._pool: List[str] = []
        self._index: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> int:
        """Fetch and validate proxies. Returns count of working proxies.

        Checks cache first; re-validates if cache is older than 30 minutes.
        Falls back to stale cache if fetching fails.
        """
        cached = self._load_cache()
        if cached is not None:
            self._pool = cached
            logger.info(f"ProxyPool: loaded {len(self._pool)} proxies from cache")
            return len(self._pool)

        candidates = self._fetch_candidates()
        if not candidates:
            logger.warning("ProxyPool: no candidate proxies fetched — will use direct requests")
            self._pool = []
            return 0

        test_count = len(candidates) if self._validate_count == 0 else min(self._validate_count, len(candidates))
        logger.info(
            f"ProxyPool: validating {test_count} "
            f"of {len(candidates)} candidates (up to 50 workers)…"
        )
        working = self._validate_parallel(candidates[:test_count])
        logger.info(
            f"ProxyPool: {len(candidates)} fetched → {test_count} "
            f"tested → {len(working)} working"
        )

        self._pool = working
        self._save_cache(working)
        return len(working)

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
        """Load validated proxies from cache if fresh (< 30 min).

        Returns list of proxy URLs, or None if cache is missing/stale/corrupt.
        """
        if not self._cache_path.exists():
            return None

        age = time.time() - self._cache_path.stat().st_mtime
        if age >= CACHE_MAX_AGE_SECONDS:
            logger.debug(f"ProxyPool: cache is {int(age)}s old — will re-validate")
            return None

        try:
            with open(self._cache_path, "r") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                logger.debug(f"ProxyPool: cache is {int(age)}s old — reusing {len(data)} proxies")
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"ProxyPool: cache read error ({e}) — will re-fetch")

        return None

    def _save_cache(self, proxies: List[str]) -> None:
        """Persist validated proxy list to cache file."""
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, "w") as f:
                json.dump(proxies, f)
            logger.debug(f"ProxyPool: saved {len(proxies)} proxies to {self._cache_path}")
        except IOError as e:
            logger.warning(f"ProxyPool: failed to save cache: {e}")

    def _fetch_candidates(self) -> List[str]:
        """Fetch proxy candidates from CDN sources, shuffled."""
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

    def _validate_parallel(self, candidates: List[str]) -> List[str]:
        """Validate proxy candidates in parallel. Returns working proxies."""
        working: List[str] = []

        with ThreadPoolExecutor(max_workers=50) as executor:
            future_to_proxy = {
                executor.submit(_validate_proxy, p): p for p in candidates
            }
            for future in as_completed(future_to_proxy):
                result = future.result()
                if result is not None:
                    working.append(result)

        return working
