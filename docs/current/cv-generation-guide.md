# CV Generation Guide - Source of Truth

> **Purpose:** This document is the single source of truth for the CV generation system's strategy, architecture, data structures, and algorithms. Read this first before modifying any CV generation code.

---

## Quick Reference Card

### Pipeline Overview (6 Phases)

```
Input: JobState + Master CV (6 roles)
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐
│ Role 1  │   │ Role 2  │   │ Role 3  │  ... (6 roles total)
│ Bullets │   │ Bullets │   │ Bullets │
└────┬────┘   └────┬────┘   └────┬────┘
     │             │             │
     └─────────────┼─────────────┘
                   ▼
           ┌──────────────┐
           │   Stitcher   │  (Deduplication)
           │   + QA       │
           └──────┬───────┘
                  ▼
           ┌──────────────┐
           │   Header     │  (Profile + Skills)
           │   Generator  │
           └──────┬───────┘
                  ▼
           ┌──────────────┐
           │   Grader +   │  (5-Dimension Score)
           │   Improver   │
           └──────┬───────┘
                  ▼
           ┌──────────────┐
           │   Final CV   │
           └──────────────┘
```

### Key Files

| Component | File Path |
|-----------|-----------|
| Orchestrator | `src/layer6_v2/orchestrator.py` |
| Data Types | `src/layer6_v2/types.py` |
| Role Generator | `src/layer6_v2/role_generator.py` |
| Stitcher | `src/layer6_v2/stitcher.py` |
| Header Generator | `src/layer6_v2/header_generator.py` |
| Grader | `src/layer6_v2/grader.py` |
| ATS Checker | `src/layer6_v2/ats_checker.py` |
| Role QA | `src/layer6_v2/role_qa.py` |

### Processing Tiers

| Tier | Fit Score | Passes | Model | Use Case |
|------|-----------|--------|-------|----------|
| GOLD | > 0.8 | 3-pass + synthesis | Opus | High-priority jobs |
| SILVER | 0.6-0.8 | 2-pass | Sonnet | Medium-priority |
| BRONZE | 0.4-0.6 | 1-pass | Haiku | Low-priority |
| SKIP | < 0.4 | Template only | None | Not pursuing |

### Anti-Hallucination Guarantees

1. **Source Traceability**: Every bullet links to `source_text` from master CV
2. **Skill Whitelist**: All skills from candidate's verified skill list
3. **Metric Verification**: QA checks all numbers against source
4. **STAR Validation**: Every bullet has Situation, Action, Result

---

## Part 1: Strategy & Philosophy

### 1.1 Why Divide-and-Conquer?

The CV generation system uses a **per-role generation strategy** rather than generating the entire CV at once. This approach provides:

1. **Better Hallucination Control**: Each role is validated against its specific source text
2. **Targeted Tailoring**: Different roles get different emphasis based on career stage
3. **Easier Debugging**: If one role has issues, we can trace and fix it independently
4. **Quality Checkpoints**: QA runs after each role, catching issues early

### 1.2 Anti-Hallucination Philosophy

**Core Principle: Every claim must trace back to source material.**

The system prevents hallucination through multiple layers:

```
Layer 1: Source Traceability
├── GeneratedBullet.source_text → Original achievement text
├── GeneratedBullet.source_metric → Exact metric from source
└── AchievementSource.match_confidence → How closely it matches

Layer 2: Skill Whitelist Enforcement
├── SkillsProvenance.all_from_whitelist = True (guaranteed)
├── rejected_jd_skills → JD skills candidate doesn't have
└── Zero tolerance for invented skills

Layer 3: QA Verification
├── Metric verification (fuzzy match with 15% tolerance)
├── STAR format validation
└── Phrase grounding check
```

**What We Refuse To Do:**
- Add skills from JD that candidate doesn't have evidence for
- Invent metrics or quantified outcomes
- Claim achievements not in master CV
- Generate content without traceability

### 1.3 Role-Framing Strategy

The CV emphasizes different aspects based on target role type:

| Role Type | Emphasis | Keywords to Prioritize |
|-----------|----------|----------------------|
| **IC (Staff/Principal)** | Technical depth, architecture, scale | Systems, architecture, scale, performance |
| **Manager** | People, delivery, business outcomes | Team, hired, coached, shipped, revenue |
| **Director+** | Strategy, vision, organizational impact | Strategy, vision, transformed, scaled org |

**Career Context Rules:**
- **Current Role**: Maximum detail (5-6 bullets)
- **Previous Role**: Medium detail (4-5 bullets)
- **Older Roles**: Brief (2-3 bullets)

### 1.4 ATS Optimization Approach

The system optimizes for Applicant Tracking Systems through:

1. **Keyword Frequency**: Target 2-4 mentions of key terms
2. **Acronym Expansion**: Both forms required (e.g., "AWS" AND "Amazon Web Services")
3. **Strategic Placement**: Keywords in headline, profile first 50 words, and recent role bullets
4. **Standard Structure**: Professional Summary, Experience, Education, Skills

---

## Part 2: Pipeline Architecture

### 2.1 Phase-by-Phase Data Flow

#### Phase 1: CV Loader (`cv_loader.py`)

**Input:** Master CV files from `data/master-cv/roles/`
**Output:** `CandidateData` with 6 `RoleData` objects

```python
CandidateData:
├── name, email, phone, linkedin
├── education_masters, education_bachelors
├── certifications, languages
├── roles: List[RoleData]  # 6 roles
└── skill_whitelist: Dict[str, List[str]]  # hard_skills, soft_skills
```

The loader parses enhanced role files that contain achievements with pre-written variants for different emphasis.

#### Phase 2: Role Bullet Generation (`role_generator.py`)

**Input:** `RoleData` + `ExtractedJD` (from earlier pipeline layers)
**Output:** `RoleBullets` for each role

Two generation paths:

**Path A: Variant Selection (Zero-Hallucination)**
1. Parse role file → achievements with variants
2. Score each variant against JD pain points
3. Select top variants matching requirements
4. Apply annotation boosts

**Path B: LLM Generation (Full Tailoring)**
1. Build role-specific system prompt
2. Inject career context (emphasis guidance)
3. Call LLM with pain point mappings
4. Validate output with Pydantic
5. Optional STAR correction pass

#### Phase 3: Quality Assurance (`role_qa.py`)

**Input:** `RoleBullets` + Source `RoleData`
**Output:** `QAResult` + `ATSResult` per role

**Checks Performed:**
- Metric verification against source
- STAR format completeness
- ATS keyword coverage
- Phrase grounding in source material

#### Phase 4: Stitching & Deduplication (`stitcher.py`)

**Input:** `List[RoleBullets]` (all 6 roles)
**Output:** `StitchedCV`

**Process:**
1. Flatten all bullets with role context
2. Compare all pairs for similarity (keyword overlap + string matching)
3. If similarity > 0.75: keep more recent role's version
4. Track what was removed in `DeduplicationResult`

#### Phase 4.5: Annotation Context Building (`annotation_header_context.py`)

**Input:** `jd_annotations` + `all_stars`
**Output:** `HeaderGenerationContext`

Builds context for header generation using JD annotations to prioritize skills and achievements.

#### Phase 5: Header Generation (`header_generator.py`)

**Input:** `StitchedCV` + `ExtractedJD` + `CandidateData`
**Output:** `HeaderOutput`

**Components Generated:**
- **Headline**: "[EXACT_TITLE] | [YEARS]+ Years Technology Leadership"
- **Tagline**: Persona-driven hook (15-25 words)
- **Key Achievements**: 5-6 quantified bullets (scored and selected)
- **Core Competencies**: 6-8 ATS-optimized keywords
- **Skills Sections**: 4 sections with 6-8 skills each

#### Phase 6: Grading & Improvement (`grader.py`, `improver.py`)

**Input:** Complete CV text
**Output:** `GradeResult` + `ImprovementResult`

**5-Dimension Grading:**
1. ATS Optimization (20%)
2. Impact & Clarity (25%)
3. JD Alignment (25%)
4. Executive Presence (15%)
5. Anti-Hallucination (15%)

