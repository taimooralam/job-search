# Next Steps - December 1, 2025+

## Current State Summary
- **622 unit tests passing** (507 base + 62 token tracker + 53 rate limiter)
- **5 major gaps completed** this session (Config, Token Budget, Rate Limiting, Progress UI, App Stats)
- **All 7 pipeline layers working** with structured logging
- **Main branch**: 6 commits ahead, all changes documented in `plans/session-continuity-nov-30.md`

## Immediate Priority Queue

### Priority 1: Gap #13 - Service Health Status (20-30 min)
**Objective**: Add visual health indicators for PDF service and other dependencies

**Implementation Plan**:
1. Create `/api/health/status` endpoint in runner service
   - Check PDF service availability
   - Check MongoDB connection
   - Check FireCrawl connectivity
   - Return structured health object with timestamps

2. Add health indicators to frontend dashboard
   - Small status badge in header (green/yellow/red)
   - Expandable detail panel with per-service status
   - Last check timestamp

**Files to Create/Modify**:
- `runner_service/app.py` - Add `/api/health/status` endpoint
- `runner_service/health_checker.py` - New async health check module
- `frontend/templates/partials/health_status.html` - New template
- `frontend/templates/index.html` - Add health status badge

**Test Coverage Required**:
- 6-8 tests in `tests/unit/test_runner_health.py`
- Health check cascading failures
- Timeout handling for external services

**Estimated Effort**: 25 minutes implementation + 15 minutes testing = 40 minutes

---

### Priority 2: Gap CB-1 - Circuit Breaker Pattern (45-60 min)
**Objective**: Add fault tolerance for external API calls (FireCrawl, LLMs, etc.)

**Implementation Plan**:
1. Create `src/common/circuit_breaker.py`
   - States: CLOSED (normal), OPEN (fail-fast), HALF_OPEN (recovering)
   - Threshold configuration: failure_count, success_threshold, timeout
   - Thread-safe state management

2. Wrap high-risk external calls
   - FireCrawl API calls in layer2
   - OpenRouter/Anthropic calls in all layers
   - PDF service calls in runner service

3. Graceful degradation
   - FireCrawl failure: Use synthetic contacts fallback
   - LLM failure: Return cached response or "unknown" placeholder
   - PDF failure: Return error message to UI

**Files to Create/Modify**:
- `src/common/circuit_breaker.py` - Circuit breaker implementation
- `tests/unit/test_circuit_breaker.py` - 40+ tests
- `src/layer2/pain_point_miner.py` - Wrap FireCrawl calls
- `runner_service/pdf_client.py` - Wrap PDF service calls

**Test Coverage Required**: 40-50 unit tests
- State transitions
- Failure counting and reset
- Timeout handling
- Integration with existing code

**Estimated Effort**: 50 minutes implementation + 30 minutes testing = 80 minutes

---

### Priority 3: Gap OB-1 - Metrics & Dashboards (Deferred - Complex)
**Objective**: Add Prometheus metrics and Grafana visualization

**Note**: This is more complex and should be deferred until gap circuit-breaker is working.

**Planned Components**:
- Prometheus metrics export from runner and pipeline
- Job duration, success rate, cost per layer
- API call counts and latencies
- Grafana dashboard templates

---

## Testing Strategy for This Phase

### Unit Tests Required
- **Health Status**: 8 tests (all services, cascade failures)
- **Circuit Breaker**: 45 tests (state transitions, failure scenarios, integration)
- **Total**: ~53 new tests

### Target Test Execution Time
- < 5 seconds for all new tests
- Keep running total under 7 seconds for full suite

### Key Test Patterns
```python
# Health check tests
@pytest.mark.asyncio
async def test_health_status_all_services_ok():
    # All services return 200, health returns HEALTHY

@pytest.mark.asyncio
async def test_health_status_pdf_service_timeout():
    # PDF service times out, health returns DEGRADED

# Circuit breaker tests
def test_circuit_breaker_opens_after_threshold():
    # Track failures, verify OPEN state triggers

def test_circuit_breaker_half_open_succeeds():
    # Half-open state with successful request transitions to CLOSED
```

