# Classification 4.1.2 Plan: Taxonomy Engine Hardening

Author: planning pass on 2026-04-20
Parent plans:
- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`
- `plans/iteration-4.1-job-blueprint-preenrich-cutover.md`
- `plans/extraction-4.1.1-jd-facts-runner-parity.md`
- `plans/runnerless-vps-mongo-skill-pipeline.md`
- `plans/brainstorming-new-cv-v2.md`

Status: planning only. No code changes in this pass. This plan is strictly scoped to the `classification` stage and the minimum adjacent changes required to make a taxonomy-driven classifier functional inside the existing iteration-4.1 stage DAG.

---

## 1. Executive Summary

The current `classification` stage is a one-line title heuristic wrapped in a taxonomy-metadata lookup. It is the weakest LLM-free stage in the iteration-4.1 preenrich DAG. `src/preenrich/stages/classification.py` calls `title_family(title)` from `src/preenrich/stages/blueprint_common.py:136-152`, which returns one of eight slugs based on case-insensitive substring matching of the job title alone. The richer taxonomy in `data/job_archetypes.yaml` is consulted only for downstream *mapping metadata* (search profiles, selector profiles, tone family, ideal archetypes). The taxonomy never drives the classification decision.

Extraction 4.1.1 already removed the direct compat overwrite path: current `classification` no longer writes `level-2.extracted_jd.role_category`; it writes only the root AI compat fields (`is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification`). That fixed the immediate ownership bug, but it did not make the classification artifact itself any better. Every consumer that reads `pre_enrichment.outputs.classification.primary_role_category` — `job_inference`, `blueprint_assembly` snapshot, the job-detail blueprint panel — is still receiving title-only heuristic output. And because the root AI compat fields still feed `src/layer6_v2/orchestrator.py:495-531`, classification remains behavior-changing even without directly patching `extracted_jd.role_category`.

Classification 4.1.2 upgrades `classification` into a real taxonomy engine that:

1. Uses `data/job_archetypes.yaml` as the source of truth for the decision, not just for mapping lookups. The taxonomy file is extended with per-category signal lists and tie-breakers so the decision is auditable.
2. Classifies from richer inputs: `jd_facts.extraction` (role_category, seniority_level, responsibilities, qualifications, top_keywords, competency_weights, ideal_candidate_profile.archetype) plus title, company, and (read-only) `processed_jd_sections`, rather than title alone.
3. Executes a two-part flow: a deterministic taxonomy pre-score that walks the YAML signals across all 8 categories, then a bounded LLM reasoning call only when the pre-score is ambiguous *or* when it disagrees with `jd_facts.extraction.role_category`. High-confidence unambiguous agreements skip the LLM entirely, keeping cost low.
4. Emits richer outputs: `primary_role_category`, `secondary_role_categories` (0–2), `confidence` (high/medium/low enum), `ambiguity_score` (derived from pre-score distribution), `reason_codes`, `evidence` spans, `jd_facts_agreement`, and a new structured `ai_taxonomy` block that becomes the richest AI-role taxonomy surface in the pipeline.
5. Keeps the short-term compat boundary from 4.1.1: in 4.1.2, `classification` still does not write `extracted_jd.role_category`; that write remains `jd_facts`-owned. But the long-term source-of-truth target changes: `classification` becomes the canonical taxonomy artifact, and future consumers must migrate to it instead of reclassifying or overriding it.
6. Replaces the current heuristic `ai_relevance` regex with taxonomy-driven AI classification rich enough to act as the global AI taxonomy source later on: `ai_taxonomy.is_ai_job`, `primary_specialization`, `secondary_specializations`, `intensity`, `scope_tags`, evidence, and a stable back-compat mapping to legacy `ai_categories`.
7. Rolls out behind shadow-write and live-write flags, with a benchmark harness that bootstraps from 1 human-labeled seed job and grows to a 10-job human gold set before live cutover.

Classification 4.1.2 is not a pipeline redesign. It is a stage upgrade with an explicit long-term migration contract. The preenrich DAG shape is unchanged. No stage is added, removed, reordered, or given new prerequisites beyond what `classification` already has. Short-term, compat ownership of `role_category` remains with `jd_facts`. Long-term, `classification` is the canonical taxonomy source of truth and every other taxonomy-like field becomes a projection from it rather than an independent override.

---

## 2. Scope Ruling

**In scope:**
- `src/preenrich/stages/classification.py` (rewrite of `run`)
- `src/preenrich/stages/blueprint_common.py` (new deterministic taxonomy scoring helpers; `title_family()` is kept only as a fail-open rescue path when taxonomy signal blocks are missing or malformed)
- `src/preenrich/blueprint_models.ClassificationDoc` (schema expansion)
- `src/preenrich/blueprint_prompts.py` (new `build_p_classify` prompt)
- `data/job_archetypes.yaml` (schema expansion: per-category signal lists, disambiguation rules, richer AI taxonomy dimension)
- `src/preenrich/stages/blueprint_assembly.py` (snapshot mirrors richer classification fields; no new compat writes)
- `src/layer6_v2/orchestrator.py` is not modified by 4.1.2, but its AI override behavior is explicitly accounted for in the migration contract and rollout gating
- `src/preenrich/types.py` and `scripts/preenrich_model_preflight.py` (per-stage provider/model config for `classification`)
- `tests/unit/preenrich/` (unit, contract, taxonomy, consumer-compat, benchmark-regression)
- `scripts/benchmark_classification_4_1_2.py` (new benchmark harness)

**Out of scope:**
- Any changes to `jd_facts`, `jd_structure`, `research_enrichment`, `application_surface`, `job_inference`, `cv_guidelines`, `job_hypotheses`, `annotations`, `persona_compat`, `blueprint_assembly` (beyond the snapshot mirror), or the legacy `jd_extraction` / `ai_classification` / `persona` stages.
- Candidate-side logic (persona matching, CV generation, role bullets, variant selection). The `extracted_jd.role_category` compat contract stays as-is.
- Persona behavior. The `orchestrator.py:495-531` AI-gate hack (overriding `extracted_jd.role_category` to `ai_leadership` / `ai_architect`) is not removed by 4.1.2 implementation, but 4.1.2 does define the long-term replacement contract: orchestrator and later consumers must migrate to the richer classification-owned AI taxonomy instead of overriding role category.
- Non-engineering role families. The taxonomy stays engineering-focused (the 8 existing primary categories). Product, design, data-science, security, and support roles are not added here, because the scout/top-jobs search surface is engineering-focused and the CV generation pipeline assumes engineering role archetypes.
- Salary. Salary is outside classification's scope (extraction 4.1.1 closed this).
- Search or selector profile taxonomy expansion beyond what's needed for the richer AI taxonomy dimension. The existing `search_profiles` (`ai_core`, `ai_leadership`, `ai_senior_ic`, `ai_architect`) and `selector_profiles` (`tech-lead`, `architect`, `staff-principal`, `head-director`, `engineering-manager`) stay unchanged.

---

## 3. Current-State Review

### 3.1 What `classification` does today

Source: `src/preenrich/stages/classification.py` (full file ≤60 lines).

1. Reads `jd_facts.merged_view.title` (or falls back to `job_doc.title`).
2. Calls `title_family(title)` — a case-insensitive substring cascade over the 8 primary categories (`blueprint_common.py:136-152`). Substrings: "cto", "vp ... engineering", "head of engineering", "director ... engineering", "manager", "staff|principal|architect", "lead", else `senior_engineer`.
3. Looks up `search_profiles_for_primary`, `selector_profiles_for_primary`, `tone_for_primary` from `data/job_archetypes.yaml`.
4. Calls `ai_relevance(description, title)` — also in `blueprint_common.py:180-194`, regex token scan of "ai", "machine learning", "ml", "llm", "genai", "rag", "agent", "mlops", "llmops". Emits `is_ai_job`, `ai_categories` (one of `ai_general`, `genai_llm`, `mlops_llmops`), `ai_rationale`.
5. Hard-codes `ambiguity_score=0.1` and `secondary_role_categories=[]`.
6. Returns a `ClassificationDoc` as `stage_output` plus a compat `output` patch that writes `is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, and a nested `ai_classification` dict onto `level-2`.

### 3.2 Weaknesses

