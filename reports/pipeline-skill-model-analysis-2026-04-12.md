# Pipeline Skill/Model Analysis: Claude Code vs Codex, Token Optimization, Stale Code

**Date:** 2026-04-12  
**Scope:** End-to-end pipeline from job ingestion to CV output — every LLM call, every stage  
**Reviewed by:** Codex gpt-5.4 exec (corrections applied inline, marked with `[CX]`)

---

## 1. Pipeline Architecture Overview

```
JOB INPUT (MongoDB level-2)
    │
    ├── Layer 1.4: JD Extractor ──────── Claude CLI (low tier = Haiku)
    │
    ├── Layer 2: Pain Point Miner ────── Claude CLI (middle tier = Sonnet)
    │
    ├── Layer 2.5: STAR Selector ─────── Claude CLI (middle tier = Sonnet)
    │
    ├── Layer 3.0: Company Researcher ── Claude CLI (middle) + FireCrawl + Web Search
    │
    ├── Layer 3.5: Role Researcher ───── Claude CLI (middle) + Web Search
    │
    ├── Layer 4: Opportunity Mapper ──── Claude CLI (middle tier)
    │
    ├── Layer 5: People Mapper ────────��� Claude CLI (middle) + LinkedIn Scraper
    │
    ├── Layer 6a: Outreach Generator ─── Claude CLI (middle tier)
    │
    ├── Layer 6b: CV Generator V2 ────── 7 internal phases (see Section 3)
    │       Phase 1: CV Loader ────────── No LLM (file read)
    │       Phase 2: Role Generator ───── Claude CLI × 6 roles (middle)
    │       Phase 3: Role QA ──────────── No LLM (rule-based)
    │       Phase 4: Stitcher ─────────── No LLM (algorithmic)
    │       Phase 5: Header Generator ─── Claude CLI × 1-3 (middle, tier-aware)
    │       Phase 5b: Title Sanitizer ─── Claude CLI × 1 (low = Haiku)
    │       Phase 6: Grader ───────────── Claude CLI × 1 (low = Haiku)
    │       Phase 6: Improver ─────────── Claude CLI × 0-1 (middle, conditional)
    │       Phase 6.5: Tailorer ───────── Claude CLI × 0-1 (middle, conditional)
    │
    ├── Layer 6c: Cover Letter ────────── Claude CLI (middle)
    │
    ├── Layer 7: Output Publisher ─────── No LLM (Google Drive + Sheets API)
    │
    └── Post-pipeline: CV Reviewer ────── Codex CLI (gpt-5.4-mini)
```

---

## 2. Complete LLM Call Inventory

### 2.1 Per-Step Model & Provider Mapping

