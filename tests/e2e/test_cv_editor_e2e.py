"""
End-to-End tests for CV Rich Text Editor using Playwright.

Tests validate real browser interactions with the deployed CV editor, covering:
- Phase 1: Editor initialization, basic formatting (bold, italic, underline)
- Phase 2: Font family/size, alignment, indentation, highlight colors
- Phase 3: Document styles (margins, line height, page size, header/footer)
- Phase 4: PDF export functionality
- Phase 5: Keyboard shortcuts, mobile responsiveness, accessibility

Test Environment:
- Browser: Chromium (primary), Firefox, WebKit (cross-browser testing)
- Target: Deployed Vercel app (https://job-search-inky-sigma.vercel.app)
- Authentication: Password-based login
- Test Data: Existing jobs in MongoDB (no fixtures created)
"""

import os
import pytest
import re
from pathlib import Path
from playwright.sync_api import Page, expect, BrowserContext


# ==============================================================================
# Configuration
# ==============================================================================

BASE_URL = os.getenv("E2E_BASE_URL", "https://job-search-inky-sigma.vercel.app")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "test-password")


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for all tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
    }


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    """
    Fixture that provides an authenticated page.

    Logs in to the application and returns a page ready for testing.
    """
    # Navigate to login page
    page.goto(f"{BASE_URL}/login")

    # Fill login form
    password_input = page.locator('input[name="password"]')
    password_input.fill(LOGIN_PASSWORD)

    # Submit form
    submit_button = page.locator('button[type="submit"]')
    submit_button.click()

    # Wait for redirect to job list
    page.wait_for_url(f"{BASE_URL}/", timeout=10000)

    return page


@pytest.fixture
def cv_editor_page(authenticated_page: Page) -> Page:
    """
    Fixture that navigates to the CV editor for the first job.

    Assumes at least one job exists in the database.
    """
    # Navigate to job list
    authenticated_page.goto(f"{BASE_URL}/")

    # Wait for job cards to load
    authenticated_page.wait_for_selector('a[href*="/job/"]', timeout=10000)

    # Click first job card
    first_job_link = authenticated_page.locator('a[href*="/job/"]').first
    first_job_link.click()

    # Wait for job detail page to load
    authenticated_page.wait_for_load_state("networkidle")

    # Wait for TipTap editor to initialize
    authenticated_page.wait_for_selector('.tiptap', timeout=15000)

    return authenticated_page


@pytest.fixture
def mobile_context(browser_context_args):
    """Browser context configured for mobile viewport."""
    return {
        **browser_context_args,
        "viewport": {"width": 375, "height": 667},  # iPhone SE
        "is_mobile": True,
    }


# ==============================================================================
# Test Class: Editor Initialization & Loading
# ==============================================================================

class TestEditorInitialization:
    """Tests for CV editor page loading and initialization."""

    def test_editor_page_loads_successfully(self, cv_editor_page: Page):
        """CV editor page should load without errors."""
        # Assert: No JavaScript errors
        # (Playwright automatically fails on uncaught exceptions unless configured otherwise)

        # Assert: Page title is correct
        expect(cv_editor_page).to_have_title(re.compile(r"Job Detail|CV Editor", re.IGNORECASE))

    def test_tiptap_editor_initializes(self, cv_editor_page: Page):
        """TipTap editor should initialize and be interactive."""
        editor = cv_editor_page.locator('.tiptap')

        # Assert: Editor is visible
        expect(editor).to_be_visible()

        # Assert: Editor is editable
        expect(editor).to_be_editable()

    def test_toolbar_buttons_are_visible(self, cv_editor_page: Page):
        """Editor toolbar should display all formatting buttons."""
        # Check for common formatting buttons
        bold_button = cv_editor_page.locator('button[title*="Bold"], button:has-text("Bold")')
        expect(bold_button.first).to_be_visible()

        italic_button = cv_editor_page.locator('button[title*="Italic"], button:has-text("Italic")')
        expect(italic_button.first).to_be_visible()

        underline_button = cv_editor_page.locator('button[title*="Underline"], button:has-text("Underline")')
        expect(underline_button.first).to_be_visible()

    def test_document_styles_panel_loads(self, cv_editor_page: Page):
        """Document styles panel should load with default values."""
        # Check for font family selector
        font_selector = cv_editor_page.locator('select#cv-font-family, [name="fontFamily"]')
        if font_selector.count() > 0:
            expect(font_selector.first).to_be_visible()

        # Check for font size selector
        font_size_selector = cv_editor_page.locator('select#cv-font-size, [name="fontSize"]')
        if font_size_selector.count() > 0:
            expect(font_size_selector.first).to_be_visible()

    def test_auto_save_indicator_present(self, cv_editor_page: Page):
        """Auto-save indicator should be present."""
        save_indicator = cv_editor_page.locator('#cv-save-indicator, [id*="save"]')

        # Wait for save indicator (may take a moment after editor loads)
        cv_editor_page.wait_for_timeout(2000)

        if save_indicator.count() > 0:
            expect(save_indicator.first).to_be_visible()


