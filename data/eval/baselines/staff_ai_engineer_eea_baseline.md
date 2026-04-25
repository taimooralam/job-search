# Staff AI Engineer — EEA Baseline

- Category ID: `staff_ai_engineer_eea`
- Macro family: `ai_engineering_adjacent`
- Priority: `secondary_target`
- Confidence: `high`
- Representation proxy mode: `True`

## Overall Assessment

- Combined fit score: **7.95 / 10**
- Readiness tier: **GOOD**
- Verdict: Strong production AI platform evidence with Commander-4/Joyia directly matching the category's core signals—platform architecture, evaluation harnesses, RAG pipelines, and reliability—while mentoring and player-coach evidence aligns with the senior IC profile; main gaps are headline framing and surfacing latency/scale metrics more explicitly.
- Uncertainty: Representation is proxy-derived from role_metadata.json; headline adjustment from 'Technical Architect' to 'Staff AI Engineer' framing is category-critical but not yet reflected in curated master CV.

### Citations
- Platform design 34/34 (100%); candidate evidence shows Commander-4 platform serving 2,000 users across 42 plugins — data/master-cv/roles/01_seven_one_entertainment.md:28
- Evaluation_quality 15/34 (44.1%); candidate has MRR@k, NDCG@k retrieval evaluation — data/master-cv/projects/commander4_skills.json:22
- Mentoring 20/34 (58.8%); candidate mentored 10+ engineers, promoted 3 — data/master-cv/roles/01_seven_one_entertainment.md:231

## Score Breakdown

- Candidate evidence coverage: 8.50
- Evidence curation completeness: 7.50
- Master CV representation quality: 7.00
- AI / architecture fit: 9.00
- Leadership / scope fit: 8.00
- Impact proof strength: 7.50

### Weighted Score Explanation
- candidate_evidence_coverage_score (8.5 × 0.30 = 2.55): Commander-4 provides direct evidence for platform design, evaluation harnesses, RAG pipelines, hybrid search, semantic caching, and guardrails—matching the category's table-stakes and differentiators. Minor gap in explicit agentic workflow depth.
- evidence_curation_completeness_score (7.5 × 0.15 = 1.125): Core AI platform work is well-curated with detailed technical implementation; upstream STAR records contain additional scalability and cross-functional evidence not yet promoted.
- master_cv_representation_quality_score (7.0 × 0.25 = 1.75): AI platform work prominently featured but headline uses 'Technical Architect' instead of category-aligned 'Staff AI Engineer'; reliability and latency metrics underrepresented in priority bullets.
- ai_architecture_fit_score (9.0 × 0.15 = 1.35): Enterprise AI platform with 2,000 users, hybrid retrieval (BM25+RRF), LLM-as-judge reranking, evaluation harness (MRR/NDCG), semantic caching, guardrails, and MCP tools—excellent category fit.
- leadership_scope_fit_score (8.0 × 0.10 = 0.80): Player-coach evidence with 10+ engineers mentored and 3 promoted; hiring evidence exists but appropriately understated; not overclaiming formal management.
- impact_proof_strength_score (7.5 × 0.05 = 0.375): Quantified outcomes (2,000 users, 42 plugins, 75% incident reduction, 3 years zero downtime) but latency/cost optimization metrics could be more explicit.

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28
- data/master-cv/roles/01_seven_one_entertainment.md:55
- data/master-cv/roles/01_seven_one_entertainment.md:77
- data/master-cv/roles/01_seven_one_entertainment.md:231
- data/master-cv/projects/commander4_skills.json:22

## Strongest Supported Signals

### Production AI platform architecture at enterprise scale
- Why it matters: Platform design is the clearest category anchor (34/34, 100%); Commander-4 serving 2,000 users across 42 plugins directly matches the primary hiring signal.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:6
- Citation: Platform design 34/34 (100%); valued evidence type architecture 20/20 deep-analysis samples.

