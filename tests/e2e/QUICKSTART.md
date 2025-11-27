# E2E Tests Quick Start Guide

Get started with E2E testing in 5 minutes.

## 1. Install Dependencies

```bash
# From project root
pip install -r requirements.txt
playwright install chromium
```

## 2. Set Environment Variable

```bash
export LOGIN_PASSWORD="your-password-here"
```

## 3. Run Tests

### Option A: Use the Helper Script (Recommended)

```bash
# Headless mode (fastest)
./tests/e2e/run_tests.sh

# Headed mode (see browser)
./tests/e2e/run_tests.sh --headed

# Slow motion (for debugging)
./tests/e2e/run_tests.sh --headed --slow

# Mobile tests only
./tests/e2e/run_tests.sh --mobile

# Accessibility tests only
./tests/e2e/run_tests.sh --a11y
```

### Option B: Use pytest Directly

```bash
# All tests
pytest tests/e2e/ -v

# Specific test class
pytest tests/e2e/test_cv_editor_e2e.py::TestTextFormatting -v

# Specific test
pytest tests/e2e/test_cv_editor_e2e.py::TestPDFExport::test_pdf_downloads_successfully_when_clicked -v --headed

# With slow motion
pytest tests/e2e/ -v --headed --slowmo 1000
```

## 4. View Results

Test results are saved to `test-results/`:

```bash
# Screenshots (on failure)
ls test-results/screenshots/

# Videos (on failure)
ls test-results/videos/
```

## Common Use Cases

### Debugging a Failing Test

```bash
# Run in headed mode with slow motion
pytest tests/e2e/test_cv_editor_e2e.py::TestPDFExport::test_pdf_downloads_successfully_when_clicked \
  -v --headed --slowmo 1000
```

### Test on Different Browsers

```bash
# Firefox
pytest tests/e2e/ -v --browser firefox

# WebKit (Safari)
pytest tests/e2e/ -v --browser webkit

# All browsers
pytest tests/e2e/ -v --browser chromium --browser firefox --browser webkit
```

### Test Mobile Responsiveness

```bash
# Run mobile tests
pytest tests/e2e/ -v -m mobile --headed
```

### Test Accessibility

```bash
# Run accessibility tests
pytest tests/e2e/ -v -m accessibility
```

## Troubleshooting

### "LOGIN_PASSWORD not set"

```bash
export LOGIN_PASSWORD="your-password"
```

### "Timeout waiting for .tiptap"

- Ensure the Vercel app is running
- Ensure at least one job exists in MongoDB
- Try increasing timeout: `pytest tests/e2e/ -v --timeout 60`

### Tests Are Flaky

```bash
# Use slow motion to stabilize
pytest tests/e2e/ -v --slowmo 500

# Or increase default timeout in conftest.py
```

## Next Steps

Read the [full README](README.md) for:
- Complete test coverage details
- CI/CD integration
- Advanced configuration
- Contributing guidelines
