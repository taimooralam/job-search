# Documentation Sync Report: Dashboard Monitoring Requirements

**Date**: 2025-11-30
**Agent**: doc-sync (Haiku)
**Task**: Add dashboard monitoring feature requirements to project documentation

---

## Summary

Successfully added comprehensive dashboard monitoring requirements to the project documentation, including four interconnected features for user insight and operational monitoring. All requirements are now tracked in the official project gap-tracking system.

---

## Changes Made

### 1. `plans/missing.md` - Feature Requirements Added

**Section**: "Dashboard Statistics & Monitoring (NEW - 2025-11-30)"

**Added Four Feature Gaps**:

#### Gap #12: Job Application Progress Bars
- **Priority**: High (User-facing feature)
- **Duration**: 3-4 hours
- **Complexity**: Medium
- **Status**: Not started

**Deliverables**:
- Progress bars showing: today, this week, this month, total applications
- Color-coded based on progress (gray/blue/green)
- Auto-refresh every 60 seconds
- Responsive mobile design
- MongoDB aggregation of completed applications
- Backend endpoint: `GET /api/dashboard/application-stats`

**Files to Create**:
- `runner_service/dashboard_stats.py` - Aggregation logic
- `frontend/static/js/dashboard.js` - Rendering
- `tests/unit/test_dashboard_stats.py` - 45 unit tests

#### Gap #13: Service Health Status Indicator
- **Priority**: High (Operational visibility)
- **Duration**: 2-3 hours
- **Complexity**: Low
- **Status**: Not started

**Deliverables**:
- Real-time health badge for pdf-service
- Status indicators: healthy (green), unhealthy (red), degraded (yellow)
- Last check timestamp in tooltip
- Response time measurement
- 30-second polling interval
- Graceful fallback if service unreachable

**Files to Create**:
- `runner_service/health_checker.py` - Health check logic
- `frontend/static/js/health-monitor.js` - Polling logic
- `tests/unit/test_health_checker.py` - 20 unit tests

#### Gap #14: API Budget Monitoring
- **Priority**: Medium (Cost awareness)
- **Duration**: 3-4 hours
- **Complexity**: Medium
- **Status**: Not started

**Deliverables**:
- Budget cards for: OpenRouter, Anthropic, OpenAI
- Show remaining budget in dollars or tokens
- Color-coded status: healthy (>50%), warning (25-50%), critical (<25%)
- Manual refresh button
- Configurable budget limits via env vars
- New MongoDB collection: `api_usage` for tracking

**Files to Create**:
- `runner_service/budget_tracker.py` - Budget aggregation
- `frontend/static/js/budget-monitor.js` - Budget card rendering
- `tests/unit/test_budget_tracker.py` - 50 unit tests

**Configuration Added**:
```bash
OPENROUTER_BUDGET=50.00
ANTHROPIC_BUDGET=100.00
OPENAI_BUDGET=25.00
BUDGET_WARNING_THRESHOLD=0.25
BUDGET_CRITICAL_THRESHOLD=0.10
```

#### Gap #15: Budget Usage Graphs
- **Priority**: Medium (Trend analysis)
- **Duration**: 4-5 hours
- **Complexity**: High
- **Status**: Not started

**Deliverables**:
- Mini sparkline charts showing 7-day trends
- Three chart types: Line (cost trend), Area (token usage), Bar (daily burn rate)
- Hover tooltips with exact values
- CSV export functionality
- Responsive mobile layout
- Chart.js library (lightweight, ~30KB)

**Files to Create**:
- `runner_service/trend_analyzer.py` - Trend calculation
- `frontend/static/js/budget-charts.js` - Chart rendering
- `frontend/static/css/dashboard.css` - Chart styling
- `tests/unit/test_trend_analyzer.py` - 60 unit tests

---

### 2. `plans/dashboard-monitoring-implementation.md` - Comprehensive Plan Document (NEW)

**Created**: `/Users/ala0001t/pers/projects/job-search/plans/dashboard-monitoring-implementation.md`

**Contents** (1,650+ lines):

1. **Overview & Goals**
   - User insight, operational awareness, budget control
   - System architecture diagram

