# AI Engineering Manager — EEA — Eval Rubric

## Meta
- Category ID: ai_eng_manager_eea
- Macro family: ai_engineering_adjacent
- Priority: secondary_target
- Confidence: high
- Rubric version: 2026-04-17

## Identity
- Purpose: Evaluate CVs for delivery-led AI engineering manager or player-coach roles that ship and scale AI platform capabilities with architecture, evaluation, governance, and stakeholder translation proof.
- Core persona: Player-coach AI engineering leader who combines hands-on platform architecture with team mentorship, stakeholder alignment, and measurable AI delivery outcomes without overstating formal product-management or executive ownership.
Job overlay notes:
- Manager scope appears in 45.2% of roles while player-coach appears in 16.1% and executive in only 3.2% — calibrate leadership expectations accordingly
- Platform design appears in 54.8% of roles — architecture proof is a major separator for this category
- GDPR appears in 32.3% of roles — surface compliance evidence when available but do not overclaim formal compliance ownership
- Evaluation and guardrails are differentiators not table-stakes — reward when present but do not require universally
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

## Dimension Rubrics
### ats_optimization (weight 20)
**Layer A — Category core**
What good looks like:
- AI platform, GenAI, or AI workflow keywords appear 2-3 times across headline, profile, experience, and skills
- Platform design and architecture keywords repeated with outcome linkage not just tool lists
- Evaluation, guardrails, governance keywords present when supported by evidence
- Stakeholder management and adoption keywords tied to concrete decisions or outcomes
Common failures:
- Over-indexing on PM tools like Airtable, Asana, HubSpot, Notion without AI delivery context
- Generic AI buzzwords without shipped outcome proof
- Missing platform or architecture keywords despite having that evidence
- Prompt engineering framing when category shows 0% signal for this skill
**Layer B — Job-specific overlay**
Adjust per JD:
- Mirror specific AI stack terms from JD (LangChain, vector DB names, orchestration frameworks)
- Adjust evaluation terminology to match JD language (quality, testing, validation)
- Include specific governance or compliance terms mentioned in JD
Company/domain overrides:
- Enterprise SaaS roles may emphasize workflow automation and plugin ecosystems
- B2B platform roles may require integration and API terminology
- Regulated industry roles should surface compliance keywords more prominently
Region overrides:
- EEA roles may explicitly request GDPR awareness — surface if evidenced
- Remote-first appears in 54.8% of roles — mention distributed collaboration capability
**Score anchors**
- 9-10:
  - AI platform and delivery keywords appear 3+ times with natural distribution across sections
  - Architecture and platform design terminology linked to measurable outcomes
  - Evaluation, governance, and stakeholder keywords all present and evidence-backed
  - Keywords mirror JD terminology without keyword stuffing
- 7-8:
  - Core AI platform keywords present 2+ times
  - Architecture terminology present but may lack outcome linkage
  - Most category-relevant keywords covered with minor gaps
  - Good JD keyword alignment with some missed opportunities
- 5-6:
  - AI keywords present but underrepresented or poorly distributed
  - Architecture proof exists but not keyword-optimized
  - Missing key differentiator keywords like evaluation or governance
  - Partial JD alignment with noticeable keyword gaps
- <=4:
  - AI platform keywords sparse or absent despite relevant experience
  - Over-reliance on PM tool keywords without AI context
  - No architecture or platform design terminology
  - Poor JD keyword alignment or keyword stuffing without substance
Red flags:
- Prompt engineering positioned as primary skill when category shows 0% signal
- PM operations tools dominate keywords without AI delivery context
- Generic innovation or strategy language without shipped outcome keywords
- Keyword stuffing that reads as unnatural or disconnected from experience
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

### impact_clarity (weight 25)
**Layer A — Category core**
What good looks like:
- Measurable adoption metrics for AI platform or workflow capabilities
- User count, usage growth, or efficiency gains tied to AI delivery
- Architecture outcomes with latency, throughput, reliability, or cost metrics
- Quality and evaluation metrics showing improvement in AI system performance
- Business value metrics connecting AI delivery to revenue, cost, or productivity
Common failures:
- Vague delivery claims without quantified adoption or usage metrics
- Architecture work described without production impact metrics
- Evaluation work mentioned without quality improvement numbers
- Missing business value connection for technical achievements
**Layer B — Job-specific overlay**
Adjust per JD:
- Emphasize adoption metrics for product-focused roles
- Foreground technical metrics for platform-heavy roles
- Add efficiency or productivity metrics for internal tooling roles
Company/domain overrides:
- Enterprise roles may value user count, workflow volume, or integration count
- Platform roles may prioritize latency, throughput, or reliability metrics
- Startup roles may value time-to-launch or iteration speed metrics
Region overrides:
- EEA roles may value compliance audit outcomes as impact evidence
- GDPR protection with revenue exposure quantification is relevant for EEA
**Score anchors**
- 9-10:
  - 3+ distinct quantified outcomes across delivery, scale, architecture, and business value
  - Adoption metrics with growth percentages or absolute user numbers
  - Architecture improvements with before/after metrics
  - Business impact tied to revenue, cost savings, or productivity gains
  - Quality metrics showing measurable improvement in AI system performance