| Step | File | step_name | Tier | Model | Provider | Calls/Job | Approx In | Approx Out |
|------|------|-----------|------|-------|----------|-----------|-----------|------------|
| JD Extraction | `layer1_4/claude_jd_extractor.py` | `jd_extraction` | low | Haiku 4.5 | Claude CLI | 1 | 2K | 800 |
| JD Structure Parsing `[CX]` | `layer1_4/jd_processor.py` | `jd_structure_parsing` | low | Haiku 4.5 | Claude CLI | 1 | 2K | 600 |
| Pain Point Mining | `layer2/pain_point_miner.py` | `pain_point_extraction` | middle | Sonnet 4.5 | Claude CLI | 1-2 | 3K | 1.2K |
| STAR Selection | `layer2_5/star_selector.py` | `star_selection` | middle | Sonnet 4.5 | Claude CLI | 1 | 4K | 1K |
| Company Classification `[CX]` | `layer3/company_researcher.py` | `classify_company_type` | low | Haiku 4.5 | Claude CLI | 1 | 1K | 200 |
| Company Signal Analysis | `layer3/company_researcher.py` | `analyze_company_signals` | middle | Sonnet 4.5 | Claude CLI + WebSearch | 1-2 | 3K | 2K |
| Company Summarization `[CX]` | `layer3/company_researcher.py` | `summarize_with_llm` | low | Haiku 4.5 | Claude CLI | 1 | 2K | 500 |
| Role Analysis `[CX]` | `layer3/role_researcher.py` | `role_analysis` | middle* | Sonnet 4.5 | Claude CLI + WebSearch | 1-2 | 3K | 1.5K |
| Fit Analysis | `layer4/opportunity_mapper.py` | `fit_analysis` | middle | Sonnet 4.5 | Claude CLI | 1-2 | 4K | 1K |
| People Mapping | `layer5/people_mapper.py` | `people_research` | middle | Sonnet 4.5 | Claude CLI + WebSearch | 2-3 | 3K | 2K |
| Contact Classification `[CX]` | `layer5/people_mapper.py` | `contact_classification` | middle* | Sonnet 4.5 | Claude CLI | 1 | 1.5K | 500 |
| Fallback Cover Letters `[CX]` | `layer5/people_mapper.py` | `fallback_cover_letters` | middle* | Sonnet 4.5 | Claude CLI | 1-2 | 2K | 1K |
| Outreach Gen | `layer6/outreach_generator.py` | `outreach_generation` | middle | Sonnet 4.5 | Claude CLI | 3-5 | 2K each | 500 each |
| Recruiter Cover Letter `[CX]` | `layer6/recruiter_cover_letter.py` | `recruiter_cover_letter` | middle | Sonnet 4.5 | Claude CLI | 1 | 3K | 1K |
| **Role Bullets** | `layer6_v2/role_generator.py` | `role_generator` | middle | Sonnet 4.5 | Claude CLI | **6** | 2.4K each | 500 each |
| Title Sanitizer `[CX]` | `layer6_v2/title_sanitizer.py` | `title_sanitizer` | middle* | Sonnet 4.5 | Claude CLI | 1 | 200 | 50 |
| Header Gen (single) | `layer6_v2/header_generator.py` | `header_generator` | middle | Sonnet 4.5 | Claude CLI | 1 | 5K | 1.5K |
| Header Gen (ensemble) | `layer6_v2/ensemble_header_generator.py` | `ensemble_header` | middle | Sonnet 4.5 | Claude CLI | 3 | 5K each | 1.5K each |
| Grading | `layer6_v2/grader.py` | `grader` | low | Haiku 4.5 | Claude CLI | 1 | 6K | 1K |
| Improvement | `layer6_v2/improver.py` | `improver` | middle | Sonnet 4.5 | Claude CLI | 0-1 | 6K | 2K |
| Tailoring | `layer6_v2/cv_tailorer.py` | `cv_tailorer` | middle | Sonnet 4.5 | Claude CLI | 0-1 | 5K | 2K |
| Cover Letter | `layer6_v2/cover_letter_generator.py` | `cover_letter_generation` | middle | Sonnet 4.5 | Claude CLI | 1 | 4K | 1K |
| AI Classification `[CX]` | `services/` | `ai_classification` | low | Haiku 4.5 | Claude CLI | 1 | 1K | 200 |
| Quick Scorer `[CX]` | `services/` | `quick_scorer` | low | Haiku 4.5 | Claude CLI | 1 | 1K | 200 |
| Form Scraping `[CX]` | `services/` | `form_scraping` | low | Haiku 4.5 | Claude CLI | 1 | 2K | 500 |
| Answer Generation `[CX]` | `services/` | `answer_generation` | middle | Sonnet 4.5 | Claude CLI | 1-3 | 2K each | 500 each |
| **CV Review** | `services/cv_review_service.py` | — | — | **gpt-5.4-mini** | **Codex CLI** | 1 | 8K | 2K |

> `[CX]` = Added/corrected after Codex gpt-5.4 review. `middle*` = not in STEP_CONFIGS, defaults to middle via StepConfig() default tier.

### 2.2 Call Count Summary

