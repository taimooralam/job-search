#!/usr/bin/env bash
#
# Export recent job IDs to markdown files, optionally grouped by location.
#
# USAGE:
#   scripts/export_recent_job_ids.sh [OPTIONS]
#
# OPTIONS:
#   --days N         Days back from today to include (default: 14)
#   --collection C   MongoDB collection to query (default: level-1)
#   --output FILE    Output file path (default: assets/pipeline.md)
#   --by-location    Group jobs by location into separate files under assets/by-location/.
#                    Optionally pass a location string right after the flag to filter results
#                    (e.g. --by-location "United Arab Emirates").
#   --location L     Filter results to locations matching L (case-insensitive regex escape)
#   --help           Show this help message
#
# EXAMPLES:
#   # Export last 14 days to assets/pipeline.md
#   scripts/export_recent_job_ids.sh
#
#   # Export last 7 days
#   scripts/export_recent_job_ids.sh --days 7
#
#   # Export grouped by location
#   scripts/export_recent_job_ids.sh --by-location
#
#   # Export last 30 days, grouped by location, from level-2 collection
#   scripts/export_recent_job_ids.sh --days 30 --collection level-2 --by-location
#   # Export last 7 days only for United Arab Emirates
#   scripts/export_recent_job_ids.sh --days 7 --collection level-2 --by-location "United Arab Emirates"
#
# OUTPUT:
#   Default: Single file with job IDs, one per line
#   With --by-location: Creates assets/by-location/<location>.md for each location
#                       Uses "unknown" for jobs without location data
#

set -euo pipefail

# Defaults
DAYS=14
COLLECTION="level-1"
OUTPUT="assets/pipeline.md"
BY_LOCATION=false
LOCATION_FILTER=""

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)
      DAYS="$2"
      shift 2
      ;;
    --collection)
      COLLECTION="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --by-location)
      BY_LOCATION=true
      if [[ $# -gt 1 && "$2" != --* ]]; then
        LOCATION_FILTER="$2"
        shift 2
      else
        shift
      fi
      ;;
    --location)
      LOCATION_FILTER="$2"
      shift 2
      ;;
    --help|-h)
      # Print help from header comments
      sed -n '2,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Use --help for usage information" >&2
      exit 1
      ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Run the Python export logic
python - "$DAYS" "$COLLECTION" "$OUTPUT" "$BY_LOCATION" "$LOCATION_FILTER" <<'PY'
"""
Export recent job IDs from MongoDB.
Supports flat output or grouping by location.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
import re

# Add project root to path for config import
PROJECT_ROOT = Path(__file__).resolve().parent if '__file__' in dir() else Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import MongoClient
from src.common.config import Config


def build_created_at_regex(start: datetime, end: datetime) -> str:
    """Build regex matching ISO date prefixes between start and end (inclusive)."""
    dates: List[str] = []
    current = start.date()
    end_date = end.date()
    while current <= end_date:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return f"^({'|'.join(dates)})"


def sanitize_filename(name: str) -> str:
    """Convert location string to safe filename."""
    if not name or not name.strip():
        return "unknown"
    # Replace problematic characters with underscore
    safe = re.sub(r'[<>:"/\\|?*\s]+', '_', name.strip())
    # Remove leading/trailing underscores and collapse multiples
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe.lower() if safe else "unknown"


def fetch_jobs_with_location(
    collection_name: str, regex_pattern: str, location_filter: str
) -> List[Dict]:
    """Fetch jobId and location from MongoDB matching the createdAt regex."""
    client = MongoClient(Config.MONGODB_URI)
    db = client["jobs"]
    collection = db[collection_name]

    query: Dict = {"createdAt": {"$regex": regex_pattern}}
    if location_filter:
        query["location"] = {
            "$regex": re.escape(location_filter),
            "$options": "i",  # case-insensitive
        }

    cursor = collection.find(
        query,
        {"jobId": 1, "location": 1, "createdAt": 1},
    ).sort("createdAt", -1)  # Descending: newest first

    jobs = []
    for doc in cursor:
        job_id = doc.get("jobId")
        if job_id is not None:
            jobs.append({
                "jobId": str(job_id),
                "location": doc.get("location", "") or ""
            })

    client.close()
    return jobs


def write_job_ids(output_path: Path, job_ids: List[str]) -> None:
    """Write jobIds to file, one per line."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(job_ids), encoding="utf-8")


def write_by_location(base_dir: Path, jobs: List[Dict]) -> Dict[str, int]:
    """Group jobs by location and write to separate files."""
    base_dir.mkdir(parents=True, exist_ok=True)

    # Group by location
    by_location: Dict[str, List[str]] = {}
    for job in jobs:
        loc_key = sanitize_filename(job["location"])
        if loc_key not in by_location:
            by_location[loc_key] = []
        by_location[loc_key].append(job["jobId"])

    # Write each location file
    counts = {}
    for loc, ids in sorted(by_location.items()):
        filepath = base_dir / f"{loc}.md"
        filepath.write_text("\n".join(ids), encoding="utf-8")
        counts[loc] = len(ids)

    return counts


def main():
    args = sys.argv[1:]
    if len(args) < 5:
        print(
            "Usage: <days> <collection> <output> <by_location> <location_filter>",
            file=sys.stderr,
        )
        sys.exit(1)

    days = int(args[0])
    collection = args[1]
    output = args[2]
    by_location = args[3].lower() == "true"
    location_filter = args[4]

    Config.validate()

    end = datetime.utcnow()
    start = end - timedelta(days=days - 1)
    regex_pattern = build_created_at_regex(start, end)

    print(f"Querying MongoDB for createdAt dates matching: {regex_pattern}")
    if location_filter:
        print(f"Filtering by location containing: {location_filter}")

    jobs = fetch_jobs_with_location(collection, regex_pattern, location_filter)
    print(f"Found {len(jobs)} jobs after filtering")

    if by_location:
        base_dir = Path("assets") / "by-location"
        counts = write_by_location(base_dir, jobs)
        print(f"\nWritten to {base_dir}/")
        for loc, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {loc}.md: {count} jobs")
    else:
        job_ids = [j["jobId"] for j in jobs]
        write_job_ids(Path(output), job_ids)
        print(f"Written to {output}")


if __name__ == "__main__":
    main()
PY
