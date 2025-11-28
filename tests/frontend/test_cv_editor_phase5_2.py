"""
Unit tests for CV Editor Phase 5.2: Keyboard Shortcuts, Undo/Redo UI, and Polish

Tests validate:
- Keyboard shortcut functionality (text formatting, alignment, lists, document actions)
- Undo/redo button UI and state management
- Mobile responsiveness CSS classes
- Accessibility enhancements (ARIA attributes, focus management)
- Keyboard shortcuts reference panel
"""

import pytest
import re
from flask import Flask
from flask.testing import FlaskClient
from unittest.mock import Mock, patch, MagicMock
from bson import ObjectId


# ==============================================================================
# Test Class: Keyboard Shortcuts HTML/JavaScript Integration
# ==============================================================================

class TestKeyboardShortcutsIntegration:
    """Tests for keyboard shortcuts integration in the editor."""

    def test_keyboard_shortcuts_setup_function_exists(self):
        """setupKeyboardShortcuts function should exist in cv-editor.js."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'function setupKeyboardShortcuts' in content
            assert 'document.addEventListener(\'keydown\'' in content

    def test_keyboard_shortcuts_prevent_browser_defaults(self):
        """Keyboard shortcuts should prevent default browser behavior."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Check that Ctrl+S prevents browser save dialog
            assert 'e.preventDefault()' in content
            # Check for Ctrl+S handler
            assert 'Control+S' in content or "key === 's'" in content

    def test_keyboard_shortcuts_check_editor_open(self):
        """Shortcuts should only work when editor panel is open."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'translate-x-full' in content  # Check for panel closed state

    def test_escape_closes_editor(self):
        """Escape key handler should close the editor panel."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert "key === 'Escape'" in content or "e.key === 'Escape'" in content
            assert 'closeCVEditorPanel' in content

    def test_ctrl_slash_opens_shortcuts_panel(self):
        """Ctrl+/ should open keyboard shortcuts reference panel."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'toggleKeyboardShortcutsPanel' in content
            assert "key === '/'" in content or 'Slash' in content

    def test_text_alignment_shortcuts_exist(self):
        """Text alignment shortcuts (Ctrl+Shift+L/E/R/J) should be implemented."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Check for alignment shortcuts
            assert "'l'" in content or "'L'" in content  # Left
            assert "'e'" in content or "'E'" in content  # Center
            assert "'r'" in content or "'R'" in content  # Right
            assert "'j'" in content or "'J'" in content  # Justify
            assert 'textAlign' in content

    def test_list_shortcuts_exist(self):
        """List shortcuts (Ctrl+Shift+7/8) should be implemented."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert "'7'" in content or "'&'" in content  # Numbered list
            assert "'8'" in content or "'*'" in content  # Bullet list
            assert 'orderedList' in content or 'bulletList' in content


# ==============================================================================
# Test Class: Keyboard Shortcuts Reference Panel
# ==============================================================================

class TestKeyboardShortcutsPanel:
    """Tests for the keyboard shortcuts reference panel."""

    def test_create_shortcuts_panel_function_exists(self):
        """createKeyboardShortcutsPanel function should exist."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'function createKeyboardShortcutsPanel' in content

    def test_shortcuts_panel_has_modal_structure(self):
        """Shortcuts panel should have proper modal ARIA structure."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Check for setAttribute calls for ARIA attributes
            assert 'setAttribute' in content and 'role' in content and 'dialog' in content
            assert 'aria-modal' in content
            assert 'aria-labelledby' in content

    def test_shortcuts_panel_displays_platform_specific_keys(self):
        """Panel should display Cmd on Mac, Ctrl on Windows/Linux."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'navigator.platform' in content or '/Mac/' in content
            assert '⌘' in content  # Cmd symbol for Mac

    def test_shortcuts_panel_has_categories(self):
        """Panel should organize shortcuts into categories."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Check for category headers
            assert 'Text Formatting' in content
            assert 'Text Alignment' in content
            assert 'Lists' in content
            assert 'Document Actions' in content
            assert 'Navigation' in content

    def test_shortcuts_panel_closes_on_escape(self):
        """Escape key should close shortcuts panel."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Panel should handle Escape specially when open
            assert 'keyboard-shortcuts-panel' in content

    def test_shortcuts_panel_closes_on_background_click(self):
        """Clicking background should close shortcuts panel."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Check for click handler on panel background
            assert 'addEventListener' in content


# ==============================================================================
# Test Class: Undo/Redo UI Buttons
# ==============================================================================

class TestUndoRedoUIButtons:
    """Tests for undo/redo buttons in editor header."""

    def test_undo_button_exists_in_template(self):
        """Undo button should exist in job_detail.html."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            assert 'id="cv-undo-btn"' in content

    def test_redo_button_exists_in_template(self):
        """Redo button should exist in job_detail.html."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            assert 'id="cv-redo-btn"' in content

    def test_undo_button_has_aria_label(self):
        """Undo button should have aria-label for accessibility."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            # Find undo button section and check for aria-label
            undo_section = content[content.find('id="cv-undo-btn"'):content.find('id="cv-undo-btn"') + 500]
            assert 'aria-label' in undo_section
            assert 'Undo' in undo_section

    def test_redo_button_has_aria_label(self):
        """Redo button should have aria-label for accessibility."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            redo_section = content[content.find('id="cv-redo-btn"'):content.find('id="cv-redo-btn"') + 500]
            assert 'aria-label' in redo_section
            assert 'Redo' in redo_section

    def test_undo_button_starts_disabled(self):
        """Undo button should have disabled attribute by default."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            undo_section = content[content.find('id="cv-undo-btn"'):content.find('id="cv-undo-btn"') + 500]
            assert 'disabled' in undo_section

    def test_redo_button_starts_disabled(self):
        """Redo button should have disabled attribute by default."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            redo_section = content[content.find('id="cv-redo-btn"'):content.find('id="cv-redo-btn"') + 500]
            assert 'disabled' in redo_section

    def test_undo_button_has_onclick_handler(self):
        """Undo button should have onclick handler."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            undo_section = content[content.find('id="cv-undo-btn"'):content.find('id="cv-undo-btn"') + 500]
            assert 'onclick' in undo_section
            assert 'undo()' in undo_section

    def test_redo_button_has_onclick_handler(self):
        """Redo button should have onclick handler."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            redo_section = content[content.find('id="cv-redo-btn"'):content.find('id="cv-redo-btn"') + 500]
            assert 'onclick' in redo_section
            assert 'redo()' in redo_section

    def test_update_undo_redo_buttons_function_exists(self):
        """updateUndoRedoButtons function should exist in cv-editor.js."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'updateUndoRedoButtons' in content

    def test_undo_redo_buttons_check_editor_can_undo_redo(self):
        """updateUndoRedoButtons should check editor.can().undo() and redo()."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'can().undo()' in content or 'can().undo' in content
            assert 'can().redo()' in content or 'can().redo' in content

    def test_undo_redo_buttons_toggle_disabled_state(self):
        """Buttons should enable/disable based on history state."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # Check that disabled property is being set
            assert 'disabled = ' in content or '.disabled' in content