- 7-8:
  - 2-3 quantified outcomes covering delivery and scale
  - User or adoption metrics present but may lack growth context
  - Technical metrics present for architecture work
  - Some business value connection though not fully quantified
- 5-6:
  - 1-2 quantified outcomes with gaps in key areas
  - Metrics present but vague or lacking specificity
  - Missing adoption or user impact metrics despite relevant work
  - Business value implied but not quantified
- <=4:
  - No quantified outcomes or only trivial metrics
  - Vague claims of delivery or scale without evidence
  - No adoption, user impact, or business value metrics
  - Technical work described without measurable outcomes
Red flags:
- Round numbers without context suggesting fabrication
- Metrics that cannot be attributed to candidate actions
- Conflicting metrics within same role or project
- Business outcomes claimed without delivery mechanism explanation
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

### jd_alignment (weight 25)
**Layer A — Category core**
What good looks like:
- AI platform or GenAI delivery experience matching category table-stakes
- Platform design and architecture proof matching 54.8% category signal
- Evaluation and quality management evidence when JD emphasizes trusted AI
- Stakeholder translation and cross-functional alignment evidence
- Greenfield plus productionization experience when both are requested
Common failures:
- Pure IC architecture framing when JD emphasizes management scope
- Pure management framing when JD emphasizes hands-on delivery
- Missing platform or architecture evidence despite category emphasis
- No stakeholder or cross-functional evidence despite 67.7% category signal
**Layer B — Job-specific overlay**
Adjust per JD:
- Weight architecture vs management evidence based on JD role scope signals
- Emphasize evaluation and guardrails when JD mentions quality or trust
- Surface GDPR or compliance evidence when JD explicitly requires it
- Adjust greenfield vs optimization emphasis based on JD context
Company/domain overrides:
- Enterprise roles may require workflow automation and integration experience
- Platform company roles may emphasize API and multi-tenant architecture
- Regulated industries may require governance and compliance evidence
Region overrides:
- EEA roles may explicitly require GDPR awareness or compliance experience
- Remote-first alignment for distributed team roles common in EEA
**Score anchors**
- 9-10:
  - Direct match on AI platform or GenAI delivery requirement
  - Architecture and platform design evidence matching JD emphasis
  - Stakeholder translation proof matching cross-functional requirements
  - Evaluation, governance, or compliance evidence when JD requires it
  - Role scope alignment with JD manager vs IC vs player-coach signals
- 7-8:
  - Strong AI delivery evidence with minor gaps in JD-specific requirements
  - Architecture proof present though may not perfectly match JD stack
  - Stakeholder evidence present but could be more prominent
  - Most JD requirements addressed with some secondary gaps
- 5-6:
  - AI experience present but not strongly aligned to JD delivery emphasis
  - Architecture evidence exists but underrepresented or misaligned
  - Missing stakeholder or cross-functional evidence despite JD requirement
  - Significant gaps in JD-specific technical or leadership requirements
- <=4:
  - No AI platform or delivery experience matching JD requirements
  - Missing architecture proof when JD emphasizes platform work
  - Role scope misalignment with JD manager vs IC expectations
  - Major JD requirements unaddressed
Red flags:
- Product Manager title or framing when JD is engineering-manager scoped
- Executive or VP framing when JD is manager or player-coach scoped
- Research or academic framing when category shows 0% PhD or research signal
- No AI delivery evidence for AI engineering manager role
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

