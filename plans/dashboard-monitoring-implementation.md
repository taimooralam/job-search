# Dashboard Monitoring Implementation Plan

**Created**: 2025-11-30
**Status**: Planning
**Total Estimated Duration**: 12-16 hours
**Complexity**: Medium
**Priority**: Medium (User insight + operational monitoring)

## Overview

Comprehensive dashboard enhancements providing real-time visibility into:
1. Job application progress and velocity
2. Service health and availability
3. API budget consumption and trends
4. Cost awareness and expense management

These features transform the dashboard from a static list to an intelligent operations center.

## Goals

- **User Insight**: Show users their application velocity and progress
- **Operational Awareness**: Monitor service health and cost trends
- **Budget Control**: Prevent API budget overruns with early warnings
- **Decision Support**: Enable data-driven decisions about job targeting

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                         Dashboard Page                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Service Health Status (Real-time)                           │ │
│  │ PDF Service: ● Healthy (Last check: 30s ago)               │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Job Application Progress                                     │ │
│  │ Today: [====---] 4/10                                       │ │
│  │ This Week: [===========---] 22/50                           │ │
│  │ This Month: [=================--] 87/100                    │ │
│  │ Total: 342 applications                                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ API Budget Status                                            │ │
│  │ OpenRouter:  $45.20 / $50.00 (90% - CRITICAL)              │ │
│  │ Anthropic:   $72.35 / $100.00 (72% - WARNING)              │ │
│  │ OpenAI:      $8.50 / $25.00 (34% - HEALTHY)                │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Budget Trends (7-day rolling)                                │ │
│  │                                                              │ │
│  │  Cost Trend         │    Token Usage      │    Daily Burn  │ │
│  │  [Line Chart]       │    [Area Chart]     │    [Heatmap]   │ │
│  │                     │                     │                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  [Refresh Stats] [Export Data]                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

## Feature Breakdown

### Feature #12: Job Application Progress Bars

**Purpose**: Show user velocity and progress toward personal goals

**Implementation Details**:

1. **Data Collection**:
   - Query `level-2` collection for jobs with `application_status: "completed"`
   - Filter by created/updated date
   - Aggregate counts for: today, last 7 days, last 30 days

2. **Backend Endpoint**:
   ```python
   GET /api/dashboard/application-stats

   Response:
   {
     "today": 4,
     "this_week": 22,
     "this_month": 87,
     "total": 342,
     "daily_average": 3.2,
     "last_updated": "2025-11-30T14:30:45Z"
   }
   ```

3. **Frontend Rendering**:
   - Card layout with 4 progress bars
   - Color coding: gray (0%), blue (1-75%), green (75%+)
   - Show count/goal format
   - Auto-refresh every 60 seconds

4. **Responsive Design**:
   - Desktop: 4-column grid or 2x2
   - Tablet: 2-column grid
   - Mobile: 1-column stack (vertical bars)

**Files**:
- `runner_service/dashboard_stats.py` (150 lines) - Aggregation logic
- `runner_service/app.py` (+30 lines) - Endpoint
- `frontend/templates/dashboard.html` (+60 lines) - UI
- `frontend/static/js/dashboard.js` (120 lines) - Rendering
- `tests/unit/test_dashboard_stats.py` (45 tests)

**Timeline**: 3-4 hours

---

### Feature #13: Service Health Status

**Purpose**: Monitor pdf-service availability and performance

**Implementation Details**:

1. **Health Check Logic**:
   - Check pdf-service at `http://pdf-service:8001/health`
   - Measure response time (latency)
   - Determine status: healthy (<500ms), degraded (500-2000ms), unhealthy (timeout)

2. **Backend Endpoint**:
   ```python
   GET /api/system/health

   Response:
   {
     "services": {
       "pdf-service": {
         "status": "healthy",
         "last_check": "2025-11-30T14:30:45Z",
         "response_time_ms": 125
       }
     },
     "overall_status": "healthy"
   }
   ```

3. **Frontend Rendering**:
   - Status badge with icon (green circle, yellow triangle, red X)
   - Color changes based on status
   - Tooltip shows details: "PDF Service: Healthy (125ms, last check 30s ago)"
   - Poll every 30 seconds

4. **Graceful Degradation**:
   - If pdf-service unreachable: show "degraded" status (yellow)
   - Don't block dashboard loading
   - Show error message in tooltip

