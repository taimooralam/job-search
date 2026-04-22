# Iteration 4.1 Plan: Job Blueprint Preenrich Cutover

## 1. Executive Summary
Iteration 4.1 keeps the iteration-4 Mongo work-item DAG, `cv_ready` terminal state, sweepers, `systemd` worker model, and job-detail single-document read pattern. It replaces the legacy content logic of the current preenrich lane with the Stage 1 blueprint pipeline from `plans/brainstorming-new-cv-v2.md`, while preserving the parts the current repo still depends on: `jd_structure`, `annotations`, and a temporary persona-compatibility path.

Iteration 4.1 does not introduce candidate modeling, CV prose generation, or new downstream runner lanes. It makes preenrich produce `job_blueprint` as the new source of truth, mirrors a safe snapshot back onto `level-2`, keeps current UI and downstream consumers working through compatibility projections, and ensures the blueprint lane finishes before any CV runner pipeline starts.

The correct move after iteration 4 is not a clean-slate rewrite. It is a content-layer replacement on top of the existing stage-DAG control plane.

## 2. Current-State Review
The live iteration-4 architecture already provides the hard part: stage-level orchestration in `src/preenrich/stage_registry.py`, `src/preenrich/stage_worker.py`, `src/preenrich/root_enqueuer.py`, and `src/preenrich/sweepers.py`. The current stages are:

- `jd_structure`
- `jd_extraction`
- `ai_classification`
- `pain_points`
- `annotations`
- `persona`
- `company_research`
- `role_research`

What already aligns with v2:
- stage-level DAG and `cv_ready`
- per-stage provider/model/prompt-version tracking in `src/preenrich/types.py`
- detail page still reading one job document from `frontend/app.py`
- application URL already exists as a top-level job field
- annotations are already a separate preenrich concern

What diverges from v2:
- current outputs are legacy top-level fields, not the six blueprint collections
- current `jd_extraction` is not deterministic-first with LLM-as-judge
- current `ai_classification` is AI-relevance detection, not canonical role taxonomy
- current `pain_points`, `company_research`, and `role_research` are not the Stage 1 artifact model
- current UI is not blueprint-aware
- current research stages still follow legacy company/role research shapes

### 2.1 Observed quality gap vs runner-era content surfaces
The stage-DAG/control-plane migration is not sufficient on its own. The content layer must also reach parity with the richer runner/service outputs that existing operators are implicitly comparing against. The following gaps were observed while running a real 4.1 canary job and comparing the resulting snapshot against the older runner-era surfaces:

- The current detail page can render a hybrid of legacy extracted-JD UI and new blueprint-derived research/guidance. This is structurally valid for migration, but it is not content-parity-valid and can make the same job look internally inconsistent.
- The current 4.1 artifact graph is structurally correct but semantically thinner than the runner-era extraction + research stack. A `cv_ready` job can therefore still produce a visibly weaker job detail page.
- Several 4.1 prompt builders already exist, but multiple stages still use heuristics or deterministic assembly instead of actually invoking the intended prompt contract. This creates “prompt-defined but not prompt-executed” behavior.

These gaps are not cosmetic. They are tracked here as content-parity requirements for the remainder of 4.1 and any follow-on hardening work.

## 3. Gap Analysis: v2 vs Iteration 4
| v2 stage | 4.1 decision |
|---|---|
| `S0` capability gate | Fold into worker/stage context setup, not its own queued stage |
| `S1a` deterministic extraction | Fold into new `jd_facts` stage |
| `S1b` `P-jd-judge` | Fold into new `jd_facts` stage |
| `S2` `P-classify` | Replace `ai_classification` with new `classification` stage |
| `S3` `P-role-model` | Replace `pain_points` with new `job_inference` stage |
| `S3b` `P-hypotheses` | Add new `job_hypotheses` stage |
| `S4` `P-research` | Replace `company_research` with new `research_enrichment` stage |
| `S4b` `P-application-url` | Add new `application_surface` stage |
| `S5` `P-cv-guidelines` | Add new `cv_guidelines` stage |
| `S6` assembly | Replace `role_research` with new `blueprint_assembly` stage |