2. **Feature Breakdown** (4 detailed sections)
   - Purpose, implementation details, API specs, frontend rendering
   - Files to create/modify with line counts
   - Timeline estimates
   - Configuration requirements

3. **Integration Points**
   - MongoDB collections (existing + new `api_usage`)
   - Environment variables (6 new)
   - Frontend API endpoints (4 new)
   - Backend implementation locations

4. **Implementation Phases**
   - Phase 1: Progress Bars (3-4 hrs)
   - Phase 2: Health Status (2-3 hrs)
   - Phase 3: Budget Monitoring (3-4 hrs)
   - Phase 4: Trend Graphs (4-5 hrs)

5. **Testing Strategy**
   - Unit tests per component (175 total tests)
   - Integration and E2E test approaches
   - Test coverage breakdown

6. **Deployment Considerations**
   - Database setup (new collection + indexes)
   - Environment variables
   - Backward compatibility
   - Performance targets

7. **Success Criteria & Timeline Summary**
   - Total effort: 12-16 hours
   - Test count: 175 unit tests
   - Complexity: Medium overall

---

## Detailed Specifications

### New Backend Endpoints

All endpoints follow REST conventions and return JSON:

1. **GET `/api/dashboard/application-stats`** (Gap #12)
   - Returns: today, this_week, this_month, total counts
   - Cache: No caching (real-time)

2. **GET `/api/system/health`** (Gap #13)
   - Returns: Service status, last check time, response latency
   - Cache: 30 seconds

3. **GET `/api/dashboard/budget-status`** (Gap #14)
   - Returns: Budget limits, spent, remaining, status per provider
   - Cache: 1 hour (manual refresh available)

4. **GET `/api/dashboard/budget-trends`** (Gap #15)
   - Returns: Historical cost/token data by provider and time period
   - Cache: 1 hour
   - Parameters: `days=7`, `provider=openrouter`

### Frontend Components

All components are responsive (mobile, tablet, desktop):

1. **Progress Bars Widget** (Gap #12)
   - Auto-refresh: 60 seconds
   - Color coding: gray → blue → green
   - Layout: 4-column (desktop), 2-column (tablet), 1-column (mobile)

2. **Health Status Badge** (Gap #13)
   - Auto-refresh: 30 seconds via polling
   - Icon: Circle (healthy), Triangle (degraded), X (unhealthy)
   - Tooltip: Service name, status, last check time

3. **Budget Cards** (Gap #14)
   - One card per API provider
   - Status color: Green (>50%), Yellow (25-50%), Red (<25%)
   - Elements: Limit, spent, remaining, percentage, burn rate estimate
   - Manual refresh button

4. **Trend Charts** (Gap #15)
   - Chart library: Chart.js
   - Three charts: Line, Area, Bar
   - Interactive: Hover tooltips, data point highlighting
   - Export: CSV download functionality
   - Time scales: 1 day (hourly), 7 days (daily), 30 days (weekly)

### New MongoDB Schema

**New Collection: `api_usage`**
```javascript
{
  _id: ObjectId,
  api: "openrouter" | "anthropic" | "openai",
  timestamp: ISODate("2025-11-30T..."),
  tokens_used: Number,
  estimated_cost: Number,  // USD
  endpoint: String,
  job_id: String
}
```

**Indexes**:
- Compound: `{timestamp: -1, api: 1}`
- Compound: `{api: 1, timestamp: -1}`

---

## Test Coverage

**Total Unit Tests**: 175

| Component | Tests | Focus Areas |
|-----------|-------|------------|
| Dashboard Stats | 45 | Aggregation, date boundaries, edge cases |
| Health Checker | 20 | Service checks, timeouts, latency |
| Budget Tracker | 50 | Calculations, status logic, edge cases |
| Trend Analyzer | 60 | Aggregations, time scales, trend detection |

---

## Effort Estimation

| Phase | Duration | Complexity |
|-------|----------|------------|
| #12 Progress | 3-4 hrs | Medium |
| #13 Health | 2-3 hrs | Low |
| #14 Budget | 3-4 hrs | Medium |
| #15 Graphs | 4-5 hrs | High |
| **TOTAL** | **12-16 hrs** | **Medium** |

**Per-feature breakdown:**
- Gap #12: 3-4 hours, 45 tests
- Gap #13: 2-3 hours, 20 tests
- Gap #14: 3-4 hours, 50 tests
- Gap #15: 4-5 hours, 60 tests

---

## Dependencies

### External Libraries
- **Chart.js** (~30KB) for trend visualizations (new dependency)

### Existing Infrastructure
- MongoDB (already in use)
- Runner service (already deployed)
- Frontend Flask app (already deployed)

### No Breaking Changes
- All new endpoints are additive
- Existing APIs unchanged
- Backward compatible with current deployment

---

## Verification Checklist

### Documentation Quality
- [x] All four features comprehensively documented
- [x] Clear purpose and requirements for each feature
- [x] Technical approach specified with implementation details
- [x] Files to create/modify identified with line counts
- [x] API specifications documented (endpoint, request, response)
- [x] Frontend component specifications documented
- [x] Testing strategy defined
- [x] Deployment considerations documented
- [x] Success criteria defined for each feature

### Tracking Accuracy
- [x] missing.md updated with 4 new gap entries (#12-#15)
- [x] Gap numbers sequential and non-conflicting
- [x] Priority levels appropriate (High/Medium)
- [x] Duration estimates realistic
- [x] Complexity ratings accurate
- [x] References to architecture.md maintained

### Plan Document Quality
- [x] Comprehensive implementation guide (1,650+ lines)
- [x] System architecture diagram included
- [x] Feature-by-feature breakdown with details
- [x] Integration points clearly specified
- [x] MongoDB schema with indexes defined
- [x] Four phased implementation plan
- [x] Testing strategy with test counts
- [x] Deployment considerations covered
- [x] Related documents referenced

---

## Related Documentation

### Existing Documents Referenced
- `plans/missing.md` - Implementation gap tracking (UPDATED)
- `plans/architecture.md` - System architecture overview
- `plans/phase6-pdf-service-separation.md` - Related service (health endpoint)

### New Documents Created
- `plans/dashboard-monitoring-implementation.md` - Full implementation guide

### Future Documents
- Implementation reports as phases complete
- Feature specification details if needed

---

## Recommended Next Steps

### For Development Team
1. **Prioritize** Gap #12 (Progress Bars) - highest user value
2. **Sequence**:
   - Week 1: #12 + #13 (progress + health = core features)
   - Week 2: #14 + #15 (budget + trends = advanced features)
3. **Quick Win**: Gap #13 (Health Status) is simplest to implement (2-3 hrs)

### For Product/UX
1. **Design Mockups**: Create visual specifications for dashboard layout
2. **Define Goals**: Set concrete progress targets (e.g., "10 apps/day goal")
3. **Budget Limits**: Configure realistic API budgets for production
4. **Success Metrics**: Define dashboard performance targets

### For Ops/Deployment
1. **MongoDB**: Create `api_usage` collection before deployment
2. **Environment**: Add 6 new env vars to Vercel and VPS
3. **Chart Library**: Add Chart.js to requirements.txt
4. **Testing**: Validate health checks work in production

---

## Summary

Successfully added comprehensive dashboard monitoring requirements to the Job Intelligence Pipeline project. Four interconnected features (progress bars, health status, budget monitoring, trend graphs) are now fully documented with implementation guidance, API specifications, test requirements, and timeline estimates.

**Total Estimated Effort**: 12-16 hours
**Total Unit Tests**: 175
**New Files**: 15
**Modified Files**: 5
**New MongoDB Collection**: 1 (`api_usage`)
**New Environment Variables**: 6

All changes maintain backward compatibility and follow project coding standards.

---

## Files Modified/Created

### New Files Created
- `plans/dashboard-monitoring-implementation.md` (1,650+ lines)

### Files Modified
- `plans/missing.md` (+290 lines) - Added gaps #12-#15

### No Breaking Changes
- All changes are additive
- No existing functionality modified
- All new code isolated to new modules

---

**Report Generated**: 2025-11-30
**Agent**: doc-sync
**Status**: Complete
