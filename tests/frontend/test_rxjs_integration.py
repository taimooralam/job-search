"""
Unit tests for RxJS integration in frontend JavaScript files.

Tests verify:
1. RxJS utilities module exports required functions
2. QueueWebSocket creates expected observables
3. Graceful fallback code exists when RxJS is unavailable
4. Message type filtering is properly implemented

Note: These are Python-based structure validation tests, NOT JavaScript runtime tests.
They verify that the JavaScript files contain expected patterns and structures.
"""

import pytest
from pathlib import Path
import re


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def js_dir():
    """Return path to frontend JavaScript directory."""
    return Path(__file__).parent.parent.parent / "frontend" / "static" / "js"


@pytest.fixture
def rxjs_utils_content(js_dir):
    """Read rxjs-utils.js content."""
    js_file = js_dir / "rxjs-utils.js"
    return js_file.read_text()


@pytest.fixture
def queue_websocket_content(js_dir):
    """Read queue-websocket.js content."""
    js_file = js_dir / "queue-websocket.js"
    return js_file.read_text()


@pytest.fixture
def cli_panel_content(js_dir):
    """Read cli-panel.js content."""
    js_file = js_dir / "cli-panel.js"
    return js_file.read_text()


# =============================================================================
# Tests for rxjs-utils.js
# =============================================================================


class TestRxjsUtilsModule:
    """Tests for RxJS utilities module structure."""

    def test_module_exists(self, js_dir):
        """rxjs-utils.js should exist in the frontend JS directory."""
        js_file = js_dir / "rxjs-utils.js"
        assert js_file.exists(), f"rxjs-utils.js not found at {js_file}"

    def test_exports_exponential_backoff(self, rxjs_utils_content):
        """Should export exponentialBackoff function."""
        assert "function exponentialBackoff" in rxjs_utils_content
        assert "exponentialBackoff" in rxjs_utils_content

    def test_exports_create_websocket(self, rxjs_utils_content):
        """Should export createWebSocket function."""
        assert "function createWebSocket" in rxjs_utils_content

    def test_exports_create_debounced_save(self, rxjs_utils_content):
        """Should export createDebouncedSave function."""
        assert "function createDebouncedSave" in rxjs_utils_content

    def test_exports_create_pending_buffer(self, rxjs_utils_content):
        """Should export createPendingBuffer function."""
        assert "function createPendingBuffer" in rxjs_utils_content

    def test_exports_create_interval(self, rxjs_utils_content):
        """Should export createInterval function."""
        assert "function createInterval" in rxjs_utils_content

    def test_exports_create_message_router(self, rxjs_utils_content):
        """Should export createMessageRouter function."""
        assert "function createMessageRouter" in rxjs_utils_content

    def test_checks_rxjs_loaded(self, rxjs_utils_content):
        """Should check if global rxjs is loaded before using."""
        assert "global.rxjs" in rxjs_utils_content or "window.rxjs" in rxjs_utils_content

    def test_exponential_backoff_uses_jitter(self, rxjs_utils_content):
        """exponentialBackoff should add random jitter to prevent thundering herd."""
        assert "Math.random()" in rxjs_utils_content
        assert "jitter" in rxjs_utils_content.lower()

    def test_exponential_backoff_respects_max_delay(self, rxjs_utils_content):
        """exponentialBackoff should cap delay at maxDelay."""
        assert "Math.min" in rxjs_utils_content
        assert "maxDelay" in rxjs_utils_content

    def test_exports_rxjs_operators(self, rxjs_utils_content):
        """Should re-export common RxJS operators."""
        # Check that operators are exposed
        common_operators = [
            "Subject",
            "BehaviorSubject",
            "debounceTime",
            "filter",
            "map",
            "tap",
        ]
        for op in common_operators:
            assert op in rxjs_utils_content, f"Operator {op} not found in rxjs-utils.js"


# =============================================================================
# Tests for queue-websocket.js
# =============================================================================


class TestQueueWebSocketModule:
    """Tests for QueueWebSocket class structure."""

    def test_module_exists(self, js_dir):
        """queue-websocket.js should exist."""
        js_file = js_dir / "queue-websocket.js"
        assert js_file.exists()

    def test_defines_queue_websocket_class(self, queue_websocket_content):
        """Should define QueueWebSocket class."""
        assert "class QueueWebSocket" in queue_websocket_content

    def test_creates_message_subject(self, queue_websocket_content):
        """Should create _message$ Subject for all messages."""
        assert "_message$" in queue_websocket_content

    def test_creates_connected_behavior_subject(self, queue_websocket_content):
        """Should create _connected$ BehaviorSubject for connection state."""
        assert "_connected$" in queue_websocket_content
        assert "BehaviorSubject" in queue_websocket_content

    def test_creates_typed_observables(self, queue_websocket_content):
        """Should create typed message observables with filter."""
        typed_observables = [
            "queueState$",
            "queueUpdate$",
            "actionResult$",
            "error$",
        ]
        for obs in typed_observables:
            assert obs in queue_websocket_content, f"Observable {obs} not found"

    def test_has_fallback_for_rxjs_unavailable(self, queue_websocket_content):
        """Should have fallback code when RxJS is not available."""
        # Check for typeof check pattern
        assert "typeof window.RxUtils" in queue_websocket_content or "window.RxUtils" in queue_websocket_content
        # Should have fallback event handler pattern (Map-based)
        assert "eventHandlers" in queue_websocket_content or "emit(" in queue_websocket_content

    def test_implements_ping_pong(self, queue_websocket_content):
        """Should implement ping/pong keepalive."""
        assert "ping" in queue_websocket_content.lower()
        assert "pong" in queue_websocket_content.lower()

    def test_implements_reconnection(self, queue_websocket_content):
        """Should implement reconnection logic."""
        assert "reconnect" in queue_websocket_content.lower()
        assert "_scheduleReconnect" in queue_websocket_content or "reconnectAttempt" in queue_websocket_content

    def test_uses_rxjs_interval_for_ping(self, queue_websocket_content):
        """Should use RxJS interval for periodic ping (when available)."""
        # Either uses RxUtils.createInterval or rxjs.interval
        assert "interval" in queue_websocket_content.lower()

    def test_uses_rxjs_race_for_timeout(self, queue_websocket_content):
        """Should use RxJS race operator for pong timeout detection."""
        # Either mentions race or implements timeout pattern
        assert "race" in queue_websocket_content.lower() or "timeout" in queue_websocket_content.lower()


