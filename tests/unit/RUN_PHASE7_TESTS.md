# Running Phase 7 Tests

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all Phase 7 tests in parallel
pytest tests/unit/test_layer7*.py tests/unit/test_analytics*.py tests/unit/test_annotation_types_phase7.py -v -n auto
```

## Test Files Overview

| File | Tests | Purpose |
|------|-------|---------|
| `test_layer7_interview_predictor.py` | 30 | Core interview predictor functionality |
| `test_layer7_interview_predictor_edge_cases.py` | 35 | Error handling and edge cases |
| `test_analytics_outcome_tracker.py` | 28 | Core outcome tracker functionality |
| `test_analytics_outcome_tracker_edge_cases.py` | 30 | Date/time and database edge cases |
| `test_annotation_types_phase7.py` | 25 | Type validation for Phase 7 types |
| **TOTAL** | **148** | **Complete Phase 7 coverage** |

## Running Tests by Category

### 1. Interview Predictor Tests
```bash
# All interview predictor tests
pytest tests/unit/test_layer7_interview_predictor.py tests/unit/test_layer7_interview_predictor_edge_cases.py -v -n auto

# Only core functionality
pytest tests/unit/test_layer7_interview_predictor.py -v -n auto

# Only edge cases
pytest tests/unit/test_layer7_interview_predictor_edge_cases.py -v -n auto
```

### 2. Outcome Tracker Tests
```bash
# All outcome tracker tests
pytest tests/unit/test_analytics_outcome_tracker.py tests/unit/test_analytics_outcome_tracker_edge_cases.py -v -n auto

# Only core functionality
pytest tests/unit/test_analytics_outcome_tracker.py -v -n auto

# Only edge cases
pytest tests/unit/test_analytics_outcome_tracker_edge_cases.py -v -n auto
```

### 3. Type Validation Tests
```bash
# All type validation tests
pytest tests/unit/test_annotation_types_phase7.py -v -n auto
```

### 4. New Tests Only (90 tests)
```bash
# Run only newly created tests
pytest tests/unit/test_annotation_types_phase7.py tests/unit/test_layer7_interview_predictor_edge_cases.py tests/unit/test_analytics_outcome_tracker_edge_cases.py -v -n auto
```

## Running with Coverage

### Generate Coverage Report
```bash
# HTML coverage report
pytest tests/unit/test_layer7*.py tests/unit/test_analytics*.py tests/unit/test_annotation_types_phase7.py \
  -v -n auto \
  --cov=src/layer7 \
  --cov=src/analytics \
  --cov=src/common/annotation_types \
  --cov-report=html \
  --cov-report=term

# Open coverage report
open htmlcov/index.html
```

### Coverage Threshold Check
```bash
# Fail if coverage below 90%
pytest tests/unit/test_layer7*.py tests/unit/test_analytics*.py tests/unit/test_annotation_types_phase7.py \
  -v -n auto \
  --cov=src/layer7 \
  --cov=src/analytics \
  --cov-fail-under=90
```

## Running Specific Test Classes

### Interview Predictor
```bash
# Schema validation tests
pytest tests/unit/test_layer7_interview_predictor.py::TestPredictedQuestionSchema -v

# Error handling tests
pytest tests/unit/test_layer7_interview_predictor_edge_cases.py::TestErrorHandling -v

# Edge cases tests
pytest tests/unit/test_layer7_interview_predictor_edge_cases.py::TestEdgeCases -v
```

### Outcome Tracker
```bash
# Date/time edge cases
pytest tests/unit/test_analytics_outcome_tracker_edge_cases.py::TestDateTimeEdgeCases -v

# MongoDB error handling
pytest tests/unit/test_analytics_outcome_tracker_edge_cases.py::TestMongoDBErrorHandling -v

# Status transitions
pytest tests/unit/test_analytics_outcome_tracker_edge_cases.py::TestStatusTransitions -v
```

### Type Validation
```bash
# Interview question types
pytest tests/unit/test_annotation_types_phase7.py::TestInterviewQuestionType -v

# Application outcome types
pytest tests/unit/test_annotation_types_phase7.py::TestApplicationOutcomeType -v

# Multiplier constants
pytest tests/unit/test_annotation_types_phase7.py::TestMultiplierConstants -v
```

## Running Individual Tests

```bash
# Single test by name
pytest tests/unit/test_layer7_interview_predictor.py::TestInterviewPredictor::test_predict_questions_with_gaps -v

# Multiple specific tests
pytest tests/unit/test_analytics_outcome_tracker.py::TestOutcomeTracker::test_update_outcome_with_additional_fields tests/unit/test_analytics_outcome_tracker.py::TestOutcomeTracker::test_get_job_outcome -v
```

## Test Output Options

### Verbose Output
```bash
# Show each test name
pytest tests/unit/test_layer7*.py -v

