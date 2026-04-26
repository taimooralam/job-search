# Iteration 4.3.6 Plan: Publisher, Renderer, and Remote Delivery Integration

## 1. Executive Summary

By the time a job reaches `lifecycle="cv_assembled"`, it carries a
validator-clean `cv_assembly.synthesis` (4.3.5), a winning draft id,
a header blueprint (4.3.2), and a dossier evidence map (4.3.7).
4.3.6 is the stage that turns that validated artifact set into
**delivered files** — a rendered CV PDF, a rendered dossier PDF, a
Google Drive folder, a Google Sheets row, and an updated `level-2`
projection — while preserving every existing reader of legacy
publisher fields and never inventing prose.

This plan makes five contracts explicit, all of which are missing or
hand-waved in the prior revision:

1. **Hard prerequisites** at claim time (§8). Render is gated on
   synthesis validator status, pdf-service `/health` freshness, n8n
   reachability, Google OAuth scope validity, and Sheets quota.
2. **The pdf-service `/health` gate** is a real circuit breaker
   with N consecutive failures, M consecutive recoveries, freshness
   window, and per-surface CV-vs-dossier semantics (§12).
3. **n8n idempotency** is not a wish — it is a publisher-side and
   workflow-side contract over a stable `request_id`, an
   authoritative workflow JSON committed at
   `n8n/workflows/cv-upload.json`, and Mongo-side short-circuiting
   when a prior `done` artifact is present (§14).
4. **Google Sheets row schema** is enumerated to 12 columns with
   types, nullability, and the upsert key; the last three columns
   (`winner_draft_id`, `synthesis_hash`, `pattern_label`) are new in
   4.3.6 (§15).
5. **Compatibility projection** is written in the **same Mongo
   `findOneAndUpdate`** that performs the `published` CAS, so a
   crash cannot leave the legacy fields and `cv_assembly.published_at`
   out of sync (§10.2 + §16.1).

The Layer 7 publisher path (`output_publisher.publish()`),
pdf-service (Playwright/Chromium), n8n webhook, Google Drive, and
Google Sheets are preserved verbatim; 4.3.6 adapts inputs, formalizes
state, and adds idempotency and observability — it does not replace
any of them. The dossier evidence body is owned by 4.3.7
(`cv_assembly.dossier_state.body_html`); 4.3.6 owns the **render
artifact and upload state** (`cv_assembly.publish_state.render.dossier`,
`...upload.drive.dossier`).

## 2. Mission

Turn every `cv_assembled` job into delivered artifacts — CV PDF,
dossier PDF, Drive folder, Sheets row, legacy projections — through
the existing Layer 7 + pdf-service + n8n + Drive/Sheets path, with
explicit hard prerequisites, an idempotent webhook contract, atomic
projection writes, observable per-surface state, and CAS-guarded
`published` and `delivered` lifecycle transitions, so a job can be
retried, replayed, or partially recovered without producing
inconsistent state for any downstream reader.

## 3. Objectives

O1. Define a `cv_assembled → published → delivered` lane with five
    explicit task types: `publish.render.cv`, `publish.render.dossier`,
    `publish.upload.drive`, `publish.upload.sheets`,
    `publish.finalize`.
O2. Adapt `output_publisher.publish()` to accept a strict input
    contract (§9) sourced from `cv_assembly.winner` /
    `cv_assembly.synthesis` / `cv_assembly.dossier_state` — no
    re-derivation of prose, no mutation of upstream state.
O3. Persist a per-surface `cv_assembly.publish_state` (§11) that
    distinguishes pending / in-progress / done / degraded / failed
    per render and per upload, with `request_id`, `attempt_count`,
    `artifact_sha256`, `trace_ref`, and timing fields.
O4. Lock the pdf-service `/health` circuit breaker semantics (§12).
O5. Lock the n8n idempotency contract (§14): authoritative workflow
    file path; stable `request_id`; dedup TTL; duplicate-request
    response shape; publisher-side Mongo short-circuit.
O6. Enumerate the Google Sheets row schema (§15) with the three new
    columns added in 4.3.6 and an explicit upsert/append policy.
O7. Formalize `published` and `delivered` lifecycle CAS (§16) with
    event emission rules and partial-success operator status.
O8. Lock the compatibility projection map (§10.1) and its same-update
    atomicity contract with the `published` CAS (§10.2).
O9. Emit Langfuse traces under `scout.cv_assembly.publish.*` with
    standardized metadata and forbidden-payload enumeration (§22).
O10. Ship a frozen eval corpus and fault-injection harness under
     `data/eval/validation/cv_assembly_4_3_6_publish/` (§23).
O11. Validate end-to-end on the VPS against a real eligible job per
     §24 before default-on rollout.

## 4. Success Criteria

4.3.6 is done when, in production, all of the following hold:

SC1. Every `lifecycle=cv_assembled` job either reaches
     `lifecycle=published` (CV PDF + dossier PDF rendered, CV PDF +
     dossier PDF uploaded to Drive, Sheets row written) or terminates
     with a deterministic per-surface failure that an operator can
     diagnose from `cv_assembly.publish_state`.
SC2. Re-running the publish lane on a `published` job is a no-op for
     remote sinks (n8n returns the original `file_id`; Sheets does
     not append a duplicate row); `published_at` is unchanged.
SC3. The pdf-service `/health` gate prevents claim of `publish.render.*`
     work when the gate is open; gate state is observable in Mongo
     (`pdf_service_health_state` collection §12) and Langfuse.
SC4. No legacy reader of `level-2` regresses: every legacy publisher
     field (`cv_text`, `cv_path`, `cv_reasoning`, `generated_dossier`,
     `drive_folder_url`, `sheet_row_id`, `gdrive_uploaded_at`,
     `dossier_gdrive_uploaded_at`, `fit_score`, `fit_rationale`,
     `selected_star_ids`, `pipeline_runs[]`, `total_cost_usd`,
     `token_usage`, `status`) is populated with values derived from
     `cv_assembly.*` per §10.1.
SC5. Compatibility projection and `cv_assembly.published_at` are
     either both present or both absent; the partial-write window is
     zero (asserted by a fault-injection test that crashes the
     finalizer mid-update).
SC6. n8n idempotency holds under a 3× concurrent retry storm; one
     `request_id` produces exactly one Drive `file_id` for that
     request_id (asserted by §23 harness).
SC7. Sheets row schema has 12 columns in declared order; new columns
     are populated when synthesis exists; nullability matches §15.
SC8. Langfuse trace for any single `cv_assembled` job surfaces every
     §22 span and event; operator can reach Mongo `trace_ref` from
     the operator UI.
SC9. VPS smoke pass (§24) completed on a real eligible job with
     artifacts captured under `reports/cv-assembly-publish/<job_id>/`.

## 5. Non-Goals

- Redesigning `output_publisher.publish()`. 4.3.6 adapts its input
  shape and adds a per-surface state writer; it does not change the
  ordering of local-save → Mongo persist → Drive → Sheets within
  `publish()`.
- Replacing the n8n webhook with a direct Drive API call. That is
  triaged §26 as safe-to-defer.
- Changing the pdf-service HTTP contract. Same endpoints
  (`/health`, `/render-pdf`, `/cv-to-pdf`, `/url-to-pdf`,
  `/scrape-linkedin`); no breaking schema changes.
- Adding a local non-Playwright CV render fallback. If pdf-service
  is unhealthy past budget, the job fails terminally; we never
  publish a degraded CV PDF to Drive.
- Creating a new Mongo collection for publish state. `level-2` is
  authoritative; `cv_assembly.publish_state` lives inline.
- Generating dossier prose. 4.3.7 owns `dossier_state.body_*`;
  4.3.6 only renders the bytes 4.3.7 produces.
- Mutating `pre_enrichment.*` or any 4.3.5 output. 4.3.6 reads and
  appends only.

## 6. Why This Stage Exists

The publisher exists. The pdf-service exists. n8n exists. Yet the
current path (Layer 7 `OutputPublisher.publish()` + standalone
`gdrive_upload_service`) cannot ship 4.3 outputs as-is, for five
reasons:

1. **Input source has moved.** Layer 7 reads `state['cv_text']`,
   `state['cv_path']`, `state['generated_dossier']`. After 4.3.5,
   the canonical content is under `cv_assembly.winner` /
   `cv_assembly.synthesis` / `cv_assembly.dossier_state`. Some
   adapter must read the new namespace and write the legacy fields
   until every downstream reader migrates.
2. **One CV is no longer one CV.** With three drafts plus a
   synthesis, the wrong PDF is a real failure mode. We need
   `winner_draft_id` and `synthesis_hash` carried into the upload
   payload so a lost upload can be reconciled and so an audit can
   prove which draft + synthesis produced the artifact.
3. **Multi-surface partial success is real.** Today's `publish()`
   collapses dossier render failures, Drive upload failures, and
   Sheets failures into one boolean. With three renders and three
   uploads each separately retriable, partial success must be
   observable and resumable.
4. **Idempotency is currently absent.** `gdrive_upload_service.py`
   sends `jobId` to the n8n webhook, not a stable `request_id`. A
   retry inside the same lifecycle run would (and does) create a
   duplicate Drive file. The 4.3 lane will retry under load.
5. **Atomicity between projection and CAS is missing.** Today's
   `_persist_to_mongodb` writes legacy fields in one call; the n8n
   webhook updates `gdrive_uploaded_at` in another. A crash between
   them produces "published-looking" jobs whose lifecycle never
   advances. We need the projection and the lifecycle transition to
   land in the same Mongo update.

4.3.6 fixes all five without rewriting the publisher.

## 7. Stage Boundary

### 7.1 DAG position

```text
cv_assembled
  ├─ publish.render.cv         ─┐
  ├─ publish.render.dossier    ─┤  (parallel)
  ↓                             │
  ├─ publish.upload.drive.cv   ─┤  (waits on render.cv)
  ├─ publish.upload.drive.dossier  (waits on render.dossier; degradable)
  ↓                             │
  └─ publish.upload.sheets     ─┘  (waits on upload.drive.cv)
        ↓
   publish.finalize  →  lifecycle = published
        ↓
   (n8n ACK observed)  →  lifecycle = delivered
```

`publish.finalize` is a single sweeper-style finalizer (no LLM call)
that performs the §16.1 `published` CAS *and* the §10.2 compatibility
projection in one atomic Mongo update.

### 7.2 Inputs (canonical sources)

Required upstream — all on `level-2`:

- `cv_assembly.synthesis.final_cv_struct` (TipTap-equivalent doc)
- `cv_assembly.synthesis.final_cv_text` (string)
- `cv_assembly.synthesis.cover_letter` (nullable; falls back to
  winner draft cover letter)
- `cv_assembly.synthesis.synthesis_hash` (sha256 over the canonical
  serialization of `final_cv_struct`)
- `cv_assembly.synthesis.validator_report.status` (must be
  `pass` or `repair_attempted`; not `failed`)
- `cv_assembly.winner.draft_id` (string)
- `cv_assembly.winner.pattern_id` (string)
- `cv_assembly.winner.pattern_label` (enum)
- `cv_assembly.winner.grade.composite_score` (float in [0, 1])
- `cv_assembly.winner.grade.dimensions[*].rationale`
- `cv_assembly.winner.grade.rationale_summary` (≤ 300 chars)
- `cv_assembly.synthesis.evidence_lineage.bullet_lineage[*].achievement_id`
  (for `selected_star_ids` projection)
- `cv_assembly.dossier_state.body_html` (4.3.7-owned; required for
  dossier render unless degraded path engaged per §13.2)
- `cv_assembly.dossier_state.body_sha256`
- `cv_assembly.dossier_state.source` (`evidence_map` |
  `best_effort_fallback` | `partial`)
