# Head of AI — Global/Remote — Eval Rubric

## Meta
- Category ID: head_of_ai_global
- Macro family: ai_leadership
- Priority: primary_target
- Confidence: high
- Rubric version: 2026-04-17

## Identity
- Purpose: Evaluate CVs for remote AI platform architect and player-coach roles that reward production architecture proof, delivery outcomes, reliability, and business-to-technical translation over executive org-building claims.
- Core persona: Hands-on AI platform architect or player-coach who ships production systems, translates business needs into technical execution, and demonstrates reliability and evaluation quality—not a pure executive with budget and hiring authority.
Job overlay notes:
- Role scope skews IC/player-coach (IC 54.2%, player-coach 13.3%) over executive (3.6%); adjust expectations accordingly
- Platform design appears in 66.3% of sample; architecture proof is central
- Remote-first collaboration is 84.3%; distributed execution context is structural, not differentiating
- No hard skill exceeds 60%; Python leads at 45.8%; tool-stacking is not rewarded
- Budget/P&L is 0.0% and hiring is 2.4%; penalize unsupported management claims
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

## Dimension Rubrics
### ats_optimization (weight 20)
**Layer A — Category core**
What good looks like:
- AI platform, systems architecture, platform design repeated 2-3 times across headline, profile, and achievement bullets
- Python mentioned in skills and experience when evidenced; not buried or omitted
- Reliability, service resilience, production systems appear in profile and core experience
- Remote-first, distributed team, cross-functional delivery mentioned 2 times minimum
- Technical execution, delivery, stakeholder communication present for business-translation signal
Common failures:
- Generic AI or ML keywords without platform/architecture specificity
- Tool-stacking lists (Kubernetes, Terraform, Helm) without delivery context
- Executive buzzwords (strategic, transformational) that don't match IC/player-coach profile
- Missing Python or implementation language when category requires hands-on credibility
- Frontend-heavy keywords (React) dominating when category values backend/platform
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD emphasizes agents/orchestration (19.3% signal), surface workflow orchestration and multi-step systems
- If JD mentions evaluation/quality (13.3% signal), emphasize evaluation harnesses, MRR, NDCG metrics
- If JD requires guardrails/governance (9.6% signal), add governance, compliance, GDPR if evidenced
- Match JD's specific cloud provider (AWS, GCP, Azure) only when CV has direct delivery evidence
Company/domain overrides:
- Healthcare or fintech domains: add compliance and data-governance keywords if evidenced
- Startup stage: emphasize greenfield, 0-to-1, rapid iteration keywords
- Enterprise: emphasize scale, reliability, service resilience, observability
Region overrides:
- EU roles: add GDPR if candidate has actual compliance evidence
- Do not assume Southern Europe expansion ownership unless JD explicitly requires it
**Score anchors**
- 9-10:
  - All table-stakes keywords (AI platform, systems architecture, Python, reliability, remote-first) present with natural repetition
  - Differentiator keywords (agents, orchestration, evaluation, guardrails) present when JD signals them
  - No keyword stuffing; terms appear in context with outcomes
  - Headline and profile optimized for ATS with accurate title family
- 7-8:
  - Most table-stakes keywords present but one category missing or underrepresented
  - Differentiator keywords present but could be stronger in frequency
  - Minor keyword placement issues (buried in skills section vs. prominent in profile)
- 5-6:
  - Core platform/architecture keywords present but reliability or remote-first context missing
  - Implementation language (Python) mentioned but not prominent
  - Some keyword stuffing or generic AI terms without specificity
- <=4:
  - Missing AI platform or architecture keywords entirely
  - Executive or research keywords dominating when category requires architect/IC profile
  - Tool-stacking without delivery context; frontend-heavy positioning
Red flags:
- Kubernetes, Terraform, GitOps, Helm listed without project-level delivery evidence
- React-heavy positioning when category values backend/platform
- Executive titles (Head of AI, VP, Chief) in headline without matching scope evidence
- Research or PhD framing when category requires production delivery
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

