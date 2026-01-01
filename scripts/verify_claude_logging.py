#!/usr/bin/env python
"""
Verify Claude Code CLI logging is working correctly.

Run a test pipeline and check Redis for expected log entries.
This script validates that ClaudeCLI properly emits structured logs
for Redis live-tail visibility.

Usage:
    # Check logs from a specific run
    python scripts/verify_claude_logging.py --run-id <run_id>

    # Check recent logs (last 10 minutes)
    python scripts/verify_claude_logging.py --recent

    # Run with verbose output
    python scripts/verify_claude_logging.py --run-id <run_id> --verbose
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_redis_client():
    """Get Redis client from environment."""
    import redis

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    return redis.from_url(redis_url)


def get_logs_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Fetch all logs for a specific run from Redis."""
    r = get_redis_client()
    key = f"logs:{run_id}:buffer"
    raw_logs = r.lrange(key, 0, -1)

    logs = []
    for raw in raw_logs:
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            logs.append(json.loads(raw))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

    return logs


def filter_claude_cli_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter logs to only include Claude CLI entries."""
    return [
        log for log in logs
        if log.get("backend") == "claude_cli"
    ]


def verify_claude_logs(logs: List[Dict[str, Any]], verbose: bool = False) -> Dict[str, Any]:
    """
    Verify that Claude Code logs have required fields.

    Required fields per Phase 0 plan:
    - session_id: Unique ID for this invocation
    - system_prompt_preview: First 10 + "..." + last 10 chars (on start)
    - user_prompt_preview: First 10 + "..." + last 10 chars (on start)
    - result_preview: First 10 + "..." + last 10 chars (on complete)
    - prompt_length: Total prompt character count (on start)
    - result_length: Total result character count (on complete)

    Returns:
        Dict with verification results
    """
    claude_logs = filter_claude_cli_logs(logs)

    if not claude_logs:
        return {
            "status": "no_logs",
            "message": "No Claude CLI logs found in the provided logs",
            "total_logs": len(logs),
            "claude_cli_logs": 0,
        }

    # Separate by status
    start_logs = [l for l in claude_logs if l.get("status") == "start"]
    complete_logs = [l for l in claude_logs if l.get("status") == "complete"]
    error_logs = [l for l in claude_logs if l.get("status") == "error"]

    # Track issues
    issues = []
    valid_starts = 0
    valid_completes = 0

    # Verify start logs have required fields
    for log in start_logs:
        metadata = log.get("metadata", {})
        missing = []

        if not metadata.get("session_id"):
            missing.append("session_id")
        if "system_prompt_preview" not in metadata:
            missing.append("system_prompt_preview")
        if "user_prompt_preview" not in metadata:
            missing.append("user_prompt_preview")
        if "prompt_length" not in metadata:
            missing.append("prompt_length")

        if missing:
            issues.append({
                "type": "start_missing_fields",
                "step_name": log.get("step_name"),
                "missing": missing,
            })
        else:
            valid_starts += 1

    # Verify complete logs have required fields
    for log in complete_logs:
        metadata = log.get("metadata", {})
        missing = []

        if not metadata.get("session_id"):
            missing.append("session_id")
        if "result_preview" not in metadata:
            missing.append("result_preview")
        if "result_length" not in metadata:
            missing.append("result_length")
        if log.get("duration_ms") is None:
            missing.append("duration_ms")

        if missing:
            issues.append({
                "type": "complete_missing_fields",
                "step_name": log.get("step_name"),
                "missing": missing,
            })
        else:
            valid_completes += 1

    # Verify session_id consistency (start and complete should match)
    start_sessions = {
        log.get("metadata", {}).get("session_id"): log
        for log in start_logs
    }
    complete_sessions = {
        log.get("metadata", {}).get("session_id"): log
        for log in complete_logs
    }

    orphan_starts = set(start_sessions.keys()) - set(complete_sessions.keys()) - {None}
    orphan_completes = set(complete_sessions.keys()) - set(start_sessions.keys()) - {None}

    if orphan_starts:
        issues.append({
            "type": "orphan_starts",
            "message": f"{len(orphan_starts)} start logs without matching complete",
            "session_ids": list(orphan_starts)[:5],  # Show first 5
        })

    # Calculate call pairs
    total_call_pairs = len(set(start_sessions.keys()) & set(complete_sessions.keys()) - {None})

    results = {
        "status": "pass" if not issues else "issues_found",
        "total_logs": len(logs),
        "claude_cli_logs": len(claude_logs),
        "breakdown": {
            "start_events": len(start_logs),
            "complete_events": len(complete_logs),
            "error_events": len(error_logs),
        },
        "validation": {
            "valid_start_events": valid_starts,
            "valid_complete_events": valid_completes,
            "complete_call_pairs": total_call_pairs,
        },
        "issues": issues,
    }

    if verbose and claude_logs:
        # Add sample logs
        results["sample_logs"] = claude_logs[:6]

    return results


def print_results(results: Dict[str, Any]) -> None:
    """Print verification results in a readable format."""
    status_emoji = "✅" if results["status"] == "pass" else "⚠️" if results["status"] == "issues_found" else "❌"

    print(f"\n{status_emoji} Claude Code Logging Verification")
    print("=" * 50)

    print(f"\nTotal logs examined: {results['total_logs']}")
    print(f"Claude CLI logs found: {results['claude_cli_logs']}")

    if "breakdown" in results:
        print("\nLog Breakdown:")
        for key, val in results["breakdown"].items():
            print(f"  • {key}: {val}")

    if "validation" in results:
        print("\nValidation:")
        for key, val in results["validation"].items():
            print(f"  • {key}: {val}")

    if results.get("issues"):
        print(f"\n⚠️  Issues Found ({len(results['issues'])}):")
        for issue in results["issues"][:10]:  # Show first 10
            print(f"  - {issue.get('type')}: {issue.get('missing', issue.get('message', 'unknown'))}")

    if results.get("sample_logs"):
        print("\nSample Logs:")
        for i, log in enumerate(results["sample_logs"]):
            print(f"\n  [{i+1}] {log.get('status', 'unknown')} - {log.get('step_name', 'unknown')}")
            if log.get("metadata"):
                meta = log["metadata"]
                if meta.get("session_id"):
                    print(f"      session_id: {meta['session_id']}")
                if meta.get("system_prompt_preview"):
                    print(f"      system_prompt_preview: {meta['system_prompt_preview']}")
                if meta.get("user_prompt_preview"):
                    print(f"      user_prompt_preview: {meta['user_prompt_preview']}")
                if meta.get("result_preview"):
                    print(f"      result_preview: {meta['result_preview']}")

    print("\n" + "=" * 50)

    if results["status"] == "pass":
        print("✅ All Claude Code logging validations passed!")
    elif results["status"] == "issues_found":
        print("⚠️  Some issues found - see above for details")
    else:
        print("❌ No Claude CLI logs found - run a pipeline first")


def main():
    parser = argparse.ArgumentParser(
        description="Verify Claude Code CLI logging integration"
    )
    parser.add_argument(
        "--run-id",
        help="Run ID to check logs for",
    )
    parser.add_argument(
        "--recent",
        action="store_true",
        help="Check logs from recent runs (last 10 minutes)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show sample log entries",
    )

    args = parser.parse_args()

    if not args.run_id and not args.recent:
        parser.print_help()
        print("\nError: Either --run-id or --recent is required")
        sys.exit(1)

    try:
        if args.run_id:
            print(f"Fetching logs for run: {args.run_id}")
            logs = get_logs_for_run(args.run_id)
        else:
            # For --recent, we'd need to scan Redis keys
            # This is a simplified implementation
            print("--recent not yet implemented. Please provide --run-id")
            sys.exit(1)

        results = verify_claude_logs(logs, verbose=args.verbose)
        print_results(results)

        # Exit with appropriate code
        if results["status"] == "pass":
            sys.exit(0)
        elif results["status"] == "issues_found":
            sys.exit(1)
        else:
            sys.exit(2)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
