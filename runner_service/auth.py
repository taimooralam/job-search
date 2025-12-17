"""
Authentication Module

Handles API authentication using shared secret tokens.
Uses centralized config for settings validation.
"""

import logging

from fastapi import HTTPException, Security
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
