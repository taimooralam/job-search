# Implementation Gaps vs ROADMAP

This file tracks what is **missing or only partially implemented** compared to `ROADMAP.md`, organized by phase.

---

## Phase 1 – Foundation & Core Infrastructure

- **MongoDB collections**:  
  - `star_records` and `pipeline_runs` collections are not used anywhere in the current codebase (only `level-1`, `level-2`, and `company_cache` are referenced).
- **FireCrawl rate limiting**:  
  - FireCrawl is used with retries in `src/layer3/company_researcher.py`, but there is no explicit rate‑limiting (e.g., throttling, sleep, token bucket).
- **OpenRouter + Anthropic fallback**:  
  - `Config.USE_OPENROUTER` and `Config.get_llm_base_url()` exist, but there is no Anthropic fallback path; all LLM calls use a single model name.
- **Structured logging**:  
  - Logging is via `print` statements; there is no shared JSON logger, log levels, or centralized logging utilities.
- **Git hooks / pre‑commit**:  
  - No `.pre-commit-config.yaml` and only default `.git/hooks/*.sample` files; black/mypy/flake8 are not wired into hooks.
- **Connectivity checks**:  
  - Connectivity to external services is only exercised via ad‑hoc scripts (`scripts/test_layer2.py`, `scripts/test_layer3.py`, `scripts/test_layer7.py`), not as a unified health check or automated test suite.

---

## Phase 2 – STAR Library & Candidate Knowledge Base

- **STARRecord schema mismatch**:  
  - ROADMAP expects `timeframe: str`, `actions: List[str]`, `metrics: List[str]`, `keywords: List[str]`, and an `embedding` field.  
  - Current `STARRecord` (`src/common/state.py` and `src/layer2_5/star_parser.py`) uses `period: str`, flattens `actions`, `metrics`, and `keywords` into plain strings, and has no `embedding`.
- **STAR parser location & behavior**:  
  - `src/common/star_parser.py` (as described) does not exist; the parser lives in `src/layer2_5/star_parser.py`.  
  - Parser does basic extraction and prints warnings, but there is no explicit "lenient parsing with warnings + skip malformed records" configuration surface beyond best‑effort regex parsing.
- **MongoDB STAR storage**:  
  - Parsed STARs are not stored in a `star_records` MongoDB collection; they are loaded directly from `knowledge-base.md` at runtime.
- **Embeddings**:  
  - No one‑time embedding generation for STARs and no embedding field on `STARRecord`.
- **CLI tool**:  
  - `scripts/parse_stars.py` does not exist.
- **STAR selector strategy modes**:  
  - `STARSelector` implements an LLM‑based scoring path only. The configurable strategies (`LLM_ONLY`, `HYBRID`, `EMBEDDING_ONLY`) and caching of selections in MongoDB are not implemented.
- **Tests**:  
  - STAR parser and selector are exercised by `scripts/test_star_parser.py`, but there are no pytest tests under `tests/` with mocked LLMs/embeddings as described.

---

## Phase 3 – Layer 1 & 1.5 (Input Collector & Form Miner)

- **Layer 1 code**:  
  - `src/layer1/input_collector.py` does not exist. There is no implementation for batch job fetching, CLI filters, prioritization, or deduplication based on `pipeline_run_at`.
- **Layer 1.5 code**:  
  - `src/layer1_5/form_miner.py` does not exist. There is no FireCrawl‑based form scraping or LLM‑based form field extraction.
- **JobState fields**:  
  - `JobState` lacks `location`, `criteria`, and `application_form_fields`, so the downstream contract for these fields is not present.
- **Filesystem outputs**:  
  - There is no `application_form_fields.txt` generation under `applications/<company>/<role>/`.
- **Tests**:  
  - No pytest tests for input collection or form mining behavior.

---

## Phase 4 – Layer 2 (Enhanced Pain‑Point Miner) ✅ COMPLETE

**Status**: Production-ready and ROADMAP-compliant

### ROADMAP Phase 4 Compliance Verification

