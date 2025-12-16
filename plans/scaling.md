# VPS Scaling Plan: Runners + GitHub Actions Self-Hosted Runner

## Executive Summary

Scale the production VPS (72.61.92.76) to support bulk job applications with:
1. **Keep n8n-worker at 1** (not the bottleneck)
2. **Scale job-search runners to 3** (add 2 more instances)
3. **Add GitHub Actions self-hosted runner** (repository-level, per GAP-097)

**Risk Level:** LOW - All changes are additive, no service restarts for existing containers.

---

## Current State

### Server Resources
| Resource | Total | Used | Available |
|----------|-------|------|-----------|
| CPUs | 4 | ~31% | ~69% |
| RAM | 16GB | 1.17GB | 13GB |
| Disk | 193GB | 66GB | 128GB |
| Redis | - | 2.18MB | Plenty |

### Current Containers
| Container | RAM | CPU | Role |
|-----------|-----|-----|------|
| n8n-main | 358MB | 0.1% | Workflow orchestrator |
| n8n-worker-2 | 455MB | 0.3% | Queue processor |
| n8n-postgres | 191MB | 0% | Database |
| n8n-redis | 4MB | 0.4% | Queue + shared cache |
| n8n-traefik | 24MB | 0% | Reverse proxy |
| runner-1 | 91MB | 0.2% | Job pipeline |
| pdf-service-1 | 44MB | 0.2% | PDF generation |

---

## Scaling Decisions

### 1. n8n-worker: KEEP AT 1

**Rationale:**
- Current worker handles all n8n executions (14,905+ jobs processed)
- CPU usage is minimal (0.3%) - not a bottleneck
- The actual bottleneck is downstream (job pipeline + external APIs)
- Adding workers would only help if n8n workflows were queuing, which they're not

**Action:** No change required.

### 2. Job Runners: SCALE TO 3 (Add 2)

**Rationale:**
- Current MAX_CONCURRENCY=3 per runner = 3 parallel jobs max
- User needs bulk job applications + future spy jobs + himalaya MCP
- Each additional runner adds ~300-700MB RAM peak
- FireCrawl limit (10 req/min) is per-account, not per-runner - more runners help parallelize non-FireCrawl work

**Resource Calculation:**
```
Current: 1 runner × 91MB = 91MB idle (700MB peak)
After:   3 runners × 91MB = 273MB idle (2.1GB peak)
Total new RAM: ~1.4GB additional peak
```

**Configuration Change:**
```yaml
# In docker-compose.runner.yml
services:
  runner:
    deploy:
      replicas: 3
```

### 3. GitHub Actions Self-Hosted Runner: ADD 1

**Per GAP-097 Requirements:**
- Eliminate SSH connectivity issues from GitHub-hosted runners
- Repository-level runner for taimooralam/job-search
- Auto-start as systemd service
- Health monitoring

**Resource Calculation:**
```
GitHub Actions runner: ~300-500MB RAM when active
Idle: ~50-100MB
```

---

## Implementation Plan

### Phase 1: Pre-Flight Checks (5 min)
**Goal:** Validate server state before any changes.

```bash
# SSH to server
ssh root@72.61.92.76

# Check current state
docker ps -a
docker compose -f /root/n8n-prod/docker-compose.yml ps
docker compose -f /root/job-runner/docker-compose.runner.yml ps
free -h
df -h
```

### Phase 2: Scale Job Runners (10 min)
**Goal:** Add 2 more runner instances.

**Step 2.1:** Update docker-compose.runner.yml on VPS
```yaml
services:
  runner:
    # Add deploy section for scaling
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 256M
```

**Step 2.2:** Scale up
```bash
cd /root/job-runner
docker compose -f docker-compose.runner.yml up -d --scale runner=3
```

**Step 2.3:** Verify
```bash
docker compose -f docker-compose.runner.yml ps
curl http://localhost:8000/health
# Note: Each replica gets a unique port via Traefik
```

**Rollback:** `docker compose -f docker-compose.runner.yml up -d --scale runner=1`

### Phase 3: Install GitHub Actions Runner (15 min)
**Goal:** Set up repository-level self-hosted runner.

**Step 3.1:** Create runner directory
```bash
mkdir -p /root/actions-runner && cd /root/actions-runner
```

**Step 3.2:** Download runner
```bash
# Get latest version (check GitHub for current version)
curl -o actions-runner-linux-x64-2.321.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.321.0/actions-runner-linux-x64-2.321.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.321.0.tar.gz
```

**Step 3.3:** Configure as repository runner
```bash
# Get registration token from: https://github.com/taimooralam/job-search/settings/actions/runners/new
# Click "New self-hosted runner" and copy the token

./config.sh --url https://github.com/taimooralam/job-search \
  --token {REGISTRATION_TOKEN} \
  --name "vps-runner-1" \
  --labels "self-hosted,linux,x64,vps" \
  --work "_work"
```

**Note:** For personal accounts, runners are registered per-repository. If you have multiple repos that need the runner, you can add it to each repo's settings.

