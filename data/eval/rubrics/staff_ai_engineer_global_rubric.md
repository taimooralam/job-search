# Staff AI Engineer — Global/Remote — Eval Rubric

## Meta
- Category ID: staff_ai_engineer_global
- Macro family: ai_engineering_adjacent
- Priority: secondary_target
- Confidence: high
- Rubric version: 2026-04-17

## Identity
- Purpose: Evaluate CVs for hands-on Staff/Principal AI Engineer roles requiring architecture ownership, production AI platform delivery, and player-coach influence without formal management scope.
- Core persona: Architecture-first senior IC who ships production AI platforms and distributed backend systems, demonstrates reliability judgment, and influences engineering standards through mentoring and technical leadership rather than people management.
Job overlay notes:
- Stack requirements vary: Python dominates at 32% but no single skill exceeds one-third of roles; adjust keyword density based on JD-specific stack signals
- Agent orchestration (48%) and RAG (36%) are differentiators not table stakes; only emphasize when JD explicitly requests and CV evidence supports
- Player-coach scope (44%) varies by company; some roles are pure IC (56%), adjust leadership framing accordingly
- Domain requirements are fragmented (fintech, healthcare, enterprise SaaS each ~8%); do not assume domain expertise unless JD specifies
- Remote-first collaboration model dominates; emphasize async communication and cross-functional stakeholder alignment
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json

## Dimension Rubrics
### ats_optimization (weight 20)
**Layer A — Category core**
What good looks like:
- Headline uses Staff/Principal AI Engineer title family matching 96% of roles that use principal_engineer or staff_engineer titles
- Architecture and production scope keywords appear before tool names since platform design is 24/25 (96%) while no hard skill exceeds 32%
- 2-3 mentions of platform architecture, system design, AI platform across headline/profile/experience/skills
- 1-2 mentions of distributed systems, reliability, observability as secondary keywords
- Agent orchestration, RAG, evaluation, guardrails terminology used only when CV evidence supports shipped systems
Common failures:
- Using generic Software Engineer or ML Engineer titles that miss Staff/Principal seniority signal
- Leading with tool/framework lists instead of architecture and production delivery outcomes
- Over-indexing on provider brand names (OpenAI, Anthropic) without shipped platform evidence
- Missing collaboration and cross-functional keywords despite 92% role prevalence
- Using Head of AI, Director, or VP titles that trigger persona inflation for IC roles
**Layer B — Job-specific overlay**
Adjust per JD:
- Match exact title family from JD (Staff vs Principal vs Staff Software Engineer AI/ML)
- Increase Python/distributed systems mentions if JD emphasizes backend foundations
- Add Kubernetes/CI-CD keywords (each 16%) only if JD infrastructure-heavy
- Include specific framework names (LangChain 20%, vector databases 20%) only when JD lists them and CV proves usage
Company/domain overrides:
- Fintech: add reliability, compliance, governance keywords if JD mentions regulated environment
- Healthcare: include HIPAA/PHI only if CV proves direct delivery in that environment
- Enterprise SaaS: emphasize multi-tenant, integration, enterprise systems terminology
Region overrides:
- No native language requirements detected in category; English technical communication sufficient
- Remote-first model dominates; emphasize async collaboration and distributed team experience
**Score anchors**
- 9-10:
  - Headline uses exact Staff/Principal AI Engineer title family with architecture focus
  - All table-stakes keywords (platform architecture, production AI, distributed systems, reliability) present with appropriate density
  - Differentiator keywords (agent orchestration, RAG, evaluation, guardrails) precisely matched to CV evidence and JD requirements
  - No tool-brand stuffing without shipped system context
- 7-8:
  - Title family correct but supporting keywords slightly misaligned to JD emphasis
  - Core architecture and production keywords present but could be better distributed
  - Minor over/under-indexing on differentiator terminology relative to evidence strength
- 5-6:
  - Title uses generic engineer framing missing Staff/Principal seniority signal
  - Architecture keywords present but buried below tool lists
  - Missing collaboration or cross-functional terminology despite category prevalence
  - Some keyword mismatches between CV claims and JD requirements
- <=4:
  - Title implies management scope (Director, Head of, VP) inappropriate for senior IC category
  - Heavy tool/framework keyword stuffing without production context
  - Missing fundamental category signals: platform architecture, production, reliability
  - Keywords suggest research/academic positioning despite 0% research_heavy requirement
