# Iteration 4.3.2 Plan: Header Identity and Hero Proof Contract

## 1. Executive Summary

The header is the first and most scrutinized surface of any CV. It
announces identity, sets the tone for everything that follows, and
(for many recruiters) is the only surface they read carefully. In the
current Layer 6 V2 pipeline, the `HeaderGenerator` runs **after**
stitching — it re-derives profile, tagline, key achievements, and core
competencies from the already-assembled CV and the JD. That is too late
and too free-form to be safely candidate-aware across three parallel
drafts.

Iteration 4.3.2 introduces a structured, pre-prose **header blueprint**
that is computed once per job, consumed by all three draft-assembly
passes, and enforced by a deterministic validator before any header
prose exists. The blueprint is bound to master-CV evidence (4.3.1) and
the 4.2 `presentation_contract`, and it is explicitly prose-free: it
emits identity, title, tagline ingredients, hero-proof fragments,
credibility markers, and audience-variant tilts — not copy.

After 4.3.2, every draft starts from one truthful identity, one
pre-approved title, one pre-approved tagline frame, and a bounded hero-
proof fragment pool. The difference between the three drafts becomes
emphasis and pattern, not identity.

## 2. Mission

Produce one canonical, evidence-grounded, evaluator-aware header
blueprint per job, before any CV prose is generated, so that the three
candidate-aware drafts downstream all start from the same truthful
identity and the same bounded pool of header-level proof fragments.

## 3. Objective

Define and ship:

- a `HeaderBlueprintDoc` schema bound to master-CV evidence and
  presentation-contract signals;
- a stage `cv.header_blueprint` that produces exactly one blueprint
  per job per `master_cv_checksum` × `presentation_contract_checksum`;
- a deterministic header validator that every downstream 4.3 stage
  runs against final prose before persisting;
- a "minimum viable truthful header" definition and a "strong
  competitive header" definition so the blueprint can expose a graceful
  degradation path;
- a blueprint-first mode on `HeaderGenerator` in Layer 6 V2 so draft
  prose is emitted from the blueprint rather than re-derived;
- benchmark corpora under `data/eval/validation/cv_assembly_4_3_2_
  header_blueprint/`.

## 4. Success Criteria

4.3.2 is done when:

- every `cv_ready` job produces a persisted `cv_assembly.header_blueprint`
  with explicit evidence refs;
- every header produced by any downstream draft passes the
  deterministic header validator (title, tagline scaffolding, hero
  proof lines, credibility markers) against the blueprint;
- no title appears in any published CV that is not in
  `acceptable_titles.exact` ∪ `acceptable_titles.closest_truthful` ∪
  `acceptable_titles.functional_label`;
- when the blueprint is missing, Layer 6 V2 falls back to its current
  behavior deterministically (no 4.3 lane invocation);
- the eval corpus passes 100% invariants between releases.

## 5. Non-Goals

- Generating header prose. The blueprint is pre-prose.
- Inventing identity or tagline language. All strings come from
  candidate-owned master-CV fields or deterministic compositions of them.
- Replacing `HeaderGenerator`. 4.3.2 adds a blueprint-first mode; the
  existing post-stitch derivation path is preserved as fallback.
- Doing web lookups.
- Choosing between three drafts. That is 4.3.5.

## 6. Why This Artifact Exists

The current `HeaderGenerator` (see `src/layer6_v2/header_generator.py`,
`src/layer6_v2/prompts/header_generation.py`, `src/layer6_v2/types.py`)
assembles the header after the experience section is stitched,
prepending the 4.1 persona guidance to its system prompt. That flow has
three structural problems for iteration 4.3:

1. **Three parallel drafts need one identity.** With the 4.3 multi-
   draft lane, each draft otherwise re-derives its own identity,
   risking inconsistent titles and taglines across drafts of the same
   candidate for the same job.
2. **Free-form header prose is hard to audit.** Today the profile,
   tagline, and key-achievement bullets are emitted as prose and then
   partially validated; we need structured slots before prose to catch
   title inflation, AI-depth climbing, and scope overstatement
   deterministically.
3. **Header proof must be master-CV-bound.** The hero-proof lines that
   appear in the header must cite specific achievements in specific
   roles. Without a blueprint, the LLM picks the best-sounding line
   from a JD; with a blueprint, it picks from a pre-filtered pool of
   achievement ids whose metadata is already vetted by 4.3.1.

The blueprint is the place where "what does this candidate lead with"
is decided once, grounded, and frozen before anyone writes prose.

## 7. Stage Boundary

### 7.1 DAG position

`cv_ready` → **`cv.header_blueprint`** → `cv.pattern_selection` → … .

The header blueprint runs before pattern selection so every pattern
draft consumes one shared identity. An alternative (per-pattern
headers) was considered and rejected; see §18.1.

### 7.2 Inputs

Required upstream (all from `level-2`):

- `pre_enrichment.jd_facts` (title, normalized title, identity signals,
  competency weights, top keywords, expectations, team context,
  ideal candidate profile);
- `pre_enrichment.classification` (role family, seniority, ai_taxonomy
  intensity, tone family);
- `pre_enrichment.research_enrichment.role_profile` (mandate,
  business_impact, success_metrics, evaluation_signals);
- `pre_enrichment.research_enrichment.company_profile` (industry,
  stage, identity band);
- `pre_enrichment.research_enrichment.application_profile` (ATS
  vendor family, parsing posture);
- `pre_enrichment.stakeholder_surface` (evaluator coverage target,
  per-role cv_preference_surface, reject signals);
- `pre_enrichment.pain_point_intelligence` (proof_map,
  bad_proof_patterns);
- `pre_enrichment.presentation_contract.document_expectations` (goal,
  tone posture, density posture, keyword balance);