Current-stage disposition:
- `jd_structure`: preserve
- `jd_extraction`: retire and replace with `jd_facts`
- `ai_classification`: retire. Role taxonomy moves to new `classification` stage. AI-relevance fields (`is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification`) are produced as a sub-output of the new `classification` stage and mirrored into the compat projection (see §5.1). They are NOT produced by `blueprint_assembly` — `classification` is their canonical new home.
- `pain_points`: retire as a primary stage; keep its output only as a compatibility projection (populated from `job_inference` fields via `blueprint_assembly`)
- `annotations`: preserve with a prerequisite change. Current registry has `annotations.prerequisites=("pain_points",)`. In 4.1, annotations depends on `jd_structure` only. This is a deliberate contract break; the annotations stage implementation must be audited to confirm it does not read any `pain_points.*` output fields today. If it does, the read must be migrated to the equivalent field on `job_inference` before the prereq is flipped.
- `persona`: preserve temporarily as `persona_compat`. It is `required_for_cv_ready=True` only while `PREENRICH_PERSONA_COMPAT_ENABLED=true`; removing that flag is the phase-6 terminal action that finally un-pins `cv_ready` from a compatibility-only stage.
- `company_research`: retire and replace with `research_enrichment`. The compat projection field `company_research` is populated by `blueprint_assembly` from `research_enrichment.company_profile` and related blueprint fields.
- `role_research`: retire as a primary stage. The compat projection field `role_research` is populated by `blueprint_assembly` from `job_inference.semantic_role_model` and `cv_guidelines` summaries — `blueprint_assembly` is NOT a semantic replacement for role research; it is a deterministic aggregator that happens to emit the legacy field.

### 3.1 Runner-parity content gaps that must be addressed
The current 4.1 codebase still trails the runner/service implementation in specific content-richness areas. These must be treated as explicit gaps, not as acceptable migration degradation.

#### `jd_facts` is too thin
- The runner-era JD extraction prompt in `src/layer1_4/prompts.py` produces materially richer structure than the current 4.1 `jd_facts` stage.
- Runner-era extraction includes:
  - explicit role category
  - seniority level
  - competency weights
  - responsibilities
  - qualifications
  - nice-to-haves
  - technical skills
  - soft skills
  - top keywords
  - implied pain points
  - success metrics
  - industry background
  - years of experience
  - education requirements
  - ideal candidate profile with archetype, traits, experience profile, and culture signals
- Current 4.1 `jd_facts` primarily performs deterministic field collection plus an “LLM judge additions” path. That is not enough to match the older extraction surface.
- Requirement: `jd_facts` must evolve from “field collector” to “full structured JD intelligence” while keeping deterministic-first semantics and explicit provenance.

#### `classification` prompt exists but is not the real execution path
- `P-classify` is defined, but the current `classification` stage largely uses helper heuristics and title-family mapping rather than the taxonomy-driven prompt path.
- Requirement: `classification` must actually execute the canonical taxonomy-based classification contract, persist `taxonomy_version`, carry evidence/rationale, and expose meaningful ambiguity handling instead of only heuristic title-family assignment.

#### 4.1 has no runner-grade pain-point analysis stage today
- The runner-era `PainPointMiner` in `src/layer2/pain_point_miner.py` is one of the richest prompt surfaces in the old stack:
  - domain-aware few-shot examples
  - annotation-aware prioritization
  - confidence framing
  - stronger business-problem inference
- Current 4.1 does not have a dedicated pain-points artifact stage. `blueprint_assembly` derives `pain_points`, `strategic_needs`, `risks_if_unfilled`, and part of `success_metrics` from thinner upstream fields.
- Requirement: restore explicit pain-point intelligence in the 4.1 artifact model, either via a dedicated stage or by materially strengthening `job_inference`; assembly-time synthesis alone is not sufficient for runner parity.

#### `research_enrichment` is currently a thin wrapper, not a true research engine
- Runner-era company research in `src/layer3/company_researcher.py` includes:
  - multi-source research
  - signal extraction
  - company-type classification
  - source attribution
  - reasoning/confidence structure
  - STAR-aware variants
- Current 4.1 `research_enrichment` mostly:
  - copies any existing `company_research`
  - emits capability flags
  - falls back to “Public research not available...”
  - does not actually execute `P-research` as a substantive synthesis path
- Requirement: `research_enrichment` must become the true company/role research artifact, not just a status container. Reusing the old researcher and normalizing into the new schema is acceptable; leaving it thin is not.

#### `job_inference` is not a full replacement for runner-era role research yet
- Runner-era role research in `src/layer3/role_researcher.py` produces:
  - role summary
  - business-impact bullets
  - explicit `why_now`
  - ties to company signals
- Current 4.1 `job_inference` produces a lighter semantic model and `blueprint_assembly` then converts that into a shallow `role_research` compatibility view.
- Requirement: 4.1 must recover runner-grade role understanding, either by restoring an explicit role-research-grade analysis inside the new artifact model or by materially enriching `job_inference` so the compatibility projection is not a thin derived summary.

#### `application_surface` is structurally correct but operationally thin
- The current `application_surface` stage mostly normalizes URLs and infers portal family heuristically.
- The repo already has richer surfaces for apply URL resolution and form friction:
  - `n8n/skills/url-resolver/scripts/resolver.py`
  - `src/services/form_scraper_service.py`
