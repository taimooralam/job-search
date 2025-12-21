"""
Unit tests for CLI Panel LogPoller fix

Tests the fix for LogPoller subscription timing issues:
1. startRun() now ALWAYS calls subscribeToLogs() regardless of panel state
2. toggle() and showPanel() now subscribe ALL running operations, not just activeRunId

Background:
- Before fix: subscribeToLogs() only called when panel was expanded
- After fix: subscribeToLogs() called immediately in startRun(), ensuring 200ms polling begins
- Fix handles: page refresh during batch operations, panel state changes
"""

import pytest
from pathlib import Path


class TestStartRunSubscription:
    """Tests that startRun() always subscribes to log polling."""

    def test_startrun_always_subscribes_to_logs(self):
        """startRun() should call subscribeToLogs() immediately, regardless of panel state."""
        # Arrange - Read the CLI panel JavaScript file
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Extract the startRun function
        startrun_start = js_content.find('startRun(detail) {')
        assert startrun_start > 0, "startRun function not found"

        # Find the end of startRun function (next function definition or closing brace)
        # Look for the next function definition after startRun
        next_func = js_content.find('\n        /**', startrun_start + 1)
        startrun_section = js_content[startrun_start:next_func] if next_func > 0 else js_content[startrun_start:startrun_start + 3000]

        # Assert - Should call subscribeToLogs(runId) unconditionally
        assert 'this.subscribeToLogs(runId)' in startrun_section, \
            "startRun should call subscribeToLogs(runId)"

        # Verify the comment indicating this is intentional
        assert '// Always subscribe to log polling when run starts' in startrun_section or \
               'Always subscribe to log polling' in startrun_section, \
            "Should have comment explaining why subscribeToLogs is always called"

    def test_startrun_subscribes_after_run_creation(self):
        """subscribeToLogs() should be called after the run entry is created."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Find startRun and extract its body
        startrun_start = js_content.find('startRun(detail) {')
        next_func = js_content.find('\n        /**', startrun_start + 1)
        startrun_section = js_content[startrun_start:next_func]

        # Assert - There are TWO subscribeToLogs calls:
        # 1. In the "run already exists" branch (line ~1073)
        # 2. After creating new run (line ~1125)
        # We need to find the SECOND one (after run creation)

        # Find the new run creation section
        run_creation = startrun_section.find('// Create run entry')
        assert run_creation > 0, "Run creation section not found"

        # Find subscribeToLogs after the creation section
        subscribe_after_creation = startrun_section.find('this.subscribeToLogs(runId)', run_creation)

        assert subscribe_after_creation > 0, "subscribeToLogs call after run creation not found"
        assert subscribe_after_creation > run_creation, \
            "subscribeToLogs should be called after run entry is created"

    def test_startrun_handles_existing_run_subscription(self):
        """When run already exists, startRun should still subscribe if no poller exists."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Find the "run already exists" branch
        startrun_start = js_content.find('startRun(detail) {')
        next_func = js_content.find('\n        /**', startrun_start + 1)
        startrun_section = js_content[startrun_start:next_func]

        # Assert - Should check for existing run and subscribe if no poller
        assert 'if (this.runs[runId])' in startrun_section, \
            "Should check if run already exists"
        assert '!this.runs[runId]._logPoller' in startrun_section, \
            "Should check if LogPoller exists for the run"

    def test_startrun_has_guard_against_undefined_runid(self):
        """startRun should guard against undefined/null runId."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        startrun_start = js_content.find('startRun(detail) {')
        next_func = js_content.find('\n        /**', startrun_start + 1)
        startrun_section = js_content[startrun_start:next_func]

        # Assert
        assert 'if (!runId)' in startrun_section, \
            "Should guard against undefined/null runId"
        assert 'console.error' in startrun_section or 'return' in startrun_section, \
            "Should log error or return early for invalid runId"


class TestToggleSubscription:
    """Tests that toggle() subscribes all running operations."""

    def test_toggle_subscribes_all_running_operations(self):
        """When expanding panel, toggle() should subscribe ALL running operations."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Find toggle function
        toggle_start = js_content.find('toggle() {')
        assert toggle_start > 0, "toggle function not found"

        # Extract toggle function body (until next function)
        next_func = js_content.find('\n        /**', toggle_start + 1)
        toggle_section = js_content[toggle_start:next_func] if next_func > 0 else js_content[toggle_start:toggle_start + 1000]

        # Assert - Should iterate through all runs, not just activeRunId
        assert 'for (const [runId, run] of Object.entries(this.runs))' in toggle_section, \
            "Should iterate through ALL runs, not just activeRunId"

        # Should check for running status
        assert "run?.status === 'running'" in toggle_section or \
               'run.status === "running"' in toggle_section, \
            "Should check if run is in running status"

        # Should check if LogPoller exists
        assert '!run._logPoller' in toggle_section, \
            "Should check if LogPoller already exists before subscribing"

        # Should call subscribeToLogs
        assert 'this.subscribeToLogs(runId)' in toggle_section, \
            "Should call subscribeToLogs for each running operation"

    def test_toggle_only_subscribes_when_expanding(self):
        """toggle() should only subscribe when expanding, not collapsing."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        toggle_start = js_content.find('toggle() {')
        next_func = js_content.find('\n        /**', toggle_start + 1)
        toggle_section = js_content[toggle_start:next_func]

        # Assert - Should have conditional check for expanded state
        assert 'if (this.expanded)' in toggle_section, \
            "Should only subscribe when panel is being expanded"

    def test_toggle_has_comment_explaining_subscription(self):
        """toggle() should have comment explaining why it subscribes all running ops."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        toggle_start = js_content.find('toggle() {')
        next_func = js_content.find('\n        /**', toggle_start + 1)
        toggle_section = js_content[toggle_start:next_func]

        # Assert - Should explain the fix
        assert 'running operations are polling' in toggle_section.lower() or \
               'all running operations' in toggle_section.lower(), \
            "Should have comment explaining why all running operations are subscribed"

        # Should mention the page refresh use case
        assert 'page refresh' in toggle_section.lower() or 'missed' in toggle_section.lower(), \
            "Should explain that this handles page refresh during batch ops"


