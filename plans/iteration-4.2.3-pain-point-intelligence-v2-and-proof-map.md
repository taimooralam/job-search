# Iteration 4.2.3 Plan: Pain-Point Intelligence V2 and Proof Map

## 1. Executive Summary

`pain_point_intelligence` is a new preenrich stage that replaces the current
`blueprint_assembly` backfill of `pain_points`, `strategic_needs`,
`risks_if_unfilled`, and `success_metrics` with a typed, source-grounded,
evidence-referenced artifact, and introduces an explicit **proof map**: for
each pain, the shape of CV evidence that would reassure the evaluator.

The stage is candidate-agnostic. It describes what the employer is worried
about and what proof category would calm each worry. It does not prescribe
section order, title strategy, or any CV copy. It is the canonical substrate
for `presentation_contract` (4.2.2 + 4.2.4 + 4.2.5 + 4.2.6), later
candidate-evidence retrieval, STAR selection, and reviewer UI.

It reuses upstream artifacts by default; it does not duplicate
`research_enrichment` fetches. Langfuse is the observability sink. Mongo
(`work_items`, `preenrich_stage_runs`, `preenrich_job_runs`,
`pre_enrichment.stage_states`) remains the operational control plane.

## 2. Mission

Turn the employer's worries, needs, risks, and success metrics into a
structured, sourced, auditable contract that every downstream stage can
depend on without re-deriving pain from raw research.

## 3. Objectives

O1. Produce a typed four-category decomposition of employer concern
    (pain / strategic need / risk / success metric), never collapsed.
O2. Ground every entry in at least one upstream artifact reference or
    source id; reject generic HR boilerplate.
O3. Emit a `proof_map[]` that binds each pain to the evidence shape a CV
    must carry, expressed in a canonical proof-type enum.
O4. Emit `search_terms[]` suitable for later candidate-evidence retrieval.
O5. Fail open gracefully to JD-only evidence with lower confidence and
    explicit `unresolved_questions[]`.
O6. Be fully observable through the inherited 4.2 Langfuse contract with
    stage-specific metadata that supports latency, retry, schema-repair,
    cache, and fail-open debugging.
O7. Be fully validated on the VPS end-to-end on a real `level-2` job
    before default-on rollout.

## 4. Goals

G1. Single artifact: `pain_point_intelligence`, owned by one stage.
G2. Distinct `pain_id` per pain entry, referentially integrated with
    `proof_map[]`.
G3. Canonical proof-type enum defined in this plan; 4.2.2 consumes it.
G4. Compact projection in `blueprint_assembly.snapshot` — counts, top-level
    confidence, refs — never full bodies.
G5. Zero fabricated company events, funding rounds, leadership changes,
    or metrics. `unresolved` is a legal answer.
G6. No duplication of `research_enrichment` fetches on the default path.
G7. Rollout behind `pain_point_intelligence_enabled()` capability flag
    with a curated benchmark gate before default-on.

## 5. Success Criteria

The stage is successful when, for a representative corpus of 30 curated
`level-2` jobs (mixed IC / EM / Director / Head), all of the following
hold:

SC1. 100% of runs land with `status in {completed, partial, unresolved}`
     and none deadletter for schema issues.
SC2. Reviewer-rated pain specificity ≥ 4.0 / 5 median (rubric below).
SC3. `proof_map` coverage ≥ 90% of high-confidence pains on IC jobs,
     ≥ 70% on leadership jobs (leadership pains are intentionally
     broader).
SC4. 0 fabricated company events in a 10-job spot-check.
SC5. For jobs where `research_enrichment.status == "unresolved"`, the
     stage returns with `source_scope == "jd_only"` and populated
     `unresolved_questions[]`, not deadletter.
SC6. `blueprint_assembly.snapshot.pain_points` etc. match the new
     artifact's compact projection; legacy compat projection can be
     switched off on a gated job without downstream breakage.
SC7. Langfuse trace for any single job surfaces: stage span,
     `extract` substep, any `schema_repair` substep, any
     `supplemental_web` substep, cache hit/miss event, fail-open reason.
     Operator can reach it in one click from the level-2 UI.
SC8. VPS smoke pass (§17) completed on a real job with artifacts
     captured under `reports/pain-point-intelligence/<job_id>/`.

## 6. Non-Goals

- final CV prose, titles, headers, bullets, summaries, section ordering
  (→ `presentation_contract`)
- candidate evidence matching, master-CV read-through, STAR selection
  (→ 4.3.x)
- private stakeholder motives, clinical/psychological profiling,
  protected-trait inference
- cover-letter generation, outreach copy
- replacement of `research_enrichment` (never duplicate the full fetch
  pipeline)
- replacement of 4.1.3 `InitialOutreachGuidance` on `StakeholderRecord`
- owning the section-id canonical list (owned by 4.2.2; this stage
  consumes it)
- invention of a new control plane outside the blueprint DAG + Mongo

## 7. Why This Artifact Exists

`blueprint_assembly.snapshot` currently backfills pain/need/risk/metric
from proxy fields:

- `pain_points ← semantic_role_model.likely_screening_themes`
- `strategic_needs ← qualifications.must_have`
- `risks_if_unfilled ← ["Loss of role-specific delivery capacity."]`
  (hardcoded in `blueprint_assembly.py`)
- `success_metrics ← merged_view.success_metrics` (when present)

This is too thin for a pre-candidate CV skeleton because it:

- mixes pain, need, risk, and success metric into undifferentiated lists;
- carries no source attribution;
- provides no proof-target mapping;
- does not read `research_enrichment` evidence on the blueprint path.

The skeleton needs four distinct, typed truths:

- what the employer is worried about (pain);
- what the role exists to solve (strategic need);
- what failure would look like (risk if unfilled);
- what success looks like (success metric);

and one derived binding:

- what proof in a CV would reassure each pain (proof map).

These four categories stay distinct and typed; `proof_map` is the only
bridge.

## 8. Stage Boundary

### 8.1 DAG placement

```
jd_facts -> classification -> application_surface -> research_enrichment
   -> stakeholder_surface -> pain_point_intelligence -> presentation_contract
```

### 8.2 Stage registration contract

