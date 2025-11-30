# Structured Logging Implementation Plan

**Created**: 2025-11-29
**Status**: Planning
**Priority**: Medium
**Related Requirement**: #6 from missing.md

---

## Problem Statement

Currently, all pipeline layers use `print()` statements for logging, which:
1. Cannot be parsed by log aggregation tools
2. Don't include structured metadata (layer, status, duration)
3. Cannot drive frontend status button updates in real-time
4. Make debugging production issues difficult

---

## Goals

1. Replace `print()` with structured JSON logging
2. Enable frontend pipeline status button updates via log events
3. Improve observability for production debugging
4. Support log aggregation (future: LangSmith, CloudWatch, etc.)

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      PIPELINE EXECUTION                         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2 ──→ Logger.emit("layer_start", layer=2)                │
│           ──→ [Processing]                                       │
│           ──→ Logger.emit("layer_complete", layer=2, status=ok) │
│                                                                  │
│  Layer 3 ──→ Logger.emit("layer_start", layer=3)                │
│           ──→ [Error!]                                           │
│           ──→ Logger.emit("layer_error", layer=3, error=...)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    [Structured JSON Logs]
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      RUNNER SERVICE                              │
│  - Captures log stream                                           │
│  - Sends to frontend via SSE                                     │
│  - Optionally forwards to LangSmith                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND                                    │
│  - Receives log events via SSE                                   │
│  - Updates pipeline status buttons in real-time                  │
│  - Shows layer progress (pending → running → complete/error)     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Log Event Format

### Standard Event Schema

```json
{
  "timestamp": "2025-11-29T10:30:45.123Z",
  "event": "layer_complete",
  "layer": 4,
  "layer_name": "opportunity_mapper",
  "job_id": "6929c97b45fa3c355f84ba2d",
  "status": "success",
  "duration_ms": 4500,
  "metadata": {
    "fit_score": 85,
    "tokens_used": 1200
  }
}
```

### Event Types

| Event | Description | Status Values |
|-------|-------------|---------------|
| `layer_start` | Layer execution beginning | N/A |
| `layer_complete` | Layer finished successfully | `success` |
| `layer_error` | Layer failed with error | `error` |
| `layer_skip` | Layer skipped (optional layer) | `skipped` |
| `pipeline_start` | Pipeline execution beginning | N/A |
| `pipeline_complete` | Pipeline finished | `success`, `partial`, `error` |

---

## Implementation

### Phase 1: Create Logger Module (2 hours)

**File**: `src/common/structured_logger.py`

```python
import json
import sys
from datetime import datetime
from typing import Any, Optional

class StructuredLogger:
    """Structured JSON logger for pipeline events."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.start_time = datetime.utcnow()

    def emit(
        self,
        event: str,
        layer: Optional[int] = None,
        layer_name: Optional[str] = None,
        status: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[dict] = None,
        error: Optional[str] = None
    ):
        """Emit a structured log event."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event": event,
            "job_id": self.job_id,
        }

        if layer is not None:
            log_entry["layer"] = layer
        if layer_name:
            log_entry["layer_name"] = layer_name
        if status:
            log_entry["status"] = status
        if duration_ms is not None:
            log_entry["duration_ms"] = duration_ms
        if metadata:
            log_entry["metadata"] = metadata
        if error:
            log_entry["error"] = error

        # Output as JSON line (for parsing)
        print(json.dumps(log_entry), file=sys.stdout, flush=True)

    def layer_start(self, layer: int, layer_name: str):
        """Log layer execution start."""
        self.emit("layer_start", layer=layer, layer_name=layer_name)

    def layer_complete(self, layer: int, layer_name: str, duration_ms: int, metadata: dict = None):
        """Log layer execution complete."""
        self.emit("layer_complete", layer=layer, layer_name=layer_name,
                  status="success", duration_ms=duration_ms, metadata=metadata)

    def layer_error(self, layer: int, layer_name: str, error: str, duration_ms: int = None):
        """Log layer execution error."""
        self.emit("layer_error", layer=layer, layer_name=layer_name,
                  status="error", error=error, duration_ms=duration_ms)
```

### Phase 2: Integrate Into Pipeline Layers (3 hours)

**Example**: `src/layer4/opportunity_mapper.py`

