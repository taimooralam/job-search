"""
Unit tests for the unified CV editor component.

Tests validate:
- Panel mode configuration (job detail page)
- Sidebar mode configuration (batch page)
- Conditional rendering based on parameters
- Element ID prefixing for multiple instances
- Core features present in both modes
- Theme and size classes based on mode
- CV content detection and empty state handling
"""

import pytest
import re
from pathlib import Path
from bson import ObjectId
from datetime import datetime


# ==============================================================================
# Test Class: Panel Mode Configuration
# ==============================================================================

class TestPanelModeConfiguration:
    """Tests for panel mode (job detail page) configuration."""

    @pytest.fixture
    def panel_wrapper_content(self):
        """Read the panel wrapper template."""
        with open('frontend/templates/partials/job_detail/_cv_editor_panel.html', 'r') as f:
            return f.read()

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_panel_wrapper_sets_correct_mode(self, panel_wrapper_content):
        """Panel wrapper should set mode='panel'."""
        assert "{% set mode = 'panel' %}" in panel_wrapper_content

    def test_panel_wrapper_sets_empty_id_prefix(self, panel_wrapper_content):
        """Panel wrapper should set id_prefix='' for no prefix."""
        assert "{% set id_prefix = '' %}" in panel_wrapper_content

    def test_panel_wrapper_enables_overlay(self, panel_wrapper_content):
        """Panel wrapper should enable overlay background."""
        assert "{% set show_overlay = true %}" in panel_wrapper_content

    def test_panel_wrapper_enables_close_button(self, panel_wrapper_content):
        """Panel wrapper should enable close button in header."""
        assert "{% set show_close_button = true %}" in panel_wrapper_content

    def test_panel_wrapper_enables_panel_toggle(self, panel_wrapper_content):
        """Panel wrapper should enable expand/collapse button."""
        assert "{% set show_panel_toggle = true %}" in panel_wrapper_content

    def test_panel_wrapper_disables_job_info(self, panel_wrapper_content):
        """Panel wrapper should disable job info display."""
        assert "{% set show_job_info = false %}" in panel_wrapper_content

    def test_panel_wrapper_disables_compact_toolbar(self, panel_wrapper_content):
        """Panel wrapper should use full-size toolbar."""
        assert "{% set compact_toolbar = false %}" in panel_wrapper_content

    def test_panel_wrapper_includes_component(self, panel_wrapper_content):
        """Panel wrapper should include the unified component."""
        assert "{% include 'components/cv_editor.html' %}" in panel_wrapper_content

    def test_panel_mode_default_is_panel(self, component_content):
        """Component should default mode to 'panel' if not specified."""
        assert "{% set mode = mode | default('panel') %}" in component_content

    def test_panel_mode_creates_fixed_panel_container(self, component_content):
        """Panel mode should create a fixed position panel with slide-in animation."""
        # Check for panel container opening
        assert '{% if mode == \'panel\' %}' in component_content
        assert 'fixed inset-y-0 right-0' in component_content
        assert 'transform translate-x-full' in component_content
        assert 'transition-transform' in component_content
        assert 'role="dialog"' in component_content
        assert 'aria-modal="true"' in component_content


# ==============================================================================
# Test Class: Sidebar Mode Configuration
# ==============================================================================

class TestSidebarModeConfiguration:
    """Tests for sidebar mode (batch page) configuration."""

    @pytest.fixture
    def sidebar_wrapper_content(self):
        """Read the sidebar wrapper template."""
        with open('frontend/templates/partials/batch/_cv_sidebar_content.html', 'r') as f:
            return f.read()

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_sidebar_wrapper_sets_correct_mode(self, sidebar_wrapper_content):
        """Sidebar wrapper should set mode='sidebar'."""
        assert "{% set mode = 'sidebar' %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_sets_batch_id_prefix(self, sidebar_wrapper_content):
        """Sidebar wrapper should set id_prefix='batch-' for element IDs."""
        assert "{% set id_prefix = 'batch-' %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_disables_overlay(self, sidebar_wrapper_content):
        """Sidebar wrapper should disable overlay background."""
        assert "{% set show_overlay = false %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_disables_close_button(self, sidebar_wrapper_content):
        """Sidebar wrapper should disable close button."""
        assert "{% set show_close_button = false %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_disables_panel_toggle(self, sidebar_wrapper_content):
        """Sidebar wrapper should disable expand/collapse button."""
        assert "{% set show_panel_toggle = false %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_enables_job_info(self, sidebar_wrapper_content):
        """Sidebar wrapper should enable job info display."""
        assert "{% set show_job_info = true %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_enables_compact_toolbar(self, sidebar_wrapper_content):
        """Sidebar wrapper should use compact toolbar."""
        assert "{% set compact_toolbar = true %}" in sidebar_wrapper_content

    def test_sidebar_wrapper_includes_batch_specific_js(self, sidebar_wrapper_content):
        """Sidebar wrapper should include batch-specific JavaScript functions."""
        assert 'updateBatchCVSaveIndicator' in sidebar_wrapper_content
        assert 'updateBatchCVToolbarState' in sidebar_wrapper_content
        assert 'applyBatchDocumentStyle' in sidebar_wrapper_content
        assert 'applyBatchMarginPreset' in sidebar_wrapper_content

    def test_sidebar_mode_creates_flex_container(self, component_content):
        """Sidebar mode should create a flex container without fixed positioning."""
        # Check for sidebar container (else branch)
        assert '{% else %}' in component_content
        # Sidebar uses simpler container
        assert '<div class="h-full flex flex-col">' in component_content


