# Iteration 4.2 Plan: CV Skeleton Input Contract and Presentation Bridge

## 1. Executive Summary

Iteration 4.2 is the next slice after 4.1.3 / 4.1.3.1.

The 4.1 blueprint DAG now produces a strong **job understanding contract**:

- `jd_facts` for structured JD truth
- `classification` for role taxonomy and tone
- `application_surface` for canonical application context
- `research_enrichment` for company, role, application, and compact stakeholder intelligence
- `job_inference` for semantic role synthesis
- `cv_guidelines` for high-level writing guidance (current, pre-4.2)
- `blueprint_assembly` for the compact snapshot mirror

What is still missing is the bridge between:

- understanding the job
- understanding the evaluators
- understanding the likely pains and proof expectations
- producing a **candidate-agnostic but generation-ready CV skeleton contract**

Iteration 4.2 adds that bridge. The target is not CV prose. The target is a family of
structured artifacts that define, before any candidate evidence is introduced:

- who is likely evaluating the CV
- what each evaluator type wants to see
- which pains and proof expectations dominate
- what the ideal candidate looks like on paper
- what the document should structurally emphasize
- what must never be emphasized unless later candidate evidence supports it

## 2. Objective

Produce the missing pre-candidate input artifacts required for a high-quality CV
skeleton stage, using the current blueprint DAG outputs as the sole evidence base.

The 4.2 output family must enable a later CV skeleton stage to answer, in structured
form and without candidate leakage:

- What title should the CV use?
- What header shape, tagline, and proof density should be shown?
- Whether an AI highlights section should exist, and if so what type.
- Which competencies should be visible early.
- Which experience dimensions should dominate the document.
- What order of proof the CV should follow.
- What must never be emphasized unless later candidate evidence supports it.
- Who the likely evaluators are, and how their preferences shape the above.

## 3. Non-Goals

Iteration 4.2 explicitly does not:

- generate final CV text, headers, bullets, or summaries
- match candidate evidence from the master CV or evidence store
- generate cover letter prose, outreach copy, or interview prep
- invent private stakeholder data or protected-trait inferences
- produce manipulative or clinical "psychological profiles"
- replace or redesign `research_enrichment` / `application_surface` (4.1.3 / 4.1.3.1)
- collapse all synthesis work into one monolithic prompt
- introduce a new control-plane pattern outside the existing blueprint stage DAG

Final CV generation remains governed by `docs/current/cv-generation-guide.md` and is
out of scope for 4.2.

## 4. Core Design Decision

4.2 should not become six independent production DAG stages. The clean split is:

1. **Separate stage + artifact:** `stakeholder_surface` (identity-critical, web-facing)
2. **Separate stage + artifact:** `pain_point_intelligence` (evidence-mining, proof mapping)
3. **Combined synthesis stage + artifact:** `presentation_contract`

`presentation_contract` persists four co-produced subdocuments in one schema:

- `document_expectations` (4.2.2)
- `ideal_candidate_presentation_model` (4.2.4)
- `experience_dimension_weights` (4.2.5)
- `truth_constrained_emphasis_rules` (4.2.6)

This keeps identity/web work isolated from pure evidence mining, and both isolated
from presentation synthesis. It also prevents four tightly-coupled synthesis
outputs from drifting apart across separate runs and prompts.

## 5. Why This Split Is Correct

### 5.1 `stakeholder_surface` stays separate

- depends on public-professional identity resolution and web research
- has stricter safety requirements than pure synthesis
- must fail open to inferred personas when real identities are unsafe
- invalidates on company/role identity changes and research updates, not only on
  synthesis prompt changes
- shares failure modes (fabricated URLs, cross-company collisions) with 4.1.3
  stakeholder discovery and must stay governed by those same rules

### 5.2 `pain_point_intelligence` stays separate

- upgrades the runner pain-point miner into an evidence-mining stage
- has its own invalidation, evals, and source discipline
- produces a reusable proof-target map consumed by `presentation_contract` and,
  later, by candidate evidence retrieval and STAR selection
- should never be flattened into a sub-note inside a larger synthesis prompt

### 5.3 `document_expectations`, `ideal_candidate_presentation_model`,
`experience_dimension_weights`, and `truth_constrained_emphasis_rules` combine

- share the same inputs (`jd_facts`, `classification`, `research_enrichment`,
  `stakeholder_surface`, `pain_point_intelligence`, `job_inference`)
- are all presentation-synthesis, not fetch or identity work
- benefit from a shared evidence frame and a single prompt context
- splitting would produce prompt drift, contradictory defaults, and higher cost
- a single synthesis artifact can still persist each subdocument separately and
  be validated independently

