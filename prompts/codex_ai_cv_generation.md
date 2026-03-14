# CODEX TASK: Generate Anti-Hallucination AI Engineering CV

## OBJECTIVE

Generate a production-quality, anti-hallucination CV that positions the candidate as an **AI Engineering Expert** for AI/GenAI/LLM job applications. The Lantern project (LLM Quality Gateway + Eval Harness + Observability Stack) is the centerpiece proof of AI competence.

**Hard constraint:** Every claim must be grounded in source material. No invented metrics. No skills without evidence. Log every rejected JD skill explicitly.

---

## STEP 0: READ AND INTERNALIZE SOURCE MATERIAL

Read these files. For each, extract the specific data points listed.

### Candidate Profile & Master CV
| File | Extract |
|------|---------|
| `data/master-cv/role_metadata.json` | Candidate name, contact, 6 roles (companies, periods, achievements, hard/soft skills) |
| `data/master-cv/role_skills_taxonomy.json` | 8 target role definitions, competency sections, personas, power verbs, JD signals |
| `data/master-cv/roles/*.md` (all role files) | Every achievement with ALL variants (Architecture, Technical, Leadership, Impact, Short) |

### AI Engineering Context & Positioning
| File | Extract |
|------|---------|
| `../ai-engg/reports/07-positioning-strategy.md` | 3 positioning options (A/B/C), 4 content pillars with allocation %, recommended framing per context |
| `../ai-engg/reports/30-confidence-and-positioning-guide.md` | "80%/20%" formula, honesty framework, "what to sell vs what to know" table, "applying X to Y" bridge formula |
| `../ai-engg/reports/04-skills-analysis.md` | Top 22 skills with market demand frequencies (JD%, X signal, LinkedIn signal). Separate into: Table Stakes, Differentiators, Emerging Bets |
| `../ai-engg/reports/21-skill-gaps-mastery-map.md` | 7 credibility gaps, progression levels (Beginner/Intermediate/Advanced), completion status per gap |
| `../ai-engg/reports/10-portfolio-signature-builds.md` | Lantern Build 1-3: architecture, acceptance criteria, STAR interview stories, target metrics |
| `../ai-engg/reports/22-product-feature-scope.md` | Feature backlog by epic, effort estimates, hirability mapping per feature |
| `../ai-engg/reports/18-atomic-build-checklist.md` | Checked (✅) = completed, unchecked (☐) = remaining. This determines what can be claimed |
| `../ai-engg/reports/25-build-2-plan.md` | Build 2 scope: agent evaluators, error taxonomy, pairwise comparison, multi-agent, agentic RAG |

---

## STEP 1: REASON ABOUT AI POSITIONING (Chain of Thought)

Before generating any CV content, perform this analysis and write out your reasoning:

### 1a. The "Applying X to Y" Bridge (Report 30)

The candidate is NOT an AI researcher. They are a **production infrastructure expert applying proven skills to AI systems**. This is the core positioning principle. Construct the bridge:

- **X (already owned, 80%):** 11 years distributed systems, zero-downtime operations, observability at billions/day, compliance (€30M), team building (10+ mentored, 3 promoted), architecture governance (DDD, event-driven, microservices)
- **Y (applying to, 20% actively acquiring):** LLM evaluation pipelines, agent orchestration (LangGraph), RAG architecture, LLM observability (Langfuse), cost optimization (semantic caching, model routing), AI governance (EU AI Act)

**The CV must reflect this ratio.** 80% of claimed capability comes from proven infrastructure. 20% comes from the Lantern project and active learning. Never claim "years of AI experience" — claim "years of production systems now applied to AI."

### 1b. Market Demand Mapping (Report 04)

Map every skill you include to its market demand tier:

| Tier | Skills | JD Frequency | Rule |
|------|--------|-------------|------|
| **Table Stakes** | Python, LLM Fundamentals, RAG, AWS, Production Systems | 34-62% | Must appear in CV or no interview |
| **Differentiators** | Agentic AI, LLM Eval, AI Governance, Observability, Cost Optimization, Leadership+Architecture | 20-67% | Highlight prominently — these separate senior from mid |
| **Emerging** | Vector DBs, Agent Frameworks, Fine-tuning, MCP | 3-21% | Mention only if space and evidence |

### 1c. Lantern Completion Audit (Report 18)

**CRITICAL:** Read the atomic build checklist. For each feature:
- ✅ Checked = CAN claim as completed achievement (past tense)
- ☐ Unchecked = CANNOT claim. Use present tense ("Building...", "Designing...") or omit

This audit determines the entire project section scope. Do NOT fabricate completion.