| Scenario | LLM Calls | Estimated Total Tokens | Estimated Cost |
|----------|-----------|------------------------|----------------|
| Full pipeline (Gold tier, all layers) | 25-35 | ~120K | ~$0.80-1.20 |
| CV-only (Gold tier, ensemble) | 12-15 | ~55K | ~$0.35-0.50 |
| CV-only (Bronze tier, single-shot) | 8-10 | ~35K | ~$0.15-0.25 |
| CV Review (post-pipeline) | 1 | ~10K | ~$0.01 (gpt-5.4-mini) |

---

## 3. Claude Code vs Codex: Where Each Excels

### 3.1 Current State

The pipeline uses **Claude CLI** (`claude -p`) for ALL LLM calls except CV Review, which uses **Codex CLI** (`codex exec`). LangChain/Anthropic API is the fallback when Claude CLI fails.

### 3.2 Recommended Assignments

| Stage | Current | Recommended | Rationale |
|-------|---------|-------------|-----------|
| **JD Extraction** | Claude CLI (Haiku) | **Codex** (gpt-5.4-mini) | Structured JSON extraction. GPT excels at schema adherence. Cheapest option. |
| **Pain Point Mining** | Claude CLI (Sonnet) | **Claude CLI** (Sonnet) | Nuanced reading of JD subtext. Claude's strength. |
| **STAR Selection** | Claude CLI (Sonnet) | **Codex** (gpt-5.4-mini) | Ranking/scoring task. Structured output. GPT-mini sufficient. |
| **Company Research** | Claude CLI (Sonnet) + WebSearch | **Claude CLI** (Sonnet) | Needs Claude CLI's built-in WebSearch tool. Codex has no web access. |
| **Role Research** | Claude CLI (Sonnet) + WebSearch | **Claude CLI** (Sonnet) | Same — requires WebSearch tool. |
| **Fit Analysis** | Claude CLI (Sonnet) | **Codex** (gpt-5.4-mini) | Scoring with rubric. Deterministic. GPT-mini sufficient. |
| **People Mapping** | Claude CLI (Sonnet) + WebSearch | **Claude CLI** (Sonnet) | Requires WebSearch tool. |
| **Outreach Gen** | Claude CLI (Sonnet) | **Claude CLI** (Sonnet) | Creative writing. Claude's voice quality is superior. |
| **Role Bullets (×6)** | Claude CLI (Sonnet) | **Claude CLI** (Sonnet) | `[CX]` Prompt is constraint-dense (ARIS format, anti-hallucination, claim locks, pain-point linkage, JSON schema). Haiku likely breaks format. Keep Sonnet. |
| **Title Sanitizer** | Claude CLI (Sonnet*) | **Codex** (gpt-5.4-mini) | `[CX]` Currently defaults to Sonnet (not in STEP_CONFIGS). Trivial string cleanup — cheapest model wins. |
| **Header Gen** | Claude CLI (Sonnet) | **Claude CLI** (Sonnet) | Creative + strategic. Claude's narrative quality matters. |
| **Ensemble Synthesis** | Claude CLI (Sonnet) | **Claude CLI** (Sonnet) | Multi-persona synthesis. Claude excels at perspective integration. |
| **Grading** | Claude CLI (Haiku) | **Codex** (gpt-5.4-mini) | Rubric-based scoring → JSON. GPT-mini at 1/10th the cost. |
| **Improvement** | Claude CLI (Sonnet) | **Claude CLI** (Haiku) | Targeted edits with constraints. Haiku sufficient. |
| **Tailoring** | Claude CLI (Sonnet) | **Claude CLI** (Haiku) | Keyword repositioning. Mechanical task. |
| **Cover Letter** | Claude CLI (Sonnet) | **Claude CLI** (Sonnet) | Creative writing. Quality matters. |
| **CV Review** | Codex (gpt-5.4-mini) | **Codex** (gpt-5.4-mini) | Already optimal. Independent validation. |

### 3.3 Decision Framework

**Use Claude CLI when:**
- Task requires WebSearch (company/role/people research)
- Creative writing quality matters (outreach, cover letter, header/tagline)
- Nuanced JD interpretation (pain point mining)
- Multi-perspective synthesis (ensemble header)

