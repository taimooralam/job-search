# Scalable Redis-Orchestrated Architecture

**Generated**: 2026-01-14
**Goal**: Scale from 1 runner (3 concurrent) to 3 runners (9 concurrent) with preserved log transparency
**Status**: Architecture design + migration plan

---

## Executive Summary

### Current State
- **1 runner** with MAX_CONCURRENCY=3
- Redis already active for queue + logs
- Traefik configured for load balancing
- Single-writer limitation prevents horizontal scaling

### Target State
- **3 runners** with MAX_CONCURRENCY=3 each = **9 parallel jobs**
- Pull-based task distribution via Redis
- Log transparency preserved across all runners
- No separate API gateway (overengineering)

### Key Decision
**Runners handle both HTTP + execution** - no separate gateway. FastAPI HTTP layer is lightweight (~10ms). The heavy part is pipeline execution which happens in background threads.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SCALABLE RUNNER ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐      ┌──────────────────────────────────────────────────┐ │
│  │   Frontend  │      │              n8n-prod_default network            │ │
│  │  (Vercel)   │      │                                                  │ │
│  └──────┬──────┘      │  ┌─────────┐    ┌─────────────────────────────┐ │ │
│         │             │  │ Traefik │    │          Redis              │ │ │
│         │ HTTPS       │  │  :443   │    │  - queue:pending (LIST)     │ │ │
│         ▼             │  └────┬────┘    │  - logs:{run_id}:* (LIST)   │ │ │
│  runner.uqab.digital  │       │         │  - logs:owner:{run_id} NEW  │ │ │
│         │             │       │         │  - runner:heartbeat:{id}    │ │ │
│         │             │       │         └─────────────────────────────┘ │ │
│         │             │       │ round-robin                   ▲         │ │
│         │             │  ┌────┴────────────────┬──────────────┼───────┐ │ │
│         │             │  │                     │              │       │ │ │
│         │             │  ▼                     ▼              │       │ │ │
│         │             │ ┌──────────┐    ┌──────────┐    ┌─────┴────┐  │ │
│         │             │ │ Runner 1 │    │ Runner 2 │    │ Runner 3 │  │ │
│         │             │ │ MAX=3    │    │ MAX=3    │    │ MAX=3    │  │ │
│         │             │ │          │    │          │    │          │  │ │
│         └─────────────┼─┤ • HTTP   │    │ • HTTP   │    │ • HTTP   │  │ │
│                       │ │ • Pull   │    │ • Pull   │    │ • Pull   │  │ │
│                       │ │ • Execute│    │ • Execute│    │ • Execute│  │ │
│                       │ └──────────┘    └──────────┘    └──────────┘  │ │
│                       │                                               │ │
│                       └───────────────────────────────────────────────┘ │
│                                                                         │
│  TOTAL CAPACITY: 3 runners × 3 concurrent = 9 parallel jobs            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## How It Works

### Two Independent Flows

```
FLOW 1: HTTP REQUEST ROUTING (Traefik)
────────────────────────────────────────
For: API calls, log polling, health checks

Frontend ──► Traefik ──► Round-robin to any Runner ──► Response
                  │
                  ├──► Runner 1
                  ├──► Runner 2
                  └──► Runner 3

Traefik does NOT know about Redis. It just load-balances HTTP requests.


FLOW 2: TASK QUEUE DISTRIBUTION (Redis)
────────────────────────────────────────
For: Long-running jobs (CV generation, research, ingestion)

Step 1: Frontend calls POST /jobs/{id}/generate-cv
        Traefik routes to ANY runner (doesn't matter which)
        Runner enqueues task to Redis, returns run_id immediately

Step 2: ALL runners have a background worker loop:
        while True:
            if my_current_jobs < MAX_CONCURRENCY (3):
                task = redis.claim_next_task()  # Atomic pop
                if task:
                    execute_in_background(task)
            sleep(100ms)

Step 3: Frontend polls GET /logs/{run_id}
        Traefik routes to ANY runner
        Runner checks: Do I own this run_id?
          - Yes → Serve from in-memory (fastest)
          - No → Serve from Redis (still works, ~5ms overhead)
```

---

## New Redis Keys

| Key Pattern | Type | Purpose | TTL |
|-------------|------|---------|-----|
| `logs:owner:{run_id}` | STRING | Which runner owns the run | 24h |
| `runner:heartbeat:{id}` | STRING | Runner alive signal | 30s |
| `runners:active` | SET | List of active runner IDs | Persistent |

---

## Implementation Details

### 1. Log Ownership Tracking

When a runner starts an operation, it claims ownership:

```python
# In operation_streaming.py
RUNNER_INSTANCE_ID = os.environ.get("HOSTNAME", uuid4().hex[:8])

async def create_operation_run(job_id: str, operation: str) -> str:
    run_id = f"op_{operation}_{uuid4().hex[:12]}"

    # Claim ownership in Redis
    await redis.setex(f"logs:owner:{run_id}", 86400, RUNNER_INSTANCE_ID)

    # Create in-memory state
    _operation_runs[run_id] = OperationState(...)

    return run_id
```

### 2. Log Routing in Poll Endpoint

When frontend polls logs, route to correct source:

```python
# In log_polling.py
@router.get("/operations/{run_id}")
async def poll_logs(run_id: str, since: int = 0):
    # Check who owns this run
    owner = await redis.get(f"logs:owner:{run_id}")

    if owner == RUNNER_INSTANCE_ID:
        # We own it - serve from in-memory (fastest)
        return serve_from_memory(run_id, since)
    else:
        # Another runner owns it OR completed - serve from Redis
        return serve_from_redis(run_id, since)


async def serve_from_memory(run_id: str, since: int) -> dict:
    """Serve logs from in-memory state (0ms latency)"""
    state = _operation_runs.get(run_id)
    if not state:
        return serve_from_redis(run_id, since)

    logs = state.logs[since:]
    return {
        "logs": [_parse_log_entry(log, i + since) for i, log in enumerate(logs)],
        "next_index": since + len(logs),
        "status": state.status,
        "expected_log_count": len(state.logs) if state.status in {"completed", "failed"} else None,
    }


async def serve_from_redis(run_id: str, since: int) -> dict:
    """Serve logs from Redis (~5-10ms latency)"""
    key = f"logs:{run_id}:buffer"
    meta_key = f"logs:{run_id}:meta"

    # Get logs from buffer
    logs = await redis.lrange(key, since, -1)

    # Get metadata
    meta = await redis.hgetall(meta_key)

    return {
        "logs": [_parse_log_entry(log, i + since) for i, log in enumerate(logs)],
        "next_index": since + len(logs),
        "status": meta.get("status", "unknown"),
        "expected_log_count": int(meta.get("expected_log_count")) if meta.get("expected_log_count") else None,
    }
```

### 3. Heartbeat + Orphan Recovery

Runners send heartbeats and recover orphaned tasks:

```python
# In app.py
RUNNER_INSTANCE_ID = os.environ.get("HOSTNAME", uuid4().hex[:8])

@app.on_event("startup")
async def startup():
    # Start heartbeat loop
    asyncio.create_task(heartbeat_loop())

    # Start orphan recovery (only one runner needs to do this)
    asyncio.create_task(orphan_recovery_loop())


async def heartbeat_loop():
    """Send heartbeat every 10s, TTL 30s"""
    while True:
        await redis.setex(f"runner:heartbeat:{RUNNER_INSTANCE_ID}", 30, "alive")
        await redis.sadd("runners:active", RUNNER_INSTANCE_ID)
        await asyncio.sleep(10)


async def orphan_recovery_loop():
    """Check for dead runners every 60s, re-queue their tasks"""
    while True:
        await asyncio.sleep(60)

        for runner_id in await redis.smembers("runners:active"):
            if not await redis.exists(f"runner:heartbeat:{runner_id}"):
                # Runner is dead - recover its tasks
                logger.warning(f"Runner {runner_id} appears dead, recovering tasks")

                # Re-queue any claimed tasks
                claimed = await redis.smembers(f"tasks:claimed:{runner_id}")
                for task_id in claimed:
                    await redis.lpush("queue:pending", task_id)
                    await redis.hset(f"queue:item:{task_id}", "status", "pending")

                # Cleanup
                await redis.delete(f"tasks:claimed:{runner_id}")
                await redis.srem("runners:active", runner_id)
```

### 4. Dual-Write Logs

Every log write goes to both in-memory and Redis:

```python
# In operation_streaming.py
def append_operation_log(run_id: str, message: str):
    """Append log to both in-memory and Redis"""
    state = _operation_runs.get(run_id)
    if state:
        # In-memory (instant access if polled directly)
        state.logs.append(message)

        # Signal waiters
        if state.log_event:
            state.log_event.set()

    # Redis (cross-runner access, fire-and-forget)
    asyncio.create_task(_persist_log_to_redis(run_id, message))


async def _persist_log_to_redis(run_id: str, message: str):
    """Fire-and-forget Redis persistence"""
    try:
        key = f"logs:{run_id}:buffer"
        await redis.rpush(key, message)
        await redis.ltrim(key, -1000, -1)  # Keep last 1000 logs
    except Exception as e:
        logger.warning(f"Failed to persist log to Redis: {e}")
```

---

## Transparency Preservation

