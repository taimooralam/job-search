# 2E Sub-Plan: Identity-Bridge Grading Gate

## Context

The 24-hour review diagnostic exposed a grading blind spot in the current Layer 6 pipeline:

- 63% of reviewed CVs landed in `WEAK_MATCH`, 31% in `NEEDS_WORK`, and only 5% in `GOOD_MATCH`.
- Review feedback clusters around the top third of the document, not bullet quality alone:
  - headlines over-claim AI/architect identity,
  - taglines assert AI specialization without proof,
  - key achievements and competencies do not bridge verified identity to job-relevant impact.
- The candidate's verified center of gravity is `Engineering Leader / Software Architect` with grounded AI platform evidence from Commander-4/Joyia and Lantern. The current grader has no dimension that explicitly checks whether the header, tagline, AI highlights, and top-third competencies tell that story credibly.

Expected impact of 2E: reduce false-positive "good" scores on over-positioned CVs, surface top-third credibility issues earlier in improvement, and raise `GOOD_MATCH` rate by forcing the system to reward evidence-bounded positioning rather than keyword-heavy overclaiming.

## Current Architecture Findings

### Grader

- [src/layer6_v2/grader.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:58) defines one global `DIMENSION_WEIGHTS` dict with 5 dimensions.
- Rule-based scoring methods:
  - ATS: [_grade_ats_optimization()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:243)
  - Impact: [_grade_impact_clarity()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:308)
  - JD alignment: [_grade_jd_alignment()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:351)
  - Executive presence: [_grade_executive_presence()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:409)
  - Anti-hallucination: [_grade_anti_hallucination()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:545)
- LLM grading schema is fixed to 5 fields in `GradingResponse` at [grader.py:49-56](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:49).
- The live LLM prompt is hardcoded in [_grade_with_llm_inner()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:655), not loaded from `prompts/grading_rubric.py`.
- `category_keywords` for role-conditional JD alignment live inside [_grade_jd_alignment()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:377-387). This is the only existing role-conditional grading behavior.
- Passing threshold defaults to `8.5` in [CVGrader.__init__()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:82-116) and is applied when `GradeResult` is instantiated in [grader.py:897-902](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:897).
- There is no `_compute_composite_score()` method in `grader.py`. Composite scoring currently happens in `GradeResult.__post_init__`.

### Types

- `DimensionScore` is already dynamic and does not hardcode dimension names: [src/layer6_v2/types.py:1997-2026](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1997).
- `GradeResult` stores `dimension_scores: List[DimensionScore]` and computes `composite_score` as `sum(d.weighted_score ...)` in [types.py:2051-2061](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:2051).
- That means variable dimension count is already structurally supported if weights sum to 1.0.

### Prompt Module

- `src/layer6_v2/prompts/grading_rubric.py` still documents only 5 dimensions at [grading_rubric.py:9-58](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/grading_rubric.py:9).
- `DIMENSION_DESCRIPTIONS` is also fixed to 5 dimensions at [grading_rubric.py:177-224](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/grading_rubric.py:177).
- Search shows no runtime import of this rubric module. It is currently documentation/UI-only, not the active grading prompt source.

### Improver

- Improver selects the dimension dynamically via `grade_result.lowest_dimension` in [src/layer6_v2/improver.py:506-535](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/improver.py:506).
- It reads dimension details through `grade_result.get_dimension()` in [_build_improvement_prompt()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/improver.py:178) and in improvement logging paths.
- Compatibility gap: `IMPROVEMENT_STRATEGIES` only defines the current 5 dimensions in [improver.py:56-102](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/improver.py:56). A sixth dimension will not crash, but it will degrade to the generic fallback strategy.

### Orchestrator

- Orchestrator instantiates the grader with the global `passing_threshold` in [src/layer6_v2/orchestrator.py:320-325](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:320).
- AI role override happens before grading:
  - leadership AI jobs -> `ai_leadership`
  - non-leadership AI jobs -> `ai_architect`
  - see [orchestrator.py:481-509](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:481).
