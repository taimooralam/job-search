# Tech Lead AI — EEA — Eval Rubric

## Meta
- Category ID: tech_lead_ai_eea
- Macro family: ai_engineering_adjacent
- Priority: secondary_target
- Confidence: high
- Rubric version: 2026-04-17

## Identity
- Purpose: Evaluate CV fit for player-coach AI tech lead roles requiring Python backend architecture, production AI/LLM integration, and mentoring without formal management scope.
- Core persona: Hands-on technical lead who architects Python backend and AI-enabled platforms, ships production-grade systems, mentors engineers, and leads through code quality and delivery discipline rather than org-chart authority.
Job overlay notes:
- Stack variance: Python framework depth (FastAPI vs Flask vs Django) varies by employer; adjust weight if JD specifies one
- Domain variance: enterprise SaaS, media/entertainment, fintech each have different compliance and scale expectations
- AI depth variance: some roles emphasize RAG/evaluation, others want basic LLM API integration only
- Team size variance: player-coach scope ranges from 3-person pods to 15-person distributed teams
- Region variance: EEA roles may require GDPR awareness even when not explicitly stated
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json

## Dimension Rubrics
### ats_optimization (weight 20)
**Layer A — Category core**
What good looks like:
- Python appears 2-3 times across headline, profile, experience, and skills when true
- Tech Lead or Technical Lead title appears in headline rather than Architect or Manager
- Backend architecture and platform design keywords appear 2-3 times
- AI/LLM integration keywords appear alongside backend terms, not standalone
- Production readiness, CI/CD, reliability keywords appear 1-2 times
- Mentoring, collaboration, communication appear as leadership signals
- Secondary stack terms (FastAPI, Kafka, distributed systems) appear once each only when evidenced
Common failures:
- TypeScript or JavaScript dominates when Python should be foregrounded for this category
- Architect headline when Tech Lead better matches 75.6% category title family
- GenAI or AI expert standalone without backend/platform anchoring
- Tool-list stacking: every framework named once without depth proof
- Engineering Manager framing without hiring/performance scope evidence
- Missing production readiness or delivery keywords entirely
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD emphasizes FastAPI, ensure FastAPI appears if evidenced; do not add if not
- If JD names specific cloud (AWS/Azure/GCP), match that cloud in skills; do not claim multi-cloud
- If JD emphasizes evaluation or RAG, surface those terms more prominently
- If JD names specific LLM providers (OpenAI, Anthropic), match only those you used
Company/domain overrides:
- Enterprise SaaS: add integration, workflow, multi-tenant if evidenced
- Media/entertainment: add content, metadata, pipeline if evidenced
- Fintech: add compliance, audit, transaction only if truly relevant
Region overrides:
- EEA roles: GDPR awareness may be implicit; surface data privacy if you have it
- German-speaking markets: German language proficiency worth surfacing if true
**Score anchors**
- 9-10:
  - Python, backend, tech lead each appear 2-3 times naturally across CV
  - AI/LLM integration keywords paired with architecture and delivery terms
  - Production readiness, CI/CD, reliability, mentoring all represented
  - No keyword stuffing; each term appears with contextual evidence
  - Title framing matches tech_lead family without inflation
- 7-8:
  - Python appears but underweighted relative to TypeScript or other languages
  - Most category keywords present but distribution uneven
  - Tech Lead title used but architecture or AI terms slightly overemphasized
  - Minor keyword gaps in delivery or mentoring signals
- 5-6:
  - Python barely mentioned or absent despite being required
  - Architect or Manager title framing without supporting evidence
  - AI keywords dominate without backend or platform grounding
  - Multiple high-value keywords (production readiness, mentoring) missing
- <=4:
  - Core keywords (Python, tech lead, backend, AI integration) largely absent
  - Title inflation: Director, VP, Head of AI without scope evidence
  - Generic developer keywords without category-specific signals
  - Keyword stuffing with no contextual backing
Red flags:
- Engineering Manager headline without hiring/performance evidence
- AI Architect headline when actual work was hands-on tech lead
- Multi-cloud expert claims without evidence for each platform
- Every Python framework named (FastAPI, Django, Flask) without production depth
- GenAI buzzwords without backend or delivery context
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json

