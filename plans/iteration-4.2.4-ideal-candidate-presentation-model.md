# Iteration 4.2.4 Plan: Ideal Candidate Presentation Model

## 1. Objective

Define the `ideal_candidate_presentation_model` subdocument of
`presentation_contract`. This subdocument extends the existing
`jd_facts.extraction.ideal_candidate_profile` (the role-truth view) into a
**presentation-truth** view: how the ideal candidate should be framed on paper
for this specific evaluator surface.

It answers:

- what parts of the ideal candidate must be most visible in the CV
- what order of proof is preferred (proof ladder)
- what tone and framing are preferred
- what credibility markers must appear
- what title and identity framing are acceptable
- what risks exist if the CV over-claims or under-claims

It does not answer:

- what the candidate actually has (that is a later candidate-aware stage)
- exact header copy, summary copy, or bullet text

## 2. Why This Artifact Exists

`jd_facts.extraction.ideal_candidate_profile` (via `IdealCandidateProfileModel`
in `src/layer1_4/claude_jd_extractor.py`) already captures `archetype`,
`key_traits`, and `culture_signals`. That is role-truth only. It does not say:

- which parts should be front-loaded vs held back
- how identity should be framed without inflating the candidate
- what credibility ladder the document should follow
- how the evaluator (per `stakeholder_surface`) wants credibility established

This subdocument is the bridge between "role truth" and "CV skeleton truth",
and it is specifically evaluator-aware.

## 3. Stage Boundary

Co-produced inside the `presentation_contract` stage with 4.2.2, 4.2.5, and
4.2.6 (umbrella §5.3). Shared evidence, shared invalidation, one prompt context.

## 4. Inputs

Required:

- `jd_facts.extraction` / `merged_view` (particularly `ideal_candidate_profile`,
  `identity_signals`, `expectations`, `skill_dimension_profile`,
  `team_context`, `weighting_profiles`)
- `classification` (role family, tone family, seniority, AI taxonomy)
- `research_enrichment` (company_profile, role_profile)
- `stakeholder_surface` (CV preference surfaces, likely priorities, reject
  signals across real and inferred personas)
- `pain_point_intelligence` (proof_map)

Opportunistic:

- `job_inference.semantic_role_model`
- peer subdocument `document_expectations` when produced in the same run
  (allowed because they share one synthesis context)

## 5. Output Shape

```text
ideal_candidate_presentation_model {
  visible_identity,                   # short phrase describing who this person should look like on paper
  acceptable_titles[],                # bounded, evidence-safe title options
  title_strategy,                     # must match document_expectations.cv_shape.title_strategy
  must_signal[],                      # strongest evaluator-required signals
  should_signal[],                    # next-tier signals
  de_emphasize[],                     # things to downweight even if present
  proof_ladder[],                     # ordered: identity -> capability -> proof -> business outcome
  tone_profile {
    operator,                         # 0..1
    architect,                        # 0..1
    builder,                          # 0..1
    leader,                           # 0..1
    transformation,                   # 0..1
    platform,                         # 0..1
    execution                         # 0..1
  },
  framing_rules[],                    # short rule strings, candidate-agnostic
  credibility_markers[],              # what must appear to make the candidate believable
  risk_flags[],                       # over-claim / under-claim risks
  audience_variants {
    recruiter        { tilt[], must_see[] } | null,
    hiring_manager   { tilt[], must_see[] } | null,
    executive_sponsor{ tilt[], must_see[] } | null,
    peer_reviewer    { tilt[], must_see[] } | null
  },
  rationale,
  confidence: ConfidenceDoc,
  evidence[]                          # EvidenceEntry-style refs to upstream artifacts
}
```

### Suggested field semantics

- `visible_identity`: the fastest truthful answer to "who should this person
  look like on paper?" Must not inflate scope beyond the role evidence.
- `acceptable_titles[]`: bounded evidence-safe options. Must include the JD's
  `title` and may include one adjacent truthful framing per role family.
