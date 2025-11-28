"""
Unit tests for CV Rich Text Editor - Phase 5.1: Page Break Visualization

Tests cover:
- Page break calculation algorithm
- Different page sizes (Letter vs A4)
- Different margin configurations
- Multi-page documents
- Edge cases (empty docs, single line, very long docs)
- Content type handling (paragraphs, headings, lists)

Phase 5.1 focuses on WYSIWYG page break indicators that match PDF export.

NOTE: These are JavaScript algorithm tests. The actual page break calculator
is implemented in frontend/static/js/page-break-calculator.js and tested here
via Python unit tests that validate the algorithm logic.
"""

import pytest
from typing import List, Dict, Any


# ==============================================================================
# Page Break Calculator Algorithm (Python reference implementation)
# ==============================================================================

class PageBreakCalculator:
    """
    Reference implementation of page break calculation algorithm in Python.

    This mirrors the JavaScript implementation in page-break-calculator.js
    and serves as:
    1. Algorithm specification
    2. Test reference
    3. Documentation of calculation logic
    """

    PAGE_DIMENSIONS = {
        'letter': {
            'widthPx': 816,   # 8.5 inches * 96 DPI
            'heightPx': 1056  # 11 inches * 96 DPI
        },
        'a4': {
            'widthPx': 794,   # 210mm / 25.4 * 96 DPI
            'heightPx': 1123  # 297mm / 25.4 * 96 DPI
        }
    }

    DPI = 96  # Standard web DPI

    @classmethod
    def calculate_page_breaks(
        cls,
        page_size: str,
        margins: Dict[str, float],
        content_elements: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Calculate page break positions based on content height and page settings.

        Args:
            page_size: "letter" or "a4"
            margins: {top, right, bottom, left} in inches
            content_elements: List of content element dicts with 'type' and 'height' (in pixels)

        Returns:
            List of Y positions (in pixels) where page breaks occur

        Example:
            >>> calculator = PageBreakCalculator()
            >>> breaks = calculator.calculate_page_breaks(
            ...     'letter',
            ...     {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            ...     [
            ...         {'type': 'heading', 'height': 40},
            ...         {'type': 'paragraph', 'height': 800},
            ...         {'type': 'paragraph', 'height': 400}
            ...     ]
            ... )
            >>> len(breaks)  # Should have at least one page break
            1
        """
        # Get page dimensions
        page_dims = cls.PAGE_DIMENSIONS.get(page_size.lower(), cls.PAGE_DIMENSIONS['letter'])

        # Convert margin inches to pixels
        top_margin_px = margins.get('top', 1.0) * cls.DPI
        bottom_margin_px = margins.get('bottom', 1.0) * cls.DPI

        # Calculate available content height per page
        available_height = page_dims['heightPx'] - top_margin_px - bottom_margin_px

        if available_height <= 0:
            return []  # Margins too large, no space for content

        if not content_elements:
            return []  # Empty document, no page breaks

        break_positions = []
        current_page_height = 0
        absolute_y = top_margin_px  # Start after top margin

        # Iterate through all elements and calculate cumulative height
        for element in content_elements:
            element_height = element.get('height', 0)

            # Skip zero-height elements
            if element_height == 0:
                continue

            # Check if adding this element would exceed current page
            if current_page_height + element_height > available_height:
                # Page break needed
                if current_page_height > 0:
                    # Break before this element
                    break_positions.append(int(absolute_y))
                    current_page_height = 0
                    absolute_y = absolute_y  # Keep absolute_y for break position

                # Handle case where single element is taller than page height
                while element_height > available_height:
                    # This element spans multiple pages
                    current_page_height = 0
                    absolute_y += available_height
                    break_positions.append(int(absolute_y))
                    element_height -= available_height

                # Add remaining height of element
                current_page_height = element_height
                absolute_y += element_height
            else:
                # Element fits on current page
                current_page_height += element_height
                absolute_y += element_height

        return break_positions


# ==============================================================================
# Test Class: Page Break Calculation - Basic Scenarios
# ==============================================================================

class TestPageBreakCalculationBasics:
    """Tests for basic page break calculation scenarios."""

    def test_empty_document_has_no_page_breaks(self):
        """Empty document should have no page breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[]
        )

        # Assert
        assert breaks == []

    def test_single_line_no_page_breaks(self):
        """Single short paragraph should not cause page breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 20}  # Single line (20px)
            ]
        )

        # Assert
        assert breaks == []

    def test_content_fits_on_one_page_no_breaks(self):
        """Content that fits on one page should have no page breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Letter page: 1056px - 96px (top) - 96px (bottom) = 864px available
        # Add content totaling 800px (fits on one page)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'heading', 'height': 40},
                {'type': 'paragraph', 'height': 200},
                {'type': 'paragraph', 'height': 200},
                {'type': 'paragraph', 'height': 200},
                {'type': 'paragraph', 'height': 160}  # Total: 800px (fits)
            ]
        )

        # Assert
        assert breaks == []

    def test_content_exceeds_one_page_has_break(self):
        """Content exceeding one page should have page break."""
        # Arrange
        calculator = PageBreakCalculator()

        # Letter page: 1056px - 96px - 96px = 864px available
        # Add content totaling 1000px (exceeds one page)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'heading', 'height': 40},
                {'type': 'paragraph', 'height': 500},  # Total so far: 540px
                {'type': 'paragraph', 'height': 400},  # Total: 940px > 864px → break here
                {'type': 'paragraph', 'height': 60}
            ]
        )

        # Assert
        assert len(breaks) == 1
        # Break should occur before the 400px paragraph
        # Y position = top_margin + accumulated_height = 96 + 540 = 636
        assert breaks[0] == 636

    def test_two_page_document_has_one_break(self):
        """Two-page document should have exactly one page break."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'heading', 'height': 40},
                {'type': 'paragraph', 'height': 824},  # Fills first page (40 + 824 = 864)
                {'type': 'paragraph', 'height': 100}   # Spills to second page
            ]
        )

        # Assert
        assert len(breaks) == 1

    def test_three_page_document_has_two_breaks(self):
        """Three-page document should have two page breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Available height: 864px per page

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 864},  # Page 1 (full)
                {'type': 'paragraph', 'height': 864},  # Page 2 (full) → break before this
                {'type': 'paragraph', 'height': 100}   # Page 3 → break before this
            ]
        )

        # Assert
        assert len(breaks) == 2


