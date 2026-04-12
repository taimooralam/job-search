# CV Pipeline Audit: Plan vs Implementation vs Actual Output

**Date:** 2026-04-12  
**Source Plan:** `reports/agentic-ai-architect-focus-plan-2026-04-11.md` (Section 10.7, 7 Actions)  
**Methodology:** Code trace through 13 pipeline layers + MongoDB verification of 3 recent AI job CVs

---

## 1. Executive Summary

| Action | Status | Impact |
|--------|--------|--------|
| **Action 1:** Headline Grounding | IMPLEMENTED BUT DEFEATED | Standard path re-creates dual-title at assembly |
| **Action 2:** Commander-4 Claim Guard | WORKING (role bullets) / PARTIALLY DEFEATED (header) | Header generator still embellishes claims |
| **Action 3:** Core Competencies 10-12 | IMPLEMENTED BUT UNDERSIZED | Section 4 empty → only 3 sections render → 6-9 keywords not 10-12 |
| **Action 4:** Surface Verified AI Skills | NOT WORKING | `lantern_skills.json` never loaded; soft skills destroyed by grounding filter |
| **Action 5:** Scout Negative Scoring | FULLY WORKING | Exact caps match plan |
| **Action 6:** Pain Point Rebalancing | FULLY WORKING | 60% coverage target implemented |
| **Action 7:** Tagline Evidence-First | PARTIALLY WORKING | Templates exist, no enforcement — 2/3 CVs still AI-first |

**Bottom line: 2 of 7 actions are fully working end-to-end (Actions 5, 6). 3 are partially working (Actions 1, 2, 7). 2 are broken or not working (Actions 3 effectively, Action 4).**

---

## 2. Per-Action Audit

### Action 1: Add Headline Grounding Constraint

#### A. Plan vs Code

**Plan:** Add HEADLINE GROUNDING RULES to `PROFILE_SYSTEM_PROMPT` preventing dual-title headlines like "AI Engineer · AI Architect".

**Implementation found:**
- `src/layer6_v2/prompts/header_generation.py:35-41` — HEADLINE GROUNDING RULES present in prompt. States: "Use ONE title from the JD — NEVER combine two senior titles."
- `src/layer6_v2/headline_resolver.py:82-102` — `_clean_title()` strips dual-title patterns using 6 separator patterns (" · ", " / ", " | ", " - ", " – ", " — ") and rejects 14 unearned specialization patterns.
- `src/layer6_v2/headline_resolver.py:77-79` — `clean_jd_title()` wrapper called by orchestrator.

**Both assembly paths call `clean_jd_title()`:**
- `orchestrator.py:1674` — `_assemble_cv_text()` ✅
- `orchestrator.py:1326` — `_assemble_claude_cv_text()` ✅

#### B. End-to-End Trace — WHERE IT BREAKS

**Override point:** `orchestrator.py:1676`:
```python
lines.append(f"### {bounded_title} · {generic_title}")
```

This **always** appends `· {generic_title}` (e.g., "AI Architect") to the cleaned JD title, reconstructing the exact dual-title pattern the resolver just stripped. Even when `bounded_title` already contains "AI Architect", it produces: `### AI Architect · AI Architect`.

The Claude CLI path at `orchestrator.py:1329-1332` has a smarter redundancy check:
```python
if generic_title.lower() not in bounded_title.lower():
    lines.append(f"### {bounded_title} · {generic_title}")
else:
    lines.append(f"### {bounded_title}")
```

But the standard path (used for ALL non-CLI jobs) lacks this check.

#### C. MongoDB Evidence

All 3 recent AI CVs show the reconstructed dual-title:
- EPAM: `### Enterprise Artificial Intelligence Architect · AI Architect`
- Baldur: `### AI Automation Specialist · AI Architect`
- Autodesk: `### Distinguished AI Architect, AEC Construction · AI Architect`

The Autodesk CV is the worst case — "AI Architect" appears twice in the H3 line.

#### D. Status: IMPLEMENTED BUT DEFEATED

**Code locations:** `header_generation.py:35-41`, `headline_resolver.py:77-102`  
**Override point:** `orchestrator.py:1676` — unconditional dual-title construction  
**Required fix:** Add the same redundancy check from `_assemble_claude_cv_text()` to `_assemble_cv_text()`:
```python
# orchestrator.py:1676 — REPLACE:
lines.append(f"### {bounded_title} · {generic_title}")
# WITH:
if generic_title.lower() not in bounded_title.lower():
    lines.append(f"### {bounded_title} · {generic_title}")
else:
    lines.append(f"### {bounded_title}")
```

