"""
Common utility functions for the Job Intelligence Pipeline.

This module contains shared helper functions used across multiple layers
to ensure consistent behavior throughout the pipeline.

Includes:
- Async execution helpers
- Path sanitization
- Type coercion for LLM outputs, YAML/JSON data, and MongoDB documents
"""

import asyncio
import concurrent.futures
from typing import Any, Coroutine, Dict, List, Optional, TypeVar, Union

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


# =============================================================================
# Type Coercion Utilities
# =============================================================================
# These functions handle inconsistent types from LLM outputs, YAML/JSON data,
# and MongoDB documents. LLMs frequently return wrong types (string instead of
# list, int instead of string, etc.) and these helpers normalize to expected types.


def coerce_to_list(
    value: Any,
    separator: str = ",",
    strip: bool = True,
    filter_empty: bool = True,
) -> List[str]:
    """
    Safely convert any value to a list of strings.

    Handles common LLM output inconsistencies:
    - String "a, b, c" → ["a", "b", "c"]
    - Single string "value" → ["value"]
    - List ["a", "b"] → ["a", "b"] (unchanged)
    - None → []
    - Integer/float → [str(value)]
    - Dict → [str(value)] (fallback)

    Args:
        value: The value to convert (can be any type)
        separator: Delimiter for splitting strings (default: ",")
        strip: Whether to strip whitespace from each element (default: True)
        filter_empty: Whether to remove empty strings (default: True)

    Returns:
        List of strings

    Examples:
        >>> coerce_to_list("python, java, kubernetes")
        ['python', 'java', 'kubernetes']
        >>> coerce_to_list(["Python", "Java"])
        ['Python', 'Java']
        >>> coerce_to_list(None)
        []
        >>> coerce_to_list("single_value")
        ['single_value']
    """
    if value is None:
        return []

    if isinstance(value, list):
        # Ensure all elements are strings
        result = []
        for item in value:
            if item is None:
                continue
            str_item = str(item) if not isinstance(item, str) else item
            if strip:
                str_item = str_item.strip()
            if filter_empty and not str_item:
                continue
            result.append(str_item)
        return result

    if isinstance(value, str):
        if separator in value:
            # Split by separator
            parts = value.split(separator)
        else:
            # Single value - wrap in list
            parts = [value]
        result = []
        for part in parts:
            str_part = part.strip() if strip else part
            if filter_empty and not str_part:
                continue
            result.append(str_part)
        return result

    if isinstance(value, (tuple, set, frozenset)):
        # Convert iterable to list
        return coerce_to_list(list(value), separator, strip, filter_empty)

    # Fallback: convert to string and wrap in list
    try:
        str_value = str(value)
        if strip:
            str_value = str_value.strip()
        if filter_empty and not str_value:
            return []
        return [str_value]
    except Exception:
        return []


def coerce_to_dict(
    value: Any,
    default: Optional[Dict] = None,
) -> Dict:
    """
    Safely convert a value to a dictionary.

    Handles:
    - Dict → Dict (unchanged)
    - None → default (or {})
    - String (JSON) → parsed dict
    - Other → default (or {})

    Args:
        value: The value to convert
        default: Default value if conversion fails (default: {})

    Returns:
        Dictionary

    Examples:
        >>> coerce_to_dict({"key": "value"})
        {'key': 'value'}
        >>> coerce_to_dict(None)
        {}
        >>> coerce_to_dict('{"key": "value"}')
        {'key': 'value'}
    """
    if default is None:
        default = {}

    if value is None:
        return default

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        # Try to parse as JSON
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return default

    return default


def coerce_to_str(
    value: Any,
    default: str = "",
    strip: bool = True,
) -> str:
    """
    Safely convert a value to a string.

    Handles:
    - String → String (optionally stripped)
    - None → default
    - List → first element as string (or joined)
    - Other → str(value)

    Args:
        value: The value to convert
        default: Default value if conversion fails (default: "")
        strip: Whether to strip whitespace (default: True)

    Returns:
        String value

    Examples:
        >>> coerce_to_str("  hello  ")
        'hello'
        >>> coerce_to_str(None)
        ''
        >>> coerce_to_str(["first", "second"])
        'first'
        >>> coerce_to_str(123)
        '123'
    """
    if value is None:
        return default

    if isinstance(value, str):
        return value.strip() if strip else value

    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return default
        # Return first element as string
        first = value[0]
        if first is None:
            return default
        result = str(first) if not isinstance(first, str) else first
        return result.strip() if strip else result

    try:
        result = str(value)
        return result.strip() if strip else result
    except Exception:
        return default


def safe_get_nested(
    data: Dict,
    *keys: str,
    default: Any = None,
    coerce_type: Optional[type] = None,
) -> Any:
    """
    Safely get a nested value from a dictionary with optional type coercion.

    Handles MongoDB documents and LLM outputs where nested structures may
    be None, missing, or have unexpected types.

    Args:
        data: The dictionary to traverse
        *keys: Keys to traverse (e.g., "contact", "email")
        default: Default value if path doesn't exist
        coerce_type: If provided, coerce result to this type (list, dict, str)

    Returns:
        The nested value, or default if not found

    Examples:
        >>> data = {"contact": {"email": "test@example.com"}}
        >>> safe_get_nested(data, "contact", "email")
        'test@example.com'
        >>> safe_get_nested(data, "contact", "phone", default="N/A")
        'N/A'
        >>> safe_get_nested({"skills": "python, java"}, "skills", coerce_type=list)
        ['python', 'java']
    """
    current = data

    for key in keys:
        if current is None:
            return default
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    if current is None:
        return default

    # Apply type coercion if requested
    if coerce_type is list:
        return coerce_to_list(current)
    elif coerce_type is dict:
        return coerce_to_dict(current, default if isinstance(default, dict) else {})
    elif coerce_type is str:
        return coerce_to_str(current, default if isinstance(default, str) else "")

    return current
