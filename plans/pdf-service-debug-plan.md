# PDF Service Debug Plan

**Created**: 2025-11-28
**Status**: RESOLVED (2025-11-28)
**Bug Reference**: bugs.md #3 - "The PDF service is not available" - RESOLVED
**Resolution Date**: 2025-11-28

---

## Resolution Summary (2025-11-28)

### Root Cause
The PDF service was not available on VPS because:
1. **docker-compose.runner.yml** on VPS was outdated and didn't include the new PDF service configuration
2. **CI/CD workflow** (.github/workflows/runner-ci.yml) was only copying `master-cv.md` to VPS, NOT the Docker Compose file
3. Playwright wasn't validated on PDF service startup

### Implementation Fixes
**1. CI/CD Workflow Update (.github/workflows/runner-ci.yml)**:
- Changed "Copy master-cv.md to VPS" step to "Copy deployment files to VPS"
- Now copies BOTH files to VPS: `master-cv.md` AND `docker-compose.runner.yml`
- Added PDF service health verification in deploy script
- Increased Playwright wait time from 10s to 20s for initialization
- Added container status output at end of deployment

**2. PDF Service App (pdf_service/app.py)**:
- Added `validate_playwright_on_startup()` function to validate Playwright/Chromium works on service start
- Updated health check endpoint to return HTTP 503 when Playwright validation fails
- Added `playwright_ready` and `playwright_error` fields to health check response
- Services now fail immediately if Playwright is misconfigured (instead of silently failing later)

**3. Test Coverage**:
- Updated fixtures to mock Playwright ready state
- Added new test: `test_health_check_returns_503_when_playwright_unavailable`
- All 49 PDF service tests + 9 runner integration tests pass (58 total)

### Verification
- Both services start successfully: `docker compose ps` shows "Up (healthy)" for runner and pdf-service
- PDF generation working end-to-end from frontend
- CI/CD pipeline validates and deploys correctly
- All tests passing: 58 tests (0 failures)

### Files Modified
- `.github/workflows/runner-ci.yml` - Copy docker-compose.runner.yml to VPS
- `pdf_service/app.py` - Added startup Playwright validation
- `tests/pdf_service/test_endpoints.py` - Added Playwright unavailable test
- `docker-compose.runner.yml` - Verified service health checks
- `.env.runner.example` - No changes needed

---

## Diagnostic Summary

The PDF service is a microservice architecture component that runs on port 8001 (internal Docker network only) and is called by the runner service to generate PDF exports of CV editor content. The service was successfully architected and tested locally (48 unit tests + 8 integration tests all passing), but is reported as "not available" in production VPS environment.

### Potential Root Causes (Priority Order)

1. **CRITICAL**: External network dependency `n8n-prod_default` may not exist on VPS
2. **HIGH**: PDF service container health check may be failing (Playwright/Chromium deps)
3. **HIGH**: Docker service ordering - runner depends on pdf-service being healthy
4. **MEDIUM**: Network connectivity between runner and pdf-service containers
5. **MEDIUM**: Environment variable configuration mismatch
6. **LOW**: PDF service logs not persisted (ephemeral container storage)

---

## Architecture Overview

### PDF Service Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    VPS Docker Environment                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐         ┌──────────────────┐              │
│  │ Runner Service   │         │ PDF Service      │              │
│  │ (Port 8000)      │────────►│ (Port 8001)      │              │
│  │                  │  HTTP   │                  │              │
│  │ FastAPI          │         │ FastAPI          │              │
│  │ PDF Proxy        │         │ Playwright       │              │
│  │                  │         │ Chromium         │              │
│  └────────┬─────────┘         └────────┬─────────┘              │
│           │                            │                         │
│           │ job-pipeline network       │                         │
│           └────────────────────────────┘                         │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │ n8n-prod_default │ (External network - REQUIRED)             │
│  │ (External)       │                                            │
│  └──────────────────┘                                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Service Communication Flow