### 1d. Positioning Selection (Report 07)

Choose the positioning variant based on the target JD:

| JD Type | Positioning | Framing |
|---------|------------|---------|
| Individual Contributor (AI Engineer, Staff) | Option A: Technical Specialist | Lead with Lantern architecture depth |
| Manager/Head/Director | Option B: Leadership + Technical | Lead with team building + AI vision |
| Consulting/Advisory | Option C: Problem-Solver | Lead with "I help companies ship LLMs that don't break" |

---

## STEP 2: AI ENGINEERING PERSONA DEFINITION

### New Role: `ai_architect`

This role does not exist in the current taxonomy. Create it with these properties:

**Identity:** Production infrastructure expert who brings engineering rigor to AI systems — evaluation, observability, cost, governance. Not an ML researcher; not a prompt engineer; an architect who makes AI work reliably at scale.

**Voice rules:**
- Speaks in metrics and outcomes, not buzzwords
- References production incidents, not research papers
- Uses: "architected", "instrumented", "evaluated", "governed", "orchestrated"
- Avoids: "explored", "experimented", "passionate about", "leveraged"

**4 Static Competency Sections:**

| Section | Name | Covers |
|---------|------|--------|
| 1 | LLM Reliability & Evaluation | Eval harnesses, golden datasets, quality gates, LLM-as-judge, regression detection, CI eval |
| 2 | Agentic AI & Orchestration | LangGraph, tool use, multi-agent systems, RAG pipelines, guardrails, agent evaluation |
| 3 | Production Operations & Observability | Langfuse tracing, Prometheus metrics, Grafana SLO dashboards, cost tracking, drift detection |
| 4 | AI Governance & Engineering Leadership | EU AI Act compliance, risk frameworks, team building, architecture decisions, mentorship |

**JD Signals (trigger this persona when JD contains):** "AI Engineer", "AI Architect", "LLM", "GenAI", "Agentic AI", "RAG", "LLM Evaluation", "AI Platform", "ML Engineer", "AI Infrastructure", "Head of AI"

---

## STEP 3: CV HEADER GENERATION

### Principle: 4-Question Framework

Every header MUST answer these 4 questions. If any is unanswered, the header fails:

| # | Question | Answered By | Source |
|---|----------|-------------|--------|
| 1 | **Who are you?** | Headline + Tagline | Identity + level from persona |
| 2 | **What problems can you solve?** | Key Achievements | Capabilities mapped to JD pain points |
| 3 | **What proof do you have?** | Quantified Metrics | ONLY from master CV or completed Lantern |
| 4 | **Why should they call you?** | Differentiation | The "applying X to Y" angle |

### 3a. Headline

**Formula:** `[EXACT JD TITLE] | [DOMAIN QUALIFIER]`

Rules:
- Use the EXACT title from the target JD (research: 10.6x more interview likelihood with exact title match, per 625 hiring manager survey)
- Calculate years: earliest role 2014 → present = 11+ years
- Domain qualifier options (choose based on JD emphasis):
  - `11+ Years Production Systems & Engineering Leadership`
  - `LLM Reliability · Evaluation · Agentic AI`
  - `Distributed Systems → AI Infrastructure`

### 3b. Identity Line / Tagline

**Hard constraints:**
- 15-25 words maximum (200 characters)
- Third-person absent voice (ZERO pronouns: I, my, me, you, your, we, our)
- Start with role/identity noun phrase
- Must encode the "applying X to Y" bridge formula from Step 1a
- Must answer both "Who are you?" AND "Why should they call you?"

**Construction algorithm:**
1. Identity noun: "Production infrastructure expert" | "Engineering leader" | "Platform architect"
2. Bridge clause: "applying [X years] of [proven domain] to [AI domain]"
3. Proof clause: reference 1-2 quantified outcomes OR the differentiation angle
4. Validate: count words (15-25), scan for pronouns (must be zero), check both questions answered

