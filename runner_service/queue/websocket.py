"""
WebSocket Handler for Queue State Broadcasting

Manages WebSocket connections for real-time queue updates.
Handles client messages (retry, cancel, refresh) and broadcasts queue events.
Implements server-side ping to detect stale connections.

Reliability Improvements:
- Increased timeout for long-running operations (CV generation ~78s)
- Separate lock-free pong time updates to avoid blocking pings
- Enhanced logging for connection lifecycle debugging
- Graceful close with proper close frames
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from .manager import QueueManager

logger = logging.getLogger(__name__)

# Ping/pong configuration
# CV generation can take ~78 seconds, so we need generous timeouts
PING_INTERVAL_SECONDS = 15  # Send ping every 15 seconds (more frequent)
PONG_TIMEOUT_SECONDS = 120  # 2 minutes - allows for long operations + network delays


@dataclass
class ConnectionState:
    """Tracks state for a single WebSocket connection."""

    websocket: WebSocket
    ping_task: Optional[asyncio.Task] = None
    last_pong_time: float = field(default_factory=time.time)
    last_ping_sent: float = field(default_factory=time.time)
    connection_id: str = ""
    pings_sent: int = 0
    pongs_received: int = 0

    def is_stale(self) -> bool:
        """Check if connection is stale (no pong received within timeout)."""
        return time.time() - self.last_pong_time > PONG_TIMEOUT_SECONDS

    def get_age_since_last_pong(self) -> float:
        """Get seconds since last pong for logging."""
        return time.time() - self.last_pong_time


class QueueWebSocketManager:
    """
    Manages WebSocket connections for queue state updates.

    Provides:
    - Connection lifecycle management
    - Initial state broadcast on connect
    - Event broadcasting to all connected clients
    - Client message handling (retry, cancel, refresh)
    - Server-side ping to detect stale connections
    """

    def __init__(self, queue_manager: QueueManager):
        """
        Initialize WebSocket manager.

        Args:
            queue_manager: QueueManager instance for queue operations
        """
        self.queue_manager = queue_manager
        self.active_connections: Set[WebSocket] = set()
        self._connection_states: Dict[WebSocket, ConnectionState] = {}
        self._connection_counter: int = 0
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> str:
        """
        Accept new WebSocket connection and send initial state.

        Args:
            websocket: FastAPI WebSocket instance

        Returns:
            Connection ID for tracking
        """
        await websocket.accept()

        # Get client info for logging
        client_host = websocket.client.host if websocket.client else "unknown"

        async with self._lock:
            self._connection_counter += 1
            connection_id = f"conn_{self._connection_counter}"
            self.active_connections.add(websocket)

            # Create connection state and start ping loop
            now = time.time()
            conn_state = ConnectionState(
                websocket=websocket,
                connection_id=connection_id,
                last_pong_time=now,
                last_ping_sent=now,
            )
            conn_state.ping_task = asyncio.create_task(
                self._ping_loop(websocket, connection_id)
            )
            self._connection_states[websocket] = conn_state

        logger.info(
            f"[{connection_id}] WebSocket connected from {client_host}, "
            f"total connections: {len(self.active_connections)}"
        )

        # Send initial queue state
        try:
            state = await self.queue_manager.get_state()
            await websocket.send_json({
                "type": "queue_state",
                "payload": state.to_dict()
            })
            logger.debug(f"[{connection_id}] Sent initial queue state")
        except Exception as e:
            logger.error(f"[{connection_id}] Failed to send initial state: {e}")

        return connection_id

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove WebSocket connection and clean up associated resources.

        Args:
            websocket: FastAPI WebSocket instance
        """
        connection_id = "unknown"

        async with self._lock:
            self.active_connections.discard(websocket)

            # Clean up connection state and cancel ping task
            if websocket in self._connection_states:
                conn_state = self._connection_states.pop(websocket)
                connection_id = conn_state.connection_id
                if conn_state.ping_task and not conn_state.ping_task.done():
                    conn_state.ping_task.cancel()
                    try:
                        await conn_state.ping_task
                    except asyncio.CancelledError:
                        pass

        logger.info(
            f"WebSocket {connection_id} disconnected, "
            f"total connections: {len(self.active_connections)}"
        )

    async def _ping_loop(self, websocket: WebSocket, connection_id: str) -> None:
        """
        Send periodic pings to keep connection alive and detect stale connections.

        Improvements:
        - Lock-free pong time check (read only, atomic in Python)
        - Periodic health logging for debugging long operations
        - Graceful close with proper close frame on stale detection

        Args:
            websocket: WebSocket to ping
            connection_id: Connection identifier for logging
        """
        logger.info(
            f"[{connection_id}] Ping loop started "
            f"(interval={PING_INTERVAL_SECONDS}s, timeout={PONG_TIMEOUT_SECONDS}s)"
        )

        try:
            while True:
                await asyncio.sleep(PING_INTERVAL_SECONDS)

                # Lock-free stale check - reading last_pong_time is atomic
                # We only need the lock for structural modifications (add/remove)
                conn_state = self._connection_states.get(websocket)
                if not conn_state:
                    logger.warning(f"[{connection_id}] Connection state not found, stopping ping loop")
                    break

                if conn_state.is_stale():
                    age = conn_state.get_age_since_last_pong()
                    logger.warning(
                        f"[{connection_id}] Connection is stale "
                        f"(no pong for {age:.1f}s > {PONG_TIMEOUT_SECONDS}s), closing"
                    )
                    # Send close frame before breaking
                    try:
                        await websocket.close(code=1000, reason="Connection stale - no pong received")
                    except Exception as e:
                        logger.debug(f"[{connection_id}] Error sending close frame: {e}")
                    break

                # Send ping and track it
                try:
                    conn_state.pings_sent += 1
                    conn_state.last_ping_sent = time.time()
                    await websocket.send_json({"type": "ping"})
                    logger.debug(f"[{connection_id}] Sent ping #{conn_state.pings_sent}")

                    # Periodic health logging (every 4 pings = ~60s)
                    if conn_state.pings_sent % 4 == 0:
                        age = conn_state.get_age_since_last_pong()
                        logger.info(
                            f"[{connection_id}] Connection health: "
                            f"pings_sent={conn_state.pings_sent}, "
                            f"pongs_received={conn_state.pongs_received}, "
                            f"last_pong_age={age:.1f}s"
                        )
                except Exception as e:
                    logger.warning(f"[{connection_id}] Failed to send ping: {e}")
                    break

        except asyncio.CancelledError:
            logger.debug(f"[{connection_id}] Ping loop cancelled")
            raise
        except Exception as e:
            logger.error(f"[{connection_id}] Ping loop error: {e}")
        finally:
            conn_state = self._connection_states.get(websocket)
            if conn_state:
                logger.info(
                    f"[{connection_id}] Ping loop ended after {conn_state.pings_sent} pings, "
                    f"{conn_state.pongs_received} pongs received"
                )

    def _update_pong_time(self, websocket: WebSocket) -> None:
        """
        Update last pong time for a connection.

        Lock-free update - modifying a float is atomic in Python.

        Args:
            websocket: WebSocket that sent the pong
        """
        conn_state = self._connection_states.get(websocket)
        if conn_state:
            conn_state.last_pong_time = time.time()
            conn_state.pongs_received += 1
            # Calculate round-trip time if we have a recent ping
            rtt_ms = (conn_state.last_pong_time - conn_state.last_ping_sent) * 1000
            logger.debug(
                f"[{conn_state.connection_id}] Received pong "
                f"(#{conn_state.pongs_received}, RTT={rtt_ms:.1f}ms)"
            )

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """
        Broadcast message to all connected clients.

        Args:
            message: Message dictionary to send
        """
        if not self.active_connections:
            return

        dead_connections: Set[WebSocket] = set()

        async with self._lock:
            for websocket in self.active_connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to WebSocket: {e}")
                    dead_connections.add(websocket)

            # Clean up dead connections
            self.active_connections -= dead_connections

        if dead_connections:
            logger.info(f"Cleaned up {len(dead_connections)} dead connections")

    async def handle_message(
        self,
        websocket: WebSocket,
        data: Dict[str, Any]
    ) -> None:
        """
        Handle incoming client message.

        Supported message types:
        - retry: Retry a failed queue item
        - cancel: Cancel a pending queue item
        - dismiss: Dismiss a failed queue item
        - refresh: Request fresh queue state
        - ping: Client-initiated keepalive (server responds with pong)
        - pong: Response to server-initiated ping (updates last_pong_time)

        Args:
            websocket: WebSocket that sent the message
            data: Parsed JSON message
        """
        msg_type = data.get("type", "")
        payload = data.get("payload", {})

        try:
            if msg_type == "retry":
                queue_id = payload.get("queue_id")
                if queue_id:
                    item = await self.queue_manager.retry(queue_id)
                    if item:
                        await websocket.send_json({
                            "type": "action_result",
                            "payload": {
                                "action": "retry",
                                "success": True,
                                "queue_id": queue_id
                            }
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "payload": {
                                "message": f"Cannot retry {queue_id}: not found or not failed"
                            }
                        })

            elif msg_type == "cancel":
                queue_id = payload.get("queue_id")
                if queue_id:
                    success = await self.queue_manager.cancel(queue_id)
                    await websocket.send_json({
                        "type": "action_result",
                        "payload": {
                            "action": "cancel",
                            "success": success,
                            "queue_id": queue_id
                        }
                    })

            elif msg_type == "dismiss":
                queue_id = payload.get("queue_id")
                if queue_id:
                    success = await self.queue_manager.dismiss_failed(queue_id)
                    await websocket.send_json({
                        "type": "action_result",
                        "payload": {
                            "action": "dismiss",
                            "success": success,
                            "queue_id": queue_id
                        }
                    })

            elif msg_type == "refresh":
                # Send fresh state to requesting client only
                state = await self.queue_manager.get_state()
                await websocket.send_json({
                    "type": "queue_state",
                    "payload": state.to_dict()
                })

            elif msg_type == "ping":
                # Client-initiated keepalive ping
                await websocket.send_json({"type": "pong"})

            elif msg_type == "pong":
                # Response to server-initiated ping
                self._update_pong_time(websocket)

            else:
                logger.warning(f"Unknown WebSocket message type: {msg_type}")
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": f"Unknown message type: {msg_type}"}
                })

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"message": str(e)}
                })
            except Exception:
                pass  # Connection may be closed

    async def run_connection(self, websocket: WebSocket) -> None:
        """
        Run WebSocket connection lifecycle.

        Handles connection, message loop, and disconnection.
        Includes enhanced logging for debugging connection issues.

        Args:
            websocket: FastAPI WebSocket instance
        """
        connection_id = await self.connect(websocket)
        messages_received = 0

        try:
            while True:
                # Receive and parse message
                raw_data = await websocket.receive_text()
                messages_received += 1

                try:
                    data = json.loads(raw_data)
                    await self.handle_message(websocket, data)
                except json.JSONDecodeError:
                    logger.warning(f"[{connection_id}] Received invalid JSON")
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"message": "Invalid JSON"}
                    })

        except WebSocketDisconnect as e:
            logger.info(
                f"[{connection_id}] WebSocket disconnected by client "
                f"(code={getattr(e, 'code', 'unknown')}, messages={messages_received})"
            )
        except Exception as e:
            logger.error(f"[{connection_id}] WebSocket error: {e}")
        finally:
            await self.disconnect(websocket)
            logger.info(
                f"[{connection_id}] Connection lifecycle ended, "
                f"total messages received: {messages_received}"
            )

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)
