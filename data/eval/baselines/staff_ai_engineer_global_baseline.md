# Staff AI Engineer — Global/Remote Baseline

- Category ID: `staff_ai_engineer_global`
- Macro family: `ai_engineering_adjacent`
- Priority: `secondary_target`
- Confidence: `high`
- Representation proxy mode: `True`

## Overall Assessment

- Combined fit score: **7.85 / 10**
- Readiness tier: **GOOD**
- Verdict: Strong architecture-first AI platform evidence with production RAG, evaluation harnesses, guardrails, and player-coach mentoring aligns well with this senior IC category, though headline framing and agent orchestration depth need refinement.
- Uncertainty: Representation is proxy-derived; headline currently uses 'Technical Architect' rather than Staff/Principal AI Engineer framing that matches 96% of target roles.

### Citations
- Platform design appears in 24/25 roles (96%); candidate has Commander-4 platform lead evidence at data/master-cv/roles/01_seven_one_entertainment.md:28
- RAG 9/25 (36%), evaluation_quality 5/25 (20%), guardrails_governance 7/25 (28%) — all supported by Commander-4 curated evidence
- Player_coach 11/25 (44%) matches mentoring 10+ engineers at data/master-cv/roles/01_seven_one_entertainment.md:231

## Score Breakdown

- Candidate evidence coverage: 8.50
- Evidence curation completeness: 7.50
- Master CV representation quality: 7.00
- AI / architecture fit: 8.00
- Leadership / scope fit: 8.00
- Impact proof strength: 8.50

### Weighted Score Explanation
- Evidence coverage (8.5 × 0.30 = 2.55): Platform architecture, RAG, evaluation, guardrails, and distributed systems all strongly supported by Commander-4 and legacy modernization evidence.
- Curation completeness (7.5 × 0.15 = 1.125): Core AI platform work is curated; some upstream STAR records and Daypaio evidence remain pending promotion.
- Representation quality (7.0 × 0.25 = 1.75): AI platform and reliability metrics are surfaced, but headline uses 'Technical Architect' instead of Staff/Principal AI Engineer title family that matches 96% of roles.
- AI architecture fit (8.0 × 0.15 = 1.20): Strong RAG, hybrid search, evaluation harness, and guardrails evidence; agent orchestration is present via MCP tools but not as deeply articulated as multi-agent patterns.
- Leadership scope fit (8.0 × 0.10 = 0.80): Player-coach mentoring of 10+ engineers with 3 promotions fits category scope; hiring involvement supports but does not over-claim.
- Impact proof strength (8.5 × 0.05 = 0.425): Quantified metrics include 75% incident reduction, 3 years zero downtime, 2,000 users, 42 plugins, and 25% velocity improvement.

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28 — Commander-4 platform lead with hybrid search, LLM-as-judge, semantic caching, evaluation harness
- data/master-cv/roles/01_seven_one_entertainment.md:77 — 75% incident reduction, 3 years zero downtime
- data/master-cv/roles/01_seven_one_entertainment.md:231 — mentored 10+ engineers, promoted 3 to lead

## Strongest Supported Signals

### AI platform architecture with production RAG and hybrid retrieval
- Why it matters: Platform design appears in 24/25 roles (96%) and RAG in 9/25 (36%); architecture is the top valued evidence type in deep-analysis samples.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:8
- Citation: BM25 + RRF hybrid search with LLM-as-judge reranking via Claude Sonnet serving 2,000 users across 42 plugins

### Evaluation harness with retrieval quality metrics
- Why it matters: Evaluation_quality appears in 5/25 (20%) and is a differentiator; this category values AI quality and production behavior over generic prompt claims.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7
- Citation: MRR@k and NDCG@k (exponential gain) scoring functions with 14 unit tests for retrieval quality evaluation

### Guardrails and governed structured outputs for enterprise AI
- Why it matters: Guardrails_governance appears in 7/25 (28%); shows practical controls and safe production behavior.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- Citation: Zod schema validation, composable guardrail profiles across 42 plugins, per-silo guardrail injection via LiteLLM proxy with access-control-aware behavior

