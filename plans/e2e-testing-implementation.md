# E2E Testing Implementation Plan

**Created**: 2025-11-28
**Status**: Planning (Disabled - pending Phase 5 backend implementation)

---

## Overview

This document outlines the strategy for re-enabling and properly implementing End-to-End (E2E) tests using Playwright. Currently, 48 comprehensive tests exist but are disabled due to configuration issues and incomplete feature implementation.

**Current Situation**:
- 48 Playwright tests written and exist in `tests/e2e/test_cv_editor_e2e.py`
- GitHub Actions workflow disabled: `.github/workflows/e2e-tests.yml.disabled`
- Tests written for Phases 1-5, but Phase 5 features only partially implemented
- pytest-playwright dependency commented out in `requirements.txt`

---

## What Exists Today

### Test Coverage (48 Tests Total)

**Test File**: `tests/e2e/test_cv_editor_e2e.py`

| Category | Count | Status | Notes |
|----------|-------|--------|-------|
| Phase 1: Basic Editor | 6 tests | Working | Editor load, TipTap init, toolbar visibility, save indicator |
| Phase 2: Text Formatting | 8 tests | Working | Bold, italic, underline, keyboard shortcuts, font changes |
| Phase 3: Document Styles | 8 tests | Working | Margins, line height, page size, header/footer |
| Phase 4: PDF Export | 4 tests | Disabled | Requires runner service PDF endpoint (working) |
| Phase 5: Advanced Features | 22 tests | Disabled | Keyboard shortcuts, mobile, accessibility - features not fully implemented |

**Test Infrastructure**:
- `conftest.py`: Pytest configuration, browser launch args, context setup, markers
- Fixtures: `authenticated_page`, `cv_editor_page`, `mobile_context`, `tablet_context`
- Markers: `@pytest.mark.mobile`, `@pytest.mark.accessibility`, `@pytest.mark.slow`
- Cross-browser: Chromium (default), Firefox, WebKit markers

### Configuration Issues Encountered

1. **pytest-playwright Plugin Loading**
   - `pytest_plugins = ["pytest_playwright"]` in conftest.py
   - May conflict with other pytest plugins
   - Solution: Use pytest-playwright fixture discovery correctly

2. **Browser Context Arguments**
   - Mobile/tablet fixtures not properly initialized
   - Solution: Use correct fixture inheritance pattern

3. **Test Data Requirements**
   - Tests expect valid MongoDB jobs to exist
   - Need proper fixture setup for test isolation
   - Solution: Create test fixtures or use database seeding

4. **Authentication**
   - Tests require `LOGIN_PASSWORD` environment variable
   - No mechanism to skip auth tests in development
   - Solution: Add auth bypass for testing or proper mock setup

---

## Why E2E Tests Were Disabled

### Reason 1: Phase 5 Features Not Implemented

**Tests Written For**:
- Keyboard shortcuts (Ctrl+B, Ctrl+I, Ctrl+U, Ctrl+Z)
- Version history / undo-redo persistence
- Mobile responsiveness
- Accessibility (WCAG 2.1 AA) compliance
- Screen reader compatibility

**Current Implementation Status**:
- Keyboard shortcuts: Frontend implemented but not fully integrated
- Version history: NOT IMPLEMENTED (no backend API)
- Mobile responsiveness: Frontend responsive but not tested
- Accessibility: NOT IMPLEMENTED

**Impact**: 22 out of 48 tests would fail because tested features don't exist

### Reason 2: Configuration Issues

**Problems**:
- pytest-playwright fixture discovery intermittent
- Browser context arguments not properly applied
- Headless/headed mode not consistently working
- Screenshot capture on failure not reliable

**Impact**: Tests run inconsistently; false failures in CI

### Reason 3: Test Environment Setup

**Missing Elements**:
- No test database seeding
- No test job fixtures
- No authentication bypass mechanism
- No CI environment variables configured

**Impact**: Tests can't run in CI without manual setup; locally they work only if database populated

---

## Re-enablement Strategy

### Phase 1: Smoke Tests (Start Here)

**Duration**: 2-3 hours
**Goal**: Get E2E suite running with just the working features (Phases 1-4)

**Steps**:

1. **Create Smoke Test Suite** (`tests/e2e/test_cv_editor_smoke.py`)
   ```python
   # Subset of 12-16 core tests:
   - Editor loads successfully
   - Bold/italic/underline formatting works
   - Font changes persist
   - Document styles apply (margins, line height)
   - Basic PDF export works
   - Save indicator appears
   ```

2. **Fix conftest.py**
   - Review pytest-playwright plugin loading
   - Test browser context setup locally
   - Verify fixture inheritance
   - Add proper error handling for missing environment variables

3. **Test Locally First**
   ```bash
   cd /Users/ala0001t/pers/projects/job-search
   source .venv/bin/activate

   # Install playwright (if needed)
   pip install pytest-playwright
   playwright install chromium

   # Run smoke tests
   pytest tests/e2e/test_cv_editor_smoke.py -v --headed
   ```

