# AI Architect — Global/Remote Baseline

- Category ID: `ai_architect_global`
- Macro family: `ai_architect`
- Priority: `primary_target`
- Confidence: `high`
- Representation proxy mode: `True`

## Overall Assessment

- Combined fit score: **7.80 / 10**
- Readiness tier: **GOOD**
- Verdict: Strong evidence for enterprise AI platform architecture with production RAG, evaluation harnesses, and guardrails at Commander-4 positions this candidate well for AI Architect roles, though agent orchestration and multi-provider experience need better surfacing.
- Uncertainty: Representation is proxy-derived; player-coach scope and consulting-style stakeholder work are supported but underrepresented in current master CV framing.

### Citations
- Platform design 87/88 (98.9%) in category; Commander-4 serves 2,000 users with 42 plugins per data/master-cv/roles/01_seven_one_entertainment.md:28
- Architecture valued evidence 20/20; candidate shows hybrid search, evaluation harness, guardrails per data/master-cv/projects/commander4.md:6-10
- Senior_ic 79% in category; candidate evidence shows mentoring 10+ engineers and stakeholder SME work per data/master-cv/roles/01_seven_one_entertainment.md:231 and :299

## Score Breakdown

- Candidate evidence coverage: 8.00
- Evidence curation completeness: 7.00
- Master CV representation quality: 7.50
- AI / architecture fit: 8.50
- Leadership / scope fit: 8.00
- Impact proof strength: 7.50

### Weighted Score Explanation
- Evidence coverage (8.0 × 0.30 = 2.40): Strong Commander-4 AI platform evidence with RAG, evaluation, guardrails, semantic caching, and MCP tools covering most category signals; agents/orchestration evidence exists but is less explicit.
- Curation completeness (7.0 × 0.15 = 1.05): Commander-4 and Seven.One modernization well-curated; upstream STAR records show additional stakeholder and architecture evidence not yet promoted.
- Representation quality (7.5 × 0.25 = 1.875): Headline fits category; summary captures AI platform work but underweights guardrails, evaluation, and stakeholder translation signals.
- AI architecture fit (8.5 × 0.15 = 1.275): Direct match on platform design, RAG, evaluation harness, guardrails, enterprise integration, and production delivery at scale.
- Leadership scope fit (8.0 × 0.10 = 0.80): Evidence supports senior IC/player-coach framing with mentoring and stakeholder alignment; no inflation into management claims.
- Impact proof strength (7.5 × 0.05 = 0.375): Good quantification (2,000 users, 75% incident reduction, billions of events daily) but could strengthen cost and scalability metrics.

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28 - Commander-4 platform lead with retrieval quality and runtime control
- data/master-cv/projects/commander4.md:6 - governed structured outputs, MCP tools, per-silo guardrails
- data/master-cv/roles/01_seven_one_entertainment.md:77 - 75% incident reduction, 3 years zero downtime
- data/master-cv/roles/01_seven_one_entertainment.md:231 - mentored 10+ engineers, promoted 3

## Strongest Supported Signals

### Enterprise AI platform architecture with production delivery
- Why it matters: Platform design appears in 98.9% of roles and architecture is the top valued evidence type in 20/20 deep analyses. Commander-4 directly proves target-state design and shipped enterprise AI.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:2
- Citation: Platform design 87/88 (98.9%); architecture valued evidence 20/20; Commander-4 serves 2,000 users across 42 plugins

### RAG pipeline with hybrid search and retrieval evaluation
- Why it matters: RAG appears in 28.4% of roles and evaluation/quality in 20.5%. Evidence shows BM25+RRF hybrid search, LLM-as-judge reranking, MRR@k and NDCG@k scoring functions.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7, data/master-cv/projects/commander4.md:8
- Citation: RAG 25/88 (28.4%); evaluation/quality 18/88 (20.5%); candidate implements BM25 scoring, RRF fusion, MRR@k, NDCG@k

### Guardrails, governance, and per-silo access control
- Why it matters: Guardrails/governance appears in 37.5% of roles. Evidence shows per-silo guardrail injection via LiteLLM proxy, access-control-aware workflow behavior, and content policy enforcement.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/projects/commander4.md:6, data/master-cv/projects/commander4.md:7, data/master-cv/roles/01_seven_one_entertainment.md:55
- Citation: Guardrails/governance 33/88 (37.5%); governance valued evidence 10/20; Commander-4 shows 42 workflow plugins with per-silo guardrail injection

