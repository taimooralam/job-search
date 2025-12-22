"""
Unit tests for QueuePoller and LogPoller 502/503 error handling

Tests the implementation of friendly error handling for service unavailability:
1. 502/503 HTTP errors trigger service unavailable handling
2. Network/CORS errors are treated as service unavailable
3. Exponential backoff with max 30s delay
4. Toast messages shown only once (with 5s cooldown to prevent duplicates)
5. Shared state between QueuePoller and LogPoller prevents duplicate toasts
6. Service restored notification when connection is back

Background:
During deployment restarts, the runner service returns 502 errors (from Traefik).
These show up as confusing CORS errors in the browser console. This fix adds
user-friendly toast messages and proper backoff.
"""

import pytest
from pathlib import Path


class TestQueuePollerServiceUnavailable:
    """Tests for QueuePoller 502/503 error handling."""

    @pytest.fixture
    def queue_poller_js(self):
        """Load QueuePoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/queue-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    def test_has_service_unavailable_backoff_config(self, queue_poller_js):
        """QueuePoller should have dedicated backoff config for service unavailability."""
        assert '_serviceUnavailableBackoff = 1000' in queue_poller_js, \
            "Should have initial service unavailable backoff of 1000ms"
        assert '_maxServiceUnavailableBackoff = 30000' in queue_poller_js, \
            "Should have max service unavailable backoff of 30000ms (30s)"
        assert '_isServiceUnavailable = false' in queue_poller_js, \
            "Should track service unavailable state"

    def test_handles_502_status(self, queue_poller_js):
        """QueuePoller should handle 502 status code specially."""
        assert 'response.status === 502' in queue_poller_js, \
            "Should check for 502 status"
        assert '502' in queue_poller_js and '_handleServiceUnavailable' in queue_poller_js, \
            "Should call _handleServiceUnavailable for 502"

    def test_handles_503_status(self, queue_poller_js):
        """QueuePoller should handle 503 status code specially."""
        assert 'response.status === 503' in queue_poller_js, \
            "Should check for 503 status"

    def test_has_handle_service_unavailable_method(self, queue_poller_js):
        """QueuePoller should have _handleServiceUnavailable method."""
        assert '_handleServiceUnavailable(reason)' in queue_poller_js, \
            "Should have _handleServiceUnavailable method"

    def test_handle_service_unavailable_shows_toast(self, queue_poller_js):
        """_handleServiceUnavailable should show user-friendly toast."""
        # Find the method
        method_start = queue_poller_js.find('_handleServiceUnavailable(reason)')
        assert method_start > 0, "_handleServiceUnavailable method not found"

        method_end = queue_poller_js.find('\n        /**', method_start + 1)
        method_section = queue_poller_js[method_start:method_end]

        assert "showToast" in method_section, \
            "Should call showToast in _handleServiceUnavailable"
        assert "restarting" in method_section.lower() or "wait" in method_section.lower(), \
            "Toast message should be user-friendly"

    def test_handle_service_unavailable_applies_exponential_backoff(self, queue_poller_js):
        """_handleServiceUnavailable should apply exponential backoff."""
        method_start = queue_poller_js.find('_handleServiceUnavailable(reason)')
        method_end = queue_poller_js.find('\n        /**', method_start + 1)
        method_section = queue_poller_js[method_start:method_end]

        assert '_serviceUnavailableBackoff * 2' in method_section, \
            "Should double backoff on each retry"
        assert '_maxServiceUnavailableBackoff' in method_section, \
            "Should respect max backoff limit"

    def test_has_handle_service_restored_method(self, queue_poller_js):
        """QueuePoller should have _handleServiceRestored method."""
        assert '_handleServiceRestored()' in queue_poller_js, \
            "Should have _handleServiceRestored method"

    def test_handle_service_restored_resets_backoff(self, queue_poller_js):
        """_handleServiceRestored should reset backoff when service is back."""
        # Find the method definition, not a call
        method_start = queue_poller_js.find('_handleServiceRestored() {')
        assert method_start > 0, "_handleServiceRestored method definition not found"
        method_end = queue_poller_js.find('\n        }', method_start + 50)
        method_section = queue_poller_js[method_start:method_end + 10]

        assert 'this._serviceUnavailableBackoff = 1000' in method_section, \
            "Should reset backoff to initial value"
        assert 'this._isServiceUnavailable = false' in method_section, \
            "Should reset service unavailable flag"

    def test_handle_service_restored_shows_success_toast(self, queue_poller_js):
        """_handleServiceRestored should show success toast."""
        # Find the method definition
        method_start = queue_poller_js.find('_handleServiceRestored() {')
        assert method_start > 0, "_handleServiceRestored method definition not found"
        # Find the end by looking for the next method or closing brace pattern
        method_end = queue_poller_js.find('\n        /**', method_start + 50)
        if method_end < 0:
            method_end = method_start + 1500
        method_section = queue_poller_js[method_start:method_end]

        assert "showToast" in method_section, \
            "Should call showToast when service is restored"
        assert "reconnected" in method_section.lower() or "restored" in method_section.lower(), \
            "Toast message should indicate service is back"

    def test_has_is_network_or_cors_error_method(self, queue_poller_js):
        """QueuePoller should have method to detect network/CORS errors."""
        assert '_isNetworkOrCorsError(error)' in queue_poller_js, \
            "Should have _isNetworkOrCorsError method"

    def test_network_error_detection(self, queue_poller_js):
        """_isNetworkOrCorsError should detect various network error patterns."""
        # Find the method definition (with opening brace)
        method_start = queue_poller_js.find('_isNetworkOrCorsError(error) {')
        assert method_start > 0, "_isNetworkOrCorsError method definition not found"
        # Find the next method
        method_end = queue_poller_js.find('\n        /**', method_start + 50)
        if method_end < 0:
            method_end = method_start + 800
        method_section = queue_poller_js[method_start:method_end]

        assert 'TypeError' in method_section, \
            "Should check for TypeError (common for fetch failures)"
        assert 'failed to fetch' in method_section.lower(), \
            "Should check for 'failed to fetch' message"
        assert 'network' in method_section.lower(), \
            "Should check for 'network' in error message"
        assert 'cors' in method_section.lower(), \
            "Should check for 'cors' in error message"

    def test_fetch_state_handles_network_errors_as_service_unavailable(self, queue_poller_js):
        """_fetchState should treat network errors as service unavailable."""
        # Find the _fetchState method definition
        fetch_start = queue_poller_js.find('async _fetchState() {')
        assert fetch_start > 0, "_fetchState method definition not found"
        # Find the next method (look for the closing pattern)
        method_end = queue_poller_js.find('_isNetworkOrCorsError(error) {', fetch_start + 1)
        if method_end < 0:
            method_end = fetch_start + 3000
        fetch_section = queue_poller_js[fetch_start:method_end]

        assert '_isNetworkOrCorsError(error)' in fetch_section or 'this._isNetworkOrCorsError(error)' in fetch_section, \
            "Should check if error is network/CORS error"
        assert '_handleServiceUnavailable' in fetch_section, \
            "Should call _handleServiceUnavailable for network errors"

    def test_get_backoff_interval_uses_service_unavailable_backoff(self, queue_poller_js):
        """_getBackoffInterval should use service unavailable backoff when applicable."""
        # Find the method definition
        method_start = queue_poller_js.find('_getBackoffInterval() {')
        assert method_start > 0, "_getBackoffInterval method definition not found"
        method_end = queue_poller_js.find('async _fetchState', method_start + 1)
        if method_end < 0:
            method_end = method_start + 800
        method_section = queue_poller_js[method_start:method_end]

        assert '_isServiceUnavailable' in method_section or 'this._isServiceUnavailable' in method_section, \
            "Should check service unavailable state"
        assert '_serviceUnavailableBackoff' in method_section or 'this._serviceUnavailableBackoff' in method_section, \
            "Should return service unavailable backoff when appropriate"


class TestLogPollerServiceUnavailable:
    """Tests for LogPoller 502/503 error handling."""

    @pytest.fixture
    def log_poller_js(self):
        """Load LogPoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/log-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    def test_has_service_unavailable_backoff_config(self, log_poller_js):
        """LogPoller should have dedicated backoff config for service unavailability."""
        assert '_serviceUnavailableBackoff = 1000' in log_poller_js, \
            "Should have initial service unavailable backoff of 1000ms"
        assert '_maxServiceUnavailableBackoff = 30000' in log_poller_js, \
            "Should have max service unavailable backoff of 30000ms (30s)"
        assert '_isServiceUnavailable = false' in log_poller_js, \
            "Should track service unavailable state"

    def test_handles_502_status(self, log_poller_js):
        """LogPoller should handle 502 status code specially."""
        assert 'response.status === 502' in log_poller_js, \
            "Should check for 502 status"

    def test_handles_503_status(self, log_poller_js):
        """LogPoller should handle 503 status code specially."""
        assert 'response.status === 503' in log_poller_js, \
            "Should check for 503 status"

    def test_has_handle_service_unavailable_method(self, log_poller_js):
        """LogPoller should have _handleServiceUnavailable method."""
        assert '_handleServiceUnavailable(reason)' in log_poller_js, \
            "Should have _handleServiceUnavailable method"

    def test_has_handle_service_restored_method(self, log_poller_js):
        """LogPoller should have _handleServiceRestored method."""
        assert '_handleServiceRestored()' in log_poller_js, \
            "Should have _handleServiceRestored method"

    def test_has_is_network_or_cors_error_method(self, log_poller_js):
        """LogPoller should have method to detect network/CORS errors."""
        assert '_isNetworkOrCorsError(error)' in log_poller_js, \
            "Should have _isNetworkOrCorsError method"

    def test_fetch_logs_calls_service_unavailable_for_502(self, log_poller_js):
        """_fetchLogs should call _handleServiceUnavailable for 502 errors."""
        # Find the method definition
        fetch_start = log_poller_js.find('async _fetchLogs() {')
        assert fetch_start > 0, "_fetchLogs method definition not found"
        # Find the next method
        method_end = log_poller_js.find('_isNetworkOrCorsError(error) {', fetch_start + 1)
        if method_end < 0:
            method_end = fetch_start + 3000
        fetch_section = log_poller_js[fetch_start:method_end]

        assert '502' in fetch_section and '_handleServiceUnavailable' in fetch_section, \
            "Should call _handleServiceUnavailable for 502"

    def test_get_backoff_interval_uses_service_unavailable_backoff(self, log_poller_js):
        """_getBackoffInterval should use service unavailable backoff when applicable."""
        # Find the method definition
        method_start = log_poller_js.find('_getBackoffInterval() {')
        assert method_start > 0, "_getBackoffInterval method definition not found"
        method_end = log_poller_js.find('async _fetchLogs', method_start + 1)
        if method_end < 0:
            method_end = method_start + 800
        method_section = log_poller_js[method_start:method_end]

        assert '_isServiceUnavailable' in method_section or 'this._isServiceUnavailable' in method_section, \
            "Should check service unavailable state"
        assert '_serviceUnavailableBackoff' in method_section or 'this._serviceUnavailableBackoff' in method_section, \
            "Should return service unavailable backoff when appropriate"


