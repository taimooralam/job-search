"""
Pytest configuration for End-to-End tests using Playwright.

Configures:
- Playwright browser instances (Chromium, Firefox, WebKit)
- Viewport sizes (desktop, mobile)
- Timeouts and retries
- Screenshot/video capture on failure
- Browser launch options (headless/headed)
"""

import os
import pytest
from playwright.sync_api import Browser, BrowserContext, Page


# ==============================================================================
# Pytest Plugins
# ==============================================================================

pytest_plugins = ["pytest_playwright"]


# ==============================================================================
# Configuration
# ==============================================================================

def pytest_addoption(parser):
    """Add custom command-line options."""
    # Note: pytest-playwright already provides --headed, --browser, --slowmo, etc.
    # We only add custom options here that aren't provided by the plugin
    parser.addoption(
        "--base-url",
        action="store",
        default="https://job-search-inky-sigma.vercel.app",
        help="Base URL for E2E tests",
    )


# ==============================================================================
# Browser Launch Configuration
# ==============================================================================

@pytest.fixture(scope="session")
def browser_launch_args(pytestconfig):
    """
    Configure browser launch arguments.

    Note: pytest-playwright handles --headed and --slowmo options automatically.
    This fixture only adds custom args not provided by the plugin.
    """
    return {
        "args": [
            "--disable-blink-features=AutomationControlled",  # Avoid detection
        ],
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_launch_args):
    """Browser type launch args (used by pytest-playwright)."""
    return browser_launch_args


# ==============================================================================
# Context Configuration
# ==============================================================================

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for all tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "device_scale_factor": 1,
        "has_touch": False,
        "is_mobile": False,
        # Record video on failure
        "record_video_dir": "test-results/videos" if os.getenv("CI") else None,
        # Screenshot on failure (handled by pytest-playwright automatically)
    }


# ==============================================================================
# Test Lifecycle Hooks
# ==============================================================================

@pytest.fixture(autouse=True)
def set_base_url(pytestconfig, monkeypatch):
    """Set BASE_URL environment variable for tests."""
    base_url = pytestconfig.getoption("--base-url")
    monkeypatch.setenv("E2E_BASE_URL", base_url)


@pytest.fixture(autouse=True)
def slow_down_on_ci(page: Page, request):
    """Slow down tests when running in CI for stability."""
    if os.getenv("CI"):
        # Add default timeout for all actions in CI
        page.set_default_timeout(30000)  # 30 seconds
    else:
        page.set_default_timeout(15000)  # 15 seconds for local


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook to capture test results and save screenshots on failure.

    pytest-playwright handles this automatically, but we can customize here.
    """
    outcome = yield
    report = outcome.get_result()

    # Check if test failed
    if report.when == "call" and report.failed:
        # pytest-playwright will automatically save screenshot
        # Additional custom logging can go here
        print(f"\n[FAILED] {item.nodeid}")


# ==============================================================================
# Helper Fixtures
# ==============================================================================

@pytest.fixture
def screenshot_on_failure(page: Page, request):
    """
    Fixture to take screenshot on test failure.

    Usage: Add as parameter to any test function.
    """
    yield

    if request.node.rep_call.failed:
        screenshot_path = f"test-results/screenshots/{request.node.name}.png"
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\n[SCREENSHOT] Saved to {screenshot_path}")


# ==============================================================================
# Marker Configuration
# ==============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "mobile: Mark test as mobile-specific (runs on mobile viewport)"
    )
    config.addinivalue_line(
        "markers", "accessibility: Mark test as accessibility-specific (WCAG tests)"
    )
    config.addinivalue_line(
        "markers", "firefox: Mark test to run specifically on Firefox"
    )
    config.addinivalue_line(
        "markers", "webkit: Mark test to run specifically on WebKit/Safari"
    )
    config.addinivalue_line(
        "markers", "slow: Mark test as slow (may take >30 seconds)"
    )


# ==============================================================================
# Retry Configuration (for flaky E2E tests)
# ==============================================================================

@pytest.fixture(scope="function", autouse=True)
def retry_on_failure(request):
    """
    Automatically retry failed tests up to 2 times.

    E2E tests can be flaky due to network, timing, etc.
    """
    # Only retry in CI
    if os.getenv("CI"):
        request.node.add_marker(pytest.mark.flaky(reruns=2, reruns_delay=2))