# ==============================================================================
# Test Class: Conditional Rendering - Overlay
# ==============================================================================

class TestOverlayConditionalRendering:
    """Tests for conditional overlay rendering."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_overlay_default_based_on_mode(self, component_content):
        """show_overlay should default to true for panel mode, false otherwise."""
        assert "{% set show_overlay = show_overlay | default(mode == 'panel') %}" in component_content

    def test_overlay_conditional_rendering(self, component_content):
        """Overlay should only render when show_overlay is true."""
        assert "{% if show_overlay %}" in component_content
        assert 'id="{{ id_prefix }}cv-editor-overlay"' in component_content

    def test_overlay_has_correct_classes(self, component_content):
        """Overlay should have fixed inset, background, and z-index."""
        overlay_section = self._extract_overlay_section(component_content)
        assert 'fixed inset-0' in overlay_section
        assert 'bg-black bg-opacity-50' in overlay_section
        assert 'z-40' in overlay_section
        assert 'hidden' in overlay_section  # Hidden by default
        assert 'transition-opacity' in overlay_section

    def test_overlay_closes_editor_on_click(self, component_content):
        """Overlay should close editor when clicked."""
        overlay_section = self._extract_overlay_section(component_content)
        assert 'onclick="closeCVEditorPanel()"' in overlay_section

    def test_overlay_has_accessibility_attributes(self, component_content):
        """Overlay should have proper ARIA attributes."""
        overlay_section = self._extract_overlay_section(component_content)
        assert 'role="presentation"' in overlay_section
        assert 'aria-hidden="true"' in overlay_section

    def _extract_overlay_section(self, content):
        """Extract overlay section from template."""
        start = content.find('{% if show_overlay %}')
        end = content.find('{% endif %}', start)
        return content[start:end + 100]


# ==============================================================================
# Test Class: Conditional Rendering - Close Button
# ==============================================================================

class TestCloseButtonConditionalRendering:
    """Tests for conditional close button rendering."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_close_button_default_based_on_mode(self, component_content):
        """show_close_button should default to true for panel mode."""
        assert "{% set show_close_button = show_close_button | default(mode == 'panel') %}" in component_content

    def test_close_button_conditional_rendering(self, component_content):
        """Close button should only render when show_close_button is true."""
        assert "{% if show_close_button %}" in component_content

    def test_close_button_has_onclick_handler(self, component_content):
        """Close button should call closeCVEditorPanel."""
        close_button_section = self._extract_close_button_section(component_content)
        assert 'onclick="closeCVEditorPanel()"' in close_button_section

    def test_close_button_has_accessibility_attributes(self, component_content):
        """Close button should have aria-label and title."""
        close_button_section = self._extract_close_button_section(component_content)
        assert 'aria-label="Close CV editor' in close_button_section
        assert 'title="Close (Esc)"' in close_button_section

    def test_close_button_has_icon(self, component_content):
        """Close button should have X icon (M6 18L18 6M6 6l12 12)."""
        close_button_section = self._extract_close_button_section(component_content)
        assert '<svg' in close_button_section
        assert 'M6 18L18 6M6 6l12 12' in close_button_section

    def _extract_close_button_section(self, content):
        """Extract close button section from template."""
        start = content.find('{% if show_close_button %}')
        end = content.find('{% endif %}', start)
        return content[start:end + 200]


# ==============================================================================
# Test Class: Conditional Rendering - Job Info
# ==============================================================================

