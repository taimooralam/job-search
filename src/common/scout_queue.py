"""
Scout Queue Module — JSONL-based staging between search, scraper, and selector.

Two JSONL files:
  - queue.jsonl    — raw job_ids waiting to be scraped (Phase 1 → Phase 2)
  - scored.jsonl   — scraped + scored jobs waiting for selection (Phase 2 → Phase 3)

Queue directory:
  - VPS: /var/lib/scout/ (set SCOUT_QUEUE_DIR or auto-detected)
  - Local dev: data/scout/

File locks use a cross-platform abstraction: `fcntl.flock` on POSIX and
`msvcrt.locking` on Windows. Both paths honour a `LOCK_TIMEOUT` budget so the
contract is identical from the caller's perspective.
"""

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

LOCK_TIMEOUT = 5  # seconds

_IS_WINDOWS = sys.platform.startswith("win")

if _IS_WINDOWS:
    import msvcrt  # type: ignore[import-not-found]
else:
    import fcntl  # type: ignore[import-not-found]


def get_queue_dir() -> Path:
    """Get the scout queue directory, creating it if needed.

    Priority:
    1. SCOUT_QUEUE_DIR env var
    2. /var/lib/scout/ if it exists (VPS)
    3. data/scout/ relative to project root (local dev)
    """
    env_dir = os.getenv("SCOUT_QUEUE_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    vps_dir = Path("/var/lib/scout")
    if vps_dir.exists():
        return vps_dir

    # Local dev fallback
    project_root = Path(__file__).parent.parent.parent
    local_dir = project_root / "data" / "scout"
    local_dir.mkdir(parents=True, exist_ok=True)
    return local_dir


def _acquire_lock(fd, *, exclusive: bool, path: Path) -> None:
    """Platform-aware advisory lock with a shared timeout budget.

    POSIX path: `fcntl.flock` with `LOCK_NB` polling.
    Windows path: `msvcrt.locking(LK_NBLCK)` polling. Windows `msvcrt.locking`
    does not distinguish shared vs exclusive — all locks are exclusive, which
    is safe (never less safe than POSIX `LOCK_EX`, only less concurrent for
    readers). Reader paths in this module are short-lived so the loss is
    negligible.
    """
    deadline = time.monotonic() + LOCK_TIMEOUT
    if _IS_WINDOWS:
        # msvcrt.locking requires the file to contain the bytes we lock.
        # Lock 1 byte at offset 0 — the canonical Windows lockfile pattern.
        fd.seek(0)
        while True:
            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire {'exclusive' if exclusive else 'shared'} "
                        f"lock on {path} within {LOCK_TIMEOUT}s"
                    )
                time.sleep(0.1)
    else:
        mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        while True:
            try:
                fcntl.flock(fd, mode | fcntl.LOCK_NB)
                return
            except (IOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire {'exclusive' if exclusive else 'shared'} "
                        f"lock on {path} within {LOCK_TIMEOUT}s"
                    )
                time.sleep(0.1)


def _release_lock(fd) -> None:
    """Release the platform-appropriate lock previously taken on `fd`."""
    if _IS_WINDOWS:
        try:
            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            # Best-effort release — the fd close below frees the OS lock anyway.
            pass
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _file_lock(path: Path, exclusive: bool = True):
    """Acquire a file lock with timeout.

    Cross-platform: uses fcntl on POSIX, msvcrt on Windows. The `exclusive`
    distinction is honoured on POSIX via `LOCK_EX` vs `LOCK_SH`; on Windows
    all locks are exclusive (see `_acquire_lock`).

    Args:
        path: Path to the data file. A sibling `<path>.lock` file backs the lock.
        exclusive: True for writer lock, False for reader lock.
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    # msvcrt.locking needs at least 1 byte in the file to lock. Ensure it
    # exists and is non-empty before opening the fd. `r+b` is required on
    # Windows so msvcrt.locking can lock the region for both read and write
    # access patterns used by this module.
    if not lock_path.exists() or lock_path.stat().st_size == 0:
        lock_path.touch(exist_ok=True)
        with open(lock_path, "wb") as _seed:
            _seed.write(b"\0")
    fd = open(lock_path, "r+b")
    try:
        _acquire_lock(fd, exclusive=exclusive, path=path)
        yield
    finally:
        _release_lock(fd)
        fd.close()


def _read_jsonl(path: Path) -> List[Dict]:
    """Read all entries from a JSONL file."""
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed JSONL line in {path}")
    return entries


def _write_jsonl(path: Path, entries: List[Dict]):
    """Overwrite a JSONL file with entries."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, default=str) + "\n")


def _append_jsonl(path: Path, entries: List[Dict]):
    """Append entries to a JSONL file."""
    with open(path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, default=str) + "\n")