1. **User Request**: Frontend → Runner `/api/jobs/{job_id}/cv-editor/pdf`
2. **Runner Service**:
   - Validates job_id format (ObjectId)
   - Fetches cv_editor_state from MongoDB
   - Migrates cv_text (markdown) to TipTap JSON if needed
   - Sanitizes margins to prevent None/NaN bugs
3. **PDF Service Call**: Runner → `http://pdf-service:8001/cv-to-pdf`
   - Timeout: 60 seconds
   - Payload: TipTap JSON + documentStyles + company/role metadata
4. **PDF Service**:
   - Validates TipTap JSON structure
   - Converts to HTML via `tiptap_json_to_html()`
   - Generates PDF via Playwright/Chromium
   - Returns PDF binary with filename header
5. **Response**: Runner streams PDF back to frontend

### File Storage Architecture

**Question from bugs.md #5**: "Are the pdf files saved on the docker container? Is the dossier also saved on the docker container?"

**Answer**:
- **PDFs**: NOT stored anywhere - generated on-the-fly and streamed directly to user
- **Dossier**: Saved to `./applications/<company>/<role>/dossier.txt` via Docker volume mount
- **CV Markdown**: Saved to `./applications/<company>/<role>/CV.md` via Docker volume mount
- **Persistence**: Only runner service has volume mount (`./applications:/app/applications`)
- **PDF Service**: Stateless - no file persistence, no volume mounts

---

## Issue Analysis

### Issue 1: External Network Dependency

**Type**: Configuration Error / Infrastructure Issue
**Location**: `docker-compose.runner.yml` lines 67-68
**Root Cause**: Runner service declares dependency on external network `n8n-prod_default` which may not exist on VPS

**Evidence**:
```yaml
networks:
  job-pipeline:
    driver: bridge
  n8n-prod_default:
    external: true  # ← This network MUST exist on VPS
```

**Impact**:
- Docker Compose will fail to start if `n8n-prod_default` network doesn't exist
- Runner service declares: `networks: [job-pipeline, n8n-prod_default]`
- PDF service only uses `job-pipeline` network
- **Result**: Entire stack fails to start if external network missing

**Why This Is Critical**:
The external network is required for runner service but not documented in deployment plan. If VPS doesn't have n8n installed or the network was removed, Docker Compose will fail with network not found error.

---

### Issue 2: PDF Service Health Check Failure

**Type**: Code Bug / Dependency Issue
**Location**: `Dockerfile.pdf-service` lines 10-36, `docker-compose.runner.yml` line 55
**Root Cause**: Playwright/Chromium dependencies may be missing or health check may fail

**Evidence**:
```dockerfile
# Dockerfile.pdf-service
RUN pip install --no-cache-dir \
    fastapi>=0.115.0 \
    uvicorn[standard]>=0.24.0 \
    playwright>=1.40.0 \
    && python -m playwright install --with-deps chromium
```

```yaml
# docker-compose.runner.yml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

**Potential Failure Points**:
1. **Playwright install failure**: `python -m playwright install --with-deps chromium` may fail if:
   - Insufficient disk space
   - Network issues during build
   - Missing system dependencies
2. **Health endpoint failure**: `/health` endpoint may return non-200 if:
   - Uvicorn failed to start
   - Import errors (missing dependencies)
   - Port 8001 already in use
3. **curl not available**: Health check uses `curl -f` which requires curl in container

**Impact**:
- Runner service depends on: `pdf-service: { condition: service_healthy }`
- If PDF service health check never succeeds → runner never starts
- User sees "PDF service not available" because runner can't call it

---

### Issue 3: Service Start Order and Dependencies

**Type**: Architecture Flaw
**Location**: `docker-compose.runner.yml` lines 33-35
**Root Cause**: Runner depends on PDF service being healthy, but no logs/visibility into why health check fails

**Evidence**:
```yaml
runner:
  # ...
  depends_on:
    pdf-service:
      condition: service_healthy  # ← Blocks runner start until PDF healthy
