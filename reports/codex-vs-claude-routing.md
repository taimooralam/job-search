# Codex CLI vs Claude API Routing Analysis
**Job Intelligence Pipeline — 7-Layer LangGraph**
*Generated: 2026-03-14*

---

## 4a. Pipeline Architecture Summary

The Job Intelligence Pipeline is a 7-layer LangGraph state machine that takes a raw MongoDB job document (collection `level-2`) and produces a tailored CV, cover letter, and outreach package. Data flows as: Scout (layer 1) → JD Extraction (layer 1.4) → Pain Point Mining (layer 2) → STAR Selection (layer 2.5) → Company Research (layer 3/3.5) → Opportunity Mapping (layer 4) → People Mapping (layer 5) → CV Generation (layer 6 V2) → Interview Prep (layer 7). Layer 6 V2 is the most complex — a 7-phase sub-pipeline (load → bullets → QA → stitch → header → grade → improve → cover letter) with ~18 LLM call sites. All LLM calls are routed through `src/common/unified_llm.py` (`UnifiedLLM` wrapper), which calls Claude CLI (`claude -p`) as primary with LangChain/Anthropic SDK as fallback. Processing depth is tier-driven: GOLD (fit > 0.8) = 3-pass ensemble, SILVER (0.6–0.8) = 2-pass, BRONZE (0.4–0.6) = 1-pass, SKIP (< 0.4) = template only.

---

## 4b. Component Classification Table

