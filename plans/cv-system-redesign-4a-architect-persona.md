# CV System Redesign 4A: Collapse Ensemble Passes and Add ARCHITECT Persona

## Context

Section 4A exists because the current ensemble favors storytelling over systems thinking in the most expensive part of the CV pipeline. In the current implementation, `EnsembleHeaderGenerator` defines `PersonaType` locally in [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:63), routes GOLD to `METRIC + NARRATIVE + KEYWORD` and SILVER to `METRIC + KEYWORD` via `TIER_PERSONAS` at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:102), and hard-codes GOLD as a 3-pass ensemble in `generate()` at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:201).

That architecture is misaligned with this candidate. The candidate’s verified identity in the prompt stack is already "Engineering Leader / Software Architect" with AI platform experience, and the header prompt file already contains evidence-first AI architect guidance in the V2 value proposition section at [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:1047). But the ensemble layer does not expose a persona dedicated to architecture judgment, platform trade-offs, technical depth, or infrastructure-to-outcome framing. The closest specialization today is NARRATIVE, whose prompt at [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:534) explicitly optimizes for "career storytelling" and "transformation narrative", which is the wrong lever for an architect-focused candidate and explains the observed over-positioning and weak proof quality.

The goal of 4A is therefore twofold:

1. Improve quality by replacing the NARRATIVE lens with an ARCHITECT lens for GOLD-tier header generation.
2. Reduce cost by collapsing GOLD from 3 persona passes to 2 persona passes before synthesis.

Expected outcome: better architect-fit headlines and taglines, tighter proof chains, lower hallucination pressure, and lower token spend in the highest-cost header path.

## Current Architecture Map

### Ensemble Flow

- `PersonaType` is defined only in [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:63), not in `types.py`.
- `TIER_PERSONAS` is defined in [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:102).
- GOLD execution:
  - `generate()` branches to `_generate_gold_tier()` at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:202)
  - `_generate_gold_tier()` runs each persona sequentially at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:260)
  - then synthesizes via `_synthesize_profiles()` at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:269)
  - then validates grounding with `_validate_and_flag()` from [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:545)
- SILVER execution:
  - `_generate_silver_tier()` runs two sequential personas and synthesis at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:289)
- BRONZE/SKIP execution:
  - fall back to the single-shot `HeaderGenerator.generate()` path via [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:217)

### Persona Prompt Sources

All persona prompts are imported from [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:472), not defined inline in the ensemble module:

- `METRIC_PERSONA_SYSTEM_PROMPT`: [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:476)
- `NARRATIVE_PERSONA_SYSTEM_PROMPT`: [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:534)
- `KEYWORD_PERSONA_SYSTEM_PROMPT`: [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:596)
- `SYNTHESIS_SYSTEM_PROMPT`: [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:660)

### Persona Output Schema

Each persona returns JSON validated into `ProfileResponse` at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:147). Required fields:

- `headline`
- `tagline`
- `key_achievements`
- `core_competencies`
- `highlights_used`
- `keywords_integrated`
- `exact_title_used`
- `answers_who`
- `answers_what_problems`
- `answers_proof`
- `answers_why_you`

The ensemble converts those responses into `ProfileOutput` in `_generate_with_persona()` at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:428). It also stores `tagline` in `value_proposition` and `narrative` for backward compatibility at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:444).

### Synthesis Behavior

Current synthesis is overly specific to the old 3-persona world:

- System prompt says:
  - tagline should take flow from NARRATIVE, metric hook from METRIC, keywords from KEYWORD
  - achievements should take metrics from METRIC, framing from NARRATIVE, coverage from KEYWORD
  - see [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:668)
- User prompt repeats the same fixed assumptions at [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:904)

This is the main prompt surface that must change for a 2-pass GOLD design. Without changing it, the synthesizer will continue optimizing for a missing NARRATIVE draft.

### Tier Routing in the Orchestrator

