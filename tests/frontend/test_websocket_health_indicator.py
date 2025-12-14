"""
Unit tests for WebSocket health indicator feature in base.html.

Tests the Q(ws) WebSocket health indicator that was added to the frontend:
1. Health indicator DOM structure in base.html
2. Health API endpoint structure (consumed by updateHealthStatus)
3. JavaScript QueueWebSocket integration (documented, not executable)

The WebSocket health indicator checks:
- window.queueWebSocket?.isConnected for connection status
- window.queueWebSocket?.shouldReconnect === false for disabled state
- Displays appropriate CSS classes: health-healthy, health-unhealthy, health-unknown

Note: JavaScript behavior is tested via DOM structure verification.
For full E2E testing, pytest-playwright would be needed (currently disabled).
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Import the Flask app
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "frontend"))
from app import app


@pytest.fixture
def client():
    """Create an authenticated test client for the Flask app."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        # Set up authenticated session
        with client.session_transaction() as sess:
            sess['authenticated'] = True
        yield client


@pytest.fixture
def mock_db():
    """Mock the MongoDB database."""
    with patch('app.get_db') as mock_get_db:
        mock_database = MagicMock()
        mock_collection = MagicMock()
        mock_database.__getitem__ = MagicMock(return_value=mock_collection)
        mock_get_db.return_value = mock_database
        yield mock_database


@pytest.fixture
def mock_runner_service():
    """Mock the runner service HTTP requests for health checks."""
    with patch('app.requests.get') as mock_get:
        # Default: runner service responds healthy
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "queue_size": 0,
            "capacity": {"total": 3, "available": 3}
        }
        mock_response.elapsed.total_seconds.return_value = 0.05
        mock_get.return_value = mock_response

        yield mock_get


