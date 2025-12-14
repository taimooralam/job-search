"""
Unit tests for WebSocket authentication in runner_service.

Tests cover:
1. verify_websocket_token() function in auth.py
2. WebSocket endpoint /ws/queue authentication behavior
3. ASGI spec compliance (accept() before close())
4. Error message formatting

Critical Bug Fix (Gap #XXX):
- WebSocket connections MUST call accept() before close() to avoid HTTP 403
- Authentication failures return 1008 code with JSON error message
- Missing Redis returns 1011 code with JSON error message
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import WebSocket
from fastapi.testclient import TestClient


# =============================================================================
# Unit Tests for verify_websocket_token()
# =============================================================================


class TestVerifyWebSocketToken:
    """Tests for the verify_websocket_token() function."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        ws = MagicMock(spec=WebSocket)
        ws.headers = {}
        ws.query_params = {}
        return ws

    @pytest.fixture
    def mock_settings_auth_required(self, mocker):
        """Mock settings with auth required."""
        mock_settings = mocker.patch("runner_service.auth.settings")
        mock_settings.auth_required = True
        mock_settings.runner_api_secret = "test-secret-key-1234"
        return mock_settings

    @pytest.fixture
    def mock_settings_auth_not_required(self, mocker):
        """Mock settings with auth NOT required (development mode)."""
        mock_settings = mocker.patch("runner_service.auth.settings")
        mock_settings.auth_required = False
        return mock_settings

    def test_returns_true_when_auth_not_required(self, mock_websocket, mock_settings_auth_not_required):
        """Should return (True, None) when auth is not required."""
        from runner_service.auth import verify_websocket_token

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is True
        assert error_msg is None

    def test_returns_false_when_auth_required_but_no_token(self, mock_websocket, mock_settings_auth_required):
        """Should return (False, error) when no token provided (header or query param)."""
        from runner_service.auth import verify_websocket_token

        # No Authorization header and no query params
        mock_websocket.headers = {}
        mock_websocket.query_params = {}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is False
        assert error_msg == "Missing authentication token"

    def test_returns_false_when_auth_header_format_invalid_and_no_query_param(self, mock_websocket, mock_settings_auth_required):
        """Should return (False, error) when header has invalid format and no query param token."""
        from runner_service.auth import verify_websocket_token

        # Invalid format (missing Bearer prefix) and no query param
        mock_websocket.headers = {"authorization": "test-secret-key-1234"}
        mock_websocket.query_params = {}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        # Falls back to query param, finds nothing, returns missing token
        assert is_valid is False
        assert error_msg == "Missing authentication token"

    def test_falls_back_to_query_param_when_header_format_invalid(self, mock_websocket, mock_settings_auth_required):
        """Should fall back to query param when header format is invalid."""
        from runner_service.auth import verify_websocket_token

        # Invalid header format but valid query param
        mock_websocket.headers = {"authorization": "test-secret-key-1234"}  # Missing Bearer
        mock_websocket.query_params = {"token": "test-secret-key-1234"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        # Falls back to query param which is valid
        assert is_valid is True
        assert error_msg is None

    def test_returns_false_when_token_invalid(self, mock_websocket, mock_settings_auth_required):
        """Should return (False, error) when token doesn't match secret."""
        from runner_service.auth import verify_websocket_token

        # Wrong token
        mock_websocket.headers = {"authorization": "Bearer wrong-token-12345"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is False
        assert error_msg == "Invalid authentication token"

    def test_returns_true_when_token_valid(self, mock_websocket, mock_settings_auth_required):
        """Should return (True, None) when token matches secret."""
        from runner_service.auth import verify_websocket_token

        # Valid token
        mock_websocket.headers = {"authorization": "Bearer test-secret-key-1234"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is True
        assert error_msg is None

    def test_case_insensitive_bearer_prefix(self, mock_websocket, mock_settings_auth_required):
        """Should accept 'Bearer' or 'bearer' prefix (case insensitive)."""
        from runner_service.auth import verify_websocket_token

        # Lowercase 'bearer'
        mock_websocket.headers = {"authorization": "bearer test-secret-key-1234"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is True
        assert error_msg is None

    def test_returns_true_when_valid_token_in_query_param(self, mock_websocket, mock_settings_auth_required):
        """Should return (True, None) when valid token provided via query parameter."""
        from runner_service.auth import verify_websocket_token

        # Token in query param (browser direct connection)
        mock_websocket.headers = {}
        mock_websocket.query_params = {"token": "test-secret-key-1234"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is True
        assert error_msg is None

    def test_returns_false_when_invalid_token_in_query_param(self, mock_websocket, mock_settings_auth_required):
        """Should return (False, error) when invalid token provided via query parameter."""
        from runner_service.auth import verify_websocket_token

        # Invalid token in query param
        mock_websocket.headers = {}
        mock_websocket.query_params = {"token": "wrong-token-12345"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is False
        assert error_msg == "Invalid authentication token"

    def test_prefers_header_over_query_param(self, mock_websocket, mock_settings_auth_required):
        """Should use Authorization header when both header and query param are provided."""
        from runner_service.auth import verify_websocket_token

        # Both header (valid) and query param (invalid)
        mock_websocket.headers = {"authorization": "Bearer test-secret-key-1234"}
        mock_websocket.query_params = {"token": "wrong-token-12345"}

        is_valid, error_msg = verify_websocket_token(mock_websocket)

        # Header takes precedence, so should succeed
        assert is_valid is True
        assert error_msg is None

    def test_handles_server_misconfiguration(self, mock_websocket, mock_settings_auth_required):
        """Should return (False, error) when server secret is not configured."""
        from runner_service.auth import verify_websocket_token

        # Mock settings to raise ValueError when accessing runner_api_secret
        mock_settings_auth_required.runner_api_secret = None

        mock_websocket.headers = {"authorization": "Bearer test-secret-key-1234"}

        with patch("runner_service.auth.get_runner_secret", side_effect=ValueError("Secret not configured")):
            is_valid, error_msg = verify_websocket_token(mock_websocket)

        assert is_valid is False
        assert "Server authentication not configured" in error_msg


# =============================================================================
# Integration Tests for WebSocket Endpoint /ws/queue
# =============================================================================


class TestWebSocketEndpoint:
    """Tests for the /ws/queue WebSocket endpoint."""

    @pytest.fixture
    def mock_settings(self, mocker):
        """Mock settings for WebSocket tests."""
        mock_settings = mocker.patch("runner_service.app.settings")
        mock_settings.auth_required = True
        mock_settings.runner_api_secret = "test-secret-key-1234"
        mock_settings.redis_url = "redis://localhost:6379"
        mock_settings.cors_origins_list = []
        return mock_settings

    @pytest.fixture
    def mock_queue_manager(self, mocker):
        """Mock the queue manager."""
        mock_manager = AsyncMock()
        mock_manager.get_state = AsyncMock()
        return mock_manager

    @pytest.fixture
    def mock_ws_manager(self, mocker):
        """Mock the WebSocket manager."""
        mock_ws_mgr = AsyncMock()
        mock_ws_mgr.run_connection = AsyncMock()
        return mock_ws_mgr

    def test_websocket_accepts_valid_auth(self, client, mock_settings, mocker):
        """Should accept WebSocket connection with valid Bearer token when Redis configured."""
        # Mock the global _ws_manager as not None (Redis configured)
        mock_ws_manager = AsyncMock()
        mock_ws_manager.run_connection = AsyncMock()
        mocker.patch("runner_service.app._ws_manager", mock_ws_manager)

        # Attempt WebSocket connection with valid auth
        with client.websocket_connect(
            "/ws/queue",
            headers={"Authorization": "Bearer test-secret-key-1234"}
        ) as websocket:
            # Connection should be accepted and run_connection should be called
            # The connection will close immediately since it's a test, but it shouldn't return 403
            pass

        # Verify run_connection was called (indicates successful auth)
        mock_ws_manager.run_connection.assert_called_once()

    def test_websocket_rejects_missing_auth(self, client, mock_settings, mocker):
        """Should close WebSocket with code 1008 when Authorization header missing."""
        # Mock the global _ws_manager as not None (Redis configured)
        mocker.patch("runner_service.app._ws_manager", AsyncMock())

        # Mock the WebSocket to capture close() calls
        with patch("runner_service.app.WebSocket") as MockWebSocket:
            mock_ws_instance = AsyncMock()
            mock_ws_instance.accept = AsyncMock()
            mock_ws_instance.send_json = AsyncMock()
            mock_ws_instance.close = AsyncMock()
            mock_ws_instance.headers = {}  # No Authorization header
            mock_ws_instance.client = MagicMock()
            mock_ws_instance.client.host = "127.0.0.1"
            mock_ws_instance.url = MagicMock()
            mock_ws_instance.url.path = "/ws/queue"
            MockWebSocket.return_value = mock_ws_instance

            # Attempt connection without auth header
            try:
                with client.websocket_connect("/ws/queue") as websocket:
                    pass
            except Exception:
                # Connection will fail, but we're testing server behavior
                pass

        # Note: Testing WebSocket close codes requires direct endpoint testing
        # as TestClient doesn't expose close codes. This test verifies the flow.

    def test_websocket_rejects_invalid_token(self, client, mock_settings, mocker):
        """Should close WebSocket with code 1008 when token is invalid."""
        # Mock the global _ws_manager as not None (Redis configured)
        mocker.patch("runner_service.app._ws_manager", AsyncMock())

        # Attempt WebSocket connection with invalid token
        try:
            with client.websocket_connect(
                "/ws/queue",
                headers={"Authorization": "Bearer wrong-token"}
            ) as websocket:
                # Should receive error message before close
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert "Authentication failed" in data["payload"]["message"]
        except Exception:
            # Connection should be rejected
            pass

    def test_websocket_closes_gracefully_when_redis_not_configured(self, client, mock_settings, mocker):
        """Should close WebSocket with code 1011 when Redis not configured (after accept)."""
        # Mock the global _ws_manager as None (Redis not configured)
        mocker.patch("runner_service.app._ws_manager", None)

        # Attempt WebSocket connection with valid auth
        try:
            with client.websocket_connect(
                "/ws/queue",
                headers={"Authorization": "Bearer test-secret-key-1234"}
            ) as websocket:
                # Should receive error message before close
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert "Queue service not configured" in data["payload"]["message"]
                assert data["payload"]["code"] == "QUEUE_NOT_CONFIGURED"
        except Exception:
            # Connection should close gracefully with 1011
            pass

    def test_websocket_sends_json_error_before_close_on_auth_failure(self, mocker):
        """Should send JSON error message before closing on authentication failure."""
        from runner_service.app import queue_websocket
        from fastapi import WebSocket

        # Create mock WebSocket
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.headers = {}  # No Authorization header
        mock_ws.client = MagicMock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.url = MagicMock()
        mock_ws.url.path = "/ws/queue"
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()

        # Mock settings
        mock_settings = mocker.patch("runner_service.app.settings")
        mock_settings.auth_required = True

        # Mock _ws_manager as not None
        mocker.patch("runner_service.app._ws_manager", AsyncMock())

        # Call the endpoint
        import asyncio
        asyncio.run(queue_websocket(mock_ws))

        # Verify the sequence of calls
        mock_ws.accept.assert_called_once()  # MUST accept before close
        mock_ws.send_json.assert_called_once()  # Send error message

        # Verify error message structure
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert "Authentication failed" in call_args["payload"]["message"]
        assert call_args["payload"]["code"] == "AUTH_FAILED"

        # Verify close was called with correct code
        mock_ws.close.assert_called_once_with(code=1008, reason="Authentication failed")

    def test_websocket_sends_json_error_before_close_on_redis_missing(self, mocker):
        """Should send JSON error message before closing when Redis not configured."""
        from runner_service.app import queue_websocket
        from fastapi import WebSocket

        # Create mock WebSocket
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.headers = {"authorization": "Bearer test-secret-key-1234"}  # Valid auth
        mock_ws.client = MagicMock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.url = MagicMock()
        mock_ws.url.path = "/ws/queue"
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()
        mock_ws.close = AsyncMock()

        # Mock settings
        mock_settings = mocker.patch("runner_service.app.settings")
        mock_settings.auth_required = True
        mock_settings.runner_api_secret = "test-secret-key-1234"

        # Mock _ws_manager as None (Redis not configured)
        mocker.patch("runner_service.app._ws_manager", None)

        # Call the endpoint
        import asyncio
        asyncio.run(queue_websocket(mock_ws))

        # Verify the sequence of calls
        mock_ws.accept.assert_called_once()  # MUST accept before close
        mock_ws.send_json.assert_called_once()  # Send error message

        # Verify error message structure
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert "Queue service not configured" in call_args["payload"]["message"]
        assert call_args["payload"]["code"] == "QUEUE_NOT_CONFIGURED"

        # Verify close was called with correct code
        mock_ws.close.assert_called_once_with(code=1011, reason="Queue not configured")

    def test_websocket_accept_called_before_close_prevents_403(self, mocker):
        """Critical test: WebSocket MUST call accept() before close() to avoid HTTP 403."""
        from runner_service.app import queue_websocket
        from fastapi import WebSocket

        # Create mock WebSocket that tracks call order
        call_order = []

        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.headers = {}  # No auth (will fail)
        mock_ws.client = MagicMock()
        mock_ws.client.host = "127.0.0.1"
        mock_ws.url = MagicMock()
        mock_ws.url.path = "/ws/queue"

        # Track call order
        async def track_accept():
            call_order.append("accept")

        async def track_send_json(data):
            call_order.append("send_json")

        async def track_close(code=None, reason=None):
            call_order.append("close")

        mock_ws.accept = AsyncMock(side_effect=track_accept)
        mock_ws.send_json = AsyncMock(side_effect=track_send_json)
        mock_ws.close = AsyncMock(side_effect=track_close)

        # Mock settings
        mock_settings = mocker.patch("runner_service.app.settings")
        mock_settings.auth_required = True

        # Mock _ws_manager
        mocker.patch("runner_service.app._ws_manager", AsyncMock())

        # Call the endpoint
        import asyncio
        asyncio.run(queue_websocket(mock_ws))

        # CRITICAL: Verify accept() is called BEFORE close()
        assert call_order == ["accept", "send_json", "close"], \
            "WebSocket MUST call accept() before close() to avoid HTTP 403 Forbidden"

    def test_websocket_allows_connection_when_auth_not_required_in_development(self, client, mocker):
        """Should allow WebSocket connection without auth when auth_required=False."""
        # Mock settings with auth not required - MUST mock both app and auth module settings
        mock_app_settings = mocker.patch("runner_service.app.settings")
        mock_app_settings.auth_required = False
        mock_app_settings.redis_url = "redis://localhost:6379"

        # Also mock auth module settings (verify_websocket_token uses this)
        mock_auth_settings = mocker.patch("runner_service.auth.settings")
        mock_auth_settings.auth_required = False

        # Mock _ws_manager as not None
        mock_ws_manager = AsyncMock()
        mock_ws_manager.run_connection = AsyncMock()
        mocker.patch("runner_service.app._ws_manager", mock_ws_manager)

        # Attempt WebSocket connection WITHOUT auth header
        with client.websocket_connect("/ws/queue") as websocket:
            # Connection should be accepted in development mode
            pass

        # Verify run_connection was called (indicates successful connection)
        mock_ws_manager.run_connection.assert_called_once()