Red flags:
- Head of AI, Director, VP, or Engineering Manager titles for IC-scoped roles
- Tool-brand keyword lists without system-level outcomes
- Research-heavy or PhD-style framing when category shows 0% research requirement
- Multi-cloud expertise claims without JD requirement or CV evidence
- Agentic AI buzzwords without architecture or evaluation proof
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json

### impact_clarity (weight 25)
**Layer A — Category core**
What good looks like:
- Quantified platform delivery: users served, integrations shipped, workflows enabled with specific numbers
- Reliability metrics: uptime percentages, incident reduction rates, MTTR improvements, latency stability
- Scale markers: events processed, requests handled, teams adopting standards
- AI system quality: evaluation pass rates, retrieval quality scores (MRR, NDCG), hallucination reduction
- Team multiplier effects: engineers mentored, promotions enabled, onboarding time reduced
Common failures:
- Vague platform claims without adoption or usage metrics
- Missing reliability outcomes despite category valuing production stability
- AI work described as exploration/POC without production deployment evidence
- Leadership claims without quantified team or org impact
- Scale language (millions, billions) without supporting context or evidence
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD emphasizes greenfield: highlight time-to-production and adoption ramp metrics
- If JD emphasizes modernization: emphasize legacy system transformation metrics (incident reduction, tech debt elimination)
- If JD emphasizes reliability: foreground uptime, SLO attainment, MTTR over feature delivery metrics
- If JD emphasizes AI quality: emphasize evaluation harness metrics, guardrail effectiveness, structured output validation rates
Company/domain overrides:
- Fintech: availability and transaction reliability metrics carry extra weight
- Healthcare: compliance-passing milestones and audit outcomes relevant if CV supports
- Startup stage: velocity and time-to-market metrics more relevant than enterprise scale
Region overrides:
- Global/remote roles value async delivery outcomes and cross-timezone collaboration metrics
**Score anchors**
- 9-10:
  - Every major achievement includes specific, verifiable metrics tied to business or technical outcomes
  - Reliability and production stability quantified with multiple proof points (uptime, incidents, latency)
  - AI system quality demonstrated with evaluation metrics (MRR@k, NDCG@k, retrieval accuracy, guardrail catch rates)
  - Team multiplier effects quantified (engineers mentored with outcomes, standards adoption rates)
  - Scale appropriate to role scope without inflation beyond documented evidence
- 7-8:
  - Most achievements quantified but one or two key areas lack specific metrics
  - Reliability outcomes mentioned with numbers but could include additional proof points
  - AI quality claims supported but evaluation methodology could be clearer
  - Team impact mentioned with some quantification
- 5-6:
  - Achievements present but metrics scattered or inconsistent
  - Reliability mentioned without specific numbers (e.g., 'improved uptime' without percentage)
  - AI delivery claims lack evaluation or quality metrics
  - Leadership impact asserted without quantified outcomes
- <=4:
  - Achievements described qualitatively without metrics
  - No reliability or production stability evidence despite category requirement
  - AI work appears exploratory without deployment or adoption proof
  - Team claims unsubstantiated or inflated beyond reasonable inference
Red flags:
- Millions-scale user claims without supporting platform context
- Revenue impact claims without clear causal chain to individual contribution
- Time savings or efficiency gains without baseline comparison methodology
- Evaluation metrics cited without explaining measurement approach
- Incident reduction percentages that imply sole credit for systemic improvements
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json
- data/master-cv/roles/01_seven_one_entertainment.md:77