- Grading happens once in [orchestrator.py:870-881](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:870).
- There is one optional improvement pass in [orchestrator.py:908-945](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:908).
- There is no re-grade after improvement. Final logs and reasoning still use the original `grade_result`.
- The top third is assembled in [_assemble_cv_text()](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1608):
  - headline line: [1651-1655](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1651)
  - summary/tagline: [1676-1688](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1676)
  - key achievements: [1690-1694](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1690)
  - core competencies: [1696-1708](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1696)
  - AI project section for AI jobs: [1710-1724](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1710)

### Tests

- Main grading/improver coverage is in [tests/unit/test_layer6_v2_grader_improver.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_grader_improver.py:1).
- Existing tests assume 5 dimensions explicitly:
  - full rule-based grade: [414](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_grader_improver.py:414)
  - mocked LLM grade: [454](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_grader_improver.py:454)
  - fallback grade: [468](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_grader_improver.py:468)
  - convenience function: [571](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_grader_improver.py:571)
  - edge cases: [597, 615](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_grader_improver.py:597)
- Orchestrator fixtures also hardcode 5 dimensions in [tests/unit/test_layer6_v2_orchestrator.py:293-302](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_orchestrator.py:293) and [419-428](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_orchestrator.py:419).

## Architecture Decisions

### 1. Identity-Bridge grading mode

Decision: `Option C`, hybrid grading.

- LLM should own the final `identity_bridge` score because coherence across headline, tagline, achievements, and competencies is a semantic judgment, not just a regex problem.
- Code should provide deterministic guardrails and evidence features so the LLM is grading from grounded signals, not free-form intuition.
- Recommended pattern:
  - Add `_extract_identity_bridge_evidence()` in `grader.py`.
  - Feed those evidence features into the LLM prompt.
  - Add a rule-based fallback `_grade_identity_bridge()` for when LLM grading fails.

Why not pure LLM:

- The exact failure modes here are repetitive and detectable:
  - headline mirrors JD title,
  - AI title appears without AI proof terms,
  - AI job lacks AI project/highlight section,
  - competencies include terms absent from the CV body or master CV.
- Those are cheaper and more reliable as code checks.

Why not pure code:

- "Credible bridge" also depends on how the parts work together. A tagline can be technically grounded and still fail as positioning. That requires semantic evaluation.

### 2. Weight strategy

Decision: `Option A`, explicit per-role weight tables resolved inside the grader.

- Add named weight profiles keyed by `role_category`.
- Use `role_category` already passed in `extracted_jd`.
- Keep weight resolution inside the grader so callers do not need to understand scoring internals.

Why not multipliers:

- Harder to reason about and harder to test because the final normalized weights become indirect.

Why not pass-in weights from callers:

- Spreads grading policy into orchestrator and tests unnecessarily.

### 3. Threshold strategy

Decision: keep `8.5` for default roles, introduce `8.3` for `ai_architect`, keep `8.5` for `ai_leadership`.

Rationale:

- Architect CVs are currently failing mostly on top-third identity bridge, which this change will intentionally score more harshly during rollout.
- Dropping from `8.5` to `8.3` for `ai_architect` avoids turning the new gate into a blunt traffic jam while prompts and improver tactics catch up.
- `ai_leadership` should stay at `8.5` because executive credibility is already a higher bar and the new dimension is aligned with that expectation.

## Identity-Bridge Scoring Rubric

The dimension should judge four sub-signals, all from the top third of the CV:

1. Headline truthfulness
   - Uses a role-appropriate title without claiming unearned specialization.
   - Good: `AI Platform Architect | Engineering Leader` when the CV contains platform architecture and verified AI platform evidence.
   - Bad: `AI Architect` when the evidence is limited to one project mention and the rest of the CV reads as general engineering leadership.

2. Tagline proof ladder
   - Starts from verified identity.
   - Extends to JD-relevant capability.
   - Anchors that extension in evidence or outcome.
   - Good: `Software architect and engineering leader who built enterprise AI platforms serving 2,000 users and production LLM gateway capabilities.`
   - Bad: `AI visionary architect driving next-generation LLM transformation across enterprises.`