### Legacy platform modernization with reliability outcomes
- Why it matters: Reliability is cited in 18 deep-analysis samples; success metrics cluster around reliability (4), performance (3), scalability (2).
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77
- Citation: Transformed legacy JS AdTech platform to TypeScript microservices on AWS; achieved 75% incident reduction and 3 years zero downtime

### Player-coach mentoring with quantified team development
- Why it matters: Player_coach 11/25 (44%) and mentoring 12/25 (48%); shows technical leadership without overstating formal management.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:172
- Citation: Mentored 10+ senior engineers on architectural patterns, event-driven design, and cloud best practices; promoted 3 engineers to lead positions

### MCP tool design and external system integrations
- Why it matters: Agent orchestration appears in 12/25 (48%); MCP tool design shows production AI integration capability.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4_skills.json:22
- Citation: 5 MCP server tools for external system integrations within Commander-4 enterprise AI workflow platform

### Event-driven distributed systems architecture
- Why it matters: Distributed systems appears in 7/25 (28%); backend foundations matter under the AI layer.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:172
- Citation: EventBridge choreography, autonomous event-driven TypeScript microservices, DDD with bounded contexts

## Gap Analysis

### curated_but_underrepresented
- Signal: Staff/Principal AI Engineer title framing in headline
- Why it matters: Title families cluster around principal_engineer 13/25 (52%) and staff_engineer 11/25 (44%); current headline uses 'Technical Architect' which may not trigger ATS or recruiter pattern matching for this category.
- Current state: Headline reads 'Technical Architect / AI Platform Architect' per data/master-cv/role_metadata.json:4
- Safe interpretation: Evidence supports Staff AI Engineer positioning given platform lead role and 11 years experience.
- Recommended action: Update headline to 'Staff AI Engineer | AI Platform Architecture, Distributed Systems, Production GenAI' per blueprint safe title families.
- Evidence refs: data/master-cv/role_metadata.json:4, data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: Blueprint recommends Staff/Principal framing first because title families cluster around principal_engineer 13/25 (52%) and staff_engineer 11/25 (44%)

- Signal: Agent orchestration beyond MCP tools
- Why it matters: Agents_orchestration appears in 12/25 (48%); showing reusable agent workflow systems and orchestration logic is a differentiator.
- Current state: MCP tools (5) are curated but broader agent orchestration patterns are not emphasized in current representation.
- Safe interpretation: MCP integration is valid agent orchestration evidence; can be positioned as agent-enabling infrastructure.
- Recommended action: Surface Commander-4 as agent-enabling platform in summary; emphasize workflow plugin system (42 plugins) as reusable AI workflow orchestration.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:2
- Citation: Category values shipped agent workflows and reusable tool integrations; agents_orchestration 12/25 (48%)

- Signal: Observability pipeline at billions-scale
- Why it matters: Observability appears in 6/25 (24%); scale proof strengthens reliability narrative valued by this category.
- Current state: Observability pipeline with billions of events daily is curated at data/master-cv/roles/01_seven_one_entertainment.md:103 but not prominently surfaced in role priorities.
- Safe interpretation: Evidence is strong and can be elevated in experience bullets for this category.
- Recommended action: Elevate observability pipeline achievement to top-4 experience bullets for Staff AI Engineer applications; include 'billions of events' scale marker.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:103
- Citation: Valued evidence types include reliability 18 samples; hard skill observability 6/25 (24%)

- Signal: Semantic caching latency and cost reduction metrics
- Why it matters: Production reliability and cost efficiency matter for platform delivery; quantified caching impact proves production judgment.
- Current state: Two-tier semantic caching with L1 ~2ms and L2 ~200ms is curated but cost/latency reduction percentages are not quantified.
- Safe interpretation: Cache architecture is proven; can claim latency tiers without fabricating reduction percentages.
- Recommended action: Surface semantic caching latency tiers explicitly in experience bullets; add cost reduction claim only if Lantern project 40% reduction applies to Commander-4.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/lantern.md:10
- Citation: L1 exact-match ~2ms, L2 semantic similarity ~200ms via Redis TTL and S3 Vectors cosine search