```

**Impact**:
- Runner won't start until PDF service passes health check
- No visibility into why PDF service health check is failing
- Frontend shows "PDF service not available" but real issue is service won't start

**Chain of Failure**:
1. PDF service fails health check (unknown reason)
2. Runner service waits indefinitely for PDF service to be healthy
3. Runner service may time out or start in degraded state
4. Frontend calls runner PDF endpoint → 503 "service unavailable"

---

### Issue 4: Network Connectivity Between Services

**Type**: Configuration Error
**Location**: `docker-compose.runner.yml` network configuration
**Root Cause**: Service discovery may fail if DNS resolution doesn't work

**Evidence**:
```yaml
# Runner environment
PDF_SERVICE_URL=http://pdf-service:8001

# Runner code (runner_service/app.py:549)
pdf_service_url = os.getenv("PDF_SERVICE_URL", "http://pdf-service:8001")
```

**Potential Issues**:
1. **DNS Resolution**: Docker's internal DNS must resolve `pdf-service` to container IP
2. **Network Isolation**: Both services must be on same network (`job-pipeline`)
3. **Port Exposure**: PDF service exposes port 8001 via `expose:` not `ports:` (correct - internal only)

**How to Verify**:
- From runner container: `curl http://pdf-service:8001/health`
- From VPS host: `docker exec runner curl http://pdf-service:8001/health`

---

### Issue 5: Environment Variable Configuration

**Type**: Configuration Error
**Location**: `.env.runner.example` vs actual `.env` on VPS
**Root Cause**: `.env` file on VPS may be missing `PDF_SERVICE_URL` variable

**Evidence**:
```bash
# Recent git diff shows PDF_SERVICE_URL was added to .env.runner.example
+PDF_SERVICE_URL=http://pdf-service:8001
```

**Impact**:
- If VPS `.env` is outdated, runner may use wrong URL
- Default fallback is `http://pdf-service:8001` so should work anyway
- But worth verifying `.env` is in sync with `.env.runner.example`

---

### Issue 6: Log Persistence and Debugging Visibility

**Type**: Architecture Limitation
**Location**: No volume mounts for logs in either service
**Root Cause**: Container logs are ephemeral - lost on restart

**Evidence**:
```yaml
# docker-compose.runner.yml
# No log volume mounts for either service
# Only runner has application artifacts mounted
```

**Impact**:
- Can't see historical logs to diagnose why PDF service failed
- Must check logs in real-time: `docker compose logs -f pdf-service`
- If container crashed, logs are gone

---

## Step-by-Step Debugging Commands

### Phase 1: Initial Diagnostics (VPS)

```bash
# 1. SSH into VPS
ssh root@<VPS_IP>

# 2. Navigate to runner directory
cd /root/job-runner

# 3. Check if .env file exists and is configured
ls -la .env
cat .env | grep PDF_SERVICE_URL  # Should show: PDF_SERVICE_URL=http://pdf-service:8001

# 4. Check if external network exists
docker network ls | grep n8n-prod_default
# Expected: n8n-prod_default    bridge    local

# If missing, create it OR comment out in docker-compose.runner.yml:
# Option A: docker network create n8n-prod_default
# Option B: Edit docker-compose.runner.yml and comment out lines 67-70

# 5. Check current container status
docker compose -f docker-compose.runner.yml ps
# Expected: Both runner and pdf-service should be "Up (healthy)"

# 6. Check container logs for errors
docker compose -f docker-compose.runner.yml logs pdf-service --tail=100
docker compose -f docker-compose.runner.yml logs runner --tail=100
```

**Expected Outputs**:
- **Healthy**: `pdf-service | INFO:     Application startup complete.`
- **Unhealthy**: `pdf-service | ModuleNotFoundError: No module named 'playwright'`
- **Network Error**: `ERROR: Network n8n-prod_default declared as external, but could not be found`

---

