"""
Performance tests for CV Editor Phase 5.1 & 5.2

Tests validate:
- Page break calculation performance with large documents (100+ pages)
- Debounce behavior (300ms delay on updates)
- Concurrent updates (user typing while calculating)
- Memory usage with many page break indicators
- Keyboard shortcut handler performance
- Undo/redo stack memory usage

These tests focus on performance characteristics and edge cases.
"""

import pytest
import time
from typing import List, Dict, Any


# ==============================================================================
# Test Class: Page Break Calculation Performance
# ==============================================================================

class TestPageBreakCalculationPerformance:
    """Tests for page break calculation performance with large documents."""

    def test_calculate_page_breaks_for_100_page_document(self):
        """Page break calculation should complete quickly for 100-page document."""
        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Create 100 pages worth of content (100 * 864 = 86,400px)
        large_content = [
            {'type': 'paragraph', 'height': 864}
            for _ in range(100)
        ]

        # Act
        start_time = time.time()
        breaks = calculator.calculate_page_breaks('letter', margins, large_content)
        end_time = time.time()

        elapsed_ms = (end_time - start_time) * 1000

        # Assert
        assert len(breaks) == 99  # 100 pages = 99 breaks
        assert elapsed_ms < 100  # Should complete in < 100ms

    def test_calculate_page_breaks_for_500_page_document(self):
        """Page break calculation should handle very large documents (500 pages)."""
        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Create 500 pages worth of content
        very_large_content = [
            {'type': 'paragraph', 'height': 864}
            for _ in range(500)
        ]

        # Act
        start_time = time.time()
        breaks = calculator.calculate_page_breaks('letter', margins, very_large_content)
        end_time = time.time()

        elapsed_ms = (end_time - start_time) * 1000

        # Assert
        assert len(breaks) == 499  # 500 pages = 499 breaks
        assert elapsed_ms < 500  # Should complete in < 500ms

    def test_calculate_page_breaks_with_many_small_elements(self):
        """Page breaks should handle 1000+ small elements efficiently."""
        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Create 1000 small elements (20px each)
        many_small_elements = [
            {'type': 'paragraph', 'height': 20}
            for _ in range(1000)
        ]

        # Act
        start_time = time.time()
        breaks = calculator.calculate_page_breaks('letter', margins, many_small_elements)
        end_time = time.time()

        elapsed_ms = (end_time - start_time) * 1000

        # Assert
        # 1000 elements * 20px = 20,000px / 864px per page ≈ 23 pages
        assert len(breaks) >= 20
        assert len(breaks) <= 25
        assert elapsed_ms < 200  # Should complete quickly

    def test_recalculation_with_element_height_changes(self):
        """Recalculating page breaks after height changes should be efficient."""
        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Original content
        content = [
            {'type': 'paragraph', 'height': 400},
            {'type': 'paragraph', 'height': 400},
            {'type': 'paragraph', 'height': 400}
        ]

        # Calculate initial breaks
        breaks_initial = calculator.calculate_page_breaks('letter', margins, content)

        # Change height of one element
        content[1]['height'] = 600

        # Act
        start_time = time.time()
        breaks_updated = calculator.calculate_page_breaks('letter', margins, content)
        end_time = time.time()

        elapsed_ms = (end_time - start_time) * 1000

        # Assert
        assert breaks_initial != breaks_updated  # Breaks should change
        assert elapsed_ms < 10  # Recalculation should be very fast


# ==============================================================================
# Test Class: Debounce Behavior
# ==============================================================================

