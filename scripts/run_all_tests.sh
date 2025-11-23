#!/usr/bin/env bash
set -euo pipefail

# Activate local virtual environment
if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

source .venv/bin/activate

# Install dependencies if needed
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
fi

# Run unit test suite only (exclude slower integration/E2E)
python -m pytest tests/unit "$@"