# =============================================================================
# Tests for cli-panel.js RxJS Integration
# =============================================================================


class TestCliPanelRxjsIntegration:
    """Tests for CLI panel RxJS integration."""

    def test_module_exists(self, js_dir):
        """cli-panel.js should exist."""
        js_file = js_dir / "cli-panel.js"
        assert js_file.exists()

    def test_has_rxjs_subjects(self, cli_panel_content):
        """Should create RxJS subjects for state management."""
        assert "_rxjsSubjects" in cli_panel_content or "runCreated$" in cli_panel_content

    def test_implements_debounced_save(self, cli_panel_content):
        """Should implement debounced state save."""
        assert "debounce" in cli_panel_content.lower()
        assert "saveState" in cli_panel_content or "_saveState" in cli_panel_content

    def test_has_pending_log_buffer(self, cli_panel_content):
        """Should implement pending log buffer for race condition handling."""
        assert "pending" in cli_panel_content.lower()
        # Should have some form of buffering
        assert "buffer" in cli_panel_content.lower() or "queue" in cli_panel_content.lower()

    def test_has_fallback_for_rxjs_unavailable(self, cli_panel_content):
        """Should have fallback when RxJS is not available."""
        assert "typeof window.RxUtils" in cli_panel_content or "RxUtils" in cli_panel_content
        # Should have setTimeout fallback
        assert "setTimeout" in cli_panel_content

    def test_cleanup_on_destroy(self, cli_panel_content):
        """Should have cleanup logic using destroy$ or similar."""
        assert "destroy" in cli_panel_content.lower()


# =============================================================================
# Tests for Graceful Fallback Pattern
# =============================================================================


class TestGracefulFallbackPattern:
    """Tests verifying graceful fallback when RxJS is unavailable."""

    def test_queue_websocket_works_without_rxjs(self, queue_websocket_content):
        """QueueWebSocket should work even if RxJS fails to load."""
        # Should have conditional check
        has_check = (
            "typeof window.RxUtils" in queue_websocket_content or
            "window.RxUtils &&" in queue_websocket_content or
            "_rxjsAvailable" in queue_websocket_content
        )
        assert has_check, "Missing RxJS availability check"

        # Should have legacy event handler fallback (Map-based eventHandlers + emit)
        has_fallback = (
            "eventHandlers" in queue_websocket_content or
            "emit(" in queue_websocket_content
        )
        assert has_fallback, "Missing legacy event handler fallback"

    def test_cli_panel_works_without_rxjs(self, cli_panel_content):
        """CLI panel should work even if RxJS fails to load."""
        # Should have conditional check
        has_check = (
            "typeof window.RxUtils" in cli_panel_content or
            "window.RxUtils" in cli_panel_content
        )
        assert has_check, "Missing RxJS availability check in cli-panel"

        # Should have setTimeout fallback for debounce
        assert "setTimeout" in cli_panel_content, "Missing setTimeout fallback"


# =============================================================================
# Tests for Message Type Constants
# =============================================================================


class TestMessageTypeConstants:
    """Tests for message type filtering constants."""

    def test_queue_state_type_defined(self, queue_websocket_content):
        """Should handle queue_state message type."""
        assert "queue_state" in queue_websocket_content

    def test_queue_update_type_defined(self, queue_websocket_content):
        """Should handle queue_update message type."""
        assert "queue_update" in queue_websocket_content

    def test_action_result_type_defined(self, queue_websocket_content):
        """Should handle action_result message type."""
        assert "action_result" in queue_websocket_content

    def test_error_type_defined(self, queue_websocket_content):
        """Should handle error message type."""
        # error can appear in many contexts, so be more specific
        has_error_handling = (
            "case 'error'" in queue_websocket_content or
            'case "error"' in queue_websocket_content or
            "error$" in queue_websocket_content or
            "emit('error'" in queue_websocket_content
        )
        assert has_error_handling


# =============================================================================
# Tests for CDN Loading
# =============================================================================


class TestCdnLoading:
    """Tests for RxJS CDN loading in templates."""

    def test_rxjs_loaded_in_base_template(self):
        """base.html should load RxJS from CDN."""
        base_html = Path(__file__).parent.parent.parent / "frontend" / "templates" / "base.html"
        content = base_html.read_text()

        # Should load RxJS 7 from CDN
        assert "rxjs" in content.lower()
        assert "unpkg.com" in content or "cdnjs" in content or "jsdelivr" in content

    def test_rxjs_utils_loaded_after_rxjs(self):
        """rxjs-utils.js should be loaded after RxJS CDN."""
        base_html = Path(__file__).parent.parent.parent / "frontend" / "templates" / "base.html"
        content = base_html.read_text()

        # rxjs-utils.js should appear in the template
        assert "rxjs-utils.js" in content

        # Find positions to verify order
        rxjs_pos = content.find("rxjs")
        utils_pos = content.find("rxjs-utils.js")

        # utils should come after rxjs CDN load
        assert utils_pos > rxjs_pos, "rxjs-utils.js should be loaded after RxJS CDN"