**Pass Threshold:** 8.5/10 composite score

### 2.2 Processing Tier Logic

Based on `fit_score` from JD analysis:

```python
def get_processing_tier(fit_score: float) -> ProcessingTier:
    if fit_score > 0.8:
        return ProcessingTier.GOLD    # 3-pass ensemble
    elif fit_score > 0.6:
        return ProcessingTier.SILVER  # 2-pass ensemble
    elif fit_score > 0.4:
        return ProcessingTier.BRONZE  # 1-pass simple
    else:
        return ProcessingTier.SKIP    # Template only
```

**GOLD Tier Ensemble Passes:**
1. **Metric Pass**: Maximize quantified outcomes
2. **Narrative Pass**: Compelling story, address pain points
3. **Keyword Pass**: Natural JD keyword integration
4. **Synthesis**: Combine best of all passes

---

## Part 3: Data Structures

### 3.1 Core Types (from `types.py`)

#### GeneratedBullet

Single CV bullet with full traceability:

```python
@dataclass
class GeneratedBullet:
    text: str                    # Final bullet text (20-35 words)
    source_text: str             # Original achievement from master CV
    source_metric: Optional[str] # Exact metric from source
    jd_keyword_used: Optional[str]     # JD keyword integrated
    pain_point_addressed: Optional[str] # Pain point this addresses

    # ARIS/STAR components
    action: str      # What was done
    result: str      # Quantified outcome
    situation: str   # Context/challenge

    # Annotation integration
    annotation_influenced: bool = False
    annotation_ids: List[str] = []
    annotation_boost: float = 1.0
```

#### RoleBullets

Generated bullets for one role:

```python
@dataclass
class RoleBullets:
    role_id: str
    company: str
    title: str
    period: str
    location: str

    bullets: List[GeneratedBullet]
    keywords_integrated: List[str]
    hard_skills: List[str]
    soft_skills: List[str]

    qa_result: Optional[QAResult]
    ats_result: Optional[ATSResult]
```

#### QAResult

Hallucination detection results:

```python
@dataclass
class QAResult:
    passed: bool                    # All content grounded
    flagged_bullets: List[str]      # Bullets that failed
    issues: List[str]               # Specific problems
    verified_metrics: List[str]     # Metrics that checked out
    star_result: Optional[STARResult]
    confidence: float               # 0.0 to 1.0
```

#### StitchedCV

Complete experience section after deduplication:

```python
@dataclass
class StitchedCV:
    roles: List[StitchedRole]       # Chronological, recent first
    total_word_count: int
    total_bullet_count: int
    keywords_coverage: List[str]    # JD keywords found
    deduplication_result: DeduplicationResult
```

#### ProfileOutput

Executive summary with anti-hallucination tracking:

```python
@dataclass
class ProfileOutput:
    headline: str                   # "[TITLE] | [X]+ Years..."
    tagline: str                    # 15-25 word hook
    key_achievements: List[str]     # 5-6 bullets
    core_competencies: List[str]    # 6-8 keywords

    # Anti-hallucination tracking
    achievement_sources: List[AchievementSource]
    skills_provenance: SkillsProvenance
    value_proposition: str
```

#### GradeResult

Multi-dimensional grading:

```python
@dataclass
class GradeResult:
    dimension_scores: List[DimensionScore]
    composite_score: float          # 1-10 weighted average
    passed: bool                    # >= 8.5 threshold
    improvement_priority: List[str] # Ordered dimensions to improve
```

### 3.2 Key Enums

```python
class ProcessingTier(Enum):
    GOLD = "gold"       # fit > 0.8
    SILVER = "silver"   # 0.6 < fit <= 0.8
    BRONZE = "bronze"   # 0.4 < fit <= 0.6
    SKIP = "skip"       # fit <= 0.4

class RoleCategory(Enum):
    IC = "ic"           # Individual Contributor
    MANAGER = "manager"
    DIRECTOR = "director"
    VP = "vp"
    CTO = "cto"
```

---

## Part 4: Algorithms

