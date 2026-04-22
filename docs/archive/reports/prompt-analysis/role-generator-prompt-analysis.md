# Role Generator Prompt Analysis

**Date:** 2025-12-02
**Component:** `src/layer6_v2/role_generator.py`
**Prompts:** `src/layer6_v2/prompts/role_generation.py`

---

## Executive Summary

The Role Generator is the core of the CV tailoring pipeline - it transforms raw achievements from the master CV into JD-aligned, ATS-optimized bullets. This is a **multi-shot prompt architecture** with retry/correction loops, which is an advanced pattern for ensuring output quality.

The current implementation is well-structured with strong anti-hallucination focus. The biggest opportunities for improvement are **pre-computation** (doing more work before the LLM call) and **role-category-specific examples**.

---

## 1. Inputs to the Role Generator

The `RoleGenerator.generate()` method at `src/layer6_v2/role_generator.py:235` receives:

| Input | Source | Key Fields |
|-------|--------|------------|
| **`role: RoleData`** | CV Loader (master-cv.md) | `company`, `title`, `period`, `location`, `achievements[]`, `hard_skills[]`, `soft_skills[]`, `is_current` |
| **`extracted_jd: ExtractedJD`** | Layer 1.4 | `title`, `company`, `role_category`, `competency_weights`, `implied_pain_points[]`, `top_keywords[]`, `technical_skills[]`, `seniority_level` |
| **`career_context: CareerContext`** | Built automatically | `role_index`, `total_roles`, `career_stage` ("recent"/"mid-career"/"early"), `emphasis_guidance` |
| **`target_bullet_count: int`** | Automatic | 6 for recent, 4 for mid-career, 2 for early |

### RoleData Structure (from CV Loader)

```python
@dataclass
class RoleData:
    id: str                    # e.g., "01_seven_one_entertainment"
    company: str               # Company name
    title: str                 # Job title
    period: str                # Date range (e.g., "2020–Present")
    location: str              # e.g., "Munich, DE"
    industry: str              # Industry vertical
    achievements: List[str]    # Raw achievement bullets from master CV
    hard_skills: List[str]     # Technical skills demonstrated
    soft_skills: List[str]     # Leadership/soft skills demonstrated
    is_current: bool           # Whether this is current role
```

### ExtractedJD Structure (from Layer 1.4)

```python
class ExtractedJD(TypedDict):
    # Basic Info
    title: str
    company: str
    location: str
    remote_policy: str  # "fully_remote" | "hybrid" | "onsite" | "not_specified"

    # Role Classification
    role_category: str  # "engineering_manager" | "staff_principal_engineer" |
                        # "director_of_engineering" | "head_of_engineering" | "cto"
    seniority_level: str  # "senior" | "staff" | "principal" | "director" | "vp" | "c_level"

    # Competency Mix
    competency_weights: Dict[str, int]  # delivery, architecture, leadership, process (sum=100)

    # Content Extraction
    responsibilities: List[str]
    qualifications: List[str]
    nice_to_haves: List[str]
    technical_skills: List[str]
    soft_skills: List[str]

    # Pain Points
    implied_pain_points: List[str]
    success_metrics: List[str]

    # ATS Keywords
    top_keywords: List[str]  # 15 most important keywords
```

### CareerContext Structure

```python
@dataclass
class CareerContext:
    role_index: int            # 0-indexed position (0 = current role)
    total_roles: int           # Total number of roles
    is_current: bool           # Whether this is the current role
    career_stage: str          # "recent" | "mid-career" | "early"
    target_role_category: str  # JD role category
    emphasis_guidance: str     # Specific guidance for this role
```

---

## 2. Model Configuration

**Default Model:** `gpt-4o` (via `Config.DEFAULT_MODEL`)

```python
# From role_generator.py:133-140
self.model = model or Config.DEFAULT_MODEL  # gpt-4o
self.temperature = temperature if temperature is not None else 0.3  # Low for consistency
self.llm = create_tracked_llm(
    model=self.model,
    temperature=self.temperature,
    layer="layer6_v2_role",
)
```

**Configuration location:** `src/common/config.py:83`