Tier selection and ensemble routing happen in [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:706):

- fit score to tier: [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:707)
- ensemble for GOLD/SILVER: [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:714)
- single-shot for BRONZE/SKIP: [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:735)

No persona-specific logic exists in the orchestrator today. Tier routing remains purely fit-score based.

### Single-Shot Path

The non-ensemble path is the V2 `HeaderGenerator.generate()` flow at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:1433). It differs materially from ensemble:

- `generate_profile()` uses a value proposition plus LLM bullet-selection model rather than persona drafts and synthesis, starting at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:715)
- it already includes strong evidence-first AI guidance and the Commander-4 guard at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:793)
- it already has role-category-specific templates for `ai_architect` and `ai_leadership` in [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:1010)

The ARCHITECT persona should reuse those concepts, not duplicate NARRATIVE-style copywriting logic.

### Types and Compatibility

Relevant data structures live in [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:915):

- `ProfileOutput`: [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:915)
- `ValidationFlags`: [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1367)
- `EnsembleMetadata`: [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1414)
- `HeaderOutput`: [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1460)

`PersonaType` is not in `types.py`, so changing it does not require a schema migration there. Compatibility risk is concentrated in tests and any consumer that interprets `ensemble_metadata.personas_used`.

### Existing Tests

The current ensemble test file is [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:1). It explicitly encodes the current architecture:

- enum members asserted at [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:142)
- GOLD expected as 3 personas at [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:161)
- metadata assumes GOLD has 3 passes and `["metric", "narrative", "keyword"]` at [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:279)
- prompt builder tests expect NARRATIVE-specific copy at [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:485)
- synthesis prompt test assumes NARRATIVE is part of the drafted inputs at [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:519)

## Architecture Decision

### Tier Personas

Recommended final configuration:

```python
# Before
TIER_PERSONAS = {
    ProcessingTier.GOLD: [PersonaType.METRIC, PersonaType.NARRATIVE, PersonaType.KEYWORD],
    ProcessingTier.SILVER: [PersonaType.METRIC, PersonaType.KEYWORD],
    ProcessingTier.BRONZE: [],
    ProcessingTier.SKIP: [],
}

# After
TIER_PERSONAS = {
    ProcessingTier.GOLD: [PersonaType.METRIC, PersonaType.ARCHITECT],
    ProcessingTier.SILVER: [PersonaType.METRIC, PersonaType.KEYWORD],
    ProcessingTier.BRONZE: [],
    ProcessingTier.SKIP: [],
}
```

Justification:

- `METRIC` is still required because it is the cleanest proof-preserving persona.
- `ARCHITECT` fills the missing quality gap: system design, platform decisions, technical depth, and infrastructure-to-outcome framing.
- `KEYWORD` remains valuable, but SILVER is the correct place for it because its main job is ATS term coverage rather than candidate identity shaping.
- Retaining all 3 personas for GOLD would preserve ATS coverage but fails the 4A cost objective and keeps the synthesis problem over-constrained.
- Keeping SILVER as `METRIC + KEYWORD` avoids role-conditional branching in the orchestrator and preserves the current cheaper ATS-oriented path.

Decision: do not make SILVER role-conditional in 4A. Revisit only if post-change diagnostics show architect-role SILVER headers are still materially weaker than GOLD headers.

### What ARCHITECT Emphasizes

ARCHITECT should emphasize what METRIC and KEYWORD do not:

- architecture decisions rather than generic achievements
- platform design, system boundaries, operating models, and trade-offs
- why a design mattered, not just that it transformed something
- links between technical choices and business outcomes
- production rigor when AI claims are present
- evidence-first identity: software architect and engineering leader first, AI platform extension second

This persona should not:

- optimize for story arc like NARRATIVE
- optimize for keyword density like KEYWORD
- overclaim AI-specialist identity when evidence is recent or partial

### Synthesis Strategy

Change synthesis from fixed-role merge logic to persona-aware merge logic.