3. Top-third evidence mix
   - Key achievements include at least one architecture/platform proof point.
   - For AI-targeted roles, top-third also includes at least one AI/LLM/platform proof point.

4. Competency grounding
   - Core competencies match the JD only where those terms are reflected in achievements, experience, or verified projects.

Suggested 1-10 interpretation:

- `9-10`: Headline is evidence-bounded, tagline contains a clear proof ladder, top third includes both architecture and AI proof where relevant, competencies are tightly grounded.
- `7-8`: Mostly credible; minor overreach or weak proof density, but the story still holds.
- `5-6`: Mixed; identity is directionally right but proof is partial, vague, or uneven.
- `3-4`: Over-positioned or generic; claims outrun evidence, especially in headline/tagline.
- `1-2`: Identity is materially misleading, AI specialization is asserted without proof, or top third lacks a coherent bridge entirely.

## Weight Tables

### Before

| Role profile | ATS | Impact | JD Align | Exec | Anti-Hallucination | Identity-Bridge | Threshold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All roles today | 20% | 25% | 25% | 15% | 15% | 0% | 8.5 |

### After

| Role profile | ATS | Impact | JD Align | Exec | Anti-Hallucination | Identity-Bridge | Threshold |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Default roles | 20% | 25% | 25% | 15% | 15% | 0% | 8.5 |
| AI architect | 15% | 20% | 22% | 13% | 20% | 10% | 8.3 |
| AI leadership | 15% | 17% | 20% | 18% | 20% | 10% | 8.5 |

Notes:

- Default roles remain unchanged to avoid unnecessary regression.
- `ai_architect` emphasizes grounding and bridge quality over executive polish.
- `ai_leadership` keeps executive presence more important than `ai_architect` but still introduces the same bridge gate.

## Data Structure Changes

### `src/layer6_v2/types.py`

Current `DimensionScore` at [types.py:1997-2026](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1997) already supports arbitrary dimension names. No field addition is required for the sixth dimension.

Current `GradeResult` at [types.py:2030-2085](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:2030) also supports variable-length dimensions, but it should gain a weight-sum guard.

### Before

```python
@dataclass
class GradeResult:
    dimension_scores: List[DimensionScore]
    composite_score: float = 0.0
    passed: bool = False
    passing_threshold: float = 8.5
    lowest_dimension: str = ""
    improvement_priority: List[str] = field(default_factory=list)
    exemplary_sections: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.dimension_scores and self.composite_score == 0.0:
            self.composite_score = sum(d.weighted_score for d in self.dimension_scores)
            self.passed = self.composite_score >= self.passing_threshold
```

### After

```python
@dataclass
class GradeResult:
    dimension_scores: List[DimensionScore]
    composite_score: float = 0.0
    passed: bool = False
    passing_threshold: float = 8.5
    lowest_dimension: str = ""
    improvement_priority: List[str] = field(default_factory=list)
    exemplary_sections: List[str] = field(default_factory=list)
    role_category: str = ""
    weight_profile: str = "default"

    def __post_init__(self):
        if self.dimension_scores and self.composite_score == 0.0:
            total_weight = sum(d.weight for d in self.dimension_scores)
            if total_weight <= 0:
                raise ValueError("GradeResult requires positive total weight")
            self.composite_score = sum(d.weighted_score for d in self.dimension_scores) / total_weight
            self.passed = self.composite_score >= self.passing_threshold
```

Notes:

- Normalizing by `total_weight` makes the composite robust even if a profile is misconfigured temporarily.
- `role_category` and `weight_profile` are optional but useful for logging, debugging, and future analytics.

### LLM response schema changes in `src/layer6_v2/grader.py`

Current at [grader.py:41-56](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:41):

```python
class GradingResponse(BaseModel):
    ats_optimization: DimensionGrade
    impact_clarity: DimensionGrade
    jd_alignment: DimensionGrade
    executive_presence: DimensionGrade
    anti_hallucination: DimensionGrade
    exemplary_sections: List[str] = Field(default_factory=list)
```

