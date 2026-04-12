# Agentic AI Architect — Focused Application & Pipeline Optimization Plan

**Date:** 2026-04-11 (Revised 2026-04-12 after Codex gpt-5.4 review + CV reviewer diagnostic)  
**Objective:** Maximize AI Architect applications (10-15/day) under one market identity  
**Time Split:** 70-80% applying, 20-30% learning  

---

## Part 0: Current State Snapshot

### MongoDB Pipeline Inventory

| Metric | Count |
|--------|-------|
| Total processable jobs (null + under processing + ready) | 9,183 |
| **Focused AI/Architect roles (matching target titles)** | **1,580** |
| With CV generated | 810 |
| Ready to apply (CV + GDrive + Dossier) | 681 |
| Starred | 2 |
| Tier A focused | 18 |
| Tier B focused | 50 |
| Tier C focused | 535 |
| Tier D focused (weak fit) | 347 |
| Unscored (Tier ?) | 630 |

**Immediate application pool: 681 jobs are fully ready (CV + GDrive + Dossier).**  
At 10-15 applications/day, this is **45-68 days of focused applications** without any new discovery.

### Pipeline Throughput

| Stage | Capacity/Day |
|-------|-------------|
| Scout discovery (new jobs) | 50-100/day |
| Full pipeline (extraction + CV + dossier) | 12-15/day |
| Apply-jobs (browser automation) | 20-30/day |
| **Bottleneck:** Full pipeline processing | **12-15/day** |

---

## Part 1: Market Identity — One Story, One Persona

### Primary Identity: **Agentic AI Architect**

```
Headline: AI Architect | 11+ Years Production Systems & Engineering Leadership
Tagline: AI architect designing enterprise LLM platforms at scale — 
         bridging distributed systems rigor with production AI governance
```

### Fallback Hierarchy

| Priority | Title | When to Use |
|----------|-------|-------------|
| 1 | Agentic AI Architect | Roles mentioning agentic, agents, orchestration, LangChain/LangGraph |
| 2 | AI Systems Architect | Roles mentioning system design, platform, infrastructure, reliability |
| 3 | Head of AI | Roles with real org/team ownership + hands-on architecture (selective — see note) |
| 4 | AI Solutions Architect | Roles at consultancies/SIs with strong technical depth (avoid sales-adjacent) |
| 5 | Senior AI Engineer | IC roles without explicit architecture scope |

> **Note on Head of AI:** Current evidence supports "hands-on AI platform lead" better than "department head." Apply only when the JD emphasizes architecture + leadership + team-building and the team size is <20. For pure executive/strategy Head of AI roles (50+ headcount, P&L ownership), the evidence is thinner — apply selectively and frame as "building AI from zero."

### Target Role Titles (Prioritized)

**Tier 1 — Perfect Fit (apply immediately):**
- AI Architect / AI Solutions Architect / AI Systems Architect
- GenAI Architect / LLM Architect / AI Platform Architect
- Head of AI / Head of AI Engineering / Head of GenAI
- Platform Architect (AI/ML scope)

**Tier 2 — Strong Fit (apply with slight reframe):**
- Staff AI Engineer / Principal AI Engineer
- Staff LLM Engineer / Staff GenAI Engineer
- AI Infrastructure Architect / Cloud Architect (AI)
- Director of AI Engineering

**Tier 3 — Acceptable (apply if score > 60):**
- Senior AI Engineer (with architecture scope in JD)
- AI Platform Engineer (if system design heavy)
- ML Architect / ML Platform Engineer
- Principal Engineer (AI/ML domain)

**Do NOT apply to:**
- Pure ML/Data Science (model training, Kaggle-style)
- Frontend/UI roles with "AI" in title
- Sales/Solutions Consultant roles
- Junior/Mid-level AI Engineer
- Roles requiring >3 years PyTorch/TensorFlow model training

---

## Part 2: Changes to Master CV & Pipeline

### 2.1 Master CV Changes (`data/master-cv/`)

#### A. Extend existing `ai_leadership` in scout layer — do NOT create parallel `head_of_ai`

> **Codex Review Finding:** The scout layer already has `ai_leadership` in `rule_scorer.py` (line 138) which handles Head of AI titles. The CV pipeline forces all AI jobs to `ai_architect` via `orchestrator.py` (line 493). Adding a separate `head_of_ai` would create a broken path — scout detects it as `ai_leadership`, but downstream would not recognize it.

**Correct approach — two-phase:**

**Phase 1 (Scout layer):** Enhance existing `ai_leadership` role definition in `rule_scorer.py` to boost architecture-heavy Head of AI roles higher. No new role needed.

**Phase 2 (CV layer):** Modify the AI gate in `orchestrator.py` to distinguish between `ai_architect` (IC/architect) and `ai_leadership` (Head/Director/VP) instead of collapsing all AI jobs to `ai_architect`. This requires:
1. Pass the original `role_category` from extraction through the AI gate
2. Add `ai_leadership` persona to `role_skills_taxonomy.json` using the **correct schema**:

```json
"ai_leadership": {
  "display_name": "Head of AI / AI Leadership",
  "static_competency_sections": {
    "_comment": "V2 Header Generation: Fixed 4 section names for core competencies.",
    "section_1": {
      "name": "AI Strategy & Platform Architecture",
      "description": "AI strategy, LLM platform design, RAG architecture, agentic system design"
    },
    "section_2": {
      "name": "Engineering Leadership & Team Building",
      "description": "AI team building, technical hiring, mentoring, cross-functional leadership"
    },
    "section_3": {
      "name": "Production AI Operations",
      "description": "LLM reliability, evaluation pipelines, observability, cost optimization"
    },
    "section_4": {
      "name": "AI Governance & Compliance",
      "description": "EU AI Act, GDPR for AI, guardrail design, risk assessment, responsible AI"
    }
  },
  "persona": {
    "identity_statement": "hands-on AI platform leader building and governing enterprise AI systems with 11 years of production infrastructure foundation",
    "voice": "strategic, hands-on, governance-aware",
    "tagline_templates": [
      "Hands-on AI leader with {years} years building production platforms — from LLM gateway design to AI governance at enterprise scale.",
      "{Identity} bridging distributed systems rigor with AI platform leadership and team building."
    ],
    "headline_pattern": "{Title} | {Years}+ Years AI Platform Leadership & Production Systems",
    "power_verbs": ["led", "architected", "scaled", "governed", "established", "pioneered", "built", "transformed"],
    "metric_priorities": ["team_scale", "platform_scale", "reliability", "cost_optimization"],
    "key_achievement_focus": ["AI platform at scale", "team building", "governance frameworks", "cost optimization"],
    "differentiators": ["hands-on + leadership hybrid", "infrastructure-to-AI bridge", "governance depth"],
    "metric_emphasis": 0.4,
    "high_impact_themes": [
      "Building AI teams from zero and establishing engineering culture",
      "LLM platform architecture with production reliability guarantees",
      "AI governance and compliance (GDPR, guardrails, responsible AI)",
      "Cost-optimized multi-provider AI routing at enterprise scale"
    ],
    "red_flags_to_avoid": [
      "Overstating org-scale beyond 10-15 direct reports",
      "Claiming P&L ownership without evidence",
      "Implying deep ML research expertise",
      "Missing hands-on technical credibility"
    ],
    "board_level_language": false,
    "expected_team_size_range": "8-20",
    "expected_budget_range": null,
    "ats_priority": "high"
  }
}
```

> **Critical dependency:** This taxonomy addition only works AFTER the orchestrator AI gate is updated (Step 1 in execution plan).

#### B. Verify AI Achievement Promotion (Already Handled)

> **Codex Review Finding:** The system already handles this. `variant_selector.py` (line 405) hard-forces Achievement 15 for AI jobs on the Seven.One role, and picks from 16-18 as well. No metadata changes needed here.

**Action:** Verify variant selection is working correctly by running the pipeline on 3 AI Architect JDs and checking that achievements 15-18 appear in the output. If they don't, investigate `variant_selector.py` — don't change `role_metadata.json`.

#### C. Role Bullet Emphasis for AI Architect

For each of the 6 roles, identify the **AI-adjacent achievements** that should be promoted:

| Role | AI-Adjacent Achievements to Promote |
|------|-------------------------------------|
| Seven.One (01) | #15 AI Platform (Commander-4), #16 Document Ingestion, #17 Structured Outputs, #18 Semantic Caching, #3 Real-Time Observability, #1 Platform Modernization |
| Samdock (02) | Event Sourcing + CQRS (maps to agentic state management) |
| KI Labs (03) | Flask/MongoDB backend (maps to AI API design) |
| Fortis (04) | Microservices + Message Brokers (maps to agent orchestration) |
| OSRAM (05) | Protocol Design + CoAP (maps to AI system protocol design) |
| Clary (06) | Real-time WebRTC (maps to streaming AI / SSE architecture) |

### 2.2 Header Generation Changes

**File:** `src/layer6_v2/header_generator.py` + `prompts/header_generation.py`

Enhance existing `ai_architect` tagline templates in `prompts/header_generation.py` (line 998, the existing `ai_architect` guidance block):