Implementation decision:

- Keep one synthesizer entry point, but make both prompt builders dynamic.
- `SYNTHESIS_SYSTEM_PROMPT` becomes generic and conditional:
  - if `ARCHITECT` is present, prioritize architecture identity, system design framing, and technical depth
  - if `METRIC` is present, preserve exact metrics and scale indicators
  - if `KEYWORD` is present, preserve grounded JD terminology and competency coverage
  - do not refer to personas that are absent
- `build_synthesis_user_prompt()` should compute an explicit `synthesis_priorities` block based on the actual persona set rather than hard-coding NARRATIVE.

For GOLD (`METRIC + ARCHITECT`), merge rules should be:

- headline: choose the most accurate and evidence-bounded title
- tagline: start from ARCHITECT identity and platform framing, then inject one metric or scale anchor from METRIC
- achievements: preserve all strong quantified proof from METRIC, but prefer ARCHITECT wording when it better surfaces design decisions or platform outcomes
- competencies: merge grounded competencies from both drafts; do not try to emulate KEYWORD-only density if no keyword draft exists

For SILVER (`METRIC + KEYWORD`), merge rules remain:

- metric proof from METRIC
- ATS wording and competency coverage from KEYWORD
- no narrative requirement

## ARCHITECT Persona System Prompt

Insert the following new constant into [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:533) immediately after `METRIC_PERSONA_SYSTEM_PROMPT` and before `NARRATIVE_PERSONA_SYSTEM_PROMPT`.

