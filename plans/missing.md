# Implementation Gaps

**Last Updated**: 2025-11-30 (Complete system analysis with numbered priorities)

> **See also**: `plans/architecture.md` | `plans/next-steps.md` | `bugs.md`

---

## Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **P0 (CRITICAL)** | 2 (2 fixed) | Must fix immediately - system broken or data integrity at risk |
| **P1 (HIGH)** | 9 | Fix this week - user-facing bugs or important features |
| **P2 (MEDIUM)** | 13 | Fix this sprint - enhancements and incomplete features |
| **P3 (LOW)** | 8 | Backlog - nice-to-have improvements |
| **Total** | **34** (2 fixed, 32 open) | All identified gaps |

**Test Coverage**: 708 unit tests passing, 48 E2E tests disabled, integration tests pending

---

## P0: CRITICAL (Must Fix Immediately)

### GAP-001: CV V2 - Hallucinated Skills
**Priority**: P0 CRITICAL | **Status**: ✅ FIXED (2025-11-30) | **Effort**: 1.5 days
**Impact**: CVs claim Java/PHP/Spring Boot expertise candidate DOESN'T have

**Root Cause**: Hardcoded skill lists in `src/layer6_v2/header_generator.py:200-226`

**Fix Implemented**:
1. Added `get_all_hard_skills()`, `get_all_soft_skills()`, `get_skill_whitelist()` to CVLoader
2. Replaced hardcoded skill lists with dynamic whitelist from master-CV
3. Only skills from `data/master-cv/roles/*.md` now appear in generated CVs
4. JD keywords only included if they have evidence in experience bullets

**Commit**: `85bebfea` - fix(cv-v2): prevent hallucinated skills and add dynamic categories

---

### GAP-002: CV V2 - Static Core Skills Categories
**Priority**: P0 CRITICAL | **Status**: ✅ FIXED (2025-11-30) | **Effort**: 1.5 days
**Impact**: All CVs have identical 4 categories instead of JD-derived dynamic categories

**Root Cause**: Hardcoded loop in `src/layer6_v2/header_generator.py:495`

**Fix Implemented**:
1. Created `src/layer6_v2/category_generator.py` with LLM-driven category clustering
2. Updated `header_generator.py` with `use_dynamic_categories` parameter (default: True)
3. Categories now derived from JD keywords and role type
4. Example output: ["Cloud Platform Engineering", "Backend Architecture", "Technical Leadership"]

**Commit**: `85bebfea` - fix(cv-v2): prevent hallucinated skills and add dynamic categories

---

### GAP-003: VPS Backup Strategy - No Backups
**Priority**: P0 CRITICAL | **Status**: PENDING | **Effort**: 20-30 hours
**Impact**: No backups for generated CVs/dossiers; disk failure = total data loss

**Current State**:
- VPS has no backup mechanism for generated artifacts
- MongoDB Atlas has PITR but never tested
- API keys exist only on VPS (no secure vault)

**Fix Required**:
1. Implement S3 backup for VPS artifacts
2. Create disaster recovery plan
3. Test MongoDB backup restoration

**Report**: `reports/agents/doc-sync/2025-11-30-vps-backup-assessment.md`

---

### GAP-004: Credential Backup Vault - No Secure Storage
**Priority**: P0 CRITICAL | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: API keys/MongoDB URI only on VPS; loss = system failure

**Fix Required**:
- AWS Secrets Manager or Git-crypt encrypted vault
- Document all credentials with recovery procedures

---

## P1: HIGH (Fix This Week)

### GAP-005: CV V2 - Missing STAR Format
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 1 day
**Impact**: Experience bullets lack challenge→skill→result structure, appear generic

**Root Cause**: No STAR enforcement in `src/layer6_v2/prompts/role_generation.py`

**Current Bullet** (generic):
> "Led migration to microservices architecture, improving system reliability"

**Required STAR Bullet** (specific):
> "Facing 30% annual outage increase [SITUATION], led 12-month migration to event-driven microservices [TASK] using AWS Lambda and EventBridge [ACTION/SKILLS], achieving 75% incident reduction [RESULT]"

**Fix Required**:
1. Add STAR template to role generation prompts
2. Add validator to reject bullets without skill mentions
3. Add retry logic for non-STAR bullets

**Files**: `src/layer6_v2/prompts/role_generation.py`, `src/layer6_v2/role_qa.py`

---

### GAP-006: CV V2 - Markdown Asterisks in Output
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Every generated CV has `**text**` formatting needing manual removal

**Root Cause**: LLM prompts don't forbid markdown; `to_markdown()` methods add `**` syntax

**Fix Required**:
1. Add "no markdown" instruction to all generation prompts
2. Create `src/common/markdown_sanitizer.py` for post-processing

**Files**: `src/layer6_v2/types.py`, `src/layer6_v2/prompts/`, `src/layer6_v2/role_generator.py`
**Bug**: bugs.md #14

---

### GAP-007: Time-Based Filters Bug
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: 1h/3h/6h/12h quick filters return all-day results instead of hour-based