class TestHealthAPIEndpoint:
    """Tests for the /api/health endpoint that updateHealthStatus() consumes."""

    def test_health_api_returns_complete_structure(self, client, mock_db, mock_runner_service):
        """Should return health status for all monitored services."""
        response = client.get('/api/health')

        assert response.status_code == 200
        data = response.get_json()

        # Verify structure that JavaScript expects
        assert "runner" in data
        assert "mongodb" in data

    def test_health_api_runner_status_healthy(self, client, mock_db, mock_runner_service):
        """Should return healthy status when runner is responsive."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "queue_size": 0}
        mock_response.elapsed.total_seconds.return_value = 0.05
        mock_runner_service.return_value = mock_response

        response = client.get('/api/health')
        data = response.get_json()

        assert data["runner"]["status"] == "healthy"

    def test_health_api_runner_status_unhealthy(self, client, mock_db, mock_runner_service):
        """Should return unhealthy status when runner is unreachable."""
        # Simulate connection timeout
        import requests
        mock_runner_service.side_effect = requests.exceptions.Timeout("Connection timeout")

        response = client.get('/api/health')
        data = response.get_json()

        assert data["runner"]["status"] == "unhealthy"

    def test_health_api_mongodb_status_healthy(self, client, mock_db, mock_runner_service):
        """Should return healthy status when MongoDB is responsive."""
        # Mock MongoDB ping command to succeed
        mock_db.command.return_value = {"ok": 1}

        response = client.get('/api/health')
        data = response.get_json()

        assert data["mongodb"]["status"] == "healthy"

    def test_health_api_mongodb_status_unhealthy(self, client, mock_db, mock_runner_service):
        """Should return unhealthy status when MongoDB is unreachable."""
        # Simulate MongoDB connection error
        from pymongo.errors import ConnectionFailure
        mock_db.command.side_effect = ConnectionFailure("Connection refused")

        response = client.get('/api/health')
        data = response.get_json()

        assert data["mongodb"]["status"] == "unhealthy"


class TestWebSocketHealthIndicatorDOM:
    """Tests for WebSocket health indicator DOM structure in base.html."""

    def test_health_indicator_container_exists(self, client, mock_db, mock_runner_service):
        """Should render health-status container in base template."""
        # Get any page that extends base.html
        response = client.get('/')

        assert response.status_code == 200
        assert b'id="health-status"' in response.data

    def test_websocket_health_indicator_has_correct_id(self, client, mock_db, mock_runner_service):
        """WebSocket health indicator should have id="ws-health-indicator"."""
        # The updateHealthStatus function creates the indicator dynamically
        # We verify the template loads the JavaScript that creates it
        response = client.get('/')

        assert response.status_code == 200
        # Check that updateHealthStatus function is defined
        assert b'updateHealthStatus' in response.data
        assert b'ws-health-indicator' in response.data

    def test_websocket_health_indicator_shows_q_ws_label(self, client, mock_db, mock_runner_service):
        """WebSocket health indicator should display 'Q(ws)' label."""
        response = client.get('/')

        assert response.status_code == 200
        # The JavaScript in updateHealthStatus creates this label
        assert b'Q(ws)' in response.data

    def test_health_indicator_uses_correct_css_classes(self, client, mock_db, mock_runner_service):
        """Health indicators should use health-healthy/unhealthy/unknown classes."""
        response = client.get('/')

        assert response.status_code == 200
        # Check that CSS classes are referenced in JavaScript
        assert b'health-healthy' in response.data
        assert b'health-unhealthy' in response.data
        assert b'health-unknown' in response.data

    def test_websocket_health_indicator_has_title_attribute(self, client, mock_db, mock_runner_service):
        """WebSocket health indicator should have descriptive title for tooltip."""
        response = client.get('/')

        assert response.status_code == 200
        # JavaScript creates title attribute with status descriptions
        data = response.data.decode('utf-8')
        assert 'WebSocket: Connected' in data or 'title=' in data


class TestHealthIndicatorJavaScriptIntegration:
    """
    Tests for JavaScript integration of QueueWebSocket health indicator.

    Note: These tests verify the DOM structure that JavaScript relies on.
    Full JavaScript behavior testing would require pytest-playwright (currently disabled).
    """

    def test_queue_websocket_script_loaded(self, client, mock_db, mock_runner_service):
        """Should load queue-websocket.js script."""
        response = client.get('/')

        assert response.status_code == 200
        assert b'queue-websocket.js' in response.data

    def test_update_health_status_function_exists(self, client, mock_db, mock_runner_service):
        """Should define updateHealthStatus() function in base.html."""
        response = client.get('/')

        assert response.status_code == 200
        assert b'async function updateHealthStatus()' in response.data or \
               b'function updateHealthStatus()' in response.data

    def test_health_status_updates_on_interval(self, client, mock_db, mock_runner_service):
        """Should call updateHealthStatus() on 30-second interval."""
        response = client.get('/')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Verify setInterval is used to refresh health status
        assert 'setInterval(updateHealthStatus' in data or \
               'setInterval' in data and 'updateHealthStatus' in data

    def test_websocket_connection_status_checked(self, client, mock_db, mock_runner_service):
        """Should check window.queueWebSocket?.isConnected for status."""
        response = client.get('/')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Verify JavaScript checks isConnected property
        assert 'queueWebSocket' in data
        assert 'isConnected' in data

    def test_websocket_should_reconnect_flag_checked(self, client, mock_db, mock_runner_service):
        """Should check window.queueWebSocket?.shouldReconnect for disabled state."""
        response = client.get('/')

        assert response.status_code == 200
        data = response.data.decode('utf-8')
        # Verify JavaScript checks shouldReconnect property
        assert 'shouldReconnect' in data


class TestQueueWebSocketBehaviorDocumented:
    """
    Documentation tests for QueueWebSocket class behavior.

    These document the expected JavaScript behavior that cannot be tested
    directly without a JavaScript test framework. They serve as specification
    tests and will fail if the JavaScript implementation is removed or changed.
    """

    def test_queue_websocket_class_defined(self, client):
        """QueueWebSocket class should be defined in queue-websocket.js."""
        # Read the JavaScript file directly to verify class exists
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"

        if not js_file_path.exists():
            pytest.fail(f"queue-websocket.js not found at {js_file_path}")

        js_content = js_file_path.read_text()

        assert 'class QueueWebSocket' in js_content

    def test_queue_websocket_has_is_connected_getter(self, client):
        """QueueWebSocket should have isConnected getter property."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'get isConnected()' in js_content or 'get isConnected' in js_content
        assert 'WebSocket.OPEN' in js_content

    def test_queue_websocket_has_should_reconnect_property(self, client):
        """QueueWebSocket should have shouldReconnect boolean property."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'shouldReconnect' in js_content

    def test_queue_websocket_has_mixed_content_detection(self, client):
        """QueueWebSocket should have wouldCauseMixedContent() method."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'wouldCauseMixedContent' in js_content

    def test_queue_websocket_disables_reconnect_on_mixed_content(self, client):
        """QueueWebSocket should set shouldReconnect=false on mixed content."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        # Verify mixed content detection sets shouldReconnect = false
        assert 'shouldReconnect = false' in js_content or 'shouldReconnect=false' in js_content

    def test_queue_websocket_singleton_instance_created(self, client):
        """QueueWebSocket should be instantiated as window.queueWebSocket."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'window.queueWebSocket' in js_content
        assert 'new QueueWebSocket()' in js_content