Registered in `_blueprint_registry()` in `src/preenrich/stage_registry.py`:

```python
StageDefinition(
    name="pain_point_intelligence",
    task_type="preenrich.pain_point_intelligence",
    prerequisites=("jd_facts", "classification", "research_enrichment"),
    produces_fields=("pain_point_intelligence",),
    required_for_cv_ready=True,
    max_attempts=3,
    default_priority=50,
    retryable_error_tags=(
        *RETRYABLE_LLM_ERRORS,
        *RETRYABLE_RESEARCH_ERRORS,   # only when supplemental web is on
        *RETRYABLE_LOCAL_ERRORS,
    ),
    terminal_error_tags=(*TERMINAL_LLM_ERRORS,),
    job_fail_policy="fail_open",       # see §12
)
```

Gated by `pain_point_intelligence_enabled()` alongside
`blueprint_enabled()` (consistent with `presentation_contract_enabled()`).

### 8.3 Relationship to research_enrichment

`pain_point_intelligence` reads these fields and nothing else from
`research_enrichment`:

- `company_profile.signals[]`, `company_profile.recent_signals[]`,
  `company_profile.role_relevant_signals[]`,
  `company_profile.scale_signals[]`,
  `company_profile.ai_data_platform_maturity`
- `role_profile.mandate`, `role_profile.business_impact`,
  `role_profile.success_metrics[]`, `role_profile.risk_landscape[]`,
  `role_profile.evaluation_signals[]`, `role_profile.interview_themes[]`,
  `role_profile.why_now`
- `application_profile.friction_signals[]`,
  `application_profile.stale_signal`, `application_profile.closed_signal`
- `sources[]` (for `source_id` propagation)

It is a synthesis-plus-structured-extraction stage over upstream
artifacts. It does not re-fetch company or role pages on the default
path.

### 8.4 Relationship to legacy pain_point_miner

`src/layer2/pain_point_miner.py` remains in `LEGACY_STAGE_REGISTRY` as
stage `pain_points` for the runner pipeline. It is not invoked on
blueprint jobs. No field is shared between the legacy and the V2 paths;
legacy output lives only on runner-produced jobs predating the blueprint
DAG.

## 9. Inputs

### 9.1 Required

- `pre_enrichment.outputs.jd_facts` — merged view including
  `implied_pain_points`, `success_metrics`, `operating_signals`,
  `ambiguity_signals`, `top_keywords`, `responsibilities`,
  `qualifications`.
- `pre_enrichment.outputs.classification` — `primary_role_category`,
  `seniority`, `tone_family`, `ai_taxonomy`.
- `pre_enrichment.outputs.research_enrichment` — subset in §8.3.

### 9.2 Opportunistic (not hard prerequisites)

- `pre_enrichment.outputs.stakeholder_surface.inferred_stakeholder_personas[]`
  (adds `related_stakeholders[]` hints and raises `preferred_proof_type`
  priors)
- `pre_enrichment.outputs.job_inference.semantic_role_model`
  (compat; used as a secondary prior if present)
- `application_surface.ui_actionability` (only to weight
  `category=application` pains when friction is explicit)

### 9.3 Deterministic preflight helpers

Built by the pre-pass before any LLM call:

- `evidence_bag_by_category` — `{category: [ {text, source_ref, weight} ]}`
  covering `technical, business, delivery, org, stakeholder,
  application`.
- `source_registry` — merged `SourceEntry[]` from
  `research_enrichment.sources[]` plus synthetic JD-derived entries
  (`source_type="jd_section"`, `source_id="jd:<section>:<idx>"`).
- `top_phrase_frequencies` — from `jd_facts.top_keywords` capped at 32.

### 9.4 Input hashing (pain_input_hash)

SHA-256 over a canonical JSON projection of:

- `jd_facts.merged_view` (sorted keys),
- `classification.primary_role_category`, `tone_family`, `ai_taxonomy`,
- `research_enrichment.research_input_hash`,
- `research_enrichment.status`,
- `stakeholder_surface.coverage_digest` when present,
- `PROMPT_VERSION` for this stage.

`pain_input_hash` is the cache key. It is recomputed deterministically;
any drift causes a cache miss.

## 10. Output Shape

### 10.1 Top-level schema (Pydantic model: PainPointIntelligenceDoc)

```
PainPointIntelligenceDoc {
  job_id,
  level2_job_id,
  input_snapshot_id,
  pain_input_hash,
  prompt_version,             # "pain_point_intelligence:vX"
  prompt_metadata: PromptMetadata,
  provider_used, model_used, transport_used,
  status,                     # "completed" | "partial" | "unresolved"
  source_scope,               # "jd_only" | "jd_plus_research" | "supplemental_web"
  pain_points: list[PainPointEntry],
  strategic_needs: list[StrategicNeedEntry],
  risks_if_unfilled: list[RiskEntry],
  success_metrics: list[SuccessMetricEntry],
  proof_map: list[ProofMapEntry],
  search_terms: list[SearchTerm],
  unresolved_questions: list[str],
  sources: list[SourceEntry],
  evidence: list[EvidenceEntry],
  confidence: ConfidenceDoc,
  cache_refs: CacheRefs,
  timing: TimingBlock,
  usage: UsageBlock,
  debug_context: PainPointDebugContext | None,
}
```

### 10.2 pain_points[] entry

```
PainPointEntry {
  pain_id,                    # stable slug "p_<category>_<hash8>"
  category,                   # PainCategoryEnum (see 10.5)
  statement,                  # <= 240 chars, specific, non-generic
  why_now,                    # company/role context explaining urgency
  source_scope,               # jd_only | jd_plus_research | supplemental_web
  evidence_refs: list[str],   # source_ids or upstream-artifact dotted paths (see 10.6)
  urgency,                    # low | medium | high
  related_stakeholders: list[str],     # StakeholderTypeEnum values, optional
  likely_proof_targets: list[str],     # ProofTypeEnum values (see 10.5)
  confidence: ConfidenceDoc,
}
```

### 10.3 strategic_needs[], risks_if_unfilled[], success_metrics[]

