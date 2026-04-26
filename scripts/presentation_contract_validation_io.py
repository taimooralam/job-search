from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bson import ObjectId

_UNSAFE_TARGET_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def load_validation_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Validation fixture must be a JSON object: {fixture_path}")

    job_doc = dict(payload)
    raw_id = job_doc.get("_id")
    if isinstance(raw_id, dict) and "$oid" in raw_id:
        raw_id = raw_id["$oid"]

    if isinstance(raw_id, ObjectId):
        job_doc["_id"] = raw_id
    elif isinstance(raw_id, str) and ObjectId.is_valid(raw_id):
        job_doc["_id"] = ObjectId(raw_id)
    else:
        job_doc["_id"] = ObjectId()

    if not str(job_doc.get("job_id") or "").strip():
        job_doc["job_id"] = f"fixture-{fixture_path.stem}"
    return job_doc


def validation_target_key(job_doc: dict[str, Any], *, fixture_path: str | Path | None = None) -> str:
    raw = str(job_doc.get("job_id") or job_doc.get("_id") or "").strip()
    if not raw and fixture_path is not None:
        raw = f"fixture-{Path(fixture_path).stem}"
    sanitized = _UNSAFE_TARGET_CHARS.sub("-", raw).strip(".-_")
    return sanitized or str(job_doc.get("_id") or "validation")
