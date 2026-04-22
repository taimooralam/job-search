# CV Quality Fixes 3B + 4D

**Date:** 2026-04-12
**Scope:** Planning only. No code changes in this document.

## Task 1: 4D — Negative Scoring Integration

### What the code does today

- Tiering happens in [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:706) through [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:715).
- Current thresholds come from [src/common/tiering.py](/Users/ala0001t/pers/projects/job-search/src/common/tiering.py:135):
  - `>= 85` => `GOLD`
  - `>= 70` => `SILVER`
  - `>= 50` => `BRONZE`
  - `< 50` => `SKIP`
- The CV pipeline state is built from the MongoDB job document in [src/services/cv_generation_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_generation_service.py:368), with the current state payload assembled at [src/services/cv_generation_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_generation_service.py:393).
- Today `_build_state()` carries `extracted_jd`, `fit_score`, `fit_rationale`, and `location`, but not the scout rule-score breakdown.
- The rule scorer currently stores penalties as negative values in the returned `breakdown` object in [src/common/rule_scorer.py](/Users/ala0001t/pers/projects/job-search/src/common/rule_scorer.py:938). Specifically:
  - `jdNegativeHard`: `-jd_hard_penalty`
  - `experienceMismatch`: `-experience_penalty`
- Scout ingestion is not fully uniform:
  - raw scout outputs write top-level `breakdown` in [scripts/scout_linkedin_jobs.py](/Users/ala0001t/pers/projects/job-search/scripts/scout_linkedin_jobs.py:383) and [scripts/scout_scraper_cron.py](/Users/ala0001t/pers/projects/job-search/scripts/scout_scraper_cron.py:197)
  - insertion paths also mirror it into `linkedin_metadata.rule_score_breakdown` in [scripts/scout_selector_cron.py](/Users/ala0001t/pers/projects/job-search/scripts/scout_selector_cron.py:322) and [scripts/scout_dimensional_selector.py](/Users/ala0001t/pers/projects/job-search/scripts/scout_dimensional_selector.py:262)

### Exact files and line numbers to modify

1. [src/services/cv_generation_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_generation_service.py:383)
   Current state assembly at lines `383-407`.
2. [src/common/state.py](/Users/ala0001t/pers/projects/job-search/src/common/state.py:284)
   JobState fit/tier section at lines `284-289`.
3. [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:706)
   Tier determination block at lines `706-715`.

### Specific code changes

#### 1. Carry the scout breakdown into pipeline state

Modify [src/services/cv_generation_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_generation_service.py:383).

Add a normalization step before the `state = { ... }` dict:

```python
score_breakdown = (
    job.get("score_breakdown")
    or job.get("breakdown")
    or (job.get("linkedin_metadata") or {}).get("rule_score_breakdown")
    or {}
)
```

Then include it in the state dict:

```python
"score_breakdown": score_breakdown,
```

Reason: this is the narrowest place where MongoDB job shape becomes pipeline state. It avoids teaching the orchestrator about multiple storage variants.

#### 2. Extend the state contract

Modify [src/common/state.py](/Users/ala0001t/pers/projects/job-search/src/common/state.py:284).

Add one optional field near `fit_score` and `tier`:

```python
score_breakdown: Optional[Dict[str, Any]]  # Scout rule-score penalty/bonus breakdown from MongoDB
```

Reason: `JobState` is a TypedDict used as the shared contract, and this field is now part of generator routing.

#### 3. Add a BRONZE cap based on negative scout penalties

Modify [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:706).

Recommended implementation shape:

- Add a small private helper above the main generation flow, near other module helpers or as a `CVGeneratorV2` private method:

```python
def _penalty_magnitude(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return abs(number) if number < 0 else number
```

- In the tier block, replace the current direct call with:

