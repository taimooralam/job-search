"""
Unit tests for CV markdown-to-TipTap migration function.

Tests the migrate_cv_text_to_editor_state() function that converts
legacy markdown CV content to TipTap JSON format.
"""

import pytest


class TestMigrationFunction:
    """Tests for migrate_cv_text_to_editor_state() function."""

    def test_migrate_simple_markdown(self):
        """Should convert plain text to paragraphs."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "This is a simple paragraph.\n\nThis is another paragraph."

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        assert result["version"] == 1
        assert result["content"]["type"] == "doc"
        content = result["content"]["content"]

        assert len(content) == 2
        assert content[0]["type"] == "paragraph"
        assert content[0]["content"][0]["text"] == "This is a simple paragraph."
        assert content[1]["type"] == "paragraph"
        assert content[1]["content"][0]["text"] == "This is another paragraph."

    def test_migrate_headings(self):
        """Should convert #, ##, ### to TipTap heading nodes."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "# Heading 1\n\n## Heading 2\n\n### Heading 3"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) == 3

        # Check heading level 1
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 1
        assert content[0]["content"][0]["text"] == "Heading 1"

        # Check heading level 2
        assert content[1]["type"] == "heading"
        assert content[1]["attrs"]["level"] == 2
        assert content[1]["content"][0]["text"] == "Heading 2"

        # Check heading level 3
        assert content[2]["type"] == "heading"
        assert content[2]["attrs"]["level"] == 3
        assert content[2]["content"][0]["text"] == "Heading 3"

    def test_migrate_bullet_lists(self):
        """Should convert - item to bulletList nodes."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "- First item\n- Second item\n- Third item"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "bulletList"

        list_items = content[0]["content"]
        assert len(list_items) == 3

        # Check first item
        assert list_items[0]["type"] == "listItem"
        assert list_items[0]["content"][0]["type"] == "paragraph"
        assert list_items[0]["content"][0]["content"][0]["text"] == "First item"

    def test_migrate_mixed_content(self):
        """Should handle markdown with headings + lists + paragraphs."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = """# John Doe

Software Engineer with 10 years experience.

## Skills

- Python
- JavaScript
- SQL

## Experience

Led team of 8 engineers."""

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) >= 5

        # Check structure
        assert content[0]["type"] == "heading"
        assert content[0]["attrs"]["level"] == 1
        assert "John Doe" in content[0]["content"][0]["text"]

        # Should have paragraph after heading
        assert any(node["type"] == "paragraph" for node in content)

        # Should have bullet list
        assert any(node["type"] == "bulletList" for node in content)

        # Should have h2 heading
        h2_headings = [node for node in content if node.get("type") == "heading" and node.get("attrs", {}).get("level") == 2]
        assert len(h2_headings) >= 1

    def test_migrate_empty_string(self):
        """Should return empty TipTap doc for empty input."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = ""

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        assert result["version"] == 1
        assert result["content"]["type"] == "doc"
        assert result["content"]["content"] == []

    def test_migrate_preserves_line_breaks(self):
        """Should handle \\n\\n as paragraph separators."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "First paragraph.\n\nSecond paragraph.\n\n\nThird paragraph."

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]

        # Should create separate paragraphs (not merge them)
        paragraphs = [node for node in content if node["type"] == "paragraph"]
        assert len(paragraphs) >= 2

    def test_migrate_returns_valid_tiptap_json(self):
        """Output should pass TipTap schema validation."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = """# CV Title

## Section 1

Some text here.

- Bullet 1
- Bullet 2

