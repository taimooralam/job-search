# End-to-End Tests for CV Rich Text Editor

Comprehensive End-to-End tests for the CV Rich Text Editor using Playwright.

## Overview

These tests validate the **full user experience** by testing real browser interactions with the deployed CV editor. Unlike unit/integration tests, E2E tests:

- Run in a real browser (Chromium, Firefox, WebKit)
- Test against the deployed Vercel app
- Validate actual user interactions (clicks, typing, navigation)
- Verify auto-save, persistence, and PDF export
- Test mobile responsiveness and accessibility

## Test Coverage

### 1. Editor Initialization & Loading (5 tests)
- ✅ CV editor page loads successfully
- ✅ TipTap editor initializes and is interactive
- ✅ Toolbar buttons are visible
- ✅ Document styles panel loads
- ✅ Auto-save indicator appears

### 2. Text Formatting (10 tests)
- ✅ Bold formatting (Ctrl+B and toolbar)
- ✅ Italic formatting (Ctrl+I and toolbar)
- ✅ Underline formatting (Ctrl+U and toolbar)
- ✅ Font family changes persist
- ✅ Font size changes persist
- ✅ Text color changes persist
- ✅ Highlight color changes persist
- ✅ Text alignment (left, center, right, justify)

### 3. Document Styles (5 tests)
- ✅ Line height changes
- ✅ Margin changes (top, right, bottom, left)
- ✅ Page size toggle (letter ↔ A4)
- ✅ Header text editable and persists
- ✅ Footer text editable and persists

### 4. Auto-Save & Persistence (4 tests)
- ✅ Content auto-saves after typing (debounced)
- ✅ Auto-save indicator updates
- ✅ Content persists after page reload
- ✅ Document styles persist after reload

### 5. PDF Export (4 tests)
- ✅ "Export to PDF" button visible
- ✅ PDF downloads successfully
- ✅ PDF filename format correct (CV_Company_Title.pdf)
- ✅ PDF export shows loading state

### 6. Keyboard Shortcuts (5 tests)
- ✅ Ctrl+B toggles bold
- ✅ Ctrl+I toggles italic
- ✅ Ctrl+U toggles underline
- ✅ Ctrl+Z performs undo
- ✅ Ctrl+Y performs redo

### 7. Mobile Responsiveness (4 tests)
- ✅ Editor loads on mobile viewport (375px)
- ✅ Toolbar accessible on mobile
- ✅ Text input works on mobile
- ✅ Auto-save works on mobile

### 8. Accessibility (4 tests)
- ✅ Editor is keyboard navigable (Tab/Shift+Tab)
- ✅ Toolbar buttons have accessible labels
- ✅ Focus indicators visible
- ✅ Save status has screen reader support

### 9. Edge Cases (3 tests)
- ✅ Very large documents (10,000+ chars)
- ✅ Special characters (emoji, unicode) preserved
- ✅ Session timeout redirects to login

### 10. Cross-Browser Compatibility (2 tests)
- ✅ Tests pass on Firefox
- ✅ Tests pass on WebKit (Safari)

**Total: 46 E2E tests**

## Prerequisites

### 1. Install Dependencies

```bash
# Install Python dependencies (includes Playwright)
pip install -r requirements.txt

# Install Playwright browsers
playwright install
```

### 2. Set Environment Variables

Create a `.env` file or set environment variables:

```bash
# Required
export LOGIN_PASSWORD="your-password-here"

# Optional (defaults to deployed Vercel app)
export E2E_BASE_URL="https://job-search-inky-sigma.vercel.app"
```

### 3. Ensure Test Data Exists

E2E tests require **at least one job** to exist in MongoDB. The tests will:
1. Log in to the application
2. Navigate to the first job in the list
3. Open the CV editor

If no jobs exist, seed the database first:

```bash
cd frontend
python seed_jobs.py
```

## Running Tests

### Run All E2E Tests

```bash
# Default: Chromium, headless
pytest tests/e2e/ -v

# Headed mode (visible browser)
pytest tests/e2e/ -v --headed

# Slow motion (500ms delay between actions)
pytest tests/e2e/ -v --headed --slowmo 500
```

### Run Specific Test Classes

```bash
# Test only editor initialization
pytest tests/e2e/test_cv_editor_e2e.py::TestEditorInitialization -v

# Test only text formatting
pytest tests/e2e/test_cv_editor_e2e.py::TestTextFormatting -v

# Test only PDF export
pytest tests/e2e/test_cv_editor_e2e.py::TestPDFExport -v
```

### Run Specific Tests

```bash
# Test PDF download
pytest tests/e2e/test_cv_editor_e2e.py::TestPDFExport::test_pdf_downloads_successfully_when_clicked -v --headed

# Test auto-save
pytest tests/e2e/test_cv_editor_e2e.py::TestAutoSaveAndPersistence::test_content_auto_saves_after_typing -v --headed
```

### Run Tests by Marker

```bash
# Run only mobile tests
pytest tests/e2e/ -v -m mobile

# Run only accessibility tests
pytest tests/e2e/ -v -m accessibility

# Run only Firefox tests (requires --browser firefox)
pytest tests/e2e/ -v -m firefox --browser firefox

# Run only WebKit tests
pytest tests/e2e/ -v -m webkit --browser webkit
```

### Cross-Browser Testing

```bash
# Run on all browsers
pytest tests/e2e/ -v --browser chromium --browser firefox --browser webkit

# Run only on Firefox
pytest tests/e2e/ -v --browser firefox

# Run only on WebKit (Safari)
pytest tests/e2e/ -v --browser webkit
```

### Debugging Tests