# Very verbose (show print statements)
pytest tests/unit/test_layer7*.py -vv

# Show local variables on failure
pytest tests/unit/test_layer7*.py -l
```

### Quiet Output
```bash
# Only show summary
pytest tests/unit/test_layer7*.py -q

# Only failures
pytest tests/unit/test_layer7*.py --tb=short
```

### Detailed Failure Info
```bash
# Show full traceback
pytest tests/unit/test_layer7*.py --tb=long

# Show first failure only
pytest tests/unit/test_layer7*.py -x

# Stop after N failures
pytest tests/unit/test_layer7*.py --maxfail=3
```

## Parallel Execution

```bash
# Auto-detect CPU count
pytest tests/unit/test_layer7*.py -n auto

# Specific number of workers
pytest tests/unit/test_layer7*.py -n 14

# Disable parallel (useful for debugging)
pytest tests/unit/test_layer7*.py
```

## Debugging Tests

### Run with Debugging
```bash
# Drop into debugger on failure
pytest tests/unit/test_layer7*.py --pdb

# Drop into debugger at start of each test
pytest tests/unit/test_layer7*.py --trace
```

### Show Print Statements
```bash
# Show print output
pytest tests/unit/test_layer7*.py -s

# Show captured logging
pytest tests/unit/test_layer7*.py --log-cli-level=INFO
```

## Continuous Integration

### Pre-commit Hook
```bash
#!/bin/bash
# Run Phase 7 tests before commit
source .venv/bin/activate
pytest tests/unit/test_layer7*.py tests/unit/test_analytics*.py tests/unit/test_annotation_types_phase7.py -v -n auto --tb=short
```

### CI Pipeline Command
```bash
# Fast, parallel, with coverage
pytest tests/unit/test_layer7*.py tests/unit/test_analytics*.py tests/unit/test_annotation_types_phase7.py \
  -v -n auto \
  --cov=src/layer7 \
  --cov=src/analytics \
  --cov-report=xml \
  --cov-fail-under=85 \
  --junit-xml=test-results.xml
```

## Troubleshooting

### Tests Not Found
```bash
# Verify test discovery
pytest --collect-only tests/unit/test_layer7*.py
```

### Import Errors
```bash
# Check if virtual environment is activated
which python
# Should show: /Users/.../job-search/.venv/bin/python

# Reinstall dependencies
pip install -e .
```

### Mock Issues
```bash
# Clear pytest cache
pytest --cache-clear

# Run without cache
pytest --cache-clear tests/unit/test_layer7*.py -v
```

### Slow Tests
```bash
# Show slowest 10 tests
pytest tests/unit/test_layer7*.py --durations=10

# Only run fast tests (mark @pytest.mark.slow for slow tests)
pytest tests/unit/test_layer7*.py -m "not slow"
```

## Test Markers

```python
# Mark slow tests
@pytest.mark.slow
def test_large_dataset():
    pass

# Mark integration tests
@pytest.mark.integration
def test_full_pipeline():
    pass

# Run only marked tests
pytest -m slow
pytest -m "not integration"
```

## Expected Results

### All Tests Passing
```
================================ test session starts =================================
collected 148 items

tests/unit/test_annotation_types_phase7.py ......................... [ 16%]
tests/unit/test_analytics_outcome_tracker.py ............................ [ 35%]
tests/unit/test_analytics_outcome_tracker_edge_cases.py .............................. [ 56%]
tests/unit/test_layer7_interview_predictor.py .............................. [ 76%]
tests/unit/test_layer7_interview_predictor_edge_cases.py .................................... [100%]

================================ 148 passed in 12.34s ================================
```

### Coverage Results (Expected)
```
Name                                    Stmts   Miss  Cover
-----------------------------------------------------------
src/analytics/outcome_tracker.py          250      5    98%
src/layer7/interview_predictor.py         180      3    98%
src/common/annotation_types.py             50      0   100%
-----------------------------------------------------------
TOTAL                                     480      8    98%
```

## Next Steps After Tests Pass

1. **Update missing.md** - Mark Phase 7 testing as complete
2. **Run integration tests** - Test Phase 7 in full pipeline
3. **Performance testing** - Test with large datasets
4. **Documentation** - Update API documentation

## Related Documentation

- `PHASE7_TEST_SUMMARY.md` - Detailed test coverage summary
- `/Users/ala0001t/pers/projects/job-search/CLAUDE.md` - Testing guidelines
- `/Users/ala0001t/pers/projects/job-search/ROADMAP.md` - Phase 7 requirements