class TestShowPanelSubscription:
    """Tests that showPanel() subscribes all running operations."""

    def test_showpanel_subscribes_all_running_operations(self):
        """showPanel() should subscribe ALL running operations when opened."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Find showPanel function
        showpanel_start = js_content.find('showPanel() {')
        assert showpanel_start > 0, "showPanel function not found"

        # Extract showPanel function body
        next_func = js_content.find('\n        /**', showpanel_start + 1)
        showpanel_section = js_content[showpanel_start:next_func] if next_func > 0 else js_content[showpanel_start:showpanel_start + 1000]

        # Assert - Should iterate through all runs
        assert 'for (const [runId, run] of Object.entries(this.runs))' in showpanel_section, \
            "Should iterate through ALL runs"

        # Should check for running status
        assert "run?.status === 'running'" in showpanel_section or \
               'run.status === "running"' in showpanel_section, \
            "Should filter for running operations"

        # Should check if poller exists
        assert '!run._logPoller' in showpanel_section, \
            "Should check if LogPoller already exists"

        # Should call subscribeToLogs
        assert 'this.subscribeToLogs(runId)' in showpanel_section, \
            "Should call subscribeToLogs for each running operation"

    def test_showpanel_sets_expanded_true(self):
        """showPanel() should set expanded to true."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        showpanel_start = js_content.find('showPanel() {')
        next_func = js_content.find('\n        /**', showpanel_start + 1)
        showpanel_section = js_content[showpanel_start:next_func]

        # Assert
        assert 'this.expanded = true' in showpanel_section, \
            "showPanel should set expanded to true"

    def test_showpanel_saves_state(self):
        """showPanel() should save state after changes."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        showpanel_start = js_content.find('showPanel() {')
        next_func = js_content.find('\n        /**', showpanel_start + 1)
        showpanel_section = js_content[showpanel_start:next_func]

        # Assert
        assert 'this._saveState()' in showpanel_section, \
            "showPanel should save state"

    def test_showpanel_has_comment_explaining_subscription(self):
        """showPanel() should have comment explaining subscription logic."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        showpanel_start = js_content.find('showPanel() {')
        next_func = js_content.find('\n        /**', showpanel_start + 1)
        showpanel_section = js_content[showpanel_start:next_func]

        # Assert
        assert 'running operations are polling' in showpanel_section.lower() or \
               'all running operations' in showpanel_section.lower(), \
            "Should explain that all running operations get subscribed"