**Root Cause**: MongoDB query timezone/format mismatch or frontend parameter not reaching backend

**Files**: `frontend/templates/index.html`, `frontend/app.py`, MongoDB `createdAt` field
**Bug**: bugs.md #12
**Plan**: `plans/time-filter-bug-fix-and-enhancement.md`

---

### GAP-008: GitHub Workflow - Master-CV Sync
**Priority**: P1 HIGH | **Status**: FIXED (pending commit) | **Effort**: 1 hour
**Impact**: VPS only receives `master-cv.md` not `data/master-cv/` directory with role skill files

**Root Cause**: `.github/workflows/runner-ci.yml:147` only copies single file

**Fix**: Updated to include `data/master-cv` in source files (commit pending)

---

### GAP-009: CV Editor Not Synced with Detail Page
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2-3 hours
**Impact**: Generated CV content (TipTap editor) doesn't display on job detail view

**Component**: `frontend/templates/job_detail.html`
**Bug**: bugs.md #11

---

### GAP-010: Database Backup Monitoring
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 3-4 hours
**Impact**: MongoDB Atlas PITR enabled but never tested

**Fix Required**:
- Test monthly restore
- Document recovery procedures
- Verify backup retention

---

### GAP-011: LinkedIn 300 Char Message Limit
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Hard 300 character limit for LinkedIn connection messages not enforced

**Fix Required**:
- Prompt guardrail in LLM instructions
- Output validation with retry logic
- UI character counter

**Files**: `src/layer5/people_mapper.py`, `src/layer6/outreach_generator.py`, frontend templates
**Plan**: `plans/linkedin-message-character-limit.md`

---

### GAP-012: TODO - Inline Mark Parsing Not Implemented
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Bold/italic marks not parsed in CV text conversion

**Location**: `frontend/app.py:2116`, `runner_service/app.py:476`
```python
# TODO: Implement proper inline mark parsing
return [{"type": "text", "text": text}]  # Just returns plain text
```

---

### GAP-013: Bare Except Block - Bad Practice
**Priority**: P1 HIGH | **Status**: PENDING | **Effort**: 30 minutes
**Impact**: Swallows all exceptions, hides bugs

**Location**: `src/layer5/people_mapper.py:479`
```python
except:  # Should catch specific exceptions
    continue
```

---

## P2: MEDIUM (Fix This Sprint)

### GAP-014: CV V2 - Dynamic Tagline for Location
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 0.5 days
**Impact**: Middle East jobs need "International Relocation in 2 months" tagline

**Trigger Countries**: Saudi Arabia, UAE, Kuwait, Qatar, Oman, Pakistan

**Implementation**:
1. Parse job location from `extracted_jd.location`
2. Check against MIDDLE_EAST_COUNTRIES list
3. Inject tagline in header

**Files**: `src/layer6_v2/orchestrator.py:315-333`, `src/common/constants.py`

---

### GAP-015: CV V2 - Color Scheme Change
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 0.5 days
**Impact**: Current teal/green doesn't suit; need dark greyish blue

**Current**: `#0f766e` (teal/green)
**Required**: `#475569` (slate-600 dark greyish blue)

**Additional**: Detail page design must match editor design (consistency)

**Files**: `frontend/templates/base.html`, `job_detail.html`, `pdf_service/`

---

### GAP-016: DateTime Range Picker Enhancement
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 1-2 hours
**Impact**: Date filter only allows day-level; users need hour/minute precision

**Fix**: Use HTML5 `datetime-local` input instead of `date` input
**Files**: `frontend/templates/index.html` (lines 175-188)

---

### GAP-017: E2E Tests Disabled
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: 48 Playwright tests exist but disabled due to config issues

**Plan**: `plans/e2e-testing-implementation.md`

---

### GAP-018: Integration Tests Not in CI/CD
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 3-4 hours
**Impact**: No automated integration testing on push

---

### GAP-019: Code Coverage Not Tracked
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 2 hours
**Impact**: Unknown test coverage percentage

---

### GAP-020: STAR Selector Disabled/Incomplete
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Feature flag `ENABLE_STAR_SELECTOR=false` by default

**Missing**: Embeddings, caching, graph edges for STAR selection

---

### GAP-021: Remote Publishing Disabled
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Feature flag `ENABLE_REMOTE_PUBLISHING=false` by default

**Missing**: Google Drive/Sheets integration not tested

---

### GAP-022: Job Application Progress UI Frontend
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Backend API done; frontend components pending

**Completed**: `/api/dashboard/application-stats`, `/jobs/{run_id}/progress`
**Missing**: Frontend progress bar, layer indicators, real-time updates

---

### GAP-023: Application Form Mining (Layer 1.5)
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: TBD
**Impact**: Form field extraction from job postings not implemented

---

### GAP-024: V2 Parser/Tailoring Not Implemented
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: 18+ unit tests skipped with reason "Will fail until V2 parser/tailoring implemented"