### 4.1 Achievement Scoring Formula

When selecting key achievements for the profile section:

```python
def score_achievement(bullet: str, context: ScoringContext) -> float:
    score = 0.0

    # Pain point matching (weight: 2.0 per match)
    for pain_point in context.pain_points:
        if pain_point.lower() in bullet.lower():
            score += 2.0

    # Annotation suggested (weight: 3.0)
    if bullet in context.annotation_suggested_bullets:
        score += 3.0

    # Keyword matching (weight: 0.5 per keyword)
    for keyword in context.jd_keywords:
        if keyword.lower() in bullet.lower():
            score += 0.5

    # Core strength (weight: 1.5)
    if is_core_strength(bullet, context.candidate_strengths):
        score += 1.5

    # Recency factor
    if context.role_index == 0:      # Current role
        score += 1.0
    elif context.role_index == 1:    # Previous role
        score += 0.5
    # Older roles: +0.0

    return score
```

### 4.2 Deduplication Algorithm

Cross-role duplicate detection:

```python
def detect_duplicates(all_bullets: List[BulletWithContext]) -> List[DuplicatePair]:
    duplicates = []

    for i, bullet1 in enumerate(all_bullets):
        for j, bullet2 in enumerate(all_bullets[i+1:], i+1):
            # Skip if same role
            if bullet1.role_index == bullet2.role_index:
                continue

            # Calculate similarity
            keyword_overlap = len(
                set(extract_keywords(bullet1.text)) &
                set(extract_keywords(bullet2.text))
            )
            metrics_match = bullet1.metrics == bullet2.metrics
            string_sim = SequenceMatcher(
                None, bullet1.text.lower(), bullet2.text.lower()
            ).ratio()

            # Check threshold
            if (keyword_overlap > 0 or metrics_match) and string_sim > 0.75:
                duplicates.append(DuplicatePair(
                    bullet1=bullet1,
                    bullet2=bullet2,
                    similarity=string_sim,
                    reason=f"overlap={keyword_overlap}, metrics={metrics_match}"
                ))

    return duplicates
```

**Resolution:** Keep the more recent role's version.

### 4.3 Skills Section Selection

Taxonomy-based skills selection:

```python
def select_skills_sections(
    taxonomy: RoleTaxonomy,
    jd: ExtractedJD,
    whitelist: Set[str]
) -> List[SkillsSection]:

    # Step 1: Score each taxonomy section
    section_scores = []
    for section in taxonomy.sections:
        jd_match_score = sum(
            1 for signal in section.jd_signals
            if signal.lower() in jd.job_description.lower()
        ) / len(section.jd_signals)

        section_scores.append((section, jd_match_score))

    # Step 2: Select top 4 sections
    section_scores.sort(key=lambda x: x[1], reverse=True)
    selected_sections = [s for s, _ in section_scores[:4]]

    # Step 3: For each section, select skills
    result = []
    for section in selected_sections:
        skills_in_whitelist = [
            s for s in section.skills
            if s.lower() in whitelist
        ]

        # Score each skill
        scored_skills = []
        for skill in skills_in_whitelist:
            skill_score = (
                (1.0 if skill.lower() in jd.keywords_lower else 0.0) +
                evidence_score(skill, bullets) +
                annotation_boost(skill, annotations)
            )
            scored_skills.append((skill, skill_score))

        # Select top 6
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        result.append(SkillsSection(
            category=section.name,
            skills=[s for s, _ in scored_skills[:6]]
        ))

    return result
```

### 4.4 Keyword Placement Strategy

Priority positions for ATS optimization:

```python
KEYWORD_PLACEMENT_WEIGHTS = {
    "headline": 40,          # Most important
    "profile_first_50": 30,  # Critical for 6-second scan
    "core_competencies": 20, # Skills section
    "recent_role_bullets": 10 # Experience bullets
}

def calculate_placement_score(cv: str, keywords: List[str]) -> int:
    score = 0

    for keyword in keywords:
        if keyword in cv_headline:
            score += 40
        if keyword in cv_profile[:50_words]:
            score += 30
        if keyword in core_competencies:
            score += 20
        if keyword in recent_role_section:
            score += 10

    return score  # 0-100 normalized
```