### Retrieval evaluation with quality metrics (MRR@k, NDCG@k)
- Why it matters: Evaluation is the strongest AI-specific differentiator (15/34, 44.1%); explicit MRR/NDCG implementation with unit tests proves mature applied AI engineering.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7, data/master-cv/projects/commander4_skills.json:22
- Citation: Evaluation_quality 15/34 (44.1%); valued evidence type evaluation 15/20 deep-analysis samples.

### RAG pipeline with hybrid search (BM25 + RRF + semantic)
- Why it matters: RAG is a meaningful differentiator (10/34, 29.4%); custom BM25 implementation with RRF fusion and LLM-as-judge reranking shows production retrieval depth.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:8
- Citation: RAG 10/34 (29.4%); vector_search 6/34 (17.6%).

### Guardrails and governed AI workflows
- Why it matters: Guardrails supports applied AI stories (5/34, 14.7%); per-silo guardrail injection with access-control-aware behavior shows production safety patterns.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- Citation: Guardrails_governance 5/34 (14.7%); pain points emphasize production controls and safe AI behavior.

### Reliability and operational resilience
- Why it matters: Reliability is table-stakes (18/20 valued evidence); 75% incident reduction and 3 years zero downtime proves stable production operation.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:212
- Citation: Valued evidence type reliability 18/20; success metrics include reliability, resilience, and high availability.

### Mentoring and technical guidance without formal management
- Why it matters: Mentoring is table-stakes for player-coach profile (20/34, 58.8%); 10+ engineers mentored with 3 promoted to lead positions matches the role scope.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:172
- Citation: Mentoring 20/34 (58.8%), leadership 14/34 (41.2%), role scope player-coach 15/34.

### Cross-functional collaboration and communication
- Why it matters: Collaboration (29/34, 85.3%) and communication (23/34, 67.6%) are the most repeated soft-skill signals; stakeholder alignment and business education evidence supports this.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:172, data/master-cv/roles/01_seven_one_entertainment.md:299
- Citation: Collaboration 29/34 (85.3%), communication 23/34 (67.6%), cross-functional collaboration 8/34 (23.5%).

## Gap Analysis

### curated_but_underrepresented
- Signal: Explicit latency/throughput metrics for AI serving
- Why it matters: Pain points repeatedly emphasize low latency, high throughput, and maintainable scale (valued evidence types scale 14/20, cost 11/20); success metrics include latency optimization.
- Current state: Semantic caching latencies mentioned (~2ms L1, ~200ms L2) but not prominently surfaced; scaling patterns exist in legacy modernization but not connected to AI-specific throughput.
- Safe interpretation: Can claim latency-aware design for semantic caching and general platform scalability; cannot claim specific p99 latency targets or throughput benchmarks for LLM serving without additional evidence.
- Recommended action: Surface the 2ms/200ms cache latency metrics more prominently in role bullets; add any available throughput metrics from Commander-4 production.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/roles/01_seven_one_entertainment.md:195
- Citation: Valued evidence types scale 14/20, cost 11/20; success metrics include scalability, performance, latency optimization.

- Signal: Agentic workflow orchestration
- Why it matters: Agents/orchestration appears at 9/34 (26.5%); differentiator when tied to production controls and automation outcomes.
- Current state: MCP tool design (5 server tools) curated but not framed as agentic orchestration; structured outputs and tool-calling architecture exist but 'agent' language absent.
- Safe interpretation: Can claim tool-calling architecture and MCP integrations for external system access; frame as 'workflow orchestration' rather than autonomous agents unless deeper evidence exists.
- Recommended action: Reframe MCP tool design and structured outputs as 'workflow orchestration' in experience bullets; clarify if any autonomous agent behavior exists in Commander-4.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- Citation: Agents_orchestration 9/34 (26.5%); hard skill agentic workflows 3/34 (8.8%).