### Legacy modernization and distributed systems architecture
- Why it matters: The category favors architects who can modernize existing systems as well as build greenfield. Evidence shows transformation from legacy JS to event-driven microservices with 75% incident reduction.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:103
- Citation: Greenfield_split: both 42 in category; delivery valued evidence 19/20; candidate shows 3 years zero downtime post-modernization

### Semantic caching and LLM gateway architecture
- Why it matters: Production AI platforms need runtime efficiency and cost control. Evidence shows two-tier semantic caching (L1 exact-match, L2 cosine similarity) and LiteLLM gateway design.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/commander4.md:9, data/master-cv/projects/lantern.md:10
- Citation: Cost valued evidence 7/20; performance 5/20; candidate shows L1 ~2ms, L2 ~200ms caching with SHA-256 and cosine similarity

### Stakeholder translation and cross-functional collaboration
- Why it matters: Communication appears in 76.1% and stakeholder management in 44.3% of roles. Evidence shows SME consultation, business stakeholder education on technical debt ROI, and product owner collaboration.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:172, data/master-cv/roles/01_seven_one_entertainment.md:299, data/master-cv/roles/01_seven_one_entertainment.md:315
- Citation: Communication 67/88 (76.1%); stakeholder management 39/88 (44.3%); candidate shows business stakeholder education and SME collaboration

## Gap Analysis

### curated_but_underrepresented
- Signal: Agents and orchestration connected to enterprise systems
- Why it matters: Agents/orchestration appears in 38.6% of roles as the leading GenAI production signal. The category distinctly values agentic system design over isolated prompt work.
- Current state: Evidence shows 5 MCP server tools for external integrations and workflow plugins, but agent orchestration patterns, routing logic, and production controls around agentic flows are not prominently surfaced.
- Safe interpretation: MCP tool design implies agent-adjacent capability but explicit agent workflow evidence is underrepresented in current framing.
- Recommended action: Surface MCP tool design and workflow orchestration more explicitly in headline or summary; add agent-oriented language to Commander-4 bullets if accurate.
- Evidence refs: data/master-cv/projects/commander4.md:6, data/master-cv/roles/01_seven_one_entertainment.md:55
- Citation: Agents/orchestration 34/88 (38.6%); MCP tools exist in curated evidence but agent workflow framing is underrepresented

- Signal: Player-coach mentoring and technical guidance scope
- Why it matters: Player_coach scope is material at 38% and mentoring appears in 20.5% of roles. The category rewards architecture leadership with technical coaching, not pure management.
- Current state: Evidence shows mentoring 10+ engineers and promoting 3, but this is not surfaced prominently in summary or headline. The player-coach angle is implicit rather than explicit.
- Safe interpretation: Mentoring evidence is curated and claimable but underweighted in representation.
- Recommended action: Strengthen player-coach language in summary; surface mentoring and design review evidence in role framing.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:172
- Citation: Player_coach 38%; mentoring 18/88 (20.5%); candidate has mentored 10+ engineers per curated evidence

- Signal: GDPR, EU AI Act, or compliance program ownership
- Why it matters: GDPR appears in 9.1% and EU AI Act in 2.3% of roles. Compliance signals can differentiate but require explicit ownership evidence.
- Current state: Evidence shows GDPR/TCF compliance program leadership with successful BLM regulatory audits, but this is not surfaced for AI Architect framing.
- Safe interpretation: GDPR compliance evidence exists but is AdTech-specific rather than AI-specific. Safe to mention as regulatory experience but not as AI compliance authority.
- Recommended action: Keep GDPR evidence available for compliance-sensitive roles but do not foreground as AI-specific governance ownership.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:155
- Citation: GDPR 8/88 (9.1%); EU AI Act 2/88 (2.3%); candidate shows GDPR/TCF success but in AdTech domain

