"""
WebSocket Handler for Queue State Broadcasting

Manages WebSocket connections for real-time queue updates.
Handles client messages (retry, cancel, refresh) and broadcasts queue events.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

from .manager import QueueManager

logger = logging.getLogger(__name__)


class QueueWebSocketManager:
    """
    Manages WebSocket connections for queue state updates.

    Provides:
    - Connection lifecycle management
    - Initial state broadcast on connect
    - Event broadcasting to all connected clients
    - Client message handling (retry, cancel, refresh)
    """

    def __init__(self, queue_manager: QueueManager):
        """
        Initialize WebSocket manager.

        Args:
            queue_manager: QueueManager instance for queue operations
        """
        self.queue_manager = queue_manager
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept new WebSocket connection and send initial state.

        Args:
            websocket: FastAPI WebSocket instance
        """
        await websocket.accept()

        async with self._lock:
            self.active_connections.add(websocket)

        logger.info(
            f"WebSocket connected, total connections: {len(self.active_connections)}"
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

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
        """
        async with self._lock:
            self.active_connections.discard(websocket)

        logger.info(
            f"WebSocket disconnected, total connections: {len(self.active_connections)}"
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
                # Keepalive ping
                await websocket.send_json({"type": "pong"})

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
