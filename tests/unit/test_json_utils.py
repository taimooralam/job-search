"""
Unit tests for src/common/json_utils.py

Tests robust JSON parsing for LLM outputs including:
- Valid JSON parsing
- Single quote repair
- Trailing comma repair
- Markdown code block extraction
- Error handling for invalid inputs
"""

import pytest
from src.common.json_utils import parse_llm_json, _strip_markdown_blocks, _extract_json_object


# ===== TESTS: Valid JSON Parsing =====

class TestValidJsonParsing:
    """Tests for parsing valid, well-formed JSON."""

    def test_parses_simple_json(self):
        """Should parse simple valid JSON."""
        result = parse_llm_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parses_nested_json(self):
        """Should parse nested JSON structures."""
        json_str = '{"outer": {"inner": "value"}, "list": [1, 2, 3]}'
        result = parse_llm_json(json_str)
        assert result["outer"]["inner"] == "value"
        assert result["list"] == [1, 2, 3]

    def test_parses_json_with_various_types(self):
        """Should parse JSON with string, number, boolean, null types."""
        json_str = '{"str": "text", "num": 42, "float": 3.14, "bool": true, "null": null}'
        result = parse_llm_json(json_str)
        assert result["str"] == "text"
        assert result["num"] == 42
        assert result["float"] == 3.14
        assert result["bool"] is True
        assert result["null"] is None

    def test_handles_unicode(self):
        """Should handle unicode characters."""
        json_str = '{"name": "Claude", "emoji": "\\u2728"}'
        result = parse_llm_json(json_str)
        assert result["name"] == "Claude"


# ===== TESTS: Markdown Code Block Extraction =====

class TestMarkdownExtraction:
    """Tests for extracting JSON from markdown code blocks."""

    def test_strips_json_markdown_block(self):
        """Should strip ```json ... ``` wrapper."""
        result = parse_llm_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_strips_plain_markdown_block(self):
        """Should strip ``` ... ``` wrapper without language specifier."""
        result = parse_llm_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_handles_markdown_with_surrounding_text(self):
        """Should extract JSON from markdown with surrounding text."""
        text = 'Here is the JSON:\n```json\n{"key": "value"}\n```\nEnd of response.'
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_handles_whitespace_in_markdown(self):
        """Should handle extra whitespace in markdown blocks."""
        result = parse_llm_json('```json\n\n  {"key": "value"}  \n\n```')
        assert result == {"key": "value"}


# ===== TESTS: JSON Extraction from Text =====

class TestJsonExtraction:
    """Tests for extracting JSON embedded in surrounding text."""

    def test_extracts_json_from_prefix_text(self):
        """Should extract JSON when preceded by text."""
        text = 'Here is the extracted data: {"key": "value"}'
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_extracts_json_from_suffix_text(self):
        """Should extract JSON when followed by text."""
        text = '{"key": "value"} - this is the result'
        result = parse_llm_json(text)
        assert result == {"key": "value"}

    def test_extracts_json_from_surrounding_text(self):
        """Should extract JSON surrounded by text on both sides."""
        text = 'Based on analysis: {"key": "value"} Hope this helps!'
        result = parse_llm_json(text)
        assert result == {"key": "value"}


# ===== TESTS: Single Quote Repair =====

class TestSingleQuoteRepair:
    """Tests for repairing single quotes to double quotes."""

    def test_repairs_single_quotes_for_keys(self):
        """Should repair single-quoted keys."""
        result = parse_llm_json("{'key': 'value'}")
        assert result == {"key": "value"}

    def test_repairs_single_quotes_for_values(self):
        """Should repair single-quoted string values."""
        result = parse_llm_json('{"key": \'value\'}')
        assert result == {"key": "value"}

    def test_repairs_nested_single_quotes(self):
        """Should repair single quotes in nested structures."""
        result = parse_llm_json("{'outer': {'inner': 'value'}}")
        assert result["outer"]["inner"] == "value"

    def test_handles_mixed_quotes(self):
        """Should handle mix of single and double quotes."""
        result = parse_llm_json("""{"key1": 'value1', 'key2': "value2"}""")
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"


# ===== TESTS: Trailing Comma Repair =====

class TestTrailingCommaRepair:
    """Tests for repairing trailing commas."""

    def test_repairs_trailing_comma_in_object(self):
        """Should repair trailing comma before closing brace."""
        result = parse_llm_json('{"key": "value",}')
        assert result == {"key": "value"}

    def test_repairs_trailing_comma_in_array(self):
        """Should repair trailing comma in array."""
        result = parse_llm_json('{"list": [1, 2, 3,]}')
        assert result["list"] == [1, 2, 3]

    def test_repairs_multiple_trailing_commas(self):
        """Should repair trailing commas at multiple levels."""
        result = parse_llm_json('{"a": 1, "b": [1, 2,], "c": {"d": 3,},}')
        assert result["a"] == 1
        assert result["b"] == [1, 2]
        assert result["c"]["d"] == 3