4. **Verify Test Data**
   - Ensure at least one job exists in MongoDB
   - Test with that job ID
   - Document required test data

**Expected Outcome**: 12-16 E2E tests passing consistently locally

---

### Phase 2: Phase 5 Feature Implementation

**Duration**: 5-8 hours
**Blockers**: Requires backend/frontend work before tests can run
**Goal**: Implement missing Phase 5 features so tests become valid

**Backend Work**:

1. **Version History API** (2-3 hours)
   ```python
   # Add to runner_service/app.py
   POST /api/jobs/{id}/cv-editor/versions
   GET /api/jobs/{id}/cv-editor/versions
   GET /api/jobs/{id}/cv-editor/versions/{version_id}

   # Add to MongoDB schema
   cv_editor_versions: [
     {
       version_id: string,
       content: TipTap JSON,
       documentStyles: { ... },
       timestamp: ISODate,
       label: string (optional)
     }
   ]
   ```

2. **Keyboard Shortcut Backend Support** (1 hour)
   - Verify frontend handles all Ctrl+key combinations
   - Add to API for saving shortcut preferences
   - No server-side processing needed (client-side only)

3. **Mobile PDF Rendering** (1-2 hours)
   - Verify Playwright renders correctly on mobile viewport
   - Add media query testing to PDF generation
   - Test responsive margins/fonts on mobile page sizes

4. **Accessibility (WCAG 2.1 AA)** (1-2 hours)
   - Add ARIA labels to PDF generation
   - Ensure semantic HTML in CV export
   - Test with accessibility auditors

**Frontend Work**:

1. **Version History UI** (1-2 hours)
   - Add "Save Version" button to toolbar
   - Add version history panel/dropdown
   - Implement restore functionality

2. **Keyboard Shortcuts Display** (1 hour)
   - Add keyboard shortcuts help modal
   - Verify all shortcuts working in browser

3. **Mobile Testing** (1 hour)
   - Test on mobile device/emulator
   - Verify touch interactions
   - Test PDF export on mobile

**Expected Outcome**: All Phase 5 features implemented and working, tests pass

---

### Phase 3: CI/CD Infrastructure

**Duration**: 1-2 hours
**Goal**: Make E2E tests reliable in GitHub Actions CI
**Prerequisites**: Phase 1 & 2 complete

**Steps**:

1. **Re-enable pytest-playwright in requirements.txt**
   ```
   # Change from:
   # pytest-playwright==0.x.x (commented)

   # To:
   pytest-playwright==0.4.6  # Uncomment and pin version
   ```

2. **Re-enable GitHub Actions Workflow**
   ```bash
   # Rename workflow back
   mv .github/workflows/e2e-tests.yml.disabled \
      .github/workflows/e2e-tests.yml
   ```

3. **Configure CI Secrets**
   - Add `E2E_BASE_URL` (GitHub Pages URL or preview deployment)
   - Add `LOGIN_PASSWORD` (test account password)
   - Add `MONGODB_URI` (test database connection)

4. **Update Workflow** (`.github/workflows/e2e-tests.yml`)
   ```yaml
   name: E2E Tests

   on:
     push:
       branches: [main, develop]
     pull_request:
       branches: [main, develop]

   jobs:
     e2e:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v4
           with:
             python-version: 3.11
         - run: pip install -r requirements.txt
         - run: playwright install chromium
         - run: pytest tests/e2e/ -v --base-url ${{ secrets.E2E_BASE_URL }}
           env:
             LOGIN_PASSWORD: ${{ secrets.LOGIN_PASSWORD }}
             MONGODB_URI: ${{ secrets.MONGODB_URI }}
         - uses: actions/upload-artifact@v3
           if: failure()
           with:
             name: playwright-report
             path: playwright-report/
   ```

5. **Test Locally with CI Config**
   ```bash
   # Simulate CI environment
   export E2E_BASE_URL=http://localhost:5000
   export LOGIN_PASSWORD=test-password
   export CI=true

   pytest tests/e2e/test_cv_editor_smoke.py -v
   ```

**Expected Outcome**: E2E tests run in CI on every PR and commit

---

### Phase 4: Full E2E Suite Re-enablement

**Duration**: 1-2 hours
**Prerequisites**: Phases 1-3 complete
**Goal**: Enable all 48 tests and establish reliability baseline

**Steps**:

1. **Enable All Phase 5 Tests**
   - Uncomment Phase 5 test sections in `test_cv_editor_e2e.py`
   - Verify all 48 tests pass locally with `--headed` flag
   - Run 3x to verify stability (flakiness detection)

2. **Establish CI Test Strategy**
   - Run smoke tests on every PR (fast, < 2 min)
   - Run full E2E suite on release/main commits (slower, ~5 min)
   - Keep Firefox/WebKit tests optional (run on release only)

3. **Document Test Results**
   - Create `TESTING.md` with E2E test documentation
   - Include environment setup instructions
   - List known flaky tests and mitigations

4. **Monitor and Optimize**
   - Track test execution times
   - Identify and fix flaky tests
   - Adjust timeouts based on CI performance