- Signal: Staff/Principal title-level scope evidence
- Why it matters: Title families concentrate in staff_engineer (20/34) and principal_engineer (13/34); headline must reflect senior IC scope with multi-team architecture influence.
- Current state: Current headline is 'Technical Architect / AI Platform Architect' which signals architecture scope but not Staff/Principal IC framing expected by this category.
- Safe interpretation: Evidence supports Staff AI Engineer positioning (11 years experience, platform lead, multi-team influence); headline adjustment is representation issue not evidence gap.
- Recommended action: Update headline to 'Staff AI Engineer' or 'Principal AI Engineer' framing with 'Platform Architecture' qualifier; current 'Technical Architect' is adjacent but not category-aligned.
- Evidence refs: data/master-cv/role_metadata.json:4, data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: Title families: staff_engineer 20/34, principal_engineer 13/34, senior_engineer 1/34.

- Signal: Cost optimization metrics for AI inference
- Why it matters: Cost evidence is valued (11/20 deep-analysis samples); semantic caching implies cost reduction but no explicit metrics surfaced.
- Current state: Two-tier semantic caching designed to reduce redundant LLM calls; Lantern project mentions '~40% reduction in redundant API spend' but this is personal project not enterprise.
- Safe interpretation: Can claim cost-aware design patterns; specific percentage claims require enterprise context confirmation.
- Recommended action: If Commander-4 has cost reduction metrics from semantic caching, surface them; otherwise frame as 'cost-optimized caching design'.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/lantern.md:10
- Citation: Valued evidence type cost 11/20; semantic caching reduces redundant API calls.

### supported_upstream_pending_curation
- Signal: Scalability and performance optimization for ML workloads
- Why it matters: The category values scaling AI-enabled services under latency/throughput/reliability constraints as a key achievement archetype (rank 4).
- Current state: Upstream STAR records mention scalability optimization but AI-specific scaling patterns not yet promoted to curated store; Lambda/ECS auto-scaling mentioned for backend, not explicitly for ML inference.
- Safe interpretation: Can claim platform-level scaling experience; ML-specific throughput optimization requires curation from upstream or new evidence.
- Recommended action: Review upstream STAR records (docs/archive/knowledge-base.md:360, :546) for any ML-specific scaling evidence; curate if found.
- Evidence refs: docs/archive/knowledge-base.md:360, docs/archive/knowledge-base.md:546
- Citation: Success metrics include scalability, performance, resilience; valued evidence types reliability 18/20, scale 14/20, cost 11/20.

### unsupported_or_unsafe
- Signal: Fine-tuning, RLHF, or custom embedding training
- Why it matters: Fine-tuning appears at 4/34 (11.8%) in the category; candidate explicitly lists these as do_not_claim.
- Current state: Explicitly marked as do_not_claim: fine-tuning pipeline, custom embedding training, RLHF.
- Safe interpretation: Do not claim any fine-tuning, RLHF, or custom embedding work; category does not require these (low frequency at 11.8%).
- Recommended action: Maintain explicit exclusion in skills; this is not a material gap since fine-tuning is optional for the category.
- Evidence refs: data/master-cv/projects/commander4_skills.json:42
- Citation: Fine_tuning 4/34 (11.8%); marked do_not_claim in candidate evidence.

## Safe Claims Now

### headline_safe
- Staff AI Engineer
- Principal AI Engineer
- Staff Software Engineer - Applied AI
- AI Platform Architect

### profile_safe
- Production AI platform architect delivering enterprise AI workflow systems at scale
- Senior IC building retrieval pipelines, evaluation harnesses, and governed AI workflows
- Player-coach who mentors engineers on architecture while shipping production AI features
- Applied AI engineer with hybrid search, semantic caching, and quality measurement expertise

### experience_safe
- Platform lead for enterprise AI workflow platform serving 2,000+ users with 42 workflow plugins
- Engineered BM25 + RRF hybrid search with LLM-as-judge reranking for production retrieval
- Built retrieval evaluation harness with MRR@k and NDCG@k scoring validated by 14 unit tests
- Architected two-tier semantic caching reducing redundant LLM calls
- Designed governed structured outputs with Zod validation and per-silo guardrail injection
- Implemented MCP server tools for external system integrations
- Achieved 75% incident reduction and 3 years zero downtime in platform modernization
- Mentored 10+ senior engineers on architecture, promoted 3 to lead positions