class TestSubscribeToLogsGuards:
    """Tests guards in subscribeToLogs() to prevent duplicate subscriptions."""

    def test_subscribetologs_guards_against_undefined_runid(self):
        """subscribeToLogs() should guard against undefined/null runId."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Find subscribeToLogs function
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        assert subscribe_start > 0, "subscribeToLogs function not found"

        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func] if next_func > 0 else js_content[subscribe_start:subscribe_start + 2000]

        # Assert
        assert 'if (!runId)' in subscribe_section, \
            "Should guard against undefined/null runId"
        assert 'console.error' in subscribe_section, \
            "Should log error for invalid runId"

    def test_subscribetologs_checks_run_exists(self):
        """subscribeToLogs() should verify run exists before subscribing."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert
        assert 'if (!this.runs[runId])' in subscribe_section, \
            "Should check if run exists before subscribing"
        assert 'console.warn' in subscribe_section or 'return' in subscribe_section, \
            "Should warn or return early if run doesn't exist"

    def test_subscribetologs_prevents_duplicate_subscriptions(self):
        """subscribeToLogs() should not create duplicate pollers."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert
        assert 'if (this.runs[runId]._logPoller)' in subscribe_section, \
            "Should check if LogPoller already exists"
        assert 'Already subscribed' in subscribe_section or 'return' in subscribe_section, \
            "Should return early if already subscribed"

    def test_subscribetologs_checks_logpoller_availability(self):
        """subscribeToLogs() should verify LogPoller class is available."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert
        assert 'typeof window.LogPoller' in subscribe_section, \
            "Should check if LogPoller is available"
        assert 'console.error' in subscribe_section, \
            "Should log error if LogPoller is not available"


class TestLogPollerIntegration:
    """Tests integration with LogPoller class."""

    def test_logpoller_instantiated_with_runid(self):
        """LogPoller should be instantiated with runId parameter."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert
        assert 'new window.LogPoller(runId' in subscribe_section, \
            "Should create LogPoller with runId"

    def test_logpoller_stored_in_run_object(self):
        """LogPoller instance should be stored in run._logPoller."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert
        assert 'this.runs[runId]._logPoller = poller' in subscribe_section or \
               'this.runs[runId]._logPoller=' in subscribe_section, \
            "Should store LogPoller instance in run._logPoller"

    def test_logpoller_start_called_with_error_handling(self):
        """LogPoller.start() should be called with .catch() error handling."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert - Should call poller.start() with .catch()
        assert 'poller.start()' in subscribe_section, \
            "Should call poller.start()"
        assert '.catch(' in subscribe_section, \
            "Should have .catch() error handler for poller.start()"

    def test_logpoller_callbacks_configured(self):
        """LogPoller callbacks (onLog, onLayerStatus, onComplete, onError) should be configured."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        subscribe_start = js_content.find('subscribeToLogs(runId) {')
        next_func = js_content.find('\n        /**', subscribe_start + 1)
        subscribe_section = js_content[subscribe_start:next_func]

        # Assert
        assert 'poller.onLog(' in subscribe_section, \
            "Should configure onLog callback"
        assert 'poller.onLayerStatus(' in subscribe_section, \
            "Should configure onLayerStatus callback"
        assert 'poller.onComplete(' in subscribe_section, \
            "Should configure onComplete callback"
        assert 'poller.onError(' in subscribe_section, \
            "Should configure onError callback"


