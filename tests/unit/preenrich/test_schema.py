"""Tests for iteration-4 schema and idempotency helpers."""

from src.preenrich.schema import attempt_token, idempotency_key, input_snapshot_id


def test_input_snapshot_id_has_sha256_prefix_and_is_stable():
    first = input_snapshot_id("sha256:jd", "sha256:company", "v1")
    second = input_snapshot_id("sha256:jd", "sha256:company", "v1")

    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == 71


def test_input_snapshot_id_changes_when_any_input_changes():
    baseline = input_snapshot_id("sha256:jd", "sha256:company", "v1")
    assert baseline != input_snapshot_id("sha256:jd2", "sha256:company", "v1")
    assert baseline != input_snapshot_id("sha256:jd", "sha256:company2", "v1")
    assert baseline != input_snapshot_id("sha256:jd", "sha256:company", "v2")


def test_idempotency_key_matches_pinned_format():
    key = idempotency_key("jd_structure", "507f1f77bcf86cd799439011", "sha256:abc123")
    assert key == "preenrich.jd_structure:507f1f77bcf86cd799439011:sha256:abc123"


def test_attempt_token_excludes_provider_and_model():
    first = attempt_token("job-1", "jd_structure", "sha256:jd", "v1", 1)
    second = attempt_token("job-1", "jd_structure", "sha256:jd", "v1", 1)

    assert first == second
    assert len(first) == 64


def test_attempt_token_changes_with_attempt_number():
    assert attempt_token("job-1", "jd_structure", "sha256:jd", "v1", 1) != attempt_token(
        "job-1", "jd_structure", "sha256:jd", "v1", 2
    )