```python
ARCHITECT_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN SYSTEM DESIGN AND PLATFORM ARCHITECTURE.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY that positions the candidate as a credible systems thinker, platform architect, and engineering leader.

=== ARCHITECT-FIRST HYBRID STRUCTURE ===

1. **HEADLINE**: "[CLEANED JOB TITLE] | [X]+ Years Technology Leadership"
   - Use ONE title from the JD — NEVER combine two senior titles
   - The candidate's verified identity is "Engineering Leader / Software Architect" with AI platform experience
   - If the JD title is more specialized than the evidence supports, choose the closest accurate architect/leadership title
   - The headline must stay credible under interview scrutiny

2. **TAGLINE** (15-25 words, max 200 chars):
   - Third-person absent voice (NO pronouns: I, my, you, your, we, our)
   - Lead with architect identity, platform scope, or systems-thinking orientation
   - Show technical depth through system design, architecture choices, platform modernization, reliability, or infrastructure-to-outcome framing
   - Include one proof anchor when possible: scale, uptime, latency, delivery acceleration, cost impact, or user/platform scope
   - Prefer evidence-first positioning: verified architect identity first, AI/platform extension second

   Good examples:
   - "Software architect designing resilient platforms that scale to 50,000 requests per second with measurable reliability gains."
   - "Engineering leader translating distributed systems rigor into AI platform reliability for enterprise-scale production use."
   - "Platform architect guiding architecture modernization, uptime improvement, and delivery acceleration across complex systems."

   Bad examples:
   - "Generative AI visionary redefining the future of enterprise intelligence."  # over-positioned, ungrounded
   - "Engineering leader with a compelling story of transformation."  # narrative-first, not architecture-first
   - "Cloud expert passionate about innovation and excellence."  # cliché, weak proof

3. **KEY ACHIEVEMENTS** (5-6 bullets):
   - Every bullet must come from the source bullets
   - Prefer bullets that show architecture decisions, system design, platform choices, technical strategy, reliability engineering, or infrastructure modernization
   - Explain the bridge from architecture choice to outcome
   - Preserve exact metrics when present
   - Show scale where available: users, requests, uptime, cost, team size, deployment speed, incidents, regions
   - Use compact architect framing:
     "[Architected/Designed/Built/Established] [system/platform/operating model] [for scope], [result/outcome]"

   Examples:
   - "Architected event-driven platform handling 50,000 requests/second, improving scalability and operational resilience"
   - "Designed CI/CD operating model reducing deployment time by 75%, enabling faster and safer releases"
   - "Built cloud platform foundations delivering $2M cost savings through infrastructure modernization"
   - "Established reliability practices reducing production incidents by 60% across critical systems"
   - "Led architecture modernization supporting team scale, platform stability, and sustained delivery velocity"

4. **CORE COMPETENCIES**: 10-12 ATS-friendly keywords
   - Prioritize system design, platform, architecture, reliability, cloud, distributed systems, and verified JD terms
   - Keep competencies grounded in actual evidence

=== ARCHITECT PERSONA EMPHASIS ===

Focus on what a strong architect signals:
- System boundaries
- Design decisions
- Platform operating models
- Technical trade-offs
- Reliability and scalability
- Infrastructure-to-business-outcome bridges
- Cross-team technical influence
- Architecture judgment that can be defended in interview

Do NOT behave like the METRIC persona:
- Metrics matter, but they are supporting proof, not the whole message
- Do not force every sentence to be metric-led if architecture signal becomes weaker

Do NOT behave like the KEYWORD persona:
- ATS coverage matters, but do not stuff terms unnaturally
- Prefer the strongest grounded architecture terms over raw JD mirroring

Do NOT behave like the NARRATIVE persona:
- Do not optimize for story arc, transformation drama, or career mythology
- Prefer technical credibility over inspirational phrasing

=== EVIDENCE-FIRST ORDERING RULE ===

Lead with the candidate's VERIFIED identity, then extend to JD-relevant capabilities.

PATTERN:
"[Verified architect/engineering identity] + [platform/system design capability] + [proof anchor]"

GOOD:
- "Production platform architect applying distributed systems rigor to enterprise AI reliability"
- "Engineering leader building resilient cloud platforms with verified cost and delivery gains"

BAD:
- "AI architect revolutionizing enterprise intelligence through next-generation agents"
- "Narrative-driven leader transforming organizations through visionary innovation"

RULE:
If the candidate's primary career is software architecture / engineering leadership and AI is a recent or partial extension, lead with architecture / engineering identity first and extend to AI second.

=== HEADLINE GROUNDING RULES ===

- Use ONE title from the JD — NEVER combine two senior titles (e.g., "AI Engineer · AI Architect")
- The candidate's verified identity is "Engineering Leader / Software Architect" with AI platform experience
- If the JD title implies a specialization the candidate does not have, use the closest accurate title from the candidate's background
- The credibility anchor must reflect actual years from experience
- When the JD title is a reasonable match and can be defended, use it as-is for ATS

=== COMMANDER-4 / JOYIA CLAIM GUARD ===

When using AI-platform evidence:
- Commander-4 / Joyia is an enterprise AI workflow platform within Seven.One
- Use "42 plugins" NOT "42 agents"
- Use "2,000 users" NOT "2,000+ enterprise users"
- Do NOT present Commander-4 as a standalone employer or standalone job title
- Do NOT invent AI capabilities, adoption metrics, or platform scope beyond the verified bullets provided

=== ANTI-HALLUCINATION RULES ===

CRITICAL:
- You may ONLY use achievements, claims, technologies, and metrics that appear in the provided bullets or grounded keyword list
- Do NOT round numbers
- Do NOT invent architecture initiatives, trade-offs, platforms, or governance structures
- Transform phrasing if needed, but never change the underlying facts
- If a claim cannot pass the "show me the source bullet" proof test, do NOT include it

=== QUALITY CHECKLIST ===

Before finalizing, verify:
- Tagline is third-person absent voice
- Tagline stays under 200 characters
- Headline is evidence-bounded
- At least 3 achievements clearly express architecture or platform judgment when source bullets allow
- Metrics remain exact wherever used
- Output sounds like an architect, not a storyteller or ATS optimizer
- Content could be defended verbally in interview

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[CLEANED JOB TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word architect-driven hook (third-person absent voice, max 200 chars)",
  "key_achievements": ["Achievement 1", "Achievement 2", "...5-6 total"],
  "core_competencies": ["Competency 1", "Competency 2", "...10-12 total"],
  "highlights_used": ["exact metric or proof point from bullets", "another proof point"],
  "keywords_integrated": ["grounded_jd_keyword_1", "grounded_jd_keyword_2"],
  "exact_title_used": "The exact title from the JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
}

Do NOT include markdown, explanation, or preamble. Just JSON.
"""
```