- `cv_assembly.header_blueprint.identity.chosen_title` (used as
  publisher's `role` argument when `state.title` is missing)
- `pre_enrichment.outputs.research_enrichment.company_profile` /
  `role_profile` (unchanged; for projection of `company_summary`)
- `pre_enrichment.outputs.pain_point_intelligence.*` (unchanged;
  for projection of `pain_points`, `strategic_needs`,
  `risks_if_unfilled`, `success_metrics`)
- `pre_enrichment.outputs.stakeholder_surface.primary_contacts` /
  `secondary_contacts` (unchanged; passed through to projection)
- `extracted_jd` (Layer 1.4 output; unchanged)
- top-level `company`, `title`, `job_url`, `source` (unchanged
  `level-2` fields)

### 7.3 Outputs (canonical writes)

Per task, on success:

- `cv_assembly.publish_state.render.cv.*` (see §11)
- `cv_assembly.publish_state.render.dossier.*` (see §11)
- `cv_assembly.publish_state.upload.drive.cv.*` (see §11)
- `cv_assembly.publish_state.upload.drive.dossier.*` (see §11)
- `cv_assembly.publish_state.upload.sheets.*` (see §11)
- `cv_assembly.publish_state.summary.*`
- `cv_assembly.published_at` (set by `publish.finalize` only, via
  §16.1 CAS)
- `cv_assembly.delivered_at` (set by `publish.finalize` re-entry only,
  via §16.2 CAS, when n8n ACK is observed)
- legacy compatibility projection on `level-2` root (§10.1) —
  written **only** in the `publish.finalize` `findOneAndUpdate`,
  same update as `published_at`.
- `pdf_service_health_state` collection — periodic write by health
  prober (§12).

### 7.4 Task ownership and work-item details

| Task type | Reads | Writes | `required_for_published` |
|-----------|-------|--------|--------------------------|
| `publish.render.cv` | `cv_assembly.synthesis.final_cv_struct`, `header_blueprint` (footer fields), `documentStyles` | `publish_state.render.cv` | yes |
| `publish.render.dossier` | `cv_assembly.dossier_state.body_html` | `publish_state.render.dossier` | no (degradable to `degraded`) |
| `publish.upload.drive.cv` | `publish_state.render.cv.artifact_local_path`, top-level `company`, `title`, `jobId` | `publish_state.upload.drive.cv` | yes |
| `publish.upload.drive.dossier` | `publish_state.render.dossier.artifact_local_path` | `publish_state.upload.drive.dossier` | no (degradable) |
| `publish.upload.sheets` | row tuple per §15 | `publish_state.upload.sheets` | no (sidecar) |
| `publish.finalize` | full `publish_state`, `cv_assembly.synthesis`, `cv_assembly.winner`, projection sources (§10.1) | `cv_assembly.published_at`, all legacy projection fields, `pipeline_runs[]` push | n/a (this *is* the finalizer) |

For every render/upload work item:

- `lane = publish`.
- `idempotency_key = <task_type>:<level2_id>:<input_snapshot_id>:
   <winner_draft_id>:<synthesis_hash>` for renders;
  `idempotency_key = <task_type>:<level2_id>:<input_snapshot_id>:
   <winner_draft_id>:<synthesis_hash>:<artifact_sha256>` for uploads.
- `request_id` (sent to n8n) = sha256(idempotency_key)[:32].
- `max_attempts`: render = 5; drive upload = 5; sheets = 3;
  finalize = 5. Backoff per iteration-4 pattern.
- `lease_seconds`: render = 180; drive upload = 90; sheets = 60;
  finalize = 30.
- Heartbeat interval: 30 s for renders, 15 s for uploads, 10 s for
  finalize.
- Deadletter on attempt budget exhaustion → `cv_assembly.status =
  failed`; lifecycle stays `cv_assembled` for required tasks
  (operator may re-enqueue) and stays `cv_assembled` for degradable
  tasks too — degradation only applies to dossier render/upload that
  fails *transiently* before deadletter.

### 7.5 Source-of-truth chain

| Concern | Owned by | Defined in |
|---------|----------|------------|
| CV prose / structured doc | 4.3.5 synthesis | `cv_assembly.synthesis.final_cv_struct` / `final_cv_text` |
| Dossier prose / HTML body | 4.3.7 | `cv_assembly.dossier_state.body_html` |
| CV PDF render artifact | 4.3.6 | `cv_assembly.publish_state.render.cv.artifact_local_path` |
| Dossier PDF render artifact | 4.3.6 | `cv_assembly.publish_state.render.dossier.artifact_local_path` |
| Drive folder URLs / file ids | 4.3.6 | `cv_assembly.publish_state.upload.drive.*` |
| Sheets row id | 4.3.6 | `cv_assembly.publish_state.upload.sheets.row_id` |
| `published_at` lifecycle stamp | 4.3.6 finalize | `cv_assembly.published_at` |
| `delivered_at` lifecycle stamp | 4.3.6 finalize re-entry | `cv_assembly.delivered_at` |
| Legacy `level-2` publisher fields | 4.3.6 finalize (atomic projection) | `level-2` root |
| `cv_assembly.dossier_state` schema | 4.3.7 | 4.3.7 §8.1 |
| pdf-service health state | 4.3.6 (prober) | `pdf_service_health_state` Mongo collection |

Implications:

- 4.3.6 may not write to `cv_assembly.dossier_state.body_*` or
  `dossier_state.source`. Those are 4.3.7. 4.3.6 writes a render
  reference at `publish_state.render.dossier` only.
- 4.3.6 may not mutate `cv_assembly.synthesis.*` or
  `cv_assembly.winner.*`.
- The legacy `level-2` projection is an output of 4.3.6's finalizer,
  not of any individual upload task. No upload task touches the root
  of `level-2`.

## 8. Hard Prerequisites

Before any `publish.*` work item is *claimed*, the prerequisite check
runs at claim time on the work-item row. Failures push `available_at`
forward by backoff and emit a structured event; they do not delete
the work item.

| Prereq | Check | Blocking | Degradable | On unmet |
|--------|-------|----------|------------|----------|
| `lifecycle == "cv_assembled"` | level-2 read | yes | no | reject claim |
| `cv_assembly.synthesis.validator_report.status ∈ {pass, repair_attempted}` | level-2 read | yes | no | reject claim → publishing terminally fails the lane |
| `cv_assembly.synthesis.synthesis_hash` present | level-2 read | yes | no | reject claim |
| `cv_assembly.winner.draft_id` present | level-2 read | yes | no | reject claim |
| `cv_assembly.dossier_state.source` present (any value) | level-2 read | for `publish.render.dossier` only | yes — if absent, render is skipped and `publish_state.render.dossier.status=degraded` with `reason=dossier_state_missing` | proceed for CV; degrade dossier |
| pdf-service `/health` returns `playwright_ready=true` within `PUBLISH_PDF_HEALTH_FRESHNESS_SECONDS` (default 300s) | `pdf_service_health_state` collection read | yes for `publish.render.*` | no | push `available_at` by backoff; emit `pdf_service_unhealthy` event |
| n8n webhook reachable (DNS + TCP within `PUBLISH_N8N_REACHABILITY_TIMEOUT_SECONDS`, default 10s) | live probe at upload claim time | yes for `publish.upload.drive.*` | no | push `available_at` by backoff; emit `n8n_unreachable` event |
| Google Drive OAuth scopes present and non-expired (service-account credentials load and reflect `drive` + `spreadsheets` scopes) | publisher init | yes for `publish.upload.drive.*` and `publish.upload.sheets` | no | reject claim; alert |
| Google Sheets API quota not exhausted (caller-side rate limiter; 6h window) | `publisher_rate_limiter` Mongo doc | sidecar — does not block `published`, blocks the Sheets task only | yes — Sheets task degrades to `status=skipped` with `reason=quota_exhausted` after `PUBLISH_SHEETS_QUOTA_RETRY_BUDGET` (default 3) attempts | degrade Sheets only |
| Render artifact present and `artifact_sha256` matches recorded hash | finalize-time read | yes for `publish.upload.drive.*` | no | reject claim; require fresh render |
| Feature flag `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=true` for the cutover branch | env / config | yes (post-cutover only; pre-cutover the legacy path runs) | n/a | route to legacy single-pass `output_publisher.publish()` |
| Feature flag `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED=true` (default true) | env / config | yes for `publish.finalize` | yes — when false, finalize emits an alert and proceeds without projection write (only for emergency rollback) | finalize without projection |

Concrete behaviors:

- **Synthesis degraded but valid** (`synthesis.degraded=true` and
  `validator_report.status ∈ {pass, repair_attempted}`): publish
  proceeds. Synthesis improvement delta is reported but does not
  block.
- **CV render OK but dossier render impossible**: `publish.render.cv`
  succeeds; `publish.render.dossier` and `publish.upload.drive.dossier`
  enter `status=degraded` after the dossier-render retry budget is
  exhausted; `published` finalizer still fires (CV is the required
  surface; dossier is degradable).
- **Sheets quota exhausted but Drive upload succeeds**: Sheets
  status=`skipped` with reason; `published` fires; an alert is
  emitted; the Sheets row is *not* backfilled later (best-effort
  sidecar by design).
- **n8n reachable intermittently**: claim is pushed forward; idempotency
  contract (§14) ensures a duplicate `request_id` returns the original
  `file_id` if a prior attempt actually completed in n8n but the
  publisher lost the response.
- **Inputs unreadable from `cv_assembly.*` or `level-2`**: prerequisite
  check fails at claim; lifecycle stays `cv_assembled`; alert fires.

## 9. Input Contract to `output_publisher.publish()`

`OutputPublisher.publish()` is extended with a strict input adapter
controlled by `cv_assembly_source: bool` (default `True` post-cutover).

### 9.1 Required input shape (when `cv_assembly_source=True`)

```python
PublishInput {
    # identity
    job_id: str,                     # level-2 _id as string
    company: str,                    # level-2 root
    title: str,                      # level-2 root, == header_blueprint.identity.chosen_title when populated
    job_url: Optional[str],
    source: Optional[str],
    render_variant: Literal["ats_safe", "recruiter_rich", "regional_enriched"],
    header_surface_policy: Dict,     # exact 4.3.2 policy used by the renderer

    # winner / synthesis (canonical 4.3.5 outputs)
    winner_draft_id: str,
    winner_pattern_id: str,
    winner_pattern_label: str,
    winner_grade: GradeProjection {  # see §10.1
        composite_score: float,      # in [0, 1]
        composite_score_legacy: float,  # composite_score * 10, for legacy fit_score
        dimensions: List[GradeDimensionProjection],
        rationale_summary: str,
    },
    synthesis_hash: str,
    final_cv_struct: TipTapDoc,      # the document the publisher renders via /cv-to-pdf
    final_cv_text: str,              # plain-text projection, for legacy cv_text
    final_cv_reasoning: str,         # synthesis.debug_context.reasoning_summary ∪ winner rationale
    cover_letter: Optional[str],     # synthesis.cover_letter ∪ winner draft cover letter
    selected_star_ids: List[str],    # dedup of evidence_lineage.bullet_lineage[*].achievement_id

    # dossier (4.3.7-owned)
    dossier_body_html: Optional[str],
    dossier_body_sha256: Optional[str],
    dossier_source: Literal["evidence_map", "best_effort_fallback", "partial", "missing"],

    # contacts and prerequirements (passthrough)
    primary_contacts: Optional[List[Contact]],
    secondary_contacts: Optional[List[Contact]],

    # research / pain projection sources (passthrough)
    company_summary: Optional[str],
    extracted_jd: Optional[Dict],
    pain_points: Optional[List[str]],
    strategic_needs: Optional[List[str]],
    risks_if_unfilled: Optional[List[str]],
    success_metrics: Optional[List[str]],

    # cost and run tracking
    total_cost_usd: float,
    token_usage: Dict,
    run_id: str,
    processing_tier: str,

    # observability
    trace_parent: TraceParent,       # langfuse trace id + span id for parent
}
```

### 9.2 Mandatory vs optional

Mandatory (publisher rejects if absent):

- `job_id`, `company`, `title`, `winner_draft_id`, `synthesis_hash`,
  `final_cv_struct`, `final_cv_text`, `winner_grade.composite_score`,
  `selected_star_ids`, `total_cost_usd`, `token_usage`, `run_id`,
  `processing_tier`, `trace_parent`, `render_variant`,
  `header_surface_policy`.

Optional (projection writes the field only when present; no
fabrication on absence):

- `cover_letter`, `dossier_body_html`, `primary_contacts`,
  `secondary_contacts`, `company_summary`, `extracted_jd`, the four
  pain dimensions, `job_url`, `source`.

### 9.3 What the publisher is forbidden to do

- Re-derive `final_cv_struct` from `state['cv_text']` or any other
  source. The struct is opaque input.
- Generate any prose. No fallback summarization, no rationale
  stitching, no synthetic cover letters.
- Mutate `pre_enrichment.*`.
- Mutate `cv_assembly.synthesis.*`, `cv_assembly.winner.*`, or
  `cv_assembly.dossier_state.body_*`.
- Skip `synthesis_hash` validation. Before sending bytes to n8n, the
  publisher recomputes sha256 over the rendered PDF and asserts that
  the sha matches the recorded `publish_state.render.cv.artifact_sha256`,
  preventing stale-draft uploads after a render-then-rerender race.
- Touch `pipeline_runs[]` outside the `publish.finalize` atomic
  update.

### 9.4 Legacy fallback (when `cv_assembly_source=False`)

The publisher reads from the legacy state shape (`state['cv_text']`,
`state['cv_path']`, `state['generated_dossier']`, ...) and skips
4.3-only writes (`publish_state`, atomic projection). This branch is
preserved for rollback only and is removed in a follow-up release
once no callers remain.

## 10. Compatibility Projection Contract

### 10.1 Field-by-field projection map

Canonical projection from `cv_assembly.*` → legacy `level-2` root.
This map is encoded in `src/cv_assembly/compat/projection.py` per
4.3.7 §10. 4.3.6 is the only writer of these legacy fields when
`cv_assembly_source=True`.

| Legacy field | Type | Source | Projection rule |
|--------------|------|--------|-----------------|
| `cv_text` | str | `synthesis.final_cv_text` | identity |
| `cv_path` | str | local file path written by publisher from `final_cv_struct` | absolute path, sanitized per `sanitize_path_component` |
| `cv_reasoning` | str | `synthesis.debug_context.reasoning_summary` ∪ `winner.grade.rationale_summary` | concat with `\n\n---\n\n` separator |
| `cover_letter` | str | nullable: `synthesis.cover_letter` ∪ `winner.draft.cover_letter` | first non-null |
| `generated_dossier` | str | `cv_assembly.dossier_state.body_markdown` (4.3.7) | identity if present; otherwise unchanged (don't overwrite with null) |
| `fit_score` | float (0-10) | `winner.grade.composite_score * 10` | round to 1 dp |
| `fit_rationale` | str | concat of `winner.grade.dimensions[*].rationale` separated by `\n` | clamp to 2000 chars |
| `selected_star_ids` | List[str] | `synthesis.evidence_lineage.bullet_lineage[*].achievement_id` | dedup, preserve first occurrence |
| `primary_contacts` | List[Contact] | `pre_enrichment.outputs.stakeholder_surface.primary_contacts` | passthrough, identity |
| `secondary_contacts` | List[Contact] | same | passthrough, identity |
| `pain_points` | List[str] | `pain_point_intelligence.pain_points[*].description` | passthrough |
| `strategic_needs` | List[str] | `pain_point_intelligence.strategic_needs[*].description` | passthrough |
| `risks_if_unfilled` | List[str] | `pain_point_intelligence.risks_if_unfilled[*].description` | passthrough |
| `success_metrics` | List[str] | `pain_point_intelligence.success_metrics[*].description` | passthrough |
| `company_summary` | str | `research_enrichment.company_profile.summary` | passthrough |
| `extracted_jd` | dict | `pre_enrichment.outputs.jd_facts` projection | identity |
| `drive_folder_url` | str | `publish_state.upload.drive.cv.role_folder` resolved to URL | `f"https://drive.google.com/drive/folders/{folder_id}"` |
| `sheet_row_id` | int | `publish_state.upload.sheets.row_id` | identity |
| `gdrive_uploaded_at` | datetime | `publish_state.upload.drive.cv.uploaded_at` | identity |
| `dossier_gdrive_uploaded_at` | datetime | `publish_state.upload.drive.dossier.uploaded_at` | identity (null if dossier upload degraded) |
| `total_cost_usd` | float | sum across `cv_assembly.drafts[*].cost_usd` + `grades` + `synthesis` + `publish_state.summary.total_cost_usd` | sum |
| `token_usage` | dict | merged across the same scopes | sum keyed by stage |
| `pipeline_runs[]` (push) | list[dict] | one new entry: `{run_id, tier, status, cost_usd, timestamp}` | $push |
| `status` | str | constant `"ready for applying"` on `published` | identity |
| `pipeline_run_at` | datetime | finalizer `$$NOW` | identity |

**Null-preserving rule.** Absent `cv_assembly.*` source projects to
the legacy field's existing value; the projection never overwrites a
populated legacy field with null. `$set` operations skip null-valued
keys.

### 10.2 Atomicity / write semantics

The compatibility projection write occurs exclusively inside
`publish.finalize`'s `findOneAndUpdate` that performs the §16.1
`published` CAS. There is no other writer of legacy publisher fields
when `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=true`.

```python
# pseudo-code; canonical impl in src/cv_assembly/sweepers.py
result = level2.find_one_and_update(
    filter={
        "_id": object_id,
        "lifecycle": "cv_assembled",
        "cv_assembly.published_at": {"$exists": False},
        "cv_assembly.publish_state.render.cv.status": "done",
        "cv_assembly.publish_state.render.dossier.status": {
            "$in": ["done", "degraded"]
        },
        "cv_assembly.publish_state.upload.drive.cv.status": "done",
        "cv_assembly.publish_state.upload.drive.dossier.status": {
            "$in": ["done", "degraded"]
        },
    },
    update={
        "$set": {
            "lifecycle": "published",
            "cv_assembly.published_at": SERVER_TIMESTAMP,
            **{k: v for k, v in projection.items() if v is not None},
        },
        "$push": {
            "pipeline_runs": pipeline_run_entry
        },
    },
    return_document=ReturnDocument.AFTER,
)
```

**Crash semantics.**

- *Crash before update.* No legacy field changes; no `published_at`.
  Re-run of the finalizer enters the same CAS branch deterministically;
  projection is recomputed from current `cv_assembly.*` and applied
  in the same way. Idempotent.
- *Crash after update commits but before the worker writes its
  stage-run record.* `published_at` is set; legacy fields are
  populated; the work-item row reverts to claimable on lease expiry.
  The next finalizer claim observes `published_at` already set →
  CAS misses → emit `published_cas_conflict` event → idempotent
  no-op completion of the work item.
- *Partial-write window.* Zero. Mongo `findOneAndUpdate` is a
  single-document atomic operation. Either the entire `$set` lands
  or none of it does.

**Retry on CAS miss.**

If the filter doesn't match (e.g., one render is still
`in_progress` because of a phantom claim race), the finalizer emits
`published_finalize_preconditions_unmet` with a structured snapshot
of which sub-states blocked the CAS, pushes `available_at` forward
by backoff, and retries up to `max_attempts=5`.

**Replay.**

Re-running the finalizer on a `published` job:
- filter `cv_assembly.published_at: {$exists: false}` excludes the
  doc → CAS miss; emit `published_cas_already_set`; mark work-item
  done. Projection is *not* re-written. Once published, the legacy
  fields are frozen for that publish run.

## 11. Output Shape: `cv_assembly.publish_state`

```text
PublishStateDoc {
  schema_version: "4.3.6.1",
  request_id_namespace,                # sha256(level2_id) — stable per job
  render {
    cv: RenderSurfaceDoc,
    dossier: RenderSurfaceDoc          # nullable when dossier_source=missing
  },
  upload {
    drive {
      cv: DriveUploadDoc,
      dossier: DriveUploadDoc          # nullable when render.dossier=missing
    },
    sheets: SheetsUploadDoc
  },
  summary {
    cv_public_url,                     # best-effort; from Drive webViewLink
    dossier_public_url,
    role_folder_url,                   # Drive folder
    total_duration_ms,
    total_attempts,                    # sum across all surfaces
    total_cost_usd,                    # render+upload only; LLM cost is in synthesis
    publish_started_at,
    publish_completed_at
  }
}

RenderSurfaceDoc {
  status: pending | in_progress | done | degraded | failed,
  source,                              # "synthesis" | "best_effort_fallback" | "evidence_map"
  artifact_local_path,
  artifact_size_bytes,
  artifact_sha256,
  pdf_service_endpoint,                # "/cv-to-pdf" | "/render-pdf"
  pdf_service_request_id,              # X-Request-Id sent
  pdf_service_response_time_ms,
  pdf_service_playwright_ready,        # echoed from response header
  duration_ms,
  attempt_count,
  last_error: ErrorDoc?,
  started_at, completed_at,
  trace_ref,                           # langfuse span id
  degraded_reason?                     # when status=degraded
}

DriveUploadDoc {
  status: pending | in_progress | done | degraded | failed,
  webhook_url,                         # n8n url at request time
  request_id,                          # sha256(idempotency_key)[:32]
  duplicate_of_request_id?,            # set when n8n returned dedup'd response
  file_id,                             # response from n8n
  role_folder,                         # response from n8n (folder id)
  file_web_view_link?,                 # when n8n returns webViewLink
  uploaded_at,
  attempt_count,
  last_error: ErrorDoc?,
  trace_ref,
  degraded_reason?
}

SheetsUploadDoc {
  status: pending | in_progress | done | failed | skipped,
  row_id,
  sheet_id,
  sheet_tab,
  schema_version: "4.3.6.sheets.v1",
  logged_at,
  attempt_count,
  last_error: ErrorDoc?,
  trace_ref,
  skipped_reason?                      # when status=skipped, e.g. "quota_exhausted"
}

ErrorDoc {
  class,                               # exception class name
  message,                             # truncated 240 chars
  http_status?,                        # for HTTP errors
  at,                                  # timestamp
  trace_ref
}
```

**Immutability rules.**

- `request_id` and `request_id_namespace` are write-once.
- `artifact_sha256` is write-once per render; if a render is replayed,
  a new render produces a new sha; the upload task validates that
  the sha it sees matches what it was originally enqueued for or
  re-enqueues itself.
- `published_at`, `delivered_at` are write-once; CAS-protected.

## 12. PDF-Service / Playwright Health-Gate Contract

### 12.1 Authoritative endpoint

`pdf_service:/health` (`pdf_service/app.py` lines 160-190). Returns
HTTP 200 with `{status:"healthy", playwright_ready:true, ...}` when
Playwright validated on startup; returns HTTP 503 with
`{playwright_ready:false, playwright_error:str, ...}` otherwise.

### 12.2 Health prober

A new sidecar `src/cv_assembly/publish_health_prober.py` runs every
`PUBLISH_PDF_HEALTH_PROBE_INTERVAL_SECONDS` (default 30s) and writes
to a Mongo document `pdf_service_health_state` (one doc per
pdf-service URL) with shape:

```text
{
  _id: <pdf_service_url>,
  last_checked_at,
  last_response_at,
  last_status,                   # "healthy" | "unhealthy" | "unreachable"
  last_playwright_ready,         # bool
  last_playwright_error,         # str | null
  consecutive_unhealthy_count,
  consecutive_healthy_count,
  gate_open,                     # bool — true when claims are blocked
  gate_opened_at,
  gate_closed_at,
  gate_history: [{at, transition, reason}, ...]   # capped at 100 entries
}
```

### 12.3 Gate semantics

The gate is **separate per pdf-service URL** (typically one in dev,
one on VPS) but **shared between CV and dossier renders** — both
endpoints depend on the same Playwright instance.

Open (block claims):

- `consecutive_unhealthy_count >= PUBLISH_PDF_HEALTH_OPEN_THRESHOLD`
  (default `3` consecutive unhealthy probes within
  `PUBLISH_PDF_HEALTH_OPEN_WINDOW_SECONDS`, default `300s`).
- "Unhealthy" = HTTP 503, HTTP error class, network unreachable, or
  HTTP 200 with `playwright_ready=false`.

Close (re-allow claims):

- `consecutive_healthy_count >= PUBLISH_PDF_HEALTH_CLOSE_THRESHOLD`
  (default `5` consecutive healthy probes).
- "Healthy" = HTTP 200 with `playwright_ready=true`.

Freshness window:

- A claim attempt rejects when `now() - last_response_at >
  PUBLISH_PDF_HEALTH_FRESHNESS_SECONDS` (default `300s`) regardless
  of `gate_open`. Stale prober ⇒ treat as unhealthy.

Manual override:

- An operator may force-close the gate by setting
  `gate_open=false` and `gate_history.append({reason:"manual_override"})`
  via `scripts/cv_assembly_pdf_health_override.py`. The next probe
  re-evaluates.

### 12.4 Configurable knobs

| Env var | Default | Notes |
|---------|---------|-------|
| `PUBLISH_PDF_SERVICE_URL` | `http://pdf-service:8001` | also used by uploader |
| `PUBLISH_PDF_HEALTH_PROBE_INTERVAL_SECONDS` | `30` | |
| `PUBLISH_PDF_HEALTH_FRESHNESS_SECONDS` | `300` | |
| `PUBLISH_PDF_HEALTH_OPEN_THRESHOLD` | `3` | consecutive unhealthy |
| `PUBLISH_PDF_HEALTH_OPEN_WINDOW_SECONDS` | `300` | window over which to count |
| `PUBLISH_PDF_HEALTH_CLOSE_THRESHOLD` | `5` | consecutive healthy |
| `PUBLISH_PDF_HEALTH_GATE_ENABLED` | `true` | emergency disable |
| `PUBLISH_PLAYWRIGHT_TIMEOUT_SECONDS` | `90` | inside pdf-service container |
| `PUBLISH_PDF_SERVICE_HTTP_TIMEOUT_SECONDS` | `120` | publisher-side timeout |
| `PUBLISH_RENDER_STARVATION_ALERT_SECONDS` | `900` | alert if gate stays open > N |

### 12.5 Render block vs degrade

- **CV render under open gate.** Claim is rejected; work item's
  `available_at` pushed by backoff. After
  `PUBLISH_RENDER_STARVATION_ALERT_SECONDS` of continuous open gate,
  alert fires (`pdf_service_starvation`). After
  `max_attempts` exhausted, deadletter → `cv_assembly.status=failed`.
- **Dossier render under open gate.** Same backoff path; after
  budget exhausted, dossier degrades (`status=degraded`,
  `degraded_reason="pdf_service_unhealthy"`); CV publish still
  proceeds because dossier is degradable.

### 12.6 Local dev vs VPS production

| Env | pdf-service URL | gate enforced |
|-----|-----------------|---------------|
| local dev (`docker-compose.local.yml`) | `http://pdf-service:8001` | yes (same code) |
| VPS production (`docker-compose.ingest.yml`) | `http://pdf-service:8001` | yes |
| local dev without docker | `PUBLISH_PDF_SERVICE_URL` env var must be set; tests in offline mode use fixture transports per §23 | yes (gate state read from a fixture-backed prober) |

Local dev and VPS run the same prober + gate logic; only the URL
and the container restart cadence differ.

### 12.7 Failure artifacts

On render failure, the publisher captures and persists:

- pdf-service response status code and headers
- pdf-service response body (first 4KB) when status >= 400
- last 50 lines of pdf-service container stderr (when accessible —
  on VPS via `docker logs --tail 50 pdf-service`; not blocking on
  local)
- Playwright error from the `/health` body when applicable

These are written to `publish_state.render.<surface>.last_error`
and to `reports/cv-assembly-publish/<job_id>/render_<surface>.log`
per §24.

## 13. Render Pathway Details

### 13.1 `publish.render.cv`

Inputs:

- `final_cv_struct` (TipTap doc).
- `header_blueprint.identity` (for header/footer text), `documentStyles`
  (passthrough; defaults from `pdf_service.app.CVToPDFRequest`).
- `company`, `title` (filename hints).

Pre-render:

- Verify pdf-service `/health` gate is closed for the configured URL
  (§12).
- Compute deterministic local path:
  `applications/<sanitize(company)>/<sanitize(title)>/CV_<sanitize(company)>_<sanitize(title)>.pdf`.

Render call:

- POST `pdf_service:/cv-to-pdf` with body
  `{tiptap_json, documentStyles, header, footer, company, role}`.
- Headers: `X-Job-Id`, `X-Trace-Id`, `X-Request-Id`,
  `X-CV-Assembly-Run-Id`, `X-Synthesis-Hash`, `X-Winner-Draft-Id`.
- Total HTTP timeout: `PUBLISH_PDF_SERVICE_HTTP_TIMEOUT_SECONDS`.

Post-render:

- Compute `artifact_sha256 = sha256(pdf_bytes)`.
- Write file to local path; persist
  `publish_state.render.cv = {status:"done", artifact_local_path,
   artifact_size_bytes, artifact_sha256, ...}`.
- Emit `scout.cv_assembly.publish.render_cv` span event.

Failure semantics:

- HTTP 503 / `playwright_ready=false`: push `available_at` by backoff;
  feed the prober.
- HTTP 5xx persistent past attempt budget: deadletter → fail-closed.
- HTTP 400 (TipTap shape error): deadletter immediately; this is a
  contract violation in upstream synthesis, not a render flake.

Render variants and disclosure modes:

- `ats_safe`
  - required for every job;
  - the renderer must omit any metadata not explicitly permitted for the
    ATS-safe surface;
  - photo is forbidden.
- `recruiter_rich`
  - may include additional header lines and policy-approved metadata, while
    remaining single-column and parser-safe.
- `regional_enriched`
  - only used when `header_surface_policy.default_variant` or explicit
    operator choice selects it;
  - may render region-allowed fields such as nationality, visa status,
    languages, or driving-license data when 4.3.1 permits them.

4.3.6 must not invent or infer disclosure policy. It applies the exact policy
handed in by 4.3.2 and 4.3.1.

### 13.2 `publish.render.dossier`

Inputs:

- `cv_assembly.dossier_state.body_html` (4.3.7-owned). This is the
  authoritative source — there is no fallback inside 4.3.6 to
  `best_effort_dossier`. If `dossier_state.source ==
  "best_effort_fallback"`, the body is already fallback content
  written by 4.3.7; 4.3.6 still renders it normally.

Pre-render:

- Verify gate.
- If `dossier_state.body_html` is absent: skip the work item with
  `status=degraded`, `degraded_reason="dossier_state_missing"`. Do
  not invoke `best_effort_dossier` from inside 4.3.6.

Render call:

- POST `pdf_service:/render-pdf` with `{html: body_html}`.

Post-render:

- Same as CV: sha256, persist, span.

Failure semantics:

- Transient / persistent failures degrade the dossier surface
  (`status=degraded`); the `published` finalizer accepts
  `degraded` for dossier render and dossier upload (§16.1 filter).
- A degraded dossier surfaces in `cv_assembly.status_breakdown`
  per 4.3.7 §8.3.

### 13.3 `publish.upload.drive.cv`

Inputs:

- `publish_state.render.cv.artifact_local_path` (validated to exist
  and to match `artifact_sha256`).
- `company`, `title`, `webhook_jobId` (= `level-2.jobId` cast to
  string, falling back to `level-2._id`).
- `request_id` (= `sha256(idempotency_key)[:32]`).

Upload call:

- POST `n8n_webhook_url` (env `N8N_WEBHOOK_CV_UPLOAD`,
  authoritative path declared in §14.1) with multipart form:
  - `files["data"]` = (`Taimoor Alam Resume.pdf`, pdf_bytes,
    `application/pdf`)
  - `data["company_name"]` = company
  - `data["role_name"]` = role
  - `data["file_name"]` = `Taimoor Alam Resume.pdf`
  - `data["jobId"]` = webhook_jobId
  - `data["request_id"]` = request_id (NEW in 4.3.6)
  - `data["winner_draft_id"]` = winner_draft_id (NEW)
  - `data["synthesis_hash"]` = synthesis_hash (NEW)
  - `data["surface"]` = `"cv"` (NEW)
- Total HTTP timeout: `PUBLISH_N8N_HTTP_TIMEOUT_SECONDS` (default 60s).
- Read response: `{file_id, role_folder, webViewLink?,
  duplicate_of_request_id?}`.

Persist:

- `publish_state.upload.drive.cv` populated per §11.

Failure / idempotency: see §14.

### 13.4 `publish.upload.drive.dossier`

Same shape as 13.3 with:

- `data["surface"]` = `"dossier"`.
- `data["file_name"]` = generated by
  `pdf_helpers.generate_dossier_filename(company, role)`.
- Failure path degrades the surface (does not block `published`).

### 13.5 `publish.upload.sheets`

See §15 for row schema. Append-only via `gspread.append_row()`;
upsert by `request_id` is enforced *publisher-side* (§14.4) — Sheets
itself does not dedup.

## 14. n8n Idempotency Contract

### 14.1 Authoritative workflow file

The authoritative export of the n8n workflow lives at
`n8n/workflows/cv-upload.json`, committed to the repo as part of
this iteration. `runner_service` and `gdrive_upload_service` MAY only
target the production n8n URL declared in `N8N_WEBHOOK_CV_UPLOAD`
env, but the hosted workflow MUST match the committed JSON within
the freshness window enforced by `scripts/verify_n8n_workflow_sync.py`
(part of the §24 VPS validation).

### 14.2 Required `request_id` semantics

The publisher MUST send a stable, deterministic `request_id` in the
multipart form body, derived as:

```python
request_id = sha256(
    f"{task_type}:{level2_id}:{input_snapshot_id}:"
    f"{winner_draft_id}:{synthesis_hash}:{artifact_sha256}"
).hexdigest()[:32]
```

The `request_id` is **stable across attempts of the same upload work
item** (because `idempotency_key` is stable) and **unique across
distinct artifact bytes** (because `artifact_sha256` differs when
the rendered PDF differs).

### 14.3 n8n-side dedup table

The committed workflow includes a "Dedup" node before the Drive
upload step:

- Storage: an n8n static-data store keyed by `request_id` →
  `{file_id, folder_id, web_view_link, drive_uploaded_at}`.
- TTL: `7 days` from first observation (n8n `Code` node sweeps
  expired entries on each invocation; entries older than TTL are
  removed).
- On duplicate `request_id` within TTL: the workflow short-circuits
  the Drive upload and returns the **stored** `{file_id, folder_id,
  web_view_link}` plus `duplicate_of_request_id=request_id` and
  `dedup_hit=true` in the response body.
- On duplicate `request_id` past TTL: treated as fresh; new Drive
  file created. (Acceptable because past 7 days a stale upload is no
  longer actionable; operator concern at that horizon is loss of
  publish state, not duplication.)

### 14.4 Publisher-side short-circuit (defense in depth)

Before calling n8n, the upload work item performs a Mongo CAS:

```python
findOneAndUpdate(
    {
        "_id": object_id,
        "cv_assembly.publish_state.upload.drive.<surface>.request_id": request_id,
        "cv_assembly.publish_state.upload.drive.<surface>.status": "done",
    },
    no-op
)
```

If the record matches (CAS hit), the upload task short-circuits
with `status=done`, no n8n call, and emits
`drive_upload_short_circuited` event.

This guards against the n8n hosted instance being unreachable when
the publisher already knows the prior request succeeded.

### 14.5 Retry / backoff semantics

- HTTP timeouts and 5xx: retry with exponential backoff (500ms,
  1s, 2s, 4s, 8s) up to `max_attempts=5`.
- HTTP 4xx (other than 408 Request Timeout): treat as fail-closed;
  deadletter.
- Mid-flight crash (publisher dies after POST but before reading
  response): on retry, the same `request_id` is sent; n8n returns
  the dedup'd response → publisher records `duplicate_of_request_id`
  and persists state as `done`.

### 14.6 Interaction with stage retries and CAS

- Re-claim of an upload work item after lease expiry: same
  `idempotency_key` → same `request_id` → §14.4 short-circuit if
  already done; else §14.3 dedup.
- Re-render between attempts (rare; happens if `publish.render.cv`
  is replayed with a different `synthesis_hash`): a new
  `artifact_sha256` ⇒ new `request_id` ⇒ a *new* Drive file is
  created. Operator-visible because `publish_state.upload.drive.cv.
  duplicate_of_request_id` is null and `attempt_count` doesn't tell
  the full story; we additionally write a `prior_request_ids[]`
  history field with capped length 5.

### 14.7 Callback / update failures

Scenario: n8n successfully uploads to Drive, returns 200, but the
publisher crashes before persisting `publish_state.upload.drive.<>.
status=done`.

- On retry, the publisher sends the same `request_id`; n8n returns
  the dedup'd response with the original `file_id`; publisher
  persists `status=done` with `duplicate_of_request_id` set.
- No double-upload occurs.
- `attempt_count` reflects two attempts; that is correct telemetry.

## 15. Google Sheets Row Schema

### 15.1 Authoritative schema (12 columns, ordered)

| # | Column | Type | Nullable | Source | New in 4.3.6? |
|---|--------|------|----------|--------|----------------|
| 1 | `timestamp` | str ISO-8601 | no | `datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")` | no |
| 2 | `company` | str | no | `level-2.company` | no |
| 3 | `title` | str | no | `level-2.title` | no |
| 4 | `job_url` | str | yes | `level-2.job_url` | no |
| 5 | `fit_score` | float (0-10) | yes | `winner.grade.composite_score * 10` (1 dp) | no |
| 6 | `fit_rationale` | str | yes | `winner.grade.rationale_summary` (≤ 300 chars) | no |
| 7 | `drive_folder_url` | str | yes | `publish_state.summary.role_folder_url` | no |
| 8 | `status` | str | no | `"ready for applying"` on published | no |
| 9 | `source` | str | yes | `level-2.source` | no |
| 10 | `winner_draft_id` | str | yes | `cv_assembly.winner.draft_id` | **yes** |
| 11 | `synthesis_hash` | str | yes | `cv_assembly.synthesis.synthesis_hash` (first 16 chars) | **yes** |
| 12 | `pattern_label` | str | yes | `cv_assembly.winner.pattern_label` | **yes** |

### 15.2 Permitted `status` values

- `"ready for applying"` — set by 4.3.6 finalizer on `published`.
- Operator may later edit to `"applied"`, `"rejected"`, `"interview"`,
  `"offer"`, `"declined"`, `"withdrawn"` — those are downstream and
  out of 4.3.6 scope.

### 15.3 Append-only with publisher-side upsert key

Sheets is treated as append-only by the API
(`sheet.append_row(row)`). Idempotency is enforced *publisher-side*:

- On `publish.upload.sheets` claim, check
  `publish_state.upload.sheets.row_id`. If non-null and
  `status=done`, short-circuit (no append).
- Otherwise, append. Capture row_id = current row count after
  append. Persist.

### 15.4 Quota handling

- Caller-side rate limiter (token bucket) sized for Google Sheets
  free quota (60 reads + 60 writes per 60s per user).
- On quota error: retry budget of `PUBLISH_SHEETS_QUOTA_RETRY_BUDGET`
  (default 3); after exhausted, set `status=skipped`,
  `skipped_reason="quota_exhausted"`. `published` proceeds without
  Sheets (sidecar).

### 15.5 Schema migration

- v1 (current, pre-4.3.6): 9 columns, 1-9.
- v2 (4.3.6): 12 columns. Existing v1 sheet has 9 columns; v2 rows
  written into the same sheet pad columns 10-12 with empty strings
  for any v1 row read; v2 rows always write all 12.
- Header row in column index 1 must be updated once at cutover via
  `scripts/cv_assembly_sheets_migrate_v2.py`.

## 16. Lifecycle CAS Semantics

### 16.1 `published` finalizer CAS

```python
findOneAndUpdate(
  filter={
    "_id": object_id,
    "lifecycle": "cv_assembled",
    "cv_assembly.published_at": {"$exists": False},
    "cv_assembly.synthesis.validator_report.status": {
      "$in": ["pass", "repair_attempted"]
    },
    "cv_assembly.publish_state.render.cv.status": "done",
    "cv_assembly.publish_state.render.cv.artifact_sha256": {"$exists": True},
    "cv_assembly.publish_state.render.dossier.status": {
      "$in": ["done", "degraded"]
    },
    "cv_assembly.publish_state.upload.drive.cv.status": "done",
    "cv_assembly.publish_state.upload.drive.cv.file_id": {"$exists": True},
    "cv_assembly.publish_state.upload.drive.dossier.status": {
      "$in": ["done", "degraded"]
    },
  },
  update={
    "$set": {
      "lifecycle": "published",
      "cv_assembly.published_at": SERVER_TIMESTAMP,
      "status": "ready for applying",
      ...projection (§10.1, §10.2)
    },
    "$push": { "pipeline_runs": pipeline_run_entry },
  },
  return_document=AFTER,
)
```

Event emission:

- On match (CAS success): `scout.cv_assembly.publish.published`
  with metadata per §22.
- On no-match: `published_finalize_preconditions_unmet` with a
  state snapshot (which sub-status blocked the CAS).
- On replay (`published_at` already set): `published_cas_already_set`.

Retry behavior:

- `publish.finalize` work item retries on no-match up to
  `max_attempts=5` with exponential backoff. Each retry recomputes
  the projection from current `cv_assembly.*`, so a finalize that
  was blocked by a still-in-progress dossier render will land on the
  next attempt once dossier transitions.

Duplicate finalizer behavior:

- Two finalizer claims (e.g., lease lost) both attempt the CAS; only
  one matches. The losing claim emits `published_cas_conflict` and
  marks the work item `done` (no-op success).

### 16.2 `delivered` finalizer CAS

`delivered` is set when both Drive uploads have non-null
`uploaded_at` AND the Sheets row was written (or skipped with
explicit reason). The finalizer re-enters and attempts:

```python
findOneAndUpdate(
  filter={
    "_id": object_id,
    "lifecycle": "published",
    "cv_assembly.delivered_at": {"$exists": False},
    "cv_assembly.publish_state.upload.drive.cv.uploaded_at": {"$exists": True},
    "cv_assembly.publish_state.upload.drive.dossier.status": {
      "$in": ["done", "degraded"]
    },
    "cv_assembly.publish_state.upload.sheets.status": {
      "$in": ["done", "skipped"]
    },
  },
  update={
    "$set": {
      "lifecycle": "delivered",
      "cv_assembly.delivered_at": SERVER_TIMESTAMP,
      "gdrive_uploaded_at": "$cv_assembly.publish_state.upload.drive.cv.uploaded_at",
      "dossier_gdrive_uploaded_at": "$cv_assembly.publish_state.upload.drive.dossier.uploaded_at",
    }
  },
  return_document=AFTER,
)
```

(In practice the legacy `gdrive_uploaded_at` is already populated by
the §10.2 projection at `published` time; re-writing it is harmless
and idempotent.)

Event emission:

- On match: `scout.cv_assembly.publish.delivered`.
- On no-match (e.g., dossier upload still pending): emit
  `delivered_finalize_preconditions_unmet`; retry up to 5 attempts.

Retry behavior:

- The `publish.finalize` work item is **re-enqueued** on
  `published` if `delivered_at` is not yet set, with `available_at`
  pushed by `PUBLISH_DELIVERED_RETRY_INTERVAL_SECONDS` (default 60s).
- After `PUBLISH_DELIVERED_BUDGET_SECONDS` (default 600s) without
  meeting preconditions, the finalizer stops retrying for delivered;
  the lifecycle remains `published`. Operator can re-trigger via
  `scripts/cv_assembly_finalize_delivered.py <level2_id>`.

### 16.3 Partial-success operator status

If `published` succeeded but `delivered` cannot be reached (e.g.,
n8n callback failure, dossier upload degraded indefinitely), the
operator-visible state is:

- `lifecycle = "published"` (green, but not strongest signal).
- `cv_assembly.status_breakdown.publish_dossier_status = "degraded"`
  (4.3.7 ownership).
- `cv_assembly.delivered_at` absent.
- `pipeline_runs` last entry has `status=published` (not
  `delivered`).

The operator UI (4.3.7 §11.1) groups this as "Published" not
"Delivered". An alert fires on `delivered` lag exceeding
`PUBLISH_DELIVERED_LAG_ALERT_SECONDS` (default 1800s).

## 17. Cross-Artifact Invariants

INV1. 4.3.6 may publish only when
  `cv_assembly.synthesis.validator_report.status ∈ {pass,
  repair_attempted}`. A `failed` validator status blocks the entire
  publish lane.
INV2. 4.3.6 never mutates `pre_enrichment.*`.
INV3. 4.3.6 never mutates `cv_assembly.synthesis.*` or
  `cv_assembly.winner.*`.
INV4. 4.3.6 never writes `cv_assembly.dossier_state.body_*`,
  `dossier_state.source`, or `dossier_state.sections[*]`. Those are
  4.3.7 ownership. 4.3.6 writes only `publish_state.render.dossier`
  and `publish_state.upload.drive.dossier`.
INV5. `publish_state.render.cv.artifact_sha256` =
  sha256(rendered PDF bytes); the same sha is recorded in
  `publish_state.upload.drive.cv.request_id` derivation; a
  mismatch is a deadletter condition.
INV6. `publish_state.render.cv` (and dossier) refer to bytes derived
  from a single (`winner_draft_id`, `synthesis_hash`) pair. A
  re-render with a different pair invalidates downstream uploads
  via §14.6.
INV7. `cv_assembly.published_at` is set only via §16.1 CAS.
  `cv_assembly.delivered_at` only via §16.2 CAS.
INV8. `cv_assembly.delivered_at` is null when
  `cv_assembly.published_at` is null. A `delivered` job without
  prior `published` is a corrupted state.
INV9. The compatibility projection write occurs in the same
  `findOneAndUpdate` that sets `published_at`. There is no other
  writer of legacy publisher fields when `cv_assembly_source=True`.
INV10. Legacy readers (frontend, operator UI, batch pipeline) remain
  coherent during rollout: every legacy field has a deterministic
  source per §10.1, populated at `published` time, never null-
  overwritten.
INV11. n8n `request_id` is a deterministic function of
  `(idempotency_key, artifact_sha256)`; identical inputs ⇒ identical
  request_id ⇒ Drive returns the same `file_id`.
INV12. `cv_assembly.publish_state.summary.role_folder_url` ==
  legacy `drive_folder_url` after projection.
INV13. Sheets row order matches §15.1 byte-for-byte; column count
  is exactly 12.
INV14. Every rendered CV has an `ats_safe` variant path available,
  even when richer variants are also rendered.
INV15. No rendered variant may expose metadata fields outside the
  supplied `header_surface_policy`; violation is fail-closed for that
  render surface.
INV16. `regional_enriched` may be emitted only when the candidate
  display policy and the header blueprint both allow it; the
  publisher may not promote itself into that mode.

Failure of any invariant fails the affected work item; INV1, INV5,
INV7, INV8, INV9 are deadletter conditions; the rest are repair-
candidate.

## 18. Downstream Consumer Contracts

### 18.1 4.3.7 (state contract / dossier)

May rely on:

- `cv_assembly.publish_state.render.dossier.artifact_local_path` and
  `artifact_sha256` to produce `dossier_state.metadata` projections.
- `cv_assembly.publish_state.upload.drive.dossier.uploaded_at` and
  `file_id` for projection of `dossier_gdrive_uploaded_at`.
- `cv_assembly.published_at`, `cv_assembly.delivered_at` for
  status_breakdown rollups.

May not rely on:

- The render artifact existing on local disk after
  `published_at + 24h` (publisher cleanup may remove local PDF; the
  Drive copy is canonical).
- `publish_state.upload.drive.dossier.status="done"` for every
  published job — dossier is degradable.

### 18.2 Frontend dashboards / operator UI (4.3.7 §11)

May rely on:

- legacy `drive_folder_url`, `gdrive_uploaded_at`,
  `dossier_gdrive_uploaded_at`, `cv_text`, `cv_path`, `cv_reasoning`,
  `cover_letter`, `fit_score`, `fit_rationale`, `selected_star_ids`,
  `pipeline_runs[]` populated at `published`.
- `cv_assembly.publish_state.*` for granular per-surface badges.
- `cv_assembly.published_at` for green-state badge; presence of
  `delivered_at` for the strongest green.

May not rely on:

- pre-`published` populated values for any 4.3.6-owned legacy field;
  before `published`, those legacy fields hold their pre-cutover
  values (or null on first run).
- `sheet_row_id` non-null on every published job (Sheets is
  degradable).
- `delivered_at` being eventually set; lag may exceed budget without
  manual intervention.

### 18.3 Legacy batch pipeline / runner_service

May rely on:

- `OutputPublisher.publish()` callable signature unchanged when
  `cv_assembly_source=False` (rollback path).
- `gdrive_upload_service.upload_cv_to_gdrive()` and
  `upload_dossier_to_gdrive()` callable signatures unchanged
  (those code paths remain for editor-driven manual uploads outside
  the 4.3 lane).

May not rely on:

- The 4.3 lane writing `gdrive_uploaded_at` *before* `published_at`.
  In 4.3, both fields are written in the same finalizer update.

### 18.4 Interview-prep workflows

May rely on:

- `cv_assembly.winner.draft_id` and `cv_assembly.synthesis.synthesis_hash`
  on any `published` job for downstream interview prep keying.

## 19. Fail-Open / Fail-Closed Matrix

| Condition | Behavior | Lifecycle outcome |
|-----------|----------|-------------------|
| Synthesis validator status = `failed` | Publisher rejects at prereq check | stays `cv_assembled`; alert; deadletter after budget |
| pdf-service unhealthy < starvation timeout | render claims rejected; backoff | stays `cv_assembled`; recovers when gate closes |
| pdf-service unhealthy > starvation timeout (CV) | deadletter render | `cv_assembly.status=failed`; lifecycle stays `cv_assembled` |
| pdf-service unhealthy > starvation timeout (dossier) | dossier surface degraded | publishes via `published` CAS; dossier status=degraded |
| n8n unreachable < retry budget | upload retries with backoff | stays `cv_assembled`; recovers |
| n8n unreachable past retry budget (CV upload) | deadletter | `cv_assembly.status=failed` |
| n8n unreachable past retry budget (dossier upload) | dossier upload degraded | publishes; degraded |
| n8n succeeded but response lost | next retry returns dedup'd response | publishes normally |
| Drive OAuth scopes invalid | publisher refuses; alert | stays `cv_assembled` |
| Sheets API quota exhausted | sheets task skipped after retry budget | publishes; sheets=skipped |
| Sheets transient 5xx within budget | retry | publishes; sheets=done |
| Cover letter absent in synthesis AND winner | proceed; legacy `cover_letter` field unset (null-preserving) | publishes |
| Dossier body missing entirely | dossier render skipped → degraded | publishes; degraded dossier |
| Synthesis present but `synthesis.degraded=true` | publisher proceeds normally | publishes |
| Render artifact sha mismatch at upload time | upload re-enqueued; render re-enqueued via dependency | retries |
| Crash mid-finalize | re-claim runs deterministic CAS again | publishes |
| Replay of finalize on already-published | CAS miss; no-op | unchanged |

Fail-closed (deadletter, lifecycle stays `cv_assembled`):

- INV1, INV5, INV7-INV9 violations.
- HTTP 4xx from pdf-service for CV render (contract violation).
- HTTP 4xx (non-408) from n8n for CV upload (workflow misconfig).
- Drive OAuth invalid.

## 20. Safety / Anti-Hallucination

- Publisher does not generate prose. It renders the validator-clean
  `synthesis.final_cv_struct` and the 4.3.7-validated dossier body.
- Pre-upload, the publisher recomputes sha256 over the bytes it is
  about to send and asserts equality with
  `publish_state.render.<surface>.artifact_sha256`. Mismatch → fail-
  closed.
- Upload payload metadata carries `winner_draft_id` and
  `synthesis_hash` so audits can reconcile any uploaded artifact
  back to its source draft + synthesis.
- `publish.render.dossier` does not invoke `best_effort_dossier`
  from inside 4.3.6. The fallback decision is 4.3.7's; 4.3.6
  consumes whatever dossier_state body 4.3.7 has produced.
- No `stakeholder_surface` content enters publish payloads; the
  publisher does not condition uploads on stakeholder identity.
- No protected-trait inferences anywhere in the publish path.
- Sheets row uses only fields enumerated in §15.1; no free-form
  body content is logged.

## 21. Operational Catalogue

| Item | Value |
|------|-------|
| Stage owner | `src/cv_assembly/stages/publish_*.py`, `src/cv_assembly/sweepers.py` |
| Prerequisite artifacts | `cv_assembly.synthesis`, `cv_assembly.winner`, `cv_assembly.dossier_state`, `cv_assembly.header_blueprint`, `pre_enrichment.outputs.*` (passthrough sources) |
| Persisted Mongo locations | `level-2.cv_assembly.publish_state.*`, `level-2.cv_assembly.published_at`, `level-2.cv_assembly.delivered_at`, `level-2` root (legacy projection), `pdf_service_health_state` |
| Stage-run records | `cv_assembly_stage_runs` rows for each task type with `trace_id`, `trace_url`, `model_used=null` (no LLM), `tokens_input=0`, `tokens_output=0`, `cost_usd` (HTTP-call latency cost only) |
| Work-item lane | `publish` |
| Task types | `publish.render.cv`, `publish.render.dossier`, `publish.upload.drive.cv`, `publish.upload.drive.dossier`, `publish.upload.sheets`, `publish.finalize` |
| Retry / repair | per §7.4 max_attempts; backoff per iteration-4 pattern; deterministic re-claim on lease expiry |
| Deadletter | render attempt budget exhausted → `cv_assembly.status=failed`; CV upload past budget → same; dossier degradable surfaces never deadletter, they degrade |
| Cache semantics | none; renders are recomputed on retry, but `request_id` keeps n8n idempotent |
| Heartbeat | 30s for renders, 15s for uploads, 10s for finalize; lease heartbeat 60s |
| Feature flags (cutover) | `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED`, `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED`, `PUBLISH_PDF_HEALTH_GATE_ENABLED`, `PUBLISH_N8N_REQUEST_ID_ENABLED`, `PUBLISH_SHEETS_V2_SCHEMA_ENABLED`, `LANGFUSE_PUBLISH_TRACING_ENABLED`, `PUBLISH_REQUIRE_N8N_ACK_FOR_DELIVERED` |
| Operator success signals | lifecycle = `published` then `delivered`, status_breakdown rollup green, Langfuse trace contains `published` event, Drive folder URL renders, Sheets row visible |
| Operator failure signals | `cv_assembly.status=failed`, Langfuse `*_unmet` events, `pdf_service_starvation` alert, `delivered_lag` alert |
| Downstream consumers | 4.3.7 status_breakdown, frontend dashboards, batch pipeline `pipeline_runs[]` |
| Rollback strategy | flip `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=false`; legacy single-pass `publish()` resumes; `cv_assembly.publish_state` retained for audit |

## 22. Langfuse Tracing Contract

### 22.1 Canonical span taxonomy

```
scout.cv_assembly.publish                    # parent stage span (per work item batch)
scout.cv_assembly.publish.finalizer
scout.cv_assembly.publish.render_cv
scout.cv_assembly.publish.render_dossier
scout.cv_assembly.publish.pdf_health
scout.cv_assembly.publish.upload_drive_cv
scout.cv_assembly.publish.upload_drive_dossier
scout.cv_assembly.publish.upload_sheets
scout.cv_assembly.publish.n8n_webhook        # transport span (child of upload_drive_*)
scout.cv_assembly.publish.projection_write
scout.cv_assembly.publish.published_cas
scout.cv_assembly.publish.delivered_cas
```

Session pinning: `langfuse_session_id = job:<level2_id>`.

### 22.2 Required metadata per span

Every span carries:

- `level2_id`, `job_id`, `work_item_id`, `attempt_count`,
  `attempt_token`, `idempotency_key`, `lane="publish"`, `task_type`,
  `input_snapshot_id`.

Stage-specific metadata:

| Span | Additional metadata |
|------|---------------------|
| `publish` | `winner_draft_id`, `winner_pattern_label`, `synthesis_hash`, `publish_mode` (`winner` \| `legacy_fallback`) |
| `publish.render_cv` | `pdf_service_endpoint="/cv-to-pdf"`, `pdf_service_request_id`, `cv_render_status`, `artifact_sha256`, `artifact_size_bytes`, `duration_ms`, `pdf_service_playwright_ready` |
| `publish.render_dossier` | same shape; `dossier_render_status`, `dossier_source` |
| `publish.pdf_health` | `gate_open`, `consecutive_unhealthy_count`, `consecutive_healthy_count`, `last_response_at`, `pdf_service_health` |
| `publish.upload_drive_cv` | `n8n_request_id`, `drive_folder_id`, `drive_file_id`, `duplicate_of_request_id`, `dedup_hit`, `attempt_count`, `http_status`, `duration_ms` |
| `publish.upload_drive_dossier` | same |
| `publish.upload_sheets` | `sheet_id`, `row_id`, `sheets_write_status`, `schema_version` |
| `publish.n8n_webhook` | transport-level: `provider="n8n"`, `transport="http"`, `endpoint`, `duration_ms`, `http_status`, `request_id`, `dedup_hit` |
| `publish.projection_write` | `fields_written_count`, `legacy_fields_touched_count` |
| `publish.published_cas` | `cas_outcome` (`match` \| `miss` \| `already_set`), `published_at`, `status` |
| `publish.delivered_cas` | `cas_outcome`, `delivered_at`, `delivered_lag_seconds` |

### 22.3 Required events

- `scout.cv_assembly.publish.pdf_service_unhealthy` — gate opened or
  probe failed; metadata `{playwright_ready, playwright_error,
  consecutive_unhealthy_count}`.
- `scout.cv_assembly.publish.render_degraded` — surface=`dossier`,
  reason.
- `scout.cv_assembly.publish.drive_upload_started` — surface,
  request_id.
- `scout.cv_assembly.publish.drive_upload_duplicate_request` —
  request_id, `duplicate_of_request_id`, `dedup_hit=true`,
  `original_file_id`.
- `scout.cv_assembly.publish.sheets_row_written` — row_id, schema_version.
- `scout.cv_assembly.publish.sheets_row_skipped` — reason.
- `scout.cv_assembly.publish.n8n_retry` — attempt_count, last_error.
- `scout.cv_assembly.publish.projection_atomic_write` —
  fields_written_count, lifecycle_transition.
- `scout.cv_assembly.publish.published_cas_conflict` — losing_actor.
- `scout.cv_assembly.publish.delivered_cas_conflict` — losing_actor.
- `scout.cv_assembly.publish.published` — finalizer success.
- `scout.cv_assembly.publish.delivered` — delivered finalizer success.
- `scout.cv_assembly.publish.pdf_service_starvation` — gate open >
  starvation timeout.
- `scout.cv_assembly.publish.delivered_lag` — published-at to
  now > lag alert threshold.

### 22.4 Forbidden payload content

- PDF bytes, render artifact full content, `tiptap_json` full body.
- Full webhook multipart request body (just metadata + sizes).
- Full Sheets row body (publish only the schema_version + row_id).
- Full dossier HTML body (just `dossier_body_sha256` + `body_size_bytes`).
- Full debug JSON. Debug body stays in Mongo
  (`cv_assembly.publish_state.<>.debug_context`) and is never mirrored.

### 22.5 Mongo trace refs

- `cv_assembly.publish_state.render.cv.trace_ref`
- `cv_assembly.publish_state.render.dossier.trace_ref`
- `cv_assembly.publish_state.upload.drive.cv.trace_ref`
- `cv_assembly.publish_state.upload.drive.dossier.trace_ref`
- `cv_assembly.publish_state.upload.sheets.trace_ref`
- `cv_assembly.stage_runs.publish.<task_type>.trace_id` /
  `trace_url` per stage-run record
- `cv_assembly_stage_runs` rows: `trace_id`, `trace_url`

Operators jump from Mongo UI → Langfuse with one click.

### 22.6 Cardinality / naming safety

- Span names are static strings (no per-job interpolation).
- Metadata values are never raw bytes.
- `request_id`, `file_id`, `synthesis_hash` are bounded to ≤ 64
  chars before recording; longer values are truncated and a
  `*_truncated=true` flag is set.

## 23. Tests and Evals

### 23.1 Unit tests

- `tests/unit/cv_assembly/publish/test_publish_state_schema.py` —
  TypedDict validation, immutability rules.
- `tests/unit/cv_assembly/publish/test_request_id_derivation.py` —
  byte-deterministic `request_id` for fixed inputs.
- `tests/unit/cv_assembly/publish/test_projection_module.py` —
  field-by-field projection per §10.1; null-preserving rule.
- `tests/unit/cv_assembly/publish/test_pdf_health_gate.py` —
  open/close threshold transitions; freshness window; manual override.
- `tests/unit/cv_assembly/publish/test_published_cas.py` — CAS
  match / miss / already_set branches; partial-write window asserted
  zero via fault injection (kill mid-update simulator).
- `tests/unit/cv_assembly/publish/test_delivered_cas.py` — same.
- `tests/unit/cv_assembly/publish/test_sheets_row_schema.py` —
  exact 12-column ordering, types, nullability, schema migration.
- `tests/unit/cv_assembly/publish/test_n8n_idempotency.py` —
  duplicate request_id within TTL → dedup'd response;
  publisher-side short-circuit.
- `tests/unit/cv_assembly/publish/test_synthesis_hash_assertion.py` —
  pre-upload sha mismatch → fail-closed.
- `tests/unit/cv_assembly/publish/test_trace_emission.py` — every
  span / event listed in §22 emitted.

### 23.2 Integration tests (with fixture transports)

- `tests/integration/cv_assembly/publish/test_full_lane.py` — golden
  path: `cv_assembled` → all five publish tasks → `publish.finalize`
  → `published` → `delivered`.
- `tests/integration/cv_assembly/publish/test_replay_idempotent.py` —
  re-run all publish tasks on a `published` job; no duplicate Drive
  files; no duplicate Sheets rows; `published_at` unchanged.

### 23.3 Fault-injection cases (under
`data/eval/validation/cv_assembly_4_3_6_publish/fault_cases/`)

