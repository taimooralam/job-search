# Senior AI Engineer — EEA Baseline

- Category ID: `senior_ai_engineer_eea`
- Macro family: `ai_engineering_adjacent`
- Priority: `secondary_target`
- Confidence: `low`
- Representation proxy mode: `True`

## Overall Assessment

- Combined fit score: **7.72 / 10**
- Readiness tier: **GOOD**
- Verdict: Candidate has strong curated evidence for production RAG, AI platform architecture, and evaluation harnesses that directly match this category's core signals, but the current master-CV representation over-indexes on leadership/player-coach framing that this pure senior-IC category explicitly avoids.
- Uncertainty: Representation assessment is currently in proxy mode because no canonical master CV artifact was found. Category confidence is low with only 7 jobs sampled; the strongest signal (platform_design 7/7) aligns well with Commander-4 evidence, but sparse pain-point distribution means specific framing choices carry higher variance than usual.

### Citations
- platform_design 7/7 (100.0%)
- RAG 5/7 (71.4%)
- senior_ic 7/7 (100.0%)
- hiring/org_building 0/7 (0.0%)
- data/master-cv/roles/01_seven_one_entertainment.md:28

## Score Breakdown

- Candidate evidence coverage: 8.50
- Evidence curation completeness: 8.00
- Master CV representation quality: 6.50
- AI / architecture fit: 9.00
- Leadership / scope fit: 6.00
- Impact proof strength: 8.00

### Weighted Score Explanation
- Evidence coverage (8.5 × 0.30 = 2.55): RAG, evaluation harnesses, semantic caching, MCP tools, and platform architecture all directly curated with implementation detail.
- Curation completeness (8.0 × 0.15 = 1.20): Most category-relevant signals are already in master-cv files; upstream evidence largely duplicates rather than extends.
- Representation quality (6.5 × 0.25 = 1.625): AI platform work is well-surfaced but headline uses 'Technical Architect' instead of Senior AI Engineer family, and summary foregrounds player-coach framing that is risky for this IC-heavy category.
- AI architecture fit (9.0 × 0.15 = 1.35): Commander-4 evidence is near-perfect for the category's platform-design, RAG, agent-orchestration, and evaluation signals.
- Leadership scope fit (6.0 × 0.10 = 0.60): Curated mentorship, hiring, and promotion evidence is strong but this category explicitly avoids management signals (hiring 0/7); requires de-emphasis not removal.
- Impact proof strength (8.0 × 0.05 = 0.40): 2,000 users, 42 plugins, MRR/NDCG metrics, 75% incident reduction, and 3-year zero-downtime provide concrete proof.

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28
- data/master-cv/roles/01_seven_one_entertainment.md:55
- data/master-cv/roles/01_seven_one_entertainment.md:231
- data/master-cv/projects/commander4.md:7
- senior_ic 7/7 (100.0%)
- hiring/org_building 0/7 (0.0%)

## Strongest Supported Signals

### Production RAG with hybrid retrieval architecture
- Why it matters: RAG appears in 5/7 roles (71.4%) and is the clearest applied-AI pattern; candidate's BM25 + RRF + LLM-as-judge reranking implementation directly matches the category's retrieval-design expectations.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:8
- Citation: RAG 5/7 (71.4%); hard skill retrieval-augmented generation 2/7 (28.6%)

### AI platform design serving production users at scale
- Why it matters: Platform design is the strongest category signal at 7/7 (100.0%); Commander-4 serving 2,000 users across 42 plugins with governed workflows directly proves this.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:2
- Citation: platform_design 7/7 (100.0%); architecture valued in 7/7 deep analyses

### Retrieval evaluation harness with quality metrics
- Why it matters: Evaluation is valued in 6/7 deep analyses and appears in 4/7 roles (57.1%); candidate's MRR@k and NDCG@k implementation with 14 unit tests proves measurement discipline.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7
- Citation: evaluation valued in 6/7 deep analyses; evaluation_quality 4/7 (57.1%)