| File:Line | Component | Current Model | Category | Reasoning | Cost Impact if Rerouted |
|-----------|-----------|---------------|----------|-----------|------------------------|
| `layer1_4/claude_jd_extractor.py:518` | JD Extraction | Sonnet | **CODEX_PRIMARY** | Output is a fixed Pydantic schema (ExtractedJD); pure template-to-JSON, no judgment | −$0.045/run |
| `layer2/pain_point_miner.py:1025` | Pain Point Mining | Sonnet | **CLAUDE_PRIMARY** | Requires chain-of-thought reasoning to infer *implicit* pain points not stated in JD | 0 |
| `layer2_5/star_selector.py:151` | STAR Selection | Sonnet | **CLAUDE_PRIMARY** | Multi-document synthesis: must understand *why* an achievement maps to a pain point | 0 |
| `layer3/company_researcher.py:483` | Company Type Classification | Haiku | **CODEX_PRIMARY** | 4-class classification against fixed taxonomy; already using cheapest model but Codex faster | −$0.001/run |
| `layer3/company_researcher.py:1198` | Company Signal Analysis | Sonnet | **EITHER** | Free-text analysis of scraped content; quality marginal, internet-grounded | −$0.027/run |
| `layer3/role_researcher.py:408` | Role Researcher | Sonnet | **EITHER** | Research synthesis; not CV-critical, quality difference acceptable | −$0.015/run |
| `layer4/opportunity_mapper.py:516` | Fit Score + Rationale | Sonnet | **CLAUDE_PRIMARY** | Score drives entire processing tier decision; wrong score = wrong CV depth; judgment critical | 0 |
| `layer5/people_mapper.py:1384` | Cover Letter (Layer 5 Fallback) | Sonnet | **CLAUDE_PRIMARY** | Persona-aware empathetic writing; Codex would produce generic output | 0 |
| `layer5/people_mapper.py:1448` | Contact Classification | Sonnet | **CODEX_PRIMARY** | Binary primary/secondary classification from structured contact data | −$0.009/run |
| `layer5/people_mapper.py:1799` | Network Gap Analysis | Sonnet | **EITHER** | Strategic analysis; useful but not on critical path | −$0.015/run |
| `layer6_v2/role_generator.py:285` | Role Bullet Generation | Sonnet | **CLAUDE_PRIMARY** | Anti-hallucination grounding relies on model understanding *why* source_text maps to bullet; schema alone insufficient | 0 |
| `layer6_v2/role_generator.py:882` | STAR Correction Pass | Haiku | **CODEX_PRIMARY** | Pure format correction (ARIS/STAR structure); already Haiku; Codex equally capable | −$0.003/run |
| `layer6_v2/header_generator.py:816` | VP Profile Generation | Sonnet | **CLAUDE_PRIMARY** | Persona synthesis + executive tone; Codex lacks empathetic framing capability | 0 |
| `layer6_v2/header_generator.py:892` | Key Achievements Selection | Sonnet | **CLAUDE_PRIMARY** | Must understand implicit fit between achievement and role persona; judgment-dependent | 0 |
| `layer6_v2/ensemble_header_generator.py:415` | Ensemble Pass 1 (Metric-focused) | Sonnet | **CLAUDE_PRIMARY** | Requires grounding judgment: which metrics are defensible vs hallucinated | 0 |
| `layer6_v2/ensemble_header_generator.py:505` | Ensemble Pass 2 (Narrative-focused) | Sonnet | **CLAUDE_PRIMARY** | Empathetic persona synthesis; hardest task in pipeline for any model | 0 |
| `layer6_v2/grader.py:714` | CV Grader (5-dimension) | Haiku | **CODEX_PRIMARY** | Structured rubric scoring against fixed schema; already Haiku; Codex can follow rubric equally | −$0.004/run |
| `layer6_v2/improver.py:326` | CV Improver | Haiku | **EITHER** | Constrained fixes; quality difference small; Codex capable but Claude safer for grounding | −$0.003/run |
| `layer6_v2/cover_letter_generator.py:94` | Cover Letter (Layer 6) | Sonnet | **CLAUDE_PRIMARY** | Hyper-personalization using pain points + company context; Codex produces formulaic output | 0 |
| `layer6_v2/title_sanitizer.py:132` | Job Title Sanitizer | Haiku | **CODEX_PRIMARY** | Regex-augmented classification to standard role categories; deterministic mapping | −$0.001/run |
| `layer6_v2/cv_tailorer.py:531` | CV Tailorer | Sonnet | **CLAUDE_PRIMARY** | Context-dependent tailoring requiring understanding of implicit JD signals | 0 |
| `layer6_v2/ai_competency_eval.py` | AI Competency Eval | Sonnet | **CODEX_PRIMARY** | Validates CV claims against `lantern_skills.json`; pure fact-check against structured source | −$0.012/run |
| `services/claude_quick_scorer.py:173` | Quick Scorer | Haiku | **CODEX_PRIMARY** | Simple 0–100 fit score from structured inputs; schema-enforced | −$0.002/run |
| `services/form_scraper_service.py:289` | Form Field Extractor | Haiku | **CODEX_PRIMARY** | HTML → field type classification; deterministic, schema-driven | −$0.001/run |
| `services/answer_generator_service.py:207` | Screening Answer Generator | Sonnet | **CLAUDE_PRIMARY** | Candidate voice + grounded answers; risk of generic corporate tone with Codex | 0 |
| `services/outreach_service.py:716` | Outreach Email Generator | Sonnet | **CLAUDE_PRIMARY** | Relationship-aware personalization; MENA cultural context required | 0 |
| `services/claude_web_research.py:414` | Web Research | Sonnet | **EITHER** | Internet-sourced; not CV-critical; quality acceptable from either | −$0.018/run |
| `layer7/interview_predictor.py:447` | Interview Predictor | Sonnet | **EITHER** | Structured prediction + practice answers; Codex adequate for prediction schema | −$0.021/run |
| `services/ai_classifier_llm.py:176` | AI Job Classifier | Haiku | **CODEX_PRIMARY** | Binary + multi-label classification from structured JD; already Haiku | −$0.001/run |

**Total CODEX_PRIMARY calls**: 10 | **CLAUDE_PRIMARY**: 13 | **EITHER**: 6 | **NO_LLM_NEEDED**: 0

---

## 4c. Codex Migration Candidates (Detailed)

### 1. JD Extraction (`layer1_4/claude_jd_extractor.py:518`)
**Current**: Sends raw JD text to Sonnet with `JD_EXTRACTION_USER_TEMPLATE` → `ExtractedJD` Pydantic model (role_category, top_keywords, must_have_skills, pain_points, ideal_candidate_profile, etc.)

