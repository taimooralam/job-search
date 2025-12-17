"""
WebSocket Proxy for Queue State.

Provides a Flask WebSocket endpoint that proxies to the FastAPI runner service.
Uses flask-sock for WebSocket support and websocket-client for backend connection.

Includes keepalive mechanism with ping/pong messages to detect stale connections.

Reliability Improvements:
- Priority handling for ping/pong messages (processed before regular messages)
- Increased stale timeout for long-running operations (CV generation ~78s)
- Enhanced logging for connection lifecycle debugging
- Separate activity tracking for keepalive vs data messages
"""

import json
import logging
import os
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from flask import Blueprint
from flask_sock import Sock

# Import websocket-client library with alias to avoid naming conflicts
import websocket as ws_client
from websocket import (
    WebSocketException,
    WebSocketTimeoutException,
    WebSocketConnectionClosedException,
)

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
RUNNER_URL = os.getenv("RUNNER_URL", "http://72.61.92.76:8000")
RUNNER_API_SECRET = os.getenv("RUNNER_API_SECRET", "")

# Keepalive configuration
# CV generation can take ~78 seconds, so we need generous timeouts
PING_INTERVAL_SECONDS = 15  # Send ping every 15 seconds (more frequent)
STALE_TIMEOUT_SECONDS = 120  # 2 minutes - allows for long operations + network delays
RECEIVE_TIMEOUT_SECONDS = 0.5  # Faster timeout for more responsive ping handling

# Convert HTTP URL to WebSocket URL
def get_runner_ws_url() -> str:
    """Convert runner HTTP URL to WebSocket URL."""
    ws_url = RUNNER_URL.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_url}/ws/queue"


# Create blueprint and Sock instance
ws_bp = Blueprint("websocket", __name__)
sock = Sock()


def init_websocket(app):
    """
    Initialize WebSocket support on Flask app.

    Must be called during app initialization after blueprint registration.

    Args:
        app: Flask application instance
    """
    sock.init_app(app)
    # Register route AFTER sock is initialized with the app
    sock.route("/ws/queue")(queue_websocket)
    logger.info("WebSocket support initialized at /ws/queue")


