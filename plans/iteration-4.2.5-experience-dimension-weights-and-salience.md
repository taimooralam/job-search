# Iteration 4.2.5 Plan: Experience Dimension Weights and Salience

## 1. Objective

Define the `experience_dimension_weights` subdocument of
`presentation_contract`. It explicitly weights which kinds of experience should
dominate the ideal CV for a given job and evaluator surface, and how those
weights shift by stakeholder persona.

This extends the seed six dimensions and aligns them with the repo's existing
grading rubric, CV generation guide, and achievement review language.

The artifact is candidate-agnostic: it describes preferred visibility, not
candidate truth.

## 2. Why This Artifact Exists

Today the system implicitly knows dimension salience through:

- `classification.primary_role_category`
- `jd_facts.extraction.competency_weights` and `weighting_profiles`
- CV grading rubric (`src/layer6_v2/prompts/grading_rubric.py`)
- hiring-manager guidance in `docs/current/cv-generation-guide.md`

It does not yet emit an explicit per-dimension weighting contract like:

- hands-on implementation: 25
- architecture and system design: 20
- leadership and enablement: 20
- business impact: 15
- ai/ml depth: 10
- platform/scaling/change: 10

That missing explicit weighting is why many generated CVs feel generically
"good" instead of intentionally shaped. The purpose of this subdocument is to
make shape explicit, auditable, and stakeholder-variable.

## 3. Stage Boundary

Co-produced inside `presentation_contract` (umbrella §5.3). Shared evidence
with 4.2.2, 4.2.4, 4.2.6. A deterministic validator normalizes dimension
names, enforces the allowed enum, and enforces sum-to-100.

## 4. Inputs

Required:

- `jd_facts` (merged view, especially `competency_weights`,
  `weighting_profiles`, `skill_dimension_profile`, `top_keywords`)
- `classification` (role family, tone family, seniority, AI taxonomy)
- `research_enrichment.role_profile` (mandate, business_impact,
  success_metrics, evaluation_signals)
- `stakeholder_surface` (per-persona CV preference surfaces)
- `pain_point_intelligence` (proof_map)
- `ideal_candidate_presentation_model` (same-run peer)

Priors to incorporate (non-authoritative but informative):

- ATS optimization importance
- impact / clarity importance
- JD alignment and pain-point coverage
- executive presence
- anti-hallucination constraints from the CV generation guide

## 5. Canonical Dimensions

The initial dimension enum is:

1. `hands_on_implementation`
2. `architecture_system_design`
3. `leadership_enablement`
4. `tools_technology_stack`
5. `methodology_operating_model`
6. `business_impact`
7. `stakeholder_communication`
8. `ai_ml_depth`
9. `domain_context`
10. `quality_risk_reliability`
11. `delivery_execution_pace`
12. `platform_scaling_change`

No other dimension names are allowed. If a new dimension is needed it must be
added to this enum in `blueprint_models.py`, bumped in the prompt version,
and documented.

## 6. Output Shape

```text
experience_dimension_weights {
  overall_weights: { <dimension>: int },          # sum to 100
  stakeholder_variant_weights {
    recruiter         : { <dimension>: int } | null,
    hiring_manager    : { <dimension>: int } | null,
    executive_sponsor : { <dimension>: int } | null,
    peer_reviewer     : { <dimension>: int } | null
  },                                              # each non-null map sums to 100
  minimum_visible_dimensions[],                   # dimensions that must be visible even if not top-weighted
  overuse_risks[],                                # dimensions that become risky if over-emphasized
  rationale,
  confidence: ConfidenceDoc,
  evidence[]
}
```

Rules:

- every key must be in the canonical dimension enum
- every non-null weight map sums to exactly 100 (deterministic validator)
- integer weights only (no floats)
- a dimension may be `0` but must still be present if it is in the enum and
  mentioned in `minimum_visible_dimensions` or `overuse_risks`
- `minimum_visible_dimensions` must be a subset of the enum
- `stakeholder_variant_weights` entries are emitted only for persona types
  present in the `stakeholder_surface` evaluator coverage target; others are
  `null`

## 7. Fail-Open / Fail-Closed

Fail open:

- if role-specific evidence is thin, use taxonomy / rubric priors by
  `classification.primary_role_category` and seniority, and record this in
  `rationale`

Fail closed:

- reject invalid sums (anything other than 100)
- reject dimensions outside the canonical enum
- reject impossible emphasis mixes that contradict role evidence (e.g.,
  `ai_ml_depth >= 30` for a role with `classification.ai_taxonomy.intensity
  = none` or `adjacent`)
- reject stakeholder variants for persona types not in the evaluator coverage
  target

## 8. Model and Execution

Primary: `gpt-5.4`.

Deterministic post-processing:

- normalize dimension names (slug-normalize, reject unknowns)
- enforce sum to 100 (error if off by any amount; do not auto-rescale silently)
- clamp or reject negative / null values
- cross-check `ai_ml_depth` against `classification.ai_taxonomy.intensity`
- cross-check `architecture_system_design` against JD scope signals
- cross-check `leadership_enablement` against seniority and `team_context`

If the LLM produces invalid sums, run one schema-repair retry with an explicit
error message. If it still fails, fall back to role-family default weights.

## 9. Prompt Constraints

Prompt rules:

- Weight by evaluator salience, not generic resume advice.
- Explain trade-offs in `rationale`, not just top scores.
- Do not assume the candidate already has those strengths; emit preferred
  visibility, not candidate truth.
- Per-stakeholder variants must diverge from `overall_weights` only where
  `stakeholder_surface` evidence justifies it.
- Use only the canonical dimension enum.

## 10. Expected Downstream Use

- skeleton section weighting
- achievement selection priors in later candidate-aware stages
- header and summary emphasis
- "what to front-load vs what to keep secondary" controls

## 11. Tests and Evals

Minimum tests:

- all weight maps sum to 100 exactly
- recruiter vs peer variants differ where JD/stakeholder evidence supports it
- high-AI roles elevate `ai_ml_depth`
- architecture-heavy roles elevate `architecture_system_design`
- delivery-heavy roles elevate `hands_on_implementation` and
  `business_impact`
- leadership roles elevate `leadership_enablement` and
  `stakeholder_communication`
- dimensions outside the enum are rejected
- stakeholder variants absent when evaluator coverage target excludes that
  persona type

Eval questions:

- does the weighting explain why some strong achievements should appear early
  and others later?
- does it align with the grading rubric and hiring-manager guidance already in
  the repo?
- does it diverge meaningfully from naive role-family priors when evidence
  supports it?

## 12. Primary Source Surfaces

- `docs/current/cv-generation-guide.md`
- `src/layer6_v2/prompts/grading_rubric.py`
- `docs/current/evals.md`
- `docs/current/achievement-review-tracker.yaml`
- `plans/brainstorming-new-cv-v2.md`
- `src/preenrich/blueprint_models.py` (`CompetencyWeightsModel`,
  `WeightingProfiles`, existing sum-to-100 validators)

Implementation surfaces:

- `presentation_contract` stage
- `ExperienceDimensionWeightsDoc` sub-model in
  `src/preenrich/blueprint_models.py`, with an `ExperienceDimension` enum and
  sum-to-100 validators similar to `ExpectationWeights`
- prompt additions in `src/preenrich/blueprint_prompts.py`
