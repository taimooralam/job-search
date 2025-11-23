#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

# shellcheck disable=SC1091
source ".venv/bin/activate"

if [ -f "requirements.txt" ]; then
  pip install -r "requirements.txt"
fi

INPUT_MD="${1:-}"
OUTPUT_DOCX="${2:-}"
TEMPLATE="$REPO_ROOT/assets/template-cv.docx"

if [ -z "$INPUT_MD" ]; then
  echo "Usage: $0 <path/to/cv.md> [output.docx]" >&2
  exit 1
fi

python - "$INPUT_MD" "$OUTPUT_DOCX" "$TEMPLATE" <<'PY'
import sys
from pathlib import Path

input_arg, output_arg, template_arg = sys.argv[1:4]

input_path = Path(input_arg).expanduser().resolve()
output_path = Path(output_arg).expanduser().resolve() if output_arg else input_path.with_suffix(".docx")
template_path = Path(template_arg).expanduser().resolve()

if not input_path.exists():
    sys.stderr.write(f"Input file not found: {input_path}\n")
    sys.exit(1)

if input_path.suffix.lower() != ".md":
    sys.stderr.write("Input must be a Markdown file (.md)\n")
    sys.exit(1)

try:
    import pypandoc
except ImportError:
    sys.stderr.write(
        "pypandoc is not installed. Activate the venv and run pip install -r requirements.txt.\n"
    )
    sys.exit(1)

extra_args = []
if template_path.exists():
    extra_args.append(f"--reference-doc={template_path}")
else:
    sys.stderr.write(f"Template not found at {template_path}; converting without template.\n")

try:
    pypandoc.convert_file(
        str(input_path),
        "docx",
        outputfile=str(output_path),
        extra_args=extra_args or None,
    )
except Exception as exc:  # noqa: BLE001
    sys.stderr.write(f"Conversion failed: {exc}\n")
    sys.exit(1)

print(f"Created: {output_path}")
PY
