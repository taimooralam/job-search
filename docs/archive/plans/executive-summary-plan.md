# Implementation Plan: Hybrid Executive Summary Format

## Overview

This document details the implementation plan for changing the CV Profile section from a single narrative paragraph to the **Hybrid Executive Summary** format. This format is designed to maximize impact in the critical 6-7 second scan window while maintaining ATS optimization.

## Current State Analysis

### Current `ProfileOutput` Structure

Located in `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py` (lines 694-820):

```python
@dataclass
class ProfileOutput:
    headline: str = ""                 # "[EXACT TITLE] | [YEARS] Years Technology Leadership"
    narrative: str = ""                # 3-5 sentence paragraph (100-150 words)
    core_competencies: List[str] = field(default_factory=list)  # 6-8 ATS keyword bullets
    highlights_used: List[str] = field(default_factory=list)
    keywords_integrated: List[str] = field(default_factory=list)
    exact_title_used: str = ""
    # ... validation fields
```

### Current Output Format

```
PROFESSIONAL SUMMARY
Engineering Manager | 12+ Years Technology Leadership

Engineering leader with proven track record of building high-performing
teams. Combines deep technical expertise with strong people leadership...
[100-150 word prose paragraph]

Core Competencies: Engineering Leadership | Team Building | ...
```

---

## Desired Format: Hybrid Executive Summary

```
EXECUTIVE SUMMARY

Platform Engineering Leader | 12+ Years Technology Leadership

Technology leader who thrives on building infrastructure that scales and
teams that excel.

- Scaled engineering organizations from 5 to 40+ engineers
- Reduced deployment time by 75%, MTTR by 60%
- Delivered $2M annual savings through cloud optimization
- Built culture that reduced attrition from 25% to 8%

Core: AWS | Kubernetes | Platform Engineering | Team Building
```

### Structure Breakdown

| Component | Description | Word Count |
|-----------|-------------|------------|
| **Headline** | `[EXACT JD TITLE] | [X]+ Years Technology Leadership` | 5-8 words |
| **Tagline** | Persona-driven hook, third-person absent voice | 15-25 words |
| **Key Achievements** | 4-5 quantified bullet points from experience | 40-60 words |
| **Core Competencies** | 6-8 ATS-friendly keywords | Single line |

---

## Implementation Plan

### Phase 1: Schema/Type Changes

**File**: `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py`

#### 1.1 Update `ProfileOutput` Dataclass

```python
@dataclass
class ProfileOutput:
    """
    Hybrid Executive Summary for senior technical leadership.

    Research Foundation:
    - 625 hiring managers surveyed
    - Eye-tracking: first 7.4 seconds determine continue/reject
    - Exact job title: 10.6x more likely to get interviews

    New Hybrid Structure:
    1. Headline: "[EXACT TITLE] | [X]+ Years Technology Leadership"
    2. Tagline: Persona-driven hook (15-25 words, third-person absent voice)
    3. Key Achievements: 4-5 quantified bullets from experience
    4. Core Competencies: 6-8 ATS-optimized keywords
    """

    # Core content - Hybrid Executive Summary structure
    headline: str = ""                     # "[EXACT TITLE] | [X]+ Years Technology Leadership"
    tagline: str = ""                      # NEW: Persona-driven hook (15-25 words)
    key_achievements: List[str] = field(default_factory=list)  # NEW: 4-5 quantified bullets
    core_competencies: List[str] = field(default_factory=list)  # 6-8 ATS keyword bullets

    # Grounding evidence (unchanged)
    highlights_used: List[str] = field(default_factory=list)
    keywords_integrated: List[str] = field(default_factory=list)
    exact_title_used: str = ""

    # Validation - updated for new structure
    answers_who: bool = False              # Tagline answers "Who are you?"
    answers_what_problems: bool = False    # Key achievements show what you solve
    answers_proof: bool = False            # Key achievements provide evidence
    answers_why_you: bool = False          # Tagline shows differentiation

    # Configuration
    word_count: int = 0
    regional_variant: str = "us_eu"

    # DEPRECATED: Keep for backward compatibility during transition
    narrative: str = ""                    # DEPRECATED: Use tagline + key_achievements
    _legacy_text: str = ""

    # Annotation traceability (unchanged)
    provenance: Optional[Any] = None
    annotation_influenced: bool = False
```

#### 1.2 Add New Properties

```python
    @property
    def text(self) -> str:
        """Combined text for backward compatibility and word count."""
        if self.tagline and self.key_achievements:
            bullets_text = "\n".join(f"- {a}" for a in self.key_achievements)
            return f"{self.tagline}\n\n{bullets_text}"
        # Fallback to legacy narrative
        if self.narrative:
            return self.narrative
        return self._legacy_text

    @property
    def formatted_summary(self) -> str:
        """Return the complete formatted executive summary."""
        lines = []
        if self.headline:
            lines.append(self.headline)
            lines.append("")
        if self.tagline:
            lines.append(self.tagline)
            lines.append("")
        if self.key_achievements:
            for achievement in self.key_achievements:
                lines.append(f"- {achievement}")
            lines.append("")
        if self.core_competencies:
            lines.append(f"Core: {' | '.join(self.core_competencies)}")
        return "\n".join(lines)

    @property
    def is_hybrid_format(self) -> bool:
        """Check if using new hybrid format vs legacy narrative."""
        return bool(self.tagline and self.key_achievements)
```