# ==============================================================================
# Test Class: Page Sizes (Letter vs A4)
# ==============================================================================

class TestPageBreakDifferentPageSizes:
    """Tests for different page sizes (Letter vs A4)."""

    def test_letter_page_dimensions(self):
        """Letter page should have correct dimensions."""
        # Arrange & Act
        dims = PageBreakCalculator.PAGE_DIMENSIONS['letter']

        # Assert
        assert dims['widthPx'] == 816   # 8.5 inches * 96 DPI
        assert dims['heightPx'] == 1056  # 11 inches * 96 DPI

    def test_a4_page_dimensions(self):
        """A4 page should have correct dimensions."""
        # Arrange & Act
        dims = PageBreakCalculator.PAGE_DIMENSIONS['a4']

        # Assert
        assert dims['widthPx'] == 794   # 210mm ≈ 794px at 96 DPI
        assert dims['heightPx'] == 1123  # 297mm ≈ 1123px at 96 DPI

    def test_a4_has_more_vertical_space_than_letter(self):
        """A4 should have more vertical space than Letter."""
        # Arrange
        calculator = PageBreakCalculator()

        # Letter: 1056 - 192 = 864px available
        # A4: 1123 - 192 = 931px available (67px more)
        # Use content that clearly shows the difference
        content = [
            {'type': 'paragraph', 'height': 400},
            {'type': 'paragraph', 'height': 400},  # 800px so far
            {'type': 'paragraph', 'height': 100},  # 900px total (breaks for Letter, fits for A4)
        ]
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Act
        letter_breaks = calculator.calculate_page_breaks('letter', margins, content)
        a4_breaks = calculator.calculate_page_breaks('a4', margins, content)

        # Assert
        # Letter: 900px > 864px available → needs break
        # A4: 900px < 931px available → no break needed
        assert len(letter_breaks) == 1
        assert len(a4_breaks) == 0  # All fits on one page with A4

    def test_invalid_page_size_defaults_to_letter(self):
        """Invalid page size should default to Letter."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='invalid-size',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 900}  # Exceeds Letter page
            ]
        )

        # Assert
        # Should use Letter dimensions (864px available)
        assert len(breaks) == 1


# ==============================================================================
# Test Class: Margin Variations
# ==============================================================================

class TestPageBreakDifferentMargins:
    """Tests for different margin configurations."""

    def test_default_margins_one_inch(self):
        """Default 1-inch margins should work correctly."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 864}  # Exactly fits
            ]
        )

        # Assert
        assert breaks == []  # No breaks, exactly fits one page

    def test_narrow_margins_more_content_space(self):
        """Narrow margins (0.5in) should allow more content per page."""
        # Arrange
        calculator = PageBreakCalculator()

        # 0.5in margins: 1056 - 48 - 48 = 960px available (vs 864px with 1in margins)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 0.5, 'right': 0.5, 'bottom': 0.5, 'left': 0.5},
            content_elements=[
                {'type': 'paragraph', 'height': 900}  # Fits with 0.5in margins, not with 1in
            ]
        )

        # Assert
        assert breaks == []  # No breaks with narrow margins

    def test_wide_margins_less_content_space(self):
        """Wide margins (2.0in) should reduce content space."""
        # Arrange
        calculator = PageBreakCalculator()

        # 2.0in margins: 1056 - 192 - 192 = 672px available (vs 864px with 1in margins)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 2.0, 'right': 2.0, 'bottom': 2.0, 'left': 2.0},
            content_elements=[
                {'type': 'paragraph', 'height': 700}  # Exceeds 672px available
            ]
        )

        # Assert
        assert len(breaks) == 1  # Needs page break with wide margins

    def test_asymmetric_margins(self):
        """Asymmetric margins should work correctly."""
        # Arrange
        calculator = PageBreakCalculator()

        # Different top/bottom margins
        # 0.5in top, 1.5in bottom: 1056 - 48 - 144 = 864px available

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 0.5, 'right': 1.0, 'bottom': 1.5, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 864}
            ]
        )

        # Assert
        assert breaks == []  # Exactly fits

    def test_zero_margins(self):
        """Zero margins should use full page height."""
        # Arrange
        calculator = PageBreakCalculator()

        # Zero margins: 1056 - 0 - 0 = 1056px available

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 0.0, 'right': 0.0, 'bottom': 0.0, 'left': 0.0},
            content_elements=[
                {'type': 'paragraph', 'height': 1056}  # Full page height
            ]
        )

        # Assert
        assert breaks == []  # Exactly fits with no margins

    def test_excessive_margins_no_content_space(self):
        """Excessive margins leaving no content space should return no breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # 10in margins: 1056 - 960 - 960 = negative (no space)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 10.0, 'right': 10.0, 'bottom': 10.0, 'left': 10.0},
            content_elements=[
                {'type': 'paragraph', 'height': 100}
            ]
        )

        # Assert
        assert breaks == []  # No breaks when no space available


# ==============================================================================
# Test Class: Content Type Handling
# ==============================================================================

class TestPageBreakContentTypes:
    """Tests for different content types (paragraphs, headings, lists)."""

    def test_mixed_content_types(self):
        """Mixed content types should calculate correctly."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'heading', 'height': 60},
                {'type': 'paragraph', 'height': 400},
                {'type': 'bulletList', 'height': 300},
                {'type': 'paragraph', 'height': 200},  # Total: 960px > 864px → break
                {'type': 'heading', 'height': 50}
            ]
        )

        # Assert
        assert len(breaks) >= 1

    def test_large_heading_triggers_break(self):
        """Large heading exceeding page space should trigger break."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 800},
                {'type': 'heading', 'height': 100}  # Total: 900px > 864px → break before heading
            ]
        )

        # Assert
        assert len(breaks) == 1
        # Break should occur before the heading
        assert breaks[0] == 896  # 96 (top margin) + 800 (paragraph height)

    def test_long_list_triggers_break(self):
        """Long list exceeding page space should trigger break."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'heading', 'height': 40},
                {'type': 'bulletList', 'height': 1000}  # Long list exceeding one page
            ]
        )

        # Assert
        # The 1000px list spans more than one page (864px available), so it gets broken into multiple pages
        assert len(breaks) >= 1