Share the entry skeleton but have their own category enum
(`StrategicNeedCategoryEnum`, `RiskCategoryEnum`, `SuccessMetricKindEnum`)
and must each carry `evidence_refs[]` and `confidence`. None of them
duplicate a `pain_points[].statement`; the post-pass enforces this.

Each `SuccessMetricEntry` also carries `metric_kind`
(`outcome | leading | lagging | qualitative`) and optional `horizon`
(`30_day | 90_day | 6_month | 12_month | multi_year`).

### 10.4 proof_map[] entry

```
ProofMapEntry {
  pain_id,                                # FK → pain_points[].pain_id
  preferred_proof_type,                   # ProofTypeEnum (see 10.5)
  preferred_evidence_shape,               # free text, <= 160 chars
  bad_proof_patterns: list[str],          # what would fail to reassure
  affected_document_sections: list[str],  # DocumentSectionIdEnum (owned by 4.2.2)
  rationale,                              # <= 300 chars
  confidence: ConfidenceDoc,
}
```

### 10.5 Canonical enums (owned by 4.2.3)

```
PainCategoryEnum:
  technical | business | delivery | org | stakeholder | application

ProofTypeEnum (owned by 4.2.3; consumed by 4.2.2, 4.2.4, 4.2.5):
  metric | architecture | leadership | domain | reliability
  | ai | stakeholder | process | compliance | scale

StakeholderTypeEnum (widened in 4.2.1):
  recruiter | hiring_manager | skip_level_leader | peer_technical
  | cross_functional_partner | executive_sponsor | unknown

DocumentSectionIdEnum:
  owned by 4.2.2; imported as a frozen enum, not redefined here.
```

### 10.6 search_terms[], unresolved_questions[], debug_context

```
SearchTerm { term, intent, source_basis }   # intent ∈ {retrieval, disambiguation, ats}
unresolved_questions: list[str]             # <= 64 chars each, <= 12 entries
debug_context {
  prompt_id,
  prompt_hash,
  evidence_bag_counts,                      # dict category -> count
  deterministic_validator_diffs: list[str],
  llm_request_ids: list[str],
  retry_reasons: list[str],
  supplemental_web_queries: list[str] | None,
}
```

`evidence_refs[]` format is pinned:

- `source:<source_id>` where `source_id` matches `sources[].source_id`, or
- `artifact:<dotted-path>` rooted at
  `pre_enrichment.outputs.<stage>.<field>[...]`.

Mixed forms are rejected by the post-pass.

## 11. Extraction Strategy

### 11.1 Deterministic pre-pass (Python, no LLM)

Mine text from:

- JD sections: `responsibilities`, `requirements`, `nice-to-haves`, `about`,
  `challenges`;
- `jd_facts.top_keywords`, `operating_signals`, `ambiguity_signals`,
  `success_metrics`, `implied_pain_points`;
- `research_enrichment.company_profile` signal lists;
- `research_enrichment.role_profile` list fields;
- `application_profile.friction_signals`.

Emit `evidence_bag_by_category` and `source_registry`. Cardinality caps:
≤ 12 entries per category, ≤ 64 entries total in the evidence bag.

No LLM call in this pass. Deterministic and idempotent.

### 11.2 LLM synthesis pass

Single prompt (`build_p_pain_point_intelligence`) consuming the
evidence bag plus compact JD/role/company excerpts (bounded to 6 KB
total). Produces the typed output in §10.

Model routing:

- primary: `gpt-5.4` via default provider;
- fallback: `gpt-5.2` (same provider or fallback provider if declared);
- transport: `_call_llm_with_fallback` in the worker;
- `max_web_queries=0` on the default path.

`get_stage_step_config("pain_point_intelligence")` governs provider,
model, transport, prompt_version, and fallback.

### 11.3 Deterministic post-pass

Hard rules, all enforced by a Python validator before `StageResult`
returns:

- unique `pain_id` values;
- every `proof_map` entry references an existing `pain_id`;
- `likely_proof_targets[]`, `preferred_proof_type` use `ProofTypeEnum`;
- no `statement` appears in two category lists (Jaccard ≥ 0.8 on tokens
  treated as duplication);
- `urgency == "high"` requires `source_scope == "jd_plus_research"` or
  `supplemental_web` AND ≥ 2 converging evidence refs across source
  surfaces;
- every pain has ≥ 1 `evidence_refs[]`;
- genericity filter: reject pain statements matching a curated
  stop-list (`team player`, `strong communicator`, `passionate about`,
  `fast-paced environment`, `rockstar`, `ninja`, ...) unless
  `source_scope == "jd_only"` AND the JD literally contains the phrase;
- `affected_document_sections[]` values are in `DocumentSectionIdEnum`.

Post-pass is not a repair step; it is a gate. Violations escalate
to §11.4.

### 11.4 Schema-repair retry contract

Exactly one repair retry is permitted, only when:

- the LLM call succeeded with valid JSON, AND
- the post-pass failed on a narrow, listed set of recoverable defects:
  `missing_evidence_ref`, `duplicate_pain_id`, `proof_map_orphan_fk`,
  `enum_drift`, `cross_category_duplication`.

The repair prompt passes only the diff and the original output. Emits
`scout.preenrich.pain_point_intelligence.schema_repair` with metadata
`{ repair_reason, repair_attempt }`. If the retry still fails, status
downgrades per §12.

### 11.5 Optional supplemental web research

Default: off. Permitted only when all three hold:

- `research_enrichment.status` in `{"partial", "unresolved"}`;
- `pain_point_supplemental_web_enabled()` is true;
- deterministic pre-pass emitted an `evidence_bag_by_category` with
  fewer than 3 total entries tagged `research`.

When enabled, the stage issues at most `max_web_queries=2` through the
same `CodexResearchTransport` used by `research_enrichment`. Every
query, URL, and fetched snippet is persisted in
`debug_context.supplemental_web_queries` and in `sources[]` with
`source_type="supplemental_web"`. It never replaces the
`research_enrichment` pipeline.

## 12. Fail-Open / Fail-Closed Rules

Fail open:

- research thin → emit JD-only pains with `source_scope="jd_only"`,
  lower confidence band, populated `unresolved_questions[]`,
  `status in {"partial", "unresolved"}`;