```python
fit_score = state.get("fit_score")
score_breakdown = state.get("score_breakdown") or {}

base_tier = get_tier_from_fit_score(fit_score)
jd_negative_hard = _penalty_magnitude(score_breakdown.get("jdNegativeHard"))
experience_mismatch = _penalty_magnitude(score_breakdown.get("experienceMismatch"))

force_bronze = (
    jd_negative_hard > 20
    or experience_mismatch > 15
)

tier = base_tier
if force_bronze and base_tier in [ProcessingTier.GOLD, ProcessingTier.SILVER]:
    tier = ProcessingTier.BRONZE
```

- Log the downgrade with the actual values:

```python
self._logger.info(
    "  Downgrading tier from %s to bronze due to scout penalties "
    "(jdNegativeHard=%s, experienceMismatch=%s)",
    base_tier.value,
    jd_negative_hard,
    experience_mismatch,
)
```

#### Threshold interpretation

- Use the product requirement as magnitude thresholds:
  - `jdNegativeHard > 20`
  - `experienceMismatch > 15`
- Do not compare directly to `< -20` and `< -15` in orchestrator code, because the storage shape may drift between signed penalties and positive magnitudes.
- Normalize once, then compare using the positive thresholds from the requirement.

#### Tier behavior nuance

- This should be a cap to `BRONZE`, not a forced overwrite in every case.
- If `fit_score` already yields `SKIP`, keep `SKIP`.
- If `fit_score` yields `BRONZE`, keep `BRONZE`.
- Only expensive tiers `GOLD` and `SILVER` should be downgraded.

### What to test

1. `tests/unit/services/test_cv_generation_service.py`
   Add `_build_state()` coverage for:
   - top-level `breakdown`
   - top-level `score_breakdown`
   - nested `linkedin_metadata.rule_score_breakdown`
   - missing breakdown => `{}` fallback

2. `tests/unit/test_layer6_v2_orchestrator.py`
   Add tier-routing tests for:
   - `fit_score=90`, no breakdown => `GOLD` path still uses ensemble
   - `fit_score=90`, `jdNegativeHard=-25` => capped to `BRONZE`, single-shot path
   - `fit_score=75`, `experienceMismatch=-16` => capped to `BRONZE`
   - `fit_score=40`, penalty present => remains `SKIP`, not promoted to `BRONZE`
   - positive stored magnitudes (`25`, `16`) also trigger the same downgrade

3. Optional integration check
   Run `pytest tests/unit/services/test_cv_generation_service.py tests/unit/test_layer6_v2_orchestrator.py`

### Risk assessment

- Low implementation risk: the change is local and does not alter prompt formats.
- Medium schema risk: scout documents are not uniform, so missing the nested metadata fallback would cause silent non-application on older jobs.
- Medium behavioral risk: if the code overwrites `SKIP` with `BRONZE`, token usage would go up on low-fit jobs. The implementation should explicitly avoid that.
- Low observability risk if logging is added. Without a downgrade log line, diagnosing why a `GOLD`-fit job ran single-shot will be harder.

---

## Task 2: 3B — Structured Review Taxonomy

### What the code does today

- The reviewer prompt schema is defined in [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:32).
- The output JSON shape is documented in the system prompt at [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:100).
- The service fetches the job and current CV in [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:367).
- The parsed LLM review is persisted into `cv_review` in [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:548).
- Current stored top-level fields are:
  - `reviewed_at`
  - `model`
  - `reviewer`
  - `verdict`
  - `would_interview`
  - `confidence`
  - `first_impression_score`
  - `full_review`
- The nested `full_review` already includes the signals needed to derive taxonomy:
  - `top_third_assessment`
  - `pain_point_alignment`
  - `hallucination_flags`
  - `ats_assessment`
  - `strengths`
  - `weaknesses`
  - `ideal_candidate_fit`

### Exact files and line numbers to modify

1. [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:32)
   System prompt schema at lines `32-177`.
2. [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:514)
   Parsed-review handling and post-processing at lines `514-568`.