- Signal: Cross-functional collaboration with product/security stakeholders
- Why it matters: Collaboration appears in 23/25 (92%); this is the most consistent soft skill signal in the category.
- Current state: Stakeholder alignment is mentioned in Technical Vision achievement but collaboration is not emphasized in summary or headline.
- Safe interpretation: Evidence supports cross-functional collaboration claims across AdTech and AI platform work.
- Recommended action: Add 'cross-functional collaboration' to summary positioning; emphasize product owner and enterprise architect alignment in experience bullets.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:172, data/master-cv/roles/01_seven_one_entertainment.md:299
- Citation: Collaboration 23/25 (92%) is highest soft skill; blueprint recommends showing how you aligned product, platform, security, and engineering stakeholders

### supported_upstream_pending_curation
### unsupported_or_unsafe
- Signal: Go language depth for backend systems
- Why it matters: Go appears in 4/25 (16%) of roles; some Staff AI Engineer roles expect Go expertise.
- Current state: No curated evidence of Go development; primary languages are TypeScript and Python.
- Safe interpretation: Do not claim Go expertise; position TypeScript/Python as primary backend languages with Node.js and Python-based ML integration.
- Recommended action: Do not add Go claims; focus on TypeScript distributed systems and Python AI layer evidence.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: Blueprint unsafe claims include 'Deep production backend delivery in Go unless the CV clearly proves Go depth'

- Signal: Direct SLO/SLI ownership and incident response programs
- Why it matters: Some roles expect direct SLO/SLI ownership; blueprint flags this as an unsafe claim without explicit evidence.
- Current state: MTTR reduction and incident management culture are mentioned but formal SLO/SLI ownership is not documented.
- Safe interpretation: Can claim incident reduction outcomes and monitoring/alerting implementation; should not claim SLO program ownership.
- Recommended action: Position as reliability-focused architect with incident reduction outcomes; avoid claiming SLO/SLI program ownership unless Lantern project SLO/SLI Design skill is promoted to Commander-4.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:212, data/master-cv/projects/lantern_skills.json:38
- Citation: Blueprint unsafe claims include 'Ownership of SLOs, incident response, or reliability programs unless the CV shows direct operational scope'

- Signal: Multi-cloud implementation breadth
- Why it matters: Multi_cloud appears in 8 deep-analysis samples; some roles expect cross-cloud platform work.
- Current state: Evidence shows AWS-centric delivery (Lambda, ECS, EventBridge, S3, CloudFront); Lantern mentions OpenAI/Anthropic/Azure endpoints but not full multi-cloud infrastructure.
- Safe interpretation: Can claim AWS platform delivery and multi-provider LLM integration; should not claim full multi-cloud infrastructure implementation.
- Recommended action: Position as AWS-experienced with multi-provider LLM gateway integration; avoid claiming GCP/Azure infrastructure deployment.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/projects/lantern.md:7
- Citation: Blueprint warns against 'Full multi-cloud implementation across Bedrock and Vertex AI if the work was only on one cloud or one provider'

## Safe Claims Now

### headline_safe
- Staff AI Engineer
- AI Platform Architecture
- Production AI Systems
- Distributed Systems
- Enterprise AI Workflows

### profile_safe
- Architected and shipped enterprise AI workflow platform serving 2,000 users with 42 workflow plugins
- Built production RAG systems with hybrid retrieval (BM25 + RRF fusion) and LLM-as-judge reranking
- Designed evaluation harnesses with MRR@k and NDCG@k retrieval quality metrics
- Implemented governed structured outputs and per-silo guardrails for multi-tenant AI safety
- Transformed legacy platforms into event-driven TypeScript microservices achieving 75% incident reduction
- Led observability pipeline channeling billions of events daily with real-time dashboards
- Player-coach technical leader mentoring 10+ engineers and promoting 3 to lead positions

### experience_safe
- Platform lead for Commander-4 (Joyia) enterprise AI workflow platform at ProSiebenSat.1
- BM25 scoring from scratch for S3 Vectors with RRF fusion (k=60)
- LLM-as-judge reranking via Claude Sonnet through LiteLLM gateway with parallel execution
- Two-tier semantic caching with L1 exact-match (~2ms) and L2 semantic similarity (~200ms)
- 5 MCP server tools for external system integrations
- Zod schema validation for type-safe LLM outputs across 42 workflow plugins
- 3 years zero downtime on revenue-critical AdTech platform
- DDD bounded contexts reducing developer onboarding from 6 to 3 months