- **Title-only decision.** `title_family` does not look at responsibilities, qualifications, competency mix, reporting structure, team scope, or even `jd_facts.extraction.role_category` (which exists after extraction 4.1.1). Any JD whose title omits "CTO/VP/Head/Director/Manager/Staff/Principal/Architect/Lead" falls through to `senior_engineer`, including clearly-leadership roles titled "AI Engineering Leader", "Head of AI", "Engineering Lead", "Technical Lead", "Tech Lead, AI Platform", etc.
- **Taxonomy is not load-bearing.** `data/job_archetypes.yaml` is only consulted for `maps_from.search_profiles`, `maps_from.selector_profiles`, `maps_from.tone_families`, `maps_from.ideal_candidate_archetypes`. The decision itself never reads the YAML. Changing the YAML cannot change what `title_family` returns.
- **No disambiguation.** Hard cases that the taxonomy itself admits (see `data/job_archetypes.yaml:28-42` — `tech_lead` vs `staff_principal_engineer` both map from similar selector profiles) are resolved by substring ordering in `title_family`, not by JD content.
- **No secondary categories.** `secondary_role_categories` is always `[]`. The `ClassificationDoc` schema allows it but the stage never populates it, so cases like "Staff Engineer / Tech Lead" or "Engineering Manager with Architect expectations" lose the secondary axis.
- **No confidence or evidence.** `ambiguity_score` is the hard-coded literal `0.1` regardless of JD. `ClassificationDoc` has no `confidence`, no `reason_codes`, no evidence spans. Debugging a wrong classification requires re-reading the JD by hand.
- **AI classification lives in regex.** `ai_relevance` is a token scan that fires on the string "ai" appearing anywhere in the title or description — meaning "Maintaining AI-enabled monitoring" counts equally to "AI Engineering Leader". The 3-way bucket (`ai_general`, `genai_llm`, `mlops_llmops`) is orthogonal to seniority but is flagged onto both the classification artifact and compat fields, competing with the legacy `ai_classification` stage (`src/preenrich/stages/ai_classification.py`, registered in `LEGACY_STAGE_REGISTRY` only when `blueprint_enabled()==False`) that uses `classify_job_document_llm` (`src/services/ai_classifier_llm.py`, Haiku).
- **Compat clobber avoided by removing writes, not by fixing classification.** Extraction 4.1.1 closed the `extracted_jd.role_category` overwrite bug by rule: classification stops patching it. That rule is right, but it leaves `pre_enrichment.outputs.classification.primary_role_category` as thin as the heuristic produced.

### 3.3 How stage output reaches consumers

Stage-output patching is handled by `stage_worker._persist_stage_success_phase_a` (`src/preenrich/stage_worker.py:471-547`). The worker writes:

- `pre_enrichment.outputs.{stage}` from `result.stage_output`
- Top-level `level-2` fields from `result.output` via `set_doc.update(... result.output ...)` at line 522

This means anything `classification` returns under `StageResult.output` is flattened onto the root level-2 document. Today, that's the AI compat fields (`is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification`). Anything `classification` returns under `StageResult.stage_output` lives under `pre_enrichment.outputs.classification`. Extraction 4.1.1's rule is that the stage MUST NOT return `extracted_jd.*` in `result.output`. 4.1.2 preserves that rule.

### 3.4 Ownership reality

| Field | Who writes today | Who should write (4.1.2) |
|---|---|---|
| `level-2.extracted_jd.role_category` | `jd_facts` (per 4.1.1) | `jd_facts` — unchanged |
| `level-2.pre_enrichment.outputs.classification.primary_role_category` | `classification` (heuristic) | `classification` (upgraded taxonomy engine) |
| `level-2.is_ai_job`, `level-2.ai_categories`, `level-2.ai_rationale`, `level-2.ai_classification` | `classification` (regex) + legacy `ai_classification` stage when blueprint off | `classification` (taxonomy-driven, same keys) |
| `level-2.pre_enrichment.job_blueprint_snapshot.classification.*` | `blueprint_assembly` (mirror) | `blueprint_assembly` (mirror of upgraded fields) |
| `level-2.extracted_jd.top_keywords`, `level-2.extracted_jd.ideal_candidate_profile` | `jd_facts` (current owner; `blueprint_assembly` does not patch these today) | `jd_facts` — unchanged |

Classification 4.1.2 does not renegotiate *short-term* ownership. It stays in its current implementation lane: the `classification` artifact and the AI compat fields. The long-term source-of-truth target, however, is explicit: classification becomes the only canonical taxonomy object, and every legacy role/AI compatibility field becomes a projection from it rather than a competing classifier.

### 3.5 Short-term vs long-term taxonomy ownership

**Short-term 4.1.2 boundary**
- `pre_enrichment.outputs.classification` is the canonical taxonomy artifact inside preenrich and blueprint assembly.
- `level-2.extracted_jd.role_category` remains a legacy compatibility field written by `jd_facts`.
- `level-2.is_ai_job`, `level-2.ai_categories`, `level-2.ai_rationale`, `level-2.ai_classification` become compatibility projections derived from the richer classification artifact.
- `src/layer6_v2/orchestrator.py` remains a known legacy exception because it still mutates `extracted_jd.role_category` from the AI compat projection.

**Long-term target**
- `classification` is the global source of truth for role and AI taxonomy.
- `job_blueprint_snapshot.classification` mirrors that source of truth for UI and downstream reads.
- `extracted_jd.role_category`, `is_ai_job`, and `ai_categories` become backward-compatible projections only.
- No downstream component may synthesize, override, or widen role taxonomy independently; they must consume the classification artifact or its snapshot mirror.

---

## 4. Consumer Impact Matrix

Downstream reads grouped by what they depend on. Breaks in this matrix are what constrain the 4.1.2 design.

### 4.1 Readers of `pre_enrichment.outputs.classification.primary_role_category`

| Consumer | File/line | Field(s) read | Break if classification returns a richer but backward-compatible `primary_role_category` (still ∈ 8 taxonomy values)? |
|---|---|---|---|
| `job_inference` stage | `src/preenrich/stages/job_inference.py:26,54` | `classification.primary_role_category` (default `senior_engineer`), `classification.tone_family` (default `hands_on`) | No. Enum widening is not planned; existing 8-value contract is preserved. |
| `cv_guidelines` stage | `src/preenrich/stages/cv_guidelines.py:32` | `job_inference.primary_role_category` (transitive) | No. |
| `blueprint_assembly` snapshot | `src/preenrich/stages/blueprint_assembly.py:58-65` | `classification.primary_role_category`, `secondary_role_categories`, `search_profiles`, `selector_profiles`, `tone_family`, `taxonomy_version` | No. Existing snapshot dict will gain new optional keys (`ai_taxonomy`, `confidence`, `ambiguity_score`, `reason_codes`); no removed keys. |
| Frontend blueprint snapshot tests | `frontend/tests/test_job_detail_blueprint_snapshot.py:43,131,165,199` | `classification.primary_role_category` | No — tests pass `engineering_manager` as literal; additive fields don't break them. |
| `scripts/preenrich_model_preflight.py` | references | provider/model routing for `classification` | No, but the plan adds env plumbing (§8). |

### 4.2 Readers of `level-2.extracted_jd.role_category`

These are unaffected by 4.1.2 because `extracted_jd.role_category` remains `jd_facts`-owned. Listed here so the ownership boundary is explicit.

| Consumer | File/line | Fields read |
|---|---|---|
| Claude CV service | `src/services/claude_cv_service.py:236` | `extracted_jd.role_category` (default `engineering_manager`) |
| Answer generator | `src/services/answer_generator_service.py:313-314` | `extracted_jd.role_category` |
| Role generator (layer6_v2) | `src/layer6_v2/role_generator.py:403,528,751,932,1013,1121` | `extracted_jd.role_category` (default `staff_principal_engineer` or `engineering_manager`) |
| Variant selector | `src/layer6_v2/variant_selector.py:361,605,607,870` | `extracted_jd.role_category` (default `default`) |
| Grader | `src/layer6_v2/grader.py:377,708,835,947` | `extracted_jd.role_category` |
| Skills taxonomy | `src/layer6_v2/skills_taxonomy.py:348` | `extracted_jd.role_category` |
| Ensemble header generator | `src/layer6_v2/ensemble_header_generator.py:278,336,407,463,568` | `extracted_jd.role_category` |
| Improver | `src/layer6_v2/improver.py:200` | `extracted_jd.role_category` |
| Orchestrator AI gate | `src/layer6_v2/orchestrator.py:504-531` | **overwrites** `extracted_jd.role_category` with `ai_leadership` / `ai_architect` when `is_ai_job` is true |
| CV review core | `src/services/cv_review_core.py:315` | `extracted_jd.role_category` |
| Annotation suggester | `src/services/annotation_suggester.py:795` | `extracted_jd.role_category` (via doc description) |
| Layer-7 output publisher | `src/layer7/output_publisher.py:373,785` | logs `extracted_jd.role_category` |
| Best-effort dossier | `runner_service/utils/best_effort_dossier.py:143,148-149` | `extracted_jd.role_category` |
| Job detail template | `frontend/templates/job_detail.html:1581,1583` | `job.extracted_jd.role_category` |
| Batch preview partial | `frontend/templates/partials/batch/_jd_preview_content.html:30-31` | `jd.role_category` |
| JD annotation editor component | `frontend/templates/components/jd_annotation_editor.html:189,192` | `job.extracted_jd.role_category` |
| Extracted JD compact component | `frontend/templates/components/extracted_jd_compact.html:24,26` | `extracted.role_category` |