### Specific code changes

#### 1. Expand the reviewer schema so the single response contains explicit structured cues

Modify the JSON schema inside `REVIEWER_SYSTEM_PROMPT` in [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:100).

Recommended additions are inside existing nested sections, not as final persisted top-level document fields. That keeps the prompt aligned with the user requirement that the stored taxonomy is derived from the single review response.

Add these nested fields:

```json
"top_third_assessment": {
  "headline_verdict": "...",
  "headline_evidence_bounded": true,
  "tagline_verdict": "...",
  "tagline_proof_gap": true,
  "achievements_verdict": "...",
  "competencies_verdict": "...",
  "bridge_quality_score": 1,
  "first_impression_score": 1,
  "first_impression_summary": "..."
},
"pain_point_alignment": {
  "addressed": [],
  "missing": [],
  "coverage_ratio": 0.0,
  "low_pain_point_coverage": false
},
"ats_assessment": {
  "keyword_coverage": "...",
  "missing_critical_keywords": [],
  "acronym_issues": [],
  "ats_survival_likely": true,
  "thin_competencies": false
},
"ideal_candidate_fit": {
  "archetype_match": "...",
  "trait_coverage": {"present": [], "missing": []},
  "experience_level_match": "...",
  "missing_ai_evidence": false
}
```

Also add one short instruction block after the output schema:

- `headline_evidence_bounded` should be `false` when the headline overstates role identity, seniority, or specialization relative to the source evidence.
- `tagline_proof_gap` should be `true` when the tagline makes claims without enough proof in the CV or master CV.
- `bridge_quality_score` should rate how well the top third connects identity -> proof -> pain-point relevance.
- `thin_competencies` should be `true` when the competencies section is too sparse or too generic for ATS and hiring-manager confidence.
- `missing_ai_evidence` should be `true` when the JD clearly asks for AI/LLM/GenAI depth and the CV does not provide convincing proof.
- `low_pain_point_coverage` should be `true` when the CV misses a material portion of the JD pain points.

Reason: this keeps the service single-call while making downstream derivation deterministic.

#### 2. Add server-side derivation helpers after JSON parse

Modify [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:514).

Add small pure helpers in the class or module:

```python
def _normalize_text_list(values: Any) -> List[str]: ...
def _contains_any(text: str, phrases: List[str]) -> bool: ...
def _derive_failure_modes(review: Dict[str, Any], extracted_jd: Dict[str, Any]) -> List[str]: ...
def _derive_headline_evidence_bounded(review: Dict[str, Any]) -> bool: ...
def _derive_bridge_quality_score(review: Dict[str, Any]) -> int: ...
```

Recommended derivation rules:

- `headline_overclaim`
  - true if `top_third_assessment.headline_evidence_bounded` is `false`
  - or `headline_verdict` / `weaknesses` contain cues like `overclaim`, `inflated`, `mismatch`, `not supported`, `too senior`

- `tagline_proof_gap`
  - true if `top_third_assessment.tagline_proof_gap` is `true`
  - or `tagline_verdict` / `weaknesses` mention `proof`, `claims`, `generic`, `unsupported`

- `missing_ai_evidence`
  - true if `ideal_candidate_fit.missing_ai_evidence` is `true`
  - or the JD clearly contains AI markers and the review says the CV lacks proof
  - AI markers can be read from `extracted_jd.top_keywords`, `technical_skills`, and `title`
  - match terms like `ai`, `genai`, `llm`, `ml`, `machine learning`, `rag`

- `hallucination_project_context`
  - true if any `hallucination_flags` exist for project-specific claims or unsupported project context
  - especially when claim text includes `commander`, `lantern`, `project`, `not found in master cv`

- `thin_competencies`
  - true if `ats_assessment.thin_competencies` is `true`
  - or `competencies_verdict` / `weaknesses` mention sparse, thin, generic, not enough keywords
  - or `missing_critical_keywords` length crosses a small threshold such as `>= 3`