- Requirement: ambiguous or weak application surfaces should have a richer resolution path available. Deterministic-first is correct, but deterministic-only is not enough for parity with the existing resolver/form-discovery capability.

#### `cv_guidelines` is constrained by thin upstream artifacts and currently underuses its prompt surface
- `P-cv-guidelines` is defined, but the current stage mostly assembles bullets from already-thin keywords and must-haves.
- Requirement: `cv_guidelines` must be driven by richer upstream artifacts and should execute its schema-first prompt path rather than functioning mostly as a formatter around sparse inputs.

#### `persona_compat` is acceptable as compatibility, but not as a richness substitute
- Keeping `persona_compat` is architecturally correct for migration.
- It is not, by itself, enough to recreate the runner’s combined “annotations + persona + research + pain points” richness on the job detail page.
- Requirement: persona compatibility remains temporary and should not be used as a reason to leave the upstream blueprint artifacts semantically weak.

#### Detail-page parity must be measured against content quality, not just successful rendering
- A job that reaches `cv_ready` with a valid blueprint snapshot can still render a materially weaker page than the runner-era result if the underlying artifacts are too thin.
- Requirement: 4.1 acceptance must include content-parity review for representative jobs, not only DAG completion, snapshot presence, and UI rendering success.

## 4. Canonical Iteration-4.1 DAG
Iteration 4.1 should move from 8 stages to 11 stages. The orchestration framework stays the same; the registry changes.

Canonical 4.1 stages:
- `jd_structure`
- `jd_facts`
- `classification`
- `research_enrichment`
- `application_surface`
- `job_inference`
- `job_hypotheses`
- `annotations`
- `persona_compat`
- `cv_guidelines`
- `blueprint_assembly`

Dependency shape:
- `jd_structure` starts first
- `annotations` depends on `jd_structure` (changed from current `pain_points`; see §3)
- `persona_compat` depends on `annotations`
- `jd_facts` depends on `jd_structure`
- `classification` depends on `jd_facts`
- `research_enrichment` depends on `jd_facts`
- `application_surface` depends on `jd_facts`
- `job_inference` depends on `jd_facts`, `classification`, `research_enrichment`, `application_surface`
- `job_hypotheses` depends on `jd_facts`, `classification`, `research_enrichment`, `application_surface`
- `cv_guidelines` depends on `jd_facts`, `job_inference`, `research_enrichment`
- `blueprint_assembly` depends on `jd_facts`, `job_inference`, `cv_guidelines`, `application_surface`, `annotations`, `persona_compat`; it reads `job_hypotheses` by reference only

`annotations` remains because the repo still depends on `jd_annotations` for the annotation UI and downstream CV/outreach logic. `persona_compat` also remains for the same reason, but it is no longer a canonical Stage 1 artifact.

`cv_ready` in 4.1 should require:
- `jd_structure`
- `jd_facts`
- `classification`
- `application_surface`
- `job_inference`
- `annotations`
- `persona_compat`
- `cv_guidelines`
- `blueprint_assembly`

`research_enrichment` is required only when research is enabled and company identity is resolvable. `job_hypotheses` is not `cv_ready`-gating.

`application_surface` is `required_for_cv_ready=True`. An unresolved application URL is NOT a failure — the stage reaches terminal state `completed` with a structured payload carrying `status="unresolved"`. This is enforced at registry level (the stage never emits `failed`/`deadletter` for unresolvable URLs) so the iteration-4 `cv_ready` CAS continues to work unchanged.

**Fan-in correctness.** `job_inference` (4 prereqs), `job_hypotheses` (4 prereqs), `cv_guidelines` (3 prereqs), and `blueprint_assembly` (6 prereqs) introduce real fan-in. The current `src/preenrich/stage_worker.py::_missing_prerequisites` already iterates every prereq in the registry tuple and checks `input_snapshot_id` equality per prereq, so fan-in is supported by the existing control plane. 4.1 does NOT require changes to the worker prereq gate; it DOES require new tests (see §12) that exercise partial-completion scenarios for the new fan-in stages.

**Required-set migration for in-flight jobs.** The 4.1 required-stage set differs from iter-4's. Jobs already in `lifecycle="preenriching"` under the iter-4 required set will not satisfy the new `cv_ready` CAS. Handle this with a `required_set_version` bump on the registry, propagated through `input_snapshot_id` composition, so the `preenrich-snapshot-invalidator` cancels stale work items and the root-enqueuer re-enqueues the new stage set. No destructive Mongo edits. The phase plan (§11) must not widen the canary until this invalidator pass has drained the pre-cutover in-flight population to zero.

## 5. Data Model And Storage Plan
Stage 1 source-of-truth artifacts remain collection-backed:
- `jd_facts`
- `job_inference`
- `job_hypotheses`
- `research_enrichment`
- `cv_guidelines`
- `job_blueprint`