### impact_clarity (weight 25)
**Layer A — Category core**
What good looks like:
- Quantified platform scale: users served, workflows supported, services integrated
- Reliability metrics: uptime percentage, incident reduction, MTTR improvement
- Delivery outcomes: time to launch, milestones shipped, adoption growth
- Evaluation quality: MRR@k, NDCG@k, pass rates, quality scores when AI system
- Business translation proof: stakeholders aligned, roadmap delivered, scope clarified
Common failures:
- Vague scale claims (millions of users) without specific evidence
- Responsibilities listed without outcomes (built platform vs. shipped platform serving X users)
- Technical implementations without business or operational impact
- Revenue or P&L claims when category shows 0% budget signal
- Team size claims without mentorship or practice-shaping outcomes
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD emphasizes scaling: prioritize users, traffic, throughput metrics
- If JD emphasizes reliability: prioritize uptime, incident, MTTR metrics
- If JD emphasizes AI quality: prioritize evaluation, guardrail, accuracy metrics
- If JD emphasizes delivery speed: prioritize time-to-launch, release frequency metrics
Company/domain overrides:
- Startup context: accept smaller absolute numbers if growth rate is strong
- Enterprise context: expect larger scale numbers for platform adoption
- Regulated industries: value compliance and audit metrics
Region overrides:
- Global remote: distributed team coordination outcomes valued
- Regional expansion: only credit market metrics if explicitly evidenced
**Score anchors**
- 9-10:
  - 3+ quantified achievements with specific metrics tied to category signals (platform scale, reliability, delivery)
  - Before/after framing showing measurable improvement
  - Metrics credible for role level and context
  - Business translation outcomes quantified (stakeholders, milestones)
- 7-8:
  - 2-3 quantified achievements but metrics could be more specific
  - Strong outcomes but some achievements lack before/after context
  - Most metrics credible; one or two at edge of believability
- 5-6:
  - 1-2 quantified achievements; others are responsibility statements
  - Metrics present but vague (improved reliability vs. 75% incident reduction)
  - Some outcomes disconnected from category signals
- <=4:
  - No quantified outcomes; pure responsibility listing
  - Metrics appear fabricated or implausible for role level
  - Revenue or P&L claims without evidence when category shows 0% signal
Red flags:
- Tens-of-millions user scale claimed without supporting context
- Revenue impact claimed when category shows no budget/P&L signal
- Hiring numbers (hired 50 engineers) when hiring signal is 2.4%
- Round-number metrics suggesting fabrication (exactly 10x improvement)
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

### jd_alignment (weight 25)
**Layer A — Category core**
What good looks like:
- Platform architecture evidence when JD requires platform design (66.3% signal)
- Business-to-technical translation when JD mentions stakeholder collaboration (67.5% signal)
- Reliability and resilience evidence when JD requires service scale
- Python and hands-on implementation when JD requires technical depth (45.8% signal)
- Remote-first execution context when JD is global/distributed (84.3% signal)
Common failures:
- Executive org-building framing for IC/player-coach role requirements
- Research or ML training focus when JD requires production delivery
- Frontend-heavy evidence when JD requires backend/platform
- Generic AI claims without addressing specific JD pain points
- Missing greenfield or optimization evidence when JD requires both
**Layer B — Job-specific overlay**
Adjust per JD:
- Extract specific pain points from JD and verify CV addresses them
- Map JD's technical stack requirements to CV's evidenced skills
- Identify JD's scope level (IC, player-coach, manager) and verify CV matches
- Check if JD requires both greenfield and optimization evidence
Company/domain overrides:
- B2B enterprise: weight reliability and scale evidence higher
- Startup: weight greenfield delivery and speed evidence higher
- Regulated domain: verify compliance/governance evidence if JD requires
Region overrides:
- GDPR-heavy JDs: only credit GDPR evidence if CV shows actual compliance work
- Regional expansion JDs: only credit if CV explicitly evidences market ownership
**Score anchors**
- 9-10:
  - CV addresses 90%+ of JD's explicit requirements with evidenced claims
  - Scope level (IC/player-coach) matches JD expectations exactly
  - Technical stack alignment verified; no overstated tool claims
  - Pain points from JD explicitly addressed in achievements