---

## Part 5: Quality Gates

### 5.1 Hallucination QA

**Location:** `role_qa.py`

**Checks:**

1. **Metric Verification**
   - Extract all metrics from generated bullet (%, $, numbers)
   - Fuzzy match against source achievements (15% tolerance)
   - Flag if metric doesn't exist in source

2. **Leadership Claim Support**
   - Detect claims like "led", "managed", "built team"
   - Verify evidence exists in source role

3. **Source Grounding**
   - Key phrases must appear in master CV
   - Fuzzy matching with 0.7 similarity threshold

```python
def check_hallucination(bullet: str, source: str) -> QAResult:
    issues = []

    # Check metrics
    for metric in extract_metrics(bullet):
        if not metric_in_source(metric, source, tolerance=0.15):
            issues.append(f"Metric '{metric}' not in source")

    # Check key phrases
    for phrase in extract_key_phrases(bullet):
        if not phrase_grounded(phrase, source):
            issues.append(f"Phrase '{phrase}' not grounded")

    return QAResult(
        passed=len(issues) == 0,
        issues=issues,
        confidence=max(0, 1 - len(issues) / 5)
    )
```

### 5.2 STAR Format Validation

**Target:** 80%+ bullets must have complete STAR components.

```python
def validate_star(bullet: str) -> STARResult:
    has_situation = bool(re.search(
        r'(faced|challenged|when|amid|during|despite)',
        bullet, re.I
    ))
    has_action = bool(re.search(
        r'(led|built|architected|designed|implemented|created)',
        bullet, re.I
    ))
    has_result = bool(re.search(
        r'(\d+%|\$[\d,]+|[0-9]+x|reduced|increased|improved)',
        bullet, re.I
    ))

    return STARResult(
        has_situation=has_situation,
        has_action=has_action,
        has_result=has_result,
        complete=all([has_situation, has_action, has_result])
    )
```

### 5.3 ATS Keyword Coverage

**Targets:**
- Must-have keywords: 80%+ coverage
- Nice-to-have keywords: 60%+ coverage
- Overall: 70%+ minimum

```python
def check_ats_coverage(cv: str, jd_keywords: Keywords) -> ATSResult:
    must_have_found = sum(
        1 for kw in jd_keywords.must_have
        if kw.lower() in cv.lower()
    )

    coverage = must_have_found / len(jd_keywords.must_have)

    return ATSResult(
        coverage_ratio=coverage,
        passed=coverage >= 0.8,
        missing=[
            kw for kw in jd_keywords.must_have
            if kw.lower() not in cv.lower()
        ]
    )
```

### 5.4 Multi-Dimensional Grading

**Location:** `grader.py`

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| ATS Optimization | 20% | Keyword frequency, acronym expansion, standard format |
| Impact & Clarity | 25% | Metrics count, action verbs, specificity |
| JD Alignment | 25% | Pain points addressed, terminology match |
| Executive Presence | 15% | Strategic framing, leadership evidence |
| Anti-Hallucination | 15% | Source grounding, metric verification |

**Passing Threshold:** 8.5/10 composite score

---

## Part 6: Role-Specific Guidance

### 6.1 IC Track (Staff/Principal Engineer)

**Emphasis:**
- Technical depth and architecture decisions
- System scale (users, requests/sec, data volumes)
- Cross-team influence without direct reports
- Code quality and technical standards

**Keywords to Prioritize:**
- Architecture, distributed systems, scalability
- Microservices, Kubernetes, cloud-native
- Performance optimization, system design
- Technical leadership, mentorship

**Bullet Format:**
```
"Architected [system] handling [scale], reducing [metric] by [X]% through [technical approach]"
```

**What NOT to Emphasize:**
- Team management, hiring metrics
- P&L responsibility
- Executive reporting

### 6.2 Engineering Manager

**Emphasis:**
- Team size and growth
- Hiring and retention
- Delivery metrics (velocity, quality)
- People development

