# Gap Analysis: Circuit Breaking, Budget Guardrails, and Observability
**Date**: 2025-11-30
**Analyst**: doc-sync agent
**Focus**: Three critical operational categories

---

## Executive Summary

Complete gap analysis across three operational domains:

| Domain | Complete Gaps | Partial Gaps | Status | Priority |
|--------|---------------|--------------|--------|----------|
| **Circuit Breaking** | 1 | 0 | Missing | MEDIUM |
| **Budget Guardrails** | 2 | 1 | Partial | HIGH |
| **Observability** | 3 | 2 | Mostly Complete | MEDIUM |

---

## Circuit Breaking Gaps

### Overview

Circuit breaking is **NOT explicitly tracked** in the codebase but is a critical reliability pattern for production systems. The pipeline makes multiple external API calls (OpenAI, Anthropic, FireCrawl, Google APIs) where failures can cascade.

### Gap #CB-1: No Circuit Breaker Pattern for External Services

**Category**: Reliability Infrastructure
**Status**: NOT IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: 3-4 hours to implement

**Description**:
Pipeline layers make synchronous calls to external services without circuit breaker protection. If a service degrades (slow responses, high error rate), the pipeline continues retrying indefinitely, consuming resources and delaying failures.

**Current State**:
- Retry logic: YES (tenacity exponential backoff on all LLM calls)
- Circuit breaking: NO
- Fast-fail on repeated errors: NO
- Graceful degradation: Partial (synthetic contacts fallback for FireCrawl only)

**Impact**:
- Resource exhaustion from retry storms
- Poor user experience (slow timeouts instead of fast failure)
- No cascading failure detection across layers
- Difficult debugging when external service degrades

**Affected Layers**:
- Layer 2: OpenAI LLM calls (pain points)
- Layer 3: FireCrawl calls (company research)
- Layer 4: OpenAI LLM calls (fit scoring)
- Layer 5: FireCrawl calls (contact discovery), OpenAI (outreach)
- Layer 6: Anthropic/OpenAI/OpenRouter (CV generation)

**Recommended Solution**:
```python
# Pseudo-code pattern
from pybreaker import CircuitBreaker

llm_breaker = CircuitBreaker(
    fail_max=5,           # Fail after 5 errors
    reset_timeout=60      # Reset every 60 seconds
)

@llm_breaker
def call_openai():
    return openai.ChatCompletion.create(...)
```

**Implementation Path**:
1. Add `pybreaker` or `pycircuitbreaker` to requirements.txt
2. Wrap all external service calls with circuit breakers
3. Implement fallback strategies per layer
4. Add circuit breaker state to LangSmith traces
5. Test: Simulate service degradation and verify fast-fail behavior

---

## Budget Guardrails Gaps

### Overview

No explicit budget or cost tracking exists. With multiple LLM providers (Anthropic, OpenAI, OpenRouter), uncontrolled usage could lead to unexpected costs. CV Gen V2 implements word budgets but not token/cost budgets.

### Gap #BG-1: No LLM Token Budget Enforcement

**Category**: Cost Control
**Status**: NOT IMPLEMENTED
**Priority**: HIGH
**Complexity**: 2-3 hours

**Description**:
No mechanism to limit total tokens consumed per job or per run. Each layer can independently generate unlimited tokens, especially in Layer 6 (CV generation) with its 6-phase pipeline.

**Current State**:
- Token counting: NO
- Per-job token limits: NO
- Cost tracking: NO
- Provider prioritization: YES (Anthropic > OpenRouter > OpenAI)

**Cost Exposure** (Estimated):
- Layer 2 (pain points): ~500 tokens per call
- Layer 3 (company research): ~1000 tokens per call
- Layer 4 (fit scoring): ~500 tokens per call
- Layer 5 (outreach): ~800 tokens per call
- Layer 6 (CV generation V2): ~5000-10000 tokens (6 phases sequential)
- **Total per job**: ~8000-15000 tokens (high variance)

**Impact**:
- Unpredictable monthly costs
- No spending alerts or budget enforcement
- No way to limit expensive CV generation runs
- Difficult to debug cost surprises