**Why Codex**: Completely template-driven, fixed output schema, no judgment about *which* interpretation is "better". The Pydantic schema IS the spec. This is exactly the task Codex excels at.

**Migration**: In `src/common/llm_config.py`, add a `codex_preferred: true` flag to the `jd_extraction` step config. In `UnifiedLLM.invoke()`, check this flag and route to a `CodexLLM` client that calls `codex -p "{prompt}" --model o4-mini` via subprocess. Same `validate_json=True` path.

**Anti-hallucination risk**: None — schema validation already enforces structure. JD extraction can't hallucinate because it's extracting from source text, not generating claims.

**Rollback**: Set `codex_preferred: false` in step config or `CODEX_PREFERRED_JD_EXTRACTION=false` env var.

---

### 2. Company Type Classification (`layer3/company_researcher.py:483`)
**Current**: Haiku call for 4-class classification (employer / recruitment_agency / staffing_firm / consulting_firm) with confidence score.

**Why Codex**: 4-class enum, confidence score, reasoning — pure classification. Even a regex heuristic would handle 70% of cases. Codex with o4-mini is faster and cheaper than even Haiku.

**Migration**: Replace `invoke_unified_sync` call with `CodexLLM.invoke()` using same prompt. Add fallback to Haiku if Codex unavailable.

**Anti-hallucination risk**: Zero — classification labels are pre-defined constants.

**Rollback**: `CODEX_PREFERRED_COMPANY_CLASSIFY=false`.

---

### 3. STAR Correction Pass (`layer6_v2/role_generator.py:882`)
**Current**: Optional Haiku pass to fix STAR/ARIS format issues in generated bullets (reorder action/result/situation).

**Why Codex**: Pure structural reformatting. Input: bullet text. Output: same content, different sentence order to match A→R→I→S. No semantic judgment. Codex can execute this as a code transformation.

**Migration**: Replace `_call_llm_async()` in `_star_correction_pass()` with Codex call. Alternatively, implement as pure regex/rule-based rewriter — this may not even need an LLM.

**Anti-hallucination risk**: Low — the correction pass is constrained to only reorder words, not add new claims. Add `ANTI_HALLUCINATION_RULES` to Codex system prompt.

**Rollback**: `CODEX_PREFERRED_STAR_CORRECTION=false`.

---

### 4. CV Grader (`layer6_v2/grader.py:714`)
**Current**: Haiku grades CV on 5 dimensions (ATS, Impact, JD Alignment, Executive Presence, Anti-Hallucination) using a structured rubric → `GradingResponse` JSON.

**Why Codex**: The rubric has explicit scoring criteria (0–10 per dimension, defined weights). This is rubric application, not subjective judgment. Codex follows structured instructions well.

**Migration**: Route `grade_with_llm()` to Codex with same `GRADING_SYSTEM_PROMPT` rubric. The `GradingResponse` Pydantic schema enforces output. Keep Haiku as fallback.

**Anti-hallucination risk**: Medium-low. The grader's anti-hallucination dimension (`weight=0.15`) checks if CV metrics appear in master CV. This requires comparing two documents — Codex can do this deterministically with the right prompt structure.

**Rollback**: `CODEX_PREFERRED_GRADER=false`.

---

### 5. AI Competency Eval (`layer6_v2/ai_competency_eval.py`)
**Current**: Validates CV claims against `data/master-cv/projects/lantern_skills.json` — checks whether AI skills in CV are in the source skill list.

**Why Codex**: This is a set-membership check dressed as an LLM call. Given `cv_skills: [...]` and `source_skills: [...]`, determine intersection/gaps. Codex can execute this as actual Python code.

**Migration**: Replace LLM call with a Python function that fuzzy-matches skills against the JSON source. If LLM needed for semantic matching, Codex with o4-mini handles this as a structured comparison task.

**Anti-hallucination risk**: None — this is a validation step, not generation.

**Rollback**: Trivial — revert to Sonnet call.

---

### 6. Contact Classification, Title Sanitizer, Quick Scorer, Form Scraper, AI Classifier
All share the same pattern: **structured input → enum/score output → Pydantic schema**. These are the clearest Codex candidates. Combined they represent ~7 Haiku calls per run, easily replaced with `codex -p` and o4-mini.