### impact_clarity (weight 25)
**Layer A — Category core**
What good looks like:
- Architecture-led achievements show design decision plus measurable production impact
- Production readiness gains quantified: incident reduction %, uptime, deployment frequency
- Scale and reliability metrics: latency, throughput, availability, error rate
- Delivery metrics: cycle time, estimation accuracy, release predictability
- AI feature impact: adoption rate, quality scores, cost/latency tradeoffs
- Mentoring impact: engineers coached, promotions influenced, team velocity gains
- STAR or ARIS structure: situation/task, action with technical specifics, measurable result
Common failures:
- Architecture described without production outcomes or metrics
- Feature delivery listed without reliability or quality impact
- Led team without delivery or quality outcomes attached
- AI work described without evaluation or production adoption metrics
- Mentoring claimed without engineer outcomes or team improvements
- Vague scale terms (large-scale, enterprise) without numbers
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD emphasizes reliability/SLA: foreground uptime, incident metrics
- If JD emphasizes delivery speed: foreground cycle time, deployment frequency
- If JD emphasizes AI quality: foreground evaluation scores, error reduction
- If JD emphasizes team growth: foreground mentoring outcomes
Company/domain overrides:
- Enterprise B2B: user counts, integration counts, workflow automation rates
- Consumer-facing: DAU/MAU impact, response latency, feature adoption
- Platform/infrastructure: API call volumes, processing throughput, cost efficiency
Region overrides:
- EEA compliance contexts: audit pass rates, compliance metrics if applicable
**Score anchors**
- 9-10:
  - Every major role has 2+ quantified achievements with STAR structure
  - Architecture decisions tied to measurable production impact (latency, uptime, cost)
  - AI integration achievements include adoption, quality, or efficiency metrics
  - Mentoring shows engineer-level outcomes (promotions, capability gains)
  - Delivery achievements show before/after with timeline or velocity metrics
- 7-8:
  - Most roles have quantified achievements but some lack full STAR context
  - Architecture impact present but metrics sometimes vague (improved vs 40% reduction)
  - AI or mentoring achievements present but not all quantified
  - One strong role dominates; earlier roles underdetailed
- 5-6:
  - Some metrics present but many achievements are responsibility descriptions
  - Architecture mentioned but production impact unclear
  - AI work lacks evaluation or adoption metrics
  - Mentoring claimed without specific outcomes
- <=4:
  - Achievements read as job descriptions rather than impact statements
  - No quantified metrics across roles
  - Architecture, AI, and leadership claims all unsubstantiated
  - Vague terms dominate: improved, enhanced, contributed to
Red flags:
- Round-number metrics without context (100% improvement, 10x scale)
- Metrics impossible to attribute (company revenue figures for IC role)
- AI impact claims without evaluation or adoption numbers
- Led X engineers without team outcome metrics
- Scale claims without throughput, latency, or availability numbers
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json
- data/master-cv/roles/01_seven_one_entertainment.md:77
- data/master-cv/roles/01_seven_one_entertainment.md:103

### jd_alignment (weight 25)
**Layer A — Category core**
What good looks like:
- Python backend leadership prominently surfaced when JD requires Python
- Platform/architecture scope matches JD: enterprise, distributed, microservices
- AI/LLM integration depth matches JD requirements: RAG, evaluation, basic API
- Production readiness evidence matches JD emphasis on reliability, CI/CD
- Player-coach framing matches JD team scope (no manager inflation for IC-heavy roles)
- Domain experience surfaces if JD specifies industry
Common failures:
- Python underweighted when JD explicitly requires Python leadership
- Manager framing when JD describes player-coach or senior IC scope
- Generic AI claims when JD specifies RAG, agents, or evaluation
- Enterprise architecture claims for startup-scale JD or vice versa
- Cloud mismatch: AWS experience for Azure-required role
**Layer B — Job-specific overlay**
Adjust per JD:
- Match framework requirements exactly: FastAPI role needs FastAPI evidence
- Match cloud requirements: AWS role should not overstate Azure/GCP
- Match AI depth: evaluation-heavy role needs evaluation evidence foregrounded
- Match team structure: distributed team JD needs distributed collaboration evidence
Company/domain overrides:
- Consultancy: emphasize client delivery, stakeholder management, estimation accuracy
- Product company: emphasize platform ownership, feature delivery, production metrics
- Enterprise: emphasize integration, scale, compliance-adjacent work
Region overrides:
- DACH region: German language skills and local company experience valuable
- UK roles: may have different compliance considerations post-Brexit
- Remote-first EEA: distributed team coordination becomes differentiator
**Score anchors**
- 9-10:
  - CV directly addresses all must-have requirements from JD
  - Tech stack matches: Python, cloud, AI tools align with JD specifics
  - Scope matches: player-coach evidence for player-coach JD
  - Domain match or clearly transferable experience demonstrated
  - Differentiators (RAG, evaluation, distributed teams) addressed if in JD