## Sample Persona Output Differences

Using the same grounded evidence set:

- Source bullets:
  - `Reduced deployment time by 75% through CI/CD pipeline improvements`
  - `Built event-driven architecture handling 50,000 requests/second`
  - `Led team of 15 engineers to deliver $2M cost savings through cloud migration`

`METRIC` output should look like:

- Tagline: `Technology leader delivering $2M savings while reducing deployment time by 75% across cloud platform modernization.`
- Best bullet pattern: `Reduced deployment time by 75% through CI/CD pipeline improvements`

`NARRATIVE` output currently looks like:

- Tagline: `Engineering leader who transformed a legacy platform into an enterprise-ready foundation serving millions.`
- Risk: compelling, but prone to over-stretch and weak proof chains

`ARCHITECT` output should look like:

- Tagline: `Software architect modernizing platform foundations to improve delivery speed, reliability, and system scale with measurable proof.`
- Best bullet pattern: `Architected event-driven platform handling 50,000 requests/second, improving scalability and operational resilience`

The ARCHITECT version differs by making architecture judgment explicit instead of turning the same evidence into story language.

## Code Changes

### 1. Extend Persona Enum and Prompt Imports

File: [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:53)

Changes:

- add `ARCHITECT_PERSONA_SYSTEM_PROMPT` to the import list near lines 53-59
- add `ARCHITECT = "architect"` to `PersonaType` at lines 63-67
- update the docstring at line 64 to mention ARCHITECT

### 2. Update Tier Configuration

File: [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:102)

Changes:

- replace GOLD persona list at lines 103-105 with `[PersonaType.METRIC, PersonaType.ARCHITECT]`
- leave SILVER unchanged as `[PersonaType.METRIC, PersonaType.KEYWORD]`
- update GOLD comments and docstrings:
  - `generate()` currently hard-codes `passes = 3` at line 204
  - `_generate_gold_tier()` currently says `3-pass ensemble` at lines 252-257
- convert `passes` calculation in `generate()` to `len(self.TIER_PERSONAS[tier])` for GOLD and SILVER so counts stay aligned with configuration

### 3. Wire ARCHITECT Persona into Persona Generation

File: [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:352)

Changes:

- extend `prompt_map` at lines 353-357 with `PersonaType.ARCHITECT: ARCHITECT_PERSONA_SYSTEM_PROMPT`
- update method docstring at lines 340-350 to include ARCHITECT

### 4. Add ARCHITECT Prompt Constant and Persona Emphasis

File: [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:476)

Changes:

- insert `ARCHITECT_PERSONA_SYSTEM_PROMPT` between the existing METRIC and NARRATIVE prompt blocks
- extend the `persona_emphasis` map inside `build_persona_user_prompt()` at lines 760-780 with a new `"architect"` branch emphasizing:
  - system design
  - platform architecture
  - technical trade-offs
  - architecture-to-outcome bridges
- update the argument documentation at lines 738-740 so the supported persona set includes `"architect"`

Recommended new `persona_emphasis["architect"]` text:

```text
PERSONA EMPHASIS: ARCHITECT
Your goal is to emphasize system design, platform architecture, technical judgment, and infrastructure-to-outcome bridges.
Focus on: architectural decisions, reliability, scalability, modernization, operating models, and technical depth.
Prefer achievements that show why a design mattered, not just what changed.
```