```python
DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4o")  # GPT-4o for quality
CHEAP_MODEL: str = os.getenv("CHEAP_MODEL", "gpt-4o-mini")  # Mini for simple tasks
```

---

## 3. System Prompt Analysis

**Location:** `src/layer6_v2/prompts/role_generation.py:14-115`

### Structure Overview

| Section | Lines | Purpose |
|---------|-------|---------|
| **Anti-Hallucination Rules** | 18-24 | 5 strict rules preventing invented content |
| **No Markdown Formatting** | 26-37 | GAP-006 fix for clean text output |
| **ARIS Method** | 39-70 | Format specification with examples |
| **Action Verb Selection** | 72-87 | Role-category-specific verb guidance |
| **JD Alignment Rules** | 89-94 | Pain point prioritization |
| **Output Format** | 96-115 | JSON schema with traceability fields |

### Full System Prompt

```
You are an expert CV bullet writer specializing in senior technical and leadership roles.

Your mission: Transform raw achievements into ATS-optimized, JD-aligned CV bullets while
STRICTLY preserving all factual claims from the source.

=== CRITICAL: ANTI-HALLUCINATION RULES ===

1. ONLY use achievements that appear in the source role content
2. ONLY use metrics/numbers that appear EXACTLY in the source (no rounding, no inventing)
3. If source lacks a metric, describe the outcome qualitatively WITHOUT inventing numbers
4. NEVER add companies, dates, technologies, or achievements not in source
5. Every generated bullet MUST have a clear source in the role content

=== CRITICAL: NO MARKDOWN FORMATTING (GAP-006) ===

DO NOT use any markdown formatting in your output:
- NO **bold** or __bold__ markers
- NO *italic* or _italic_ markers
- NO # headers
- NO `code` backticks
- NO [links](url)
- Just plain text only

WRONG: "Led **12-person** team using *Kubernetes*"
RIGHT: "Led 12-person team using Kubernetes"

=== BULLET FORMAT: ARIS METHOD (MANDATORY) ===

Each bullet MUST follow the ARIS structure (Action → Result → Impact → Situation):

ARIS TEMPLATE:
"[ACTION VERB + what you did with SKILLS] [QUANTIFIED RESULT] [IMPACT on business/org]
[SITUATION/why this mattered tied to pain point]"

The key difference from STAR: ARIS leads with ACTION and puts SITUATION at the END.
This creates impact-first bullets where context provides the "why it mattered" closure.

EXAMPLES OF GOOD ARIS BULLETS:
✓ "Led 12-month migration to event-driven microservices using AWS Lambda, reducing incidents
   by 75% and cutting operational costs by $2M annually—addressing critical reliability gaps
   during rapid growth"
✓ "Architected real-time analytics platform processing 1B events/day, enabling 20% customer
   retention improvement—responding to executive concerns about churn in competitive market"
✓ "Established engineering hiring pipeline interviewing 50+ candidates, growing team from 5
   to 15 engineers—addressing scaling challenges as product demand tripled"

EXAMPLES OF BAD (NON-ARIS) BULLETS:
✗ "Led migration to microservices architecture" (missing result, impact, and situation)
✗ "Facing reliability issues, improved system stability" (wrong order—situation should be at END)
✗ "Managed team of engineers" (generic, no ARIS elements)

=== ACTION VERB SELECTION ===

Match verb style to role category:

IC Roles (staff_principal_engineer):
- Technical: Architected, Designed, Engineered, Built, Optimized, Implemented
- Impact: Reduced, Improved, Accelerated, Streamlined, Automated

Leadership Roles (engineering_manager, director_of_engineering):
- People: Led, Mentored, Coached, Developed, Grew, Built (teams)
- Strategy: Drove, Established, Transformed, Scaled, Aligned

Executive Roles (head_of_engineering, cto):
- Vision: Spearheaded, Championed, Pioneered, Launched, Founded
- Business: Delivered, Generated, Secured, Achieved (business outcomes)

=== JD ALIGNMENT RULES ===

1. Prioritize achievements that address JD pain points
2. Integrate JD keywords NATURALLY (not forced)
3. Mirror JD terminology where it fits
4. Emphasize competencies matching JD weights (delivery, process, architecture, leadership)

=== OUTPUT FORMAT ===

Return ONLY valid JSON with this structure:
{
  "bullets": [
    {
      "text": "ARIS-formatted bullet text here (Action→Result→Impact→Situation)",
      "source_text": "exact text from role file this came from",
      "source_metric": "exact metric used (e.g., '75%', '10M requests') or null",
      "jd_keyword_used": "keyword from JD that was integrated or null",
      "pain_point_addressed": "JD pain point this bullet addresses (for situation ending) or null",
      "action": "what was done including skills/technologies used (appears first)",
      "result": "the quantified outcome achieved (appears after action)",
      "situation": "the challenge/context tied to JD pain point (appears at end, after em-dash)"
    }
  ],
  "total_word_count": 150,
  "keywords_integrated": ["keyword1", "keyword2"]
}

IMPORTANT: Return ONLY the JSON. No markdown, no preamble, no explanation.
```