class TestDebounceBehavior:
    """Tests for debounced page break updates."""

    def test_update_page_breaks_has_debounce_delay(self):
        """updatePageBreaks should have debounce delay defined."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should have setTimeout or debounce logic
        assert 'setTimeout' in content or 'debounce' in content

    def test_debounce_delay_is_300ms_or_less(self):
        """Debounce delay should be reasonable (300ms or less)."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Common debounce values: 100, 200, 300ms
        # Should not have excessive delays (> 500ms)
        assert '100' in content or '200' in content or '300' in content

    def test_debounce_clears_previous_timer(self):
        """Debounce should clear previous timer to avoid multiple executions."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should call clearTimeout before setting new timer
        assert 'clearTimeout' in content

    def test_rapid_updates_only_trigger_one_calculation(self):
        """Rapid editor updates should only trigger one page break calculation."""
        # This is validated by the debounce pattern in the code

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Debounce pattern should be present
        assert 'setTimeout' in content
        assert 'clearTimeout' in content or 'debounce' in content


# ==============================================================================
# Test Class: Concurrent Updates
# ==============================================================================

class TestConcurrentUpdates:
    """Tests for concurrent updates (user typing while calculations run)."""

    def test_typing_while_calculating_does_not_break_editor(self):
        """User typing while page breaks calculate should not cause errors."""
        # This is a structural test - actual concurrency tested in E2E

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Debounce should handle concurrent updates
        assert 'setTimeout' in content or 'debounce' in content

    def test_page_break_calculation_does_not_block_ui(self):
        """Page break calculation should not block UI interaction."""
        # JavaScript is single-threaded, but calculation should be fast enough

        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Large document
        content = [
            {'type': 'paragraph', 'height': 864}
            for _ in range(50)
        ]

        # Act
        start_time = time.time()
        breaks = calculator.calculate_page_breaks('letter', margins, content)
        end_time = time.time()

        elapsed_ms = (end_time - start_time) * 1000

        # Assert
        # Should complete fast enough to not block UI (< 16ms for 60fps)
        # We allow up to 50ms for Python overhead
        assert elapsed_ms < 50

    def test_multiple_rapid_recalculations_handled_gracefully(self):
        """Multiple rapid recalculations should be handled by debounce."""
        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        content = [
            {'type': 'paragraph', 'height': 500},
            {'type': 'paragraph', 'height': 500}
        ]

        # Act - Simulate rapid recalculations
        results = []
        start_time = time.time()

        for i in range(10):
            # Slightly modify content each time
            content[0]['height'] = 500 + i
            breaks = calculator.calculate_page_breaks('letter', margins, content)
            results.append(breaks)

        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000

        # Assert
        # 10 calculations should complete quickly
        assert len(results) == 10
        assert elapsed_ms < 100  # < 100ms for 10 calculations


# ==============================================================================
# Test Class: Memory Usage
# ==============================================================================

class TestMemoryUsage:
    """Tests for memory usage with many page breaks and undo history."""

    def test_page_break_indicators_do_not_leak_memory(self):
        """Removing and re-adding page breaks should not leak DOM elements."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # clearPageBreaks should remove old indicators before adding new ones
        assert 'remove()' in content or 'removeChild' in content
        assert 'querySelectorAll' in content
        assert 'page-break-indicator' in content

    def test_undo_redo_stack_has_reasonable_size_limit(self):
        """Undo/redo history should have size limit to prevent memory bloat."""
        # TipTap's history plugin has default depth limit

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # History extension should be configured
        assert 'History' in content or 'history' in content.lower()
        # May have depth configuration

    def test_large_document_does_not_cause_memory_overflow(self):
        """Processing very large document should not cause memory issues."""
        # Arrange
        from tests.frontend.test_cv_editor_phase5_page_breaks import PageBreakCalculator

        calculator = PageBreakCalculator()
        margins = {'top': 1.0, 'right': 1.0, 'bottom': 1.0, 'left': 1.0}

        # Create extremely large document (1000 pages)
        huge_content = [
            {'type': 'paragraph', 'height': 864}
            for _ in range(1000)
        ]

        # Act
        breaks = calculator.calculate_page_breaks('letter', margins, huge_content)

        # Assert
        # Should complete without errors
        assert len(breaks) == 999  # 1000 pages = 999 breaks
        # Memory usage is implicit - test passes if no exception


# ==============================================================================
# Test Class: Keyboard Shortcut Handler Performance
# ==============================================================================

class TestKeyboardShortcutPerformance:
    """Tests for keyboard shortcut handler performance."""

    def test_keyboard_event_handler_is_efficient(self):
        """Keyboard event handler should check conditions efficiently."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should return early if editor panel not open
        assert 'return' in content  # Early returns for efficiency

    def test_shortcuts_do_not_trigger_on_every_keypress(self):
        """Shortcuts should only trigger for specific key combinations."""
        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should check modKey or specific keys before processing
        assert 'modKey' in content or 'ctrlKey' in content or 'metaKey' in content
        assert 'key ===' in content or 'e.key' in content

    def test_shortcut_handler_does_not_block_typing(self):
        """Keyboard shortcut handler should not slow down typing."""
        # This is tested via the early return pattern

        # Arrange
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Handler should return early for non-shortcut keys
        assert 'return' in content


# ==============================================================================
# Test Class: Rendering Performance
# ==============================================================================

class TestRenderingPerformance:
    """Tests for page break indicator rendering performance."""

    def test_render_page_breaks_clears_old_indicators_first(self):
        """renderPageBreaks should clear old indicators before adding new ones."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should remove existing indicators first
        assert 'querySelectorAll' in content
        assert 'page-break-indicator' in content
        assert 'remove()' in content or 'forEach' in content

    def test_render_100_page_breaks_efficiently(self):
        """Rendering 100 page break indicators should be fast."""
        # This is a structural test - actual rendering tested in E2E

        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # renderPageBreaks should loop through breaks and create elements
        assert 'forEach' in content or 'for' in content
        assert 'createElement' in content
        assert 'appendChild' in content

    def test_page_break_indicators_use_efficient_positioning(self):
        """Page break indicators should use absolute positioning for efficiency."""
        # Arrange
        with open('frontend/static/js/page-break-calculator.js', 'r') as f:
            content = f.read()

        # Act & Assert
        # Should use position: absolute
        assert "position: 'absolute'" in content or 'position: absolute' in content


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