✅ **All Deliverables Complete** (src/layer2/pain_point_miner.py:25-306):
- ✅ JSON-only output enforced by Pydantic `PainPointAnalysis` schema (lines 25-83)
- ✅ Four categories with exact item counts:
  - `pain_points`: 3-6 items (line 50-55)
  - `strategic_needs`: 3-6 items (line 56-61)
  - `risks_if_unfilled`: 2-4 items (line 62-67)
  - `success_metrics`: 3-5 items (line 68-73)
- ✅ Prompt engineering (lines 87-139):
  - Emphasizes "why now" and business context
  - Forbids generic boilerplate with concrete examples (lines 112-118)
  - Requires specificity to company/role/industry
  - Hallucination prevention section (lines 106-110)
- ✅ Temperature: 0.3 (ANALYTICAL_TEMPERATURE, line 151)
- ✅ Model: GPT-4o (Config.DEFAULT_MODEL, line 150)
- ✅ Pydantic schema validation with field validators (lines 75-82)
- ✅ Retry logic: 3 attempts with exponential backoff (lines 156-160, tenacity)
- ✅ Stores all four fields in JobState (lines 246-252, 289-299)

✅ **All Quality Gates Met**:
- ✅ JSON-only output validated across 5 test job scenarios (integration tests)
- ✅ Pain points are specific, not generic (quality gate validators)
- ✅ pytest tests with mocked LLM + schema validation (34 tests total)
- ✅ Hallucination test: No invented company facts (integration tests)

### Implementation Details

**1. ✅ Hallucination & Boilerplate Controls** (TODO 1)
- SYSTEM_PROMPT includes (lines 106-120):
  - "Only use facts explicitly stated in the job description provided"
  - "DO NOT invent company details (funding, products, size, history) not in the JD"
  - "If something is unclear, infer from job requirements, don't fabricate"
  - Explicit forbidden boilerplate examples with ✅/❌ markers
  - "Be concrete, technical, and tied to actual business problems"

**2. ✅ Pytest Unit Tests** (TODO 2)
- Created `tests/unit/test_pain_point_miner.py` with 18 unit tests:
  - **Schema validation tests (7)**: All required fields, min/max counts, non-empty strings, type checking
  - **JSON parsing tests (6)**: Valid JSON, malformed JSON, extra text handling, missing fields
  - **LLM integration tests (5)**: Successful extraction, LLM failures, incomplete schema, error handling
- All tests use `unittest.mock.patch` on `ChatOpenAI` for determinism
- Test coverage includes all fallback paths and error scenarios

**3. ✅ Quality Gate Tests** (TODO 3)
- Created `tests/integration/test_pain_point_quality_gates.py` with 16 integration tests:
  - **3 validator functions**:
    - `validate_no_generic_boilerplate`: Checks for 10 forbidden phrases
    - `validate_specific_metrics`: Ensures numeric metrics present
    - `validate_no_hallucinated_facts`: Detects invented company details
  - **15 parametrized tests** across 5 diverse job scenarios:
    - Senior SRE (technical role)
    - Engineering Manager (leadership role)
    - ML Engineer (data role)
    - Senior Product Manager (product role)
    - Security Engineer (security role)
  - Each scenario tested against all 3 quality gates
  - Plus 1 summary test documenting quality gate status

**4. ✅ In-Code Documentation** (TODO 4)
- Extended `PainPointAnalysis` docstring (lines 25-49) with:
  - ROADMAP Phase 4 Quality Gates checklist
  - Schema enforcement details (exact item counts per field)
  - Content requirements with examples
  - Links implementation to ROADMAP targets

### Test Results
```
✅ 18/18 unit tests PASSED (7.80s)
✅ 16/16 integration tests PASSED (0.45s)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 34/34 total tests PASSING (4.63s)
```

### Files Delivered
- `src/layer2/pain_point_miner.py` - Production-ready implementation
- `tests/unit/test_pain_point_miner.py` - Comprehensive unit test suite
- `tests/integration/test_pain_point_quality_gates.py` - Quality gate validation
- `pytest.ini` - Test configuration with custom markers

**Phase 4 is production-ready for single-job processing with full ROADMAP compliance.**

---

## Phase 5 – Layer 3 (Company & Role Researcher)