def enqueue_jobs(
    jobs: List[Dict],
    source_cron: str,
    search_profile: str = "",
) -> int:
    """Append new jobs to queue.jsonl, deduplicating against existing entries.

    Args:
        jobs: List of job dicts with at least job_id, title, company, location, job_url
        source_cron: Origin cron identifier ("hourly" or "ai_top15")
        search_profile: Search profile that found the job ("ai" or "engineering")

    Returns:
        Number of jobs actually enqueued (after dedup)
    """
    queue_dir = get_queue_dir()
    queue_file = queue_dir / "queue.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    scored_file = queue_dir / "scored.jsonl"
    dead_file = queue_dir / "queue_dead.jsonl"

    with _file_lock(queue_file, exclusive=True):
        existing = _read_jsonl(queue_file)
        existing_ids = {e["job_id"] for e in existing}

        # Also check scored.jsonl (already scraped, awaiting selection)
        scored_entries = _read_jsonl(scored_file)
        existing_ids.update(e["job_id"] for e in scored_entries if "job_id" in e)

        # Also check dead letter (permanently failed — no point re-enqueuing)
        dead_entries = _read_jsonl(dead_file)
        existing_ids.update(e["job_id"] for e in dead_entries if "job_id" in e)

        new_entries = []
        for job in jobs:
            jid = job.get("job_id")
            if not jid or jid in existing_ids:
                continue
            existing_ids.add(jid)
            new_entries.append({
                "job_id": jid,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "job_url": job.get("job_url", f"https://linkedin.com/jobs/view/{jid}"),
                "search_profile": search_profile or job.get("_search_profile", ""),
                "source_cron": source_cron,
                "enqueued_at": now,
                "retry_count": 0,
            })

        if new_entries:
            _append_jsonl(queue_file, new_entries)

    if new_entries:
        logger.info(f"Enqueued {len(new_entries)} jobs to {queue_file}")
    return len(new_entries)


def dequeue_batch(batch_size: int = 5) -> List[Dict]:
    """Pop the newest N entries from queue.jsonl (LIFO).

    Newest jobs are scraped first so fresh postings reach the selector
    before the quota fills up with stale entries.

    Args:
        batch_size: Number of jobs to dequeue

    Returns:
        List of dequeued job entries (newest first)
    """
    queue_dir = get_queue_dir()
    queue_file = queue_dir / "queue.jsonl"

    with _file_lock(queue_file, exclusive=True):
        entries = _read_jsonl(queue_file)
        if not entries:
            return []

        # LIFO: take from the end (newest enqueued first)
        batch = entries[-batch_size:]
        remaining = entries[:-batch_size] if len(entries) > batch_size else []
        _write_jsonl(queue_file, remaining)

    logger.info(f"Dequeued {len(batch)} jobs, newest first ({len(remaining)} remaining)")
    return batch


def append_scored(jobs: List[Dict]) -> int:
    """Append scored jobs to scored.jsonl.

    Args:
        jobs: List of scored job dicts

    Returns:
        Number of jobs appended
    """
    if not jobs:
        return 0

    queue_dir = get_queue_dir()
    scored_file = queue_dir / "scored.jsonl"

    with _file_lock(scored_file, exclusive=True):
        _append_jsonl(scored_file, jobs)

    logger.info(f"Appended {len(jobs)} scored jobs to {scored_file}")
    return len(jobs)


def scored_contains_job(job_id: str) -> bool:
    """Check whether scored.jsonl already contains a job_id."""
    queue_dir = get_queue_dir()
    scored_file = queue_dir / "scored.jsonl"
    with _file_lock(scored_file, exclusive=False):
        for entry in _read_jsonl(scored_file):
            if entry.get("job_id") == job_id:
                return True
    return False


def append_scored_unique(jobs: List[Dict]) -> int:
    """Append scored jobs only when their job_id is not already staged."""
    if not jobs:
        return 0

    queue_dir = get_queue_dir()
    scored_file = queue_dir / "scored.jsonl"

    with _file_lock(scored_file, exclusive=True):
        existing_ids = {
            entry.get("job_id")
            for entry in _read_jsonl(scored_file)
            if entry.get("job_id")
        }
        new_jobs = [job for job in jobs if job.get("job_id") and job.get("job_id") not in existing_ids]
        if new_jobs:
            _append_jsonl(scored_file, new_jobs)

    if new_jobs:
        logger.info(f"Appended {len(new_jobs)} unique scored jobs to {scored_file}")
    return len(new_jobs)