class TestEdgeCases:
    """Edge case tests for LogPoller subscription."""

    def test_fetchrunlogs_subscribes_for_running_operations(self):
        """fetchRunLogs() should subscribe to logs if operation is running."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act - Find fetchRunLogs
        fetch_start = js_content.find('async fetchRunLogs(runId, jobId')
        assert fetch_start > 0, "fetchRunLogs function not found"

        next_func = js_content.find('\n        /**', fetch_start + 1)
        fetch_section = js_content[fetch_start:next_func] if next_func > 0 else js_content[fetch_start:fetch_start + 3000]

        # Assert - Should subscribe for running operations
        assert "opStatus === 'running'" in fetch_section or \
               "data.status === 'running'" in fetch_section, \
            "Should check if operation is running"
        assert 'this.subscribeToLogs(runId)' in fetch_section, \
            "Should subscribe to logs for running operations"

    def test_switchtorun_subscribes_if_needed(self):
        """switchToRun() should subscribe if run is active but not polling."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        switch_start = js_content.find('switchToRun(runId) {')
        assert switch_start > 0, "switchToRun function not found"

        next_func = js_content.find('\n        /**', switch_start + 1)
        switch_section = js_content[switch_start:next_func] if next_func > 0 else js_content[switch_start:switch_start + 1000]

        # Assert
        assert "status === 'running'" in switch_section, \
            "Should check if run is still active"
        assert '!this.runs[runId]._logPoller' in switch_section, \
            "Should check if polling is already active"
        assert 'this.subscribeToLogs(runId)' in switch_section, \
            "Should subscribe if needed"

    def test_closerun_cleans_up_logpoller(self):
        """closeRun() should stop LogPoller before removing run."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        close_start = js_content.find('closeRun(runId) {')
        assert close_start > 0, "closeRun function not found"

        next_func = js_content.find('\n        /**', close_start + 1)
        close_section = js_content[close_start:next_func] if next_func > 0 else js_content[close_start:close_start + 1500]

        # Assert
        assert 'this.runs[runId]?._logPoller' in close_section, \
            "Should check for LogPoller existence"
        assert '.stop()' in close_section, \
            "Should call stop() on LogPoller"
        assert 'delete this.runs[runId]' in close_section, \
            "Should delete run entry after cleanup"


class TestComments:
    """Tests that critical comments are present explaining the fix."""

    def test_startrun_has_explanation_comment(self):
        """startRun() should have comment explaining immediate subscription."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        startrun_start = js_content.find('startRun(detail) {')
        next_func = js_content.find('\n        /**', startrun_start + 1)
        startrun_section = js_content[startrun_start:next_func]

        # Assert - Find the SECOND subscribeToLogs call (after run creation)
        run_creation = startrun_section.find('// Create run entry')
        subscribe_line_start = startrun_section.find('this.subscribeToLogs(runId)', run_creation)

        # Look for comment within 200 chars before the call
        comment_area = startrun_section[max(0, subscribe_line_start - 200):subscribe_line_start + 50]

        assert '//' in comment_area or '/*' in comment_area, \
            "Should have comment explaining why subscribeToLogs is always called"

    def test_toggle_has_explanation_comment(self):
        """toggle() should explain why it subscribes all running operations."""
        # Arrange
        cli_panel_path = Path(__file__).parent.parent.parent / "frontend/static/js/cli-panel.js"
        with open(cli_panel_path, 'r') as f:
            js_content = f.read()

        # Act
        toggle_start = js_content.find('toggle() {')
        next_func = js_content.find('\n        /**', toggle_start + 1)
        toggle_section = js_content[toggle_start:next_func]

        # Assert
        # Look for comment explaining the subscription loop
        for_loop_start = toggle_section.find('for (const [runId, run]')
        comment_area = toggle_section[max(0, for_loop_start - 200):for_loop_start + 100]

        assert '//' in comment_area or '/*' in comment_area, \
            "Should have comment explaining the subscription loop"