### executive_presence (weight 15)
**Layer A — Category core**
What good looks like:
- Player-coach positioning with hands-on delivery plus team leadership evidence
- Stakeholder translation and cross-functional alignment proof
- Technical decision-making authority demonstrated through architecture choices
- Mentorship and team development evidence without overclaiming formal management
- Business outcome ownership through engineering delivery leadership
Common failures:
- Executive or VP framing when category shows only 3.2% executive scope
- Pure IC framing when manager or player-coach scope is expected
- Claiming formal people management without supporting evidence
- Generic leadership language without concrete decisions or outcomes
**Layer B — Job-specific overlay**
Adjust per JD:
- Calibrate management vs IC emphasis based on JD role scope signals
- Emphasize team building when JD mentions org growth or hiring
- Surface mentorship evidence when JD emphasizes team development
- Adjust stakeholder scope based on JD cross-functional requirements
Company/domain overrides:
- Startup roles may accept player-coach without formal management scope
- Enterprise roles may require more explicit org-building evidence
- Platform company roles may emphasize technical leadership over people management
Region overrides:
- EEA roles commonly accept remote-first leadership models
- Distributed team leadership experience valuable for EEA targeting
**Score anchors**
- 9-10:
  - Clear player-coach positioning with hands-on delivery plus team leadership
  - Stakeholder translation evidence with concrete alignment outcomes
  - Mentorship or team development with quantified results
  - Technical authority demonstrated through architecture decisions and adoption
  - Appropriate scope claims matching category 45.2% manager, 16.1% player-coach signals
- 7-8:
  - Player-coach or leadership framing present and appropriate
  - Stakeholder collaboration evidence though may lack decision outcomes
  - Some mentorship or team evidence without full quantification
  - Technical leadership evident but could be more prominent
- 5-6:
  - Leadership framing present but unclear player-coach positioning
  - Limited stakeholder or cross-functional evidence
  - Minimal team development or mentorship evidence
  - Technical authority implied but not demonstrated
- <=4:
  - Inappropriate executive or VP framing without supporting evidence
  - Pure IC framing when role requires leadership scope
  - No stakeholder, team, or cross-functional evidence
  - Leadership claims unsupported by concrete outcomes
Red flags:
- Unsupported people-management framing without explicit evidence of direct reports
- Executive or C-suite positioning when category shows 3.2% executive scope
- Budget or P&L ownership claims when category shows only 6.5% signal
- Performance management claims without explicit review or compensation authority evidence
- Director or VP title inflation from player-coach or manager scope
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

### anti_hallucination (weight 15)
**Layer A — Category core**
What good looks like:
- All metrics traceable to specific roles, projects, or outcomes
- Title claims match actual role evidence without inflation
- Technical claims supported by concrete project or architecture evidence
- Leadership scope claims appropriate to evidenced responsibilities
- No fabricated adoption numbers, user counts, or revenue impact
Common failures:
- Unsourced metrics with round numbers suggesting fabrication
- Product Manager or PM ownership claims without PM role evidence
- Research, PhD, or publication framing when background does not support
- Direct report counts without explicit management evidence
- GTM, pricing, or budget ownership claims without supporting authority
**Layer B — Job-specific overlay**
Adjust per JD:
- Verify technical stack claims match candidate evidence when JD is specific
- Check leadership scope claims align with evidenced responsibilities
- Validate compliance or governance claims when JD requires formal authority
Company/domain overrides:
- Enterprise roles require verifiable scale and adoption metrics
- Startup roles may have less formal metrics but claims should still be traceable
- Regulated industry roles require accurate compliance authority claims
Region overrides:
- GDPR compliance claims should be delivery-linked not ownership-claimed unless evidenced
- Native language claims should not be fabricated for EEA targeting
**Score anchors**
- 9-10:
  - All quantified claims traceable to specific evidence sources
  - Titles and role scope precisely match documented experience
  - Technical claims fully supported by project and architecture evidence
  - Leadership scope appropriately calibrated to actual responsibilities
  - No detectable inflation or unsupported claims
- 7-8:
  - Most claims traceable with minor gaps in attribution
  - Titles accurate with appropriate scope framing
  - Technical claims well-supported though some may lack full context
  - Leadership claims generally appropriate with minimal overreach
- 5-6:
  - Some claims lack clear traceability to evidence
  - Minor title or scope framing concerns
  - Technical claims partially supported but gaps exist
  - Some leadership claims may slightly exceed evidenced scope
- <=4:
  - Multiple unsupported metrics or fabricated numbers
  - Title inflation or scope overclaiming evident
  - Technical claims not supported by evidence
  - Leadership or ownership claims significantly exceed documented responsibilities
  - Detectable hallucination or fabrication patterns
Red flags:
- Unsupported metrics with suspiciously round numbers
- Fabricated titles not matching role evidence
- PhD or publication claims when background shows no academic work
- Unsupported scope of direct reports or org ownership
- Formal product-management ownership without PM role evidence
- GTM, pricing, or product marketing ownership claims without authority evidence
- Budget or P&L ownership claims without finance authority evidence
- Fine-tuning, RLHF, or custom model training claims without supporting evidence
- Prompt engineering expert framing when category shows 0% signal
- Research agenda or experimentation leadership when category shows 0% research-heavy signal
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

