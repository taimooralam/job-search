# Iteration 4.2.3 Plan: Pain-Point Intelligence V2 and Proof Map

## 1. Objective

Produce a canonical `pain_point_intelligence` artifact that upgrades the runner
pain-point miner into an evidence-grounded, research-aware stage and adds an
explicit **proof map**: for each pain, what proof in a CV would reassure the
evaluator.

This artifact becomes the canonical pain-and-proof substrate for
`presentation_contract`, later candidate evidence retrieval, STAR selection,
and reviewer UI.

The stage is candidate-agnostic: it describes what the employer is worried
about, not what any specific candidate has done.

## 2. Why This Artifact Exists

`blueprint_assembly.snapshot` currently backfills `pain_points`,
`strategic_needs`, `risks_if_unfilled`, and `success_metrics` from proxy fields
(screening themes, evaluation signals, JD `implied_pain_points`). That is too
thin for a pre-candidate CV skeleton because it:

- mixes pain, need, risk, and success metric into undifferentiated lists
- carries no source attribution
- provides no proof-target mapping
- does not use `research_enrichment` evidence

The skeleton needs to know:

- what the employer is worried about (pain)
- what the role exists to solve (strategic need)
- what failure would look like (risk if unfilled)
- what success looks like (success metric)
- what proof in a CV would reassure each pain (proof map)

These four categories must stay **distinct and typed**, not collapsed into a
single list.

## 3. Stage Boundary

`pain_point_intelligence` is its own stage and artifact (see umbrella §5.2).

### 3.1 Prerequisites (for `stage_registry`)

- `prerequisites = ("jd_facts", "classification", "research_enrichment")`
- `produces_fields = ("pain_point_intelligence",)`
- `stakeholder_surface` is an opportunistic input, not a hard prerequisite
  (the stage can run in parallel with stakeholder discovery)

### 3.2 Relationship to `research_enrichment`

`research_enrichment.role_profile` already surfaces `risk_landscape`,
`success_metrics`, and `interview_themes`. `pain_point_intelligence` reuses
those fields as evidence, but does not duplicate research fetches. It is a
synthesis-plus-structured-extraction stage over upstream artifacts.

## 4. Inputs

Required:

- `jd_facts` (merged view, including `implied_pain_points`, `success_metrics`,
  `operating_signals`, `ambiguity_signals`)
- `classification` (role family, tone, AI taxonomy)
- `research_enrichment.company_profile` (signals, recent_signals,
  role_relevant_signals, scale_signals, ai_data_platform_maturity)
- `research_enrichment.role_profile` (mandate, business_impact, success_metrics,
  risk_landscape, evaluation_signals, interview_themes, why_now)
- `research_enrichment.application_profile` (friction_signals, stale_signal,
  closed_signal)

Opportunistic:

- `stakeholder_surface` (evaluator CV preference surfaces, reject signals)
- `job_inference.semantic_role_model`
- top-keywords and repeated phrases from `jd_facts.top_keywords`

## 5. Output Shape

```text
pain_point_intelligence {
  status,                             # completed | partial | unresolved
  pain_points[],
  strategic_needs[],
  risks_if_unfilled[],
  success_metrics[],
  proof_map[],
  search_terms[],
  unresolved_questions[],
  sources: [SourceEntry],             # points to upstream artifacts and/or URLs
  evidence: [EvidenceEntry],
  confidence: ConfidenceDoc,
  debug_context?
}
```

Pain point entry:

```text
pain_points[] {
  pain_id,                            # stable slug, e.g. "p_scaling_ml_eval"
  category,                           # technical | business | delivery | org | stakeholder | application
  statement,                          # short, specific, non-generic
  why_now,                            # company/role context explaining urgency
  source_scope,                       # jd_only | jd_plus_research | research_only
  evidence_refs[],                    # source_ids or upstream-artifact paths
  urgency,                            # low | medium | high
  related_stakeholders[],             # persona_type enum values (optional)
  likely_proof_targets[],             # proof-category enum values
  confidence: ConfidenceDoc
}
```

Strategic-need, risk, success-metric entries share a similar shape with their
own category enum but must **not** duplicate pain_point statements. Each must
be typed, sourced, and linked to at least one pain_point where applicable.

Proof map entry:

```text
proof_map[] {
  pain_id,                            # foreign key to pain_points[].pain_id
  preferred_proof_type,               # metric | architecture | leadership | domain | reliability | ai | stakeholder
  preferred_evidence_shape,           # short description, e.g. "scope + scale + outcome"
  bad_proof_patterns[],               # what would fail to reassure
  affected_document_sections[],       # canonical section ids (see 4.2.2 §5)
  rationale,
  confidence: ConfidenceDoc
}
```