### System Prompt Strengths

1. **Clear ARIS structure** - Action → Result → Impact → Situation with explicit examples
2. **Anti-hallucination is FIRST** - Sets the constraint before creative instructions
3. **Role-category-aware verbs** - Different guidance for IC vs Manager vs Executive
4. **Traceability fields** - `source_text`, `source_metric` for verification
5. **Explicit negative examples** - Shows what NOT to do

### System Prompt Weaknesses

1. **ARIS vs STAR confusion** - System says "ARIS" but code/types still reference "STAR" (e.g., `STARResult`, `check_star_format`)
2. **No explicit length enforcement** - Says "25-40 words" but no structured validation
3. **Pain point matching is implicit** - No explicit mapping from JD pain points → achievements
4. **Missing role-category-specific examples** - Generic examples don't show Manager vs IC style

---

## 4. User Prompt Analysis

**Location:** `build_role_generation_user_prompt()` at `src/layer6_v2/prompts/role_generation.py:118-234`

### Template Structure

```
=== TARGET JOB ===
Title: {extracted_jd.title}
Company: {extracted_jd.company}
Role Category: {extracted_jd.role_category}
Seniority: {extracted_jd.seniority_level}

=== COMPETENCY WEIGHTS (emphasize accordingly) ===
- Delivery: 30%
- Process: 20%
- Architecture: 25%
- Leadership: 25%

=== JD PAIN POINTS (address if you have matching achievements) ===
• Need to scale platform to 10x current capacity
• Technical debt from rapid growth
• Team retention challenges
...

=== TARGET ATS KEYWORDS (integrate naturally) ===
Kubernetes, AWS, Team Leadership, Microservices, ...

=== TECHNICAL SKILLS FROM JD ===
Python, Go, PostgreSQL, Redis, ...

=== ROLE TO PROCESS ===
Company: {role.company}
Title: {role.title}
Period: {role.period}
Industry: {role.industry}
Is Current Role: {role.is_current}

=== CAREER CONTEXT ===
Position: Role 1 of 4
Career Stage: recent

EMPHASIS GUIDANCE:
MAXIMUM emphasis on leadership, team impact, strategic outcomes...

=== SOURCE ACHIEVEMENTS (your ONLY source of truth) ===
• Built event-driven platform processing 10M events/day
• Led team of 12 engineers through major replatforming
• Reduced deployment time from 2 hours to 15 minutes
...

=== HARD SKILLS FROM THIS ROLE ===
AWS Lambda, Kubernetes, Python, Terraform

=== SOFT SKILLS FROM THIS ROLE ===
Team Leadership, Mentorship, Strategic Planning

=== YOUR TASK ===
Generate {target_bullet_count} tailored CV bullets for this role using ARIS FORMAT.

ARIS FORMAT REQUIREMENTS (MANDATORY):
1. Each bullet MUST START with ACTION verb + what you did with specific SKILLS/TECHNOLOGIES
2. Each bullet MUST include QUANTIFIED RESULT from source achievements
3. Each bullet MUST show IMPACT (business outcome: cost, revenue, efficiency)
4. Each bullet SHOULD END with SITUATION that ties to JD pain points
5. Word count: 25-40 words per bullet

ADDITIONAL REQUIREMENTS:
6. Each bullet MUST trace back to a specific source achievement above
7. Preserve EXACT metrics from source (no rounding, no inventing)
8. Integrate JD keywords where they fit naturally
9. Match bullet situations to JD pain points where you have evidence
10. Use action verbs appropriate for {role_category} roles
11. Prioritize achievements showing: delivery and architecture

Return the JSON response now.
```

