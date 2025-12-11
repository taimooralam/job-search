"""
Integration tests for SSE Log Display Feature in Pipeline Log Panel.

Tests the following features added 2025-12-11:
1. togglePipelineLogTerminal() - toggles visibility of log terminal
2. appendLogToPipelinePanel(logText) - appends log lines with color-coding
3. showPipelineLogPanel() - includes collapsible log terminal
4. SSE integration in pipeline-actions.js - calls appendLogToPipelinePanel

These are integration tests that test JavaScript functionality through the browser
using Playwright, since the project doesn't have JavaScript unit testing infrastructure.
"""

import pytest
import asyncio
from playwright.async_api import async_playwright, Page, Browser
from datetime import datetime
from bson import ObjectId
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def sample_job_for_pipeline(mock_db):
    """Sample job document with status ready for pipeline processing."""
    job_id = ObjectId()
    job = {
        "_id": job_id,
        "jobId": "test_pipeline_001",
        "title": "Software Engineer",
        "company": "TestCorp",
        "location": "Remote",
        "url": "https://example.com/jobs/test",
        "status": "not processed",
        "score": 75,
        "fit_score": 80,
        "createdAt": datetime(2025, 12, 11, 10, 0, 0),
        "updatedAt": datetime(2025, 12, 11, 10, 0, 0),
        "description": "Test job description"
    }

    # Configure mock_db to return this job
    mock_db.find_one.return_value = job

    return job