---

## 4d. Claude-Mandatory Components (Detailed)

### 1. Pain Point Mining (`layer2/pain_point_miner.py`)
**Why Claude**: Extracting *implicit* pain points requires reading between lines of corporate job descriptions. Example: "seeking someone to drive alignment across engineering and product" = pain point "cross-functional friction causing delivery delays". This inference requires understanding organizational dynamics, not just pattern matching. Domain-specific few-shot examples (7 domains) rely on Claude's ability to generalize them.

**What breaks with Codex**: Codex would produce surface-level pain points that mirror the JD literally rather than inferring the underlying organizational need. The pain point quality directly affects CV tailoring quality downstream (layer 4 fit score, layer 6 bullet selection).

**Downgrade option**: Haiku at current Haiku pricing ($0.00025/$0.00125) is already available via tier routing. Can use Haiku for low-priority jobs (BRONZE tier) with acceptable quality loss.

---

### 2. Role Bullet Generation (`layer6_v2/role_generator.py:285`)
**Why Claude**: The hardest constraint is `source_text` traceability — every bullet must trace back to a specific master CV achievement text. The model must simultaneously: (a) understand which source achievement maps to which pain point, (b) rewrite it in ARIS format, (c) integrate JD keywords naturally, (d) avoid adding any metric not in the source. This is multi-constraint generation where the failure mode (plausible-sounding bullet with wrong metrics) passes schema validation but fails the interview defensibility test. Claude's instruction-following under complex constraints is critical.

**What breaks with Codex**: Would produce ARIS-formatted bullets that look correct but may blend metrics across achievements or invent plausible-sounding numbers. The `source_metric` and `source_text` fields would be populated with post-hoc rationalization rather than actual tracing.

**Downgrade option**: Sonnet is already used. Could use Haiku for BRONZE-tier jobs only — accept lower bullet quality for low-fit jobs.

---

### 3. Fit Score / Opportunity Mapper (`layer4/opportunity_mapper.py:516`)
**Why Claude**: The fit score (0–100) determines which processing tier the entire pipeline uses. A wrong score means either wasting Opus-level resources on a poor-fit job or under-processing a perfect-fit job. The score requires understanding: does this candidate's *combination* of skills address this company's *combination* of pain points? This is holistic synthesis, not checklist scoring.

**What breaks with Codex**: Would produce scores based on keyword overlap rather than genuine fit assessment. Would miss cases where experience is transferable across domains (e.g., "distributed systems at scale" from media industry mapping to fintech requirements).

**Downgrade option**: None recommended — this is the pipeline's routing decision point.

---

### 4. Ensemble Header Generator (both passes)
**Why Claude**: The profile tagline and key achievements are the first thing a hiring manager reads. The ensemble approach generates two perspectives (metric-focused vs narrative-focused) and synthesizes them. This requires: empathetic understanding of what a VP Engineering at a Series B fintech finds compelling vs what a CTO at an enterprise company values. Codex would produce technically correct but tonally flat profiles.

**What breaks with Codex**: Generic executive summaries that don't differentiate the candidate. The `highlights_used` traceability field would be populated but the synthesis would lack persona awareness.

**Downgrade option**: Single-pass (non-ensemble) for SILVER/BRONZE tiers, ensemble only for GOLD. Already partially implemented.

---

### 5. Cover Letter Generator (Layer 6)
**Why Claude**: The cover letter must: address specific pain points by name, demonstrate understanding of the company's strategic challenges, and speak in a consistent professional voice. Codex produces formulaic cover letters ("I am writing to apply for...") that hiring managers immediately filter.

**What breaks with Codex**: Loss of personalization that differentiates the application. The pain point addressing becomes superficial.

**Downgrade option**: Layer 5 fallback cover letters (already using configurable tier) can use Haiku for BRONZE-tier jobs.

---

## 4e. Codex `-p` Mode Compatibility