```python
# In the existing ai_architect guidance dict at line 998:
"ai_architect": {
    "formula": "[Infrastructure-to-AI bridge] with [X years] distributed systems applying [production rigor] to [LLM reliability/AI systems].",
    "examples": [
        # EXISTING examples stay
        "Production infrastructure leader with 11+ years applying distributed systems rigor to LLM gateway design and AI reliability at scale.",
        # ADD new tagline variants:
        "AI architect who ships LLM platforms that don't break — 11 years of distributed systems rigor applied to production AI.",
        "Enterprise AI architect bridging evaluation-driven, governance-first platform design with hands-on implementation.",
    ],
}
```

For `ai_leadership` roles (after orchestrator fix), add a new entry to the same guidance dict:

```python
"ai_leadership": {
    "formula": "[Hands-on AI leader] building [AI platforms] with [X years] production systems + [team building/governance].",
    "examples": [
        "Hands-on AI leader with 11+ years building production platforms — from LLM gateway design to AI governance at enterprise scale.",
        "AI platform leader bridging distributed systems architecture with team building and AI governance.",
    ],
}
```

> **Note:** There is no `ROLE_GUIDANCE` dict — the actual guidance lives in the `ai_architect` entry within `prompts/header_generation.py` starting at line 998, and fallback taglines in `header_generator.py`.

### 2.3 CV Grader Changes

**File:** `src/layer6_v2/grader.py`

> **Codex Review Finding:** The grader currently has ONE global weight map — there are no role-specific branches. The `category_keywords` dict at line 378 has entries for `engineering_manager`, `staff_principal_engineer`, `director_of_engineering`, `head_of_engineering`, `cto` — but NOT `ai_architect`. This is a real gap.

**Change 1:** Add `ai_architect` and `ai_leadership` to `category_keywords` (line 378):

```python
category_keywords = {
    # ... existing entries ...
    "ai_architect": ["architecture", "designed", "llm", "ai", "evaluation", "production", "scale", "platform"],
    "ai_leadership": ["led", "team", "ai", "platform", "architecture", "governance", "built", "scale"],
}
```

**Change 2 (optional, lower priority):** Add role-conditional weight adjustment. Currently the 5 dimension weights are global constants. For AI roles, we could add a post-scoring boost to JD alignment. However, this requires refactoring the grader's `_compute_composite_score` method — defer to after the plumbing fixes.

**Do NOT** add a mandatory Lantern/Commander-4 mention requirement — that increases hallucination pressure. Commander-4 is the stronger proof point; let the variant selector and bullet generator surface it naturally.

### 2.4 CV Reviewer / Improver Changes

**File:** `src/layer6_v2/improver.py`

For AI Architect roles, add a focused improvement directive:

```
When improving for AI Architect roles:
1. Ensure the profile section leads with AI platform architecture, not generic engineering
2. Key achievements must include at least 2 AI-specific metrics (e.g., cache hit rate, eval coverage, latency)
3. Core competencies must include: LLM Architecture, RAG, Evaluation Pipelines, AI Governance
4. The headline MUST contain "AI Architect" or "AI Platform" or "AI Systems"
```

> **Codex correction:** Do NOT require "every role to have at least 1 bullet reframed through AI lens." Forcing older roles (OSRAM IoT, Clary WebRTC) through an AI lens degrades credibility. Only roles 01 (Seven.One) and 02 (Samdock CQRS) have natural AI-adjacent framing.

### 2.5 Rule Scorer Changes (Scout Pipeline)

**File:** `n8n/skills/scout-jobs/src/common/rule_scorer.py`

> **Codex Finding:** `ai_leadership` already exists (line 138) with `titleWeight: 50` and `displayName: "Head of AI"`. Do NOT add a parallel `head_of_ai` — enhance the existing role instead.

**Changes to existing `ai_leadership`:**

1. Verify title patterns cover: head of genai, head of ai engineering, vp of ai, director of ai
2. Boost architecture keyword weight within `ai_leadership` scoring (line 511):
```python
"ai_leadership": {
    "genaiLlm":      {"weight": 2.5, "max": 25},
    "agenticAi":     {"weight": 2.5, "max": 25},
    "architecture":  {"weight": 2.5, "max": 25},   # NEW
    "aiLeadership":  {"weight": 3,   "max": 30},
}
```
3. Add false-positive exclusions: `["sales", "pre-sales", "marketing", "customer success"]`

### 2.5b Negative Scoring & Exclusion Filters (Implemented 2026-04-12)

**Problem:** 63% of pipeline CVs scored WEAK_MATCH, 31% NEEDS_WORK. Pipeline wasting capacity on PyTorch/TensorFlow/CUDA ML research roles, manufacturing domain, mobile GenAI, and other fundamentally misaligned positions.

**Changes implemented:**

1. **UNWANTED_TITLE_KEYWORDS** — Added 12 entries: data scientist variants, ml engineer variants, ml researcher, research scientist, computer vision, robotics, firmware, devops engineer
2. **TITLE_HARD_NEGATIVES** — Added 9 entries: data scientist, ml researcher, machine learning research, computer vision engineer, robotics engineer, android/ios engineer, firmware engineer, network engineer (-25 each, word-boundary)
3. **JD_NEGATIVE_SIGNALS** — New constant with two tiers:
   - Hard (penalty 8/match, cap 35): pytorch, tensorflow, keras, cuda, rlhf, phd required, mobile genai, manufacturing, etc.
   - Soft (penalty 4/match, cap 20): azure/gcp/databricks required, scikit-learn, data scientist, feature engineering, etc.
4. **Experience mismatch penalty** — Regex scanning for "N+ years <lacking_tech>" patterns (2yr=8, 3yr=12, 5yr=20 per-tech cap, 30 global cap)
5. **Integration** — JD body scanned via `crit_lower + desc_lower` (excludes title to avoid double-counting). New breakdown fields: `jdNegativeHard`, `jdNegativeSoft`, `experienceMismatch`

**Files synced:** `n8n/skills/scout-jobs/src/common/rule_scorer.py` and `src/common/rule_scorer.py` are now identical (were diverged since Mar 25)

**Tests:** 8 new tests in `TestJDNegativeSignals` class. 51 total tests pass, 0 regressions.

**Expected impact:** Bad-fit roles score 15-40 points lower, WEAK_MATCH rate 63% -> <35%

---

## Part 3: Scout Cron Profile Optimization

> **Codex Review Findings:**
> - `high_score` is dead config — `compute_rank_score()` (line 114) never reads it. Only `leadership`, `staff_architect`, `remote`, and `newest` are implemented.
> - `title_must_match` is unsupported by `scout_dimensional_selector.py` — it only reads `quota`, `location_patterns`, `rank_boosts`, and `location_mode`.
> - Total daily quota across all profiles must not exceed pipeline capacity (12-15/day actual throughput).

### Current Profiles vs. Proposed Changes

#### Profile 1: `uae_ksa_leadership` — ADD ARCHITECT BOOST

```yaml
# Current
rank_boosts:
  leadership: 15
  newest: 5

# Proposed
rank_boosts:
  leadership: 15
  staff_architect: 12    # NEW — prioritize architect titles
  newest: 5
```

#### Profile 2: `global_remote` — INCREASE QUOTA + ARCHITECT BOOST

```yaml
# Current: quota 2
# Proposed: quota 3 (conservative increase — avoid overwhelming pipeline)
rank_boosts:
  staff_architect: 15        # NEW — architect titles primary signal
  leadership: 10
  newest: 5
```

#### Profile 3: `eea_remote` — ADD ARCHITECT BOOST

```yaml
# Current: quota 2 — keep unchanged
rank_boosts:
  staff_architect: 12        # NEW
  remote: 10
  leadership: 8
  newest: 5
```

#### Profile 4: `eea_staff_architect` — BOOST FRESHNESS

```yaml
# Current: quota 2
# Proposed: quota 3 (slight increase — most aligned profile)
rank_boosts:
  staff_architect: 20        # INCREASE from 15
  newest: 10                 # INCREASE from 8
  leadership: 8              # INCREASE from 5
  remote: 5                  # INCREASE from 3
```

#### ~~NEW Profile 5: `global_ai_architect`~~ — DEFERRED

> **Codex Review:** Do not add this profile yet. The selector does not support `title_must_match` or `location_mode: "ignore"`. Without title filtering, this profile would just be a quota multiplier with heavy overlap against `eea_staff_architect` and `global_remote`. To implement properly:
> 1. First add `title_must_match` support to `scout_dimensional_selector.py`
> 2. Then add the profile with conservative quota (3, not 6)
> 3. Test for overlap against existing profiles before deploying

#### Quota Capacity Check

| Profile | Quota | Runs/Day | Max/Day |
|---------|-------|----------|---------|
| uae_ksa_leadership | 6 | 4 | 24 |
| global_remote | 3 | 8 | 24 |
| eea_remote | 2 | 4 | 8 |
| eea_staff_architect | 3 | 4 | 12 |
| **Theoretical max** | | | **68** |