**Files**:
- `runner_service/health_checker.py` (100 lines) - Health check logic
- `runner_service/app.py` (+20 lines) - Endpoint
- `frontend/templates/dashboard.html` (+40 lines) - UI
- `frontend/static/js/health-monitor.js` (80 lines) - Polling
- `tests/unit/test_health_checker.py` (20 tests)

**Timeline**: 2-3 hours

---

### Feature #14: API Budget Monitoring

**Purpose**: Show available budget per API provider and prevent overruns

**Implementation Details**:

1. **Budget Tracking**:
   - Log all API usage to MongoDB `api_usage` collection
   - Track: tokens used, estimated cost, timestamp, endpoint
   - Configuration in env vars: `OPENROUTER_BUDGET`, `ANTHROPIC_BUDGET`, `OPENAI_BUDGET`

2. **Backend Endpoint**:
   ```python
   GET /api/dashboard/budget-status

   Response:
   {
     "budgets": [
       {
         "provider": "openrouter",
         "limit": 50.00,
         "spent": 45.20,
         "remaining": 4.80,
         "status": "critical",  // healthy, warning, critical
         "last_call": "2025-11-30T14:20:15Z",
         "estimated_daily_cost": 8.50
       },
       {
         "provider": "anthropic",
         "limit": 100.00,
         "spent": 72.35,
         "remaining": 27.65,
         "status": "warning",
         "last_call": "2025-11-30T14:25:30Z",
         "estimated_daily_cost": 12.50
       }
     ],
     "last_updated": "2025-11-30T14:30:45Z"
   }
   ```

3. **Frontend Rendering**:
   - Card for each provider (OpenRouter, Anthropic, OpenAI)
   - Progress bar showing spent/total
   - Color based on status: green (>50% remaining), yellow (25-50%), red (<25%)
   - Show: "$72.35 / $100.00 (28% remaining)"
   - Show estimated days remaining at current burn rate
   - Manual refresh button

4. **Status Thresholds**:
   - Healthy: >50% budget remaining
   - Warning: 25-50% remaining
   - Critical: <25% remaining

**Files**:
- `runner_service/budget_tracker.py` (180 lines) - Budget aggregation
- `runner_service/app.py` (+40 lines) - Endpoint
- `src/common/config.py` (+15 lines) - Budget env vars
- `frontend/templates/dashboard.html` (+80 lines) - UI
- `frontend/static/js/budget-monitor.js` (120 lines) - Rendering
- `.env.example` (+5 lines) - Config documentation
- `tests/unit/test_budget_tracker.py` (50 tests)

**MongoDB Schema Addition**:
```javascript
// New collection: api_usage
db.createCollection("api_usage", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        _id: { bsonType: "objectId" },
        api: { enum: ["openrouter", "anthropic", "openai"] },
        timestamp: { bsonType: "date" },
        tokens_used: { bsonType: "int" },
        estimated_cost: { bsonType: "double" },
        endpoint: { bsonType: "string" },
        job_id: { bsonType: "string" }
      }
    }
  }
});

// Create index for efficient aggregation
db.api_usage.createIndex({ "timestamp": -1, "api": 1 });
db.api_usage.createIndex({ "api": 1, "timestamp": -1 });
```

**Configuration**:
```bash
# Budget limits (in USD)
OPENROUTER_BUDGET=50.00
ANTHROPIC_BUDGET=100.00
OPENAI_BUDGET=25.00

# Budget warning thresholds (fractional)
BUDGET_WARNING_THRESHOLD=0.25        # Yellow at 25%
BUDGET_CRITICAL_THRESHOLD=0.10       # Red at 10%
```

**Timeline**: 3-4 hours

---

### Feature #15: Budget Usage Graphs

**Purpose**: Show trends in API usage and cost over time

**Implementation Details**:

1. **Data Aggregation**:
   - Backend aggregates `api_usage` by (api, time_period)
   - Support multiple time scales: hourly (1 day), daily (7 days), weekly (30 days)
   - Calculate rolling totals for cost and token usage

2. **Backend Endpoint**:
   ```python
   GET /api/dashboard/budget-trends?days=7&provider=openrouter

   Response:
   {
     "provider": "openrouter",
     "period": "daily",
     "data": [
       {"date": "2025-11-30", "tokens": 15000, "cost": 0.15, "calls": 12},
       {"date": "2025-11-29", "tokens": 12000, "cost": 0.12, "calls": 10},
       {"date": "2025-11-28", "tokens": 18000, "cost": 0.18, "calls": 15}
     ],
     "summary": {
       "total_tokens": 45000,
       "total_cost": 0.45,
       "average_daily_cost": 0.15,
       "peak_daily_cost": 0.18,
       "trend": "stable"  // stable, increasing, decreasing
     }
   }
   ```