---

### Action 2: Stop Commander-4 Claim Embellishment

#### A. Plan vs Code

**Plan:** Add COMMANDER-4 CLAIM RULES to role generation prompts; verify cv_review_service includes project files.

**Implementation found:**
- `src/layer6_v2/prompts/role_generation.py:54-62` — COMMANDER-4 CLAIM RULES present:
  - `"42 plugins" stays "42 plugins" — NEVER "42 agents"`
  - `"2,000 users" stays "2,000 users" — NEVER "2,000+ enterprise users"`
  - Platform name: always "Commander-4 (Joyia)"
- `src/services/cv_review_service.py:407-415` — loads both `commander4.md` and `lantern.md` into review context ✅

#### B. End-to-End Trace — PARTIAL DEFEAT

The claim guard is in **role generation prompts only**. The header generator (Phase 5) generates the PROFESSIONAL SUMMARY tagline and key achievements independently, and its prompts do NOT contain the Commander-4 claim rules.

**Override point:** `header_generation.py:1058` mentions "Commander-4 AI platform (2,000 users, 42 plugins)" in a tagline template example but does not enforce the claim rules.

#### C. MongoDB Evidence

- Commander-4 section (all 3 CVs): Correctly says "42 plugins" ✅ — role generation guard works
- PROFESSIONAL SUMMARY tagline (CV3 Autodesk): `"42 multi-agent workflow plugins"` — the word "multi-agent" is NOT in the source text. Header generator embellishes.
- Key achievements (CV1 EPAM): `"42 plugins with Agentic AI capabilities"` — "Agentic AI capabilities" is added framing not in the Commander-4 source file.

#### D. Status: WORKING for role bullets / PARTIALLY DEFEATED for header

**Code locations:** `role_generation.py:54-62` (claim guard), `cv_review_service.py:407-415` (source files)  
**Override points:** `header_generation.py` system prompt, `ensemble_header_generator.py` synthesis prompt  
**Required fix:** Add Commander-4 claim rules to header generation system prompt:
```python
# Add to PROFILE_SYSTEM_PROMPT after the HEADLINE GROUNDING RULES:
COMMANDER-4 FACTS (verified — do not embellish):
- "42 plugins" (NOT "42 agents" or "42 multi-agent plugins" or "42 AI agents")
- "2,000 users" (NOT "2,000+ enterprise users")
- Platform name: "Commander-4 (Joyia)" — a PROJECT within Seven.One
```

---

### Action 3: Expand Core Competencies to 10-12 Keywords

#### A. Plan vs Code

**Plan:** Update CORE COMPETENCIES instruction from 6-8 to 10-12 keywords.

**Implementation found:**
- `src/layer6_v2/prompts/header_generation.py:75` — `4. **CORE COMPETENCIES** (10-12 keywords)` ✅
- `src/layer6_v2/skills_taxonomy.py:908-909` — `MIN_SKILLS_PER_SECTION = 4`, `MAX_SKILLS_PER_SECTION = 10`
- `orchestrator.py:1720-1724` — Renders V2 competencies, empty sections skipped with `if skills:`

#### B. End-to-End Trace — EFFECTIVELY BROKEN

The prompt says 10-12, but the algorithmic competency generator (CoreCompetencyGeneratorV2) operates independently from the prompt. It assigns skills from the whitelist to 4 taxonomy sections. **Section 4 ("AI Governance & Engineering Leadership") gets 0 matching skills because all 6 of its skills are either absent from the whitelist or filtered by achievement grounding:**

| Section 4 Skill | In full whitelist? | Survives grounding? |
|---|---|---|
| Engineering Leadership | ❌ (not in any role file) | N/A |
| GDPR Compliance | ❌ (not in any role file) | N/A |
| Risk Analysis | ✅ (soft_skills) | ❌ (filtered) |
| Stakeholder Management | ✅ (soft_skills) | ❌ (filtered) |
| Mentoring | ✅ (soft_skills) | ❌ (filtered) |
| Technical Hiring | ❌ (not in any role file) | N/A |

**Result:** Section 4 always empty → always skipped → only 3 sections render → 6-9 keywords instead of 10-12.