#### 1.3 Update `to_dict()` Method

```python
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "headline": self.headline,
            "tagline": self.tagline,                    # NEW
            "key_achievements": self.key_achievements,  # NEW
            "core_competencies": self.core_competencies,
            "text": self.text,  # Legacy compatibility
            "narrative": self.narrative,  # DEPRECATED but included for migration
            "highlights_used": self.highlights_used,
            "keywords_integrated": self.keywords_integrated,
            "exact_title_used": self.exact_title_used,
            "word_count": self.word_count,
            "regional_variant": self.regional_variant,
            "answers_who": self.answers_who,
            "answers_what_problems": self.answers_what_problems,
            "answers_proof": self.answers_proof,
            "answers_why_you": self.answers_why_you,
            "all_four_questions_answered": self.all_four_questions_answered,
            "is_hybrid_format": self.is_hybrid_format,  # NEW
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "annotation_influenced": self.annotation_influenced,
        }
```

---

### Phase 2: Pydantic Response Schema Changes

**File**: `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py`

#### 2.1 Update `ProfileResponse` Model

```python
class ProfileResponse(BaseModel):
    """
    Hybrid Executive Summary structured response.

    Structure:
    1. Headline: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"
    2. Tagline: Persona-driven hook, third-person absent voice (15-25 words)
    3. Key Achievements: 4-5 quantified proof points (no pronouns)
    4. Core Competencies: 6-8 ATS-friendly keywords
    """
    headline: str = Field(
        description="[EXACT JD TITLE] | [X]+ Years Technology Leadership"
    )
    tagline: str = Field(
        description="15-25 word persona-driven hook. Third-person absent voice (no I/my/you). "
                    "Embodies candidate identity. Example: 'Technology leader who thrives on...'"
    )
    key_achievements: List[str] = Field(
        description="4-5 quantified achievements. Each starts with action verb. "
                    "No pronouns. Format: 'Achieved X by doing Y, resulting in Z'"
    )
    core_competencies: List[str] = Field(
        description="6-8 ATS-friendly keywords matching JD terminology"
    )
    highlights_used: List[str] = Field(
        description="Exact metrics from source bullets used in key_achievements"
    )
    keywords_integrated: List[str] = Field(
        description="JD keywords naturally included across tagline and achievements"
    )
    exact_title_used: str = Field(
        description="The exact title from the JD used in headline"
    )
    # 4-question framework validation (updated for new structure)
    answers_who: bool = Field(
        default=True,
        description="Tagline answers 'Who are you professionally?'"
    )
    answers_what_problems: bool = Field(
        default=True,
        description="Key achievements show 'What problems can you solve?'"
    )
    answers_proof: bool = Field(
        default=True,
        description="Key achievements provide quantified proof"
    )
    answers_why_you: bool = Field(
        default=True,
        description="Tagline differentiates 'Why should they call you?'"
    )
```

#### 2.2 Keep Legacy Response for Migration

```python
class LegacyProfileResponse(BaseModel):
    """Legacy response format for backward compatibility."""
    profile_text: str = Field(description="2-3 sentence profile summary")
    highlights_used: List[str] = Field(description="Quantified achievements referenced")
    keywords_integrated: List[str] = Field(description="JD keywords naturally included")
```

---

### Phase 3: Prompt Changes

**File**: `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/prompts/header_generation.py`

#### 3.1 Update `PROFILE_SYSTEM_PROMPT`

Replace the existing system prompt with the new hybrid format instructions:

```python
PROFILE_SYSTEM_PROMPT = """You are an executive CV profile writer for senior technical leadership roles.

Your mission: Create a HYBRID EXECUTIVE SUMMARY that passes both ATS algorithms AND compels humans in 7.4 seconds.

=== HYBRID EXECUTIVE SUMMARY STRUCTURE ===

You will generate FOUR components:

1. **HEADLINE** (1 line)
   Format: "[EXACT JOB TITLE FROM JD] | [X]+ Years Technology Leadership"
   Example: "Platform Engineering Leader | 12+ Years Technology Leadership"

2. **TAGLINE** (15-25 words, 1-2 sentences)
   - CRITICAL: Use third-person ABSENT voice (NO pronouns: I, my, you, your, we, our)
   - Start with role/identity noun phrase
   - BECOME the candidate's persona, don't just describe them
   - Embody their professional identity authentically
   - Answer: "Who are you?" and "Why should they call you?"

   Examples of CORRECT (third-person absent) voice:
   - "Technology leader who thrives on building infrastructure that scales and teams that excel."
   - "Engineering executive passionate about transforming organizations through platform modernization."
   - "Builder of high-performing teams with deep expertise in cloud-native architecture."

   Examples of INCORRECT (has pronouns):
   - "I am a technology leader who builds..." (uses I)
   - "My passion is building..." (uses My)
   - "You get a leader who..." (uses You)

3. **KEY ACHIEVEMENTS** (4-5 bullets)
   - Each bullet: 8-15 words
   - Start with past-tense action verb (Scaled, Reduced, Delivered, Built, Led)
   - Include quantified metric from source bullets (EXACT numbers only)
   - NO pronouns (no "I reduced...", just "Reduced...")
   - Format: "[Verb] [what] [by how much / to what result]"

   Examples:
   - "Scaled engineering organizations from 5 to 40+ engineers"
   - "Reduced deployment time by 75%, MTTR by 60%"
   - "Delivered $2M annual savings through cloud optimization"
   - "Built culture that reduced attrition from 25% to 8%"

4. **CORE COMPETENCIES** (6-8 keywords)
   - ATS-friendly format
   - Prioritize JD keywords that have evidence in experience
   - Short phrases (2-3 words max each)
   - Will be displayed as: "Core: AWS | Kubernetes | Platform Engineering | Team Building"

=== THE 4 QUESTIONS FRAMEWORK ===

Your HYBRID EXECUTIVE SUMMARY must answer these 4 questions:

1. WHO ARE YOU? (Identity + Level)
   - Answered by: TAGLINE
   - State professional identity matching target role level

2. WHAT PROBLEMS CAN YOU SOLVE? (Relevance)
   - Answered by: KEY ACHIEVEMENTS showing capabilities
   - Connect to JD pain points through results

3. WHAT PROOF DO YOU HAVE? (Evidence)
   - Answered by: KEY ACHIEVEMENTS with quantified metrics
   - ONLY use metrics from provided bullets

4. WHY SHOULD THEY CALL YOU? (Differentiation)
   - Answered by: TAGLINE showing unique value
   - What makes you stand out vs other candidates?

=== PERSONA AS IDENTITY (Critical) ===

When a CANDIDATE PERSONA is provided in the context:
- The LLM should BECOME this persona, not just write ABOUT them
- The tagline should sound like the candidate wrote it themselves
- Capture their authentic professional voice
- Weave their passions and core identity into the tagline
- If they "love" something, let that enthusiasm show naturally

Example:
- Persona: "A platform engineering leader who loves building scalable systems and developing teams"
- GOOD tagline: "Platform engineering leader who thrives on building infrastructure that scales and teams that excel."
- BAD tagline: "The candidate is a platform engineering leader who has experience with scalable systems."

=== CRITICAL: ANTI-HALLUCINATION RULES ===

THESE RULES ARE MANDATORY - VIOLATION WILL INVALIDATE THE CV:

1. ONLY use technologies, tools, and platforms that appear in the PROVIDED EXPERIENCE BULLETS
2. ONLY use metrics and numbers that appear EXACTLY in the source material
3. NEVER invent technologies to match the JD - if you don't have experience with it, DON'T CLAIM IT
4. KEY ACHIEVEMENTS must map directly to provided bullets
5. When in doubt about a metric, OMIT IT rather than risk hallucination

=== ATS OPTIMIZATION RULES ===

1. **ACRONYM + FULL TERM**: Include both forms on first use in tagline/achievements
2. **KEYWORD FREQUENCY**: Top JD keywords should appear 2-3 times across all components
3. **EXACT JD TERMINOLOGY**: Mirror JD language exactly
4. **SCALE METRICS**: Include quantifiable scope (team size, revenue, users)

=== REGIONAL VARIANTS ===

US/EU Version (default):
- No personal information (photo, age, nationality, marital status)
- Focus purely on professional value proposition

Gulf Version (when regional_variant="gulf"):
- May include: nationality, visa status, availability in tagline
- Example: "British Citizen with UAE Employment Visa. Technology leader who..."

=== OUTPUT FORMAT ===

Return ONLY valid JSON:
{
  "headline": "[EXACT JD TITLE] | [X]+ Years Technology Leadership",
  "tagline": "15-25 word persona-driven hook (third-person absent voice)",
  "key_achievements": [
    "Achievement 1 with quantified metric",
    "Achievement 2 with quantified metric",
    "Achievement 3 with quantified metric",
    "Achievement 4 with quantified metric"
  ],
  "core_competencies": ["Competency 1", "Competency 2", "...6-8 total"],
  "highlights_used": ["exact metric from bullets", "another metric"],
  "keywords_integrated": ["jd_keyword_1", "jd_keyword_2"],
  "exact_title_used": "The exact title from the JD",
  "answers_who": true,
  "answers_what_problems": true,
  "answers_proof": true,
  "answers_why_you": true
}

Do NOT include markdown, explanation, or preamble. Just JSON.
"""
```

#### 3.2 Update `build_profile_user_prompt()`