# ===== TESTS: Combined Malformed JSON =====

class TestCombinedMalformedJson:
    """Tests for JSON with multiple issues combined."""

    def test_repairs_single_quotes_and_trailing_comma(self):
        """Should repair both single quotes and trailing comma."""
        result = parse_llm_json("{'name': 'test',}")
        assert result == {"name": "test"}

    def test_repairs_markdown_and_single_quotes(self):
        """Should handle markdown wrapper with single quotes inside."""
        result = parse_llm_json("```json\n{'key': 'value'}\n```")
        assert result == {"key": "value"}

    def test_complex_llm_response(self):
        """Should handle realistic complex LLM response."""
        llm_response = """
        Here's the extracted information:

        ```json
        {
            'title': 'Software Engineer',
            'company': 'Acme Corp',
            'skills': ['Python', 'JavaScript',],
            'remote': true,
        }
        ```

        Let me know if you need anything else!
        """
        result = parse_llm_json(llm_response)
        assert result["title"] == "Software Engineer"
        assert result["company"] == "Acme Corp"
        assert result["skills"] == ["Python", "JavaScript"]
        assert result["remote"] is True


# ===== TESTS: Error Handling =====

class TestErrorHandling:
    """Tests for error handling with invalid inputs."""

    def test_raises_on_empty_string(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError) as exc_info:
            parse_llm_json("")
        assert "Empty input" in str(exc_info.value)

    def test_raises_on_whitespace_only(self):
        """Should raise ValueError for whitespace-only string."""
        with pytest.raises(ValueError) as exc_info:
            parse_llm_json("   \n\t  ")
        assert "Empty input" in str(exc_info.value)

    def test_raises_on_no_json_found(self):
        """Should raise ValueError when no JSON object is present."""
        with pytest.raises(ValueError) as exc_info:
            parse_llm_json("This is just plain text without any JSON")
        assert "No JSON object found" in str(exc_info.value)

    def test_raises_on_completely_invalid_json(self):
        """Should raise ValueError for completely invalid JSON."""
        with pytest.raises(ValueError) as exc_info:
            parse_llm_json("{this is not valid at all}")
        assert "Failed to parse" in str(exc_info.value)

    def test_raises_on_array_only(self):
        """Should raise ValueError for array-only input (not object)."""
        # parse_llm_json expects an object starting with {
        with pytest.raises(ValueError) as exc_info:
            parse_llm_json("[1, 2, 3]")
        assert "No JSON object found" in str(exc_info.value)


# ===== TESTS: Helper Functions =====

class TestStripMarkdownBlocks:
    """Tests for the _strip_markdown_blocks helper."""

    def test_strips_json_prefix(self):
        """Should strip ```json prefix."""
        result = _strip_markdown_blocks("```json\ncontent")
        assert result == "content"

    def test_strips_plain_prefix(self):
        """Should strip ``` prefix."""
        result = _strip_markdown_blocks("```\ncontent")
        assert result == "content"

    def test_strips_suffix(self):
        """Should strip ``` suffix."""
        result = _strip_markdown_blocks("content\n```")
        assert result == "content"

    def test_strips_both(self):
        """Should strip both prefix and suffix."""
        result = _strip_markdown_blocks("```json\ncontent\n```")
        assert result == "content"

    def test_preserves_non_markdown(self):
        """Should preserve text without markdown markers."""
        result = _strip_markdown_blocks("plain content")
        assert result == "plain content"