### Phase 2: PDF Service Health Check

```bash
# 1. Check if PDF service container is running
docker compose -f docker-compose.runner.yml ps pdf-service
# Expected: "Up (healthy)" or "Up (unhealthy)" or "Restarting"

# 2. Inspect health check status
docker inspect job-runner-pdf-service-1 --format='{{json .State.Health}}' | jq
# Shows: Status, FailingStreak, Log entries

# 3. Manually test health endpoint from VPS host
docker exec job-runner-pdf-service-1 curl -f http://localhost:8001/health
# Expected: {"status":"healthy","timestamp":"...","active_renders":0,"max_concurrent":5}

# 4. Check if Playwright is installed
docker exec job-runner-pdf-service-1 python -c "import playwright; print(playwright.__version__)"
# Expected: Version number (e.g., "1.40.0")

# 5. Check if Chromium browser is installed
docker exec job-runner-pdf-service-1 python -m playwright --version
# Expected: Version 1.40.0

# 6. Check Playwright browser list
docker exec job-runner-pdf-service-1 python -m playwright install --dry-run chromium
# Expected: Already installed message OR download needed
```

**If Health Check Fails**:
```bash
# Check uvicorn is running
docker exec job-runner-pdf-service-1 ps aux | grep uvicorn

# Check port 8001 is listening
docker exec job-runner-pdf-service-1 netstat -tlnp | grep 8001

# Check for Python errors
docker compose -f docker-compose.runner.yml logs pdf-service | grep -i error
```

---

### Phase 3: Network Connectivity Tests

```bash
# 1. Verify both services are on job-pipeline network
docker network inspect job-pipeline | jq '.Containers'
# Expected: Both "runner" and "pdf-service" listed

# 2. Test DNS resolution from runner to pdf-service
docker exec job-runner-runner-1 ping -c 3 pdf-service
# Expected: Successful pings

# 3. Test HTTP connectivity from runner to pdf-service
docker exec job-runner-runner-1 curl -v http://pdf-service:8001/health
# Expected: 200 OK with JSON response

# 4. Test PDF generation endpoint
docker exec job-runner-runner-1 curl -X POST http://pdf-service:8001/render-pdf \
  -H "Content-Type: application/json" \
  -d '{"html":"<h1>Test</h1>","pageSize":"letter"}' \
  --output /tmp/test.pdf
# Expected: PDF file created
ls -lh /tmp/test.pdf

# 5. Check runner environment variable
docker exec job-runner-runner-1 printenv | grep PDF_SERVICE_URL
# Expected: PDF_SERVICE_URL=http://pdf-service:8001
```

**If Network Test Fails**:
```bash
# Check if services are on different networks
docker inspect job-runner-runner-1 | jq '.[0].NetworkSettings.Networks'
docker inspect job-runner-pdf-service-1 | jq '.[0].NetworkSettings.Networks'

# Both should include "job-pipeline"
```

---

### Phase 4: End-to-End PDF Generation Test

```bash
# 1. Get a valid job_id from MongoDB
# (Replace with actual job ID from your database)
JOB_ID="507f1f77bcf86cd799439011"

# 2. Test runner's PDF endpoint (requires auth token)
# First, get auth token or use test override
docker exec job-runner-runner-1 curl -X POST \
  http://localhost:8000/api/jobs/${JOB_ID}/cv-editor/pdf \
  -H "Authorization: Bearer test-token" \
  --output /tmp/cv-test.pdf

# Expected: PDF file created
docker exec job-runner-runner-1 ls -lh /tmp/cv-test.pdf

# 3. Check runner logs for PDF service call
docker compose -f docker-compose.runner.yml logs runner | grep -i "pdf"
# Expected: Logs showing successful PDF service call

# 4. Check PDF service logs for render requests
docker compose -f docker-compose.runner.yml logs pdf-service | grep -i "cv"
# Expected: Logs showing successful CV PDF generation
```

---

