"""
Unit tests for skills_taxonomy.py - type coercion for skill aliases.

Tests the _coerce_to_list helper and its usage in get_skill_aliases
and skill_matches methods.
"""

import pytest
from unittest.mock import MagicMock

from src.layer6_v2.skills_taxonomy import SkillsTaxonomy


class TestCoerceToList:
    """Tests for _coerce_to_list helper method."""

    @pytest.fixture
    def taxonomy(self):
        """Create a minimal taxonomy instance for testing."""
        taxonomy = SkillsTaxonomy.__new__(SkillsTaxonomy)
        taxonomy._taxonomy_data = {}
        taxonomy._skill_aliases = {}
        taxonomy._sections = {}
        return taxonomy

    def test_coerce_string_to_list(self, taxonomy):
        """String values are wrapped in a list."""
        result = taxonomy._coerce_to_list("Python")
        assert result == ["Python"]

    def test_coerce_list_unchanged(self, taxonomy):
        """List values are returned unchanged."""
        result = taxonomy._coerce_to_list(["Python", "JavaScript"])
        assert result == ["Python", "JavaScript"]

    def test_coerce_none_to_empty_list(self, taxonomy):
        """None values become empty list."""
        result = taxonomy._coerce_to_list(None)
        assert result == []

    def test_coerce_tuple_to_list(self, taxonomy):
        """Tuple values are converted to list."""
        result = taxonomy._coerce_to_list(("Python", "JavaScript"))
        assert result == ["Python", "JavaScript"]


class TestGetSkillAliasesWithStringAlias:
    """Tests for get_skill_aliases with string alias values (bug fix)."""

    @pytest.fixture
    def taxonomy_with_string_alias(self):
        """Create taxonomy where aliases value is a string, not a list."""
        taxonomy = SkillsTaxonomy.__new__(SkillsTaxonomy)
        taxonomy._taxonomy_data = {}
        # Simulate YAML/JSON data where alias is a string instead of list
        taxonomy._skill_aliases = {
            "Python": "Py",  # String, not list - this was causing the bug
            "JavaScript": ["JS", "ECMAScript"],  # Correct list format
        }
        taxonomy._sections = {}
        return taxonomy

    def test_get_skill_aliases_with_string_value(self, taxonomy_with_string_alias):
        """get_skill_aliases handles string alias values without TypeError."""
        # This was raising: TypeError: can only concatenate list (not "str") to list
        result = taxonomy_with_string_alias.get_skill_aliases("Python")
        assert "Python" in result
        assert "Py" in result

    def test_get_skill_aliases_with_list_value(self, taxonomy_with_string_alias):
        """get_skill_aliases still works with list alias values."""
        result = taxonomy_with_string_alias.get_skill_aliases("JavaScript")
        assert "JavaScript" in result
        assert "JS" in result
        assert "ECMAScript" in result

    def test_get_skill_aliases_unknown_skill(self, taxonomy_with_string_alias):
        """Unknown skill returns just the skill itself."""
        result = taxonomy_with_string_alias.get_skill_aliases("Rust")
        assert result == ["Rust"]


class TestSkillMatchesWithStringAlias:
    """Tests for skill_matches with string alias values."""

    @pytest.fixture
    def taxonomy_with_string_alias(self):
        """Create taxonomy where aliases value is a string, not a list."""
        taxonomy = SkillsTaxonomy.__new__(SkillsTaxonomy)
        taxonomy._taxonomy_data = {}
        taxonomy._skill_aliases = {
            "Python": "Py",  # String, not list
            "JavaScript": ["JS", "ECMAScript"],
        }
        taxonomy._sections = {}
        return taxonomy

    def test_skill_matches_with_string_alias(self, taxonomy_with_string_alias):
        """skill_matches handles string alias values without TypeError."""
        # Should match via string alias
        assert taxonomy_with_string_alias.skill_matches("Py", "Python") is True
        assert taxonomy_with_string_alias.skill_matches("Python", "Py") is True

    def test_skill_matches_with_list_alias(self, taxonomy_with_string_alias):
        """skill_matches still works with list alias values."""
        assert taxonomy_with_string_alias.skill_matches("JS", "JavaScript") is True
        assert taxonomy_with_string_alias.skill_matches("ECMAScript", "JS") is True

    def test_skill_matches_direct_match(self, taxonomy_with_string_alias):
        """Direct match works without aliases."""
        assert taxonomy_with_string_alias.skill_matches("Python", "Python") is True
        assert taxonomy_with_string_alias.skill_matches("python", "PYTHON") is True

    def test_skill_matches_no_match(self, taxonomy_with_string_alias):
        """Non-matching skills return False."""
        assert taxonomy_with_string_alias.skill_matches("Rust", "Go") is False