| Feature | Single Runner | 3 Runners | Change |
|---------|---------------|-----------|--------|
| **Livetail Latency** | 0ms (in-memory) | 0-10ms | +5ms max if polling wrong runner |
| **Backend Attribution** | ✅ In log JSON | ✅ Unchanged | None |
| **Cost Tracking** | ✅ cost_usd field | ✅ Unchanged | None |
| **Layer Progress** | ✅ layer_status | ✅ In Redis | None |
| **Log Replay** | ✅ From memory | ✅ From Redis | None |
| **Error Tracebacks** | ✅ In metadata | ✅ Unchanged | None |

**Key Insight**: The frontend sees identical behavior. Log polling URL doesn't change. The only difference is internal routing.

---

## Migration Path

### Phase 1: Prepare (No Downtime) - 1 day

Add new capabilities without changing behavior:

1. **Add `logs:owner:{run_id}` key** on operation start
2. **Add heartbeat loop** (doesn't affect single-runner)
3. **Add log routing** in poll endpoint (falls back to current behavior)
4. **Test**: Verify single runner still works

```bash
# Deploy and verify
docker compose up -d
curl http://runner.uqab.digital/health
# Run a CV generation, verify logs appear in CLI panel
```

### Phase 2: Fix Livetail Gaps (No Downtime) - 1-2 days

Can't scale what you can't observe:

1. **Job Import**: Add StructuredLogger events
2. **Job Search**: Add operation tracking
3. **Annotations**: Add operation tracking
4. **Contact Outreach**: Use streaming only

### Phase 3: Scale (10 minutes)

```bash
cd /root/job-runner
docker compose up -d --scale runner=3

# Verify
docker compose ps
# Should show: runner-1, runner-2, runner-3
```

Traefik auto-discovers new containers via Docker labels.

### Phase 4: Validate

1. **Run 5+ concurrent jobs** from frontend
2. **Verify all logs appear** in CLI panel
3. **Check Redis keys**: `logs:owner:*` should show different runner IDs
4. **Kill one runner**: Verify orphan recovery re-queues its tasks

---

## Resource Projection

From `docs/current/scaling.md`:

| Container | Count | RAM (Idle) | RAM (Peak) |
|-----------|-------|------------|------------|
| runner | 3 | 273MB | 2.1GB |
| pdf-service | 1 | 44MB | 200MB |
| n8n-main | 1 | 358MB | 400MB |
| n8n-worker | 1 | 455MB | 600MB |
| n8n-postgres | 1 | 191MB | 300MB |
| n8n-redis | 1 | 4MB | 10MB |
| n8n-traefik | 1 | 24MB | 50MB |
| **TOTAL** | **9** | **1.35GB** | **3.66GB** |

**Headroom**: 12.3GB RAM available at peak load.

---

## Rollback Plan

If issues arise:

```bash
# Scale back to 1 runner
cd /root/job-runner
docker compose up -d --scale runner=1

# Verify
docker compose ps
curl http://runner.uqab.digital/health
```

Log routing code automatically falls back to in-memory when owner check fails.

---

## Files to Modify

| File | Changes | Lines |
|------|---------|-------|
| `runner_service/routes/operation_streaming.py` | Add `logs:owner` on operation start | ~5 |
| `runner_service/routes/log_polling.py` | Add log routing (memory vs Redis) | ~20 |
| `runner_service/app.py` | Add heartbeat + orphan recovery loops | ~30 |
| `runner_service/routes/job_ingest.py` | Add StructuredLogger events | ~50 |
| `runner_service/routes/job_search.py` | Add operation tracking | ~30 |
| `runner_service/routes/annotations.py` | Add operation tracking | ~40 |

---

## FAQ

### Q: Why not use a separate API gateway?

**A**: Overengineering for 3 runners. FastAPI's HTTP handling is ~10ms. The heavy part is pipeline execution which runs in background threads. Adding a gateway adds:
- Another service to maintain
- Another failure point
- Extra network hop
- Can't serve in-memory logs (gateway doesn't have them)

### Q: What if log polling hits the wrong runner?

**A**: It falls back to Redis. The latency difference is ~5-10ms, imperceptible with 200ms poll interval.

### Q: What if a runner dies mid-execution?

**A**: Heartbeat timeout (30s) triggers orphan recovery. Tasks are re-queued and picked up by other runners. Logs already in Redis are preserved.

### Q: Does frontend need changes?

**A**: No. Log polling URL stays the same. Any runner can serve any run's logs (from memory or Redis).

---

## Success Criteria

- [ ] 3 runners visible in `docker compose ps`
- [ ] All runners healthy: `/health` returns 200
- [ ] 5+ concurrent jobs execute successfully
- [ ] All logs visible in frontend CLI panel
- [ ] `logs:owner:*` keys show different runner IDs
- [ ] Orphan recovery works when killing a runner
- [ ] Cost tracking shows accurate totals
- [ ] Backend attribution (Claude CLI vs LangChain) displays correctly