- 7-8:
  - CV addresses 70-90% of JD requirements
  - Scope level roughly matches; minor inflation or understatement
  - Most technical requirements met; one or two gaps
  - Major pain points addressed; minor ones missing
- 5-6:
  - CV addresses 50-70% of JD requirements
  - Scope level mismatch (executive framing for player-coach role)
  - Multiple technical gaps or overstated tool claims
  - Some pain points addressed but major ones missing
- <=4:
  - CV addresses <50% of JD requirements
  - Fundamental scope mismatch (pure IC for manager role or vice versa)
  - Technical stack largely misaligned
  - JD pain points not addressed
Red flags:
- Executive framing (VP, Head, C-level) when JD scope is IC or player-coach
- Research/PhD positioning when JD requires production delivery
- Cloud tool claims (K8s, Terraform) when JD requires them but CV lacks evidence
- Frontend-heavy React positioning when JD emphasizes backend/platform
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

### executive_presence (weight 15)
**Layer A — Category core**
What good looks like:
- Player-coach leadership: mentoring engineers, shaping practices, design reviews
- Technical authority: architecture decisions, system boundaries, technical direction
- Cross-functional influence: stakeholder collaboration, business translation, unblocking delivery
- Ownership language: driving outcomes, accountability for systems, delivery leadership
- Remote leadership context: distributed team coordination, async collaboration
Common failures:
- C-suite or boardroom language when category is architect/player-coach
- Budget, P&L, or headcount ownership claims when signals are 0-2.4%
- Org-building narrative when evidence only supports mentoring
- Strategic transformation language detached from technical delivery
- Hiring authority claims when evidence is interview process design only
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD explicitly requires people management, raise threshold for team leadership evidence
- If JD is pure IC/architect, lower people-management expectations entirely
- If JD mentions player-coach, verify mentoring + hands-on combination
- Match leadership language to JD's stated scope precisely
Company/domain overrides:
- Startup: accept informal influence and smaller team context
- Enterprise: expect more formalized leadership evidence if JD requires
- Scale-up: value growth-phase mentoring and practice-shaping
Region overrides:
- Global remote: distributed leadership coordination is expected context, not differentiator
- Do not assume regional org ownership from remote-first exposure
**Score anchors**
- 9-10:
  - Clear player-coach evidence: hands-on technical work + mentoring/practice-shaping
  - Technical authority demonstrated through architecture ownership and system decisions
  - Cross-functional influence quantified (stakeholders aligned, blockers removed)
  - Leadership scope precisely matches category's IC/player-coach profile
- 7-8:
  - Mentoring and technical leadership present but could be better quantified
  - Cross-functional collaboration mentioned but outcomes not fully clear
  - Player-coach profile evident but some language slightly inflated
- 5-6:
  - Leadership evidence present but scope unclear (mentoring vs. management ambiguous)
  - Some executive-sounding language without matching evidence
  - Technical authority claimed but not demonstrated through outcomes
- <=4:
  - Executive framing (VP, Head, C-suite) without supporting scope evidence
  - Budget, P&L, or hiring authority claimed when category shows 0-2.4% signals
  - Org-building narrative without any supporting evidence
  - No leadership or influence evidence at all
Red flags:
- Unsupported people-management framing when hiring signal is 2.4%
- Budget or P&L ownership claims when category signal is 0.0%
- Org-building or headcount authority claims without evidence
- C-suite or boardroom language when category is architect/player-coach
- Global executive claims derived only from remote-first exposure
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