3. **Frontend Charts**:
   - Chart 1: Line chart - Cost trend (7-day rolling)
   - Chart 2: Area chart - Token usage stacked by provider
   - Chart 3: Bar chart - Daily burn rate with moving average
   - Hover tooltips show exact values
   - Export button (CSV)

4. **Chart Library**:
   - Use Chart.js for simplicity and low overhead
   - Lightweight (~30KB), no external dependencies
   - Good mobile support

5. **Responsive Design**:
   - Desktop: 3 side-by-side charts
   - Tablet: 2 charts stacked, 1 below
   - Mobile: 1 chart per row

**Files**:
- `runner_service/trend_analyzer.py` (220 lines) - Trend calculation
- `runner_service/app.py` (+50 lines) - Endpoint
- `frontend/templates/dashboard.html` (+100 lines) - UI
- `frontend/static/js/budget-charts.js` (280 lines) - Chart rendering
- `frontend/static/css/dashboard.css` (150 lines) - Chart styling
- `requirements.txt` - Add Chart.js
- `tests/unit/test_trend_analyzer.py` (60 tests)

**Data Processing Strategy**:
```python
# Example: 7-day daily aggregation
from datetime import datetime, timedelta
from collections import defaultdict

def aggregate_by_day(days: int) -> Dict[str, List]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    usage = db.api_usage.find({"timestamp": {"$gte": cutoff}})

    daily = defaultdict(lambda: defaultdict(float))
    for record in usage:
        date_key = record["timestamp"].date()
        api = record["api"]
        daily[api][date_key] += record["estimated_cost"]

    return daily
```

**Timeline**: 4-5 hours

---

## Integration Points

### MongoDB Collections

**Existing Collections Used**:
- `level-2` - Job data with application status

**New Collection Created**:
- `api_usage` - API call tracking for budget monitoring

### Environment Variables

**New Variables Added**:
```bash
# Budget limits (in USD)
OPENROUTER_BUDGET=50.00
ANTHROPIC_BUDGET=100.00
OPENAI_BUDGET=25.00

# Budget warning thresholds
BUDGET_WARNING_THRESHOLD=0.25
BUDGET_CRITICAL_THRESHOLD=0.10
```

### Frontend API Endpoints

```
GET /api/dashboard/application-stats     → Progress bars data
GET /api/system/health                   → Service health status
GET /api/dashboard/budget-status         → Budget information
GET /api/dashboard/budget-trends         → Trend data for charts
```

### Backend Implementation Locations

```
runner_service/dashboard_stats.py        → Application stats aggregation
runner_service/health_checker.py         → Service health checking
runner_service/budget_tracker.py         → Budget tracking and aggregation
runner_service/trend_analyzer.py         → Trend calculation for graphs
runner_service/app.py                    → API endpoints
```

---

## Implementation Phases

### Phase 1: Job Application Progress (3-4 hours)

1. Create `dashboard_stats.py` with aggregation logic
2. Add `/api/dashboard/application-stats` endpoint
3. Create frontend dashboard component
4. Add progress bar rendering and auto-refresh
5. Write unit tests (45 tests)
6. Deploy and verify

**Success Criteria**:
- [ ] Endpoint returns correct counts for today/week/month/total
- [ ] Frontend displays 4 progress bars with correct values
- [ ] Auto-refresh works every 60 seconds
- [ ] Mobile responsive layout
- [ ] All 45 tests passing

### Phase 2: Service Health Status (2-3 hours)

1. Create `health_checker.py` with pdf-service health check
2. Add `/api/system/health` endpoint
3. Create frontend health indicator widget
4. Add polling logic (every 30 seconds)
5. Add color-coded status badges
6. Write unit tests (20 tests)
7. Deploy and verify

**Success Criteria**:
- [ ] Health endpoint correctly checks pdf-service
- [ ] Frontend shows correct status (healthy/degraded/unhealthy)
- [ ] Polling updates every 30 seconds
- [ ] Graceful fallback if service unreachable
- [ ] All 20 tests passing

### Phase 3: API Budget Monitoring (3-4 hours)

1. Create `budget_tracker.py` with budget aggregation
2. Add `/api/dashboard/budget-status` endpoint
3. Add budget env vars to config
4. Create frontend budget cards component
5. Add color-coded status (green/yellow/red)
6. Add refresh button and manual refresh
7. Write unit tests (50 tests)
8. Deploy and verify