- `proof_map` cannot be generated for a low-confidence pain → omit the
  proof entry rather than fabricate one; the missing binding is
  declared in `unresolved_questions[]`;
- schema-repair exhausted → keep the LLM's first parseable output,
  down-rank to `status="partial"`, record
  `fail_open_reason="schema_repair_exhausted"`.

Fail closed:

- no fabricated company events, funding rounds, leadership changes,
  acquisitions, layoffs, headcounts, or metrics;
- no unsupported urgency: `high` requires converging evidence
  (§11.3);
- no generic HR boilerplate for non-generic JDs;
- no pain statement without `evidence_refs[]`;
- no cross-category duplication of statements;
- no `supplemental_web` fabrication: every claim must be traceable to
  a fetched URL captured in `sources[]`;
- no private-stakeholder motives, protected-trait inference, or
  clinical profiling.

## 13. Safety / Anti-Hallucination Rules

Inherited from 4.2 umbrella §8.5 and restated here as hard
implementation rules:

- every pain / need / risk / metric entry carries `evidence_refs[]`;
- `evidence_refs[]` must resolve: `source:<id>` must exist in
  `sources[]`; `artifact:<path>` must exist in the input snapshot;
- prompt must instruct: "Unresolved is a valid answer. Emit
  `unresolved_questions[]` rather than guess.";
- prompt must instruct: "Do not claim external company facts absent
  from the provided inputs.";
- prompt must instruct: "Do not produce CV prose, titles, headers,
  or bullets.";
- prompt must instruct: "Do not infer private motives, protected
  traits, or clinical psychology.";
- the deterministic post-pass is the single source of truth for
  enforcement.

## 14. Operational Catalogue

### 14.1 Stage registration contract

See §8.2.

### 14.2 Mongo persistence map

| What             | Location                                                                                      |
| ---------------- | --------------------------------------------------------------------------------------------- |
| Full artifact    | `pain_point_intelligence` collection, unique filter `(job_id, input_snapshot_id, prompt_version)` |
| Stage output ref | `level-2.pre_enrichment.outputs.pain_point_intelligence`                                      |
| Stage state      | `level-2.pre_enrichment.stage_states.pain_point_intelligence`                                 |
| Compact snapshot | `level-2.pre_enrichment.job_blueprint_snapshot` (projected by `blueprint_assembly`)           |
| Work item        | `work_items` collection, `task_type="preenrich.pain_point_intelligence"`                      |
| Run audit        | `preenrich_stage_runs`, `preenrich_job_runs`                                                  |
| Alerts           | `preenrich_alerts` (on deadletter only, rate-limited)                                         |

Legacy root-level `pain_points`, `strategic_needs`,
`risks_if_unfilled`, `success_metrics` on the job doc are populated only
by `blueprint_assembly.compat_projection` for the rollout window; see
§18.

### 14.3 Compact snapshot projection

`blueprint_assembly` projects into
`JobBlueprintSnapshot.pain_point_intelligence_compact`:

```
{
  status,
  source_scope,
  pains_count,
  strategic_needs_count,
  risks_count,
  success_metrics_count,
  proof_map_size,
  high_urgency_pains_count,
  unresolved_questions_count,
  confidence_band,
  artifact_ref: { collection: "pain_point_intelligence", _id },
  trace_ref: { trace_id, trace_url },
}
```

No pain bodies, no proof map bodies, no evidence text in the snapshot.

### 14.4 Work-item semantics

- enqueued by the DAG sweeper when all prerequisites
  (`jd_facts`, `classification`, `research_enrichment`) report
  `status="completed"` and their `input_snapshot_id` matches the
  current job snapshot;
- payload carries `input_snapshot_id`, `attempt_token`,
  `correlation_id`, `jd_checksum`, `level2_job_id`;
- claimed atomically via `StageWorker.claim` with lease;
- on success, Phase A writes `pre_enrichment.outputs` and pushes
  `presentation_contract` onto `pending_next_stages`; Phase B drains.

### 14.5 Retry / deadletter behavior

- `max_attempts = 3` (plus one in-stage schema-repair retry in §11.4);
- backoff uses the shared `RETRY_BACKOFF_SECONDS = (30, 120, 600, 1800, 3600)`;
- retryable: LLM transient errors, research transport transients,
  `mongo_transient`, `transient_io`;
- terminal: `unsupported_provider`, `missing_required_input`,
  `schema_validation` after repair retry exhausted;
- `job_fail_policy="fail_open"`: terminal failure of this stage does
  not deadletter the whole job — `presentation_contract` runs in
  degraded mode with an empty `pain_point_intelligence.pain_points[]`
  and records `fail_open_reason="pain_intel_unavailable"`.

### 14.6 Cache behavior

- cache key: `pain_input_hash` (§9.4);
- cache stored in `pain_point_intelligence` collection itself,
  filtered by `(job_id, pain_input_hash)`;
- hit ⇒ skip LLM, project cached doc into a new
  `input_snapshot_id`-keyed write;
- miss ⇒ full pipeline;
- bust on any change to: `jd_facts.merged_view`,
  `research_enrichment.research_input_hash`,
  `research_enrichment.status`, `PROMPT_VERSION`, stage
  `prompt_metadata.git_sha` on the prompt file;
- emits `scout.preenrich.pain_point_intelligence.cache.hit|miss`
  events with metadata `{ cache_key, hit_reason, ttl_remaining_s, upstream_research_status }`.

### 14.7 Heartbeat expectations

- `PREENRICH_STAGE_HEARTBEAT_SECONDS` default 60 s applied by
  `StageWorker._heartbeat_loop`;
- the stage must not hold CPU for more than 30 s between yield points
  (evidence mining, LLM call, post-pass); worker background thread
  renews the lease;
- launcher-side wrapper (see §17) emits operator heartbeat every
  15–30 s and streams any Codex subprocess PID / stdout / stderr from
  supplemental research.

### 14.8 Feature flags

- `pain_point_intelligence_enabled()` — master flag for the stage.
  Off: stage not registered; `blueprint_assembly` continues legacy
  compat.
- `pain_point_supplemental_web_enabled()` — gate for §11.5.
- `pain_point_intelligence_compat_projection_enabled()` — keep
  populating legacy root-level `pain_points` etc. during rollout.

