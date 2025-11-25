# VPS Runner Deployment Plan

## Executive Summary

Complete the deployment of a working job-intelligence pipeline on Hostinger VPS with the following key deliverables:
1. Real pipeline execution (replacing stubs)
2. Artifact serving and MongoDB status persistence
3. Secure API with JWT authentication
4. CI/CD automation via GitHub Actions
5. Frontend integration for process buttons

---

## Current State Analysis

### What Exists
| Component | Status | Location |
|-----------|--------|----------|
| Runner service | ✅ COMPLETE | `runner_service/` |
| Dockerfile with Playwright | ✅ COMPLETE | `Dockerfile.runner` |
| Docker Compose | ✅ COMPLETE | `docker-compose.runner.yml` |
| Pipeline CLI | ✅ Working | `scripts/run_pipeline.py` |
| Frontend (Vercel) | ⏸️ Pending Phase 7 | `frontend/` |
| CI/CD | ✅ COMPLETE | `.github/workflows/runner-ci.yml` |

### VPS Current State (from `vps-hosting.md`)
- Runner container up on `n8n-prod_default` network
- Uses existing Redis at `redis:6379/5`
- Port 8000 exposed directly (not HTTPS)
- `.env` on VPS is empty - needs secrets
- Files at `/root/job-runner` (not git-managed)

---

## Phase 1: Real Pipeline Execution ✅ COMPLETE (25 Nov 2025)

**Status**: All tasks implemented and tested

**Delivered**:
- `runner_service/executor.py` (175 lines)
  - Async subprocess execution
  - Real-time log streaming via callback
  - Timeout handling (configurable, default 10 min)
  - Exit code capture
  - Artifact discovery (4 file types)
- `runner_service/app.py` updated with real execution
- Tests: 4/4 executor tests passing

**Goal**: Replace `_simulate_run` with actual subprocess execution of `scripts/run_pipeline.py`

### Implementation Tasks

#### 1.1 Create Pipeline Executor Module
```
runner_service/
├── app.py (existing)
├── executor.py (NEW - pipeline subprocess management)
├── models.py (NEW - shared Pydantic models)
└── __init__.py
```

**executor.py responsibilities:**
- Spawn `python scripts/run_pipeline.py --job-id {job_id} --profile {profile}`
- Stream stdout/stderr to log buffer in real-time
- Capture exit code and determine success/failure
- Parse pipeline output for artifact paths
- Handle timeouts (configurable, default 10 min)

#### 1.2 Modify `_simulate_run` → `_execute_pipeline`
```python
async def _execute_pipeline(run_id: str, job_id: str, profile_ref: Optional[str]) -> None:
    """Execute real pipeline as subprocess with log streaming."""
    try:
        _update_status(run_id, "running")

        cmd = ["python", "scripts/run_pipeline.py", "--job-id", job_id]
        if profile_ref:
            cmd.extend(["--profile", profile_ref])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ}  # Inherit .env vars
        )

        # Stream output to logs
        async for line in process.stdout:
            _append_log(run_id, line.decode().strip())

        await process.wait()

        if process.returncode == 0:
            artifacts = _discover_artifacts(job_id)
            _update_status(run_id, "completed", artifacts)
        else:
            _update_status(run_id, "failed")

    except asyncio.TimeoutError:
        _append_log(run_id, "Pipeline timed out")
        _update_status(run_id, "failed")
    except Exception as exc:
        _append_log(run_id, f"Pipeline error: {exc}")
        _update_status(run_id, "failed")
    finally:
        _semaphore.release()
```

#### 1.3 Artifact Discovery Helper
```python
def _discover_artifacts(job_id: str) -> Dict[str, str]:
    """Scan applications/ directory for generated artifacts."""
    # Pattern: applications/<company>/<role>/
    # Look for: CV.md, CV.docx, dossier.txt, cover_letter.txt
    ...
```

### Testing Strategy
- Unit test: Mock subprocess, verify log streaming
- Integration test: Run against test job with mocked LLM responses

---

## Phase 2: Artifact Serving & MongoDB Updates ✅ COMPLETE (25 Nov 2025)

**Status**: All tasks implemented and tested

**Delivered**:
- `runner_service/app.py`: Artifact endpoint with path validation
- `runner_service/persistence.py` (60 lines)
  - MongoDB `level-2` collection updates
  - Fields: `pipeline_run_id`, `pipeline_status`, `artifact_urls`
  - Best-effort persistence (non-blocking)
- Tests: Security validation, file serving tests

**Goal**: Serve generated files and persist status to MongoDB

### Implementation Tasks

