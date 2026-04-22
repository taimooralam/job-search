# Extraction 4.1.1 Plan: `jd_facts` Runner Parity

Author: planning pass on 2026-04-19
Parent plans:
- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`
- `plans/iteration-4.1-job-blueprint-preenrich-cutover.md`
- `plans/runnerless-vps-mongo-skill-pipeline.md`
- `plans/brainstorming-new-cv-v2.md`
- `plans/scout-pre-enrichment-skills-plan.md`

Status: planning only. No code changes in this pass. Focus is extraction richness, extraction prompts, extraction compatibility, extraction evaluation, extraction rollout.

---

## 1. Executive Summary

Iteration 4.1 correctly replaced the runner-era content stages with a blueprint-native DAG, but the extraction stage it shipped — `jd_facts` — is materially thinner than the runner-era extraction surface (`src/layer1_4/claude_jd_extractor.JDExtractor` + `src/layer1_4/prompts.JD_EXTRACTION_SYSTEM_PROMPT`). The live `jd_facts` combines a shallow regex-plus-static-vocabulary deterministic pass (`src/preenrich/stages/blueprint_common.py`) with a minimal LLM "judge" prompt (`src/preenrich/blueprint_prompts.build_p_jd_judge`). Iteration 4.1 §3.1 already called this out as a non-cosmetic gap: "`jd_facts` is too thin."

Extraction 4.1.1 is a content-quality hardening of `jd_facts` that:

1. Restores every field the runner-era `ExtractedJD` contract produces.
2. Upgrades the prompt surface from a "field collector + light judge" to a schema-first, evidence-grounded extraction pass that matches or exceeds runner output.
3. Preserves the existing `extracted_jd` compatibility projection so CV generation, CV review, answer generation, outreach, annotation suggester, and job detail/batch preview surfaces keep working unchanged.
4. Adds a real-job benchmark harness comparing new extraction against an existing runner-generated extraction, with explicit acceptance thresholds.
5. Rolls out behind shadow-write and live-write gates so the richer extraction can be benchmarked and canaried without immediately overwriting `level-2.extracted_jd`.

This is primarily a `jd_facts` hardening plan, but it also includes the minimum adjacent ownership fixes required to make parity real: `classification` must stop clobbering richer `extracted_jd.role_category` with the current heuristic output, and `blueprint_assembly` must stop overwriting richer `extracted_jd.top_keywords` / `ideal_candidate_profile` with thinner guideline-derived values. It is not a full re-architecture of 4.1. It does not redesign `jd_structure`, `research_enrichment`, `job_inference`, `cv_guidelines`, candidate modeling, or CV generation.

The benchmark acceptance is specific: on a curated set of jobs that already have runner-era `extracted_jd` persisted on `level-2`, the new `jd_facts` must (a) emit every field in `ExtractedJDModel` with its Pydantic-level validity intact, (b) match runner content at or above the thresholds defined in §10, and (c) produce a compatibility projection that passes every existing consumer read in §6 without modification.

---

## 2. Scope Ruling

**Structuring changes are OUT OF SCOPE. Read-only use of structured sections is IN SCOPE.**

Evidence:

- `jd_structure` produces `processed_jd_html`, `processed_jd_sections`, and `content_hash` via `src/layer1_4.process_jd` / `process_jd_sync`. These artifacts primarily serve the annotation UI (`frontend/templates/partials/job_detail/_jd_annotation_panel.html`) and `src/services/annotation_suggester.py`, but `processed_jd_sections` is also the safest existing source for separating responsibilities from qualifications when the raw JD is long or poorly formatted.
- 4.1 explicitly preserves `jd_structure` (iteration-4.1 plan §3 "`jd_structure`: preserve") and keeps `annotations` dependent on `jd_structure`, not on `jd_facts`.
- Runner parity for extraction does not require changing the `jd_structure` stage contract, but it does require allowing `jd_facts` to read `processed_jd_sections` when available so list fields are packed section-aware instead of by naive head truncation.
- The structure service `src/services/structure_jd_service.py` and the `/api/jobs/<job_id>/process-jd` endpoint are parallel operator paths, not inputs to extraction richness.

Consequence: this plan does not change `jd_structure`, the `processed_jd_sections` schema, the annotation locator schema, or `StructureJDService`. It does allow `jd_facts` to consume `processed_jd_sections` as read-only input when present. Any improvement to structuring itself is a separate plan.

What stays in scope:

- `src/preenrich/stages/jd_facts.py` (primary)
- `src/preenrich/blueprint_prompts.build_p_jd_extract` (new schema-first extraction prompt)
- `src/preenrich/stages/blueprint_common.py` (deterministic extraction helpers)
- `src/preenrich/blueprint_models.JDFactsDoc` (schema evolution)
- `jd_facts` compatibility projection `{"extracted_jd": ...}` emitted to `level-2`
- Model routing for `jd_facts` in `src/preenrich/types.py` and `scripts/preenrich_model_preflight.py`
- Minimal ownership fixes in `src/preenrich/stages/classification.py` and `src/preenrich/stages/blueprint_assembly.py` so richer extraction is not overwritten downstream
- Tests under `tests/unit/preenrich/` and a new real-job benchmark harness

What stays out of scope:

- `jd_structure`, `annotations`, `persona_compat` (and any UI that renders them)
- Prompt redesign of `classification`, `research_enrichment`, `application_surface`, `job_inference`, `job_hypotheses`, `cv_guidelines`
- Candidate matching, CV prose generation, CV review, outreach generation
- Runner vs non-runner transport decisions; this plan assumes preenrich continues to run under the 4.1 stage worker model

---

## 3. Current-State Extraction Topology

Five live code paths still touch structured JD extraction. They must be understood as a set before hardening `jd_facts`.

| # | Path | Entrypoint | Extracts to | Model | Notes |
|---|------|-----------|-------------|-------|-------|
| 1 | Runner full-extraction | `src/services/full_extraction_service.FullExtractionService.execute` via `runner_service/routes/operations.py` | `level-2.extracted_jd`, `level-2.processed_jd`, `level-2.pain_points`, `level-2.strategic_needs`, `level-2.jd_annotations`, `level-2.synthesized_persona`, `level-2.is_ai_job`/`ai_categories`/`ai_rationale` | Runs `JDExtractor` (tier-configurable Claude / LangChain fallback) + `JDProcessor` + `PainPointMiner` + `annotation_suggester` + `PersonaBuilder` + `classify_job_document_llm` | This is the richness benchmark. All consumers of `extracted_jd` were designed around its output. |
| 2 | Direct extract | `src/layer1_4/claude_jd_extractor.JDExtractor.extract` (via `runner_service/routes/operations.py` `/api/jobs/<id>/extract`) | `level-2.extracted_jd` | Single LLM call against `JD_EXTRACTION_SYSTEM_PROMPT` / `JD_EXTRACTION_USER_TEMPLATE` (`src/layer1_4/prompts.py`) with `ExtractedJDModel` validation | Same prompt, same Pydantic. This is the one to benchmark against. |
| 3 | Structure JD | `src/services/structure_jd_service.StructureJDService` via `/api/jobs/<id>/process-jd` | `level-2.processed_jd.*`, `level-2.jd_annotations.processed_jd_html/_sections/content_hash`, `level-2.ai_classification`, `level-2.is_ai_job` | `process_jd` LLM call + `classify_job_document_llm` | Parallel path. Structuring logic is excluded, but `processed_jd_sections` is an allowed read-only input to extraction in this plan. |
| 4 | Preenrich legacy | `src/preenrich/stages/jd_extraction.JDExtractionStage` (used only when `blueprint_enabled()==False` per `src/preenrich/stage_registry.LEGACY_STAGE_REGISTRY`) | `level-2.extracted_jd` | Codex `gpt-5.4` primary with Claude/`JDExtractor` fallback on schema failure | Effectively re-executes path #2 content-wise. Same `ExtractedJDModel` validation. |
| 5 | Preenrich 4.1 blueprint | `src/preenrich/stages/jd_facts.JDFactsStage` (active when `blueprint_enabled()==True`) | `jd_facts` collection + `level-2.pre_enrichment.jd_facts.*` + compat `level-2.extracted_jd` | Deterministic regex+static-vocab pass (`blueprint_common`) + `P-jd-judge` LLM "additions/flags/confirmations" call | **This is the thin path the plan hardens.** |

The same subject (`level-2.description`) is extracted three different ways across these paths with three different richness levels. Extraction 4.1.1 standardizes on path #5 and drives its quality to meet or beat path #1/#2.

What the current `jd_facts` actually does (read from `src/preenrich/stages/jd_facts.py` + `blueprint_common.py`):

- `_deterministic_extract` returns ten keys: `title`, `company`, `location`, `remote_policy`, `salary_range`, `must_haves`, `nice_to_haves`, `technical_skills`, `soft_skills`, `top_keywords`, `application_url`.
- `technical_skills` and `soft_skills` are bounded by a static list of ~17 tokens each (`KNOWN_SKILLS`, `KNOWN_SOFT_SKILLS` in `blueprint_common.py`). Any skill not in that list is invisible unless `extract_keywords` catches it as a generic word.
- `top_keywords` is a regex word-walk with a minimal stopword list, not a ranked ATS keyword set.
- `_judge_additions` calls `build_p_jd_judge` with a thin instruction ("Review… deterministic fields cannot be silently overwritten… output additions only when they include evidence spans"). The prompt carries no role-category contract, no competency-weights contract, no responsibilities/pain-point contract, and no ideal-candidate contract.
- The compat `extracted_jd` projection the stage emits contains only: `title`, `company_name`, `location`, `remote_policy`, `salary_range`, `qualifications`, `nice_to_haves`, `technical_skills`, `soft_skills`, `top_keywords`.
- The current blueprint path has downstream clobber points even if `jd_facts` is enriched: `classification` directly writes `extracted_jd.role_category`, and `blueprint_assembly` directly writes `extracted_jd.top_keywords` plus `extracted_jd.ideal_candidate_profile`.

This is a field collector, not an extraction engine.

---

## 4. Runner vs 4.1 Delta

Ground truth for runner extraction is `ExtractedJDModel` (`src/layer1_4/claude_jd_extractor.py:152`) + `ExtractedJD` TypedDict (`src/common/state.py:73`). Ground truth for current 4.1 extraction is `JDFactsDoc` (`src/preenrich/blueprint_models.py:38`) + the compat projection emitted at `src/preenrich/stages/jd_facts.py:146-157`.

### 4.1 Field-level gap matrix

| Runner `ExtractedJD` field | Runner contract | Current `jd_facts` merged_view | Current compat `extracted_jd` | Gap |
|-----------------------------|-----------------|-------------------------------|-------------------------------|-----|
| `title` | required str ≥3 | present (deterministic, passthrough of `job_doc.title`) | `title` | none |
| `company` | required str ≥1 | present | emitted as `company_name` (NOT `company`) | **compat field name mismatch** — `src/services/cv_review_core.py:313`, `src/services/outreach_service.py:555` expect `company` |
| `location` | default "Not specified" | present | `location` | none |
| `remote_policy` | enum | heuristic (`detect_remote_policy`) | `remote_policy` | coverage-ok, but no evidence span |
| `role_category` | required enum (8 values) | **missing** | **missing** | **critical gap** — consumed by `src/services/claude_cv_service.py:236`, `answer_generator_service.py:314`, `src/layer6_v2/role_generator.py`, `src/layer6_v2/variant_selector.py` |
| `seniority_level` | required enum | missing | missing | **critical gap** — sorting + CV tone rely on this |
| `competency_weights` | required, sum=100 | missing | missing | **critical gap** — used by CV generation emphasis decisions |
| `responsibilities` | required 3–15 | partially covered by `must_haves` (header-bucket collector, not a responsibilities list) | missing | **critical gap** — consumed by `src/services/annotation_suggester.py:815` |
| `qualifications` | required 2–12 | `must_haves` (same collector) | `qualifications` | coverage-ok (mapped from `must_haves`); quality-thin because extractor is header-match only |
| `nice_to_haves` | 0–10 | present | present | coverage-ok; quality-thin (header-match only) |
| `technical_skills` | 0–20 | present but capped to a 17-term static vocabulary | present | **quality gap** — any real JD skill outside the static list is dropped |
| `soft_skills` | 0–10 | present, also bounded to 7-term static vocabulary | present | **quality gap** |
| `implied_pain_points` | 0–8 | missing | missing | **critical gap** — consumed by `src/services/outreach_service.py:509` as outreach pain-point source |
| `success_metrics` | 0–8 | missing | missing | **critical gap** — consumed via `FullExtractionService._persist_results` into `level-2.success_metrics`; surfaces in job detail and CV challenges |
| `top_keywords` | required 10–20 | present but unranked / mostly noise | present | **quality gap** — this is the ATS keyword contract; consumers expect prioritized list |
| `industry_background` | Optional str | missing | missing | optional runner carryover; no current runtime reader found |
| `years_experience_required` | Optional int 0–50 | missing | missing | **gap** |
| `education_requirements` | Optional str | missing | missing | **gap** |
| `ideal_candidate_profile` | Optional nested (identity_statement, archetype, key_traits, experience_profile, culture_signals) | missing | missing | **critical gap** — `src/common/persona_builder.py` accepts `ideal_candidate_profile` as JD alignment input; `FullExtractionService` at `full_extraction_service.py:765` explicitly reads `extracted_jd.ideal_candidate_profile` before persona synthesis |

Additional compatibility aliases missing from the current plan and current `jd_facts`:

- `required_qualifications` — read by `frontend/templates/partials/batch/_jd_preview_content.html` and `frontend/templates/mobile/index.html`
- `key_responsibilities` — read by `runner_service/utils/best_effort_dossier.py` as a fallback alias
- `salary` — not part of `ExtractedJDModel`, but `frontend/templates/job_detail.html` falls back to `job.extracted_jd.salary` when top-level `job.salary_range` is absent

### 4.2 Structural deltas

- Runner validates via `ExtractedJDModel` with 8-value `RoleCategory`, 6-value `SeniorityLevel`, 4-value `RemotePolicy`, 8-value `CandidateArchetype`, and `CompetencyWeightsModel` with sum-to-100 invariant. Current `jd_facts` has no such validation.
- Runner prompt (`JD_EXTRACTION_SYSTEM_PROMPT`, 199 lines) carries role-category decision rules, competency-mix heuristics, keyword-extraction rules, ideal-candidate archetype definitions, and guardrails. Current `P-jd-judge` (5 lines) has none of these.
- Runner extraction is one LLM call against the whole JD. Current `jd_facts` does a shallow deterministic pass then asks an LLM only for "additions" on top of it — the LLM never sees the full richness contract.
- `JDFactsDoc.model_config = extra="forbid"` — adding richer fields to the artifact requires a schema change (planned in §7.3).

### 4.3 Why the current shape is not salvageable as-is

The current `jd_facts._deterministic_extract` cannot be promoted to parity by widening the static vocabulary or adding more regex. Runner parity requires role_category, seniority, competency weights, responsibilities, implied_pain_points, success_metrics, years_experience, and ideal_candidate_profile. None of those can be extracted from regex. The deterministic pass is useful as a pre-pass (title/company/location/salary/URL) but the primary richness path must be LLM-driven with a schema-first contract.

---

## 5. No-Loss Extraction Contract

Extraction 4.1.1 treats the union of (a) runner `ExtractedJDModel` fields and (b) fields that any in-repo consumer currently reads from `level-2.extracted_jd` as a **hard no-loss set**. Nothing in this set may be dropped, renamed, or shape-changed without a corresponding consumer migration committed in the same slice.

### 5.1 Mandatory no-loss fields (from code review)

The following fields MUST be present and Pydantic-valid in the compat projection written to `level-2.extracted_jd`:

Core identity:
- `title` (str)
- `company` (str) — **must be emitted under this exact key**, not `company_name`
- `location` (str)
- `remote_policy` (one of `fully_remote|hybrid|onsite|not_specified`)

Role taxonomy:
- `role_category` (one of the 8 `RoleCategory` enum values)
- `seniority_level` (one of the 6 `SeniorityLevel` enum values)

Competency mix:
- `competency_weights` (dict with `delivery|process|architecture|leadership` ints summing to 100)

Content extraction:
- `responsibilities` (list[str], 3–15 items)
- `qualifications` (list[str], 2–12 items)
- `nice_to_haves` (list[str], 0–10)
- `technical_skills` (list[str], 0–20)
- `soft_skills` (list[str], 0–10)

Pain-point surface:
- `implied_pain_points` (list[str], 0–8)
- `success_metrics` (list[str], 0–8)

ATS:
- `top_keywords` (list[str], 10–20, deduplicated, ranked)

Background:
- `years_experience_required` (Optional[int], 0–50)
- `education_requirements` (Optional[str])

Ideal candidate:
- `ideal_candidate_profile` (Optional nested with `identity_statement`, `archetype` ∈ 8-value enum, `key_traits` 3–5, `experience_profile`, `culture_signals` 0–4)

Legacy compatibility aliases:
- `required_qualifications` (alias of `qualifications` for existing template readers)
- `key_responsibilities` (alias of `responsibilities` for dossier fallback)
- `salary` (optional alias used only as a job-detail fallback; top-level `job.salary_range` is the single canonical source of truth and may be populated first from JD extraction, then later enriched by research)

Optional runner carryovers that should be retained when cheap but are not rollout-blocking:
- `industry_background`

### 5.2 Ownership rule

The canonical source of taxonomy remains `classification`, but the current implementation detail matters:

- `classification` currently writes `extracted_jd.role_category` directly in its own stage output patch.
- `blueprint_assembly` currently writes `extracted_jd.top_keywords` and `extracted_jd.ideal_candidate_profile` in its compatibility projection.

This means extraction parity cannot be achieved by changing `jd_facts` alone. The ownership rule for 4.1.1 is:

- `jd_facts` owns the extraction-rich compat payload for `responsibilities`, `qualifications`, `nice_to_haves`, `technical_skills`, `soft_skills`, `implied_pain_points`, `success_metrics`, `top_keywords`, `ideal_candidate_profile`, `years_experience_required`, `education_requirements`, alias fields, and provisional `role_category`.
- `classification` remains the canonical taxonomy artifact owner, but while it is still heuristic it must not overwrite `level-2.extracted_jd.role_category` with a lower-fidelity value. For 4.1.1 it writes only to `pre_enrichment.outputs.classification` and stops patching the compat field directly. When classification is upgraded later, it must classify against `data/job_archetypes.yaml` as the source of truth rather than the current `title_family()` heuristic.
- `blueprint_assembly` must stop overwriting extraction-rich `extracted_jd.top_keywords` and `extracted_jd.ideal_candidate_profile`; its blueprint snapshot can keep separate guideline-driven summaries.

This is ordered overwrite control, not a true race. `stage_worker` patches each stage's `result.output` directly into `level-2`, so the later stage wins deterministically unless the write is removed.

### 5.3 Invalidation and indexes

No index redesign is required, but version bumps alone are not enough for live rollout semantics. The existing `jd_facts` unique index on `(job_id, jd_text_hash, extractor_version, judge_prompt_version)` supports side-by-side artifact versions. It does not cause already-processed `cv_ready` jobs to be re-enqueued because the root enqueuer only claims `lifecycle="selected"` jobs and the current `input_snapshot_id` does not include extractor version. Cutover therefore needs explicit shadow-run / canary selection mechanics, not just an `EXTRACTOR_VERSION` bump.

---

## 6. Consumer Impact Matrix

Consumers classified by whether they need the runner-era shape, a strict subset, or can work against the richer projection.

| Consumer | File/line | Fields read | Classification | Break if thinner? |
|---|---|---|---|---|
| CV generation | `src/services/cv_generation_service.py:358-391` | `extracted_jd` object presence, `title`, `company` fallback only; deeper reads happen in downstream layer-6 consumers | compat hand-off | **Yes** — unchanged `extracted_jd` contract still required end-to-end |
| Claude CV service | `src/services/claude_cv_service.py:213,236,638` | `role_category`, `top_keywords[:10]` | needs runner shape | **Yes** |
| Answer generator | `src/services/answer_generator_service.py:86,309,314` | `top_keywords[:10]`, `role_category` | needs runner shape | **Yes** |
| Outreach | `src/services/outreach_service.py:501,509,555,556` | `implied_pain_points`, `company`, `title` | needs runner shape (`implied_pain_points` is load-bearing) | **Yes** |
| Annotation suggester | `src/services/annotation_suggester.py:563,619,622,814,815,816` | `qualifications`, `nice_to_haves`, `technical_skills`, `responsibilities`, `top_keywords` | needs runner shape | **Yes** — `_infer_dimensions_from_extracted_jd` degrades silently without `responsibilities`/`technical_skills` |
| CV review core | `src/services/cv_review_core.py:313-340` | `title`, `company`, `role_category`, `responsibilities`, `top_keywords`, `implied_pain_points`, `ideal_candidate_profile` | needs runner shape (`company` key, not `company_name`) | **Yes** — current jd_facts compat emits `company_name`; this breaks cv_review |
| Role generator (layer6_v2) | `src/layer6_v2/role_generator.py:403,528-532,751,932` | `role_category`, `top_keywords`, `implied_pain_points` | needs runner shape | **Yes** |
| Variant selector | `src/layer6_v2/variant_selector.py:360-361,797,870-871` | `implied_pain_points`, `role_category`, `top_keywords` | needs runner shape | **Yes** |
| Persona builder | `src/common/persona_builder.py:233-248,374-400` (fed from `src/services/full_extraction_service.py:763-768`) | `ideal_candidate_profile` | needs runner shape | **Yes** — persona synthesis uses `identity_statement` + `archetype` + `culture_signals` |
| Best-effort dossier | `runner_service/utils/best_effort_dossier.py` | reads `extracted_jd` broadly | needs runner shape | Yes |
| Job detail page | `frontend/templates/job_detail.html` + partials | `extracted_jd.*` for several panels | needs runner shape with blueprint overlay | Yes during migration, already handled by blueprint snapshot fallback |
| Batch preview | `frontend/templates/partials/batch/_jd_preview_content.html` | subset of `extracted_jd` | needs runner shape | Yes |
| Bulk CV review | `n8n/skills/cv-review/scripts/bulk_review.py` | `extracted_jd` fields consumed via `cv_review_core` | needs runner shape | Yes transitively |
| Apply-jobs sorting hints | `.claude/skills/apply-jobs/modules/sorting.md` | documentation-only reference to `extracted_jd` richness; no code dependency | doc-only | No — skill text can be updated if field names change |

Skill files (`.codex/skills/ingest-prep`, `.codex/skills/top-jobs`, `.codex/skills/scout-jobs`) do not impose extraction richness requirements; they consume `level-2` documents as read and do not validate extraction schema. They do not constrain this plan.

Hard requirement from this matrix: the compat projection must emit `company` (not `company_name`), `role_category`, `responsibilities`, `implied_pain_points`, `success_metrics`, `ideal_candidate_profile`, and ranked `top_keywords`. Without those, current consumers break silently (annotation suggester, outreach, role generator, variant selector) or loudly (cv_review_core on missing `company`).

---

## 7. Target Extraction 4.1.1 Architecture

### 7.1 Single extraction artifact, two-pass execution

Keep `jd_facts` as the single stage and single artifact collection. Replace its internal "deterministic-then-judge" pattern with a **deterministic pre-pass + schema-first LLM extraction pass + deterministic post-merge** pattern.

Flow:

1. **Pre-pass (deterministic)** — `blueprint_common` extracts the facts that regex/heuristics handle well and unambiguously: `title`, `company`, `location`, `remote_policy`, `salary_range`, `application_url`, and a *weak* keyword hint set. If `processed_jd_sections` exists, package section slices (`responsibilities`, `requirements`, `preferred`, `about_company`) as read-only inputs for the LLM prompt.
2. **Main pass (LLM, schema-first)** — one LLM call with a new prompt `P-jd-extract` that accepts the raw JD plus the pre-pass hints, and returns the full runner-shape JSON validated against a new Pydantic model `JDFactsExtractionOutput` (see §7.3). This is the richness path. Deterministic fields are passed in so the LLM does not waste capacity on them but may flag disagreement.
3. **Post-merge (deterministic)** — reconcile LLM output with the pre-pass: deterministic wins on the narrow set where it is definitive (`title`, `company`, `application_url`, `location` when non-empty, and `salary_range` when found); the LLM wins everywhere else. Disagreements are written to `llm_flags` with `severity="warn"`, not suppressed.

This replaces the current "additions on top of a thin deterministic view" pattern. The LLM is now the primary extractor; the deterministic layer is a guardrail on a small set of fields with clear textual anchors.

### 7.2 Judge pass

`P-jd-judge` is removed from the default 4.1.1 design. It does not carry the full extraction contract, adds cost, and duplicates validation logic that is better handled by schema validation plus model escalation. If a second-opinion auditor is ever needed later, it should be a separate follow-up plan, not a latent branch in this rollout.

### 7.3 Schema evolution

`JDFactsDoc` must grow without breaking the existing unique index.

New required sub-document `JDFactsExtractionOutput` (Pydantic):

```
class JDFactsExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # identity
    title: str
    company: str
    location: str
    remote_policy: RemotePolicy

    # taxonomy (compat projection; canonical home is `classification`)
    role_category: RoleCategory
    seniority_level: SeniorityLevel
    competency_weights: CompetencyWeightsModel  # sum == 100

    # content
    responsibilities: list[str]         # 3..15
    qualifications: list[str]           # 2..12
    nice_to_haves: list[str]            # 0..10
    technical_skills: list[str]         # 0..20
    soft_skills: list[str]              # 0..10

    # pain surface
    implied_pain_points: list[str]      # 0..8
    success_metrics: list[str]          # 0..8

    # ATS
    top_keywords: list[str]             # 10..20, deduplicated

    # background
    industry_background: Optional[str]
    years_experience_required: Optional[int]  # 0..50
    education_requirements: Optional[str]

    # ideal candidate
    ideal_candidate_profile: Optional[IdealCandidateProfileModel]

    # extras for provenance — optional
    salary_range: Optional[str]
    application_url: Optional[str]