class TestJobInfoConditionalRendering:
    """Tests for conditional job info rendering."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_job_info_default_based_on_mode(self, component_content):
        """show_job_info should default to true for sidebar mode."""
        assert "{% set show_job_info = show_job_info | default(mode == 'sidebar') %}" in component_content

    def test_job_info_conditional_rendering(self, component_content):
        """Job info should only render when show_job_info and job are present."""
        assert "{% if show_job_info and job %}" in component_content

    def test_job_info_displays_title(self, component_content):
        """Job info should display job title."""
        job_info_section = self._extract_job_info_section(component_content)
        assert '{{ job.title' in job_info_section
        assert 'Untitled Position' in job_info_section  # Fallback

    def test_job_info_displays_company(self, component_content):
        """Job info should display company name."""
        job_info_section = self._extract_job_info_section(component_content)
        assert '{{ job.company' in job_info_section
        assert 'Unknown Company' in job_info_section  # Fallback

    def test_job_info_uses_theme_classes(self, component_content):
        """Job info should use theme classes for dark mode support."""
        job_info_section = self._extract_job_info_section(component_content)
        assert '{{ theme_text_primary }}' in job_info_section
        assert '{{ theme_text_secondary }}' in job_info_section

    def test_job_info_else_shows_edit_cv_title(self, component_content):
        """When job info is not shown, should display 'Edit CV' title."""
        assert '{% else %}' in component_content
        assert 'Edit CV' in component_content
        assert 'id="{{ id_prefix }}cv-editor-title"' in component_content

    def _extract_job_info_section(self, content):
        """Extract job info section from template."""
        start = content.find('{% if show_job_info and job %}')
        end = content.find('{% else %}', start)
        return content[start:end + 50]


# ==============================================================================
# Test Class: Conditional Rendering - Panel Toggle
# ==============================================================================

class TestPanelToggleConditionalRendering:
    """Tests for conditional panel toggle button rendering."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_panel_toggle_default_based_on_mode(self, component_content):
        """show_panel_toggle should default to true for panel mode."""
        assert "{% set show_panel_toggle = show_panel_toggle | default(mode == 'panel') %}" in component_content

    def test_panel_toggle_conditional_rendering(self, component_content):
        """Panel toggle should only render when show_panel_toggle is true."""
        assert "{% if show_panel_toggle %}" in component_content

    def test_panel_toggle_has_onclick_handler(self, component_content):
        """Panel toggle should call toggleCVPanelSize."""
        toggle_section = self._extract_panel_toggle_section(component_content)
        assert 'onclick="toggleCVPanelSize()"' in toggle_section

    def test_panel_toggle_has_accessibility_attributes(self, component_content):
        """Panel toggle should have aria-label and title."""
        toggle_section = self._extract_panel_toggle_section(component_content)
        assert 'aria-label="Toggle panel size"' in toggle_section
        assert 'title="Expand/Collapse"' in toggle_section

    def test_panel_toggle_has_icon(self, component_content):
        """Panel toggle should have expand/collapse icon."""
        toggle_section = self._extract_panel_toggle_section(component_content)
        assert '<svg' in toggle_section
        assert 'M4 8V4m0 0h4M4 4l5 5' in toggle_section  # Expand icon path

    def _extract_panel_toggle_section(self, content):
        """Extract panel toggle section from template."""
        start = content.find('{% if show_panel_toggle %}')
        end = content.find('{% endif %}', start)
        return content[start:end + 200]


# ==============================================================================
# Test Class: Element ID Prefixing
# ==============================================================================

