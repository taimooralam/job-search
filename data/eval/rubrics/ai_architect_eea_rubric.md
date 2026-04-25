# AI Architect — EEA — Eval Rubric

## Meta
- Category ID: ai_architect_eea
- Macro family: ai_architect
- Priority: primary_target
- Confidence: medium
- Rubric version: 2026-04-17

## Identity
- Purpose: Evaluate CV fit for senior AI architect and player-coach roles in EEA markets that require enterprise AI solution architecture, governed agentic delivery, and strong stakeholder translation without executive or heavy people-management framing.
- Core persona: Senior architect or player-coach who translates complex enterprise requirements into governed AI blueprints and delivery roadmaps, combining platform design, production reliability, and cross-functional collaboration.
Job overlay notes:
- Adjust keyword density based on whether the JD emphasizes agentic workflows, governance, or platform modernization
- Calibrate cloud-provider mentions to match the JD; do not pad multi-cloud claims beyond evidence
- EEA roles may require GDPR or EU AI Act awareness; use only when JD specifies and evidence supports
- Player-coach vs pure IC framing should match JD signals on mentoring and technical leadership scope
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

## Dimension Rubrics
### ats_optimization (weight 20)
**Layer A — Category core**
What good looks like:
- Architecture keywords appear 2-3 times across headline, profile, and experience: 'AI solutions architecture', 'enterprise architecture', 'platform design'
- Governed AI terms present 2-3 times if evidenced: 'agent orchestration', 'agentic AI', 'guardrails', 'AI governance'
- Production delivery language appears throughout: 'production-grade', 'delivery', 'implementation roadmap'
- Stakeholder translation vocabulary surfaces: 'stakeholder management', 'requirements translation', 'roadmap'
- Cloud terms used narrowly and only when evidenced; no multi-cloud padding
Common failures:
- Generic leadership terms dominate over architecture-specific vocabulary
- Prompt engineering or fine-tuning centered when category rewards workflow architecture
- Compliance acronyms stacked without matching delivery evidence
- Tool names repeated excessively without architecture context
- Missing agent orchestration and guardrails vocabulary despite category signal
**Layer B — Job-specific overlay**
Adjust per JD:
- Match cloud provider emphasis to JD: Azure, AWS, or multi-cloud as specified
- If JD mentions specific frameworks like LangChain or Semantic Kernel, include once if evidenced
- Adjust governance vocabulary density based on whether JD emphasizes compliance or delivery
Company/domain overrides:
- Consulting firms: emphasize client-facing delivery and solution shaping vocabulary
- Product companies: emphasize platform ownership and internal scale vocabulary
- Regulated industries: include narrow compliance terms only when JD requires and CV proves
Region overrides:
- EEA roles may value GDPR or EU AI Act terms; use sparingly and only with evidence
- German roles may benefit from explicit reliability and governance vocabulary
**Score anchors**
- 9-10:
  - All table-stakes keywords appear 2-3 times with natural distribution
  - Architecture-first vocabulary dominates over generic engineering terms
  - Governed AI and production delivery terms present and contextually appropriate
  - Zero keyword stuffing; all terms tied to concrete evidence
- 7-8:
  - Most table-stakes keywords present with good distribution
  - Architecture vocabulary clear but could be stronger in headline or summary
  - Governance or agent orchestration terms present but underweighted
- 5-6:
  - Some architecture keywords present but inconsistent distribution
  - Generic engineering or leadership terms compete with architecture vocabulary
  - Missing key category signals like guardrails or agent orchestration
- <=4:
  - Architecture vocabulary largely absent or drowned by generic terms
  - Prompt engineering or model training centered despite category mismatch
  - Keyword stuffing visible or compliance acronym padding without evidence
Red flags:
- Multi-cloud expert claims across all major providers without evidence
- Prompt engineering or fine-tuning specialist framing
- Compliance acronym stacking without delivery proof
- Tool-name repetition without architecture context
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