```

Reuse the existing Pydantic enums and sub-models where possible to avoid duplicate taxonomies:

- `RoleCategory`, `SeniorityLevel`, `RemotePolicy`, `CandidateArchetype`, `CompetencyWeightsModel`, `IdealCandidateProfileModel` already exist in `src/layer1_4/claude_jd_extractor.py`.
- Move these shared models into `src/preenrich/blueprint_models.py` (or a new `src/preenrich/extraction_models.py`) and re-export from the existing location to preserve backward compatibility for any imports in `full_extraction_service.py` or `JDExtractor`. This is a mechanical move — no semantic change, no consumer churn.

Extend `JDFactsDoc`:

- Add `extraction: JDFactsExtractionOutput | None = None` as a new optional field (gated by `extra="forbid"` so the model grows explicitly).
- Keep `deterministic`, `merged_view`, `llm_additions`, `llm_flags`, `confirmations`, `provenance` unchanged for back-compat with the existing artifact reader.
- Bump `EXTRACTOR_VERSION` to `jd-facts.det.v2` and `PROMPT_VERSION` to `P-jd-extract:v1` so the existing unique index naturally partitions old vs new artifacts.

### 7.4 Compatibility projection written by `jd_facts`

`jd_facts` already writes a compat projection key `extracted_jd` into its `StageResult.output`. Extend the projection to include every field in §5.1 using `JDFactsExtractionOutput`. Explicit rules:

- Emit under key `company`, not `company_name`. (Fixes the cv_review_core break.)
- Emit `role_category` from `JDFactsExtractionOutput.role_category` with provenance marker stored in `jd_facts.provenance.role_category = "llm_jd_facts"`. `classification` may continue to own the canonical classification artifact, but it must not overwrite the compat field with the current heuristic value during the 4.1.1 rollout.
- `ideal_candidate_profile` is emitted as a dict matching `IdealCandidateProfileModel.to_extracted_jd`-style shape (same keys as runner).
- `competency_weights` must sum to 100; Pydantic enforces this before emit.
- Emit compatibility aliases `required_qualifications`, `key_responsibilities`, and optional `salary` in addition to the canonical fields.

The compat projection is the single contract consumers see. It is authoritative. The structured artifact in the `jd_facts` collection is the debugger/auditor view with full evidence spans.

### 7.5 Provenance and evidence

Every field in `JDFactsExtractionOutput` must carry a `provenance` entry in `jd_facts.provenance` (one of `deterministic`, `llm_extract`, `llm_extract_with_flag`, `fallback_default`). Optional but recommended: richer evidence spans for high-value fields (`responsibilities`, `implied_pain_points`, `success_metrics`, `ideal_candidate_profile.identity_statement`) using `EvidenceRef` with `quote` preserved up to 280 chars.

Evidence is for debuggability and later parity evaluation; consumers do not read it.

### 7.6 What does NOT change

- The preenrich DAG shape (still `jd_facts` as `jd_structure`'s child, still a prerequisite of `classification`, `research_enrichment`, `application_surface`, `job_inference`, `cv_guidelines`).
- The unique index on the `jd_facts` collection.
- The stage worker / sweeper / finalizer semantics from iteration 4.
- The blueprint snapshot contract or the job_detail rendering path.
- `classification`'s ownership of the taxonomy decision.

---

## 8. Prompt Strategy

### 8.1 New prompt `P-jd-extract:v1`

Built in `src/preenrich/blueprint_prompts.build_p_jd_extract`. Structure:

- **System contract**: JSON-only output, schema pinned by field names. Reuse the core rules from `JD_EXTRACTION_SYSTEM_PROMPT` (`src/layer1_4/prompts.py:44-199`) but adapted for Codex/Claude dual-provider output and stripped of runner-era formatting assumptions.
- **Role-category decision table**: the 8-category signal list and competency-mix guidance from the runner prompt, unchanged in substance. This is the single biggest richness upgrade.
- **Keyword extraction rules**: runner's 6-category priority order (hard technical, role title, domain expertise, certifications, methodologies, leadership terms) with exact 15 + up to 20 ceiling.
- **Ideal candidate archetype definitions**: the 8-archetype signal list, unchanged.
- **Guardrails**: only extract what's stated/strongly implied, "Not specified" fallbacks, competency weights sum to 100, list-length bounds.
- **Deterministic inputs**: a section-aware JD payload, not blind truncation. If `processed_jd_sections` exists, pass ordered section slices plus a compacted raw-JD head+tail envelope. If not, fall back to raw JD packing with explicit tail retention; do not silently drop the bottom of long JDs.
- **No access to `job_hypotheses`** — enforced by the existing `_reject_hypotheses_payload` guard pattern.

The 4.1 prompt-contract test helper (iteration-4.1 §12) already requires every prompt builder to reject inputs referencing `job_hypotheses`. `build_p_jd_extract` inherits that guard.

### 8.2 Prompt versioning and storage

- Keep `PROMPT_VERSION` as a stage-level constant (string like `"P-jd-extract:v1"`).
- Persist `prompt_version` in both `work_items.payload` and `jd_facts.judge_prompt_version` (rename to `jd_facts.extract_prompt_version` if schema evolution permits, or reuse the existing field by convention).
- Bumping the version creates a new artifact partition. It does not by itself force live jobs back through the DAG; rollout still needs explicit shadow/canary selection.

### 8.3 Prompt hardening tests (see §11)

- **Contract test**: asserts the rendered prompt contains the 8 role-category slugs, the 4 competency-mix labels, the 8 archetype slugs, and the strict "JSON only" instruction.
- **Schema presence test**: asserts the rendered prompt references every required key in `JDFactsExtractionOutput`.
- **Hypothesis-leak guard**: asserts building with a payload containing `job_hypotheses` raises `ValueError` (reuse existing helper).
- **Golden-prompt snapshot test**: capture rendered prompt for a seed JD and diff on future changes so accidental prompt drift shows up in PR review.

### 8.4 Prompt disposition of existing extraction surfaces

- `P-jd-judge` is not part of 4.1.1.
- `JD_EXTRACTION_SYSTEM_PROMPT` / `JD_EXTRACTION_USER_TEMPLATE` (`src/layer1_4/prompts.py`) remain unchanged to avoid disturbing the runner path during benchmarking. After 4.1.1 cutover is stable, they can be marked deprecated (follow-up plan, not this one).
- The current `jd_extraction` legacy stage (`src/preenrich/stages/jd_extraction.py`) stays as-is. It only runs when `blueprint_enabled()==False`; after 4.1.1 is live, it has no production role.

---

## 9. Model Routing Strategy

Iteration 4.1 §8 assigned `jd_facts` to `gpt-5.4-mini` by default. 4.1.1 should keep an efficient default and add bounded escalation rather than hard-switching every extraction to `gpt-5.4`.

Recommended routing:

| Pass | Default provider / model | Fallback | Rationale |
|---|---|---|---|
| Pre-pass (deterministic) | none | none | Regex/heuristics, no LLM |
| Main extraction (`P-jd-extract`) | codex `gpt-5.4-mini` | codex `gpt-5.4`, then claude `claude-sonnet-4-6` | Keep the cheap model as the steady-state default. Escalate only on schema-validation failure, missing mandatory fields, or explicit ambiguity triggers. |
| Post-merge (deterministic) | none | none | Local reconciliation |

Per-stage env overrides:

- `PREENRICH_PROVIDER_JD_FACTS` (default `codex`)
- `PREENRICH_MODEL_JD_FACTS` (default `gpt-5.4-mini`)
- `PREENRICH_FALLBACK_PROVIDER_JD_FACTS` (default `claude`)
- `PREENRICH_FALLBACK_MODEL_JD_FACTS` (default `claude-sonnet-4-6`)
- `PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED` (default `true`)
- `PREENRICH_JD_FACTS_ESCALATION_MODEL` (default `gpt-5.4`)

Extend `scripts/preenrich_model_preflight.py` to fail-fast if `jd_facts` has no configured provider/model. Existing model-preflight test (`tests/unit/preenrich/test_model_preflight_routing.py`) is updated to cover the new env names.

Cost envelope (order-of-magnitude):

- One `gpt-5.4-mini` call per JD should be the steady-state assumption. The plan only pays `gpt-5.4` rates on the minority of jobs that fail schema validation, miss mandatory fields, or trip explicit ambiguity heuristics.
- Claude fallback should remain Sonnet-class, because the runner parity baseline is the existing Sonnet-grade `JDExtractor`, not a new Opus-only path.

---

## 10. Benchmark / Eval Plan

Parity cannot be asserted by schema alone. Extraction 4.1.1 includes a concrete, repeatable benchmark that compares new `jd_facts` output against runner-era `extracted_jd` on real jobs pulled from MongoDB.

### 10.1 Benchmark corpus selection

Select a two-part benchmark set:

- **Prompt-iteration smoke corpus**: 20 jobs from `level-2`
- **Sign-off corpus**: 50 jobs spanning the same role mix plus a 10-job human-labeled gold set for the highest-value inferred fields

The 20-job set is for rapid iteration. It is not enough to make strong statistical claims like "90% role-category accuracy" on its own.

Selection rules:

- `extracted_jd` exists and has non-empty `responsibilities`, `top_keywords`, `ideal_candidate_profile`
- `full_extraction_completed_at` is set (runner extraction confirmed)
- Jobs span all 8 `role_category` values (ensure ≥1 per category; top up with recent jobs if some categories are missing)
- Jobs span all 4 `remote_policy` values
- Include at least 3 jobs with ambiguous role signals (e.g., "Tech Lead / Engineering Manager" dual titles)
- Include at least 2 non-English / MENA-region jobs (Saudi/Gulf) to test prompt generalization

Corpus is materialized as `reports/extraction_4_1_1_benchmark_corpus.json` with `_id`, `title`, `company`, `description`, and the runner `extracted_jd` snapshot.

### 10.2 Harness

New script `scripts/benchmark_extraction_4_1_1.py`:

1. Load corpus.
2. For each job, invoke the new `JDFactsStage.run` against a fresh `StageContext` (re-uses preenrich wiring; no production side effects — writes to a throwaway `jd_facts_benchmark` collection + local JSON report).
3. Compare new compat `extracted_jd` vs runner `extracted_jd` field-by-field.
4. Emit a per-job report and an aggregate scorecard.

### 10.3 Comparison metrics

Per field:

- **Presence parity** — did the new extraction emit the field? (required for every §5.1 field; missing = hard fail)
- **Enum parity** — `role_category`, `seniority_level`, `remote_policy`, `ideal_candidate_profile.archetype`: exact-match rate
- **Numeric parity** — `years_experience_required`: within ±2 years; `competency_weights`: each dimension within ±10 AND sum == 100
- **List content parity** — `responsibilities`, `qualifications`, `nice_to_haves`, `technical_skills`, `soft_skills`, `implied_pain_points`, `success_metrics`: item-aligned token-F1 after normalization; `top_keywords`: precision@10 and recall@10
- **Identity statement parity** — `ideal_candidate_profile.identity_statement`: cosine similarity via a small sentence-embedding (reuse an existing embedding path if one exists in repo; otherwise score by BLEU/ROUGE as a fallback)
- **Schema validity** — the new compat projection must pass `ExtractedJDModel(**projection)` with no errors

### 10.4 Acceptance thresholds

4.1.1 is **NOT** cutover-ready unless the smoke corpus clears the operational thresholds below and the sign-off corpus confirms the taxonomy and inference fields are stable:

| Metric | Threshold | Rationale |
|---|---|---|
| Schema validity pass rate | 100% | Consumers break on Pydantic failure |
| `role_category` enum match | smoke corpus diagnostic only | 20 jobs is too small for a hard 90% claim with statistical meaning |
| `seniority_level` enum match | smoke corpus diagnostic only | same limitation |
| `remote_policy` enum match | ≥ 95% | Trivial field |
| `competency_weights` sum == 100 | 100% | Invariant |
| `competency_weights` per-dimension Δ | p95 ≤ 10 | Emphasis decisions are weight-sensitive |
| `responsibilities` item-F1 | mean ≥ 0.55, p25 ≥ 0.40 | Lists won't match exactly but must overlap meaningfully |
| `qualifications` item-F1 | mean ≥ 0.60 | Tends to be more literal than responsibilities |
| `technical_skills` item-F1 | mean ≥ 0.65 | These are named entities; high overlap expected |
| `implied_pain_points` item-F1 | mean ≥ 0.40 | Inference-heavy; looser bar |
| `success_metrics` item-F1 | mean ≥ 0.40 | Same |
| `top_keywords` precision@10 / recall@10 | both ≥ 0.60 | ATS-critical |
| `ideal_candidate_profile.archetype` match | ≥ 80% | 8-class classification, runner baseline tends to be ~85% self-consistent |
| Mean end-to-end extraction duration | ≤ runner_mean × 1.25 | Don't regress speed badly |

If any threshold fails, the plan calls for prompt iteration and re-run, not for lowering the bar. "Better than runner" is defined as passing schema validity, preserving consumer compatibility, matching or beating runner on the smoke corpus, and beating the runner baseline on the human gold set for the inferred fields that runner itself handles weakly.

### 10.5 Regression hedge

The harness is kept under `scripts/` and wired into CI on a tiny sampled corpus (3 jobs, fast variant) to prevent future prompt edits silently regressing. Full 20-job corpus runs manually on prompt version bumps.

### 10.6 Secondary parity against `FullExtractionService` run

Where the corpus does not contain a runner `extracted_jd` or freshness is suspect, the harness falls back to running `src/layer1_4/claude_jd_extractor.JDExtractor.extract` inline against the same JD as the live runner baseline for that job. This gives a real-time apples-to-apples comparison rather than relying solely on historical snapshots, at the cost of extra LLM calls. Toggle via `--fresh-runner-baseline`.

---

## 11. Test Plan

### 11.1 Unit tests

- `tests/unit/preenrich/test_stage_jd_facts.py`
  - deterministic pre-pass: title/company/location/salary/URL captured correctly from fixture JDs
  - main pass: mocked LLM returns valid JSON → artifact + compat projection both valid
  - main pass: mocked LLM returns invalid JSON once → fallback provider invoked and succeeds
  - main pass: mocked LLM returns schema-invalid output → stage emits `schema_validation` terminal error
  - compat projection: emits `company` (not `company_name`), emits `role_category`, `responsibilities`, `implied_pain_points`, `success_metrics`, `ideal_candidate_profile`
  - compat projection: validates against `ExtractedJDModel(**projection)` without error
  - provenance entries present for every emitted field
  - deterministic vs LLM conflict on `title` → deterministic wins, flag emitted
  - `competency_weights` sum != 100 in LLM output → Pydantic rejects; fallback invoked
  - escalation path: schema-invalid `gpt-5.4-mini` output retries once on `gpt-5.4`

- `tests/unit/preenrich/test_build_p_jd_extract.py` (new)
  - contract: prompt contains all 8 role-category slugs, all 8 archetype slugs, all 4 competency-mix labels, all 4 remote-policy values
  - contract: prompt contains "JSON only" / "no markdown" directive
  - schema presence: every required key of `JDFactsExtractionOutput` referenced in the prompt text
  - hypothesis-leak guard: payload containing `job_hypotheses` raises `ValueError`
  - golden snapshot: rendered prompt for a frozen seed JD matches a stored fixture byte-for-byte

- `tests/unit/preenrich/test_jd_facts_extraction_models.py` (new)
  - `JDFactsExtractionOutput`: `competency_weights` sum=100 enforced
  - enum normalization: lowercase, hyphen→underscore for `role_category` / `seniority_level` / `archetype`
  - list-length bounds enforced
  - `ideal_candidate_profile` optional; when present, required sub-fields enforced
  - alias fields `required_qualifications` / `key_responsibilities` mirror canonical values

- `tests/unit/preenrich/test_model_preflight_routing.py` (update)
  - asserts `PREENRICH_PROVIDER_JD_FACTS` / `PREENRICH_MODEL_JD_FACTS` routing is validated
  - missing config for `jd_facts` primary fails preflight
  - escalation-model routing validated when `PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED=true`

### 11.2 Consumer compatibility tests

New `tests/unit/preenrich/test_jd_facts_consumer_compat.py`:

- Given a synthetic `JDFactsExtractionOutput` built by the stage, assert:
  - `annotation_suggester._infer_dimensions_from_extracted_jd` executes without missing-key errors and returns non-empty dimension overrides
  - `claude_cv_service` keyword-ensure path reads `top_keywords[:10]` successfully
  - `answer_generator_service` context-build path consumes `role_category` and `top_keywords` successfully
  - `outreach_service` falls back to `implied_pain_points` when `pain_points` is empty (regression guard for 4.1.1 thin output)
  - `cv_review_core._format_jd_context` reads `extracted_jd.title`/`company`

These tests pin the consumer contract as a load-bearing interface. They run against the compat projection, not the artifact.

### 11.3 Benchmark harness tests

- `tests/unit/scripts/test_benchmark_extraction_4_1_1.py` (new)
  - harness loads a 2-job mini corpus
  - harness compares a fake "new extraction" vs a fake "runner extraction" and emits scorecard
  - harness fails when schema validity < 100%
  - harness passes when item-F1 / precision@10 thresholds met

### 11.4 Integration / end-to-end

- Existing `tests/unit/preenrich/test_stage_worker.py` and `test_dag.py` should already cover the stage wiring; add assertions only where `jd_facts` output shape changes:
  - `jd_facts` output now carries richer compat projection; assert downstream `classification` still receives its expected input (which was `jd_facts.merged_view`, and still is)
  - `classification` does not overwrite richer compat `extracted_jd.role_category` while the heuristic classifier remains in place
  - `blueprint_assembly` does not overwrite richer compat `extracted_jd.top_keywords` or `extracted_jd.ideal_candidate_profile`

### 11.5 Prompt regression

- `tests/unit/preenrich/test_jd_facts_golden_prompt.py` — snapshot test for the rendered `P-jd-extract` prompt on a seed JD. Intentional prompt edits bump the snapshot; accidental drift fails CI.

### 11.6 No-loss contract test

- `tests/unit/preenrich/test_jd_facts_no_loss.py` — parametrized over the field list in §5.1. For a fixture LLM output, asserts each field is present on the compat projection, non-null where §5.1 marks required, and passes `ExtractedJDModel` validation.
- Property/fuzz tests:
  - truncated-JD packing retains tail sections
  - multi-locale fixtures (at minimum EN + Gulf/MENA formatting)
  - competency-weight repair / rejection property tests

---

## 12. Migration / Rollout Plan

### 12.1 Feature flags

One flag is not enough. Use three:

- `PREENRICH_JD_FACTS_V2_ENABLED` — runs the new extraction path and writes the richer artifact
- `PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED` — allows the richer compat payload to overwrite `level-2.extracted_jd`
- `PREENRICH_JD_FACTS_ESCALATE_ON_FAILURE_ENABLED` — enables retry from `gpt-5.4-mini` to `gpt-5.4`

Mutual exclusion: `PREENRICH_JD_FACTS_V2_ENABLED=true` implies `PREENRICH_PROVIDER_JD_FACTS` must be set to a real provider (validated by startup probe).

### 12.2 Version bumps

- `EXTRACTOR_VERSION = "jd-facts.det.v2"` when V2 is on (current value `jd-facts.det.v1` remains for V1 branch)
- `PROMPT_VERSION = "P-jd-extract:v1"` when V2 is on

The `jd_facts` collection unique index `(job_id, jd_text_hash, extractor_version, judge_prompt_version)` ensures V1 and V2 artifacts coexist for the same job without collision. Rollback to V1 does not require deleting V2 artifacts; they remain inspectable.

### 12.3 Rollout phases

Phase A — dark launch (code merged, flag off):
- Merge schema evolution, prompt builder, tests. No behavior change in production.

Phase B — bench:
- Run the §10 benchmark locally. Iterate prompt until smoke-corpus thresholds pass and the sign-off set is acceptable. Do not enable live compat writes until both pass.

Phase C — canary shadow-write:
- Enable `PREENRICH_JD_FACTS_V2_ENABLED=true` with `PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED=false` for jobs selected using the existing root-enqueuer DAG canary controls (`PREENRICH_DAG_CANARY_ALLOWLIST`, `PREENRICH_DAG_CANARY_PCT`).
- Verify: V2 artifact written in `jd_facts`, benchmark report produced, and no live `level-2.extracted_jd` overwrite yet.

Phase D — live-write canary:
- Keep the same DAG canary controls and turn on `PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED=true` only for the canary cohort.
- Watch Langfuse for `jd_facts` span error rate and duration deltas.
- Widen to 25%, then 100% over at least 72h total soak.

Phase E — cutover:
- Default `PREENRICH_JD_FACTS_V2_ENABLED=true` and `PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED=true` in `infra/env/scout-workers.env.example`. V1 path remains in code as a recovery toggle.

Phase F — decommission (follow-up plan, not this one):
- After one stable release, remove V1 code path, static-vocab keyword helpers, and `build_p_jd_judge`-based default logic. Mark `src/layer1_4/prompts.py` runner extraction prompts as deprecated.

### 12.4 Compatibility invariants during rollout

- The compat projection at `level-2.extracted_jd` must pass `ExtractedJDModel` validation in the V2 path. V1 remains the documented thin baseline.
- Consumers that reach into `extracted_jd` must not crash on either shape. Current code either defaults missing fields to empty lists/None or short-circuits; spot-check this during Phase B before enabling canary.
- `classification` and `blueprint_assembly` overwrite behavior is pinned by tests before live compat write is enabled, with `classification` no longer patching `extracted_jd.role_category` in 4.1.1.

### 12.5 Rollback

- Flip `PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED=false` first to stop new overwrites, then `PREENRICH_JD_FACTS_V2_ENABLED=false` if needed. Existing V2 artifacts remain for inspection.
- No destructive Mongo edits. No schema downgrade needed.
- Because live overwrite is feature-gated, rollback works without trying to reconstruct `level-2.extracted_jd` from already-overwritten canary jobs.

### 12.6 Historical jobs

- 4.1.1 does NOT retroactively re-extract existing `cv_ready` jobs. If a specific historical job needs V2 extraction, operator re-selects it or uses an explicit benchmark harness / backfill command; `EXTRACTOR_VERSION` bump alone is not enough to re-enqueue historical jobs.
- For the benchmark corpus (§10.1), the harness runs V2 in isolation without touching production `level-2` state.

---

## 13. Risks And Open Questions

Real risks grounded in the repo:

- **Compat clobber by later stages.** Even if `jd_facts` becomes runner-parity rich, current `classification` and `blueprint_assembly` directly patch overlapping `extracted_jd` keys. If those writes are not removed or gated, parity work is silently lost.

- **Prompt truncation tail loss.** The current runner-style 12000-char truncation still drops bottom-of-JD signal. If the new prompt just copies that behavior, long-JD pain points and preferred qualifications will continue to disappear. Mitigation: section-aware packing plus tail retention tests.

- **Prompt cost regression.** Main extraction is richer than the thin path. Mitigation: `gpt-5.4-mini` default plus bounded escalation instead of paying `gpt-5.4` on every job.

- **`full_extraction_service.py` still produces `extracted_jd` via the runner path** for operator-triggered extractions. After 4.1.1 is live, an operator who clicks "full-extraction" in the UI overwrites the preenrich-produced `extracted_jd` with the runner version. This is acceptable (operator explicitly chose to) but must be documented so comparisons stay honest.

- **Annotation suggester compatibility.** `_infer_dimensions_from_extracted_jd` reads `technical_skills`, `responsibilities`, `qualifications`. V1 `jd_facts` left `responsibilities` empty, meaning the current production annotation path for V1-only jobs has been silently running with reduced dimension inference. The §11.2 consumer compat tests must include a case that runs on V1 output and confirms whether annotations are meaningfully degraded today — that result informs whether V2 is purely additive or also fixes latent annotation quality.

- **Benchmark corpus bias.** If the corpus is skewed toward a specific role-category mix, thresholds in §10.4 may not generalize. Mitigation: the corpus construction rule mandates all 8 role_category values.

Closed decisions for 4.1.1:

- `classification` stops patching `extracted_jd.role_category` entirely until it is upgraded from the current heuristic title-family classifier. The future upgraded classifier must use `data/job_archetypes.yaml` as the taxonomy source of truth.

- `job.salary_range` remains the single canonical salary field. `jd_facts` populates it when salary is present in the JD, and later research may enrich the same canonical field. `extracted_jd.salary` remains a compatibility alias only.

- Benchmarking is not runner-only. Use runner output as an operational baseline, but add a small human-labeled gold set specifically to turn known runner weaknesses into explicit improvement targets.

- `ideal_candidate_profile` stays status quo for 4.1.1: keep it inline on `level-2.extracted_jd` for consumer compatibility and do not add a new persona mirror path in this plan. Persona behavior is deferred.

---

## 14. Final Recommended Plan

Commit this plan as `plans/extraction-4.1.1-jd-facts-runner-parity.md`. Execute in this order:

1. **Move shared Pydantic enums** (`RoleCategory`, `SeniorityLevel`, `RemotePolicy`, `CandidateArchetype`, `CompetencyWeightsModel`, `IdealCandidateProfileModel`) from `src/layer1_4/claude_jd_extractor.py` into a shared module (`src/preenrich/extraction_models.py` or similar) and re-export for back-compat.
2. **Extend `JDFactsDoc`** in `src/preenrich/blueprint_models.py` with `extraction: JDFactsExtractionOutput | None = None` and keep `extra="forbid"` discipline.
3. **Add `build_p_jd_extract`** to `src/preenrich/blueprint_prompts.py` with the rules copied from `JD_EXTRACTION_SYSTEM_PROMPT` plus the payload envelope from `build_p_jd_judge`.
4. **Rewrite `JDFactsStage.run`** in `src/preenrich/stages/jd_facts.py` to use the two-pass pattern (§7.1), with `processed_jd_sections` as an optional read-only input and `gpt-5.4-mini` as the primary extraction model.
5. **Fix the compat projection** to emit `company` (not `company_name`) and the full §5.1 field set. This is load-bearing for `cv_review_core`.
6. **Add env plumbing** (`PREENRICH_PROVIDER_JD_FACTS`, `PREENRICH_MODEL_JD_FACTS`, `PREENRICH_JD_FACTS_V2_ENABLED`, `PREENRICH_JD_FACTS_V2_LIVE_COMPAT_WRITE_ENABLED`, escalation flags) in `src/preenrich/types.py` and `scripts/preenrich_model_preflight.py`.
7. **Add unit + contract + consumer-compat + golden-prompt tests** per §11.
8. **Build the benchmark harness** `scripts/benchmark_extraction_4_1_1.py` + smoke corpus + sign-off set + scorecard generator per §10.
9. **Run benchmark, iterate prompt** until all §10.4 thresholds pass.
10. **Shadow canary → live-write canary → 25% → 100%** rollout per §12.3. Do not enable live compat writes without green benchmark and overwrite-protection tests.

This remains a hardening plan rather than a full extraction-system rewrite, but it is not `jd_facts` in isolation. To make runner parity real, it must upgrade `jd_facts`, preserve cheap-by-default model routing, and remove the current downstream compat overwrites that would otherwise erase the richer extraction before consumers read it.