### supported_upstream_pending_curation
- Signal: Consulting-style stakeholder translation in enterprise environments
- Why it matters: Consulting and consultancy appear 20 times in market context. The category leans toward consulting-flavored architecture translation for enterprise AI rollout.
- Current state: Upstream STAR records reference stakeholder collaboration, business metrics identification, and client-facing work more explicitly than curated evidence currently captures.
- Safe interpretation: Curated evidence shows stakeholder alignment but upstream records may strengthen consulting-style framing if promoted.
- Recommended action: Review upstream STAR records at docs/archive/knowledge-base.md:7 and :268 for client-facing and stakeholder translation details; promote to curated store if accurate.
- Evidence refs: docs/archive/knowledge-base.md:7, docs/archive/knowledge-base.md:268
- Citation: Consulting 17, consultancy 3 in domain context; upstream shows stakeholder collaboration evidence pending curation

### unsupported_or_unsafe
- Signal: Multi-cloud or provider-specific architecture authority
- Why it matters: Azure and AWS each appear in 15.9% of roles and multi_cloud in 29%. Provider branding can differentiate but requires explicit delivery evidence.
- Current state: Evidence shows AWS Lambda, EventBridge, ECS, CloudFront but no Azure or GCP AI service delivery. Multi-cloud claims are not supported.
- Safe interpretation: AWS-native services are evidenced for platform infrastructure but not explicitly for AI/ML services. Azure and multi-cloud are unsafe claims.
- Recommended action: Do not claim Azure, GCP, or multi-cloud authority. AWS infrastructure is safe to claim but AWS AI services (Bedrock, SageMaker) are not evidenced.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77
- Citation: Azure 14/88 (15.9%), AWS 14/88 (15.9%), multi_cloud 29%; candidate shows AWS infrastructure but not multi-cloud AI delivery

- Signal: Hiring, org-building, or performance management ownership
- Why it matters: Hiring appears in only 2.3% and org_building in 11.4% of roles. The category does not expect people management as a core signal.
- Current state: Evidence shows hiring process definition at one role but scope is limited. No performance management or org-building evidence.
- Safe interpretation: Hiring involvement is mentioned but not as ownership. Do not inflate into management claims.
- Recommended action: Keep hiring reference compressed; do not foreground people management or org-building in AI Architect positioning.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:266
- Citation: Hiring 2/88 (2.3%); performance management 2/88 (2.3%); org_building 10/88 (11.4%); management scope is weak evidence

## Safe Claims Now

### headline_safe
- AI Solution Architect
- AI Architect
- AI Platform Architect
- Enterprise AI Platform, Agents, Integration & Governance

### profile_safe
- Enterprise AI platform design and production delivery
- RAG pipeline architecture with hybrid search and evaluation harnesses
- Guardrails, governance, and per-silo access control for AI workflows
- Semantic caching and LLM gateway design
- Legacy platform modernization to event-driven microservices
- Stakeholder translation and cross-functional collaboration

### experience_safe
- Commander-4 (Joyia) enterprise AI workflow platform serving 2,000 users
- BM25 + RRF hybrid search with LLM-as-judge reranking
- MRR@k and NDCG@k retrieval evaluation harness with 14 unit tests
- 42 workflow plugins with per-silo guardrail injection via LiteLLM proxy
- 5 MCP server tools for external integrations
- Two-tier semantic caching (L1 exact-match, L2 cosine similarity)
- Legacy JavaScript to TypeScript microservices transformation with 75% incident reduction
- Observability pipeline processing billions of events daily

### leadership_safe
- Senior individual contributor and player-coach
- Mentored 10+ senior engineers on architectural patterns
- Stakeholder alignment and technical debt ROI education
- Subject matter expert on enterprise architecture challenges
- Collaborative architecture design and pattern guidance

### unsafe_or_too_weak
- Head of AI, Director of AI, VP AI, Engineering Manager titles
- AWS or Azure AI services authority (Bedrock, SageMaker, Azure OpenAI)
- Multi-cloud architecture ownership
- Customer-facing solution architect or workshops
- Hiring ownership or org-building
- Research, PhD, or advanced experimentation framing
- DevOps or infrastructure ownership (vs architecture collaboration)
- GDPR/EU AI Act AI-specific compliance ownership

### Citations
- Title families: solutions_architect 50%, ai_architect 37% per blueprint; candidate current title Technical Architect/AI Platform Architect fits
- data/master-cv/roles/01_seven_one_entertainment.md:28 - Commander-4 evidence supports enterprise AI platform claims
- data/master-cv/roles/01_seven_one_entertainment.md:231 - mentoring evidence supports player-coach but not management claims
- Blueprint unsafe claims: AWS ownership, customer-facing architecture, DevOps ownership without explicit evidence