#### 2.1 Artifact Serving Endpoint
```python
@app.get("/artifacts/{run_id}/{filename}")
async def get_artifact(run_id: str, filename: str) -> FileResponse:
    """Serve artifact files with path validation."""
    state = _runs.get(run_id)
    if not state:
        raise HTTPException(404, "Run not found")

    # Map run_id to job artifacts path
    artifacts_path = _get_artifacts_path(state.job_id)
    file_path = artifacts_path / filename

    # Security: Ensure file is within allowed directory
    if not file_path.resolve().is_relative_to(artifacts_path.resolve()):
        raise HTTPException(403, "Access denied")

    if not file_path.exists():
        raise HTTPException(404, "Artifact not found")

    return FileResponse(file_path)
```

#### 2.2 MongoDB Status Persistence
Add a background task to update MongoDB `level-2` collection:
```python
async def _persist_run_to_mongo(run_id: str, state: RunState) -> None:
    """Update MongoDB with run status and artifact URLs."""
    from pymongo import MongoClient

    client = MongoClient(os.getenv("MONGODB_URI"))
    db = client["jobs"]

    job_id_int = int(state.job_id) if state.job_id.isdigit() else state.job_id

    update = {
        "$set": {
            "pipeline_run_id": run_id,
            "pipeline_status": state.status,
            "pipeline_run_at": state.started_at,
            "pipeline_completed_at": state.updated_at if state.status in {"completed", "failed"} else None,
            "artifact_urls": state.artifacts,
        }
    }

    db["level-2"].update_one({"jobId": job_id_int}, update)
```

#### 2.3 Run State Persistence
Current state is in-memory only. Options:
- **Simple**: Write state to Redis (already available)
- **Complex**: Full Redis-backed state store

Recommendation: Use Redis for run state persistence to survive restarts.

---

## Phase 3: Authentication & CORS ✅ COMPLETE (25 Nov 2025)

**Status**: All tasks implemented and tested

**Delivered**:
- `runner_service/auth.py` (60 lines)
  - JWT bearer token validation
  - Shared secret from `RUNNER_API_SECRET` env var
  - Development mode bypass
  - HTTP 401 on invalid tokens
- CORS middleware in `app.py`
  - Configurable origins from `CORS_ORIGINS` env var
  - Ready for Vercel frontend integration
- Tests: 14/14 API tests with auth validation

**Goal**: Secure API access from Vercel frontend

### Implementation Tasks

#### 3.1 JWT/Shared Secret Middleware
```python
from fastapi import Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

security = HTTPBearer()
RUNNER_SECRET = os.getenv("RUNNER_API_SECRET")

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify shared secret token."""
    if credentials.credentials != RUNNER_SECRET:
        raise HTTPException(401, "Invalid token")
    return credentials
```

Apply to all endpoints:
```python
@app.post("/jobs/run", dependencies=[Depends(verify_token)])
async def run_job(...):
    ...
```

#### 3.2 CORS Configuration
```python
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # ["https://your-app.vercel.app"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### 3.3 Traefik Integration (Optional for HTTPS)
Add labels to `docker-compose.runner.yml`:
```yaml
services:
  runner:
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.runner.rule=Host(`runner.yourdomain.com`)"
      - "traefik.http.routers.runner.tls=true"
      - "traefik.http.routers.runner.tls.certresolver=letsencrypt"
```

---

## Phase 4: Environment & Compose Configuration

**Goal**: Document all required secrets and update compose

### 4.1 Create `.env.example` for Runner
```bash
# Runner Service Configuration
MAX_CONCURRENCY=3
LOG_BUFFER_LIMIT=500
RUNNER_API_SECRET=your-secret-here

# CORS (comma-separated origins)
CORS_ORIGINS=https://your-app.vercel.app

# Redis (reuse n8n Redis on DB 5)
REDIS_URL=redis://redis:6379/5

# Pipeline Secrets (must match src/common/config.py)
MONGODB_URI=mongodb+srv://...
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=...
FIRECRAWL_API_KEY=fc-...

# Optional: LangSmith tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=job-intelligence

# Optional: Google integrations (if enabled)
# GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account.json
# GOOGLE_DRIVE_FOLDER_ID=...
# GOOGLE_SHEET_ID=...
```

### 4.2 Update `docker-compose.runner.yml`
```yaml
version: "3.9"

services:
  runner:
    build:
      context: .
      dockerfile: Dockerfile.runner
    env_file:
      - .env
    environment:
      - MAX_CONCURRENCY=3
      - LOG_BUFFER_LIMIT=500
    ports:
      - "127.0.0.1:8000:8000"  # Localhost only, use Traefik for external
    volumes:
      - ./applications:/app/applications
      - ./credentials:/app/credentials:ro
      - ./master-cv.md:/app/master-cv.md:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - n8n-prod_default

networks:
  n8n-prod_default:
    external: true
```

### 4.3 Add Health Check Endpoint
```python
@app.get("/health")
async def health_check():
    """Readiness probe for container orchestration."""
    return {
        "status": "healthy",
        "active_runs": MAX_CONCURRENCY - _semaphore._value,
        "max_concurrency": MAX_CONCURRENCY,
    }
