# Logging Migration Report
**Date:** 2025-11-28
**Agent:** architecture-debugger
**Task:** Replace ad-hoc print statements with structured logging

## Diagnostic Summary

**Status:** PARTIALLY COMPLETE
**Files Modified:** 5/11
**Priority:** HIGH (observability critical for production debugging)

### Issues Found
1. **Heavy print usage across pipeline**: 100+ print statements in 11 files
2. **No contextual information**: Prints lack run_id/job_id for correlation
3. **Mixed log levels**: No distinction between info/warning/error
4. **Production debugging difficulty**: Impossible to trace issues across distributed runs

## Completed Fixes

### 1. Runner Service (COMPLETED ✅)
**Files:**
- `runner_service/persistence.py` - 6 prints → logger calls
- `runner_service/executor.py` - 1 print → logger call

**Changes:**
- Added `import logging` and `logger = logging.getLogger(__name__)`
- Replaced all `print(f"Warning: ...")` with `logger.warning(...)`
- Replaced `traceback.print_exc()` with `logger.exception(...)`

### 2. Core Workflow (COMPLETED ✅)
**File:** `src/workflow.py`

**Changes:**
- Replaced pipeline start/complete banners with `run_logger.info()`
- All prints now use `get_logger(__name__, run_id=run_id)` for correlation
- Error prints replaced with `run_logger.exception()`

### 3. Layer 2 - Pain Point Miner (COMPLETED ✅)
**File:** `src/layer2/pain_point_miner.py`

**Changes:**
- Added `from src.common.logger import get_logger`
- All 13 prints replaced with contextual logger calls
- Uses `get_logger(__name__, run_id=state.get("run_id"), layer="layer2")`

### 4. Layer 3 - Company Researcher (IN PROGRESS ⏳)
**File:** `src/layer3/company_researcher.py`

**Status:** Import added, 40+ prints remain
**Prints to Replace:**
- Cache hit/miss logs (lines 351, 369, 414)
- FireCrawl scraping status (lines 462, 489, 549, 558, 587, 590, 604)
- Multi-source scraping logs (lines 643, 655, 669, 672)
- Signal extraction logs (lines 716, 784, 835)
- STAR context logs (lines 873, 883, 888, 894, 897, 904, 908, 912, 918)
- Fallback logs (lines 945, 946, 954, 956, 959, 965, 976)
- Summary output (lines 998-1031)

## Pending Fixes

### 5. Layer 3 - Role Researcher (PENDING ⏸️)
**File:** `src/layer3/role_researcher.py`
**Prints:** 23 statements (lines 290-562)

**Key Areas:**
- FireCrawl search queries
- Role context scraping
- STAR-aware prompting
- Business impact extraction
- Summary output

### 6. Layer 4 - Opportunity Mapper (PENDING ⏸️)
**File:** `src/layer4/opportunity_mapper.py`
**Prints:** 9 statements (lines 372-447)

**Key Areas:**
- Fit rationale quality warnings
- Fit score generation
- Summary output

### 7. Layer 5 - People Mapper (PENDING ⏸️)
**File:** `src/layer5/people_mapper.py`
**Prints:** 27 statements (lines 438-1353)

**Key Areas:**
- Team page scraping
- LinkedIn/Crunchbase searches
- Contact discovery
- Outreach generation
- Synthetic contact fallback
- Summary output

### 8. Layer 6 - Generators (PENDING ⏸️)
**Files:**
- `src/layer6/generator.py` - 16 prints
- `src/layer6/cv_generator.py` - 19 prints
- `src/layer6/html_cv_generator.py` - 5 prints
- `src/layer6/cover_letter_generator.py` - 2 prints
- `src/layer6/outreach_generator.py` - 9 prints

**Total:** 51 prints across CV/cover letter/outreach generation

### 9. Layer 7 - Output Publisher (PENDING ⏸️)
**File:** `src/layer7/output_publisher.py`
**Prints:** 34 statements (lines 188-741)

