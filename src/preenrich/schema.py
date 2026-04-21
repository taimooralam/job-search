"""Schema and idempotency helpers for the iteration-4 preenrich DAG."""

from __future__ import annotations

import hashlib


def _sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def input_snapshot_id(
    jd_checksum: str,
    company_checksum: str,
    dag_version: str,
    *,
    taxonomy_version: str | None = None,
    required_set_version: str | None = None,
) -> str:
    """Build the stable snapshot identifier for one job input state."""
    parts = [jd_checksum, company_checksum, dag_version]
    if taxonomy_version:
        parts.append(taxonomy_version)
    if required_set_version:
        parts.append(required_set_version)
    raw = "|".join(parts)
    return f"sha256:{_sha256_hex(raw)}"


def idempotency_key(stage: str, level2_id: str, input_snapshot_id: str) -> str:
    """Build the canonical stage work-item idempotency key."""
    return f"preenrich.{stage}:{level2_id}:{input_snapshot_id}"


def attempt_token(
    job_id: str,
    stage: str,
    jd_checksum: str,
    prompt_version: str,
    attempt_number: int,
) -> str:
    """Build the stable completion token for one stage attempt."""
    raw = "|".join([job_id, stage, jd_checksum, prompt_version, str(attempt_number)])
    return _sha256_hex(raw)
