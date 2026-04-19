"""Aggregate preenrich stage health into one periodic operator heartbeat."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient

from src.common.telegram import send_telegram


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_heartbeat(db: Any) -> dict[str, Any]:
    work_items = db["work_items"]
    stage_runs = db["preenrich_stage_runs"]
    completed_today = list(
        stage_runs.aggregate(
            [
                {
                    "$match": {
                        "status": "completed",
                        "$expr": {
                            "$gte": [
                                "$started_at",
                                {"$dateTrunc": {"date": "$$NOW", "unit": "day"}},
                            ]
                        },
                    }
                },
                {"$count": "count"},
            ]
        )
    )
    return {
        "pending": work_items.count_documents({"lane": "preenrich", "status": "pending"}),
        "leased": work_items.count_documents({"lane": "preenrich", "status": "leased"}),
        "deadletter": work_items.count_documents({"lane": "preenrich", "status": "deadletter"}),
        "completed_24h": completed_today[0]["count"] if completed_today else 0,
        "cv_ready": db["level-2"].count_documents({"lifecycle": "cv_ready"}),
    }


def send_heartbeat(db: Any) -> dict[str, Any]:
    snapshot = build_heartbeat(db)
    send_telegram(
        "\n".join(
            [
                "&#128994; <b>Preenrich Heartbeat</b>",
                f"pending={snapshot['pending']} leased={snapshot['leased']} deadletter={snapshot['deadletter']}",
                f"completed_24h={snapshot['completed_24h']} cv_ready={snapshot['cv_ready']}",
            ]
        )
    )
    return snapshot


def main() -> None:
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    snapshot = send_heartbeat(MongoClient(uri)["jobs"])
    print(json.dumps(snapshot, indent=2, default=str))


if __name__ == "__main__":
    main()