### 5.1 Required indexes and unique keys

Adopted verbatim from `plans/brainstorming-new-cv-v2.md` §6; none of these were specified in the earlier 4.1 draft.

- `jd_facts`: unique on `(job_id, jd_text_hash, extractor_version, judge_prompt_version)`
- `job_inference`: unique on `(jd_facts_id, research_enrichment_id, prompt_version, taxonomy_version)`
- `job_hypotheses`: unique on `(jd_facts_id, research_enrichment_id, prompt_version, taxonomy_version)`
- `research_enrichment`: unique on `(jd_facts_id, research_input_hash, prompt_version)`
- `cv_guidelines`: unique on `(jd_facts_id, job_inference_id, research_enrichment_id, prompt_version)`
- `job_blueprint`: unique on `(job_id, blueprint_version)`
- Non-unique indexes on every `*_id` reference field used by `blueprint_assembly` and review UIs.
- `level-2`: `{ "pre_enrichment.job_blueprint_refs.job_blueprint_id": 1 }`, `{ "pre_enrichment.job_blueprint_status": 1, "pre_enrichment.job_blueprint_updated_at": 1 }`.

Indexes must ship in the same deploy slice as the code that reads them. `infra/scripts/verify-preenrich-cutover.sh` (extended in §13) must fail if any of the above is missing.

### 5.2 Projections on `level-2`

`level-2` must also get a read-optimized projection:
- `pre_enrichment.job_blueprint_refs`
- `pre_enrichment.job_blueprint_snapshot`
- `pre_enrichment.job_blueprint_version`
- `pre_enrichment.job_blueprint_status`
- `pre_enrichment.job_blueprint_updated_at`

Source of truth vs mirror:
- collections are authoritative
- `level-2` snapshot is denormalized for UI and downstream compatibility
- `job_hypotheses` never denormalizes into the job document except for an ID reference in `job_blueprint_refs`

### 5.3 Compatibility projections written by `blueprint_assembly`

Each projection names its canonical source collection/field so implementers do not guess:

- `application_url` ← `application_surface` stage output (which is persisted into `job_inference.application_surface` and carried through `job_blueprint.snapshot.application_surface`)
- `is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification` ← written directly by the new `classification` stage (NOT by `blueprint_assembly`). `blueprint_assembly` only mirrors them into the `job_blueprint_snapshot` for readers that consume the snapshot.
- `pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics` ← derived from `job_inference.semantic_role_model.likely_screening_themes`, `job_inference.qualifications.implicit[]`, `cv_guidelines.challenges_guidance`
- `company_research` ← `research_enrichment.company_profile` + `research_enrichment.sources[]`
- `role_research` ← `job_inference.semantic_role_model` + `cv_guidelines` summaries
- `jd_annotations.synthesized_persona` ← produced by the temporary `persona_compat` stage only, not by `blueprint_assembly`

### 5.4 Invalidation rules

- `jd_facts` invalidates on JD hash or extractor/judge version change
- `classification` invalidates on `jd_facts` or taxonomy version change
- `research_enrichment` invalidates on `jd_facts`, research depth, fetch-input hash, or prompt version change
- `application_surface` invalidates on URL inputs, resolver rules, or prompt version change
- `job_inference` invalidates on `jd_facts`, `classification`, `research_enrichment`, `application_surface`, or prompt version change
- `job_hypotheses` invalidates on the same inputs
- `cv_guidelines` invalidates on `jd_facts`, `job_inference`, `research_enrichment`, or prompt version change
- `job_blueprint` rebuilds whenever any referenced artifact changes

### 5.5 Taxonomy invalidation mechanism

A `data/job_archetypes.yaml` edit is not content drift — it is a global invalidation trigger. Mechanism:

- `taxonomy_version` (from the YAML `version:` field) is added to `input_snapshot_id` composition for 4.1. This is a deliberate change to iter-4's snapshot contract and must be documented in `docs/current/architecture.md` as part of the cutover.
- On taxonomy version bump, `preenrich-snapshot-invalidator` computes the new snapshot for every `lifecycle="preenriching"` or `lifecycle="cv_ready"` doc, cancels any `work_items` at the old snapshot (per iter-4 §6.6), and the root-enqueuer re-enqueues `classification` onward for docs whose `classification.input_snapshot_id` is stale. `jd_structure`, `jd_facts`, and `annotations` are NOT re-run — their outputs are taxonomy-independent.
- A dedicated `scripts/invalidate_on_taxonomy_bump.py` one-shot runs at deploy time to force the re-scan; the steady-state invalidator timer catches any stragglers.

## 6. Detail Page Exposure Plan
The detail page should keep reading one serialized job document from `frontend/app.py`. It should not query blueprint collections directly in 4.1.

