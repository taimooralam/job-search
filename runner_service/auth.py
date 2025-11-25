"""
Authentication Module

Handles API authentication using shared secret tokens.
"""

import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


security = HTTPBearer()


def get_runner_secret() -> str:
    """Get the runner API secret from environment."""
    secret = os.getenv("RUNNER_API_SECRET")
    if not secret:
        raise ValueError(
            "RUNNER_API_SECRET environment variable is required for authentication"
        )
    return secret


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
    try:
        expected_secret = get_runner_secret()
    except ValueError as e:
        # Secret not configured - for development/testing only
        if os.getenv("ENVIRONMENT") == "development":
            return credentials
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