class TestElementIDPrefixing:
    """Tests for element ID prefixing to support multiple editor instances."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_id_prefix_defaults_to_empty(self, component_content):
        """id_prefix should default to empty string."""
        assert "{% set id_prefix = id_prefix | default('') %}" in component_content

    def test_overlay_id_uses_prefix(self, component_content):
        """Overlay ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-editor-overlay"' in component_content

    def test_panel_id_uses_prefix(self, component_content):
        """Panel ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-editor-panel"' in component_content

    def test_editor_title_id_uses_prefix(self, component_content):
        """Editor title ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-editor-title"' in component_content

    def test_undo_button_id_uses_prefix(self, component_content):
        """Undo button ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-undo-btn"' in component_content

    def test_redo_button_id_uses_prefix(self, component_content):
        """Redo button ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-redo-btn"' in component_content

    def test_save_indicator_id_uses_prefix(self, component_content):
        """Save indicator ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-save-indicator"' in component_content

    def test_editor_content_id_uses_prefix(self, component_content):
        """Editor content ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-editor-content"' in component_content

    def test_font_family_select_id_uses_prefix(self, component_content):
        """Font family select ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-font-family"' in component_content

    def test_font_size_select_id_uses_prefix(self, component_content):
        """Font size select ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-font-size"' in component_content

    def test_line_height_select_id_uses_prefix(self, component_content):
        """Line height select ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-line-height"' in component_content

    def test_margin_preset_select_id_uses_prefix(self, component_content):
        """Margin preset select ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-margin-preset"' in component_content

    def test_custom_margins_container_id_uses_prefix(self, component_content):
        """Custom margins container ID should use prefix."""
        assert 'id="{{ id_prefix }}custom-margins-container"' in component_content

    def test_all_margin_controls_use_prefix(self, component_content):
        """All margin control IDs should use prefix."""
        assert 'id="{{ id_prefix }}cv-margin-top"' in component_content
        assert 'id="{{ id_prefix }}cv-margin-right"' in component_content
        assert 'id="{{ id_prefix }}cv-margin-bottom"' in component_content
        assert 'id="{{ id_prefix }}cv-margin-left"' in component_content

    def test_page_size_select_id_uses_prefix(self, component_content):
        """Page size select ID should use prefix."""
        assert 'id="{{ id_prefix }}cv-page-size"' in component_content

    def test_header_footer_inputs_use_prefix(self, component_content):
        """Header and footer input IDs should use prefix."""
        assert 'id="{{ id_prefix }}cv-header-text"' in component_content
        assert 'id="{{ id_prefix }}cv-footer-text"' in component_content

    def test_color_inputs_use_prefix(self, component_content):
        """Color input IDs should use prefix."""
        assert 'id="{{ id_prefix }}cv-text-color"' in component_content
        assert 'id="{{ id_prefix }}cv-highlight-color"' in component_content

    def test_document_settings_ids_use_prefix(self, component_content):
        """Document settings section IDs should use prefix."""
        assert 'id="{{ id_prefix }}document-settings-heading"' in component_content
        assert 'id="{{ id_prefix }}document-settings-content"' in component_content

    def test_editor_loading_id_uses_prefix(self, component_content):
        """Editor loading indicator ID should use prefix (sidebar mode)."""
        assert 'id="{{ id_prefix }}cv-editor-loading"' in component_content


# ==============================================================================
# Test Class: Core Features Present in Both Modes
# ==============================================================================