### 5. Make Synthesis Prompt Persona-Aware

Files:

- [src/layer6_v2/prompts/header_generation.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py:660)
- [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:457)

Changes:

- replace fixed NARRATIVE/METRIC/KEYWORD instructions in `SYNTHESIS_SYSTEM_PROMPT` at lines 668-695 with conditional rules based on which draft types are present
- update `build_synthesis_user_prompt()` at lines 858-916 to:
  - inspect the incoming `persona_outputs`
  - emit a `PERSONAS PRESENT:` line
  - emit a `SYNTHESIS PRIORITIES:` block tailored to the persona set
  - stop hard-coding `Take narrative flow from narrative draft` when no narrative draft exists

Recommended synthesis behavior:

- if `architect` and `metric` present:
  - tagline = architect identity + metric proof
  - achievements = metric completeness + architect framing
- if `metric` and `keyword` present:
  - tagline = metric proof + grounded JD wording
  - achievements = metric completeness + keyword coverage
- if `architect`, `metric`, and `keyword` ever coexist in future:
  - metric proof + architect identity + keyword coverage

### 6. Orchestrator Changes

File: [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:714)

Decision: no tier-routing code change required in 4A.

Reason:

- ensemble vs single-shot routing is already purely tier-based
- GOLD and SILVER still use the same ensemble entry point
- changing persona composition inside `EnsembleHeaderGenerator` is sufficient

Only optional changes:

- update log messages or comments if they mention the legacy 3-pass GOLD assumption
- no role-conditional SILVER logic in 4A

### 7. No `types.py` Change Required

File checked: [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1414)

No schema change required because:

- `EnsembleMetadata.personas_used` is already `List[str]`
- `ProfileOutput` schema is unchanged
- `HeaderOutput` schema is unchanged

## Token Budget Analysis

The codebase does not currently persist per-pass token counts in ensemble metadata. `UnifiedLLM` can expose `input_tokens` and `output_tokens` in `LLMResult` at [src/common/unified_llm.py](/Users/ala0001t/pers/projects/job-search/src/common/unified_llm.py:67), but `EnsembleHeaderGenerator` does not capture or aggregate that data.

Using the actual prompt builders with representative inputs:

- persona system prompt size:
  - `METRIC`: about 609 tokens
  - `NARRATIVE`: about 608 tokens
  - `KEYWORD`: about 619 tokens
- representative persona user prompt: about 410 tokens
- representative synthesis system prompt: about 506 tokens
- synthesis user prompt:
  - 2 persona drafts: about 417 tokens
  - 3 persona drafts: about 526 tokens

Approximate input-token budget:

- one persona pass: `~609 + ~410 = ~1,019` tokens
- 3-draft synthesis input: `~506 + ~526 = ~1,032` tokens
- 2-draft synthesis input: `~506 + ~417 = ~923` tokens

Approximate total input tokens:

- Current GOLD: `3 * 1,019 + 1,032 = ~4,089`
- Proposed GOLD: `2 * 1,019 + 923 = ~2,961`
- Input-token savings: `~1,128` tokens before counting output reduction

Once output tokens are included, the end-to-end savings are realistically closer to `~1.5K-2.0K` tokens per GOLD header because:

- one full persona JSON response is removed
- the synthesis user prompt is shorter
- the synthesizer has fewer draft bullets and competencies to inspect

Recommended plan language: keep the external estimate as `~2K tokens saved per GOLD-tier CV`, but document that current code does not yet record exact ensemble pass usage, so this remains a modeled estimate rather than a logged measurement.

Post-implementation follow-up:

- optionally add pass-level token aggregation to `EnsembleMetadata` if the redesign wants hard measurements in later iterations

## Test Strategy

Update and extend [tests/unit/test_layer6_v2_ensemble_header.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_ensemble_header.py:1).

### Required Unit Tests