### jd_alignment (weight 25)
**Layer A — Category core**
What good looks like:
- Platform architecture evidence for roles where platform design appears in 96% of JDs
- Distributed systems and backend foundations demonstrated for roles emphasizing system depth
- Agent orchestration and RAG evidence when JD explicitly requests (48% and 36% respectively)
- Reliability, observability, and production hardening proof for all roles given category-wide signal
- Collaboration and mentoring evidence for player-coach scoped roles (44%)
Common failures:
- Emphasizing pure AI/ML research for a production-delivery focused category
- Missing architecture evidence for a category where 96% of roles require platform design
- Over-claiming agent or RAG experience when JD doesn't require it
- Under-emphasizing collaboration despite 92% category prevalence
- Mismatched seniority framing (too junior or too management-heavy)
**Layer B — Job-specific overlay**
Adjust per JD:
- Greenfield roles (32%): emphasize architecture decision-making and system design from scratch
- Mixed greenfield/optimization roles (48%): balance new-build and modernization evidence
- Pure IC roles (56%): emphasize individual technical contribution over team leadership
- Player-coach roles (44%): include mentoring and standards-setting with hands-on delivery
- Observability-heavy roles (24%): elevate monitoring, alerting, and instrumentation experience
Company/domain overrides:
- B2B enterprise: emphasize multi-tenant architecture, integration complexity, enterprise stakeholder alignment
- Consumer tech: emphasize scale and performance if CV supports consumer-level throughput
- Healthcare/fintech: include governance and compliance only if CV proves that environment
Region overrides:
- US-based companies with global teams: emphasize timezone-spanning collaboration patterns
- EU companies: no specific regulatory framing unless JD mentions GDPR or data residency
**Score anchors**
- 9-10:
  - CV addresses every must-have signal from JD with specific evidence
  - Differentiators (agent orchestration, RAG, evaluation) precisely matched when JD requests them
  - Seniority framing exactly matches role scope (IC vs player-coach)
  - Experience chronology and depth aligned to years-of-experience requirements
  - Tech stack alignment clear without over-claiming unmentioned technologies
- 7-8:
  - Core JD requirements addressed with strong evidence
  - Minor gaps in differentiator coverage or slight over/under-emphasis
  - Seniority framing appropriate with minor adjustments possible
  - Most tech stack requirements covered with evidence
- 5-6:
  - Table-stakes requirements addressed but differentiators weak or missing
  - Evidence present but not well-mapped to JD priorities
  - Seniority framing slightly misaligned (e.g., too IC for player-coach role)
  - Some tech stack gaps between CV claims and JD requirements
- <=4:
  - Missing evidence for fundamental category signals (platform architecture, production delivery)
  - Seniority dramatically mismatched (junior framing for Staff role or VP framing for IC role)
  - Tech stack claims don't support JD requirements
  - CV optimized for different category (research, management, different domain)
Red flags:
- Research-first framing for production-delivery focused roles
- Management-heavy positioning for IC-scoped roles
- Domain expertise claims without JD requirement or CV evidence
- Stack claims (Go, specific cloud providers) without supporting delivery proof
- Ignoring explicit JD requirements while emphasizing CV strengths
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json

### executive_presence (weight 15)
**Layer A — Category core**
What good looks like:
- Senior IC authority demonstrated through architecture decisions and technical direction
- Cross-team influence shown via standards adoption, code review impact, and design reviews
- Stakeholder translation: converting technical complexity into business-aligned communication
- Mentoring and enablement: elevating team capability without claiming management authority
- Technical vision: establishing north stars and roadmaps within IC scope
Common failures:
- Inflating player-coach influence into people management claims
- Using Director, Head of, VP language for IC-scoped contributions
- Claiming hiring authority beyond interview participation (hiring appears in only 8% of roles)
- Describing org-building as primary focus when delivery should lead
- Missing collaboration evidence despite 92% category prevalence
**Layer B — Job-specific overlay**
Adjust per JD:
- Player-coach roles (44%): include mentoring and standards-setting with hands-on delivery emphasis
- Pure IC roles (56%): emphasize technical judgment and architecture ownership over team leadership
- Roles with org_building signal (36%): can include enablement and internal platform work as secondary
- Roles without explicit mentoring requirement: keep leadership claims minimal and delivery-focused
Company/domain overrides:
- Startups: IC authority through shipping velocity and founder-level technical dialogue
- Enterprise: influence through stakeholder alignment and cross-functional coordination
- Platform teams: authority demonstrated through adoption metrics and developer experience improvements
Region overrides:
- Remote-first: emphasize async influence patterns and written technical communication
**Score anchors**
- 9-10:
  - Technical authority evident through architecture decisions with org-wide impact
  - Cross-team influence documented with specific outcomes (standards adopted, practices changed)
  - Stakeholder translation demonstrated with concrete business-technical bridging examples
  - Mentoring quantified (engineers developed, promotions enabled) without management inflation
  - All influence claims scoped appropriately for senior IC role
- 7-8:
  - Technical authority clear with evidence of architecture ownership
  - Some cross-team influence documented but could be more specific
  - Mentoring mentioned with reasonable quantification
  - Influence claims appropriate for IC scope with minor adjustments possible
- 5-6:
  - Technical contribution evident but authority/influence understated
  - Cross-team impact mentioned without specific outcomes
  - Leadership role implied but not well-documented
  - Some risk of under-claiming appropriate senior IC authority