These are ceilings, not guarantees — actual fills depend on available scored jobs and dedup. The pipeline bottleneck (12-15/day) is the real constraint. **Priority:** Apply from the existing 681 ready pool first; new selector output supplements, not replaces.

### Search Keyword Optimization

**File:** `n8n/skills/scout-jobs/scripts/scout_linkedin_jobs.py`

Add new search profile `ai_architect_focused` (runs alongside existing profiles):

```python
"ai_architect_focused": [
    "AI Architect", "AI Solutions Architect", "AI Systems Architect",
    "AI Platform Architect", "GenAI Architect", "LLM Architect",
    "Agentic AI Architect", "Head of AI", "Head of AI Engineering",
    "Head of GenAI", "AI Infrastructure Architect", "Enterprise AI Architect",
]
```

---

## Part 4: Commander-4 Short-Burst Contributions (AI Architect Portfolio)

### Why This Matters

Commander-4/Joyia is a **production enterprise AI platform with 2,000 users** — your day job is already AI Architect work. But the gap is: **undocumented, unmetricated, and ungoverned AI infrastructure**. Each contribution below fills a governance/observability gap that directly maps to AI Architect competencies on your CV.

### High-Impact 2-4 Hour Contributions

| # | Contribution | Hours | CV Bullet It Creates | AI Architect Competency |
|---|-------------|-------|---------------------|------------------------|
| 1 | **Semantic Cache Analytics** — Log hit/miss rates, similarity scores, TTL patterns to CloudWatch/Datadog | 2-3h | "Instrumented semantic caching analytics revealing 60-70% L1 hit rate, enabling targeted optimization" | Production Observability |
| 2 | **RAG Quality Metrics** — Track retrieval@k, chunk relevance distribution, reranker effectiveness | 2-3h | "Designed retrieval evaluation framework measuring MRR@k and NDCG@k across knowledge base silos" | Evaluation Pipelines |
| 3 | **LLM Cost Attribution** — Token tracking per workflow/step, cost column in execution history | 3-4h | "Built per-workflow LLM cost attribution system across 42 AI plugins, enabling ROI analysis" | Cost Optimization |
| 4 | **Guardrail Chain Metrics** — Log which guardrails trigger, false positive rates, optimal ordering | 2-3h | "Instrumented guardrail chain analytics for content safety optimization across per-silo profiles" | AI Governance |
| 5 | **Structured Output Governance** — Schema validation wrapper with retry + fallback for generateObject | 2-3h | "Hardened structured LLM output pipeline with schema enforcement, retry logic, and fallback parsing" | LLM Reliability |
| 6 | **OpenTelemetry AI Tracing** — Trace AI decision trees in Datadog for debugging complex workflows | 3h | "Integrated OpenTelemetry tracing for AI workflow execution, enabling end-to-end decision auditability" | Observability |
| 7 | **Prompt Versioning System** — Migrate hardcoded prompts to DynamoDB with version tracking | 3-4h | "Designed prompt versioning system enabling A/B testing and data-driven prompt optimization" | Prompt Engineering at Scale |
| 8 | **Embedding Quality Dashboard** — Track embedding model performance, detect semantic drift | 2-3h | "Built embedding quality monitoring detecting semantic drift and outlier vectors across knowledge silos" | Vector Search Quality |
| 9 | **Token Budget Enforcement** — Per-workflow/user token limits to prevent cost runaway | 2-3h | "Implemented token budget governance with per-workflow quotas and real-time cost alerting" | AI Governance |
| 10 | **Agentic Workflow Circuit Breaker** — Error handling patterns for AI agent steps with confidence scoring | 3-4h | "Architected circuit breaker pattern for agentic workflows with confidence-based fallback strategies" | Agentic AI Reliability |

### Recommended Sequence (2 contributions/week)

**Week 1:** #1 (Cache Analytics) + #3 (Cost Attribution) — Observability foundation  
**Week 2:** #2 (RAG Quality) + #5 (Structured Output) — Quality & reliability  
**Week 3:** #4 (Guardrail Metrics) + #9 (Token Budget) — Governance  
**Week 4:** #6 (OTel Tracing) + #10 (Circuit Breaker) — Advanced architecture  

Each contribution is a **merge-ready PR** with its own description mapping to AI Architect competencies.

### How to Document for CV

After each contribution, update `data/master-cv/roles/01_seven_one_entertainment.md` with a new achievement variant. The pipeline will automatically pick it up.

---

## Part 5: Learning That Sharpens Applications (20-30% time)

### Daily Learning Rule

Each day, learn ONE thing from this prioritized list that directly improves your next application:

| Day | Topic | Duration | Direct Application |
|-----|-------|----------|-------------------|
| 1 | RAG architecture patterns (chunking strategies, hybrid search) | 45 min | Answer "How would you design a RAG system?" in interviews |
| 2 | Eval harness design (golden sets, LLM-as-judge, regression) | 45 min | Answer "How do you evaluate LLM quality in production?" |
| 3 | Observability for AI (Langfuse, tracing, SLO/SLI for LLMs) | 45 min | Answer "How do you monitor LLM reliability?" |
| 4 | System design framing (AI system design interview patterns) | 45 min | Nail "Design an AI-powered X" interview questions |
| 5 | Agentic patterns (reflection, tool use, planning, multi-agent) | 45 min | Answer "How would you build an agent system?" |
| 6 | Data ingestion & orchestration (RAPTOR, chunking, change detection) | 45 min | Answer "How do you handle document ingestion at scale?" |
| 7 | Cost optimization patterns (caching, model routing, batching) | 45 min | Answer "How do you control LLM costs?" |

### Source Material (Already in Your Repos)

- **RAG:** `certifications/agentic-ai/courses/rag-course/content/` (316 concepts)
- **Agentic AI:** `certifications/agentic-ai/courses/agentic-ai-course/content/` (309 concepts)
- **AI Governance:** `certifications/agentic-ai/courses/governing-ai-agents-course/content/` (80 concepts)
- **Eval/Quality:** `ai-engg/reports/16-llm-evaluation-harness.md`
- **System Design:** `ai-engg/reports/10-portfolio-signature-builds.md`

---

## Part 6: Execution Plan — Prioritized Steps (Revised Order)

> **Codex Review:** The original order was wrong. Taxonomy/header polish before fixing upstream role detection wastes effort because `orchestrator.py` collapses all AI jobs to `ai_architect` anyway. Correct order: **plumbing first → scorer/selector → taxonomy/header → grader/improver.**

### Step 0: Immediate Actions (Today) — PARALLEL WITH EVERYTHING

| # | Action | Time | Impact |
|---|--------|------|--------|
| 0.1 | **Apply** from the 681 ready-to-apply pool (Tier A first, then B) | 2h/day | Start applying NOW — don't wait for pipeline fixes |
| 0.2 | Star/prioritize the 18 Tier A + 50 Tier B focused jobs | 15 min | Focus on highest-fit roles |
| 0.3 | Score the 630 unscored jobs (run scraper cron on them) | 30 min | These need scoring before pipeline, NOT direct pipeline trigger |

> **Note:** 0.3 is scoring, not pipelining. The 630 unscored jobs need to go through the scraper first to get a tier assignment, then the selector picks the best ones for the pipeline. Don't batch-pipeline all 630.

### Step 1: Fix Orchestrator AI Gate (Priority: CRITICAL) — ✅ COMPLETED 2026-04-12

**Why first:** This is the blocking dependency for everything else. Currently `orchestrator.py` line 493 forces ALL AI jobs to `ai_architect`, which means any `ai_leadership` taxonomy work is bypassed.

**Status:** COMPLETED. The AI gate now distinguishes leadership vs IC AI roles:
- Leadership categories (engineering_manager, director_of_engineering, head_of_engineering, vp_engineering, cto) + AI → `ai_leadership`
- IC categories (senior_engineer, tech_lead, staff_principal_engineer) + AI → `ai_architect` (unchanged)
- Non-AI jobs → unchanged

**Files changed:**
- `src/layer6_v2/orchestrator.py` — AI gate branching logic + title map ("Head of AI")
- `src/layer6_v2/variant_selector.py` — Priority order + Achievement 15 constraint
- `src/layer6_v2/grader.py` — category_keywords + executive_presence check
- `src/layer6_v2/prompts/header_generation.py` — VALUE_PROPOSITION_TEMPLATES
- `src/layer6_v2/header_generator.py` — Fallback tagline

**Tests:** 3 new AI gate tests pass (leadership→ai_leadership, IC→ai_architect, non-AI→unchanged). 138 tests pass, 0 regressions.
**Note:** `ai_leadership` falls back to engineering_manager persona until Step 4 adds taxonomy entry.

### Step 2: Enhance Rule Scorer `ai_leadership` + Negative Scoring (Priority: HIGH)

**Plan:** Boost architecture keywords in existing `ai_leadership` weights, verify title coverage, add false-positive exclusions
**Files:** `n8n/skills/scout-jobs/src/common/rule_scorer.py`
**Review:** Re-score 50 existing Head of AI jobs, verify Tier A/B assignment
**Test:** Check no false positives from "Head of Marketing AI" etc.
**Time:** 1-2 hours