#### C. MongoDB Evidence

All 3 CVs show exactly 3 competency sections:
- **LLM Reliability & Evaluation:** 2-3 skills
- **Agentic AI & Orchestration:** 5-8 skills
- **Production Operations & Observability:** 2-4 skills

Section 4 **never appears**. Total keyword count: 9-15 per CV. But the 10-12 target is for the CORE COMPETENCIES section in the PROFESSIONAL SUMMARY (generated by LLM), not the algorithmic sections. The algorithmic V2 sections are displayed separately as `**CORE COMPETENCIES**` in the markdown.

The LLM-generated `core_competencies` in the ProfileOutput is a flat list of 10-12 keywords, but the orchestrator renders the V2 dict (line 1720) instead.

#### D. Status: IMPLEMENTED BUT UNDERMINED BY SECTION 4 EMPTINESS

**Code locations:** `header_generation.py:75`, `skills_taxonomy.py:908-1206`, `orchestrator.py:1720-1724`  
**Override point:** Achievement grounding destroys Section 4 skills  
**Required fix:** Two options:
1. **Quick fix:** Add Section 4 skills ("Engineering Leadership", "GDPR Compliance", "Mentoring", "Stakeholder Management", "Technical Hiring") directly to the skill whitelist bypass for ai_architect and ai_leadership roles
2. **Proper fix:** Update Section 4 skills in the taxonomy to use terms that DO appear in achievements (e.g., "Domain-Driven Design" instead of "Engineering Leadership", "TCF Compliance" instead of "GDPR Compliance", "Lean Friday Mentoring" instead of "Mentoring")

---

### Action 4: Surface Verified AI Skills from Project Files

#### A. Plan vs Code

**Plan:** Ensure skill whitelist includes skills from `lantern_skills.json` (LangChain, LangGraph, RAG Pipeline, Vector Search, etc.)

**Implementation found:**
- `orchestrator.py:133-144` — `_load_ai_project_skills()` loads from `commander4_skills.json` only
- **`lantern_skills.json` is NEVER loaded anywhere.** Grep across entire codebase returns zero matches for "lantern_skills" in any Python file.
- `orchestrator.py:523` — Expansion only adds to `hard_skills`: `skill_whitelist.setdefault("hard_skills", []).extend(new_skills)`

#### B. End-to-End Trace

**Missing chain:** `lantern_skills.json` contains critical AI skills:
- verified_competencies: LLM Gateway Design, Provider Fallback Chain, Circuit Breaker Pattern, Multi-Provider Routing, LLM-as-Judge Evaluation, Langfuse Tracing, RAG Pipeline, Vector Search, Semantic Caching, Model Routing, LangGraph, LangChain, Agent Frameworks, API Gateway Design
- post_checklist_competencies: Golden-Set Testing, Eval Harness Design, Faithfulness Evaluation, Streaming SSE, Rate Limiting, SLO/SLI Design, Prompt Engineering, Document Ingestion Pipeline, Hybrid Search

These skills exist in the taxonomy sections and would match — but they're never added to the whitelist.

**Second gap:** Achievement grounding filters out 87 hard skills including Docker, Kubernetes, Prometheus, Grafana, RAG Pipeline, RAPTOR Indexing, LLM-as-Judge Evaluation, Prompt Engineering, Vector Search. Many of these are in the taxonomy sections but filtered because the exact substring doesn't appear in achievement bullets.

**Result:** The algorithm can only assign skills it finds in the whitelist. Critical verified AI skills (LangChain, LangGraph, Prompt Engineering) are missing from the whitelist → never assigned to competency sections.

#### C. MongoDB Evidence

All 3 CVs are missing from core competencies:
- LangChain (verified in lantern_skills.json) — MISSING
- LangGraph (verified) — MISSING
- Prompt Engineering (verified) — MISSING
- Docker (verified in KI Labs role) — MISSING
- Kubernetes (verified in KI Labs role) — MISSING

#### D. Status: NOT WORKING

**Code locations:** `orchestrator.py:133-144` (only loads commander4), `orchestrator.py:523` (only hard_skills)  
**Missing code:** No `_load_lantern_skills()` function exists  
**Required fix:**
1. Create `_load_lantern_skills()` parallel to `_load_ai_project_skills()` that reads `lantern_skills.json`
2. Add lantern skills to whitelist in the AI gate section (after line 524)
3. Add soft skills from both project files to `skill_whitelist["soft_skills"]`
4. Consider relaxing achievement grounding for skills that appear in verified project files (commander4_skills.json, lantern_skills.json)

