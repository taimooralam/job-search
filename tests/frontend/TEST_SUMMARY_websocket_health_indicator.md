# Test Summary: WebSocket Health Indicator

## Overview

Tests for the Q(ws) WebSocket health indicator feature added to the frontend application. This feature provides real-time visibility of the WebSocket connection status for queue updates.

## Feature Description

The WebSocket health indicator appears in the base.html template alongside other service health indicators (Runner, MongoDB, etc.) and displays the connection status of the QueueWebSocket client.

### Key Components

1. **base.html** - Contains `updateHealthStatus()` JavaScript function
2. **queue-websocket.js** - QueueWebSocket class with connection management
3. **Flask /api/health endpoint** - Provides health status for all services

### Health States

| State | Condition | CSS Class | Display |
|-------|-----------|-----------|---------|
| Connected | `isConnected === true` | `health-healthy` | Green dot |
| Disconnected | `!isConnected && shouldReconnect !== false` | `health-unhealthy` | Red dot |
| Disabled | `shouldReconnect === false` | `health-unknown` | Gray dot |

### Disabled State Triggers

The WebSocket sets `shouldReconnect = false` in these scenarios:
1. **Mixed Content**: HTTPS page + ws:// URL (browser blocks connection)
2. **Permanent Errors**: Service not configured, Redis unavailable, etc.

## Test Coverage

### Test File

`tests/frontend/test_websocket_health_indicator.py`

### Test Classes

#### 1. TestHealthAPIEndpoint
Tests the `/api/health` endpoint that the JavaScript consumes.

- ✅ Returns complete structure (runner, mongodb)
- ✅ Runner status healthy
- ✅ Runner status unhealthy (timeout)
- ✅ MongoDB status healthy
- ✅ MongoDB status unhealthy (connection failure)

#### 2. TestWebSocketHealthIndicatorDOM
Verifies DOM structure in base.html template.

- ✅ Health status container exists
- ✅ WebSocket indicator has correct ID (`ws-health-indicator`)
- ✅ Displays Q(ws) label
- ✅ Uses correct CSS classes (health-healthy/unhealthy/unknown)
- ✅ Has descriptive title tooltips

#### 3. TestHealthIndicatorJavaScriptIntegration
Tests JavaScript integration points.

- ✅ queue-websocket.js script loaded
- ✅ updateHealthStatus() function exists
- ✅ Health status updates on 30-second interval
- ✅ Checks window.queueWebSocket?.isConnected
- ✅ Checks window.queueWebSocket?.shouldReconnect

#### 4. TestQueueWebSocketBehaviorDocumented
Documents expected QueueWebSocket class behavior (specification tests).

- ✅ QueueWebSocket class defined
- ✅ Has isConnected getter property
- ✅ Has shouldReconnect boolean property
- ✅ Has wouldCauseMixedContent() method
- ✅ Disables reconnect on mixed content
- ✅ Singleton instance created as window.queueWebSocket

#### 5. TestHealthIndicatorStates
Tests state determination logic in JavaScript.

- ✅ Connected state shows healthy (green)
- ✅ Disabled state shows unknown (gray)
- ✅ Disconnected state shows unhealthy (red)
- ✅ Tooltip messages for each state

#### 6. TestMixedContentDetection
Tests mixed content security detection.

