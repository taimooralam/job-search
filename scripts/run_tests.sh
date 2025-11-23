#!/usr/bin/env bash

# Run the test suite with virtual environment activated.
# Usage:
#   scripts/run_tests.sh                    # Run all tests
#   scripts/run_tests.sh unit               # Run unit tests only
#   scripts/run_tests.sh integration        # Run integration tests only
#   scripts/run_tests.sh tests/unit/test_layer6_cover_letter_generator.py  # Specific file
#
# Pass additional pytest args after the first argument:
#   scripts/run_tests.sh unit -v --tb=short

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  echo "Warning: .venv/bin/activate not found, using system Python" >&2
fi

# Determine test path
TEST_PATH="${1:-tests/}"
shift 2>/dev/null || true

case "$TEST_PATH" in
  unit)
    TEST_PATH="tests/unit/"
    ;;
  integration)
    TEST_PATH="tests/integration/"
    ;;
esac

# Run pytest with remaining args
python -m pytest "$TEST_PATH" "$@"