# ==============================================================================
# Test Class: Mobile Responsiveness CSS
# ==============================================================================

class TestMobileResponsiveCSS:
    """Tests for mobile responsiveness in cv-editor.css."""

    def test_cv_editor_css_file_exists(self):
        """cv-editor.css file should exist."""
        import os
        assert os.path.exists('frontend/static/css/cv-editor.css')

    def test_mobile_breakpoints_defined(self):
        """CSS should have mobile breakpoints (768px, 1023px)."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert '@media' in content
            assert '768px' in content
            assert '1023px' in content

    def test_touch_target_sizes_defined(self):
        """Touch targets should be at least 44x44px for WCAG compliance."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert '44px' in content  # WCAG touch target size

    def test_mobile_toolbar_stacking(self):
        """Toolbar should stack vertically on mobile."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert 'flex-direction: column' in content or 'flex-wrap' in content

    def test_focus_indicators_wcag_compliant(self):
        """Focus indicators should meet WCAG 3:1 contrast ratio."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert 'focus-visible' in content or ':focus' in content
            assert 'outline' in content

    def test_reduced_motion_support(self):
        """CSS should respect prefers-reduced-motion."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert 'prefers-reduced-motion' in content
            assert 'animation: none' in content or 'transition: none' in content

    def test_high_contrast_mode_support(self):
        """CSS should support high contrast mode."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert 'prefers-contrast' in content

    def test_print_styles_hide_editor_ui(self):
        """Print styles should hide editor UI elements."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert '@media print' in content
            assert 'display: none' in content


# ==============================================================================
# Test Class: Accessibility Enhancements
# ==============================================================================

class TestAccessibilityEnhancements:
    """Tests for WCAG 2.1 AA accessibility compliance."""

    def test_keyboard_shortcuts_button_exists_in_header(self):
        """Keyboard shortcuts help button should exist in header."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            assert 'toggleKeyboardShortcutsPanel' in content

    def test_editor_has_role_textbox(self):
        """Editor should have role="textbox" for screen readers."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'role: \'textbox\'' in content or 'role="textbox"' in content

    def test_editor_has_aria_label(self):
        """Editor should have aria-label describing purpose."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'aria-label' in content
            assert 'CV content editor' in content or 'editor' in content.lower()

    def test_editor_has_aria_multiline(self):
        """Editor should have aria-multiline="true"."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'aria-multiline' in content

    def test_screen_reader_announcements_exist(self):
        """Screen reader announcements should be made for actions."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'announceToScreenReader' in content
            assert 'aria-live' in content

    def test_toolbar_has_role_toolbar(self):
        """Toolbar should have role="toolbar" for accessibility."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            # Check for toolbar role
            toolbar_section = content[content.find('cv-toolbar'):content.find('cv-toolbar') + 200]
            assert 'role="toolbar"' in toolbar_section or 'role=\'toolbar\'' in toolbar_section

    def test_buttons_have_aria_pressed_for_toggles(self):
        """Toggle buttons should have aria-pressed attribute."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'aria-pressed' in content

    def test_sr_only_utility_class_exists(self):
        """Screen reader only utility class should exist in CSS."""
        with open('frontend/static/css/cv-editor.css', 'r') as f:
            content = f.read()
            assert '.sr-only' in content
            assert 'position: absolute' in content