## Representation Diagnosis

### well_represented_now
- Enterprise AI platform architecture via Commander-4 lead position
- RAG pipeline with hybrid search (BM25, RRF, vector search)
- Retrieval evaluation harness (MRR@k, NDCG@k)
- Semantic caching architecture (two-tier L1/L2)
- Legacy modernization to event-driven microservices
- TypeScript and Python implementation depth

### underrepresented_now
- Agents and orchestration framing (MCP tools exist but agent language is weak)
- Player-coach and mentoring scope in summary/headline
- Guardrails and governance as explicit production control signals
- Stakeholder translation and enterprise consulting-style work
- Scale and reliability outcomes (cost, latency, throughput metrics)
- Evaluation harness positioned as production quality gate

### overstated_risk_now
- Headline may imply broader Technical Architect scope than AI-focused category expects
- AWS infrastructure evidence could be misread as AWS AI services authority
- Hiring bullet could inflate management scope if not properly scoped

### representation_priorities
- P1: Add explicit agent/orchestration language to Commander-4 framing if accurate
- P2: Surface player-coach mentoring in summary rather than buried in mid-priority bullet
- P3: Strengthen guardrails/governance as production-ready AI signal in headline or summary
- P4: Add cost/latency/reliability metrics to architecture outcomes where evidenced
- P5: Position evaluation harness as production quality gate, not just test coverage

### Citations
- data/master-cv/role_metadata.json:4 - current headline 'Technical Architect / AI Platform Architect'
- data/master-cv/role_metadata.json:5 - summary mentions AI platform but underweights guardrails and stakeholder translation
- data/master-cv/projects/commander4.md:6 - MCP tools exist but agent framing underrepresented
- Blueprint: agents/orchestration 38.6%, guardrails/governance 37.5% - both material signals

## Curation Priorities

### 1. Promote stakeholder translation and consulting-style architecture work from upstream STAR records
- Why now: Category values consulting-flavored stakeholder work (consulting 17, consultancy 3 in context) and communication appears in 76.1% of roles. Upstream records show richer evidence than currently curated.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md, data/master-cv/role_metadata.json
- Source refs: docs/archive/knowledge-base.md:7, docs/archive/knowledge-base.md:268, docs/archive/knowledge-base.md:360
- Expected impact: Strengthens stakeholder management signal from curated-but-underrepresented to well-represented; improves representation quality score.
- Citation: Communication 67/88 (76.1%); stakeholder management 39/88 (44.3%); upstream shows high overlap scores 23 and 20

### 2. Curate explicit agent workflow and orchestration evidence from Commander-4 work if exists
- Why now: Agents/orchestration is the top GenAI signal at 38.6%. MCP tools are curated but explicit agent workflow routing, multi-step orchestration, or tool-calling patterns need promotion.
- Target files: data/master-cv/projects/commander4.md, data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: data/master-cv/projects/commander4.md:6
- Expected impact: Elevates agents/orchestration from curated-but-underrepresented to well-represented; improves AI architecture fit score.
- Citation: Agents/orchestration 34/88 (38.6%); MCP Tool Design verified skill but agent workflow framing missing

### 3. Add cost, latency, and throughput metrics to architecture outcomes
- Why now: Scale valued evidence 15/20, reliability 11/20, cost 7/20 in deep analyses. Current metrics focus on incident reduction and users; cost efficiency and latency outcomes are underrepresented.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md, data/master-cv/projects/commander4.md
- Source refs: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/lantern.md:10
- Expected impact: Strengthens impact proof strength; improves production maturity signal.
- Citation: Semantic cache shows ~2ms L1, ~200ms L2; Lantern shows ~40% API cost reduction - metrics exist but are buried

### 4. Review and promote Daypaio CQRS/event-sourcing evidence for distributed systems foundation
- Why now: Category pain points include CQRS/event sourcing as transferable evidence. Daypaio event-sourced CRM platform is curated but could be better positioned as architecture foundation.
- Target files: data/master-cv/roles/02_samdock_daypaio.md
- Source refs: docs/archive/knowledge-base.md:734
- Expected impact: Strengthens non-AI architecture foundation; supports modernization narrative.
- Citation: Deep-analysis candidate mapping values CQRS/event sourcing; Daypaio shows EventStore, CQRS, NestJS