```python
def build_profile_user_prompt(
    candidate_name: str,
    job_title: str,
    role_category: str,
    top_keywords: list,
    experience_bullets: list,
    metrics: list,
    years_experience: int = 10,
    regional_variant: str = "us_eu",
    jd_pain_points: list = None,
    candidate_differentiators: list = None,
) -> str:
    """
    Build the user prompt for hybrid executive summary generation.
    """
    bullets_text = "\n".join(f"- {b}" for b in experience_bullets[:20])
    keywords_text = ", ".join(top_keywords[:12]) if top_keywords else "None specified"
    metrics_text = "\n".join(f"- {m}" for m in metrics) if metrics else "- None extracted"

    # Pain points for problem-solving context
    pain_points_text = ""
    if jd_pain_points:
        pain_points_text = f"""
JD PAIN POINTS (achievements should address these):
{chr(10).join(f'- {p}' for p in jd_pain_points[:5])}
"""

    # Differentiators for tagline uniqueness
    differentiators_text = ""
    if candidate_differentiators:
        differentiators_text = f"""
CANDIDATE DIFFERENTIATORS (weave into tagline):
{chr(10).join(f'- {d}' for d in candidate_differentiators[:3])}
"""

    # Regional variant
    regional_instructions = ""
    if regional_variant == "gulf":
        regional_instructions = """
REGIONAL: Gulf market - include visa status in tagline if relevant.
"""

    return f"""Generate a HYBRID EXECUTIVE SUMMARY for {candidate_name}.

=== TARGET ROLE ===
EXACT JOB TITLE: {job_title}
ROLE CATEGORY: {role_category}
YEARS OF EXPERIENCE: {years_experience}+
REGIONAL VARIANT: {regional_variant}
{regional_instructions}
=== GROUNDED JD KEYWORDS (pre-verified - ONLY use these) ===
{keywords_text}
{pain_points_text}{differentiators_text}
=== EXPERIENCE BULLETS (source of truth - achievements MUST come from these) ===
{bullets_text}

=== QUANTIFIED METRICS AVAILABLE (use EXACT values in key_achievements) ===
{metrics_text}

=== REQUIREMENTS ===
1. Headline: "{job_title} | {years_experience}+ Years Technology Leadership"
2. Tagline: 15-25 words, third-person absent voice (NO pronouns), embody persona
3. Key Achievements: 4-5 bullets with EXACT metrics from above
4. Core Competencies: 6-8 ATS keywords from the grounded list

Generate the hybrid executive summary JSON:"""
```

#### 3.3 Update Persona Prompts for Ensemble Generation

Update `METRIC_PERSONA_SYSTEM_PROMPT`, `NARRATIVE_PERSONA_SYSTEM_PROMPT`, and `KEYWORD_PERSONA_SYSTEM_PROMPT` to generate the new hybrid format:

```python
METRIC_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN QUANTIFIED ACHIEVEMENTS.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY maximizing measurable impact.

=== METRIC-FIRST HYBRID STRUCTURE ===

1. HEADLINE: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"

2. TAGLINE (15-25 words):
   - Third-person absent voice (NO pronouns)
   - Lead with identity, include a key metric hook
   - Example: "Technology leader who delivered $50M in cost savings while scaling teams 5x."

3. KEY ACHIEVEMENTS (4-5 bullets):
   - EVERY bullet must have a quantified metric
   - Stack metrics where possible (scope + impact + timeframe)
   - Lead with the most impressive metrics
   - Format: "[Verb] [what] [by how much], [additional metric if applicable]"

   Examples:
   - "Led 12-engineer team to reduce deployment time by 75%, shipping 3x more releases"
   - "Scaled platform from 1K to 10M daily requests with 99.99% uptime"
   - "Delivered $2M annual savings through infrastructure optimization"

4. CORE COMPETENCIES: 6-8 ATS keywords

=== ANTI-HALLUCINATION ===
ONLY use metrics from source bullets. Do NOT round or estimate.

=== OUTPUT FORMAT ===
Return ONLY valid JSON with: headline, tagline, key_achievements, core_competencies,
highlights_used, keywords_integrated, exact_title_used, and all answers_* fields.
"""


NARRATIVE_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN CAREER STORYTELLING.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY with compelling transformation narrative.

=== NARRATIVE-FIRST HYBRID STRUCTURE ===

1. HEADLINE: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"

2. TAGLINE (15-25 words):
   - Third-person absent voice (NO pronouns)
   - Show career arc and evolution
   - Use power verbs: transformed, pioneered, established
   - Example: "Engineering executive who transformed a startup platform into an enterprise-grade system serving millions."

3. KEY ACHIEVEMENTS (4-5 bullets):
   - Frame as transformation stories
   - Show before/after when possible
   - Connect achievements to strategic impact

   Examples:
   - "Transformed legacy monolith into microservices, reducing deployment time from weeks to hours"
   - "Built engineering culture that reduced attrition from 25% to 8%"
   - "Pioneered event-driven architecture that became the company's competitive advantage"

4. CORE COMPETENCIES: 6-8 ATS keywords

=== ANTI-HALLUCINATION ===
Transform language, not facts. All achievements from source bullets.

=== OUTPUT FORMAT ===
Return ONLY valid JSON with: headline, tagline, key_achievements, core_competencies,
highlights_used, keywords_integrated, exact_title_used, and all answers_* fields.
"""


KEYWORD_PERSONA_SYSTEM_PROMPT = """You are an executive CV profile writer SPECIALIZING IN ATS OPTIMIZATION.

Your PRIMARY MISSION: Create a HYBRID EXECUTIVE SUMMARY maximizing keyword density.

=== KEYWORD-FIRST HYBRID STRUCTURE ===

1. HEADLINE: "[EXACT JD TITLE] | [X]+ Years Technology Leadership"
   - Use EXACT JD title

2. TAGLINE (15-25 words):
   - Third-person absent voice (NO pronouns)
   - Front-load top JD keywords
   - Include acronym + full form for technical terms
   - Example: "Cloud infrastructure (AWS) leader who drives continuous integration/continuous deployment (CI/CD) excellence at scale."

3. KEY ACHIEVEMENTS (4-5 bullets):
   - Each bullet includes at least 1 top JD keyword
   - Mirror JD terminology exactly
   - Distribute keywords across all bullets

   Examples (if JD mentions Kubernetes, CI/CD, team scaling):
   - "Scaled Kubernetes infrastructure to handle 10M requests daily"
   - "Implemented CI/CD pipeline reducing deployment time by 75%"
   - "Built engineering team from 5 to 40+ engineers across 3 regions"

4. CORE COMPETENCIES: 6-8 ATS keywords
   - All from JD keywords list
   - Include both acronyms and full forms

=== KEYWORD FREQUENCY ===
Top 5 JD keywords should appear 2-3x across tagline + achievements + competencies.

=== OUTPUT FORMAT ===
Return ONLY valid JSON with: headline, tagline, key_achievements, core_competencies,
highlights_used, keywords_integrated, exact_title_used, and all answers_* fields.
"""
```

