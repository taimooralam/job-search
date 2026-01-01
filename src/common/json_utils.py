"""
JSON Utilities for LLM Response Parsing.

This module provides robust JSON parsing for LLM outputs which may contain
malformed JSON (single quotes, trailing commas, unquoted keys, etc.).

Uses json-repair library as a fallback when standard json.loads() fails.
"""

import json
import re
from typing import Any, Dict


def parse_llm_json(text: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response with robust error recovery.

    Handles common LLM output issues:
    - Markdown code blocks (```json ... ```)
    - JSON embedded in surrounding text
    - Single quotes instead of double quotes
    - Trailing commas
    - Unquoted keys
    - Other malformed JSON patterns

    Args:
        text: Raw LLM response text that may contain JSON

    Returns:
        Parsed dictionary from the JSON

    Raises:
        ValueError: If no valid JSON can be extracted or repaired

    Example:
        >>> parse_llm_json('```json\\n{"key": "value"}\\n```')
        {'key': 'value'}
        >>> parse_llm_json("{'name': 'test',}")  # Single quotes + trailing comma
        {'name': 'test'}
    """
    if not text or not text.strip():
        raise ValueError("Empty input: no JSON content to parse")

    # Step 1: Strip markdown code blocks
    json_str = _strip_markdown_blocks(text.strip())

    # Step 2: Extract JSON object from surrounding text
    json_str = _extract_json_object(json_str)

    # Step 3: Try standard json.loads() first (fastest path)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass  # Fall through to repair

    # Step 4: Fall back to json-repair for malformed JSON
    try:
        from json_repair import repair_json
        repaired = repair_json(json_str, return_objects=True)

        # repair_json returns the parsed object when return_objects=True
        if isinstance(repaired, dict):
            return repaired
        elif isinstance(repaired, list):
            # LLM sometimes wraps response in brackets: [{...}]
            # Or returns multiple JSON objects that get parsed as a list
            if len(repaired) == 1 and isinstance(repaired[0], dict):
                # Single dict wrapped in brackets - unwrap it
                return repaired[0]
            elif len(repaired) > 0 and isinstance(repaired[0], dict):
                # Multiple dicts - merge them (common LLM pattern)
                merged = {}
                for item in repaired:
                    if isinstance(item, dict):
                        merged.update(item)
                return merged
            else:
                # List of non-dicts (strings, numbers, etc.) - not valid for our use case
                raise ValueError(
                    f"json_repair returned list of non-dict items: {repaired[:3]}..."
                    if len(repaired) > 3 else f"json_repair returned list of non-dict items: {repaired}"
                )
        elif isinstance(repaired, str):
            # Sometimes it returns a repaired string
            return json.loads(repaired)
        else:
            raise ValueError(f"json_repair returned unexpected type: {type(repaired)}")

    except Exception as e:
        raise ValueError(
            f"Failed to parse or repair JSON: {e}\n"
            f"Original text (first 500 chars): {text[:500]}"
        )


def _strip_markdown_blocks(text: str) -> str:
    """
    Remove markdown code block wrappers from text.

    Handles:
    - ```json ... ```
    - ``` ... ```
    - Leading/trailing whitespace

    Args:
        text: Text that may be wrapped in markdown code blocks

    Returns:
        Text with code block markers removed
    """
    result = text

    # Remove ```json prefix
    if result.startswith("```json"):
        result = result[7:]
    # Remove ``` prefix (without language specifier)
    elif result.startswith("```"):
        result = result[3:]

    # Remove ``` suffix
    if result.endswith("```"):
        result = result[:-3]

    return result.strip()


def _extract_json_object(text: str) -> str:
    """
    Extract JSON object from text that may contain surrounding content.

    If the text doesn't start with '{', attempts to find a JSON object
    within the text using regex.

    Args:
        text: Text that may contain a JSON object

    Returns:
        The extracted JSON string

    Raises:
        ValueError: If no JSON object pattern is found
    """
    text = text.strip()

    # If it already starts with {, return as-is
    if text.startswith("{"):
        return text

    # Try to find JSON object in the text
    # Use regex to find content between first { and last }
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json_match.group(0)

    raise ValueError(f"No JSON object found in text: {text[:200]}")