- pdf-service 503 for 4 consecutive probes → gate opens; render
  blocks; alert after starvation timeout; gate closes after 5
  healthy probes.
- pdf-service `playwright_ready=false` (HTTP 200) → treated as
  unhealthy.
- n8n timeout on first attempt, success on retry with same
  request_id → dedup response with original `file_id`.
- n8n returns dedup response on first attempt (because a prior
  zombie attempt populated dedup) → publisher records
  `duplicate_of_request_id`.
- Sheets 429 quota → 3 retries → status=skipped; `published`
  proceeds.
- Crash mid-finalize before update commits → on retry, deterministic
  CAS lands; legacy fields populated; `published_at` set.
- Crash mid-finalize after update commits but before stage-run
  record → on retry, CAS already-set; work item completes no-op.
- Synthesis validator status=`failed` → prereq blocks lane;
  deadletter after budget.
- Dossier body absent → dossier surface degraded; CV publishes.
- Re-render with new `synthesis_hash` → new `request_id` → new
  Drive file; `prior_request_ids[]` records.

### 23.4 Eval corpus structure

```
data/eval/validation/cv_assembly_4_3_6_publish/
├── cases/<job_id>/
│   ├── input/
│   │   ├── level2.json                  # frozen at cv_assembled
│   │   ├── synthesis.json               # cv_assembly.synthesis fixture
│   │   ├── winner.json                  # cv_assembly.winner fixture
│   │   ├── dossier_state.json           # 4.3.7 fixture
│   │   └── header_blueprint.json
│   ├── expected/
│   │   ├── publish_state.json           # exact target state at published
│   │   ├── level2_projection.json       # legacy fields after projection
│   │   ├── sheets_row.json              # 12-tuple
│   │   └── trace_envelope.json          # spans + events expected
│   └── ground_truth.md
├── fixtures/
│   ├── pdf_service_responses/
│   ├── n8n_responses/
│   └── sheets_responses/
└── fault_cases/
```