---

## Session Execution Plan

### When Starting Session (Use session-continuity agent)
```bash
# Read these in order
1. plans/session-continuity-nov-30.md ← Recent work
2. plans/architecture.md ← System design
3. plans/missing.md ← Current gaps
4. plans/next-steps-nov-30.md ← This file
```

### Implementation Phases
1. **Phase 1** (main agent): Implement gap #13 (health status)
   - Create endpoint, health checker module
   - Add frontend badge and panel
   - Run tests: `pytest tests/unit/test_runner_health.py -v`

2. **Phase 2** (test-generator agent): Write comprehensive tests
   - Edge cases: timeouts, cascading failures, partial outages
   - Target: 45+ tests, 100% coverage

3. **Phase 3** (doc-sync agent): Update documentation
   - Add to architecture.md: new health check layer
   - Update missing.md: mark gap #13 complete
   - Create session continuity report

4. **Phase 4** (main agent): Implement gap CB-1 (circuit breaker)
   - Create circuit breaker class and tests
   - Integrate with layer2, runner PDF client
   - Run full suite: `pytest tests/unit/ -v`

---

## Monitoring Checklist

Before moving to gap CB-1, verify:
- [ ] All 622 + new tests passing
- [ ] Health status endpoint working locally
- [ ] Frontend health badge displays correctly
- [ ] No regressions in existing features
- [ ] Documentation updated in missing.md

---

## Key Files to Know for Next Session

| File | Purpose | Changed? |
|------|---------|----------|
| `runner_service/config.py` | Config validation | YES (new) |
| `src/common/token_tracker.py` | Token budget enforcement | YES (new) |
| `src/common/rate_limiter.py` | Rate limiting | YES (new) |
| `runner_service/app.py` | Main API service | YES (modified) |
| `frontend/templates/partials/application_stats.html` | Stats dashboard | YES (new) |
| `plans/session-continuity-nov-30.md` | Session summary | YES (new) |
| `plans/architecture.md` | System architecture | NO (ready to update) |
| `plans/missing.md` | Gap tracking | YES (updated) |

---

## Environment Variables Needed
```bash
# Token budget (set these for full enforcement)
TOKEN_BUDGET_USD=100.00
ENFORCE_TOKEN_BUDGET=true
TOKEN_WARN_THRESHOLD=0.8

# Rate limiting
ENABLE_RATE_LIMITING=true
OPENAI_RATE_LIMIT_PER_MIN=3500
FIRECRAWL_DAILY_LIMIT=600
ANTHROPIC_RATE_LIMIT_PER_MIN=50000

# Health checks (will add next session)
HEALTH_CHECK_TIMEOUT=5
HEALTH_CHECK_INTERVAL=30
```

---

## Recommendations

### If Time is Limited
1. Focus on gap #13 (health status) - Quick win, ~40 min total
2. Defer circuit breaker to separate session
3. Mark gap #13 complete, commit with clear message

### If Time is Abundant
1. Complete gap #13 (health status)
2. Implement gap CB-1 (circuit breaker) in parallel
3. Both can be done in 2-hour session
4. Strong foundation for metrics work after

### Best Practice Reminders
- Always run full test suite before committing: `pytest tests/unit/ -v`
- Use atomic commits: one gap per commit
- No Claude signatures in commits
- Update missing.md immediately after completing each gap
- Keep session continuity report updated for next session

---

## Contact & Support

If you encounter issues:
1. Check `plans/session-continuity-nov-30.md` for recent changes
2. Review architecture in `plans/architecture.md`
3. Look at test patterns in `tests/unit/test_*.py`
4. Check environment setup in `.env.example`

Good luck with the next sprint!