class TestCoreFeaturesInBothModes:
    """Tests to verify core features are present in both panel and sidebar modes."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_tiptap_editor_container_exists(self, component_content):
        """TipTap editor container should exist."""
        assert 'id="{{ id_prefix }}cv-editor-content"' in component_content

    def test_toolbar_exists(self, component_content):
        """Formatting toolbar should exist."""
        assert 'role="toolbar"' in component_content
        assert 'cv-toolbar' in component_content

    def test_formatting_buttons_exist(self, component_content):
        """Bold, italic, underline buttons should exist."""
        assert 'data-format="bold"' in component_content
        assert 'data-format="italic"' in component_content
        assert 'data-format="underline"' in component_content

    def test_small_caps_button_exists(self, component_content):
        """Small caps button should exist."""
        assert 'data-format="smallCaps"' in component_content

    def test_heading_buttons_exist(self, component_content):
        """H1, H2, H3 buttons should exist."""
        assert 'data-heading="1"' in component_content
        assert 'data-heading="2"' in component_content
        assert 'data-heading="3"' in component_content

    def test_list_buttons_exist(self, component_content):
        """Bullet and numbered list buttons should exist."""
        assert 'data-format="bulletList"' in component_content
        assert 'data-format="orderedList"' in component_content

    def test_alignment_buttons_exist(self, component_content):
        """Text alignment buttons should exist."""
        assert 'data-align="left"' in component_content
        assert 'data-align="center"' in component_content
        assert 'data-align="right"' in component_content
        assert 'data-align="justify"' in component_content

    def test_indentation_buttons_exist(self, component_content):
        """Indent/outdent buttons should exist."""
        assert 'increaseIndent()' in component_content
        assert 'decreaseIndent()' in component_content

    def test_color_pickers_exist(self, component_content):
        """Text color and highlight color pickers should exist."""
        assert 'id="{{ id_prefix }}cv-text-color"' in component_content
        assert 'id="{{ id_prefix }}cv-highlight-color"' in component_content

    def test_font_controls_exist(self, component_content):
        """Font family and size controls should exist."""
        assert 'id="{{ id_prefix }}cv-font-family"' in component_content
        assert 'id="{{ id_prefix }}cv-font-size"' in component_content

    def test_undo_redo_buttons_exist(self, component_content):
        """Undo and redo buttons should exist."""
        assert 'id="{{ id_prefix }}cv-undo-btn"' in component_content
        assert 'id="{{ id_prefix }}cv-redo-btn"' in component_content

    def test_save_indicator_exists(self, component_content):
        """Save indicator should exist."""
        assert 'id="{{ id_prefix }}cv-save-indicator"' in component_content

    def test_export_pdf_button_exists(self, component_content):
        """Export PDF button should exist."""
        assert 'exportCVToPDF' in component_content or 'exportBatchCVToPDF' in component_content

    def test_keyboard_shortcuts_button_exists(self, component_content):
        """Keyboard shortcuts help button should exist."""
        assert 'toggleKeyboardShortcutsPanel()' in component_content

    def test_document_settings_section_exists(self, component_content):
        """Document settings section should exist."""
        assert 'cv-document-settings' in component_content
        assert 'Document Settings' in component_content

    def test_line_height_control_exists(self, component_content):
        """Line height control should exist."""
        assert 'id="{{ id_prefix }}cv-line-height"' in component_content

    def test_margin_controls_exist(self, component_content):
        """Margin controls should exist."""
        assert 'id="{{ id_prefix }}cv-margin-preset"' in component_content
        assert 'id="{{ id_prefix }}cv-margin-top"' in component_content

    def test_page_size_control_exists(self, component_content):
        """Page size control should exist."""
        assert 'id="{{ id_prefix }}cv-page-size"' in component_content

    def test_header_footer_controls_exist(self, component_content):
        """Header and footer controls should exist."""
        assert 'id="{{ id_prefix }}cv-header-text"' in component_content
        assert 'id="{{ id_prefix }}cv-footer-text"' in component_content


# ==============================================================================
# Test Class: Theme Classes Based on Mode
# ==============================================================================

class TestThemeClassesBasedOnMode:
    """Tests for theme classes that differ between panel and sidebar modes."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_theme_classes_defined_based_on_mode(self, component_content):
        """Theme classes should be defined differently for sidebar vs panel."""
        assert "{% set theme_bg = 'theme-bg-card' if mode == 'sidebar' else 'bg-white' %}" in component_content

    def test_theme_bg_class_varies(self, component_content):
        """theme_bg should be theme-bg-card for sidebar, bg-white for panel."""
        assert "'theme-bg-card' if mode == 'sidebar' else 'bg-white'" in component_content

    def test_theme_bg_secondary_class_varies(self, component_content):
        """theme_bg_secondary should use theme classes for sidebar."""
        assert "'theme-bg-secondary' if mode == 'sidebar' else 'bg-gray-50'" in component_content

    def test_theme_bg_tertiary_class_varies(self, component_content):
        """theme_bg_tertiary should use theme classes for sidebar."""
        assert "'theme-bg-tertiary' if mode == 'sidebar' else 'bg-gray-100'" in component_content

    def test_theme_text_primary_class_varies(self, component_content):
        """theme_text_primary should use theme classes for sidebar."""
        assert "'theme-text-primary' if mode == 'sidebar' else 'text-gray-900'" in component_content

    def test_theme_text_secondary_class_varies(self, component_content):
        """theme_text_secondary should use theme classes for sidebar."""
        assert "'theme-text-secondary' if mode == 'sidebar' else 'text-gray-500'" in component_content

    def test_theme_text_tertiary_class_varies(self, component_content):
        """theme_text_tertiary should use theme classes for sidebar."""
        assert "'theme-text-tertiary' if mode == 'sidebar' else 'text-gray-400'" in component_content

    def test_theme_border_class_varies(self, component_content):
        """theme_border should use theme classes for sidebar."""
        assert "'theme-border' if mode == 'sidebar' else 'border-gray-200'" in component_content

    def test_dark_mode_classes_in_sidebar(self, component_content):
        """Sidebar mode should have dark mode support classes."""
        # Check that sidebar mode has dark: classes
        assert "dark:bg-gray-700" in component_content
        assert "dark:border-gray-600" in component_content
        assert "dark:hover:bg-gray-600" in component_content


# ==============================================================================
# Test Class: Size Classes Based on Compact Mode
# ==============================================================================