def queue_websocket(ws):
    """
    WebSocket proxy endpoint for queue state.

    Establishes bidirectional WebSocket connection:
    - Browser <-> Flask (this endpoint)
    - Flask <-> Runner Service (backend connection)

    Messages are forwarded in both directions.
    Includes keepalive mechanism with ping/pong to detect stale connections.

    Reliability Features:
    - Separate tracking for keepalive (ping/pong) vs data activity
    - Priority handling for ping/pong messages
    - Enhanced logging for connection lifecycle debugging
    - Graceful close with proper close frames
    """
    runner_ws: Optional[ws_client.WebSocket] = None
    receive_thread: Optional[threading.Thread] = None
    ping_thread: Optional[threading.Thread] = None
    should_close = threading.Event()

    # Generate connection ID for logging
    import uuid
    conn_id = uuid.uuid4().hex[:8]

    # Activity tracking with thread synchronization
    # Track keepalive separately from data messages for more accurate stale detection
    activity_lock = threading.Lock()
    last_activity = {
        "browser": time.time(),
        "runner": time.time(),
        "browser_keepalive": time.time(),  # Track ping/pong separately
        "runner_keepalive": time.time(),
    }

    def update_activity(source: str, is_keepalive: bool = False) -> None:
        """Update last activity timestamp for a source."""
        with activity_lock:
            last_activity[source] = time.time()
            if is_keepalive:
                last_activity[f"{source}_keepalive"] = time.time()

    def get_last_activity() -> dict:
        """Get copy of last activity timestamps."""
        with activity_lock:
            return last_activity.copy()

    def ping_loop():
        """Background thread to send keepalive pings and detect stale connections.

        Uses keepalive timestamps for stale detection to be more resilient during
        long-running operations where data messages may be sparse but ping/pong
        continues working.
        """
        nonlocal runner_ws
        ping_count = 0

        logger.info(f"[{conn_id}] Ping loop started (interval={PING_INTERVAL_SECONDS}s, timeout={STALE_TIMEOUT_SECONDS}s)")

        while not should_close.is_set():
            # Wait for ping interval or until close signal
            should_close.wait(PING_INTERVAL_SECONDS)
            if should_close.is_set():
                break

            current_time = time.time()
            timestamps = get_last_activity()
            ping_count += 1

            # Check for stale connections using keepalive timestamps
            # This is more reliable during long operations (CV generation)
            browser_keepalive_age = current_time - timestamps["browser_keepalive"]
            runner_keepalive_age = current_time - timestamps["runner_keepalive"]

            browser_stale = browser_keepalive_age > STALE_TIMEOUT_SECONDS
            runner_stale = runner_keepalive_age > STALE_TIMEOUT_SECONDS

            # Log periodic status for debugging
            if ping_count % 4 == 0:  # Every ~60 seconds
                logger.info(
                    f"[{conn_id}] Connection health: browser_keepalive={browser_keepalive_age:.1f}s, "
                    f"runner_keepalive={runner_keepalive_age:.1f}s, pings_sent={ping_count}"
                )

            if browser_stale or runner_stale:
                stale_source = "browser" if browser_stale else "runner"
                stale_age = browser_keepalive_age if browser_stale else runner_keepalive_age
                logger.warning(
                    f"[{conn_id}] Stale connection detected ({stale_source}), "
                    f"no keepalive for {stale_age:.1f}s (>{STALE_TIMEOUT_SECONDS}s). Closing connections."
                )
                should_close.set()
                break

            # Send ping to browser
            try:
                ping_msg = json.dumps({"type": "ping"})
                ws.send(ping_msg)
                logger.debug(f"[{conn_id}] Sent ping #{ping_count} to browser")
            except Exception as e:
                if not should_close.is_set():
                    logger.error(f"[{conn_id}] Failed to send ping to browser: {e}")
                    should_close.set()
                break

            # Send ping to runner
            try:
                if runner_ws:
                    runner_ws.send(ping_msg)
                    logger.debug(f"[{conn_id}] Sent ping #{ping_count} to runner")
            except Exception as e:
                if not should_close.is_set():
                    logger.error(f"[{conn_id}] Failed to send ping to runner: {e}")
                    should_close.set()
                break

        logger.info(f"[{conn_id}] Ping loop ended after {ping_count} pings")

    def forward_from_runner():
        """Forward messages from runner to browser.

        Uses shorter receive timeout for more responsive ping/pong handling.
        Tracks keepalive messages separately from data messages.
        """
        nonlocal runner_ws
        messages_forwarded = 0

        logger.info(f"[{conn_id}] Runner forward thread started")

        try:
            while not should_close.is_set():
                if runner_ws is None:
                    break

                try:
                    # Use shorter timeout for responsive ping/pong handling
                    runner_ws.settimeout(RECEIVE_TIMEOUT_SECONDS)
                    message = runner_ws.recv()
                    if message:
                        messages_forwarded += 1

                        # Parse message to check for ping/pong (priority messages)
                        is_keepalive = False
                        try:
                            msg_data = json.loads(message)
                            msg_type = msg_data.get("type")

                            if msg_type == "pong":
                                # Pong received from runner, update keepalive timestamp
                                is_keepalive = True
                                logger.debug(f"[{conn_id}] Received pong from runner")
                            elif msg_type == "ping":
                                # Ping from runner (server-initiated), respond and update
                                is_keepalive = True
                                logger.debug(f"[{conn_id}] Received ping from runner, responding with pong")
                                try:
                                    runner_ws.send(json.dumps({"type": "pong"}))
                                except Exception as e:
                                    logger.warning(f"[{conn_id}] Failed to send pong to runner: {e}")

                        except (json.JSONDecodeError, TypeError):
                            pass  # Not JSON, just forward it

                        # Update activity timestamp
                        update_activity("runner", is_keepalive=is_keepalive)

                        # Forward all messages to browser
                        ws.send(message)

                except WebSocketTimeoutException:
                    continue  # Check should_close and try again
                except WebSocketConnectionClosedException:
                    logger.info(f"[{conn_id}] Runner WebSocket connection closed cleanly")
                    break
                except Exception as e:
                    if not should_close.is_set():
                        logger.error(f"[{conn_id}] Error receiving from runner: {e}")
                    break
        except Exception as e:
            logger.error(f"[{conn_id}] Runner forward thread error: {e}")
        finally:
            logger.info(f"[{conn_id}] Runner forward thread ended after {messages_forwarded} messages")
            should_close.set()

    try:
        # Connect to runner WebSocket
        runner_ws_url = get_runner_ws_url()
        logger.info(f"[{conn_id}] Connecting to runner WebSocket: {runner_ws_url}")

        # Build headers for authentication
        headers = {}
        if RUNNER_API_SECRET:
            headers["Authorization"] = f"Bearer {RUNNER_API_SECRET}"

        runner_ws = ws_client.create_connection(
            runner_ws_url,
            header=headers,
            timeout=10,
        )
        logger.info(f"[{conn_id}] Connected to runner WebSocket successfully")

        # Start thread to forward messages from runner to browser
        receive_thread = threading.Thread(target=forward_from_runner, daemon=True)
        receive_thread.start()

        # Start keepalive ping thread
        ping_thread = threading.Thread(target=ping_loop, daemon=True)
        ping_thread.start()

        # Main loop: forward messages from browser to runner
        messages_from_browser = 0
        logger.info(f"[{conn_id}] Browser message loop started")

        while not should_close.is_set():
            try:
                # Receive from browser (flask-sock) with shorter timeout
                message = ws.receive(timeout=RECEIVE_TIMEOUT_SECONDS)
                if message is None:
                    # Connection closed by browser
                    logger.info(f"[{conn_id}] Browser WebSocket connection closed (received None)")
                    break

                messages_from_browser += 1

                # Check if this is a ping/pong (keepalive) message
                is_keepalive = False
                try:
                    msg_data = json.loads(message)
                    msg_type = msg_data.get("type")

                    if msg_type == "pong":
                        # Pong received from browser, update keepalive timestamp
                        is_keepalive = True
                        logger.debug(f"[{conn_id}] Received pong from browser")
                    elif msg_type == "ping":
                        # Ping from browser (client-initiated), respond and update
                        is_keepalive = True
                        logger.debug(f"[{conn_id}] Received ping from browser, responding with pong")
                        try:
                            ws.send(json.dumps({"type": "pong"}))
                        except Exception as e:
                            logger.warning(f"[{conn_id}] Failed to send pong to browser: {e}")

                except (json.JSONDecodeError, TypeError):
                    pass  # Not JSON, just forward it

                # Update browser activity timestamp
                update_activity("browser", is_keepalive=is_keepalive)

                # Forward all messages to runner
                if runner_ws:
                    runner_ws.send(message)

            except Exception as e:
                # Check if it's just a timeout
                if "timed out" in str(e).lower():
                    continue
                logger.error(f"[{conn_id}] Error in browser receive loop: {e}")
                break

        logger.info(f"[{conn_id}] Browser message loop ended after {messages_from_browser} messages")

    except WebSocketException as e:
        logger.error(f"[{conn_id}] Failed to connect to runner WebSocket: {e}")
        # Send error to browser
        try:
            ws.send(json.dumps({
                "type": "error",
                "payload": {"message": f"Cannot connect to runner: {e}"}
            }))
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[{conn_id}] WebSocket proxy error: {e}")
        try:
            ws.send(json.dumps({
                "type": "error",
                "payload": {"message": str(e)}
            }))
        except Exception:
            pass

    finally:
        # Signal threads to stop
        should_close.set()

        # Close runner connection with proper close frame
        if runner_ws:
            try:
                # Send close frame before closing
                runner_ws.close(status=1000, reason="Proxy connection closed")
                logger.debug(f"[{conn_id}] Sent close frame to runner")
            except Exception as e:
                logger.debug(f"[{conn_id}] Error closing runner connection: {e}")

        # Wait for receive thread to finish
        if receive_thread and receive_thread.is_alive():
            receive_thread.join(timeout=2.0)
            if receive_thread.is_alive():
                logger.warning(f"[{conn_id}] Receive thread did not terminate in time")

        # Wait for ping thread to finish
        if ping_thread and ping_thread.is_alive():
            ping_thread.join(timeout=2.0)
            if ping_thread.is_alive():
                logger.warning(f"[{conn_id}] Ping thread did not terminate in time")

        logger.info(f"[{conn_id}] WebSocket proxy connection closed")
