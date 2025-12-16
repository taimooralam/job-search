"""
Unit tests for WebSocket keepalive functionality in runner_service.

Tests cover:
1. ConnectionState.is_stale() - timeout detection
2. QueueWebSocketManager._update_pong_time() - pong time tracking
3. QueueWebSocketManager._ping_loop() - periodic ping sending
4. QueueWebSocketManager.connect() - ping task creation
5. QueueWebSocketManager.disconnect() - ping task cancellation
6. QueueWebSocketManager.handle_message() - pong message handling

Critical Features:
- Server-side ping detects stale connections (no pong within PONG_TIMEOUT_SECONDS)
- Ping loop sends pings every PING_INTERVAL_SECONDS
- Client pong responses update last_pong_time to keep connection alive
- Stale connections are detected and cleaned up
"""

import asyncio
import pytest
import time
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch, call

from runner_service.queue.websocket import (
    ConnectionState,
    QueueWebSocketManager,
    PING_INTERVAL_SECONDS,
    PONG_TIMEOUT_SECONDS,
)
from runner_service.queue.models import QueueItem, QueueItemStatus, QueueState


# =============================================================================
# Unit Tests for ConnectionState
# =============================================================================


class TestConnectionState:
    """Tests for the ConnectionState dataclass."""

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        ws = MagicMock()
        ws.send_json = AsyncMock()
        return ws

    def test_is_stale_returns_false_when_fresh(self, mock_websocket):
        """Should return False when connection is fresh (recent pong)."""
        # Arrange
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=time.time(),  # Just now
            connection_id="conn_1",
        )

        # Act
        is_stale = conn_state.is_stale()

        # Assert
        assert is_stale is False

    def test_is_stale_returns_true_after_timeout(self, mock_websocket):
        """Should return True when no pong received within PONG_TIMEOUT_SECONDS."""
        # Arrange
        old_time = time.time() - (PONG_TIMEOUT_SECONDS + 10)  # 10 seconds past timeout
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=old_time,
            connection_id="conn_1",
        )

        # Act
        is_stale = conn_state.is_stale()

        # Assert
        assert is_stale is True

    def test_is_stale_returns_false_just_before_timeout(self, mock_websocket):
        """Should return False when just under the timeout threshold."""
        # Arrange
        recent_time = time.time() - (PONG_TIMEOUT_SECONDS - 5)  # 5 seconds before timeout
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=recent_time,
            connection_id="conn_1",
        )

        # Act
        is_stale = conn_state.is_stale()

        # Assert
        assert is_stale is False

    def test_is_stale_returns_true_exactly_at_timeout(self, mock_websocket):
        """Should return True when exactly at timeout threshold."""
        # Arrange
        exact_timeout = time.time() - (PONG_TIMEOUT_SECONDS + 1)
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=exact_timeout,
            connection_id="conn_1",
        )

        # Act
        is_stale = conn_state.is_stale()

        # Assert
        assert is_stale is True


# =============================================================================
# Unit Tests for QueueWebSocketManager
# =============================================================================