**Use Codex CLI when:**
- Task is structured JSON extraction (JD extraction, grading, scoring)
- Task is ranking/sorting (STAR selection, fit analysis)
- Task is trivial (title sanitization)
- Independent validation of Claude's output (CV review — avoid self-grading bias)

**Use Haiku (downgrade from Sonnet) when:**
- Task is mechanical editing (improvement, tailoring)
- Output is short and structured
- `[CX]` Note: Role bullets were initially recommended for Haiku, but Codex review found the prompt is too constraint-dense (ARIS format + anti-hallucination + claim locks + pain-point linkage). Keep at Sonnet.

### 3.4 Configurable Skill Architecture

To make this configurable, extend `STEP_CONFIGS` in `llm_config.py`:

```python
@dataclass
class StepConfig:
    tier: TierType = "middle"
    provider: Literal["claude_cli", "codex_cli", "anthropic_api", "openai_api"] = "claude_cli"
    claude_model: Optional[str] = None
    codex_model: Optional[str] = None  # NEW: e.g., "gpt-5.4-mini"
    fallback_model: Optional[str] = None
    timeout_seconds: int = 180
    max_retries: int = 2
    use_fallback: bool = True
```

Then `UnifiedLLM.invoke()` routes to the configured provider per step.

---

## 4. Token Optimization Opportunities

### 4.1 Biggest Wins

| Optimization | Tokens Saved/Job | Implementation |
|-------------|-----------------|----------------|
| ~~Role generation: Sonnet → Haiku~~ | ~~Same tokens, 3x cheaper~~ | `[CX]` Rejected — prompt too complex for Haiku |
| **Anthropic Prompt Caching** | ~9,600 (system prompt × 6 roles) | Set `cache_control` on system prompt |
| **JD context deduplication** | ~4,800 (800 × 6 roles) | Extract JD summary once, inject reference |
| **Batch 2-3 roles per call** | ~3,200 (fewer system prompts) | Restructure role_generator prompts |
| **Grading + Improvement: single call** | ~6,000 (eliminate duplicate CV text) | Combine grade+improve into one step |
| **Skip cover letter for low-fit** | ~5,000 (skip for Tier C/D) | Conditional in orchestrator |

### 4.2 Current Token Waste Analysis (per CV generation)

| Source of Waste | Tokens | % of Total |
|----------------|--------|------------|
| System prompt reparsed 6× (no caching) | 9,600 | 27% |
| Identical JD context in 6 role calls | 4,800 | 14% |
| Grading + Improvement as separate calls (duplicate CV text) | 6,000 | 17% |
| Cover letter for low-fit jobs | 5,000 | 14% |
| **Total waste** | **25,400** | **~45% of ~55K total** |

### 4.3 Model Cost Comparison (per CV)

| Configuration | Calls | Cost | Quality |
|-------------|-------|------|---------|
| Current (all Sonnet except grader) | 8-10 | ~$0.35 | High |
| Optimized (Haiku for improve/tailor/star/fit) `[CX]` | 8-10 | ~$0.18 | Same (mechanical tasks only) |
| + Prompt caching | 8-10 | ~$0.14 | Same |
| + Codex for grading/scoring/title | 8-10 | ~$0.12 | Same |

**Potential ~3x cost reduction** from current to fully optimized. `[CX]` Revised from 4x — role_generator stays Sonnet.

---

## 5. Stale & Redundant Code

### 5.1 Stale Code (Can Be Removed)

| File/Directory | Reason | Impact |
|---------------|--------|--------|
| `src/layer6/generator.py` | Deprecated, emits DeprecationWarning. Legacy two-stage CV gen. | ~460 lines dead code |
| `src/layer6/cv_generator.py` | Old OpenAI-based CV gen. Not in active workflow. | ~500 lines dead code |
| `src/layer6/html_cv_generator.py` | HTML CV variant. Never called in pipeline. | ~300 lines dead code |
| `prompts/*.md` (root level) | Old markdown prompt files (EVAL_PROMPT.md, cv-creator.prompt.md, star-curator.prompt.md). Replaced by `src/layer6_v2/prompts/`. | Confusion risk |
| `src/layer6/cover_letter_generator.py` (old) | Replaced by `src/layer6_v2/cover_letter_generator.py` | Duplicate |
| ~~`src/layer6/recruiter_cover_letter.py`~~ | `[CX]` Has active `recruiter_cover_letter` step in STEP_CONFIGS. Called from `people_mapper.py`. **NOT stale.** | Keep |