- <=4:
  - Influence claims inflated to management/director scope for IC role
  - Hiring authority claimed beyond evidence (only 8% of roles involve hiring)
  - Org-building positioned as primary focus over delivery
  - No evidence of technical authority or cross-team influence
  - Persona mismatch: management-first framing for architecture-first category
Red flags:
- People management framing without documented management authority
- Director/Head/VP title claims for IC-scoped work
- Hiring authority claims beyond interview participation (hiring only 8%)
- Performance management claims without formal scope (only 4% of roles)
- Budget/P&L ownership claims (0% of roles)
- Company-wide ownership claims without adoption metrics or scope evidence
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json
- data/master-cv/roles/01_seven_one_entertainment.md:231

### anti_hallucination (weight 15)
**Layer A — Category core**
What good looks like:
- All metrics traceable to specific projects and timeframes
- Title claims match documented role history without inflation
- Tech stack claims limited to technologies with shipped production evidence
- Scale claims proportionate to documented platform scope
- Leadership scope matches organizational evidence (IC vs manager vs player-coach)
Common failures:
- Unsourced percentage improvements without baseline context
- Title inflation from Staff to Director/Head without documented transition
- Go language claims without production evidence (common unsafe claim in category)
- SLO/incident response program ownership without operational scope proof
- Multi-cloud implementation claims when work was single-cloud
**Layer B — Job-specific overlay**
Adjust per JD:
- If JD requires specific provider experience (MCP, OpenAI, Anthropic): verify integration vs platform development distinction
- If JD requires multi-cloud: verify breadth of cloud evidence, not just LLM provider routing
- If JD requires HIPAA/healthcare: verify direct delivery in regulated environment vs general security practice
- If JD requires formal leadership: verify management scope vs player-coach influence
Company/domain overrides:
- Healthcare companies: HIPAA/PHI claims require direct delivery evidence in that environment
- Enterprise SaaS: multi-tenant claims require architectural proof, not just deployment context
Region overrides:
- No region-specific compliance claims unless CV proves that regulatory environment
**Score anchors**
- 9-10:
  - Every quantified claim traceable to specific project with measurement context
  - Titles exactly match documented role progression without inflation
  - Tech claims limited to demonstrated production usage
  - Scale claims supported by platform scope evidence
  - No unsafe claims from category blueprint appear without supporting evidence
- 7-8:
  - Most claims well-sourced with minor attribution gaps
  - Titles accurate with perhaps slight variation in exact wording
  - Tech claims supported but one or two could be more precisely scoped
  - No major red-flag claims from unsafe list
- 5-6:
  - Some metrics lack clear source or methodology
  - Title framing slightly elevated beyond documented scope
  - Tech breadth claims exceed demonstrated depth in some areas
  - One minor unsafe claim present but not central to positioning
- <=4:
  - Metrics appear fabricated or dramatically inflated
  - Title inflation from IC to management scope without evidence
  - Critical tech claims (Go, multi-cloud, specific providers) unsupported
  - Multiple unsafe claims from category blueprint present
  - PhD/publication/research credentials added for category where 0% require them
Red flags:
- Go language depth claims without production evidence
- SLO/SLI program ownership without direct operational scope documentation
- Direct MCP/OpenAI/Anthropic platform engineering claims when work was integration only
- Multi-cloud infrastructure claims when work was single-cloud with multi-provider LLM routing
- Formal people management or hiring authority claims without documented scope
- Fine-tuning, custom embedding training, or RLHF claims without explicit project evidence
- Millions-scale user claims when documented scope is thousands
- PhD or publication framing for category with 0% research requirement
- Company-wide AI tooling ownership claims without adoption metrics
- HIPAA/PHI/healthcare compliance ownership without direct delivery evidence
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json
- data/master-cv/projects/commander4_skills.json:42

## Gates
### must_have_coverage_gate
Pass criteria:
- Platform architecture evidence present (required in 96% of roles)
- Production delivery evidence with reliability or scale markers
- Senior IC seniority clearly established (required in 100% of roles)
- Distributed systems or backend engineering foundation demonstrated
- Collaboration or cross-functional evidence present (required in 92% of roles)
Fail conditions:
- No platform or system architecture evidence for architecture-required category
- No production delivery evidence (pure research or POC-only positioning)
- Seniority unclear or appears junior to Staff/Principal level
- No backend/systems foundation (pure frontend or data-only background)
- Zero collaboration or stakeholder alignment evidence
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json