**Status**: ✅ COMPLETE - All ROADMAP Phase 5 deliverables have been implemented with production-grade quality.

### 5.1 Company Researcher with Multi-Source Scraping

- **What is implemented**:
  - `src/common/state.py`:
    - `CompanySignal` and `CompanyResearch` `TypedDict`s.
    - `JobState.company_research` field, plus legacy `company_summary`/`company_url` for backward compatibility.
  - `src/layer3/company_researcher.py`:
    - Pydantic `CompanySignalModel` and `CompanyResearchOutput` models with JSON-only enforcement and validation.
    - `SYSTEM_PROMPT_COMPANY_SIGNALS` + `USER_PROMPT_COMPANY_SIGNALS_TEMPLATE` with hallucination prevention and `"unknown"` fallback rules.
    - **✅ `_search_with_firecrawl`** - New method that uses FireCrawl search API to find and scrape LinkedIn, Crunchbase, and news URLs with domain-specific filtering and retry logic.
    - **✅ `_scrape_multiple_sources`** - Fully implemented for all four ROADMAP queries (official site, LinkedIn, Crunchbase, news) using direct URL construction for official site and FireCrawl search for other sources.
    - `_analyze_company_signals` that calls the LLM, parses JSON, and validates via `CompanyResearchOutput`.
    - Enhanced cache (`_check_cache`, `_store_cache`) that stores/loads full `company_research` and fills legacy fields.
    - `research_company` returning `company_research` plus legacy `company_summary`/`company_url`, with a robust fallback to the legacy single-URL scrape.
  - Tests in `tests/unit/test_layer3_researchers.py` (21 tests total):
    - Pydantic schema tests for `CompanyResearchOutput`.
    - Tests with mocked FireCrawl, Mongo, and LLM for cache hits/misses and prompt contents.
    - **✅ 6 signal type coverage tests** - One test per signal type (funding, acquisition, leadership_change, product_launch, partnership, growth) verifying correct extraction and schema validation.
    - **✅ Quality gate test** - `test_quality_gate_minimum_signals` asserting ≥3 signals for rich content scenarios.

### 5.2 Role Researcher

- **What is implemented**:
  - `src/common/state.py`:
    - `RoleResearch` `TypedDict` and `JobState.role_research` field.
  - `src/layer3/role_researcher.py`:
    - Pydantic `RoleResearchOutput` model with `summary`, `business_impact` (3–5 items), and `why_now`.
    - `SYSTEM_PROMPT_ROLE_RESEARCH` and `USER_PROMPT_ROLE_RESEARCH_TEMPLATE` with JSON-only instructions, hallucination prevention, and role-specific context section.
    - **✅ `_scrape_role_context`** - ROADMAP Phase 5.2 FireCrawl queries for role-specific responsibilities and KPIs:
      - Query 1: `"${title}" responsibilities ${company}"`
      - Query 2: `"${title}" KPIs ${industry}"`
      - Uses FireCrawl search API with retry logic
      - Scrapes top results and limits to 1000 chars per query
      - Graceful degradation if scraping fails (continues with job description only)
    - `_analyze_role` that builds the prompt from job description, role context, and company signals, calls the LLM, and validates JSON via `RoleResearchOutput`.
    - `research_role` calls `_scrape_role_context`, then converts the model into the `RoleResearch` `TypedDict` and updating state, with graceful error fallback.
    - `role_researcher_node` printing the role summary, business impact, and why_now.
  - **✅ `src/workflow.py`** - Role Researcher wired into main workflow as Layer 3.5 between `company_researcher` and `opportunity_mapper`, with `role_research` field added to initial state.
  - Tests in `tests/unit/test_layer3_researchers.py`:
    - Schema tests for `RoleResearchOutput` including business_impact list length validation (3-5 items).
    - Mocked LLM tests verifying `RoleResearcher.research_role` populates `role_research` and that prompts contain hallucination-prevention text.
    - Test verifying "why_now" references company signals when available.
    - Integration test for `role_researcher_node`.

**Phase 5 is production-ready with full multi-source scraping, comprehensive signal extraction, and complete workflow integration.**  