### leadership_safe
- Technical mentoring and coaching on architectural patterns
- Cross-functional collaboration with product and stakeholders
- Design influence across distributed platform teams
- Technical guidance without claiming formal management

### unsafe_or_too_weak
- Fine-tuning pipelines or custom embedding training (explicitly do_not_claim)
- RLHF or reinforcement learning from human feedback (explicitly do_not_claim)
- Formal people management or performance review ownership (limited evidence, category discourages)
- Strategic hiring leadership (3/34 in category, minimal evidence)
- Deep ML research or publications (research-heavy 1/34, 2.9%)
- Specific p99 latency SLOs for LLM inference without additional evidence
- Autonomous agent systems beyond tool-calling orchestration

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28
- data/master-cv/roles/01_seven_one_entertainment.md:55
- data/master-cv/roles/01_seven_one_entertainment.md:77
- data/master-cv/roles/01_seven_one_entertainment.md:231
- data/master-cv/projects/commander4_skills.json:42

## Representation Diagnosis

### well_represented_now
- AI platform engineering with Commander-4/Joyia prominently featured in priority bullets
- RAG pipeline with hybrid search (BM25, RRF, vector search) well-documented
- Evaluation harness with MRR/NDCG explicitly stated
- Guardrails and structured outputs clearly described
- Semantic caching architecture with technical detail

### underrepresented_now
- Headline uses 'Technical Architect' instead of category-aligned 'Staff AI Engineer' framing
- Latency metrics (~2ms, ~200ms) buried in detailed achievement text, not surfaced in summary
- Reliability outcomes (75% incident reduction, 3 years zero downtime) present but not prioritized for AI platform context
- Cost optimization implications of semantic caching not quantified
- Cross-functional collaboration and communication strengths understated relative to category emphasis

### overstated_risk_now
- Hiring & Team Building achievement may overstate management scope relative to category's modest hiring signal (3/34, 8.8%)
- Representation is proxy-derived; cannot confirm actual headline and summary until canonical master CV exists

### representation_priorities
- Adjust headline from 'Technical Architect' to 'Staff AI Engineer | AI Platform Architecture' framing
- Surface latency and reliability metrics higher in summary or first role bullet
- Reframe MCP tools and structured outputs as 'workflow orchestration' where appropriate
- Understate hiring/team-building relative to mentoring when tailoring for this category

### Citations
- data/master-cv/role_metadata.json:4
- data/master-cv/role_metadata.json:5
- data/master-cv/roles/01_seven_one_entertainment.md:28
- data/master-cv/roles/01_seven_one_entertainment.md:266

## Curation Priorities

### 1. Curate scalability and performance evidence from upstream STAR records
- Why now: Category values scale (14/20) and performance outcomes; upstream records contain additional platform scaling evidence not yet in curated store.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: docs/archive/knowledge-base.md:360, docs/archive/knowledge-base.md:546
- Expected impact: Strengthens achievement archetype #4 (scaled AI-enabled service under constraints); improves candidate_evidence_coverage_score.
- Citation: Upstream signal: Seven.One Entertainment Group — Technical Lead - Addressable TV with overlap score 25-27.

### 2. Extract explicit latency/throughput metrics for Commander-4 if available
- Why now: Semantic caching latencies mentioned (~2ms, ~200ms) but no throughput or p99 metrics; category pain points emphasize low-latency, high-throughput constraints.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md, data/master-cv/projects/commander4.md
- Source refs: data/master-cv/roles/01_seven_one_entertainment.md:354
- Expected impact: Provides quantified latency evidence for key achievement archetype; improves impact_proof_strength_score.
- Citation: Success metrics include latency optimization; valued evidence type scale 14/20.