**Estimated removal: ~1,260 lines of dead code across 4 files.** `[CX]` Reduced from 5 files — recruiter_cover_letter is live.

### 5.2 Redundant Implementations

| Redundancy | Files | Recommendation |
|-----------|-------|----------------|
| Two CV assembly methods | `_assemble_cv_text()` (standard) + `_assemble_claude_cv_text()` (Claude CLI) in `orchestrator.py` | Merge into one. Claude CLI path is rarely used. |
| Sync + async LLM wrappers | `invoke()` (async) + `invoke_unified_sync()` (sync bridge) in `unified_llm.py` | Keep both — sync needed for legacy layers. But document that sync is deprecated. |
| Two rule_scorer copies | `src/common/rule_scorer.py` + `n8n/skills/scout-jobs/src/common/rule_scorer.py` | Single source of truth. Symlink or git submodule. |
| Two selector_profiles copies | `data/selector_profiles.yaml` + `n8n/skills/scout-jobs/data/selector_profiles.yaml` | Same — symlink or single location. |

### 5.3 Feature Flags for Dead Paths

| Flag | Default | Dead Path When Off |
|------|---------|-------------------|
| `ENABLE_CV_GEN_V2` | true | Legacy `generator.py` — remove the flag and the old code |
| `Config.USE_ANTHROPIC` | true | OpenAI-only path barely tested — remove or deprecate |
| `STAR_SELECTION_STRATEGY: "LLM_ONLY"` | "LLM_ONLY" | HYBRID and EMBEDDING_ONLY strategies — if unused, remove |

---

## 6. Recommended Model Assignment Per Stage

### 6.1 Optimal Configuration

```python
STEP_CONFIGS = {
    # --- Haiku tasks (cheap, structured, already low or safe to downgrade) ---
    "jd_extraction":         StepConfig(tier="low"),       # Haiku — structured JSON extraction
    "jd_structure_parsing":  StepConfig(tier="low"),       # Haiku — already configured low
    "ai_classification":     StepConfig(tier="low"),       # Haiku — already configured low
    "ats_validation":        StepConfig(tier="low"),       # Haiku — already configured low
    "grader":                StepConfig(tier="low"),       # Haiku — rubric scoring (already low)
    "quick_scorer":          StepConfig(tier="low"),       # Haiku — already configured low
    "classify_company_type": StepConfig(tier="low"),       # Haiku — already configured low
    "summarize_with_llm":    StepConfig(tier="low"),       # Haiku — already configured low
    "form_scraping":         StepConfig(tier="low"),       # Haiku — already configured low
    "title_sanitizer":       StepConfig(tier="low"),       # [CX] ← WAS missing (defaulted to middle). Trivial task.

    # --- Haiku tasks (downgraded from Sonnet — safe for mechanical tasks) ---
    "improver":              StepConfig(tier="low"),       # ← WAS middle. Targeted edits with constraints.
    "cv_tailorer":           StepConfig(tier="low"),       # ← WAS middle. Keyword repositioning.
    "star_selection":        StepConfig(tier="low"),       # ← WAS middle. Ranking/scoring task.
    "fit_analysis":          StepConfig(tier="low"),       # ← WAS middle. Scoring with rubric.

    # --- Sonnet tasks (quality-sensitive, keep at middle) ---
    "role_generator":        StepConfig(tier="middle"),    # [CX] Keep Sonnet — constraint-dense prompts need it
    "pain_point_extraction": StepConfig(tier="middle"),    # Nuanced JD reading
    "header_generator":      StepConfig(tier="middle"),    # Creative profile writing
    "ensemble_header":       StepConfig(tier="middle"),    # Multi-persona synthesis
    "cover_letter_generation": StepConfig(tier="middle"),  # Creative writing
    "outreach_generation":   StepConfig(tier="middle"),    # Personalized messaging
    "answer_generation":     StepConfig(tier="middle"),    # Application question answers
    "recruiter_cover_letter": StepConfig(tier="middle"),   # [CX] Live step, not stale

    # --- Sonnet + WebSearch (requires Claude CLI, no fallback) ---
    "research_company":      StepConfig(tier="middle", use_fallback=False),
    "research_role":         StepConfig(tier="middle", use_fallback=False),
    "research_people":       StepConfig(tier="middle", use_fallback=False),

    # --- Opus (only for persona synthesis in Gold tier) ---
    "persona_synthesis":     StepConfig(tier="high"),
}
```

