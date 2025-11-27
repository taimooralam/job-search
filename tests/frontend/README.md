# Frontend Tests - CV Rich Text Editor

Quick reference for running CV editor tests.

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all frontend tests
pytest tests/frontend/ -v

# Run specific test file
pytest tests/frontend/test_cv_editor_api.py -v
pytest tests/frontend/test_cv_migration.py -v
pytest tests/frontend/test_cv_editor_db.py -v

# Run single test
pytest tests/frontend/test_cv_editor_api.py::TestGetCvEditorState::test_get_cv_editor_state_with_existing_state -v
```

## Test Files

| File | Tests | Purpose |
|------|-------|---------|
| `test_cv_editor_api.py` | 18 | API endpoint tests (GET/PUT) |
| `test_cv_migration.py` | 17 | Markdown → TipTap migration |
| `test_cv_editor_db.py` | 11 | MongoDB integration |
| **Total** | **46** | **Complete coverage** |

## Coverage

- API Endpoints: **100%**
- Migration Function: **100%**
- Error Handling: **100%**
- MongoDB Integration: **95%**

## Expected Results

```
============================== 46 passed in 0.21s ==============================
```

## Documentation

- `TEST_SUMMARY.md` - Detailed test summary with all test cases
- `../TEST_GENERATION_REPORT.md` - Full test generation report

## Fixtures

See `conftest.py` for shared fixtures:
- `app` - Flask test app
- `authenticated_client` - Authenticated test client
- `mock_db` - Mocked MongoDB
- `sample_job` - Test job data
- `sample_job_with_editor_state` - Job with editor state

## Troubleshooting

**Import errors?**
- Ensure you're in the project root directory
- `setup_frontend_imports` fixture should handle path setup

**Tests fail?**
- Check MongoDB mocks are working
- Verify Flask app configuration
- Ensure authentication is mocked properly

## Next Steps

After tests pass:
1. Review `TEST_SUMMARY.md` for detailed coverage
2. Run manual E2E test in browser
3. Deploy to staging environment