### Agent/tool-calling architecture with MCP integrations
- Why it matters: Agent orchestration appears in 5/7 roles (71.4%); candidate's 5 MCP server tools, Zod schema validation, and per-silo guardrail injection prove shipped orchestration.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- Citation: agents_orchestration 5/7 (71.4%); hard skill AI agents 2/7 (28.6%)

### Semantic caching for LLM cost and latency control
- Why it matters: Cost is valued in 4/7 deep analyses; two-tier caching (L1 exact-match ~2ms, L2 semantic ~200ms) proves runtime economics work beyond just feature delivery.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/commander4.md:9
- Citation: cost valued in 4/7 deep analyses; reliability 7/7

### Python implementation alongside TypeScript
- Why it matters: Python is the most common language signal at 4/7 (57.1%); candidate's Python work on S3VectorSemanticCache for LiteLLM is explicitly curated.
- Status: `supported_and_curated`
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4_skills.json:2
- Citation: Python 4/7 (57.1%)

## Gap Analysis

### curated_but_underrepresented
- Signal: Collaboration and cross-functional delivery evidence
- Why it matters: Collaboration appears in 5/7 roles (71.4%); the category expects senior ICs who work across product and engineering without formal management claims.
- Current state: Stakeholder collaboration and cross-functional team evidence exists in curated files (technical vision, DDD, stakeholder alignment) but is not surfaced prominently in the representation layer.
- Safe interpretation: Candidate has collaboration proof but it is buried under leadership framing; needs repositioning as senior IC collaboration not management.
- Recommended action: Surface collaboration evidence in project bullets without management vocabulary; emphasize 'worked with' and 'collaborated across' rather than 'led' or 'mentored'.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:172, data/master-cv/roles/01_seven_one_entertainment.md:299
- Citation: collaboration 5/7 (71.4%); communication 2/7 (28.6%)

- Signal: Reliability and production resilience for AI systems
- Why it matters: Reliability is valued in 7/7 deep analyses; the category wants operational proof beyond feature shipping.
- Current state: Strong reliability evidence exists for AdTech platform (75% incident reduction, 3 years zero downtime) but is not yet connected to AI system reliability in the representation.
- Safe interpretation: Can claim reliability engineering experience; should bridge AdTech reliability evidence to AI platform context when positioning for this category.
- Recommended action: Add explicit reliability framing to Commander-4 bullets (e.g., semantic cache fallback behavior, guardrail enforcement, evaluation gating) to prove AI-specific operational discipline.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:212
- Citation: reliability valued in 7/7 deep analyses; delivery and scale also valued in 7/7

- Signal: Explicit agent workflow orchestration language
- Why it matters: Agent orchestration is 5/7 (71.4%) in the category; MCP tools and guardrails are curated but 'agent orchestration' as a term is not prominent.
- Current state: Commander-4 evidence covers tool-calling, structured outputs, and guardrails but does not use 'agent orchestration' or 'workflow automation' vocabulary explicitly.
- Safe interpretation: The underlying capability is proven; the framing can be upgraded without overclaiming.
- Recommended action: Reframe Commander-4 bullet 2 to lead with 'agent workflow orchestration' language, connecting MCP tools and guardrails to the workflow automation pattern.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- Citation: agents_orchestration 5/7 (71.4%); context management 2/7 (28.6%)

- Signal: Integration into existing products vs greenfield-only framing
- Why it matters: The category's greenfield_split shows 'both' at 4/7 (57.1%); pain points center on embedding AI into existing products and workflows, not building standalone demos.
- Current state: Legacy modernization evidence is strong (AdTech platform transformation) but not connected to AI integration; Commander-4 is framed as new platform work.
- Safe interpretation: Candidate has both greenfield and optimization experience; needs to surface AI-into-existing-system integration evidence.
- Recommended action: If Commander-4 integrated into existing ProSiebenSat.1 workflows or systems, add that context; otherwise, bridge AdTech integration experience as transferable proof.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: greenfield_split: both 4/7 (57.1%), greenfield 2/7 (28.6%)

