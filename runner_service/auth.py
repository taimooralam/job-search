"""
Authentication Module

Handles API authentication using shared secret tokens.
Uses centralized config for settings validation.
Includes WebSocket-specific authentication for real-time endpoints.
"""

import logging
from typing import Optional, Tuple

from fastapi import HTTPException, Security, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import settings


logger = logging.getLogger(__name__)
security = HTTPBearer()


def get_runner_secret() -> str:
    """Get the runner API secret from validated config."""
    if not settings.runner_api_secret:
        raise ValueError(
            "RUNNER_API_SECRET environment variable is required for authentication"
        )
    return settings.runner_api_secret


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> HTTPAuthorizationCredentials:
    """
    Verify shared secret token.

    Raises HTTP 401 if token is invalid.

    Args:
        credentials: Bearer token from request header

    Returns:
        The credentials if valid

    Raises:
        HTTPException: 401 if token is invalid
    """
    # Check if auth is required using validated config
    if not settings.auth_required:
        # Auth not required in development without secret
        return credentials

    try:
        expected_secret = get_runner_secret()
    except ValueError:
        # Secret not configured but auth is required
        raise HTTPException(
            status_code=500,
            detail="Server authentication not configured"
        )

    if credentials.credentials != expected_secret:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )

    return credentials


def verify_websocket_token(websocket: WebSocket) -> Tuple[bool, Optional[str]]:
    """
    Verify authentication token from WebSocket headers.

    WebSocket connections pass auth via headers during handshake.
    Extracts and validates the Bearer token from the Authorization header.

    Args:
        websocket: FastAPI WebSocket instance

    Returns:
        Tuple of (is_valid, error_message):
        - (True, None) if authentication passes
        - (False, "error message") if authentication fails
    """
    # Check if auth is required
    if not settings.auth_required:
        logger.debug("[WS Auth] Auth not required, allowing connection")
        return True, None

    # Get Authorization header
    auth_header = websocket.headers.get("authorization", "")

    if not auth_header:
        logger.warning("[WS Auth] Missing Authorization header")
        return False, "Missing Authorization header"

    # Parse Bearer token
    if not auth_header.lower().startswith("bearer "):
        logger.warning("[WS Auth] Invalid Authorization header format")
        return False, "Invalid Authorization header format (expected: Bearer <token>)"

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Validate token
    try:
        expected_secret = get_runner_secret()
    except ValueError as e:
        logger.error(f"[WS Auth] Server config error: {e}")
        return False, "Server authentication not configured"

    if token != expected_secret:
        logger.warning("[WS Auth] Invalid token provided")
        return False, "Invalid authentication token"

    logger.debug("[WS Auth] Authentication successful")
    return True, None
