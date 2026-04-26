"""Cross-platform tests for the scout queue file-lock abstraction.

These exercise the POSIX `fcntl.flock` path on Linux/macOS and the
`msvcrt.locking` path on Windows without branching on platform in the
test body — both code paths must satisfy the same contract.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from src.common import scout_queue


@pytest.fixture
def scout_dir(tmp_path, monkeypatch) -> Path:
    """Isolate each test to its own SCOUT_QUEUE_DIR."""
    monkeypatch.setenv("SCOUT_QUEUE_DIR", str(tmp_path))
    return tmp_path


def test_platform_branch_matches_host():
    """The module must pick exactly one locking backend for the host OS."""
    is_win = sys.platform.startswith("win")
    assert scout_queue._IS_WINDOWS is is_win


def test_file_lock_round_trip_creates_lockfile(scout_dir):
    target = scout_dir / "queue.jsonl"
    target.write_text("")

    with scout_queue._file_lock(target, exclusive=True):
        pass

    lock_file = scout_dir / "queue.jsonl.lock"
    assert lock_file.exists()
    # msvcrt.locking needs ≥1 byte in the backing file; the POSIX path is
    # agnostic but the seed byte is harmless.
    assert lock_file.stat().st_size >= 1


def test_file_lock_serialises_concurrent_writers(scout_dir):
    """Two threads contending for the same exclusive lock must serialise."""
    target = scout_dir / "queue.jsonl"
    target.write_text("")

    order: list[str] = []
    holder_released = threading.Event()
    contender_started = threading.Event()

    def _holder():
        with scout_queue._file_lock(target, exclusive=True):
            order.append("holder_acquired")
            # Wait until the contender has definitely started trying.
            assert contender_started.wait(timeout=2.0)
            time.sleep(0.2)
            order.append("holder_releasing")
        holder_released.set()

    def _contender():
        contender_started.set()
        # Small head start so the holder is definitely inside the lock.
        time.sleep(0.05)
        with scout_queue._file_lock(target, exclusive=True):
            order.append("contender_acquired")

    t1 = threading.Thread(target=_holder)
    t2 = threading.Thread(target=_contender)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert order == ["holder_acquired", "holder_releasing", "contender_acquired"]
    assert holder_released.is_set()


def test_enqueue_dequeue_round_trip(scout_dir):
    """End-to-end sanity: enqueue then dequeue under the real lock."""
    scout_queue.enqueue_jobs(
        jobs=[
            {"job_id": "j1", "title": "Engineer", "company": "Acme"},
            {"job_id": "j2", "title": "Engineer", "company": "Acme"},
        ],
        source_cron="test",
        search_profile="engineering",
    )

    assert scout_queue.queue_length() == 2

    batch = scout_queue.dequeue_batch(batch_size=5)
    assert {entry["job_id"] for entry in batch} == {"j1", "j2"}
    assert scout_queue.queue_length() == 0


def test_enqueue_deduplicates_against_scored_and_dead(scout_dir):
    """Dedup must work regardless of platform locking backend."""
    scored_file = scout_dir / "scored.jsonl"
    scored_file.write_text('{"job_id": "j_scored"}\n')

    dead_file = scout_dir / "queue_dead.jsonl"
    dead_file.write_text('{"job_id": "j_dead"}\n')

    count = scout_queue.enqueue_jobs(
        jobs=[
            {"job_id": "j_scored", "title": "dup"},
            {"job_id": "j_dead", "title": "dup"},
            {"job_id": "j_new", "title": "fresh"},
        ],
        source_cron="test",
    )
    assert count == 1
    assert scout_queue.queue_length() == 1


def test_pool_append_and_read_round_trip(scout_dir):
    scout_queue.append_to_pool([{"job_id": "p1"}, {"job_id": "p2"}])
    entries = scout_queue.read_pool()
    assert {entry["job_id"] for entry in entries} == {"p1", "p2"}
    assert all("pooled_at" in entry for entry in entries)