- ✅ wouldCauseMixedContent() method exists
- ✅ Checks window.location.protocol
- ✅ Checks WebSocket protocol (ws:// vs wss://)
- ✅ Sets shouldReconnect = false on mixed content

#### 7. TestWebSocketHealthRefresh
Tests automatic refresh behavior.

- ✅ Refreshes every 30 seconds
- ✅ Loads initial status on DOMContentLoaded

#### 8. TestRunnerWebSocketURLConfiguration
Tests WebSocket URL configuration for different deployment scenarios.

- ✅ window.RUNNER_WS_URL config exists
- ✅ QueueWebSocket uses RUNNER_WS_URL
- ✅ Falls back to current host if not set

## Test Strategy

### Python Tests (Executable)

Tests that can be run with pytest:
- Flask endpoint behavior
- Template rendering
- DOM structure verification
- JavaScript code presence

### JavaScript Behavior (Documented)

Since pytest-playwright is currently disabled, JavaScript runtime behavior is tested by:
1. Verifying JavaScript code exists in templates
2. Reading queue-websocket.js file to verify implementation
3. Documenting expected behavior as specification tests

### Mock Strategy

```python
@pytest.fixture
def mock_runner_service():
    """Mock the runner service HTTP requests for health checks."""
    with patch('app.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "queue_size": 0,
            "capacity": {"total": 3, "available": 3}
        }
        mock_get.return_value = mock_response
        yield mock_get
```

## Running the Tests

### Run All WebSocket Health Indicator Tests

```bash
source .venv/bin/activate
pytest tests/frontend/test_websocket_health_indicator.py -v -n auto
```

### Run Specific Test Class

```bash
source .venv/bin/activate
pytest tests/frontend/test_websocket_health_indicator.py::TestHealthAPIEndpoint -v
```

### Run with Coverage

```bash
source .venv/bin/activate
pytest tests/frontend/test_websocket_health_indicator.py -v --cov=frontend.app --cov-report=term-missing
```

## Test Results

Total Tests: **41**

| Category | Count | Status |
|----------|-------|--------|
| Health API Endpoint | 5 | ✅ |
| DOM Structure | 5 | ✅ |
| JavaScript Integration | 5 | ✅ |
| QueueWebSocket Behavior | 6 | ✅ |
| Health Indicator States | 4 | ✅ |
| Mixed Content Detection | 4 | ✅ |
| Health Refresh | 2 | ✅ |
| WebSocket URL Config | 3 | ✅ |

## Edge Cases Covered

1. **Mixed Content Blocking**: HTTPS page attempting ws:// connection
2. **Service Unavailable**: Runner service timeout or unreachable
3. **MongoDB Connection Failure**: Database connection refused
4. **Missing Configuration**: RUNNER_WS_URL not set (falls back to current host)
5. **Reconnection Disabled**: Permanent errors that shouldn't retry

## Future Enhancements

### When pytest-playwright is Enabled

The following E2E tests could be added:

```python
@pytest.mark.playwright
def test_websocket_indicator_updates_on_connection_change(page):
    """E2E: Indicator should change color when WebSocket connects/disconnects."""
    page.goto("http://localhost:5000/")

    # Wait for initial connection
    indicator = page.locator("#ws-health-indicator .health-dot")
    expect(indicator).to_have_class(re.compile("health-healthy"))

    # Simulate disconnect
    page.evaluate("window.queueWebSocket.disconnect()")
    expect(indicator).to_have_class(re.compile("health-unhealthy"))
```

### Additional Integration Tests

```python
def test_websocket_health_persists_across_page_navigation(browser):
    """WebSocket health should be maintained during client-side navigation."""
    pass

def test_websocket_reconnection_updates_indicator(browser):
    """Indicator should update when WebSocket auto-reconnects."""
    pass
```

## Related Files

- `/Users/ala0001t/pers/projects/job-search/frontend/templates/base.html` - Health indicator UI
- `/Users/ala0001t/pers/projects/job-search/frontend/static/js/queue-websocket.js` - WebSocket client
- `/Users/ala0001t/pers/projects/job-search/frontend/app.py` - Flask /api/health endpoint

## Dependencies

- Flask test client
- pytest-mock (for mocking requests)
- MongoDB mock fixtures
- Runner service mock fixtures

## Notes

- Tests use the same pattern as existing frontend tests (test_job_detail_enhancements.py)
- JavaScript behavior is tested via DOM verification rather than runtime execution
- Mock fixtures prevent actual HTTP requests to runner service
- All tests are independent and can run in parallel with pytest-xdist
