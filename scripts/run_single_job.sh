#!/usr/bin/env bash

# Thin wrapper to run the full job intelligence pipeline for a single job ID.
# Usage:
#   scripts/run_single_job.sh <JOB_ID> [PROFILE_PATH]
#
# Examples:
#   scripts/run_single_job.sh 4335713702
#   scripts/run_single_job.sh 4335713702 ./my-profile.md
#
# This script just forwards to:
#   python scripts/run_pipeline.py --job-id <JOB_ID> --profile <PROFILE_PATH>

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <JOB_ID> [PROFILE_PATH]" >&2
  exit 1
fi

JOB_ID="$1"
PROFILE_PATH="${2:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

if [ -n "$PROFILE_PATH" ]; then
  python scripts/run_pipeline.py --job-id "$JOB_ID" --profile "$PROFILE_PATH"
else
  python scripts/run_pipeline.py --job-id "$JOB_ID"
fi

