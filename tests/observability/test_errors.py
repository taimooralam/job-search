"""record_error contract tests.

Pinned behaviours from iteration-4.4 §5.2 (review-amended):
- Fingerprint hash uses class | repo-relative POSIX path | top-frame func.
- ``lineno`` is NOT in the hash (refactor moves don't fork the bucket).
- Windows backslash paths are normalised to POSIX.
- Best-effort: ``record_error`` never raises even when Langfuse is missing.
- Project routing honours ``SCOUT_LANGFUSE_DEV`` and ``SCOUT_LANGFUSE_PROJECT``.
"""

from __future__ import annotations

import logging

from src.observability import errors as errors_mod
from src.observability.errors import fingerprint, record_error

# --------------------------------------------------------------------------- #
# fingerprint() — stability + line-number invariance
# --------------------------------------------------------------------------- #


def test_fingerprint_stable_across_calls_for_same_call_site():
    def boom() -> None:
        raise ValueError("a")

    fps: list[str] = []
    for _ in range(3):
        try:
            boom()
        except ValueError as exc:
            fps.append(fingerprint(exc))
    assert len(set(fps)) == 1, fps


def test_fingerprint_differs_across_exception_classes():
    def boom_value() -> None:
        raise ValueError("a")

    def boom_type() -> None:
        raise TypeError("a")

    try:
        boom_value()
    except ValueError as exc:
        fp_v = fingerprint(exc)
    try:
        boom_type()
    except TypeError as exc:
        fp_t = fingerprint(exc)
    assert fp_v != fp_t


def test_fingerprint_invariant_to_lineno_within_same_function():
    """Two raises in the same function should fingerprint identically.

    The §5.2 (amended) hash drops ``lineno`` so harmless refactors that move
    line numbers don't fork the error bucket.
    """

    def two_raises(which: int) -> None:
        if which == 0:
            raise ValueError("a")  # line A
        else:
            raise ValueError("b")  # line B (different line)

    try:
        two_raises(0)
    except ValueError as exc:
        fp_a = fingerprint(exc)
    try:
        two_raises(1)
    except ValueError as exc:
        fp_b = fingerprint(exc)
    assert fp_a == fp_b


def test_fingerprint_handles_exception_without_traceback():
    # An exception that was constructed but never raised has no __traceback__;
    # the fingerprinter must not crash.
    fp = fingerprint(RuntimeError("dangling"))
    assert isinstance(fp, str) and len(fp) == 40  # SHA-1 hex


# --------------------------------------------------------------------------- #
# record_error() — best-effort, never raises
# --------------------------------------------------------------------------- #


def test_record_error_swallows_when_langfuse_unconfigured(monkeypatch, caplog):
    # Strip Langfuse env so _langfuse_config returns None.
    for var in (
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_DEV_PUBLIC_KEY",
        "LANGFUSE_DEV_SECRET_KEY",
        "SCOUT_LANGFUSE_DEV",
        "SCOUT_LANGFUSE_PROJECT",
    ):
        monkeypatch.delenv(var, raising=False)

    try:
        raise RuntimeError("disabled-path smoke")
    except RuntimeError as exc:
        # Must not raise; must not log at WARNING (clean degraded path).
        with caplog.at_level(logging.WARNING, logger=errors_mod.logger.name):
            record_error(
                session_id="test_disabled",
                trace_id=None,
                pipeline="ad_hoc",
                stage="unit_test",
                exc=exc,
            )
    assert not caplog.records


def test_record_error_swallows_when_langfuse_client_raises(monkeypatch):
    """If the Langfuse SDK raises during construction, record_error must not propagate."""
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.delenv("SCOUT_LANGFUSE_DEV", raising=False)
    monkeypatch.delenv("SCOUT_LANGFUSE_PROJECT", raising=False)

    class ExplodingLangfuse:
        def __init__(self, **_kwargs):
            raise RuntimeError("simulated SDK failure")

    monkeypatch.setattr(errors_mod, "Langfuse", ExplodingLangfuse)

    try:
        raise ValueError("boom")
    except ValueError as exc:
        # Must not raise.
        record_error(
            session_id="s",
            trace_id=None,
            pipeline="ad_hoc",
            stage="unit_test",
            exc=exc,
        )


# --------------------------------------------------------------------------- #
# Project routing
# --------------------------------------------------------------------------- #


def test_project_routing_dev_via_explicit_flag(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-prod")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-prod")
    monkeypatch.setenv("LANGFUSE_DEV_PUBLIC_KEY", "pk-dev")
    monkeypatch.setenv("LANGFUSE_DEV_SECRET_KEY", "sk-dev")
    monkeypatch.setenv("SCOUT_LANGFUSE_DEV", "true")
    monkeypatch.delenv("SCOUT_LANGFUSE_PROJECT", raising=False)

    cfg = errors_mod._resolve_langfuse_config()
    assert cfg == {
        "host": "http://example.invalid",
        "public_key": "pk-dev",
        "secret_key": "sk-dev",
    }


def test_project_routing_dev_via_project_name(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-prod")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-prod")
    monkeypatch.setenv("LANGFUSE_DEV_PUBLIC_KEY", "pk-dev")
    monkeypatch.setenv("LANGFUSE_DEV_SECRET_KEY", "sk-dev")
    monkeypatch.delenv("SCOUT_LANGFUSE_DEV", raising=False)
    monkeypatch.setenv("SCOUT_LANGFUSE_PROJECT", "scout-dev")

    cfg = errors_mod._resolve_langfuse_config()
    assert cfg is not None
    assert cfg["public_key"] == "pk-dev"


def test_project_routing_dev_keys_missing_returns_none(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-prod")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-prod")
    monkeypatch.setenv("SCOUT_LANGFUSE_DEV", "true")
    monkeypatch.delenv("LANGFUSE_DEV_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_DEV_SECRET_KEY", raising=False)

    # Dev requested but not configured → None (and record_error degrades).
    assert errors_mod._resolve_langfuse_config() is None


def test_project_routing_defaults_to_prod(monkeypatch):
    monkeypatch.setenv("LANGFUSE_HOST", "http://example.invalid")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-prod")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-prod")
    monkeypatch.delenv("SCOUT_LANGFUSE_DEV", raising=False)
    monkeypatch.delenv("SCOUT_LANGFUSE_PROJECT", raising=False)

    cfg = errors_mod._resolve_langfuse_config()
    assert cfg is not None
    assert cfg["public_key"] == "pk-prod"


# --------------------------------------------------------------------------- #
# Path normalisation
# --------------------------------------------------------------------------- #


def test_normalise_frame_path_uses_forward_slashes_for_windows_paths(tmp_path):
    """Windows backslash paths must normalise to POSIX so fingerprints match
    Linux runs of the same bug."""
    win_path = "C:\\Users\\x\\some\\file.py"
    out = errors_mod._normalise_frame_path(win_path)
    assert "\\" not in out
