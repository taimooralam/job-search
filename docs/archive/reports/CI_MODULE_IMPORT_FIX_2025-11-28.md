# CI Module Import Fix - 2025-11-28

## Executive Summary

**Issue**: Persistent `ModuleNotFoundError: No module named 'pdf_service.pdf_helpers'` in GitHub Actions CI despite adding `PYTHONPATH` environment variable.

**Root Cause**: CI workflow failed to install the package in editable mode using `pip install -e .`, which is required for Python to resolve absolute imports like `from pdf_service.pdf_helpers import ...`.

**Fix**: Added `pip install -e .` to the CI workflow's dependency installation step.

**Verification**: All 31 PDF helper tests now pass in both local and simulated CI environments.

---

## Diagnostic Summary

### Critical Issue Found
- **Type**: Configuration Error
- **Location**: `.github/workflows/runner-ci.yml` (Install dependencies step)
- **Severity**: Critical - Blocked all PDF service tests in CI
- **Impact**: 48 tests (17 endpoint + 31 helper) failing in CI pipeline

---

## Issue Analysis

### Issue 1: Missing Editable Package Installation in CI

**Location**: `.github/workflows/runner-ci.yml`, lines 45-48

**Root Cause**:
The project uses `setup.py` with `find_packages()`, indicating it's designed to be installed as a Python package. The CI workflow installed dependencies from `requirements.txt` but did not install the package itself. Without `pip install -e .`, Python cannot resolve absolute imports like `from pdf_service.pdf_helpers import ...` because:

1. **Package Not Registered**: The package isn't registered in Python's site-packages
2. **Import Resolution**: Python's import system prioritizes installed packages over PYTHONPATH
3. **Pytest Discovery**: Pytest's module collection requires proper package installation for absolute imports
4. **Namespace Initialization**: Package `__init__.py` files don't get properly initialized without installation

**Why PYTHONPATH Didn't Work**:
- Setting `PYTHONPATH: ${{ github.workspace }}` should theoretically add the project root to Python's import path
- However, for projects with `setup.py`/`pyproject.toml`, the canonical approach is package installation
- Pytest's import system is more reliable with installed packages than PYTHONPATH manipulation
- Package metadata and entry points require actual installation

**Evidence**:
```bash
# Before fix (CI failure):
ModuleNotFoundError: No module named 'pdf_service.pdf_helpers'

# After pip install -e . (local test):
$ pip install -e .
Successfully installed job-search-0.1.0

$ pytest tests/pdf_service/test_pdf_helpers.py -v
============================== 31 passed in 0.02s ==============================
```

**Impact**:
- All 48 PDF service tests failed in CI
- Blocked CI pipeline and deployments
- Created false impression of code issues when problem was configuration

---

## Recommended Fix (APPLIED)

### Fix 1: Install Package in Editable Mode

**Priority**: Critical

**Implementation**:

```yaml
# File: .github/workflows/runner-ci.yml
# Lines: 45-49

- name: Install dependencies
  run: |
    pip install -r requirements.txt
    pip install pytest pytest-asyncio httpx
    pip install -e .  # Install package in editable mode for module imports
```

**Verification Steps**:
1. ✅ Simulated CI environment locally
2. ✅ Verified all 31 PDF helper tests pass
3. ✅ Verified package installation succeeds
4. ✅ Created import verification tests

**Expected CI Output**:
```
Successfully built job-search
Installing collected packages: job-search
Successfully installed job-search-0.1.0
```

**Side Effects**: None - this is the standard Python packaging approach

---

## Verification Results

### Local Simulation Test

Created fresh virtual environment to simulate CI:

```bash
$ python -m venv /tmp/test-ci-env
$ source /tmp/test-ci-env/bin/activate
$ pip install -r requirements.txt
$ pip install pytest pytest-asyncio httpx
$ pip install -e .
Successfully installed job-search-0.1.0

$ python -m pytest tests/pdf_service/test_pdf_helpers.py -v
============================== 31 passed in 0.02s ==============================
```

### Import Verification Tests

Created `tests/test_package_imports.py` with 3 tests:
1. ✅ Package structure verification
2. ✅ PDF helpers module import verification
3. ✅ PDF service app import verification

All tests pass:
```bash
$ pytest tests/test_package_imports.py -v
============================== 3 passed in 0.12s ==============================
```

---

## Architecture Improvements (Recommended)

### 1. Consolidate Test Dependencies

**Current State**: Test dependencies split between `requirements.txt` and inline CI installation

**Recommendation**: Create `requirements-dev.txt`:

```txt
# requirements-dev.txt
-r requirements.txt  # Production dependencies
pytest>=8.0.0
pytest-mock>=3.12.0
pytest-asyncio>=1.3.0
httpx>=0.28.0
pytest-cov>=4.0.0  # For coverage reports
```

**CI Update**:
```yaml
- name: Install dependencies
  run: |
    pip install -r requirements-dev.txt
    pip install -e .
```

**Benefits**:
- Single source of truth for dev dependencies
- Easier local development setup
- Consistent dependency versions between local and CI

### 2. Document Development Setup

Add to `README.md` or `CONTRIBUTING.md`:

```markdown
## Development Setup

### Prerequisites
- Python 3.11+
- Git

### Initial Setup
1. Clone the repository
2. Create virtual environment: `python -m venv .venv`
3. Activate virtual environment:
   - macOS/Linux: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\activate`
4. Install in editable mode: `pip install -e .`
5. Install dependencies: `pip install -r requirements.txt`
6. Install dev dependencies: `pip install pytest pytest-asyncio httpx`

### Running Tests
```bash
# All tests
pytest

# Specific test file
pytest tests/pdf_service/test_pdf_helpers.py

# Specific test
pytest tests/pdf_service/test_pdf_helpers.py::TestSanitizeForPath::test_sanitize_removes_special_chars
```

### 3. Add Package Installation Verification

**Current**: No verification that package is properly installed

**Recommendation**: Add to CI workflow:

```yaml
- name: Verify package installation
  run: |
    python -c "import pdf_service; print(f'pdf_service version: {pdf_service.__version__}')"
    python -c "from pdf_service.pdf_helpers import sanitize_for_path; print('pdf_helpers imported successfully')"
```

**Benefits**:
- Early detection of installation issues
- Clear error messages if package isn't installed
- Validates package metadata

---

## Testing Recommendations

### 1. Package Import Tests (IMPLEMENTED)

Created `tests/test_package_imports.py`:
- Verifies package is importable
- Verifies critical modules can be imported
- Catches installation issues early

### 2. CI Smoke Tests

Add minimal smoke tests to verify environment:
```python
# tests/test_ci_environment.py
def test_python_version():
    """Verify Python version is 3.11+."""
    import sys
    assert sys.version_info >= (3, 11)

def test_required_packages_installed():
    """Verify required packages are installed."""
    import pytest
    import httpx
    import fastapi
    assert True  # If imports succeed, packages are installed
```

### 3. Pre-commit Hooks

Add to `.pre-commit-config.yaml`:
```yaml
- repo: local
  hooks:
    - id: verify-package-installs
      name: Verify package can be installed
      entry: bash -c 'pip install -e . && python -c "import pdf_service"'
      language: system
      pass_filenames: false
```

---

## Files Modified

### Changed Files
1. `.github/workflows/runner-ci.yml` - Added `pip install -e .` to dependency installation

### New Files
2. `tests/test_package_imports.py` - Import verification tests
3. `reports/CI_MODULE_IMPORT_FIX_2025-11-28.md` - This report

---

## Next Steps

### Immediate (Required for CI)
1. ✅ Applied fix to `.github/workflows/runner-ci.yml`
2. ✅ Created import verification tests
3. ⏳ Commit and push changes to trigger CI
4. ⏳ Verify CI passes with all 48+ PDF service tests

### Short-term (Recommended)
1. Create `requirements-dev.txt` to consolidate dev dependencies
2. Add development setup documentation to README.md
3. Add package installation verification step to CI

### Long-term (Nice to Have)
1. Add pre-commit hooks for package installation verification
2. Create CI environment smoke tests
3. Add coverage reporting to CI

---

## Lessons Learned

### What Went Wrong
1. **Assumption**: PYTHONPATH would be sufficient for module imports
2. **Reality**: Projects with `setup.py` require package installation
3. **Gap**: No verification that package was properly installed in CI

### What Worked
1. **Systematic Debugging**: Checked local environment, compared to CI
2. **Root Cause Analysis**: Identified the missing `pip install -e .`
3. **Verification**: Created simulation environment to test fix before applying

### Best Practices Going Forward
1. **Always install packages in editable mode** for testing: `pip install -e .`
2. **Document development setup** to prevent similar issues
3. **Add verification tests** to catch environment issues early
4. **Test CI changes locally** before pushing (simulate with fresh venv)

---

## Summary

**Problem**: ModuleNotFoundError in CI for `pdf_service.pdf_helpers`

**Solution**: Added `pip install -e .` to CI workflow

**Verification**: All 31 PDF helper tests pass in simulated CI environment

**Status**: ✅ Fix applied and verified locally. Ready for CI testing.

**Next Action**: Commit changes and verify CI passes.
