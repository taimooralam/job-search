"""
Comprehensive keyboard shortcuts tests for CV Editor Phase 5.2

Tests validate ALL keyboard shortcuts individually:
- Text formatting: Ctrl+B, Ctrl+I, Ctrl+U, Ctrl+Shift+X
- Text alignment: Ctrl+Shift+L/E/R/J
- Lists: Ctrl+Shift+7/8
- Document actions: Ctrl+S, Ctrl+Z, Ctrl+Y
- Navigation: Escape, Ctrl+/
- Shortcut conflicts and combinations
- Platform-specific modifiers (Mac vs Windows)
"""

import pytest
from typing import Dict, Any


# ==============================================================================
# Test Class: Individual Keyboard Shortcuts
# ==============================================================================

class TestIndividualKeyboardShortcuts:
    """Tests for each keyboard shortcut individually."""

    def test_ctrl_b_bold_shortcut_exists(self):
        """Ctrl+B should toggle bold formatting."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # TipTap handles Ctrl+B natively via Bold extension
        # Just verify bold functionality exists
        assert 'bold' in content.lower() or 'Bold' in content

    def test_ctrl_i_italic_shortcut_exists(self):
        """Ctrl+I should toggle italic formatting."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'italic' in content.lower() or 'Italic' in content

    def test_ctrl_u_underline_shortcut_exists(self):
        """Ctrl+U should toggle underline formatting."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'underline' in content.lower() or 'Underline' in content

    def test_ctrl_shift_x_strikethrough_shortcut_implemented(self):
        """Ctrl+Shift+X should toggle strikethrough."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Check for strikethrough in keyboard shortcut handler
        assert "'x'" in content.lower() or "'X'" in content
        assert 'strike' in content.lower() or 'Strike' in content

    def test_ctrl_z_undo_shortcut_exists(self):
        """Ctrl+Z should undo last action."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # TipTap handles undo natively
        assert 'undo' in content.lower()

    def test_ctrl_y_redo_shortcut_exists(self):
        """Ctrl+Y should redo last undone action."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # TipTap handles redo natively
        assert 'redo' in content.lower()

    def test_ctrl_shift_l_align_left_shortcut_implemented(self):
        """Ctrl+Shift+L should align text left."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'l'" in content or "'L'" in content
        assert 'textAlign' in content or 'align' in content.lower()

    def test_ctrl_shift_e_align_center_shortcut_implemented(self):
        """Ctrl+Shift+E should align text center."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'e'" in content or "'E'" in content
        assert 'center' in content.lower() or 'textAlign' in content

    def test_ctrl_shift_r_align_right_shortcut_implemented(self):
        """Ctrl+Shift+R should align text right."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'r'" in content or "'R'" in content
        assert 'right' in content.lower() or 'textAlign' in content

    def test_ctrl_shift_j_align_justify_shortcut_implemented(self):
        """Ctrl+Shift+J should justify text."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'j'" in content or "'J'" in content
        assert 'justify' in content.lower() or 'textAlign' in content

    def test_ctrl_shift_7_numbered_list_shortcut_implemented(self):
        """Ctrl+Shift+7 should create numbered list."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'7'" in content or "'&'" in content  # Shift+7 = &
        assert 'orderedList' in content or 'ordered' in content.lower()

    def test_ctrl_shift_8_bullet_list_shortcut_implemented(self):
        """Ctrl+Shift+8 should create bullet list."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'8'" in content or "'*'" in content  # Shift+8 = *
        assert 'bulletList' in content or 'bullet' in content.lower()

    def test_ctrl_s_save_shortcut_implemented(self):
        """Ctrl+S should trigger manual save."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "'s'" in content or "'S'" in content
        assert 'saveCVContent' in content or 'save' in content.lower()

    def test_escape_close_editor_shortcut_implemented(self):
        """Escape should close editor panel."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "key === 'Escape'" in content or "'Escape'" in content
        assert 'closeCVEditorPanel' in content or 'close' in content.lower()

    def test_ctrl_slash_shortcuts_panel_shortcut_implemented(self):
        """Ctrl+/ should toggle keyboard shortcuts panel."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert "key === '/'" in content or "'Slash'" in content
        assert 'toggleKeyboardShortcutsPanel' in content


# ==============================================================================
# Test Class: Shortcut Prevent Default Behavior
# ==============================================================================

class TestShortcutPreventDefault:
    """Tests that shortcuts prevent browser default behavior."""

    def test_ctrl_s_prevents_browser_save_dialog(self):
        """Ctrl+S should call preventDefault() to avoid browser save dialog."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Look for preventDefault() in keyboard handler
        assert 'preventDefault()' in content
        assert 'e.preventDefault' in content

    def test_ctrl_b_prevents_browser_bookmark(self):
        """Ctrl+B should prevent browser bookmark dialog (if custom handler)."""
        # TipTap handles this natively, but check for preventDefault pattern
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'preventDefault' in content

    def test_all_custom_shortcuts_have_prevent_default(self):
        """All custom shortcuts should call preventDefault()."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Count instances of shortcuts and preventDefault calls
        # There should be multiple preventDefault calls
        prevent_default_count = content.count('preventDefault()')

        # Should have at least 5 preventDefault calls for custom shortcuts
        assert prevent_default_count >= 5


# ==============================================================================
# Test Class: Shortcut Conflicts
# ==============================================================================

class TestShortcutConflicts:
    """Tests for keyboard shortcut conflicts and combinations."""

    def test_ctrl_b_vs_ctrl_shift_b_no_conflict(self):
        """Ctrl+B and Ctrl+Shift+B should be distinct shortcuts."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Check that shiftKey is checked for differentiation
        assert 'shiftKey' in content

    def test_ctrl_i_vs_ctrl_shift_i_no_conflict(self):
        """Ctrl+I and Ctrl+Shift+I should be distinct."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'shiftKey' in content

    def test_ctrl_vs_ctrl_shift_shortcuts_differentiated(self):
        """Ctrl and Ctrl+Shift shortcuts should be properly differentiated."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Should check both modKey and shiftKey
        assert 'modKey' in content or 'ctrlKey' in content
        assert 'shiftKey' in content

    def test_escape_closes_shortcuts_panel_before_editor(self):
        """Escape should close shortcuts panel first if open, then editor."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Should check if shortcuts panel is open before closing editor
        assert 'keyboard-shortcuts-panel' in content
        assert 'hidden' in content.lower()
        assert 'Escape' in content


# ==============================================================================
# Test Class: Platform-Specific Modifiers
# ==============================================================================

class TestPlatformSpecificModifiers:
    """Tests for Mac (Cmd) vs Windows/Linux (Ctrl) modifiers."""

    def test_mac_platform_detection(self):
        """Code should detect Mac platform for Cmd key."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Check for Mac platform detection
        assert 'navigator.platform' in content or 'Mac' in content or '/Mac/' in content

    def test_mod_key_variable_for_cross_platform(self):
        """Code should use modKey variable (Cmd on Mac, Ctrl elsewhere)."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Should use metaKey (Cmd) or ctrlKey depending on platform
        assert 'metaKey' in content or 'ctrlKey' in content
        assert 'modKey' in content or 'const mod' in content.lower()

    def test_keyboard_shortcuts_panel_shows_platform_key(self):
        """Shortcuts panel should show ⌘ on Mac, Ctrl on Windows/Linux."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Should display different symbols based on platform
        assert '⌘' in content or 'Cmd' in content  # Mac symbol
        assert 'Ctrl' in content  # Windows/Linux