1. ARCHITECT enum and routing
- replace the NARRATIVE enum assertion block at lines 146-149 with an ARCHITECT assertion
- update GOLD tier routing assertions at lines 161-167:
  - expect exactly 2 personas
  - expect `METRIC` and `ARCHITECT`
  - assert `NARRATIVE` is not present

2. GOLD metadata
- update metadata fixture expectations at lines 279-292
- expect `passes_executed == 2`
- expect `personas_used == ["metric", "architect"]`

3. Persona prompt builder
- add `test_build_persona_user_prompt_architect()`
- assert the prompt contains `ARCHITECT`
- assert terms like `architecture`, `system design`, or `platform`

4. Synthesis prompt behavior
- replace the current fixed NARRATIVE synthesis test at lines 519-536
- add:
  - one test for `metric + architect`
  - one test for `metric + keyword`
- assert the generated prompt references the actual personas present and does not reference absent personas

5. Persona generation mapping
- add a unit test around `_generate_with_persona()` with mocked `UnifiedLLM.invoke`
- verify `PersonaType.ARCHITECT` uses `ARCHITECT_PERSONA_SYSTEM_PROMPT`

6. SILVER regression
- keep SILVER assertions at lines 169-174 unchanged
- add an explicit test that SILVER remains `["metric", "keyword"]`

### Optional Higher-Level Regression Tests

- add a mocked GOLD end-to-end test where two persona results are synthesized successfully
- if golden outputs exist later, compare:
  - headline defensibility
  - proof density in tagline
  - number of architecture-signaling bullets

## Risks and Rollback

### Primary Risks

- synthesis quality regression if the prompt remains implicitly tuned for NARRATIVE
- weaker ATS keyword density on GOLD because KEYWORD is removed from that tier
- test failures wherever GOLD is assumed to be 3 passes
- unexpected downstream assumptions in logs, analytics, or dashboards that parse `personas_used`

### Mitigations

- make synthesis persona-aware instead of simply renaming NARRATIVE to ARCHITECT
- keep SILVER unchanged to preserve one ATS-oriented path
- preserve `keywords_integrated` aggregation across persona results in `_synthesize_profiles()` at [src/layer6_v2/ensemble_header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py:521)
- verify architect prompts still pull grounded JD keywords into competencies even without KEYWORD persona

### Rollback Plan

Rollback is low risk because the change is localized:

1. revert `TIER_PERSONAS` GOLD entry to `METRIC + NARRATIVE + KEYWORD`
2. remove `ARCHITECT` from `PersonaType`
3. remove `ARCHITECT_PERSONA_SYSTEM_PROMPT` and its prompt-map entry
4. restore old synthesis prompt wording
5. restore ensemble tests to 3-pass GOLD expectations

No data migration is required because no persisted schema is changing.

## Implementation Sequence

1. Add `ARCHITECT_PERSONA_SYSTEM_PROMPT` and `persona_emphasis["architect"]`.
2. Extend `PersonaType` and prompt imports.
3. Change GOLD `TIER_PERSONAS` to `METRIC + ARCHITECT`.
4. Update pass counting so GOLD derives count from configuration instead of hard-coded `3`.
5. Refactor synthesis prompts to be persona-aware.
6. Update unit tests for enum membership, routing, metadata, and synthesis.
7. Run:
   - `python -m pytest tests/unit/test_layer6_v2_ensemble_header.py`
   - `python -m pytest tests/unit/test_layer6_v2_orchestrator.py -k header`
   - `python -m pytest tests/unit/test_layer6_v2_header_generator.py -k profile`

## Final Recommendation

Implement 4A as:

- GOLD: `METRIC + ARCHITECT + synthesis`
- SILVER: unchanged `METRIC + KEYWORD + synthesis`
- BRONZE/SKIP: unchanged single-shot

This gives the best quality/cost trade-off for the current candidate and removes the least defensible part of the ensemble architecture: narrative-first optimization in a role family that needs architect-first credibility.
