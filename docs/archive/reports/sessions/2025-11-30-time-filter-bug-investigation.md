# Time-Based Filters Bug Investigation & Enhancement Plan

**Date**: 2025-11-30
**Status**: RESOLVED
**Severity**: HIGH (Bug), MEDIUM (Enhancement)
**Estimated Effort**: 3-5 hours total

---

## RESOLUTION - COMPLETED 2025-12-12

The time-based filter bug has been successfully fixed and verified. The issue was not a data/query problem but rather a missing HTMX configuration.

**Root Cause**: The `#job-table-container` div was missing the `hx-include=".filter-input"` attribute, preventing hidden datetime input values from being sent with HTMX refresh requests.

**Solution Applied**:
1. Added `hx-include=".filter-input"` to job table container in `frontend/templates/index.html`
2. Ensured `frontend/templates/partials/job_rows.html` properly includes `datetime_from` and `datetime_to` in filter query params
3. Added `@app.after_request` cache-busting headers to prevent stale responses
4. Verified quick filter buttons (1h, 3h, 6h, 12h) now correctly filter by hour-level precision

**Verification**: All quick filters now work correctly with hour-level precision filtering.

---

## Original Executive Summary

The job list UI has quick filter buttons for time-based filtering (1h, 3h, 6h, 12h) that appeared to be broken. All filters were initially returning jobs from the entire day instead of the specified hour range.

**Code Review Result**: Frontend logic was correctly calculating hour-based datetimes and the backend had proper infrastructure for datetime filtering.

---

## Bug Details

### BUG #12: Time-Based Quick Filters (1h, 3h, 6h, 12h) Not Working

**Reported**: 2025-11-30
**Priority**: HIGH
**Severity**: User-facing feature appears broken

#### Current Behavior

User clicks "Last 1h" button → Expects to see jobs from past hour → Actually sees jobs from entire day

#### Root Cause Candidates

1. **MongoDB Field Type Mismatch** (Most Likely)
   - Frontend sends: ISO string `"2025-11-30T14:30:00.000Z"`
   - MongoDB `createdAt` might be: Unix timestamp, Date object, or different format
   - Result: String comparison fails or returns wrong range

2. **Timezone Mismatch** (Likely)
   - Frontend: Uses browser's local timezone or UTC
   - Database: Uses different timezone
   - Result: Time ranges don't align, filter returns wrong results

3. **Query Execution Issue** (Less Likely)
   - Query construction is correct but not reaching MongoDB
   - Query reaching MongoDB but aggregation pipeline is wrong
   - Index missing on `createdAt` field (performance issue masking as bug)

#### Evidence

**Frontend Code** (frontend/templates/index.html:502-523):
```javascript
function setQuickDateFilter(button, amount, unit) {
    const now = new Date();
    let fromDate = new Date();

    switch (unit) {
        case 'hour':
            // Correctly calculates hour offset
            fromDate.setTime(now.getTime() - (amount * 60 * 60 * 1000));
            break;
    }

    // Formats as ISO string with 'T' component
    const formatDateTime = (d) => d.toISOString();

    // Sets hidden inputs with ISO datetime
    document.getElementById('datetime-from').value = formatDateTime(fromDate);
    document.getElementById('datetime-to').value = formatDateTime(now);

    // Triggers table refresh with HTMX
    triggerTableRefresh();
}
```

**Status**: ✅ Frontend logic appears correct

**Backend Code** (frontend/app.py:306-328):
```python
# Date range filter - prefer datetime inputs for precision
datetime_from = request.args.get("datetime_from", "").strip()
datetime_to = request.args.get("datetime_to", "").strip()

# Use datetime inputs if available, otherwise use date inputs
effective_from = datetime_from if datetime_from else date_from
effective_to = datetime_to if datetime_to else date_to

if effective_from or effective_to:
    date_filter: Dict[str, str] = {}
    if effective_from:
        # If already has time component, use as-is
        if 'T' in effective_from:
            date_filter["$gte"] = effective_from
        else:
            date_filter["$gte"] = f"{effective_from}T00:00:00.000Z"
    if effective_to:
        if 'T' in effective_to:
            date_filter["$lte"] = effective_to
        else:
            date_filter["$lte"] = f"{effective_to}T23:59:59.999Z"
    and_conditions.append({"createdAt": date_filter})
```

