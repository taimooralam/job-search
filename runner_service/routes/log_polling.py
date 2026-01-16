"""
Log Polling Endpoint for Pipeline Operations.

Provides HTTP polling endpoint for fetching logs from Redis.
Enables the "replay + live tail" pattern:
1. Client fetches all past logs (since=0)
2. Client polls at 200ms intervals for new logs
3. On completion, client stops polling

This replaces SSE streaming for better reliability during long operations.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

# Regex patterns for parsing Python logger output
# Matches: "2025-01-15 10:22:33 [INFO] module.name: message"
# Or: "[INFO] module.name: message"
# Or: "[UnifiedLLM:step_name] message"
PYTHON_LOG_PATTERN = re.compile(
    r'^(?:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+)?'  # Optional timestamp
    r'\[([A-Z]+)\]\s*'  # Log level [INFO], [ERROR], etc.
    r'(?:[\w.]+:\s*)?'  # Optional module name
    r'(.*)$'  # Message
)

# Matches: "[ClaudeCLI:job_id] message" or "[UnifiedLLM:step] message"
COMPONENT_LOG_PATTERN = re.compile(
    r'^\[(\w+):([^\]]+)\]\s*(.*)$'  # [Component:context] message
)

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _parse_log_entry(log: str, index: int) -> Dict[str, Any]:
    """
    Parse a log entry string into a structured log object.

    Handles two log formats:
    1. StructuredLogger (JSON): Parsed with full metadata extraction
    2. Python logger (plain text): Parsed with level/component extraction

    Args:
        log: Raw log string (may be JSON or plain text)
        index: Log index for ordering

    Returns:
        Dict with index, message, source, and optional metadata fields
    """
    log_obj: Dict[str, Any] = {"index": index}

    # Safety: handle None or empty logs
    if not log:
        log_obj["message"] = ""
        log_obj["source"] = "unknown"
        return log_obj

    # Handle case where log is already a dict (from in-memory state)
    # This happens when serving from memory rather than Redis
    if isinstance(log, dict):
        log_obj["source"] = "structured"
        log_obj["message"] = log.get("message", str(log))
        # Copy relevant fields from the dict
        for key in ("backend", "tier", "cost_usd", "event", "metadata", "traceback", "error"):
            if key in log:
                log_obj[key] = log[key]
        return log_obj

    log_stripped = log.strip()

    # Try to parse as JSON (structured log from StructuredLogger)
    if log_stripped.startswith("{"):
        try:
            parsed = json.loads(log_stripped)
            log_obj["source"] = "structured"

            # Extract metadata early for use in all event handlers
            metadata = parsed.get("metadata", {})

            # Build human-readable message from structured log
            # Priority: explicit message > layer event > event type
            if "message" in parsed:
                log_obj["message"] = parsed["message"]
            elif parsed.get("event") in ("layer_start", "layer_complete", "layer_error"):
                layer_name = parsed.get("layer_name", f"layer_{parsed.get('layer', '?')}")
                status = parsed.get("status", "")
                duration = parsed.get("duration_ms")
                duration_str = f" ({duration}ms)" if duration else ""
                log_obj["message"] = f"{layer_name}: {parsed['event']}{duration_str}"
            elif parsed.get("event") in ("llm_call_start", "llm_call_complete", "llm_call_error", "llm_call_fallback"):
                step = parsed.get("step_name", "llm_call")
                status = parsed.get("status", "")
                backend = parsed.get("backend", "")
                duration = parsed.get("duration_ms")
                duration_str = f" ({duration}ms)" if duration else ""
                backend_str = f" [{backend}]" if backend else ""
                log_obj["message"] = f"{step}: {status}{backend_str}{duration_str}"
            elif parsed.get("event") in ("pipeline_error", "error"):
                # Handle error events with traceback
                error_msg = parsed.get("error", "Unknown error")
                log_obj["message"] = f"❌ Error: {error_msg}"
                log_obj["level"] = "error"
                # Extract traceback from metadata for CLI panel display (support both names)
                metadata = parsed.get("metadata", {})
                if metadata.get("traceback"):
                    log_obj["traceback"] = metadata["traceback"]
                elif metadata.get("stack_trace"):
                    log_obj["traceback"] = metadata["stack_trace"]
                if parsed.get("metadata", {}).get("error_type"):
                    log_obj["error_type"] = parsed["metadata"]["error_type"]

            # CV Generation Phase Events
            elif parsed.get("event") == "phase_start":
                phase = parsed.get("phase", "?")
                phase_msg = metadata.get("message", f"Phase {phase}")
                log_obj["message"] = f"📋 {phase_msg}"
                log_obj["phase"] = phase

            elif parsed.get("event") == "phase_complete":
                phase = parsed.get("phase", "?")
                phase_msg = metadata.get("message", f"Phase {phase} complete")
                duration = parsed.get("duration_ms")
                duration_str = f" ({duration}ms)" if duration else ""
                log_obj["message"] = f"✅ {phase_msg}{duration_str}"
                log_obj["phase"] = phase

            # CV Generation Subphase Events (per-role processing)
            elif parsed.get("event") == "subphase_start":
                subphase = metadata.get("subphase", "subphase")
                role_title = metadata.get("role_title", "")
                role_info = f" - {role_title}" if role_title else ""
                log_obj["message"] = f"  🔹 Starting {subphase}{role_info}"
                log_obj["subphase"] = subphase

            elif parsed.get("event") == "subphase_complete":
                subphase = metadata.get("subphase", "subphase")
                role_title = metadata.get("role_title", "")
                bullets = metadata.get("bullets_generated", metadata.get("bullets_count"))
                duration = parsed.get("duration_ms")
                details = []
                if bullets:
                    details.append(f"{bullets} bullets")
                if duration:
                    details.append(f"{duration}ms")
                details_str = f" ({', '.join(details)})" if details else ""
                log_obj["message"] = f"  ✓ {subphase} complete{details_str}"
                log_obj["subphase"] = subphase

            # Decision Point Events (key choices with reasoning)
            elif parsed.get("event") == "decision_point":
                decision = metadata.get("decision", "decision")
                # Format based on decision type
                if decision == "bullet_generation":
                    bullets_count = metadata.get("output", {}).get("bullets_count", "?")
                    persona = metadata.get("output", {}).get("persona_used", "")
                    persona_str = f" [{persona}]" if persona else ""
                    log_obj["message"] = f"  📝 Generated {bullets_count} bullets{persona_str}"
                elif decision == "header_generation":
                    headline_preview = metadata.get("headline", {}).get("text_preview", "")[:40]
                    log_obj["message"] = f"  📝 Header: {headline_preview}..."
                elif decision == "cv_grade":
                    score = metadata.get("composite_score", "?")
                    passed = "✅" if metadata.get("passed") else "❌"
                    log_obj["message"] = f"  {passed} Grade: {score}/10"
                elif decision == "bullet_selection":
                    selected = metadata.get("selected_count", "?")
                    rejected = metadata.get("rejected_count", 0)
                    log_obj["message"] = f"  📝 Selected {selected} bullets (rejected {rejected})"
                else:
                    log_obj["message"] = f"  📝 Decision: {decision}"
                log_obj["decision"] = decision

            # Validation Result Events
            elif parsed.get("event") == "validation_result":
                validation = metadata.get("validation", "validation")
                passed = metadata.get("passed", False)
                icon = "✅" if passed else "⚠️"
                # Add relevant details based on validation type
                if validation == "ats_coverage":
                    coverage = metadata.get("coverage_pct", "?")
                    log_obj["message"] = f"  {icon} ATS Coverage: {coverage}%"
                elif validation == "keyword_placement":
                    top_third = metadata.get("top_third_pct", "?")
                    log_obj["message"] = f"  {icon} Keyword Placement: {top_third}% in top third"
                elif validation == "hallucination_qa":
                    score = metadata.get("grounding_score", "?")
                    log_obj["message"] = f"  {icon} Hallucination QA: {score}"
                else:
                    log_obj["message"] = f"  {icon} {validation}: {'passed' if passed else 'failed'}"
                log_obj["validation"] = validation
                log_obj["validation_passed"] = passed

            # Retry Events (grader retries, etc.)
            elif parsed.get("event") == "retry_attempt":
                attempt = metadata.get("attempt", "?")
                error_msg = metadata.get("error", "")[:50]
                log_obj["message"] = f"  ⚠️ Retry attempt {attempt}: {error_msg}"
                log_obj["level"] = "warning"

            # Grading-specific Events
            elif parsed.get("event") == "grading_error":
                error_type = metadata.get("error_type", "unknown")
                error_msg = metadata.get("error", "")[:80]
                log_obj["message"] = f"  ❌ Grading error ({error_type}): {error_msg}"
                log_obj["level"] = "error"

            elif parsed.get("event") == "grading_parsed":
                score = metadata.get("composite_score", "?")
                passed = metadata.get("passed", False)
                icon = "✅" if passed else "⚠️"
                log_obj["message"] = f"  {icon} Grading complete: {score}/10"

            # === CVImprover Events (Phase 0 Extension) ===

            # Improvement Start - shows all dimensions being analyzed
            elif parsed.get("event") == "cv_struct_improvement_start":
                num_dims = len(metadata.get("all_dimensions", {}))
                score = metadata.get("composite_score", "?")
                log_obj["message"] = f"🔧 Starting improvement - analyzing {num_dims} dimensions (score: {score}/10)"
                log_obj["all_dimensions"] = metadata.get("all_dimensions", {})
                log_obj["all_strategies"] = metadata.get("all_strategies_available", {})

            # Improvement Skipped - CV already passed
            elif parsed.get("event") == "cv_struct_improvement_skipped":
                score = metadata.get("composite_score", "?")
                log_obj["message"] = f"✅ CV passed ({score}/10) - no improvement needed"
                log_obj["level"] = "info"

            # Dimension Targeting Decision - shows which dimension was selected and why
            elif parsed.get("event") == "cv_struct_decision_point":
                decision = metadata.get("decision", "")
                if decision == "dimension_targeting":
                    target = metadata.get("target_dimension", "?")
                    target_score = metadata.get("target_score", "?")
                    ranking = metadata.get("dimension_ranking", [])
                    log_obj["message"] = f"🎯 Targeting: {target} ({target_score}/10) - lowest of {len(ranking)} dimensions"
                    log_obj["dimension_ranking"] = ranking
                    log_obj["strategy_to_apply"] = metadata.get("strategy_to_apply", {})
                else:
                    log_obj["message"] = f"📝 Decision: {decision}"

            # LLM Call Start - shows full prompt details
            elif parsed.get("event") == "cv_struct_llm_call_start":
                target = metadata.get("target_dimension", "improvement")
                focus = metadata.get("strategy_focus", "")
                tactics = metadata.get("tactics_applied", [])
                prompt_len = metadata.get("user_prompt_length", 0)
                log_obj["message"] = f"🔄 Calling LLM for {target} (focus: {focus}, {len(tactics)} tactics)"
                log_obj["system_prompt_preview"] = metadata.get("system_prompt_preview", "")
                log_obj["user_prompt_preview"] = metadata.get("user_prompt_preview", "")
                log_obj["prompt_length"] = prompt_len
                log_obj["tactics"] = tactics
                log_obj["issues_to_fix"] = metadata.get("issues_to_fix", [])

            # LLM Call Complete - shows full result details
            elif parsed.get("event") == "cv_struct_llm_call_complete":
                target = metadata.get("target_dimension", "improvement")
                changes_count = metadata.get("changes_made_count", 0)
                summary = metadata.get("improvement_summary", "")[:80]
                log_obj["message"] = f"✅ {target} complete: {changes_count} changes - {summary}"
                log_obj["changes_made"] = metadata.get("changes_made", [])
                log_obj["improved_cv_preview"] = metadata.get("improved_cv_preview", "")
                log_obj["cv_length_delta"] = metadata.get("cv_length_delta", 0)

            # LLM Call Error
            elif parsed.get("event") == "cv_struct_llm_call_error":
                error = metadata.get("error", "unknown")[:80]
                log_obj["message"] = f"❌ LLM error: {error}"
                log_obj["level"] = "error"

            # Improvement Complete - final result
            elif parsed.get("event") == "cv_struct_improvement_complete":
                target = metadata.get("target_dimension", "?")
                changes_count = metadata.get("changes_made_count", 0)
                summary = metadata.get("improvement_summary", "")[:60]
                retries = metadata.get("retries_used", 0)
                retry_str = f" ({retries} retries)" if retries > 0 else ""
                log_obj["message"] = f"✅ Improved {target}: {changes_count} changes{retry_str} - {summary}"
                log_obj["changes_made"] = metadata.get("changes_made", [])

            # Improvement Failed
            elif parsed.get("event") == "cv_struct_improvement_failed":
                target = metadata.get("target_dimension", "?")
                error = metadata.get("error", "")[:60]
                retries = metadata.get("retries_used", 0)
                log_obj["message"] = f"❌ Improvement failed for {target} ({retries} retries): {error}"
                log_obj["level"] = "error"

            # Retry Attempt (generic and improver-specific)
            elif parsed.get("event") == "cv_struct_retry_attempt":
                attempt = metadata.get("attempt_number", "?")
                exc = metadata.get("exception", "")[:50]
                log_obj["message"] = f"⚠️ Retry attempt {attempt}: {exc}"
                log_obj["level"] = "warning"

            # Catch-all for other cv_struct_ events not handled above
            elif parsed.get("event", "").startswith("cv_struct_"):
                event_name = parsed.get("event", "").replace("cv_struct_", "")
                msg = metadata.get("message", event_name)
                log_obj["message"] = f"📋 {msg}"

            # === Job Ingestion Events ===
            elif parsed.get("event") == "ingest_start":
                source = metadata.get("source", "unknown")
                log_obj["message"] = f"🚀 {parsed.get('message', f'Starting {source} ingestion')}"
            elif parsed.get("event") == "fetch_start":
                source = metadata.get("source", "unknown")
                log_obj["message"] = f"📥 {parsed.get('message', f'Fetching from {source}')}"
            elif parsed.get("event") == "fetch_complete":
                jobs_count = metadata.get("jobs_count", "?")
                source = metadata.get("source", "unknown")
                log_obj["message"] = f"✅ {parsed.get('message', f'Received {jobs_count} jobs from {source}')}"
            elif parsed.get("event") == "scoring_start":
                jobs_count = metadata.get("jobs_count", "?")
                log_obj["message"] = f"🔍 {parsed.get('message', f'Scoring {jobs_count} jobs')}"
            elif parsed.get("event") == "ingest_complete":
                ingested = metadata.get("ingested", 0)
                log_obj["message"] = f"✅ {parsed.get('message', f'Ingestion complete: {ingested} jobs')}"
                log_obj["status"] = parsed.get("status", "success")
            elif parsed.get("event") == "ingest_error":
                log_obj["message"] = f"❌ {parsed.get('message', 'Ingestion error')}"
                log_obj["level"] = "error"

            # === Job Search Events ===
            elif parsed.get("event") == "search_start":
                log_obj["message"] = f"🔎 {parsed.get('message', 'Starting job search')}"
            elif parsed.get("event") == "search_sources":
                sources = metadata.get("sources", [])
                log_obj["message"] = f"📡 {parsed.get('message', f'Searching {len(sources)} sources')}"
            elif parsed.get("event") == "source_complete":
                source = metadata.get("source", "?")
                jobs_count = metadata.get("jobs_count", 0)
                log_obj["message"] = f"  ✓ {parsed.get('message', f'{source}: {jobs_count} jobs')}"
            elif parsed.get("event") == "search_complete":
                total = metadata.get("total_results", 0)
                cache_hit = "📦 cache hit" if metadata.get("cache_hit") else ""
                log_obj["message"] = f"✅ {parsed.get('message', f'Search complete: {total} jobs')} {cache_hit}".strip()
            elif parsed.get("event") == "search_error":
                log_obj["message"] = f"❌ {parsed.get('message', 'Search error')}"
                log_obj["level"] = "error"

            # === Annotation Events ===
            elif parsed.get("event") == "annotation_start":
                log_obj["message"] = f"📝 {parsed.get('message', 'Starting annotation generation')}"
            elif parsed.get("event") == "annotation_processing":
                log_obj["message"] = f"  🔄 {parsed.get('message', 'Processing...')}"
            elif parsed.get("event") == "annotation_complete":
                created = metadata.get("created", 0)
                skipped = metadata.get("skipped", 0)
                log_obj["message"] = f"✅ {parsed.get('message', f'Generated {created} annotations ({skipped} skipped)')}"
            elif parsed.get("event") == "annotation_error":
                log_obj["message"] = f"❌ {parsed.get('message', 'Annotation error')}"
                log_obj["level"] = "error"

            else:
                # Fallback: use message field if present, otherwise event type or raw log
                if parsed.get("message"):
                    log_obj["message"] = parsed["message"]
                else:
                    log_obj["message"] = parsed.get("event", log)

            # Extract LLM attribution fields for frontend backend stats
            if parsed.get("backend"):
                log_obj["backend"] = parsed["backend"]
            if parsed.get("tier"):
                log_obj["tier"] = parsed["tier"]
            if parsed.get("cost_usd") is not None:
                log_obj["cost_usd"] = parsed["cost_usd"]

            # Include event type for frontend filtering/display
            if parsed.get("event"):
                log_obj["event"] = parsed["event"]

            # Include model info if available
            if parsed.get("model"):
                log_obj["model"] = parsed["model"]

            # Include verbose context fields if present (for debugging)
            # These can be at top level OR inside metadata - check both
            # (metadata already extracted at top of try block)

            # prompt_length: check top level first, then metadata
            if parsed.get("prompt_length"):
                log_obj["prompt_length"] = parsed["prompt_length"]
            elif metadata.get("prompt_length"):
                log_obj["prompt_length"] = metadata["prompt_length"]

            # prompt_preview (legacy single field): check top level first, then metadata
            if parsed.get("prompt_preview"):
                log_obj["prompt_preview"] = parsed["prompt_preview"]
            elif metadata.get("prompt_preview"):
                log_obj["prompt_preview"] = metadata["prompt_preview"]

            # Prompt previews are in metadata (Phase 0 logging) - newer split fields
            if parsed.get("system_prompt_preview"):
                log_obj["system_prompt_preview"] = parsed["system_prompt_preview"]
            elif metadata.get("system_prompt_preview"):
                log_obj["system_prompt_preview"] = metadata["system_prompt_preview"]

            if parsed.get("user_prompt_preview"):
                log_obj["user_prompt_preview"] = parsed["user_prompt_preview"]
            elif metadata.get("user_prompt_preview"):
                log_obj["user_prompt_preview"] = metadata["user_prompt_preview"]

            if parsed.get("result_preview"):
                log_obj["result_preview"] = parsed["result_preview"]
            elif metadata.get("result_preview"):
                log_obj["result_preview"] = metadata["result_preview"]

            if parsed.get("result_length"):
                log_obj["result_length"] = parsed["result_length"]
            elif metadata.get("result_length"):
                log_obj["result_length"] = metadata["result_length"]

            # Session ID for correlating start/complete pairs
            if metadata.get("session_id"):
                log_obj["session_id"] = metadata["session_id"]

            if parsed.get("max_turns"):
                log_obj["max_turns"] = parsed["max_turns"]

            # Pass through full metadata for frontend collapsible display
            if metadata:
                log_obj["metadata"] = metadata

            # Extract error fields (critical for CLI error visibility in browser)
            # These were previously dropped by whitelist-based extraction
            if parsed.get("error"):
                log_obj["error"] = parsed["error"]
            if parsed.get("cli_error"):
                log_obj["cli_error"] = parsed["cli_error"]
            if parsed.get("duration_ms"):
                log_obj["duration_ms"] = parsed["duration_ms"]

            # Extract raw CLI output for debugging (shows what Claude actually returned)
            if parsed.get("raw_output"):
                log_obj["raw_output"] = parsed["raw_output"]
            if parsed.get("stderr"):
                log_obj["stderr"] = parsed["stderr"]

        except json.JSONDecodeError:
            # Not valid JSON despite starting with {, treat as plain text
            log_obj["source"] = "python"
            log_obj["message"] = log_stripped

    else:
        # Check for "emoji layer_key: {json}" pattern (e.g., "❌ cv_struct_error: {...}")
        # This format is used by create_layer_callback for structured error logs with traceback
        colon_brace_idx = log_stripped.find(": {")
        if colon_brace_idx != -1:
            json_portion = log_stripped[colon_brace_idx + 2:]  # Skip ": "
            if json_portion.endswith("}"):
                try:
                    parsed_json = json.loads(json_portion)
                    # Successfully parsed embedded JSON - treat as structured log
                    log_obj["source"] = "structured_embedded"

                    # Extract prefix (e.g., "❌ cv_struct_error")
                    prefix = log_stripped[:colon_brace_idx].strip()
                    log_obj["prefix"] = prefix

                    # Use message from JSON or the prefix
                    log_obj["message"] = parsed_json.get("message", prefix)

                    # Extract event for frontend display
                    if parsed_json.get("event"):
                        log_obj["event"] = parsed_json["event"]

                    # Critical: Extract metadata including traceback for CLI panel display
                    if parsed_json.get("metadata"):
                        log_obj["metadata"] = parsed_json["metadata"]
                        # Also extract traceback at top level for easy access (support both names)
                        if parsed_json["metadata"].get("traceback"):
                            log_obj["traceback"] = parsed_json["metadata"]["traceback"]
                        elif parsed_json["metadata"].get("stack_trace"):
                            log_obj["traceback"] = parsed_json["metadata"]["stack_trace"]
                        if parsed_json["metadata"].get("error_type"):
                            log_obj["error_type"] = parsed_json["metadata"]["error_type"]

                    # Extract other useful fields
                    if parsed_json.get("layer"):
                        log_obj["layer"] = parsed_json["layer"]
                    if parsed_json.get("layer_name"):
                        log_obj["layer_name"] = parsed_json["layer_name"]
                    if parsed_json.get("job_id"):
                        log_obj["job_id"] = parsed_json["job_id"]

                    return log_obj
                except json.JSONDecodeError:
                    pass  # Not valid JSON, fall through to plain text parsing

        # Plain text log - try to parse Python logger format
        log_obj["source"] = "python"

        # Try to extract log level from Python logger format
        # e.g., "2025-01-15 10:22:33 [INFO] module: message" or "[ERROR] message"
        python_match = PYTHON_LOG_PATTERN.match(log_stripped)
        if python_match:
            level = python_match.group(1)
            message = python_match.group(2).strip()
            log_obj["level"] = level.lower()
            log_obj["message"] = message
        else:
            # Try component format: [ClaudeCLI:job_id] message
            component_match = COMPONENT_LOG_PATTERN.match(log_stripped)
            if component_match:
                component = component_match.group(1)
                context = component_match.group(2)
                message = component_match.group(3).strip()
                log_obj["component"] = component
                log_obj["context"] = context
                log_obj["message"] = message
            else:
                # Plain unformatted text - use as-is
                log_obj["message"] = log_stripped

    return log_obj

# Redis key prefixes (must match operation_streaming.py)
REDIS_LOG_PREFIX = "logs:"


def _get_redis_client():
    """
    Get Redis client from queue manager (reuse existing connection).

    Returns:
        Redis client or None if unavailable
    """
    try:
        from runner_service.app import _queue_manager
        if _queue_manager and _queue_manager.is_connected:
            return _queue_manager._redis
        return None
    except ImportError:
        return None


@router.get("/{run_id}")
async def poll_logs(
    run_id: str,
    since: int = Query(0, ge=0, description="Index to start from (0 = all logs)"),
    limit: int = Query(100, ge=1, le=500, description="Max logs to return"),
) -> Dict[str, Any]:
    """
    Poll logs for a pipeline operation.

    Multi-Runner Support:
    - If this runner owns the run, serve from in-memory (fastest)
    - If another runner owns it, serve from Redis (slightly delayed)
    - Response includes X-Log-Owner header for debugging

    Enables the "replay + live tail" pattern:
    - First request: since=0 to get all past logs
    - Subsequent requests: since=next_index to get only new logs
    - Poll every 200ms during active viewing for near-instant updates

    Args:
        run_id: Operation run ID (e.g., "op_generate-cv_abc123")
        since: Index to start from (0 = beginning)
        limit: Maximum logs to return per request

    Returns:
        - logs[]: Array of log entries with index and message
        - next_index: Starting index for next poll
        - total_count: Total logs available
        - status: Operation status (running/completed/failed)
        - layer_status: Layer-level progress (if available)
        - log_source: "memory" or "redis" (for debugging)

    Example response:
        {
            "logs": [
                {"index": 0, "message": "Starting pipeline..."},
                {"index": 1, "message": "Fetching job data..."}
            ],
            "next_index": 2,
            "total_count": 2,
            "status": "running",
            "layer_status": {"fetch_job": {"status": "success"}},
            "log_source": "memory"
        }
    """
    # MULTI-RUNNER: Check if we own this run (fastest path)
    try:
        from runner_service.routes.operation_streaming import (
            is_log_owner,
            get_operation_state,
            get_runner_id,
        )

        # If we own this run, serve from in-memory (instant, no Redis latency)
        if is_log_owner(run_id):
            state = get_operation_state(run_id)
            if state:
                logs_slice = state.logs[since:since + limit]
                total = len(state.logs)
                expected = total if state.status in {"completed", "failed"} else None
                logger.debug(f"[LOG_POLL] Serving {run_id} from memory (we own it)")
                return {
                    "logs": [
                        _parse_log_entry(msg, since + i)
                        for i, msg in enumerate(logs_slice)
                    ],
                    "next_index": since + len(logs_slice),
                    "total_count": total,
                    "expected_log_count": expected,
                    "status": state.status,
                    "layer_status": state.layer_status or {},
                    "error": state.error,
                    "langsmith_url": state.langsmith_url,
                    "log_source": "memory",
                    "runner_id": get_runner_id(),
                }
    except ImportError:
        pass

    # Not owned by us - serve from Redis
    logger.debug(f"[LOG_POLL] Serving {run_id} from Redis (not our run)")

    redis = _get_redis_client()
    if not redis:
        logger.warning(f"[LOG_POLL] Redis not available for run_id={run_id}")
        raise HTTPException(
            status_code=503,
            detail="Log service unavailable (Redis not connected)"
        )

    # Build Redis keys
    logs_key = f"{REDIS_LOG_PREFIX}{run_id}:buffer"
    meta_key = f"{REDIS_LOG_PREFIX}{run_id}:meta"
    layers_key = f"{REDIS_LOG_PREFIX}{run_id}:layers"

    # Check if run exists in Redis
    try:
        exists = await redis.exists(logs_key) or await redis.exists(meta_key)
    except Exception as e:
        logger.error(f"[LOG_POLL] Redis exists check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Redis error: {e}")

    if not exists:
        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found"
        )

    # Fetch logs from Redis (LRANGE with 0-indexed bounds)
    end_index = since + limit - 1
    logs_raw = await redis.lrange(logs_key, since, end_index)

    # Parse logs (they may be bytes or strings depending on Redis encoding)
    logs: List[Dict[str, Any]] = []
    for i, log in enumerate(logs_raw):
        if isinstance(log, bytes):
            log = log.decode("utf-8")

        log_obj = _parse_log_entry(log, since + i)
        logs.append(log_obj)

    # Get total count from Redis
    total_count = await redis.llen(logs_key)

    # Get metadata
    meta = await redis.hgetall(meta_key)
    status = meta.get("status", "unknown") if meta else "unknown"
    error = meta.get("error") or None if meta else None
    langsmith_url = meta.get("langsmith_url") or None if meta else None

    # Get expected_log_count from metadata (fixes race condition)
    # When status is completed/failed, this tells the frontend how many logs
    # to expect, even if they haven't all been persisted to Redis yet.
    expected_log_count = None
    if meta:
        expected_str = meta.get("expected_log_count")
        if expected_str:
            try:
                expected_log_count = int(expected_str)
            except (ValueError, TypeError):
                pass

    # Get layer status
    layers_json = await redis.get(layers_key)
    layer_status = {}
    if layers_json:
        try:
            layer_status = json.loads(layers_json)
        except json.JSONDecodeError:
            pass

    return {
        "logs": logs,
        "next_index": since + len(logs),
        "total_count": total_count,
        "expected_log_count": expected_log_count,  # May be None if not yet completed
        "status": status,
        "layer_status": layer_status,
        "error": error,
        "langsmith_url": langsmith_url,
        "log_source": "redis",  # Multi-runner: served from Redis (not our run)
    }


@router.get("/{run_id}/status")
async def get_log_status(run_id: str) -> Dict[str, Any]:
    """
    Get just the status of an operation (lightweight endpoint).

    Useful for quick status checks without fetching logs.

    Args:
        run_id: Operation run ID

    Returns:
        - status: Operation status
        - layer_status: Layer-level progress
        - error: Error message if failed
    """
    redis = _get_redis_client()

    if not redis:
        raise HTTPException(
            status_code=503,
            detail="Log service unavailable (Redis not connected)"
        )

    meta_key = f"{REDIS_LOG_PREFIX}{run_id}:meta"
    layers_key = f"{REDIS_LOG_PREFIX}{run_id}:layers"

    # Check if run exists
    meta = await redis.hgetall(meta_key)

    if not meta:
        # Check in-memory state as fallback
        try:
            from runner_service.routes.operation_streaming import get_operation_state
            state = get_operation_state(run_id)
            if state:
                return {
                    "status": state.status,
                    "layer_status": state.layer_status or {},
                    "error": state.error,
                    "langsmith_url": state.langsmith_url,
                }
        except ImportError:
            pass

        raise HTTPException(
            status_code=404,
            detail=f"Run {run_id} not found"
        )

    # Get layer status
    layers_json = await redis.get(layers_key)
    layer_status = {}
    if layers_json:
        try:
            layer_status = json.loads(layers_json)
        except json.JSONDecodeError:
            pass

    return {
        "status": meta.get("status", "unknown"),
        "layer_status": layer_status,
        "error": meta.get("error") or None,
        "langsmith_url": meta.get("langsmith_url") or None,
    }
