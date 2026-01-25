# Plan: Claude Code Hooks System

**Created**: 2026-01-24
**Status**: Draft
**Priority**: P2 - Automation & Quality Gates

---

## Overview

Implement Claude Code hooks to automate validation, testing, and quality checks before/after tool executions.

```
┌─────────────────────────────────────────────────────────────────┐
│                    HOOK EXECUTION FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request                                                    │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────┐                                                │
│  │ PreToolUse  │──► Validate, Gate, Transform                   │
│  │   Hooks     │    Can BLOCK tool execution                    │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ Tool Runs   │    (Bash, Write, Edit, etc.)                   │
│  └──────┬──────┘                                                │
│         │                                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │ PostToolUse │──► Log, Validate Output, Trigger Actions       │
│  │   Hooks     │    Runs after tool completion                  │
│  └─────────────┘                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Hook Types & Triggers

| Hook Type | When It Runs | Can Block? | Use Cases |
|-----------|--------------|------------|-----------|
| `PreToolUse` | Before tool execution | Yes | Validation, gating, transformation |
| `PostToolUse` | After tool completion | No | Logging, notifications, follow-up actions |
| `Notification` | On specific events | No | Alerts, external integrations |

---

## Configuration File

**Location**: `.claude/hooks.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "name": "validate-cv-edits",
        "matcher": {
          "tool": "Edit",
          "path": "data/master-cv/**/*.md"
        },
        "command": ".claude/hooks/pre-cv-edit.sh",
        "description": "Validate master CV edits don't break format"
      },
      {
        "name": "block-secrets",
        "matcher": {
          "tool": "Write"
        },
        "command": ".claude/hooks/check-secrets.sh",
        "description": "Prevent writing files with secrets"
      }
    ],
    "PostToolUse": [
      {
        "name": "auto-test-on-edit",
        "matcher": {
          "tool": "Edit",
          "path": "src/**/*.py"
        },
        "command": ".claude/hooks/run-related-tests.sh",
        "description": "Run tests related to edited file"
      },
      {
        "name": "log-all-writes",
        "matcher": {
          "tool": "Write"
        },
        "command": ".claude/hooks/log-write.sh",
        "description": "Log all file writes for audit"
      },
      {
        "name": "validate-star-bullets",
        "matcher": {
          "tool": "Edit",
          "path": "data/master-cv/roles/*.md"
        },
        "command": ".claude/hooks/validate-star.py",
        "description": "Validate STAR format in role files"
      }
    ]
  }
}
```

---

## Hooks to Implement

### 1. Pre-Edit CV Validation Hook

**Purpose**: Prevent breaking master CV format when editing.

**File**: `.claude/hooks/pre-cv-edit.sh`

```bash
#!/bin/bash
# Pre-hook: Validate CV edit won't break format
# Input: JSON with tool details via stdin
# Exit 0 to allow, non-zero to block

set -e

# Read input from Claude Code
INPUT=$(cat)

# Extract the file path and new content
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
NEW_CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // empty')

# Skip if not a master-cv file
if [[ ! "$FILE_PATH" =~ data/master-cv ]]; then
    exit 0
fi

# Check for required sections in role files
if [[ "$FILE_PATH" =~ roles/.*\.md ]]; then
    # Ensure we're not removing required headers
    REQUIRED_HEADERS=("## Role" "## Company" "## Achievements")

    for header in "${REQUIRED_HEADERS[@]}"; do
        if [[ "$NEW_CONTENT" != *"$header"* ]]; then
            echo "BLOCKED: Edit would remove required section: $header"
            exit 1
        fi
    done
fi

# Check for accidental deletion of metrics (numbers)
if [[ -n "$NEW_CONTENT" ]]; then
    # If editing achievements, ensure metrics remain
    if echo "$NEW_CONTENT" | grep -q "Achievement"; then
        if ! echo "$NEW_CONTENT" | grep -qE '[0-9]+%|[$][0-9]+|\b[0-9]+[KMB]\b'; then
            echo "WARNING: Achievement bullet may be missing metrics"
            # Don't block, just warn
        fi
    fi
fi

exit 0
```

### 2. Secrets Detection Hook

**Purpose**: Prevent accidentally writing files containing secrets.

**File**: `.claude/hooks/check-secrets.sh`

```bash
#!/bin/bash
# Pre-hook: Block writes containing potential secrets
# Input: JSON with tool details via stdin

set -e

INPUT=$(cat)

# Extract content being written
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Skip certain file types
if [[ "$FILE_PATH" =~ \.(md|txt|json)$ ]] && [[ ! "$FILE_PATH" =~ \.env ]]; then
    # Check for common secret patterns
    SECRET_PATTERNS=(
        'sk-[a-zA-Z0-9]{20,}'           # OpenAI keys
        'ANTHROPIC_API_KEY.*='           # Anthropic keys
        'mongodb\+srv://[^@]+@'          # MongoDB connection strings
        'ghp_[a-zA-Z0-9]{36}'            # GitHub tokens
        'Bearer [a-zA-Z0-9\-._~+/]+=*'   # Bearer tokens
    )

    for pattern in "${SECRET_PATTERNS[@]}"; do
        if echo "$CONTENT" | grep -qE "$pattern"; then
            echo "BLOCKED: Detected potential secret in content (pattern: $pattern)"
            echo "File: $FILE_PATH"
            exit 1
        fi
    done