### impact_clarity (weight 25)
**Layer A — Category core**
What good looks like:
- Achievement bullets follow STAR or ARIS format with quantified outcomes
- Metrics tied to architecture outcomes: reliability improvement, incident reduction, adoption scale, time-to-production
- Governance impact quantified: guardrail coverage, policy pass rate, failure-rate reduction
- Delivery acceleration shown: deployment frequency, release cycle improvement, team enablement
- Cost-aware decisions evidenced with numbers: cost reduction, unit-cost improvement, build-vs-buy savings
Common failures:
- Vague responsibility statements without measurable outcomes
- Metrics disconnected from architecture or delivery impact
- Generic percentages without baseline or context
- Activity lists masquerading as achievements
- Impact claimed at wrong scope level (team work claimed as individual achievement)
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD emphasizes scale, foreground user counts, system throughput, or deployment scope
- If JD emphasizes governance, quantify compliance coverage, audit outcomes, or risk reduction
- If JD emphasizes cost efficiency, surface cost metrics and efficiency gains
Company/domain overrides:
- Enterprise contexts value reliability metrics: uptime, SLO attainment, incident reduction
- Product contexts value adoption and engagement metrics
- Consulting contexts value delivery velocity and client outcome metrics
Region overrides:
- EEA contexts may value data protection compliance outcomes
- German contexts may appreciate engineering precision and reliability metrics
**Score anchors**
- 9-10:
  - 3+ achievements with concrete metrics tied to architecture or delivery outcomes
  - STAR/ARIS structure clear with situation, action, and quantified result
  - Metrics span reliability, scale, governance, and cost dimensions appropriately
  - All numbers verifiable against CV context; no orphan percentages
- 7-8:
  - 2-3 achievements with metrics; some strong, some could be sharper
  - Most bullets show clear cause-effect between action and outcome
  - Minor gaps in metric coverage across key dimensions
- 5-6:
  - 1-2 quantified achievements but others vague or activity-focused
  - Metrics present but disconnected from architecture impact
  - Some STAR structure but results section often weak
- <=4:
  - No quantified achievements or metrics clearly fabricated
  - Activity lists without outcomes dominate experience section
  - Impact language present but no supporting evidence
Red flags:
- Metrics that cannot be verified against role scope or timeline
- Round-number percentages without baseline context
- Claiming outcomes for work done by others without attribution
- Revenue or P&L metrics claimed without direct ownership evidence
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

### jd_alignment (weight 25)
**Layer A — Category core**
What good looks like:
- Platform and solution architecture evidence matches category anchor of 100% platform design signal
- Agent orchestration and guardrails governance evidence present for categories showing 60% signal
- Communication and stakeholder management evidence strong for 90% and 70% category signals
- Production delivery and reliability evidence matches category delivery emphasis
- IC or player-coach scope matches category bias away from manager-heavy framing
Common failures:
- Manager or executive framing when category favors IC/player-coach scope
- Model training or fine-tuning emphasis when category rewards workflow architecture
- Missing governance and guardrails evidence despite category signal
- Pure engineering framing without architecture decision evidence
- Consulting-leader or executive framing without supporting evidence
**Layer B — Job-specific overlay**
Adjust per JD:
- Weight greenfield vs brownfield evidence based on JD emphasis
- Adjust agent orchestration prominence based on JD agentic workflow signals
- Match stakeholder translation evidence to JD customer-facing or internal-facing emphasis
Company/domain overrides:
- Consulting JDs: emphasize client-facing requirement shaping and solution delivery
- Product JDs: emphasize platform ownership and internal stakeholder alignment
- Enterprise JDs: emphasize governed delivery and integration complexity
Region overrides:
- EEA JDs may require explicit privacy-aware delivery evidence
- Sovereign AI mentions require narrow compliance framing with evidence
**Score anchors**
- 9-10:
  - All category table-stakes signals evidenced: platform design, agent orchestration, guardrails, delivery, stakeholder translation
  - IC or player-coach scope clearly demonstrated without manager inflation
  - Differentiators present: greenfield+brownfield, evaluation, cost-aware decisions
  - Evidence directly maps to JD requirements with minimal gaps
- 7-8:
  - Most table-stakes signals present with good evidence
  - Scope framing appropriate but could be sharper
  - 1-2 differentiators present; others implicit or missing
- 5-6:
  - Some table-stakes present but gaps in governance or stakeholder translation
  - Scope framing ambiguous between IC, player-coach, and manager
  - Limited differentiator evidence
- <=4:
  - Major table-stakes missing: architecture, governance, or delivery
  - Scope framing misaligned with category bias
  - Evidence suggests different category fit entirely
Red flags:
- Executive or director framing when category signals IC/player-coach
- Prompt engineering or fine-tuning centered when category rewards architecture
- Missing platform design or architecture evidence entirely
- Pure management framing without technical architecture ownership
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