### 6.2 Cost Impact

| Stage Group | Current Tier | Proposed Tier | Cost Reduction |
|------------|-------------|---------------|----------------|
| ~~Role generation (×6)~~ | ~~Sonnet~~ | ~~Haiku~~ | `[CX]` Keep Sonnet — too complex |
| Grading | Haiku | Haiku (unchanged) | — |
| Improvement | Sonnet | Haiku | **12x cheaper** |
| Tailoring | Sonnet | Haiku | **12x cheaper** |
| STAR selection | Sonnet | Haiku | **12x cheaper** |
| Fit analysis | Sonnet | Haiku | **12x cheaper** |
| Title sanitizer `[CX]` | Sonnet (default) | Haiku | **12x cheaper** |
| **Per-job savings** | ~$0.35/CV | ~$0.18/CV | **~49% reduction** |

---

## 7. Implementation Priority

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| **P0** | Downgrade improver + tailorer + star_selection + fit_analysis to Haiku | 4 lines in `llm_config.py` | ~49% cost reduction per CV |
| **P0** | Add `title_sanitizer` to STEP_CONFIGS as low tier | 1 line in `llm_config.py` | Stops defaulting to Sonnet for trivial task |
| **P1** | Add `provider` field to StepConfig for Codex routing | 30 min refactor | Enables Codex for grading/scoring |
| **P1** | Enable Anthropic prompt caching for role system prompt | 15 min | ~9.6K token savings per CV |
| **P2** | Remove `src/layer6/` legacy files (5 files, ~1,560 lines) | 30 min cleanup | Reduces confusion, simplifies tests |
| **P2** | Deduplicate rule_scorer.py (symlink or single source) | 15 min | Prevents sync drift |
| **P3** | Combine grading + improvement into single LLM call | 2h refactor | ~6K token savings |
| **P3** | Skip cover letter for Tier C/D jobs | 15 min config | ~5K tokens saved on 80% of jobs |
| **P3** | Batch 2-3 roles per LLM call | 3h refactor | ~3.2K token savings, fewer calls |

---

## 8. Architecture Decision: Configurable Provider per Step

### 8.1 Proposed Change to `unified_llm.py`

The `invoke()` method currently always tries Claude CLI first, then falls back to LangChain. To support Codex:

```python
async def invoke(self, prompt, system=None, ...):
    provider = self.config.provider  # NEW field
    
    if provider == "codex_cli":
        return await self._invoke_codex(prompt, system, ...)
    elif provider == "claude_cli":
        result = await self._invoke_cli(prompt, ...)
        if not result.success and self.config.use_fallback:
            return await self._invoke_langchain(prompt, ...)
        return result
    else:
        return await self._invoke_langchain(prompt, ...)
```

### 8.2 Codex CLI Integration

Codex CLI is already used by `cv_review_service.py`. The pattern:
```python
cmd = f"cat {prompt_file} | codex exec -m {model} --full-auto"
subprocess.run(cmd, shell=True, capture_output=True, timeout=...)
```

Extract this into a shared `_invoke_codex()` method in `unified_llm.py` or `claude_cli.py`.
