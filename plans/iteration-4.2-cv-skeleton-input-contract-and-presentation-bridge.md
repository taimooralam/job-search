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

### 8.8 Langfuse tracing principles (inherited from iteration 4)

Every 4.2 stage and prompt boundary must be observable through the shared
preenrich tracing seam. This section is the contract; it is not optional and
sub-plans 4.2.1–4.2.6 inherit it verbatim.

**Sink vs orchestration.** Langfuse is the observability sink, never the
orchestration plane. Run-level traces and job-level correlation stay separate;
do not collapse the pipeline into one giant session-only trace. Orchestration
lives in Mongo (`work_items`, `preenrich_stage_runs`, `preenrich_job_runs`,
`pre_enrichment.stage_states`). Langfuse mirrors what happened.

**Session pinning.** `langfuse_session_id` is pinned to `job:<level2_object_id>`
for every trace, span, and event emitted by any 4.2 stage or its sweeper path.

**Canonical naming.** Reuse the iteration-4 scheme. Every 4.2 stage is addressed
as `scout.preenrich.<stage_name>` for the stage span; stage-internal substeps
use `scout.preenrich.<stage_name>.<substep>`. No new top-level namespaces.
The canonical events that must be reachable for 4.2 jobs are:

- `scout.preenrich.run` (trace)
- `scout.preenrich.enqueue_root`
- `scout.preenrich.claim`
- `scout.preenrich.<stage_name>` (one per 4.2 stage: `stakeholder_surface`,
  `pain_point_intelligence`, `presentation_contract`, etc.)
- `scout.preenrich.enqueue_next`
- `scout.preenrich.finalize_cv_ready`
- `scout.preenrich.retry`
- `scout.preenrich.deadletter`
- `scout.preenrich.release_lease` (sweeper-driven)
- `scout.preenrich.snapshot_invalidation` (sweeper-driven)

**Required correlation metadata.** Every span and event must carry: `job_id`,
`level2_job_id`, `correlation_id`, `langfuse_session_id`, `run_id`,
`worker_id`, `task_type`, `stage_name`, `attempt_count`, `attempt_token`,
`input_snapshot_id`, `jd_checksum`, `lifecycle_before`, `lifecycle_after`,
`work_item_id`. 4.2 stages do not invent new required fields; they use the
canonical payload builder in `PreenrichTracingSession`.

**Metadata-first payloads.** Prefer counts, booleans, previews, checksums, ids,
prompt version, provider/model, transport, cache refs, retry reason, output
validity, and confidence band over full payload dumps. Do not attach full raw
JD, full stakeholder profiles, full proof-map bodies, or full
`presentation_contract` subdocuments to every span. Debug snapshots live in
Mongo under `debug_context`, not in Langfuse.

**Prompt policy.** If prompt capture is useful, it must flow through
`_sanitize_langfuse_payload(...)` in `src/pipeline/tracing.py` and respect
`LANGFUSE_CAPTURE_FULL_PROMPTS`. No stage may bypass the sanitizer with
ad-hoc string truncation or direct client calls.

**Span vs event discipline.**

- Spans for meaningful timed work: the stage body, each live Codex research
  call, each LLM primary/fallback attempt inside `_call_llm_with_fallback`,
  blueprint assembly where time is non-trivial, and artifact persistence
  when collection-backed writes happen.
- Events for point-in-time lifecycle transitions: claim, enqueue_next,
  finalize_cv_ready, retry, deadletter, release_lease, snapshot_invalidation.
- Do **not** create spans for pure local helpers, tiny formatters, or
  normalization passes that do not meaningfully affect latency. Do **not**
  create per-bullet or per-rule spans inside prompt synthesis — metadata
  counts are sufficient.

**External boundaries are non-negotiable.** Every external boundary a 4.2
stage reaches must be traceable: the Codex research transport
(`CodexResearchTransport.invoke_json`), LLM calls through
`_call_llm_with_fallback`, Mongo artifact upserts performed by the worker,
retry/deadletter transitions, snapshot invalidation, and cv-ready
finalization. Transport spans must expose `provider`, `model`, `transport`,
`duration_ms`, `success`, outcome classification
(`unsupported_transport`, `error_missing_binary`, `error_timeout`,
`error_subprocess`, `error_no_json`, `error_schema`, `error_exception`,
`success`), and `schema_valid`.

**Shared seam.** 4.2 stages must reuse `PreenrichTracingSession` via the
`ctx.tracer` handle threaded through `StageContext`. New helpers live in
`src/pipeline/tracing.py` or a closely related shared module. Do not scatter
direct `langfuse.Langfuse(...)` construction across stage files. Sweeper-side
emissions use `emit_preenrich_sweeper_event(...)` with canonical
`langfuse_session_id=job:<level2_id>`.

**Cardinality.** Stage-internal span names must be bounded. Per-candidate
iteration (e.g. stakeholder rank N, proof-map item N, dimension N) is
expressed through metadata fields, **not** by baking the index into the span
name. Unbounded candidate ranks in span names are a review blocker.

**Concurrency.** Stages that parallelize sub-calls (e.g. `stakeholder_surface`
discovery fan-out, pain extraction fan-out) must treat the shared tracer as
thread-safe at the coarse level and must not end the parent span before all
child spans have ended.

**Trace refs on Mongo state.** When a 4.2 stage run produces a Langfuse
trace, its `trace_id` and `trace_url` must flow into the preenrich run
records (`preenrich_stage_runs`, `preenrich_job_runs`) and become reachable
from the level-2 UI fields, matching the iteration-4 contract. This is what
lets an operator open a single job in the UI and jump directly into
Langfuse for its timing, retries, and boundary failures.

**Operator goal.** A human must be able to debug one 4.2 preenrich job from
Mongo state into Langfuse and understand where time went, which retries
happened, which model and transport boundaries failed, and which stage
fell back versus succeeded. Tracing exists for this goal; any instrumentation
that does not advance it is noise.

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
