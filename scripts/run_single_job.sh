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
# After the run, a helper script is generated to turn the latest cv.md into a .docx
# using the repo's .venv and scripts/convert_cv_to_docx.sh.

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <JOB_ID> [PROFILE_PATH]" >&2
  exit 1
fi

JOB_ID="$1"
PROFILE_PATH="${2:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Track start time to find newly generated CV.md/cv.md
RUN_MARKER="$(mktemp)"
touch "$RUN_MARKER"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

if [ -n "$PROFILE_PATH" ]; then
  python scripts/run_pipeline.py --job-id "$JOB_ID" --profile "$PROFILE_PATH"
else
  python scripts/run_pipeline.py --job-id "$JOB_ID"
fi

# Find the most recent application folder (company/role) by directory mtime.
LATEST_APP_DIR="$(python - <<'PY'
import os
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "applications"
if not root.exists():
    raise SystemExit("")

candidates = []
for company_dir in root.iterdir():
    if not company_dir.is_dir():
        continue
    for role_dir in company_dir.iterdir():
        if not role_dir.is_dir():
            continue
        try:
            mtime = role_dir.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, role_dir))

if not candidates:
    raise SystemExit("")

candidates.sort(key=lambda x: x[0], reverse=True)
print(candidates[0][1])
PY
)"

if [ -n "$LATEST_APP_DIR" ]; then
  CV_DIR="$LATEST_APP_DIR"
  HELPER_SCRIPT="${CV_DIR}/convert_cv_to_docx.sh"
  DEFAULT_CV_MD="${CV_DIR}/cv.md"  # Expect cv.md in the application folder

  cat > "$HELPER_SCRIPT" <<EOF
#!/usr/bin/env bash
# Convert the generated cv.md to .docx using the repo's .venv and template
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONVERTER="$REPO_ROOT/scripts/convert_cv_to_docx.sh"
DEFAULT_CV_MD="$DEFAULT_CV_MD"

CV_MD_PATH="\${1:-\$DEFAULT_CV_MD}"
OUTPUT_PATH="\${2:-}"

if [ ! -f "\$CV_MD_PATH" ]; then
  ALT_PATH="\$(dirname "\$CV_MD_PATH")/CV.md"
  if [ -f "\$ALT_PATH" ]; then
    CV_MD_PATH="\$ALT_PATH"
  fi
fi

if [ ! -f "\$CV_MD_PATH" ]; then
  echo "cv.md not found in \$(dirname "\$CV_MD_PATH"). Expected cv.md or CV.md." >&2
  exit 1
fi

"\$CONVERTER" "\$CV_MD_PATH" "\$OUTPUT_PATH"
EOF

  chmod +x "$HELPER_SCRIPT"
  echo ""
  echo "💡 Run this to generate a .docx from the latest CV markdown:"
  echo "  $HELPER_SCRIPT \"$DEFAULT_CV_MD\""
else
  echo ""
  echo "⚠️ No new CV markdown found after this run."
  echo "   Expected path: applications/<company>/<role>/CV.md (case-insensitive)"
  echo "   If the pipeline generated only a .docx (CV_<Company>.docx), conversion is not needed."
fi

rm -f "$RUN_MARKER"