### 14.9 Failure classes

| Class                        | Example                                | Retryable?        | Outcome                                                       |
| ---------------------------- | -------------------------------------- | ----------------- | ------------------------------------------------------------- |
| `missing_required_input`     | upstream artifact absent               | no                | terminal, fail_open                                           |
| `schema_validation`          | post-pass gate fail, repair exhausted  | no                | terminal, fail_open                                           |
| `provider_timeout`           | LLM timeout                            | yes               | retry                                                         |
| `error_schema`               | LLM returned malformed JSON            | yes (1x repair)   | retry/terminal                                                |
| `unsupported_transport`      | supplemental web not configured        | no                | terminal; stage still completes fail-open if §11.5 not required |
| `transient_error`            | network blip                           | yes               | retry                                                         |
| `mongo_transient`            | write conflict                         | yes               | retry                                                         |
| `cross_category_duplication` | post-pass                              | yes (1x repair)   | terminal after                                                |

### 14.10 Operator-visible success/failure signals

- `level-2.pre_enrichment.stage_states.pain_point_intelligence.status`
  — `pending | leased | completed | failed | deadletter`;
- `level-2.pre_enrichment.outputs.pain_point_intelligence.status` —
  `completed | partial | unresolved`;
- `preenrich_stage_runs` row with `trace_id`, `trace_url`,
  `fail_open_reason` (when present);
- `preenrich_alerts` row only on deadletter.

### 14.11 Downstream consumers

- `presentation_contract` — reads
  `pain_points[].likely_proof_targets`,
  `proof_map[].preferred_proof_type`,
  `proof_map[].affected_document_sections`,
  `search_terms[]`, `strategic_needs[]`, `success_metrics[]`;
- `blueprint_assembly` — compact projection (§14.3);
- later candidate-evidence retrieval (4.3.x) — `search_terms[]`,
  `pain_points[].likely_proof_targets`;
- reviewer UI "what this job needs solved" — full artifact;
- optional outreach guidance refresh — `pain_points[].statement`,
  `why_now`.

### 14.12 Rollback strategy

- toggle `pain_point_intelligence_enabled()` false;
  `blueprint_assembly` falls back to the legacy proxy synthesis;
- existing `pain_point_intelligence` collection documents remain;
  they are inert;
- no schema migration on rollback; compat projection continues.

## 15. Langfuse Tracing Contract

Inherits 4.2 umbrella §8.8 verbatim. Stage-specific rules follow and
are normative for this stage.

### 15.1 Canonical trace, stage span, substep spans

- trace: `scout.preenrich.run` (unchanged);
- job span: `scout.preenrich.job` (unchanged);
- stage span: `scout.preenrich.pain_point_intelligence`;
- substeps (only those that meaningfully time work):
  - `scout.preenrich.pain_point_intelligence.evidence_mine`
  - `scout.preenrich.pain_point_intelligence.prompt_build`
  - `scout.preenrich.pain_point_intelligence.llm_call`
    (primary + any fallback — one span each, named
    `...llm_call.primary`, `...llm_call.fallback`)
  - `scout.preenrich.pain_point_intelligence.post_pass`
  - `scout.preenrich.pain_point_intelligence.schema_repair`
    (only when §11.4 fires)
  - `scout.preenrich.pain_point_intelligence.supplemental_web`
    (only when §11.5 fires; follows the iteration-4 research-transport
    contract)
  - `scout.preenrich.pain_point_intelligence.artifact_persist`

No per-pain, per-need, or per-proof-map spans. Cardinality is
expressed as metadata, never in span names.

### 15.2 Events

- `scout.preenrich.pain_point_intelligence.cache.hit`
- `scout.preenrich.pain_point_intelligence.cache.miss`
- `scout.preenrich.pain_point_intelligence.fail_open`
- lifecycle events (`claim`, `enqueue_next`, `retry`, `deadletter`,
  `release_lease`, `snapshot_invalidation`) are the canonical umbrella
  events — not redefined here.

### 15.3 Required metadata on every span/event

Canonical payload from `PreenrichTracingSession.payload_builder`:

`job_id`, `level2_job_id`, `correlation_id`, `langfuse_session_id`, `run_id`, `worker_id`, `task_type`, `stage_name`, `attempt_count`, `attempt_token`, `input_snapshot_id`, `jd_checksum`, `lifecycle_before`, `lifecycle_after`, `work_item_id`.

### 15.4 Stage-specific metadata (stage span)

On end:

- `status ∈ {completed, partial, unresolved, failed}`,
- `source_scope`,
- `pains_count`, `strategic_needs_count`, `risks_count`, `success_metrics_count`, `proof_map_size`, `high_urgency_pains_count`, `unresolved_questions_count`,
- `confidence_band`,
- `research_enrichment_available`, `jd_facts_available`, `classification_available`, `stakeholder_surface_available`, `supplemental_web_enabled`,
- `pain_input_hash`,
- `prompt_version`, `prompt_git_sha`,
- `fail_open_reason` when `status ∈ {partial, unresolved}`: one of
  `jd_only_fallback`, `thin_research`, `schema_repair_exhausted`,
  `supplemental_web_unavailable`, `llm_terminal_failure`.

### 15.5 Outcome classifications

`llm_call.*` spans carry the iteration-4 transport outcome
classification: `success | unsupported_transport | error_missing_binary | error_timeout | error_subprocess | error_no_json | error_schema | error_exception`. `schema_valid: bool` is always set.

### 15.6 Retry / repair metadata

`schema_repair` span metadata:

- `repair_reason ∈ {missing_evidence_ref, duplicate_pain_id, proof_map_orphan_fk, enum_drift, cross_category_duplication}`,
- `repair_attempt` (1),
- `repaired_fields: list[str]`,
- `pre_repair_schema_valid: bool`,
- `post_repair_schema_valid: bool`.

Retry events use the canonical `scout.preenrich.retry` with
`stage_name="pain_point_intelligence"` and the same `attempt_token`.

### 15.7 Fail-open reason metadata

On the stage span and on any `fail_open` event. Exactly one of:

`jd_only_fallback | thin_research | schema_repair_exhausted | supplemental_web_unavailable | llm_terminal_failure | pain_intel_unavailable` (last one only
on downstream
`presentation_contract` when this stage did not produce output).

### 15.8 Cache metadata

`cache.hit|miss` event metadata:

- `cache_key=pain_input_hash`,
- `hit_reason ∈ {same_snapshot, same_pain_input_hash, research_status_stable}`,
- `ttl_remaining_s` when computable,
- `upstream_research_status`,
- `prompt_version`.

### 15.9 Trace refs into Mongo run records

The stage's `trace_id` and `trace_url` flow into:

- `preenrich_stage_runs` — for this row;
- `preenrich_job_runs` — aggregate job-level;
- `pre_enrichment.stage_states.pain_point_intelligence.trace_id/url`;
- `pre_enrichment.outputs.pain_point_intelligence.trace_ref`
  (projection only);
- `JobBlueprintSnapshot.pain_point_intelligence_compact.trace_ref`.

An operator opening a single level-2 job in the UI reaches the
Langfuse trace in one click.

### 15.10 Forbidden in Langfuse

- full pain bodies;
- full proof-map entries;
- full JD excerpts;
- full `research_enrichment` subdocuments;
- full `sources[]` URL lists;
- raw LLM prompts unless `_sanitize_langfuse_payload` is applied and
  `LANGFUSE_CAPTURE_FULL_PROMPTS=true`;
- any field matching `*prompt*` key without sanitisation.

Previews capped at 160 chars via `_sanitize_langfuse_payload`.

### 15.11 What may live only in debug_context

- raw evidence-bag contents;
- full LLM request ids and raw repair prompts;
- supplemental web URLs with snippets;
- post-pass validator diffs;
- deterministic pre-pass per-category rejection reasons.

### 15.12 Cardinality and naming

- substep span names are a fixed, small set (§15.1);
- per-pain, per-need, per-risk, per-metric details only via metadata
  counts;
- repair attempts bounded at 1, hence bounded spans;
- supplemental web spans follow the research-transport contract and
  cap at `max_web_queries`.

### 15.13 Operator debug checklist (normative)

An operator must be able to diagnose each of these from Mongo → trace
in under two minutes:

- slow stage execution — inspect `llm_call.primary.duration_ms`
  and `supplemental_web.duration_ms`;
- malformed LLM output — look for `schema_repair` span with
  `repair_reason`;
- schema-repair retry usage — count of `schema_repair` spans;
- supplemental research path — presence of
  `supplemental_web` span and outcome classification;
- Mongo persistence failure — `artifact_persist` span outcome,
  `mongo_transient` retry events;
- downstream incompatibility — `presentation_contract` span in
  the same job trace with `fail_open_reason="pain_intel_unavailable"`
  and `pain_point_intelligence` outputs.

## 16. Tests and Evals

### 16.1 Unit tests (`tests/preenrich/test_pain_point_intelligence.py`)

- evidence-bag builder: given fixtures, expected category buckets;
- source registry merge: JD + research sources, no id collisions;
- `pain_input_hash` stable across dict key order;
- post-pass gate: each of the failure classes in §11.3 is caught.

### 16.2 Stage contract tests

- `StageDefinition` lookup returns the registered instance under
  `pain_point_intelligence` when flag is on, raises when off;
- `prerequisites = ("jd_facts", "classification", "research_enrichment")`;
- `produces_fields = ("pain_point_intelligence",)`;
- `task_type == "preenrich.pain_point_intelligence"`;
- retry / terminal error tag sets match §8.2.

### 16.3 Deterministic validator tests

Table-driven. Each case is a malformed LLM output plus an expected
`repair_reason` (or expected terminal).

### 16.4 Trace emission tests

Using a `FakeTracer`:

- stage span emitted with required metadata keys (§15.3 + §15.4);
- `llm_call` substep emitted with outcome classification;
- `schema_repair` substep emitted exactly when the LLM output
  required repair;
- `cache.hit` / `cache.miss` exactly once per run;
- no forbidden keys leak into span metadata (grep assertion on
  serialized payload).

### 16.5 Fail-open / fail-closed tests

- `research_enrichment.status = "unresolved"` →
  `status = "partial"`, `source_scope = "jd_only"`,
  `fail_open_reason = "thin_research"`;
- LLM terminal failure → stage returns `status = "unresolved"` with
  empty arrays but valid schema, `fail_open_reason = "llm_terminal_failure"`;
- fabricated company event in LLM output → post-pass rejects,
  repair does not fabricate, final output excludes it;
- generic HR boilerplate ("team player") → rejected unless JD
  literally contains the phrase.

### 16.6 Regression corpus

- 30 curated level-2 jobs in `tests/data/pain_point_intel/corpus/`
  (10 IC, 10 EM/Director, 10 Head/VP);
- golden outputs captured as JSON in
  `tests/data/pain_point_intel/golden/` with tolerance for ordering
  and `pain_id` stability checks (statement Jaccard ≥ 0.9 allowed);
- CI job: run pipeline with mocked LLM returning a recorded response,
  compare against golden, diff non-deterministic fields separately.

### 16.7 Proof-map referential integrity

- for every `proof_map[]` entry, `pain_id` resolves;
- no orphaned `proof_map[]` entries;
- `affected_document_sections[]` every value is in
  `DocumentSectionIdEnum`;
- `preferred_proof_type` in `ProofTypeEnum`.

### 16.8 Downstream consumer compatibility tests

- `presentation_contract` prompt builder test: given a fixture
  `PainPointIntelligenceDoc`, the prompt resolves `proof_map[]` and
  `pain_points[].likely_proof_targets[]` without `KeyError` or
  enum-drift;
- `blueprint_assembly` compact projection test: the snapshot
  projection never includes full pain bodies and includes all §14.3
  keys;
- legacy compat projection test: when
  `pain_point_intelligence_compat_projection_enabled()` is true,
  root-level `pain_points` etc. are populated from the new artifact.

### 16.9 Snapshot projection and run-record trace-ref tests

- after a successful run, `preenrich_stage_runs` for this stage has
  populated `trace_id` and `trace_url`;
- `JobBlueprintSnapshot.pain_point_intelligence_compact.trace_ref`
  matches the `stage_runs` row.