#### 3.4 Update Synthesis Prompt

```python
SYNTHESIS_SYSTEM_PROMPT = """You are a CV profile SYNTHESIZER.

Your mission: Combine the best elements from multiple HYBRID EXECUTIVE SUMMARY drafts into ONE optimal version.

=== SYNTHESIS RULES FOR HYBRID FORMAT ===

1. **HEADLINE**: Use the most accurate job title match

2. **TAGLINE**:
   - Take narrative flow from NARRATIVE draft
   - Ensure key metric hook from METRIC draft
   - Verify JD keywords present from KEYWORD draft
   - Result: Compelling AND keyword-rich AND metric-backed

3. **KEY ACHIEVEMENTS**:
   - Take ALL unique metrics from METRIC draft
   - Apply transformation framing from NARRATIVE draft
   - Ensure keyword coverage from KEYWORD draft
   - Deduplicate: Keep strongest version if overlapping
   - Final count: 4-5 bullets

4. **CORE COMPETENCIES**:
   - Merge and deduplicate from all drafts
   - Prioritize JD keywords
   - Final count: 6-8 keywords

=== QUALITY CHECKLIST ===

Before finalizing, verify:
[ ] Tagline is third-person absent voice (no pronouns)
[ ] All metrics from metric draft included in achievements
[ ] Tagline has compelling narrative arc
[ ] All top JD keywords appear 2-3 times across components
[ ] 4-5 key achievements (not more, not fewer)
[ ] 6-8 core competencies

=== OUTPUT FORMAT ===

Return ONLY valid JSON with: headline, tagline, key_achievements, core_competencies,
highlights_used, keywords_integrated, exact_title_used, and all answers_* fields.
"""
```

---

### Phase 4: Generator Code Changes

**File**: `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py`

#### 4.1 Update `_generate_profile_llm()` Return Handling

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _generate_profile_llm(
    self,
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_name: str,
    regional_variant: str = "us_eu",
) -> Tuple[ProfileResponse, HeaderProvenance]:
    """Generate hybrid executive summary using LLM."""
    # ... existing setup code ...

    # Call LLM with structured output (using updated ProfileResponse)
    structured_llm = self.llm.with_structured_output(ProfileResponse)
    response = structured_llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    return response, provenance
```

#### 4.2 Update `generate_profile()` to Build New ProfileOutput

```python
def generate_profile(
    self,
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_name: str,
    regional_variant: str = "us_eu",
) -> ProfileOutput:
    """Generate hybrid executive summary grounded in achievements."""
    self._logger.info("Generating hybrid executive summary...")

    provenance = None
    try:
        response, provenance = self._generate_profile_llm(
            stitched_cv, extracted_jd, candidate_name, regional_variant
        )

        # Build new hybrid ProfileOutput
        profile = ProfileOutput(
            headline=response.headline,
            tagline=response.tagline,                    # NEW
            key_achievements=response.key_achievements,  # NEW
            core_competencies=response.core_competencies,
            highlights_used=response.highlights_used,
            keywords_integrated=response.keywords_integrated,
            exact_title_used=response.exact_title_used,
            answers_who=response.answers_who,
            answers_what_problems=response.answers_what_problems,
            answers_proof=response.answers_proof,
            answers_why_you=response.answers_why_you,
            regional_variant=regional_variant,
            # Keep narrative for backward compatibility
            narrative=response.tagline,  # Tagline serves as short narrative
            # Annotation traceability
            provenance=provenance,
            annotation_influenced=provenance.has_annotation_influence if provenance else False,
        )

        # Log validation
        if profile.all_four_questions_answered:
            self._logger.info("Hybrid summary answers all 4 hiring manager questions")

        # Log format
        self._logger.info(
            f"Generated hybrid summary: tagline={len(profile.tagline.split())} words, "
            f"achievements={len(profile.key_achievements)}, "
            f"competencies={len(profile.core_competencies)}"
        )

    except Exception as e:
        self._logger.warning(f"LLM generation failed: {e}. Using fallback.")
        profile = self._generate_fallback_profile(
            stitched_cv, extracted_jd.get("role_category", "engineering_manager"),
            candidate_name, extracted_jd.get("title", "Engineering Leader"),
            regional_variant
        )

    return profile