### supported_upstream_pending_curation
### unsupported_or_unsafe
- Signal: Fine-tuning or custom embedding training
- Why it matters: Fine-tuning appears in only 1/7 (14.3%) so it is not a universal requirement, but if claimed without evidence it would be a significant overstatement.
- Current state: Explicitly listed in do_not_claim: fine-tuning pipeline, custom embedding training, RLHF.
- Safe interpretation: Do not claim fine-tuning or embedding training; this category does not require it, but overclaiming would be unsafe.
- Recommended action: No action needed unless candidate acquires this evidence in future; current positioning around retrieval and evaluation is sufficient.
- Evidence refs: data/master-cv/projects/commander4_skills.json:42
- Citation: fine_tuning 1/7 (14.3%); do_not_claim includes fine-tuning pipeline

- Signal: Hiring, org-building, or budget ownership
- Why it matters: This category explicitly avoids management signals: hiring 0/7, org_building 0/7, budget_pnl 0/7. Overclaiming would misposition for IC roles.
- Current state: Candidate has curated hiring and mentorship evidence that is appropriate for other categories but risky for this one.
- Safe interpretation: Do not foreground hiring/team-building in this category's CV variant; compress or omit to avoid IC/manager mismatch.
- Recommended action: In category-specific CV, de-emphasize data/master-cv/roles/01_seven_one_entertainment.md:231 and :266; keep mentorship only if framed as technical guidance.
- Evidence refs: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:266
- Citation: hiring/org_building/budget_pnl 0/7 (0.0%)

## Safe Claims Now

### headline_safe
- Senior AI Engineer
- Senior Applied AI Engineer
- Senior Software Engineer (AI/ML)
- Production RAG / Agent Systems
- Platform Design and Evaluation

### profile_safe
- Hands-on senior AI engineer building production RAG and agent workflows
- Senior software engineer with applied AI depth across platform design, evaluation, and system integration
- Designed and shipped enterprise AI workflow platform serving 2,000 users with 42 plugins
- Built hybrid retrieval pipelines with BM25, RRF fusion, and LLM-as-judge reranking
- Implemented retrieval evaluation harnesses with MRR@k and NDCG@k metrics
- Architected semantic caching reducing LLM latency and cost

### experience_safe
- Engineered retrieval-quality layer for production AI platform
- Implemented BM25 scoring from scratch for vector search
- Built LLM-as-judge reranking via Claude Sonnet/LiteLLM
- Designed two-tier semantic caching with L1 exact-match and L2 cosine similarity
- Created MCP server tools for external system integrations
- Implemented guardrail profiles for per-silo content policy enforcement
- Validated retrieval quality with 14 unit tests

### leadership_safe
- Technical guidance on architectural patterns (framed as IC contribution)
- Cross-functional collaboration with product and platform teams
- Domain expertise consultation (not management)

### unsafe_or_too_weak
- Do not claim: fine-tuning, custom embedding training, RLHF
- Do not claim: hiring leadership, org-building, performance management, budget ownership
- Do not claim: Head of AI, AI Director, CTO, or executive framing
- Do not claim: Tech Lead unless explicitly showing player-coach scope
- Do not claim: GDPR program ownership (only 1/7 in category)
- Do not claim: model serving infrastructure or vLLM/TGI experience
- Do not claim: LangChain/LangGraph/LlamaIndex unless central to delivery

### Citations
- data/master-cv/roles/01_seven_one_entertainment.md:28
- data/master-cv/roles/01_seven_one_entertainment.md:55
- data/master-cv/projects/commander4.md:7
- data/master-cv/projects/commander4_skills.json:42
- senior_ic 7/7 (100.0%)
- hiring/org_building 0/7 (0.0%)
- fine_tuning 1/7 (14.3%)

## Representation Diagnosis

### well_represented_now
- RAG and hybrid retrieval architecture details are prominently surfaced in role bullets
- Evaluation harness with MRR/NDCG metrics is explicitly documented
- Semantic caching architecture is well-described with implementation detail
- MCP tools and guardrail engineering are captured in project evidence
- Python and TypeScript implementation is explicitly noted

