# Time-Based Filters: Bug Fix + Enhancement Plan

**Status**: BUG FIX COMPLETE | Enhancement PENDING
**Priority**: HIGH (bug) / MEDIUM (enhancement)
**Estimated Duration**: 3-5 hours total
**Recommended Agent**: `frontend-developer` (with backend support as needed)

---

## RESOLUTION UPDATE - 2025-12-12

### Bug Fix Status: COMPLETE

The time-based filter bug has been successfully fixed and verified working. The issue was **not** a data storage/query execution problem as originally hypothesized.

**Root Cause**: The `#job-table-container` div was missing the `hx-include=".filter-input"` attribute, preventing hidden datetime input values from being transmitted with HTMX requests.

**Solution Implemented**:
1. Added `hx-include=".filter-input"` to `#job-table-container` in `frontend/templates/index.html`
2. Verified `frontend/templates/partials/job_rows.html` properly includes datetime params in filter_query
3. Added `@app.after_request` cache-busting headers in `frontend/app.py`
4. All quick filters (1h, 3h, 6h, 12h) now work correctly with hour-level precision

**Verification**: Tested with real data - time-based filters returning correct hour ranges.

### Enhancement Status: PENDING

The enhancement for datetime-local picker inputs remains on the roadmap for future implementation.

---

## Original Overview

The job list UI has quick time-based filters (1h, 3h, 6h, 12h) that were not working correctly. They were returning all jobs from the entire day instead of the specified hour range. This document provides a complete plan for fixing the bug and adding a datetime range picker enhancement.

**Original Assumption**: Frontend and backend code appeared logically correct, suggesting a data storage/query execution problem. **Actual Finding**: The issue was a frontend HTMX configuration problem, not backend logic.

---

## Part 1: Bug Fix (#12)

### Problem Statement

User clicks "Last 1h" → Expects: jobs from past 60 minutes → Actually gets: jobs from entire day

### Root Cause Analysis Required

The code review shows:
1. ✅ Frontend correctly calculates hour offsets: `fromDate.setTime(now.getTime() - (1 * 60 * 60 * 1000))`
2. ✅ Frontend correctly formats as ISO string: `2025-11-30T14:30:00.000Z`
3. ✅ Backend correctly accepts datetime_from/datetime_to parameters
4. ✅ Backend correctly constructs MongoDB query with $gte/$lte operators

**However**: The actual query results are wrong, suggesting one of:

**Hypothesis A**: MongoDB `createdAt` field type mismatch
- Frontend sends: ISO string `"2025-11-30T14:30:00.000Z"`
- MongoDB stores: Unix timestamp (e.g., `1701349800000`) or Date object
- Fix: Convert string to timestamp in backend before querying OR ensure MongoDB stores as ISO string

**Hypothesis B**: Timezone mismatch
- Frontend timestamps: Generated in browser timezone or UTC
- MongoDB timestamps: Different timezone
- Fix: Ensure all timestamps are UTC, use explicit `Z` suffix

**Hypothesis C**: Query execution issue
- Fix: Add debug logging to verify actual query being sent to MongoDB

### Investigation Checklist

#### Step 1: Verify MongoDB Field Format (15 minutes)

```bash
# Connect to MongoDB production
mongo mongodb+srv://[your-cluster]

# Switch to job_search database
use job_search

# Check sample document
db['level-2'].findOne()

# Look specifically for createdAt field:
# - Type: Should be ISODate("...") or "2025-11-30T..."
# - Value: Should be UTC time
# - Example output:
{
  _id: ObjectId("..."),
  title: "Senior Engineer",
  company: "...",
  createdAt: ISODate("2025-11-30T14:30:00.000Z"),  // ← Check this
  ...
}
```

**Document your findings**:
- [ ] Field type: ____________________
- [ ] Sample value: ____________________
- [ ] Timezone: ____________________

#### Step 2: Verify Frontend Sends Parameter (10 minutes)

```javascript
// In browser DevTools:
// 1. Open Network tab
// 2. Click "1h" filter button
// 3. Look for request to `/partials/job-rows`
// 4. Click on request, go to "Query String Parameters"
// 5. Should see:
//    datetime_from=2025-11-30T14:30:00.000Z
//    datetime_to=2025-11-30T15:30:00.000Z

// Document findings:
// [ ] datetime_from parameter present? YES / NO
// [ ] datetime_to parameter present? YES / NO
// [ ] Format is ISO string with Z suffix? YES / NO
```

#### Step 3: Add Debug Logging (20 minutes)

**Edit**: `frontend/app.py` around line 310