`frontend/templates/job_detail.html` currently has 32 references to `company_research|role_research|pain_points`, plus partials under `frontend/templates/partials/job_detail/` (`_interview_prep_panel.html`, `_jd_annotation_panel.html`, `_outcome_tracker.html`, `_pipeline_progress.html`, `_add_contacts_modal.html`, `_cv_editor_panel.html`, `_annotation_list.html`, `_annotation_popover.html`). The migration is NOT file-level: implementers must produce a field-by-field mapping table before Phase 4 begins, covering every legacy read and its snapshot successor (plus declared fallback). That mapping becomes an artifact checked into `docs/current/` and reviewed as part of Phase 4.

UI read strategy:
- read `pre_enrichment.job_blueprint_snapshot` first
- fall back to legacy top-level fields during migration
- keep `job_blueprint_refs` available for debug links and future APIs

Job detail page changes:
- current company research section becomes snapshot-first, using blueprint-derived company model and research notes
- current role research section becomes snapshot-first, using blueprint-derived role model and CV-guideline summary
- current application URL surface becomes snapshot-first, showing `application_url`, `portal_family`, `is_direct_apply`, and friction signals
- add a new "Job Blueprint" section showing:
  - normalized role classification
  - must-have and nice-to-have summary
  - key ATS keywords
  - title guidance
  - identity guidance
  - bullet-theme guidance
  - cover-letter expectations

Hypothesis isolation:
- no `job_hypotheses` content in `job_blueprint_snapshot`
- no `job_hypotheses` content in the default detail page
- if inspectability is needed, add a gated operator/debug endpoint later that reads the collection by reference; do not denormalize it
- the §12 test `no-hypothesis-leak validation for job_blueprint_snapshot` MUST be implemented as a snapshot-schema allow-list (snapshot keys must appear in a declared schema), NOT as a deny-list over known hypothesis field names. A deny-list will not catch new hypothesis dimensions added in future iterations.
- every prompt builder (not just `P-cv-guidelines`) must pass a prompt-contract test that fails if its assembled input references the `job_hypotheses` collection or field paths.

## 7. Prompt And Stage Catalog
4.1 prompt catalog:
- `P-jd-judge` inside `jd_facts`
- `P-classify` inside `classification`
- `P-research` inside `research_enrichment`
- `P-application-url` inside `application_surface`
- `P-role-model` inside `job_inference`
- `P-hypotheses` inside `job_hypotheses`
- `P-cv-guidelines` inside `cv_guidelines`

Current prompt disposition:
- current `jd_extraction` prompt is superseded by deterministic-first `jd_facts`
- current `ai_classification` prompt is superseded by `P-classify`
- current `pain_points` prompt is retired as a primary artifact producer
- current `company_research` and `role_research` prompts are retired as primary artifact producers
- current `persona` prompt stays only for `persona_compat`

Prompt rules:
- every new prompt must be schema-first and JSON-only
- deterministic-first stages must reject silent overwrite by LLM
- `P-cv-guidelines` must not read `job_hypotheses`
- `P-hypotheses` outputs must stay in their own collection only
- `P-classify` must load taxonomy from `data/job_archetypes.yaml`

## 8. Model Routing Plan
Recommended 4.1 model mapping under current repo constraints:

| Stage | Model |
|---|---|
| `jd_structure` | none |
| `jd_facts` deterministic pass | none |
| `jd_facts` judge pass / `P-jd-judge` | `gpt-5.4-mini` |
| `classification` / `P-classify` | `gpt-5.4-mini` |
| `research_enrichment` fetch | none or existing fetch transport |
| `research_enrichment` synthesis / `P-research` | `gpt-5.4-mini` |
| `application_surface` deterministic resolution | none |
| `application_surface` ambiguity resolver / `P-application-url` | `gpt-5.4-mini` |
| `job_inference` / `P-role-model` | `gpt-5.4` |
| `job_hypotheses` / `P-hypotheses` | `gpt-5.4-mini` |
| `annotations` | embedding / priors only |
| `persona_compat` | keep `gpt-5.4` in 4.1 |
| `cv_guidelines` / `P-cv-guidelines` | `gpt-5.4` |
| `blueprint_assembly` | none |

Quality vs cost:
- `gpt-5.4-mini` is correct for bounded extraction, classification, URL resolution, and research-note synthesis
- `gpt-5.4` is justified only for the two high-value synthesis stages: `job_inference` and `cv_guidelines`
- `persona_compat` stays at current quality to avoid destabilizing downstream CV behavior during migration

Routing configuration:
- extend `src/preenrich/types.py` with defaults for the new stage names
- keep env overrides per stage
- extend `scripts/preenrich_model_preflight.py` to fail when a new stage has no provider/model mapping