**Recommended Solution**:
```python
# Pseudo-code pattern
class TokenBudget:
    def __init__(self, job_id: str, token_limit: int = 20000):
        self.job_id = job_id
        self.token_limit = token_limit
        self.tokens_used = 0

    def check_budget(self, tokens_needed: int) -> bool:
        return (self.tokens_used + tokens_needed) <= self.token_limit

    def add_tokens(self, tokens: int):
        self.tokens_used += tokens
        if self.tokens_used > self.token_limit:
            raise BudgetExceededError(f"Used {self.tokens_used} of {self.token_limit}")
```

**Implementation Path**:
1. Add `token_budget` field to JobState
2. Implement token counter wrapper for LLM calls
3. Check budget before each LLM call
4. Fail gracefully (use shorter prompts or skip optional steps)
5. Track token usage in MongoDB for analytics

---

### Gap #BG-2: No Rate Limiting for FireCrawl/LLM Calls

**Category**: Cost Control & API Fairness
**Status**: NOT IMPLEMENTED (Explicitly listed in backlog)
**Priority**: HIGH
**Complexity**: 2-3 hours

**Description**:
Pipeline layers make unlimited concurrent calls to external APIs. FireCrawl has rate limits (~600 requests/day on free tier), and LLM providers charge per token. No throttling or queuing mechanism exists.

**Current State**:
- FireCrawl calls: DEFAULT DISABLED (by design to reduce costs)
- When enabled: Sequential calls, no rate limiting
- LLM calls: Concurrent per layer, no rate limiting
- Queue depth: Unlimited

**Missing Feature**:
Listed in `plans/missing.md` under "Features (Backlog)":
```
- [ ] Rate limiting for FireCrawl/LLM calls
```

**Impact**:
- FireCrawl quota exhaustion if calls enabled
- LLM provider rate limit errors
- Unpredictable costs due to unthrottled requests
- Unfair resource usage across multiple users (if multi-tenant)

**Recommended Solution**:
```python
# Pseudo-code pattern
from ratelimit import limits, sleep_and_retry
import time

@sleep_and_retry
@limits(calls=100, period=3600)  # 100 calls per hour
def call_firecrawl(url: str):
    return firecrawl.scrape(url)

# Alternative: Token bucket algorithm
class RateLimiter:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()

    def allow_request(self) -> bool:
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False
```

**Implementation Path**:
1. Add rate limiter configuration to `runner_service/config.py`
2. Wrap FireCrawl calls with rate limiting
3. Wrap LLM calls with concurrent request limits (per provider)
4. Implement queue with backpressure for high demand
5. Add metrics: requests/second, quota remaining

---

### Gap #BG-3: No Cost Tracking / Billing Integration