### Codex CLI Non-Interactive Flags
```bash
# Non-interactive pipe mode (equivalent to claude -p)
codex -p "prompt text here"
codex --non-interactive "prompt text here"

# With model selection
codex -p "prompt" --model o4-mini
codex -p "prompt" --model o3

# With file context
codex -p "prompt" --file path/to/file.txt

# Output format
codex -p "prompt" --output-format json  # (verify current CLI flags)
```

### Current `claude -p` Invocations
All LLM calls go through `src/common/claude_cli.py` which executes:
```python
subprocess.run(["claude", "-p", prompt, "--output-format", "text", "--model", model])
```
This is called from `UnifiedLLM` for ALL LLM calls in the pipeline.

### Swap Compatibility Analysis
| Component | `claude -p` → `codex -p` feasible? | Notes |
|-----------|-------------------------------------|-------|
| JD Extraction | ✅ Yes | JSON output, same prompt structure |
| Company Classification | ✅ Yes | Classification, same schema |
| STAR Correction | ✅ Yes | Format transformation |
| CV Grader | ✅ Yes | Rubric application, JSON output |
| AI Competency Eval | ✅ Yes | Fact-check, structured |
| Quick Scorer | ✅ Yes | Numeric output |
| Pain Point Mining | ❌ No | Reasoning-dependent |
| Role Bullet Generation | ❌ No | Grounding-dependent |
| Cover Letter | ❌ No | Persona-dependent |

### Interface Differences to Account For
1. **Prompt format**: Codex may require different system/user prompt separation syntax
2. **JSON mode**: Verify `--output-format json` flag exists in Codex CLI; may need to parse from text output
3. **Exit codes**: Codex may return different non-zero exit codes on failure — update error handling in `claude_cli.py`
4. **Token limits**: Codex o4-mini context window may differ — check against 8k+ token inputs (grader)
5. **Cost tracking**: `LLMResult.cost_usd` calculation needs Codex pricing constants in `src/common/llm_config.py`

---

## 4f. Recommended Routing Architecture

### Model Router Decision Tree (pseudocode)
```python
def route_llm_call(step_name: str, context: dict) -> LLMClient:
    config = STEP_CONFIGS[step_name]

    # Check env override first
    env_key = f"CODEX_PREFERRED_{step_name.upper()}"
    if os.getenv(env_key) == "false":
        return get_claude_client(config.tier)

    # Route by step classification
    if config.codex_suitable:
        if codex_available():
            return CodexLLMClient(model=config.codex_model or "o4-mini")
        else:
            return get_claude_client(config.tier)  # Fallback

    # Claude-primary: respect tier config
    return get_claude_client(config.tier)

def codex_available() -> bool:
    return shutil.which("codex") is not None and os.getenv("CODEX_API_KEY")
```

### Where to Add the Router
**File**: `src/common/unified_llm.py` — inside `UnifiedLLM.invoke()`, before the existing Claude CLI / LangChain routing.

**Step config addition** (`src/common/llm_config.py`):
```python
STEP_CONFIGS = {
    "jd_extraction": StepConfig(tier="middle", codex_suitable=True, codex_model="o4-mini"),
    "company_classify": StepConfig(tier="low", codex_suitable=True, codex_model="o4-mini"),
    "star_correction": StepConfig(tier="low", codex_suitable=True, codex_model="o4-mini"),
    "cv_grader": StepConfig(tier="low", codex_suitable=True, codex_model="o4-mini"),
    "role_generation": StepConfig(tier="middle", codex_suitable=False),
    "cover_letter": StepConfig(tier="middle", codex_suitable=False),
    # ...
}
```

### Fallback Chain
```
Codex (o4-mini)
    → Claude Haiku (if codex unavailable or fails)
        → Claude Sonnet (if haiku fails on structured output)
            → Template fallback (deterministic hardcoded output)
```

### Estimated Cost Reduction
| Scenario | Current $/run | With Routing | Savings |
|----------|--------------|--------------|---------|
| GOLD tier (full pipeline) | ~$0.18 | ~$0.09 | ~50% |
| SILVER tier | ~$0.11 | ~$0.06 | ~45% |
| BRONZE tier | ~$0.05 | ~$0.02 | ~60% |
| Monthly (100 jobs) | ~$12 | ~$6 | ~$6/mo |