More text."""

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert - Check schema structure
        assert "version" in result
        assert isinstance(result["version"], int)

        assert "content" in result
        assert result["content"]["type"] == "doc"
        assert "content" in result["content"]
        assert isinstance(result["content"]["content"], list)

        assert "documentStyles" in result
        assert "fontFamily" in result["documentStyles"]
        assert "fontSize" in result["documentStyles"]
        assert "lineHeight" in result["documentStyles"]
        assert "margins" in result["documentStyles"]
        assert "pageSize" in result["documentStyles"]

        # Validate each node has required fields
        for node in result["content"]["content"]:
            assert "type" in node
            assert node["type"] in ["heading", "paragraph", "bulletList", "orderedList"]

            if node["type"] == "heading":
                assert "attrs" in node
                assert "level" in node["attrs"]
                assert 1 <= node["attrs"]["level"] <= 6

    def test_migrate_whitespace_only_string(self):
        """Should handle whitespace-only input."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "   \n\n   \n\n   "

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        assert result["content"]["content"] == []

    def test_migrate_nested_bullets(self):
        """Should handle bullet points that span multiple lines."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = """- First item that is very long
- Second item
- Third item"""

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "bulletList"

        list_items = content[0]["content"]
        assert len(list_items) == 3

    def test_migrate_headings_with_leading_whitespace(self):
        """Should handle headings with extra whitespace."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "#  Title with Spaces  \n\n##   Another Heading   "

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert content[0]["type"] == "heading"
        assert content[0]["content"][0]["text"].strip() == "Title with Spaces"

    def test_migrate_mixed_list_and_paragraph(self):
        """Should handle lists followed by paragraphs."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = """- Item 1
- Item 2

This is a paragraph after the list."""

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "bulletList"
        assert content[1]["type"] == "paragraph"

    def test_migrate_real_cv_example(self):
        """Should migrate a realistic CV markdown document."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = """# Taimoor Alam

## Senior Engineering Manager

### Experience

- 10+ years software engineering
- 5 years technical leadership
- Led teams of 8-15 engineers

### Skills

- Python, JavaScript, Go
- AWS, Kubernetes, Docker
- Agile, CI/CD, DevOps

### Achievements

Increased deployment frequency by 10x while reducing bugs by 40%.

### Education

B.S. Computer Science, 2012"""

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]

        # Should have at least 5 nodes (headings, lists, paragraphs)
        assert len(content) >= 5

        # Check document styles
        assert result["documentStyles"]["fontFamily"] == "Source Sans 3"
        assert result["documentStyles"]["fontSize"] == 11
        assert result["documentStyles"]["pageSize"] == "letter"

        # Verify specific content exists
        all_text = str(result)
        assert "Taimoor Alam" in all_text
        assert "Engineering Manager" in all_text
        assert "Python" in all_text or "AWS" in all_text


class TestMigrationEdgeCases:
    """Edge case tests for migration function."""

    def test_handles_markdown_with_special_characters(self):
        """Should handle special characters in markdown."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "# François Müller\n\n- Experience with C++ & Java\n- Worked at AT&T"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) >= 1

        # Check special characters preserved
        all_text = str(result)
        assert "François" in all_text or "Muller" in all_text
        assert "C++" in all_text or "Java" in all_text

    def test_handles_unicode_characters(self):
        """Should handle Unicode characters."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "# 王小明\n\nSoftware Engineer: 你好世界"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        assert result["content"]["type"] == "doc"
        assert len(result["content"]["content"]) >= 1

    def test_handles_emojis(self):
        """Should handle emoji characters."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "# John Doe 👨‍💻\n\n- Python developer 🐍\n- Cloud expert ☁️"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) >= 1

    def test_handles_very_long_paragraphs(self):
        """Should handle paragraphs with > 1000 characters."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        long_text = "A" * 2000
        markdown = f"# Heading\n\n{long_text}"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        assert len(content) >= 2
        assert any(len(str(node)) > 1000 for node in content)

    def test_handles_multiple_consecutive_newlines(self):
        """Should handle multiple consecutive \\n\\n separators."""
        # Arrange
        from app import migrate_cv_text_to_editor_state

        markdown = "Para 1\n\n\n\n\nPara 2"

        # Act
        result = migrate_cv_text_to_editor_state(markdown)

        # Assert
        content = result["content"]["content"]
        paragraphs = [n for n in content if n["type"] == "paragraph"]
        assert len(paragraphs) >= 1  # Should have at least 1 paragraph