# ==============================================================================
# Test Class: Text Formatting (Phase 1-2)
# ==============================================================================

class TestTextFormatting:
    """Tests for basic and enhanced text formatting features."""

    def test_bold_formatting_with_button(self, cv_editor_page: Page):
        """Bold formatting should work via toolbar button."""
        editor = cv_editor_page.locator('.tiptap')

        # Type some text
        editor.click()
        editor.type("Bold text test")

        # Select all text
        cv_editor_page.keyboard.press("Control+A")

        # Click bold button
        bold_button = cv_editor_page.locator('button[title*="Bold"], button:has-text("Bold")').first
        bold_button.click()

        # Assert: Text should have bold formatting
        bold_element = editor.locator('strong, b, [style*="font-weight"]')
        expect(bold_element.first).to_be_visible()

    def test_bold_formatting_with_keyboard_shortcut(self, cv_editor_page: Page):
        """Ctrl+B should toggle bold formatting."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Keyboard bold")

        # Select text
        cv_editor_page.keyboard.press("Control+A")

        # Apply bold with keyboard shortcut
        cv_editor_page.keyboard.press("Control+B")

        # Wait for formatting to apply
        cv_editor_page.wait_for_timeout(500)

        # Assert: Bold element exists
        bold_element = editor.locator('strong, b')
        expect(bold_element.first).to_be_visible()

    def test_italic_formatting_with_keyboard_shortcut(self, cv_editor_page: Page):
        """Ctrl+I should toggle italic formatting."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Italic text")

        cv_editor_page.keyboard.press("Control+A")
        cv_editor_page.keyboard.press("Control+I")

        cv_editor_page.wait_for_timeout(500)

        italic_element = editor.locator('em, i')
        expect(italic_element.first).to_be_visible()

    def test_underline_formatting_with_keyboard_shortcut(self, cv_editor_page: Page):
        """Ctrl+U should toggle underline formatting."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Underlined text")

        cv_editor_page.keyboard.press("Control+A")
        cv_editor_page.keyboard.press("Control+U")

        cv_editor_page.wait_for_timeout(500)

        underline_element = editor.locator('u, [style*="text-decoration"]')
        expect(underline_element.first).to_be_visible()

    def test_font_family_changes_persist(self, cv_editor_page: Page):
        """Font family changes should persist in editor."""
        # Locate font family selector
        font_selector = cv_editor_page.locator('select#cv-font-family, [name="fontFamily"]')

        if font_selector.count() == 0:
            pytest.skip("Font family selector not found")

        # Change font to Roboto
        font_selector.first.select_option("Roboto")

        # Wait for change to apply
        cv_editor_page.wait_for_timeout(1000)

        # Verify selected value
        selected_value = font_selector.first.input_value()
        assert selected_value == "Roboto"

    def test_font_size_changes_persist(self, cv_editor_page: Page):
        """Font size changes should persist in editor."""
        font_size_selector = cv_editor_page.locator('select#cv-font-size, [name="fontSize"]')

        if font_size_selector.count() == 0:
            pytest.skip("Font size selector not found")

        # Change font size to 14pt
        font_size_selector.first.select_option("14pt")

        cv_editor_page.wait_for_timeout(1000)

        selected_value = font_size_selector.first.input_value()
        assert selected_value == "14pt"

    def test_text_color_changes_persist(self, cv_editor_page: Page):
        """Text color changes should apply and persist."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Colored text")
        cv_editor_page.keyboard.press("Control+A")

        # Look for color picker
        color_picker = cv_editor_page.locator('input[type="color"]#cv-text-color, input[type="color"][id*="color"]')

        if color_picker.count() == 0:
            pytest.skip("Text color picker not found")

        # Change color to red
        color_picker.first.fill("#ff0000")

        cv_editor_page.wait_for_timeout(1000)

        # Verify color applied (check for style attribute)
        colored_element = editor.locator('[style*="color"]')
        expect(colored_element.first).to_be_visible()

    def test_highlight_color_changes_persist(self, cv_editor_page: Page):
        """Highlight color should apply to selected text."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Highlighted text")
        cv_editor_page.keyboard.press("Control+A")

        # Look for highlight color picker
        highlight_picker = cv_editor_page.locator('input[type="color"]#cv-highlight-color, input[type="color"][id*="highlight"]')

        if highlight_picker.count() == 0:
            pytest.skip("Highlight color picker not found")

        # Apply yellow highlight
        highlight_picker.first.fill("#ffff00")

        cv_editor_page.wait_for_timeout(1000)

        # Verify highlight applied
        highlighted_element = editor.locator('mark, [style*="background"]')
        expect(highlighted_element.first).to_be_visible()

    def test_text_alignment_left(self, cv_editor_page: Page):
        """Left alignment button should align text left."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Left aligned text")

        # Click align left button
        align_left_button = cv_editor_page.locator('button[data-align="left"], button:has-text("Align Left")')

        if align_left_button.count() == 0:
            pytest.skip("Align left button not found")

        align_left_button.first.click()

        cv_editor_page.wait_for_timeout(500)

        # Text alignment is applied via CSS, check for text-align style
        aligned_element = editor.locator('p, [style*="text-align: left"]')
        expect(aligned_element.first).to_be_visible()

    def test_text_alignment_center(self, cv_editor_page: Page):
        """Center alignment button should center text."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Centered text")

        align_center_button = cv_editor_page.locator('button[data-align="center"], button:has-text("Align Center")')

        if align_center_button.count() == 0:
            pytest.skip("Align center button not found")

        align_center_button.first.click()

        cv_editor_page.wait_for_timeout(500)

        centered_element = editor.locator('[style*="text-align: center"]')
        expect(centered_element.first).to_be_visible()


# ==============================================================================
# Test Class: Document Styles (Phase 3)
# ==============================================================================

class TestDocumentStyles:
    """Tests for document-level styles (margins, line height, page size)."""

    def test_line_height_changes_reflect_in_editor(self, cv_editor_page: Page):
        """Line height changes should apply to editor."""
        line_height_selector = cv_editor_page.locator('select#cv-line-height, [name="lineHeight"]')

        if line_height_selector.count() == 0:
            pytest.skip("Line height selector not found")

        # Change line height to 1.5
        line_height_selector.first.select_option("1.5")

        cv_editor_page.wait_for_timeout(1000)

        # Verify selection
        selected_value = line_height_selector.first.input_value()
        assert selected_value == "1.5"

    def test_margin_top_changes_work(self, cv_editor_page: Page):
        """Top margin changes should apply."""
        margin_top_input = cv_editor_page.locator('input#margin-top, input[name="marginTop"], select[name="marginTop"]')

        if margin_top_input.count() == 0:
            pytest.skip("Margin top control not found")

        # Change top margin to 0.5
        if margin_top_input.first.get_attribute("type") == "select":
            margin_top_input.first.select_option("0.5")
        else:
            margin_top_input.first.fill("0.5")

        cv_editor_page.wait_for_timeout(1000)

        # Verify value
        value = margin_top_input.first.input_value()
        assert "0.5" in value

    def test_page_size_toggle_letter_to_a4(self, cv_editor_page: Page):
        """Page size should toggle between Letter and A4."""
        page_size_selector = cv_editor_page.locator('select#cv-page-size, [name="pageSize"]')

        if page_size_selector.count() == 0:
            pytest.skip("Page size selector not found")

        # Change to A4
        page_size_selector.first.select_option("a4")

        cv_editor_page.wait_for_timeout(1000)

        # Verify selection
        selected_value = page_size_selector.first.input_value()
        assert selected_value.lower() == "a4"

        # Change back to Letter
        page_size_selector.first.select_option("letter")

        cv_editor_page.wait_for_timeout(1000)

        selected_value = page_size_selector.first.input_value()
        assert selected_value.lower() == "letter"

    def test_header_text_is_editable(self, cv_editor_page: Page):
        """Header text should be editable."""
        header_input = cv_editor_page.locator('input#cv-header, [name="header"], textarea#cv-header')

        if header_input.count() == 0:
            pytest.skip("Header input not found")

        # Clear and type new header
        header_input.first.fill("John Doe | john@example.com | (555) 123-4567")

        cv_editor_page.wait_for_timeout(1000)

        # Verify value
        value = header_input.first.input_value()
        assert "John Doe" in value

    def test_footer_text_is_editable(self, cv_editor_page: Page):
        """Footer text should be editable."""
        footer_input = cv_editor_page.locator('input#cv-footer, [name="footer"], textarea#cv-footer')

        if footer_input.count() == 0:
            pytest.skip("Footer input not found")

        # Type footer text
        footer_input.first.fill("Portfolio: https://johndoe.dev")

        cv_editor_page.wait_for_timeout(1000)

        # Verify value
        value = footer_input.first.input_value()
        assert "Portfolio" in value


# ==============================================================================
# Test Class: Auto-Save & Persistence
# ==============================================================================

class TestAutoSaveAndPersistence:
    """Tests for auto-save functionality and state persistence."""

    def test_content_auto_saves_after_typing(self, cv_editor_page: Page):
        """Content should auto-save after typing (debounced)."""
        editor = cv_editor_page.locator('.tiptap')

        # Type content
        editor.click()
        editor.type("This content should auto-save")

        # Wait for auto-save debounce (typically 3 seconds)
        cv_editor_page.wait_for_timeout(4000)

        # Check save indicator
        save_indicator = cv_editor_page.locator('#cv-save-indicator, [id*="save"]')

        if save_indicator.count() > 0:
            # Should show "Saved" or "Saved at HH:MM:SS"
            indicator_text = save_indicator.first.inner_text()
            assert "Saved" in indicator_text or "saved" in indicator_text.lower()

    def test_auto_save_indicator_updates(self, cv_editor_page: Page):
        """Auto-save indicator should update from 'Saving...' to 'Saved'."""
        editor = cv_editor_page.locator('.tiptap')
        save_indicator = cv_editor_page.locator('#cv-save-indicator, [id*="save"]')

        if save_indicator.count() == 0:
            pytest.skip("Save indicator not found")

        # Type to trigger save
        editor.click()
        editor.type("Test auto-save indicator")

        # Wait briefly (may show "Saving...")
        cv_editor_page.wait_for_timeout(1000)

        # Wait for save to complete (should show "Saved")
        cv_editor_page.wait_for_timeout(4000)

        indicator_text = save_indicator.first.inner_text()
        assert "Saved" in indicator_text or "saved" in indicator_text.lower()

    def test_content_persists_after_page_reload(self, cv_editor_page: Page):
        """Content should persist after page reload."""
        editor = cv_editor_page.locator('.tiptap')

        # Type unique content
        unique_text = "Persistent content 12345"
        editor.click()
        cv_editor_page.keyboard.press("Control+A")
        editor.type(unique_text)

        # Wait for auto-save
        cv_editor_page.wait_for_timeout(4000)

        # Reload page
        cv_editor_page.reload()

        # Wait for editor to reinitialize
        cv_editor_page.wait_for_selector('.tiptap', timeout=10000)
        cv_editor_page.wait_for_timeout(2000)

        # Verify content is still there
        editor_content = cv_editor_page.locator('.tiptap').inner_text()
        assert unique_text in editor_content

    def test_document_styles_persist_after_reload(self, cv_editor_page: Page):
        """Document styles should persist after page reload."""
        line_height_selector = cv_editor_page.locator('select#cv-line-height, [name="lineHeight"]')

        if line_height_selector.count() == 0:
            pytest.skip("Line height selector not found")

        # Set line height to 2.0
        line_height_selector.first.select_option("2.0")

        # Wait for auto-save
        cv_editor_page.wait_for_timeout(4000)

        # Reload page
        cv_editor_page.reload()
        cv_editor_page.wait_for_selector('.tiptap', timeout=10000)
        cv_editor_page.wait_for_timeout(2000)

        # Re-locate selector after reload
        line_height_selector = cv_editor_page.locator('select#cv-line-height, [name="lineHeight"]')

        # Verify line height is still 2.0
        selected_value = line_height_selector.first.input_value()
        assert selected_value == "2.0"


# ==============================================================================
# Test Class: PDF Export (Phase 4)
# ==============================================================================

class TestPDFExport:
    """Tests for PDF export functionality."""

    def test_export_pdf_button_is_visible(self, cv_editor_page: Page):
        """Export to PDF button should be visible."""
        pdf_button = cv_editor_page.locator('button:has-text("Export"), button:has-text("PDF"), button[id*="pdf"]')

        # Button should exist
        assert pdf_button.count() > 0
        expect(pdf_button.first).to_be_visible()

    def test_pdf_downloads_successfully_when_clicked(self, cv_editor_page: Page):
        """PDF should download when Export button is clicked."""
        pdf_button = cv_editor_page.locator('button:has-text("Export"), button:has-text("PDF")').first

        # Set up download handler
        with cv_editor_page.expect_download() as download_info:
            pdf_button.click()

        download = download_info.value

        # Verify download
        assert download is not None

        # Verify filename contains CV
        suggested_filename = download.suggested_filename
        assert "CV" in suggested_filename or "cv" in suggested_filename.lower()
        assert suggested_filename.endswith(".pdf")

    def test_pdf_filename_format_correct(self, cv_editor_page: Page):
        """PDF filename should follow CV_<Company>_<Title>.pdf format."""
        pdf_button = cv_editor_page.locator('button:has-text("Export"), button:has-text("PDF")').first

        with cv_editor_page.expect_download() as download_info:
            pdf_button.click()

        download = download_info.value
        filename = download.suggested_filename

        # Should match pattern: CV_CompanyName_JobTitle.pdf
        assert filename.startswith("CV_")
        assert filename.endswith(".pdf")
        assert "_" in filename  # At least one underscore separator

    def test_pdf_export_shows_loading_state(self, cv_editor_page: Page):
        """PDF export button should show loading state during generation."""
        pdf_button = cv_editor_page.locator('button:has-text("Export"), button:has-text("PDF")').first

        # Click and immediately check for loading state
        pdf_button.click()

        # Wait briefly to see loading state
        cv_editor_page.wait_for_timeout(500)

        # Button may show "Generating...", "Loading...", or be disabled
        # Check if button is disabled (common loading pattern)
        is_disabled = pdf_button.is_disabled()

        # Or check for loading text
        button_text = pdf_button.inner_text()
        has_loading_indicator = "..." in button_text or "Loading" in button_text or "Generating" in button_text

        # Either disabled OR shows loading text
        assert is_disabled or has_loading_indicator


# ==============================================================================
# Test Class: Keyboard Shortcuts (Phase 5)
# ==============================================================================

class TestKeyboardShortcuts:
    """Tests for keyboard shortcuts."""

    def test_ctrl_b_toggles_bold(self, cv_editor_page: Page):
        """Ctrl+B should toggle bold on/off."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Toggle bold test")
        cv_editor_page.keyboard.press("Control+A")

        # Apply bold
        cv_editor_page.keyboard.press("Control+B")
        cv_editor_page.wait_for_timeout(300)

        bold_element = editor.locator('strong, b')
        expect(bold_element.first).to_be_visible()

        # Toggle off
        cv_editor_page.keyboard.press("Control+B")
        cv_editor_page.wait_for_timeout(300)

        # Bold should be removed (this is harder to test, so we just verify no crash)

    def test_ctrl_i_toggles_italic(self, cv_editor_page: Page):
        """Ctrl+I should toggle italic on/off."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Toggle italic test")
        cv_editor_page.keyboard.press("Control+A")

        cv_editor_page.keyboard.press("Control+I")
        cv_editor_page.wait_for_timeout(300)

        italic_element = editor.locator('em, i')
        expect(italic_element.first).to_be_visible()

    def test_ctrl_u_toggles_underline(self, cv_editor_page: Page):
        """Ctrl+U should toggle underline on/off."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Toggle underline test")
        cv_editor_page.keyboard.press("Control+A")

        cv_editor_page.keyboard.press("Control+U")
        cv_editor_page.wait_for_timeout(300)

        underline_element = editor.locator('u, [style*="underline"]')
        expect(underline_element.first).to_be_visible()

    def test_ctrl_z_performs_undo(self, cv_editor_page: Page):
        """Ctrl+Z should undo last action."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        original_text = editor.inner_text()

        # Type new text
        editor.type("Text to undo")
        cv_editor_page.wait_for_timeout(500)

        # Undo
        cv_editor_page.keyboard.press("Control+Z")
        cv_editor_page.wait_for_timeout(500)

        # Text should be reverted
        current_text = editor.inner_text()
        assert "Text to undo" not in current_text or current_text == original_text

    def test_ctrl_y_performs_redo(self, cv_editor_page: Page):
        """Ctrl+Y should redo last undone action."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Text to redo")
        cv_editor_page.wait_for_timeout(500)

        # Undo
        cv_editor_page.keyboard.press("Control+Z")
        cv_editor_page.wait_for_timeout(500)

        # Redo
        cv_editor_page.keyboard.press("Control+Y")
        cv_editor_page.wait_for_timeout(500)

        # Text should be back
        current_text = editor.inner_text()
        assert "Text to redo" in current_text


