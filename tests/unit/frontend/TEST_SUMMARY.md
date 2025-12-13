# Batch Processing Tests Summary

## Overview

Comprehensive pytest tests for the batch processing workflow implemented in `frontend/app.py`.

**Test File**: `/Users/ala0001t/pers/projects/job-search/tests/unit/frontend/test_batch_processing.py`

**Total Tests**: 18 (all passing)

**Test Execution Time**: ~1.3s (with parallel execution using pytest-xdist)

---

## Routes Tested

### 1. POST /api/jobs/move-to-batch (Lines 936-978)
Moves selected jobs to batch processing queue.

**Functionality**:
- Updates job status to "under processing"
- Sets `batch_added_at` timestamp to current UTC time
- Validates ObjectId format
- Returns success status and updated count

**Tests** (7 tests):
- ✅ `test_moves_jobs_to_batch_successfully` - Verifies status update and timestamp
- ✅ `test_returns_error_when_no_job_ids_provided` - Empty array validation
- ✅ `test_returns_error_when_job_ids_missing` - Missing field validation
- ✅ `test_returns_error_for_invalid_objectid_format` - Invalid ID format handling
- ✅ `test_requires_authentication` - Auth requirement (401)
- ✅ `test_handles_zero_updates_gracefully` - Already processed jobs
- ✅ `test_batch_added_at_is_recent_timestamp` - Timestamp accuracy

### 2. GET /batch-processing (Lines 2229-2238)
Renders the batch processing page view.

**Functionality**:
- Renders `batch_processing.html` template
- Passes JOB_STATUSES to template context

**Tests** (2 tests):
- ✅ `test_renders_batch_processing_template` - Template rendering
- ✅ `test_requires_authentication` - Auth requirement (redirect)

### 3. GET /partials/batch-job-rows (Lines 2241-2278)
HTMX partial for batch job table rows.

**Functionality**:
- Filters jobs by status "under processing"
- Supports sorting by multiple fields (batch_added_at, createdAt, company, title, score)
- Supports ascending/descending direction
- Renders `partials/batch_job_rows.html`

**Tests** (8 tests):
- ✅ `test_returns_only_under_processing_jobs` - Status filter verification
- ✅ `test_default_sort_by_batch_added_at_desc` - Default sort behavior
- ✅ `test_supports_custom_sort_field` - Custom sort field (company, asc)
- ✅ `test_supports_sort_by_score_desc` - Score sorting
- ✅ `test_renders_batch_job_rows_template` - Template rendering with context
- ✅ `test_requires_authentication` - Auth requirement
- ✅ `test_handles_invalid_sort_field_gracefully` - Fallback to default
- ✅ `test_returns_empty_list_when_no_jobs_in_batch` - Empty state

---

## Integration Tests

### TestBatchProcessingWorkflow (1 test)
- ✅ `test_full_workflow_move_to_batch_then_view` - End-to-end workflow

**Scenario**:
1. Move 2 jobs to batch via POST /api/jobs/move-to-batch
2. Verify successful update
3. Retrieve batch jobs via GET /partials/batch-job-rows
4. Verify correct filtering by "under processing" status

---

## Test Coverage

### Overall Coverage
- **Total Statements**: 2252
- **Covered**: 364
- **Coverage**: 13% (of entire app.py)

**Note**: Low overall coverage is expected since we're only testing 3 routes out of ~50+ in app.py.

### Batch Processing Routes Coverage
All lines in the following functions are covered:
- `move_to_batch()` (lines 950-978): **100%**
- `batch_processing()` (lines 2243-2250): **100%**
- `batch_job_rows_partial()` (lines 2255-2290): **100%**

---

## Test Patterns Used

### 1. MongoDB Mocking
```python
@pytest.fixture
def mock_db_collection(mocker):
    """Mock MongoDB collection with common operations."""
    mock_collection = MagicMock()
    mock_update_result = MagicMock()
    mock_update_result.modified_count = 0
    mock_collection.update_many.return_value = mock_update_result
    # ...
    return mock_collection
```

### 2. Flask Test Client
```python
@pytest.fixture
def authenticated_client(client):
    """Create authenticated Flask test client."""
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client
```

### 3. Patch Decorators
```python
@patch("frontend.app.get_collection")
@patch("frontend.app.render_template")
def test_returns_only_under_processing_jobs(...):
    # Test implementation
```

---

## Running the Tests

### Run all batch processing tests (parallel)
```bash
source .venv/bin/activate && pytest tests/unit/frontend/test_batch_processing.py -v -n auto
```

### Run with coverage
```bash
source .venv/bin/activate && pytest tests/unit/frontend/test_batch_processing.py -v -n auto --cov=frontend.app --cov-report=term-missing
```

### Run specific test class
```bash
source .venv/bin/activate && pytest tests/unit/frontend/test_batch_processing.py::TestMoveToBatch -v
```

### Run single test
```bash
source .venv/bin/activate && pytest tests/unit/frontend/test_batch_processing.py::TestMoveToBatch::test_moves_jobs_to_batch_successfully -v
```

---

## Edge Cases Covered

1. **Empty job_ids array** - Returns 400 error
2. **Missing job_ids field** - Returns 400 error
3. **Invalid ObjectId format** - Returns 400 error with clear message
4. **Zero updates** - Handles gracefully (e.g., jobs already in batch)
5. **Unauthenticated requests** - Returns 401 for API, redirects for pages
6. **Invalid sort field** - Fallbacks to default (batch_added_at)
7. **Empty batch queue** - Returns empty list without errors
8. **Timestamp precision** - Verifies batch_added_at is recent UTC time

---

## Bug Fixed During Test Implementation

**Issue**: `get_collection()` function was used in `move_to_batch()` and `batch_job_rows_partial()` but not defined.

**Fix**: Added `get_collection()` helper function at line 273:
```python
def get_collection():
    """
    Get the level-2 MongoDB collection.

    Convenience wrapper around get_db()["level-2"].
    """
    return get_db()["level-2"]
```

**File Modified**: `/Users/ala0001t/pers/projects/job-search/frontend/app.py`

---

## Next Steps

After running these tests, consider:

1. **Frontend Integration Tests**: Test actual HTMX interactions with Selenium
2. **Template Tests**: Verify `batch_processing.html` and `batch_job_rows.html` render correctly
3. **E2E Tests**: Test full workflow in browser with real MongoDB
4. **Performance Tests**: Test batch operations with 100+ jobs
5. **Update Documentation**: Mark batch processing as tested in `missing.md`

---

## Dependencies

- pytest
- pytest-xdist (for parallel execution)
- pytest-mock
- Flask
- pymongo
- bson

All dependencies are already in the project's requirements.