After:

```python
class GradingResponse(BaseModel):
    ats_optimization: DimensionGrade
    impact_clarity: DimensionGrade
    jd_alignment: DimensionGrade
    executive_presence: DimensionGrade
    anti_hallucination: DimensionGrade
    identity_bridge: Optional[DimensionGrade] = None
    exemplary_sections: List[str] = Field(default_factory=list)
```

Use `Optional` so default-role prompts can omit the field while AI profiles require it.

## Grader Code Changes

### 1. Add explicit weight profiles

File: [src/layer6_v2/grader.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:58)

Replace current single `DIMENSION_WEIGHTS` block at [58-65](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:58) with:

```python
WEIGHT_PROFILES = {
    "default": {
        "ats_optimization": 0.20,
        "impact_clarity": 0.25,
        "jd_alignment": 0.25,
        "executive_presence": 0.15,
        "anti_hallucination": 0.15,
    },
    "ai_architect": {
        "ats_optimization": 0.15,
        "impact_clarity": 0.20,
        "jd_alignment": 0.22,
        "executive_presence": 0.13,
        "anti_hallucination": 0.20,
        "identity_bridge": 0.10,
    },
    "ai_leadership": {
        "ats_optimization": 0.15,
        "impact_clarity": 0.17,
        "jd_alignment": 0.20,
        "executive_presence": 0.18,
        "anti_hallucination": 0.20,
        "identity_bridge": 0.10,
    },
}

PASSING_THRESHOLDS = {
    "default": 8.5,
    "ai_architect": 8.3,
    "ai_leadership": 8.5,
}
```

Add helper methods immediately after `__init__`:

- `_resolve_weight_profile(role_category: str) -> str`
- `_get_dimension_weights(role_category: str) -> Dict[str, float]`
- `_get_passing_threshold(role_category: str) -> float`

### 2. Add identity-bridge evidence extractor and rule-based scorer

File: [src/layer6_v2/grader.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:612)

Insert after `_grade_anti_hallucination()` at [545-610](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:545).

Add:

- `_extract_identity_bridge_evidence(cv_text, extracted_jd, master_cv_text) -> Dict[str, Any]`
- `_grade_identity_bridge(cv_text, extracted_jd, master_cv_text, weights) -> DimensionScore`

Recommended code checks inside `_extract_identity_bridge_evidence()`:

- Parse headline from the `###` line in the assembled CV.
- Parse summary/tagline as the first non-empty line after the summary header.
- Detect AI project section presence by looking for `Commander-4`, `Joyia`, `Lantern`, `LLM`, `AI platform`, or the dedicated AI project block inserted by orchestrator [1710-1724](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1710).
- Count architecture proof terms in key achievements and first experience bullets.
- Count AI proof terms in top third for `ai_architect` and `ai_leadership`.
- Cross-check headline/tagline specialty terms against `master_cv_text`.

Recommended fallback scoring weights inside the dimension:

- Headline truthfulness: 3 points
- Tagline proof ladder: 3 points
- Top-third evidence mix: 2 points
- Competency grounding: 2 points

### 3. Update LLM grading prompt and response parsing

File: [src/layer6_v2/grader.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:655)

Update `_grade_with_llm_inner()` at [662-697](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:662):

- Resolve `role_category`, `weight_profile`, and `weights` before prompt construction.
- Inject the identity-bridge dimension only for `ai_architect` and `ai_leadership`.
- Include extracted identity evidence in the user prompt.

Add to the JSON contract:

- `identity_bridge: {score, feedback, issues, strengths}` for AI architect and AI leadership profiles.

### 4. Update `grade()` assembly path

File: [src/layer6_v2/grader.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:815)

Current grade assembly is hardcoded at [841-883](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:841).

Refactor to:

- resolve weights once from `role_category`,
- build `dimension_scores` dynamically,
- append `identity_bridge` when the selected profile includes it,
- instantiate `GradeResult` with:
  - `passing_threshold=self._get_passing_threshold(role_category)`
  - `role_category=role_category`
  - `weight_profile=weight_profile`

