# CV Quality Fixes — Implementation Plan

**Date:** 2026-04-12
**Source:** CV Reviewer 24h Diagnostic (127 reviews, Part 10 of focus plan)
**Goal:** Raise GOOD_MATCH from 5% to 20-30%, first-impression score from 4.2 to 6.5+

---

## Summary of Remaining Work

| ID | Change | Type | File(s) | Risk |
|----|--------|------|---------|------|
| A1 | Headline grounding constraint | Prompt | header_generation.py | Low |
| A2 | Tagline evidence-first pattern | Prompt | header_generation.py | Low |
| A3 | Competencies 6-8 → 10-12 | Prompt | header_generation.py, cv_review_service.py | Low-Med |
| A4 | Commander-4 claim guard | Prompt | role_generation.py, header_generator.py, ensemble_header_generator.py | Low |
| B1 | Merge Lantern skills into commander4_skills.json | Data | commander4_skills.json | Low |
| B2 | Project files in reviewer source context | Code | cv_review_service.py | Low |
| B3 | Pain point rebalancing | Code | variant_selector.py, role_generator.py | Medium |
| C1 | Rule scorer ai_leadership tweaks | Config | rule_scorer.py (×2) | Low |
| C2 | Selector profile updates | Config | selector_profiles.yaml | Low |

---

## Batch 1: Prompt & Config Changes (all parallel, no dependencies)

### A1. Headline Grounding Constraint

**File:** `src/layer6_v2/prompts/header_generation.py`
**Problem:** 94% of reviews flag headline as over-positioned. Generator uses "AI Engineer · AI Architect" dual-title.

**Change:** Insert GROUNDING RULES after the HEADLINE format spec (line 33) and before the TAGLINE section (line 35). Also add the same rules in the 3 persona prompts that repeat the headline spec (METRIC_PERSONA ~line 472, NARRATIVE_PERSONA ~line 528, KEYWORD_PERSONA ~line 590).

```
   HEADLINE GROUNDING RULES:
   - Use ONE title from the JD — NEVER combine two senior titles (e.g., "AI Engineer · AI Architect")
   - The candidate's verified identity is "Engineering Leader / Software Architect" with AI platform experience
   - If the JD title implies a specialization the candidate does not have (e.g., "ML Researcher"),
     use the closest accurate title from the candidate's background
   - The credibility anchor must reflect actual years from experience
```

**Test:** `pytest tests/unit/test_layer6_v2_header_generator.py tests/unit/test_layer6_v2_ensemble_header.py tests/layer6_v2/test_header_generator_persona.py`

### A2. Tagline Evidence-First Pattern

**File:** `src/layer6_v2/prompts/header_generation.py`
**Problem:** 80% of taglines fail the "proof test" — claim AI identity with unverified proof.

**Change:** In `VALUE_PROPOSITION_SYSTEM_PROMPT_V2` (line ~1019), after constraint 7 "Never invent numbers" (line 1033) and before `=== ROLE-LEVEL TEMPLATES ===` (line 1035), insert:

```
=== EVIDENCE-FIRST ORDERING (Critical for Authenticity) ===

Lead with the candidate's VERIFIED identity, then extend to JD-relevant capabilities.

PATTERN: "[Verified identity] + [JD-relevant extension backed by evidence]"

BAD (leads with unverified AI-first identity):
- "Generative AI architect delivering enterprise LLM platforms with cutting-edge RAG pipelines"

GOOD (leads with verified identity, extends to AI with evidence):
- "Production platform architect applying 11 years of distributed systems rigor to enterprise LLM reliability"
- "Engineering leader who built Commander-4 AI platform (2,000 users, 42 plugins) on a foundation of 11+ years scaling distributed teams"

RULE: If the candidate's primary career is X and they have Y as a recent extension,
the tagline must lead with X and extend to Y — never the reverse.
```

**Test:** `pytest tests/unit/test_header_generation_v2.py`

### A3. Expand Core Competencies 6-8 → 10-12

**File:** `src/layer6_v2/prompts/header_generation.py`
**Problem:** 88% of reviews flag competencies as "too thin for ATS survival."

**Change:** Replace all 13 occurrences of "6-8" with "10-12" in header_generation.py. Exact lines:

| Line | Old | New |
|------|-----|-----|
| 67 | `(6-8 keywords)` | `(10-12 keywords)` |
| 192 | `"...6-8 total"` | `"...10-12 total"` |
| 336 | `6-8 ATS keywords` | `10-12 ATS keywords` |
| 492 | `6-8 ATS keywords` | `10-12 ATS keywords` |
| 508 | `"...6-8 total"` | `"...10-12 total"` |
| 549 | `6-8 ATS keywords` | `10-12 ATS keywords` |
| 570 | `"...6-8 total"` | `"...10-12 total"` |
| 611 | `6-8 ATS keywords` | `10-12 ATS keywords` |
| 634 | `"...6-8 total"` | `"...10-12 total"` |
| 674 | `6-8 keywords` | `10-12 keywords` |
| 685 | `6-8 core competencies` | `10-12 core competencies` |
| 694 | `"...6-8 total"` | `"...10-12 total"` |
| 840 | `6-8 ATS-friendly` | `10-12 ATS-friendly` |
| 902 | `(6-8 total)` | `(10-12 total)` |

Also add at line 67 after the count change:
```
   - MUST include at least 3 JD-specific terms verified in the experience section
   - Balance: ~5 technical skills + ~3 leadership/delivery + ~3 JD-specific terms
```

Also update reviewer prompt for consistency:
**File:** `src/services/cv_review_service.py` — change any reference to "6-8" competencies to "10-12".

**Note:** `CoreCompetencyGeneratorV2` in `skills_taxonomy.py` has `MAX_SKILLS_PER_SECTION = 10` — this is per-section, not total. No change needed there.

**Test:** `pytest tests/unit/test_layer6_v2_header_generator.py tests/unit/test_layer6_v2_ensemble_header.py`

### A4. Commander-4 Claim Guard

**Files:**
- `src/layer6_v2/prompts/role_generation.py` — main guard
- `src/layer6_v2/header_generator.py` — value prop AI enrichment (~line 801)
- `src/layer6_v2/ensemble_header_generator.py` — same (~line 410)

**Problem:** "42 plugins" inflated to "42 agents", Commander-4 framed as standalone job.

**Change in role_generation.py:** After `ANTI_HALLUCINATION_RULES` (line 45), before `=== CRITICAL: NO MARKDOWN FORMATTING` (line 47), insert:

```
=== COMMANDER-4 (JOYIA) CLAIM RULES ===

When writing bullets for the Seven.One role referencing Commander-4:
1. "42 plugins" stays "42 plugins" — NEVER "42 agents" or "42 AI agents"
2. "2,000 users" stays "2,000 users" — NEVER "2,000+ enterprise users"
3. Platform name: always "Commander-4 (Joyia)" as-is
4. Commander-4 is a PROJECT within Seven.One, NOT a standalone job or company
5. Valid: hybrid retrieval, document ingestion, structured outputs, semantic caching,
   42 plugins, 2,000 users, LLM-as-judge reranking, MCP tools, guardrail profiles
6. Invalid: "42 agents", "enterprise-wide AI transformation", "company-wide AI adoption"
```

**Change in header_generator.py (~line 801):** After the AI enrichment section, append:
```python
ai_section += "\nNOTE: '42 plugins' NOT '42 agents'. '2,000 users' NOT '2,000+ enterprise users'. Commander-4 is a PROJECT within Seven.One, not a standalone job.\n"
```

**Same in ensemble_header_generator.py (~line 410).**

**Test:** `pytest tests/unit/test_layer6_v2_orchestrator.py`

### B1. Merge Lantern Skills into commander4_skills.json

**File:** `data/master-cv/projects/commander4_skills.json`
**Problem:** LangChain (21× missing), LangGraph (7×), FastAPI (5×), Kubernetes (14×) are verified in Lantern but not in the whitelist.

**Change:** Add Lantern's verified skills and competencies that aren't already in commander4_skills.json:

From `lantern_skills.json` `verified_skills` — add to `verified_skills`:
- `FastAPI`, `Pydantic V2`, `Qdrant`, `Docker Compose`, `Prometheus`, `Grafana`, `GitHub Actions`, `pytest`, `ruff`, `mypy`, `pre-commit`, `httpx`, `Traefik`, `Langfuse`

From `lantern_skills.json` `verified_competencies` — add to `verified_competencies`:
- `LLM Gateway Design`, `Provider Fallback Chain`, `Circuit Breaker Pattern`, `Multi-Provider Routing`, `Langfuse Tracing`, `LangGraph`, `LangChain`, `Agent Frameworks`, `API Gateway Design`, `Model Routing`

From `lantern_skills.json` `post_checklist_competencies` — add as new `post_checklist_competencies` key:
- `Golden-Set Testing`, `Eval Harness Design`, `Faithfulness Evaluation`, `Regression Detection`, `Streaming SSE`, `Rate Limiting`, `SLO/SLI Design`, `Incident Runbooks`, `Cost Optimization`, `Prompt Engineering`, `Document Ingestion Pipeline`, `Hybrid Search`

From `lantern_skills.json` `post_checklist_skills` — add as new `post_checklist_skills` key:
- `React`, `Vite`, `Tailwind CSS`, `Vercel`