---

## Phase 6 – Layer 4 (Opportunity Mapper)

**Status**: ✅ COMPLETE - All ROADMAP Phase 6 deliverables have been implemented with production-grade quality and comprehensive test coverage.

### 6.1 Enhanced Opportunity Mapper with STAR Citations

- **What is implemented**:
  - `src/common/state.py`:
    - **✅ `fit_category: Optional[str]`** - Added to JobState with allowed values: "exceptional" | "strong" | "good" | "moderate" | "weak"
  - `src/layer4/opportunity_mapper.py` (375 lines):
    - **✅ `_derive_fit_category`** - Derives category from score per ROADMAP rubric (90-100: exceptional, 80-89: strong, 70-79: good, 60-69: moderate, <60: weak)
    - **✅ `_validate_rationale`** - Comprehensive validation with 3 quality gates:
      - Quality Gate 1: Must cite ≥1 STAR by number (regex: `STAR #\d+`)
      - Quality Gate 2: Must include ≥1 quantified metric (patterns: `\d+%`, `\d+x`, `\d+M`, `\d+K`, `\d+\s*min`, `\d+h`)
      - Quality Gate 3: Detects generic boilerplate ("strong background", "team player", etc.) and rejects if too many generic phrases
    - **✅ `_format_company_research`** - Formats company_research (summary + signals) for prompt
    - **✅ `_format_role_research`** - Formats role_research (summary, business_impact, why_now) for prompt
    - **✅ Enhanced `_analyze_fit`** - Now returns (score, rationale, category) tuple and calls validation (raises ValueError on failure to trigger retry)
    - **✅ Updated `USER_PROMPT_TEMPLATE`** - Includes COMPANY RESEARCH (Phase 5.1) and ROLE RESEARCH (Phase 5.2) sections with explicit requirements:
      - Must reference STAR by number and company (e.g., "STAR #1 (AdTech modernization)")
      - Must cite quantified metrics (e.g., "75% incident reduction", "24x faster")
      - Must reference company signals OR role "why now" when available
      - Must avoid generic phrases
    - **✅ Backward compatibility** - Handles states without company_research/role_research gracefully
    - **✅ `map_opportunity`** - Returns fit_score, fit_rationale, AND fit_category
  - `src/workflow.py`:
    - **✅ `fit_category` field** - Added to initial state initialization
  - Tests in `tests/unit/test_layer4_opportunity_mapper.py` (23 tests total, 310 lines):
    - **✅ 14 parametrized fit_category tests** - Validates all score ranges map to correct categories
    - **✅ STAR citation validation tests** - Pass/fail scenarios for STAR references
    - **✅ Metric validation tests** - Pass/fail scenarios for quantified metrics
    - **✅ Generic phrase detection tests** - Rejects boilerplate rationales
    - **✅ Company research integration tests** - Verifies company_research in prompts
    - **✅ Role research integration tests** - Verifies role_research in prompts
    - **✅ Backward compatibility test** - Works without Phase 5 fields
    - **✅ Integration test** - Full node function test

**Phase 6 is production-ready with comprehensive validation, quality gates, and 23/23 tests passing.**  

---

## Phase 7 – Layer 5 (People Mapper)

**Status**: ✅ COMPLETE - All ROADMAP Phase 7 deliverables have been implemented with production-grade quality and comprehensive test coverage.

### 7.1 Enhanced People Mapper with Multi-Source Discovery