## 6. Recommended Stage Order

Recommended blueprint DAG order after the current 4.1 chain:

1. `jd_facts`
2. `classification`
3. `application_surface`
4. `research_enrichment`
5. `stakeholder_surface` *(new, 4.2.1)*
6. `pain_point_intelligence` *(new, 4.2.3)*
7. `presentation_contract` *(new, 4.2.2 + 4.2.4 + 4.2.5 + 4.2.6)*
8. `job_inference` remains as today; it may optionally read the new artifacts
9. `cv_guidelines` eventually reads `presentation_contract` instead of re-deriving
10. `blueprint_assembly` updated to mirror compact projections from the new artifacts

Prerequisite wiring (to mirror current `stage_registry` conventions):

- `stakeholder_surface.prerequisites = ("jd_facts", "classification", "application_surface", "research_enrichment")`
- `pain_point_intelligence.prerequisites = ("jd_facts", "classification", "research_enrichment")`
  - `stakeholder_surface` is an opportunistic input, not a hard prerequisite
- `presentation_contract.prerequisites = ("jd_facts", "classification", "research_enrichment", "stakeholder_surface", "pain_point_intelligence")`
  - `job_inference` is an opportunistic input when available

## 7. Canonical New Artifacts

### 7.1 `stakeholder_surface`

Purpose:

- real stakeholder discovery when safely available (public-professional only)
- explicit inferred stakeholder personas when real identities are weak or uncovered
- public-professional decision style and evaluator-conditioned CV preference signals

Detail: `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`.

### 7.2 `pain_point_intelligence`

Purpose:

- pain, strategic-need, risk, and success-metric extraction richer than the current
  proxy fields in `blueprint_assembly.snapshot`
- explicit mapping from pain to proof expectation
- reusable `search_terms[]` for later candidate evidence retrieval

Detail: `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`.

### 7.3 `presentation_contract`

Purpose:

- one canonical pre-candidate CV skeleton contract
- document shape and audience expectations (4.2.2)
- ideal-candidate-on-paper model (4.2.4)
- experience dimension salience (4.2.5)
- truth-constrained emphasis rules (4.2.6)

All four subdocuments share evidence and must be validated together.

## 8. Cross-Cutting Rules

### 8.1 Web research

- `stakeholder_surface`: may perform bounded web research when company identity is
  resolved and public-professional discovery is enabled. Reuses the 4.1.3 identity
  ladder rather than inventing a new one.
- `pain_point_intelligence`: does **not** perform web research by default. Reuses
  `research_enrichment` outputs. Optional supplemental search is permitted only
  when evidence is thin and budget allows; it never duplicates the full research
  pipeline.
- `presentation_contract`: never fetches the web in the normal path. Synthesizes
  strictly over upstream artifacts.

### 8.2 Fail-open / fail-closed

- `stakeholder_surface`: fail open to inferred personas; fail closed on fabricated
  names, URLs, LinkedIn slugs, cross-company identities, private contact data,
  and protected-trait inference.
- `pain_point_intelligence`: fail open to JD-only pain extraction with lower
  confidence and explicit `source_scope`; fail closed on fabricated company events,
  unsupported urgency, and generic HR boilerplate for non-generic JDs.
- `presentation_contract`: fail open to role-family defaults and explicit
  unresolved markers; fail closed on candidate-specific assumptions, title
  inflation unsupported by role evidence, and claims that contradict upstream
  artifacts.

### 8.3 Richer-first ingress (inherited from 4.1.3.1)

All 4.2 stages adopt the 4.1.3.1 principle: validation is loose on shape and
strict on truth. Unexpected wrappers, aliases, and list/dict/scalar drift are
normalized at ingress via shared normalizers. Fabricated identities, private
data, and protected-trait claims are rejected hard.

### 8.4 Model routing (initial defaults)

- web-facing identity work (`stakeholder_surface` discovery):
  primary `gpt-5.2` for extraction discipline; escalate to `gpt-5.4` only when
  evidence is solid but the first pass returns ambiguity.
- bounded structured extraction and normalization helpers:
  `gpt-5.4-mini` where safe.
- high-value synthesis (`pain_point_intelligence`, `presentation_contract`):
  `gpt-5.4` primary. Benchmark `gpt-5.2` as an alternative for extraction
  discipline on pain mining.

Final model choices are gated by benchmarks per stage, following the pattern
established in `docs/current/decisions/2026-04-21-jd-facts-model-selection.md`.