### executive_presence (weight 15)
**Layer A — Category core**
What good looks like:
- Architectural authority demonstrated through platform design ownership, reference architectures, and target-state blueprints
- System ownership evidenced by production responsibility, governance controls, and operational accountability
- Stakeholder translation shown through cross-functional collaboration, requirements shaping, and roadmap delivery
- Technical leadership via mentoring, architecture reviews, standards setting, and north-star direction
- Player-coach scope with hands-on contribution alongside team enablement
Common failures:
- C-suite, boardroom, or P&L language when category rewards architect scope
- Direct-reports or org-building claims without supporting evidence
- Generic leadership adjectives without concrete authority examples
- Confusing seniority with management hierarchy
- Executive-presentation framing when category values technical translation
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD mentions technical leadership, emphasize architecture reviews, mentoring, standards
- If JD mentions customer-facing, emphasize stakeholder translation and requirement shaping
- If JD mentions team lead, show player-coach scope without inflating to manager
Company/domain overrides:
- Consulting contexts: emphasize client-facing authority and solution shaping
- Product companies: emphasize platform ownership and cross-team coordination
- Startups: show end-to-end ownership without implying enterprise hierarchy
Region overrides:
- EEA contexts may value collaborative decision-making framing over directive language
**Score anchors**
- 9-10:
  - Clear architectural authority through named platforms, blueprints, or reference architectures
  - Production ownership with accountability for governance, reliability, and delivery
  - Stakeholder translation evidenced with specific cross-functional outcomes
  - Player-coach leadership with mentoring and standards-setting evidence
- 7-8:
  - Good architectural authority evidence but could be more specific
  - System ownership present; stakeholder translation somewhat implicit
  - Technical leadership shown but mentoring or reviews underweighted
- 5-6:
  - Some authority evidence but scope unclear or inconsistent
  - Ownership language present without concrete platform or system examples
  - Leadership framing generic rather than architecture-specific
- <=4:
  - No architectural authority evidence; pure execution framing
  - Executive or manager claims without IC/player-coach substance
  - Leadership language inflated beyond evidenced scope
Red flags:
- Unsupported people-management framing or direct-report claims
- P&L, budget ownership, or commercial accountability claims without evidence
- Executive, director, or VP scope claimed when evidence shows architect scope
- Org-building or hiring-owner claims when category shows 10% hiring signal
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

### anti_hallucination (weight 15)
**Layer A — Category core**
What good looks like:
- All metrics traceable to specific roles, projects, or timelines in the CV
- Titles match documented role history without inflation
- Technical claims scoped to evidenced experience without extrapolation
- Cloud and tool claims limited to platforms actually used
- Governance and compliance claims tied to specific delivery evidence
Common failures:
- Metrics invented or extrapolated beyond evidence scope
- Title inflation: architect claims without architecture ownership evidence
- Multi-cloud expert claims across all providers without platform-specific evidence
- Fine-tuning or model training claims when work was inference or workflow architecture
- Compliance program ownership claimed when evidence shows delivery participation only
**Layer B — Job-specific overlay**
Adjust per JD:
- Verify any JD-specific tool or framework claims against actual CV evidence
- Confirm compliance or certification claims match JD requirements with evidence
- Check scale metrics align with company size and role scope in evidence
Company/domain overrides:
- Enterprise claims: verify scale metrics plausible for stated company context
- Startup claims: confirm ownership scope against typical startup team sizes
- Consulting claims: verify client outcome metrics against engagement scope
Region overrides:
- EEA compliance claims: verify GDPR or EU AI Act evidence exists before including
- Language requirements: do not claim language proficiency beyond evidence
**Score anchors**
- 9-10:
  - All claims verifiable against CV evidence with clear provenance
  - Zero unsupported metrics, titles, or scope inflation
  - Technical claims precisely scoped to evidenced work
  - Compliance and governance claims narrowly tied to delivery evidence
- 7-8:
  - Nearly all claims verifiable; minor ambiguities in 1-2 areas
  - Titles accurate; technical scope mostly precise
  - No major hallucination risks; minor tightening could help
- 5-6:
  - Some claims verifiable but 2-3 areas ambiguous or stretched
  - Title or scope framing somewhat inflated beyond evidence
  - Metrics present but some difficult to trace to specific evidence
- <=4:
  - Multiple unsupported claims or fabricated metrics
  - Title inflation clear: executive claims without executive evidence
  - Technical claims contradict or exceed evidence scope
  - Compliance ownership claimed without delivery proof
Red flags:
- Fabricated or unverifiable metrics without evidence anchor
- Title inflation: director/VP/executive when evidence shows architect/lead
- PhD or publication claims in category where research_heavy_pct is 0.0
- Fine-tuning, RLHF, or model training claims without pipeline ownership evidence
- Deep multi-cloud expertise across AWS, Azure, GCP, and IBM without explicit evidence
- Power Platform, Copilot Studio, Purview, or DLP specialist claims without delivery proof
- GDPR, EU AI Act, or governance program ownership without direct accountability evidence
- Unsupported direct-report counts or team-size claims
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