```

---

## Phase 5: Runner Smoke Tests

**Goal**: Automated tests for runner service

### 5.1 Test Structure
```
tests/
├── runner/
│   ├── __init__.py
│   ├── test_runner_api.py      # API endpoint tests
│   ├── test_executor.py        # Pipeline execution tests
│   └── conftest.py             # Fixtures
```

### 5.2 Key Test Cases

**test_runner_api.py:**
```python
import pytest
from fastapi.testclient import TestClient
from runner_service.app import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_run_job_requires_auth(client):
    response = client.post("/jobs/run", json={"job_id": "123"})
    assert response.status_code == 401

def test_run_job_with_auth(client, mock_pipeline):
    response = client.post(
        "/jobs/run",
        json={"job_id": "123"},
        headers={"Authorization": "Bearer test-secret"}
    )
    assert response.status_code == 200
    assert "run_id" in response.json()

def test_status_endpoint(client, completed_run):
    response = client.get(f"/jobs/{completed_run.run_id}/status")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

def test_log_streaming(client, running_job):
    with client.stream("GET", f"/jobs/{running_job.run_id}/logs") as response:
        lines = list(response.iter_lines())
        assert any("Starting pipeline" in line for line in lines)
```

### 5.3 Integration Smoke Test
```python
@pytest.mark.integration
def test_full_pipeline_smoke(client, test_job_in_mongo):
    """End-to-end test with real (but mocked LLM) pipeline."""
    # Trigger run
    response = client.post(
        "/jobs/run",
        json={"job_id": test_job_in_mongo},
        headers={"Authorization": f"Bearer {TEST_SECRET}"}
    )
    run_id = response.json()["run_id"]

    # Poll until complete (with timeout)
    for _ in range(60):
        status = client.get(f"/jobs/{run_id}/status").json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(1)

    assert status["status"] == "completed"
    assert "cv_md_url" in status["artifacts"]
```

---

## Phase 6: GitHub Actions CI/CD

**Goal**: Automate runner image build and VPS deployment

### 6.1 Create `.github/workflows/runner-ci.yml`
```yaml
name: Runner CI/CD