### 3. Review achievement-review-tracker for cross-functional collaboration evidence
- Why now: Collaboration (85.3%) and communication (67.6%) are highest soft-skill signals; Subject Matter Expertise & Stakeholder Collaboration achievement marked for review.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: docs/current/achievement-review-tracker.yaml:1051
- Expected impact: Strengthens table-stakes soft skills representation; supports player-coach narrative.
- Citation: Collaboration 29/34 (85.3%), communication 23/34 (67.6%).

## Master CV Upgrade Actions

### 1. Change headline from 'Technical Architect / AI Platform Architect' to 'Staff AI Engineer | AI Platform Architecture | Production GenAI & Evaluation'
- Section: `headline`
- Why now: Title families cluster around staff_engineer (20/34) and principal_engineer (13/34); current headline signals architecture but not IC-track AI engineer positioning expected by recruiters.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/role_metadata.json:4
- Citation: Title families: staff_engineer 20/34, principal_engineer 13/34; platform design 34/34 (100%).

### 2. Add explicit latency metrics to summary: mention ~2ms exact-match cache and production AI platform scale
- Section: `summary`
- Why now: Category pain points emphasize low-latency constraints; current summary mentions reliability and evaluation but not latency explicitly.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/role_metadata.json:5
- Citation: Success metrics include latency optimization; valued evidence type scale 14/20.

### 3. Reorder role bullets to lead with evaluation/quality outcomes before implementation details
- Section: `role_bullets`
- Why now: Evaluation is the strongest AI-specific differentiator (44.1%); current bullet leads with technical implementation rather than quality improvement outcome.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: Evaluation_quality 15/34 (44.1%); valued evidence type evaluation 15/20.

### 4. Add 'workflow orchestration' language to structured outputs bullet
- Section: `role_bullets`
- Why now: Agents/orchestration appears at 26.5%; MCP tools and structured outputs can be framed as orchestration without claiming autonomous agents.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:55
- Citation: Agents_orchestration 9/34 (26.5%); hard skill agentic workflows 3/34 (8.8%).

### 5. Ensure skills section includes evaluation/quality keywords: 'retrieval evaluation', 'quality measurement', 'LLM-as-judge'
- Section: `skills`
- Why now: Evaluation is category's strongest AI differentiator; skills list should repeat strongest 4-6 keywords 2-3 times if true.
- Supported by: data/master-cv/projects/commander4_skills.json:22
- Citation: ATS strategy should center on strongest repeated concepts; evaluation_quality 15/34 (44.1%).

### 6. Understate hiring evidence in bullets; lead with mentoring and technical guidance
- Section: `role_bullets`
- Why now: Hiring appears in only 3/34 (8.8%) category roles; mentoring 20/34 (58.8%) is safer positioning.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:266
- Citation: Hiring 3/34 (8.8%), mentoring 20/34 (58.8%), performance_management 1/34 (2.9%).

## Evidence Ledger

- `supported_and_curated` (high): Anchor CV around production AI platform architecture and delivery (Commander-4/Joyia) rather than generic architecture experience
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- `supported_and_curated` (high): Lead with evaluation and quality measurement evidence (MRR, NDCG, retrieval quality) as primary AI differentiator
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7, data/master-cv/projects/commander4_skills.json:22
- `supported_and_curated` (high): Use senior IC or light player-coach narrative; do not overclaim formal management
  Support: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:172
- `supported_and_curated` (high): Include RAG and retrieval evidence as differentiator since candidate has strong hybrid search implementation
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:8
- `curated_but_underrepresented` (high): Surface reliability outcomes (75% incident reduction, 3 years zero downtime) as platform maturity evidence
  Support: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:212
- `supported_upstream_pending_curation` (medium): Promote scalability and performance evidence from upstream STAR records to strengthen scale signal
  Support: docs/archive/knowledge-base.md:360, docs/archive/knowledge-base.md:546
- `unsupported_or_unsafe` (high): Do not claim fine-tuning, RLHF, or custom embedding training
  Support: data/master-cv/projects/commander4_skills.json:42
- `curated_but_underrepresented` (medium): Frame MCP tools and structured outputs as workflow orchestration when relevant to agents signal
  Support: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
