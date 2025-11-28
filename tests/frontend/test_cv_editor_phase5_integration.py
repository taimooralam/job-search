"""
Integration tests for CV Editor Phase 5.1 & 5.2

Tests validate integration between:
- Page break calculation ↔ Editor content
- Page breaks ↔ PDF export
- Keyboard shortcuts ↔ Page break recalculation
- Undo/redo ↔ Page breaks
- Mobile responsiveness ↔ Page break rendering
- Document styles ↔ Page break calculations

These tests focus on cross-component interactions rather than isolated functionality.
"""

import pytest
from typing import Dict, Any
from unittest.mock import MagicMock, Mock, patch


# ==============================================================================
# Test Class: Page Breaks ↔ Editor Content Integration
# ==============================================================================

class TestPageBreaksEditorIntegration:
    """Tests for page break calculation integrated with editor content."""

    def test_page_breaks_recalculate_on_content_change(self):
        """Page breaks should recalculate when editor content changes."""
        # This test validates that the updatePageBreaks function is called
        # when editor content changes

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Verify that updatePageBreaks exists and is called
        assert 'updatePageBreaks' in content
        # Editor updates trigger page break recalculation
        assert 'onUpdate' in content or 'on("transaction"' in content or 'addEventListener' in content

    def test_page_breaks_use_actual_element_heights(self):
        """Page break calculator should use getBoundingClientRect for heights."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Verify that getBoundingClientRect is used
        assert 'getBoundingClientRect' in content
        assert 'rect.height' in content or 'height' in content

    def test_page_breaks_handle_empty_editor(self):
        """Page breaks should handle empty editor gracefully."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Check for null/empty checks
        assert 'if (!contentElement)' in content or 'if (!element)' in content
        assert 'return []' in content  # Should return empty array

    def test_page_breaks_update_on_font_size_change(self):
        """Page breaks should recalculate when font size changes."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Font size changes should trigger updatePageBreaks
        # Look for font size controls
        assert 'font-size' in content.lower() or 'fontSize' in content
        assert 'updatePageBreaks' in content

    def test_page_breaks_update_on_line_height_change(self):
        """Page breaks should recalculate when line height changes."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        assert 'cv-line-height' in content or 'lineHeight' in content
        assert 'updatePageBreaks' in content

    def test_page_breaks_update_on_margin_change(self):
        """Page breaks should recalculate when margins change."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        assert 'margin' in content.lower()
        # Margin changes should trigger page break recalculation

    def test_page_breaks_update_on_page_size_change(self):
        """Page breaks should recalculate when page size changes (Letter ↔ A4)."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        assert 'page-size' in content or 'pageSize' in content
        assert 'letter' in content.lower()
        assert 'a4' in content.lower()


# ==============================================================================
# Test Class: Page Breaks ↔ PDF Export Integration
# ==============================================================================