### 4.3 Readers of the AI compat fields

| Consumer | File/line | Fields read |
|---|---|---|
| Orchestrator AI gate | `src/layer6_v2/orchestrator.py:130,496,513-526` | `is_ai_job`, `ai_categories` |
| CV generation fallback | `src/services/cv_generation_service.py:419-428` | `is_ai_job` (with fallback to running `classify_job_document_llm` if unset) |
| Full extraction service | `src/services/full_extraction_service.py:473-491` | writes `is_ai_job`, `ai_categories`, `ai_rationale`, `ai_classification` |
| Structure JD service | `src/services/structure_jd_service.py:155-166` | writes `is_ai_job` |
| Job ingest service | `src/services/job_ingest_service.py:276` | default seed `is_ai_job: False` |
| Legacy `ai_classification` stage | `src/preenrich/stages/ai_classification.py` | writes `is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification` (only when `blueprint_enabled()==False`) |

### 4.4 Hard requirements from the matrix

1. `classification.primary_role_category` MUST remain one of the 8 `RoleCategory` enum values (`src/layer1_4/claude_jd_extractor.py:43-52`). Adding any new value would break `job_inference`, `cv_guidelines`, and every consumer in §4.2 that falls back on a literal from this enum. AI-specific values (`ai_leadership`, `ai_architect`) must not leak into `primary_role_category`; they live in `classification.ai_taxonomy`, not on the primary role axis. (The orchestrator's AI-gate overwrite of `extracted_jd.role_category` to `ai_leadership`/`ai_architect` is a separate hack; classification 4.1.2 does not feed it and does not attempt to remove it.)
2. `classification` MUST emit the same AI compat keys it emits today (`is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification`). Consumers of those keys in §4.3 must keep working. These root fields are no longer treated as independent classification outputs; they are stable compatibility projections derived from the richer classification-owned AI taxonomy.
3. `classification` MUST NOT write `extracted_jd.role_category`, `extracted_jd.seniority_level`, `extracted_jd.competency_weights`, `extracted_jd.top_keywords`, or `extracted_jd.ideal_candidate_profile` (all §4.2 compat consumers are served by `jd_facts`). The stage's `StageResult.output` dict may only include the AI compat keys described in (2).
4. `blueprint_assembly` MUST keep mirroring `primary_role_category`, `secondary_role_categories`, `search_profiles`, `selector_profiles`, `tone_family`, `taxonomy_version` into `pre_enrichment.job_blueprint_snapshot.classification`. 4.1.2 adds optional keys to that dict (`ai_taxonomy`, `confidence`, `ambiguity_score`, `reason_codes`); it does not remove any.
5. `classification` MUST become the richest AI taxonomy surface in the system. Any later consumer that needs more than `ai_categories` must read `classification.ai_taxonomy` or its snapshot mirror, not invent its own richer AI categorization.

---

## 5. Taxonomy Audit

Source: `data/job_archetypes.yaml:1-180` (version `2026-04-19-v1`).

### 5.1 What the taxonomy covers well

- **Eight-way primary category space across engineering seniority**: `senior_engineer`, `tech_lead`, `staff_principal_engineer`, `engineering_manager`, `director_of_engineering`, `head_of_engineering`, `vp_engineering`, `cto`. This matches `RoleCategory` enum exactly and covers the scout/top-jobs search mix.
- **Mapping metadata**: `maps_from.selector_profiles`, `maps_from.search_profiles`, `maps_from.tone_families`, `maps_from.ideal_candidate_archetypes` are complete and non-conflicting. These are what `blueprint_common.py:155-177` consumes today.
- **Orthogonality statement**: `design_rules:` line 19 says "AI specialization is orthogonal to role seniority and management scope." This is correct and aligns with keeping the richer `ai_taxonomy` separate from `primary_role_category`.
- **Portal families** for `application_surface`, scoped and working.

### 5.2 What the taxonomy lacks — the actual gap

For classification 4.1.2 to be a decision engine, the YAML needs three additions. These are pure schema extensions; no existing field is removed or renamed.

**A. Per-category signal lists.** Today there is no way to score a JD against a category using the taxonomy. The file needs, per primary category:
- `title_signals`: exact-match and substring patterns for titles
- `title_negatives`: patterns that *exclude* a category despite overlap (e.g., "Lead Engineer" contains "engineer" but indicates `tech_lead`, not `senior_engineer`)
- `responsibility_signals`: verb phrases and idioms from `jd_facts.extraction.responsibilities` that push toward this category (e.g., "mentor engineers", "lead team", "architect systems")
- `qualification_signals`: qualification-text phrases (e.g., "10+ years", "experience managing managers")
- `keyword_signals`: domain keywords that lean a category (e.g., "system design", "roadmap", "P&L")
- `competency_anchors`: the `CompetencyWeightsModel` quadrant where the category typically lives (e.g., `engineering_manager` centroid = `{delivery: 20, process: 25, architecture: 15, leadership: 40}`)
- `archetype_signals`: the `CandidateArchetype` values most commonly emitted by `jd_facts` for this category

Scoring is additive with bounded weights; total per-category score is `w_title * title_match + w_resp * resp_match + ... + w_competency * competency_proximity`. Weights and thresholds live in the YAML so operators can retune without a code change.

**B. Disambiguation rules.** The taxonomy file admits that several category pairs overlap (`tech_lead` vs `engineering_manager`, `staff_principal_engineer` vs `tech_lead`, `head_of_engineering` vs `director_of_engineering` vs `vp_engineering`). A new top-level `disambiguation_rules` list encodes the tie-breakers:
- `tech_lead vs engineering_manager` → prefer `engineering_manager` when responsibilities contain "manage people", "performance reviews", "hiring", "headcount"; prefer `tech_lead` when responsibilities contain "set technical direction", "hands-on", "code review"
- `staff_principal_engineer vs tech_lead` → prefer `staff_principal_engineer` when qualifications contain "10+ years" or "principal level" or `jd_facts.extraction.seniority_level == "principal"`
- `head_of_engineering vs vp_engineering vs director_of_engineering` → title-priority rule (`vp` > `head` > `director`) with fallback to `jd_facts.extraction.seniority_level`

Each rule has an `id`, a `when` condition (a simple expression over already-extracted fields), and a `prefer` target. Rules are evaluated after the signal-score pass, only when the top-1 and top-2 scores are within a configurable margin (`disambiguation_margin`, default `0.15`).

**C. Orthogonal AI taxonomy dimension.** Replace the current flat AI regex output with a structured taxonomy block. The taxonomy must be rich enough to serve as the long-term global source of truth for AI-role categorization, while still projecting to the current `ai_categories` compatibility surface.

```yaml
ai_taxonomy:
  specializations:
    none:
      description: "No AI/ML specialization signaled."
      signals: []
      legacy_categories: []
    ai_core:
      description: "Applied ML / AI core IC work."
      signals:
        responsibility_patterns: ["deploy ml", "train models", "fine-tune", "retrieval", "inference", "model evaluation"]
        keyword_patterns: ["pytorch", "tensorflow", "huggingface", "transformers", "llm", "rag"]
        title_patterns: ["ai engineer", "ml engineer", "applied scientist"]
      legacy_categories: [ai_general]
    genai_llm:
      description: "GenAI / LLM product or application work."
      signals:
        keyword_patterns: ["llm", "genai", "prompt engineering", "agentic", "rag", "evaluations", "guardrails"]
      legacy_categories: [ai_general, genai_llm]
    mlops_llmops:
      description: "ML/LLM platform and operations."
      signals:
        keyword_patterns: ["mlops", "llmops", "model serving", "feature store", "vector store", "inference platform"]
      legacy_categories: [ai_general, mlops_llmops]
    ai_leadership:
      description: "AI-focused engineering leadership."
      signals:
        title_patterns: ["head of ai", "director of ai", "vp of ai", "cto ai", "ai engineering leader"]
        leans_primary: [engineering_manager, director_of_engineering, head_of_engineering, vp_engineering, cto]
      legacy_categories: [ai_general]
    ai_architect:
      description: "AI-focused staff/principal or architect IC."
      signals:
        title_patterns: ["ai architect", "ml architect", "principal ai", "staff ai"]
        leans_primary: [staff_principal_engineer, tech_lead]
      legacy_categories: [ai_general]
  intensity_levels: [none, adjacent, significant, core]
  scope_tags:
    - applied_ai
    - genai_product
    - agentic_systems
    - rag
    - model_platform
    - mlops_llmops
    - ai_architecture
    - ai_leadership
    - ai_governance
```

This yields a structured artifact surface:
- `is_ai_job`
- `primary_specialization`
- `secondary_specializations`
- `intensity`
- `scope_tags`
- `legacy_ai_categories`
- evidence-backed rationale

`legacy_ai_categories` is the stable compatibility map to the current root-level `{ai_general, genai_llm, mlops_llmops}` contract. `leans_primary` remains advisory-only; the primary role decision still runs independently so AI specialization does not hijack leadership classification.

### 5.3 What the taxonomy should NOT grow

- **Non-engineering role families** (product, design, data science, security, etc.) are out of scope. The pipeline, CV generation, and scout/selector all assume engineering role archetypes. Adding non-engineering categories would cascade through `variant_selector`, `role_generator`, `grader`, and every layer-6 consumer listed in §4.2, which is outside 4.1.2.
- **Salary bands, comp signals.** Out of scope (extraction-owned, salary out of classification scope).
- **Geography/remote dimension.** `remote_policy` is `jd_facts`-owned; classification does not classify on remote.
- **Seniority as a separate axis on classification.** `jd_facts.extraction.seniority_level` already exists. Classification reads it as an input but does not re-publish it. Adding a `classification.seniority_level` field would duplicate `extracted_jd.seniority_level`.

### 5.4 Versioning

`taxonomy_version` is computed from the YAML's `version:` string (`blueprint_config.taxonomy_version()`). Extending the YAML with the new blocks bumps the version to e.g. `2026-04-20-v2`. This string propagates to `ClassificationDoc.taxonomy_version`, `JobInferenceDoc.taxonomy_version`, `JobBlueprintDoc.taxonomy_version`, and the `job_blueprint` collection unique filter — so V2 classifications are naturally partitioned from V1 in artifact storage. The root enqueuer's `input_snapshot_id` already includes `taxonomy_version` (via `current_input_snapshot_id` in `blueprint_config.py:108-120`), so bumping it will cause in-flight V1 work items to see snapshot drift and cancel themselves, consistent with existing behavior. That is fine for rollout: 4.1.2 targets new-preenrich jobs and explicitly-selected benchmark jobs, not historical backfill.

---

## 6. Target Classification 4.1.2 Architecture

### 6.1 Stage-DAG position

- `classification` stays a separate stage, not folded into `jd_facts`. Folding would couple extraction richness to taxonomy ownership, which 4.1.1 just unwound. It would also remove the natural boundary between "what the JD says" (extraction) and "what the role is" (classification).
- Prerequisite stays `jd_facts` only. No new prerequisite. Classification runs before `research_enrichment`, `application_surface`, `job_inference`, `cv_guidelines`, `blueprint_assembly`. This matches the existing registry in `src/preenrich/stage_registry.py:202-213,241,253`.
- The stage remains single-pass (no post-research refinement). Research is not needed for role-category decisions, and adding a second classification call would double cost and slow the DAG. If future iterations want research-refined secondary categories, that's a follow-up plan.

### 6.2 Decision flow

```
┌─ INPUT: jd_facts.extraction (V2 preferred; falls back to merged_view when V2 absent)
│         + title, company
│         + processed_jd_sections (read-only, optional)
│         + data/job_archetypes.yaml (taxonomy + new signal blocks)
│
├─ STEP 1: deterministic taxonomy pre-score
│   For each of the 8 primary categories:
│     score = Σ w_axis * axis_match(jd_facts, taxonomy.category.signals)
│     where axes = {title, responsibility, qualification, keyword, competency, archetype}
│   Returns sorted [(category, score, evidence_refs)] for all 8.
│   Derive: top1_score, top2_score, margin = top1 - top2
│           ambiguity_score = 1 - clamp(margin, 0, 1)
│
├─ STEP 2: apply disambiguation rules
│   If margin < disambiguation_margin:
│     For each rule whose `when` matches the top-1/top-2 pair AND evaluates true:
│       swap top-1/top-2 per rule.prefer
│       append reason_code = rule.id
│   Recompute margin.
│
├─ STEP 3: agreement check with jd_facts
│   jd_facts_role = jd_facts.extraction.role_category (if present)
│   agrees = (jd_facts_role == top1.category)
│   If NOT agrees AND top1 in {top1, top2}:
│     mark disagreement in evidence; keep classification's top-1 but lower confidence
│
├─ STEP 4: LLM short-circuit decision
│   If top1_score >= high_confidence_threshold (default 0.60)
│      AND margin >= short_circuit_margin (default 0.20)
│      AND agrees == true:
│     confidence = "high"
│     skip LLM  →  go to STEP 6
│   Else:
│     invoke LLM (STEP 5)
│
├─ STEP 5: bounded LLM reasoning
│   Prompt: P-classify:v1 (see §7)
│   Inputs: pre-score distribution (top-3 with evidence), jd_facts extraction summary,
│           raw JD excerpt (compact head+tail), taxonomy definitions, disambiguation rules
│   Output schema: {
│     primary_role_category: RoleCategory,
│     secondary_role_categories: list[RoleCategory],   # 0..2
│     confidence: "high"|"medium"|"low",
│     reason_codes: list[str],
│     evidence: list[{signal, quote, locator}],
│     ai_taxonomy: {
│       is_ai_job: bool,
│       primary_specialization: AISpecialization | null,
│       secondary_specializations: list[AISpecialization],
│       intensity: "none"|"adjacent"|"significant"|"core",
│       scope_tags: list[AIScopeTag],
│       legacy_ai_categories: list[str],
│       rationale: str | null,
│     },
│     disagreement_with_jd_facts: str | null
│   }
│   Validated against Pydantic.
│
├─ STEP 6: AI taxonomy pass
│   Deterministic taxonomy scan for AI specialization, intensity, and scope tags (§5.2-C).
│   If LLM ran, merge its ai_taxonomy with deterministic tags; deterministic compat mapping wins on legacy fields.
│   Emit ai_categories compat list from ai_taxonomy.legacy_ai_categories,
│   is_ai_job = ai_taxonomy.is_ai_job, ai_rationale = ai_taxonomy.rationale (≤240 chars).
│
├─ STEP 7: emit ClassificationDoc + compat projections
│   stage_output → pre_enrichment.outputs.classification
│   result.output → level-2.{is_ai_job, ai_categories, ai_category_count, ai_rationale, ai_classification}
│   NO write to level-2.extracted_jd.*
└─
```

### 6.3 Deterministic vs LLM split

- **Steady state (expected majority path):** deterministic pre-score + disambiguation + jd_facts agreement + deterministic AI specialization. Zero LLM calls. This matters because the preenrich DAG runs this stage for every preenriched job; paying an LLM per job would dominate classification cost.
- **LLM-invoked path:** pre-score ambiguous, OR disagreement with `jd_facts`, OR pre-score below confidence threshold. One LLM call, bounded output schema.
- **Deterministic-only never happens when `jd_facts` disagrees.** A silent disagreement would hide a classification problem behind a "high confidence" label, which is worse than the current title heuristic. Disagreement always escalates to LLM reasoning for an explicit resolution.

### 6.4 Inputs, exactly

- **Primary inputs (required):**
  - `jd_facts.extraction` when present — full runner-parity extraction (role_category, seniority_level, competency_weights, responsibilities, qualifications, top_keywords, ideal_candidate_profile.archetype, success_metrics)
  - `jd_facts.merged_view` as fallback — used when `jd_facts.extraction` is `None` (V1 jd_facts or partial V2 failure)
  - `title`, `company` from `level-2`
  - `data/job_archetypes.yaml` via `load_job_taxonomy()`
- **Secondary inputs (optional, read-only):**
  - `processed_jd_sections` from `jd_structure.processed_jd_sections` or `level-2.processed_jd_sections` — used only by the LLM prompt when invoked, to let it cite evidence spans; never used to change the deterministic score
  - `level-2.description` — used only in the LLM excerpt envelope
- **Not used:**
  - `research_enrichment` (adds cost, would force a DAG reorder, not needed for role-category decisions)
  - `application_surface` (portal/URL, irrelevant to role classification)
  - `job_inference`, `cv_guidelines`, `job_hypotheses`, `annotations`, `persona_compat` (downstream stages, prerequisite violation)

### 6.5 Outputs, exactly

`ClassificationDoc` schema expansion (backwards-compatible — existing keys stay; new keys are optional with safe defaults):

```
class ClassificationDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_role_category: str             # unchanged, one of 8 RoleCategory values
    secondary_role_categories: list[str]   # unchanged; now 0..2 populated
    search_profiles: list[str]             # unchanged (from taxonomy.maps_from)
    selector_profiles: list[str]           # unchanged
    tone_family: str                       # unchanged
    taxonomy_version: str                  # unchanged

    # Existing fields that stop being dummies
    ambiguity_score: float                 # derived from pre-score margin (0..1)
    ai_relevance: dict[str, Any]           # retained as a legacy serialized view of ai_taxonomy

    # New fields (all optional with defaults for back-compat)
    confidence: Literal["high", "medium", "low"] = "medium"
    reason_codes: list[str] = Field(default_factory=list)
    evidence: list[ClassificationEvidence] = Field(default_factory=list)
    ai_taxonomy: AITaxonomyDoc | None = None
    jd_facts_agreement: JdFactsAgreement | None = None
    pre_score: list[PreScoreEntry] = Field(default_factory=list)   # top-3 only, for debuggability
    decision_path: Literal["deterministic", "deterministic_disambiguated", "llm"] = "deterministic"
    model_used: str | None = None
    provider_used: str | None = None
    prompt_version: str | None = None      # e.g. "P-classify:v1"
```

New sub-models:

```
class ClassificationEvidence(BaseModel):
    signal: str                          # e.g. "responsibility_signal:mentor_engineers"
    source: Literal["title", "responsibility", "qualification", "keyword",
                    "competency", "archetype", "jd_facts", "processed_section", "llm"]
    quote: str | None = None
    locator: str | None = None

class JdFactsAgreement(BaseModel):
    jd_facts_role_category: str | None
    classification_role_category: str
    agrees: bool
    disagreement_reason: str | None = None

class PreScoreEntry(BaseModel):
    category: str                        # one of 8
    score: float
    axis_contributions: dict[str, float] # title, responsibility, keyword, ...

class AITaxonomyDoc(BaseModel):
    is_ai_job: bool = False
    primary_specialization: str | None = None
    secondary_specializations: list[str] = Field(default_factory=list)
    intensity: Literal["none", "adjacent", "significant", "core"] = "none"
    scope_tags: list[str] = Field(default_factory=list)
    legacy_ai_categories: list[str] = Field(default_factory=list)
    rationale: str | None = None
```

Compat `result.output` (root level-2 patch) — only the AI fields, as today:

```python
{
    "is_ai_job": bool(ai_categories),
    "ai_categories": list[str],                    # subset of {ai_general, genai_llm, mlops_llmops}
    "ai_category_count": int,
    "ai_rationale": str,
    "ai_classification": {
        "is_ai_job": bool,
        "ai_categories": list[str],
        "ai_category_count": int,
        "ai_rationale": str,
        "taxonomy_version": str,
    },
}
```

Classification 4.1.2 does not add new root-level compat keys. The richer AI taxonomy lives in the artifact and the snapshot; the legacy AI root keys are explicit projections from it. Short-term, `orchestrator.py` and other legacy consumers still read the root keys. Long-term, they must migrate to the classification artifact or its snapshot mirror.

### 6.6 Blueprint assembly mirror

`blueprint_assembly.py:58-65` already mirrors classification fields into the snapshot. The mirror is extended to include the new optional keys:

```
snapshot.classification = {
    "primary_role_category": ...,
    "secondary_role_categories": [...],
    "search_profiles": [...],
    "selector_profiles": [...],
    "tone_family": ...,
    "taxonomy_version": ...,
    # new:
    "ai_taxonomy": {...},
    "confidence": ...,
    "ambiguity_score": ...,
    "reason_codes": [...],
}
```

`blueprint_assembly` does not gain any new compat writes. It remains thin. §11 pins this with tests.

### 6.7 Fail-open behavior

Classification 4.1.2 must fail open, not fail closed.

- If the new taxonomy signal blocks are missing for one or more categories, classification does not abort the job.
- The stage records `reason_codes=["taxonomy_signal_block_missing"]`, sets `confidence="low"`, and falls back to the best available reduced-signal path:
  1. deterministic scoring over whatever signal blocks are present
  2. `jd_facts.extraction.role_category` prior if available
  3. `title_family()` as the final rescue heuristic
- Fail-open fallback still emits a valid `ClassificationDoc` and valid AI compat projection so the DAG can continue.
- The benchmark harness and tests treat this path as degraded quality, not as a success path for sign-off.

---

## 7. Prompt Strategy

### 7.1 New prompt `P-classify:v1`

Built in `src/preenrich/blueprint_prompts.build_p_classify`. The prompt is invoked only when the deterministic path cannot make a high-confidence decision.

Structure:
- **System contract:** JSON-only output, pinned by field names matching `ClassificationDoc` (see §6.5). Forbids markdown, prose, or extra keys.
- **Taxonomy grounding block:** renders the 8 primary categories from `data/job_archetypes.yaml` with their summaries, plus the relevant disambiguation rule snippets filtered to the top-2 pair in contention.
- **Deterministic pre-score block:** the top-3 scored categories with their axis contributions and evidence refs, so the LLM sees what the scorer already concluded.
- **Extraction block:** `jd_facts.extraction.role_category`, `seniority_level`, `competency_weights`, `responsibilities[:8]`, `qualifications[:8]`, `ideal_candidate_profile.archetype`, top 10 `top_keywords`. This replaces the old "title only" context.
- **JD excerpt envelope:** section-aware packing when `processed_jd_sections` is available (responsibilities + requirements + about_company slices), otherwise head+tail compaction of `level-2.description` (reuses the existing `_compact_raw_jd` helper pattern from `jd_facts.py:116`).
- **AI taxonomy block:** the `ai_taxonomy` taxonomy block with specialization signals, intensity levels, scope tags, and legacy mapping guidance.
- **Decision guidance:**
  - Prefer the pre-score top-1 unless specific evidence supports an override.
  - If top-1 disagrees with `jd_facts.extraction.role_category`, give an explicit reason in `disagreement_with_jd_facts`.
  - Keep `primary_role_category` strictly within the 8-value enum.
  - `secondary_role_categories` ≤ 2, no self-duplicate.
  - `ai_taxonomy.primary_specialization` must come from the taxonomy's AI block, with `secondary_specializations` carrying any additional tags.
- **Guardrails:**
  - Reject inputs referencing `job_hypotheses` (reuse existing `_reject_hypotheses_payload` guard)
  - Reject inputs referencing `research_enrichment` (research must not leak into classification)
  - Output must be valid JSON conforming to the schema; the stage catches validation errors and retries once (see §8).

### 7.2 Prompt versioning

- `PROMPT_VERSION = "P-classify:v1"` stored in `ClassificationDoc.prompt_version` (new field) and in `pre_enrichment.stage_states.classification.prompt_version` via existing stage-worker wiring (`stage_worker.py:507`).
- Bumping the prompt version causes pre-score-driven LLM invocations to use the new prompt. Deterministic-path decisions carry the same `prompt_version` string to indicate the taxonomy schema they were scored against.

### 7.3 Prompt tests

See §11.2 for the test list. The critical ones:
- Contract test: prompt contains all 8 primary category slugs and all AI taxonomy specialization slugs.
- Schema-presence test: prompt mentions every required output key of the Pydantic output schema.
- Hypothesis-leak guard test: rendering with a payload referencing `job_hypotheses` raises.
- Golden snapshot test: frozen JD + frozen pre-score produce byte-identical prompt.

### 7.4 One prompt, not two

There is no separate "judge" prompt. The deterministic pre-score is the first pass; the LLM's role is reasoning over that pass, not a second-opinion audit of an LLM-first extraction. This matches the 4.1.1 decision to drop `P-jd-judge`.

---

## 8. Model Routing Strategy

### 8.1 Default and escalation

| Pass | Default provider/model | Fallback | Rationale |
|---|---|---|---|
| Deterministic pre-score | none | none | Pure Python over taxonomy YAML |
| LLM reasoning (invoked on ambiguity or disagreement) | codex `gpt-5.4-mini` | codex `gpt-5.4`, then claude `claude-haiku-4-5` | Cheap default; escalate only on schema failure or repeated low-confidence disagreement |
| Deterministic AI specialization | none | none | Taxonomy-driven regex/keyword scan |

Rationale for the defaults:
- Classification is a ≤8-class decision over already-structured inputs (extraction exists, taxonomy is known). `gpt-5.4-mini` is well within capacity for this, as evidenced by its role as the `jd_facts` primary in extraction 4.1.1, which is a harder task.
- Claude fallback is `claude-haiku-4-5` (not Sonnet), because classification is simpler than extraction and Haiku is the cheapest compliant path. Sonnet would be over-spec for a taxonomy-grounded 8-way decision.
- Escalation to `gpt-5.4` triggers only on schema-validation failure or on a failed Codex attempt, not on ambiguity alone. Ambiguity is handled by giving the mini model the pre-score evidence in the prompt.

### 8.2 Per-stage env plumbing

Add to `src/preenrich/types.py` config resolver and to `infra/env/scout-workers.env.example`:

- `PREENRICH_PROVIDER_CLASSIFICATION` (default `codex`)
- `PREENRICH_MODEL_CLASSIFICATION` (default `gpt-5.4-mini`)
- `PREENRICH_FALLBACK_PROVIDER_CLASSIFICATION` (default `claude`)
- `PREENRICH_FALLBACK_MODEL_CLASSIFICATION` (default `claude-haiku-4-5`)
- `PREENRICH_CLASSIFICATION_ESCALATE_ON_FAILURE_ENABLED` (default `true`)
- `PREENRICH_CLASSIFICATION_ESCALATION_MODEL` (default `gpt-5.4`)
- `PREENRICH_CLASSIFICATION_HIGH_CONFIDENCE_THRESHOLD` (default `0.60`)
- `PREENRICH_CLASSIFICATION_SHORT_CIRCUIT_MARGIN` (default `0.20`)
- `PREENRICH_CLASSIFICATION_DISAMBIGUATION_MARGIN` (default `0.15`)

`scripts/preenrich_model_preflight.py` gains assertions that these names are set before worker startup (mirrors the existing `jd_facts` preflight from 4.1.1).

### 8.3 Cost envelope

- Steady-state expectation: the majority of jobs skip the LLM entirely. Taxonomy-driven pre-scoring with `jd_facts.extraction` as input should produce margin ≥ 0.20 for the vast majority of engineering-titled jobs because `jd_facts.extraction.role_category` already provides a strong prior. The benchmark in §9 will measure the actual skip rate; if it is below ~60% the thresholds should be retuned, not the model upgraded.
- LLM-path jobs pay one `gpt-5.4-mini` call; escalation to `gpt-5.4` only on schema failure.
- Claude fallback is budgeted only when Codex is unreachable.

---

## 9. Benchmark / Eval Plan

### 9.1 Corpus selection

Reuse the extraction 4.1.1 benchmark corpus (`reports/extraction_4_1_1_benchmark_corpus.json`) as the base, extended with explicit classification labels.

- **Smoke corpus**: 20 jobs (the extraction 4.1.1 smoke set). Used for rapid prompt iteration and deterministic threshold tuning.
- **Seed gold set**: 1 fully human-labeled job used first to wire the harness, validate schema shape, and confirm prompt/evidence quality before broader labeling starts.
- **Sign-off corpus**: 50 jobs covering all 8 `RoleCategory` values (≥3 per category). 10 of these are a **classification gold set** with human-labeled `primary_role_category`, `secondary_role_categories`, `ai_taxonomy.primary_specialization`, `ai_taxonomy.intensity`, and `confidence` annotations.
- **Ambiguity corpus**: 10 deliberately-ambiguous jobs (dual titles like "Tech Lead / Engineering Manager", "Staff Engineer or Architect", "Head/Director of AI Engineering"). Human-labeled for the expected resolved category *and* the expected ambiguity score range.

Selection rules for sign-off + ambiguity corpora:
- `extracted_jd` and `jd_facts` both exist (so classification gets full input richness)
- At least 3 jobs per `RoleCategory`
- At least 4 jobs with `is_ai_job=true` spanning `ai_core`, `genai_llm`, `mlops_llmops`, `ai_leadership`, `ai_architect` (from legacy classification)
- At least 3 non-English / MENA-region jobs to stress the deterministic pre-score against locale variance
- At least 3 jobs where `jd_facts.extraction.role_category` is known to disagree with the runner-era `extracted_jd.role_category` (identified via a one-off Mongo query during corpus construction)

### 9.2 Harness

New script `scripts/benchmark_classification_4_1_2.py` (patterned on `scripts/benchmark_extraction_4_1_1.py`):

1. Load corpus.
2. For each job, build a `StageContext` and run `ClassificationStage.run` against a fresh doc; write to a throwaway `classification_benchmark` collection and local JSON.
3. Compare classification output against:
   - the gold label (when available)
   - `jd_facts.extraction.role_category` (for agreement rate)
   - the legacy `classification.primary_role_category` (for drift analysis during cutover)
4. Emit a per-job report + aggregate scorecard.

### 9.3 Metrics

- **Primary category accuracy** (exact match vs gold label): on the 10-job gold set, and separately on the sign-off 50
- **Secondary category recall** (is at least one of the human-labeled secondaries present in output): gold set only
- **Ambiguity-detection recall** (for human-labeled ambiguous jobs, does `ambiguity_score` ≥ 0.5?): ambiguity corpus
- **Agreement with `jd_facts.extraction.role_category`** on the full sign-off corpus (expected high; divergences are reviewed manually)
- **AI primary-specialization precision/recall** on gold set
- **AI intensity exact-match** on gold set
- **Deterministic-path skip rate** (jobs classified without LLM invocation): target ≥ 60% on the non-ambiguity corpus
- **LLM-path duration p95** (prompt-to-parse wall time)
- **Schema validity** (100% required; classification doc must be Pydantic-valid for every job)

### 9.4 Acceptance thresholds

| Metric | Threshold |
|---|---|
| Schema validity | 100% |
| Gold-set primary-category exact-match | ≥ 80% |
| Gold-set top-2 recall (gold ∈ {top-1, top-2}) | ≥ 95% |
| Ambiguity-corpus ambiguity_score ≥ 0.5 | ≥ 80% |
| Sign-off corpus agreement with `jd_facts.extraction.role_category` | ≥ 85% |
| Deterministic-path skip rate on non-ambiguity corpus | ≥ 60% |
| AI primary-specialization recall on AI-labeled gold | ≥ 80% |
| AI intensity exact-match on AI-labeled gold | ≥ 70% |
| Drift vs legacy classifier (changed `primary_role_category` count) on sign-off 50 | must be analyzed per job; no absolute threshold (expected changes are improvements) |
| LLM-path duration p95 | ≤ 6 s |

Smoke corpus (20 jobs) is a diagnostic, not a hard gate — too small for claims at these precisions. The 1-job seed gold case is also diagnostic only; no live cutover happens until the full 10-job gold set exists.

If thresholds fail, iterate on taxonomy signals and prompt. Do not lower the bar. Do not escalate default model to `gpt-5.4`; the correct fix is either a better signal list in the YAML or a better prompt.

### 9.5 Regression hedge

Wire a 3-job mini corpus into CI as a regression test for the deterministic scorer; the LLM path is mocked in CI. Full corpus runs manually on taxonomy or prompt version bumps.

---

## 10. Test Plan

### 10.1 Unit tests

- `tests/unit/preenrich/test_stage_classification.py` (rewrite of whatever exists; `tests/unit/preenrich/test_blueprint_stages.py` partially covers this today and is split out for clarity)
  - deterministic pre-score: taxonomy with seeded signals produces expected distribution for a fixture JD
  - disambiguation rule: `tech_lead` vs `engineering_manager` with "manage people" responsibility resolves to `engineering_manager`
  - short-circuit: high-confidence + agreement → decision_path == "deterministic", zero LLM calls (assert via mock)
  - ambiguity: low-margin pre-score → LLM invoked; LLM result merged with pre-score evidence
  - disagreement with `jd_facts`: even if pre-score margin is wide, LLM path is taken
  - LLM schema-validation failure → retries on `gpt-5.4` once, then falls back to deterministic top-1 with confidence="low"
  - AI specialization: detects `ai_core` + `genai_llm` on a GenAI-heavy JD; detects `ai_leadership` on a "Head of AI" title
  - `ClassificationDoc` emit: all new fields present with correct defaults
  - Compat output: `is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification` emitted; NO `extracted_jd.*` keys emitted

- `tests/unit/preenrich/test_build_p_classify.py` (new)
  - Contract: prompt contains all 8 primary category slugs, all 6 AI specialization slugs, JSON-only directive
  - Schema presence: every required output key referenced
  - Hypothesis-leak guard: payload containing `job_hypotheses` raises
  - Research-leak guard: payload containing `research_enrichment` raises
  - Golden snapshot: rendered prompt for a frozen seed JD + pre-score matches stored fixture

- `tests/unit/preenrich/test_taxonomy_signals.py` (new)
  - YAML loads successfully with the new signal blocks
  - Every primary category has a `title_signals` list (even if empty — presence is the contract)
  - Every `ai_taxonomy.specializations` entry has a `signals` block
  - Every `disambiguation_rules` entry has `id`, `when`, `prefer`
  - Version string matches expected pattern `YYYY-MM-DD-vN`

- `tests/unit/preenrich/test_classification_scoring.py` (new)
  - Per-axis scoring helpers (title match, responsibility match, keyword match, competency proximity) produce deterministic scores on fixture JDs
  - `ambiguity_score` derivation: margin=0.5 → score=0.5; margin=0.0 → score=1.0
  - Disambiguation pipeline is order-independent for non-overlapping rules
  - `short_circuit_margin` and `disambiguation_margin` thresholds honored

- `tests/unit/preenrich/test_model_preflight_routing.py` (update)
  - Asserts `PREENRICH_PROVIDER_CLASSIFICATION`, `PREENRICH_MODEL_CLASSIFICATION`, `PREENRICH_FALLBACK_PROVIDER_CLASSIFICATION`, `PREENRICH_FALLBACK_MODEL_CLASSIFICATION` routing is validated

### 10.2 Consumer-compat tests

`tests/unit/preenrich/test_classification_consumer_compat.py` (new):

- Given a V2 `ClassificationDoc`, assert:
  - `job_inference.run` reads `primary_role_category` and `tone_family` without KeyError
  - `cv_guidelines.run` renders without error
  - `blueprint_assembly.run` produces a snapshot whose `classification.primary_role_category` matches
  - Frontend blueprint snapshot fixtures still pass (assert the existing test suite `frontend/tests/test_job_detail_blueprint_snapshot.py` is unchanged)
  - `orchestrator._should_include_ai_section` / AI gate (`src/layer6_v2/orchestrator.py:130,496-531`) reads `is_ai_job` and `ai_categories` from the compat projection without error — both the `ai_leadership` and `ai_architect` gate branches still fire when appropriate
  - `cv_generation_service` `is_ai_job` fallback path (`src/services/cv_generation_service.py:419-428`) still works (i.e., `is_ai_job` is set so the fallback isn't triggered)

### 10.3 Overwrite-protection tests

`tests/unit/preenrich/test_classification_overwrite_protection.py` (new):

- Classification stage output does NOT contain `extracted_jd`, `extracted_jd.role_category`, `extracted_jd.top_keywords`, `extracted_jd.ideal_candidate_profile`, or any other `extracted_jd.*` key
- After `classification` runs over a `level-2` doc with pre-existing `extracted_jd.role_category` set by `jd_facts`, `level-2.extracted_jd.role_category` is unchanged
- `blueprint_assembly.run` output does NOT patch `extracted_jd.top_keywords` or `extracted_jd.ideal_candidate_profile` (pins the 4.1.1 rule)

### 10.4 Benchmark harness tests

`tests/unit/scripts/test_benchmark_classification_4_1_2.py` (new):

- Harness loads a 2-job mini corpus
- Computes metrics correctly for a seeded fake classifier
- Asserts acceptance thresholds (pass/fail)

### 10.5 Integration / DAG

Existing `tests/unit/preenrich/test_stage_worker.py` and `test_dag.py` cover wiring. Add:
- `classification` still depends only on `jd_facts`
- V2 taxonomy_version propagates to `ClassificationDoc`, `JobInferenceDoc`, `JobBlueprintDoc`
- `stage_worker._persist_stage_success_phase_a` patches the expected compat keys onto `level-2` and nothing else

### 10.6 No-loss contract tests

`tests/unit/preenrich/test_classification_no_loss.py` (new):

- Every field currently present in the classification stage_output is still present in V2 output
- AI compat fields (`is_ai_job`, `ai_categories`, `ai_category_count`, `ai_rationale`, `ai_classification`) continue to be emitted at the root level for consumers in §4.3

### 10.7 Prompt regression

- `tests/unit/preenrich/test_classification_golden_prompt.py`: snapshot test for `P-classify:v1` on a seed pre-score + JD. Intentional edits bump the snapshot; drift fails CI.

---

## 11. Migration / Rollout Plan

### 11.1 Feature flags

Four flags, narrowly scoped:

- `PREENRICH_CLASSIFICATION_V2_ENABLED` — enables the new classifier. When false, `classification` falls back to the current `title_family` + `ai_relevance` path.
- `PREENRICH_CLASSIFICATION_SHADOW_MODE_ENABLED` — when both `V2_ENABLED=true` and `SHADOW_MODE_ENABLED=true`, the V2 classifier runs and writes `pre_enrichment.outputs.classification_shadow` (a sibling artifact), while the V1 path continues to write `pre_enrichment.outputs.classification`. This lets us shadow-benchmark on live traffic without changing any downstream consumer reads.
- `PREENRICH_CLASSIFICATION_AI_TAXONOMY_ENABLED` — emits the richer `ai_taxonomy` block on the artifact and snapshot. Off by default until the orchestrator migration contract is validated on canary.
- `PREENRICH_CLASSIFICATION_V2_AI_COMPAT_WRITE_ENABLED` — allows V2 to replace the live root AI compat projection (`is_ai_job`, `ai_categories`, `ai_rationale`, `ai_classification`). When false, V2 may still run and write the artifact/snapshot in shadow without changing orchestrator-facing behavior.

Flag validation (in `blueprint_config.validate_blueprint_feature_flags`):
- Shadow mode requires V2 enabled
- V2 enabled requires `PREENRICH_PROVIDER_CLASSIFICATION` configured
- V2 AI compat write requires V2 enabled and shadow mode disabled

### 11.2 Version bumps

- `PROMPT_VERSION = "P-classify:v1"`
- `taxonomy_version = "2026-04-20-v2"` (bumped when the YAML gets the new signal blocks)
- `ClassificationDoc` schema grows (extra fields), `extra="forbid"` retained — adding keys is explicit

Because `current_input_snapshot_id` includes `taxonomy_version` (`blueprint_config.py:108-120`), jobs in flight at the moment of taxonomy bump will see snapshot drift, and their `classification` work items will cancel with `snapshot_changed`. That's fine — the root enqueuer or operator re-selects those jobs, and they pick up V2. No retroactive backfill is forced.

### 11.3 Rollout phases

**Phase A — dark launch** (code merged, flags off): taxonomy YAML extended, new helpers added, new prompt added, new tests pass. Production still runs V1.

**Phase B0 — seed gold**: label 1 seed job by hand, run the harness end-to-end, verify that `ClassificationDoc`, `ai_taxonomy`, and the legacy AI compat projection all look correct.

**Phase B1 — bench**: grow the human gold set to 10 jobs, run the §9 benchmark harness locally against the smoke corpus and sign-off corpus, iterate signals and prompt. Iterate until thresholds pass. Do not enable any live-write flag until the 10-job gold set meets threshold.

**Phase C — shadow write** (`V2_ENABLED=true`, `SHADOW_MODE_ENABLED=true` on a small canary cohort via `PREENRICH_DAG_CANARY_ALLOWLIST` / `PREENRICH_DAG_CANARY_PCT`): V2 runs side-by-side with V1; both artifacts written to `pre_enrichment.outputs.classification` (V1) and `pre_enrichment.outputs.classification_shadow` (V2). Root AI compat fields remain V1 while shadow mode is on. Collect 72h of drift data:
  - agreement rate between V1 and V2
  - per-category movement counts
  - LLM-invocation rate in practice (sanity-check against expected ≥60% skip)
  - AI compat drift vs live orchestrator behavior

**Phase D — live artifact cutover on canary** (`V2_ENABLED=true`, `SHADOW_MODE_ENABLED=false`, `V2_AI_COMPAT_WRITE_ENABLED=false` on canary): V2 writes `pre_enrichment.outputs.classification` directly; V1 is bypassed for the artifact only. Root AI compat fields remain V1. Watch:
  - `job_inference` / `cv_guidelines` / `blueprint_assembly` for errors or empty outputs
  - job-detail snapshot rendering of richer classification fields

**Phase E — live AI compat cutover on canary** (`V2_AI_COMPAT_WRITE_ENABLED=true`): V2 now also emits the live root AI compat fields using taxonomy-driven computation. Watch:
  - orchestrator AI gate behavior (`src/layer6_v2/orchestrator.py:495-531`)
  - CV generation fallback path (`src/services/cv_generation_service.py:419-428`)
  - Langfuse spans for classification duration and cost

**Phase F — widen canary**: 25% → 50% → 100% with a minimum 72h soak at each step.

**Phase G — default-on**: set `PREENRICH_CLASSIFICATION_V2_ENABLED=true` and `PREENRICH_CLASSIFICATION_V2_AI_COMPAT_WRITE_ENABLED=true` as defaults in `infra/env/scout-workers.env.example`. V1 code remains as a recovery toggle.

**Phase H — source-of-truth completion (follow-up plan, informed by 4.1.2 findings)**: migrate orchestrator, layer6 role consumers, and UI surfaces from legacy `extracted_jd.role_category` / `ai_categories` assumptions to the classification snapshot. Remove the orchestrator AI override, make classification the only taxonomy source of truth, then retire `title_family` fallback and the regex-era AI logic.

### 11.4 Compatibility invariants during rollout

- `pre_enrichment.outputs.classification.primary_role_category` MUST remain ∈ 8 `RoleCategory` values in both V1 and V2. Tests pin this.
- `level-2.is_ai_job` / `ai_categories` / `ai_rationale` / `ai_classification` MUST continue to be written by `classification` when live AI compat writes are enabled. In V2 they are derived from `classification.ai_taxonomy`, not from standalone regex. Consumer tests pin the shape and mapping.
- `classification` MUST NOT write `extracted_jd.*` keys. §10.3 tests pin this.
- `blueprint_assembly` snapshot MUST include all classification keys the UI currently renders.
- `classification.ai_taxonomy` MUST be richer than `ai_categories`; `ai_categories` is a compatibility view, not the canonical AI taxonomy.

### 11.5 Rollback

- If live AI compat writes are enabled, first flip `PREENRICH_CLASSIFICATION_V2_AI_COMPAT_WRITE_ENABLED=false` to restore V1 AI compat behavior while leaving the V2 artifact available for inspection.
- Flip `PREENRICH_CLASSIFICATION_V2_ENABLED=false` to restore V1 behavior entirely. Shadow artifacts written so far remain inspectable.
- No Mongo edits required. No schema downgrade.
- Taxonomy YAML version does not need to be reverted; V1 never read the new signal blocks, so they are inert.

### 11.6 Historical jobs

- 4.1.2 does not retroactively reclassify existing `cv_ready` jobs. Operators can re-select specific jobs if needed.
- The benchmark harness runs V2 in isolation and does not touch production `level-2` state.

---

## 12. Risks And Open Questions

Real risks grounded in the repo:

- **Signal-list bootstrapping.** The new per-category signal lists in `data/job_archetypes.yaml` are only as good as the seed content. If they are written once and never revisited, the deterministic pre-score will stagnate. Mitigation: keep the benchmark harness in CI (small mini-corpus) so signal changes are scored immediately; treat the YAML as a first-class artifact with per-change PR review.
- **Drift with `jd_facts.extraction.role_category`.** `jd_facts` has its own LLM-based role-category decision (via `JD_EXTRACTION_SYSTEM_PROMPT` rules surfaced into the V2 schema). If `jd_facts` and `classification` repeatedly disagree on the same job shape, the correct fix may be in either stage or in the shared taxonomy — not necessarily in `classification`. Mitigation: the `jd_facts_agreement` field records disagreements; Phase C shadow data surfaces systematic drift before cutover.
- **Orchestrator AI hack inertia.** `orchestrator.py:495-531` overwrites `extracted_jd.role_category` with `ai_leadership` / `ai_architect` for AI jobs, a value that is NOT a valid `RoleCategory` enum member. Classification 4.1.2 introduces the richer `ai_taxonomy` replacement, but the runtime orchestrator migration is a follow-up phase. Until then, classification may be the canonical taxonomy artifact while the orchestrator remains a legacy consumer that still mutates compat state.
- **Deterministic-path skip rate lower than expected.** If fewer than 60% of jobs skip the LLM, the cost envelope expands. Mitigation: threshold retuning in Phase B, not model upgrade. If structurally unavoidable (e.g., scout corpus is unusually ambiguous), accept a lower skip rate but keep `gpt-5.4-mini` as default.
- **Taxonomy version bump cancels in-flight jobs.** Bumping `taxonomy_version` changes `input_snapshot_id`, causing in-flight work items to cancel as `snapshot_changed`. That is consistent with existing behavior but means coordinating the bump with queue drain, not during a traffic spike. Mitigation: bump during a low-traffic window.
- **Ambiguity corpus is small.** 10 ambiguous jobs is a weak basis for claiming broad ambiguity detection. Mitigation: treat the threshold in §9.4 as a diagnostic, not a precise measurement; expand corpus if needed between Phase B and Phase E.
- **AI taxonomy alias drift.** The legacy compat categories (`ai_general`, `genai_llm`, `mlops_llmops`) are a lossy projection of the richer AI taxonomy. Risk: consumers overfit to the lossy view and never migrate. Mitigation: document the mapping explicitly, pin it with tests, and make the classification artifact/snapshot the published long-term source of truth.
- **Fail-open overuse.** If taxonomy signal blocks are missing too often, the pipeline may silently lean on `title_family()` and degrade back toward V1 behavior. Mitigation: emit explicit `reason_codes`, benchmark the fallback rate, and block rollout if fail-open triggers above an agreed threshold.

Closed decisions for 4.1.2:

- **Classification stays a separate stage.** Folding into `jd_facts` was considered and rejected — 4.1.1 just finished separating ownership; re-merging duplicates extraction-richness coupling.
- **Short-term compat ownership of `extracted_jd.role_category` stays with `jd_facts`.** 4.1.2 does not move the live compat writer. Long-term, classification becomes the canonical taxonomy source and `extracted_jd.role_category` becomes a projection derived from it after downstream migration.
- **Classification is single-pass, pre-research.** Two-phase (pre + post research) was considered and rejected — research does not change role category in practice; the benefit is not worth a DAG reorder.
- **Taxonomy YAML is load-bearing.** The YAML becomes the decision engine, not just a mapping index. Signal lists, disambiguation rules, and the richer AI taxonomy are authored there.
- **Primary category enum stays at 8 values.** No non-engineering role families. The richer AI taxonomy is its own orthogonal dimension.
- **Default model is `gpt-5.4-mini`.** `gpt-5.4` is only an escalation path on schema failure, not an ambiguity-triggered path.
- **`blueprint_assembly` stays thin.** It mirrors the new classification fields into the snapshot and writes nothing to `extracted_jd.*`.
- **Classification is the long-term taxonomy source of truth.** The 4.1.2 implementation boundary keeps legacy projections for compatibility, but later plans must migrate runtime consumers to the classification artifact/snapshot and remove downstream taxonomy overrides.

---

## 13. Final Recommended Plan

Commit this document as `plans/classification-4.1.2-taxonomy-engine-hardening.md`. Execute in this order:

1. **Extend `data/job_archetypes.yaml`** with per-category signal blocks, disambiguation rules, and the richer `ai_taxonomy` block. Bump `version` to `2026-04-20-v2`. Add `tests/unit/preenrich/test_taxonomy_signals.py`.
2. **Add deterministic scoring helpers** to `src/preenrich/stages/blueprint_common.py`: `score_categories_from_taxonomy`, `apply_disambiguation_rules`, `detect_ai_taxonomy`. Add `tests/unit/preenrich/test_classification_scoring.py`.
3. **Extend `ClassificationDoc`** in `src/preenrich/blueprint_models.py` with the new optional fields, `ClassificationEvidence`, `JdFactsAgreement`, `PreScoreEntry` sub-models. Keep `extra="forbid"`.
4. **Add `build_p_classify`** in `src/preenrich/blueprint_prompts.py`. Add `tests/unit/preenrich/test_build_p_classify.py` (contract + schema + guard + golden).
5. **Rewrite `ClassificationStage.run`** in `src/preenrich/stages/classification.py` following §6.2. Keep `title_family` import only as a last-resort fallback when `jd_facts` is entirely missing.
6. **Update `BlueprintAssemblyStage`** in `src/preenrich/stages/blueprint_assembly.py` to mirror the new classification keys into the snapshot.
7. **Add env plumbing** in `src/preenrich/types.py` and `scripts/preenrich_model_preflight.py`: `PREENRICH_PROVIDER_CLASSIFICATION`, `PREENRICH_MODEL_CLASSIFICATION`, and the other flags in §8.2 and §11.1.
8. **Add feature-flag validation** to `src/preenrich/blueprint_config.validate_blueprint_feature_flags`.
9. **Write unit + contract + consumer-compat + overwrite-protection + no-loss tests** per §10.
10. **Build benchmark harness** `scripts/benchmark_classification_4_1_2.py` + smoke + sign-off + ambiguity corpora.
11. **Run benchmark, iterate taxonomy signals and prompt** until §9.4 thresholds pass.
12. **Dark-launch → shadow → live canary → 25% → 50% → 100% → default-on** per §11.3. Do not enable live V2 writes without green benchmark and green overwrite-protection tests.

Classification 4.1.2 is a stage upgrade, not a DAG redesign. It makes the taxonomy YAML load-bearing, replaces a title heuristic with a scored decision, and adds a richer orthogonal AI taxonomy dimension — all while respecting the compat-ownership boundary extraction 4.1.1 established. It does not renegotiate short-term ownership of `extracted_jd.role_category`, does not touch consumers directly in this iteration, and does not expand the taxonomy into non-engineering roles. The only things it insists on are: `data/job_archetypes.yaml` must drive the decision; LLM must be the exception, not the default; ambiguity must be surfaced, not hidden; and long-term taxonomy ownership must converge on classification rather than downstream overrides.