**Template variants (adapt, don't copy verbatim):**
- `"Production infrastructure leader applying 11 years of distributed systems rigor to LLM reliability, evaluation, and governance at scale."`
- `"Engineering leader building production-grade AI systems — evaluation pipelines, quality gateways, and observability stacks grounded in 11 years of enterprise platform engineering."`

### 3c. Key Achievements (5-6 Bullets)

**Format:** Past-tense action verb + quantified outcome, 8-15 words per bullet.

**Selection scoring — score each candidate bullet:**

| Factor | Weight | Source |
|--------|--------|--------|
| JD pain point addressed | 2.0x | Match bullet to JD requirements |
| JD keyword present in bullet | 0.5x | Natural keyword integration |
| Core strength alignment (from persona) | 1.5x | Maps to one of 4 competency sections |
| Recency (current role = 1.0, previous = 0.5) | 1.0x | Prefer recent achievements |

**Grounded metrics pool (ONLY select from these):**

From Seven.One:
- 75% incident reduction, 3 years zero downtime
- Observability pipeline processing billions of events/day, 10x cost reduction
- GDPR/TCF 2.0 compliance protecting €30M annual ad revenue
- 10+ engineers mentored, 3 promoted to lead positions
- CI/CD modernization: 25% delivery predictability improvement
- Developer onboarding reduced from 6 to 3 months via DDD adoption

From Samdock:
- Event-sourced CRM 0→1, 25 production tenants
- 30% sprint velocity improvement

From KI Labs:
- 35% production incident reduction
- 60% query latency improvement

From Lantern (ONLY if completed per report 18 checklist):
- LLM gateway: 99.5% availability, 25% cost reduction via semantic caching
- Eval harness: 100+ golden examples, CI quality gate
- Observability: Langfuse tracing (prompt, response, tokens, cost, latency per request)
- Fallback routing: provider switch within 2 seconds

**Formatting rule:** Front-load the most JD-relevant keyword in the first 3 words when natural:
- ✅ "Architected LLM evaluation pipeline with 100+ golden examples and CI regression gates"
- ❌ "Built a pipeline that evaluates LLM quality" (keyword buried)

### 3d. Core Competencies (4 Sections)

**Algorithm:**

1. Load the 4 section names from ai_architect persona (Step 2)
2. For each section, score all candidate skills:
   - Base score: 1.0 (skill exists in candidate whitelist)
   - JD match boost: +2.0 (skill keyword appears in target JD)
   - Annotation boost: +1.5 (skill emphasized in JD requirements section)
3. Select top 6-8 skills per section by score
4. **WHITELIST ENFORCEMENT:** Skills MUST exist in candidate's master CV hard_skills/soft_skills OR in completed Lantern features. Never add a JD skill the candidate doesn't have evidence for.
5. **Log rejected JD skills:** If JD requires "Kubernetes" but candidate has no K8s, log: "REJECTED: Kubernetes — no evidence in candidate profile"
6. Ensure at least 50% of selected skills per section match JD keywords

---

## STEP 4: EXPERIENCE BULLETS (ARIS Format)

### Bullet Format: Action → Result → Impact → Situation

`[Action verb] [what was done], [quantified result] [in what context/situation]`

Example: "Architected event-driven observability pipeline processing billions of events daily to OpenSearch, reducing infrastructure costs by 10x through real-time alerting and automated incident detection"

### Role-Specific Emphasis by Career Stage

| Role | Stage | Bullet Count | Emphasis | Variant Preference |
|------|-------|-------------|----------|-------------------|
| **Lantern Portfolio** | Current project | 4-5 | AI depth: eval, observability, RAG, agents, production controls | Technical, Architecture |
| **Seven.One** | Current (5yr, primary) | 5-6 | Architecture + leadership + scale + AI bridge | Architecture first, then Leadership |
| **Samdock** | Previous (1yr) | 3-4 | Event sourcing, 0→1, startup velocity | Technical, Impact |
| **KI Labs** | Earlier (1yr) | 2-3 | Data pipelines, testing discipline | Impact, Short |
| **OSRAM** | Earlier (2yr) | 2-3 | IoT/protocol (relevant for IoT+AI roles) | Technical, Short |
| **Clary Icon** | Earliest (2yr) | 2 | Real-time, cross-platform | Short |

### Seven.One AI Bridge Bullets

For the Seven.One role, generate 1-2 bullets that bridge platform engineering to AI. These must be grounded in real work:

**Grounded bridges:**
- Observability pipeline (billions/day) → maps to LLM observability (same architecture patterns)
- Auto-scaling with traffic classification → maps to model routing / intelligent decisioning
- GDPR/TCF compliance (€30M) → maps to AI governance (EU AI Act)
- CI/CD modernization → maps to eval gates in CI

**DO NOT fabricate AI work at Seven.One.** Instead, frame the infrastructure work as directly transferable: "Architected real-time observability pipeline processing billions of events daily — the same architectural patterns now applied to LLM request tracing and quality monitoring"

### Bullet Validation Rules

- [ ] Every bullet starts with a past-tense action verb from ai_architect power verbs
- [ ] Every metric is EXACT from source (no rounding: "75%" not "~75%", "10x" not "roughly 10x")
- [ ] Zero pronouns (no "I", "my", "we", "our")
- [ ] 20-35 words per bullet
- [ ] JD terminology mirrored naturally (not forced)
- [ ] No skill mentioned that isn't in candidate whitelist

---

## STEP 5: LANTERN PROJECT SECTION

### Section Pattern

Position the Lantern project as a dedicated section BETWEEN the header and professional experience. This is the "proof bridge" between the candidate's positioning claims and their historical experience.

```
[HEADER: Headline + Tagline + Key Achievements + Core Competencies]

[LANTERN PROJECT SECTION] ← HERE

[PROFESSIONAL EXPERIENCE: Seven.One → Samdock → KI Labs → ...]
```

### Project Section Template

```
**[Project Name]** (Portfolio — GitHub: github.com/taimooralam/lantern)
- [Bullet 1: Core gateway/proxy capability]
- [Bullet 2: Evaluation pipeline capability]
- [Bullet 3: Observability/monitoring capability]
- [Bullet 4: RAG/agent capability]
- [Bullet 5: Production controls / governance]
Stack: [technology list]
```

### Conditional Content Based on Build Phase

**Check report 18 checklist completion status, then include ONLY completed features:**

#### If Build 1 (Prototype 1) is complete:
Include: LLM Quality Gateway (FastAPI proxy, semantic caching, multi-provider routing, fallback chains), evaluation pipeline (100+ golden examples, LLM-as-judge, CI regression gates), observability stack (Langfuse tracing, Prometheus metrics, Grafana SLO dashboards), DocAssist consumer app (RAG pipeline, hybrid search, source citations), cost tracking per request

#### If Build 2 (Prototype 2) is also complete:
Add: Agent evaluators (6 types: tool selection, plan quality, task completion, error propagation, reflection effectiveness, coherence), error taxonomy classifier, pairwise comparison evaluator (position-bias measurement), multi-agent orchestration (delegation, shared state, guardrails), agentic RAG (query decomposition + iterative retrieval), cost-quality Pareto analysis

#### If Build 3 is also complete:
Add: Open-source LLM operations playbooks (6+ runbooks), GameDay scenarios (4+), EU AI Act compliance mapping (Article 12 logging), SLO definitions with error budgets, model card templates

### Project Bullet Rules

1. Past tense for completed features: "Architected...", "Implemented...", "Built..."
2. Present tense for in-progress: "Building...", "Designing..." (use sparingly, max 1)
3. Each bullet maps to a Lantern epic from report 22
4. Stack line demonstrates technology breadth: `FastAPI, LangGraph, LiteLLM, Redis, Langfuse, Prometheus, Grafana | Python, Pydantic V2, pytest`
5. Project section should touch ALL 4 content pillars: Eval (P1), Operations (P2), Architecture (P3), Governance (P4)

---

## STEP 6: VALIDATE (5-Dimension Grading)

### Grading Rubric

Score the generated CV across 5 dimensions. Composite score MUST exceed **8.5/10** to pass.

| Dimension | Weight | Scoring Criteria |
|-----------|--------|-----------------|
| **ATS Optimization** | 0.20 | Top JD keywords appear 2-3 times across all components. Acronyms expanded on first use (e.g., "Retrieval-Augmented Generation (RAG)"). Exact JD title in headline. |
| **Impact Clarity** | 0.25 | Every bullet has a quantified metric. Action verbs are specific (not "managed" or "worked on"). Results > responsibilities. |
| **JD Alignment** | 0.25 | JD pain points explicitly addressed. JD terminology mirrored. Must-have requirements mapped to evidence. |
| **Executive Presence** | 0.15 | Strategic framing appropriate for role seniority. Leadership evidence proportional to role level. Vision articulated for senior roles. |
| **Anti-Hallucination** | 0.15 | Every metric traces to source. No invented skills. Whitelist enforced. Lantern claims match checklist completion. "80/20 formula" respected. |

### Anti-Hallucination Final Checklist

Before outputting the CV, verify:

- [ ] Every metric appears verbatim in source material (master CV roles OR completed Lantern features)
- [ ] No skills added that aren't in candidate's hard_skills/soft_skills whitelist OR completed Lantern stack
- [ ] Lantern claims match ✅ checked items in report 18 (unchecked = not claimable)
- [ ] Zero instances of "X years of AI experience" (candidate has 11yr infrastructure, ~1yr AI focus)
- [ ] The "80/20 formula" is respected: 80% proven infrastructure, 20% AI-specific via Lantern
- [ ] Zero pronouns in tagline, key achievements, and competency sections
- [ ] Rejected JD skills are logged with reason ("REJECTED: [skill] — no evidence in profile")
- [ ] Every key achievement traces to a specific role file and achievement number

---

## OUTPUT FORMAT

Generate these 5 deliverables:

### Deliverable 1: Reasoning Trace
Your chain-of-thought analysis from Steps 1a-1d. Show:
- The X→Y bridge constructed
- Market demand mapping applied
- Lantern completion audit results
- Positioning variant selected for the target JD

### Deliverable 2: Role Taxonomy Definition
JSON object for the `ai_architect` role to add to `role_skills_taxonomy.json`. Include: display_name, static_competency_sections (4), persona, power_verbs, jd_signals.

### Deliverable 3: CV Header
- Headline (formula-based, exact JD title)
- Identity line / tagline (15-25 words, third-person absent, validated)
- 5-6 key achievements (quantified, scored, sourced)
- 4 core competency sections (whitelist-validated, JD-matched)

### Deliverable 4: Lantern Project Section + Enhanced Experience Bullets
- Project section scoped to completion status
- Seven.One: 5-6 bullets with AI bridge where grounded
- Other roles: bullet count per career stage table

### Deliverable 5: Validation Report
- 5-dimension scores with justification
- Anti-hallucination checklist (all items checked)
- Rejected JD skills log with reasons
- Source traceability table: each achievement → source file:line

---

## REFERENCE: GROUNDED METRICS POOL

These are the ONLY metrics you may use. They come from the candidate's master CV and completed Lantern features.

### From Seven.One Entertainment (2020–Present)
| Metric | Context |
|--------|---------|
| 75% incident reduction | Legacy → modern platform migration |
| 3 years zero downtime | Production reliability achievement |
| Billions of events/day | Observability pipeline scale |
| 10x cost reduction | Infrastructure optimization |
| €30M annual ad revenue protected | GDPR/TCF 2.0 compliance |
| 10+ engineers mentored | Team development |
| 3 promoted to lead positions | Leadership development |
| 25% delivery predictability improvement | CI/CD modernization |
| 6→3 months developer onboarding | DDD adoption impact |
| 20% missed impressions reduction | Auto-scaling for bursty traffic |

### From Samdock/Daypaio (2019–2020)
| Metric | Context |
|--------|---------|
| 25 production tenants | 0→1 SaaS launch |
| 30% sprint velocity improvement | Agile practice refinement |
| 85% code coverage | Testing discipline |
| 40% bug reduction | Quality improvement |

### From KI Labs (2018–2019)
| Metric | Context |
|--------|---------|
| 35% production incident reduction | Testing approach |
| 60% query latency improvement | Data layer optimization |

### From OSRAM (2016–2018)
| Metric | Context |
|--------|---------|
| CoAP reference implementation | Adopted as team standard |
| EU-funded OpenAIS project | Enterprise IoT context |

### From Lantern Project (CONDITIONAL — check report 18)
| Metric | Claimable When |
|--------|---------------|
| 99.5% availability | Build 1 gateway complete |
| 25% cost reduction (semantic caching) | Build 1 caching epic complete |
| 100+ golden evaluation examples | Build 1 eval epic complete |
| CI quality gate blocks regressions | Build 1 eval CI integration complete |
| Langfuse tracing per request | Build 1 observability epic complete |
| Provider fallback within 2 seconds | Build 1 routing epic complete |
| F1 > 0.85 tool selection accuracy | Build 2 agent eval complete |
| 60% failures from tool selection | Build 2 error taxonomy complete |
| 6 runbooks, 4 GameDay scenarios | Build 3 playbook complete |
| EU AI Act Article 12 mapping | Build 3 governance complete |

### Market Demand Frequencies (Report 04 — for keyword prioritization)
| Skill | JD% | LinkedIn% | Priority |
|-------|------|-----------|----------|
| Python | 62% | 42% | Table Stakes |
| AWS | 59% | 23.5% | Table Stakes |
| Production Systems | 55%+ | — | Table Stakes |
| LLM Fundamentals | 50%+ | 48% | Table Stakes |
| Leadership+Architecture | 67% | — | Top Differentiator |
| Agentic AI | 46% | 28.6% | Differentiator |
| RAG | 34% | 34.5% | Table Stakes |
| AI Governance | 15-20% | 34.5% | Differentiator (rising) |
| LLM Eval | 30-35% | 31.9% | Differentiator |
| Observability | 25-30% | — | Differentiator |
| Cost Optimization | 20-25% | — | Differentiator |
| Vector DBs | — | 21% | Emerging |
| Agent Frameworks | — | 16.8% | Emerging |
| Fine-tuning | 20-25% | 18.5% | Emerging |
| MCP | 5-10% | 3.4% | Emerging |