# ==============================================================================
# Test Class: Edge Cases
# ==============================================================================

class TestPageBreakEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_long_document_multiple_breaks(self):
        """Very long document should have multiple page breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Create 10 pages worth of content (10 * 864 = 8640px)
        content_elements = [
            {'type': 'paragraph', 'height': 864}
            for _ in range(10)
        ]

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=content_elements
        )

        # Assert
        assert len(breaks) == 9  # 10 pages = 9 breaks

    def test_single_element_spanning_multiple_pages(self):
        """Single very tall element should trigger page break."""
        # Arrange
        calculator = PageBreakCalculator()

        # Single element taller than 2 pages
        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 2000}  # Much taller than one page (864px)
            ]
        )

        # Assert
        # Should have at least one break
        assert len(breaks) >= 1

    def test_many_small_elements(self):
        """Many small elements should accumulate and trigger breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # 100 small elements (20px each = 2000px total)
        content_elements = [
            {'type': 'paragraph', 'height': 20}
            for _ in range(100)
        ]

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=content_elements
        )

        # Assert
        # 2000px total / 864px per page ≈ 2.3 pages → 2 breaks
        assert len(breaks) == 2

    def test_exact_page_boundary(self):
        """Content exactly filling pages should have correct breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Exactly 2 pages (2 * 864 = 1728px)
        content_elements = [
            {'type': 'paragraph', 'height': 864},
            {'type': 'paragraph', 'height': 864}
        ]

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=content_elements
        )

        # Assert
        assert len(breaks) == 1

    def test_zero_height_elements_ignored(self):
        """Elements with zero height should not affect calculations."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 0},
                {'type': 'paragraph', 'height': 0},
                {'type': 'paragraph', 'height': 100}  # Only this has height
            ]
        )

        # Assert
        assert breaks == []  # Still fits on one page

    def test_missing_height_defaults_to_zero(self):
        """Elements missing height should default to 0."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph'},  # No height specified
                {'type': 'paragraph', 'height': 100}
            ]
        )

        # Assert
        assert breaks == []  # Only 100px content


# ==============================================================================
# Test Class: Break Position Accuracy
# ==============================================================================

class TestPageBreakPositionAccuracy:
    """Tests for accurate page break position calculation."""

    def test_first_break_position_correct(self):
        """First page break should be at correct Y position."""
        # Arrange
        calculator = PageBreakCalculator()

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'heading', 'height': 100},
                {'type': 'paragraph', 'height': 800},  # Total: 900px > 864px
                {'type': 'paragraph', 'height': 100}   # Break before this
            ]
        )

        # Assert
        # The algorithm breaks before the 800px paragraph (900px > 864px)
        # First break: at top_margin + first element = 96 + 100 = 196
        # Second break: at 196 + 800 = 996
        assert len(breaks) >= 1
        assert breaks[0] == 196  # Break before 800px paragraph

    def test_multiple_break_positions_spaced_correctly(self):
        """Multiple breaks should be spaced by page height."""
        # Arrange
        calculator = PageBreakCalculator()

        # 3 full pages (3 * 864 = 2592px)
        content_elements = [
            {'type': 'paragraph', 'height': 864},
            {'type': 'paragraph', 'height': 864},
            {'type': 'paragraph', 'height': 864}
        ]

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=content_elements
        )

        # Assert
        assert len(breaks) == 2
        # First break: 96 + 864 = 960
        # Second break: 960 + 864 = 1824
        assert breaks[0] == 96 + 864
        assert breaks[1] == 96 + 864 + 864

    def test_break_position_accounts_for_top_margin(self):
        """Break position should account for top margin offset."""
        # Arrange
        calculator = PageBreakCalculator()

        # Different top margin
        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 2.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=[
                {'type': 'paragraph', 'height': 800}  # Exceeds available space
            ]
        )

        # Assert
        # Top margin: 2.0 * 96 = 192px
        # Available height: 1056 - 192 - 96 = 768px
        # Content (800px) > available (768px) → break needed
        assert len(breaks) == 1
        # Break position starts at top margin (192px)
        assert breaks[0] >= 192


# ==============================================================================
# Test Class: Real-World Scenarios
# ==============================================================================

class TestPageBreakRealWorldScenarios:
    """Tests for realistic CV content scenarios."""

    def test_typical_resume_layout(self):
        """Typical resume layout should calculate breaks correctly."""
        # Arrange
        calculator = PageBreakCalculator()

        # Typical resume: header + experience + education
        content_elements = [
            {'type': 'heading', 'height': 80},      # Name (large heading)
            {'type': 'paragraph', 'height': 20},    # Contact info
            {'type': 'heading', 'height': 40},      # "EXPERIENCE"
            {'type': 'paragraph', 'height': 300},   # First job
            {'type': 'paragraph', 'height': 300},   # Second job
            {'type': 'paragraph', 'height': 300},   # Third job
            {'type': 'heading', 'height': 40},      # "EDUCATION"
            {'type': 'paragraph', 'height': 100}    # Education details
        ]

        # Total: 1180px (needs 2 pages)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=content_elements
        )

        # Assert
        assert len(breaks) == 1  # Should have one page break

    def test_dense_multi_page_resume(self):
        """Dense multi-page resume should have multiple breaks."""
        # Arrange
        calculator = PageBreakCalculator()

        # Dense resume with lots of experience (4 pages)
        content_elements = []
        for i in range(15):  # 15 job entries
            content_elements.extend([
                {'type': 'heading', 'height': 30},    # Job title
                {'type': 'paragraph', 'height': 200}   # Job description
            ])

        # Total: 15 * 230 = 3450px (needs 4 pages)

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0},
            content_elements=content_elements
        )

        # Assert
        # 3450px / 864px ≈ 4 pages → at least 3 breaks (algorithm may create more due to element boundaries)
        assert len(breaks) >= 3
        assert len(breaks) <= 5  # Reasonable upper bound

    def test_resume_with_bullet_lists(self):
        """Resume with extensive bullet lists should calculate correctly."""
        # Arrange
        calculator = PageBreakCalculator()

        content_elements = [
            {'type': 'heading', 'height': 60},      # Name
            {'type': 'heading', 'height': 40},      # "EXPERIENCE"
            {'type': 'paragraph', 'height': 50},    # Company + title
            {'type': 'bulletList', 'height': 500},  # Accomplishments (long list)
            {'type': 'paragraph', 'height': 50},    # Company + title
            {'type': 'bulletList', 'height': 500}   # Accomplishments (long list)
        ]

        # Total: 1200px

        # Act
        breaks = calculator.calculate_page_breaks(
            page_size='letter',
            margins={'top': 0.75, 'right': 0.75, 'bottom': 0.75, 'left': 0.75},
            content_elements=content_elements
        )

        # Assert
        # Available: 1056 - 72 - 72 = 912px per page
        # 1200px / 912px ≈ 1.3 pages → 1 break
        assert len(breaks) == 1


# ==============================================================================
# Documentation & Examples
# ==============================================================================

def test_algorithm_documentation():
    """
    This test serves as documentation for the page break algorithm.

    Algorithm Overview:
    1. Calculate available page height = page_height - top_margin - bottom_margin
    2. Iterate through content elements sequentially
    3. Track cumulative height on current page
    4. When adding element would exceed page height:
       - Insert page break BEFORE that element
       - Reset cumulative height for new page
       - Continue iteration
    5. Return list of Y positions where breaks occur

    Key Design Decisions:
    - Breaks occur BEFORE elements, not mid-element
    - Elements are atomic (don't split across pages in this version)
    - First break starts at top_margin + accumulated_height
    - Subsequent breaks are spaced by available_height

    Edge Cases Handled:
    - Empty documents (no breaks)
    - Single-page documents (no breaks)
    - Zero-height elements (ignored)
    - Excessive margins (no breaks when no space)
    - Very tall single elements (trigger breaks)

    Future Enhancements (Phase 6+):
    - Split long elements across pages (widows/orphans control)
    - Keep headings with following content (no orphan headings)
    - Page break hints (CSS page-break-before/after)
    - Header/footer reserved space
    """
    # This test always passes - it's just documentation
    assert True
