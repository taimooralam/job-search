# Implementation Gaps vs ROADMAP

This file tracks only **what is missing or partially implemented** compared to `ROADMAP.md`.
Completed items have been removed. See git history for detailed completion records.

**Last Updated**: 2025-11-22

---

## Operational Deviations (by design)

- **STAR selector paused**: Layer 2.5 disabled via `ENABLE_STAR_SELECTOR=false`; downstream uses master-cv.md fallback
- **CV format**: Generates `CV.md` (not `.docx`) via `prompts/cv-creator.prompt.md` + `master-cv.md`
- **Remote publishing disabled**: `ENABLE_REMOTE_PUBLISHING=false`; outputs in `./applications/<company>/<role>/`
- **People discovery fallback**: When no contacts found, returns 3 fallback cover letters grounded in master CV

---

## Phase 1 – Foundation & Core Infrastructure

### Remaining Gaps
- **MongoDB collections**: `star_records` and `pipeline_runs` collections defined but unused
- **FireCrawl rate limiting**: No explicit throttling (retries exist but no rate-limit/token bucket)
- **OpenRouter + Anthropic fallback**: Config exists but no Anthropic fallback path implemented
- **Structured logging**: Uses `print` statements; no JSON logger, log levels, or centralized logging
- **Git hooks / pre-commit**: No `.pre-commit-config.yaml`; black/mypy/flake8 not wired to hooks
- **Connectivity checks**: Only ad-hoc scripts; no unified health check CLI or automated suite

---

## Phase 2 – STAR Library & Candidate Knowledge Base

### 2.1 Canonical STAR Schema – ✅ COMPLETE

### 2.2 STAR Knowledge Graph & Hybrid Selector – ✅ COMPLETE

### Remaining Gaps
- **Embedding generation**: No actual embedding calls implemented; placeholder only
- **Graph edges**: No MongoDB graph edges persisted (Company/Role/Skill relationships)
- **STAR selection caching**: Cache logic exists but keying by `pain_points_hash` not implemented

---

## Phase 3 – Layer 1 & 1.5 (Input & Form Mining)

### 3.1 Job Input Collector – ✅ COMPLETE (via run_pipeline.py)

### 3.2 Application Form Field Miner – ✅ COMPLETE

### Remaining Gaps
- **Job prioritization**: No automatic tier pre-assignment from MongoDB
- **Time-based filtering**: `posted_at` filtering not exposed in CLI

---

## Phase 4 – Layer 2 (Pain-Point Miner) – ✅ COMPLETE

---

## Phase 5 – Layer 3 (Company & Role Research) – ✅ COMPLETE

### Remaining Gaps
- **Source attribution**: FireCrawl-scraped signals lack URL tagging
- **MongoDB caching TTL**: No TTL index configured on `company_cache`

---

## Phase 6 – Layer 4 (Opportunity Mapper) – ✅ COMPLETE

---

## Phase 7 – Layer 5 (People Mapper) – ✅ COMPLETE

### Remaining Gaps
- **Contact enrichment**: `recent_signals` field not populated (requires LinkedIn scraping)

---

## Phase 8 – Layer 6a (Cover Letter & CV Generator) – ✅ COMPLETE

---

## Phase 9 – Layer 6b (Outreach Generator) – ✅ COMPLETE

---

## Phase 10 – Layer 7 (Dossier & Output Publisher)

### 10.1 Dossier Generator – ✅ COMPLETE (22 Nov 2025)
- 10-section structure with Pain→Proof→Plan implemented
- Primary/secondary contacts with outreach_packages
- Application form fields and feature flags in metadata

### 10.2 Remaining Gaps
- **JobState.dossier_path**: Field not added to JobState TypedDict
- **Local output files**: Missing `application_form_fields.txt` and `outreach/` subfolder per-contact files
- **MongoDB persistence**: Missing `outreach_packages`, `cv_path`, `run_id`, `pipeline_runs` collection writes
- **Per-section validation**: No validation metadata or tier/status fields per section
- **FireCrawl query logging**: Queries used not logged in dossier

---

## Phase 11 – Tier System & Batch Processing

### Not Started
- **Tier field**: `JobState` has no `tier` field
- **Tier CLI flags**: `--tier` argument not implemented
- **Tier-based execution**: No conditional layer execution by tier
- **Cost tracking by tier**: No per-tier cost logging
- **Tier auto-assignment**: No automatic tier based on fit score
- **Batch CLI**: `scripts/run_batch.py` does not exist
- **Concurrency runner**: No parallel job processing
- **Progress display**: No terminal progress bars

---

## Phase 12 – Caching & Performance Optimization

### Partially Implemented
- **Company cache**: Exists in MongoDB but no TTL index
- **STAR selection cache**: Code exists but incomplete

### Not Started
- **Batch optimization**: No company grouping, pre-fetch, or batch embedding
- **Rate limiting infrastructure**: No token bucket for FireCrawl
- **Connection pooling**: No explicit MongoDB connection pooling
- **OpenAI batch API**: Not implemented

---

## Phase 13 – Testing & QA

### Partially Implemented
- **Unit tests**: Good coverage for Layers 2-7 (~150+ tests)
- **Integration tests**: Layer-specific e2e tests added (11 tests)

### Not Started
- **CI integration**: No GitHub Actions pytest workflow
- **Coverage**: No coverage measurement or 80% target enforcement
- **Hallucination tests**: No systematic hallucination detection suite
- **Cost validation**: No automated cost measurement tests

---

## Phase 14 – Production Deployment & Monitoring

### Not Started
- **Dockerfile**: Not created
- **docker-compose.yml**: Not created
- **VPS deployment guide**: Not written
- **systemd unit files**: Not created
- **Cron scheduling**: Not configured
- **Structured logging**: Print-based only
- **LangSmith dashboards**: No custom dashboards
- **Alerting**: No Telegram bot or error alerts
- **Cost budget enforcement**: No daily caps or alerts

---

## Phase 15 – Advanced Features & Polish

### Not Started
- All features (tier auto-tuning, advanced STAR matching, dossier customization, UI)

---

## Phase 16 – Documentation & Handoff

### Partially Implemented
- `architecture.md` exists but not fully updated
- Inline code documentation exists

### Not Started
- **User guide**: `docs/user-guide.md` not written
- **Developer guide**: `docs/developer-guide.md` not written
- **Prompts documentation**: `docs/prompts.md` not written
- **API documentation**: `docs/api.md` not written
- **Maintenance playbook**: `docs/maintenance.md` not written
- **Video walkthrough**: Not created

---

## Summary: What's Working vs What's Left

### ✅ Production-Ready (Phases 1-9)
- Full pipeline from job input → dossier output
- Pain point mining with 4-category schema
- Company & role research with signals
- Fit scoring with STAR/master-CV fallback
- People mapping with primary/secondary contacts
- Cover letter generation with 5-gate validation
- CV generation via markdown template
- Outreach packaging with LinkedIn/email variants
- 10-section dossier generation

### 🚧 Partially Complete (Phase 10)
- Dossier generator enhanced
- MongoDB persistence needs expansion
- Local file output needs additional files

### ❌ Not Started (Phases 11-16)
- Tier system & batch processing
- Caching & optimization
- Full test suite with CI
- Production deployment
- Advanced features
- Documentation