class TestSizeClassesBasedOnCompactMode:
    """Tests for size classes that differ based on compact_toolbar parameter."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_compact_toolbar_default_based_on_mode(self, component_content):
        """compact_toolbar should default to true for sidebar mode."""
        assert "{% set compact_toolbar = compact_toolbar | default(mode == 'sidebar') %}" in component_content

    def test_icon_size_varies_by_compact_mode(self, component_content):
        """Icon size should be smaller in compact mode."""
        assert "{% set icon_size = 'w-4 h-4' if compact_toolbar else 'w-5 h-5' %}" in component_content

    def test_icon_size_sm_varies_by_compact_mode(self, component_content):
        """Small icon size should vary by compact mode."""
        assert "{% set icon_size_sm = 'w-3 h-3' if compact_toolbar else 'w-4 h-4' %}" in component_content

    def test_text_size_varies_by_compact_mode(self, component_content):
        """Text size should be smaller in compact mode."""
        assert "{% set text_size = 'text-xs' if compact_toolbar else 'text-sm' %}" in component_content

    def test_padding_x_varies_by_compact_mode(self, component_content):
        """Horizontal padding should be smaller in compact mode."""
        assert "{% set padding_x = 'px-1.5' if compact_toolbar else 'px-2' %}" in component_content

    def test_padding_y_varies_by_compact_mode(self, component_content):
        """Vertical padding should be smaller in compact mode."""
        assert "{% set padding_y = 'py-1' if compact_toolbar else 'py-1.5' %}" in component_content

    def test_gap_size_varies_by_compact_mode(self, component_content):
        """Gap size should be smaller in compact mode."""
        assert "{% set gap_size = 'gap-0.5' if compact_toolbar else 'gap-1' %}" in component_content

    def test_divider_height_varies_by_compact_mode(self, component_content):
        """Divider height should be smaller in compact mode."""
        assert "{% set divider_height = 'h-5' if compact_toolbar else 'h-6' %}" in component_content

    def test_select_width_font_varies_by_compact_mode(self, component_content):
        """Font select width should be smaller in compact mode."""
        assert "{% set select_width_font = 'w-36' if compact_toolbar else 'w-48' %}" in component_content

    def test_select_width_size_varies_by_compact_mode(self, component_content):
        """Size select width should be smaller in compact mode."""
        assert "{% set select_width_size = 'w-16' if compact_toolbar else 'w-20' %}" in component_content

    def test_button_min_width_varies_by_compact_mode(self, component_content):
        """Button min width should vary by compact mode."""
        assert "{% set button_min_width = '' if compact_toolbar else 'min-w-[2.75rem]' %}" in component_content


# ==============================================================================
# Test Class: CV Content Detection and Empty State
# ==============================================================================

class TestCVContentDetectionAndEmptyState:
    """Tests for CV content detection and empty state handling in sidebar mode."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_cv_content_detection_logic(self, component_content):
        """CV content should be detected from multiple fields in sidebar mode."""
        assert "{% if mode == 'sidebar' and job %}" in component_content
        assert "{% set cv_content = job.cv_editor_state or job.cv_text or job.generated_cv or job.cv_output or '' %}" in component_content
        assert "{% set has_cv = cv_content | length > 0 %}" in component_content

    def test_cv_content_defaults_to_has_cv_true_in_panel_mode(self, component_content):
        """Panel mode should default has_cv to true."""
        assert "{% else %}" in component_content
        assert "{% set has_cv = true %}" in component_content

    def test_editor_renders_when_has_cv_true(self, component_content):
        """Editor should render when has_cv is true."""
        assert "{% if has_cv %}" in component_content
        # Toolbar should be inside this block
        toolbar_start = component_content.find('{% if has_cv %}')
        toolbar_pos = component_content.find('role="toolbar"')
        assert toolbar_start < toolbar_pos

    def test_empty_state_renders_when_has_cv_false(self, component_content):
        """Empty state should render when has_cv is false."""
        assert "{% else %}" in component_content
        assert "No CV Generated Yet" in component_content

    def test_empty_state_has_icon(self, component_content):
        """Empty state should have a document icon."""
        empty_state_section = self._extract_empty_state_section(component_content)
        assert '<svg' in empty_state_section
        assert 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586' in empty_state_section

    def test_empty_state_has_message(self, component_content):
        """Empty state should have informative message."""
        empty_state_section = self._extract_empty_state_section(component_content)
        assert 'Run the pipeline to generate a tailored CV' in empty_state_section

    def test_empty_state_has_run_pipeline_button(self, component_content):
        """Empty state should have run pipeline button in sidebar mode."""
        empty_state_section = self._extract_empty_state_section(component_content)
        assert 'processSingleBatchJob' in empty_state_section
        assert 'Run Pipeline' in empty_state_section

    def test_empty_state_run_button_conditional(self, component_content):
        """Run pipeline button should only show in sidebar mode with job."""
        empty_state_section = self._extract_empty_state_section(component_content)
        assert "{% if mode == 'sidebar' and job %}" in empty_state_section

    def _extract_empty_state_section(self, content):
        """Extract empty state section from template."""
        start = content.find('No CV Generated Yet')
        # Go back to find the opening div
        start = content.rfind('<div', 0, start)
        # Find the end of this section
        end = content.find('{% endif %}', start)
        return content[start:end + 100]


