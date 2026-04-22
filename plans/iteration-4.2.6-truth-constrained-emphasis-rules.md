# Iteration 4.2.6 Plan: Truth-Constrained Emphasis Rules

## 1. Objective

Define the `truth_constrained_emphasis_rules` subdocument of
`presentation_contract`. It is the guardrail layer that tells later
candidate-aware CV generation:

- what may be emphasized only if later candidate evidence exists
- what must be softened even if the job wants it
- what title or identity framing becomes unsafe without direct proof
- how the proof ladder should degrade gracefully under imperfect evidence

This subdocument keeps the pre-candidate skeleton useful without turning into
fantasy. It is policy, not prose.

## 2. Why This Artifact Exists

The repo already has strong anti-hallucination and ATS guidance, but 4.2 needs
a dedicated pre-candidate rule layer that is:

- structured (not free-text guidance)
- actionable by a later deterministic enforcer
- aligned to the canonical section ids, proof categories, and dimension enum
  used by 4.2.2, 4.2.4, and 4.2.5
- evaluator-aware (shaped by `stakeholder_surface` reject signals)

Without this, a later skeleton will overfit the job description and
under-constrain the truth.

## 3. Stage Boundary

Co-produced inside `presentation_contract` with 4.2.2, 4.2.4, and 4.2.5
(umbrella §5.3). All four subdocuments must pass cross-validation before the
artifact is persisted; a failure in any one fails the run.

## 4. Inputs

Required:

- `jd_facts` (merged view)
- `classification` (role family, tone family, seniority, AI taxonomy)
- `research_enrichment` (company_profile, role_profile)
- `stakeholder_surface` (likely reject signals across real and inferred
  personas)
- `pain_point_intelligence` (proof_map, bad_proof_patterns)
- `document_expectations` (same-run peer: section ids, ai_section_policy,
  title_strategy)
- `ideal_candidate_presentation_model` (same-run peer: proof ladder,
  acceptable titles, risk flags)
- `experience_dimension_weights` (same-run peer: canonical dimension enum)

Useful later consumer (not a dependency):

- candidate evidence store / master CV matching in future phases

## 5. Output Shape

```text
truth_constrained_emphasis_rules {
  global_rules[],                                 # Rule[]
  section_rules {
    title: Rule[],
    header: Rule[],
    summary: Rule[],
    key_achievements: Rule[],
    core_competencies: Rule[],
    ai_highlights: Rule[],
    experience: Rule[]
  },
  allowed_if_evidenced[],                         # Rule[]
  downgrade_rules[],                              # Rule[]
  omit_rules[],                                   # Rule[]
  forbidden_claim_patterns[],                     # Rule[] (string pattern + reason)
  credibility_ladder_rules[],                     # Rule[]
  confidence: ConfidenceDoc,
  evidence[]
}
```

Rule shape:

```text
Rule {
  rule_id,                                        # stable slug
  rule_type,                                      # enum (see §5.1)
  applies_to,                                     # section id or dimension or proof category
  condition,                                      # human-readable condition string
  action,                                         # what a later generator should do
  basis,                                          # short rationale
  source_refs[],                                  # upstream-artifact refs
  confidence: ConfidenceDoc
}
```

### 5.1 Rule type enum

- `allowed_if_evidenced`          — claim is permitted only if candidate evidence supports it
- `prefer_softened_form`          — claim is permitted but must be phrased conservatively
- `omit_if_weak`                  — claim must be omitted when evidence is weak
- `forbid_without_direct_proof`   — claim is forbidden absent direct evidence
- `never_infer_from_job_only`     — claim cannot be constructed from JD inference alone
- `cap_dimension_weight`          — deterministic cap on dimension weight absent evidence
- `require_credibility_marker`    — section requires at least one credibility marker

### 5.2 Applies-to enum

Must reference:

- canonical section ids from 4.2.2
- canonical proof-category enum from 4.2.3 / 4.2.2
- canonical dimension enum from 4.2.5
- or the string `global`

## 6. Rule Topics Coverage

The rule set must cover at least:

- title inflation (title_strategy enforcement)
- AI claims without real evidence (gated on `ai_section_policy` and
  `classification.ai_taxonomy.intensity`)
- leadership framing without scope evidence (gated on seniority,
  `team_context`, and `leadership_enablement` weight)
- architecture claims without system-level proof
- domain expertise claims without direct signal
- stakeholder-management claims without outcome evidence
- vague keyword stuffing without proof
- metric / scale statements requiring a direct source truth
- credibility-ladder degradation path when evidence is thin

Each topic must have at least one rule, with `rule_id` stable across runs for
the same job inputs.

## 7. Fail-Open / Fail-Closed

Fail open:

- when evidence conditions are unknown, default to conservative wording and
  explicit omission rules
- when a topic lacks evaluator signal, emit a neutral `allowed_if_evidenced`
  rule rather than no rule

Fail closed:

- no rule may authorize unsupported title inflation
- no rule may authorize unsupported AI expertise claims
- no rule may authorize unsupported strategic leadership claims
- no rule may authorize fabricated metrics
- no rule may treat inferred stakeholder preference as candidate strength

## 8. Cross-Subdocument Consistency

A deterministic validator must enforce:

- every `applies_to` references a valid section id, proof category, dimension,
  or `global`
- `title` section rules are consistent with
  `document_expectations.cv_shape.title_strategy` and
  `ideal_candidate_presentation_model.acceptable_titles`
- `ai_highlights` section rules are consistent with
  `document_expectations.cv_shape.ai_section_policy` and
  `classification.ai_taxonomy.intensity`
- `cap_dimension_weight` rules reference dimensions from the canonical enum
- forbidden_claim_patterns do not contradict `document_expectations.proof_order`

If any cross-consistency check fails, the entire `presentation_contract` run
fails and falls back to role-family defaults.

## 9. Model and Execution

Primary: `gpt-5.4`.

Deterministic validation enforces:

- allowed rule_type values only
- no candidate-specific assertions
- no references to private, future, or speculative evidence
- unique rule_id values
- required topic coverage (see §6)

## 10. Prompt Constraints

Prompt rules:

- Produce policy, not prose.
- Every rule must be actionable by a later generator or deterministic enforcer.
- Every risky emphasis must have a matching downgrade or omission path.
- Later candidate matching is assumed but not available yet; rules are
  conditional on evidence state.
- Unresolved evidence should push toward conservative emphasis, not empty
  output.
- Use only the canonical section id, proof-category, and dimension enums.

## 11. Expected Downstream Use

- candidate-aware CV generation guardrails
- title and header safety checks
- AI highlight eligibility gating
- competency and bullet selection rules
- repair / verifier loops in future generation stages
- reviewer UI showing "what this CV must not claim"

## 12. Tests and Evals

Minimum tests:

- forbidden_claim_patterns populated for risky role families (AI-heavy,
  architecture-heavy, leadership-heavy)
- AI-heavy roles still require evidence gating regardless of JD enthusiasm
- title rules prevent inflation beyond role evidence
- omission and downgrade rules exist for unsupported strategic claims
- cross-subdocument consistency enforced (title_strategy, ai_section_policy,
  dimension enum)
- rule_id uniqueness
- `applies_to` references valid enum values only

Eval questions:

- do the rules materially reduce hallucination risk?
- are the rules specific enough to drive later generation behavior?
- do they still allow strong positioning when evidence exists?
- are they internally consistent with the other three subdocuments?

## 13. Primary Source Surfaces

- `src/layer6_v2/prompts/grading_rubric.py`
- `docs/current/cv-generation-guide.md`
- `docs/current/outreach-detection-principles.md`
- `src/preenrich/stages/jd_facts.py`
- `src/preenrich/stages/research_enrichment.py`
- `plans/brainstorming-new-cv-v2.md`

Implementation surfaces:

- `presentation_contract` stage
- `TruthConstrainedEmphasisRulesDoc` and `Rule` sub-models in
  `src/preenrich/blueprint_models.py`
- prompt additions in `src/preenrich/blueprint_prompts.py`