- 7-8:
  - Most must-haves addressed; 1-2 minor gaps in secondary requirements
  - Tech stack mostly matches with minor gaps (e.g., FastAPI not explicit)
  - Scope alignment good but framing could be tighter
  - Domain transferable with clear explanation
- 5-6:
  - Core must-haves present but significant gaps in secondary requirements
  - Tech stack has notable mismatches or gaps
  - Scope framing misaligned (manager for IC role or vice versa)
  - Domain gap without clear transferability story
- <=4:
  - Multiple must-haves missing or only tangentially addressed
  - Tech stack fundamentally mismatched
  - Scope wildly misaligned (VP framing for senior IC role)
  - No relevant domain experience or transferability
Red flags:
- Claiming FastAPI/Django/Flask depth when JD requires it but CV lacks it
- Manager title for explicitly IC/player-coach JD
- AWS expertise claimed for Azure-required role without evidence
- Generic AI claims for JD requiring specific RAG or evaluation experience
- Startup-scale evidence only for enterprise-scale JD
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json

### executive_presence (weight 15)
**Layer A — Category core**
What good looks like:
- Player-coach authority: technical direction, code review, design decisions
- Mentoring evidence: engineers coached, capability uplift, promotions influenced
- Delivery ownership: estimation accuracy, handoff quality, timeline alignment
- Stakeholder translation: technical debt ROI, architecture decisions explained
- Cross-functional collaboration: distributed teams, client coordination
- Technical vision: north-star decisions, quality standards, engineering excellence
Common failures:
- Manager language without management scope (direct reports, performance reviews)
- VP/Director framing for what is actually player-coach scope
- Pure IC framing that undersells mentoring and technical leadership
- Stakeholder management claimed without specific translation examples
- Led team without delivery or quality outcomes
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD mentions team size: match mentoring evidence to that scale
- If JD emphasizes client-facing: surface stakeholder translation more
- If JD is pure IC with influence: reduce direct leadership claims
- If JD mentions hiring involvement: surface interview participation if true
Company/domain overrides:
- Consultancy: client management and delivery planning become key signals
- Product company: platform ownership and technical vision emphasized
- Startup: 0-to-1 delivery and hands-on breadth valued
Region overrides:
- EEA distributed teams: coordination across time zones becomes differentiator
- German corporate culture: formal stakeholder communication valued
**Score anchors**
- 9-10:
  - Clear player-coach evidence: hands-on plus mentoring plus delivery ownership
  - Specific mentoring outcomes: engineers promoted, capabilities built
  - Technical vision with adoption: standards set and followed
  - Stakeholder translation with outcomes: investment secured, alignment achieved
  - No management inflation: framing matches actual scope
- 7-8:
  - Player-coach evidence present but mentoring or stakeholder outcomes less specific
  - Technical leadership clear but vision/standards not fully articulated
  - Scope framing accurate but could be more compelling
- 5-6:
  - Leadership claimed but evidence is thin (worked with not mentored)
  - Manager or architect language without matching scope proof
  - Delivery involvement unclear: coordinated vs led vs contributed
- <=4:
  - Unsupported people-management framing (direct reports, performance reviews)
  - VP/Director/Head language for clearly IC-scope work
  - No leadership evidence: pure IC with no influence signals
  - Budget or P&L claims without any supporting evidence
Red flags:
- Unsupported people-management framing: direct reports, performance reviews, hiring ownership
- Budget or P&L ownership claims for tech lead role
- Org-building or company-wide headcount claims without evidence
- Director/VP/Head titles without matching organizational scope
- Mentored without specific engineer outcomes or numbers
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json
- data/master-cv/roles/01_seven_one_entertainment.md:231