Search terms:

```text
search_terms[] { term, intent, source_basis }
```

`search_terms[]` must be usable as retrieval queries over a candidate evidence
store (master CV, STAR records, lantern skills) in a later phase.

## 6. Extraction Strategy

### 6.1 Deterministic pre-pass (Python, no LLM)

Mine text from:

- JD sections (responsibilities, requirements, nice-to-haves, about, challenges)
- `jd_facts.top_keywords`, `operating_signals`, `ambiguity_signals`
- `research_enrichment.company_profile` signal lists
- `research_enrichment.role_profile` list fields
- `application_profile.friction_signals`

Produce a candidate evidence bag per pain category, with source ids.

### 6.2 LLM synthesis pass

Input: structured evidence bag + JD excerpt + role/company/role context.
Output: typed `pain_points`, `strategic_needs`, `risks_if_unfilled`,
`success_metrics`, `proof_map`, `search_terms`, `unresolved_questions`.

### 6.3 Deterministic post-pass

- enforce unique `pain_id` values
- enforce every `proof_map` entry references a valid `pain_id`
- enforce `likely_proof_targets` and `preferred_proof_type` use the canonical
  proof-category enum (shared with 4.2.2)
- de-duplicate statements across the four category lists (one statement cannot
  appear in both `pain_points` and `strategic_needs`)
- clamp urgency and confidence bands based on source_scope (research-only
  pains cannot be `high` urgency without converging evidence)

## 7. Web Research

Default: **no web research**. Reuse upstream artifacts only.

Optional supplemental web research is permitted only when:

- `research_enrichment.status` is `partial` or `unresolved`
- pain evidence is thin and budget permits
- the stage explicitly records its search queries and source ids

Never duplicate the full `research_enrichment` pipeline.

## 8. Fail-Open / Fail-Closed

Fail open:

- if research is thin, emit JD-only pain points with `source_scope=jd_only`,
  lower confidence, and explicit `unresolved_questions`
- if `proof_map` cannot be generated for a low-confidence pain, omit the proof
  entry rather than fabricate one

Fail closed:

- no fabricated company events, leadership changes, funding rounds, or metrics
- no unsupported urgency claims (`high` urgency requires converging evidence)
- no generic HR boilerplate for specific JDs (e.g., "team player" as a pain)
- no pain statements without at least one source id or upstream-artifact ref
- no cross-category duplication

## 9. Model and Execution

Recommended flow:

1. deterministic evidence mining (Python)
2. LLM synthesis pass (`gpt-5.4` primary; benchmark `gpt-5.2` for extraction
   discipline)
3. deterministic post-pass (Python)

Escalation: one schema-repair retry if payload is useful but malformed.
No unbounded retries.

## 10. Prompt Constraints

Prompt rules:

- No generic pain points. Every pain must be concrete and tied to the JD,
  company, or role evidence.
- Every pain must map to at least one evidence source.
- Distinguish pain from strategic need from risk from success metric.
- Explicitly state what proof would reassure the evaluator for each pain.
- Do not assert external company facts absent from the inputs.
- Produce `search_terms[]` that a later retrieval stage can execute verbatim.
- Unresolved is a valid first-class answer; `unresolved_questions[]` must be
  populated rather than guessed.

## 11. Downstream Use

- `presentation_contract` (all four subdocuments)
- later candidate evidence retrieval over master CV and STAR records
- STAR selection improvements
- reviewer UI: "what this job needs solved"
- (optional, later) input to outreach guidance refresh

## 12. Tests and Evals

Minimum tests:

- pain category coverage (at least one pain across `technical`, `business`,
  `delivery` where JD supports it)
- no duplication across pain / need / risk / metric lists
- every pain has `evidence_refs[]`
- every high-confidence pain has a proof_map entry
- genericity checks (reject "team player", "strong communicator" as pains)
- proof-category enum compliance
- pain_id uniqueness and referential integrity with proof_map

Eval metrics:

- pain-point specificity (reviewer rating)
- proof-target usefulness (reviewer rating)
- role/company grounding (source-id coverage)
- JD-only graceful degradation quality

## 13. Primary Source Surfaces

- `src/layer2/pain_point_miner.py`
- `docs/phase-4-pain-point-miner.md`
- `src/preenrich/stages/research_enrichment.py`
- `src/preenrich/stages/job_inference.py`
- `src/preenrich/stages/blueprint_assembly.py`
- `docs/current/cv-generation-guide.md`

Implementation surfaces:

- new `src/preenrich/stages/pain_point_intelligence.py`
- new `PainPointIntelligenceDoc` and entry sub-models in
  `src/preenrich/blueprint_models.py`
- new prompt builder in `src/preenrich/blueprint_prompts.py`