## Gates
### must_have_coverage_gate
Pass criteria:
- Platform or solution architecture evidence present with concrete examples
- Production delivery evidence with measurable outcomes
- Stakeholder translation or communication evidence demonstrated
- At least one governed AI signal present: agent orchestration, guardrails, evaluation, or access control
Fail conditions:
- No platform or architecture design evidence anywhere in CV
- Pure execution or coding role framing without architecture decisions
- No production delivery or implementation evidence
- No stakeholder-facing or cross-functional collaboration evidence
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

### unsafe_claim_gate
Pass criteria:
- All metrics traceable to evidence sources
- Titles consistent with documented role history
- Technical claims scoped to evidenced platforms and tools
- Leadership claims match IC/player-coach category expectation
Fail conditions:
- Fabricated metrics or percentages without evidence anchor
- Title inflation to executive, director, or VP without evidence
- Fine-tuning, RLHF, or model training claims without pipeline evidence
- Multi-cloud expert claims across all providers without evidence
- Formal governance or compliance program ownership without accountability evidence
- P&L, budget, or commercial ownership claims without direct evidence
- Direct-report or hiring-owner claims exceeding category 10% signal
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

### persona_fit_gate
Pass criteria:
- IC or player-coach scope clear in framing and evidence
- Architecture-first positioning with delivery backing
- Technical leadership through mentoring, reviews, or standards evident
- Stakeholder translation without executive framing
Fail conditions:
- Executive, director, or management-heavy framing dominates
- Pure engineering or coding role framing without architecture scope
- Research, publication, or PhD-centric positioning when category shows 0% research signal
- Prompt engineering or fine-tuning specialist identity when category rewards workflow architecture
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

## Verdict Thresholds
- STRONG_MATCH >= 8.5
- GOOD_MATCH   >= 7.0
- NEEDS_WORK   >= 5.5
- WEAK_MATCH   <= 5.49

## Scoring Guidance
- Executive presence: For this architect category, executive_presence means architectural authority and system ownership—platform design, governance controls, production AI integration, stakeholder translation—NOT direct-reports, C-suite access, P&L ownership, or formal management hierarchy. Reward evidence of reference architectures, architecture reviews, north-star direction, mentoring, and cross-functional collaboration. Penalize unsupported people-management framing or executive title inflation.
- Unsupported claims: Deduct 1-2 points per dimension for each unsupported claim: fabricated metrics without evidence anchor, title inflation beyond documented history, technical scope claims exceeding evidenced work, compliance ownership without delivery proof. Multiple unsupported claims in anti_hallucination should floor that dimension at 4 or below. Gate failures from unsafe claims should trigger automatic needs_work or weak_match verdict regardless of dimension scores.
- Category vs job tradeoffs: Category signals establish baseline expectations; JD-specific signals adjust weighting within those baselines. When JD emphasizes something the category underweights (e.g., specific compliance), give credit if evidenced but do not penalize its absence. When JD de-emphasizes a category table-stake, still require evidence but reduce weight. Never inflate claims to match JD requirements beyond available evidence.
Citations:
- data/eval/blueprints/ai_architect_eea_blueprint.json
- data/eval/baselines/ai_architect_eea_baseline.json

## Evidence Ledger
- [high] Platform design is the category anchor and must appear in CV
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] Agent orchestration and guardrails governance are table-stakes with 60% category signal
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] Communication and stakeholder management are critical soft skills at 90% and 70% signals
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] IC and player-coach scope preferred over manager scope (4/10 each vs 2/10)
  - data/eval/blueprints/ai_architect_eea_blueprint.json
  - data/eval/baselines/ai_architect_eea_baseline.json
- [high] Hiring and performance management are weak signals at 10% each; do not reward management-heavy framing
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] Prompt engineering and fine-tuning are not category differentiators (0% and 10%)
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] Research-heavy and PhD requirements are 0% in this category
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] Budget/P&L ownership, formal hiring/performance responsibility, and deep multi-cloud claims are unsafe without explicit evidence
  - data/eval/blueprints/ai_architect_eea_blueprint.json
  - data/eval/baselines/ai_architect_eea_baseline.json
- [high] Delivery and reliability are valued evidence types at 9/10 in deep analysis
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [medium] Greenfield and brownfield scope both appear in 8/10 jobs; reward architects who demonstrate both
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [medium] GDPR appears in 2/10 and EU AI Act in 1/10; use compliance terms only with narrow evidence
  - data/eval/blueprints/ai_architect_eea_blueprint.json
- [high] Solutions Architect and AI Architect are the safe title families (6/10 and 4/10)
  - data/eval/blueprints/ai_architect_eea_blueprint.json
