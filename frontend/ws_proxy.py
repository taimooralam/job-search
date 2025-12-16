"""
WebSocket Proxy for Queue State.

Provides a Flask WebSocket endpoint that proxies to the FastAPI runner service.
Uses flask-sock for WebSocket support and websocket-client for backend connection.

Includes keepalive mechanism with ping/pong messages to detect stale connections.
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
PING_INTERVAL_SECONDS = 20  # Send ping every 20 seconds
STALE_TIMEOUT_SECONDS = 30  # Close connection if no activity for 30 seconds

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
    """
    runner_ws: Optional[ws_client.WebSocket] = None
    receive_thread: Optional[threading.Thread] = None
    ping_thread: Optional[threading.Thread] = None
    should_close = threading.Event()

    # Activity tracking with thread synchronization
    activity_lock = threading.Lock()
    last_activity = {
        "browser": time.time(),
        "runner": time.time(),
    }

    def update_activity(source: str) -> None:
        """Update last activity timestamp for a source."""
        with activity_lock:
            last_activity[source] = time.time()

    def get_last_activity() -> dict:
        """Get copy of last activity timestamps."""
        with activity_lock:
            return last_activity.copy()

    def ping_loop():
        """Background thread to send keepalive pings and detect stale connections."""
        nonlocal runner_ws
        while not should_close.is_set():
            # Wait for ping interval or until close signal
            should_close.wait(PING_INTERVAL_SECONDS)
            if should_close.is_set():
                break

            current_time = time.time()
            timestamps = get_last_activity()

            # Check for stale connections
            browser_stale = (current_time - timestamps["browser"]) > STALE_TIMEOUT_SECONDS
            runner_stale = (current_time - timestamps["runner"]) > STALE_TIMEOUT_SECONDS

            if browser_stale or runner_stale:
                stale_source = "browser" if browser_stale else "runner"
                logger.warning(
                    f"Stale connection detected ({stale_source}), "
                    f"no activity for >{STALE_TIMEOUT_SECONDS}s. Closing connections."
                )
                should_close.set()
                break

            # Send ping to browser
            try:
                ping_msg = json.dumps({"type": "ping"})
                ws.send(ping_msg)
                logger.debug("Sent ping to browser")
            except Exception as e:
                if not should_close.is_set():
                    logger.error(f"Failed to send ping to browser: {e}")
                    should_close.set()
                break

            # Send ping to runner
            try:
                if runner_ws:
                    runner_ws.send(ping_msg)
                    logger.debug("Sent ping to runner")
            except Exception as e:
                if not should_close.is_set():
                    logger.error(f"Failed to send ping to runner: {e}")
                    should_close.set()
                break

    def forward_from_runner():
        """Forward messages from runner to browser."""
        nonlocal runner_ws
        try:
            while not should_close.is_set():
                if runner_ws is None:
                    break

                try:
                    # Receive with timeout to allow checking should_close
                    runner_ws.settimeout(1.0)
                    message = runner_ws.recv()
                    if message:
                        # Update activity timestamp
                        update_activity("runner")

                        # Parse message to check for pong
                        try:
                            msg_data = json.loads(message)
                            if msg_data.get("type") == "pong":
                                # Pong received, activity already updated
                                # Forward pong to browser as well
                                logger.debug("Received pong from runner")
                        except (json.JSONDecodeError, TypeError):
                            pass  # Not JSON, just forward it

                        # Forward all messages to browser
                        ws.send(message)
                except WebSocketTimeoutException:
                    continue  # Check should_close and try again
                except WebSocketConnectionClosedException:
                    logger.info("Runner WebSocket connection closed")
                    break
                except Exception as e:
                    if not should_close.is_set():
                        logger.error(f"Error receiving from runner: {e}")
                    break
        except Exception as e:
            logger.error(f"Runner forward thread error: {e}")
        finally:
            should_close.set()

    try:
        # Connect to runner WebSocket
        runner_ws_url = get_runner_ws_url()
        logger.info(f"Connecting to runner WebSocket: {runner_ws_url}")

        # Build headers for authentication
        headers = {}
        if RUNNER_API_SECRET:
            headers["Authorization"] = f"Bearer {RUNNER_API_SECRET}"

        runner_ws = ws_client.create_connection(
            runner_ws_url,
            header=headers,
            timeout=10,
        )
        logger.info("Connected to runner WebSocket")

        # Start thread to forward messages from runner to browser
        receive_thread = threading.Thread(target=forward_from_runner, daemon=True)
        receive_thread.start()

        # Start keepalive ping thread
        ping_thread = threading.Thread(target=ping_loop, daemon=True)
        ping_thread.start()

        # Main loop: forward messages from browser to runner
        while not should_close.is_set():
            try:
                # Receive from browser (flask-sock)
                message = ws.receive(timeout=1.0)
                if message is None:
                    # Connection closed by browser
                    logger.info("Browser WebSocket connection closed")
                    break

                # Update browser activity timestamp
                update_activity("browser")

                # Check if this is a pong response
                try:
                    msg_data = json.loads(message)
                    if msg_data.get("type") == "pong":
                        # Pong received, activity already updated
                        # Forward pong to runner as well
                        logger.debug("Received pong from browser")
                except (json.JSONDecodeError, TypeError):
                    pass  # Not JSON, just forward it

                # Forward all messages to runner
                if runner_ws:
                    runner_ws.send(message)

            except Exception as e:
                # Check if it's just a timeout
                if "timed out" in str(e).lower():
                    continue
                logger.error(f"Error in browser receive loop: {e}")
                break

    except WebSocketException as e:
        logger.error(f"Failed to connect to runner WebSocket: {e}")
        # Send error to browser
        try:
            ws.send(json.dumps({
                "type": "error",
                "payload": {"message": f"Cannot connect to runner: {e}"}
            }))
        except Exception:
            pass

    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
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

        # Close runner connection
        if runner_ws:
            try:
                runner_ws.close()
            except Exception:
                pass

        # Wait for receive thread to finish
        if receive_thread and receive_thread.is_alive():
            receive_thread.join(timeout=2.0)

        # Wait for ping thread to finish
        if ping_thread and ping_thread.is_alive():
            ping_thread.join(timeout=2.0)

        logger.info("WebSocket proxy connection closed")