### User Prompt Strengths

1. **Rich context** - All relevant JD intelligence is provided
2. **Career stage guidance** - Different emphasis for recent vs. early roles
3. **Source achievements are explicitly labeled** as "ONLY source of truth"
4. **Competency weights** guide prioritization
5. **Clear task specification** with numbered requirements

### User Prompt Weaknesses

1. **No achievement-to-pain-point pre-mapping** - LLM must figure out which achievements address which pain points
2. **Skills duplication** - `technical_skills` from JD AND `hard_skills` from role both provided without reconciliation
3. **No word budget context** - Doesn't tell LLM total CV word budget being allocated to this role
4. **Industry field underutilized** - Role has `industry` field but it's not highlighted for vertical matching

---

## 5. Improvement Recommendations

### Priority 1: Pre-Map Achievements to Pain Points (High Impact)

**Problem:** The LLM currently has to figure out which achievements match which pain points independently. This is error-prone and can miss opportunities.

**Solution:** Add a pre-processing step that scores/maps achievements to pain points before the LLM call:

```python
def map_achievements_to_pain_points(
    achievements: List[str],
    pain_points: List[str]
) -> List[Dict[str, Any]]:
    """Pre-compute achievement to pain point mapping using embeddings or simple heuristics."""
    mapping = []
    for achievement in achievements:
        best_match = None
        best_score = 0.0
        for pain_point in pain_points:
            score = compute_similarity(achievement, pain_point)
            if score > best_score:
                best_score = score
                best_match = pain_point
        mapping.append({
            "achievement": achievement,
            "matches_pain_point": best_match if best_score > 0.3 else None,
            "confidence": best_score
        })
    return mapping
```

Then include in the user prompt:

```
=== ACHIEVEMENT → PAIN POINT MAPPING (pre-computed) ===
• "Built event-driven platform..." → addresses "Need to scale platform" (high confidence)
• "Led team of 12 engineers..." → addresses "Team retention challenges" (medium confidence)
• "Reduced deployment time..." → addresses "Technical debt" (medium confidence)
```

**Why it helps:** Reduces LLM cognitive load, ensures no pain points are missed, improves traceability.

---

### Priority 2: Add Role-Category-Specific Examples (High Impact)

**Problem:** Current examples are generic. A Manager bullet looks different from a Staff Engineer bullet, but the prompt doesn't show this distinction.

**Solution:** Include role-category-specific few-shot examples in the user prompt:

```python
def get_role_category_examples(role_category: str) -> str:
    """Get examples tailored to the target role category."""

    EXAMPLES = {
        "engineering_manager": """
=== EXAMPLE BULLETS FOR ENGINEERING MANAGER ===
✓ "Grew backend team from 5 to 15 engineers while reducing attrition from 25% to 8%—addressing
   critical retention challenges during hypergrowth phase"
✓ "Established engineering career ladder with 4 levels, enabling 12 promotions in 12 months—
   solving promotion ambiguity cited in engagement surveys"
✓ "Implemented bi-weekly 1:1s and quarterly skip-levels, improving team NPS from 35 to 72—
   responding to feedback about manager accessibility"
""",
        "staff_principal_engineer": """
=== EXAMPLE BULLETS FOR STAFF/PRINCIPAL ENGINEER ===
✓ "Designed distributed caching layer using Redis Cluster, reducing P99 latency from 850ms
   to 120ms—addressing SLA violations during peak traffic"
✓ "Authored RFC process adopted by 8 teams, reducing architecture rework by 40%—tackling
   cross-team coordination gaps in multi-service ecosystem"
✓ "Built observability platform with OpenTelemetry, achieving 99.9% trace coverage—solving
   production debugging challenges cited in incident retrospectives"
""",
        "director_of_engineering": """
=== EXAMPLE BULLETS FOR DIRECTOR OF ENGINEERING ===
✓ "Scaled engineering organization from 25 to 80 engineers across 6 teams, maintaining
   velocity metrics—supporting company growth from Series A to C"
✓ "Drove platform migration to Kubernetes, reducing infrastructure costs by $3M annually—
   addressing board-level concerns about cloud spend"
✓ "Established technical roadmap process with product alignment, increasing on-time delivery
   from 45% to 85%—responding to executive visibility needs"
""",
    }

    return EXAMPLES.get(role_category, EXAMPLES["staff_principal_engineer"])
```