**Keywords to Prioritize:**
- Team leadership, talent development
- Agile, Scrum, delivery
- Hiring, onboarding, coaching
- Cross-functional collaboration

**Bullet Format:**
```
"Led [X]-person team delivering [project], improving [metric] by [Y]% while [people outcome]"
```

### 6.3 Director of Engineering

**Emphasis:**
- Multiple team leadership
- Budget responsibility
- Strategic planning
- Organizational impact

**Keywords to Prioritize:**
- Strategic planning, roadmap
- Budget management, P&L
- Organizational design
- Executive stakeholder management

**Bullet Format:**
```
"Directed [X]-person organization across [Y] teams, scaling from [A] to [B] while [business outcome]"
```

### 6.4 Head of Engineering / VP

**Emphasis:**
- Department-wide strategy
- Executive leadership
- Business partnership
- Transformation initiatives

**Keywords:**
- Engineering strategy, vision
- Executive leadership
- Digital transformation
- Business outcomes, revenue impact

### 6.5 CTO

**Emphasis:**
- Company-wide technology strategy
- Board-level communication
- M&A technical due diligence
- Industry thought leadership

**Keywords:**
- Technology vision, strategy
- Innovation, digital transformation
- Board reporting, investor relations
- Industry leadership

### 6.6 Regional Variations

| Region | Key Differences |
|--------|-----------------|
| **US** | Focus on impact metrics, aggressive self-promotion acceptable |
| **UK** | Slightly more modest tone, still metrics-focused |
| **Germany** | Detailed qualifications, formal structure, certifications matter |
| **MENA** | Relationship-building emphasis, regional experience valued |

---

## Part 7: ATS Optimization Reference

### 7.1 Keyword Frequency Targets

```
Must-Have Keywords: 2-4 mentions each
Nice-to-Have Keywords: 1-2 mentions each
Total Keyword Occurrences: 30-50 across CV
```

**Avoid Keyword Stuffing:** > 4 mentions of same term triggers penalty

### 7.2 Acronym Expansion Rules

Every acronym must appear with its full form at least once:

```
AWS (Amazon Web Services)
K8s (Kubernetes)
CI/CD (Continuous Integration/Continuous Deployment)
ML (Machine Learning)
API (Application Programming Interface)
```

**Placement Strategy:**
- Full form first, then acronym in parentheses
- Use acronym alone in subsequent mentions

### 7.3 Section Structure Requirements

Standard ATS-parseable sections:

```
PROFESSIONAL SUMMARY (or EXECUTIVE SUMMARY)
CORE COMPETENCIES (or TECHNICAL SKILLS)
PROFESSIONAL EXPERIENCE
EDUCATION
CERTIFICATIONS (optional)
```

**Avoid:**
- Creative section names ("My Journey", "What I Bring")
- Non-standard headers that ATS can't categorize
- Tables or multi-column layouts

### 7.4 Platform-Specific Quirks

| ATS | Key Quirk | Mitigation |
|-----|-----------|------------|
| **Greenhouse** | No abbreviation recognition | Include both forms always |
| **Greenhouse** | Word frequency = skill depth | Repeat key terms 3-5x naturally |
| **Lever** | PDF parsing issues | Prefer DOCX format |
| **Lever** | Tables break parsing | Avoid tables entirely |
| **Taleo** | Extreme literalism | Match JD phrasing exactly |
| **Workday** | Complex formatting fails | Use single-column, simple layout |

### 7.5 Keyword Placement Priority

```
1. Headline (40 points)
   - Include primary role keyword + years

2. Profile First 50 Words (30 points)
   - Front-load with JD-matched terminology

3. Core Competencies (20 points)
   - ATS-scannable skills list

4. Recent Role Bullets (10 points)
   - Natural integration in achievements
```

---

## Appendix A: File Reference

### Pipeline Code