class TestSharedServiceStatus:
    """Tests for shared service status between pollers."""

    @pytest.fixture
    def queue_poller_js(self):
        """Load QueuePoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/queue-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    @pytest.fixture
    def log_poller_js(self):
        """Load LogPoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/log-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    def test_queue_poller_creates_shared_state(self, queue_poller_js):
        """QueuePoller should initialize shared service status object."""
        assert '_pollerServiceStatus' in queue_poller_js, \
            "Should reference shared service status object"
        assert 'global._pollerServiceStatus = {' in queue_poller_js, \
            "Should initialize shared service status"
        assert 'isUnavailable: false' in queue_poller_js, \
            "Shared state should have isUnavailable flag"
        assert 'lastToastTime: 0' in queue_poller_js, \
            "Shared state should track last toast time"
        assert 'toastCooldownMs: 5000' in queue_poller_js, \
            "Shared state should have 5s cooldown"

    def test_log_poller_uses_shared_state(self, log_poller_js):
        """LogPoller should use shared service status object."""
        assert '_pollerServiceStatus' in log_poller_js, \
            "Should reference shared service status object"
        # Should check if already exists (in case QueuePoller initialized it)
        assert 'if (!global._pollerServiceStatus)' in log_poller_js, \
            "Should check if shared state exists before creating"

    def test_shared_state_prevents_duplicate_toasts(self, queue_poller_js):
        """Shared state should prevent duplicate toasts within cooldown period."""
        # Find the method definition
        method_start = queue_poller_js.find('_handleServiceUnavailable(reason) {')
        assert method_start > 0, "_handleServiceUnavailable method definition not found"
        method_end = queue_poller_js.find('_handleServiceRestored', method_start + 1)
        if method_end < 0:
            method_end = method_start + 1500
        method_section = queue_poller_js[method_start:method_end]

        assert 'lastToastTime' in method_section, \
            "Should check last toast time"
        assert 'toastCooldownMs' in method_section, \
            "Should respect toast cooldown"

    def test_handle_service_unavailable_updates_shared_state(self, queue_poller_js):
        """_handleServiceUnavailable should update shared state."""
        # Find the method definition
        method_start = queue_poller_js.find('_handleServiceUnavailable(reason) {')
        assert method_start > 0, "_handleServiceUnavailable method definition not found"
        method_end = queue_poller_js.find('_handleServiceRestored', method_start + 1)
        if method_end < 0:
            method_end = method_start + 1500
        method_section = queue_poller_js[method_start:method_end]

        assert 'global._pollerServiceStatus.isUnavailable = true' in method_section, \
            "Should set shared isUnavailable flag"
        assert 'global._pollerServiceStatus.lastToastTime' in method_section, \
            "Should update last toast time"

    def test_handle_service_restored_resets_shared_state(self, queue_poller_js):
        """_handleServiceRestored should reset shared state."""
        # Find the method definition
        method_start = queue_poller_js.find('_handleServiceRestored() {')
        assert method_start > 0, "_handleServiceRestored method definition not found"
        method_end = queue_poller_js.find('\n        /**', method_start + 50)
        if method_end < 0:
            method_end = method_start + 1500
        method_section = queue_poller_js[method_start:method_end]

        assert 'global._pollerServiceStatus.isUnavailable = false' in method_section, \
            "Should reset shared isUnavailable flag"


