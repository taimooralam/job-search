#!/usr/bin/env python3
"""Best-effort verification of Langfuse project retention capability."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth


def _base_url() -> Optional[str]:
    raw = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL")
    if not raw:
        return None
    return raw.rstrip("/")


def _extract_projects(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "projects"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _find_retention_field(document: Any) -> Optional[tuple[str, Any]]:
    if isinstance(document, dict):
        for key, value in document.items():
            if "retention" in key.lower():
                return key, value
            nested = _find_retention_field(value)
            if nested is not None:
                return nested
    if isinstance(document, list):
        for item in document:
            nested = _find_retention_field(item)
            if nested is not None:
                return nested
    return None


def main() -> int:
    base_url = _base_url()
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not (base_url and public_key and secret_key):
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "LANGFUSE_HOST/LANGFUSE_BASE_URL and LANGFUSE_PUBLIC_KEY/SECRET_KEY are required",
                }
            )
        )
        return 2

    response = requests.get(
        f"{base_url}/api/public/projects",
        auth=HTTPBasicAuth(public_key, secret_key),
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    projects = _extract_projects(payload)
    if not projects:
        print(json.dumps({"status": "unknown", "message": "No Langfuse projects returned by API"}))
        return 1

    requested_project_id = os.getenv("LANGFUSE_PROJECT_ID")
    selected = next((project for project in projects if project.get("id") == requested_project_id), projects[0])
    retention_field = _find_retention_field(selected)
    has_ee_key = bool(os.getenv("LANGFUSE_EE_LICENSE_KEY"))

    result = {
        "status": "unknown",
        "project_id": selected.get("id"),
        "project_name": selected.get("name"),
        "retention_available": False,
        "retention_field": None,
        "retention_value": None,
        "self_hosted_enterprise_hint": has_ee_key,
        "notes": [
            "Project-level retention is documented by Langfuse.",
            "Self-hosted retention policies are documented as an enterprise capability.",
        ],
    }

    if retention_field is not None:
        result["status"] = "ok"
        result["retention_available"] = True
        result["retention_field"] = retention_field[0]
        result["retention_value"] = retention_field[1]
    elif has_ee_key:
        result["status"] = "warning"
        result["notes"].append(
            "LANGFUSE_EE_LICENSE_KEY is set, but the project API response did not expose a retention field. Confirm in the Langfuse UI."
        )
    else:
        result["status"] = "warning"
        result["notes"].append(
            "No retention field detected in the project API response and no enterprise license hint found."
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["retention_available"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        print(json.dumps({"status": "error", "message": f"HTTP error: {exc}"}))
        raise SystemExit(2)
    except Exception as exc:  # pragma: no cover - operator script
        print(json.dumps({"status": "error", "message": str(exc)}))
        raise SystemExit(2)