### underrepresented_now
- Agent orchestration language is implicit rather than explicit in headlines and summaries
- Reliability and production resilience evidence is not connected to AI system context
- Collaboration evidence is buried under leadership framing instead of IC collaboration
- Integration-into-existing-systems evidence is not prominent for AI work specifically

### overstated_risk_now
- Current headline 'Technical Architect / AI Platform Architect' may imply more scope than senior IC
- Summary mentions 'player-coach' which is only 1/7 (14.3%) in this category
- Mentorship and hiring evidence is curated but should be de-emphasized for this IC category
- Leadership framing across achievements may trigger management-role assumptions

### representation_priorities
- 1. Adjust headline to 'Senior AI Engineer' family with production RAG/agent clause
- 2. Remove 'player-coach' from summary; reframe as hands-on senior IC
- 3. Add explicit 'agent orchestration' and 'workflow automation' language to Commander-4 framing
- 4. Surface AI-specific reliability evidence (guardrail enforcement, cache fallback, eval gating)
- 5. Compress hiring/mentorship bullets or reframe as technical guidance

### Citations
- data/master-cv/role_metadata.json:4
- data/master-cv/role_metadata.json:5
- data/master-cv/roles/01_seven_one_entertainment.md:231
- senior_ic 7/7 (100.0%)
- player_coach 1/7 (14.3%)

## Curation Priorities

### 1. Surface explicit agent-orchestration and workflow-automation vocabulary in Commander-4 evidence
- Why now: Agent orchestration is 5/7 (71.4%) in category but current framing uses MCP/guardrails without the orchestration keyword; low-effort high-impact vocabulary upgrade.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md, data/master-cv/projects/commander4.md
- Source refs: data/master-cv/roles/01_seven_one_entertainment.md:55
- Expected impact: Directly matches agents_orchestration signal at 5/7 (71.4%) and context_management at 2/7 (28.6%)
- Citation: agents_orchestration 5/7 (71.4%)

### 2. Add AI-specific reliability evidence to Commander-4 bullets
- Why now: Reliability is valued in 7/7 deep analyses but current AI evidence lacks operational framing; existing AdTech reliability evidence can bridge.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md, data/master-cv/projects/commander4.md
- Source refs: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:212
- Expected impact: Proves reliability valued in 7/7 deep analyses for AI context, not just AdTech
- Citation: reliability valued in 7/7 deep analyses

### 3. Reframe collaboration evidence as IC contribution rather than management
- Why now: Collaboration is 5/7 (71.4%) but current framing uses leadership vocabulary that conflicts with IC scope; needs vocabulary shift.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: data/master-cv/roles/01_seven_one_entertainment.md:172, data/master-cv/roles/01_seven_one_entertainment.md:299
- Expected impact: Aligns with collaboration 5/7 (71.4%) without triggering hiring/org_building 0/7 mismatch
- Citation: collaboration 5/7 (71.4%); hiring 0/7 (0.0%)

### 4. Review upstream STAR records for AI-into-existing-system integration evidence
- Why now: greenfield_split shows 'both' at 4/7 (57.1%); if Commander-4 integrated into existing ProSiebenSat.1 systems, that context should be curated.
- Target files: data/master-cv/roles/01_seven_one_entertainment.md
- Source refs: docs/archive/knowledge-base.md:98
- Expected impact: Matches pain points on integrating AI into existing products and workflows
- Citation: greenfield_split: both 4/7 (57.1%)

## Master CV Upgrade Actions

### 1. Update headline from 'Technical Architect / AI Platform Architect' to 'Senior AI Engineer' family with production RAG/agent clause
- Section: `headline`
- Why now: Current headline uses title outside safe families; senior_engineer 6/7 in category vs tech_lead 1/7; immediate mismatch risk.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:2
- Citation: safe_title_families: Senior AI Engineer, Senior Applied AI Engineer, Senior Software Engineer (AI/ML)