class TestOnServiceStatusCallback:
    """Tests for the onServiceStatus callback registration."""

    @pytest.fixture
    def queue_poller_js(self):
        """Load QueuePoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/queue-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    @pytest.fixture
    def log_poller_js(self):
        """Load LogPoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/log-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    def test_queue_poller_has_on_service_status_callback(self, queue_poller_js):
        """QueuePoller should have onServiceStatus callback registration."""
        assert '_onServiceStatusCallbacks = []' in queue_poller_js, \
            "Should have _onServiceStatusCallbacks array"
        assert 'onServiceStatus(callback)' in queue_poller_js, \
            "Should have onServiceStatus method"

    def test_log_poller_has_on_service_status_callback(self, log_poller_js):
        """LogPoller should have onServiceStatus callback registration."""
        assert '_onServiceStatusCallbacks = []' in log_poller_js, \
            "Should have _onServiceStatusCallbacks array"
        assert 'onServiceStatus(callback)' in log_poller_js, \
            "Should have onServiceStatus method"

    def test_queue_poller_notifies_service_status_listeners(self, queue_poller_js):
        """QueuePoller should notify service status listeners."""
        assert '_notifyServiceStatus(' in queue_poller_js, \
            "Should have _notifyServiceStatus method"

        # Find the method definition
        method_start = queue_poller_js.find('_notifyServiceStatus(isUnavailable, message) {')
        assert method_start > 0, "_notifyServiceStatus method definition not found"
        method_end = queue_poller_js.find('\n        /**', method_start + 50)
        if method_end < 0:
            method_end = method_start + 500
        method_section = queue_poller_js[method_start:method_end]

        assert '_onServiceStatusCallbacks' in method_section, \
            "Should iterate through service status callbacks"


