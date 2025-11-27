# Pipeline Progress Indicator - Backend Integration Guide

## Overview

This document describes how to integrate the frontend Pipeline Progress Indicator with the backend runner service. The indicator displays real-time progress as the 7-layer LangGraph pipeline executes.

## Frontend Implementation Summary

**Files Modified:**
- `/frontend/static/css/pipeline-progress.css` - Stepper component styles
- `/frontend/templates/job_detail.html` - Progress indicator UI and JavaScript

**UI Components:**
1. **Overall Progress Bar** - Shows percentage completion (0-100%)
2. **7-Layer Stepper** - Visual representation of each pipeline layer
3. **Live Logs** - Collapsible terminal showing execution logs
4. **Status Indicators** - Pending, Executing, Success, Failed states

---

## Backend Integration Options

### Option 1: Server-Sent Events (SSE) - Recommended

SSE provides real-time, one-way communication from server to client. Best for streaming progress updates.

#### Endpoint Requirements

**Endpoint:** `GET /api/runner/jobs/{run_id}/progress`

**Response Type:** `text/event-stream`

**Event Format:**
```
data: {"layer": "intake", "status": "executing", "index": 0}

data: {"layer": "intake", "status": "success", "index": 0, "duration": 2.5}

data: {"layer": "pain_points", "status": "executing", "index": 1}

data: {"layer": "pain_points", "status": "failed", "index": 1, "error": "API rate limit exceeded", "duration": 1.2}

data: {"status": "complete", "progress": 100}
```

#### Event Schema

```json
{
  "layer": "string",          // Layer name (see Layer Names below)
  "status": "string",         // "pending" | "executing" | "success" | "failed" | "skipped"
  "index": "number",          // Layer index (0-6)
  "duration": "number",       // Execution time in seconds (optional)
  "error": "string",          // Error message if failed (optional)
  "progress": "number"        // Overall progress 0-100 (optional)
}
```

#### Layer Names

Must match the `data-layer` attributes in the frontend:

1. `intake` - Parse job posting and candidate profile
2. `pain_points` - Extract company/role pain points
3. `company_research` - Research company via FireCrawl
4. `role_research` - Research specific role requirements
5. `fit_scoring` - Score candidate fit (0-100)
6. `people_mapping` - Find LinkedIn recruiters/contacts
7. `cv_outreach_generation` - Generate personalized CV and outreach

#### FastAPI Implementation Example

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

@app.get("/api/runner/jobs/{run_id}/progress")
async def stream_pipeline_progress(run_id: str):
    """Stream pipeline execution progress via Server-Sent Events."""

    async def event_generator():
        layers = [
            "intake", "pain_points", "company_research",
            "role_research", "fit_scoring", "people_mapping",
            "cv_outreach_generation"
        ]

        for i, layer in enumerate(layers):
            # Send layer start event
            yield f"data: {json.dumps({'layer': layer, 'status': 'executing', 'index': i})}\n\n"

            try:
                # Execute layer (replace with actual pipeline execution)
                start_time = time.time()
                result = await execute_layer(layer, run_id)
                duration = time.time() - start_time

                # Send layer success event
                yield f"data: {json.dumps({'layer': layer, 'status': 'success', 'index': i, 'duration': duration})}\n\n"

            except Exception as e:
                # Send layer failure event
                duration = time.time() - start_time
                yield f"data: {json.dumps({'layer': layer, 'status': 'failed', 'index': i, 'error': str(e), 'duration': duration})}\n\n"
                # Optionally continue or break on failure
                break

        # Send completion event
        yield f"data: {json.dumps({'status': 'complete', 'progress': 100})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

#### Integration with LangGraph

Hook into the LangGraph workflow to emit progress events:

```python
async def execute_pipeline_with_progress(job_id: str, progress_callback):
    """Execute pipeline and call progress_callback for each layer."""

    layers = [
        ("intake", intake_node),
        ("pain_points", pain_points_node),
        ("company_research", company_research_node),
        ("role_research", role_research_node),
        ("fit_scoring", fit_scoring_node),
        ("people_mapping", people_mapping_node),
        ("cv_outreach_generation", cv_outreach_generation_node),
    ]

    state = {"job_id": job_id}

    for i, (layer_name, node_func) in enumerate(layers):
        # Notify layer start
        await progress_callback({
            'layer': layer_name,
            'status': 'executing',
            'index': i
        })

        try:
            # Execute layer
            start_time = time.time()
            state = await node_func(state)
            duration = time.time() - start_time

            # Notify layer success
            await progress_callback({
                'layer': layer_name,
                'status': 'success',
                'index': i,
                'duration': duration
            })
        except Exception as e:
            # Notify layer failure
            duration = time.time() - start_time
            await progress_callback({
                'layer': layer_name,
                'status': 'failed',
                'index': i,
                'error': str(e),
                'duration': duration
            })
            raise

    # Notify completion
    await progress_callback({
        'status': 'complete',
        'progress': 100
    })
```

---

### Option 2: Polling Status Endpoint (Fallback)

If SSE is not feasible, the frontend falls back to polling.

#### Endpoint Requirements

**Endpoint:** `GET /api/runner/jobs/{run_id}/status`

**Response Type:** `application/json`

**Response Schema:**

```json
{
  "status": "running",           // "pending" | "running" | "completed" | "failed"
  "progress": 0.57,             // 0.0 to 1.0
  "layers": [
    {
      "name": "intake",
      "status": "success",
      "duration": 2.5
    },
    {
      "name": "pain_points",
      "status": "executing",
      "duration": null
    },
    {
      "name": "company_research",
      "status": "pending",
      "duration": null
    }
    // ... remaining layers
  ],
  "error": null                 // Error message if status is "failed"
}
```