### anti_hallucination (weight 15)
**Layer A — Category core**
What good looks like:
- All metrics traceable to specific roles and timeframes
- Titles match employer-given titles; headline uses safe title families only
- Technical claims (tools, languages, platforms) evidenced through project delivery
- Scale claims plausible for company and role context
- Leadership scope precisely stated (mentoring vs. hiring vs. org-building)
Common failures:
- Fabricated or round-number metrics (exactly 10x, millions without context)
- Title inflation (Head, VP, Chief) without matching employer title or scope
- Tool claims (Kubernetes, Terraform, Helm) without delivery evidence
- Research or PhD implications when background is production engineering
- Budget or P&L claims when category shows 0% signal
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD requires specific tools, verify CV claims are evidenced not just listed
- If JD requires management scope, verify CV claims are supported not inflated
- If JD requires domain expertise, verify CV claims are evidenced not assumed
- Cross-reference JD requirements against CV's do_not_claim boundaries
Company/domain overrides:
- Startup: smaller scale numbers acceptable if growth context provided
- Enterprise: larger scale expected; verify plausibility against company size
- Regulated: compliance claims must have specific evidence
Region overrides:
- GDPR claims: only valid with evidenced compliance or data-governance work
- Regional ownership: only valid if explicitly documented market scope
**Score anchors**
- 9-10:
  - Zero unsupported claims; all metrics and titles verifiable
  - Technical claims match evidenced project delivery
  - Scale claims plausible and contextualized
  - Leadership scope precisely bounded (no inflation)
- 7-8:
  - One or two claims at edge of supportability but not egregious
  - Minor title generalization that doesn't fundamentally misrepresent
  - Technical claims mostly evidenced; one or two need tightening
- 5-6:
  - Two or three claims that stretch evidence materially
  - Title inflation present but not extreme
  - Some tool claims lack direct delivery evidence
- <=4:
  - Multiple fabricated metrics or implausible scale claims
  - Executive title inflation (VP, Head, Chief) without scope evidence
  - Tool claims (K8s, Terraform) contradicted by evidence showing different stack
  - Research/PhD implications without academic background
Red flags:
- Unsourced numeric claims (revenue, user counts, team sizes) without project context
- Fabricated titles not matching employer-given titles
- PhD, publication, or research framing when requires-PhD is 0% in category
- Fine-tuning, RLHF, custom embedding training claims when explicitly in do_not_claim
- Budget or P&L ownership when category signal is 0.0%
- Hiring authority (hired X engineers) when category signal is 2.4%
- Kubernetes, Terraform, GitOps, Helm claims without shipped infrastructure evidence
- Tens-of-millions user scale without supporting company or project context
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json
- data/master-cv/projects/commander4_skills.json

## Gates
### must_have_coverage_gate
Pass criteria:
- CV demonstrates AI platform or systems architecture evidence
- CV shows hands-on implementation credibility (Python or equivalent language)
- CV demonstrates business-to-technical translation or stakeholder collaboration
- CV shows reliability, delivery, or production system outcomes
- CV scope matches IC or player-coach profile (not pure executive)
Fail conditions:
- No AI platform or architecture evidence present
- No implementation language or hands-on credibility demonstrated
- Pure executive or org-builder narrative with no technical delivery proof
- No quantified outcomes or delivery evidence
- Research-only profile without production delivery
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json

### unsafe_claim_gate
Pass criteria:
- No budget or P&L ownership claims unless explicitly evidenced
- No hiring authority claims beyond interview process design unless evidenced
- No Kubernetes, Terraform, GitOps, Helm claims without project delivery evidence
- No executive titles (Head, VP, Chief) in headline without matching scope
- No research, PhD, or fine-tuning claims when evidence is production engineering
Fail conditions:
- Budget or P&L ownership claimed when category signal is 0.0%
- Hiring ownership claimed when category signal is 2.4% and evidence is interview design only
- Cloud/infra tool claims contradicted by CV showing different stack
- Title inflation to executive level without scope evidence
- Fine-tuning, RLHF, custom embedding claims listed in do_not_claim
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json
- data/master-cv/projects/commander4_skills.json

### persona_fit_gate
Pass criteria:
- CV projects architect-first or player-coach persona, not pure executive
- Technical depth evident; not pure management or strategy narrative
- Delivery and production outcomes prominent; not research or experimental
- Remote-first or distributed execution context present or assumable
- Mentoring and influence framed appropriately; not org-building inflation
Fail conditions:
- Pure executive persona (C-suite, boardroom, P&L) when category is architect/player-coach
- Research-led persona when category values production delivery
- Frontend-heavy persona when category values backend/platform
- Org-builder persona when hiring signal is 2.4%
- No technical depth; pure management or stakeholder narrative
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