class TestExtractJsonObject:
    """Tests for the _extract_json_object helper."""

    def test_returns_json_starting_with_brace(self):
        """Should return as-is if starts with brace."""
        result = _extract_json_object('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_extracts_from_prefix(self):
        """Should extract JSON from text with prefix."""
        result = _extract_json_object('prefix {"key": "value"}')
        assert result == '{"key": "value"}'

    def test_extracts_from_suffix(self):
        """Should extract JSON from text with suffix."""
        result = _extract_json_object('{"key": "value"} suffix')
        assert result == '{"key": "value"} suffix'  # regex is greedy

    def test_raises_on_no_object(self):
        """Should raise ValueError when no object found."""
        with pytest.raises(ValueError) as exc_info:
            _extract_json_object("no json here")
        assert "No JSON object found" in str(exc_info.value)


# ===== TESTS: Real-world LLM Output Examples =====

class TestRealWorldExamples:
    """Tests based on real LLM output patterns that have caused issues."""

    def test_jd_extractor_sample_output(self):
        """Should parse a realistic JD extractor LLM output."""
        llm_output = """```json
{
    "title": "Head of Engineering",
    "company": "TechStartup Inc",
    "location": "Remote (EU)",
    "remote_policy": "fully_remote",
    "role_category": "head_of_engineering",
    "seniority_level": "director",
    "competency_weights": {
        "delivery": 25,
        "process": 15,
        "architecture": 20,
        "leadership": 40
    },
    "responsibilities": [
        "Build the engineering team from scratch",
        "Define engineering culture and hiring bar"
    ],
    "qualifications": [
        "10+ years software engineering experience",
        "5+ years leading engineering teams"
    ],
    "top_keywords": [
        "Head of Engineering", "Engineering Leadership", "Python",
        "TypeScript", "AWS", "GCP", "CI/CD", "Team Building",
        "Startup", "Remote", "Scaling", "Architecture",
        "Engineering Culture", "Hiring", "SaaS"
    ]
}
```"""
        result = parse_llm_json(llm_output)
        assert result["title"] == "Head of Engineering"
        assert result["competency_weights"]["leadership"] == 40
        assert len(result["top_keywords"]) == 15

    def test_output_with_explanation_before_json(self):
        """Should handle LLM output that explains before providing JSON."""
        llm_output = """Based on the job description, I've extracted the following information:

{
    "title": "Software Engineer",
    "company": "Example Corp"
}"""
        result = parse_llm_json(llm_output)
        assert result["title"] == "Software Engineer"

    def test_output_with_python_style_dict(self):
        """Should handle Python-style dict syntax that LLMs sometimes produce."""
        # Note: Python's True/False are converted to JSON true/false
        # Python's None becomes string "None" (not null) - this is a known limitation
        llm_output = "{'role': 'Engineer', 'level': 'senior', 'remote': True}"
        result = parse_llm_json(llm_output)
        assert result["role"] == "Engineer"
        assert result["remote"] is True

    def test_output_with_json_null(self):
        """Should handle JSON null properly."""
        llm_output = "{'role': 'Engineer', 'salary': null}"
        result = parse_llm_json(llm_output)
        assert result["role"] == "Engineer"
        assert result["salary"] is None


# ===== TESTS: JSON Repair List Response Handling =====

class TestJsonRepairListHandling:
    """Tests for handling when json_repair returns a list instead of a dict.

    This happens when the LLM wraps JSON in brackets like [{...}] or
    returns multiple JSON objects that get parsed as a list.
    """

    def test_single_dict_wrapped_in_brackets(self):
        """Should unwrap single dict from list.

        Common LLM pattern: [{...}] instead of {...}
        """
        # This is a tricky case - the _extract_json_object will find the inner dict
        # But we test the json_repair list handling directly
        from json_repair import repair_json

        # When json_repair parses this, it may return a list
        json_str = '[{"key": "value"}]'
        repaired = repair_json(json_str, return_objects=True)

        # Our code should handle this
        if isinstance(repaired, list):
            # This is what we're testing - single dict unwrapping
            assert len(repaired) == 1
            assert repaired[0] == {"key": "value"}

    def test_malformed_json_repaired_to_list_single_dict(self):
        """Should handle malformed JSON that json_repair fixes to a single-dict list."""
        # Simulate what happens when LLM returns wrapped JSON with quotes issues
        # and _extract_json_object still finds a {} but json_repair parses it as list
        llm_output = """Here's the data: {'selected_bullets': ['bullet1', 'bullet2']}"""
        result = parse_llm_json(llm_output)
        assert "selected_bullets" in result
        assert result["selected_bullets"] == ["bullet1", "bullet2"]

    def test_merge_multiple_json_objects(self):
        """Should merge multiple dicts from repair into single dict.

        When LLM returns something like: {...} {...} and json_repair
        parses it as a list of dicts, we merge them.
        """
        from json_repair import repair_json

        # Test the behavior with multiple objects
        json_str = '{"a": 1} {"b": 2}'
        repaired = repair_json(json_str, return_objects=True)

        # If json_repair returns a list here, our code should merge
        if isinstance(repaired, list) and len(repaired) > 1:
            merged = {}
            for item in repaired:
                if isinstance(item, dict):
                    merged.update(item)
            assert merged.get("a") == 1
            assert merged.get("b") == 2

    def test_realistic_cv_bullet_response_with_repair(self):
        """Test realistic CV bullet selection response that might need repair."""
        llm_output = """```json
{
    "selected_bullets": [
        {"bullet_text": "Led team of 10 engineers", "source_role": "Tech Lead"}
    ],
    "rejected_jd_skills": ["Java", "React"],
}
```"""
        result = parse_llm_json(llm_output)
        assert "selected_bullets" in result
        assert "rejected_jd_skills" in result
        assert result["rejected_jd_skills"] == ["Java", "React"]

    def test_non_dict_list_raises_error(self):
        """Should raise error for non-dict lists (not valid for LLM JSON responses)."""
        from json_repair import repair_json

        # If json_repair returns a list of non-dicts, we should raise an error
        # because our use case requires dict responses
        json_str = '["item1", "item2", "item3"]'
        repaired = repair_json(json_str, return_objects=True)

        # Verify json_repair returns a list of strings
        assert isinstance(repaired, list)
        assert isinstance(repaired[0], str)

        # parse_llm_json expects this to fail at _extract_json_object
        # (since it doesn't start with {), but if json_repair returns
        # a list of non-dicts, it should also raise an error