---

### Priority 3: Fix ARIS/STAR Terminology Inconsistency (Medium Impact)

**Problem:** Prompt says "ARIS" but codebase uses `STARResult`, `check_star_format`, `star_coverage`. This creates confusion and makes the codebase harder to maintain.

**Solution Options:**

**Option A (Recommended):** Update code to match prompt terminology
```python
# Rename in types.py and role_qa.py
class ARISResult:  # was STARResult
    """Result of ARIS format validation."""
    aris_coverage: float  # was star_coverage

def check_aris_format(self, role_bullets: RoleBullets) -> ARISResult:
    """Check ARIS format compliance."""
```

**Option B:** Update prompt to use STAR (less work, but ARIS is better terminology)

**Option C:** Add a mapping comment explaining the terminology
```python
# NOTE: ARIS (Action-Result-Impact-Situation) is our internal terminology.
# Code still uses "STAR" naming for historical reasons.
# ARIS = STAR with different ordering (impact-first, situation-last)
```

---

### Priority 4: Add Word Count Validation (Medium Impact)

**Problem:** Prompt says "25-40 words" but there's no enforcement mechanism. Bullets can be too short (missing ARIS elements) or too long (verbose).

**Solution:** Add explicit word count instruction and Pydantic validation:

In prompt:
```
WORD COUNT REQUIREMENTS:
- Each bullet: 25-40 words (strictly enforced)
- Bullets under 20 words are REJECTED (likely missing ARIS elements)
- Bullets over 50 words are REJECTED (too verbose for ATS parsing)
- Include actual word count in JSON response for validation
```

In Pydantic model:
```python
@field_validator('text')
@classmethod
def validate_word_count(cls, v: str) -> str:
    """Validate bullet word count is in acceptable range."""
    word_count = len(v.split())
    if word_count < 20:
        raise ValueError(f"Bullet too short ({word_count} words, minimum 20)")
    if word_count > 50:
        raise ValueError(f"Bullet too long ({word_count} words, maximum 50)")
    return v
```

---

### Priority 5: Industry Vertical Matching (Medium Impact)

**Problem:** `role.industry` is available but not emphasized in the prompt. Cross-industry applications need jargon translation.

**Solution:** Add industry context section:

```python
def get_industry_guidance(source_industry: str, target_industry: str) -> str:
    """Generate guidance for cross-industry applications."""
    if source_industry.lower() == target_industry.lower():
        return f"Industry match: Both {source_industry}. Use industry-specific terminology."

    return f"""
=== INDUSTRY TRANSLATION ===
Your background: {source_industry}
Target company: {target_industry}

Cross-industry guidance:
- Translate {source_industry} jargon to {target_industry} equivalents
- Emphasize transferable patterns over domain-specific details
- Focus on universal impact metrics (revenue, efficiency, scale)
"""
```

---

### Priority 6: Merge Skills Sections (Low Impact)

**Problem:** Both `TECHNICAL SKILLS FROM JD` and `HARD SKILLS FROM THIS ROLE` are provided, causing redundancy and potential confusion about which to prioritize.

**Solution:** Merge into unified skills section with clear priority:

```python
def build_unified_skills_section(
    jd_skills: List[str],
    role_skills: List[str]
) -> str:
    """Create unified skills section with clear priority."""

    # Skills from JD that candidate has evidence for
    evidenced_jd_skills = set(jd_skills) & set(role_skills)

    # JD skills candidate doesn't have (don't integrate these)
    missing_jd_skills = set(jd_skills) - set(role_skills)

    # Candidate skills not in JD (use sparingly)
    additional_skills = set(role_skills) - set(jd_skills)

    return f"""
=== SKILLS TO INTEGRATE ===
PRIORITY 1 - JD skills you can evidence (INTEGRATE THESE):
{', '.join(evidenced_jd_skills)}

PRIORITY 2 - Your skills not in JD (use if naturally relevant):
{', '.join(additional_skills)}

DO NOT INTEGRATE - JD skills without evidence in this role:
{', '.join(missing_jd_skills)}
"""
```

---

## 6. Summary

### Improvement Priority Matrix

| Priority | Improvement | Effort | Impact | Status |
|----------|-------------|--------|--------|--------|
| 1 | Pre-map achievements to pain points | Medium | High | **IMPLEMENTED** |
| 2 | Role-category-specific examples | Low | High | Recommended |
| 3 | Fix ARIS/STAR terminology | Low | Medium | Recommended |
| 4 | Add word count validation | Low | Medium | Optional |
| 5 | Industry vertical matching | Low | Medium | Optional |
| 6 | Merge skills sections | Low | Low | Optional |
| **7** | **ATRIS/TARIS hybrid format** | Medium | High | **Analysis Complete** |

### Implementation Log

#### Priority 1: Achievement-to-Pain-Point Mapping - IMPLEMENTED (2025-12-02)

**Files Created:**
- `src/layer6_v2/achievement_mapper.py` - New module with `AchievementMapper` class
- `tests/unit/test_layer6_v2_achievement_mapper.py` - 26 unit tests

**Files Modified:**
- `src/layer6_v2/prompts/role_generation.py` - Integrated mapper into `build_role_generation_user_prompt()`

**How it works:**
1. Before building the prompt, achievements are mapped to pain points using keyword overlap + string similarity
2. The mapping is formatted and inserted into the user prompt
3. LLM receives explicit guidance on which achievements address which pain points
4. Uncovered pain points are flagged to prevent forced connections

### Key Insight

The current prompt architecture is fundamentally sound with strong anti-hallucination focus. The biggest opportunity is **pre-computation** - doing more analytical work before the LLM call to:

1. ~~Map achievements to pain points explicitly~~ **DONE**
2. Reconcile JD skills with candidate evidence
3. Provide role-category-specific examples

This reduces the LLM's cognitive load, improves consistency, and makes outputs more traceable.

---

## 7. Related Analysis: ATRIS/TARIS Bullet Format

A detailed analysis of bullet point formats has been conducted to evaluate ATS keyword optimization vs. human readability trade-offs.

**See:** [`bullet-format-analysis-aris-atris-taris.md`](./bullet-format-analysis-aris-atris-taris.md)

### Quick Summary

| Format | Structure | Best For | ATS Score |
|--------|-----------|----------|-----------|
| **ARIS** (current) | Action → Result → Impact → Situation | Leadership roles | 70% |
| **ATRIS** (proposed) | Action → Technology → Result → Impact → Situation | Technical IC roles | 90% |
| **TARIS** (selective) | Technology → Action → Result → Impact → Situation | Tech-centric achievements | 95% |

### Recommendation

Implement a **hybrid approach** that selects format based on:
1. `role_category` from ExtractedJD
2. Achievement type (technical vs. leadership)
3. JD keyword requirements

**Expected Impact:**
- +20-25% ATS keyword score for technical roles
- -10% readability trade-off (acceptable)
- NET POSITIVE for Staff/Principal Engineer targeting

---

## Appendix: File References

### Core Files
- Role Generator: `src/layer6_v2/role_generator.py`
- Prompts: `src/layer6_v2/prompts/role_generation.py`
- Types: `src/layer6_v2/types.py`
- Config: `src/common/config.py`
- ExtractedJD: `src/common/state.py:31`
- CV Loader: `src/layer6_v2/cv_loader.py`

### New Files (Priority 1 Implementation)
- Achievement Mapper: `src/layer6_v2/achievement_mapper.py`
- Achievement Mapper Tests: `tests/unit/test_layer6_v2_achievement_mapper.py`

### Related Reports
- Bullet Format Analysis: `reports/prompt-analysis/bullet-format-analysis-aris-atris-taris.md`