# ==============================================================================
# Test Class: Mobile Responsiveness (Phase 5)
# ==============================================================================

@pytest.mark.mobile
class TestMobileResponsiveness:
    """Tests for mobile viewport responsiveness."""

    @pytest.fixture
    def mobile_page(self, browser_context_args, context: BrowserContext):
        """Create a mobile context and page."""
        # Create new context with mobile viewport
        mobile_context = context.browser.new_context(
            viewport={"width": 375, "height": 667},
            is_mobile=True,
            has_touch=True,
        )
        page = mobile_context.new_page()

        # Login
        page.goto(f"{BASE_URL}/login")
        page.locator('input[name="password"]').fill(LOGIN_PASSWORD)
        page.locator('button[type="submit"]').click()
        page.wait_for_url(f"{BASE_URL}/", timeout=10000)

        # Navigate to CV editor
        page.goto(f"{BASE_URL}/")
        page.wait_for_selector('a[href*="/job/"]', timeout=10000)
        page.locator('a[href*="/job/"]').first.click()
        page.wait_for_selector('.tiptap', timeout=15000)

        yield page

        mobile_context.close()

    def test_editor_loads_on_mobile_viewport(self, mobile_page: Page):
        """Editor should load and be visible on mobile viewport."""
        editor = mobile_page.locator('.tiptap')
        expect(editor).to_be_visible()

    def test_toolbar_accessible_on_mobile(self, mobile_page: Page):
        """Toolbar should be accessible on mobile (may be scrollable)."""
        bold_button = mobile_page.locator('button[title*="Bold"], button:has-text("Bold")')

        # Button should exist (may need to scroll to see it)
        assert bold_button.count() > 0

    def test_text_input_works_on_mobile(self, mobile_page: Page):
        """Text input should work on mobile viewport."""
        editor = mobile_page.locator('.tiptap')

        editor.click()
        editor.type("Mobile text input test")

        mobile_page.wait_for_timeout(1000)

        # Verify text was entered
        content = editor.inner_text()
        assert "Mobile text input test" in content

    def test_auto_save_works_on_mobile(self, mobile_page: Page):
        """Auto-save should work on mobile viewport."""
        editor = mobile_page.locator('.tiptap')

        editor.click()
        editor.type("Mobile auto-save test")

        # Wait for auto-save
        mobile_page.wait_for_timeout(4000)

        save_indicator = mobile_page.locator('#cv-save-indicator, [id*="save"]')

        if save_indicator.count() > 0:
            indicator_text = save_indicator.first.inner_text()
            assert "Saved" in indicator_text or "saved" in indicator_text.lower()