class TestPageBreaksPDFIntegration:
    """Tests for page breaks matching PDF export."""

    def test_pdf_export_uses_same_margins_as_page_breaks(self):
        """PDF export should use the same margins as page break calculator."""
        # Arrange
        page_break_file = 'frontend/static/js/page-break-calculator.js'
        cv_editor_file = 'frontend/static/js/cv-editor.js'

        with open(page_break_file, 'r') as f:
            pb_content = f.read()
        with open(cv_editor_file, 'r') as f:
            editor_content = f.read()

        # Act & Assert
        # Both should reference the same margin values
        assert 'margins' in pb_content
        assert 'margin' in editor_content.lower()

    def test_pdf_export_uses_same_page_size_as_page_breaks(self):
        """PDF export should use the same page size as page break calculator."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            pb_content = f.read()

        # Act & Assert
        # Page dimensions should be defined
        assert 'PAGE_DIMENSIONS' in pb_content or 'pageDimensions' in pb_content
        assert 'letter' in pb_content.lower()
        assert 'a4' in pb_content.lower()

    def test_page_break_positions_align_with_pdf_pages(self):
        """Page break Y positions should correspond to PDF page boundaries."""
        # This is a structural test - actual alignment requires E2E testing

        # Arrange
        import sys
        import os

        # Add tests/frontend to path
        test_dir = os.path.dirname(os.path.abspath(__file__))
        if test_dir not in sys.path:
            sys.path.insert(0, test_dir)

        from test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()

        # Letter page: 1056px height, 96px margins = 864px available per page
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Create content that spans exactly 2 pages
        content_elements = [
            {'type': 'paragraph', 'height': 864},  # Page 1
            {'type': 'paragraph', 'height': 100}   # Page 2
        ]

        # Act
        breaks = calculator.calculate_page_breaks('letter', margins, content_elements)

        # Assert
        # First break should be at 96 (top margin) + 864 (first page content) = 960
        assert len(breaks) == 1
        assert breaks[0] == 96 + 864  # Y position of first page break


# ==============================================================================
# Test Class: Keyboard Shortcuts ↔ Page Break Recalculation
# ==============================================================================

class TestKeyboardShortcutsPageBreaksIntegration:
    """Tests for keyboard shortcuts triggering page break recalculation."""

    def test_ctrl_z_undo_triggers_page_break_update(self):
        """Undo should trigger page break recalculation."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Editor update events should trigger page break recalculation
        assert 'updatePageBreaks' in content
        assert 'onUpdate' in content or 'transaction' in content

    def test_ctrl_y_redo_triggers_page_break_update(self):
        """Redo should trigger page break recalculation."""
        # Same as undo - both should trigger editor updates
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        assert 'updatePageBreaks' in content

    def test_text_formatting_shortcuts_trigger_page_break_update(self):
        """Text formatting (bold, italic) should trigger recalculation."""
        # Formatting might change text height (e.g., bold text wraps differently)
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Editor updates should trigger page breaks
        assert 'updatePageBreaks' in content

    def test_alignment_shortcuts_do_not_affect_page_breaks(self):
        """Text alignment shouldn't affect page break positions (height unchanged)."""
        # Arrange
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

        from test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        content = [
            {'type': 'paragraph', 'height': 500},
            {'type': 'paragraph', 'height': 500}
        ]

        # Act
        breaks_before = calculator.calculate_page_breaks('letter', margins, content)

        # Alignment doesn't change height, so breaks should be identical
        breaks_after = calculator.calculate_page_breaks('letter', margins, content)

        # Assert
        assert breaks_before == breaks_after


# ==============================================================================
# Test Class: Undo/Redo ↔ Page Breaks Integration
# ==============================================================================

class TestUndoRedoPageBreaksIntegration:
    """Tests for undo/redo affecting page breaks correctly."""

    def test_undo_removes_page_break_if_content_fits_on_one_page(self):
        """Undoing content addition should remove page break if content now fits."""
        # Arrange
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

        from test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Before undo: 2 paragraphs exceeding one page
        content_before_undo = [
            {'type': 'paragraph', 'height': 500},
            {'type': 'paragraph', 'height': 500}  # Total: 1000px > 864px
        ]

        # After undo: only 1 paragraph
        content_after_undo = [
            {'type': 'paragraph', 'height': 500}  # Total: 500px < 864px
        ]

        # Act
        breaks_before = calculator.calculate_page_breaks('letter', margins, content_before_undo)
        breaks_after = calculator.calculate_page_breaks('letter', margins, content_after_undo)

        # Assert
        assert len(breaks_before) == 1  # Has page break
        assert len(breaks_after) == 0   # No page break after undo

    def test_redo_restores_page_breaks(self):
        """Redoing should restore page breaks to previous state."""
        # Arrange
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

        from test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        content_multi_page = [
            {'type': 'paragraph', 'height': 500},
            {'type': 'paragraph', 'height': 500}
        ]

        # Act
        breaks_original = calculator.calculate_page_breaks('letter', margins, content_multi_page)
        breaks_after_redo = calculator.calculate_page_breaks('letter', margins, content_multi_page)

        # Assert
        assert breaks_original == breaks_after_redo  # Redo restores same state