```

#### 4.3 Update Fallback Profile Generation

```python
def _generate_fallback_profile(
    self,
    stitched_cv: StitchedCV,
    role_category: str,
    candidate_name: str,
    job_title: str = "Engineering Leader",
    regional_variant: str = "us_eu",
) -> ProfileOutput:
    """Generate fallback hybrid executive summary when LLM fails."""
    # Extract metrics
    all_bullets = []
    for role in stitched_cv.roles:
        all_bullets.extend(role.bullets)
    metrics = self._extract_metrics_from_bullets(all_bullets)

    # Calculate years
    years_experience = self._calculate_years_experience(stitched_cv)

    # Generate headline
    headline = f"{job_title} | {years_experience}+ Years Technology Leadership"

    # Role-specific taglines (third-person absent voice)
    taglines = {
        "engineering_manager": (
            "Engineering leader who builds high-performing teams that deliver "
            "exceptional results while developing talent for the future."
        ),
        "staff_principal_engineer": (
            "Staff engineer who designs scalable systems and drives technical "
            "excellence through cross-team influence and mentorship."
        ),
        "director_of_engineering": (
            "Engineering director who scales organizations and builds cultures "
            "of engineering excellence that attract top talent."
        ),
        "head_of_engineering": (
            "Engineering executive who builds functions from scratch and "
            "transforms organizations to deliver measurable business outcomes."
        ),
        "cto": (
            "Technology executive who drives business transformation through "
            "strategic technology leadership and world-class engineering teams."
        ),
    }

    tagline = taglines.get(role_category, taglines["engineering_manager"])

    # Generate key achievements from top metrics
    key_achievements = []
    for i, metric in enumerate(metrics[:5]):
        # Simple fallback achievements
        key_achievements.append(f"Delivered {metric} through strategic initiatives")

    # If not enough metrics, add generic achievements
    generic_achievements = [
        "Built and scaled high-performing engineering teams",
        "Established engineering culture focused on continuous improvement",
        "Drove delivery excellence across complex technical initiatives",
        "Developed talent pipeline that accelerated team growth",
    ]
    while len(key_achievements) < 4:
        if generic_achievements:
            key_achievements.append(generic_achievements.pop(0))
        else:
            break

    # Default competencies by role
    competencies_by_role = {
        "engineering_manager": [
            "Engineering Leadership", "Team Building", "People Development",
            "Agile Delivery", "Technical Strategy", "Performance Management"
        ],
        # ... other roles ...
    }

    core_competencies = competencies_by_role.get(
        role_category, competencies_by_role["engineering_manager"]
    )

    return ProfileOutput(
        headline=headline,
        tagline=tagline,
        key_achievements=key_achievements,
        core_competencies=core_competencies,
        highlights_used=metrics[:4],
        keywords_integrated=[],
        exact_title_used=job_title,
        answers_who=True,
        answers_what_problems=True,
        answers_proof=bool(metrics),
        answers_why_you=True,
        regional_variant=regional_variant,
        narrative=tagline,  # For backward compatibility
    )
