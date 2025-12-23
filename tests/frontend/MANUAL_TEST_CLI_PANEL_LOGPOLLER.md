# Manual Testing Guide: CLI Panel LogPoller Fix

## Overview

This document provides manual testing procedures to verify the CLI Panel LogPoller subscription fix works correctly in a browser environment.

## Background

**Issue Fixed:** LogPoller subscriptions were missed when operations started with the CLI panel collapsed, or during batch operations across page refreshes.

**Fix Applied:**
1. `startRun()` now ALWAYS calls `subscribeToLogs()` immediately (regardless of panel state)
2. `toggle()` and `showPanel()` now subscribe ALL running operations (not just `activeRunId`)

## Prerequisites

- Runner service must be running (`python -m runner.app`)
- Frontend service must be running (`python frontend/app.py`)
- At least one job in MongoDB `level-2` collection
- Browser DevTools open to Console tab

## Test Scenarios

### Scenario 1: Operation Started with Panel Collapsed

**Objective:** Verify logs are captured even when panel is collapsed

**Steps:**
1. Open job listing page (`http://localhost:5001/jobs`)
2. Ensure CLI panel is **collapsed** (Ctrl+` to toggle if needed)
3. Click "Process" button on any job
4. Wait 5 seconds (let operation run)
5. Open CLI panel (Ctrl+`)

**Expected Result:**
- Panel should show the running operation tab
- Logs should be visible immediately (not empty)
- Logs should show activity from when operation started (not just from when panel opened)

**Pass/Fail Criteria:**
- PASS: Logs present showing full operation history
- FAIL: Empty log panel or only logs after opening panel

---

### Scenario 2: Batch Operations Across Page Refresh

**Objective:** Verify polling resumes after page refresh during batch operations

**Setup:**
1. Navigate to Batch Operations page
2. Select multiple jobs (3-5 jobs)
3. Start batch processing

**Steps:**
1. Wait for 2-3 operations to complete
2. While operations are still running, refresh the page (F5)
3. Wait 3-5 seconds
4. Open CLI panel (if collapsed)

**Expected Result:**
- Running operations should appear as tabs
- Each tab should show "Polling active" indicator (if implemented)
- Logs should resume streaming for all running operations
- No "Logs unavailable" messages

**Pass/Fail Criteria:**
- PASS: All running operations resume polling and show live logs
- FAIL: Any operation shows "Logs unavailable" or empty log stream

---

### Scenario 3: Panel Toggle During Active Operations

**Objective:** Verify toggling panel subscribes all running operations

**Steps:**
1. Start 2-3 separate pipeline operations (use different jobs)
2. Keep CLI panel open and verify logs are streaming
3. Collapse panel (Ctrl+`)
4. Wait 5 seconds
5. Expand panel (Ctrl+`)
6. Switch between operation tabs

**Expected Result:**
- All operation tabs should show recent logs
- No gaps in log timestamps
- Each tab shows activity during the time panel was collapsed

**Pass/Fail Criteria:**
- PASS: All operations have continuous log streams
- FAIL: Any operation missing logs or shows gaps

---

### Scenario 4: Direct showPanel() Call

**Objective:** Verify `showPanel()` subscribes all running operations

**Steps:**
1. Start 2-3 pipeline operations
2. Collapse CLI panel
3. Open browser console (F12)
4. Run: `Alpine.store('cli').showPanel()`
5. Switch between operation tabs

**Expected Result:**
- Panel should expand
- All running operations should show in tabs
- All operations should have active log streams
- Logs should be up-to-date

**Pass/Fail Criteria:**
- PASS: All operations polling and showing current logs
- FAIL: Any operation not polling or showing stale logs

---

### Scenario 5: Page Navigation During Operation

**Objective:** Verify polling persists across page navigation

**Steps:**
1. Start pipeline operation from job detail page
2. CLI panel should open with logs streaming
3. Navigate to another page (e.g., `/jobs` listing)
4. Wait 5 seconds
5. Check CLI panel

**Expected Result:**
- CLI panel should persist across navigation (sessionStorage)
- Operation should still be in "running" state
- Logs should continue streaming
- No interruption in polling

**Pass/Fail Criteria:**
- PASS: Logs continue streaming after navigation
- FAIL: Polling stops or logs freeze

---

### Scenario 6: Multiple Tabs Same Operation

**Objective:** Verify no duplicate subscriptions created

**Steps:**
1. Start a pipeline operation
2. Open browser console
3. Run: `Alpine.store('cli').runs`
4. Look for `_logPoller` property on your run
5. Run: `Alpine.store('cli').toggle()` (collapse)
6. Run: `Alpine.store('cli').toggle()` (expand)
7. Check `_logPoller` again

**Expected Result:**
- Only ONE `_logPoller` instance per run
- No duplicate LogPoller instances created
- Console should show "Already subscribed to logs" debug message

**Pass/Fail Criteria:**
- PASS: No duplicate pollers, single subscription maintained
- FAIL: Multiple `_logPoller` instances or duplicate subscriptions

---

## Console Debug Commands

Enable debug mode:
```javascript
localStorage.setItem('cli_debug', 'true');
location.reload();
```

Check CLI state:
```javascript
Alpine.store('cli').debugState()
```

Check if LogPoller is active:
```javascript
Alpine.store('cli').runs['<runId>']._logPoller
```

List all running operations:
```javascript
Object.entries(Alpine.store('cli').runs).filter(([id, run]) => run.status === 'running')
```

Force subscribe to logs:
```javascript
Alpine.store('cli').subscribeToLogs('<runId>')
```

---

## Common Issues & Debugging

### Issue: "Logs unavailable" message

**Cause:** Operation completed before LogPoller started, or runner service restarted

**Fix:** This is expected behavior. Start a new operation to test.

---

### Issue: Logs stop streaming mid-operation

**Check:**
1. Runner service still running: `curl http://localhost:5002/api/runner/operations/<runId>/status`
2. LogPoller instance exists: `Alpine.store('cli').runs['<runId>']._logPoller`
3. Console errors for fetch() failures

**Likely Cause:** Network error or runner service crash

---

### Issue: Panel shows wrong operation

**Check:**
1. Current `activeRunId`: `Alpine.store('cli').activeRunId`
2. Run order: `Alpine.store('cli').runOrder`
3. Manually switch: `Alpine.store('cli').switchToRun('<runId>')`

---

## Automated Test Coverage

Automated tests verify the JavaScript code structure:
- `tests/frontend/test_cli_panel_logpoller_fix.py`
- 24 tests covering all subscription logic
- Run: `pytest tests/frontend/test_cli_panel_logpoller_fix.py -v`

**Note:** Automated tests verify code presence, not runtime behavior. Manual tests verify actual browser execution.

---

## Success Criteria Summary

The fix is working correctly if:

1. Operations started with panel collapsed still capture logs
2. Batch operations resume polling after page refresh
3. Toggling panel subscribes all running operations
4. `showPanel()` subscribes all running operations
5. No duplicate subscriptions are created
6. Logs stream continuously without gaps

If ANY scenario fails, the LogPoller subscription logic needs review.
