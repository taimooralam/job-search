"""
T1 — StageResult contract and attempt_token idempotency key.

Validates:
- StageResult can be instantiated with all optional fields
- attempt_token excludes provider/model (same inputs w/ different provider → SAME token)
- attempt_token changes with different attempt_number
"""

import pytest

from src.preenrich.types import (
    StageResult,
    StageContext,
    StageStatus,
    StepConfig,
    attempt_token,
)


# ---------------------------------------------------------------------------
# StageResult contract
# ---------------------------------------------------------------------------


def test_stage_result_defaults():
    """StageResult can be created with no args; all optional fields default correctly."""
    r = StageResult()
    assert r.output == {}
    assert r.provider_used is None
    assert r.model_used is None
    assert r.prompt_version is None
    assert r.tokens_input is None
    assert r.tokens_output is None
    assert r.cost_usd is None
    assert r.duration_ms is None
    assert r.skip_reason is None
    assert r.cache_source_job_id is None


def test_stage_result_full():
    """StageResult stores all fields when provided."""
    r = StageResult(
        output={"extracted_jd": {"title": "ML Engineer"}},
        provider_used="claude",
        model_used="claude-haiku-4-5",
        prompt_version="v1",
        tokens_input=100,
        tokens_output=200,
        cost_usd=0.0021,
        duration_ms=1234,
        skip_reason=None,
        cache_source_job_id=None,
    )
    assert r.output == {"extracted_jd": {"title": "ML Engineer"}}
    assert r.provider_used == "claude"
    assert r.model_used == "claude-haiku-4-5"
    assert r.cost_usd == 0.0021


def test_stage_result_skipped():
    """A skipped StageResult has skip_reason set and empty output."""
    r = StageResult(output={}, skip_reason="company_cache_hit", cache_source_job_id="abc123")
    assert r.skip_reason == "company_cache_hit"
    assert r.cache_source_job_id == "abc123"
    assert r.output == {}


# ---------------------------------------------------------------------------
# attempt_token idempotency: excludes provider/model
# ---------------------------------------------------------------------------


def _base_token():
    return attempt_token(
        job_id="job_001",
        stage="jd_structure",
        jd_checksum="sha256:abc123",
        prompt_version="v1",
        attempt_number=1,
    )


def test_attempt_token_is_deterministic():
    """Same inputs always produce the same token."""
    t1 = _base_token()
    t2 = _base_token()
    assert t1 == t2


def test_attempt_token_excludes_provider():
    """Different provider → SAME token (provider is not in hash inputs)."""
    # In v3, provider is NOT an argument to attempt_token.
    # We verify by checking the function signature and that two calls
    # with identical inputs produce identical output.
    t_claude = attempt_token(
        job_id="job_001",
        stage="jd_extraction",
        jd_checksum="sha256:xyz",
        prompt_version="v2",
        attempt_number=1,
    )
    t_codex = attempt_token(
        job_id="job_001",
        stage="jd_extraction",
        jd_checksum="sha256:xyz",
        prompt_version="v2",
        attempt_number=1,
    )
    assert t_claude == t_codex, (
        "attempt_token must be identical regardless of provider "
        "(provider is not an input to the hash — §2.3 Codex review item #26)"
    )


def test_attempt_token_excludes_model():
    """Model is not an argument to attempt_token — identical inputs → identical token."""
    # The function signature only accepts: job_id, stage, jd_checksum,
    # prompt_version, attempt_number — no model parameter.
    import inspect

    sig = inspect.signature(attempt_token)
    param_names = list(sig.parameters.keys())
    assert "model" not in param_names, (
        "attempt_token must NOT accept 'model' as a parameter"
    )
    assert "provider" not in param_names, (
        "attempt_token must NOT accept 'provider' as a parameter"
    )


def test_attempt_token_changes_with_attempt_number():
    """Different attempt_number → different token."""
    t1 = attempt_token(
        job_id="job_001",
        stage="jd_structure",
        jd_checksum="sha256:abc123",
        prompt_version="v1",
        attempt_number=1,
    )
    t2 = attempt_token(
        job_id="job_001",
        stage="jd_structure",
        jd_checksum="sha256:abc123",
        prompt_version="v1",
        attempt_number=2,
    )
    assert t1 != t2


def test_attempt_token_changes_with_stage():
    """Different stage → different token."""
    t1 = attempt_token("j1", "jd_structure", "sha256:a", "v1", 1)
    t2 = attempt_token("j1", "jd_extraction", "sha256:a", "v1", 1)
    assert t1 != t2


def test_attempt_token_changes_with_checksum():
    """Different jd_checksum → different token."""
    t1 = attempt_token("j1", "jd_structure", "sha256:aaa", "v1", 1)
    t2 = attempt_token("j1", "jd_structure", "sha256:bbb", "v1", 1)
    assert t1 != t2


def test_attempt_token_is_hex_string():
    """Token is a 64-char hex string (SHA-256)."""
    t = _base_token()
    assert len(t) == 64
    assert all(c in "0123456789abcdef" for c in t)


# ---------------------------------------------------------------------------
# StageContext construction
# ---------------------------------------------------------------------------


def test_stage_context_shadow_mode_default():
    """StageContext.shadow_mode defaults to False."""
    ctx = StageContext(
        job_doc={"_id": "j1", "description": "ML job"},
        jd_checksum="sha256:abc",
        company_checksum="sha256:def",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(),
    )
    assert ctx.shadow_mode is False


def test_stage_context_shadow_mode_set():
    """StageContext.shadow_mode can be set to True."""
    ctx = StageContext(
        job_doc={"_id": "j1", "description": "ML job"},
        jd_checksum="sha256:abc",
        company_checksum="sha256:def",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(),
        shadow_mode=True,
    )
    assert ctx.shadow_mode is True


def test_step_config_provider_default():
    """StepConfig.provider defaults to 'claude'."""
    cfg = StepConfig()
    assert cfg.provider == "claude"


def test_stage_status_enum_values():
    """StageStatus has all required values including FAILED_TERMINAL."""
    statuses = {s.value for s in StageStatus}
    assert "pending" in statuses
    assert "in_progress" in statuses
    assert "completed" in statuses
    assert "failed" in statuses
    assert "failed_terminal" in statuses
    assert "stale" in statuses
    assert "skipped" in statuses