**COMPLETED (2026-04-12): Negative Scoring & Exclusion Filters**
- Added JD body negative signals (hard: 8/match cap 35, soft: 4/match cap 20)
- Added experience mismatch penalty (regex for "N+ years <lacking_tech>", cap 30)
- Extended UNWANTED_TITLE_KEYWORDS (+12) and TITLE_HARD_NEGATIVES (+9)
- Synced n8n and src/common rule_scorer.py files
- 51 tests pass, 0 regressions. See Part 2.5b for details.

### Step 3: Update Scout Selector Profiles (Priority: HIGH)

**Plan:** Add `staff_architect` boost to all 4 profiles, conservative quota increases
**Files:** `n8n/skills/scout-jobs/data/selector_profiles.yaml`
**Review:** Dry-run dimensional selector, verify no excessive overlap
**Test:** Compare before/after selection results
**Time:** 1 hour

### Step 4: Add `ai_leadership` Taxonomy (Priority: HIGH)

**Depends on:** Step 1 (orchestrator fix)
**Plan:** Add `ai_leadership` to `role_skills_taxonomy.json` using correct schema (see Part 2.1A)
**Files:** `data/master-cv/role_skills_taxonomy.json`
**Review:** Codex review of taxonomy against real Head of AI JDs
**Test:** Run pipeline on 3 Head of AI jobs, verify correct persona + competency sections
**Time:** 2 hours

### Step 5: Header Generator + Tagline Templates (Priority: MEDIUM)

**Depends on:** Step 4 (taxonomy)
**Plan:** Add `ai_leadership` guidance to `prompts/header_generation.py`, enhance `ai_architect` taglines
**Files:** `src/layer6_v2/prompts/header_generation.py`
**Review:** Generate 5 sample headers for each role type, review narrative strength
**Test:** Full pipeline on 3 AI Architect + 3 Head of AI JDs
**Time:** 1-2 hours

### Step 6: Grader + Improver Enhancements (Priority: MEDIUM)

**Depends on:** Step 1 (orchestrator knows role_category)
**Plan:** Add `ai_architect` and `ai_leadership` to grader `category_keywords`, add AI-focused improvement directives
**Files:** `src/layer6_v2/grader.py`, `src/layer6_v2/improver.py`
**Review:** Re-grade 5 existing AI CVs, compare before/after
**Test:** Verify grading scores improve for AI-aligned CVs
**Time:** 1-2 hours

### Step 7: Search Keywords + Profile (Priority: MEDIUM, parallelizable with Steps 4-6)

**Plan:** Add `ai_architect_focused` search keyword profile
**Files:** `n8n/skills/scout-jobs/scripts/scout_linkedin_jobs.py`
**Review:** Manual LinkedIn search validation across 3 regions
**Test:** Verify new queries return relevant results
**Time:** 1 hour

### Step 8: Commander-4 Contributions — Start Weekly Cadence (Priority: ONGOING)