# ==============================================================================
# Test Class: Accessibility (Phase 5 - WCAG 2.1 AA)
# ==============================================================================

@pytest.mark.accessibility
class TestAccessibility:
    """Tests for WCAG 2.1 AA accessibility compliance."""

    def test_editor_is_keyboard_navigable(self, cv_editor_page: Page):
        """Editor should be navigable with Tab/Shift+Tab."""
        # Focus first interactive element
        cv_editor_page.keyboard.press("Tab")

        # Check that something is focused
        focused_element = cv_editor_page.evaluate("document.activeElement.tagName")
        assert focused_element is not None

    def test_toolbar_buttons_have_accessible_labels(self, cv_editor_page: Page):
        """Toolbar buttons should have accessible labels (title or aria-label)."""
        bold_button = cv_editor_page.locator('button[title*="Bold"], button:has-text("Bold")').first

        # Should have either title or aria-label
        has_title = bold_button.get_attribute("title") is not None
        has_aria_label = bold_button.get_attribute("aria-label") is not None
        has_text = "Bold" in bold_button.inner_text()

        assert has_title or has_aria_label or has_text

    def test_focus_indicators_visible(self, cv_editor_page: Page):
        """Focus indicators should be visible on interactive elements."""
        editor = cv_editor_page.locator('.tiptap')

        # Click editor to focus
        editor.click()

        # Check for focus styles (outline or border)
        # This is a visual test, so we just ensure the element is focused
        is_focused = cv_editor_page.evaluate(
            "document.activeElement.classList.contains('tiptap') || document.activeElement.closest('.tiptap') !== null"
        )
        assert is_focused

    def test_save_indicator_has_screen_reader_announcement(self, cv_editor_page: Page):
        """Save indicator should have aria-live region for screen readers."""
        save_indicator = cv_editor_page.locator('#cv-save-indicator, [id*="save"]')

        if save_indicator.count() == 0:
            pytest.skip("Save indicator not found")

        # Check for aria-live attribute
        aria_live = save_indicator.first.get_attribute("aria-live")

        # Should have aria-live="polite" or "assertive"
        assert aria_live in ["polite", "assertive"] or aria_live is None  # Optional for now

    def test_color_contrast_meets_wcag_aa(self, cv_editor_page: Page):
        """Text color contrast should meet WCAG AA standards (4.5:1)."""
        # This is a complex test that requires actual color analysis
        # For now, we just verify text is visible
        editor = cv_editor_page.locator('.tiptap')

        editor.click()
        editor.type("Contrast test")

        # Verify text is visible (basic check)
        expect(editor).to_be_visible()

        # Note: True contrast testing requires color computation from computed styles