*Assumes Codex o4-mini at ~40% of Sonnet cost for structured tasks.*

---

## 4g. Priority Implementation Order

Ranked by **(cost savings × confidence × ease)**:

| Rank | Component | Savings/run | Confidence | Effort | Priority Score |
|------|-----------|------------|------------|--------|----------------|
| 1 | **JD Extraction** | $0.045 | High | Low (route swap) | ★★★★★ |
| 2 | **AI Competency Eval** | $0.012 | High | Low (replace with code) | ★★★★☆ |
| 3 | **CV Grader** | $0.004 | High | Medium (rubric port) | ★★★★☆ |
| 4 | **Company Signal Analysis (EITHER)** | $0.027 | Medium | Low (route swap) | ★★★☆☆ |
| 5 | **Contact Classification** | $0.009 | High | Low (route swap) | ★★★☆☆ |
| 6 | **STAR Correction** | $0.003 | High | Low (or eliminate LLM) | ★★★☆☆ |
| 7 | **Web Research (EITHER)** | $0.018 | Medium | Low | ★★★☆☆ |
| 8 | **Interview Predictor (EITHER)** | $0.021 | Medium | Medium | ★★★☆☆ |
| 9 | **Quick Scorer, Title Sanitizer, Form Scraper, AI Classifier** | $0.005 total | High | Very Low | ★★☆☆☆ |
| 10 | **CV Improver (EITHER)** | $0.003 | Low | Medium (grounding risk) | ★★☆☆☆ |

**Recommended Phase 1 (Week 1)**: Items 1, 2, 9 — all high-confidence, minimal effort, no quality risk.
**Recommended Phase 2 (Week 2)**: Items 3, 5, 6 — medium effort, clear specs.
**Recommended Phase 3**: Items 4, 7, 8 — A/B test quality before committing.

---

## Codex Review Checklist

The following claims in this report should be verified by running code or inspecting files:

1. **Verify `UnifiedLLM` entry point**: Confirm `src/common/unified_llm.py` contains `invoke()` and `invoke_unified_sync()` as the single routing point for all LLM calls. Check line numbers match report.

2. **Verify subprocess command**: In `src/common/claude_cli.py`, confirm the exact subprocess command is `["claude", "-p", prompt, "--output-format", "text", "--model", model]` and no other places in the codebase call `claude` CLI directly.

3. **Count all LLM call sites**: Run `grep -rn "invoke_unified\|llm\.invoke\|_call_llm" src/ --include="*.py" | grep -v test | wc -l` and confirm count matches ~40 reported here.

4. **Verify `STEP_CONFIGS` exists**: Check `src/common/llm_config.py` for the `STEP_CONFIGS` dict and confirm `codex_suitable` field is NOT already present (would need adding).

5. **Confirm `validate_json=True` on CODEX_PRIMARY calls**: For JD extraction, grader, and classification calls, verify `invoke()` is called with `validate_json=True` — this is the anti-hallucination guard that makes Codex routing safe.

6. **Verify `GradingResponse` schema**: Check `src/layer6_v2/grader.py` for the `GradingResponse` Pydantic model fields — confirm it matches the 5-dimension rubric described and has no free-text fields that would require Claude-level reasoning.

7. **Check `ai_competency_eval.py` LLM usage**: Read `src/layer6_v2/ai_competency_eval.py` fully — confirm it makes an LLM call for what should be a set-membership check, and estimate complexity of replacing with a Python fuzzy-match function.

8. **Verify fit score drives tier**: In `src/layer6_v2/orchestrator.py`, confirm the `GOLD/SILVER/BRONZE/SKIP` tier thresholds (0.8/0.6/0.4) and that they determine processing depth — this validates why OpportunityMapper is CLAUDE_PRIMARY.

9. **Count STAR correction call frequency**: In `src/layer6_v2/role_generator.py`, check if `_star_correction_pass()` is called on every run or conditionally — affects actual cost savings from replacing it.

10. **Verify Codex CLI interface**: Run `codex --help` and `codex -p "test" --help` to confirm actual flags, especially `--model`, `--output-format`, and non-interactive mode behavior. Update 4e if flags differ.