### 2. Remove 'player-coach' from summary and reframe as hands-on senior IC
- Section: `summary`
- Why now: player_coach appears in only 1/7 (14.3%) roles; current summary explicitly uses this term which may misposition for IC-heavy category.
- Supported by: data/master-cv/role_metadata.json:5, data/master-cv/roles/01_seven_one_entertainment.md:28
- Citation: player_coach 1/7 (14.3%); senior_ic 7/7 (100.0%)

### 3. Add 'agent workflow orchestration' language to Commander-4 role bullet on MCP/guardrails
- Section: `role_bullets`
- Why now: agents_orchestration is 5/7 (71.4%) but current bullet uses implementation vocabulary (MCP, Zod) without orchestration framing.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:55
- Citation: agents_orchestration 5/7 (71.4%)

### 4. Compress or de-emphasize hiring and mentorship bullets for this category variant
- Section: `role_bullets`
- Why now: hiring 0/7 (0.0%) and org_building 0/7 (0.0%); prominent leadership bullets create IC/manager scope confusion.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:266
- Citation: hiring/org_building/budget_pnl 0/7 (0.0%)

### 5. Add explicit reliability framing to AI platform bullets (guardrail enforcement, cache fallback, eval gating)
- Section: `role_bullets`
- Why now: reliability valued in 7/7 deep analyses but AI-specific operational evidence is implicit; needs explicit surfacing.
- Supported by: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7
- Citation: reliability valued in 7/7 deep analyses

### 6. Ensure Python is listed prominently in skills without over-positioning it
- Section: `skills`
- Why now: Python is 4/7 (57.1%), the highest language signal, but still below universal threshold; should support not dominate.
- Supported by: data/master-cv/projects/commander4_skills.json:2
- Citation: Python 4/7 (57.1%); no hard skill clears 60%

## Evidence Ledger

- `supported_and_curated` (high): Claim production RAG with hybrid retrieval architecture (BM25 + RRF + LLM-as-judge)
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:8
- `supported_and_curated` (high): Claim enterprise AI platform design serving production users at scale
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:2
- `supported_and_curated` (high): Claim retrieval evaluation harness with MRR@k and NDCG@k metrics
  Support: data/master-cv/roles/01_seven_one_entertainment.md:28, data/master-cv/projects/commander4.md:7
- `supported_and_curated` (high): Claim MCP tool design and structured-output architecture with guardrails
  Support: data/master-cv/roles/01_seven_one_entertainment.md:55, data/master-cv/projects/commander4.md:6
- `supported_and_curated` (high): Claim semantic caching architecture for LLM cost and latency control
  Support: data/master-cv/roles/01_seven_one_entertainment.md:354, data/master-cv/projects/commander4.md:9
- `supported_and_curated` (high): Claim Python implementation for AI systems (alongside TypeScript)
  Support: data/master-cv/projects/commander4_skills.json:2, data/master-cv/roles/01_seven_one_entertainment.md:28
- `curated_but_underrepresented` (high): Frame agent orchestration explicitly using curated MCP/guardrail evidence
  Support: data/master-cv/roles/01_seven_one_entertainment.md:55
- `curated_but_underrepresented` (medium): Surface collaboration evidence as IC contribution rather than management
  Support: data/master-cv/roles/01_seven_one_entertainment.md:172, data/master-cv/roles/01_seven_one_entertainment.md:299
- `curated_but_underrepresented` (medium): Bridge AdTech reliability evidence to AI platform context
  Support: data/master-cv/roles/01_seven_one_entertainment.md:77, data/master-cv/roles/01_seven_one_entertainment.md:212
- `unsupported_or_unsafe` (high): Do NOT claim fine-tuning, custom embedding training, or RLHF
  Support: data/master-cv/projects/commander4_skills.json:42
- `unsupported_or_unsafe` (high): Do NOT foreground hiring, org-building, or budget ownership for this IC category
  Support: data/master-cv/roles/01_seven_one_entertainment.md:231, data/master-cv/roles/01_seven_one_entertainment.md:266
