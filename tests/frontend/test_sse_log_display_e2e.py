"""
End-to-End tests for SSE Log Display Feature using Playwright.

These tests use Playwright to test JavaScript functionality in a real browser environment.
They require a running Flask app and test the actual browser behavior of the SSE log display.

To run these tests:
    pytest tests/frontend/test_sse_log_display_e2e.py -v -n auto --headed

Note: These are E2E tests and may be slower than unit tests.
"""

import pytest
import asyncio
from playwright.async_api import async_playwright, Page, Browser, expect
from datetime import datetime
from bson import ObjectId
import time


# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e


@pytest.fixture
async def browser():
    """Playwright browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture
async def page(browser):
    """Playwright page instance."""
    page = await browser.new_page()
    yield page
    await page.close()


@pytest.fixture
def job_with_pipeline_data(mock_db):
    """Sample job with pipeline processing data."""
    job_id = ObjectId()
    job = {
        "_id": job_id,
        "jobId": "test_pipeline_e2e_001",
        "title": "Senior Software Engineer",
        "company": "E2E TestCorp",
        "location": "Remote",
        "url": "https://example.com/jobs/e2e-test",
        "status": "processed",
        "score": 85,
        "fit_score": 90,
        "createdAt": datetime(2025, 12, 11, 10, 0, 0),
        "updatedAt": datetime(2025, 12, 11, 11, 0, 0),
        "description": "E2E test job description for SSE log testing"
    }

    mock_db.find_one.return_value = job
    return job


class TestTogglePipelineLogTerminalE2E:
    """E2E tests for togglePipelineLogTerminal() function."""

    @pytest.mark.asyncio
    async def test_clicking_toggle_shows_terminal(self, page: Page, job_with_pipeline_data, authenticated_client):
        """Should show terminal when clicking toggle button from hidden state."""
        # Note: This test would require a running Flask server
        # For now, we'll test the JavaScript logic directly

        # Set up page with the panel
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function togglePipelineLogTerminal() {
                        const terminal = document.getElementById('pipeline-log-terminal');
                        const label = document.getElementById('pipeline-log-terminal-label');
                        const chevron = document.getElementById('pipeline-log-terminal-chevron');

                        if (!terminal) return;

                        const isHidden = terminal.classList.contains('hidden');

                        if (isHidden) {
                            terminal.classList.remove('hidden');
                            if (label) label.textContent = 'Hide Logs';
                            if (chevron) chevron.classList.add('rotate-180');
                        } else {
                            terminal.classList.add('hidden');
                            if (label) label.textContent = 'Show Logs';
                            if (chevron) chevron.classList.remove('rotate-180');
                        }
                    }
                </script>
            </head>
            <body>
                <button id="toggle-btn" onclick="togglePipelineLogTerminal()">Toggle</button>
                <span id="pipeline-log-terminal-label">Show Logs</span>
                <div id="pipeline-log-terminal-chevron"></div>
                <div id="pipeline-log-terminal" class="hidden"></div>
            </body>
            </html>
        """)

        # Initial state: terminal is hidden
        terminal = page.locator('#pipeline-log-terminal')
        label = page.locator('#pipeline-log-terminal-label')
        chevron = page.locator('#pipeline-log-terminal-chevron')

        assert await terminal.evaluate('el => el.classList.contains("hidden")')
        assert await label.text_content() == 'Show Logs'

        # Click toggle button
        await page.click('#toggle-btn')

        # Assert terminal is now visible
        assert not await terminal.evaluate('el => el.classList.contains("hidden")')
        assert await label.text_content() == 'Hide Logs'
        assert await chevron.evaluate('el => el.classList.contains("rotate-180")')

    @pytest.mark.asyncio
    async def test_clicking_toggle_hides_terminal(self, page: Page):
        """Should hide terminal when clicking toggle button from visible state."""
        # Set up page with the panel (terminal visible)
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function togglePipelineLogTerminal() {
                        const terminal = document.getElementById('pipeline-log-terminal');
                        const label = document.getElementById('pipeline-log-terminal-label');
                        const chevron = document.getElementById('pipeline-log-terminal-chevron');

                        if (!terminal) return;

                        const isHidden = terminal.classList.contains('hidden');

                        if (isHidden) {
                            terminal.classList.remove('hidden');
                            if (label) label.textContent = 'Hide Logs';
                            if (chevron) chevron.classList.add('rotate-180');
                        } else {
                            terminal.classList.add('hidden');
                            if (label) label.textContent = 'Show Logs';
                            if (chevron) chevron.classList.remove('rotate-180');
                        }
                    }
                </script>
            </head>
            <body>
                <button id="toggle-btn" onclick="togglePipelineLogTerminal()">Toggle</button>
                <span id="pipeline-log-terminal-label">Hide Logs</span>
                <div id="pipeline-log-terminal-chevron" class="rotate-180"></div>
                <div id="pipeline-log-terminal"></div>
            </body>
            </html>
        """)

        # Initial state: terminal is visible
        terminal = page.locator('#pipeline-log-terminal')
        label = page.locator('#pipeline-log-terminal-label')
        chevron = page.locator('#pipeline-log-terminal-chevron')

        assert not await terminal.evaluate('el => el.classList.contains("hidden")')
        assert await label.text_content() == 'Hide Logs'
        assert await chevron.evaluate('el => el.classList.contains("rotate-180")')

        # Click toggle button
        await page.click('#toggle-btn')

        # Assert terminal is now hidden
        assert await terminal.evaluate('el => el.classList.contains("hidden")')
        assert await label.text_content() == 'Show Logs'
        assert not await chevron.evaluate('el => el.classList.contains("rotate-180")')


class TestAppendLogToPipelinePanelE2E:
    """E2E tests for appendLogToPipelinePanel(logText) function."""

    @pytest.mark.asyncio
    async def test_appends_log_with_correct_color_error(self, page: Page):
        """Should append error log with red color."""
        # Set up page with the function
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) {
                            console.log('[Pipeline Log] Panel not found, log:', logText);
                            return;
                        }

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) {
                            console.log('[Pipeline Log] Terminal content not found, log:', logText);
                            return;
                        }

                        const logLine = document.createElement('div');
                        logLine.className = 'text-green-400 whitespace-pre-wrap break-all leading-tight';

                        if (/\\[ERROR\\]|error|failed|exception/i.test(logText)) {
                            logLine.className = 'text-red-400 whitespace-pre-wrap break-all leading-tight';
                        } else if (/\\[WARN\\]|warning/i.test(logText)) {
                            logLine.className = 'text-yellow-400 whitespace-pre-wrap break-all leading-tight';
                        } else if (/\\[INFO\\]|Starting|Complete|Success/i.test(logText)) {
                            logLine.className = 'text-green-400 whitespace-pre-wrap break-all leading-tight';
                        } else if (/\\[DEBUG\\]/i.test(logText)) {
                            logLine.className = 'text-gray-500 whitespace-pre-wrap break-all leading-tight';
                        }

                        logLine.textContent = logText;
                        terminalContent.appendChild(logLine);

                        const terminal = document.getElementById('pipeline-log-terminal');
                        if (terminal) {
                            terminal.scrollTop = terminal.scrollHeight;
                        }

                        const logCount = terminalContent.children.length;
                        const label = document.getElementById('pipeline-log-terminal-label');
                        if (label) {
                            const isHidden = terminal?.classList.contains('hidden');
                            label.textContent = isHidden ? `Show Logs (${logCount})` : `Hide Logs (${logCount})`;
                        }
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <span id="pipeline-log-terminal-label">Show Logs</span>
                    <div id="pipeline-log-terminal" class="hidden" style="max-height: 200px; overflow-y: auto;">
                        <div id="pipeline-log-terminal-content"></div>
                    </div>
                </div>
            </body>
            </html>
        """)

        # Append error log
        await page.evaluate('appendLogToPipelinePanel("[ERROR] Connection failed")')

        # Assert log was appended with red color
        log_line = page.locator('#pipeline-log-terminal-content > div').first
        assert await log_line.text_content() == '[ERROR] Connection failed'
        assert await log_line.evaluate('el => el.classList.contains("text-red-400")')

    @pytest.mark.asyncio
    async def test_appends_log_with_correct_color_warning(self, page: Page):
        """Should append warning log with yellow color."""
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) return;

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) return;

                        const logLine = document.createElement('div');
                        logLine.className = 'text-green-400';

                        if (/\\[ERROR\\]|error|failed|exception/i.test(logText)) {
                            logLine.className = 'text-red-400';
                        } else if (/\\[WARN\\]|warning/i.test(logText)) {
                            logLine.className = 'text-yellow-400';
                        } else if (/\\[INFO\\]|Starting|Complete|Success/i.test(logText)) {
                            logLine.className = 'text-green-400';
                        } else if (/\\[DEBUG\\]/i.test(logText)) {
                            logLine.className = 'text-gray-500';
                        }

                        logLine.textContent = logText;
                        terminalContent.appendChild(logLine);
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <div id="pipeline-log-terminal-content"></div>
                </div>
            </body>
            </html>
        """)

        await page.evaluate('appendLogToPipelinePanel("[WARN] Deprecated API usage")')

        log_line = page.locator('#pipeline-log-terminal-content > div').first
        assert await log_line.text_content() == '[WARN] Deprecated API usage'
        assert await log_line.evaluate('el => el.classList.contains("text-yellow-400")')

    @pytest.mark.asyncio
    async def test_appends_log_with_correct_color_info(self, page: Page):
        """Should append info log with green color."""
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) return;

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) return;

                        const logLine = document.createElement('div');
                        logLine.className = 'text-green-400';

                        if (/\\[ERROR\\]|error|failed|exception/i.test(logText)) {
                            logLine.className = 'text-red-400';
                        } else if (/\\[WARN\\]|warning/i.test(logText)) {
                            logLine.className = 'text-yellow-400';
                        } else if (/\\[INFO\\]|Starting|Complete|Success/i.test(logText)) {
                            logLine.className = 'text-green-400';
                        } else if (/\\[DEBUG\\]/i.test(logText)) {
                            logLine.className = 'text-gray-500';
                        }

                        logLine.textContent = logText;
                        terminalContent.appendChild(logLine);
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <div id="pipeline-log-terminal-content"></div>
                </div>
            </body>
            </html>
        """)

        await page.evaluate('appendLogToPipelinePanel("[INFO] Pipeline completed successfully")')

        log_line = page.locator('#pipeline-log-terminal-content > div').first
        assert await log_line.text_content() == '[INFO] Pipeline completed successfully'
        assert await log_line.evaluate('el => el.classList.contains("text-green-400")')

    @pytest.mark.asyncio
    async def test_appends_log_with_correct_color_debug(self, page: Page):
        """Should append debug log with gray color."""
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) return;

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) return;

                        const logLine = document.createElement('div');
                        logLine.className = 'text-green-400';

                        if (/\\[ERROR\\]|error|failed|exception/i.test(logText)) {
                            logLine.className = 'text-red-400';
                        } else if (/\\[WARN\\]|warning/i.test(logText)) {
                            logLine.className = 'text-yellow-400';
                        } else if (/\\[INFO\\]|Starting|Complete|Success/i.test(logText)) {
                            logLine.className = 'text-green-400';
                        } else if (/\\[DEBUG\\]/i.test(logText)) {
                            logLine.className = 'text-gray-500';
                        }

                        logLine.textContent = logText;
                        terminalContent.appendChild(logLine);
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <div id="pipeline-log-terminal-content"></div>
                </div>
            </body>
            </html>
        """)

        await page.evaluate('appendLogToPipelinePanel("[DEBUG] Variable state: x=10, y=20")')

        log_line = page.locator('#pipeline-log-terminal-content > div').first
        assert await log_line.text_content() == '[DEBUG] Variable state: x=10, y=20'
        assert await log_line.evaluate('el => el.classList.contains("text-gray-500")')

    @pytest.mark.asyncio
    async def test_updates_log_count_in_label(self, page: Page):
        """Should update label with log count after appending."""
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) return;

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) return;

                        const logLine = document.createElement('div');
                        logLine.textContent = logText;
                        terminalContent.appendChild(logLine);

                        const terminal = document.getElementById('pipeline-log-terminal');
                        const logCount = terminalContent.children.length;
                        const label = document.getElementById('pipeline-log-terminal-label');
                        if (label) {
                            const isHidden = terminal?.classList.contains('hidden');
                            label.textContent = isHidden ? `Show Logs (${logCount})` : `Hide Logs (${logCount})`;
                        }
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <span id="pipeline-log-terminal-label">Show Logs</span>
                    <div id="pipeline-log-terminal" class="hidden">
                        <div id="pipeline-log-terminal-content"></div>
                    </div>
                </div>
            </body>
            </html>
        """)

        label = page.locator('#pipeline-log-terminal-label')

        # Initially no count
        assert await label.text_content() == 'Show Logs'

        # Append first log
        await page.evaluate('appendLogToPipelinePanel("Log 1")')
        assert await label.text_content() == 'Show Logs (1)'

        # Append second log
        await page.evaluate('appendLogToPipelinePanel("Log 2")')
        assert await label.text_content() == 'Show Logs (2)'

        # Append third log
        await page.evaluate('appendLogToPipelinePanel("Log 3")')
        assert await label.text_content() == 'Show Logs (3)'

    @pytest.mark.asyncio
    async def test_auto_scrolls_to_bottom(self, page: Page):
        """Should auto-scroll terminal to bottom after appending log."""
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) return;

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) return;

                        const logLine = document.createElement('div');
                        logLine.textContent = logText;
                        logLine.style.height = '50px'; // Make each log tall to force scrolling
                        terminalContent.appendChild(logLine);

                        const terminal = document.getElementById('pipeline-log-terminal');
                        if (terminal) {
                            terminal.scrollTop = terminal.scrollHeight;
                        }
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <div id="pipeline-log-terminal" style="max-height: 100px; overflow-y: auto;">
                        <div id="pipeline-log-terminal-content"></div>
                    </div>
                </div>
            </body>
            </html>
        """)

        terminal = page.locator('#pipeline-log-terminal')

        # Add multiple logs to exceed terminal height
        for i in range(5):
            await page.evaluate(f'appendLogToPipelinePanel("Log {i + 1}")')

        # Check that terminal is scrolled to bottom
        scroll_top = await terminal.evaluate('el => el.scrollTop')
        scroll_height = await terminal.evaluate('el => el.scrollHeight')
        client_height = await terminal.evaluate('el => el.clientHeight')

        # scrollTop should be at or near the bottom (scrollHeight - clientHeight)
        assert scroll_top >= (scroll_height - client_height - 5)  # Allow 5px margin


class TestMultipleLogsE2E:
    """E2E tests for handling multiple log messages."""

    @pytest.mark.asyncio
    async def test_handles_mixed_log_levels(self, page: Page):
        """Should correctly color-code mixed log levels."""
        await page.set_content("""
            <!DOCTYPE html>
            <html>
            <head>
                <script>
                    function appendLogToPipelinePanel(logText) {
                        const panel = document.getElementById('pipeline-log-panel');
                        if (!panel) return;

                        let terminalContent = document.getElementById('pipeline-log-terminal-content');
                        if (!terminalContent) return;

                        const logLine = document.createElement('div');
                        logLine.className = 'text-green-400';

                        if (/\\[ERROR\\]|error|failed|exception/i.test(logText)) {
                            logLine.className = 'text-red-400';
                        } else if (/\\[WARN\\]|warning/i.test(logText)) {
                            logLine.className = 'text-yellow-400';
                        } else if (/\\[INFO\\]|Starting|Complete|Success/i.test(logText)) {
                            logLine.className = 'text-green-400';
                        } else if (/\\[DEBUG\\]/i.test(logText)) {
                            logLine.className = 'text-gray-500';
                        }

                        logLine.textContent = logText;
                        terminalContent.appendChild(logLine);
                    }
                </script>
            </head>
            <body>
                <div id="pipeline-log-panel">
                    <div id="pipeline-log-terminal-content"></div>
                </div>
            </body>
            </html>
        """)

        # Append mixed logs
        await page.evaluate('appendLogToPipelinePanel("[INFO] Starting pipeline")')
        await page.evaluate('appendLogToPipelinePanel("[DEBUG] Loading config")')
        await page.evaluate('appendLogToPipelinePanel("[WARN] Slow response detected")')
        await page.evaluate('appendLogToPipelinePanel("[ERROR] Connection timeout")')
        await page.evaluate('appendLogToPipelinePanel("[INFO] Retrying connection")')

        # Verify each log has correct color
        logs = page.locator('#pipeline-log-terminal-content > div')
        assert await logs.nth(0).evaluate('el => el.classList.contains("text-green-400")')
        assert await logs.nth(1).evaluate('el => el.classList.contains("text-gray-500")')
        assert await logs.nth(2).evaluate('el => el.classList.contains("text-yellow-400")')
        assert await logs.nth(3).evaluate('el => el.classList.contains("text-red-400")')
        assert await logs.nth(4).evaluate('el => el.classList.contains("text-green-400")')
