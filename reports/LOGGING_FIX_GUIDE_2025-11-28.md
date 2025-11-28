# Complete Logging Fix Guide
**Date:** 2025-11-28
**Task:** Replace all print statements with structured logging

## Executive Summary

**Problem:** 100+ ad-hoc print statements across pipeline preventing production observability

**Solution:** Systematic replacement with structured logging using existing `src/common/logger.py`

**Status:** 36% complete (4/11 files)

**Estimated Effort:** 3-4 hours remaining

---

## Implementation Strategy

### Pattern to Follow

#### Before (❌)
```python
print(f"   ✓ Extracted {len(signals)} signals")
print(f"   ⚠️  Cache failed: {e}")
```

#### After (✅)
```python
logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer3")
logger.info(f"Extracted {len(signals)} signals")
logger.warning(f"Cache failed: {e}")
```

### Log Level Guidelines

| Print Content | Log Level | Reasoning |
|---------------|-----------|-----------|
| ✓, ✅, "success", "completed" | `info` | Normal operation milestone |
| "⚠️", "warning", "fallback" | `warning` | Recoverable issue |
| "✗", "❌", "failed", "error" | `error` | Non-recoverable failure |
| Exception catch blocks | `exception` | Includes automatic traceback |
| Status updates, counts | `info` | Informational |
| Cache hits/misses | `info` or `debug` | Performance tracking |

---

## Remaining Files (Priority Order)

### CRITICAL PATH (Do First)

#### 1. src/layer3/company_researcher.py (40+ prints)

**Function:** `_get_cached_research`
- Line 351: `print(f"   ✓ Cache HIT for {company_name}")` → `logger.info(...)`
- Line 369: `print(f"   ✗ Cache MISS for {company_name}")` → `logger.info(...)`

**Function:** `_cache_research`
- Line 414: `print(f"   ✓ Cached research for {company_name}")` → `logger.info(...)`

**Function:** `_scrape_with_firecrawl`
- Line 462: `print(f"   FireCrawl scraping failed: {str(e)}")` → `logger.error(...)`
- Line 489: `print(f"   ⚠️  Job posting scrape failed: {e}")` → `logger.warning(...)`

**Function:** `_firecrawl_search_and_scrape`
- Lines 549-604: 7 prints → logger.info/warning

**Function:** `_scrape_company_sources`
- Lines 643-672: 5 prints → logger.info/warning

**Function:** `_extract_company_signals_with_llm`
- Lines 716-835: 4 prints → logger.info/warning

**Function:** `research_company`
- Lines 873-976: 15 prints → logger.info/warning/error

**Function:** `company_researcher_node`
- Lines 998-1031: 14 prints (summary) → logger.info

**Critical:** Add at top of each function:
```python
logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer3")
```

---

#### 2. src/layer7/output_publisher.py (34 prints)

**Function:** `_save_to_local_disk`
- Lines 188-227: 6 prints → logger.info

**Function:** `_update_mongodb`
- Lines 273-357: 6 prints → logger.info/warning

**Function:** `_publish_to_drive_and_sheets`
- Lines 463-668: 20 prints → logger.info/warning/error

**Function:** `output_publisher_node`
- Lines 696-741: Summary output (14 prints) → logger.info

---

#### 3. src/layer4/opportunity_mapper.py (9 prints)

**Function:** `_generate_fit_analysis`
- Lines 372-409: 7 prints → logger.warning/info

**Function:** `opportunity_mapper_node`
- Lines 431-447: 2 prints (summary) → logger.info

---

### SECONDARY PATH (Do Next)

#### 4. src/layer3/role_researcher.py (23 prints)

Similar pattern to company_researcher.py:
- FireCrawl search logs → logger.info
- Scraping status → logger.info/warning
- STAR context logs → logger.info
- Analysis results → logger.info
- Summary output → logger.info

#### 5. src/layer5/people_mapper.py (27 prints)

Functions to update:
- `_scrape_company_team_page`
- `_search_linkedin_contacts`
- `_search_hiring_manager_contacts`
- `_search_crunchbase_team`
- `_discover_contacts_firecrawl`
- `_generate_outreach_for_contact`
- `people_mapper_node`

---

### LOWER PRIORITY (Can Defer)

#### 6-10. Layer 6 Generators (51 prints total)

**Rationale for deferring:**
- Less critical for debugging (outputs saved to files)
- Mainly status updates, not error handling
- Can inspect generated artifacts directly

**Files:**
- `src/layer6/generator.py` (16 prints)
- `src/layer6/cv_generator.py` (19 prints)
- `src/layer6/html_cv_generator.py` (5 prints)
- `src/layer6/cover_letter_generator.py` (2 prints)
- `src/layer6/outreach_generator.py` (9 prints)