- `pre_enrichment.presentation_contract.cv_shape_expectations`
  (title_strategy, header_shape, counts, ats_envelope);
- `pre_enrichment.presentation_contract.ideal_candidate_presentation_model`
  (visible_identity, acceptable_titles, tone_profile,
  credibility_markers, framing_rules, risk_flags);
- `pre_enrichment.presentation_contract.experience_dimension_weights`
  (overall_weights, stakeholder_variant_weights);
- `pre_enrichment.presentation_contract.truth_constrained_emphasis_rules`
  (title/header/summary/key_achievements section rules);
- master-CV (via loader) in 4.3.1 shape — full `RoleMetadata`,
  `ProjectMetadata`, taxonomies, `candidate_facts`.

Opportunistic (advisory, may be absent):

- `pre_enrichment.job_inference.semantic_role_model`.

### 7.3 Output

`cv_assembly.header_blueprint`: a `HeaderBlueprintDoc` persisted on
`level-2` under the `cv_assembly` subtree. See §9 for schema.

### 7.4 Work-item details

- `task_type = cv.header_blueprint`, `lane = cv_assembly`.
- `idempotency_key = cv.header_blueprint:<level2_id>:<input_snapshot_id>`
  where `input_snapshot_id = sha256(master_cv_checksum ||
  presentation_contract_checksum || jd_checksum)`.
- `max_attempts = 3`, retry backoff per iteration-4 pattern.
- `required_for_cv_assembled = true`. If this stage fails terminally,
  the 4.3 lane fails; no default blueprint is ever fabricated.
- Prerequisite check at claim: `lifecycle == "cv_ready"`,
  `presentation_contract.status in {completed, partial}` (not
  `failed_terminal` / `unresolved`), master-CV loader succeeds.

### 7.5 Source-of-truth chain (titles, identity, proof)

Three concerns historically had near-duplicate owners across 4.2.2,
4.2.4, 4.3.1, and 4.3.2 (plus the legacy `CandidateData.title_base`
default). 4.3.2 makes the ownership chain unambiguous:

| Concern | Owned by | Defined in |
|---------|----------|------------|
| Candidate-side title allowlist (`{exact[], closest_truthful[], functional_label[]}`) | Master-CV | 4.3.1 §9.4 (`role_metadata.acceptable_titles`) |
| Job-side title strategy enum | Job presentation contract | 4.2.2 §4.2 (`cv_shape_expectations.title_strategy`) |
| Job-side relevant-title hint (filter, not source) | Job presentation contract | 4.2.4 (`ideal_candidate_presentation_model.acceptable_titles[]`) — must be a subset of 4.3.1's allowlist |
| Picked title for a job | Header blueprint | 4.3.2 §9 (`HeaderBlueprintDoc.identity.chosen_title`); composition rule §11.1.1 |
| Candidate's default title (no job context) | Master-CV loader | `CandidateData.title_base` (used only as last-resort fallback in §11.1.1) |
| Visible-identity framing (job-aware seed) | Job presentation contract | 4.2.4 (`ideal_candidate_presentation_model.visible_identity`) |
| Visible-identity candidate **pool** | Header blueprint | 4.3.2 §9 (`identity.visible_identity_candidates[]`); composition rule §11.1.2 |
| Picked visible-identity per pattern | Pattern selection | 4.3.3 §9 (consumed via `evidence_map.header.*` per pattern) |
| Lead-phrase candidate **pool** | Header blueprint | 4.3.2 §9 (`tagline_ingredients.lead_phrase_candidates[]`); composition rule §11.1.3 |
| Picked lead-phrase per pattern | Pattern selection | 4.3.3 |
| Hero-proof fragment **pool** | Header blueprint | 4.3.2 §9 (`hero_proof_fragments[]`) |
| Hero-proof fragment **picks** per pattern | Pattern selection | 4.3.3 §9 (`evidence_map.key_achievements.slots[]`, `evidence_map.header.hero_proof_fragment_ids[]`) |

Implications:

- 4.3.2 is the **only stage** that emits `chosen_title` and
  `chosen_title_strategy`. Downstream stages may not override.
- The **pool** lives in 4.3.2; the **picks** live in 4.3.3 and
  4.3.4. No stage may add to a pool after the blueprint persists.
  If a pool is insufficient for a pattern, 4.3.3 swaps that pattern
  for a conservative default per 4.3.3 §10 — never adds to the pool
  retroactively.
- 4.2.4's `acceptable_titles[]` is a job-side **filter** (which
  subset of the candidate allowlist is plausibly relevant for this
  role family); the deterministic validator asserts it is a subset
  of 4.3.1's allowlist and never introduces titles outside that
  allowlist.
- 4.2.4's `title_strategy` is constrained to equal
  `cv_shape_expectations.title_strategy` per 4.2.2 §4.7. 4.3.2 reads
  4.2.2 as the canonical source.

## 8. Cross-Artifact Invariants

- `chosen_title ∈ role_metadata.acceptable_titles.exact ∪
  role_metadata.acceptable_titles.closest_truthful ∪
  role_metadata.acceptable_titles.functional_label` (4.3.1 is the
  source of truth; see §7.5).
- `chosen_title_strategy == cv_shape_expectations.title_strategy`
  (4.2.2 is the source of truth; 4.2.4's `title_strategy` is
  constrained to equal it; see §7.5).
- Every `hero_proof_fragments[].role_id` ∈ master-CV role ids.
- Every `hero_proof_fragments[].achievement_id` resolves within that
  role.
- Every `credibility_markers[]` ref ∈
  `credibility_marker_taxonomy.json`.
- `ai_relevance_claim.intensity_band` ≤
  `classification.ai_taxonomy.intensity`.