Target: minimum 15 cases spanning role families; minimum 10 fault
cases.

### 23.5 Harness

`scripts/benchmark_publish_4_3_6.py`:

- Runs publish tasks against fixtures.
- Asserts byte-level publish_state, byte-level legacy projection,
  byte-level Sheets row, structural trace envelope.
- Asserts retry / deadletter behavior on fault cases.

### 23.6 Regression metrics

- Publish-state shape compliance — target 1.00.
- Projection byte-equality — target 1.00.
- Sheets row byte-equality — target 1.00.
- Fault-case outcome compliance — target 1.00.
- pdf-service health-gate determinism — target 1.00.
- n8n idempotency under 3× concurrent retry storm — duplicate Drive
  file rate target 0.
- p95 publish latency per role family — report only.
- `delivered` rate (within 10 minutes of `published_at`) — report
  only; alert in 4.3.8.

### 23.7 Regression gates (block rollout)

- publish_state shape regresses,
- projection loses any legacy field,
- Sheets row loses any column or schema version drifts,
- fault_case outcomes regress,
- pdf-service health gate is bypassed by any branch,
- compatibility-projection atomicity test detects any partial-write.

## 24. VPS End-to-End Validation Plan

Full discipline from `docs/current/operational-development-manual.md`
applies. This is the live-run chain.