---

### Action 5: Improve Scout Scoring to Filter Bad-Fit Roles

#### A. Plan vs Code

**Plan:** Add negative signals, experience mismatch penalty, title hard negatives.

**Implementation found:** All changes match plan exactly:
- `rule_scorer.py:228-229` — Hard tier: `penalty_per_match: 8`, `max_penalty: 35` ✅
- `rule_scorer.py:244-245` — Soft tier: `penalty_per_match: 4`, `max_penalty: 20` ✅
- `rule_scorer.py:729` — Experience mismatch: `return min(penalty, 30)` ✅
- `rule_scorer.py:203-209` — TITLE_HARD_NEGATIVES: 9 entries ✅
- `rule_scorer.py:183-199` — UNWANTED_TITLE_KEYWORDS: 12+ entries ✅
- Both `n8n/skills/scout-jobs/src/common/rule_scorer.py` and `src/common/rule_scorer.py` synced ✅

#### B-D. Status: FULLY WORKING

**Tests:** 51 tests pass, 0 regressions (per plan status)  
**No override points identified.**

---

### Action 6: Strengthen Pain Point Mapping in Bullet Selection

#### A. Plan vs Code

**Plan:** Post-selection pain point rebalancing with 60% coverage target.

**Implementation found:**
- `src/layer6_v2/variant_selector.py:652-747` — `_rebalance_for_pain_points()` ✅
- `variant_selector.py:79-81` — Constants: `REBALANCE_MIN_COVERAGE = 0.6`, `REBALANCE_TOKEN_OVERLAP_THRESHOLD = 0.2` ✅
- Algorithm: Identifies uncovered pain points → finds matching unselected variants → swaps with lowest-value bullets ✅
- Commit `b8316b58` confirms implementation

#### B-D. Status: FULLY WORKING

**Tests:** 12 pain point rebalancing tests pass (per commit ef5cb75a)  
**No override points identified.**

---

### Action 7: Fix Tagline Identity-Proof Alignment

#### A. Plan vs Code

**Plan:** Update tagline templates to evidence-first pattern: "[Verified identity] + [AI extension with evidence]"

**Implementation found:**
- `src/layer6_v2/prompts/header_generation.py:43-48` — Tagline instruction: "Start with role/identity noun phrase" ✅
- `header_generation.py:1010-1017` — ai_architect formula: `"[Infrastructure-to-AI bridge] with [X years] distributed systems applying [production rigor] to [LLM reliability/AI systems]."` ✅
- `header_generation.py:1019-1026` — ai_leadership formula with evidence-first pattern ✅
- `header_generation.py:1058` — Commander-4 tagline example ✅

#### B. End-to-End Trace

**No enforcement mechanism exists.** The tagline is accepted directly from LLM output:
- `ensemble_header_generator.py:544-555` — `ProfileOutput.tagline = response.tagline` (no validation)
- `orchestrator.py:1703-1709` — Renders `value_proposition or tagline or narrative` (first non-empty wins)
- No post-generation function checks if the tagline starts with a verified identity statement

The prompt instructs evidence-first, but the LLM still produces AI-first taglines for AI jobs because the JD context overwhelms the grounding instruction.

#### C. MongoDB Evidence

| CV | Tagline | Evidence-First? |
|----|---------|-----------------|
| EPAM | "Technical Lead driving platform modernization and AI infrastructure at scale..." | ⚠️ OK-ish — starts with "Technical Lead" |
| Baldur | "AI automation specialist delivering workflow automation platforms with LLMs..." | ❌ AI-first |
| Autodesk | "AI Architecture specialist delivering GenAI platforms with 42 multi-agent workflow plugins..." | ❌ AI-first + embellished claim |

2 of 3 taglines lead with AI-specialist identity despite the prompt instruction.

#### D. Status: PARTIALLY WORKING — TEMPLATES EXIST BUT NOT ENFORCED