### 16.10 Live smoke tests

- `scripts/smoke_pain_point_intelligence.py` — loads `.env` from
  Python, fetches one job by `_id`, runs the stage locally against
  live Codex/LLM, validates output, prints heartbeat every 15 s.

### 16.11 Eval metrics (reviewer rubric; recorded in `reports/`)

- pain specificity (1-5): 5 = "couldn't reword into a different
  job"; 1 = "applies to any role".
- proof-target usefulness (1-5): 5 = "evaluator would read this
  proof and believe the risk is mitigated".
- role/company grounding: % of pains whose `evidence_refs[]`
  include ≥ 1 research-sourced ref (`artifact:pre_enrichment.outputs.research_enrichment...`
  or `source:<id>` with `source_type ∈ {company_research, role_research, supplemental_web}`).
- JD-only graceful degradation: for research-thin jobs, median
  specificity ≥ 3.5 with `fail_open_reason="thin_research"`.

## 17. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This section is the live-run chain.

### 17.1 Local prerequisite tests before touching VPS

- `pytest -k "pain_point_intelligence"` clean;
- `python -m scripts.preenrich_dry_run --stage pain_point_intelligence --job <level2_id> --mock-llm` clean;
- compact snapshot test green;
- Langfuse sanitizer test green.

### 17.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the live deployment path;
- verify the deployed `stage_registry.py` contains
  `pain_point_intelligence` and the flag is on:
  `grep -n "pain_point_intelligence" /root/scout-cron/src/preenrich/stage_registry.py`
  and `grep -n "pain_point_intelligence_enabled" /root/scout-cron/src/preenrich/config_flags.py`;
- verify `blueprint_prompts.py` contains
  `build_p_pain_point_intelligence`;
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`;
- deployment is file-synced, not git-pulled — read the file
  markers set by the sync, do not `git status`.

### 17.3 Target job selection

- pick a real level-2 job with `pre_enrichment.outputs.jd_facts`,
  `classification`, and `research_enrichment` all at
  `status="completed"`;
- prefer IC or EM mid-seniority and a company with rich research
  (`research_enrichment.status="completed"` and
  `research_input_hash` stable);
- record `_id`, `jd_checksum`, and `input_snapshot_id`;
- optionally choose a second job with
  `research_enrichment.status="partial"` to exercise fail-open.

### 17.4 Upstream artifact recovery

If `stage_states` show stale entries:

1. verify `pre_enrichment.outputs.jd_facts` / `classification` /
   `research_enrichment` exist;
2. recompute the current `input_snapshot_id` deterministically
   (`python -u scripts/recompute_snapshot_id.py --job <_id>`);
3. only if necessary, re-enqueue prerequisites via
   `scripts/enqueue_stage.py` rather than touching `work_items`
   directly.

### 17.5 Single-stage run path (fast path)

Preferred. A wrapper script in `/tmp/run_pain_point_intel_<job>.py`:

- loads `.env` in Python with explicit path:
  `from dotenv import load_dotenv; load_dotenv("/root/scout-cron/.env")`;
- reads `MONGODB_URI`;
- builds `StageContext` via the worker-compatible factory
  (`build_stage_context_for_job`);
- runs `PainPointIntelligenceStage().run(ctx)` directly;
- prints a heartbeat line every 15 s during LLM / supplemental web
  work with: wall clock, elapsed, last substep, Codex PID if any,
  Codex stdout/stderr tail.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u /tmp/run_pain_point_intel_<job>.py \
  > /tmp/pain_point_intel_<job>.log 2>&1 &
```

### 17.6 Full-chain path (fallback)

If the fast path is blocked by `StageContext` construction drift:

- enqueue `work_items` for the full prerequisite chain;
- start `preenrich_worker_runner.py` with
  `PREENRICH_STAGE_ALLOWLIST="pain_point_intelligence"`;
- same `.venv`, `python -u`, Python-side `.env`, `MONGODB_URI`
  discipline;
- same operator heartbeat.

### 17.7 Required launcher behavior

- `.venv` activated (`source /root/scout-cron/.venv/bin/activate`
  OR absolute path to `.venv/bin/python`);
- `python -u` unbuffered;
- `.env` loaded from Python, not `source .env`;
- `MONGODB_URI` present;
- Codex subprocess cwd defaults to an isolated `/tmp/codex-work-<job>/`
  unless repo context is explicitly required (set via
  `PREENRICH_CODEX_WORKDIR_PAIN_POINT_INTELLIGENCE` — only for
  debugging, never default);
- inner Codex PID and first 128 chars of stdout / stderr logged on
  every heartbeat.

### 17.8 Heartbeat requirements

- stage-level heartbeat every 15–30 s from the wrapper;
- lease heartbeat every 60 s by the worker
  (`PREENRICH_STAGE_HEARTBEAT_SECONDS`);
- Codex PID/stdout/stderr every heartbeat if supplemental web fires;
- silence for > 90 s between heartbeats is a stuck-run flag.

### 17.9 Expected Mongo writes

On success:

- `pain_point_intelligence` collection: new doc keyed by
  `(job_id, input_snapshot_id, prompt_version)`;
- `level-2.pre_enrichment.outputs.pain_point_intelligence`
  populated;
- `level-2.pre_enrichment.stage_states.pain_point_intelligence`:
  `status=completed`, `attempt_count`, `lease_owner` cleared,
  `trace_id`, `trace_url` set;
- `preenrich_stage_runs`: one row with `status=completed`,
  `trace_id`, `trace_url`, `provider_used`, `model_used`,
  `prompt_version`, `tokens_input`, `tokens_output`, `cost_usd`;
- `preenrich_job_runs`: aggregate updated;
- `work_items`: this row `status=completed`;
  `preenrich.enqueue_next` fires `presentation_contract` when flag on.

### 17.10 Expected Langfuse traces

In the same trace (`scout.preenrich.run`), pinned to
`langfuse_session_id=job:<level2_id>`:

- `scout.preenrich.pain_point_intelligence` stage span, full §15.4
  metadata;
- `scout.preenrich.pain_point_intelligence.evidence_mine`,
  `.prompt_build`, `.llm_call.primary`
  (+ `.llm_call.fallback` if fallback fired),
  `.post_pass`, `.artifact_persist`;