### 24.1 Local prerequisite tests before touching VPS

- `pytest -k "cv_assembly and publish"` clean.
- `python -m scripts.cv_assembly_publish_dry_run --job <level2_id>
  --mock-transports` clean.
- Projection byte-equality test green.
- Langfuse sanitizer test green.
- Health-gate threshold transition test green.

### 24.2 Verify VPS repo shape and live code path

On the VPS:

- confirm `/root/scout-cron` is the deployed path (file-synced, not
  git-pulled).
- verify `src/cv_assembly/stages/publish_*.py` exist and contain the
  five new task types.
- verify `src/cv_assembly/sweepers.py` contains
  `published_finalizer_cas` and `delivered_finalizer_cas`.
- verify `src/cv_assembly/compat/projection.py` matches the local
  build (sha equality).
- verify `pdf_service/app.py` `/health` endpoint reachable from
  publisher container:
  `docker exec scout-cv-publish-worker curl -fsS
   http://pdf-service:8001/health`.
- verify `N8N_WEBHOOK_CV_UPLOAD` env present and equals committed
  expected URL.
- verify `n8n/workflows/cv-upload.json` matches the live n8n
  workflow via `scripts/verify_n8n_workflow_sync.py`.
- verify Google Drive service-account credentials load with
  `drive` + `spreadsheets` scopes.