# ==============================================================================
# Test Class: Skip Link Accessibility (Panel Mode Only)
# ==============================================================================

class TestSkipLinkAccessibility:
    """Tests for skip link accessibility feature in panel mode."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_skip_link_only_in_panel_mode(self, component_content):
        """Skip link should only render in panel mode."""
        assert "{% if mode == 'panel' %}" in component_content
        skip_link_section = self._extract_skip_link_section(component_content)
        assert 'skip-link' in skip_link_section

    def test_skip_link_targets_editor_content(self, component_content):
        """Skip link should target the editor content area."""
        skip_link_section = self._extract_skip_link_section(component_content)
        assert 'href="#{{ id_prefix }}cv-editor-content"' in skip_link_section

    def test_skip_link_has_descriptive_text(self, component_content):
        """Skip link should have descriptive text."""
        skip_link_section = self._extract_skip_link_section(component_content)
        assert 'Skip to CV editor' in skip_link_section

    def _extract_skip_link_section(self, content):
        """Extract skip link section from template."""
        start = content.find('skip-link')
        start = content.rfind('<a', 0, start)
        end = content.find('</a>', start)
        return content[start:end + 10]


# ==============================================================================
# Test Class: JavaScript Function Calls Based on Mode
# ==============================================================================

class TestJavaScriptFunctionCallsBasedOnMode:
    """Tests for JavaScript function calls that vary based on mode."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_editor_instance_varies_by_mode(self, component_content):
        """Editor instance name should be cvEditorInstance for panel, batchCVEditorInstance for sidebar."""
        # Check undo/redo buttons use mode-specific instance
        assert "{% if mode == 'sidebar' %}batchCVEditorInstance{% else %}cvEditorInstance{% endif %}" in component_content

    def test_apply_format_function_varies_by_mode(self, component_content):
        """Format function should be applyBatchCVFormat for sidebar, applyCVFormat for panel."""
        assert "{% if mode == 'sidebar' %}applyBatchCVFormat{% else %}applyCVFormat{% endif %}" in component_content

    def test_apply_document_style_function_varies_by_mode(self, component_content):
        """Document style function should vary by mode."""
        assert "{% if mode == 'sidebar' %}applyBatchDocumentStyle{% else %}applyDocumentStyle{% endif %}" in component_content

    def test_apply_margin_preset_function_varies_by_mode(self, component_content):
        """Margin preset function should vary by mode."""
        assert "{% if mode == 'sidebar' %}applyBatchMarginPreset{% else %}applyMarginPreset{% endif %}" in component_content

    def test_update_margin_preset_function_varies_by_mode(self, component_content):
        """Update margin preset function should vary by mode."""
        assert "updateBatchMarginPreset()" in component_content
        assert "updateMarginPreset()" in component_content

    def test_export_pdf_function_varies_by_mode(self, component_content):
        """Export PDF function should vary by mode."""
        assert "{% if mode == 'sidebar' %}exportBatchCVToPDF(){% else %}exportCVToPDF(){% endif %}" in component_content

    def test_indent_functions_use_mode_specific_instance(self, component_content):
        """Indent/outdent functions should use mode-specific editor instance."""
        assert "{% if mode == 'sidebar' %}batchCVEditorInstance{% else %}cvEditorInstance{% endif %}?.decreaseIndent()" in component_content
        assert "{% if mode == 'sidebar' %}batchCVEditorInstance{% else %}cvEditorInstance{% endif %}?.increaseIndent()" in component_content


# ==============================================================================
# Test Class: Loading State (Sidebar Mode Only)
# ==============================================================================

