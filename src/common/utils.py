"""
Common utility functions for the Job Intelligence Pipeline.

This module contains shared helper functions used across multiple layers
to ensure consistent behavior throughout the pipeline.
"""


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
    return safe[:max_length] or "unknown"