```bash
# Headed mode with slow motion (1 second delay)
pytest tests/e2e/ -v --headed --slowmo 1000

# Run with debugger (pause on failure)
pytest tests/e2e/ -v --headed --pdb

# Run single test with maximum visibility
pytest tests/e2e/test_cv_editor_e2e.py::TestEditorInitialization::test_tiptap_editor_initializes -v --headed --slowmo 1000
```

### Screenshots and Videos

```bash
# Save screenshots on failure (automatic)
pytest tests/e2e/ -v --screenshot on

# Save videos on failure
pytest tests/e2e/ -v --video retain-on-failure

# Save all videos (even for passing tests)
pytest tests/e2e/ -v --video on

# Output directory
ls test-results/screenshots/
ls test-results/videos/
```

## Configuration

### pytest-e2e.ini

E2E-specific configuration:

```ini
[pytest]
testpaths = tests/e2e
markers =
    mobile: Mobile viewport tests
    accessibility: WCAG tests
    firefox: Firefox-specific tests
    webkit: WebKit-specific tests
    slow: Tests that take >30 seconds
```

### Browser Options

Modify `tests/e2e/conftest.py`:

```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},  # Desktop
        "locale": "en-US",
        "timezone_id": "America/New_York",
    }
```

## CI/CD Integration

### GitHub Actions

Add to `.github/workflows/e2e-tests.yml`:

```yaml
name: E2E Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install --with-deps

      - name: Run E2E tests
        env:
          LOGIN_PASSWORD: ${{ secrets.LOGIN_PASSWORD }}
          E2E_BASE_URL: https://job-search-inky-sigma.vercel.app
        run: |
          pytest tests/e2e/ -v --browser chromium --screenshot on --video retain-on-failure

      - name: Upload screenshots
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: screenshots
          path: test-results/screenshots/

      - name: Upload videos
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: videos
          path: test-results/videos/
```

## Troubleshooting

### Tests Fail on Login

**Issue**: `LoginError: Password input not found`

**Solution**: Verify `LOGIN_PASSWORD` environment variable is set:
```bash
echo $LOGIN_PASSWORD
```

### Editor Not Loading

**Issue**: `TimeoutError: Waiting for selector '.tiptap' to be visible`

**Solution**:
1. Verify the deployed app is running: Visit `https://job-search-inky-sigma.vercel.app`
2. Verify at least one job exists in MongoDB
3. Check browser console for JavaScript errors (run with `--headed`)

### Tests Are Flaky

**Issue**: Tests pass sometimes, fail other times

**Solution**:
1. Increase timeouts in `conftest.py`:
   ```python
   page.set_default_timeout(30000)  # 30 seconds
   ```
2. Add explicit waits:
   ```python
   page.wait_for_timeout(2000)  # 2 seconds
   ```
3. Use `--slowmo` to slow down actions:
   ```bash
   pytest tests/e2e/ -v --slowmo 1000
   ```

### PDF Download Fails

**Issue**: `download_info.value is None`

**Solution**:
1. Verify PDF export endpoint is working:
   ```bash
   curl -X POST https://job-search-inky-sigma.vercel.app/api/jobs/<job_id>/cv-editor/pdf
   ```
2. Check runner service is running (PDF generation is on runner)
3. Increase download timeout:
   ```python
   with page.expect_download(timeout=60000) as download_info:
       pdf_button.click()
   ```

### Mobile Tests Fail

**Issue**: Elements not visible on mobile viewport

**Solution**:
1. Use `pytest tests/e2e/ -v -m mobile --headed` to debug visually
2. Check if toolbar collapses/scrolls on mobile
3. Adjust viewport size in `conftest.py`

### Accessibility Tests Fail

**Issue**: ARIA attributes not found

**Solution**:
1. Accessibility features may not be fully implemented yet
2. Use `pytest.skip()` for unimplemented features:
   ```python
   if aria_live is None:
       pytest.skip("ARIA live region not implemented yet")
   ```

## Performance

### Test Execution Times

- **Full suite**: ~5-10 minutes (46 tests)
- **Single test**: ~10-30 seconds
- **Mobile tests**: ~1-2 minutes (4 tests)
- **Accessibility tests**: ~1-2 minutes (4 tests)

### Optimization Tips

1. **Run in parallel** (requires pytest-xdist):
   ```bash
   pytest tests/e2e/ -v -n auto
   ```

2. **Skip slow tests** during development:
   ```bash
   pytest tests/e2e/ -v -m "not slow"
   ```

3. **Use headless mode** for faster execution:
   ```bash
   pytest tests/e2e/ -v  # Default is headless
   ```

## Limitations

### Known Issues

1. **Network interception**: Tests don't mock network requests (test real backend)
2. **Test data isolation**: Tests use existing MongoDB jobs (no fixtures)
3. **Concurrent editing**: No tests for multiple users editing same CV
4. **Visual regression**: No pixel-perfect screenshot comparisons
5. **Color contrast**: WCAG color contrast testing requires manual computation

### Future Enhancements

- [ ] Add visual regression testing (Percy, Applitools)
- [ ] Add network interception for error scenarios
- [ ] Add test data fixtures (create/delete jobs per test)
- [ ] Add performance testing (Lighthouse scores)
- [ ] Add cross-device testing (real mobile devices)

## Contributing

When adding new E2E tests:

1. Follow the existing test structure (AAA pattern: Arrange, Act, Assert)
2. Use descriptive test names: `test_<feature>_<action>_<expected_result>`
3. Add `pytest.skip()` for unimplemented features
4. Use appropriate markers (`@pytest.mark.mobile`, etc.)
5. Add documentation in this README

## Resources

- [Playwright Python Docs](https://playwright.dev/python/)
- [pytest-playwright Plugin](https://github.com/microsoft/playwright-pytest)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [TipTap Documentation](https://tiptap.dev/)

## License

MIT License - See root LICENSE file.