- `leadership_claim.band` ≤ the max
  `RoleMetadata.seniority.managerial_level` across cited roles.
- `differentiators[]` ⊆ candidate-global
  `role_metadata.global_credibility_markers[]` (no job-specific
  differentiator fabrication).
- Every `audience_variants` key ∈
  `stakeholder_surface.evaluator_coverage_target`.
- `not_identity[]` must not intersect `identity_tags[]`.

Failure of any invariant fails the stage run (one deterministic repair
retry; then deadletter per iteration-4 semantics).

## 9. Output Shape / Schema Direction

```text
HeaderBlueprintDoc {
  schema_version,
  input_snapshot_id,
  master_cv_checksum,
  presentation_contract_checksum,
  jd_checksum,
  status,                                   # completed | partial | degraded | failed
  identity {
    chosen_title,                           # one value (4.3.2-owned; see §7.5)
    chosen_title_strategy,                  # exact_match | closest_truthful | functional_label | unresolved
    title_candidates[],                     # ordered ranks 1..N with similarity scores; see §11.1.1
    visible_identity_candidates[],          # 3-5 candidates; deterministic per §11.1.2; patterns pick
    identity_tags[],                        # refs to identity_taxonomy (frozen guardrail)
    not_identity[],                         # tags forbidden for this job (frozen guardrail)
    tone_profile { ... }                    # same enum as 4.2.4 tone_profile
  },
  tagline_ingredients {
    lead_phrase_candidates[],               # 3-6 candidates; deterministic per §11.1.3; patterns pick
    proof_anchor_pool[],                    # ordered refs into hero_proof_fragments[]; patterns pick
    differentiator_anchor_pool[],           # ordered refs into differentiators[]; patterns pick
    forbidden_phrases[],                    # frozen guardrail: reject_signals + bad_proof_patterns
    length_band                             # frozen guardrail: short | standard | expansive
  },
  hero_proof_fragments[] {                  # POOL of candidate fragments; 4.3.3 patterns pick subsets
    fragment_id,                            # stable slug within blueprint
    role_id,
    achievement_id,
    variant_id,                             # nullable
    proof_category,                         # canonical 4.2.3 proof-category enum
    dimensions[],                           # canonical 4.2.5 dimension enum
    credibility_markers[],                  # refs
    scope_band,                             # from RoleMetadata.achievements[].scope_band
    metric_band,                            # from RoleMetadata.achievements[].metric_band
    ai_relevance_band,                      # from RoleMetadata.achievements[].ai_relevance_band
    suggested_placement,                    # enum: header_line | key_achievement | summary_line | competency | experience_only
    fit_rationale,                          # <= 240 chars, cites presentation_contract ids
    confidence: ConfidenceDoc,
    source_fragment_ref                     # provenance to role markdown
  },
  credibility_markers[] {                   # header-surface markers
    marker_id,
    source_evidence_ref,
    placement_hint                          # enum: tagline | key_achievement | competency | omit
  },
  differentiators[] {                       # candidate-wide, not job-wide
    differentiator_id,
    source_evidence_ref
  },
  proof_line_policy,                        # from cv_shape_expectations.header_shape.proof_line_policy
  differentiator_line_policy,               # same
  header_surface_policy {
    default_variant,                        # ats_safe | recruiter_rich | regional_enriched
    allowed_metadata_fields[],
    required_metadata_fields[],
    forbidden_metadata_fields[],
    field_placement {<field_id>: placement},# contact_line | metadata_line | footer | omit
    region_code
  },
  ats_hints {
    priority_keywords[],                    # keywords the blueprint requires present
    forbidden_keywords[],                   # keywords that violate truth rules
    placement_bias                          # mirrors cv_shape_expectations.ats_envelope.keyword_placement_bias
  },
  audience_variants {
    recruiter          : { tilt[], must_see[], forbid[] } | null,
    hiring_manager     : { tilt[], must_see[], forbid[] } | null,
    executive_sponsor  : { tilt[], must_see[], forbid[] } | null,
    peer_reviewer      : { tilt[], must_see[], forbid[] } | null
  },
  viability_bands {                         # describes BOUNDS on what 4.3.3 patterns may pick
                                            # from the pools, not specific frames
    minimum_viable_truthful_header: {       # smallest valid pick from the pool
      chosen_title,                         # always equal to identity.chosen_title (frozen)
      visible_identity_candidate_id,        # the single most conservative candidate id
      lead_phrase_candidate_id,             # the single most conservative candidate id
      hero_proof_fragment_ids[],            # 1-2 ids that MUST be present in any pattern
      credibility_marker_ids[]              # 0-1 ids that MUST be present in any pattern
    },
    strong_competitive_header: {            # aspirational ceiling on pattern picks
      visible_identity_candidate_ids[],     # acceptable richer-frame candidates
      lead_phrase_candidate_ids[],          # acceptable richer-frame candidates
      hero_proof_fragment_ids[],            # 2-4 ids encouraged when evidence is rich
      credibility_marker_ids[],             # 2+ ids encouraged
      differentiator_ids[]                  # encouraged when evidence supports
    }
  },
  debug_context: HeaderBlueprintDebug,      # debug block, not mirrored to snapshot
  confidence: ConfidenceDoc,
  evidence[]                                # top-level evidence refs
}
```

Notes:

- The blueprint never contains full tagline prose or full key-achievement
  prose. It exposes **ingredients** and **proof fragment refs** that the
  draft-assembly stage turns into prose.
- `visible_identity` is composed deterministically from
  `ideal_candidate_presentation_model.visible_identity` and
  `role_metadata.identity_summary.primary_identity_tags`, with the LLM
  constrained to choose from a pre-filtered vocabulary.