## Gates
### must_have_coverage_gate
Pass criteria:
- AI platform, GenAI, or AI delivery experience clearly evidenced
- Platform design or architecture proof present matching 54.8% category signal
- Stakeholder translation or cross-functional collaboration evidence present
- At least one measurable delivery or adoption outcome quantified
Fail conditions:
- No AI platform or delivery experience evident
- No architecture or platform design evidence despite category emphasis
- No stakeholder or cross-functional evidence when category shows 67.7% signal
- No quantified outcomes for any claims
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

### unsafe_claim_gate
Pass criteria:
- No formal product-management ownership claims without PM role evidence
- No people management or direct report claims without explicit evidence
- No budget or P&L ownership claims without finance authority evidence
- No research, PhD, or publication claims without academic background
- No GTM, pricing, or product marketing ownership claims without authority evidence
- All metrics traceable to documented experience
Fail conditions:
- Product Manager title or ownership claimed without PM role evidence
- Direct report counts or performance management claimed without evidence
- Budget or P&L ownership claimed when category shows only 6.5% signal
- Research or PhD framing when category shows 0% signal
- Fabricated metrics or unsupported quantified claims
- Executive or VP scope claimed when role evidence is manager or player-coach
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

### persona_fit_gate
Pass criteria:
- Player-coach or delivery-led manager positioning appropriate to category
- Engineering leadership framing not executive or C-suite framing
- Hands-on technical credibility plus leadership scope balanced
- Stakeholder translation emphasized over product ownership
Fail conditions:
- Executive, VP, or C-suite positioning when category shows 3.2% executive scope
- Pure Product Manager positioning for engineering manager category
- Pure IC positioning when manager or player-coach scope expected
- Research or academic positioning when category shows 0% research signal
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

## Verdict Thresholds
- STRONG_MATCH >= 8.5
- GOOD_MATCH   >= 7.0
- NEEDS_WORK   >= 5.5
- WEAK_MATCH   <= 5.49

## Scoring Guidance
- Executive presence: For this delivery-led manager or player-coach category, interpret executive_presence as hands-on team leadership plus delivery ownership. Reward stakeholder translation, mentorship, and technical decision-making authority. Penalize inappropriate executive, VP, or C-suite framing since executive scope appears in only 3.2% of roles. Player-coach positioning with demonstrated team development is the target archetype.
- Unsupported claims: Deduct 1-2 points per unsupported metric or fabricated claim in anti_hallucination dimension. Gate-fail any CV with formal PM ownership claims without PM role evidence, people management claims without direct report evidence, or research framing when background shows no academic work. Unsupported title inflation from manager to VP or executive should trigger persona_fit_gate failure.
- Category vs job tradeoffs: Category defines table-stakes as AI delivery, platform architecture, and stakeholder translation. JD may emphasize evaluation, governance, or greenfield differently. Weight JD-specific requirements in jd_alignment dimension while maintaining category table-stakes in must_have_coverage_gate. When JD emphasizes manager scope more than category average, increase executive_presence weight mentally but do not change numeric weights.
Citations:
- data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- data/eval/baselines/ai_eng_manager_eea_baseline.json

## Evidence Ledger
- [high] AI platform and delivery keywords must appear 2-3 times across headline, profile, and experience for ATS optimization
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
  - data/eval/baselines/ai_eng_manager_eea_baseline.json
- [high] Platform design appears in 54.8% of roles making architecture proof a major separator for jd_alignment
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- [high] Delivery and scale are valued evidence types in 17/17 deep analyses requiring measurable adoption metrics for impact_clarity
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
  - data/eval/baselines/ai_eng_manager_eea_baseline.json
- [high] Executive scope appears in only 3.2% of roles so executive_presence must be interpreted as player-coach leadership not C-suite framing
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- [high] Research-heavy and PhD signals are both 0% so anti_hallucination must penalize academic or research framing without supporting background
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- [high] Stakeholder management appears in 67.7% of roles requiring cross-functional collaboration evidence as category table-stakes
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
  - data/eval/baselines/ai_eng_manager_eea_baseline.json
- [high] Budget and P&L ownership appears in only 6.5% of roles so anti_hallucination must flag such claims unless explicitly evidenced
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
- [high] Product Manager AI title appears in 13/31 roles but is noisy and should not be claimed without actual PM role evidence per unsafe_claim_gate
  - data/eval/blueprints/ai_eng_manager_eea_blueprint.json
  - data/eval/baselines/ai_eng_manager_eea_baseline.json