```python
from src.common.structured_logger import StructuredLogger

class OpportunityMapper:
    def __init__(self, logger: Optional[StructuredLogger] = None):
        self.logger = logger

    def map_opportunity(self, state: JobState) -> JobState:
        start_time = time.time()

        if self.logger:
            self.logger.layer_start(4, "opportunity_mapper")

        try:
            # ... existing logic ...

            duration_ms = int((time.time() - start_time) * 1000)
            if self.logger:
                self.logger.layer_complete(4, "opportunity_mapper", duration_ms,
                    metadata={"fit_score": state.get("fit_score")})

            return state

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            if self.logger:
                self.logger.layer_error(4, "opportunity_mapper", str(e), duration_ms)
            raise
```

### Phase 3: Runner Service Integration (2 hours)

**File**: `runner_service/app.py`

```python
import json

async def stream_pipeline_output(process, job_id: str):
    """Stream pipeline output and parse structured logs."""
    async for line in process.stdout:
        line_str = line.decode().strip()

        # Try to parse as structured log
        try:
            log_event = json.loads(line_str)
            if "event" in log_event:
                # It's a structured log - forward to SSE
                yield f"data: {json.dumps(log_event)}\n\n"
            else:
                # Regular output - wrap as message
                yield f"data: {json.dumps({'type': 'output', 'text': line_str})}\n\n"
        except json.JSONDecodeError:
            # Not JSON - wrap as plain text
            yield f"data: {json.dumps({'type': 'output', 'text': line_str})}\n\n"
```

### Phase 4: Frontend Status Button Updates (2 hours)

**File**: `frontend/static/js/runner-terminal.js`

```javascript
function handleLogEvent(event) {
    const data = JSON.parse(event.data);

    if (data.event === 'layer_start') {
        updateLayerStatus(data.layer, 'running');
    } else if (data.event === 'layer_complete') {
        updateLayerStatus(data.layer, 'complete');
    } else if (data.event === 'layer_error') {
        updateLayerStatus(data.layer, 'error');
    } else if (data.type === 'output') {
        appendToTerminal(data.text);
    }
}

function updateLayerStatus(layer, status) {
    const button = document.querySelector(`[data-layer="${layer}"]`);
    if (button) {
        button.classList.remove('running', 'complete', 'error', 'pending');
        button.classList.add(status);
    }
}
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/common/structured_logger.py` | New file - logger module |
| `src/layer2/pain_point_miner.py` | Add logger integration |
| `src/layer2_5/star_selector.py` | Add logger integration |
| `src/layer3/company_researcher.py` | Add logger integration |
| `src/layer3/role_researcher.py` | Add logger integration |
| `src/layer4/opportunity_mapper.py` | Add logger integration |
| `src/layer5/people_mapper.py` | Add logger integration |
| `src/layer6/generator.py` | Add logger integration |
| `src/layer7/publisher.py` | Add logger integration |
| `src/workflow.py` | Pass logger to all layers |
| `runner_service/app.py` | Parse structured logs, forward via SSE |
| `frontend/static/js/runner-terminal.js` | Handle log events, update UI |
| `frontend/templates/job_detail.html` | Add layer status buttons |

---

## Configuration

**Environment Variables**:

```bash
# Enable structured logging (default: true)
STRUCTURED_LOGGING=true

# Log level (debug, info, warning, error)
LOG_LEVEL=info

# Forward logs to LangSmith (future)
LANGSMITH_LOGGING=false
```

---

## Test Cases

1. **Logger Module**: Emit events, verify JSON format
2. **Layer Integration**: Each layer emits start/complete/error events
3. **Runner Parsing**: Distinguish structured logs from plain output
4. **Frontend Updates**: Status buttons update in real-time
5. **Error Handling**: Errors logged with stack traces

---

## Success Criteria

- [ ] All layers use StructuredLogger instead of print()
- [ ] Runner parses and forwards log events via SSE
- [ ] Frontend status buttons update in real-time
- [ ] Log events include duration and metadata
- [ ] Backward compatible (old output still works)

---

## Effort Estimate

**Total**: 6-8 hours

- Phase 1 (Logger Module): 2 hours
- Phase 2 (Layer Integration): 3 hours
- Phase 3 (Runner Integration): 2 hours
- Phase 4 (Frontend Updates): 2 hours

---

## Future Enhancements

- LangSmith integration for trace correlation
- CloudWatch/Datadog forwarding
- Metrics dashboard (layer durations, error rates)
- Cost tracking (tokens per layer)