def read_and_clear_scored() -> List[Dict]:
    """Atomically read all scored entries and truncate the file.

    Returns:
        All scored entries
    """
    queue_dir = get_queue_dir()
    scored_file = queue_dir / "scored.jsonl"

    with _file_lock(scored_file, exclusive=True):
        entries = _read_jsonl(scored_file)
        if entries:
            # Truncate
            scored_file.write_text("")

    if entries:
        logger.info(f"Read and cleared {len(entries)} scored jobs")
    return entries


def purge_stale(max_age_hours: int = 48) -> int:
    """Remove entries older than max_age_hours from queue.jsonl.

    Args:
        max_age_hours: Maximum age in hours before purging

    Returns:
        Number of entries purged
    """
    queue_dir = get_queue_dir()
    queue_file = queue_dir / "queue.jsonl"
    now = datetime.now(timezone.utc)

    with _file_lock(queue_file, exclusive=True):
        entries = _read_jsonl(queue_file)
        if not entries:
            return 0

        fresh = []
        stale = []
        for entry in entries:
            enqueued_str = entry.get("enqueued_at", "")
            try:
                enqueued_at = datetime.fromisoformat(enqueued_str.replace("Z", "+00:00"))
                age_hours = (now - enqueued_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    stale.append(entry)
                else:
                    fresh.append(entry)
            except (ValueError, TypeError):
                # Can't parse date — keep it
                fresh.append(entry)

        if stale:
            _write_jsonl(queue_file, fresh)
            logger.info(f"Purged {len(stale)} stale entries (>{max_age_hours}h old)")

    return len(stale)


def move_to_dead_letter(entries: List[Dict], reason: str):
    """Move failed entries to queue_dead.jsonl with failure reason.

    Args:
        entries: Failed job entries
        reason: Why they failed
    """
    if not entries:
        return

    queue_dir = get_queue_dir()
    dead_file = queue_dir / "queue_dead.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    dead_entries = []
    for entry in entries:
        entry["dead_letter_reason"] = reason
        entry["dead_letter_at"] = now
        dead_entries.append(entry)

    with _file_lock(dead_file, exclusive=True):
        _append_jsonl(dead_file, dead_entries)

    logger.info(f"Moved {len(entries)} entries to dead letter: {reason}")


def queue_length() -> int:
    """Get current number of entries in queue.jsonl."""
    queue_dir = get_queue_dir()
    queue_file = queue_dir / "queue.jsonl"
    if not queue_file.exists():
        return 0
    with open(queue_file, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def scored_length() -> int:
    """Get current number of entries in scored.jsonl."""
    queue_dir = get_queue_dir()
    scored_file = queue_dir / "scored.jsonl"
    if not scored_file.exists():
        return 0
    with open(scored_file, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


# ---------------------------------------------------------------------------
# Scored Pool — persistent pool for dimensional selectors
# ---------------------------------------------------------------------------

POOL_MAX_AGE_HOURS = 48


def append_to_pool(jobs: List[Dict]) -> int:
    """Append scored jobs to scored_pool.jsonl with a timestamp.

    Returns:
        Number of jobs appended.
    """
    if not jobs:
        return 0
    queue_dir = get_queue_dir()
    pool_file = queue_dir / "scored_pool.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    with _file_lock(pool_file, exclusive=True):
        with open(pool_file, "a", encoding="utf-8") as f:
            for job in jobs:
                job["pooled_at"] = now
                f.write(json.dumps(job) + "\n")

    logger.info(f"Appended {len(jobs)} jobs to scored_pool.jsonl")
    return len(jobs)


def read_pool() -> List[Dict]:
    """Read all entries from scored_pool.jsonl (non-destructive)."""
    queue_dir = get_queue_dir()
    pool_file = queue_dir / "scored_pool.jsonl"

    with _file_lock(pool_file, exclusive=False):
        return _read_jsonl(pool_file)


def purge_pool(max_age_hours: int = POOL_MAX_AGE_HOURS) -> int:
    """Remove pool entries older than max_age_hours. Returns count purged."""
    queue_dir = get_queue_dir()
    pool_file = queue_dir / "scored_pool.jsonl"

    if not pool_file.exists():
        return 0

    cutoff = time.time() - (max_age_hours * 3600)

    with _file_lock(pool_file, exclusive=True):
        entries = _read_jsonl(pool_file)
        if not entries:
            return 0

        kept = []
        purged = 0
        for entry in entries:
            try:
                ts = datetime.fromisoformat(entry.get("pooled_at", "2000-01-01"))
                if ts.timestamp() >= cutoff:
                    kept.append(entry)
                else:
                    purged += 1
            except (ValueError, TypeError):
                purged += 1

        if purged:
            with open(pool_file, "w", encoding="utf-8") as f:
                for entry in kept:
                    f.write(json.dumps(entry) + "\n")

    if purged:
        logger.info(f"Purged {purged} stale entries from scored_pool.jsonl ({len(kept)} remaining)")
    return purged