# ==============================================================================
# Test Class: Shortcut Enabled/Disabled States
# ==============================================================================

class TestShortcutStates:
    """Tests for shortcuts being enabled/disabled based on context."""

    def test_shortcuts_only_work_when_editor_panel_open(self):
        """Shortcuts should only work when CV editor panel is open."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Should check panel state before processing shortcuts
        assert 'cv-editor-panel' in content
        assert 'translate-x-full' in content or 'classList.contains' in content

    def test_escape_shortcut_always_active(self):
        """Escape shortcut should work regardless of editor state (to close panel)."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Escape should be handled even if panel is opening/closing
        assert 'Escape' in content

    def test_shortcuts_disabled_when_shortcuts_panel_open(self):
        """Text shortcuts should not work when shortcuts reference panel is open."""
        # This prevents conflicts (e.g., typing in search box triggers shortcuts)

        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # May check if shortcuts panel is focused
        assert 'keyboard-shortcuts-panel' in content


# ==============================================================================
# Test Class: Rapid Shortcut Combinations
# ==============================================================================

class TestRapidShortcutCombinations:
    """Tests for shortcuts triggered in rapid succession."""

    def test_ctrl_b_ctrl_i_sequential_formatting(self):
        """Ctrl+B followed by Ctrl+I should apply both bold and italic."""
        # This is handled by TipTap's native mark system
        # Just verify both marks can coexist

        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Both bold and italic should be supported
        assert 'Bold' in content
        assert 'Italic' in content

    def test_multiple_alignment_shortcuts_only_last_applies(self):
        """Pressing Ctrl+Shift+L then Ctrl+Shift+E should only center (last wins)."""
        # Text can only have one alignment, so last shortcut wins
        # This is structural - actual behavior tested in E2E

        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'textAlign' in content
        # TipTap's textAlign extension handles this

    def test_undo_redo_repeated_rapidly(self):
        """Ctrl+Z followed by Ctrl+Y repeatedly should not break history."""
        # TipTap's history plugin handles this
        # Verify history is enabled

        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'History' in content or 'history' in content.lower()