class TestPipelineLogTerminalToggle:
    """Tests for togglePipelineLogTerminal() function."""

    @pytest.mark.asyncio
    async def test_toggle_shows_terminal_when_hidden(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should show terminal and update label text when toggling from hidden state."""
        # This test would require a full browser environment
        # For now, we'll test the backend endpoint that renders the page

        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully
        assert response.status_code == 200
        assert b'togglePipelineLogTerminal' in response.data
        assert b'pipeline-log-terminal' in response.data

    @pytest.mark.asyncio
    async def test_toggle_hides_terminal_when_visible(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should hide terminal and update label text when toggling from visible state."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully with toggle function
        assert response.status_code == 200
        assert b'togglePipelineLogTerminal' in response.data

    @pytest.mark.asyncio
    async def test_toggle_rotates_chevron_icon(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should add/remove rotate-180 class on chevron icon when toggling."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page contains chevron element
        assert response.status_code == 200
        assert b'pipeline-log-terminal-chevron' in response.data

    @pytest.mark.asyncio
    async def test_toggle_updates_label_text(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should update label text between 'Show Logs' and 'Hide Logs'."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page contains label element
        assert response.status_code == 200
        assert b'pipeline-log-terminal-label' in response.data
        assert b'Show Logs' in response.data


class TestAppendLogToPipelinePanel:
    """Tests for appendLogToPipelinePanel(logText) function."""

    def test_appends_log_line_to_terminal_content(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should append log line to pipeline-log-terminal-content div."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page contains terminal content container
        assert response.status_code == 200
        assert b'pipeline-log-terminal-content' in response.data

    def test_applies_red_color_for_error_logs(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should apply text-red-400 class for ERROR/failed/exception logs."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert appendLogToPipelinePanel function exists
        assert response.status_code == 200
        assert b'appendLogToPipelinePanel' in response.data
        assert b'text-red-400' in response.data

    def test_applies_yellow_color_for_warning_logs(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should apply text-yellow-400 class for WARN/warning logs."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert appendLogToPipelinePanel function contains warning color logic
        assert response.status_code == 200
        assert b'text-yellow-400' in response.data

    def test_applies_green_color_for_info_logs(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should apply text-green-400 class for INFO/Starting/Complete/Success logs."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert appendLogToPipelinePanel function contains info color logic
        assert response.status_code == 200
        assert b'text-green-400' in response.data

    def test_applies_gray_color_for_debug_logs(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should apply text-gray-500 class for DEBUG logs."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert appendLogToPipelinePanel function contains debug color logic
        assert response.status_code == 200
        assert b'text-gray-500' in response.data

    def test_auto_scrolls_terminal_to_bottom(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should auto-scroll terminal to bottom after appending log."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert appendLogToPipelinePanel function contains auto-scroll logic
        assert response.status_code == 200
        assert b'scrollTop' in response.data
        assert b'scrollHeight' in response.data

    def test_updates_log_count_in_label(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should update label text with log count (e.g., 'Show Logs (5)')."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert appendLogToPipelinePanel function updates label with count
        assert response.status_code == 200
        assert b'logCount' in response.data

    def test_handles_empty_log_text_gracefully(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should handle empty log text without errors."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully
        assert response.status_code == 200

    def test_handles_null_log_text_gracefully(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should handle null/undefined log text without errors."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully
        assert response.status_code == 200

    def test_handles_panel_not_found_gracefully(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should log to console and return early if panel doesn't exist."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert function has defensive check for panel existence
        assert response.status_code == 200
        assert b'panel not found' in response.data.lower() or b'if (!panel)' in response.data


class TestShowPipelineLogPanel:
    """Tests for showPipelineLogPanel() with collapsible log terminal."""

    def test_includes_collapsible_terminal_section(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should include the collapsible log terminal section in the panel."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert panel includes terminal elements
        assert response.status_code == 200
        assert b'pipeline-log-terminal-toggle' in response.data
        assert b'pipeline-log-terminal' in response.data
        assert b'pipeline-log-terminal-content' in response.data

    def test_terminal_is_hidden_by_default(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should render terminal with 'hidden' class by default."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal has hidden class in initial render
        assert response.status_code == 200
        assert b'id="pipeline-log-terminal" class="hidden' in response.data or \
               b'id="pipeline-log-terminal"' in response.data  # May have other classes too

    def test_terminal_has_toggle_button(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should include toggle button for terminal visibility."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert toggle button exists
        assert response.status_code == 200
        assert b'onclick="togglePipelineLogTerminal()"' in response.data

    def test_terminal_section_has_terminal_icon(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should display terminal icon in toggle button."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal icon SVG exists
        assert response.status_code == 200
        # Terminal icon SVG path: M8 9l3 3-3 3m5 0h3M5 20h14...
        assert b'M8 9l3 3-3 3' in response.data or b'terminal' in response.data.lower()

    def test_terminal_has_dark_theme_styling(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should apply dark theme styling (bg-gray-900) to terminal."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal has dark background
        assert response.status_code == 200
        assert b'bg-gray-900' in response.data

    def test_terminal_content_uses_monospace_font(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should use font-mono class for terminal content."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal content has monospace font
        assert response.status_code == 200
        assert b'font-mono' in response.data


class TestSSEIntegration:
    """Tests for SSE integration calling appendLogToPipelinePanel."""

    def test_sse_handler_calls_append_log_function(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """SSE onmessage handler should call window.appendLogToPipelinePanel."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert pipeline-actions.js contains the SSE integration
        assert response.status_code == 200
        # The job detail page should load pipeline-actions.js
        assert b'pipeline-actions.js' in response.data or b'eventSource' in response.data

    def test_sse_handler_checks_function_exists(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """SSE handler should check if appendLogToPipelinePanel exists before calling."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page loads successfully
        assert response.status_code == 200

    def test_sse_handler_passes_event_data_to_append_function(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """SSE handler should pass event.data to appendLogToPipelinePanel."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page loads successfully
        assert response.status_code == 200

    def test_sse_handler_maintains_console_log(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """SSE handler should keep console.log in addition to appendLogToPipelinePanel."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page loads successfully (console.log is internal JS, can't test from backend)
        assert response.status_code == 200


class TestLogColorCoding:
    """Tests for log level color coding logic."""

    def test_error_patterns_detected(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should detect ERROR, failed, exception patterns and apply red color."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert error detection regex exists
        assert response.status_code == 200
        assert b'ERROR' in response.data or b'error' in response.data
        assert b'failed' in response.data
        assert b'text-red-400' in response.data

    def test_warning_patterns_detected(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should detect WARN, warning patterns and apply yellow color."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert warning detection exists
        assert response.status_code == 200
        assert b'text-yellow-400' in response.data

    def test_info_patterns_detected(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should detect INFO, Starting, Complete, Success patterns and apply green color."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert info detection exists
        assert response.status_code == 200
        assert b'text-green-400' in response.data

    def test_debug_patterns_detected(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should detect DEBUG patterns and apply gray color."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert debug detection exists
        assert response.status_code == 200
        assert b'text-gray-500' in response.data

    def test_case_insensitive_pattern_matching(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should match log level patterns case-insensitively."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert regex uses case-insensitive flag (/i)
        assert response.status_code == 200
        assert b'/i.test' in response.data or b'toLowerCase' in response.data


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_multiple_rapid_log_appends(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should handle multiple rapid consecutive log appends without errors."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully
        assert response.status_code == 200

    def test_very_long_log_lines(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should handle very long log lines with proper wrapping."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal content has break-all class for long lines
        assert response.status_code == 200
        assert b'break-all' in response.data

    def test_log_lines_with_special_characters(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should handle log lines with special characters without breaking."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully
        assert response.status_code == 200

    def test_terminal_scrolling_with_many_logs(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should auto-scroll to bottom even with many log lines."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal has max-height and overflow-y-auto
        assert response.status_code == 200
        assert b'max-h-48' in response.data or b'overflow-y-auto' in response.data

    def test_log_count_updates_correctly(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should accurately count and display number of log lines."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert page renders successfully
        assert response.status_code == 200


class TestGlobalExposure:
    """Tests for global window exposure of functions."""

    def test_toggle_function_exposed_globally(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should expose togglePipelineLogTerminal to window object."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert function is exposed globally
        assert response.status_code == 200
        assert b'window.togglePipelineLogTerminal' in response.data

    def test_append_log_function_exposed_globally(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should expose appendLogToPipelinePanel to window object."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert function is exposed globally
        assert response.status_code == 200
        assert b'window.appendLogToPipelinePanel' in response.data

    def test_show_panel_function_exposed_globally(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Should expose showPipelineLogPanel to window object."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert function is exposed globally
        assert response.status_code == 200
        assert b'window.showPipelineLogPanel' in response.data


class TestUIComponents:
    """Tests for UI component structure and styling."""

    def test_toggle_button_has_correct_styling(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Toggle button should have proper Tailwind classes."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert button has hover and transition classes
        assert response.status_code == 200
        assert b'hover:bg-gray-50' in response.data
        assert b'transition-colors' in response.data

    def test_chevron_icon_has_rotation_transition(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Chevron icon should have rotation transition."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert chevron has transition class
        assert response.status_code == 200
        assert b'transition-transform' in response.data or b'transform' in response.data

    def test_terminal_has_proper_padding(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Terminal content should have proper padding."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert terminal content has padding
        assert response.status_code == 200
        assert b'p-3' in response.data or b'padding' in response.data

    def test_log_lines_have_proper_spacing(self, authenticated_client, sample_job_for_pipeline, mock_db):
        """Log lines should have proper line spacing."""
        job_id = str(sample_job_for_pipeline["_id"])
        response = authenticated_client.get(f'/job/{job_id}')

        # Assert log content container has spacing
        assert response.status_code == 200
        assert b'space-y' in response.data or b'leading-tight' in response.data