**Code locations:** `header_generation.py:43-48` (instruction), `header_generation.py:1010-1026` (templates)  
**Missing code:** No `validate_tagline_grounding()` function  
**Required fix:** Add a post-generation tagline check:
```python
def validate_tagline_evidence_first(tagline: str, role_category: str) -> str:
    """Reject taglines that lead with unverified AI-specialist claims."""
    ai_first_patterns = [
        r"^AI\s", r"^GenAI\s", r"^Generative AI\s", r"^LLM\s",
        r"^Machine Learning\s", r"^ML\s",
    ]
    for pattern in ai_first_patterns:
        if re.match(pattern, tagline, re.I):
            # Return template-based fallback
            return EVIDENCE_FIRST_FALLBACKS.get(role_category, tagline)
    return tagline
```

---

## 3. New Gaps Found (Not in Original 7 Actions)

### Gap A: Redundant Dual-Title in Standard Assembly Path

**File:** `orchestrator.py:1676`  
**Problem:** `_assemble_cv_text()` always creates `### {bounded_title} · {generic_title}` even when redundant (e.g., "AI Architect · AI Architect"). The Claude CLI path (`_assemble_claude_cv_text()` line 1329) has a redundancy check but the standard path doesn't.  
**Impact:** 100% of non-CLI CVs have redundant H3 titles for AI jobs.  
**Fix:** Port the redundancy check from line 1329 to line 1676.

### Gap B: `lantern_skills.json` Completely Orphaned

**File:** `data/master-cv/projects/lantern_skills.json`  
**Problem:** Never imported or referenced by any Python file in the pipeline. Contains 30+ verified AI competencies (LangChain, LangGraph, RAG Pipeline, Vector Search, Semantic Caching, Prompt Engineering) that are critical for AI Architect CVs.  
**Impact:** Verified AI skills missing from all generated CVs.  
**Fix:** Create `_load_lantern_skills()` and add to whitelist expansion in AI gate.

### Gap C: Achievement Grounding Destroys 54% of Hard Skills and 89% of Soft Skills

**File:** `cv_loader.py:679-720`  
**Problem:** `get_achievement_grounded_whitelist()` uses simple substring matching (`skill.lower() in combined_lower`). This filters out Docker (not literally in any bullet), Kubernetes, Prometheus, Grafana, 73 other hard skills, and 73 of 82 soft skills. Only 9 soft skills survive.  
**Impact:** Taxonomy Section 4 (governance/leadership) gets 0 matching skills → entire section drops from output.  
**Fix:** For skills verified in project files (commander4_skills.json, lantern_skills.json), bypass achievement grounding. These are independently verified through a separate process.

### Gap D: Commander-4 Claim Guard Missing from Header Generation

**File:** `src/layer6_v2/prompts/header_generation.py`  
**Problem:** The Commander-4 claim rules exist in `role_generation.py:54-62` but NOT in the header generation prompt. The header generator produces the PROFESSIONAL SUMMARY independently and can embellish claims (e.g., "42 multi-agent workflow plugins").  
**Impact:** Taglines and key achievements can embellish Commander-4 facts.  
**Fix:** Add claim rules to `PROFILE_SYSTEM_PROMPT`.

### Gap E: Ensemble Synthesis Bypasses Headline Resolver

**File:** `ensemble_header_generator.py:543-544`  
**Problem:** `_synthesize_profiles()` returns `ProfileOutput.headline = response.headline` directly from LLM without calling `resolve_headline()` or `clean_jd_title()`. If the LLM synthesis produces a dual-title, it goes into the ProfileOutput unfiltered.  
**Impact:** Low — because the orchestrator constructs the H3 title independently at line 1676. But the ProfileOutput.headline is exposed in the grader and is displayed in the frontend pipeline viewer.  
**Fix:** Add `resolve_headline(response.headline, role_category, years)` after line 520 in ensemble_header_generator.py.

---

## 4. Priority Fix List (Ordered by Impact)