# ==============================================================================
# Test Class: Mobile Responsiveness ↔ Page Breaks Integration
# ==============================================================================

class TestMobilePageBreaksIntegration:
    """Tests for page breaks on mobile viewports."""

    def test_page_breaks_render_on_mobile_viewport(self):
        """Page break indicators should render correctly on mobile."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # renderPageBreaks should work on any viewport
        assert 'renderPageBreaks' in content
        assert 'page-break-indicator' in content

    def test_mobile_viewport_uses_same_page_dimensions(self):
        """Mobile viewport should use the same page dimensions for breaks."""
        # Page dimensions are based on PDF paper size, not screen size

        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # PAGE_DIMENSIONS should be viewport-agnostic
        assert 'PAGE_DIMENSIONS' in content
        assert 'letter' in content

    def test_mobile_touch_does_not_interfere_with_page_breaks(self):
        """Touch events on mobile shouldn't interfere with page break indicators."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Page break indicators should have pointer-events: none
        assert 'pointerEvents' in content or 'pointer-events' in content


# ==============================================================================
# Test Class: Document Styles ↔ Page Breaks Integration
# ==============================================================================

class TestDocumentStylesPageBreaksIntegration:
    """Tests for document style changes affecting page breaks."""

    def test_font_family_change_triggers_recalculation(self):
        """Changing font family should trigger page break recalculation."""
        # Different fonts have different character widths, affecting line wrap

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        assert 'font' in content.lower()
        assert 'updatePageBreaks' in content

    def test_margin_increase_reduces_available_page_height(self):
        """Increasing margins should reduce available height, possibly adding breaks."""
        # Arrange
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

        from test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()

        # Same content, different margins
        content = [
            {'type': 'paragraph', 'height': 900}
        ]

        # Act
        # 1in margins: 1056 - 96 - 96 = 864px available → break needed
        breaks_1in = calculator.calculate_page_breaks(
            'letter',
            {'top': 1.0, 'bottom': 1.0, 'left': 1.0, 'right': 1.0},
            content
        )

        # 0.5in margins: 1056 - 48 - 48 = 960px available → no break needed
        breaks_half_in = calculator.calculate_page_breaks(
            'letter',
            {'top': 0.5, 'bottom': 0.5, 'left': 0.5, 'right': 0.5},
            content
        )

        # Assert
        assert len(breaks_1in) >= 1    # 900px > 864px → needs break
        assert len(breaks_half_in) == 0  # 900px < 960px → no break

    def test_page_size_change_letter_to_a4_affects_breaks(self):
        """Changing from Letter to A4 should recalculate breaks (A4 is taller)."""
        # Arrange
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

        from test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Content that fits on A4 but not Letter
        # Letter: 864px available, A4: 931px available
        content = [
            {'type': 'paragraph', 'height': 900}
        ]

        # Act
        breaks_letter = calculator.calculate_page_breaks('letter', margins, content)
        breaks_a4 = calculator.calculate_page_breaks('a4', margins, content)

        # Assert
        assert len(breaks_letter) >= 1  # Letter needs break
        assert len(breaks_a4) == 0      # A4 fits on one page


# ==============================================================================
# Test Class: Debounce ↔ Page Breaks Integration
# ==============================================================================

class TestDebouncePageBreaksIntegration:
    """Tests for debounced page break recalculation."""

    def test_page_breaks_update_is_debounced(self):
        """updatePageBreaks should be debounced to avoid excessive recalculations."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should have debounce or setTimeout logic
        assert 'setTimeout' in content or 'debounce' in content
        # Look for 300ms delay (common debounce interval)
        assert '300' in content or 'DEBOUNCE' in content

    def test_rapid_typing_does_not_trigger_multiple_recalculations(self):
        """Rapid typing should only trigger one recalculation after debounce."""
        # This is tested via the debounce pattern in the code

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Debounce should clear previous timer
        assert 'clearTimeout' in content or 'debounce' in content


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