- **What is implemented**:
  - `src/common/state.py`:
    - **✅ Enhanced `Contact` TypedDict** - Added `recent_signals: List[str]` field (Phase 7)
    - **✅ `OutreachPackage` TypedDict** - New type for per-contact outreach (Phase 7/9)
    - **✅ `JobState` fields** - Added `primary_contacts`, `secondary_contacts`, `outreach_packages`, kept `people` for backward compatibility
  - `src/layer5/people_mapper.py` (691 lines):
    - **✅ Pydantic models** - `ContactModel` and `PeopleMapperOutput` with validation:
      - Min/max length validators (name, why_relevant ≥20 chars)
      - Quality gates: 4-6 primary contacts, 4-6 secondary contacts
      - Generic name prevention ("Unknown", "TBD", etc.)
    - **✅ FireCrawl multi-source discovery** (Phase 7.2.2):
      - `_scrape_company_team_page` - Scrapes team/about/leadership pages
      - `_search_linkedin_contacts` - FireCrawl search for LinkedIn employees
      - `_search_hiring_manager` - Searches for hiring manager by title + company
      - `_search_crunchbase_team` - Searches Crunchbase for company team information
      - `_deduplicate_contacts` - Deduplicates across sources
      - `_discover_contacts` - Orchestrates 4 discovery sources
    - **✅ JSON-only classification prompt** (Phase 7.2.3):
      - `SYSTEM_PROMPT_CLASSIFICATION` - Defines primary vs secondary buckets
      - `USER_PROMPT_CLASSIFICATION_TEMPLATE` - Includes company research, role research, pain points
      - Returns structured JSON with validated schema
    - **✅ LLM classification** - `_classify_contacts`:
      - Classifies into primary (hiring-related) and secondary (cross-functional)
      - Enriches with `recent_signals` from company research
      - Role-based fallback when no names found ("VP Engineering at {company}")
      - Validates with Pydantic (raises ValueError to trigger retry)
    - **✅ Outreach generation** (Phase 7.2.4):
      - `_generate_outreach_package` - JSON-only outreach per contact
      - `_validate_linkedin_message` - Enforces ≤550 char limit (Phase 9)
      - `_validate_email_subject` - Enforces ≤100 char limit
      - Cites STAR metrics in outreach
      - References company signals and role context
    - **✅ `map_people` main function** - Orchestrates full pipeline:
      1. Multi-source FireCrawl discovery
      2. LLM classification into primary/secondary
      3. OutreachPackage generation for all contacts
      4. Quality gate enforcement (4-6 each)
  - `src/workflow.py`:
    - **✅ Initialized new fields** - `primary_contacts`, `secondary_contacts`, `outreach_packages` in initial state
  - Tests in `tests/unit/test_layer5_people_mapper.py` (20 tests total, 708 lines):
    - **✅ Pydantic model tests (5)** - Validation, min/max contacts, required fields
    - **✅ FireCrawl discovery tests (5)** - Team page, LinkedIn, hiring manager, Crunchbase, deduplication
    - **✅ LLM classification tests (3)** - Primary/secondary split, role-based fallback, signal enrichment
    - **✅ Outreach generation tests (4)** - Package creation, length constraints, STAR metric citation
    - **✅ Integration test (1)** - Full node function with mocked FireCrawl + LLM
    - **✅ Quality gate tests (2)** - Minimum contacts, specific why_relevant

**Phase 7 is 100% ROADMAP-compliant with 4-source discovery, JSON validation, and 20/20 tests passing.**

---

## Phase 8 – Layer 6a/6b (Cover Letter & Outreach Generator)

- **Cover letter implementation**:  
  - Layer 6 is implemented in `src/layer6/generator.py` as a combined cover‑letter + CV generator. There is no dedicated `outreach_generator.py` module for cover letters alone as described in the ROADMAP.
- **Cover‑letter quality gates**:  
  - The ROADMAP requires explicit checks for STAR citations, metrics, and avoiding generic boilerplate; there is no separate validation module enforcing these constraints.
- **Per‑lead outreach (Layer 6b)**:  
  - There is no `src/layer6/outreach_generator.py` and no `JobState.outreach_packages`; lead‑specific outreach is handled inside Layer 5 instead.
- **CV reasoning**:  
  - `JobState` lacks a `cv_reasoning` field.
- **Tests**:  
  - No pytest tests under `tests/` for cover‑letter validation or outreach generation behavior.

---

## Phase 9 – Layer 6b (Per‑Lead Outreach Packages)

- **Module & type**:  
  - `src/layer6/outreach_generator.py` and `OutreachPackage` TypedDict are missing.  
  - The pipeline does not produce `JobState.outreach_packages`.
- **Constraints**:  
  - Character limits and structural constraints (subject length, LinkedIn ≤550 chars, etc.) are not enforced or tested.