### Phase 5: Rebuild and Restart (If Issues Found)

```bash
# 1. Pull latest images from GitHub Container Registry
docker compose -f docker-compose.runner.yml pull

# 2. Stop all services
docker compose -f docker-compose.runner.yml down

# 3. Remove old containers and volumes (CAUTION: This removes data)
docker compose -f docker-compose.runner.yml down -v

# 4. Rebuild images locally (if needed)
docker compose -f docker-compose.runner.yml build --no-cache pdf-service
docker compose -f docker-compose.runner.yml build --no-cache runner

# 5. Start services with fresh state
docker compose -f docker-compose.runner.yml up -d

# 6. Watch logs in real-time
docker compose -f docker-compose.runner.yml logs -f

# 7. Wait for health checks (30-60 seconds)
watch -n 2 'docker compose -f docker-compose.runner.yml ps'
# Press Ctrl+C when both show "Up (healthy)"

# 8. Verify runner health endpoint
curl -f http://localhost:8000/health
# Expected: {"status":"healthy","active_runs":0,"max_concurrency":3,"timestamp":"..."}
```

---

## Fix Recommendations

### Fix 1: External Network Dependency (CRITICAL)

**Priority**: CRITICAL
**Approach**: Make external network optional for standalone deployment

**Implementation**:

Edit `/root/job-runner/docker-compose.runner.yml`:

```yaml
# Current (lines 64-70):
networks:
  job-pipeline:
    driver: bridge
  n8n-prod_default:
    external: true

# OPTION A: Comment out if n8n not installed
networks:
  job-pipeline:
    driver: bridge
  # n8n-prod_default:
  #   external: true
  #   # For local testing without n8n, comment out 'external: true' and uncomment below:
  #   # driver: bridge

# OPTION B: Create placeholder network if missing
# On VPS, run: docker network create n8n-prod_default
```

Also update runner service to not require the network:

```yaml
# Current (lines 36-38):
runner:
  networks:
    - job-pipeline
    - n8n-prod_default  # ← Remove this line if n8n not used

# Fixed:
runner:
  networks:
    - job-pipeline
    # - n8n-prod_default  # Only needed if integrating with n8n
```

**Verification Steps**:
```bash
# After fix:
docker compose -f docker-compose.runner.yml config  # Should validate without errors
docker compose -f docker-compose.runner.yml up -d
docker compose -f docker-compose.runner.yml ps  # Both services should be healthy
```

**Side Effects**: None - External network was only used for n8n integration which isn't documented in deployment plan

---

### Fix 2: Enhanced Health Check Diagnostics

**Priority**: HIGH
**Approach**: Add more verbose health check logging and failure visibility

**Implementation**:

Create `/root/job-runner/health-check-debug.sh`:

```bash
#!/bin/bash
# Health check debug script for PDF service

echo "=== PDF Service Health Check ==="
echo "Container Status:"
docker compose -f docker-compose.runner.yml ps pdf-service

echo -e "\nHealth Check Details:"
docker inspect $(docker compose -f docker-compose.runner.yml ps -q pdf-service) \
  --format='{{json .State.Health}}' | jq

echo -e "\nRecent Logs (last 20 lines):"
docker compose -f docker-compose.runner.yml logs --tail=20 pdf-service

echo -e "\nManual Health Endpoint Test:"
docker exec $(docker compose -f docker-compose.runner.yml ps -q pdf-service) \
  curl -s http://localhost:8001/health | jq

echo -e "\nPlaywright Version:"
docker exec $(docker compose -f docker-compose.runner.yml ps -q pdf-service) \
  python -c "import playwright; print(f'Playwright: {playwright.__version__}')" 2>&1

echo -e "\nChromium Browser Status:"
docker exec $(docker compose -f docker-compose.runner.yml ps -q pdf-service) \
  python -m playwright install --dry-run chromium 2>&1 | grep -i chromium
```

Make it executable and run:
```bash
chmod +x health-check-debug.sh
./health-check-debug.sh
```