**Step 3.4:** Install as systemd service
```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

**Step 3.5:** Verify in GitHub
- Go to https://github.com/taimooralam/job-search/settings/actions/runners
- Confirm runner shows as "Idle"

### Phase 4: Update CI Workflow (5 min)
**Goal:** Configure build AND deploy jobs to use self-hosted runner (Option D).

**Why Option D (Tests on GitHub, Build+Deploy on VPS)?**
- Tests (31 matrix jobs) benefit enormously from GitHub's parallelism (90+ min sequential vs ~3 min parallel)
- Build has only 2 matrix jobs - acceptable to run sequentially (~10 min vs ~5 min)
- Deploy fixes GAP-097 reliability issue (no SSH timeouts)
- Single self-hosted runner is sufficient since build runs after tests complete

**File:** `.github/workflows/runner-ci.yml`

```yaml
# KEEP test-unit and test-services on ubuntu-latest (unchanged)
# These 31 matrix jobs benefit from GitHub's parallelism

# CHANGE build job to self-hosted
build:
  needs: [test-unit, test-services]
  runs-on: self-hosted  # Changed from ubuntu-latest
  if: github.ref == 'refs/heads/main'
  permissions:
    contents: read
    packages: write
  strategy:
    fail-fast: false
    matrix:
      image:
        - name: runner
          dockerfile: Dockerfile.runner
          image_name: runner
        - name: pdf-service
          dockerfile: Dockerfile.pdf-service
          image_name: pdf-service

  steps:
    - uses: actions/checkout@v4

    - name: Log in to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Extract image metadata
      id: meta
      uses: docker/metadata-action@v5
      with:
        images: ghcr.io/${{ github.repository }}/${{ matrix.image.image_name }}
        tags: |
          type=raw,value=latest
          type=sha,prefix={{branch}}-

    - name: Build and push ${{ matrix.image.name }} image
      uses: docker/build-push-action@v5
      with:
        context: .
        file: ./${{ matrix.image.dockerfile }}
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}

# CHANGE deploy job to self-hosted
deploy:
  needs: build
  runs-on: self-hosted  # Changed from ubuntu-latest
  if: github.ref == 'refs/heads/main'

  steps:
    - uses: actions/checkout@v4

    # No SSH needed - runner has direct access
    - name: Deploy locally
      run: |
        cd /root/job-runner
        docker compose -f docker-compose.runner.yml pull
        docker compose -f docker-compose.runner.yml up -d --remove-orphans
        docker system prune -f
        sleep 20
        curl -f http://localhost:8000/health
```

**Note:** Build will run matrix jobs sequentially on single runner (~10 min total vs ~5 min parallel).

### Phase 5: Validation (10 min)
**Goal:** Confirm everything works.

**Checklist:**
- [ ] All 3 runner instances healthy: `docker compose ps`
- [ ] GitHub Actions runner online: Check GitHub UI
- [ ] n8n workflows still execute: Trigger test workflow
- [ ] Memory usage acceptable: `free -h` (should be <4GB total)
- [ ] Test deployment: Push to main branch, verify deploy job uses self-hosted runner

---

## Files to Modify

| File | Location | Change |
|------|----------|--------|
| `docker-compose.runner.yml` | VPS: `/root/job-runner/` | Add deploy.replicas: 3 |
| `runner-ci.yml` | Local: `.github/workflows/` | Change **build AND deploy** jobs to self-hosted (Option D) |
| `missing.md` | Local: `plans/` | Mark GAP-097 as complete |

---

## Resource Projection (Post-Scaling)

| Container | Count | RAM (Idle) | RAM (Peak) |
|-----------|-------|------------|------------|
| n8n-main | 1 | 358MB | 400MB |
| n8n-worker | 1 | 455MB | 600MB |
| n8n-postgres | 1 | 191MB | 300MB |
| n8n-redis | 1 | 4MB | 10MB |
| n8n-traefik | 1 | 24MB | 50MB |
| runner | 3 | 273MB | 2.1GB |
| pdf-service | 1 | 44MB | 200MB |
| actions-runner | 1 | 50MB | 500MB |
| **TOTAL** | **10** | **1.4GB** | **4.2GB** |

**Headroom:** 11.8GB RAM available at peak load.

---

## Rollback Plan

If issues arise, rollback in reverse order:

```bash
# 1. Rollback runners
cd /root/job-runner
docker compose -f docker-compose.runner.yml up -d --scale runner=1

# 2. Stop GitHub Actions runner
cd /root/actions-runner
sudo ./svc.sh stop
sudo ./svc.sh uninstall

# 3. Revert CI workflow (git revert the commit)
```

---

## Post-Implementation

1. **Monitor for 24 hours:**
   - `docker stats` - Watch memory/CPU trends
   - GitHub Actions runs - Verify self-hosted runner works
   - n8n executions - Ensure no regressions

2. **Update documentation:**
   - Mark GAP-097 as COMPLETE in `missing.md`
   - Update architecture docs if needed

3. **Future considerations:**
   - If FireCrawl becomes bottleneck, request quota increase
   - Consider adding runner health endpoint to Traefik for external monitoring