**No code changes needed** — the existing `_load_ai_project_skills()` in orchestrator.py already reads `verified_skills`, `verified_competencies`, and iterates all list-type values. Verify this handles the new keys.

**Test:** `python -c "from src.layer6_v2.orchestrator import _load_ai_project_skills; skills = _load_ai_project_skills(); print(len(skills)); assert 'LangChain' in skills; assert 'FastAPI' in skills"`

### C1. Rule Scorer ai_leadership Tweaks

**Files:** `n8n/skills/scout-jobs/src/common/rule_scorer.py` AND `src/common/rule_scorer.py` (must stay in sync)

**Changes:**
1. Line ~173: `"excludeIfContains": []` → `"excludeIfContains": ["sales", "pre-sales", "presales", "marketing", "customer success"]`
2. Line ~576: `"architecture": {"weight": 1.5, "max": 15}` → `"architecture": {"weight": 2.5, "max": 25}`

**Test:** `pytest tests/unit/test_rule_scorer.py`

### C2. Selector Profile Updates

**File:** `n8n/skills/scout-jobs/data/selector_profiles.yaml`

**Changes:**
1. `uae_ksa_leadership` rank_boosts: add `staff_architect: 10`
2. `global_remote` rank_boosts: add `staff_architect: 10`, quota 2→3
3. `eea_remote` rank_boosts: add `staff_architect: 8`
4. `eea_staff_architect` quota: 2→3

---

## Batch 2: Code Changes (after Batch 1)

### B2. Project Files in Reviewer Source Context

**File:** `src/services/cv_review_service.py`
**Problem:** Reviewer flags Commander-4 claims as "not found in master CV" because project files aren't in source context.

**Change:** After the master CV text section (~line 293), append project file content:

```python
# Append AI project files for complete source-of-truth context
sections.append("\n## AI PROJECT FILES (Additional Source of Truth)")
import os
project_base = os.path.join(os.path.dirname(__file__), "..", "data", "master-cv", "projects")
for project_file in ("commander4.md", "lantern.md"):
    project_path = os.path.join(project_base, project_file)
    try:
        with open(project_path, "r", encoding="utf-8") as f:
            project_text = f.read()
        sections.append(f"\n### {project_file}")
        sections.append(project_text[:3000])
    except Exception:
        pass
```

**Token budget:** commander4.md is ~1200 chars, lantern.md is ~700 chars. Adds ~2000 chars total.

**Test:** Run a review for an AI job, verify Commander-4 claims (42 plugins, 2000 users) are NOT flagged.

---

## Batch 3: Pain Point Rebalancing (after Batch 2)

### B3. Pain Point Rebalancing

**File:** `src/layer6_v2/variant_selector.py`
**Problem:** Mean pain point coverage is 37%, max 73%. No job reaches 75%.

**Change:** Add `_rebalance_for_pain_points()` method to `VariantSelector`. Called after initial selection in `select_variants()`, before returning `SelectionResult`.

**Algorithm:**
1. Identify which pain points are covered by selected variants (via `matched_pain_point`)
2. If coverage < 60%, find unselected variants that address uncovered pain points
3. Swap in the best unselected variant for the weakest selected bullet, if:
   - The weakest bullet doesn't uniquely cover another pain point
   - The candidate's score is at least 70% of the weakest's score
4. Repeat until coverage >= 60% or no more swaps available

**Also update `role_generator.py` line 574:** Propagate `matched_pain_point` from `VariantScore`:
```python
pain_point_addressed=selected.score.matched_pain_point if selected.score.matched_pain_point else None,
```

**Test:** Write unit tests for the rebalancing method:
- 5 pain points, 3 covered → verify swap happens
- All covered → no-op
- Empty pain points → no-op
- Sole-coverage protection → bullet uniquely covering a pain point never swapped out

---

## Execution Order

```
Batch 1 (parallel — prompt/config/data):
  A1 + A2 + A3 + A4 + B1 + C1 + C2

Batch 2 (after Batch 1 — code):
  B2

Batch 3 (after Batch 2 — complex logic):
  B3
```

---

## Verification After All Changes

1. **Unit tests:** `pytest tests/unit/ -n 4 --ignore='tests/unit/test_integration*' --ignore='tests/unit/test_bulk*' -q`
2. **Generate 3 AI Architect CVs + 3 Head of AI CVs** → verify:
   - Headline uses JD title, no dual-title
   - Tagline leads with verified identity
   - 10-12 competencies including LangChain/LangGraph if JD mentions them
   - Commander-4 claims use exact figures
   - Pain points covered at 55%+
3. **Review 3 generated CVs** via CV reviewer → compare scores against 24h diagnostic baseline
4. **Re-score 10 WEAK_MATCH jobs** from diagnostic → verify lower scores after scout filter changes