---

## Atomic Commit Strategy

### Commit 1: Runner Service (DONE ✅)
```bash
git add runner_service/persistence.py runner_service/executor.py
git commit -m "refactor(runner): replace prints with structured logging

- Add logging module to persistence and executor
- Replace print statements with logger.warning/error
- Improve MongoDB/Redis error observability"
```

### Commit 2: Core Workflow (DONE ✅)
```bash
git add src/workflow.py
git commit -m "refactor(workflow): replace prints with structured logging

- Use get_logger with run_id context
- Replace pipeline start/complete banners with logger.info
- Preserve output format, improve correlation"
```

### Commit 3: Layer 2 (DONE ✅)
```bash
git add src/layer2/pain_point_miner.py
git commit -m "refactor(layer2): replace prints with structured logging

- Add get_logger import
- Use logger with run_id and layer context
- Replace 13 print statements with appropriate log levels"
```

### Commit 4: Layer 3 (IN PROGRESS)
```bash
git add src/layer3/company_researcher.py src/layer3/role_researcher.py
git commit -m "refactor(layer3): replace prints with structured logging

- Add get_logger to company and role researchers
- Replace 63 print statements with contextual logging
- Improve FireCrawl scraping observability
- Add run_id correlation for multi-source research"
```

### Commit 5: Layers 4, 7 (NEXT)
```bash
git add src/layer4/opportunity_mapper.py src/layer7/output_publisher.py
git commit -m "refactor(layer4,layer7): replace prints with structured logging

- Replace 43 print statements in mapper and publisher
- Improve Drive/Sheets upload observability
- Add proper error logging for MongoDB updates"
```

### Commit 6: Layer 5 (OPTIONAL)
```bash
git add src/layer5/people_mapper.py
git commit -m "refactor(layer5): replace prints with structured logging

- Replace 27 print statements in people mapper
- Improve contact discovery observability"
```

### Commit 7: Layer 6 (CAN DEFER)
```bash
git add src/layer6/*.py
git commit -m "refactor(layer6): replace prints with structured logging

- Replace 51 print statements across generator modules
- Improve CV/cover letter/outreach generation observability"
```

---

## Testing Protocol

### After Each Commit

```bash
# 1. Run relevant unit tests
source .venv/bin/activate
pytest tests/unit/test_layer3_researchers.py -v --no-cov

# 2. Check for import errors
python -c "from src.layer3.company_researcher import company_researcher_node"

# 3. Verify no syntax errors
python -m py_compile src/layer3/company_researcher.py
```

### Full Smoke Test (After All Changes)

```bash
# Set log level to INFO to see output
export LOG_LEVEL=INFO

# Run pipeline on a test job
python scripts/run_pipeline.py --job-id <test-job-id>

# Verify structured logs contain:
# - Timestamps
# - Log levels [INFO], [WARNING], [ERROR]
# - run_id context (e.g., "[run:a1b2c3d4]")
# - Layer tags (e.g., "[layer3]")
```

---

## Quick Reference: Function Signatures

### Get logger with context
```python
from src.common.logger import get_logger

# In node functions (have state access)
def my_node(state: JobState) -> Dict:
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer3")
    logger.info("Starting node")
    # ...

# In helper functions (no state access)
def helper_function():
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Helper called")
    # ...
```

### Log an exception with traceback
```python
try:
    risky_operation()
except Exception as e:
    logger.exception(f"Operation failed: {e}")
    # Automatically includes stack trace
```

---

## Definition of Done

- [ ] All print statements in critical path replaced (layers 2-4, 7)
- [ ] All files have appropriate logger imports
- [ ] Unit tests pass without errors
- [ ] Manual smoke test shows structured logs with run_id
- [ ] Commit messages follow atomic commit strategy
- [ ] missing.md updated to mark observability complete

---

## Rollback Plan

If logging migration causes issues:

```bash
# Revert specific commit
git revert <commit-hash>

# Or reset to before migration
git reset --hard <pre-migration-commit>

# Restore working state
source .venv/bin/activate
pytest tests/unit/ -v
```

---

## Next Actions

1. **Complete Layer 3 company_researcher.py** (highest priority)
2. **Update Layer 7 output_publisher.py** (critical for Drive/Sheets debugging)
3. **Update Layer 4 opportunity_mapper.py** (fit scoring observability)
4. **Run full test suite** to verify no regressions
5. **Update missing.md** to remove observability gap
6. **Deploy to staging** and monitor logs

**Estimated Time Remaining:** 3-4 hours for complete coverage