**Category**: Cost Control
**Status**: NOT IMPLEMENTED
**Priority**: MEDIUM (dependent on #BG-1 and #BG-2)
**Complexity**: 3-4 hours

**Description**:
No way to track total costs per job, per user, or per month. No alerting when costs exceed thresholds. Especially problematic for multi-user systems or when running bulk jobs.

**Current State**:
- Cost metrics: Missing entirely
- Spending alerts: Missing
- Billing data: Not collected
- Cost attribution: No per-job tracking

**Partial Workaround**:
- CV Gen V2 tracks word budgets (550-650 words) to control CV size
- But no translation to token/cost impact

**Impact**:
- No visibility into actual API spend
- Difficult to justify costs to stakeholders
- No early warning of runaway costs
- Impossible to implement usage-based pricing

**Recommended Solution**:
```python
# Pseudo-code pattern
class CostTracker:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.costs = {
            "openai": 0.0,
            "anthropic": 0.0,
            "firecrawl": 0.0,
            "total": 0.0
        }

    def log_openai_call(self, model: str, input_tokens: int, output_tokens: int):
        # GPT-4: $0.03/1K input, $0.06/1K output
        cost = (input_tokens * 0.03 + output_tokens * 0.06) / 1000
        self.costs["openai"] += cost
        self.costs["total"] += cost

    def log_anthropic_call(self, model: str, input_tokens: int, output_tokens: int):
        # Claude: $0.008/1K input, $0.024/1K output
        cost = (input_tokens * 0.008 + output_tokens * 0.024) / 1000
        self.costs["anthropic"] += cost
        self.costs["total"] += cost
```

**Implementation Path**:
1. Add cost tracking to token budget wrapper
2. Calculate costs based on provider rates
3. Store cost breakdown in MongoDB per job
4. Add cost metrics to structured logging
5. Implement dashboard for cost visibility

---

## Observability Gaps

### Overview

Observability is largely complete as of 2025-11-30 with structured logging (LayerContext) across all 10 layers. Remaining gaps are in monitoring/alerting and distributed tracing.

### Gap #OB-1: No Metrics Aggregation or Dashboards

**Category**: Monitoring
**Status**: NOT IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: 3-4 hours

**Description**:
Structured logging exists (LayerContext), but no metrics are exported to monitoring systems (Prometheus, CloudWatch, Datadog). No dashboards for pipeline health, performance, or error rates.

**Current State**:
- Structured logging: YES (LayerContext with duration_ms, status)
- Prometheus metrics: NO
- Grafana dashboards: NO
- CloudWatch integration: NO
- LangSmith traces: NO

**Log Structure**:
```json
{
  "timestamp": "2025-11-30T14:30:45.123Z",
  "event": "layer_complete",
  "layer_id": 2,
  "layer_name": "pain_point_miner",
  "status": "success",
  "duration_ms": 4500,
  "metadata": {"job_id": "...", "company": "..."}
}
```

**Impact**:
- No real-time pipeline health visibility
- Difficult to spot performance regressions
- No alerting on high error rates
- Requires manual log parsing for debugging

**Recommended Solution**:
```python
# Pseudo-code pattern - Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

layer_duration = Histogram(
    'layer_duration_seconds',
    'Layer execution time',
    ['layer_id', 'status']
)

layer_errors = Counter(
    'layer_errors_total',
    'Layer errors',
    ['layer_id', 'error_type']
)

pipeline_progress = Gauge(
    'pipeline_progress_layers',
    'Pipeline progress',
    ['job_id', 'layer_id']
)
```

**Implementation Path**:
1. Add prometheus_client to requirements.txt
2. Wrap LayerContext logging with Prometheus metrics
3. Export metrics on `/metrics` endpoint (runner service)
4. Set up Prometheus scraper
5. Create Grafana dashboard with key metrics

---

### Gap #OB-2: No Error Alerting Framework

**Category**: Alerting & Incident Response
**Status**: NOT IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: 2-3 hours

**Description**:
Errors are logged but not actively alerted. No way to be notified of pipeline failures, timeouts, or anomalies. Critical for production reliability.

**Current State**:
- Error logging: YES (LayerContext tracks errors)
- Slack alerts: NO
- Email alerts: NO
- PagerDuty integration: NO
- Alert thresholds: NO

**Missing Alerts**:
- Pipeline timeout (>30 minutes)
- Layer failure rate >10% in 5 min window
- External API failures (FireCrawl, LLM providers)
- Circuit breaker trip
- Budget exceeded

**Impact**:
- Silent failures (pipeline runs but fails silently)
- Delayed incident response
- No proactive monitoring
- Difficult to meet SLA requirements

**Recommended Solution**:
```python
# Pseudo-code pattern
class AlertManager:
    def __init__(self, slack_webhook_url: str):
        self.slack_webhook = slack_webhook_url

    def alert_layer_failure(self, layer_id: int, error: str):
        self.send_slack(f"❌ Layer {layer_id} failed: {error}")

    def alert_budget_exceeded(self, job_id: str, spent: float, limit: float):
        self.send_slack(f"⚠️ Budget exceeded for {job_id}: ${spent:.2f} > ${limit:.2f}")

    def alert_circuit_breaker_open(self, service: str):
        self.send_slack(f"🔴 Circuit breaker open for {service}")
```

**Implementation Path**:
1. Add alerting config to runner_service/config.py
2. Implement AlertManager class with Slack/email support
3. Integrate with LayerContext logging
4. Add alert triggers for critical conditions
5. Test alert routing and delivery

---

### Gap #OB-3: No Distributed Tracing Integration

**Category**: Observability
**Status**: NOT IMPLEMENTED (Future enhancement)
**Priority**: LOW
**Complexity**: 4-6 hours

**Description**:
LangSmith integration is planned but not implemented. No way to correlate logs across layers or trace requests through the entire system. Makes debugging complex issues difficult.

**Current State**:
- LangSmith integration: NO
- Trace ID propagation: NO
- Cross-layer correlation: NO
- Request tracing: NO

**Future Benefit**:
LangSmith would enable:
- Visual pipeline execution traces
- Per-node performance attribution
- Token usage tracking per node
- Integration with LangGraph debugging

**Impact**:
- Difficult to debug issues spanning multiple layers
- No visual representation of pipeline execution
- Missing integration with LangGraph developer experience

**Recommended Solution**:
```python
# Pseudo-code pattern - LangSmith integration
from langsmith import run_on_project

@run_on_project("job-search-pipeline")
def layer_2_node(state: JobState) -> JobState:
    # LangSmith automatically tracks execution
    result = pain_point_miner(state)
    return state  # Automatically logged with traces
```

**Implementation Path**:
1. Add langsmith to requirements.txt
2. Add LANGSMITH_API_KEY to runner config
3. Decorate pipeline layers with @run_on_project
4. Enable token usage tracking in LangSmith
5. Create LangSmith dashboard for pipeline visualization

---

## Summary: All Gaps by Priority

### HIGH Priority (Implement Next)

| Gap # | Name | Category | Effort | Reason |
|-------|------|----------|--------|--------|
| BG-1 | Token Budget Enforcement | Budget | 2-3h | Prevent cost surprises |
| BG-2 | Rate Limiting | Budget | 2-3h | Protect against quota exhaustion |

### MEDIUM Priority (Implement After High Priority)

| Gap # | Name | Category | Effort | Reason |
|-------|------|----------|--------|--------|
| CB-1 | Circuit Breaker Pattern | Circuit | 3-4h | Improve reliability and user experience |
| OB-1 | Metrics & Dashboards | Observability | 3-4h | Enable production monitoring |
| OB-2 | Error Alerting | Observability | 2-3h | Enable incident response |

### LOW Priority (Future Enhancement)

| Gap # | Name | Category | Effort | Reason |
|-------|------|----------|--------|--------|
| BG-3 | Cost Tracking/Billing | Budget | 3-4h | Visibility into costs |
| OB-3 | Distributed Tracing | Observability | 4-6h | Enhanced debugging |

---

## Recommended Implementation Order

1. **Gap #BG-1** (Token Budget): 2-3 hours
   - Blocks BG-3, enables CB-1
   - Highest impact per hour

2. **Gap #BG-2** (Rate Limiting): 2-3 hours
   - Complements BG-1
   - Protects production infrastructure

3. **Gap #CB-1** (Circuit Breaking): 3-4 hours
   - Requires token budget to be effective
   - Improves reliability significantly

4. **Gap #OB-1** (Metrics): 3-4 hours
   - Essential for monitoring CB-1 and BG-1
   - Enable dashboards for stakeholders

5. **Gap #OB-2** (Alerting): 2-3 hours
   - Requires metrics to be in place
   - Completes monitoring stack

---

## Conclusion

**Observability**: Mostly complete with structured logging (LayerContext).
**Circuit Breaking**: Not implemented but high-value reliability improvement.
**Budget Guardrails**: Partially implemented (word budgets), missing token/cost budgets and rate limiting.

**Recommended next steps**:
1. Implement token budget enforcement (Gap #BG-1)
2. Add rate limiting (Gap #BG-2)
3. Implement circuit breaker pattern (Gap #CB-1)
4. Export metrics for dashboards (Gap #OB-1)
5. Add alerting framework (Gap #OB-2)

Total estimated effort: **12-17 hours** for complete coverage of all gaps.