## Verdict Thresholds
- STRONG_MATCH >= 8.5
- GOOD_MATCH   >= 7.0
- NEEDS_WORK   >= 5.5
- WEAK_MATCH   <= 5.49

## Scoring Guidance
- Executive presence: For this architect-first player-coach category, executive_presence means technical authority, mentoring, cross-functional influence, and delivery leadership—NOT C-suite positioning, boardroom presence, budget ownership, or formal org-building. Player-coach framing with hands-on technical work plus team influence is the ideal. Penalize budget, P&L, hiring authority, or executive title claims that lack supporting evidence. Executive scope is only 3.6% in this category.
- Unsupported claims: Apply progressive penalties: 1-2 minor stretches = 0.5-1 point off anti_hallucination; material title inflation or fabricated metrics = 2-3 points off; egregious fabrication (fake titles, invented scale claims, contradicted tool claims) = gate failure. Cross-reference claims against blueprint's unsafe_or_weak_framing and baseline's do_not_claim lists.
- Category vs job tradeoffs: Category defines baseline expectations; JD overrides when more specific. If JD explicitly requires management scope (rare in this category), raise leadership evidence threshold. If JD emphasizes specific tools, verify those claims specifically. JD alignment (25%) and category alignment (via ats_optimization 20%, impact_clarity 25%) should balance. When JD contradicts category profile (e.g., JD requires executive scope when category is 3.6% executive), trust the JD but note the anomaly.
Citations:
- data/eval/blueprints/head_of_ai_global_blueprint.json
- data/eval/baselines/head_of_ai_global_baseline.json

## Evidence Ledger
- [high] Platform design is table-stakes; AI platform and systems architecture must appear prominently
  - data/eval/blueprints/head_of_ai_global_blueprint.json
- [high] Executive scope is only 3.6%; penalize VP/Head/Chief claims without matching evidence
  - data/eval/blueprints/head_of_ai_global_blueprint.json
  - data/eval/baselines/head_of_ai_global_baseline.json
- [high] Budget/P&L is 0.0%; any ownership claim is unsupported
  - data/eval/blueprints/head_of_ai_global_blueprint.json
- [high] Hiring is 2.4%; hiring authority claims require explicit evidence beyond interview design
  - data/eval/blueprints/head_of_ai_global_blueprint.json
  - data/eval/baselines/head_of_ai_global_baseline.json
- [high] Python leads required languages at 45.8%; hands-on implementation credibility is table-stakes
  - data/eval/blueprints/head_of_ai_global_blueprint.json
- [high] Kubernetes, Terraform, GitOps, Helm appear in 15-20% but overclaiming flagged in 2-3/20 analyses
  - data/eval/blueprints/head_of_ai_global_blueprint.json
- [high] Business-to-technical translation is top pain point (9 mentions); verify stakeholder collaboration evidence
  - data/eval/blueprints/head_of_ai_global_blueprint.json
  - data/eval/baselines/head_of_ai_global_baseline.json
- [high] Reliability is top valued evidence type (13 mentions); quantified uptime/incident metrics strengthen profile
  - data/eval/blueprints/head_of_ai_global_blueprint.json
  - data/eval/baselines/head_of_ai_global_baseline.json
- [high] Requires-PhD is 0%; research/academic framing should be avoided
  - data/eval/blueprints/head_of_ai_global_blueprint.json
- [high] Fine-tuning, RLHF, custom embedding training are in do_not_claim for candidate baseline
  - data/master-cv/projects/commander4_skills.json
- [high] Remote-first is 84.3%; distributed execution context is structural, not differentiating
  - data/eval/blueprints/head_of_ai_global_blueprint.json
- [high] Mentoring is 32.5% but org-building only 16.9%; frame influence as practice-shaping not org-building
  - data/eval/blueprints/head_of_ai_global_blueprint.json
  - data/eval/baselines/head_of_ai_global_baseline.json