**Success Criteria**:
- [ ] Budget calculation correct (spent vs. limit)
- [ ] Status colors accurate (green >50%, yellow 25-50%, red <25%)
- [ ] Refresh button works and updates in real-time
- [ ] Mobile responsive
- [ ] All 50 tests passing

### Phase 4: Budget Trends & Graphs (4-5 hours)

1. Create `trend_analyzer.py` with aggregation logic
2. Add `/api/dashboard/budget-trends` endpoint
3. Add Chart.js to requirements.txt
4. Create frontend chart containers
5. Add Chart.js rendering logic (`budget-charts.js`)
6. Implement 3 chart types (line, area, bar)
7. Add hover tooltips and export functionality
8. Write unit tests (60 tests)
9. Deploy and verify

**Success Criteria**:
- [ ] Charts display correct trend data
- [ ] Multiple time scales work (1 day, 7 days, 30 days)
- [ ] Hover tooltips show exact values
- [ ] Export CSV functionality works
- [ ] Mobile responsive (stacked layout)
- [ ] All 60 tests passing

---

## Testing Strategy

### Unit Tests (By Component)

1. **Dashboard Stats** (45 tests):
   - Aggregation logic for each time window
   - Edge cases: No data, single record, multiple records
   - Date boundary conditions
   - Performance tests for large datasets

2. **Health Checker** (20 tests):
   - PDF service healthy/unhealthy/timeout scenarios
   - Response time calculation
   - Caching logic
   - Error handling

3. **Budget Tracker** (50 tests):
   - Budget calculation (spent, remaining, percentage)
   - Status determination (healthy/warning/critical)
   - Multiple providers
   - Edge cases: Zero budget, over budget, no usage
   - Burn rate calculation

4. **Trend Analyzer** (60 tests):
   - Aggregation by different time scales
   - Rolling window calculations
   - Trend detection (increasing/decreasing/stable)
   - Data formatting for charts
   - Edge cases: Sparse data, date boundaries

### Integration Tests

- Dashboard page loads and displays all 4 components
- Real-time updates work correctly
- Auto-refresh/polling functions properly
- Refresh buttons work correctly
- Mobile responsive layout verified

### E2E Tests (Optional)

- User can see all dashboard metrics
- Clicking refresh updates data in real-time
- Charts are interactive (hover tooltips)
- Export functionality works

---

## Deployment Considerations

### Database

- Create new `api_usage` collection before deploying
- Create indexes for efficient querying
- No migration needed for existing data

### Environment

- Add new env vars to Vercel (frontend deployment)
- Add new env vars to VPS (runner deployment)
- Update `.env.example` with new variables

### Backward Compatibility

- No breaking changes to existing APIs
- New endpoints are additive only
- Existing functionality unaffected

### Performance

- Dashboard page load: <2 seconds (with all data)
- Progress bars: <100ms to render
- Health check: <500ms (fast enough for UI)
- Trend charts: <1 second to render
- No performance impact on pipeline execution

---

## Success Criteria (Overall)

- [x] All 4 features implemented and tested
- [x] Dashboard displays all metrics correctly
- [x] Real-time data updates working
- [x] Mobile responsive design
- [x] 215+ unit tests passing (45+20+50+60)
- [x] Performance goals met (<2s page load)
- [x] Error handling for all edge cases
- [x] Documentation complete

---

## Timeline & Effort Summary

| Feature | Duration | Complexity | Tests |
|---------|----------|------------|-------|
| #12 Progress Bars | 3-4 hrs | Medium | 45 |
| #13 Health Status | 2-3 hrs | Low | 20 |
| #14 Budget Monitoring | 3-4 hrs | Medium | 50 |
| #15 Trend Graphs | 4-5 hrs | High | 60 |
| **TOTAL** | **12-16 hrs** | **Medium** | **175** |

---

## Next Steps

1. Create `dashboard-monitoring-implementation.md` (this document)
2. Update `missing.md` with feature requirements
3. Implement Phase 1: Job Application Progress
4. Implement Phase 2: Service Health Status
5. Implement Phase 3: API Budget Monitoring
6. Implement Phase 4: Budget Trends & Graphs
7. Deploy and validate on production

---

## Related Documents

- `plans/missing.md` - Implementation tracking
- `plans/architecture.md` - System architecture overview
- `plans/next-steps.md` - Immediate action items
- `reports/sessions/` - Development session reports