**Status**: ✅ Backend logic appears correct

---

## Investigation Steps

### Step 1: Verify MongoDB Field Format

**Question**: What format is `createdAt` stored in MongoDB?

**Methods**:
1. Query MongoDB directly:
```bash
# Connect to MongoDB
mongo mongodb+srv://...

# Check sample document
use job_search
db['level-2'].findOne()

# Look for createdAt field type and value
# Example output:
# { ..., createdAt: ISODate("2025-11-30T14:30:00.000Z"), ... }
# { ..., createdAt: "2025-11-30T14:30:00.000Z", ... }
# { ..., createdAt: 1701349800000, ... }  # Unix timestamp
```

2. Check in application code for where jobs are created:
   - Look for inserts in `frontend/app.py` or runner service
   - Find: `createdAt` assignment

3. Check MongoDB schema documentation if available

**Expected**: All values should be ISODate or ISO string format in UTC

---

### Step 2: Verify Parameter is Sent to Backend

**Question**: Is the frontend actually sending `datetime_from` parameter?

**Methods**:
1. Open browser DevTools → Network tab
2. Click "1h" filter button
3. Look for the HTMX request to `/partials/job-rows`
4. Check Query String Parameters:
   - Should see: `datetime_from=2025-11-30T14:30:00.000Z`
   - Should see: `datetime_to=2025-11-30T15:30:00.000Z`

**Expected**: Both parameters present with ISO datetime format

---

### Step 3: Add Debug Logging to Backend

**Add to** `frontend/app.py` line ~310:

```python
# Date range filter - prefer datetime inputs for precision
datetime_from = request.args.get("datetime_from", "").strip()
datetime_to = request.args.get("datetime_to", "").strip()

# DEBUG: Log filter parameters
logger.info(f"Filter: datetime_from={datetime_from}, datetime_to={datetime_to}")

# Use datetime inputs if available, otherwise use date inputs
effective_from = datetime_from if datetime_from else date_from
effective_to = datetime_to if datetime_to else date_to

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

    # DEBUG: Log final date filter
    logger.info(f"MongoDB date_filter: {date_filter}")

    and_conditions.append({"createdAt": date_filter})

# DEBUG: Log full query
logger.info(f"Full MongoDB query: {mongo_query}")
```

**Expected Logs**:
```
INFO:__main__:Filter: datetime_from=2025-11-30T14:30:00.000Z, datetime_to=2025-11-30T15:30:00.000Z
INFO:__main__:MongoDB date_filter: {'$gte': '2025-11-30T14:30:00.000Z', '$lte': '2025-11-30T15:30:00.000Z'}
INFO:__main__:Full MongoDB query: {'$and': [{'createdAt': {'$gte': '2025-11-30T14:30:00.000Z', '$lte': '2025-11-30T15:30:00.000Z'}}]}
```

---

### Step 4: Test Actual MongoDB Query

**Commands**:

```bash
# Verify current time and 1 hour ago
node -e "
  const now = new Date();
  const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
  console.log('Now:', now.toISOString());
  console.log('1h ago:', oneHourAgo.toISOString());
"

# Output:
# Now: 2025-11-30T15:30:00.000Z
# 1h ago: 2025-11-30T14:30:00.000Z

# Then query MongoDB
use job_search

# Test query directly
db['level-2'].find({
  createdAt: {
    $gte: "2025-11-30T14:30:00.000Z",
    $lte: "2025-11-30T15:30:00.000Z"
  }
}).count()

# Check what this returns - should be < total count for today
# Compare with full day query:
db['level-2'].find({
  createdAt: {
    $gte: "2025-11-30T00:00:00.000Z",
    $lte: "2025-11-30T23:59:59.999Z"
  }
}).count()

# If 1h query returns same count as all-day query, there's a data issue
```

---

### Step 5: Check createdAt Field Type in Sample Documents

**Commands**:

```javascript
// Check field type and values
db['level-2'].findOne({}, {_id: 1, createdAt: 1})

// If createdAt is a Date object, output looks like:
// { _id: ObjectId(...), createdAt: ISODate("2025-11-30T14:30:00.000Z") }

// If createdAt is a string, output looks like:
// { _id: ObjectId(...), createdAt: "2025-11-30T14:30:00.000Z" }

// If createdAt is a timestamp, output looks like:
// { _id: ObjectId(...), createdAt: 1701349800000 }

// Check multiple documents
db['level-2'].find({}, {_id: 1, createdAt: 1}).limit(5)

// Get type information
db['level-2'].aggregate([
  { $limit: 1 },
  { $project: { createdAt: { $type: "$createdAt" } } }
])
```

---

### Step 6: Verify Timezone Consistency

**Question**: Are all timestamps in UTC?

**Methods**:
1. Check backend timestamp creation:
   - Look for: `datetime.utcnow()`, `datetime.now()`, timezone-aware datetime
   - File: `frontend/app.py` (search for `createdAt` assignment)

2. Check frontend timestamp format:
   - JavaScript `new Date().toISOString()` always returns UTC
   - Already verified in Step 1 code review

3. Verify MongoDB storage:
   - ISODate objects in MongoDB are always UTC
   - String format should be explicit: `T14:30:00.000Z` (Z = UTC)

---

## Proposed Fix Workflow

### Phase 1: Investigation (30-45 minutes)

1. ✅ Code review (COMPLETED - shows code is logically correct)
2. Add debug logging and redeploy
3. Test 1h filter and capture logs
4. Query MongoDB directly to verify field type and test query
5. Document findings

### Phase 2: Diagnosis (15-30 minutes)

Based on findings, determine root cause:
- If `createdAt` is Unix timestamp: Need to convert string to timestamp in query
- If `createdAt` is Date object: Query should work, check timezone
- If timezone mismatch: Ensure all timestamps are UTC

### Phase 3: Implementation (1-2 hours)

- Fix identified root cause
- Add unit tests for datetime filtering
- Test with real data
- Document solution

### Phase 4: Enhancement (1-2 hours)

- Implement datetime-local input for manual time selection
- Update filter UI to show hour/minute options
- Test all quick filters and manual datetime range

---

## Success Criteria

### Bug Fix #12
- [x] Root cause identified and documented
- [ ] Fix implemented and tested
- [ ] 1h filter returns jobs from past hour only
- [ ] 3h, 6h, 12h filters work correctly
- [ ] Unit tests added for datetime filtering
- [ ] Works with timezone-aware dates
- [ ] No regression on date-only filtering

### Enhancement #13
- [ ] datetime-local inputs added to filter panel
- [ ] Manual time selection works (hours + minutes)
- [ ] Complements quick filters (both available)
- [ ] Works in all major browsers
- [ ] Mobile responsive
- [ ] No additional backend changes needed

---

## Files to Modify

### For Bug Fix
- `frontend/app.py` - Add debug logging, implement fix
- `frontend/templates/index.html` - Possibly adjust filter logic if needed
- `tests/unit/test_time_filtering.py` (NEW) - Unit tests for datetime filtering

### For Enhancement
- `frontend/templates/index.html` - Add datetime-local input fields (lines 175-188)
- No backend changes needed (already supports datetime_from/datetime_to)

---

## Related Documentation

- **Bug Tracking**: `bugs.md` (#12, #13)
- **Implementation Gap**: `plans/missing.md` (Frontend & API: Time-Based Filtering)
- **Code Reference**:
  - Frontend filter: `frontend/templates/index.html` (lines 70-75, 496-536)
  - Backend filter: `frontend/app.py` (lines 306-328)
  - Time calculation: `frontend/templates/index.html` (lines 502-503)

---

## Next Steps

1. **Immediate**: Run investigation steps 1-6 to identify root cause
2. **Short-term**: Implement fix based on findings
3. **Medium-term**: Implement enhancement for datetime range picker
4. **Long-term**: Consider adding more sophisticated filtering (saved filters, predefined ranges)

---

## Questions for Review

1. When job documents are created, what timezone is used for `createdAt`?
2. Is `createdAt` stored as MongoDB Date object or string?
3. Are there any existing unit tests for datetime filtering?
4. Is there a test database with sample data to verify queries?
5. Has anyone tested the 1h, 3h, 6h, 12h filters recently to confirm they're broken?