| Priority | Fix | File:Line | Effort | Impact |
|----------|-----|-----------|--------|--------|
| **P0** | Load `lantern_skills.json` into whitelist for AI jobs | `orchestrator.py:519-524` | 30 min | Surfaces LangChain, LangGraph, Prompt Engineering in all AI CVs |
| **P0** | Fix Section 4 skill definitions to use achievement-grounded terms | `role_skills_taxonomy.json:2034-2044` | 30 min | Restores 4th competency section to output |
| **P1** | Add dual-title redundancy check to `_assemble_cv_text()` | `orchestrator.py:1676` | 5 min | Eliminates "AI Architect · AI Architect" |
| **P1** | Add Commander-4 claim rules to header generation prompt | `prompts/header_generation.py:41` | 10 min | Prevents tagline embellishment |
| **P2** | Add soft skills from project files to whitelist | `orchestrator.py:523` | 15 min | Allows Mentoring, Leadership in competencies |
| **P2** | Add tagline evidence-first validator | `orchestrator.py:1703` or `ensemble_header_generator.py:544` | 45 min | Rejects AI-first taglines |
| **P3** | Bypass achievement grounding for project-verified skills | `cv_loader.py:679-720` or `orchestrator.py:461` | 30 min | Stops filtering Docker, Kubernetes, Prometheus, etc. |
| **P3** | Apply `resolve_headline()` in ensemble synthesis | `ensemble_header_generator.py:543` | 10 min | Consistent headline cleaning |

---

## 5. Updated Plan: Revised Steps Reflecting Actual State

### Step 1: Fix Orchestrator AI Gate — ✅ COMPLETED
Works as intended. AI jobs correctly routed to `ai_architect` or `ai_leadership`.

### Step 2: Negative Scoring — ✅ COMPLETED
Exact caps and penalties match plan. 51 tests pass.

### Step 3: Scout Selector Profiles — NOT STARTED
Status unchanged from plan.

### Step 4: Add `ai_leadership` Taxonomy — ✅ COMPLETED
`role_skills_taxonomy.json` has full `ai_leadership` entry with 4 sections, persona, and skills.

### Step 5: Header Generator + Tagline Templates — ✅ PARTIALLY COMPLETED
- VALUE_PROPOSITION_TEMPLATES added ✅
- Headline grounding rules in prompt ✅
- **Missing:** Tagline enforcement, Commander-4 guard in header prompt

### Step 6: Grader + Improver Enhancements — ✅ PARTIALLY COMPLETED
- `category_keywords` for `ai_architect` and `ai_leadership` added at `grader.py:384-385` ✅
- **Missing:** Improver AI-focused directives not verified

### NEW Step 6.5: Critical Plumbing Fixes (INSERT HERE)

| # | Fix | Files |
|---|-----|-------|
| 6.5a | Load `lantern_skills.json` into whitelist | `orchestrator.py` |
| 6.5b | Fix Section 4 taxonomy skills | `role_skills_taxonomy.json` |
| 6.5c | Dual-title redundancy check | `orchestrator.py:1676` |
| 6.5d | Commander-4 claim rules in header prompt | `header_generation.py` |
| 6.5e | Soft skills expansion from project files | `orchestrator.py:523` |
| 6.5f | Tagline evidence-first validator | `ensemble_header_generator.py` / `orchestrator.py` |

### Step 7: Search Keywords + Profile — NOT STARTED

### Step 8: Commander-4 Contributions — ONGOING (independent)

---

## Appendix: MongoDB Evidence Summary

**Query:** 3 most recent AI job CVs (`is_ai_job: true`, sorted by `cv_generated_at desc`)

| Field | CV1 (EPAM) | CV2 (Baldur) | CV3 (Autodesk) |
|-------|-----------|-------------|----------------|
| Generated | 2026-04-12 16:51 | 2026-04-12 16:50 | 2026-04-12 16:45 |
| role_category | staff_principal_engineer | senior_engineer | staff_principal_engineer |
| H3 title | Enterprise Artificial Intelligence Architect · AI Architect | AI Automation Specialist · AI Architect | Distinguished AI Architect, AEC Construction · AI Architect |
| Dual-title? | **YES** (redundant) | **YES** (not redundant) | **YES** (redundant) |
| Tagline evidence-first? | ⚠️ OK ("Technical Lead...") | ❌ AI-first ("AI automation specialist...") | ❌ AI-first ("AI Architecture specialist...") |
| Commander-4 accurate? | ⚠️ "42 plugins with Agentic AI capabilities" | ✅ "42 workflow plugins" | ❌ "42 multi-agent workflow plugins" |
| Core competency sections | 3 (Section 4 missing) | 3 (Section 4 missing) | 3 (Section 4 missing) |
| Total competency keywords | ~9 | ~9 | ~11 |
| LangChain in competencies? | ❌ | ❌ | ❌ |
| LangGraph in competencies? | ❌ | ❌ | ❌ |
| Prompt Engineering? | ❌ | ❌ | ❌ |
| Docker/Kubernetes? | ❌ | ❌ | ❌ |
