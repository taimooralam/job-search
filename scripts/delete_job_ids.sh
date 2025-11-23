#!/usr/bin/env bash
#
# Delete one or more job documents from MongoDB by jobId.
#
# USAGE:
#   scripts/delete_job_ids.sh <collection> <jobId1> [jobId2 ...]
#
# EXAMPLES:
#   scripts/delete_job_ids.sh level-1 123456
#   scripts/delete_job_ids.sh level-2 123456 789012 345678
#
# NOTES:
#   - Activates the local .venv before running the Python snippet.
#   - Collection is required (e.g., level-1, level-2).
#   - Accepts a space-separated list of jobIds to delete.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

if [[ $# -lt 2 ]]; then
  echo "Usage: scripts/delete_job_ids.sh <collection> <jobId1> [jobId2 ...]" >&2
  exit 1
fi

COLLECTION="$1"
shift
JOB_IDS=("$@")

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "Missing .venv. Create it with: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python - "$COLLECTION" "${JOB_IDS[@]}" <<'PY'
"""
Delete job documents from MongoDB by jobId for a given collection.
"""
import sys
from pathlib import Path
from typing import List, Sequence

# Ensure project root is on path for config import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import MongoClient

from src.common.config import Config


def normalize_job_ids(raw_job_ids: Sequence[str]) -> List[object]:
    """
    Return jobId variants to handle string and numeric storage formats.
    """
    normalized: List[object] = []
    for raw in raw_job_ids:
        normalized.append(raw)
        if raw.isdigit():
            normalized.append(int(raw))
    return normalized


def delete_job_ids(collection_name: str, job_ids: Sequence[str]) -> None:
    """
    Delete documents matching the provided jobIds from the collection.
    """
    if not Config.MONGODB_URI:
        raise ValueError("MONGODB_URI is not set. Please update your environment.")

    normalized_ids = normalize_job_ids(job_ids)

    with MongoClient(Config.MONGODB_URI) as client:
        db = client["jobs"]
        collection = db[collection_name]

        match_count = collection.count_documents({"jobId": {"$in": normalized_ids}})
        if match_count == 0:
            print(f"No documents found in '{collection_name}' for jobIds: {', '.join(job_ids)}")
            return

        result = collection.delete_many({"jobId": {"$in": normalized_ids}})
        print(
            f"Deleted {result.deleted_count} document(s) from '{collection_name}' "
            f"for jobIds: {', '.join(job_ids)}"
        )


def main() -> None:
    if len(sys.argv) < 3:
        print("Collection and at least one jobId are required.", file=sys.stderr)
        sys.exit(1)

    collection = sys.argv[1]
    ids = sys.argv[2:]
    try:
        delete_job_ids(collection, ids)
    except Exception as exc:  # noqa: BLE001
        print(f"Error deleting jobIds: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
PY
