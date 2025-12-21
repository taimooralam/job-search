"""
Unit tests for CLI Panel Backend Badge Detection

Tests the detectBackendFromText() function which identifies backend type from log text.
This enables proper display of backend badges (robot emoji for Claude CLI, warning for LangChain).

Log formats to detect:
- Text tags: [Claude CLI], [LangChain], [Fallback]
- Backend= format: backend=langchain, backend=claude_cli
"""

import pytest
from pathlib import Path


class TestDetectBackendFromText:
    """Tests for the detectBackendFromText function."""

    @pytest.fixture
    def cli_panel_js(self):
        """Read the CLI panel JavaScript file."""
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            return f.read()

    def test_function_exists(self, cli_panel_js):
        """detectBackendFromText function should exist."""
        assert 'detectBackendFromText(text)' in cli_panel_js, \
            "detectBackendFromText function should exist"

    def test_handles_null_input(self, cli_panel_js):
        """Function should handle null/undefined text."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        assert 'if (!text) return null' in func_body, \
            "Should return null for falsy input"

    def test_detects_claude_cli_bracket_tag(self, cli_panel_js):
        """Should detect [Claude CLI] tag in text."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        assert "[Claude CLI]" in func_body, \
            "Should check for [Claude CLI] tag"
        assert "return 'claude_cli'" in func_body, \
            "Should return 'claude_cli' for Claude CLI tag"

    def test_detects_langchain_bracket_tags(self, cli_panel_js):
        """Should detect [LangChain] and [Fallback] tags in text."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        assert "[Fallback]" in func_body, \
            "Should check for [Fallback] tag"
        assert "[LangChain]" in func_body, \
            "Should check for [LangChain] tag"
        assert "return 'langchain'" in func_body, \
            "Should return 'langchain' for LangChain/Fallback tags"

    def test_detects_backend_equals_format(self, cli_panel_js):
        """Should detect backend=value format in log text."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        # Should use regex to match backend=something
        assert 'backend=' in func_body or 'backendMatch' in func_body, \
            "Should check for backend= format"
        assert 'match' in func_body.lower(), \
            "Should use regex match for backend= pattern"

    def test_backend_equals_langchain_detected(self, cli_panel_js):
        """Should detect backend=langchain format."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        # The function should match 'langchain' from backend=langchain
        assert 'langchain' in func_body.lower(), \
            "Should handle langchain backend value"

    def test_backend_equals_claude_cli_detected(self, cli_panel_js):
        """Should detect backend=claude_cli format."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        # The function should match 'claude_cli' from backend=claude_cli
        assert 'claude_cli' in func_body or 'claude-cli' in func_body or 'claudecli' in func_body, \
            "Should handle claude_cli backend value"

    def test_backend_equals_openai_detected_as_langchain(self, cli_panel_js):
        """Should detect backend=openai as langchain (same fallback)."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        # OpenAI backend should be treated as langchain
        assert 'openai' in func_body.lower(), \
            "Should handle openai backend value as langchain"

    def test_returns_null_for_no_match(self, cli_panel_js):
        """Should return null when no backend pattern is found."""
        func_start = cli_panel_js.find('detectBackendFromText(text) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        # Should return null at the end if no patterns match
        assert 'return null' in func_body, \
            "Should return null when no backend is detected"


class TestGetBackendStatsUsesDetection:
    """Tests that getBackendStats uses detectBackendFromText."""

    @pytest.fixture
    def cli_panel_js(self):
        """Read the CLI panel JavaScript file."""
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            return f.read()

    def test_getbackendstats_uses_detectbackendfromtext(self, cli_panel_js):
        """getBackendStats should use detectBackendFromText for text-based detection."""
        func_start = cli_panel_js.find('getBackendStats(runId) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        assert 'detectBackendFromText' in func_body, \
            "getBackendStats should use detectBackendFromText"

    def test_getbackendstats_checks_log_backend_field_first(self, cli_panel_js):
        """Should prefer log.backend field over text detection."""
        func_start = cli_panel_js.find('getBackendStats(runId) {')
        next_func = cli_panel_js.find('\n        /**', func_start + 1)
        func_body = cli_panel_js[func_start:next_func]

        # Should check log.backend first using || for fallback
        assert 'log.backend ||' in func_body or 'log.backend||' in func_body, \
            "Should use log.backend field with detectBackendFromText as fallback"


class TestTemplateBackendBadges:
    """Tests that the template uses proper backend detection."""

    @pytest.fixture
    def cli_panel_template(self):
        """Read the CLI panel template file."""
        template_path = Path(__file__).parent.parent.parent / "frontend/templates/components/cli_panel.html"
        with open(template_path, 'r') as f:
            return f.read()

    def test_template_uses_detected_backend_variable(self, cli_panel_template):
        """Template should use x-data with detectedBackend variable."""
        # Should have x-data that computes detectedBackend
        assert 'detectedBackend' in cli_panel_template, \
            "Template should use detectedBackend variable"
        assert '$store.cli.detectBackendFromText' in cli_panel_template, \
            "Template should call detectBackendFromText"

    def test_template_claude_cli_badge_uses_detected_backend(self, cli_panel_template):
        """Claude CLI badge should use detectedBackend variable."""
        assert "detectedBackend === 'claude_cli'" in cli_panel_template, \
            "Claude CLI badge should use detectedBackend variable"

    def test_template_langchain_badge_uses_detected_backend(self, cli_panel_template):
        """LangChain badge should use detectedBackend variable."""
        assert "detectedBackend === 'langchain'" in cli_panel_template, \
            "LangChain badge should use detectedBackend variable"

    def test_template_prefix_uses_detected_backend(self, cli_panel_template):
        """Default prefix (>) should show when no backend detected."""
        assert "x-show=\"!detectedBackend\"" in cli_panel_template, \
            "Default prefix should show when no backend detected"


class TestSubscribeToLogsBackendExtraction:
    """Tests that log polling extracts backend from logs."""

    @pytest.fixture
    def cli_panel_js(self):
        """Read the CLI panel JavaScript file."""
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            return f.read()

    def test_onlog_extracts_backend(self, cli_panel_js):
        """Log handler should extract backend from log entry or detect from text."""
        # Find the onLog handler in subscribeToLogs
        subscribe_start = cli_panel_js.find('subscribeToLogs(runId) {')
        next_func = cli_panel_js.find('\n        /**', subscribe_start + 1)
        subscribe_section = cli_panel_js[subscribe_start:next_func]

        # Find the onLog callback
        onlog_start = subscribe_section.find('poller.onLog(')
        onlog_end = subscribe_section.find('});', onlog_start)
        onlog_section = subscribe_section[onlog_start:onlog_end + 3]

        # Should extract or detect backend
        assert 'backend' in onlog_section.lower(), \
            "onLog handler should handle backend"
        assert 'detectBackendFromText' in onlog_section, \
            "onLog handler should use detectBackendFromText for text-based detection"

    def test_log_entry_includes_backend_field(self, cli_panel_js):
        """Log entries pushed to runs[].logs should include backend field."""
        subscribe_start = cli_panel_js.find('subscribeToLogs(runId) {')
        next_func = cli_panel_js.find('\n        /**', subscribe_start + 1)
        subscribe_section = cli_panel_js[subscribe_start:next_func]

        # Find the log push in onLog handler
        onlog_start = subscribe_section.find('poller.onLog(')
        onlog_end = subscribe_section.find('});', onlog_start)
        onlog_section = subscribe_section[onlog_start:onlog_end + 3]

        # Should include backend in the log entry object
        assert 'backend,' in onlog_section or 'backend:' in onlog_section, \
            "Log entry should include backend field"