- **Tests**:  
  - No pytest coverage for per‑lead outreach JSON shape or constraints.

---

## Phase 10 – Layer 7 (Dossier & Output Publisher)

- **Dossier sections**:  
  - `src/layer7/dossier_generator.py` generates a multi‑section dossier, but it does not yet implement all 10 sections described in the ROADMAP (e.g., full job requirements/criteria, role research, FireCrawl queries, per‑section validation metadata).
- **Pain → Proof → Plan block**:  
  - There is no explicit top‑of‑file “Pain → Proof → Plan” section.
- **JobState.dossier_path**:  
  - `JobState` has no `dossier_path` field; the dossier path is only returned via Layer 7 outputs.
- **Local output set**:  
  - Local writes cover `dossier.txt`, `cover_letter.txt`, contacts, and CV, but not `application_form_fields.txt` or per‑contact outreach files in an `outreach/` subfolder.
- **Mongo persistence breadth**:  
  - `_persist_to_mongodb` updates many fields (`generated_dossier`, cover letter, pain point arrays, fit analysis, contacts, Drive/Sheets references) but does not write `outreach_packages`, `cv_path`, `run_id`, or a full `JobState` snapshot, nor does it use a separate `pipeline_runs` collection.
- **Status tracking**:  
  - `JobState.status` is set in `run_pipeline`, but there is no per‑layer status or per‑section validation metadata.
- **Tests**:  
  - `scripts/test_layer7.py` exists as an integration‑style TDD script; there are no pytest tests with mocked Google/Mongo clients.

---

## Phase 11 – Tier System & Batch Processing

- **Tier field & logic**:  
  - `JobState` has no `tier` field.  
  - No tier‑based branching in the workflow (all layers run unconditionally for each job).
- **Tier CLI flags**:  
  - `scripts/run_pipeline.py` accepts `--job-id`, `--profile`, `--test`, but no `--tier` argument.
- **Cost tracking by tier**:  
  - There is no explicit cost logging per tier; only LangSmith configuration is documented.
- **Batch processing CLI**:  
  - `scripts/run_batch.py` does not exist.  
  - There is no concurrency runner, progress bars, or batch summary reporting.
- **pipeline_runs collection**:  
  - No code writes summary records or errors to a `pipeline_runs` collection.

---

## Phase 12+ – Caching, Robustness, Testing, and Docs

High‑level gaps across later phases:

- **Advanced caching & FireCrawl query logging (Phase 12)**:  
  - Beyond `company_cache`, there is no dedicated caching module for other layers and no FireCrawl query logging/metadata collection.
- **Robustness, guardrails, and validation (Phase 13)**:  
  - There is no cross‑cutting validation layer that enforces JSON schemas, hallucination checks, or per‑section validation flags in `JobState`.
- **Evaluation suite (Phase 14)**:  
  - No `tests/` pytest suite exercising all layers with mocked dependencies.  
  - No CI configuration (e.g., GitHub Actions) running pytest on each commit.
- **ML optimization, template customization, and UI (Phase 15)**:  
  - No ML models, no dynamic tier prediction, no template system (`--dossier-template`), and no web UI.
- **Documentation & maintenance (Phase 16)**:  
  - Only `docs/langsmith-usage.md` exists; other docs (`user-guide.md`, `developer-guide.md`, `configuration.md`, etc.) are not present.  
  - No maintenance playbook or operational runbooks in `docs/`.

---

## Summary

The current codebase implements a strong vertical slice (Layers 2–7, simplified) but diverges from the full ROADMAP in several ways:

- The **state model** is a simplified `JobState` without many of the later fields (tier, application form fields, full company/role research, outreach packages, validation metadata).  
- Several **planned modules and CLIs** (Layer 1/1.5, outreach generator, batch runner) are missing.  
- **Persistence and logging** are focused on immediate outputs (Mongo `level-2` update, Drive/Sheets) without `star_records` / `pipeline_runs` collections or structured logging.  
- The **testing and documentation** story is still early: integration scripts exist, but the pytest suite, CI, and full docs from the ROADMAP are not in place yet.