#### Flask Implementation Example

```python
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

@app.route('/api/runner/jobs/<run_id>/status')
def get_pipeline_status(run_id):
    """Get current pipeline execution status."""

    # Fetch status from database or cache
    pipeline_run = get_pipeline_run(run_id)

    if not pipeline_run:
        return jsonify({"error": "Run not found"}), 404

    # Calculate progress
    total_layers = 7
    completed_layers = sum(1 for layer in pipeline_run.layers if layer.status == 'success')
    progress = completed_layers / total_layers

    return jsonify({
        "status": pipeline_run.status,
        "progress": progress,
        "layers": [
            {
                "name": layer.name,
                "status": layer.status,
                "duration": layer.duration,
                "error": layer.error
            }
            for layer in pipeline_run.layers
        ],
        "error": pipeline_run.error
    })
```

---

## Frontend Activation

The frontend automatically connects to the backend when the user clicks "Process Job":

```javascript
// Triggered by button click
async function processJobDetail(jobId, jobTitle) {
    // Start pipeline
    const response = await fetch('/api/runner/jobs/run', {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId, level: 2 })
    });

    const result = await response.json();

    if (result.run_id) {
        // Show progress UI
        monitorPipeline(result.run_id);
    }
}

// Monitor pipeline progress
function monitorPipeline(runId) {
    // Option 1: Connect to SSE (uncomment when backend ready)
    // connectPipelineSSE(runId);

    // Option 2: Fallback to polling (currently active)
    statusPollingInterval = setInterval(() => pollPipelineStatus(runId), 2000);
}
```

To enable SSE, uncomment line 1415 in `job_detail.html`:

```javascript
// OPTION 1: Use Server-Sent Events (SSE) for real-time updates
connectPipelineSSE(runId);  // ← Uncomment this line
```

---

## Testing the Integration

### 1. Test SSE Endpoint

```bash
# Start SSE stream
curl -N -H "Accept: text/event-stream" \
  http://72.61.92.76:8000/api/runner/jobs/test-run-123/progress

# Expected output:
# data: {"layer": "intake", "status": "executing", "index": 0}
#
# data: {"layer": "intake", "status": "success", "index": 0, "duration": 2.5}
#
# data: {"status": "complete", "progress": 100}
```

### 2. Test Polling Endpoint

```bash
# Get current status
curl http://72.61.92.76:8000/api/runner/jobs/test-run-123/status

# Expected output:
# {
#   "status": "running",
#   "progress": 0.43,
#   "layers": [...]
# }
```

### 3. Frontend Testing

1. Navigate to job detail page: `http://localhost:5000/job/{job_id}`
2. Click "Process Job" button
3. Verify progress indicator appears
4. Check browser console for SSE/polling logs
5. Verify steps update in real-time
6. Test on mobile (375px width) for responsive design

---

## Troubleshooting

### SSE Connection Fails

**Symptom:** Browser console shows "SSE connection error"

**Solutions:**
1. Verify SSE endpoint is accessible: `curl -N http://...`
2. Check CORS headers allow SSE connections
3. Ensure `Content-Type: text/event-stream` is set
4. Frontend will automatically fallback to polling

### Steps Not Updating

**Symptom:** Progress bar moves but individual steps stay "Pending"

**Solutions:**
1. Verify layer names match exactly (case-sensitive)
2. Check backend sends `layer` and `status` fields
3. Open browser DevTools → Network → check SSE/polling responses
4. Ensure `data-layer` attributes in HTML match backend layer names

### Mobile UI Issues

**Symptom:** Stepper looks broken on mobile

**Solutions:**
1. Check viewport meta tag in `base.html`
2. Test responsive breakpoints: 375px, 768px, 1024px
3. Verify CSS file is loaded: `/static/css/pipeline-progress.css`

---

## Performance Considerations

### SSE Scalability

- **Limit concurrent SSE connections**: Use connection pooling
- **Timeout inactive connections**: Close after 5 minutes of inactivity
- **Use Redis for pub/sub**: Distribute events across multiple workers

### Polling Optimization

- **Cache status responses**: Use Redis with 1-2 second TTL
- **Batch updates**: Update all layers in single database query
- **Rate limit**: Prevent clients from polling faster than 1 request/second

---

## Next Steps

1. **Implement SSE endpoint** in runner service (`/api/runner/jobs/{run_id}/progress`)
2. **Integrate with LangGraph** to emit progress events during execution
3. **Test with real pipeline** execution
4. **Uncomment SSE connection** in frontend (`job_detail.html` line 1415)
5. **Monitor performance** and adjust polling interval if needed

---

## API Contract Summary

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/runner/jobs/run` | POST | Start pipeline | Exists |
| `/api/runner/jobs/{run_id}/progress` | GET (SSE) | Stream progress | **To Implement** |
| `/api/runner/jobs/{run_id}/status` | GET | Poll status | Exists |
| `/api/runner/jobs/{run_id}/logs` | GET (SSE) | Stream logs | Exists |

---

## Frontend Files Reference

| File | Description |
|------|-------------|
| `/frontend/static/css/pipeline-progress.css` | Stepper component styles |
| `/frontend/templates/job_detail.html` | Progress indicator UI (lines 116-294) |
| `/frontend/templates/job_detail.html` | JavaScript logic (lines 1398-1738) |

---

## Questions or Issues?

Contact the architecture team or open an issue in the project repository.