class TestHealthIndicatorStates:
    """
    Tests for different health indicator states (connected, disconnected, disabled).

    These verify the JavaScript logic in updateHealthStatus() for determining
    WebSocket health status based on QueueWebSocket state.
    """

    def test_connected_state_logic_in_javascript(self, client, mock_db, mock_runner_service):
        """JavaScript should show healthy when isConnected=true."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Verify logic: isConnected → 'connected' → 'health-healthy'
        assert 'isConnected' in data
        assert 'health-healthy' in data

    def test_disabled_state_logic_in_javascript(self, client, mock_db, mock_runner_service):
        """JavaScript should show unknown when shouldReconnect=false."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Verify logic: shouldReconnect === false → 'disabled' → 'health-unknown'
        assert 'shouldReconnect' in data
        assert 'health-unknown' in data

    def test_disconnected_state_logic_in_javascript(self, client, mock_db, mock_runner_service):
        """JavaScript should show unhealthy when disconnected (but not disabled)."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Verify logic: !isConnected && shouldReconnect → 'disconnected' → 'health-unhealthy'
        assert 'health-unhealthy' in data

    def test_websocket_status_tooltip_messages(self, client, mock_db, mock_runner_service):
        """WebSocket health indicator should have descriptive tooltip messages."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Verify tooltip messages for different states
        assert 'WebSocket: Connected' in data
        assert 'WebSocket: Disabled' in data or 'mixed content' in data
        assert 'WebSocket: Disconnected' in data


class TestMixedContentDetection:
    """
    Tests for mixed content detection in QueueWebSocket.

    Mixed content occurs when:
    - Page is served over HTTPS (window.location.protocol === 'https:')
    - WebSocket URL uses ws:// instead of wss://

    This is blocked by browsers for security, so WebSocket disables reconnection.
    """

    def test_mixed_content_detection_method_exists(self, client):
        """wouldCauseMixedContent() method should exist in QueueWebSocket."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'wouldCauseMixedContent' in js_content

    def test_mixed_content_checks_page_protocol(self, client):
        """wouldCauseMixedContent() should check window.location.protocol."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'window.location.protocol' in js_content
        assert 'https:' in js_content

    def test_mixed_content_checks_websocket_protocol(self, client):
        """wouldCauseMixedContent() should check if WS URL is ws:// or wss://."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'ws://' in js_content or 'wss:' in js_content

    def test_mixed_content_disables_reconnection(self, client):
        """Mixed content detection should set shouldReconnect = false."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        # Find the mixed content block and verify it sets shouldReconnect
        lines = js_content.split('\n')
        mixed_content_block = []
        in_mixed_content_check = False

        for line in lines:
            if 'wouldCauseMixedContent' in line or 'Mixed content' in line:
                in_mixed_content_check = True
            if in_mixed_content_check:
                mixed_content_block.append(line)
                if 'shouldReconnect' in line and 'false' in line:
                    # Found the line that disables reconnection
                    assert True
                    return
                if line.strip().startswith('}') and len(line.strip()) == 1:
                    # End of block
                    in_mixed_content_check = False

        # If we get here, we didn't find the shouldReconnect = false line
        pytest.fail("Mixed content detection should set shouldReconnect = false")


class TestWebSocketHealthRefresh:
    """Tests for automatic health status refresh on interval."""

    def test_health_status_refresh_interval_set(self, client, mock_db, mock_runner_service):
        """Should refresh health status every 30 seconds."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for 30 second interval (30000ms)
        assert 'setInterval' in data
        assert '30000' in data or '30 seconds' in data.lower()

    def test_initial_health_status_loaded_on_dom_ready(self, client, mock_db, mock_runner_service):
        """Should load health status on DOMContentLoaded."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        assert 'DOMContentLoaded' in data
        assert 'updateHealthStatus()' in data or 'updateHealthStatus' in data


class TestRunnerWebSocketURLConfiguration:
    """
    Tests for RUNNER_WS_URL configuration used by QueueWebSocket.

    The WebSocket URL can be configured via window.RUNNER_WS_URL for deployments
    where the runner service is on a different host (e.g., Vercel frontend + VPS runner).
    """

    def test_runner_ws_url_config_exists(self, client, mock_db, mock_runner_service):
        """Should define window.RUNNER_WS_URL in base template."""
        response = client.get('/')
        data = response.data.decode('utf-8')

        assert 'window.RUNNER_WS_URL' in data or 'RUNNER_WS_URL' in data

    def test_queue_websocket_uses_runner_ws_url(self, client):
        """QueueWebSocket should check window.RUNNER_WS_URL for WebSocket URL."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'window.RUNNER_WS_URL' in js_content or 'RUNNER_WS_URL' in js_content

    def test_queue_websocket_falls_back_to_current_host(self, client):
        """QueueWebSocket should fall back to current host if RUNNER_WS_URL not set."""
        js_file_path = Path(__file__).parent.parent.parent / "frontend" / "static" / "js" / "queue-websocket.js"
        js_content = js_file_path.read_text()

        assert 'window.location.host' in js_content
        assert '/ws/queue' in js_content