### anti_hallucination (weight 15)
**Layer A — Category core**
What good looks like:
- Every metric is attributable: specific project, role, timeframe
- Titles match actual roles held; no inflation to Manager/Director/Head
- Tech stack claims match actual production use, not tutorials or POCs
- AI/LLM claims specify what was actually built vs theoretical knowledge
- Leadership scope matches reality: mentoring vs managing vs influencing
- Framework claims match actual depth: used vs led vs architected
Common failures:
- Metrics without attribution (80% improvement in what? when? where?)
- Title inflation: Engineering Manager when never had direct reports
- FastAPI/Django/Flask expertise claimed from one-off usage
- Multi-cloud expert from using AWS primarily with minor Azure
- PhD, publication, or research framing when background is industry
- RAG expert from one RAG feature vs full pipeline ownership
**Layer B — Job-specific overlay**
Adjust per JD:
- Verify framework claims match JD-required depth, not overclaim
- Ensure cloud claims match JD requirements without overreach
- AI depth claims must be verifiable against JD-specific requirements
- Leadership scope claims must match JD expectations precisely
Company/domain overrides:
- Enterprise roles: do not claim GDPR, PCI, audit expertise unless evidenced
- Fintech roles: do not claim compliance expertise without specific evidence
- Consultancy roles: do not overclaim client scope or engagement size
Region overrides:
- EEA roles: do not claim language proficiency beyond actual capability
- Do not claim native-language fit beyond verified proficiency
**Score anchors**
- 9-10:
  - All metrics tied to specific roles, projects, and timeframes
  - Titles exactly match job history; no inflation
  - Tech claims verifiable against project descriptions
  - AI claims specify exact scope: API integration vs pipeline vs evaluation
  - Leadership claims precise: 10 engineers mentored vs managed team of 10
  - No unsupported credentials or certifications
- 7-8:
  - Most claims verifiable; 1-2 metrics lack full attribution
  - Titles accurate but framing slightly generous
  - Tech depth occasionally ambiguous (experienced with vs expert in)
  - Leadership scope clear but outcomes not always specific
- 5-6:
  - Multiple metrics lack clear attribution
  - Title framing somewhat inflated from actual scope
  - Tech claims include frameworks used briefly as if deep expertise
  - AI claims vague about actual implementation scope
  - Leadership claims ambiguous about direct vs indirect influence
- <=4:
  - Fabricated or unverifiable metrics
  - Title inflation: Manager/Director/Head without scope evidence
  - Tech stack overclaims: multi-cloud, every framework, full-stack
  - AI claims imply ML research or fine-tuning without evidence
  - PhD, publication, or credential claims without basis
  - Budget/P&L ownership for category where it appears 0%
Red flags:
- Unsupported metrics: round numbers, company-level figures for IC role
- Fabricated titles: Head of AI, Director, VP without org scope
- PhD or publication inflation when background is industry engineering
- Budget or P&L ownership claims (0% in this category)
- Formal people management with direct reports unless explicitly evidenced
- Hiring or performance review ownership without supporting detail
- Deep AWS/Azure/GCP platform ownership claimed for each without evidence
- Named FastAPI/Django/Flask production leadership if not actually shown
- Fine-tuning, custom embedding training, or RLHF claims without evidence
- Onshore/offshore leadership at company level without cross-border coordination proof
- GDPR, PCI, audit expertise claimed when each appears only 2.4% in category
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json
- data/master-cv/projects/commander4_skills.json:42

## Gates
### must_have_coverage_gate
Pass criteria:
- Python backend experience evidenced with production depth
- Platform or backend architecture experience demonstrated
- AI/LLM integration in production systems (not just POC or tutorial)
- Player-coach scope: hands-on technical work plus mentoring or technical leadership
- Production readiness evidence: CI/CD, testing, reliability, or deployment
Fail conditions:
- No Python evidence despite 70.7% required language in category
- Pure frontend or generalist background without backend architecture
- AI work limited to theory, tutorials, or non-production experimentation
- Pure IC with no mentoring, collaboration, or technical leadership signals
- No production delivery evidence: demo-only or research-only work
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json