### 5. `_compute_composite_score()` note

There is no `_compute_composite_score()` in `grader.py`. Composite logic currently lives in [types.py:2051-2055](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:2051). The implementation change belongs there, not in `grader.py`.

## Rubric Prompt Changes

Update both:

- the active prompt in [src/layer6_v2/grader.py:662-697](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:662)
- the dormant prompt module in [src/layer6_v2/prompts/grading_rubric.py:9-58](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/grading_rubric.py:9)

Use this exact text for the new dimension:

```text
=== DIMENSION 6: IDENTITY-BRIDGE (weight: 10%) ===

Judge whether the CV's top third tells a credible identity-to-impact story.

Check four things:
- Headline truthfulness: Uses a role-relevant title without claiming specialization the candidate has not earned.
- Tagline proof ladder: Starts from verified identity, extends to JD-relevant capability, and anchors that claim in evidence or outcome.
- Top-third proof density: Key achievements and summary include concrete architecture/platform proof; for AI-targeted roles they also include at least one grounded AI/LLM/platform proof point.
- Competency grounding: Core competencies reinforce the story and do not introduce terms that are not supported by experience or verified projects.

Score 9-10 (Excellent): Headline is evidence-bounded, tagline contains a clear proof ladder, top third includes architecture proof and AI proof where relevant, and competencies stay tightly grounded in verified experience.
Score 7-8 (Good): Mostly credible and well-positioned, but one element is weaker, more generic, or slightly under-evidenced.
Score 5-6 (Mixed): Identity is directionally plausible, but the bridge is incomplete, vague, thin on proof, or uneven across headline/tagline/achievements.
Score 3-4 (Weak): The CV is over-positioned or generic in the top third; claims outrun evidence, especially in headline or tagline.
Score 1-2 (Poor): The top third is materially misleading, claims unearned AI/architect identity, or fails to connect verified identity to measurable impact at all.
```

Also update `DIMENSION_DESCRIPTIONS` in [grading_rubric.py:177-224](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/grading_rubric.py:177) with:

```python
"identity_bridge": {
    "name": "Identity-Bridge",
    "weight": "10%",
    "focus": "Evidence-bounded headline, proof-based tagline, top-third coherence",
    "description": (
        "Evaluates whether the headline, tagline, key achievements, and competencies "
        "tell a credible identity-to-impact story without over-claiming specialization."
    ),
},
```

## Improver Changes

The improver will not break structurally because it targets dimensions dynamically, but it needs an explicit strategy so it does useful work on this new dimension.

### Required update

Add to [src/layer6_v2/improver.py:56-102](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/improver.py:56):

```python
"identity_bridge": {
    "focus": "Evidence-bounded top-third positioning",
    "tactics": [
        "Rewrite the headline to stay within verified identity while preserving JD relevance",
        "Rewrite the tagline to follow identity -> capability -> proof",
        "Ensure at least one architecture proof point appears in the summary or key achievements",
        "For AI-targeted roles, surface grounded AI platform evidence already present in the CV or master CV",
        "Remove or soften specialty terms that are not directly supported by experience or verified projects",
    ],
},
```

### Nice-to-have but recommended

- Add a specialized prompt hint in `_build_improvement_prompt()` at [178-240](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/improver.py:178) when `target_dimension == "identity_bridge"`:
  - keep the existing role title line intact if it is system-generated,
  - focus edits on summary, achievements, and competencies,
  - preserve Commander-4/Lantern grounding where present.

## Orchestrator Changes

2E can ship without orchestrator code changes because `role_category` already reaches the grader and the top-third AI section already exists.

Two orchestrator follow-ups are still recommended:

1. Fix misleading grading debug logging at [orchestrator.py:891-906](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:891)
   - It references `grade_result.dimensions`, which does not exist on `GradeResult`.
   - Change it to `grade_result.dimension_scores`.