- `low_pain_point_coverage`
  - true if `pain_point_alignment.low_pain_point_coverage` is `true`
  - or `coverage_ratio < 0.5`
  - or `pain_point_alignment.missing` materially exceeds `addressed`

#### 3. Derive `headline_evidence_bounded` server-side as the canonical stored value

Use:

```python
headline_evidence_bounded = _derive_headline_evidence_bounded(review)
```

Priority:

1. Use explicit nested boolean if present.
2. Otherwise infer from `headline_verdict`, `weaknesses`, and `hallucination_flags`.
3. Default to `True` only if there are no overclaim signals.

#### 4. Derive `bridge_quality_score` server-side as the canonical stored value

Use:

```python
bridge_quality_score = _derive_bridge_quality_score(review)
```

Recommended rule:

1. If the nested `top_third_assessment.bridge_quality_score` exists and is numeric, clamp it to `1..10` and use it.
2. Otherwise compute a fallback from existing fields:
   - start from `first_impression_score`
   - adjust down for `tagline_proof_gap`, `headline_overclaim`, hallucination flags, and low pain-point coverage
   - clamp to `1..10`

This preserves operability even while older reviews exist or the model occasionally omits the new field.

#### 5. Store the new top-level taxonomy fields on `cv_review`

Extend the `cv_review` dict in [src/services/cv_review_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_review_service.py:551) with:

```python
"failure_modes": failure_modes,
"headline_evidence_bounded": headline_evidence_bounded,
"bridge_quality_score": bridge_quality_score,
```

Resulting stored shape:

```python
cv_review = {
    "reviewed_at": ...,
    "model": ...,
    "reviewer": ...,
    "verdict": ...,
    "would_interview": ...,
    "confidence": ...,
    "first_impression_score": ...,
    "failure_modes": [...],
    "headline_evidence_bounded": True,
    "bridge_quality_score": 7,
    "full_review": review,
}
```

### What to test

1. Add unit tests for derivation helpers in a new file:
   - `tests/unit/services/test_cv_review_service.py`

2. Cover these cases:
   - headline overclaim in `headline_verdict` => `failure_modes` contains `headline_overclaim`, bounded=false
   - tagline lacks proof => `tagline_proof_gap`
   - AI-heavy JD plus weak proof => `missing_ai_evidence`
   - project hallucination flag mentioning Commander-4/Lantern => `hallucination_project_context`
   - sparse competencies / many missing keywords => `thin_competencies`
   - `coverage_ratio < 0.5` => `low_pain_point_coverage`
   - explicit nested booleans from the model override text heuristics
   - `bridge_quality_score` clamps into `1..10` and falls back correctly when omitted

3. Add one persistence-shape test:
   - mock a review payload and verify `cv_review` written to Mongo includes the three new top-level fields while preserving `full_review`

4. Recommended test command:
   - `pytest tests/unit/services/test_cv_review_service.py`

### Risk assessment

- Low schema risk: MongoDB accepts additive fields on `cv_review`.
- Medium consistency risk: if taxonomy is derived from free text only, classification will drift. The prompt additions above reduce that risk by asking the model for structured nested booleans in the same response.
- Low runtime risk: no second LLM call is required.
- Medium backfill risk: existing stored `cv_review` documents will not have the new fields until re-reviewed or migrated.
- Low product risk: storing canonical top-level enums makes downstream filtering simpler without removing the original `full_review`.

---

## Recommended implementation order

1. Task 1 first.
   It is smaller, isolated, and reduces unnecessary expensive generation immediately.
2. Task 2 second.
   It benefits from a dedicated helper-test file and can ship independently of CV generation.

## Minimal test pass before merge

- `pytest tests/unit/services/test_cv_generation_service.py tests/unit/test_layer6_v2_orchestrator.py tests/unit/services/test_cv_review_service.py`