class TestLoadingStateSidebarMode:
    """Tests for loading state in sidebar mode."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_loading_state_only_in_sidebar_mode(self, component_content):
        """Loading state should only render in sidebar mode."""
        loading_section = self._extract_loading_section(component_content)
        assert "{% if mode == 'sidebar' %}" in loading_section

    def test_loading_state_has_loading_indicator(self, component_content):
        """Loading state should have animated loading indicator."""
        loading_section = self._extract_loading_section(component_content)
        assert 'id="{{ id_prefix }}cv-editor-loading"' in loading_section
        assert 'animate-pulse' in loading_section
        assert 'animate-spin' in loading_section

    def test_loading_state_has_skeleton_content(self, component_content):
        """Loading state should have skeleton loading bars."""
        loading_section = self._extract_loading_section(component_content)
        assert 'bg-gray-300' in loading_section
        assert 'bg-gray-200' in loading_section

    def test_loading_state_has_loading_text(self, component_content):
        """Loading state should have 'Loading CV editor...' text."""
        loading_section = self._extract_loading_section(component_content)
        assert 'Loading CV editor...' in loading_section

    def _extract_loading_section(self, content):
        """Extract loading section from template."""
        start = content.find('cv-editor-loading')
        start = content.rfind('<div', 0, start)
        end = content.find('{% else %}', start)
        return content[start:end + 50]


# ==============================================================================
# Test Class: CV Reasoning Display (Sidebar Mode Only)
# ==============================================================================

class TestCVReasoningDisplay:
    """Tests for CV reasoning display in sidebar mode."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_cv_reasoning_only_in_sidebar_with_job(self, component_content):
        """CV reasoning should only show in sidebar mode with job and cv_reasoning."""
        assert "{% if mode == 'sidebar' and job and job.cv_reasoning %}" in component_content

    def test_cv_reasoning_has_header(self, component_content):
        """CV reasoning section should have header."""
        reasoning_section = self._extract_cv_reasoning_section(component_content)
        assert 'CV Tailoring Rationale' in reasoning_section

    def test_cv_reasoning_has_icon(self, component_content):
        """CV reasoning should have lightbulb icon."""
        reasoning_section = self._extract_cv_reasoning_section(component_content)
        assert '<svg' in reasoning_section
        # Lightbulb icon path
        assert 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707' in reasoning_section

    def test_cv_reasoning_displays_content(self, component_content):
        """CV reasoning should display job.cv_reasoning."""
        reasoning_section = self._extract_cv_reasoning_section(component_content)
        assert '{{ job.cv_reasoning }}' in reasoning_section

    def test_cv_reasoning_uses_theme_classes(self, component_content):
        """CV reasoning should use theme classes for dark mode support."""
        reasoning_section = self._extract_cv_reasoning_section(component_content)
        assert '{{ theme_border }}' in reasoning_section
        assert '{{ theme_bg }}' in reasoning_section
        assert '{{ theme_text_tertiary }}' in reasoning_section
        assert '{{ theme_text_secondary }}' in reasoning_section

    def _extract_cv_reasoning_section(self, content):
        """Extract CV reasoning section from template."""
        start = content.find('CV Tailoring Rationale')
        start = content.rfind('<div', 0, start)
        end = content.find('</div>', start)
        # Get a bit more context
        end = content.find('</div>', end + 1)
        return content[start:end + 10]


# ==============================================================================
# Test Class: Data Attributes (Sidebar Mode Only)
# ==============================================================================

class TestDataAttributesSidebarMode:
    """Tests for data attributes on editor content in sidebar mode."""

    @pytest.fixture
    def component_content(self):
        """Read the unified component template."""
        with open('frontend/templates/components/cv_editor.html', 'r') as f:
            return f.read()

    def test_editor_content_has_job_id_attribute(self, component_content):
        """Editor content should have data-job-id in sidebar mode."""
        assert 'data-job-id="{{ job._id }}"' in component_content

    def test_editor_content_has_state_attribute(self, component_content):
        """Editor content should have data-has-state in sidebar mode."""
        assert "data-has-state=\"{{ 'true' if job.cv_editor_state else 'false' }}\"" in component_content

    def test_data_attributes_only_in_sidebar_mode(self, component_content):
        """Data attributes should only be set in sidebar mode with job."""
        editor_content_section = self._extract_editor_content_section(component_content)
        assert "{% if mode == 'sidebar' and job %}" in editor_content_section

    def _extract_editor_content_section(self, content):
        """Extract editor content section from template."""
        start = content.find('id="{{ id_prefix }}cv-editor-content"')
        start = content.rfind('<div', 0, start)
        # Find the data attributes section (after the style attribute)
        end = content.find('data-job-id="{{ job._id }}"', start)
        # Go a bit further to include the conditional
        end = content.find('{% endif %}', end)
        return content[start:end + 50]


# ==============================================================================
# Run Tests
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