- `viability_bands` expose two anchored frames — a graceful degradation
  option and an aspirational one — so downstream drafts have a clear
  "spine" if evidence slips.

Header surface variants and metadata-slot policy:

- `ats_safe`
  - required base surface for every job;
  - keeps to name, title, contact links, location, proof line, and
    differentiator line only;
  - excludes photo and excludes sensitive personal metadata unless the
    field is explicitly marked public and directly useful to hiring friction.
- `recruiter_rich`
  - may add a tagline/identity line and selected policy-approved metadata;
  - must still remain single-column and ATS-parseable.
- `regional_enriched`
  - only available when `candidate_facts.display_policy` explicitly allows it;
  - exists for markets such as UAE/KSA where nationality, visa status,
    languages, or driving-license metadata may materially affect screening.

Canonical header skeleton:

1. `name`
2. `chosen_title`
3. `contact_line`
4. `metadata_line` (optional; policy-gated)
5. `proof_line` (required when 4.2.2 header density is `proof_dense`)
6. `differentiator_line` (optional)

The header blueprint, not draft assembly, owns the allowed metadata fields
and their placement.

### 9.1 `HeaderBlueprintDebug`

```text
HeaderBlueprintDebug {
  input_summary {
    role_family,
    seniority,
    ai_intensity,
    evaluator_roles_in_scope[],
    master_cv_roles_in_scope[],              # role_ids considered
    master_cv_achievements_in_scope_count,
    presentation_contract_status,
    title_strategy
  },
  defaults_applied[],
  normalization_events[],
  richer_output_retained[],
  rejected_output[],
  retry_events[],
  validator_trace[]                          # which invariants were checked, outcomes
}
```

Collection-backed only, never mirrored to any public projection.

## 10. Fail-Open / Fail-Closed

Fail open:

- When `presentation_contract` is `partial` or
  `ideal_candidate_presentation_model.acceptable_titles` is thin, the
  blueprint chooses `title_strategy = closest_truthful` and picks
  from role-family defaults declared in
  `role_metadata.acceptable_titles`.
- When `stakeholder_surface.status` is `inferred_only`, `audience_variants`
  is emitted only for `recruiter` and `hiring_manager` with
  lower confidence; other variants are `null`.
- When `pain_point_intelligence.proof_map` is sparse, hero_proof_fragments
  are selected by master-CV metric/scope/dimension salience alone,
  confidence capped at `medium`.
- When region-specific metadata is not explicitly permitted by
  `candidate_facts.display_policy`, the blueprint defaults to
  `header_surface_policy.default_variant = ats_safe`.

Fail closed:

- Any title outside the `acceptable_titles` allowlist → reject,
  repair retry, then deadletter.
- Any `ai_relevance_band` exceeding `classification.ai_taxonomy.intensity`
  → reject.
- Any `leadership_claim.band` exceeding the max cited role's managerial
  level → reject.
- Any `hero_proof_fragment` whose `achievement_id` does not resolve in
  master-CV → reject.
- Any `credibility_markers[]` ref not in the taxonomy → reject.
- Any `forbidden_phrases[]` absent → reject (blueprint must explicitly
  forbid `reject_signals` and `bad_proof_patterns`).
- Any `audience_variants` key not in the evaluator coverage target →
  reject.
- Any header metadata field outside `candidate_facts.display_policy` or
  `header_surface_policy.allowed_metadata_fields[]` → reject.
- Any hero proof fragment selected from a 4.3.1 achievement whose
  `allowed_surfaces[]` omits `header_proof` → reject.

## 11. Safety / Anti-Hallucination Rules

- Prose is forbidden. The prompt constrains the LLM to emit
  ingredient-level strings, not full taglines or bullets.
- No metric invention. The only numbers permitted in the blueprint are
  `metric_band` enums and numerical band ordinals; free-form numbers
  (e.g. "40% YoY") are forbidden in every string field and rejected
  at ingress.
- No AI claim climbing. `ai_relevance_claim.intensity_band` is clamped
  to `classification.ai_taxonomy.intensity`.
- No stakeholder speculation. `audience_variants` only reflects the
  evaluator coverage target; no named real stakeholders appear.
- No scope inflation. `leadership_claim.band`,
  `scope_band`, `metric_band` must each cite a master-CV achievement
  or role metadata field; the validator resolves these at persist time.
- No future claims. `candidate_facts.education[].confidence` must be
  ≥ `medium` for a credential to appear as a header proof.
- No gender/racial/protected-trait inferences anywhere.
- No sensitive metadata leakage. Stored truth in `candidate_facts` does not
  imply public-header eligibility; disclosure must pass the 4.3.1
  `display_policy` gate.

## 11.1 Deterministic Composition Rules

The blueprint exposes candidate **lists** for `chosen_title`,
`visible_identity`, and `lead_phrase` so 4.3.3 patterns can pick
distinct framings within frozen guardrails. The composition of these
candidates is deterministic by construction: for fixed inputs, the
output is byte-identical across runs (asserted by the eval corpus,
§13).

### 11.1.1 `chosen_title` and `title_candidates[]`

Inputs:

- `S = cv_shape_expectations.title_strategy` (4.2.2 — canonical SoT).
- `J = jd_facts.normalized_title`.
- `A_exact, A_closest, A_functional = role_metadata.acceptable_titles
  .{exact, closest_truthful, functional_label}` (4.3.1 — canonical
  candidate-side allowlist).
- `F = ideal_candidate_presentation_model.acceptable_titles[]`
  (4.2.4 — job-side filter; must be a subset of `A_exact ∪ A_closest
  ∪ A_functional`; rejected at ingress otherwise).
- `T = CandidateData.title_base` (master-CV loader; last-resort
  fallback only).

Algorithm:

1. If `S == exact_match` and `J ∈ (A_exact ∩ F)`: emit
   `chosen_title = J`, `chosen_title_strategy = exact_match`. Else
   downgrade strategy to `closest_truthful` and record the downgrade
   in `debug_context.normalization_events[]`; continue at step 2.
2. If `S == closest_truthful` (or downgraded to it): rank
   `(A_exact ∪ A_closest) ∩ F` by token-set similarity to `J`
   (deterministic metric: `|tokens(c) ∩ tokens(J)| /
   |tokens(c) ∪ tokens(J)|` over lower-cased whitespace-split tokens,
   stop-words preserved). Tie-break alphabetically. Emit highest-
   ranked as `chosen_title`.
3. If `S == functional_label`: rank `A_functional ∩ F` by token-set
   similarity to `ideal_candidate_presentation_model.visible_identity`.
   Tie-break alphabetically. Emit highest-ranked.
4. If `S == unresolved` or all eligible sets are empty: emit
   `chosen_title = T`, `chosen_title_strategy = unresolved`,
   `status = partial`.

`title_candidates[]` records the full ranking from step 2 or 3 with
similarity scores so 4.3.3 patterns may defensibly substitute within
the same strategy band (for example, a `leadership_led` pattern may
prefer the rank-2 `closest_truthful` candidate when its tokens
better match the pattern's emphasis). Patterns may not pick titles
outside `title_candidates[]` and may not change
`chosen_title_strategy`.

### 11.1.2 `visible_identity_candidates[]`

Bounded to 3–5 candidates. Composition order is fixed:

1. **Candidate 0** = `ideal_candidate_presentation_model.visible_identity`
   verbatim, when present and non-empty.
2. **Candidates 1..K** = templated phrases of shape
   `"<identity_tag.display_name> with <top_dimension.display_name>
   emphasis"` built by enumerating
   `role_metadata.identity_summary.primary_identity_tags` (capped at
   3 per the §16 v1 cap) paired with the top 2 dimensions from
   `experience_dimension_weights.overall_weights` sorted descending
   by weight then alphabetically. Iterate `(tag × dimension)` in
   that order; stop when the candidate count reaches 4.
3. **Candidate K+1** (last resort) = `"<role_family.display_name>
   Operator"` from `classification.primary_role_category`, included
   only when steps 1–2 produce fewer than 3 candidates.

Post-composition steps (deterministic):

- Deduplicate case-insensitively (preserving first occurrence).
- Reject any candidate containing tokens from
  `tagline_ingredients.forbidden_phrases[]`.
- Sort by composition order (NOT alphabetical — order encodes
  conservatism: index 0 is the most conservative, last index is the
  most aspirational).
- Cap at 5 candidates.

### 11.1.3 `lead_phrase_candidates[]`

Bounded to 3–6 candidates. Each is composed deterministically from a
`(visible_identity_candidate, dimension)` pair:

1. Take the top 3 `visible_identity_candidates[]` (by composition
   order).
2. Take the top 2 dimensions from
   `experience_dimension_weights.overall_weights` (sorted descending
   by weight then alphabetically).
3. For each `(vi, d)` pair in lexicographic order over indices:
   - Compose `phrase = f"{vi} — {d.display_name}"` (em-dash with
     spaces; ASCII fallback `"--"` permitted only when the ATS
     envelope requires ASCII).
   - If `len(phrase) > 80`: drop the dimension suffix → `phrase = vi`.
   - Append to candidates.
4. Deduplicate case-insensitively.
5. Reject any candidate containing tokens from
   `tagline_ingredients.forbidden_phrases[]`.
6. Sort by composition order (NOT alphabetical — index 0 is most
   conservative).
7. Cap at 6 candidates.

Patterns in 4.3.3 pick exactly one `lead_phrase_candidate` per
pattern; 4.3.4 realizes the picked phrase into prose with no further
LLM rewriting permitted.

## 11.2 Header Validator API And Repair Semantics

The header validator is a **shared library** consumed by 4.3.2,
4.3.4, and 4.3.5 — not a stage-internal helper. Its determinism is
load-bearing: the same draft + blueprint inputs must always produce
the same report.

### 11.2.1 Module and signature

Module: `src/cv_assembly/validators/header_validator.py`.

Public surface (Python pseudo-signature):

```python
def validate_header(
    header_struct: HeaderStruct,        # canonical struct: headline, tagline,
                                        # key_achievements[], core_competencies[]
    blueprint: HeaderBlueprintDoc,
    master_cv: CandidateData,
    *,
    mode: Literal["blueprint", "draft", "synthesis"],
    pattern: Optional[PatternDoc] = None,
    tracer: Optional[CvAssemblyTracingSession] = None,
) -> HeaderValidatorReport
```

Mode semantics:

- `"blueprint"`: validates the blueprint itself. Every candidate in
  `visible_identity_candidates[]`, `lead_phrase_candidates[]`, and
  every entry in `hero_proof_fragments[]` must satisfy the
  invariants in §8 and the safety rules in §11. Used inside 4.3.2
  before persist.
- `"draft"`: validates a 4.3.4 draft's header against the blueprint
  + a specific `pattern`. `pattern` is required in this mode. The
  validator asserts that every header element in the draft cites a
  pool entry the pattern picked.
- `"synthesis"`: validates a 4.3.5 synthesis output's header.
  `pattern=None` is allowed because synthesis may have promoted
  fragments across patterns; the validator instead asserts pool
  membership against the blueprint as a whole.

### 11.2.2 Report shape

```text
HeaderValidatorReport {
  status,                              # pass | repair_attempted | failed
  violations[] {
    rule_id,                           # stable slug (e.g. title_outside_allowlist)
    severity,                          # blocking | repairable | warning
    location {
      section,                         # title | tagline | key_achievement | core_competency
      slot_index?
    },
    detail,                            # <= 240 chars
    suggested_action                   # enum, see §11.2.3
  },
  repair_applied: bool,
  repair_actions[] {
    rule_id,
    action,                            # enum, see §11.2.3
    before_hash,
    after_hash
  },
  repaired_struct: HeaderStruct | null  # populated when repair_applied
}
```

### 11.2.3 Repair semantics

Repair is **deterministic**, **bounded to one pass**, and **never
calls an LLM**. It also never adds content outside the blueprint
pools + master-CV evidence. Allowed actions:

- `surgical_remove`: drop the offending fragment in place (e.g.,
  remove a forbidden phrase from a tagline; the rest of the tagline
  remains).
- `substitute_from_pool`: replace the offending value with the next-
  best candidate from the appropriate blueprint candidate list
  (e.g., substitute `chosen_title` with the next-highest
  `title_candidates[]` entry when the original is somehow outside
  `acceptable_titles`).
- `collapse_section`: drop a key_achievement or core_competency that
  fails resolution; renumber slots; preserve order.
- `clamp_band`: clamp a numeric/ordinal value (e.g., reduce an AI
  intensity claim to the maximum allowed by
  `classification.ai_taxonomy.intensity`).

Repair never:

- generates new prose;
- introduces master-CV refs not already in the blueprint pools;
- changes `chosen_title_strategy`;
- alters `identity_tags[]` or `not_identity[]`;
- regenerates via LLM.

After a single repair pass, the validator re-runs invariant checks
on `repaired_struct`. Remaining `severity=blocking` violations →
`status=failed`. Remaining `severity=repairable` violations after
one pass → `status=failed`. `severity=warning` violations are
retained in the report but do not fail the run.

### 11.2.4 Determinism guarantees

For fixed `(header_struct, blueprint, master_cv, mode, pattern)`,
`validate_header()` returns byte-identical `HeaderValidatorReport`
instances across runs. This is a hard invariant asserted by the eval
corpus (§13) and by a unit test fixture under
`tests/unit/cv_assembly/test_header_validator_determinism.py`.

## 12. Tracing / Observability Contract

- Stage span: `scout.cv.header_blueprint` with `job:<level2_id>`
  session.
- Substage spans:
  - `scout.cv.header_blueprint.preflight` — computes priors and
    projects presentation_contract inputs.
  - `scout.cv.header_blueprint.compose` — LLM call.
  - `scout.cv.header_blueprint.validate` — deterministic validator.
- Events:
  - `scout.cv.header_blueprint.title_chosen` with `chosen_title_strategy`
    and `chosen_title` (string, bounded 80 chars).
  - `scout.cv.header_blueprint.viability_bands` with boolean
    `minimum_viable_reached` and `strong_competitive_reached`.
  - `scout.cv.header_blueprint.rejection` on invariant violations with
    `rule_id`.
- Required metadata per span: `input_snapshot_id`,
  `master_cv_checksum`, `presentation_contract_checksum`, `jd_checksum`,
  `status`, `confidence.band`, `hero_proof_fragments_count`,
  `identity_tags_count`, `audience_variants_count`,
  `defaults_applied_count`, `normalization_events_count`,
  `rejected_output_count`.
- Forbidden payload content: full debug JSON, full tagline ingredients
  beyond `lead_phrase` preview (160 chars), full evidence[] entries.
  Debug body stays in Mongo.
- Trace refs are written to
  `cv_assembly.stage_states.cv.header_blueprint.trace_ref` so
  operators can jump from Mongo UI to Langfuse.

## 13. Eval / Benchmark Strategy

### 13.1 Corpus

`data/eval/validation/cv_assembly_4_3_2_header_blueprint/` holds:

- `cases/<job_id>/input/` — frozen `level-2` slice (preenriched,
  with all presentation_contract subdocuments) and the matching
  `data/master-cv/` snapshot.
- `cases/<job_id>/expected/blueprint.json` — the blueprint the
  benchmark expects given those inputs.
- `cases/<job_id>/expected/validator_report.json` — the deterministic
  validator's expected output.
- `cases/<job_id>/ground_truth.md` — reviewer notes and acceptance
  rationale.

Target minimum 20 cases spanning role families: architecture-first AI,
delivery-first engineering, engineering-leadership (EM/Sr EM), AI-
first applied ML, platform/infra, transformation, leadership
(director/head), and ambiguous `balanced` role.

### 13.2 Harness

`scripts/benchmark_header_blueprint_4_3_2.py`:

- Reads each case, runs the stage, compares against `expected/`.
- Asserts byte-level equality for the deterministic validator report.
- Asserts structural equivalence for the blueprint (bounded variance
  in string previews, strict equality for enum fields and ids).
- Reports reviewer-usefulness scores per case (manual reviewer sheet
  template provided).

### 13.3 Metrics

- Invariant pass rate (target = 1.00).
- Title allowlist compliance (target = 1.00).
- Viability band coverage (target: both
  `minimum_viable_truthful_header` and `strong_competitive_header`
  populated in ≥ 90% of cases).
- Reviewer usefulness (target ≥ 0.85).
- AI-claim drift (target = 0: any blueprint AI band > classification
  intensity is a hard fail).
- Stage latency p95 (report only; target: < 20s on canary model).

### 13.4 Regression gate

Rollout blocks if:

- Invariant pass rate drops below 1.00.
- Title allowlist violation appears in any case.
- Reviewer usefulness drops by more than 5 points.
- AI-claim drift count increases.

## 14. Model And Execution

- Primary: `gpt-5.4`.
- Baseline: `gpt-5.4-mini`.
- One schema-repair retry on invariant failure (§11).
- No web search.
- Deterministic preflight composes candidate fragments from master-CV
  evidence and presentation-contract signals; the LLM is asked to
  **rank and fill**, not invent.
- Deterministic post-processing enforces every rule in §8, §10, §11.
- Prompt is built in `src/cv_assembly/prompts/header_blueprint.py`
  (new).

## 15. Rollout / Migration / Compatibility

### 15.0 Hard prerequisites

Before any 4.3.2 code is enabled, the following must be true in
production:

- `MASTER_CV_BLUEPRINT_V2_ENABLED=true` (4.3.1) — the candidate
  allowlist `role_metadata.acceptable_titles`, the
  `identity_taxonomy`, and the `credibility_marker_taxonomy` files
  exist and load cleanly.
- `pre_enrichment.presentation_contract` is being persisted with
  populated `ideal_candidate_presentation_model`,
  `experience_dimension_weights`, `truth_constrained_emphasis_rules`,
  and `cv_shape_expectations` subdocuments. If any subdocument is
  absent at runtime, 4.3.2 fails open to role-family defaults
  derived from `classification.primary_role_category` with
  confidence capped at `medium` and `status=partial`. This is the
  degraded path — never the operating mode.
- `cv_shape_expectations.title_strategy` (4.2.2) is the canonical
  job-side title-strategy source. 4.2.4's `title_strategy` field is
  validated to equal it; no other consumer re-derives the strategy.
- `ideal_candidate_presentation_model.acceptable_titles[]` (4.2.4)
  is validated as a subset of `role_metadata.acceptable_titles`
  (4.3.1) at ingress; jobs failing this check are rejected at
  ingress, not silently demoted.

If any prerequisite is unmet for a job, 4.3.2 emits `status=partial`
or `status=degraded` and never `status=completed`.

### 15.1 Rollout order

1. Ship `HeaderBlueprintDoc` + validator schema + tests.
2. Ship the stage behind
   `CV_ASSEMBLY_HEADER_BLUEPRINT_ENABLED=false`. Bench on eval corpus.
3. Enable the flag in shadow mode — the blueprint is persisted but
   Layer 6 V2 keeps its current header path.
4. Enable blueprint-first mode on `HeaderGenerator`:
   - if `cv_assembly.header_blueprint.status in {completed, partial}`
     and `CV_ASSEMBLY_HEADER_BLUEPRINT_CONSUMED=true`, the generator
     constrains itself to the blueprint;
   - else, legacy behavior.
5. Canary 1 job, 5 jobs, 25 jobs, 100% with 72h soak.
6. Enforce the validator on all header prose before publish.

### 15.2 Compatibility

- Legacy callers of `HeaderGenerator.generate()` without a blueprint
  continue to work.
- `HeaderOutput` shape (`ProfileOutput`, `SkillsSection`,
  `Education`, `Contact`) is unchanged. 4.3.2 does not rename legacy
  fields.
- Mongo readers of `level-2` that only look at publisher fields see
  no change; the blueprint is additive.

### 15.3 Rollback

Flag-flip disables blueprint reading; `HeaderGenerator` re-engages the
legacy path. Persisted blueprints remain for audit; no deletion.

## 16. Open-Questions Triage

Items resolved in this revision are marked **(resolved)** with the
section that implements the resolution. Deferred items remain v1
recommendations subject to re-bench.

| Question | Triage | Resolution |
|----------|--------|------------|
| What is the single source of truth for `acceptable_titles` and `title_strategy` across 4.2.2, 4.2.4, 4.3.1, and 4.3.2? | Must resolve before implementation | **(resolved)** §7.5 establishes the SoT chain: 4.3.1 owns the candidate allowlist; 4.2.2 owns the job-side strategy enum; 4.3.2 owns the picked title; 4.2.4's `acceptable_titles` is a derived job-side filter validated as a subset of 4.3.1; 4.2.4's `title_strategy` is constrained to equal 4.2.2's. `CandidateData.title_base` is last-resort fallback only. |
| Does one blueprint freeze only `chosen_title` and guardrails, or also `visible_identity` and `lead_phrase`? | Must resolve before implementation | **(resolved)** §9 + §18.1 — the blueprint freezes the truth boundary (title, identity_tags, not_identity, forbidden_phrases, AI/leadership band caps, the `hero_proof_fragments[]` pool). It exposes `visible_identity_candidates[]` and `lead_phrase_candidates[]` as **bounded pools**; 4.3.3 patterns pick one of each per pattern. This preserves both cross-draft truth stability and meaningful per-pattern framing. |
| What is the deterministic composition rule for `visible_identity_candidates[]`? | Must resolve before implementation | **(resolved)** §11.1.2 — fixed composition order over `ideal_candidate_presentation_model.visible_identity` + templated `(identity_tag × top_dimension)` pairs + last-resort role-family default; deduplication; forbidden-phrase filtering; ordered by conservatism not alphabetically; capped at 5. |
| What is the deterministic composition rule for `lead_phrase_candidates[]`, including tie-breaks? | Must resolve before implementation | **(resolved)** §11.1.3 — `(visible_identity_candidate, dimension)` lexicographic enumeration; em-dash composition with ASCII fallback when ATS envelope requires it; 80-char clamp drops the dimension suffix; deduplication; forbidden-phrase filtering; ordered by conservatism; capped at 6. |
| What is the shared header-validator API and what exactly does repair do? | Must resolve before implementation | **(resolved)** §11.2 — `validate_header()` in `src/cv_assembly/validators/header_validator.py` with explicit `mode={"blueprint","draft","synthesis"}` semantics, `HeaderValidatorReport` shape, allowed repair actions (`surgical_remove`, `substitute_from_pool`, `collapse_section`, `clamp_band`), single-pass bound, no LLM in repair, byte-deterministic guarantees asserted by eval. Shared by 4.3.4 and 4.3.5. |
| Does `PresentationContractDoc` grow 4.2.4 fields before 4.3.2 starts, or does 4.3.2 read a different upstream object? | Must resolve before implementation | **(resolved)** §15.0 Hard Prerequisites — `PresentationContractDoc.ideal_candidate_presentation_model`, `experience_dimension_weights`, `truth_constrained_emphasis_rules`, and `cv_shape_expectations` must be persisted in production before 4.3.2 enables. The degraded fail-open path (role-family defaults) is permitted but is never the operating mode. |
| Are `hero_proof_fragments[]` and 4.3.3 `key_achievements.slots[]` complementary or redundant? | Must resolve before implementation | **(resolved)** §7.5 + §9 — they are complementary. 4.3.2 owns the **pool** (`hero_proof_fragments[]`); 4.3.3 owns **picks** per pattern (`evidence_map.key_achievements.slots[]`, `evidence_map.header.hero_proof_fragment_ids[]`). No stage may add to the pool after 4.3.2 persists. Pool insufficiency for a pattern triggers the conservative-default swap in 4.3.3 §10, not pool retroactive growth. |
| Should 4.3.2 also carry summary ingredients? | Safe to defer | v1 keeps summary realization in 4.3.4 (per pattern). Revisit only if header-consistency benchmarks expose drift in summary identity across drafts of the same job. |
| Should `identity_tags[]` be capped at 1–3 or 1–5? | Safe to defer | v1: cap at 1–3 to keep `visible_identity_candidates[]` composition (§11.1.2) bounded. Cardinality tuning is secondary now that the composition rule exists. |
| Should regional phrasing become an explicit flag rather than emerge from tone/profile rules? | Safe to defer | v1 encodes regional posture via `tone_profile.formality` + `ats_envelope.format_rules` (4.2.2). Explicit regional flag deferred until eval shows drift across UK / US / EU job sets. |

## 17. Primary Source Surfaces

- `src/layer6_v2/header_generator.py`
- `src/layer6_v2/prompts/header_generation.py`
- `src/layer6_v2/types.py` (`HeaderOutput`, `ProfileOutput`,
  `HeaderGenerationContext`)
- `src/layer6_v2/cv_loader.py`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
- `plans/iteration-4.2.2-document-expectations-and-cv-shape-expectations.md`
- `docs/current/cv-generation-guide.md` (Part 5, Part 6)
- `src/preenrich/blueprint_models.py` (`PresentationContractDoc`)
- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`

## 18. Implementation Targets

- `src/cv_assembly/stages/header_blueprint.py` (new)
- `src/cv_assembly/prompts/header_blueprint.py` (new)
- `src/cv_assembly/models.py` — add `HeaderBlueprintDoc`,
  `HeroProofFragmentDoc`, `TitleCandidateDoc`,
  `HeaderBlueprintDebug`, `ViabilityBandDoc`.
- `src/cv_assembly/validators/header_validator.py` (new) —
  deterministic validator; used by 4.3.4 draft assembly and 4.3.5
  synthesis before persist.
- `src/cv_assembly/stage_registry.py` — register
  `cv.header_blueprint` with `required_for_cv_assembled=True`.
- `src/cv_assembly/dag.py` — edge from `cv_ready` to
  `cv.header_blueprint`.
- `src/layer6_v2/header_generator.py` — optional `blueprint:
  HeaderBlueprintDoc` parameter; when supplied, drives prose
  composition.
- `src/layer6_v2/prompts/header_generation.py` — new
  `build_profile_system_prompt_from_blueprint()` that mints a
  blueprint-scoped system prompt.
- `scripts/benchmark_header_blueprint_4_3_2.py` (new)
- `data/eval/validation/cv_assembly_4_3_2_header_blueprint/` (new)

### 18.1 Why one blueprint per job, with pools (not per pattern, not single-frame)

Two designs were considered and rejected:

- **One blueprint with a single frozen frame** — one
  `visible_identity`, one `lead_phrase`. Rejected because it forces
  the three 4.3.3 patterns into pure emphasis variations and visibly
  degrades pattern diversity (an `architecture_led` pattern and a
  `leadership_led` pattern from the same career legitimately call
  for different framings).
- **One blueprint per pattern** — three blueprints. Rejected
  because identity must be stable across drafts of the same
  candidate for the same job; per-pattern identity invites title
  drift, multi-source hallucination, and validator divergence.

The chosen design splits the blueprint into:

- **Frozen guardrails** — `chosen_title`, `chosen_title_strategy`,
  `identity_tags[]`, `not_identity[]`, `forbidden_phrases[]`, AI
  band caps, leadership band caps, and the `hero_proof_fragments[]`
  pool. These are computed once per job and never change across
  patterns.
- **Bounded candidate pools** — `visible_identity_candidates[]`,
  `lead_phrase_candidates[]`, `proof_anchor_pool[]`,
  `differentiator_anchor_pool[]`. These are deterministic
  compositions (§11.1) over master-CV evidence and presentation-
  contract signals; 4.3.3 patterns pick from them. No stage may add
  to a pool after the blueprint persists.

Patterns differ in **which picks** they make from the pools and in
section emphasis, not in who the candidate is or what the truth
boundary allows. The header validator (§11.2) enforces this for
every draft and every synthesis, in `mode="draft"` and
`mode="synthesis"` respectively.

`viability_bands` (§9) bound the picks: the
`minimum_viable_truthful_header` IDs MUST be present in every
pattern's selection; the `strong_competitive_header` IDs are the
permitted aspirational ceiling. Patterns operate within those
bands.