- verify `.venv` resolves the repo Python:
  `/root/scout-cron/.venv/bin/python -u -c "import sys; print(sys.executable)"`.

### 24.3 Target job selection

- pick a real `level-2` job with:
  - `lifecycle == "cv_assembled"`,
  - `cv_assembly.synthesis.validator_report.status ∈
    {pass, repair_attempted}`,
  - `cv_assembly.winner.draft_id` present,
  - `cv_assembly.dossier_state.body_html` populated,
  - `cv_assembly.header_blueprint.identity.chosen_title` present.
- record `_id`, `synthesis_hash`, `winner_draft_id`,
  `input_snapshot_id`.
- prefer an IC role family for first run (less complex pattern); a
  second run on a leadership role exercises long-bullet edge cases.

### 24.4 Upstream artifact recovery

If `cv_assembly.publish_state` already has a partial state from a
prior aborted run:

- Inspect: `level2.cv_assembly.publish_state.{render,upload}` — what
  is `done` vs `pending`?
- Verify render artifact files exist on disk; if absent and status
  is `done`, that's a stale state — delete the surface state field
  and re-enqueue.
- Re-enqueue only the missing publish work items via
  `scripts/cv_assembly_enqueue_publish.py --job <_id> --tasks
  render.cv,render.dossier,upload.drive.cv,...` rather than touching
  `work_items` directly.