fi

exit 0
```

### 3. Auto-Test on Python Edit Hook

**Purpose**: Automatically run related tests after editing Python files.

**File**: `.claude/hooks/run-related-tests.sh`

```bash
#!/bin/bash
# Post-hook: Run tests related to edited file
# Input: JSON with tool result via stdin

set -e

INPUT=$(cat)

# Extract the file that was edited
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Skip if not a Python file in src/
if [[ ! "$FILE_PATH" =~ ^src/.*\.py$ ]]; then
    exit 0
fi

# Determine the test file
# src/layer6/cover_letter.py -> tests/unit/test_layer6_cover_letter.py
MODULE_PATH=$(echo "$FILE_PATH" | sed 's|^src/||' | sed 's|\.py$||' | tr '/' '_')
TEST_FILE="tests/unit/test_${MODULE_PATH}.py"

# Check if test file exists
if [[ -f "$TEST_FILE" ]]; then
    echo "Running related tests: $TEST_FILE"

    # Run tests (non-blocking, just report)
    if pytest "$TEST_FILE" -v --tb=short 2>&1 | tail -20; then
        echo "✅ Tests passed"
    else
        echo "⚠️ Some tests failed - review above"
    fi
else
    # Try to find any test that imports this module
    MODULE_NAME=$(basename "$FILE_PATH" .py)
    MATCHING_TESTS=$(grep -l "from.*${MODULE_NAME}.*import\|import.*${MODULE_NAME}" tests/unit/*.py 2>/dev/null || true)

    if [[ -n "$MATCHING_TESTS" ]]; then
        echo "Running tests that import $MODULE_NAME..."
        pytest $MATCHING_TESTS -v --tb=short 2>&1 | tail -20
    fi
fi

exit 0
```

### 4. STAR Format Validation Hook

**Purpose**: Validate STAR format in achievement bullets.

**File**: `.claude/hooks/validate-star.py`

```python
#!/usr/bin/env python3
"""Post-hook: Validate STAR format in role achievement bullets."""

import json
import sys
import re

def validate_star_bullet(bullet: str) -> tuple[bool, str]:
    """
    Validate a bullet follows STAR format.
    Returns (is_valid, reason).
    """

    # Check for metrics (numbers)
    if not re.search(r'\d+%|\$[\d,]+|\d+[KMB]|\d+x|\d+ (?:users|customers|teams)', bullet):
        return False, "Missing quantified metrics"

    # Check for strong action verb at start
    action_verbs = [
        'Led', 'Architected', 'Designed', 'Built', 'Developed', 'Implemented',
        'Reduced', 'Increased', 'Scaled', 'Optimized', 'Streamlined', 'Delivered',
        'Launched', 'Migrated', 'Automated', 'Transformed', 'Established',
        'Pioneered', 'Spearheaded', 'Orchestrated', 'Drove', 'Achieved'
    ]

    first_word = bullet.split()[0] if bullet else ""
    if first_word not in action_verbs:
        return False, f"Should start with action verb, got: {first_word}"

    # Check reasonable length (not too short, not too long)
    word_count = len(bullet.split())
    if word_count < 8:
        return False, f"Too short ({word_count} words), needs more context"
    if word_count > 35:
        return False, f"Too long ({word_count} words), should be concise"

    return True, "Valid"


def main():
    # Read hook input
    input_data = json.loads(sys.stdin.read())

    # Get the new content
    new_content = input_data.get('tool_input', {}).get('new_string', '')
    file_path = input_data.get('tool_input', {}).get('file_path', '')

    # Only validate role files
    if 'roles/' not in file_path:
        sys.exit(0)

    # Find achievement bullets (lines starting with -)
    bullets = re.findall(r'^- (.+)$', new_content, re.MULTILINE)

    issues = []
    for i, bullet in enumerate(bullets):
        is_valid, reason = validate_star_bullet(bullet)
        if not is_valid:
            issues.append(f"  Bullet {i+1}: {reason}")
            issues.append(f"    → {bullet[:80]}...")

    if issues:
        print("⚠️ STAR Format Issues Found:")
        print("\n".join(issues))
        print("\nTip: Run /star-bullet skill to improve these bullets")
    else:
        print(f"✅ All {len(bullets)} bullets pass STAR validation")

    # Don't block, just warn
    sys.exit(0)


if __name__ == "__main__":
    main()
```

### 5. Audit Log Hook

**Purpose**: Log all file modifications for review.

**File**: `.claude/hooks/log-write.sh`

```bash
#!/bin/bash
# Post-hook: Log all file writes
# Creates audit trail in .claude/audit.log

set -e

INPUT=$(cat)

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // "unknown"')
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')

# Create audit log entry
LOG_FILE=".claude/audit.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Append entry
echo "[$TIMESTAMP] $TOOL_NAME: $FILE_PATH" >> "$LOG_FILE"

# Rotate log if too large (>1MB)
if [[ -f "$LOG_FILE" ]] && [[ $(stat -f%z "$LOG_FILE" 2>/dev/null || stat -c%s "$LOG_FILE" 2>/dev/null) -gt 1048576 ]]; then
    mv "$LOG_FILE" "${LOG_FILE}.$(date +%Y%m%d)"
    gzip "${LOG_FILE}.$(date +%Y%m%d)"
fi

exit 0
```

### 6. Cost Tracking Hook

**Purpose**: Track estimated costs of Claude Code operations.

**File**: `.claude/hooks/track-costs.py`

```python
#!/usr/bin/env python3
"""Post-hook: Track estimated API costs."""

import json
import sys
import os
from datetime import datetime

COST_LOG = ".claude/costs.jsonl"

# Rough cost estimates per operation type
COST_ESTIMATES = {
    "WebSearch": 0.01,    # Per search
    "WebFetch": 0.005,    # Per fetch
    "Task": 0.05,         # Per agent spawn (varies by model)
    "Bash": 0.001,        # Minimal
    "Read": 0.0001,       # Minimal
    "Write": 0.0001,      # Minimal
    "Edit": 0.0001,       # Minimal
}

def main():
    input_data = json.loads(sys.stdin.read())

    tool_name = input_data.get('tool_name', 'unknown')
    cost = COST_ESTIMATES.get(tool_name, 0.001)

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "tool": tool_name,
        "estimated_cost_usd": cost,
        "file": input_data.get('tool_input', {}).get('file_path', None)
    }

    # Append to cost log
    os.makedirs(os.path.dirname(COST_LOG), exist_ok=True)
    with open(COST_LOG, 'a') as f:
        f.write(json.dumps(entry) + '\n')

    sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## Implementation Plan

### Phase 1: Create Hooks Directory (5 min)

```bash
mkdir -p .claude/hooks
```

### Phase 2: Create Hook Scripts (30 min)

```bash
# Create each hook script
touch .claude/hooks/{pre-cv-edit.sh,check-secrets.sh,run-related-tests.sh,log-write.sh}
touch .claude/hooks/{validate-star.py,track-costs.py}

# Make executable
chmod +x .claude/hooks/*.sh .claude/hooks/*.py
```

### Phase 3: Create hooks.json (10 min)

Create `.claude/hooks.json` with the configuration above.

### Phase 4: Test Hooks (30 min)

1. Test pre-CV-edit hook by editing a role file
2. Test secrets detection by trying to write a file with a fake key
3. Test auto-test hook by editing a Python file
4. Verify audit log is being written

---

## Hook Input/Output Format

### Input (via stdin)

```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/path/to/file.py",
    "old_string": "original text",
    "new_string": "replacement text"
  },
  "session_id": "abc123",
  "timestamp": "2026-01-24T10:00:00Z"
}
```

### Output (for PreToolUse blocking)

- Exit code 0: Allow tool execution
- Exit code non-zero: Block tool execution
- Stdout: Message shown to Claude (and user)

---

## Monitoring & Debugging

### View Audit Log

```bash
# Recent writes
tail -20 .claude/audit.log

# Filter by date
grep "2026-01-24" .claude/audit.log
```

### View Cost Estimates

```bash
# Sum estimated costs
cat .claude/costs.jsonl | jq -s 'map(.estimated_cost_usd) | add'

# Costs by tool
cat .claude/costs.jsonl | jq -s 'group_by(.tool) | map({tool: .[0].tool, total: map(.estimated_cost_usd) | add})'
```

### Debug Hook Execution

```bash
# Test a hook manually
echo '{"tool_name":"Edit","tool_input":{"file_path":"test.py"}}' | .claude/hooks/log-write.sh
```

---

## Security Considerations

1. **Hook scripts run with your user permissions** - be careful what they do
2. **Don't put secrets in hooks.json** - use environment variables
3. **Validate hook script sources** - only run trusted scripts
4. **Log hook failures** - for debugging and security auditing

---

## Validation Checklist

- [ ] Pre-hooks can block tool execution
- [ ] Post-hooks run after tool completion
- [ ] Audit log captures all writes
- [ ] Secrets detection works
- [ ] Auto-test doesn't block workflow
- [ ] Hooks don't significantly slow down operations

---

## Benefits

| Without Hooks | With Hooks |
|---------------|------------|
| Manual test running | Auto-test on edit |
| Possible secret leaks | Automatic detection |
| No audit trail | Full file change log |
| Manual validation | Automated quality gates |
| Hope-based quality | Enforced standards |