**Plan:** 2 contributions/week from the list in Part 4
**First:** Semantic Cache Analytics (contribution #1)
**Review:** PR review by team, update master CV with new achievement
**Time:** 2-4 hours per contribution

### Dependency Graph

```
Step 0 (Apply NOW) ─────────────────────────────── runs continuously
     │
Step 1 (Orchestrator fix) ──┬── Step 4 (Taxonomy) ── Step 5 (Header)
     │                      │
Step 2 (Scorer) ────────────┤── Step 6 (Grader/Improver)
     │                      │
Step 3 (Selector profiles) ─┘
     │
Step 7 (Search keywords) ──── can run in parallel with Steps 4-6
     │
Step 8 (Commander-4) ──────── ongoing, independent
```

---

## Part 7: Review Prompts

### Prompt 1: Orchestrator AI Gate Review (Post-Step 1)

```
Review the orchestrator.py changes to the AI gate (around line 481-494).

The change: Instead of unconditionally overriding role_category to "ai_architect" 
for all AI jobs, preserve "ai_leadership" when the extracted role_category is already
"ai_leadership".

Verify:
1. AI jobs with role_category="ai_leadership" keep it through the pipeline
2. AI jobs with role_category="ai_engineer" or "senior_engineer" still get overridden to "ai_architect"
3. AI jobs with role_category="ai_architect" remain unchanged
4. The title map at line ~1581 includes "ai_leadership": "Head of AI"
5. Lantern/Commander-4 skill whitelist expansion still runs for both ai_architect and ai_leadership
6. No regressions: run pipeline on 3 AI Architect JDs and verify output unchanged

Test matrix:
- Input role_category="ai_leadership" → stays "ai_leadership" ✓
- Input role_category="ai_architect" → stays "ai_architect" ✓  
- Input role_category="ai_engineer" + is_ai=True → becomes "ai_architect" ✓
- Input role_category="engineering_manager" + is_ai=True → becomes "ai_architect" ✓
- Input role_category="engineering_manager" + is_ai=False → unchanged ✓
```

### Prompt 2: Rule Scorer Review (Post-Step 2)

```
Review rule_scorer.py changes to the existing ai_leadership role definition.

Test against these real job titles (expect Tier A or B via ai_leadership):
- "Head of AI, Enterprise Platform" 
- "Head of Artificial Intelligence & Analytics"
- "VP, AI Engineering"
- "Director of AI Platform"
- "Head of GenAI Engineering"

Test against these (should NOT match ai_leadership):
- "Head of Marketing AI"
- "AI Sales Head"  
- "Head of Data Analytics"
- "Headless AI Platform Engineer"

Verify:
1. Enhanced architecture keyword weight (2.5/25) doesn't over-boost non-architecture roles
2. False-positive exclusions work (sales, marketing, customer success)
3. ai_leadership doesn't cannibalize ai_architect scoring for pure architect titles
4. Existing ai_leadership titleWeight (50) and seniority stacking unchanged
```

### Prompt 3: Scout Profile Review (Post-Step 3)

```
Review selector_profiles.yaml changes for AI Architect optimization.

Verify:
1. Total daily quota is reasonable given pipeline capacity (12-15/day):
   - uae_ksa: 6/6h × 4 = 24/day (ceiling)
   - global_remote: 3/3h × 8 = 24/day (ceiling)
   - eea_remote: 2/6h × 4 = 8/day (ceiling)
   - eea_staff_architect: 3/6h × 4 = 12/day (ceiling)
   NOTE: Actual fills << ceilings due to dedup + availability.

2. Only supported rank_boosts are used: leadership, staff_architect, remote, newest
   (NO high_score — it's dead config in compute_rank_score)
3. staff_architect boost values are proportional across profiles
4. No global_ai_architect profile until title_must_match is implemented in selector
```

### Prompt 4: CV Quality Review (Post-Steps 4-6)

```
Generate CVs for these 3 representative jobs and review quality:

1. AI Architect at a FAANG-tier company (system design heavy)
2. Head of AI at a Series B startup (leadership + hands-on)
3. AI Solutions Architect at a consultancy (client-facing + technical)

For each generated CV, verify:
1. Headline matches the exact JD title (not a generic engineering title)
2. Tagline communicates AI architect identity in first 25 words
3. Key achievements include at least 2 AI-specific metrics
4. Core competencies are AI-architecture focused (not generic engineering)
5. Role bullets for Seven.One prioritize achievements 15-18 (AI work)
6. Anti-hallucination: all claims grounded in master CV
7. ATS score > 8.5
8. JD alignment score > 8.5
9. No technology swaps (e.g., don't inject "TensorFlow" if not in source)
```

### Prompt 5: End-to-End Pipeline Review (Post All Steps)

```
Run the full pipeline on 10 focused AI Architect jobs from MongoDB (mix of tiers A/B/C).

Measure:
1. Role category detection accuracy (should be ai_architect or head_of_ai)
2. Average grading score (target: > 8.5)
3. Anti-hallucination pass rate (target: > 95%)
4. Headline quality (should contain AI-specific title)
5. Processing time per job (target: < 10 min)
6. Keyword coverage for AI-specific terms
7. Compare against previously generated CVs for same jobs — is quality improved?

Report: Summary table with pass/fail per job, aggregate metrics, and specific failure analysis.
```

---

## Part 8: Daily Execution Protocol

### Morning (9:00-10:00) — 1 hour

1. Check scout cron results from overnight
2. Review new Tier A/B focused jobs, star best ones
3. Trigger batch pipeline on any unprocessed focused jobs

### Core Block (10:00-16:00) — 6 hours

4. **Apply to 10-15 jobs** using apply-jobs skill (prioritize: starred > Tier A > Tier B > ready-to-apply)
5. Between applications: learn one topic from Part 5 list (45 min)
6. Improve one CV/story artifact (15-30 min)

### Evening (16:00-17:00) — 1 hour

7. Review application outcomes (any responses? rejections?)
8. If doing Commander-4 contribution: spend 30-60 min on current contribution
9. Update master CV if any new achievements from Commander-4 work

### Weekly Rhythm

| Day | Focus |
|-----|-------|
| Mon | Apply (15 jobs) + Pipeline step implementation |
| Tue | Apply (12 jobs) + Commander-4 contribution #1 |
| Wed | Apply (15 jobs) + Learn RAG/eval |
| Thu | Apply (12 jobs) + Commander-4 contribution #2 |
| Fri | Apply (10 jobs) + Review week's CVs + adjust |
| Sat | 5 applications + deep learning session (2h) |
| Sun | Rest + light research on target companies |

---

## Part 9: Metrics & Success Criteria

### Daily Targets

| Metric | Target | Measurement |
|--------|--------|------------|
| Applications submitted | 10-15 | MongoDB `status: "applied"` count |
| Focused role ratio | > 80% | % of applications matching target titles |
| CV grading score | > 8.5 avg | Pipeline grading output |
| ATS keyword coverage | > 80% | ATS checker output |
| Anti-hallucination pass | > 95% | QA pass rate |

### Weekly Targets

| Metric | Target | Measurement |
|--------|--------|------------|
| Total applications | 70-100 | Weekly sum |
| Response rate | > 5% | Responses / applications |
| Interview invites | 2-3 | From previous weeks' applications |
| CV artifacts improved | 3-5 | Master CV updates + header refinements |
| Commander-4 PRs | 2 | Merged contributions |
| Topics learned | 5-7 | From Part 5 list |

### 2-Week Checkpoint

After 2 weeks, evaluate:
1. Are 10-15 daily applications sustainable?
2. Which role titles get the highest response rate?
3. Is the AI Architect narrative resonating (callbacks/responses)?
4. Should we shift more toward Head of AI or stay pure Architect?
5. Are Commander-4 contributions being reflected in interview discussions?

---

## Part 10: CV Reviewer Diagnostic — 24h Quality Analysis (2026-04-12)

### 10.1 Methodology

Queried all 127 jobs with `cv_review.reviewed_at` in the past 24 hours from the `level-2` collection. All reviews were performed by `gpt-5.4-mini` via the independent reviewer service. The reviewer operates with high confidence (mean 0.92, range 0.74-0.98), meaning it is assertive about its assessments and not hedging.

### 10.2 Overall Results

| Metric | Value |
|--------|-------|
| Total reviewed | 127 |
| WEAK_MATCH | 81 (63%) |
| NEEDS_WORK | 40 (31%) |
| GOOD_MATCH | 6 (5%) |
| STRONG_MATCH | 0 (0%) |
| Would interview (yes) | 17 (13%) |
| Would interview (no) | 110 (87%) |
| Mean first-impression score | 4.2 / 10 |
| ATS survival likely | 53 (42%) |
| ATS survival unlikely | 74 (58%) |
| Mean pain point coverage | 37.3% |
| Max pain point coverage | 73% (no job reached 75%+) |

### 10.3 Six Recurring Failure Patterns

#### Pattern 1: Headline Over-Positioning (94% of reviews flagged)

**Problem:** The CV generator consistently uses "AI Engineer · AI Architect" as the headline regardless of whether the master CV supports that identity. The reviewer repeatedly states: *"The master CV supports 'Engineering Leader / Software Architect', not a verified AI Architect profile."* Even the 6 GOOD_MATCH reviews had headline issues.

Sample verdicts from WEAK_MATCH/NEEDS_WORK reviews:
- "The headline is senior and readable, but it leans on an AI-specialist identity not supported by the master CV."
- "'AI Engineer · AI Architect' signals the target role, but the master CV supports 'Engineering Leader / Software Architect' instead."
- "Headline matches the target role, but it is not grounded in the master CV. It overstates a GenAI specialization."

The `title_base` in `role_metadata.json` is `"Engineering Leader / Software Architect"` — the headline generator is ignoring this and matching the JD title too aggressively. A grounding constraint is missing: the headline may adapt toward the JD title but must stay within the evidence boundary.

#### Pattern 2: Hallucination Volume (1,089 flags — 69% high severity)

**Problem:** Across 127 reviews, the reviewer raised 1,089 hallucination flags: 754 high, 312 medium, 23 low. The primary source is Commander-4 claims being inflated or treated as unverified.

Top hallucination patterns:
- **Commander-4 framed as unverified:** "Commander-4 (Joyia) — Enterprise AI Workflow Platform (Internal — ProSiebenSat.1)" repeatedly flagged as "not found in master CV" — it IS in `data/master-cv/projects/commander4.md`, but the reviewer's source-truth context may not include project files.
- **Plugin count inflated:** "42 plugins" becoming "42 AI agents" or "42 skill-based agents" in generated CVs.
- **Metrics recombined:** Numbers from different roles/contexts merged into single claims (e.g., "60% query response time reduction and 50% faster partner integration" — exists in master CV but from separate roles).
- **Ungrounded AI framing:** "Enterprise AI platform serving 2,000 users with RAG pipelines" — the facts exist but the framing goes beyond source text.

Severity breakdown:

| Severity | Count | % |
|----------|-------|---|
| High | 754 | 69% |
| Medium | 312 | 29% |
| Low | 23 | 2% |

#### Pattern 3: Missing Verified Skills in Competencies

**Problem:** The generated CVs are failing to surface technologies that ARE verified in the master CV while simultaneously applying for roles requiring technologies the candidate does NOT have.

Top 15 missing keywords across all reviews:

| Keyword | Times Missing | Verified in Master CV? |
|---------|---------------|------------------------|
| Azure | 25x | No — genuine gap |
| LangChain | 21x | Yes (`lantern_skills.json`) |
| PyTorch | 20x | No — genuine gap |
| Machine Learning | 19x | No — genuine gap |
| TensorFlow | 16x | No — genuine gap |
| Kubernetes | 14x | Yes (KI Labs role) |
| MLOps | 13x | No — genuine gap |
| Prompt Engineering | 11x | Yes (Seven.One, Lantern) |
| AI Agents | 9x | Yes (Commander-4 plugins/tools) |
| Databricks | 8x | No — genuine gap |
| Docker | 7x | Yes (multiple roles) |
| LangGraph | 7x | Yes (`lantern_skills.json`) |
| FastAPI | 5x | Yes (Lantern) |
| Kafka | 5x | No — genuine gap |
| n8n | 5x | Yes (job-search pipeline) |

Two distinct sub-problems:
1. **Verified skills not surfaced:** LangChain, LangGraph, Kubernetes, Docker, FastAPI, Prompt Engineering, AI Agents are all in the master CV but missing from generated competencies sections.
2. **Bad-fit jobs entering pipeline:** Pure ML/Data Science roles (PyTorch, TensorFlow, CUDA, RLHF, fine-tuning) are reaching CV generation when the candidate has no evidence for these. These should be filtered at the scout scoring stage.

#### Pattern 4: Thin Competencies Section (88% of reviews flagged)

**Problem:** The core competencies section is flagged as "too thin for ATS survival" in 112 of 127 reviews. The current prompt requests 6-8 keywords; the reviewer consistently says this is insufficient against competitive searches. Even the 6 GOOD_MATCH reviews had competency gaps.

The GOOD_MATCH reviews that scored 7-8 still received feedback like:
- "Competencies section is too thin for the JD and does not front-load enough of the exact target keywords."
- "Missing several high-priority GenAI keywords that the role is likely to screen for."
- "Core competencies are underdeveloped for the JD and miss a number of required cloud and platform keywords."

#### Pattern 5: Low Pain Point Coverage (37% mean, zero jobs above 75%)

**Problem:** The CV generator addresses only about a third of identified JD pain points. Coverage distribution:

| Coverage Band | Count | % |
|---------------|-------|---|
| 0-25% | 16 | 12% |
| 25-50% | 88 | 69% |
| 50-75% | 23 | 18% |
| 75-100% | 0 | 0% |

The 6 GOOD_MATCH reviews averaged 65% coverage — meaning the bar for "good" is just being above average. The generator is not explicitly mapping pain points to achievements; it selects bullets for general relevance rather than pain-point-by-pain-point coverage.

#### Pattern 6: Tagline Fails the Proof Test (80% flagged)

**Problem:** The tagline consistently claims an AI-specialist identity with proof that the reviewer considers unverified. Sample verdicts:
- "Pronoun-free, but it fails the proof test: it claims GenAI, RAG, MLOps, and scale ownership that the master CV does not support."
- "It answers what, but not credibly — the proof trail is thin."
- "The proof is built on unverified AI/LLM claims not in the master CV, so the message is not trustworthy."

The taglines are written as AI-specialist summaries when the strongest verified evidence is platform engineering and architecture leadership. The identity-proof mismatch is the root cause.

### 10.4 Top-Third Assessment Breakdown

| Component | Reviews with Issues | % |
|-----------|-------------------|---|
| Headline | 119 / 127 | 94% |
| Tagline | 102 / 127 | 80% |
| Key Achievements | 108 / 127 | 85% |
| Core Competencies | 112 / 127 | 88% |

All four components of the top-third (the section hiring managers scan in the first 7.4 seconds) are failing at high rates. This is the most impactful area to fix because it determines whether the rest of the CV gets read at all.

### 10.5 What Works (6 GOOD_MATCH Reviews)

The 6 jobs that scored GOOD_MATCH share these characteristics:

| Job | Company | Score | Would Interview | Pain Point Coverage |
|-----|---------|-------|-----------------|---------------------|
| AI Product Engineer - Operations Domain | Factorial | 6 | Yes | 71% |
| GEN AI Architect | Capgemini | 8 | Yes | 58% |
| Senior AI Architect | WeScale | 7 | Yes | 69% |
| Senior AI Engineer (Product Development) | Tenth Revolution Group | 8 | Yes | 73% |
| Forward Deployed Engineer | ShipBob | 6 | Yes | 62% |
| AI Developer | Tind Studio | 7 | Yes | 58% |

Common traits of GOOD_MATCH reviews:
- **JD aligned with verified strengths:** Platform architecture, production systems, reliability, enterprise scale — not pure ML/model training.
- **Fewer hallucination flags:** The Tenth Revolution Group review had 0 high-severity hallucination flags; Factorial and Tind Studio had only 1 each.
- **Higher pain point coverage:** All 6 were above 55%, vs. 37% mean overall.
- **Relevant keyword match:** JDs emphasized Python, AWS, microservices, observability, RAG — technologies verified in the master CV.

The signal is clear: the CV performs well when the JD matches the candidate's actual profile (engineering leader + AI platform work), and poorly when forced to claim pure AI/ML depth.

### 10.6 Verified Strengths the Reviewer Consistently Recognizes

| Strength | Frequency |
|----------|-----------|
| Systems thinking / architecture depth | 30+ mentions |
| Cross-functional communication | 20+ mentions |
| Observability and reliability focus | 15+ mentions |
| Production-first mindset | 15+ mentions |
| Technical leadership | 15+ mentions |
| AWS / cloud infrastructure | 12+ mentions |
| Quantified impact (75% incident reduction, 3yr zero downtime, €30M) | 10+ mentions |
| Platform modernization | 10+ mentions |
| Python proficiency | 8+ mentions |

These are the candidate's defensible strengths. The CV generation profile should lead with these and frame AI work as an extension of this foundation — not the other way around.

### 10.7 Action Items

Each action includes the problem it addresses, the specific change to make, and the expected impact on reviewer scores.

---

#### Action 1: Add Headline Grounding Constraint

**Problem:** 94% of reviews flag the headline as over-positioned. The generator mirrors the JD title verbatim ("AI Engineer · AI Architect") instead of staying within evidence bounds. This triggers hallucination flags and credibility warnings.

**Change:** In `src/layer6_v2/prompts/header_generation.py`, add a grounding rule to `PROFILE_SYSTEM_PROMPT` inside the HEADLINE section:

```
GROUNDING RULE: The candidate's verified professional identity from the master CV is 
"Engineering Leader / Software Architect" with hands-on AI platform engineering 
experience (Commander-4/Joyia, Lantern). The headline MUST:
- Use the JD's exact role title (for ATS matching)
- Append a credibility anchor grounded in verified experience 
  (e.g., "| 11+ Years Production Systems & Engineering Leadership")
- NOT claim a pure AI/ML researcher or data scientist identity
- NOT use "AI Engineer" standalone — always pair with architecture/platform/leadership

ALLOWED headline patterns:
- "[JD Title] | [X]+ Years Technology Leadership"
- "[JD Title] | Platform Architecture & AI Systems"  
- "[JD Title] | Production Systems to Enterprise AI"

DISALLOWED:
- "AI Engineer · AI Architect" (dual-title with no grounding)
- Any title implying ML research, model training, or data science depth
```

**Expected impact:** Headline issue rate drops from 94% to <30%. First-impression scores should improve by 1-2 points since the headline sets the credibility frame for everything below it.

---

#### Action 2: Stop Commander-4 Claim Embellishment

**Problem:** 69% of hallucination flags are high severity. The top source is Commander-4 facts being rephrased beyond what the source text says — "42 plugins" becomes "42 AI agents", platform context gets inflated.

**Change:** Two-pronged fix:

**2a. CV Generation Guard** — In `src/layer6_v2/role_generator.py` or the role generation prompt, add:

```
COMMANDER-4 CLAIM RULES:
- "42 plugins" must stay "42 plugins" — never "42 agents" or "42 AI agents"
- "2,000 users" must stay "2,000 users" — never "2,000+ enterprise users"
- Use exact terminology from source: "workflow plugins", not "skill-based agents"
- Platform name: "Commander-4 (Joyia)" — use as-is from master CV
- Do NOT frame Commander-4 as a standalone job title or company — it is a project
  within the Seven.One Entertainment Group role
```

**2b. Reviewer Source Context** — Verify that `src/services/cv_review_service.py` includes `data/master-cv/projects/commander4.md` and `data/master-cv/projects/lantern.md` in the source truth context sent to the reviewer. If project files are excluded, the reviewer correctly flags their claims as "not found in master CV."

**Expected impact:** High-severity hallucination flags drop from 754 to <200. Reviewer confidence in grounded claims increases, which should lift GOOD_MATCH rate from 5% toward 15-20%.

---

#### Action 3: Expand Core Competencies to 10-12 Keywords

**Problem:** 88% of reviews flag competencies as "too thin for ATS survival." The current prompt requests 6-8 keywords; competitive searches require more coverage.

**Change:** In `src/layer6_v2/prompts/header_generation.py`, update the CORE COMPETENCIES section of `PROFILE_SYSTEM_PROMPT`:

```
4. **CORE COMPETENCIES** (10-12 keywords)
   - ATS-optimized format, prioritize JD keywords with verified evidence
   - Short phrases (2-3 words max each)
   - MUST include at least 3 JD-specific terms that are verified in the experience section
   - Include both technical skills AND leadership/process competencies
   - Format: "Core: AWS | Kubernetes | Platform Engineering | RAG Architecture | 
     Team Building | Observability | Event-Driven Systems | LLM Integration | ..."
```

Also ensure the competency selection draws from the full verified skill set including `lantern_skills.json` (LangChain, LangGraph, Agent Frameworks, RAG Pipeline, Vector Search, Semantic Caching, Prompt Engineering, LLM Gateway Design) — these are currently being missed.

**Expected impact:** ATS survival rate improves from 42% to >65%. Competency issue rate drops from 88% to <40%.

---

#### Action 4: Surface Verified AI Skills from Project Files

**Problem:** LangChain (21x missing), LangGraph (7x), Kubernetes (14x), Docker (7x), FastAPI (5x), and Prompt Engineering (11x) are all verified in the master CV but missing from generated CVs. The competency builder is not pulling from `lantern_skills.json`.

**Change:** In the header generation or competency selection logic, ensure the skill whitelist includes:

From `lantern_skills.json` verified_competencies:
- LLM Gateway Design, Provider Fallback Chain, Circuit Breaker Pattern, Multi-Provider Routing
- LLM-as-Judge Evaluation, Langfuse Tracing, RAG Pipeline, Vector Search
- Semantic Caching, Model Routing, **LangGraph**, **LangChain**, Agent Frameworks, API Gateway Design

From `lantern_skills.json` post_checklist_competencies:
- Golden-Set Testing, Eval Harness Design, Faithfulness Evaluation
- Streaming SSE, Rate Limiting, SLO/SLI Design
- **Prompt Engineering**, Document Ingestion Pipeline, Hybrid Search

From role files (already in role_metadata.json but undersurfaced):
- **Kubernetes** (KI Labs), **Docker** (multiple roles), **FastAPI** (Lantern)

**Expected impact:** Missing-keyword rate for verified technologies drops from 7-21x to near-zero. The gap between "what the candidate knows" and "what the CV claims" narrows.

---

#### Action 5: Improve Scout Scoring to Filter Bad-Fit Roles

**Problem:** 63% WEAK_MATCH rate means the pipeline is generating CVs for fundamentally misaligned roles — pure ML (PyTorch, TensorFlow, CUDA), data science (Kaggle, model training), manufacturing IoT, mobile GenAI. These roles require technologies the candidate has zero evidence for.

**Change:** In the scout scoring layer (`n8n/skills/scout-jobs/src/common/rule_scorer.py`), add negative signals / exclusion patterns:

```
HARD EXCLUSIONS (score to 0 or skip):
- JD requires >2 years of: PyTorch, TensorFlow, CUDA, Keras, scikit-learn model training
- JD requires: RLHF, fine-tuning pipelines, model training at scale
- JD requires: Android/iOS native, mobile GenAI on-device
- JD requires: manufacturing domain, time-series forecasting, computer vision
- JD is primarily: data science, ML research, Kaggle-style competition work

SOFT PENALTIES (reduce score by 20-30%):
- JD requires Azure/GCP as primary cloud (candidate is AWS-native)
- JD requires Databricks/Snowflake as primary data platform
- JD requires React/frontend as primary responsibility
```

**Expected impact:** WEAK_MATCH rate drops from 63% to <35% by preventing poor-fit jobs from entering the pipeline. Pipeline capacity is freed for better-matched roles. Quality of the application pool improves without increasing volume.

---

#### Action 6: Strengthen Pain Point Mapping in Bullet Selection

**Problem:** Mean pain point coverage is only 37.3%, with zero jobs exceeding 75%. The bullet selection logic optimizes for general JD relevance rather than explicit pain-point-to-achievement mapping.

**Change:** In the role generation or stitcher phase, add an explicit pain point coverage step:

1. After initial bullet selection, enumerate the JD's identified pain points.
2. For each uncovered pain point, check if any unselected achievement variant addresses it.
3. If a verified achievement maps to an uncovered pain point, swap it in for the weakest selected bullet.
4. Target: cover at least 60% of identified pain points (up from 37%).

This should be a post-selection rebalancing step, not a change to the initial generation prompt — it preserves quality while improving coverage.

**Expected impact:** Mean pain point coverage improves from 37% to >55%. GOOD_MATCH rate should increase as pain point coverage is the strongest predictor of positive review verdicts.

---

#### Action 7: Fix Tagline Identity-Proof Alignment

**Problem:** 80% of taglines fail the "proof test" — they claim AI-specialist identity but back it with unverifiable proof. The tagline should lead with the candidate's strongest verified identity and frame AI as a demonstrated extension.

**Change:** Update tagline templates in `src/layer6_v2/prompts/header_generation.py` to follow an evidence-first pattern:

```
TAGLINE GROUNDING RULE:
The tagline MUST lead with a verifiable claim before introducing AI framing.

PATTERN: [Verified identity] + [AI extension with evidence]

GOOD: "Production platform architect applying 11 years of distributed systems 
       rigor to enterprise LLM reliability and AI governance."
GOOD: "Engineering leader who modernized legacy systems at scale — now building 
       enterprise AI platforms with production-grade evaluation and caching."
GOOD: "Builder of high-performing engineering teams with hands-on AI platform 
       delivery: hybrid search, semantic caching, structured outputs."

BAD:  "Generative AI architect delivering enterprise LLM platforms..." 
      (leads with unverified AI-first identity)
BAD:  "AI/ML leader scaling RAG platforms to 2,000+ users..."
      (implies AI is the primary career identity)
```

**Expected impact:** Tagline issue rate drops from 80% to <40%. The identity-proof alignment improves reviewer trust, which is the gateway to higher first-impression scores.

---

#### Priority and Dependency Order

```
Action 1 (Headline grounding)  ─── no dependency, highest impact
Action 2 (Commander-4 guard)   ─── no dependency, second-highest impact
Action 3 (Expand competencies) ─── no dependency, quick win
Action 4 (Surface AI skills)   ─── depends on Action 3 (competency expansion)
Action 7 (Tagline fix)         ─── no dependency, pairs with Action 1
Action 5 (Scout filtering)     ─── independent, reduces waste
Action 6 (Pain point mapping)  ─── depends on stable bullet generation
```

**Recommended execution order:**
1. Actions 1 + 2 + 3 (parallel — all prompt/config changes, no code deps between them)
2. Actions 4 + 7 (parallel — skill surfacing + tagline fix)
3. Action 5 (scout scoring filter — reduces pipeline waste)
4. Action 6 (pain point rebalancing — requires more involved logic change)

**Expected combined impact:** If all 7 actions are implemented:
- GOOD_MATCH rate: 5% → 20-30%
- First-impression score: 4.2 → 6.5-7.5
- ATS survival: 42% → 70%+
- High-severity hallucination flags: 754 → <150
- Pain point coverage: 37% → 55%+
- Pipeline waste (WEAK_MATCH on bad-fit roles): 63% → <35%

---

## Part 11: Pipeline Audit Results (2026-04-12)

> **Full audit:** `reports/cv-pipeline-audit-2026-04-12.md`  
> **Methodology:** End-to-end code trace through 13 layers + MongoDB verification of 3 recent AI CVs  
> **Verified by:** Codex gpt-5.4 exec (3 critical claims independently confirmed)

### 11.1 Action Status Summary

| Action | Claimed Status | Audit Finding | Root Cause |
|--------|---------------|---------------|------------|
| 1. Headline Grounding | Prompt + resolver implemented | **DEFEATED** — `orchestrator.py:1676` always appends `· generic_title` | Standard path missing redundancy check (Claude CLI path has it at line 1329) |
| 2. Commander-4 Guard | Guard in role prompts | **PARTIALLY DEFEATED** — header generator embellishes freely | Claim rules only in `role_generation.py`, not `header_generation.py` |
| 3. Core Competencies 10-12 | Prompt updated | **UNDERMINED** — Section 4 always empty → only 3 sections → 6-9 keywords | Achievement grounding destroys all Section 4 skills |
| 4. Surface AI Skills | Commander-4 skills loaded | **NOT WORKING** — `lantern_skills.json` never loaded by any code | Zero references to `lantern_skills` in `src/*.py` |
| 5. Scout Negative Scoring | Implemented | **FULLY WORKING** — exact caps confirmed | N/A |
| 6. Pain Point Rebalancing | Implemented | **FULLY WORKING** — 60% target, 12 tests pass | N/A |
| 7. Tagline Evidence-First | Templates added | **PARTIALLY WORKING** — no enforcement | 2/3 MongoDB CVs lead with AI-first framing |

### 11.2 Critical New Gaps Discovered

**Gap A — Dual-title reconstruction (P1):** `orchestrator.py:1676` produces `"AI Architect · AI Architect"` for all AI jobs. Fix: port redundancy check from line 1329.

**Gap B — Lantern skills orphaned (P0):** `lantern_skills.json` has 30+ verified AI skills (LangChain, LangGraph, RAG Pipeline, Vector Search, Prompt Engineering) that are never loaded. All 3 MongoDB CVs are missing these keywords.

**Gap C — Achievement grounding too aggressive (P0):** Filters out 87/160 hard skills (54%) and 73/82 soft skills (89%). Section 4 of `ai_architect` taxonomy gets 0 matching skills. Only 9 soft skills survive: Adaptability, Agile, Blameless Postmortems, Communication, Documentation, Initiative, Innovation, Project Management, SCRUM.

**Gap D — Commander-4 guard missing from header prompt (P1):** The guard at `role_generation.py:54-62` protects role bullets but the header generator can still produce "42 multi-agent workflow plugins" (confirmed in Autodesk CV).

**Gap E — Ensemble headline bypass (P3):** `ensemble_header_generator.py:544` returns LLM headline without calling `resolve_headline()`. Low practical impact because orchestrator constructs H3 independently.

### 11.3 Priority Fix Sequence (NEW Step 6.5)

| # | Fix | File | Effort | Blocks |
|---|-----|------|--------|--------|
| 6.5a | Load `lantern_skills.json` into whitelist | `orchestrator.py` | 30 min | Section 1-3 quality |
| 6.5b | Fix Section 4 skills to use achievement-grounded terms | `role_skills_taxonomy.json` | 30 min | Section 4 appearing |
| 6.5c | Dual-title redundancy check | `orchestrator.py:1676` | 5 min | Headline quality |
| 6.5d | Commander-4 claim rules in header prompt | `header_generation.py` | 10 min | Tagline accuracy |
| 6.5e | Soft skills expansion from project files | `orchestrator.py:523` | 15 min | Governance skills |
| 6.5f | Tagline evidence-first validator | `orchestrator.py` | 45 min | Tagline quality |

**Execute 6.5a-e first (all < 30 min, high impact). Then 6.5f (requires more design).**

---

## Appendix A: File Reference (Revised)

| Step | Component | File | Change Type |
|------|-----------|------|-------------|
| 1 | **Orchestrator AI gate** | `src/layer6_v2/orchestrator.py` | Stop collapsing `ai_leadership` → `ai_architect` |
| 2 | Rule scorer | `n8n/skills/scout-jobs/src/common/rule_scorer.py` | Enhance `ai_leadership` weights + exclusions |
| 3 | Selector profiles | `n8n/skills/scout-jobs/data/selector_profiles.yaml` | Add `staff_architect` boost to 4 profiles |
| 4 | Role taxonomy | `data/master-cv/role_skills_taxonomy.json` | Add `ai_leadership` profile (correct schema) |
| 5 | Header generator | `src/layer6_v2/prompts/header_generation.py` | Add `ai_leadership` guidance + enhance `ai_architect` taglines |
| 6a | Grader | `src/layer6_v2/grader.py` | Add `ai_architect`/`ai_leadership` to `category_keywords` |
| 6b | Improver | `src/layer6_v2/improver.py` | Add AI-focused directives (roles 01-02 only) |
| 7 | Search keywords | `n8n/skills/scout-jobs/scripts/scout_linkedin_jobs.py` | Add `ai_architect_focused` profile |
| -- | ~~Role metadata~~ | ~~`data/master-cv/role_metadata.json`~~ | ~~Not needed — variant_selector already handles~~ |
| -- | ~~Skills taxonomy~~ | ~~`src/layer6_v2/skills_taxonomy.py`~~ | ~~Not needed if orchestrator gate is fixed~~ |

## Appendix B: Codex Review Prompt (Updated for Revised Plan)

```
Review the revised Agentic AI Architect focus plan report at:
reports/agentic-ai-architect-focus-plan-2026-04-11.md

This is revision 2, incorporating Codex gpt-5.4 review feedback. Verify that:

1. CORRECTIONS APPLIED
   - Orchestrator AI gate fix is now Step 1 (was missing before)
   - head_of_ai replaced with ai_leadership extension (no parallel role)
   - Taxonomy uses correct schema (static_competency_sections, identity_statement)
   - high_score and title_must_match removed from profiles (dead config / unsupported)
   - global_ai_architect profile deferred until selector supports title filters
   - Execution order is plumbing → scorer → selector → taxonomy → header → grader
   - Head of AI repositioned as selective fallback, not core target tier

2. REMAINING GAPS
   - Is the orchestrator fix in Step 1 complete? Any other downstream consumers?
   - Does the variant_selector need changes for ai_leadership?
   - Is the skills_taxonomy.py role detection updated?
   - Any test gaps?

3. CAPACITY MATH
   - Are the revised selector quotas within pipeline capacity?
   - Is 10-15/day from 681 ready pool realistic with browser automation speed?

Output: pass/fail per correction, any remaining issues.
```

---

## Appendix C: Codex gpt-5.4 Review (2026-04-12)

### Executive Summary

The plan is directionally right on one point: the strongest real asset is the existing Commander-4/Joyia work, and the current pipeline already has meaningful `ai_architect` support. But the report is materially inaccurate about how the system is wired today: it proposes a new `head_of_ai` role path even though the scout layer uses `ai_leadership`, the CV layer still hard-forces AI jobs to `ai_architect`, and the selector cannot execute some proposed profile fields at all. The application-volume math is also weak: `10-15/day` is achievable from the existing `681` ready jobs, but the proposed selector quotas can easily outstrip the documented `12-15/day` pipeline capacity without fixing the actual bottleneck. The biggest risk is spending time on taxonomy/header/grader polish before fixing upstream role detection, selector overlap, and downstream role-category coercion.

### Section Review

**1. Strategy Coherence — NEEDS_WORK**

The "Agentic AI Architect" identity does not hold cleanly across all target roles. It works for `AI Architect`, `AI Platform Architect`, `LLM Architect`, and some `Staff/Principal AI Engineer` roles. It is weaker for `AI Solutions Architect` because the report explicitly includes consultancies/customer-facing roles while also saying not to apply to sales/consultant-adjacent roles; that is a positioning conflict. It is weakest for `Head of AI`: current evidence supports "hands-on AI platform lead" more than "department head." The `70-80% apply / 20-30% learn` split is reasonable only because there are already `681` ready jobs; it is not justified by the proposed pipeline changes.

**2. Technical Accuracy — FAIL**

The proposed `head_of_ai` taxonomy block is not aligned to the current taxonomy shape in `role_skills_taxonomy.json`: existing roles use `static_competency_sections` and persona keys like `identity_statement`, not the report's simplified schema. The report also ignores that `ai_architect` already exists. In the scout layer, `rule_scorer.py` already has `ai_leadership`; adding `head_of_ai` as a parallel role would duplicate rather than extend current logic. Worse, the proposed selector profile uses `title_must_match` and `location_mode: "ignore"` even though `scout_dimensional_selector.py` only reads `quota`, `location_patterns`, `rank_boosts`, and `location_mode` in a way that does not support that filter. Finally, the report treats grader changes as role-aware, but `grader.py` currently has one global weight map and JD alignment logic with no `ai_architect`/`head_of_ai` branch.

**3. Pipeline Impact — FAIL**

`10-15/day` is achievable immediately from the ready pool; that part is fine. What is not fine is claiming the plan addresses the `12-15/day` batch bottleneck while proposing higher selector quotas. The review math in the report itself reaches potential daily quota ceilings far above capacity. Also, the pipeline currently has a separate global selector quota of `8` per run; the report never reconciles dimensional profile growth with that. The new `global_ai_architect` profile would almost certainly create heavy overlap with `eea_staff_architect` and `global_remote`, and dedupe happens only after selection pressure is created.

**4. Master CV Alignment — NEEDS_WORK**

The CV has strong AI-architecture evidence in Seven.One achievements 15-18 and the current role metadata already includes heavy AI signals. Commander-4 is being leveraged well in substance, but the report understates that the current variant selector already forces AI-specific emphasis for Seven.One. The gap is not "AI evidence missing"; it is "leadership evidence for true Head-of-AI scope is thinner than the report implies." Team evidence is `10+ mentored`, `3 promoted`, hiring, and platform leadership, which supports lead/director-lite positioning better than `Head of AI` for many markets. Taglines that imply broad governance maturity or enterprise AI leadership beyond evidenced scope risk overstating the case.

**5. Prioritization — NEEDS_WORK**

The execution order is wrong. Step 1 taxonomy work should not precede fixing role identity plumbing, because `orchestrator.py` currently overrides AI jobs to `ai_architect` anyway, which would bypass much of the proposed `head_of_ai` downstream work. Selector/schema fixes should come before quota expansion. Header/grader/improver work should follow only after upstream role detection and selector behavior are stable. Some tasks can be parallelized: search profile updates and selector ranking changes are separable from header/grader tuning.

**6. Gaps & Risks — FAIL**

The report misses the biggest dependency: if `head_of_ai` is introduced, the downstream CV pipeline must stop collapsing all AI jobs into `ai_architect`. It also misses role overlap management, selector-level false positive control, and response-rate instrumentation by role family. Quality vs quantity is under-modeled: `10-15/day` across `Tier B/C` roles can dilute application quality fast, especially for senior architect/leadership jobs where tailoring matters more than volume. The plan also assumes new Commander-4 contributions can be turned into clean CV claims quickly, but that depends on actual merged work and measured outcomes.

### Top 5 Recommendations

1. **Replace the proposed `head_of_ai` role with an extension of existing `ai_leadership` first**, or rename consistently across scout and CV layers before any new taxonomy work.
2. **Fix downstream role plumbing before anything else**: remove or refine the unconditional AI-to-`ai_architect` override in `orchestrator.py`.
3. **Do not add `global_ai_architect` until the selector supports title filters explicitly**; otherwise it is mostly a quota multiplier with overlap, not a true architect hunter.
4. **Keep the immediate application plan, but cap net new pipeline inflow** to actual batch capacity and prioritize `Tier A/B` plus a narrow slice of `Tier C`.
5. **Reposition `Head of AI` as a selective fallback**, not a core target tier, unless you add stronger org-scale evidence or real team/program ownership beyond current Commander-4 scope.

### Risk Matrix

| Risk | Likelihood | Impact |
|------|-----------|--------|
| `head_of_ai` path doesn't work end-to-end (scout uses `ai_leadership`, CV forces `ai_architect`) | HIGH | HIGH |
| Selector quota expansion overwhelms `12-15/day` pipeline bottleneck | HIGH | HIGH |
| `global_ai_architect` creates duplicate harvesting across existing profiles | HIGH | MEDIUM |
| Taglines oversell "Head of AI" relative to current evidence (interview-defensibility risk) | MEDIUM | HIGH |
| Forcing every role through AI lens degrades credibility for older roles | MEDIUM | MEDIUM |

### Specific Line-Level Corrections

1. **Part 1 fallback hierarchy**: Move `Head of AI` above `Senior AI Engineer` only if the role requires real org/team ownership; otherwise keep it as a selective side-branch, not fallback priority 5.
2. **Part 2.1A (taxonomy block)**: Rewrite to match existing taxonomy schema — use `static_competency_sections` and existing persona key names; do not introduce a parallel shape.
3. **Part 2.1B (achievement ordering)**: Partly obsolete — the current system already forces Achievement 15 and one of 16-18 for `ai_architect` via `variant_selector.py`.
4. **Part 2.2 (header guidance)**: `ROLE_GUIDANCE` dict does not exist in current codebase. Reference the actual AI guidance blocks in `prompts/header_generation.py` and fallback taglines in `header_generator.py`.
5. **Part 2.3 (grader changes)**: Remove mandatory Lantern mention — increases hallucination pressure for jobs where Commander-4 is the stronger, safer proof point.
6. **Part 2.5 (rule scorer)**: Do not add `head_of_ai` beside `ai_leadership`; either rename the existing role or extend it. The current scorer already handles head/director/vp AI titles.
7. **Part 3 (scout profiles)**: `high_score` boosts are currently dead config — `compute_rank_score()` never reads them. `title_must_match` is unsupported by the current selector implementation.
8. **Step 0 (immediate actions)**: Split "apply now" from "pipeline more" — 681 ready-to-apply and 630 unscored are different workflows.
9. **Step ordering**: Reorder to scorer/selector/orchestrator role plumbing first, then taxonomy/header, then grader/improver.
10. **Step 1 (taxonomy)**: Incomplete — the actual missing dependency is downstream support across orchestrator, variant selection, header, grader, improver, and skills taxonomy consumers.