on:
  push:
    branches: [main]
    paths:
      - 'runner_service/**'
      - 'Dockerfile.runner'
      - 'docker-compose.runner.yml'
      - 'scripts/run_pipeline.py'
      - 'src/**'
      - '.github/workflows/runner-ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'runner_service/**'
      - 'Dockerfile.runner'
      - 'src/**'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}/runner

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio httpx

      - name: Run runner tests
        run: |
          python -m pytest tests/runner/ -v --tb=short
        env:
          RUNNER_API_SECRET: test-secret

  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile.runner
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: production

    steps:
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /root/job-runner
            docker compose -f docker-compose.runner.yml pull
            docker compose -f docker-compose.runner.yml up -d --remove-orphans
            docker system prune -f
```

### 6.2 Required GitHub Secrets
| Secret | Description |
|--------|-------------|
| `VPS_HOST` | Hostinger VPS IP address |
| `VPS_USER` | SSH user (root or deploy user) |
| `VPS_SSH_KEY` | Private SSH key for deployment |

---

## Phase 7: Frontend Integration

**Goal**: Wire Vercel frontend to trigger VPS pipeline runs

### 7.1 Add Vercel API Route
Create `frontend/api/runner.py`:
```python
"""Proxy routes to VPS runner service."""
import os
import requests
from flask import Blueprint, request, jsonify, Response

runner = Blueprint('runner', __name__)

RUNNER_URL = os.getenv("RUNNER_URL", "http://runner.yourdomain.com")
RUNNER_SECRET = os.getenv("RUNNER_API_SECRET")

def _runner_headers():
    return {"Authorization": f"Bearer {RUNNER_SECRET}"}

@runner.route("/api/runner/jobs/run", methods=["POST"])
def trigger_run():
    """Trigger a single job run on VPS."""
    data = request.json
    resp = requests.post(
        f"{RUNNER_URL}/jobs/run",
        json=data,
        headers=_runner_headers(),
        timeout=30
    )
    return jsonify(resp.json()), resp.status_code

@runner.route("/api/runner/jobs/run-bulk", methods=["POST"])
def trigger_bulk_run():
    """Trigger multiple job runs on VPS."""
    data = request.json
    resp = requests.post(
        f"{RUNNER_URL}/jobs/run-bulk",
        json=data,
        headers=_runner_headers(),
        timeout=30
    )
    return jsonify(resp.json()), resp.status_code

@runner.route("/api/runner/jobs/<run_id>/status")
def get_run_status(run_id: str):
    """Get status for a run."""
    resp = requests.get(
        f"{RUNNER_URL}/jobs/{run_id}/status",
        headers=_runner_headers(),
        timeout=10
    )
    return jsonify(resp.json()), resp.status_code

@runner.route("/api/runner/jobs/<run_id>/logs")
def stream_logs(run_id: str):
    """Stream logs from VPS (SSE proxy)."""
    def generate():
        with requests.get(
            f"{RUNNER_URL}/jobs/{run_id}/logs",
            headers=_runner_headers(),
            stream=True,
            timeout=300
        ) as resp:
            for line in resp.iter_lines():
                if line:
                    yield line.decode() + "\n"

    return Response(generate(), mimetype="text/event-stream")
```

### 7.2 Frontend UI Changes

**Add to job list template (`templates/jobs.html`):**
```html
<!-- Single job process button -->
<button
  hx-post="/api/runner/jobs/run"
  hx-vals='{"job_id": "{{ job.jobId }}"}'
  hx-target="#status-{{ job.jobId }}"
  hx-swap="innerHTML"
  class="btn btn-primary btn-sm">
  Process
</button>

<!-- Multi-select process -->
<button
  id="bulk-process"
  hx-post="/api/runner/jobs/run-bulk"
  hx-include="[name='selected_jobs']:checked"
  hx-target="#bulk-status"
  class="btn btn-success">
  Process Selected
</button>
```

**Job detail view with logs (`templates/job_detail.html`):**
```html
<div id="run-status" hx-get="/api/runner/jobs/{{ run_id }}/status"
     hx-trigger="every 2s" hx-swap="innerHTML">
  Loading status...
</div>

<div id="log-stream">
  <pre id="logs"></pre>
</div>

<script>
// SSE log streaming
const eventSource = new EventSource('/api/runner/jobs/{{ run_id }}/logs');
eventSource.onmessage = (e) => {
  document.getElementById('logs').textContent += e.data + '\n';
};
eventSource.addEventListener('end', (e) => {
  eventSource.close();
});
</script>
```

---

## Implementation Order

| Phase | Priority | Status | Est. Effort | Dependencies |
|-------|----------|--------|-------------|--------------|
| Phase 1 | P0 | ✅ COMPLETE | 4-6 hours | None |
| Phase 2 | P0 | ✅ COMPLETE | 2-3 hours | Phase 1 |
| Phase 3 | P1 | ✅ COMPLETE | 2 hours | None |
| Phase 4 | P1 | ⏸️ Skipped* | 1 hour | Phases 1-3 |
| Phase 5 | P1 | ⏸️ Pending | 3-4 hours | Phase 1 |
| Phase 6 | P2 | ⏸️ Pending | 2-3 hours | Phase 4 |
| Phase 7 | P2 | ⏸️ Pending | 4-6 hours | Phases 1-4 |

*Phase 4 (env config) handled via .env file directly; compose uses env_file

**Total estimated effort: 18-25 hours** | **Completed: 8-11 hours (Phases 1-3)**

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Pipeline timeout on VPS | Configurable timeout, async execution, proper cleanup |
| Memory exhaustion | MAX_CONCURRENCY=3, container resource limits |
| Secrets exposure | .env not in git, env_file in compose, minimal logging of secrets |
| Network issues Vercel→VPS | Retry logic, timeout handling, health checks |
| Redis connection loss | Graceful degradation to in-memory state |

---

## Success Criteria (Current Status)

1. ✅ **Process button works**: API endpoints functional, tested locally
2. ✅ **Artifacts accessible**: Artifact serving endpoint implemented
3. ✅ **Status persisted**: MongoDB updates working
4. ✅ **Secure**: JWT authentication implemented and tested
5. ✅ **Observable**: Log streaming and status tracking working
6. ✅ **Automated**: CI/CD workflow ready, GitHub secrets configured
7. ⏸️ **VPS deployed**: Ready for deployment (pending trigger)
8. ⏸️ **Frontend integrated**: Pending Phase 7 implementation

---

## Next Steps

### Immediate (Ready to Execute)
1. ✅ **Phases 1-3 Complete** - Runner service fully implemented
2. ⏸️ **Trigger VPS deployment** - Push to main will auto-deploy via CI/CD
3. ⏸️ **Verify VPS deployment** - Check runner health endpoint after deploy
4. ⏸️ **Test with real job** - Trigger pipeline run on VPS

### Near-term (Phase 7)
5. ⏸️ **Frontend integration** - Add runner API proxy routes
6. ⏸️ **Process buttons** - Wire UI buttons to runner endpoints
7. ⏸️ **Log streaming UI** - Add SSE log viewer to job detail page

### Completed
- ✅ Real pipeline execution
- ✅ Authentication & CORS
- ✅ MongoDB persistence
- ✅ Comprehensive testing (18/18 tests)
- ✅ Docker image built and tested locally
- ✅ CI/CD workflow configured
- ✅ GitHub secrets added