2. Add optional post-improvement re-grade
   - Current flow is grade -> improve -> stop.
   - If `identity_bridge` becomes the main gate, not re-grading means the system cannot verify that the improved top third actually crossed the bar.
   - Recommended minimal change: after successful improvement, call `grade_cv()` once more only when the targeted dimension is `identity_bridge`.

## Sample Test Code

Add these tests to `tests/unit/test_layer6_v2_grader_improver.py`.

### 1. Identity-bridge scores strong grounded AI architect CV highly

```python
def test_grades_identity_bridge_grounded_ai_architect(self, sample_master_cv):
    grader = CVGrader(use_llm_grading=False)
    extracted_jd = {
        "role_category": "ai_architect",
        "top_keywords": ["LLM", "AI platform", "architecture", "RAG"],
        "technical_skills": ["LLM", "RAG", "Python"],
        "soft_skills": ["Leadership"],
        "responsibilities": ["Design AI platforms"],
        "implied_pain_points": ["Need an architect to scale AI systems"],
    }
    cv_text = \"\"\"# Candidate
### AI Platform Architect | Engineering Leader

**PROFESSIONAL SUMMARY**
Software architect and engineering leader who built enterprise AI platforms serving 2,000 users and production LLM gateway capabilities.

• Architected Commander-4/Joyia enterprise AI platform serving 2,000 users with 42 plugins
• Built Lantern LLM gateway to standardize provider access and evaluation

**CORE COMPETENCIES**
**Architecture:** Platform Architecture, System Design, AI Platform
**AI:** LLM Gateways, RAG, Evaluation
\"\"\"

    weights = grader._get_dimension_weights("ai_architect")
    result = grader._grade_identity_bridge(cv_text, extracted_jd, sample_master_cv, weights)
    assert result.dimension == "identity_bridge"
    assert result.score >= 8.0
```

### 2. Identity-bridge penalizes over-positioned AI claim

```python
def test_grades_identity_bridge_over_positioned_cv_low(self, sample_master_cv):
    grader = CVGrader(use_llm_grading=False)
    extracted_jd = {"role_category": "ai_architect", "top_keywords": ["LLM", "AI"], "implied_pain_points": []}
    cv_text = \"\"\"# Candidate
### Chief AI Architect

**PROFESSIONAL SUMMARY**
AI visionary transforming enterprises with next-generation intelligence.

**CORE COMPETENCIES**
**AI:** AGI Strategy, Autonomous Agents, AI Transformation
\"\"\"

    weights = grader._get_dimension_weights("ai_architect")
    result = grader._grade_identity_bridge(cv_text, extracted_jd, sample_master_cv, weights)
    assert result.score < 5.0
    assert any("headline" in issue.lower() or "proof" in issue.lower() for issue in result.issues)
```

### 3. Composite scoring works with 6 dimensions

```python
def test_grade_result_composite_with_six_dimensions(self):
    dims = [
        DimensionScore("ats_optimization", 8.0, 0.15, ""),
        DimensionScore("impact_clarity", 8.0, 0.20, ""),
        DimensionScore("jd_alignment", 9.0, 0.22, ""),
        DimensionScore("executive_presence", 8.0, 0.13, ""),
        DimensionScore("anti_hallucination", 9.0, 0.20, ""),
        DimensionScore("identity_bridge", 7.0, 0.10, ""),
    ]
    result = GradeResult(dimension_scores=dims, passing_threshold=8.3)
    assert result.composite_score == pytest.approx(8.27, rel=0.01)
    assert result.passed is False
```

### 4. Weight profile switches by role

```python
def test_get_dimension_weights_by_role_profile(self):
    grader = CVGrader(use_llm_grading=False)
    default_weights = grader._get_dimension_weights("engineering_manager")
    architect_weights = grader._get_dimension_weights("ai_architect")

    assert "identity_bridge" not in default_weights
    assert architect_weights["identity_bridge"] == 0.10
    assert sum(default_weights.values()) == pytest.approx(1.0)
    assert sum(architect_weights.values()) == pytest.approx(1.0)
```

### 5. Passing threshold changes by role