### 24.5 Single-stage run path (fast path)

Preferred when only 4.3.6 needs validation. A wrapper script in
`/tmp/run_cv_publish_<job>.py`:

- loads `.env` in Python with explicit path:
  `from dotenv import load_dotenv; load_dotenv("/root/scout-cron/.env")`.
- reads `MONGODB_URI`, `PUBLISH_PDF_SERVICE_URL`,
  `N8N_WEBHOOK_CV_UPLOAD`, `GOOGLE_CREDENTIALS_PATH`,
  `GOOGLE_SHEET_ID`, `GOOGLE_DRIVE_FOLDER_ID`.
- builds `StageContext` via `build_stage_context_for_job`.
- runs the publish lane work items in dependency order:
  1. `PublishHealthProbeStage` — populate gate state.
  2. `PublishRenderCVStage().run(ctx)`.
  3. `PublishRenderDossierStage().run(ctx)`.
  4. `PublishUploadDriveCVStage().run(ctx)`.
  5. `PublishUploadDriveDossierStage().run(ctx)`.
  6. `PublishUploadSheetsStage().run(ctx)`.
  7. `PublishFinalizerStage().run(ctx)` — runs `published` CAS +
     projection.
  8. After 60s, re-run `PublishFinalizerStage().run(ctx)` for
     `delivered` CAS.
- prints heartbeat every 15 s with: wall clock, elapsed, last
  substep, last HTTP status, current pdf-service health.

Launch:

```
nohup /root/scout-cron/.venv/bin/python -u /tmp/run_cv_publish_<job>.py \
  > /tmp/cv_publish_<job>.log 2>&1 &
```

### 24.6 Full-chain path (fallback)

If 4.3.5 has not yet produced synthesis, run 4.3.5 + 4.3.6 together:

- enqueue `cv.grade_select_synthesize` first.
- after barrier completes (`lifecycle=cv_assembled`), enqueue all
  five `publish.*` work items + `publish.finalize`.
- start `cv_assembly_worker_runner.py` with
  `CV_ASSEMBLY_LANE_ALLOWLIST="cv_assembly,publish"`.
- same `.venv`, `python -u`, Python-side `.env`,
  `MONGODB_URI`, heartbeat discipline.

### 24.7 Required launcher behavior

- `.venv` resolved (absolute path to `.venv/bin/python`).
- `python -u` unbuffered.
- `.env` loaded from Python.
- `MONGODB_URI`, `PUBLISH_PDF_SERVICE_URL`, `N8N_WEBHOOK_CV_UPLOAD`,
  `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_SHEET_ID`,
  `GOOGLE_DRIVE_FOLDER_ID` present.
- subprocess cwd defaults to `/tmp/cv-publish-work-<job>/` unless
  repo context is required (set via
  `PUBLISH_WORK_DIR` — only for debugging).
- inner subprocess PIDs (e.g., httpx/asyncio worker) and last 128
  chars of stdout / stderr logged on each heartbeat.

### 24.8 Heartbeat requirements

- stage-level heartbeat every 15 s from the wrapper.
- lease heartbeat every 60 s by the worker.
- pdf-service prober writes `pdf_service_health_state.last_checked_at`
  every 30 s; absence > 90 s is a stuck-prober flag.
- Silence > 90 s between heartbeats is a stuck-run flag.

### 24.9 Expected Mongo writes

On success per task:

- `publish.render.cv` →
  `level-2.cv_assembly.publish_state.render.cv.{status,
   artifact_local_path, artifact_size_bytes, artifact_sha256,
   pdf_service_endpoint, duration_ms, attempt_count, started_at,
   completed_at, trace_ref}`.
- `publish.render.dossier` → analogous.
- `publish.upload.drive.cv` →
  `level-2.cv_assembly.publish_state.upload.drive.cv.{status,
   request_id, file_id, role_folder, uploaded_at, attempt_count,
   trace_ref, duplicate_of_request_id?}`.
- `publish.upload.drive.dossier` → analogous.
- `publish.upload.sheets` →
  `level-2.cv_assembly.publish_state.upload.sheets.{status, row_id,
   sheet_id, schema_version, logged_at, trace_ref}`.
- `publish.finalize` (published CAS) →
  `level-2.{lifecycle="published", cv_assembly.published_at, status,
   cv_text, cv_path, cv_reasoning, cover_letter, fit_score,
   fit_rationale, selected_star_ids, primary_contacts,
   secondary_contacts, pain_points, strategic_needs, risks_if_unfilled,
   success_metrics, company_summary, extracted_jd, drive_folder_url,
   sheet_row_id, gdrive_uploaded_at, dossier_gdrive_uploaded_at,
   total_cost_usd, token_usage, generated_dossier, pipeline_run_at}`,
  plus `$push: pipeline_runs`.
- `publish.finalize` (delivered CAS, re-entry) →
  `level-2.{lifecycle="delivered", cv_assembly.delivered_at}`.
- `cv_assembly_stage_runs`: one row per task with `status=completed`,
  `trace_id`, `trace_url`, `cost_usd`.
- `pdf_service_health_state`: continuous probe writes.

### 24.10 Expected Langfuse traces

In session `job:<level2_id>`:

- `scout.cv_assembly.publish` parent span.
- `.render_cv`, `.render_dossier`, `.pdf_health` spans.
- `.upload_drive_cv`, `.upload_drive_dossier`, `.upload_sheets`
  spans, each with a child `.n8n_webhook` transport span where
  applicable.
- `.projection_write` and `.published_cas` events on finalize.
- `.delivered_cas` on re-entry.
- `published`, `delivered` events.
- canonical lifecycle events from iteration-4 (`claim`,
  `enqueue_next`, `lease_heartbeat`).

### 24.11 Expected stage-run / job-run records

- one `cv_assembly_stage_runs` row per task with `trace_id`,
  `trace_url`, `provider_used="pdf_service"|"n8n"|"google_sheets"`,
  `model_used=null`.
- `cv_assembly_job_runs` aggregate updated with
  `lane_status_map.publish.*`.

### 24.12 Stuck-run operator checks

If no heartbeat for > 90 s:

- tail `/tmp/cv_publish_<job>.log`.
- inspect pdf-service container:
  `docker logs --tail 200 pdf-service`.
- inspect health gate:
  `mongosh ... --eval 'db.pdf_service_health_state.find().pretty()'`.
- inspect publish_state subtree:
  `mongosh ... --eval 'db.["level-2"].findOne({_id: ObjectId("...")},
   {cv_assembly: 1})'`.
- inspect lease:
  `level-2.cv_assembly.publish_state.<surface>.lease_expires_at`.
- if lease is expiring with no progress, kill launcher; do not
  restart until prior PID is gone.

Silence is not progress.

### 24.13 Acceptance criteria

- log ends with `CV_ASSEMBLY_PUBLISH_RUN_OK job=<id> status=published
  delivered=<bool> trace=<url>`.
- Mongo writes match §24.9.
- Langfuse trace matches §24.10.
- Drive folder visible at `publish_state.summary.role_folder_url`,
  contains both PDFs.
- Sheets row at `publish_state.upload.sheets.row_id` matches §15.1
  schema.
- Re-running the launcher on the same `_id` is a remote-side no-op:
  no duplicate Drive file, no duplicate Sheets row, no
  `published_at` change.
- Synthesis-degraded run still publishes; render-degraded dossier
  still publishes with degraded badge; sheets-skipped run still
  publishes.

### 24.14 Artifact / log / report capture

Create `reports/cv-assembly-publish/<job_id>/`:

- `run.log` — full stdout/stderr.
- `publish_state.json` — final `cv_assembly.publish_state` dump.
- `level2_projection.json` — diff of root-level legacy fields
  before/after.
- `sheets_row.json` — the 12-tuple actually appended.
- `trace_url.txt` — Langfuse parent URL.
- `pdf_service_health_history.json` — last 100 entries from
  `pdf_service_health_state.gate_history`.
- `n8n_responses.jsonl` — captured webhook responses.
- `mongo_writes.md` — human summary of §24.9.
- `acceptance.md` — §24.13 pass/fail.

## 25. Rollout / Migration / Compatibility

### 25.1 Rollout order