class TestQueueWebSocketManager:
    """Tests for the QueueWebSocketManager WebSocket keepalive functionality."""

    @pytest.fixture
    def mock_queue_manager(self):
        """Create a mock QueueManager instance."""
        manager = MagicMock()
        manager.get_state = AsyncMock(return_value=QueueState(
            pending=[],
            running=[],
            failed=[],
            history=[],
        ))
        manager.retry = AsyncMock()
        manager.cancel = AsyncMock()
        manager.dismiss_failed = AsyncMock()
        return manager

    @pytest.fixture
    def ws_manager(self, mock_queue_manager):
        """Create a QueueWebSocketManager instance."""
        return QueueWebSocketManager(queue_manager=mock_queue_manager)

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket instance."""
        ws = MagicMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.receive_text = AsyncMock()
        return ws

    # =========================================================================
    # Tests for _update_pong_time()
    # =========================================================================

    def test_update_pong_time_updates_timestamp(self, ws_manager, mock_websocket):
        """Should update last_pong_time when pong is received."""
        # Arrange
        old_time = time.time() - 100
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=old_time,
            connection_id="conn_1",
        )
        ws_manager._connection_states[mock_websocket] = conn_state

        before_time = time.time()

        # Act
        ws_manager._update_pong_time(mock_websocket)

        after_time = time.time()

        # Assert
        updated_time = ws_manager._connection_states[mock_websocket].last_pong_time
        assert updated_time > old_time
        assert before_time <= updated_time <= after_time

    def test_update_pong_time_handles_missing_connection(self, ws_manager, mock_websocket):
        """Should handle gracefully when connection not in _connection_states."""
        # Act - should not raise exception
        ws_manager._update_pong_time(mock_websocket)

        # Assert - no error raised
        assert mock_websocket not in ws_manager._connection_states

    def test_update_pong_time_resets_stale_status(self, ws_manager, mock_websocket):
        """Should make a stale connection fresh again after receiving pong."""
        # Arrange - create stale connection
        old_time = time.time() - (PONG_TIMEOUT_SECONDS + 10)
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=old_time,
            connection_id="conn_1",
        )
        ws_manager._connection_states[mock_websocket] = conn_state

        # Verify it's stale before update
        assert conn_state.is_stale() is True

        # Act
        ws_manager._update_pong_time(mock_websocket)

        # Assert - should no longer be stale
        assert conn_state.is_stale() is False

    # =========================================================================
    # Tests for _ping_loop()
    # =========================================================================

    @pytest.mark.asyncio
    async def test_ping_loop_sends_pings_at_interval(self, ws_manager, mock_websocket):
        """Should send ping messages at PING_INTERVAL_SECONDS."""
        # Arrange
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=time.time(),
            connection_id="conn_test",
        )
        ws_manager._connection_states[mock_websocket] = conn_state

        ping_count = 0
        max_pings = 3

        async def send_json_side_effect(message):
            """Track ping sends and stop after max_pings."""
            nonlocal ping_count
            ping_count += 1
            if ping_count >= max_pings:
                # Raise to break the loop
                raise asyncio.CancelledError()

        mock_websocket.send_json.side_effect = send_json_side_effect

        # Mock asyncio.sleep to track interval
        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch("runner_service.queue.websocket.asyncio.sleep", side_effect=mock_sleep):
            # Act
            try:
                await ws_manager._ping_loop(mock_websocket, "conn_test")
            except asyncio.CancelledError:
                pass

        # Assert - should have called sleep with PING_INTERVAL_SECONDS
        assert len(sleep_times) >= max_pings
        assert all(t == PING_INTERVAL_SECONDS for t in sleep_times)

        # Assert - should have sent ping messages
        assert ping_count == max_pings
        assert mock_websocket.send_json.call_count == max_pings
        for call_args in mock_websocket.send_json.call_args_list:
            assert call_args[0][0] == {"type": "ping"}

    @pytest.mark.asyncio
    async def test_ping_loop_detects_stale_connection(self, ws_manager, mock_websocket):
        """Should detect and stop pinging stale connections."""
        # Arrange - create connection that will become stale
        old_time = time.time() - (PONG_TIMEOUT_SECONDS + 10)
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=old_time,  # Already stale
            connection_id="conn_stale",
        )
        ws_manager._connection_states[mock_websocket] = conn_state

        # Mock sleep to avoid waiting
        async def mock_sleep(seconds):
            pass

        with patch("runner_service.queue.websocket.asyncio.sleep", side_effect=mock_sleep):
            # Act
            await ws_manager._ping_loop(mock_websocket, "conn_stale")

        # Assert - should NOT have sent any pings (detected stale before sending)
        mock_websocket.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_ping_loop_stops_on_send_error(self, ws_manager, mock_websocket):
        """Should stop ping loop when send_json raises exception."""
        # Arrange
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=time.time(),
            connection_id="conn_error",
        )
        ws_manager._connection_states[mock_websocket] = conn_state

        # Mock send_json to raise exception
        mock_websocket.send_json.side_effect = Exception("Connection closed")

        # Mock sleep
        async def mock_sleep(seconds):
            pass

        with patch("runner_service.queue.websocket.asyncio.sleep", side_effect=mock_sleep):
            # Act
            await ws_manager._ping_loop(mock_websocket, "conn_error")

        # Assert - should have attempted to send ping once
        assert mock_websocket.send_json.call_count == 1

    @pytest.mark.asyncio
    async def test_ping_loop_handles_cancellation(self, ws_manager, mock_websocket):
        """Should handle asyncio.CancelledError gracefully."""
        # Arrange
        conn_state = ConnectionState(
            websocket=mock_websocket,
            last_pong_time=time.time(),
            connection_id="conn_cancel",
        )
        ws_manager._connection_states[mock_websocket] = conn_state

        # Mock sleep to raise CancelledError
        async def mock_sleep(seconds):
            raise asyncio.CancelledError()

        with patch("runner_service.queue.websocket.asyncio.sleep", side_effect=mock_sleep):
            # Act & Assert - should raise CancelledError
            with pytest.raises(asyncio.CancelledError):
                await ws_manager._ping_loop(mock_websocket, "conn_cancel")

    # =========================================================================
    # Tests for connect() - ping task creation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_connect_creates_ping_task(self, ws_manager, mock_websocket, mock_queue_manager):
        """Should create and start ping task when connection is established."""
        # Act
        connection_id = await ws_manager.connect(mock_websocket)

        # Assert - connection state should exist
        assert mock_websocket in ws_manager._connection_states
        conn_state = ws_manager._connection_states[mock_websocket]

        # Assert - ping task should be created and running
        assert conn_state.ping_task is not None
        assert isinstance(conn_state.ping_task, asyncio.Task)
        assert not conn_state.ping_task.done()

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_connect_initializes_pong_time(self, ws_manager, mock_websocket):
        """Should initialize last_pong_time to current time on connect."""
        # Arrange
        before_time = time.time()

        # Act
        await ws_manager.connect(mock_websocket)

        after_time = time.time()

        # Assert
        conn_state = ws_manager._connection_states[mock_websocket]
        assert before_time <= conn_state.last_pong_time <= after_time

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_connect_assigns_connection_id(self, ws_manager, mock_websocket):
        """Should assign unique connection ID."""
        # Act
        connection_id = await ws_manager.connect(mock_websocket)

        # Assert
        assert connection_id.startswith("conn_")
        assert connection_id == ws_manager._connection_states[mock_websocket].connection_id

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_connect_increments_connection_counter(self, ws_manager, mock_websocket):
        """Should increment connection counter for each new connection."""
        # Arrange
        mock_ws2 = MagicMock()
        mock_ws2.accept = AsyncMock()
        mock_ws2.send_json = AsyncMock()

        # Act
        conn_id_1 = await ws_manager.connect(mock_websocket)
        conn_id_2 = await ws_manager.connect(mock_ws2)

        # Assert
        assert conn_id_1 == "conn_1"
        assert conn_id_2 == "conn_2"

        # Cleanup
        await ws_manager.disconnect(mock_websocket)
        await ws_manager.disconnect(mock_ws2)

    # =========================================================================
    # Tests for disconnect() - ping task cancellation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_disconnect_cancels_ping_task(self, ws_manager, mock_websocket):
        """Should cancel ping task when connection is closed."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        conn_state = ws_manager._connection_states[mock_websocket]
        ping_task = conn_state.ping_task

        # Verify task is running
        assert not ping_task.done()

        # Act
        await ws_manager.disconnect(mock_websocket)

        # Assert - ping task should be cancelled
        assert ping_task.cancelled()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection_state(self, ws_manager, mock_websocket):
        """Should remove connection from _connection_states."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        assert mock_websocket in ws_manager._connection_states

        # Act
        await ws_manager.disconnect(mock_websocket)

        # Assert
        assert mock_websocket not in ws_manager._connection_states

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_active_connections(self, ws_manager, mock_websocket):
        """Should remove connection from active_connections set."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        assert mock_websocket in ws_manager.active_connections

        # Act
        await ws_manager.disconnect(mock_websocket)

        # Assert
        assert mock_websocket not in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_handles_missing_connection(self, ws_manager, mock_websocket):
        """Should handle disconnect gracefully for non-existent connection."""
        # Act - should not raise exception
        await ws_manager.disconnect(mock_websocket)

        # Assert
        assert mock_websocket not in ws_manager._connection_states
        assert mock_websocket not in ws_manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_waits_for_task_cancellation(self, ws_manager, mock_websocket):
        """Should await ping task cancellation to ensure clean shutdown."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        conn_state = ws_manager._connection_states[mock_websocket]
        ping_task = conn_state.ping_task

        # Mock the task to track await
        original_task = ping_task

        # Act
        await ws_manager.disconnect(mock_websocket)

        # Assert - task should be cancelled and awaited
        assert original_task.cancelled()

    # =========================================================================
    # Tests for handle_message() - pong handling
    # =========================================================================

    @pytest.mark.asyncio
    async def test_handle_message_pong_updates_pong_time(self, ws_manager, mock_websocket):
        """Should update last_pong_time when pong message received."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        old_time = ws_manager._connection_states[mock_websocket].last_pong_time

        # Wait a tiny bit to ensure time difference
        await asyncio.sleep(0.01)

        # Act
        await ws_manager.handle_message(mock_websocket, {"type": "pong"})

        # Assert
        new_time = ws_manager._connection_states[mock_websocket].last_pong_time
        assert new_time > old_time

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_handle_message_pong_does_not_send_response(self, ws_manager, mock_websocket):
        """Should not send response to pong message (server-initiated ping/pong)."""
        # Arrange
        await ws_manager.connect(mock_websocket)

        # Clear any previous send_json calls from connect
        mock_websocket.send_json.reset_mock()

        # Act
        await ws_manager.handle_message(mock_websocket, {"type": "pong"})

        # Assert - should not send any message back
        mock_websocket.send_json.assert_not_called()

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_handle_message_ping_sends_pong_response(self, ws_manager, mock_websocket):
        """Should send pong response to client-initiated ping."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        # Act
        await ws_manager.handle_message(mock_websocket, {"type": "ping"})

        # Assert - should send pong response
        mock_websocket.send_json.assert_called_once_with({"type": "pong"})

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_handle_message_pong_with_empty_payload(self, ws_manager, mock_websocket):
        """Should handle pong message with empty payload."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        old_time = ws_manager._connection_states[mock_websocket].last_pong_time
        await asyncio.sleep(0.01)

        # Act
        await ws_manager.handle_message(mock_websocket, {"type": "pong", "payload": {}})

        # Assert
        new_time = ws_manager._connection_states[mock_websocket].last_pong_time
        assert new_time > old_time

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_handle_message_unknown_type_sends_error(self, ws_manager, mock_websocket):
        """Should send error message for unknown message type."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        mock_websocket.send_json.reset_mock()

        # Act
        await ws_manager.handle_message(mock_websocket, {"type": "unknown"})

        # Assert
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert "unknown" in call_args["payload"]["message"].lower()

        # Cleanup
        await ws_manager.disconnect(mock_websocket)

    # =========================================================================
    # Integration Tests - Full Ping/Pong Flow
    # =========================================================================

    @pytest.mark.asyncio
    async def test_full_ping_pong_flow_keeps_connection_alive(self, ws_manager, mock_websocket):
        """Integration test: ping loop sends pings, pong responses keep connection alive."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        conn_state = ws_manager._connection_states[mock_websocket]

        # Simulate receiving pong responses
        async def simulate_pong_responses():
            """Simulate client responding to pings with pongs."""
            for _ in range(3):
                await asyncio.sleep(0.1)
                await ws_manager.handle_message(mock_websocket, {"type": "pong"})

        # Mock sleep to speed up test
        original_interval = PING_INTERVAL_SECONDS
        with patch("runner_service.queue.websocket.PING_INTERVAL_SECONDS", 0.05):
            # Act - let ping loop run for a bit while simulating pong responses
            pong_task = asyncio.create_task(simulate_pong_responses())
            await asyncio.sleep(0.4)  # Let it run for a bit

            # Assert - connection should not be stale
            assert not conn_state.is_stale()

            # Cleanup
            pong_task.cancel()
            try:
                await pong_task
            except asyncio.CancelledError:
                pass

        await ws_manager.disconnect(mock_websocket)

    @pytest.mark.asyncio
    async def test_connection_becomes_stale_without_pong(self, ws_manager, mock_websocket):
        """Integration test: connection becomes stale when client stops responding."""
        # Arrange
        await ws_manager.connect(mock_websocket)
        conn_state = ws_manager._connection_states[mock_websocket]

        # Set last_pong_time to old value
        conn_state.last_pong_time = time.time() - (PONG_TIMEOUT_SECONDS + 10)

        # Act
        is_stale = conn_state.is_stale()

        # Assert
        assert is_stale is True

        # Cleanup
        await ws_manager.disconnect(mock_websocket)