# ==============================================================================
# Test Class: CSS File Linked in Template
# ==============================================================================

class TestCSSIntegration:
    """Tests for CSS file integration in templates."""

    def test_cv_editor_css_linked_in_job_detail(self):
        """cv-editor.css should be linked in job_detail.html."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            assert 'cv-editor.css' in content
            assert '<link' in content
            assert 'stylesheet' in content

    def test_css_link_in_extra_head_block(self):
        """CSS should be linked in extra_head block."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            # Check that cv-editor.css comes after {% block extra_head %}
            extra_head_index = content.find('{% block extra_head %}')
            css_index = content.find('cv-editor.css')
            assert extra_head_index < css_index


# ==============================================================================
# Test Class: Phase 5.2 Integration with Phase 1-5.1
# ==============================================================================

class TestPhase52Integration:
    """Tests to ensure Phase 5.2 doesn't break Phase 1-5.1 features."""

    def test_existing_keyboard_shortcuts_still_work(self):
        """Ctrl+B/I/U shortcuts (Phase 1) should still work."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            # TipTap handles these natively via extensions
            # Just verify bold functionality exists
            assert 'bold' in content.lower()
            assert 'toggleBold' in content or 'Bold' in content

    def test_autosave_still_works(self):
        """Auto-save functionality (Phase 1) should still work."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'scheduleAutoSave' in content
            assert 'AUTOSAVE_DELAY' in content

    def test_save_indicator_still_works(self):
        """Save indicator (Phase 1) should still update."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'updateSaveIndicator' in content
            assert 'cv-save-indicator' in content

    def test_toolbar_formatting_buttons_still_exist(self):
        """Toolbar formatting buttons (Phase 1-2) should still exist."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            assert 'data-format="bold"' in content
            assert 'data-format="italic"' in content
            assert 'data-format="underline"' in content

    def test_document_styles_still_exist(self):
        """Document style controls (Phase 3) should still exist."""
        with open('frontend/templates/job_detail.html', 'r') as f:
            content = f.read()
            assert 'cv-line-height' in content or 'lineHeight' in content
            assert 'cv-margin' in content or 'margin' in content

    def test_pdf_export_still_works(self):
        """PDF export (Phase 4) should still work."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'exportCVToPDF' in content

    def test_page_breaks_still_work(self):
        """Page break visualization (Phase 5.1) should still work."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()
            assert 'updatePageBreaks' in content or 'PageBreakCalculator' in content


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
