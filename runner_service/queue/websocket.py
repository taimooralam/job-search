"""
WebSocket Handler for Queue State Broadcasting

Manages WebSocket connections for real-time queue updates.
Handles client messages (retry, cancel, refresh) and broadcasts queue events.
Implements server-side ping to detect stale connections.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

from .manager import QueueManager

logger = logging.getLogger(__name__)

# Ping/pong configuration
PING_INTERVAL_SECONDS = 20
PONG_TIMEOUT_SECONDS = 30


@dataclass
class ConnectionState:
    """Tracks state for a single WebSocket connection."""

    websocket: WebSocket
    ping_task: Optional[asyncio.Task] = None
    last_pong_time: float = field(default_factory=time.time)
    connection_id: str = ""

    def is_stale(self) -> bool:
        """Check if connection is stale (no pong received within timeout)."""
        return time.time() - self.last_pong_time > PONG_TIMEOUT_SECONDS


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

        async with self._lock:
            self._connection_counter += 1
            connection_id = f"conn_{self._connection_counter}"
            self.active_connections.add(websocket)

            # Create connection state and start ping loop
            conn_state = ConnectionState(
                websocket=websocket,
                connection_id=connection_id,
                last_pong_time=time.time(),
            )
            conn_state.ping_task = asyncio.create_task(
                self._ping_loop(websocket, connection_id)
            )
            self._connection_states[websocket] = conn_state

        logger.info(
            f"WebSocket {connection_id} connected, "
            f"total connections: {len(self.active_connections)}"
        )

        # Send initial queue state
        try:
            state = await self.queue_manager.get_state()
            await websocket.send_json({
                "type": "queue_state",
                "payload": state.to_dict()
            })
        except Exception as e:
            logger.error(f"Failed to send initial state: {e}")

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

        Args:
            websocket: WebSocket to ping
            connection_id: Connection identifier for logging
        """
        try:
            while True:
                await asyncio.sleep(PING_INTERVAL_SECONDS)

                # Check if connection is stale before sending ping
                async with self._lock:
                    conn_state = self._connection_states.get(websocket)
                    if conn_state and conn_state.is_stale():
                        logger.warning(
                            f"WebSocket {connection_id} is stale "
                            f"(no pong for {PONG_TIMEOUT_SECONDS}s), closing"
                        )
                        # Mark for cleanup - will be handled by broadcast or explicit close
                        break

                # Send ping
                try:
                    await websocket.send_json({"type": "ping"})
                    logger.debug(f"Sent ping to {connection_id}")
                except Exception as e:
                    logger.warning(f"Failed to send ping to {connection_id}: {e}")
                    break

        except asyncio.CancelledError:
            logger.debug(f"Ping loop cancelled for {connection_id}")
            raise
        except Exception as e:
            logger.error(f"Ping loop error for {connection_id}: {e}")

    def _update_pong_time(self, websocket: WebSocket) -> None:
        """
        Update last pong time for a connection.

        Args:
            websocket: WebSocket that sent the pong
        """
        if websocket in self._connection_states:
            self._connection_states[websocket].last_pong_time = time.time()
            logger.debug(
                f"Received pong from "
                f"{self._connection_states[websocket].connection_id}"
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

        Args:
            websocket: FastAPI WebSocket instance
        """
        await self.connect(websocket)

        try:
            while True:
                # Receive and parse message
                raw_data = await websocket.receive_text()
                try:
                    data = json.loads(raw_data)
                    await self.handle_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"message": "Invalid JSON"}
                    })

        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            await self.disconnect(websocket)

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)