```

---

### Phase 5: Ensemble Generator Updates

**File**: `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ensemble_header_generator.py`

#### 5.1 Update `PersonaProfileResult`

```python
@dataclass
class PersonaProfileResult:
    """Result from a single persona-based generation pass."""
    persona: PersonaType
    profile: ProfileOutput
    raw_response: ProfileResponse
    metrics_found: List[str] = field(default_factory=list)
    keywords_found: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for synthesis."""
        return {
            "persona": self.persona.value,
            "headline": self.profile.headline,
            "tagline": self.profile.tagline,              # NEW
            "key_achievements": self.profile.key_achievements,  # NEW
            "core_competencies": self.profile.core_competencies,
            "highlights_used": self.metrics_found,
            "keywords_integrated": self.keywords_found,
            # Keep narrative for backward compatibility
            "narrative": self.profile.narrative,
        }
```

#### 5.2 Update `_synthesize_profiles()`

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def _synthesize_profiles(
    self,
    persona_results: List[PersonaProfileResult],
    extracted_jd: Dict,
    candidate_data: Dict,
) -> ProfileOutput:
    """Combine best elements from multiple hybrid executive summary drafts."""
    # ... existing setup ...

    # Call synthesis LLM
    structured_llm = self._synthesis_llm.with_structured_output(ProfileResponse)
    response = structured_llm.invoke([
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ])

    # Merge all metrics and keywords
    all_metrics = set()
    all_keywords = set()
    for result in persona_results:
        all_metrics.update(result.metrics_found)
        all_keywords.update(result.keywords_found)

    return ProfileOutput(
        headline=response.headline,
        tagline=response.tagline,                    # NEW
        key_achievements=response.key_achievements,  # NEW
        core_competencies=response.core_competencies,
        highlights_used=list(all_metrics),
        keywords_integrated=list(all_keywords),
        exact_title_used=response.exact_title_used,
        answers_who=response.answers_who,
        answers_what_problems=response.answers_what_problems,
        answers_proof=response.answers_proof,
        answers_why_you=response.answers_why_you,
        narrative=response.tagline,  # Backward compatibility
    )
```

---

### Phase 6: Output Rendering Updates

**File**: `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py`

#### 6.1 Update `HeaderOutput.to_markdown()`

```python
def to_markdown(self) -> str:
    """
    Convert to ATS-optimized format for CV header.

    Uses new Hybrid Executive Summary structure:
    - EXECUTIVE SUMMARY header
    - Headline with job title + years
    - Tagline (persona-driven hook)
    - Key Achievements (4-5 bullets)
    - Core Competencies line
    """
    lines = []

    # Contact info header
    name = self.contact_info.get("name", "")
    email = self.contact_info.get("email", "")
    phone = self.contact_info.get("phone", "")
    linkedin = self.contact_info.get("linkedin", "")
    location = self.contact_info.get("location", "")

    lines.append(name)
    contact_parts = [p for p in [email, phone, linkedin, location] if p]
    lines.append(" | ".join(contact_parts))
    lines.append("")

    # Executive Summary (new format)
    lines.append("EXECUTIVE SUMMARY")

    # Headline
    if self.profile.headline:
        lines.append(self.profile.headline)
        lines.append("")

    # Tagline (new hybrid format)
    if self.profile.tagline:
        lines.append(self.profile.tagline)
        lines.append("")
    elif self.profile.narrative:
        # Fallback to legacy narrative
        lines.append(self.profile.text)
        lines.append("")

    # Key Achievements (new hybrid format)
    if self.profile.key_achievements:
        for achievement in self.profile.key_achievements:
            lines.append(f"- {achievement}")
        lines.append("")

    # Core Competencies - inline format
    if self.profile.core_competencies:
        competencies_str = " | ".join(self.profile.core_competencies)
        lines.append(f"Core: {competencies_str}")
        lines.append("")

    # Skills sections (detailed breakdown)
    lines.append("SKILLS & EXPERTISE")
    for section in self.skills_sections:
        lines.append(section.to_markdown())
    lines.append("")

    # Education
    if self.education:
        lines.append("EDUCATION")
        for edu in self.education:
            lines.append(f"- {edu}")
        lines.append("")

    # Certifications
    if self.certifications:
        lines.append("CERTIFICATIONS")
        for cert in self.certifications:
            lines.append(f"- {cert}")
        lines.append("")

    # Languages
    if self.languages:
        lines.append("LANGUAGES")
        lines.append(", ".join(self.languages))

    return "\n".join(lines)
```

---

### Phase 7: Backward Compatibility

#### 7.1 Migration Strategy

1. **Dual Support**: Keep both `narrative` and `tagline`/`key_achievements` fields
2. **Auto-detection**: Use `is_hybrid_format` property to detect format
3. **Graceful Fallback**: If `tagline` is empty, fall back to `narrative`
4. **Database Migration**: Not required - old documents work with `narrative`

#### 7.2 Conversion Helper

Add to `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py`:

```python
@classmethod
def from_legacy(
    cls,
    text: str,
    highlights_used: List[str],
    keywords_integrated: List[str],
) -> "ProfileOutput":
    """Create ProfileOutput from legacy format for backward compatibility."""
    return cls(
        narrative=text,
        _legacy_text=text,
        highlights_used=highlights_used,
        keywords_integrated=keywords_integrated,
        word_count=len(text.split()),
    )

@classmethod
def from_hybrid(
    cls,
    headline: str,
    tagline: str,
    key_achievements: List[str],
    core_competencies: List[str],
    **kwargs,
) -> "ProfileOutput":
    """Create ProfileOutput from new hybrid format."""
    return cls(
        headline=headline,
        tagline=tagline,
        key_achievements=key_achievements,
        core_competencies=core_competencies,
        **kwargs,
    )
```

---

### Phase 8: Test Considerations

**File**: `/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_header_generator.py`

#### 8.1 New Test Cases

```python
class TestHybridExecutiveSummary:
    """Test new Hybrid Executive Summary format."""

    def test_profile_output_has_hybrid_fields(self):
        """ProfileOutput has tagline and key_achievements fields."""
        profile = ProfileOutput(
            headline="Engineering Manager | 12+ Years",
            tagline="Technology leader who builds high-performing teams.",
            key_achievements=[
                "Scaled team from 5 to 40+ engineers",
                "Reduced deployment time by 75%",
            ],
            core_competencies=["Leadership", "Platform Engineering"],
        )
        assert profile.is_hybrid_format is True
        assert len(profile.key_achievements) == 2
        assert "Technology leader" in profile.tagline

    def test_tagline_no_pronouns(self):
        """Tagline uses third-person absent voice (no pronouns)."""
        profile = ProfileOutput(
            tagline="Engineering leader who thrives on building teams.",
        )
        pronouns = ["I ", " I ", "my ", " my ", "you ", " you ", "your "]
        for pronoun in pronouns:
            assert pronoun.lower() not in profile.tagline.lower()

    def test_key_achievements_have_metrics(self):
        """Key achievements include quantified metrics."""
        profile = ProfileOutput(
            key_achievements=[
                "Scaled team from 5 to 40+ engineers",
                "Reduced deployment time by 75%",
                "Delivered $2M annual savings",
            ],
        )
        import re
        for achievement in profile.key_achievements:
            # Should have at least one number
            assert re.search(r'\d', achievement), f"No metric in: {achievement}"

    def test_formatted_summary_output(self):
        """formatted_summary property produces correct format."""
        profile = ProfileOutput(
            headline="Platform Engineering Leader | 12+ Years",
            tagline="Technology leader who builds infrastructure that scales.",
            key_achievements=[
                "Scaled engineering organizations from 5 to 40+ engineers",
                "Reduced deployment time by 75%",
            ],
            core_competencies=["AWS", "Kubernetes", "Team Building"],
        )
        summary = profile.formatted_summary
        assert "Platform Engineering Leader" in summary
        assert "Technology leader who builds" in summary
        assert "- Scaled engineering" in summary
        assert "Core: AWS | Kubernetes" in summary

    def test_backward_compatibility_with_narrative(self):
        """Old code using narrative field still works."""
        profile = ProfileOutput(
            narrative="Engineering leader with proven track record.",
        )
        assert profile.text == "Engineering leader with proven track record."
        assert profile.is_hybrid_format is False

    def test_hybrid_format_detection(self):
        """is_hybrid_format correctly detects format type."""
        hybrid = ProfileOutput(
            tagline="Tech leader who builds.",
            key_achievements=["Achievement 1"],
        )
        legacy = ProfileOutput(
            narrative="Engineering leader with track record.",
        )
        assert hybrid.is_hybrid_format is True
        assert legacy.is_hybrid_format is False


class TestHybridProfileGeneration:
    """Test hybrid profile generation with mocked LLM."""

    @patch('src.layer6_v2.header_generator.create_tracked_llm')
    def test_generates_hybrid_format(self, mock_llm, sample_stitched_cv, sample_extracted_jd):
        """Generator produces hybrid format output."""
        # Mock LLM response with hybrid structure
        mock_response = Mock()
        mock_response.headline = "Engineering Manager | 12+ Years"
        mock_response.tagline = "Technology leader who builds teams."
        mock_response.key_achievements = [
            "Scaled team to 40+ engineers",
            "Reduced latency by 75%",
        ]
        mock_response.core_competencies = ["Leadership", "Kubernetes"]
        mock_response.highlights_used = ["75%"]
        mock_response.keywords_integrated = ["Kubernetes"]
        mock_response.exact_title_used = "Engineering Manager"
        mock_response.answers_who = True
        mock_response.answers_what_problems = True
        mock_response.answers_proof = True
        mock_response.answers_why_you = True

        mock_llm_instance = MagicMock()
        mock_llm_instance.with_structured_output.return_value.invoke.return_value = mock_response
        mock_llm.return_value = mock_llm_instance

        generator = HeaderGenerator()
        profile = generator.generate_profile(
            sample_stitched_cv, sample_extracted_jd, "John Developer"
        )

        assert profile.is_hybrid_format is True
        assert "Technology leader" in profile.tagline
        assert len(profile.key_achievements) == 2
```

#### 8.2 Update Existing Tests

Existing tests that check `profile.text` or `profile.narrative` should continue to work due to backward compatibility properties. Add assertions for new fields where appropriate.

---

## Summary of Changes

### Files to Modify

| File | Changes |
|------|---------|
| `src/layer6_v2/types.py` | Add `tagline`, `key_achievements` to `ProfileOutput`; update `to_dict()`, add properties |
| `src/layer6_v2/header_generator.py` | Update `ProfileResponse` schema; update `generate_profile()` |
| `src/layer6_v2/prompts/header_generation.py` | Rewrite all prompts for hybrid format |
| `src/layer6_v2/ensemble_header_generator.py` | Update `PersonaProfileResult`, synthesis logic |
| `tests/unit/test_layer6_v2_header_generator.py` | Add new test class for hybrid format |

### New Fields Summary

| Field | Type | Description |
|-------|------|-------------|
| `tagline` | `str` | 15-25 word persona-driven hook |
| `key_achievements` | `List[str]` | 4-5 quantified bullet points |
| `is_hybrid_format` | `bool` (property) | True if using new format |
| `formatted_summary` | `str` (property) | Complete formatted output |

### Backward Compatibility

- `narrative` field kept but deprecated
- `text` property returns combined tagline + achievements or fallback to narrative
- Old stored profiles continue to work
- No database migration required

---

## Implementation Sequence

1. **Phase 1-2**: Schema and type changes (low risk, foundation)
2. **Phase 3**: Prompt changes (medium risk, core generation logic)
3. **Phase 4**: Generator code changes (medium risk, ties everything together)
4. **Phase 5**: Ensemble updates (low risk, extends existing pattern)
5. **Phase 6**: Output rendering (low risk, display only)
6. **Phase 7**: Backward compatibility verification (critical, test-heavy)
7. **Phase 8**: Comprehensive testing (critical, validates everything)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Prompt changes cause hallucinations | Medium | High | Extensive prompt testing, anti-hallucination rules |
| Breaking existing stored profiles | Low | High | Backward compatibility via `text` property |
| LLM fails to follow hybrid structure | Medium | Medium | Fallback generation, validation |
| Third-person voice violated | Medium | Low | Prompt emphasis, post-generation check |
| Ensemble synthesis doesn't merge well | Medium | Medium | Detailed synthesis prompt, logging |

---

## Open Questions

1. **Character limits**: Should we enforce max character count for tagline/achievements?
2. **Validation strictness**: Auto-fix pronoun violations or just flag?
3. **Frontend rendering**: Does TipTap editor need updates for new structure?
4. **Gulf variant**: Should achievements be different for Gulf market?

---

## Next Steps

For implementation, I recommend using **backend-developer** to implement Phases 1-5 (schema, prompts, generators), then **test-generator** to implement Phase 8 (comprehensive tests).