1. Ship `PublishStateDoc` + projection module + sweeper code +
   prober + tests; behind flags. No prod writes.
2. Bench on §23 corpus until all gates green.
3. Ship n8n workflow JSON to `n8n/workflows/cv-upload.json`; sync to
   hosted n8n; verify with `verify_n8n_workflow_sync.py`.
4. Migrate Sheets header row to v2 (12 columns) via
   `scripts/cv_assembly_sheets_migrate_v2.py` (one-time).
5. Enable `PUBLISH_PDF_HEALTH_GATE_ENABLED=true` (no-op on existing
   path; only the prober runs).
6. Shadow mode: `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=false`,
   `PUBLISH_SHADOW_MODE=true`. Publish work items run, render
   artifacts on disk, persist `publish_state`, but skip n8n + Sheets
   writes.
7. Canary 1 job, 5 jobs, 25 jobs, 100% with 72h soak between steps.
8. After 100% soak with zero compatibility regressions, flip
   `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=true` for every new
   `cv_assembled` job.
9. Monitor `delivered` rate; tune
   `PUBLISH_DELIVERED_LAG_ALERT_SECONDS`.
10. Deprecate the `cv_assembly_source=False` branch in a follow-up
    release once no callers remain.

### 25.2 Required flags (full table)

| Flag | Default | Post-cutover | Notes |
|------|---------|--------------|-------|
| `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED` | false | true | Use winner from `cv_assembly.*` |
| `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED` | true | true | Atomic projection in finalize |
| `PUBLISH_SHADOW_MODE` | true | false | Render but do not upload |
| `PUBLISH_PDF_HEALTH_GATE_ENABLED` | true | true | |
| `PUBLISH_PDF_HEALTH_PROBE_INTERVAL_SECONDS` | 30 | 30 | |
| `PUBLISH_PDF_HEALTH_FRESHNESS_SECONDS` | 300 | 300 | |
| `PUBLISH_PDF_HEALTH_OPEN_THRESHOLD` | 3 | 3 | |
| `PUBLISH_PDF_HEALTH_OPEN_WINDOW_SECONDS` | 300 | 300 | |
| `PUBLISH_PDF_HEALTH_CLOSE_THRESHOLD` | 5 | 5 | |
| `PUBLISH_PLAYWRIGHT_TIMEOUT_SECONDS` | 90 | 90 | |
| `PUBLISH_PDF_SERVICE_HTTP_TIMEOUT_SECONDS` | 120 | 120 | |
| `PUBLISH_N8N_REQUEST_ID_ENABLED` | false | true | Send stable `request_id` |
| `PUBLISH_N8N_HTTP_TIMEOUT_SECONDS` | 60 | 60 | |
| `PUBLISH_N8N_REACHABILITY_TIMEOUT_SECONDS` | 10 | 10 | |
| `PUBLISH_N8N_UPLOAD_MAX_ATTEMPTS` | 5 | 5 | |
| `PUBLISH_SHEETS_V2_SCHEMA_ENABLED` | false | true | 12-column row |
| `PUBLISH_SHEETS_QUOTA_RETRY_BUDGET` | 3 | 3 | |
| `PUBLISH_SHEETS_REQUIRED_FOR_PUBLISHED` | false | false | Sidecar |
| `PUBLISH_REQUIRE_N8N_ACK_FOR_DELIVERED` | true | true | Gates `delivered` |
| `PUBLISH_DELIVERED_RETRY_INTERVAL_SECONDS` | 60 | 60 | |
| `PUBLISH_DELIVERED_BUDGET_SECONDS` | 600 | 600 | |
| `PUBLISH_DELIVERED_LAG_ALERT_SECONDS` | 1800 | 1800 | |
| `PUBLISH_RENDER_STARVATION_ALERT_SECONDS` | 900 | 900 | |
| `LANGFUSE_PUBLISH_TRACING_ENABLED` | false | true | |

### 25.3 Compatibility

- Legacy `OutputPublisher.publish()` callers (without
  `cv_assembly_source`) continue to work.
- `gdrive_upload_service.upload_cv_to_gdrive` / `_dossier_to_gdrive`
  continue to work for editor-driven uploads outside the lane
  (those are out of 4.3.6 scope).
- Mongo readers of `level-2` see the same legacy fields populated
  with values projected from `cv_assembly.*`.
- `pre_enrichment.*` is untouched.
- Sheets v1 rows (9 columns) remain valid; v2 rows write 12 columns
  to the same sheet.

### 25.4 Rollback

- `CV_ASSEMBLY_PUBLISH_WINNER_ENABLED=false` routes back to legacy
  single-pass publisher.
- `cv_assembly.publish_state` retained on rollback (audit).
- pdf-service config and n8n workflow remain in place; no rollback
  needed there.
- Sheets v2 rows can coexist with v1 rows indefinitely.
- `CV_ASSEMBLY_PROJECTION_WRITE_ENABLED=false` is the emergency
  switch if projection itself misfires; finalize still completes
  the `published` CAS but writes no legacy fields. An alert fires.

## 26. Open-Questions Triage

| Question | Triage | Resolution / recommendation |
|----------|--------|-----------------------------|
| Should we phase out the n8n webhook in favor of direct Drive API? | safe-to-defer | Keep n8n in 4.3.6. Direct Drive API would require re-implementing the dedup table, folder hierarchy, and OAuth refresh in publisher code, doubling the surface area without a measured reliability win. Revisit only if 4.3.8 telemetry (`drive_upload_started` → `done` lag p95 or `n8n_unreachable` rate) crosses thresholds. |
| Should render jobs be assignable to dedicated higher-memory VPS workers? | safe-to-defer | v1 uses the default worker pool. The pdf-service container is the actual memory hot spot, not the publish worker. Scale horizontally via `MAX_CONCURRENT_PDFS` + multiple pdf-service replicas before introducing a worker class. Revisit if `publish.render.*` p95 latency exceeds 60s on the default pool. |
| Should Sheets row be required for `published`? | resolved (must-resolve) | No. Sheets is sidecar by design (§7.4 `required_for_published=false`, §15.4 quota path). A Sheets failure does not block Drive delivery; the Sheets row is best-effort logging. Operator UI surfaces `sheets=skipped` when this happens. |
| Should the pdf-service emit `cv_rendered` events directly to Langfuse? | resolved (safe-to-defer) | No. The publisher wraps each render in a transport span; the pdf-service stays a simple HTTP service with no Langfuse SDK. Revisit only if cross-correlation between publisher and pdf-service traces becomes load-bearing for debugging. |
| Should dossier render depend on CV render completing first? | resolved (must-resolve) | No. They run in parallel; the `published` finalizer waits on both. Sequential ordering would double publish latency for no truth-correctness gain. The `(winner_draft_id, synthesis_hash)` pair is identical for both renders, so race conditions cannot create cross-contamination. |
| Where is the n8n workflow source-of-truth? | resolved (must-resolve) | `n8n/workflows/cv-upload.json` in this repo (§14.1). The hosted n8n instance MUST match the committed JSON; `scripts/verify_n8n_workflow_sync.py` validates the live workflow against the committed bytes during the §24 VPS chain. |
| What happens when n8n succeeds but the response is lost mid-flight? | resolved (must-resolve) | §14.7 — same `request_id` on retry; n8n returns dedup'd response with original `file_id`; publisher records `duplicate_of_request_id` and persists `status=done`. |
| What is the partial-write window between projection and CAS? | resolved (must-resolve) | Zero (§10.2). Projection and `published_at` land in the same `findOneAndUpdate`. Mongo guarantees single-document atomicity. |
| What if `delivered` callback updates fail after `published` succeeded? | resolved (must-resolve) | §16.3 — lifecycle stays `published`; `delivered_finalize_preconditions_unmet` event; budget retries; alert on lag; operator can manually trigger `delivered` re-entry. Operator-visible state remains green-but-not-strongest. |
| Should we backfill `synthesis_hash` and `pattern_label` columns on historical Sheets rows? | safe-to-defer | No. v1 rows pre-date `cv_assembly`; backfill would require speculative reconstruction. Forward-looking only. |

## 27. Primary Source Surfaces

- `src/layer7/output_publisher.py`
- `src/layer7/dossier_generator.py`
- `runner_service/utils/best_effort_dossier.py`
- `src/services/gdrive_upload_service.py`
- `src/services/batch_pipeline_service.py`
- `pdf_service/app.py`, `pdf_service/pdf_helpers.py`
- `Dockerfile.pdf-service`, `docker-compose.local.yml`,
  `docker-compose.ingest.yml`
- `n8n/workflows/cv-upload.json` (new in 4.3.6)
- `n8n/cron/`, hosted n8n at `n8n.srv1112039.hstgr.cloud`
- `runner_service/routes/operations.py`
- `src/common/repositories/atlas_repository.py`
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.3.7-dossier-and-mongodb-state-contract.md`
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md`
- `docs/current/architecture.md`
- `docs/current/operational-development-manual.md`
- `docs/current/cv-generation-guide.md`
- `docs/current/missing.md`

## 28. Implementation Targets

- `src/cv_assembly/stages/publish_render_cv.py` (new) — render CV via
  `pdf_service:/cv-to-pdf`; persist `publish_state.render.cv`.
- `src/cv_assembly/stages/publish_render_dossier.py` (new) — render
  dossier via `pdf_service:/render-pdf`.
- `src/cv_assembly/stages/publish_upload_drive_cv.py` (new) —
  request_id derivation; n8n call; dedup short-circuit;
  publish_state.upload.drive.cv.
- `src/cv_assembly/stages/publish_upload_drive_dossier.py` (new) —
  analogous; degradable.
- `src/cv_assembly/stages/publish_upload_sheets.py` (new) — 12-column
  schema; quota handling; publisher-side upsert via `row_id` short-
  circuit.
- `src/cv_assembly/sweepers.py` (new) — `published_finalizer_cas`,
  `delivered_finalizer_cas`, projection writer.
- `src/cv_assembly/compat/projection.py` (extends 4.3.7 module) —
  `project_cv_assembly_to_level2` per §10.1; idempotent; pure.
- `src/cv_assembly/publish_health_prober.py` (new) — health gate
  prober writing `pdf_service_health_state`.
- `src/cv_assembly/publish_health_gate.py` (new) — gate read API
  consumed by publish work-item claim.
- `src/cv_assembly/models.py` — add `PublishStateDoc`,
  `RenderSurfaceDoc`, `DriveUploadDoc`, `SheetsUploadDoc`,
  `PdfServiceHealthStateDoc`, `PublishInput`, `GradeProjection`.
- `src/cv_assembly/stage_registry.py` — register six new task types
  with prerequisites, lease, retry config.
- `src/cv_assembly/dag.py` — DAG edges from `cv_assembled` through
  five publish tasks plus finalize → `published` → `delivered`.
- `src/cv_assembly/types.py` — `PublishLifecycleState`,
  `PublishSurfaceStatus` enums.
- `src/layer7/output_publisher.py` — accept `cv_assembly_source`
  flag and `PublishInput`; route to legacy when False; refuse to
  generate prose.
- `src/services/gdrive_upload_service.py` — accept
  `request_id`, `winner_draft_id`, `synthesis_hash`, `surface` form
  fields; preserve legacy callable signatures for editor-driven
  uploads.
- `pdf_service/app.py` — add response headers
  `X-Pdf-Service-Duration-Ms`, `X-Pdf-Service-Status`,
  `X-Pdf-Service-Playwright-Ready`; non-breaking.
- `n8n/workflows/cv-upload.json` (new) — authoritative export
  including `request_id` dedup node with 7-day TTL.
- `infra/systemd/scout-cv-publish-worker@.service` (new).
- `infra/scripts/verify_n8n_workflow_sync.py` (new).
- `infra/scripts/verify-publish-cutover.sh` (new) — pre-flight
  cutover checks.
- `scripts/cv_assembly_publish_dry_run.py` (new).
- `scripts/cv_assembly_enqueue_publish.py` (new).
- `scripts/cv_assembly_sheets_migrate_v2.py` (new) — one-time header
  migration.
- `scripts/cv_assembly_finalize_delivered.py` (new) — operator
  manual `delivered` re-trigger.
- `scripts/cv_assembly_pdf_health_override.py` (new).
- `scripts/benchmark_publish_4_3_6.py` (new).
- `data/eval/validation/cv_assembly_4_3_6_publish/` (new).
- `tests/unit/cv_assembly/publish/` (new).
- `tests/integration/cv_assembly/publish/` (new).
- `docs/current/architecture.md` — document
  `cv_assembly.publish_state` subtree, gate, idempotency contract.
- `docs/current/operational-development-manual.md` — extend with
  the §24 VPS chain.
- `docs/current/missing.md` — close the 4.3.6 gaps enumerated above.