### leadership_safe
- Mentored 10+ senior engineers on architectural patterns, event-driven design, and cloud best practices
- Promoted 3 engineers to lead positions
- Established architectural north star and technical vision with stakeholder alignment
- Led hiring process including selection criteria, interview strategies, and technical assessments
- Cross-functional collaboration with product owners, enterprise architects, and stakeholders

### unsafe_or_too_weak
- Go language expertise — no curated evidence of Go development
- SLO/SLI program ownership — incident reduction shown but not formal SLO programs
- Direct MCP/OpenAI/Anthropic platform engineering — integration only, not platform development
- Multi-cloud infrastructure deployment — AWS-focused with multi-provider LLM routing only
- Formal people management or hiring authority — player-coach scope only
- Fine-tuning, custom embedding training, or RLHF — explicitly flagged in do_not_claim
- Millions-scale user claims — 2,000 platform users documented, not consumer-scale

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28 — Commander-4 platform lead evidence
- data/master-cv/roles/01_seven_one_entertainment.md:231 — 10+ engineers mentored, 3 promoted
- data/master-cv/projects/commander4_skills.json:42 — do_not_claim: fine-tuning, RLHF, custom embedding training

## Representation Diagnosis

### well_represented_now
- RAG and hybrid retrieval with BM25+RRF fusion — prominent in role_priority_current_state
- Evaluation harnesses with MRR@k and NDCG@k metrics — surfaced in projects
- Guardrails and governed structured outputs — mentioned in summary and projects
- Legacy modernization with reliability outcomes — 75% incident reduction visible
- MCP tool integration — 5 MCP server tools documented

### underrepresented_now
- Staff/Principal AI Engineer title framing — headline uses 'Technical Architect' instead
- Agent orchestration as category keyword — MCP tools present but 'agent orchestration' language not used
- Observability pipeline scale — 'billions of events' not in top-4 experience priorities
- Cross-functional collaboration emphasis — present in evidence but not in summary
- Semantic caching latency metrics — L1/L2 timing documented but not prominently surfaced

### overstated_risk_now
- Headline may imply broader architecture scope than AI-specific platform work for this category
- Summary mentions 'large-scale platform modernization' without quantifying scale relative to enterprise AI context

### representation_priorities
- 1. Update headline to Staff AI Engineer title family with AI Platform Architecture focus
- 2. Add agent orchestration and workflow automation language to summary
- 3. Elevate observability pipeline to top-4 experience bullets with billions-scale marker
- 4. Add cross-functional collaboration to profile positioning
- 5. Ensure semantic caching latency tiers are visible in experience section

### Citations
- data/master-cv/role_metadata.json:4 — current headline 'Technical Architect / AI Platform Architect'
- data/master-cv/role_metadata.json:5 — current summary mentions RAG, guardrails, evaluation harnesses
- data/master-cv/roles/01_seven_one_entertainment.md:103 — observability pipeline with billions of events underrepresented

## Curation Priorities

### 1. Promote upstream STAR records for Seven.One Technical Lead with agent orchestration framing
- Why now: Agents_orchestration appears in 12/25 (48%); upstream evidence at docs/archive/knowledge-base.md:268 has overlap score 28 and may contain additional agent workflow details not yet curated.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: docs/archive/knowledge-base.md:268, docs/archive/knowledge-base.md:360
- Expected impact: Strengthens agent orchestration signal from curated but underrepresented to prominently surfaced differentiator.
- Citation: Upstream pending curation signals show overlap score 28 and 26 for Technical Lead - Addressable TV records

### 2. Curate Daypaio event-sourced architecture evidence for distributed systems depth
- Why now: Distributed systems appears in 7/25 (28%); Daypaio CQRS/EventStore work adds backend architecture proof beyond current Seven.One focus.
- Target files: data/master-cv/roles/02_samdock_daypaio.md
- Source refs: docs/archive/knowledge-base.md:734
- Expected impact: Adds 0→1 platform architecture evidence with event sourcing that category candidate-mapping explicitly values.
- Citation: Upstream signal 'DAYPAIO GmbH — Senior Software Engineer Full Stack - Tech Lead' has overlap score 29