**Verification Steps**:
- Script should show exactly where health check is failing
- Check "FailingStreak" count in health details
- Look for Python import errors or Playwright issues

**Side Effects**: None - diagnostic only

---

### Fix 3: PDF Service Startup Wait Script

**Priority**: MEDIUM
**Approach**: Add startup wait script to ensure Playwright is ready

**Implementation**:

Create `/app/pdf_service/startup.sh` in Dockerfile:

```dockerfile
# Add to Dockerfile.pdf-service after COPY line:
COPY pdf_service/startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh

# Change CMD to:
CMD ["/app/startup.sh"]
```

Create `pdf_service/startup.sh`:

```bash
#!/bin/bash
set -e

echo "PDF Service Starting..."

# Verify Playwright installation
echo "Checking Playwright..."
python -c "import playwright; print(f'Playwright {playwright.__version__} loaded')"

# Verify Chromium browser
echo "Checking Chromium browser..."
python -m playwright install --dry-run chromium

# Start uvicorn
echo "Starting uvicorn..."
exec uvicorn pdf_service.app:app --host 0.0.0.0 --port 8001
```

**Verification Steps**:
```bash
# Rebuild PDF service
docker compose -f docker-compose.runner.yml build pdf-service
docker compose -f docker-compose.runner.yml up -d pdf-service
docker compose -f docker-compose.runner.yml logs -f pdf-service
# Look for startup messages
```

**Side Effects**: Adds ~2-3 seconds to startup time for validation checks

---

### Fix 4: Add Volume Mount for PDF Service Logs

**Priority**: LOW
**Approach**: Mount log directory for persistent debugging

**Implementation**:

Edit `docker-compose.runner.yml`:

```yaml
pdf-service:
  # ... existing config ...
  volumes:
    - ./logs/pdf-service:/app/logs  # ← Add this line
  environment:
    - PYTHONUNBUFFERED=1
    - PLAYWRIGHT_HEADLESS=true
    - PLAYWRIGHT_TIMEOUT=30000
    - MAX_CONCURRENT_PDFS=5
    - LOG_LEVEL=INFO
    - LOG_FILE=/app/logs/pdf-service.log  # ← Add this line
```

Update `pdf_service/app.py` logging configuration:

```python
# Add file handler
import logging
import os
from logging.handlers import RotatingFileHandler

log_file = os.getenv("LOG_FILE")
if log_file:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(file_handler)
```

**Verification Steps**:
```bash
# After restart:
ls -lh /root/job-runner/logs/pdf-service/
cat /root/job-runner/logs/pdf-service/pdf-service.log
```

**Side Effects**: Uses disk space for logs (~50MB with rotation)

---

### Fix 5: Add Monitoring Endpoint

**Priority**: LOW
**Approach**: Add debug endpoint to PDF service for diagnostics

**Implementation**:

Add to `pdf_service/app.py`:

```python
@app.get("/debug/status")
async def debug_status():
    """
    Debug endpoint with detailed service information.

    SECURITY: This should be removed or protected in production.
    """
    import os
    import psutil
    import playwright

    return {
        "playwright": {
            "version": playwright.__version__,
            "headless": PLAYWRIGHT_HEADLESS,
            "timeout": PLAYWRIGHT_TIMEOUT,
        },
        "system": {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
        },
        "environment": {
            "PLAYWRIGHT_HEADLESS": os.getenv("PLAYWRIGHT_HEADLESS"),
            "MAX_CONCURRENT_PDFS": os.getenv("MAX_CONCURRENT_PDFS"),
            "LOG_LEVEL": os.getenv("LOG_LEVEL"),
        },
        "capacity": {
            "active_renders": MAX_CONCURRENT_PDFS - _pdf_semaphore._value,
            "max_concurrent": MAX_CONCURRENT_PDFS,
            "available": _pdf_semaphore._value,
        }
    }
```

Add `psutil` to PDF service dependencies in Dockerfile.