## 9. Taxonomy Integration Plan
`data/job_archetypes.yaml` becomes the single taxonomy source of truth for:
- `primary_role_category`
- `secondary_role_categories`
- `search_profiles`
- `selector_profiles`
- `tone_family`
- `ideal_candidate_archetype`
- `portal_family`

4.1 rules:
- `P-classify` reads this taxonomy, not ad hoc regex families
- selector/search codepaths keep their current profile names but map through this file
- stage artifacts persist `taxonomy_version`
- any taxonomy change invalidates `classification`, `job_inference`, `job_hypotheses`, `cv_guidelines`, and `job_blueprint`

Role taxonomy and portal taxonomy must stay separate. `portal_family` belongs to `application_surface`, not role identity.

## 10. Application Surface Plan
4.1 should formalize `application_surface` as a first-class stage built on the current repo status quo.

Deterministic work:
- normalize `jobUrl`, `job_url`, `application_url`
- detect ATS family from URL/domain patterns
- reuse the known portal families from `.claude/skills/apply-jobs/modules/portal-detection.md`
- reuse current resolver behavior from `n8n/skills/url-resolver`
- mirror final `application_url` back to the job doc for compatibility

LLM-assisted work:
- only when deterministic resolution finds multiple candidates or ambiguous redirects
- use `P-application-url` to select the best direct-apply URL or classify ambiguity
- never use an LLM for first-pass URL discovery if deterministic resolution already succeeded

Optional work:
- login-wall likelihood
- multi-step likelihood
- closed-posting signal
- apply-surface notes for detail page display

`application_surface` is required for 4.1, but unresolved URL outcomes should complete with a structured "unresolved" status rather than blocking `cv_ready`.

## 10.1 Open question: research transport

Phase 2 (shadow writes for `research_enrichment`) MUST NOT start until one decision is closed: whether existing fetch+synthesis infrastructure (currently used by `company_research`) produces a `research_notes` payload shaped compatibly with brainstorm §6.4, or whether a new transport wrapper is needed for Codex web access. This is listed as an open question in §14 and is the gate on beginning real `research_enrichment` implementation.

## 11. Migration / Compatibility Plan

### 11.0 Feature flag invariants

The following combinations are invalid and must be enforced by a startup health probe (same pattern as iter-4 §12.2):

- `PREENRICH_BLUEPRINT_UI_READ_ENABLED=true` while `PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED=false` — UI would read stale or missing snapshots.
- `PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED=false` while `PREENRICH_BLUEPRINT_UI_READ_ENABLED=false` — no reader has data.
- `PREENRICH_BLUEPRINT_ENABLED=true` while the new registry entries are not loaded — the root-enqueuer would create `work_items` that no worker allowlist accepts.
- Legacy `shadow_mode` (iter-4, `PREENRICH_SHADOW_MODE`) and `PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED=true` together — two shadow layers writing overlapping `pre_enrichment.*` fields. At most one shadow layer is active per deploy.

Phase 1:
- add the six blueprint collections and indexes
- add new stage names behind `PREENRICH_BLUEPRINT_ENABLED=false`
- keep current 8-stage DAG as production path

Phase 2:
- run new blueprint stages in shadow for allowlisted jobs
- write collections only
- do not read snapshot in UI yet
- keep current legacy stages and fields live

Phase 3:
- enable `blueprint_assembly` to write:
  - `pre_enrichment.job_blueprint_refs`
  - `pre_enrichment.job_blueprint_snapshot`
  - legacy compatibility projections
- keep UI and downstream reading legacy fields

Phase 4:
- make `job_detail.html` snapshot-first with legacy fallback
- make CV runner precondition require `pre_enrichment.job_blueprint_status=ready`
- keep compatibility fields populated

Phase 5:
- stop generating legacy `pain_points`, `company_research`, and `role_research` as primary stages
- keep those fields as projections only
- preserve `annotations` and `persona_compat`

Phase 6:
- when downstream CV stages stop reading `jd_annotations.synthesized_persona`, flip `PREENRICH_PERSONA_COMPAT_ENABLED=false` and remove `persona_compat` from the `required_for_cv_ready` set. This is the terminal action that un-pins `cv_ready` from a compatibility-only stage.

### 11.1 In-flight job migration at required-set change

Between Phase 3 and Phase 4, the `required_for_cv_ready` set flips from the iter-4 shape to the 4.1 shape. The required-set version is part of `input_snapshot_id` (§4), so:

1. Deploy the 4.1 registry behind the feature flag.
2. Run `scripts/invalidate_on_taxonomy_bump.py` with `--reason=required_set_version_bump` (same mechanism, different trigger). The invalidator cancels stale `work_items`, writes the new `input_snapshot_id`, and the root-enqueuer picks up the new stages.
3. Do NOT widen the canary past 1 job until the dashboard shows zero `lifecycle="preenriching"` docs at the old `input_snapshot_id`.
4. Jobs already at `lifecycle="cv_ready"` under the iter-4 set are left alone; they are downstream-ready and re-running them produces no new value. If a specific job must be re-blueprinted, operator re-selects it and it flows through the 4.1 DAG naturally.

Rollback:
- disable `PREENRICH_BLUEPRINT_ENABLED`
- stop new stage workers
- keep legacy compatibility fields untouched
- return UI to legacy reads only
- leave collections in place for inspection

## 12. Test Plan
Unit tests to add:
- `test_stage_jd_facts.py`
- `test_stage_classification.py` — MUST assert that the new stage emits the AI-relevance fields (`is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification`) in addition to role taxonomy fields. This protects the downstream selector/scout ranking that currently depends on the iter-4 `ai_classification` stage.
- `test_stage_research_enrichment.py`
- `test_stage_application_surface.py` — MUST assert that an unresolved URL produces `completed` status with `payload.status="unresolved"`, not `failed` or `deadletter`.
- `test_stage_job_inference.py`
- `test_stage_job_hypotheses.py`
- `test_stage_cv_guidelines.py`
- `test_stage_blueprint_assembly.py`

Fan-in and DAG-shape tests (new in 4.1):
- `test_fan_in_job_inference.py` — 4-prereq gate: only 3 of 4 complete → stage stays `pending`; all 4 complete at the same snapshot → stage is claimable.
- `test_fan_in_blueprint_assembly.py` — 6-prereq gate with one prereq at a stale snapshot; assert the claim is rejected with `prerequisite_not_ready` and reason includes snapshot mismatch.
- `test_required_set_version_migration.py` — a job at `lifecycle="preenriching"` under the iter-4 required set is re-enqueued correctly after the 4.1 registry is loaded; no doc is stranded.
- `test_taxonomy_invalidation.py` — bumping `data/job_archetypes.yaml` `version:` recomputes `input_snapshot_id`, cancels stale work, re-enqueues `classification` onward, and does NOT re-run `jd_structure`/`jd_facts`/`annotations`.
- `test_application_surface_required_but_unresolvable.py` — `cv_ready` CAS succeeds even when application_surface completed with `status="unresolved"`.

Schema tests to add:
- collection schema validation for all six blueprint artifacts
- evidence coverage validation for `cv_guidelines`
- no-hypothesis-leak validation for `job_blueprint_snapshot`

Prompt contract tests to add:
- assert every prompt builder emits JSON-only instructions
- assert required schema keys exist in the prompt text
- assert EVERY prompt builder (not only `P-cv-guidelines`) rejects inputs that reference `job_hypotheses` — implemented as a shared test helper so new prompts added later inherit the guard
- assert `P-classify` references the taxonomy version
- assert `job_blueprint_snapshot` schema is an allow-list: snapshot keys must match a declared schema, and adding an unknown top-level key fails CI

DAG and registry tests to update:
- `tests/unit/preenrich/test_stage_registry.py`
- `tests/unit/preenrich/test_dag.py`
- `tests/unit/preenrich/test_sweepers.py`
- `tests/unit/preenrich/test_root_enqueuer.py`

UI tests to add/update:
- `frontend/tests/test_job_detail_blueprint_snapshot.py`
- snapshot-first rendering of company/role/application sections
- fallback rendering when snapshot absent
- hypotheses never rendered

Migration tests:
- legacy-only job
- dual-write job
- snapshot-first job
- rollback to legacy-only mode

Prompt correctness verification:
- capture rendered prompt strings in unit tests
- store golden fixtures for each new prompt family
- verify `prompt_version`, `model_used`, and `provider_used` are persisted in stage state

Model routing verification:
- extend `scripts/preenrich_model_preflight.py`
- test env overrides for every new stage
- fail if a required stage has no configured model/provider

Canary verification:
- one allowlisted job completes to `cv_ready`
- six blueprint collections populated
- snapshot written to `level-2`
- detail page shows blueprint-derived sections
- legacy compatibility fields still present

## 13. VPS Rollout Plan
`infra/systemd/scout-preenrich-worker@.service` stays as the worker template. Add new per-stage instances for:
- `jd_facts`
- `classification`
- `research_enrichment`
- `application_surface`
- `job_inference`
- `job_hypotheses`
- `cv_guidelines`
- `blueprint_assembly`

The existing `scout-preenrich-worker@persona.service` stays as-is and runs the `persona_compat` stage (see §13 decision above). Legacy instances for `jd_extraction`, `ai_classification`, `pain_points`, `company_research`, and `role_research` are stopped (`systemctl disable`) at Phase 5; they are NOT removed from infra assets until one stable release past full 4.1 cutover, so rollback §13 can re-enable them without a redeploy.