**Expected Outcome**: All 48 E2E tests passing reliably in CI and locally

---

## Implementation Checklist

### Phase 1: Smoke Tests

- [ ] Create `tests/e2e/test_cv_editor_smoke.py` with 12-16 core tests
- [ ] Fix `tests/e2e/conftest.py` browser configuration
- [ ] Test locally with `pytest tests/e2e/test_cv_editor_smoke.py -v --headed`
- [ ] Verify test data (at least 1 job exists in MongoDB)
- [ ] Document required environment variables
- [ ] All 12-16 smoke tests passing consistently

### Phase 2: Phase 5 Feature Implementation

- [ ] Implement version history API endpoints (runner service)
- [ ] Add version history MongoDB schema
- [ ] Implement version history UI (frontend)
- [ ] Verify keyboard shortcuts working end-to-end
- [ ] Test mobile PDF rendering
- [ ] Implement WCAG 2.1 AA compliance in PDF
- [ ] All Phase 5 features working

### Phase 3: CI/CD Infrastructure

- [ ] Uncomment pytest-playwright in `requirements.txt`
- [ ] Rename workflow: `.e2e-tests.yml.disabled` → `e2e-tests.yml`
- [ ] Configure GitHub Actions secrets (E2E_BASE_URL, LOGIN_PASSWORD, MONGODB_URI)
- [ ] Update workflow.yml with proper CI configuration
- [ ] Test workflow in dry-run mode
- [ ] Workflow runs successfully on PR

### Phase 4: Full Suite Re-enablement

- [ ] Enable all 48 tests in `test_cv_editor_e2e.py`
- [ ] Run full suite locally 3x to verify stability
- [ ] Update CI workflow to run full suite on main/release
- [ ] Create `TESTING.md` documentation
- [ ] Document known flaky tests (if any)
- [ ] All 48 tests passing in CI

---

## Test Execution Commands

### Local Development

```bash
# Smoke tests only (fast, ~1-2 min)
pytest tests/e2e/test_cv_editor_smoke.py -v --headed

# All E2E tests (slower, ~5-10 min)
pytest tests/e2e/ -v --headed

# Specific test
pytest tests/e2e/test_cv_editor_e2e.py::TestCVEditor::test_bold_formatting_with_button -v --headed

# With screenshots on failure
pytest tests/e2e/ -v --screenshot=only-on-failure

# Cross-browser testing
pytest tests/e2e/ -v --browser=firefox --browser=webkit
```

### CI Environment

```bash
# Setup
playwright install chromium

# Run smoke tests
pytest tests/e2e/test_cv_editor_smoke.py -v --base-url https://deployed-url.com

# Run full suite
pytest tests/e2e/ -v --base-url https://deployed-url.com

# Generate report
pytest tests/e2e/ -v --html=report.html
```

---

## Known Issues & Mitigations

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| pytest-playwright plugin conflict | Tests won't run | Review fixture discovery, ensure single plugin source |
| Timing issues in CI | Flaky tests | Increase timeouts, add explicit waits for elements |
| Missing test data | Tests fail | Create test job fixtures or database seeding |
| Mobile viewport not applied | Mobile tests fail | Verify browser_context_args inheritance in conftest |
| Auth tokens expire | Tests fail after 1 hour | Add token refresh or extend TTL for test account |

---

## Success Criteria

- [x] 48 E2E tests exist and documented
- [ ] Smoke test suite (12-16 tests) passing 100% locally
- [ ] All Phase 5 features implemented
- [ ] CI/CD workflow configured and passing
- [ ] Full 48-test suite passing 100% in CI
- [ ] Test execution time < 5 minutes (smoke < 1 minute)
- [ ] Zero flaky tests (3x execution pass rate = 100%)
- [ ] Documentation complete (TESTING.md, README, etc.)

---

## Timeline & Effort

| Phase | Duration | Effort | Blocker |
|-------|----------|--------|---------|
| Phase 1: Smoke Tests | 2-3 hours | Low | No |
| Phase 2: Phase 5 Features | 5-8 hours | High | Phase 1 complete |
| Phase 3: CI/CD | 1-2 hours | Low | Phase 2 complete |
| Phase 4: Full Suite | 1-2 hours | Low | Phase 3 complete |
| **Total** | **9-15 hours** | **Medium** | Phase 1 first |

---

## Related Documentation

- `plans/architecture.md` - Testing Strategy section
- `plans/missing.md` - E2E Testing subsection under Testing
- `tests/e2e/conftest.py` - Pytest configuration
- `tests/e2e/test_cv_editor_e2e.py` - Full test suite (48 tests)
- `.github/workflows/e2e-tests.yml.disabled` - GitHub Actions workflow

---

## Notes

- **Do not re-enable E2E workflow until Phase 2 is complete** - Phase 5 features must be implemented first
- **Start with Phase 1 smoke tests** - Establish baseline with working features
- **Keep E2E separate from unit tests** - Different CI jobs, different timing requirements
- **Monitor test stability** - Track flakiness in issues if re-enabled