**Key Areas:**
- Local file saves
- MongoDB updates
- Google Drive uploads
- Sheets logging
- Summary output

## Recommended Approach

### Option A: Systematic Manual Replacement (RECOMMENDED)
**Effort:** 4-6 hours
**Risk:** Low (reviewed changes)
**Benefits:** Clean, contextual logging with proper levels

**Steps:**
1. Process each layer file sequentially
2. Add `get_logger` import
3. Replace prints with appropriate log levels:
   - `logger.info()` for milestones/status
   - `logger.warning()` for recoverable issues
   - `logger.error()` for failures
   - `logger.exception()` for caught exceptions
4. Test each layer individually

### Option B: Targeted Critical Path Only
**Effort:** 1-2 hours
**Risk:** Medium (incomplete coverage)
**Benefits:** Fast production deployment

**Focus on:**
- Runner service endpoints (DONE ✅)
- Workflow orchestration (DONE ✅)
- Layer 2/3/4 (pain points, research, fit scoring)
- Layer 7 (output publishing)

**Skip for now:**
- Layer 5 (people mapper - less critical)
- Layer 6 generators (debugging via files)

### Option C: Automated Script with Manual Review
**Effort:** 2-3 hours
**Risk:** Medium (requires careful testing)
**Benefits:** Consistent patterns

**Process:**
1. Create regex-based replacement script
2. Dry-run on test copy
3. Manual review of diffs
4. Commit atomically per layer

## Testing Strategy

### Unit Tests (No Changes Expected)
```bash
source .venv/bin/activate
pytest tests/unit/ -v --no-cov
```

**Expected:** All existing tests pass (logging doesn't affect logic)

### Integration Tests
```bash
pytest tests/integration/test_pain_point_quality_gates.py -v
```

**Verify:** Log output contains run_id context

### Manual Smoke Test
```bash
python scripts/run_pipeline.py --job-id <test-job-id>
```

**Check logs for:**
- Structured format with timestamps
- run_id/layer context in Layer 2-7 logs
- Appropriate log levels (no ERROR for warnings)

## Migration Checklist

- [x] runner_service/persistence.py
- [x] runner_service/executor.py
- [x] src/workflow.py
- [x] src/layer2/pain_point_miner.py
- [ ] src/layer3/company_researcher.py (40+ prints remain)
- [ ] src/layer3/role_researcher.py
- [ ] src/layer4/opportunity_mapper.py
- [ ] src/layer5/people_mapper.py
- [ ] src/layer6/generator.py
- [ ] src/layer6/cv_generator.py
- [ ] src/layer6/html_cv_generator.py
- [ ] src/layer6/cover_letter_generator.py
- [ ] src/layer6/outreach_generator.py
- [ ] src/layer7/output_publisher.py

## Follow-Up Actions

1. **Complete migration** for remaining 7 files (recommend Option A)
2. **Run unit tests** to verify no regressions
3. **Update missing.md** to mark observability task complete
4. **Deploy to staging** and validate log aggregation
5. **Consider log rotation** for long-running services

## Recommendation

**Proceed with Option A (Systematic Manual Replacement)** for production-quality logging. The effort is justified by:
- Critical for debugging distributed pipeline runs
- Enables cost tracking (LLM call correlation)
- Required for production monitoring/alerts
- One-time investment, long-term benefit

**Next Steps:**
1. Continue manual replacement for layers 3-7
2. Test each layer after completion
3. Commit atomically with descriptive messages
4. Update agent doc-sync to mark observability complete

## Notes

- **No behavior changes:** All modifications preserve existing outputs
- **Log levels chosen based on context:**
  - FireCrawl status → info
  - Cache hits/misses → info
  - Validation warnings → warning
  - API failures → error
  - Exceptions → logger.exception (auto-includes traceback)
- **Context propagation:** All layer logs include run_id via `get_logger(..., run_id=state.get("run_id"))`