### 8.5 Prompt discipline

All 4.2 prompts must enforce:

- candidate-agnostic outputs only
- no private, speculative, or protected-trait personal data
- evidence-first reasoning with `source_ids` or explicit "upstream-artifact" basis
- unresolved is a valid first-class answer
- no CV prose generation
- no "perfect candidate" fantasy traits unsupported by JD/research evidence

### 8.6 Artifact discipline

- Full artifacts stay collection-backed.
- `blueprint_assembly.snapshot` mirrors only compact projections:
  counts, top-level confidence, key refs, and short summaries.
- Full source trails, search journals, and evidence blocks stay out of the compact
  snapshot.

### 8.7 Separation of concerns

- `stakeholder_surface` emits evaluator **signals**, never final document instructions.
- `pain_point_intelligence` emits pains, needs, risks, metrics, and a **proof map**;
  it does not prescribe section order or title strategy.
- `presentation_contract` is the **only** 4.2 artifact that emits document-shape
  decisions (section order, title strategy, AI section policy, dimension weights,
  emphasis rules).

## 9. Primary Source Surfaces for 4.2

Current implementation surfaces 4.2 must build on:

- `src/preenrich/stages/jd_facts.py`
- `src/preenrich/stages/classification.py`
- `src/preenrich/stages/application_surface.py`
- `src/preenrich/stages/research_enrichment.py`
- `src/preenrich/stages/job_inference.py`
- `src/preenrich/stages/blueprint_assembly.py`
- `src/preenrich/blueprint_models.py`
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/stage_registry.py`
- `src/preenrich/dag.py`
- `src/preenrich/stage_worker.py`
- `src/layer2/pain_point_miner.py`
- `src/layer5/people_mapper.py`
- `src/common/persona_builder.py`
- `src/layer6_v2/prompts/grading_rubric.py`
- `docs/current/cv-generation-guide.md`
- `docs/current/outreach-detection-principles.md`
- `plans/research-enrichment-4.1.3-unified-company-role-application-people-intelligence.md`
- `plans/research-enrichment-4.1.3.1-live-codex-hard-cutover-and-schema-alignment.md`
- `plans/brainstorming-new-cv-v2.md`

## 10. File Plan Index

This umbrella is implemented by:

- `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `plans/iteration-4.2.3-pain-point-intelligence-v2-and-proof-map.md`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`

Files 4.2.2, 4.2.4, 4.2.5, and 4.2.6 describe the four subdocuments co-produced
inside the single `presentation_contract` stage.

## 11. Initial Implementation Surfaces

Recommended implementation targets for 4.2 prompts:

- new `src/preenrich/stages/stakeholder_surface.py`
- new `src/preenrich/stages/pain_point_intelligence.py`
- new `src/preenrich/stages/presentation_contract.py`
- extend `src/preenrich/blueprint_models.py`
  - `StakeholderRecord` extensions (decision style, CV preference surface)
  - new `InferredStakeholderPersona`
  - new `StakeholderSurfaceDoc`
  - new `PainPointIntelligenceDoc`
  - new `PresentationContractDoc` with four sub-models
- extend `src/preenrich/blueprint_prompts.py` with the new prompt builders
- register stages in `src/preenrich/stage_registry.py`
- wire prerequisites in `src/preenrich/dag.py`
- update `src/preenrich/stages/blueprint_assembly.py` to project compact mirrors
- update `docs/current/architecture.md` and `docs/current/missing.md`

## 12. Rollout and Success Criteria

### 12.1 Rollout order

1. Ship `stakeholder_surface` behind a capability flag; benchmark against a
   curated set of jobs; default-on only after precision and safety gates pass.
2. Ship `pain_point_intelligence` behind a capability flag; benchmark specificity
   and grounding; default-on after proof-map usefulness gates pass.
3. Ship `presentation_contract` only after 1 and 2 are default-on and stable.
4. Update `cv_guidelines` to consume `presentation_contract` as its preferred
   input, with a compatibility path for jobs that predate the artifact.

### 12.2 Success condition

4.2 succeeds when the pre-candidate blueprint can answer, in structured form and
without candidate leakage:

- which evaluator lenses matter for this job
- which pains and proof targets dominate
- what the ideal candidate should look like on paper
- how the document should be shaped
- which experience dimensions deserve emphasis
- which emphasis is forbidden unless later candidate evidence supports it

And the later CV skeleton stage can consume a single coherent contract rather
than reverse-engineering evaluator preference, pain focus, and presentation
strategy from mixed research data.