- `proof_ladder[]`: ordered category sequence, typically
  `identity -> capability -> proof -> business outcome`, adjusted for role
  family.
- `tone_profile`: float weights per dimension. The values are intensities,
  not sums; they do not need to sum to a fixed total.
- `credibility_markers[]`: evaluator-derived concrete signals, e.g.
  "named production system", "named scale marker", "named stakeholder scope".

## 6. Constraints Against Candidate Leakage

This subdocument is candidate-agnostic. It must not:

- reference a specific candidate's employers, years, or achievements
- assume the candidate has or lacks any particular experience
- contain first-person language or prescriptive prose

It must:

- describe what the role wants to see, not what any particular candidate can
  show
- keep all proof categories aligned with the
  `pain_point_intelligence.proof_map` proof-category enum
- keep title_strategy consistent with `document_expectations.cv_shape.title_strategy`

## 7. Fail-Open / Fail-Closed

Fail open:

- if research is partial, derive from `jd_facts` and `classification` with
  explicit lower confidence and a populated `rationale`
- if stakeholder coverage is incomplete, still emit core fields using
  role-family defaults and note unresolved audience variants as `null`

Fail closed:

- no candidate-specific assumptions
- no title inflation beyond role evidence (e.g., "VP" when JD and classification
  say "Lead")
- no "strategic visionary" / "rockstar" / "ninja" language
- no AI depth claims that exceed `classification.ai_taxonomy.intensity`
- no audience variants for persona types not present in `stakeholder_surface`
  evaluator coverage target

## 8. Model and Execution

Primary: `gpt-5.4`. Benchmark `gpt-5.2` if identity/title safety needs
tighter discipline.

Deterministic post-processing must enforce:

- title_strategy matches `document_expectations.cv_shape.title_strategy`
- proof_ladder uses only canonical proof-category enums
- audience_variants present only for persona types in the evaluator coverage
  target
- tone_profile values are clamped to `[0.0, 1.0]`

## 9. Prompt Constraints

Prompt rules:

- Describe the ideal candidate, not a real candidate.
- No assumptions about years of experience beyond what the JD evidence supports.
- No fabricated domain expertise or culture claims.
- No generic "rockstar" / "ninja" / "guru" framing.
- Every major recommendation grounded in JD, research, stakeholder, or pain
  evidence, cited in `evidence[]`.
- Do not emit header or summary prose.

## 10. Expected Downstream Use

- header/title generation (outside 4.2)
- section-level skeleton creation
- candidate match strategy in later phases
- reviewer UI explaining "what the ideal candidate should look like on paper"

## 11. Tests and Evals

Minimum tests:

- title_strategy bounded by role evidence and consistent with
  `document_expectations`
- proof_ladder always populated and enum-valid
- tone_profile consistent with role family and `classification.tone_family`
- audience_variants never contradict the core model
- no first-person or candidate-specific strings
- confidence degraded when research is partial

Eval questions:

- does the model explain how the role wants the candidate framed?
- does it avoid candidate leakage?
- does it remain useful when research is partial?
- does it stay internally consistent with `document_expectations` and
  `experience_dimension_weights` produced in the same run?

## 12. Primary Source Surfaces

- `src/preenrich/stages/jd_facts.py`
- `src/preenrich/blueprint_models.py`
- `src/layer1_4/claude_jd_extractor.py` (`IdealCandidateProfileModel`,
  `CandidateArchetype`)
- `src/preenrich/stages/job_inference.py`
- `src/preenrich/stages/research_enrichment.py`
- `docs/current/cv-generation-guide.md`
- `plans/brainstorming-new-cv-v2.md`

Implementation surfaces:

- `presentation_contract` stage
- `IdealCandidatePresentationModel` sub-model in
  `src/preenrich/blueprint_models.py`
- prompt additions in `src/preenrich/blueprint_prompts.py`
