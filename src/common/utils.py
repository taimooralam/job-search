"""
Common utility functions for the Job Intelligence Pipeline.

This module contains shared helper functions used across multiple layers
to ensure consistent behavior throughout the pipeline.
"""

import asyncio
import concurrent.futures
from typing import Coroutine, TypeVar

T = TypeVar('T')


def run_async(coro: Coroutine[None, None, T]) -> T:
    """
    Run an async coroutine from a sync context, handling nested event loops.

    This helper solves the "asyncio.run() cannot be called from a running event loop"
    error that occurs when sync code calls async functions from within an async context
    (e.g., FastAPI endpoints calling synchronous LangGraph nodes that internally use async).

    Strategy:
    1. If no event loop is running: use asyncio.run() (simple case)
    2. If an event loop IS running: use a thread pool executor to run the coroutine
       in a new thread with its own event loop

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine

    Example:
        >>> async def fetch_data():
        ...     return "data"
        >>> result = run_async(fetch_data())  # Works from both sync and async contexts
    """
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - we can use asyncio.run() directly
        return asyncio.run(coro)

    # There's already a running loop - use thread pool to avoid nesting
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def sanitize_path_component(value: str, max_length: int = 80) -> str:
    """
    Sanitize a string for use as a filesystem path component.

    Replaces unsafe characters and truncates to max_length to ensure
    consistent folder/file naming across all pipeline layers.

    Args:
        value: The string to sanitize (e.g., company name, role title)
        max_length: Maximum length of the sanitized string (default: 80)

    Returns:
        A filesystem-safe string suitable for use in paths

    Example:
        >>> sanitize_path_component("Technology Strategy/Enterprise Architect")
        'Technology_Strategy_Enterprise_Architect'
        >>> sanitize_path_component("Director of Engineering (Software)")
        'Director_of_Engineering__Software_'
    """
    import re
    # Remove all special characters except word chars, spaces, and hyphens
    # This matches the frontend's sanitization for consistency
    safe = re.sub(r'[^\w\s-]', '_', value)
    # Replace spaces with underscores
    safe = safe.replace(" ", "_")
    # Truncate to max length
    safe = safe[:max_length]
    # Return "unknown" if empty or only underscores/spaces
    if not safe or safe.replace("_", "").replace(" ", "") == "":
        return "unknown"
    return safe