## Master CV Upgrade Actions

### 1. Revise headline to emphasize AI Architect with enterprise platform, agents, and governance signals
- Section: `headline`
- Why now: Current headline 'Technical Architect / AI Platform Architect' is acceptable but could better match category title families (solutions_architect 50%, ai_architect 37%).
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:6
- Citation: Blueprint recommends: [AI Solution Architect / AI Architect] | Enterprise AI Platforms, Agents, Integration & Governance

### 2. Add player-coach and mentoring language to summary
- Section: `summary`
- Why now: Summary mentions player-coach but buries mentoring evidence. Category has player_coach 38% and mentoring 20.5%; this should be more prominent.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:172
- Citation: Player_coach 38%; mentoring 18/88 (20.5%); candidate evidence shows 10+ engineers mentored, 3 promoted

### 3. Surface guardrails and governance as explicit production control in summary or role lead
- Section: `summary`
- Why now: Guardrails/governance appears in 37.5% of roles. Current summary mentions guardrails but not as prominently as RAG or structured outputs.
- Supported by: data/master-cv/projects/commander4.md:6, data/master-cv/projects/commander4.md:7
- Citation: Guardrails/governance 33/88 (37.5%); governance valued evidence 10/20

### 4. Reframe MCP tools as agent-adjacent capability with orchestration language
- Section: `role_bullets`
- Why now: Agents/orchestration is the top GenAI signal at 38.6%. MCP tool design is curated but not framed with agent orchestration vocabulary.
- Supported by: data/master-cv/projects/commander4.md:6, data/master-cv/roles/01_seven_one_entertainment.md:55
- Citation: Agents/orchestration 34/88 (38.6%); MCP Tool Design verified skill needs agent framing

### 5. Add evaluation harness as production quality gate framing, not just test coverage
- Section: `projects`
- Why now: Evaluation/quality appears in 20.5% of roles. Current framing mentions MRR/NDCG but positions it alongside unit tests rather than as production quality gate.
- Supported by: data/master-cv/projects/commander4.md:7, data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: Evaluation/quality 18/88 (20.5%); eval-driven quality gates distinguish production-ready architects

### 6. Compress or contextualize hiring bullet to avoid management inflation
- Section: `role_bullets`
- Why now: Hiring appears in only 2.3% of roles. Current bullet could inflate management scope expectations for a category that is 79% senior_ic.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:266
- Citation: Hiring 2/88 (2.3%); manager 1%; senior_ic 79%; hiring bullet should not foreground management

## Evidence Ledger

- `supported_and_curated` (high): Lead with AI Architect branding showing enterprise platform design and production delivery
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:2
- `supported_and_curated` (high): Claim RAG pipeline with hybrid search, evaluation harness, and semantic caching
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7, data/master-cv/projects/commander4.md:8
- `supported_and_curated` (high): Claim guardrails and governance with per-silo access control
  Support: data/master-cv/projects/commander4.md:6, data/master-cv/roles/01_seven_one_entertainment.md:55
- `curated_but_underrepresented` (medium): Strengthen agent/orchestration language using MCP tool evidence
  Support: data/master-cv/projects/commander4.md:6
- `supported_upstream_pending_curation` (high): Promote stakeholder translation and consulting-style work from upstream STAR records
  Support: docs/archive/knowledge-base.md:7, docs/archive/knowledge-base.md:268
- `curated_but_underrepresented` (high): Surface player-coach mentoring more prominently in summary
  Support: data/master-cv/roles/01_seven_one_entertainment.md:231
- `supported_and_curated` (high): Claim legacy modernization and distributed systems as AI architecture foundation
  Support: data/master-cv/roles/01_seven_one_entertainment.md:77
- `unsupported_or_unsafe` (high): Do not claim AWS or Azure AI services authority without additional evidence
  Support: data/master-cv/roles/01_seven_one_entertainment.md:77
- `unsupported_or_unsafe` (high): Do not claim hiring, org-building, or management ownership
  Support: data/master-cv/roles/01_seven_one_entertainment.md:266
- `curated_but_underrepresented` (medium): Keep GDPR evidence available but do not frame as AI-specific compliance ownership
  Support: data/master-cv/roles/01_seven_one_entertainment.md:155