```python
def test_role_specific_passing_thresholds(self):
    grader = CVGrader(use_llm_grading=False)
    assert grader._get_passing_threshold("engineering_manager") == 8.5
    assert grader._get_passing_threshold("ai_architect") == 8.3
    assert grader._get_passing_threshold("ai_leadership") == 8.5
```

## Test Strategy

1. Update existing 5-dimension assumptions
   - Change tests that assert `len(result.dimension_scores) == 5` so they branch by role profile.
   - Add AI-role fixtures in `tests/unit/test_layer6_v2_grader_improver.py`.

2. Add rule-based unit coverage
   - `_grade_identity_bridge()` high-score case.
   - `_grade_identity_bridge()` over-positioned case.
   - `_get_dimension_weights()` for default vs AI profiles.
   - `GradeResult` six-dimension composite calculation.
   - `GradeResult` threshold behavior with `8.3` architect gate.

3. Add mocked LLM coverage
   - extend mocked `GradingResponse` objects to include `identity_bridge` when testing `ai_architect` and `ai_leadership`.
   - keep existing 5-dimension tests for default roles.

4. Update orchestrator fixtures
   - Add one `sample_grade_result_ai_architect` fixture with six dimensions for reasoning/logging coverage in `tests/unit/test_layer6_v2_orchestrator.py`.

5. Regression run
   - `python -m pytest tests/unit/test_layer6_v2_grader_improver.py tests/unit/test_layer6_v2_orchestrator.py`

## Risk Assessment

### Main risks

- Runtime prompt/schema mismatch
  - If `grading_rubric.py` is updated but `grader.py` prompt is not, the change will be partially documented but not active.
- LLM schema regressions
  - `GradingResponse` is currently strict. Adding a new required field for all roles would break default-role prompts.
- Threshold churn
  - Raising dimensional strictness without tuning prompts and improver may reduce pass rate before quality improves.
- Test fallout
  - Several tests hardcode 5 dimensions.
- No re-grade after improvement
  - The system can "improve" identity bridge without proving the score actually moved.

### Mitigations

- Make `identity_bridge` optional in the Pydantic response.
- Use profile-based weight resolution so non-AI roles stay unchanged.
- Add role-specific threshold tests.
- Roll out behind role-category gating only for `ai_architect` and `ai_leadership`.
- Add post-improvement re-grade for `identity_bridge` as a follow-up if pass-rate volatility remains high.

### Rollback plan

1. Disable architect profile routing by making `_resolve_weight_profile()` return `default`.
2. Leave the new dimension code in place but unreachable.
3. Revert prompt text only after schema rollback if LLM parsing starts failing.

## Implementation Sequence

1. Update `types.py` normalization and metadata fields.
2. Add weight profiles and threshold helpers in `grader.py`.
3. Add `_extract_identity_bridge_evidence()` and `_grade_identity_bridge()`.
4. Extend `GradingResponse` and active LLM prompt in `grader.py`.
5. Refactor `grade()` and `_grade_rule_based()` to build dimensions dynamically.
6. Update `prompts/grading_rubric.py` to match runtime behavior.
7. Add `identity_bridge` improvement strategy in `improver.py`.
8. Update grader/improver/orchestrator tests.
9. Optionally add post-improvement re-grade for `identity_bridge`.

## Summary Answers To Phase 2 Questions

- LLM-graded vs code-graded: hybrid is best.
- Weight rebalancing: explicit per-role weight dicts in the grader.
- Dimension count handling: `GradeResult` already supports variable length; the hardcoded problem is in `grader.py` schema and assembly, not composite math structure.
- Improver compatibility: mostly dynamic already, but it needs a concrete `identity_bridge` strategy entry.
- Pydantic impact: `GradingResponse` must gain optional `identity_bridge`; prompt JSON contract must change too.
- Threshold impact: yes, for `ai_architect` use `8.3` during rollout; keep default and `ai_leadership` at `8.5`.
- Identity-bridge scoring: evaluate headline truthfulness, tagline proof ladder, top-third proof density, and competency grounding using the rubric above.