### 3. Extract quantified observability and reliability metrics from upstream STAR records
- Why now: Reliability is cited in 18 deep-analysis samples; upstream records may contain additional incident reduction, MTTR, or scale metrics not fully quantified in curated store.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: docs/archive/knowledge-base.md:7, docs/archive/knowledge-base.md:98
- Expected impact: Strengthens impact proof with additional quantified reliability outcomes.
- Citation: Upstream 'Lead Software Engineer / Technical Architect' records have high overlap scores 29 and 22

## Master CV Upgrade Actions

### 1. Update headline from 'Technical Architect / AI Platform Architect' to 'Staff AI Engineer | AI Platform Architecture, Distributed Systems, Production GenAI'
- Section: `headline`
- Why now: Title families cluster around principal_engineer 13/25 (52%) and staff_engineer 11/25 (44%); current headline may not match ATS patterns for this category.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/role_metadata.json:4
- Citation: Blueprint recommends safe title families including 'Staff AI Engineer', 'Principal AI Engineer', 'Staff Software Engineer, AI/ML'

### 2. Revise summary to lead with architecture-first senior IC positioning and add agent orchestration, cross-functional collaboration language
- Section: `summary`
- Why now: Collaboration 23/25 (92%) is highest soft skill; agents_orchestration 12/25 (48%) is key differentiator; current summary does not emphasize either.
- Supported by: data/master-cv/role_metadata.json:5, data/master-cv/roles/01_seven_one_entertainment.md:172
- Citation: Blueprint positioning angle recommends 'Architecture-first senior IC who ships production AI platforms' with collaboration as force multiplier

### 3. Elevate observability pipeline achievement from line 103 to top-4 experience priorities with billions-scale marker
- Section: `role_bullets`
- Why now: Observability appears in 6/25 (24%); scale proof strengthens reliability narrative that ranks as top success metric cluster.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:103
- Citation: Valued evidence types include reliability 18 deep-analysis samples; observability is category-relevant hard skill

### 4. Add 'agent orchestration' and 'workflow automation' as skills; ensure 'cross-functional collaboration' visible in skills or summary
- Section: `skills`
- Why now: Agents_orchestration 12/25 (48%) and collaboration 23/25 (92%) are high-frequency category signals not explicitly surfaced as skills.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:2
- Citation: Blueprint preferred vocabulary includes 'agent orchestration' and 'cross-functional collaboration'

### 5. Surface semantic caching latency tiers (L1 ~2ms, L2 ~200ms) explicitly in Commander-4 project bullets
- Section: `projects`
- Why now: Production reliability and latency proof matter; current project description mentions semantic caching but not specific latency tiers.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/commander4.md:9
- Citation: L1 exact-match ~2ms, L2 semantic similarity ~200ms documented in curated evidence but not prominently surfaced

## Evidence Ledger

- `curated_but_underrepresented` (high): Lead the CV as a Staff/Principal AI Engineer architecture-focused senior IC, not as a generic Technical Architect.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/role_metadata.json:4
- `supported_and_curated` (high): Make RAG, hybrid retrieval, and evaluation harnesses prominent in experience section — these are differentiators for this category.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7, data/master-cv/projects/commander4.md:8
- `supported_and_curated` (high): Show guardrails and governed structured outputs as enterprise AI production safety proof.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- `curated_but_underrepresented` (high): Emphasize agent orchestration via MCP tools and workflow plugin system as reusable AI platform capability.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:2
- `curated_but_underrepresented` (high): Promote observability pipeline with billions-scale marker to top experience priorities.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:103
- `supported_and_curated` (high): Position mentoring and player-coach influence without inflating to formal people management claims.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:172
- `supported_upstream_pending_curation` (medium): Curate upstream Daypaio CQRS/EventStore evidence to strengthen distributed systems backend foundation.
  Support: docs/archive/knowledge-base.md:734
- `unsupported_or_unsafe` (high): Do not claim Go language depth, SLO program ownership, or multi-cloud infrastructure deployment.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:77
- `unsupported_or_unsafe` (high): Do not claim fine-tuning, custom embedding training, or RLHF — explicitly flagged in do_not_claim.
  Support: data/master-cv/projects/commander4_skills.json:42
- `supported_and_curated` (high): Frame non-AI backend/platform history as the foundation for production AI delivery rather than hiding it.
  Support: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/02_samdock_daypaio.md:27