class TestDocstringsAndComments:
    """Tests for proper documentation of the feature."""

    @pytest.fixture
    def queue_poller_js(self):
        """Load QueuePoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/queue-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    @pytest.fixture
    def log_poller_js(self):
        """Load LogPoller JavaScript content."""
        js_path = Path(__file__).parent.parent.parent / "frontend/static/js/log-poller.js"
        with open(js_path, 'r') as f:
            return f.read()

    def test_queue_poller_fetch_state_has_docstring(self, queue_poller_js):
        """_fetchState should have updated docstring mentioning 502/503 handling."""
        # Find docstring before _fetchState
        fetch_start = queue_poller_js.find('async _fetchState() {')
        assert fetch_start > 0, "_fetchState method not found"
        docstring_start = queue_poller_js.rfind('/**', 0, fetch_start)
        assert docstring_start > 0, "Docstring not found before _fetchState"
        docstring = queue_poller_js[docstring_start:fetch_start]

        assert '502' in docstring or '503' in docstring or 'unavailable' in docstring.lower(), \
            "_fetchState docstring should mention 502/503 or service unavailable handling"

    def test_log_poller_fetch_logs_has_docstring(self, log_poller_js):
        """_fetchLogs should have updated docstring mentioning 502/503 handling."""
        fetch_start = log_poller_js.find('async _fetchLogs() {')
        assert fetch_start > 0, "_fetchLogs method not found"
        docstring_start = log_poller_js.rfind('/**', 0, fetch_start)
        assert docstring_start > 0, "Docstring not found before _fetchLogs"
        docstring = log_poller_js[docstring_start:fetch_start]

        assert '502' in docstring or '503' in docstring or 'unavailable' in docstring.lower(), \
            "_fetchLogs docstring should mention 502/503 or service unavailable handling"

    def test_shared_state_has_comment(self, queue_poller_js):
        """Shared state initialization should have explanatory comment."""
        shared_state_area = queue_poller_js.find('_pollerServiceStatus')
        context = queue_poller_js[max(0, shared_state_area - 200):shared_state_area + 50]

        assert 'duplicate' in context.lower() or 'coordination' in context.lower() or 'shared' in context.lower(), \
            "Shared state should have comment explaining its purpose"