- optionally `.schema_repair`, `.supplemental_web`;
- one `cache.hit` or `cache.miss` event;
- canonical lifecycle events (`claim`, `enqueue_next`).

### 17.11 Expected preenrich_stage_runs / preenrich_job_runs

- `stage_runs` row has `trace_id`, `trace_url`, `fail_open_reason`
  iff non-completed;
- `job_runs` aggregate has updated `stage_status_map.pain_point_intelligence`.

### 17.12 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/pain_point_intel_<job>.log`;
- inspect Codex PID:
  `ps -p <pid> -o pid,etime,stat,cmd`;
- inspect last output age (touch ctime on
  `/tmp/codex-work-<job>/stdout.log`);
- inspect Mongo stage_state:
  `level-2.pre_enrichment.stage_states.pain_point_intelligence.lease_expires_at`;
- if lease is expiring and no progress, kill the launcher, do not
  restart until the prior PID is confirmed gone.

Silence is not progress.

### 17.13 Acceptance criteria

- log ends with `PAIN_POINT_INTELLIGENCE_RUN_OK job=<id> status=<status> trace=<url>`;
- Mongo writes match §17.9;
- Langfuse trace matches §17.10;
- stage output validates against `PainPointIntelligenceDoc`;
- spot-check: no fabricated company events, `proof_map[]`
  referentially clean, every pain has `evidence_refs[]`;
- fail-open run (research-thin job) returns `status=partial` with
  `fail_open_reason=thin_research`, not deadletter.

### 17.14 Artifact / log / report capture

Create `reports/pain-point-intelligence/<job_id>/` containing:

- `run.log` — full stdout/stderr;
- `stage_output.json` — the emitted `PainPointIntelligenceDoc`;
- `trace_url.txt` — Langfuse URL;
- `stage_runs_row.json` — `preenrich_stage_runs` row dump;
- `mongo_writes.md` — human summary of §17.9 checks;
- `acceptance.md` — pass/fail list for §17.13.

## 18. Rollout, Feature Flags, Migration

### 18.1 Rollout order

1. Ship stage behind `pain_point_intelligence_enabled()` off;
   unit + stage contract tests green; smoke test against one job in
   staging.
2. Flip on for a curated 30-job corpus in staging; collect eval
   metrics (§16.11); gate default-on on SC1–SC5.
3. Default-on in production; keep
   `pain_point_intelligence_compat_projection_enabled()` on so
   legacy root-level fields continue to populate for one release.
4. Flip compat projection off after `presentation_contract`
   (4.2.2 / 4.2.4 / 4.2.5 / 4.2.6) is default-on and consuming the
   new artifact.

### 18.2 Migration path

- no backfill of historical jobs at ship; the stage runs lazily on
  the next pipeline touch;
- jobs with legacy `pain_points` root fields keep them until
  compat projection is removed;
- `blueprint_assembly` always reads from
  `pre_enrichment.outputs.pain_point_intelligence` first, falls back
  to proxy synthesis only if the field is absent.

### 18.3 Rollback

See §14.12. Toggle the flag; no data loss; no migration.

## 19. Open Questions

Q1. Proof-type enum ownership: 4.2.3 owns `ProofTypeEnum` (decided
    above). Confirm 4.2.2, 4.2.4, 4.2.5 import it rather than
    redefine.
Q2. Supplemental web budget: is `max_web_queries=2` correct for
    research-thin jobs, or should it be model-cost-gated?
Q3. Should `high` urgency require 2 converging evidence refs across
    distinct `source_types` (company vs role vs application),
    rather than any two refs? Recommend yes; gate on eval signal.
Q4. Does the stage need a separate `cv_guidelines` compat mode if
    older jobs lack `research_enrichment`? Recommend no — they fail
    open to JD-only.
Q5. Do reviewer UI needs require any additional field
    (e.g. `why_now_summary` at top level)? Defer until 4.2.4.

## 20. Primary Source Surfaces

- `src/layer2/pain_point_miner.py` (legacy; read-only for design)
- `src/preenrich/stages/research_enrichment.py`
- `src/preenrich/stages/job_inference.py`
- `src/preenrich/stages/blueprint_assembly.py`
- `src/preenrich/blueprint_models.py`
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/stage_registry.py`
- `src/preenrich/stage_worker.py`
- `src/pipeline/tracing.py`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md`
- `plans/iteration-4.2-cv-skeleton-input-contract-and-presentation-bridge.md`
- `plans/iteration-4.2.1-stakeholder-intelligence-and-persona-expectations.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`

## 21. Implementation Targets

- new `src/preenrich/stages/pain_point_intelligence.py`
- new `PainPointIntelligenceDoc`, `PainPointEntry`,
  `StrategicNeedEntry`, `RiskEntry`, `SuccessMetricEntry`,
  `ProofMapEntry`, `SearchTerm`, `PainPointDebugContext` in
  `src/preenrich/blueprint_models.py`
- new `ProofTypeEnum`, `PainCategoryEnum`,
  `StrategicNeedCategoryEnum`, `RiskCategoryEnum`,
  `SuccessMetricKindEnum` in `src/preenrich/blueprint_models.py`
  (or a new `src/preenrich/pain_enums.py` re-exported)
- new `build_p_pain_point_intelligence` in
  `src/preenrich/blueprint_prompts.py` with `PROMPT_VERSIONS`
  entry
- register stage in `src/preenrich/stage_registry.py`
- wire prerequisites in `src/preenrich/dag.py`
- update `src/preenrich/stages/blueprint_assembly.py` to project
  `pain_point_intelligence_compact` and to fall back to proxy
  synthesis only when flag off
- extend `src/pipeline/tracing.py` only if a new payload builder
  field is needed (prefer metadata-only extensions)
- update `docs/current/architecture.md` "Iteration 4.2.3" section
- update `docs/current/missing.md`
- new tests under `tests/preenrich/test_pain_point_intelligence.py`
  and `tests/data/pain_point_intel/`
- new `scripts/smoke_pain_point_intelligence.py` (local) and
  `scripts/vps_run_pain_point_intelligence.py` (VPS wrapper template)
