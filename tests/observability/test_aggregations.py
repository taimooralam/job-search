"""Aggregation correctness tests.

These tests pin the §9.2 rules from iteration-4.4: what counts as an error,
how fingerprints group, and how top-N rolls up. Pure unit tests — no Langfuse
dependency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.observability.langfuse_mcp.aggregations import (
    fingerprint_observation,
    group_by_fingerprint,
    is_error_observation,
    time_bucketed_rollup,
    top_n_errors,
    trace_summary,
)


def _obs(
    *,
    obs_id: str,
    name: str = "error.preenrich.jd_extraction",
    level: str = "ERROR",
    error_class: str | None = "ValueError",
    pipeline: str | None = "preenrich",
    stage: str | None = "jd_extraction",
    fingerprint: str | None = None,
    message: str = "boom",
    start_time: datetime | None = None,
    trace_id: str = "tr_1",
):
    payload: dict = {}
    if error_class is not None:
        payload["error_class"] = error_class
    if pipeline is not None:
        payload["pipeline"] = pipeline
    if stage is not None:
        payload["stage"] = stage
    if fingerprint is not None:
        payload["fingerprint"] = fingerprint
    payload["message"] = message
    return {
        "id": obs_id,
        "trace_id": trace_id,
        "session_id": "sess_1",
        "name": name,
        "level": level,
        "start_time": (start_time or datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)).isoformat(),
        "input": payload,
        "metadata": payload,
        "output": {},
    }


# --------------------------------------------------------------------------- #
# is_error_observation — covers all four §9.2 routes
# --------------------------------------------------------------------------- #


def test_is_error_via_level():
    assert is_error_observation(_obs(obs_id="a", level="ERROR", error_class=None))


def test_is_error_via_name_prefix():
    obs = _obs(obs_id="b", level="DEFAULT", name="error.cv_assembly.bullet_gen", error_class=None)
    assert is_error_observation(obs)


def test_is_error_via_error_class_in_payload():
    obs = _obs(obs_id="c", level="DEFAULT", name="span.scout.run", error_class="TimeoutError")
    assert is_error_observation(obs)


def test_non_error_observation_is_not_flagged():
    obs = _obs(
        obs_id="d",
        level="DEFAULT",
        name="span.scout.run",
        error_class=None,
        pipeline=None,
        stage=None,
    )
    assert not is_error_observation(obs)


# --------------------------------------------------------------------------- #
# fingerprint_observation — stored wins; fallback hashes class/pipeline/stage
# --------------------------------------------------------------------------- #


def test_fingerprint_prefers_stored_value():
    fp = "deadbeef" * 5
    obs = _obs(obs_id="e", fingerprint=fp)
    assert fingerprint_observation(obs) == fp


def test_fingerprint_fallback_is_stable_across_runs():
    a = _obs(obs_id="f", fingerprint=None)
    b = _obs(obs_id="g", fingerprint=None)
    assert fingerprint_observation(a) == fingerprint_observation(b)


def test_fingerprint_fallback_changes_with_class():
    a = _obs(obs_id="h", fingerprint=None, error_class="ValueError")
    b = _obs(obs_id="i", fingerprint=None, error_class="TypeError")
    assert fingerprint_observation(a) != fingerprint_observation(b)


# --------------------------------------------------------------------------- #
# group_by_fingerprint
# --------------------------------------------------------------------------- #


def test_group_by_fingerprint_collapses_repeats_and_skips_non_errors():
    fp = "abc" * 5 + "1"
    members = [
        _obs(obs_id="m1", fingerprint=fp),
        _obs(obs_id="m2", fingerprint=fp),
        _obs(obs_id="m3", fingerprint=fp),
        _obs(obs_id="ok", level="DEFAULT", name="span.x", error_class=None, pipeline=None, stage=None),
    ]
    grouped = group_by_fingerprint(members)
    assert set(grouped.keys()) == {fp}
    assert len(grouped[fp]) == 3


# --------------------------------------------------------------------------- #
# top_n_errors — count, ordering, projection
# --------------------------------------------------------------------------- #


def test_top_n_orders_by_count_desc_then_recency():
    base = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    fp_loud = "loud" * 10
    fp_quiet = "quiet" * 8
    fp_recent = "recent" * 7
    members = [
        _obs(obs_id=f"loud_{i}", fingerprint=fp_loud, start_time=base + timedelta(minutes=i))
        for i in range(5)
    ] + [
        _obs(obs_id="q_1", fingerprint=fp_quiet, start_time=base),
        _obs(obs_id="r_1", fingerprint=fp_recent, start_time=base + timedelta(hours=1)),
    ]
    top = top_n_errors(members, n=3)
    assert top[0]["fingerprint"] == fp_loud
    assert top[0]["count"] == 5
    # The two count=1 buckets — recency tiebreak puts the more recent first.
    assert {row["fingerprint"] for row in top[1:]} == {fp_quiet, fp_recent}


def test_top_n_zero_returns_empty():
    assert top_n_errors([_obs(obs_id="x")], n=0) == []


def test_top_n_includes_pipelines_and_stages_set():
    fp = "z" * 16
    members = [
        _obs(obs_id="p1", fingerprint=fp, pipeline="preenrich", stage="jd"),
        _obs(obs_id="p2", fingerprint=fp, pipeline="cv_assembly", stage="bullet"),
        _obs(obs_id="p3", fingerprint=fp, pipeline="preenrich", stage="jd"),
    ]
    [row] = top_n_errors(members, n=10)
    assert row["pipelines"] == ["cv_assembly", "preenrich"]
    assert row["stages"] == ["bullet", "jd"]


# --------------------------------------------------------------------------- #
# time_bucketed_rollup
# --------------------------------------------------------------------------- #


def test_time_bucketed_rollup_groups_by_window():
    base = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    members = [
        _obs(obs_id=f"o{i}", start_time=base + timedelta(minutes=i))
        for i in (0, 1, 4, 5, 6, 11)
    ]
    rollup = time_bucketed_rollup(members, bucket_minutes=5)
    counts = {row["bucket_start"]: row["count"] for row in rollup}
    assert counts[base.isoformat()] == 3                             # 0,1,4
    assert counts[(base + timedelta(minutes=5)).isoformat()] == 2    # 5,6
    assert counts[(base + timedelta(minutes=10)).isoformat()] == 1   # 11


def test_time_bucketed_rollup_rejects_nonpositive_bucket():
    with pytest.raises(ValueError):
        time_bucketed_rollup([], bucket_minutes=0)


def test_time_bucketed_rollup_skips_observations_without_timestamps():
    members = [
        {"id": "no_ts", "level": "ERROR", "input": {"error_class": "X"}},
        _obs(obs_id="ok"),
    ]
    rollup = time_bucketed_rollup(members, bucket_minutes=5)
    assert sum(row["count"] for row in rollup) == 1


# --------------------------------------------------------------------------- #
# trace_summary (iteration-4.4 §20)
# --------------------------------------------------------------------------- #


def test_trace_summary_truncates_io_and_normalises_keys():
    big_input = "x" * 500
    big_output = {"a": "y" * 500}
    trace = {
        "id": "t1",
        "name": "scout.search.run",
        "timestamp": "2026-04-28T10:00:00+00:00",
        "sessionId": "sess_a",
        "userId": None,
        "tags": ["region:eu"],
        "release": "0.1.0",
        "version": None,
        "input": big_input,
        "output": big_output,
        "metadata": {"env": "prod", "pipeline": "preenrich"},
    }
    summary = trace_summary(trace)
    assert summary["id"] == "t1"
    assert summary["session_id"] == "sess_a"  # camelCase normalised
    assert summary["tags"] == ["region:eu"]
    assert len(summary["input_preview"]) == 200
    assert summary["input_preview"].endswith("...")
    assert summary["output_preview"].startswith("{'a': 'y")
    assert summary["metadata"] == {"env": "prod", "pipeline": "preenrich"}


def test_trace_summary_handles_missing_optionals():
    summary = trace_summary({"id": "t2", "name": "x"})
    assert summary["id"] == "t2"
    assert summary["session_id"] is None
    assert summary["tags"] == []
    assert summary["input_preview"] == ""
    assert summary["output_preview"] == ""
    assert summary["metadata"] == {}