| Concept | Primary File | Line Range |
|---------|--------------|------------|
| Orchestration | `src/layer6_v2/orchestrator.py` | Full file |
| All Data Types | `src/layer6_v2/types.py` | 1-1800+ |
| Role Generation | `src/layer6_v2/role_generator.py` | Full file |
| Stitching | `src/layer6_v2/stitcher.py` | Full file |
| Header Generation | `src/layer6_v2/header_generator.py` | Full file |
| Ensemble Header | `src/layer6_v2/ensemble_header_generator.py` | Full file |
| Grading | `src/layer6_v2/grader.py` | Full file |
| Improvement | `src/layer6_v2/improver.py` | Full file |
| ATS Checking | `src/layer6_v2/ats_checker.py` | Full file |
| Role QA | `src/layer6_v2/role_qa.py` | Full file |

### Prompts

| Prompt Type | File |
|-------------|------|
| Role Generation | `src/layer6_v2/prompts/role_generation.py` |
| Header Generation | `src/layer6_v2/prompts/header_generation.py` |
| Grading Rubric | `src/layer6_v2/prompts/grading_rubric.py` |

### Data Files

| Data | Location |
|------|----------|
| Master CV Roles | `data/master-cv/roles/*.md` |
| Role Metadata | `data/master-cv/role_metadata.json` |
| Skills Taxonomy | `data/master-cv/role_skills_taxonomy.json` |
| Candidate Metadata | `data/master-cv/master_cv_metadata.json` |

### Tests

| Test Area | File |
|-----------|------|
| CV Loader | `tests/unit/layer6_v2/test_cv_loader.py` |
| Role Generator | `tests/unit/layer6_v2/test_role_generator.py` |
| Stitcher | `tests/unit/layer6_v2/test_stitcher.py` |
| Header Generator | `tests/unit/layer6_v2/test_header_generator.py` |
| Grader | `tests/unit/layer6_v2/test_grader.py` |

---

## Appendix B: Configuration Reference

### Scoring Weights

```python
# Achievement Selection
ACHIEVEMENT_SCORING_WEIGHTS = {
    "pain_point_match": 2.0,
    "annotation_suggested": 3.0,
    "keyword_match": 0.5,
    "core_strength": 1.5,
    "emphasis_area": 1.5,
    "recency_current_role": 1.0,
    "recency_previous_role": 0.5,
    "recency_old_role": 0.0,
    "variant_type_match": 1.0,
}

# Grading Dimensions
GRADING_DIMENSION_WEIGHTS = {
    "ats_optimization": 0.20,
    "impact_clarity": 0.25,
    "jd_alignment": 0.25,
    "executive_presence": 0.15,
    "anti_hallucination": 0.15,
}

# Keyword Placement
KEYWORD_PLACEMENT_WEIGHTS = {
    "headline": 40,
    "profile_first_50": 30,
    "core_competencies": 20,
    "recent_role_bullets": 10,
}
```

### Thresholds

```python
# Quality Gates
GRADING_PASS_THRESHOLD = 8.5          # Composite score minimum
ATS_MUST_HAVE_COVERAGE = 0.80         # 80% must-have keywords
ATS_OVERALL_COVERAGE = 0.70           # 70% total keywords
STAR_COVERAGE_TARGET = 0.80           # 80% bullets with complete STAR
HALLUCINATION_MAX_FLAGGED = 0.40      # Max 40% bullets can be flagged

# Deduplication
DEDUP_SIMILARITY_THRESHOLD = 0.75     # Above this = duplicate

# Metrics
METRIC_VERIFICATION_TOLERANCE = 0.15  # 15% fuzzy match tolerance
KEYWORD_FREQUENCY_MIN = 2
KEYWORD_FREQUENCY_MAX = 4
```

### Processing Tier Thresholds

```python
TIER_THRESHOLDS = {
    "GOLD": 0.8,     # fit_score > 0.8
    "SILVER": 0.6,   # 0.6 < fit_score <= 0.8
    "BRONZE": 0.4,   # 0.4 < fit_score <= 0.6
    "SKIP": 0.0,     # fit_score <= 0.4
}
```

---

## Changelog

| Date | Change |
|------|--------|
| 2025-12-31 | Initial creation - consolidated from exploration of layer6_v2 codebase |

---

*This document is the source of truth for CV generation. Update it when the system changes.*