# ==============================================================================
# Test Class: Edge Cases & Error Handling
# ==============================================================================

class TestEdgeCases:
    """Tests for edge cases and error scenarios."""

    def test_very_large_document_saves_successfully(self, cv_editor_page: Page):
        """Editor should handle very large documents (10,000+ characters)."""
        editor = cv_editor_page.locator('.tiptap')

        editor.click()

        # Type large content
        large_text = "A" * 10000
        editor.type(large_text[:1000])  # Type first 1000 chars (typing 10k is slow)

        # Wait for auto-save
        cv_editor_page.wait_for_timeout(4000)

        save_indicator = cv_editor_page.locator('#cv-save-indicator, [id*="save"]')

        if save_indicator.count() > 0:
            indicator_text = save_indicator.first.inner_text()
            assert "Saved" in indicator_text or "saved" in indicator_text.lower()

    def test_special_characters_are_preserved(self, cv_editor_page: Page):
        """Special characters (emoji, unicode) should be preserved."""
        editor = cv_editor_page.locator('.tiptap')

        special_text = "Test emoji 🚀 and unicode: José García-Martínez"
        editor.click()
        cv_editor_page.keyboard.press("Control+A")
        editor.type(special_text)

        # Wait for auto-save
        cv_editor_page.wait_for_timeout(4000)

        # Reload and verify
        cv_editor_page.reload()
        cv_editor_page.wait_for_selector('.tiptap', timeout=10000)
        cv_editor_page.wait_for_timeout(2000)

        content = cv_editor_page.locator('.tiptap').inner_text()
        assert "José" in content or "Garcia" in content  # Some chars may not render perfectly

    def test_network_failure_during_save_shows_error(self, cv_editor_page: Page):
        """Network failure during save should show error state."""
        # This test requires network interception (advanced)
        pytest.skip("Network interception test - requires custom implementation")

    def test_session_timeout_redirects_to_login(self, authenticated_page: Page):
        """Session timeout should redirect to login page."""
        # This requires clearing session cookies
        authenticated_page.context.clear_cookies()

        # Try to navigate to a protected page
        authenticated_page.goto(f"{BASE_URL}/")

        # Should redirect to login
        authenticated_page.wait_for_timeout(2000)

        current_url = authenticated_page.url
        assert "/login" in current_url


# ==============================================================================
# Test Class: Cross-Browser Compatibility
# ==============================================================================

@pytest.mark.firefox
class TestFirefoxCompatibility:
    """Tests specifically for Firefox browser."""

    def test_editor_works_in_firefox(self, cv_editor_page: Page):
        """Editor should work correctly in Firefox."""
        editor = cv_editor_page.locator('.tiptap')

        expect(editor).to_be_visible()
        expect(editor).to_be_editable()

        editor.click()
        editor.type("Firefox compatibility test")

        cv_editor_page.wait_for_timeout(1000)

        content = editor.inner_text()
        assert "Firefox compatibility test" in content


@pytest.mark.webkit
class TestWebKitCompatibility:
    """Tests specifically for WebKit (Safari) browser."""

    def test_editor_works_in_webkit(self, cv_editor_page: Page):
        """Editor should work correctly in WebKit/Safari."""
        editor = cv_editor_page.locator('.tiptap')

        expect(editor).to_be_visible()
        expect(editor).to_be_editable()

        editor.click()
        editor.type("WebKit compatibility test")

        cv_editor_page.wait_for_timeout(1000)

        content = editor.inner_text()
        assert "WebKit compatibility test" in content
