# Step 6 Implementation Contract

## Purpose

Step 6 converts each Step 5 category blueprint into a pre-generation baseline that answers three separate questions:

1. How much category-relevant evidence is already curated in `data/master-cv/*`?
2. What high-value evidence likely exists upstream but is not yet curated?
3. How well does the current master-CV representation surface the curated evidence?

This step is not a CV writer.
It is a scoring and diagnosis layer that produces:

- a category baseline report
- a curation queue
- a master-CV upgrade queue
- longitudinally comparable JSON outputs

## Scope

The Step 6 implementation should live in:

- `scripts/eval_step6_baselines.py`

It should read from:

- `data/eval/blueprints/{category}_blueprint.json`
- `data/master-cv/roles/*.md`
- `data/master-cv/projects/*.md`
- `data/master-cv/projects/*_skills.json`
- `data/master-cv/role_metadata.json`
- `data/master-cv/role_skills_taxonomy.json`
- a bounded set of vetted upstream evidence files from `docs/current/` and `docs/archive/`

It should write to:

- `data/eval/baselines/{category}_baseline.json`
- `data/eval/baselines/{category}_baseline.md`
- `data/eval/baselines/index.md`
- `data/eval/baselines/evidence_map.json`
- `data/eval/baselines/debug/{category}/{timestamp}/...`

## Non-Goals

Step 6 must not:

- generate a new CV
- rewrite the curated evidence store directly
- treat `data/master-cv/*` as complete truth
- treat every document in `docs/archive/` as claimable evidence
- promote unsupported claims just because they appear in planning notes

## Evidence Hierarchy

Step 6 must operate on this strict hierarchy:

1. **Curated evidence store**
   - `data/master-cv/*`
   - reusable pipeline evidence
   - highest trust for downstream claimability
2. **Upstream vetted evidence**
   - bounded, provenance-aware evidence outside `data/master-cv/*`
   - useful for identifying curation opportunities
   - not automatically reusable by downstream generation until curated
3. **Representation layer**
   - current master CV and related representation artifacts
   - used only to judge surfacing, prioritization, and framing quality

## Required Gap Taxonomy

Every important weak or missing signal must be classified into exactly one bucket:

- `supported_and_curated`
- `supported_upstream_pending_curation`
- `curated_but_underrepresented`
- `unsupported_or_unsafe`

These labels are the stable contract. Do not invent synonyms in JSON output.

## Baseline Scoring Model

Step 6 must return a `0.0-10.0` combined score using these weighted components:

- `candidate_evidence_coverage_score`: 30
- `evidence_curation_completeness_score`: 15
- `master_cv_representation_quality_score`: 25
- `ai_architecture_fit_score`: 15
- `leadership_scope_fit_score`: 10
- `impact_proof_strength_score`: 5

Combined score formula:

```text
combined_fit_score =
  0.30 * candidate_evidence_coverage_score +
  0.15 * evidence_curation_completeness_score +
  0.25 * master_cv_representation_quality_score +
  0.15 * ai_architecture_fit_score +
  0.10 * leadership_scope_fit_score +
  0.05 * impact_proof_strength_score
```

Readiness tiers:

- `STRONG`: `>= 8.5`
- `GOOD`: `7.0-8.49`
- `STRETCH`: `5.5-6.99`
- `LOW`: `< 5.5`

## Implementation Shape

The script should mirror the Step 5 architecture:

- compact summary builders
- JSON-first LLM call
- deterministic validation
- deterministic Markdown rendering
- per-attempt debug artifacts

### Required top-level functions

The implementation should expose functions with responsibilities equivalent to:

```python
def load_blueprint(category_id: str) -> dict: ...
def load_curated_evidence() -> dict: ...
def load_upstream_evidence_inventory() -> dict: ...
def load_master_cv_representation() -> dict: ...

def build_curated_evidence_summary(
    blueprint: dict,
    curated_evidence: dict,
) -> dict: ...

def build_upstream_evidence_summary(
    blueprint: dict,
    upstream_inventory: dict,
) -> dict: ...

def build_master_cv_representation_summary(
    blueprint: dict,
    curated_evidence: dict,
    representation: dict,
) -> dict: ...

def build_evidence_reference_index(
    curated_evidence: dict,
    upstream_inventory: dict,
    representation: dict,
) -> dict: ...

def build_baseline_prompt(
    category_id: str,
    blueprint: dict,
    curated_summary: dict,
    upstream_summary: dict,
    representation_summary: dict,
    evidence_reference_index: dict,
) -> str: ...

def build_baseline_json_schema(blueprint: dict) -> dict: ...

def call_baseline_codex(
    prompt: str,
    category_id: str,
    model: str,
    timeout_seconds: int,
    verbose: bool,
    heartbeat_seconds: int,
) -> dict: ...

def validate_baseline(
    baseline: dict,
    blueprint: dict,
    curated_summary: dict,
    upstream_summary: dict,
) -> list[str]: ...

def apply_lightweight_baseline_repairs(
    baseline: dict,
    blueprint: dict,
) -> tuple[dict, list[str]]: ...

def build_repair_prompt(
    blueprint: dict,
    current_baseline: dict,
    issues: list[str],
) -> str: ...

def render_baseline_markdown(baseline: dict) -> str: ...
def write_baseline_files(category_id: str, baseline: dict) -> None: ...
def render_baseline_index() -> None: ...
```

The exact signatures may vary, but the responsibilities must stay intact.

## Input Contracts

### 1. Blueprint input

Source:

- `data/eval/blueprints/{category}_blueprint.json`

Required usage:

- `meta`
- `category_signature`
- `headline_pattern`
- `tagline_profile_angle`
- `core_competency_themes`
- `key_achievement_archetypes`
- `role_weighting_guidance`
- `language_and_tone`
- `unsafe_or_weak_framing`
- `evidence_ledger`

Step 6 must treat Step 5 blueprints as the category rubric anchor.

### 2. Curated evidence input

Source files:

- `data/master-cv/roles/*.md`
- `data/master-cv/projects/*.md`
- `data/master-cv/projects/*_skills.json`
- `data/master-cv/role_metadata.json`
- `data/master-cv/role_skills_taxonomy.json`

Required extraction:

- role titles and scopes
- role achievements with line refs
- project achievements with line refs
- verified skills
- supporting skills
- explicit do-not-claim items
- taxonomy identity statements
- metadata title / competency framing

### 3. Upstream evidence input

Step 6 must not scan all docs indiscriminately.
It must use a bounded inventory of high-signal evidence sources.

Initial allowlist should include:

- `docs/archive/knowledge-base.md`
- `docs/current/achievement-review-index.md`
- `docs/current/achievement-review-tracker.yaml`
- `docs/current/cv-generation-guide.md`
- `docs/current/prompt-optimization-plan.md`
- category-relevant architecture / project docs explicitly approved later if needed

Each upstream item must be tagged:

- `claimable_evidence`
- `supporting_context`
- `guidance_only`

Only `claimable_evidence` and strong `supporting_context` may support `supported_upstream_pending_curation`.

### 4. Representation input

Representation should be loaded from the current master-CV representation artifact set.

If there is a canonical current master CV file, use it.
If not, Step 6 implementation must define a deterministic representation bundle and document it.

Minimum representation bundle:

- current headline / title
- summary / profile
- current role bullet selections
- current projects section
- skills / competencies section

If a canonical current master CV artifact does not yet exist, implement:

- a temporary representation builder from `data/master-cv/*`
- and label the result `representation_proxy_mode: true`

## Summary Builders

### Curated evidence summary

The curated summary must compress raw evidence into category-relevant signals, not dump files verbatim.

Required sections:

- `role_evidence`
- `project_evidence`
- `verified_skills`
- `supporting_skills`
- `do_not_claim`
- `leadership_signals`
- `architecture_signals`
- `impact_metrics`
- `governance_reliability_signals`
- `evidence_density_notes`

Each item should carry:

- short signal label
- supporting file refs
- confidence

### Upstream evidence summary

The upstream summary must only include evidence plausibly relevant to the category blueprint.

Required sections:

- `pending_curation_signals`
- `ambiguous_signals`
- `guidance_only_items`
- `upstream_risks`

Each `pending_curation_signal` should include:

- signal
- why relevant to category
- source refs
- confidence
- recommended target curated files

### Representation summary

The representation summary must evaluate what the current master CV currently surfaces.

Required sections:

- `headline_current_state`
- `summary_current_state`
- `role_priority_current_state`
- `project_priority_current_state`
- `skills_priority_current_state`
- `underrepresented_signals`
- `overstated_risks`

## Prompt Contract

The LLM prompt must be JSON-first and category-specific.

It must instruct the model to:

- score category readiness
- separate curation from representation
- avoid generic resume advice
- avoid unsupported leadership/research inflation
- emit strict JSON only
- cite exact evidence references

The model must not receive raw file dumps by default.
It must receive compact summaries plus a reference index.

## JSON Output Contract

Step 6 output JSON must contain exactly these top-level sections:

```json
{
  "meta": {},
  "overall_assessment": {},
  "score_breakdown": {},
  "strongest_supported_signals": [],
  "gap_analysis": [],
  "safe_claims_now": {},
  "representation_diagnosis": {},
  "curation_priorities": [],
  "master_cv_upgrade_actions": [],
  "evidence_ledger": []
}
```

### `meta`

Required fields:

- `category_id`
- `category_name`
- `macro_family`
- `priority`
- `confidence`
- `representation_proxy_mode`

### `overall_assessment`

Required fields:

- `combined_fit_score`
- `readiness_tier`
- `one_sentence_verdict`
- `uncertainty_note`
- `citations`

### `score_breakdown`

Required fields:

- `candidate_evidence_coverage_score`
- `evidence_curation_completeness_score`
- `master_cv_representation_quality_score`
- `ai_architecture_fit_score`
- `leadership_scope_fit_score`
- `impact_proof_strength_score`
- `weighted_score_explanation`
- `citations`

### `strongest_supported_signals`

Each item must include:

- `signal`
- `why_it_matters_for_category`
- `status`
- `evidence_refs`
- `citation`

Allowed `status`:

- `supported_and_curated`

### `gap_analysis`

Each item must include:

- `signal`
- `gap_type`
- `why_it_matters`
- `current_state`
- `safe_interpretation`
- `recommended_action`
- `evidence_refs`
- `citation`

Allowed `gap_type`:

- `supported_upstream_pending_curation`
- `curated_but_underrepresented`
- `unsupported_or_unsafe`

### `safe_claims_now`

Required arrays:

- `headline_safe`
- `profile_safe`
- `experience_safe`
- `leadership_safe`
- `unsafe_or_too_weak`
- `citations`

### `representation_diagnosis`

Required arrays:

- `well_represented_now`
- `underrepresented_now`
- `overstated_risk_now`
- `representation_priorities`
- `citations`

### `curation_priorities`

Each item must include:

- `priority_rank`
- `action`
- `why_now`
- `target_files`
- `source_refs`
- `expected_category_impact`
- `citation`

### `master_cv_upgrade_actions`

Each item must include:

- `priority_rank`
- `action`
- `section`
- `why_now`
- `supported_by`
- `citation`

Allowed `section`:

- `headline`
- `summary`
- `role_bullets`
- `projects`
- `skills`
- `metadata`

### `evidence_ledger`

Each item must include:

- `recommendation`
- `classification`
- `support`
- `confidence`

Allowed `classification`:

- `supported_and_curated`
- `supported_upstream_pending_curation`
- `curated_but_underrepresented`
- `unsupported_or_unsafe`

## Validation Contract

Step 6 must reject outputs that fail any of the following:

- JSON parse failure
- missing top-level sections
- missing citations on any substantive section
- any score outside `0.0-10.0`
- invalid `readiness_tier`
- invalid `gap_type`, `status`, `classification`, or `section`
- `combined_fit_score` inconsistent with weighted component scores beyond rounding tolerance
- `supported_and_curated` item that only cites upstream sources
- `supported_upstream_pending_curation` item that cites only curated files
- `curated_but_underrepresented` item lacking curated evidence refs
- `unsupported_or_unsafe` item presented with positive claim language
- generic filler language:
  - `best-in-class`
  - `world-class`
  - `visionary`
  - `thought leader`
- unsupported research/publication/PhD framing in positive sections
- missing `unsafe_or_too_weak` entries for sparse or leadership-inflation-prone categories
- too-thin evidence ledger:
  - primary: at least 8
  - secondary: at least 6
  - tertiary: at least 4

## Lightweight Repairs

Before full rejection, Step 6 should apply deterministic repairs for low-risk issues:

- normalize invalid readiness tier casing
- remove banned filler phrases
- soften inflated claim verbs
- reclassify obvious `supported_and_curated` vs `pending_curation` mismatches when refs make the correction deterministic
- add `representation_proxy_mode` when missing

If repairs still fail validation, run a repair prompt with:

- original baseline JSON
- explicit issue list
- same strict schema

## Renderer Contract

Markdown rendering must be deterministic and derived only from saved JSON.

Each `{category}_baseline.md` should include:

- category + score summary
- score breakdown table
- strongest supported signals
- gap analysis grouped by gap type
- safe claims now
- representation diagnosis
- curation priorities
- master-CV upgrade actions
- evidence ledger

`index.md` should include one row per category with:

- `category_id`
- `combined_fit_score`
- `readiness_tier`
- `representation_proxy_mode`
- `top 1-2 next actions`

## Debug Artifact Contract

Per-attempt debug directories must include:

- prompt text
- raw model output
- stdout/stderr logs
- parsed JSON
- validation issues
- repair notes
- compact summary snapshots used in the prompt

This should mirror Step 5 debug style closely.

## CLI Contract

The Step 6 script should support:

```bash
python scripts/eval_step6_baselines.py
python scripts/eval_step6_baselines.py --category ai_architect_global
python scripts/eval_step6_baselines.py --force
python scripts/eval_step6_baselines.py --render-only
python scripts/eval_step6_baselines.py --provider codex --model gpt-5.4
python scripts/eval_step6_baselines.py --verbose --heartbeat-seconds 15
python scripts/eval_step6_baselines.py --representation-source auto
```

Required flags:

- `--category` repeatable
- `--force`
- `--render-only`
- `--provider`
- `--model`
- `--timeout-seconds`
- `--max-attempts`
- `--verbose`
- `--heartbeat-seconds`
- `--representation-source`

Allowed `--representation-source` values:

- `auto`
- `proxy`
- `canonical`

Behavior:

- `auto`: use canonical representation if available, else proxy
- `proxy`: always derive from curated files
- `canonical`: require the canonical master-CV representation artifact and fail if absent

## Storage Contract

Artifacts under `data/eval/baselines/`:

```text
data/eval/baselines/
├── {category}_baseline.json
├── {category}_baseline.md
├── index.md
├── evidence_map.json
└── debug/
    └── {category}/
        └── {timestamp}/
```

`evidence_map.json` must contain:

- curated file inventory
- upstream inventory
- representation source mode
- normalized refs used across categories

## Execution Order

Recommended implementation order:

1. file loaders
2. summary builders
3. JSON schema
4. prompt builder
5. Codex caller with heartbeat/debug logging
6. validator
7. lightweight repair pass
8. markdown renderer
9. index renderer
10. end-to-end single-category test on `ai_architect_global`

## Success Criteria

Step 6 is complete when:

- a single-category run succeeds end-to-end
- baseline JSON validates deterministically
- the output clearly separates curation gaps from representation gaps
- the Markdown report is readable without looking at raw JSON
- reruns are stable enough for longitudinal comparison
- the resulting actions are directly usable for Phase 1 evidence promotion and master-CV improvement