### unsafe_claim_gate
Pass criteria:
- All metrics traceable to documented projects
- Titles match role history without inflation to management scope
- Tech claims limited to technologies with production evidence
- Leadership claims scoped appropriately for IC role
- No red-flag claims from category unsafe_or_weak_framing list
Fail conditions:
- Director/Head/VP title claims for IC-scoped work
- Go language depth claimed without production evidence
- Multi-cloud implementation claimed when work was single-cloud
- SLO program ownership claimed without operational scope evidence
- People management authority claimed without documented scope
- Fine-tuning/RLHF/custom embedding claims without explicit project evidence
- PhD/publication/research framing for production-delivery category
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json

### persona_fit_gate
Pass criteria:
- Architecture-first positioning with production delivery emphasis
- Senior IC authority framing without management inflation
- Player-coach influence (if claimed) scoped to mentoring and standards, not people management
- Technical vocabulary matches architect tone with high formality
- Collaboration emphasis appropriate for 92% category prevalence
Fail conditions:
- Management-first positioning for IC-scoped category
- Research/academic framing for production-delivery category
- Consumer-scale claims without supporting enterprise platform evidence
- Tool-evangelist positioning without shipped system outcomes
- Hiring-leader or org-owner framing beyond documented scope
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json

## Verdict Thresholds
- STRONG_MATCH >= 8.5
- GOOD_MATCH   >= 7.0
- NEEDS_WORK   >= 5.5
- WEAK_MATCH   <= 5.49

## Scoring Guidance
- Executive presence: For this senior IC category, executive_presence means architectural authority, technical judgment, cross-team influence, and mentoring impact WITHOUT formal management scope. Score highly for standards adoption, design review influence, and player-coach enablement. Penalize people-management framing, hiring authority claims, budget ownership, or Director/VP/Head positioning as persona inflation. The category shows hiring at 8%, performance_management at 4%, and budget_pnl at 0% — claims beyond these frequencies require explicit evidence.
- Unsupported claims: Apply graduated penalties: minor deductions (0.5-1.0 points) for vague metrics lacking methodology; moderate deductions (1.0-2.0 points) for tech claims exceeding demonstrated depth; severe deductions (2.0-3.0 points) for title inflation, fabricated credentials, or claims matching category red_flags (Go depth, SLO ownership, multi-cloud, people management). Any claim on the unsafe_claims_top list without explicit CV evidence should trigger anti_hallucination deduction AND may fail unsafe_claim_gate.
- Category vs job tradeoffs: Category signals (platform architecture 96%, collaboration 92%, production reliability) take precedence over JD-specific nice-to-haves. However, when JD explicitly requires a differentiator (agent orchestration 48%, RAG 36%, specific stack), penalize jd_alignment if CV doesn't address it. For table-stakes requirements appearing in >50% of roles, treat JD omission as implicit inclusion. For differentiators (<50%), only require evidence when JD explicitly requests.
Citations:
- data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- data/eval/baselines/staff_ai_engineer_global_baseline.json

## Evidence Ledger
- [high] Platform architecture evidence required as table stakes for 96% role prevalence
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
  - data/master-cv/roles/01_seven_one_entertainment.md:28
- [high] Staff/Principal title family required matching 96% combined prevalence (principal_engineer 52% + staff_engineer 44%)
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- [high] Senior IC framing required for 100% senior_ic prevalence with player-coach (44%) vs pure IC (56%) split
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
  - data/eval/baselines/staff_ai_engineer_global_baseline.json
- [high] Agent orchestration (48%) and RAG (36%) are differentiators requiring explicit JD match and CV evidence
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
  - data/master-cv/projects/commander4.md:8
- [high] Collaboration evidence required for 92% category prevalence
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- [high] Reliability and observability outcomes valued with reliability in 18 deep-analysis samples and observability in 24%
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
  - data/master-cv/roles/01_seven_one_entertainment.md:77
- [high] People management claims penalized as persona inflation (hiring 8%, performance_management 4%, budget_pnl 0%)
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
  - data/eval/baselines/staff_ai_engineer_global_baseline.json
- [high] Research/PhD framing penalized for category with 0% research_heavy and 0% requires_phd
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- [high] Go language claims flagged as unsafe without production evidence per category unsafe_claims_top
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
- [high] Multi-cloud implementation claims require breadth evidence beyond single-cloud with multi-provider LLM routing
  - data/eval/blueprints/staff_ai_engineer_global_blueprint.json
  - data/eval/baselines/staff_ai_engineer_global_baseline.json