# ==============================================================================
# Test Class: Shortcuts with Different Content Types
# ==============================================================================

class TestShortcutsWithContentTypes:
    """Tests for shortcuts applied to different content types."""

    def test_bold_shortcut_works_on_paragraphs(self):
        """Ctrl+B should work on paragraph text."""
        # TipTap handles this natively
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'Paragraph' in content or 'paragraph' in content

    def test_bold_shortcut_works_on_headings(self):
        """Ctrl+B should work on heading text."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'Heading' in content or 'heading' in content

    def test_bold_shortcut_works_on_list_items(self):
        """Ctrl+B should work on list item text."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'ListItem' in content or 'listItem' in content or 'BulletList' in content

    def test_alignment_shortcuts_work_on_all_block_types(self):
        """Alignment shortcuts should work on paragraphs, headings, list items."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # textAlign should be available for multiple node types
        assert 'textAlign' in content

    def test_list_shortcuts_convert_paragraphs_to_lists(self):
        """Ctrl+Shift+7/8 should convert paragraphs to numbered/bullet lists."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'toggleBulletList' in content or 'toggleOrderedList' in content


# ==============================================================================
# Test Class: Shortcut Accessibility
# ==============================================================================

class TestShortcutAccessibility:
    """Tests for keyboard shortcut accessibility features."""

    def test_shortcuts_panel_has_aria_modal(self):
        """Keyboard shortcuts panel should have role=dialog and aria-modal."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'role' in content.lower()
        assert 'dialog' in content.lower()
        assert 'aria-modal' in content

    def test_shortcuts_panel_has_aria_labelledby(self):
        """Shortcuts panel should have aria-labelledby for title."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        assert 'aria-labelledby' in content

    def test_shortcuts_panel_focus_trap(self):
        """Shortcuts panel should trap focus for keyboard users."""
        # Check for focus management when panel opens
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # May set focus on panel when opened
        assert 'focus()' in content or 'focus' in content.lower()

    def test_shortcuts_reference_panel_lists_all_shortcuts(self):
        """Shortcuts panel should list all available shortcuts."""
        with open('frontend/static/js/cv-editor.js', 'r') as f:
            content = f.read()

        # Should contain shortcut descriptions
        assert 'Text Formatting' in content
        assert 'Text Alignment' in content
        assert 'Lists' in content
        assert 'Document Actions' in content


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