Infra changes:
- extend `infra/scripts/verify-preenrich-cutover.sh` to additionally check:
  1. All six blueprint collections exist with the unique indexes from §5.1.
  2. `level-2` carries `pre_enrichment.job_blueprint_refs`, `_snapshot`, `_version`, `_status`, `_updated_at` indexes from §5.1.
  3. All 4.1 systemd units (for the 8 new/renamed per-stage instances) are `active`.
  4. No `lifecycle="preenriching"` doc exists at an `input_snapshot_id` that predates the current `taxonomy_version` + `required_set_version`.
  5. No `job_blueprint_snapshot` in any doc contains a key outside the declared allow-list schema.
  6. Feature-flag mutual-exclusion invariants from §11.0 hold in the live environment.
  7. At least one `cv_ready` has been written by the 4.1 DAG in the last 24h (post-canary).
- keep current root enqueuer and sweepers; update required-stage logic (driven by registry `required_for_cv_ready`, so only registry changes)
- decide operationally whether to rename `persona` → `persona_compat` systemd unit or keep the unit name and rename conceptually; pick one in this plan — no "optional" rename. Decision: KEEP systemd unit name `scout-preenrich-worker@persona.service` to avoid a cutover-time unit rename. `persona_compat` is the stage-name in the registry and env keys `PREENRICH_MODEL_PERSONA_COMPAT` / `PREENRICH_PROVIDER_PERSONA_COMPAT` are the stable config surface.
- add env flags:
  - `PREENRICH_BLUEPRINT_ENABLED`
  - `PREENRICH_BLUEPRINT_SNAPSHOT_WRITE_ENABLED`
  - `PREENRICH_BLUEPRINT_UI_READ_ENABLED`
  - `PREENRICH_BLUEPRINT_COMPAT_PROJECTIONS_ENABLED`
  - `PREENRICH_PERSONA_COMPAT_ENABLED`
  - `PREENRICH_APPLICATION_SURFACE_ENABLED`

Canary strategy:
- enable new stages for an allowlist of one job
- verify collection writes, snapshot writes, and detail-page rendering
- expand to 10%
- expand to 100%
- only then retire legacy content stages

Cutover sequence:
- deploy code with new registry and new stage workers disabled
- run index migration
- enable shadow blueprint writes
- enable snapshot projection
- enable snapshot-first UI
- switch required `cv_ready` stage set
- disable legacy content-stage execution
- keep compatibility projections on

Rollback sequence:
- disable snapshot-first UI
- disable blueprint stages
- re-enable legacy content stages if needed
- keep compatibility fields as source for UI and downstream CV paths

## 14. Risks And Open Questions
Real risks:
- `job_hypotheses` leakage through accidental snapshot projection or prompt assembly
- detail page breakage if snapshot-first logic has no fallback
- downstream CV code still reading `company_research`, `role_research`, `pain_points`, or `jd_annotations.synthesized_persona`
- research transport mismatch if 4.1 assumes native Codex web access instead of fetch-plus-synthesis
- taxonomy drift if `P-classify` is updated without versioned invalidation
- in-flight jobs stranded at required-set change if §11.1 migration is skipped
- selector/scout regression if the new `classification` stage fails to emit the AI-relevance fields the ranking surfaces depend on (see §5.3)
- future prompt builders adding hypotheses as "context" silently — mitigated only by the shared prompt-contract test (§12)

Open questions to close before implementation:
- whether `persona_compat` can be removed in 4.1 or must survive one more iteration
- whether existing fetch infrastructure for company research is sufficient for `research_enrichment` without Claude-specific assumptions
- which exact fields in current CV runner code are still hard dependencies versus safe compatibility projections

## 15. Final Recommended Iteration-4.1 Plan
Decision summary:
- keep the iteration-4 DAG control plane
- replace the legacy content stages with blueprint-native stages
- expand from 8 stages to 11 stages
- preserve `jd_structure`, `annotations`, and temporary `persona_compat`
- make the six blueprint collections the source of truth
- write `job_blueprint_snapshot` and `job_blueprint_refs` back onto `level-2`
- make the detail page snapshot-first with legacy fallback
- keep `job_hypotheses` out of the snapshot and out of default UI
- mirror compatibility fields until downstream CV consumers are migrated
- gate `cv_ready` on blueprint readiness, not legacy research-stage names
- use `gpt-5.4-mini` for bounded structured steps and `gpt-5.4` only for `job_inference`, `cv_guidelines`, and temporary `persona_compat`

This is the correct 4.1 shape because it preserves the operational gains of iteration 4, lands the Stage 1 blueprint architecture in production, keeps the current detail page and downstream CV pipeline alive, and creates a clean cutover path away from the legacy preenrich content model.