```python
# BEFORE
datetime_from = request.args.get("datetime_from", "").strip()
datetime_to = request.args.get("datetime_to", "").strip()

# AFTER - Add logging
datetime_from = request.args.get("datetime_from", "").strip()
datetime_to = request.args.get("datetime_to", "").strip()

# DEBUG LOGGING
if datetime_from or datetime_to:
    logger.info(f"TIME FILTER DEBUG:")
    logger.info(f"  datetime_from = {repr(datetime_from)}")
    logger.info(f"  datetime_to = {repr(datetime_to)}")

# ... rest of code ...

# Before appending to MongoDB query, also log:
if effective_from or effective_to:
    date_filter: Dict[str, str] = {}
    if effective_from:
        if 'T' in effective_from:
            date_filter["$gte"] = effective_from
        else:
            date_filter["$gte"] = f"{effective_from}T00:00:00.000Z"
    if effective_to:
        if 'T' in effective_to:
            date_filter["$lte"] = effective_to
        else:
            date_filter["$lte"] = f"{effective_to}T23:59:59.999Z"

    # DEBUG LOGGING
    logger.info(f"  Constructed date_filter: {date_filter}")

    and_conditions.append({"createdAt": date_filter})

# After full query built, log it:
# (find where mongo_query is finalized)
logger.info(f"FINAL MONGO QUERY: {mongo_query}")
```

**Deploy** and test with "1h" filter. Check logs and document what you see.

#### Step 4: Test Query Directly (20 minutes)

Use MongoDB CLI or Atlas UI to test the query directly:

```javascript
// Get current time and 1 hour ago
const now = new Date();
const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);

console.log('Test range:');
console.log('  From:', oneHourAgo.toISOString());  // 2025-11-30T14:30:00.000Z
console.log('  To:', now.toISOString());           // 2025-11-30T15:30:00.000Z

// Query MongoDB directly
db['level-2'].find({
  createdAt: {
    $gte: oneHourAgo.toISOString(),
    $lte: now.toISOString()
  }
}).count()

// Compare with all-day query
db['level-2'].find({
  createdAt: {
    $gte: "2025-11-30T00:00:00.000Z",
    $lte: "2025-11-30T23:59:59.999Z"
  }
}).count()

// If both counts are the same, there's definitely a problem
// If 1h count < all-day count, filters are working
```

### Implementation Based on Root Cause

#### If Hypothesis A (Field Type Mismatch)

**Problem**: `createdAt` stored as timestamp, but query uses string

**Solution in `frontend/app.py`**:

```python
# Convert datetime string to milliseconds timestamp for comparison
from datetime import datetime

def datetime_to_timestamp_ms(datetime_str: str) -> int:
    """Convert ISO datetime string to milliseconds timestamp."""
    dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
    return int(dt.timestamp() * 1000)

# In filter building:
if effective_from or effective_to:
    date_filter: Dict[str, Any] = {}
    if effective_from:
        if isinstance(date_in_db, int):  # Unix timestamp stored in DB
            ts_ms = datetime_to_timestamp_ms(effective_from)
            date_filter["$gte"] = ts_ms
        else:  # ISO string stored in DB
            date_filter["$gte"] = effective_from if 'T' in effective_from else f"{effective_from}T00:00:00.000Z"
    if effective_to:
        if isinstance(date_in_db, int):
            ts_ms = datetime_to_timestamp_ms(effective_to)
            date_filter["$lte"] = ts_ms
        else:
            date_filter["$lte"] = effective_to if 'T' in effective_to else f"{effective_to}T23:59:59.999Z"
    and_conditions.append({"createdAt": date_filter})
```

#### If Hypothesis B (Timezone Mismatch)

**Problem**: Timestamps in different timezones

**Solution**: Ensure UTC everywhere
1. Frontend already uses UTC: `new Date().toISOString()` is always UTC
2. Backend: Verify all timestamps use UTC
3. MongoDB: Ensure stored dates are UTC

**Code fix** (if needed):

```python
from datetime import datetime, timezone

# When creating jobs, use UTC explicitly:
createdAt = datetime.now(timezone.utc)  # Instead of datetime.utcnow()

# Ensure query uses UTC:
effective_from = datetime_from if datetime_from else date_from

# If timezone-naive, add UTC:
if effective_from and 'Z' not in effective_from and 'T' in effective_from:
    effective_from += 'Z'  # Add UTC indicator
```

#### If Hypothesis C (Query Execution Issue)

**Problem**: Debug logs reveal query isn't reaching MongoDB or is malformed

**Solution**: Based on specific findings in logs

### Testing the Fix

Create unit tests in `tests/unit/test_time_filtering.py`:

```python
import pytest
from datetime import datetime, timedelta, timezone
from frontend.app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_one_hour_filter(client, mock_db):
    """Test that 1h filter returns jobs from past hour only."""
    # Setup: Create mock jobs
    mock_database, mock_collection = mock_db

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    two_hours_ago = now - timedelta(hours=2)

    # Mock data: job from 30 min ago (should match), 90 min ago (should NOT)
    mock_collection.count_documents.return_value = 1  # Only recent job

    # Make request
    response = client.get(
        f'/api/jobs',
        query_string={
            'datetime_from': one_hour_ago.isoformat(),
            'datetime_to': now.isoformat()
        }
    )

    # Verify query structure
    assert response.status_code == 200
    call_args = mock_collection.find.call_args
    query = call_args[0][0]

    # Check MongoDB query was constructed correctly
    assert "$and" in query
    date_condition = next((c for c in query["$and"] if "createdAt" in c), None)
    assert date_condition is not None
    assert "$gte" in date_condition["createdAt"]
    assert "$lte" in date_condition["createdAt"]

def test_three_hour_filter(client, mock_db):
    """Test that 3h filter returns jobs from past 3 hours."""
    # Similar structure
    pass

def test_filter_precision_minutes(client, mock_db):
    """Test that filter respects minute-level precision."""
    # Similar structure
    pass
```

Run tests: `pytest tests/unit/test_time_filtering.py -v`

### Deployment Checklist

- [ ] Investigation steps 1-4 completed and findings documented
- [ ] Root cause identified
- [ ] Fix implemented with debug logging
- [ ] Unit tests added and passing
- [ ] Manual testing with real data in production DB
- [ ] All quick filters tested: 1h, 3h, 6h, 12h
- [ ] Date-only filters still work (no regression)
- [ ] Debug logging removed from production code
- [ ] Commit with clear message: `fix(time-filters): Fix hour-based filtering returning all-day results`

---

## Part 2: Enhancement (#13)

### Problem Statement

Users can only filter by full days (YYYY-MM-DD). They want to filter by specific hours and minutes.

### Solution: Add DateTime Range Picker

#### UI Changes

**File**: `frontend/templates/index.html` (around lines 175-188)

**Before** (current date inputs):
```html
<input type="date" id="date-from" name="date_from" class="filter-input form-input">
<input type="date" id="date-to" name="date_to" class="filter-input form-input">
```

**After** (add datetime inputs):
```html
<div class="form-group">
    <label for="datetime-from" class="form-label">From</label>
    <input type="datetime-local"
           id="datetime-from"
           name="datetime-from"
           class="filter-input form-input"
           hx-trigger="change"
           hx-include=".filter-input"
           hx-get="/partials/job-rows">
</div>

<div class="form-group">
    <label for="datetime-to" class="form-label">To</label>
    <input type="datetime-local"
           id="datetime-to"
           name="datetime-to"
           class="filter-input form-input"
           hx-trigger="change"
           hx-include=".filter-input"
           hx-get="/partials/job-rows">
</div>

<!-- Hidden inputs for compatibility with datetime-local -->
<input type="hidden" id="date-from" name="date_from" class="filter-input">
<input type="hidden" id="date-to" name="date_to" class="filter-input">
```

#### JavaScript Changes

Update the `setQuickDateFilter` function to also populate datetime-local inputs:

```javascript
function setQuickDateFilter(button, amount, unit) {
    const now = new Date();
    let fromDate = new Date();

    switch (unit) {
        case 'hour':
            fromDate.setTime(now.getTime() - (amount * 60 * 60 * 1000));
            break;
        case 'week':
            fromDate.setTime(now.getTime() - (amount * 7 * 24 * 60 * 60 * 1000));
            break;
        case 'month':
            fromDate.setMonth(now.getMonth() - amount);
            break;
    }

    // Format as YYYY-MM-DD for date inputs
    const formatDate = (d) => d.toISOString().split('T')[0];

    // Format as ISO string for datetime inputs
    const formatDateTime = (d) => d.toISOString();

    // Format for datetime-local (without Z suffix)
    const formatDateTimeLocal = (d) => {
        const isoString = d.toISOString();
        return isoString.slice(0, 16);  // YYYY-MM-DDTHH:mm
    };

    // Set date inputs
    document.getElementById('date-from').value = formatDate(fromDate);
    document.getElementById('date-to').value = formatDate(now);

    // Set datetime inputs (hidden)
    document.getElementById('datetime-from').value = formatDateTime(fromDate);
    document.getElementById('datetime-to').value = formatDateTime(now);

    // Update active state and refresh table
    document.querySelectorAll('.quick-date-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    button.classList.add('active');

    updateActiveFilterCount();
    triggerTableRefresh();
}

// Update clearDateFilter too:
function clearDateFilter() {
    document.getElementById('date-from').value = '';
    document.getElementById('date-to').value = '';
    document.getElementById('datetime-from').value = '';
    document.getElementById('datetime-to').value = '';

    document.querySelectorAll('.quick-date-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    updateActiveFilterCount();
    triggerTableRefresh();
}
```

#### Backend Changes

**Good news**: No changes needed! The backend already supports `datetime_from` and `datetime_to`:

```python
# In frontend/app.py (already there)
datetime_from = request.args.get("datetime_from", "").strip()
datetime_to = request.args.get("datetime_to", "").strip()

# It already checks for 'T' in the value and uses it as-is
if 'T' in effective_from:
    date_filter["$gte"] = effective_from
```

The `datetime-local` input sends values like `2025-11-30T14:30` (without Z), so we might need to add UTC suffix:

```python
# If using datetime-local format (no Z), add it
if effective_from and 'T' in effective_from and 'Z' not in effective_from:
    effective_from += 'Z'
if effective_to and 'T' in effective_to and 'Z' not in effective_to:
    effective_to += 'Z'
```

#### Styling

Add some CSS for the datetime input styling (if needed):

```css
/* In frontend/templates/base.html or style section */
input[type="datetime-local"] {
    padding: 0.5rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.375rem;
    font-family: inherit;
    font-size: 1rem;
}

input[type="datetime-local"]:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}
```

### Testing the Enhancement

#### Manual Testing Checklist

- [ ] Click on datetime-from input, select a date and time (e.g., 2 hours ago)
- [ ] Click on datetime-to input, select a date and time (e.g., now)
- [ ] Verify filter applies correctly
- [ ] Verify quick filters (1h, 3h, 6h, 12h) still work
- [ ] Test with timezone-aware times (cross-day boundaries)
- [ ] Verify mobile responsiveness (datetime-local picker on phone)
- [ ] Test browser compatibility:
  - [ ] Chrome/Chromium
  - [ ] Firefox
  - [ ] Safari
  - [ ] Edge

#### Browser Compatibility Notes

`datetime-local` input is supported in all modern browsers:
- Chrome/Edge 25+
- Firefox 93+
- Safari 14.1+

For older browsers, provide fallback to date+time inputs if needed.

### Deployment Checklist

- [ ] Bug fix (#12) completed first
- [ ] datetime-local inputs added to filter panel
- [ ] JavaScript updated to populate datetime inputs
- [ ] Backend timezone handling verified
- [ ] Manual testing completed
- [ ] All quick filters and manual datetime range tested
- [ ] No regression on existing filters
- [ ] Mobile responsive on various devices
- [ ] Commit: `feat(filters): Add hour/minute selection to date range filter`

---

## Complete Implementation Sequence

### Phase 1: Bug Investigation & Fix (2-3 hours)

1. Run investigation steps 1-4 (1 hour)
2. Document root cause
3. Implement fix based on findings (45 min - 1 hour)
4. Add unit tests (30-45 min)
5. Test with real data and verify fix works

### Phase 2: Enhancement Implementation (1.5-2 hours)

1. Update UI: Add datetime-local inputs (15 min)
2. Update JavaScript: Handle datetime inputs (15 min)
3. Update backend: Ensure UTC handling (10 min)
4. Add styling and responsive design (15 min)
5. Manual testing across browsers (30-45 min)

### Phase 3: Cleanup & Deployment (15-30 min)

1. Remove debug logging
2. Final testing
3. Create pull request with clear commit messages
4. Deploy to production

---

## File Reference

### Core Files
- `frontend/templates/index.html` - Quick filter buttons, filter panel, JavaScript
  - Lines 70-75: Hour filter buttons
  - Lines 175-188: Date filter input section (modify for datetime)
  - Lines 496-536: `setQuickDateFilter()` function
  - Lines 302-450: Filter panel HTML

- `frontend/app.py` - Backend filtering logic
  - Lines 306-328: Date range filter construction
  - Lines 273-275: Request parameter extraction

### Test Files
- `tests/unit/test_time_filtering.py` (NEW) - Unit tests for time filtering
- `tests/frontend/test_api.py` - Existing API filter tests (reference)

### Related Documentation
- `bugs.md` - Bug tracking (#12, #13)
- `plans/missing.md` - Implementation gaps
- `reports/sessions/2025-11-30-time-filter-bug-investigation.md` - Detailed investigation guide

---

## Success Metrics

### Bug Fix
- ✅ 1h filter returns only jobs from past 60 minutes
- ✅ 3h, 6h, 12h filters work with correct hour ranges
- ✅ No regression on date-only filtering
- ✅ Timezone handling is correct across UTC boundaries
- ✅ Unit tests cover datetime filtering scenarios

### Enhancement
- ✅ datetime-local inputs available in filter panel
- ✅ Manual datetime range selection works correctly
- ✅ Integrates seamlessly with quick filters
- ✅ Works in all major browsers
- ✅ Mobile responsive
- ✅ No backend changes required (leverages existing support)

---

## Questions?

Refer to:
1. Investigation guide: `reports/sessions/2025-11-30-time-filter-bug-investigation.md`
2. Code review in codebase (see file references above)
3. Bug tracking: `bugs.md` for current status
4. Implementation gaps: `plans/missing.md` for context