**Evidence**: `tests/unit/test_layer6_cv_generator_v2.py` - multiple skipped tests

---

### GAP-025: V2 Prompts Not Implemented
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Multiple tests skipped for V2 prompts (opportunity mapper, cover letter, CV QA)

**Evidence**:
- `tests/unit/test_layer4_opportunity_mapper_v2.py` - 6 skipped
- `tests/unit/test_layer6_cover_letter_generator_v2.py` - 8 skipped

---

## P3: LOW (Backlog)

### GAP-026: CV V2 - Spacing 20% Narrower
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 2 hours
**Impact**: CV needs more compact layout

**Files**: Frontend templates, PDF service CSS

---

### GAP-027: .docx CV Export
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Currently PDF only; some recruiters prefer Word format

---

### GAP-028: Runner Terminal Copy Button
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 1 hour
**Impact**: No easy way to copy pipeline logs

---

### GAP-029: UI/UX Design Refresh
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 8-16 hours
**Impact**: Modern styling improvements needed

---

### GAP-030: Layer-Specific Prompt Optimization
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: Ongoing
**Impact**: Phase 2 focus - improve prompt quality per layer

**Plan**: `plans/prompt-optimization-plan.md`

---

### GAP-031: FireCrawl Contact Discovery Fallback
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 8-12 hours
**Impact**: When FireCrawl fails, no fallback mechanism

**Plan**: `plans/ai-agent-fallback-implementation.md`

---

### GAP-032: Job Iframe Viewer
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: View original job posting in iframe

**Plan**: `plans/job-iframe-viewer-implementation.md`

---

### GAP-033: Dossier PDF Export
**Priority**: P3 LOW | **Status**: PENDING | **Effort**: 4-6 hours
**Impact**: Export complete dossier as PDF

**Plan**: `plans/dossier-pdf-export-implementation.md`

---

### GAP-034: Bulk Job Processing
**Priority**: P2 MEDIUM | **Status**: PENDING | **Effort**: 8-12 hours
**Impact**: No batch processing capability; must process jobs one at a time

**Current State**:
- Pipeline processes single job per invocation
- No queue management for multiple jobs
- No parallel processing optimization
- No bulk progress tracking

**Fix Required**:
1. Implement job queue with priority ordering
2. Add batch processing endpoint in runner service
3. Create bulk progress dashboard in frontend
4. Optimize for parallel layer execution where possible

**Files**: `runner_service/app.py`, `scripts/run_pipeline.py`, `frontend/`

---

## Completed (Nov 2025)

### Core Infrastructure
- [x] All 7 pipeline layers implemented and tested (180+ unit tests)
- [x] Runner service with subprocess execution, JWT auth, artifact serving
- [x] Frontend with job browsing, process buttons, health indicators
- [x] MongoDB persistence, FireCrawl integration, rate limiting, circuit breaker pattern
- [x] Metrics collection, error alerting, budget monitoring

### CV Rich Text Editor
- [x] Phase 1-5: TipTap foundation, formatting toolbar, document styles, PDF export, page breaks
- [x] Phase 6: PDF service separation into dedicated microservice
- [x] Playwright async API conversion, PDF generation bug fixes, WYSIWYG sync fix
- [x] 270+ unit tests for CV editor

### Observability & Safety
- [x] Token budget enforcement (TokenTracker, sliding window algorithm)
- [x] Rate limiting (RateLimiter with per-minute and daily limits)
- [x] Circuit breaker pattern (3-state, pre-configured for external services)
- [x] Structured logging across all 10 pipeline nodes (LayerContext)
- [x] Metrics dashboard (token usage, rate limits, health status)
- [x] Budget monitoring UI (progress bars, thresholds, alerts)
- [x] Error alerting system (ConsoleNotifier, SlackNotifier, deduplication)

### Pipeline & Features
- [x] CV Generation V2 (Layer 1.4 JD Extractor)
- [x] Layer-level structured logging with timing metadata
- [x] ATS compliance research (keyword integration best practices)
- [x] Pipeline progress UI backend API
- [x] Config validation (Pydantic Settings)
- [x] Service health status indicator with capacity metrics
- [x] Application stats dashboard (today/week/month/total counts)

---

## Quick Reference

### Priority Definitions

| Priority | Definition | SLA |
|----------|------------|-----|
| **P0** | System broken, data integrity at risk, production down | Fix immediately |
| **P1** | User-facing bugs, important features broken | Fix this week |
| **P2** | Enhancements, incomplete features, tech debt | Fix this sprint |
| **P3** | Nice-to-have, backlog items | When time permits |

### Key Files

| File | Purpose |
|------|---------|
| `plans/missing.md` | This file - all gaps tracked |
| `plans/architecture.md` | System architecture |
| `bugs.md` | Bug-specific tracking |
| `plans/next-steps.md` | Immediate action items |

### Agent Reports

- `reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`
- `reports/debugging/2025-11-30-cv-hallucination-root-cause-analysis.md`
- `reports/agents/doc-sync/2025-11-30-vps-backup-assessment.md`