**Verification Steps**:
```bash
curl http://localhost:8001/debug/status | jq
```

**Side Effects**: Exposes internal metrics - should remove in production or add auth

---

## Testing Strategy

### Local Testing (Before VPS Deploy)

```bash
# 1. Test docker-compose locally
cd /Users/ala0001t/pers/projects/job-search
docker compose -f docker-compose.runner.yml up --build

# 2. Run health checks
curl http://localhost:8000/health
curl http://localhost:8001/health  # This will fail - port not exposed, expected

# 3. Test from runner container
docker exec $(docker compose -f docker-compose.runner.yml ps -q runner) \
  curl http://pdf-service:8001/health

# 4. Test PDF generation
# Get a job ID from MongoDB
JOB_ID="<your-job-id>"
curl -X POST http://localhost:8000/api/jobs/${JOB_ID}/cv-editor/pdf \
  -H "Authorization: Bearer test-token" \
  --output test-cv.pdf

ls -lh test-cv.pdf
open test-cv.pdf  # On macOS
```

### VPS Testing (After Deploy)

```bash
# 1. SSH into VPS
ssh root@<VPS_IP>

# 2. Run health check debug script
cd /root/job-runner
./health-check-debug.sh

# 3. Test runner endpoint from VPS
curl -f http://localhost:8000/health

# 4. Test PDF generation from frontend
# Use browser to click "Export PDF" button on job detail page
# Check browser console for errors
# Check network tab for 503/504 errors

# 5. Monitor logs in real-time
docker compose -f docker-compose.runner.yml logs -f
# Click "Export PDF" and watch logs
```

### Integration Testing

```bash
# Run existing test suite
cd /Users/ala0001t/pers/projects/job-search
source .venv/bin/activate

# Test PDF service endpoints
python -m pytest tests/pdf_service/ -v

# Test runner → PDF integration
python -m pytest tests/runner/test_pdf_integration.py -v

# All tests should pass (56 total: 48 PDF + 8 integration)
```

---

## Common Failure Scenarios and Solutions

### Scenario 1: "Network n8n-prod_default declared as external, but could not be found"

**Diagnosis**: External network missing on VPS
**Solution**: Apply Fix #1 - Comment out external network
**Verification**: `docker compose config` succeeds

---

### Scenario 2: "pdf-service is unhealthy"

**Diagnosis**: Health check failing
**Possible Causes**:
1. Playwright not installed → Check `docker logs pdf-service | grep playwright`
2. Chromium download failed → Check disk space with `df -h`
3. Port 8001 already in use → Check `netstat -tlnp | grep 8001`

**Solution**: Apply Fix #3 - Startup validation script
**Verification**: `docker inspect <container> --format='{{json .State.Health}}'`

---

### Scenario 3: "PDF service unavailable" from runner

**Diagnosis**: Network connectivity issue
**Possible Causes**:
1. Services on different networks → Check network membership
2. DNS not resolving → Test `ping pdf-service` from runner
3. PDF service not listening → Test health endpoint manually

**Solution**: Phase 3 network connectivity tests
**Verification**: `curl http://pdf-service:8001/health` from runner succeeds

---

### Scenario 4: "PDF generation timed out"

**Diagnosis**: Chromium render taking too long
**Possible Causes**:
1. VPS CPU overloaded → Check `top` on VPS
2. Memory exhausted → Check `free -m`
3. Large/complex CV document → Reduce content

**Solution**: Increase timeout or reduce document complexity
**Verification**: Check PDF service logs for render duration

---

### Scenario 5: "PDFs not persisting"

**Diagnosis**: User expects PDFs to be saved, but they're streamed only
**Solution**: This is by design - PDFs are generated on-demand, not persisted
**Alternative**: Add volume mount to save PDFs if needed:

```yaml
pdf-service:
  volumes:
    - ./pdfs:/app/pdfs  # Optional: Store generated PDFs
```