### unsafe_claim_gate
Pass criteria:
- No budget or P&L ownership claims (0% in category)
- No formal people-management claims without direct-report evidence
- Title framing matches actual scope without Director/VP/Head inflation
- Framework claims match actual production depth
- Cloud claims match actual implementation scope
Fail conditions:
- Budget or P&L ownership claimed
- Formal people management with direct reports claimed without evidence
- Hiring or performance review ownership claimed without supporting detail
- Director/VP/Head of AI title framing for player-coach scope
- Multi-cloud expert claims without evidence for each platform
- FastAPI/Django/Flask leadership claimed without production depth
- PhD, publication, or research positioning for delivery-oriented category
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json

### persona_fit_gate
Pass criteria:
- Player-coach framing: hands-on plus technical leadership plus delivery
- Tech Lead or Technical Lead positioning rather than Architect or Manager
- Backend and AI combined positioning, not standalone AI evangelist
- Production and delivery orientation, not research or experimentation focus
- Mentoring and collaboration as leadership mode, not org-chart authority
Fail conditions:
- Pure manager framing without hands-on technical evidence
- Pure architect framing detached from implementation and delivery
- AI evangelist or GenAI expert framing without backend grounding
- Research scientist or ML researcher positioning (0% research-heavy in category)
- Executive or org-builder positioning with company-wide scope claims
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json

## Verdict Thresholds
- STRONG_MATCH >= 8.5
- GOOD_MATCH   >= 7.0
- NEEDS_WORK   >= 5.5
- WEAK_MATCH   <= 5.49

## Scoring Guidance
- Executive presence: For this tech-lead player-coach category, executive_presence means hands-on team leadership plus delivery ownership. Score based on mentoring outcomes, technical direction, stakeholder translation, and delivery discipline. Penalize unsupported people-management framing (direct reports, performance reviews, budget). Do not expect or reward Director/VP/C-suite signals—this is a player-coach category (90.2% player_coach, 0% budget/P&L).
- Unsupported claims: Apply hard penalties (score 0-4) for: fabricated metrics without attribution, title inflation beyond actual scope, budget/P&L claims, formal management claims without evidence, multi-cloud or multi-framework expertise without depth proof, PhD/publication positioning. Moderate penalties (score 5-6) for: vague metrics, slightly generous framing, ambiguous tech depth. Each unsupported claim in red_flags should reduce dimension score by 1-2 points.
- Category vs job tradeoffs: Category signals (Python, tech lead title, player-coach, production AI, mentoring) should form the baseline. JD-specific requirements can override within reason: if JD requires FastAPI and CV has it, weight FastAPI; if JD requires Azure and CV has AWS only, note the gap. Never invent claims to fill JD gaps. When JD asks for Manager scope but category is player-coach, verify actual scope in CV before accepting manager framing.
Citations:
- data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- data/eval/baselines/tech_lead_ai_eea_baseline.json

## Evidence Ledger
- [high] Python must appear 2-3 times across CV when true; Python is 68.3% hard skill and 70.7% required language
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
  - data/eval/baselines/tech_lead_ai_eea_baseline.json
- [high] Tech Lead title family preferred over Architect or Manager; tech_lead appears 31/41 (75.6%)
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [high] Player-coach framing required; player_coach scope is 37/41 (90.2%); manager scope is 1/41 (2.4%)
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [high] Budget and P&L claims are unsafe; budget/P&L is 0/41 (0.0%) in category
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [high] Hiring and performance management claims require explicit evidence; hiring 3/41 (7.3%), performance_management 4/41 (9.8%)
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [high] FastAPI/Django/Flask claims must match production depth; each appears 36-49% but blueprint warns against overclaiming
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
  - data/eval/baselines/tech_lead_ai_eea_baseline.json
- [high] PhD and research positioning unsafe; requires_phd_pct 0.0%, research_heavy_pct 0.0%
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [high] Mentoring and collaboration are table-stakes leadership signals; mentoring 30/41 (73.2%), collaboration 36/41 (87.8%)
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [high] AI/LLM integration must be production backend work not standalone experimentation; platform_design 95.1%, OpenAI 39.0%, HuggingFace 36.6%
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
- [medium] Evaluation and guardrails are differentiators worth surfacing; evaluation_quality 9/41 (22.0%), guardrails_governance 4/41 (9.8%)
  - data/eval/blueprints/tech_lead_ai_eea_blueprint.json
  - data/eval/baselines/tech_lead_ai_eea_baseline.json
