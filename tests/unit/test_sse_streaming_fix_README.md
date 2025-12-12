# SSE Streaming Fix Test Suite

## Overview

This test suite (`test_sse_streaming_fix.py`) validates the SSE (Server-Sent Events) streaming improvements that prevent event loop starvation during pipeline execution.

## Problem Fixed

Previously, partial pipeline operations (structure-jd, research-company, generate-cv) showed empty screens during execution because progress updates were batched and delivered only at the end, rather than streaming in real-time.

## Changes Tested

### 1. Service Layer: Async `emit_progress` with Event Loop Yielding

**Location**: `src/services/{full_extraction_service.py, company_research_service.py, cv_generation_service.py}`

**Fix**:
```python
async def emit_progress(layer_key: str, status: str, message: str):
    if progress_callback:
        try:
            progress_callback(layer_key, status, message)
            await asyncio.sleep(0)  # CRITICAL: Yield to event loop for SSE delivery
        except Exception as e:
            logger.warning(f"Progress callback failed: {e}")
```

**Tests**:
- `test_full_extraction_emit_progress_is_async` - Verifies FullExtractionService calls progress callback
- `test_company_research_emit_progress_is_async` - Verifies CompanyResearchService calls progress callback
- `test_cv_generation_emit_progress_is_async` - Verifies CVGenerationService calls progress callback
- `test_emit_progress_yields_to_event_loop` - Verifies `asyncio.sleep(0)` is called to yield control
- `test_emit_progress_handles_callback_exceptions_gracefully` - Ensures execution continues even if callback fails

### 2. SSE Generator: Reduced Poll Interval

**Location**: `runner_service/routes/operation_streaming.py`

**Fix**: Changed poll interval from 500ms to 100ms:
```python
await asyncio.sleep(0.1)  # 100ms poll interval for responsive updates
```

**Tests**:
- `test_sse_generator_delivers_logs_quickly` - Verifies SSE generator promptly delivers log events

### 3. Flask Proxy: Real-Time Streaming with `iter_content()`

**Location**: `frontend/runner.py`

**Fix**: Changed from `iter_lines()` to `iter_content()` for real-time delivery:
```python
for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
    if chunk:
        buffer += chunk
        # Process complete SSE events (ending with double newline)
        while "\n\n" in buffer:
            event, buffer = buffer.split("\n\n", 1)
            yield event + "\n\n"
```

**Tests**:
- `test_stream_logs_uses_iter_content` - Verifies Flask proxy streams SSE chunks as they arrive
- `test_stream_logs_processes_sse_events_with_double_newline` - Verifies correct SSE event parsing
- `test_stream_logs_handles_connection_errors` - Ensures graceful error handling
- `test_stream_logs_sets_correct_sse_headers` - Validates SSE headers (text/event-stream, no-cache)

### 4. Integration Tests

**Tests**:
- `test_progress_updates_delivered_in_real_time` - Verifies updates arrive during execution, not batched at end
- `test_multiple_rapid_progress_updates_all_delivered` - Ensures no update loss during rapid consecutive updates

## Running the Tests

```bash
# Run just these tests (with parallel execution)
source .venv/bin/activate && pytest tests/unit/test_sse_streaming_fix.py -v -n auto

# Run with coverage
source .venv/bin/activate && pytest tests/unit/test_sse_streaming_fix.py -v -n auto --cov=src/services --cov=runner_service/routes --cov=frontend

# Run with verbose output
source .venv/bin/activate && pytest tests/unit/test_sse_streaming_fix.py -vv -n auto
```

## Test Coverage

| Component | Test Category | Coverage |
|-----------|---------------|----------|
| Service Layer `emit_progress` | Happy Path | ✅ |
| Service Layer `emit_progress` | Error Handling | ✅ |
| Service Layer `emit_progress` | Event Loop Yielding | ✅ |
| SSE Generator | Real-Time Delivery | ✅ |
| Flask Proxy | `iter_content()` Streaming | ✅ |
| Flask Proxy | SSE Event Parsing | ✅ |
| Flask Proxy | Error Handling | ✅ |
| Flask Proxy | Headers | ✅ |
| Integration | Real-Time Updates | ✅ |
| Integration | Rapid Updates | ✅ |

## Key Testing Patterns Used

### 1. Mocking External Dependencies
```python
with patch.object(service, '_get_job', return_value=mock_job_doc), \
     patch.object(service, '_run_jd_processor', return_value={...}):
    result = await service.execute(...)
```

### 2. Progress Callback Tracking
```python
mock_callback = Mock()
mock_callback.calls_list = []

def track_call(layer_key: str, status: str, message: str):
    mock_callback.calls_list.append((layer_key, status, message))

mock_callback.side_effect = track_call
```

### 3. Async Sleep Verification
```python
with patch('asyncio.sleep', side_effect=tracking_sleep):
    await service.execute(...)
    assert len([s for s in sleep_calls if s == 0]) >= 4
```

### 4. Flask Response Testing
```python
with app.test_request_context():
    response = stream_logs("test_run_123")
    chunks = list(response.response)
    combined = "".join(chunks)
    assert "event: end" in combined
```

## Guardrails

- All external APIs are mocked (no real API calls)
- Tests are fast (< 1 second each)
- Tests validate behavior, not implementation
- Clear docstrings explain what each test validates
- No hardcoded secrets

## Results

All 12 tests pass successfully:

```
======================= 12 passed, 15 warnings in 10.90s =======================
```

The warnings are from pytest-asyncio and are expected for async tests.

## Next Steps

If issues arise:
1. **Tests reveal bugs** → Use `architecture-debugger` agent
2. **Need more implementation** → Return to main Claude
3. **Docs need updating** → Use `doc-sync` agent
4. **Tests need UI validation** → Use `frontend-developer` agent