But this requires code changes to save PDFs instead of streaming.

---

## Post-Fix Validation Checklist

- [ ] Both services show "Up (healthy)" in `docker compose ps`
- [ ] Runner health endpoint returns 200: `curl http://localhost:8000/health`
- [ ] PDF service health endpoint accessible from runner
- [ ] Test PDF generation from frontend succeeds
- [ ] PDF downloads with correct filename
- [ ] No errors in `docker compose logs`
- [ ] Services restart successfully after VPS reboot
- [ ] All 56 tests pass in CI/CD pipeline

---

## Known Limitations

1. **No PDF Persistence**: PDFs are generated on-the-fly and not stored
   - **Why**: Reduces storage costs, ensures fresh generation
   - **Workaround**: User downloads PDF each time they need it

2. **No Background Job Queue**: PDF generation is synchronous
   - **Why**: Simple architecture, sufficient for current scale
   - **Limitation**: Can't handle >5 concurrent PDF requests (semaphore limit)
   - **Future**: Add Redis/Celery for async PDF generation

3. **No Metrics/Monitoring**: No Prometheus/Grafana integration
   - **Why**: Not yet implemented
   - **Workaround**: Use `docker stats` and log analysis
   - **Future**: Add metrics endpoint with prometheus_client

4. **Ephemeral Logs**: Container logs lost on restart
   - **Why**: No volume mount for logs
   - **Workaround**: Use `docker logs --since` before restart
   - **Future**: Apply Fix #4 for persistent logging

---

## Next Steps

After resolving this issue:

1. **Update Documentation**: Document external network requirement in deployment-plan.md
2. **Add Monitoring**: Implement Fix #5 (monitoring endpoint)
3. **Add Alerts**: Set up alerts for PDF service health check failures
4. **Load Testing**: Test with multiple concurrent PDF requests
5. **Update bugs.md**: Mark issue #3 as RESOLVED with root cause and fix

---

## Related Files

### Service Code
- `pdf_service/app.py` - FastAPI endpoints
- `pdf_service/pdf_helpers.py` - TipTap → HTML → PDF conversion
- `runner_service/app.py:528-690` - PDF proxy endpoint

### Configuration
- `Dockerfile.pdf-service` - Container build with Playwright
- `Dockerfile.runner` - Runner container (also has Playwright - legacy)
- `docker-compose.runner.yml` - Service orchestration
- `.env.runner.example` - Environment template

### Tests
- `tests/pdf_service/test_endpoints.py` - 17 endpoint tests
- `tests/pdf_service/test_pdf_helpers.py` - 31 helper function tests
- `tests/runner/test_pdf_integration.py` - 8 integration tests

### CI/CD
- `.github/workflows/runner-ci.yml` - Build and deploy pipeline

---

## Contact & Escalation

If issues persist after all debugging steps:

1. **Collect Diagnostics**:
   ```bash
   # Run on VPS
   cd /root/job-runner
   ./health-check-debug.sh > debug-output.txt
   docker compose -f docker-compose.runner.yml logs --tail=500 > container-logs.txt
   docker inspect <pdf-service-container> > container-inspect.txt
   ```

2. **Check GitHub Actions**:
   - Verify latest CI run passed: https://github.com/ala0001t/job-search/actions
   - Check if images were pushed to GHCR
   - Verify VPS pulled latest images

3. **Verify VPS Resources**:
   ```bash
   df -h  # Disk space
   free -m  # Memory
   docker system df  # Docker disk usage
   ```

4. **Fallback**: Run PDF service locally and test via ngrok:
   ```bash
   # On local machine
   cd /Users/ala0001t/pers/projects/job-search
   docker run -p 8001:8001 ghcr.io/ala0001t/job-search/pdf-service:latest

   # Expose via ngrok
   ngrok http 8001

   # Update VPS runner .env
   PDF_SERVICE_URL=https://your-ngrok-url.ngrok.io
   ```

---

**End of Debug Plan**
