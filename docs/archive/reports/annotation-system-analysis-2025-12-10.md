# Annotation System Analysis - Full Technical Deep-Dive

**Date**: 2025-12-10
**Author**: Claude Code Analysis
**Scope**: Complete annotation data model, pipeline flow, and gap analysis

---

## 1. Executive Summary

The Job Intelligence Pipeline uses a sophisticated **5-dimensional annotation system** that enables human-in-the-loop guidance for CV and outreach generation. This report provides a comprehensive technical analysis of how annotations flow through the 7-layer pipeline.

### Key Findings

| Metric | Value |
|--------|-------|
| **Annotation Dimensions** | 5 (relevance, requirement_type, passion, identity, annotation_type) |
| **Boost Multiplier Range** | 0.0x (disqualifier) to 13.5x (max compound) |
| **Pipeline Layers Using Annotations** | 4 of 10 (40%) |
| **Dimensions Fully Utilized** | 2 of 5 (40%) |
| **Identified Improvement Gaps** | 10 new gaps |

### Integration Status Overview

```
Layer 1.4 (JD Structure)     ████████████████ 100% - Creates annotations
Layer 2 (Pain Points)        ████████████████ 100% - Full enrichment
Layer 2.5 (STAR Selector)    ████░░░░░░░░░░░░  25% - Exists but DISABLED
Layer 3 (Company Research)   ░░░░░░░░░░░░░░░░   0% - No integration
Layer 3.5 (Role Research)    ░░░░░░░░░░░░░░░░   0% - No integration
Layer 4 (Fit Signal)         ████████████████ 100% - Full blending
Layer 5 (People Mapper)      ░░░░░░░░░░░░░░░░   0% - No integration
Layer 6 (CV Generator)       ████████████████ 100% - Full consumption
Layer 6a (Cover Letter)      ████████░░░░░░░░  50% - Basic integration
Layer 6c (Outreach)          ░░░░░░░░░░░░░░░░   0% - No integration
Layer 7 (Publisher)          ████░░░░░░░░░░░░  25% - Partial integration
```

### Critical Gaps Requiring Attention

1. **Passion/Identity dimensions** are captured in UI but barely used in generation
2. **Layers 3, 3.5, 5** have NO annotation awareness
3. **Outreach generation** (Layer 6c) ignores all annotation context
4. **STAR Selector** annotation boost is disabled by default

---

## 2. Annotation Data Model

### 2.1 Core Type Definitions

**File**: `src/common/annotation_types.py`

#### JDAnnotation TypedDict (lines 109-169)

```python
class JDAnnotation(TypedDict, total=False):
    # Identification
    id: str                          # UUID
    target: TextSpan                  # Section, index, text, char offsets

    # Audit Trail
    created_at: str                   # ISO timestamp
    created_by: Literal["human", "pipeline_suggestion", "preset"]
    updated_at: str
    status: Literal["draft", "approved", "rejected", "needs_review"]
    last_reviewed_by: Optional[str]
    review_note: Optional[str]

    # Primary Type
    annotation_type: AnnotationType   # skill_match | reframe | highlight | comment | concern

    # Skill Match Attributes
    relevance: SkillRelevance         # 5-level scale
    requirement_type: RequirementType # must_have | nice_to_have | disqualifier | neutral
    passion: PassionLevel             # 5-level scale (Phase 4)
    identity: IdentityLevel           # 5-level scale (Phase 4)
    matching_skill: Optional[str]     # Which candidate skill matches

    # Reframe Attributes
    has_reframe: bool
    reframe_note: Optional[str]       # How to position experience
    reframe_from: Optional[str]       # Original skill/experience
    reframe_to: Optional[str]         # Target framing

    # Evidence Linking
    star_ids: List[str]               # Linked STAR record IDs
    evidence_summary: Optional[str]   # Brief summary

    # Keywords & ATS
    suggested_keywords: List[str]     # Keywords to integrate
    ats_variants: List[str]           # Keyword variants (e.g., ["K8s", "Kubernetes"])
    min_occurrences: int              # Target frequency min (typically 2)
    max_occurrences: int              # Target frequency max (typically 3)
    preferred_sections: List[str]     # ["skills", "experience"]
    exact_phrase_match: bool          # Must use exact JD phrasing

    # Achievement Context
    achievement_context: Dict         # Metrics and impact thresholds

    # Pipeline Control
    is_active: bool                   # Toggle for generation
    priority: int                     # 1-5 (1 = highest)
    confidence: float                 # 0.0-1.0
    highlight_color: Optional[str]    # Custom hex color
```

#### TextSpan TypedDict (lines 101-107)

```python
class TextSpan(TypedDict):
    section: str           # JD section name (e.g., "responsibilities")
    index: int             # Position within section
    text: str              # Selected text content
    char_start: int        # Character offset start
    char_end: int          # Character offset end
```

### 2.2 Dimension Definitions

#### SkillRelevance (lines 20-26)

```python
SkillRelevance = Literal[
    "core_strength",        # 3.0x boost - Perfect match, IS your core competency
    "extremely_relevant",   # 2.0x boost - Very strong match, directly applicable
    "relevant",             # 1.5x boost - Good match, transferable with minor framing
    "tangential",           # 1.0x boost - Weak match, loosely related
    "gap"                   # 0.3x penalty - No match, candidate lacks this
]
```

#### RequirementType (lines 28-35)

```python
RequirementType = Literal[
    "must_have",            # 1.5x boost - Explicitly required, critical
    "nice_to_have",         # 1.0x - Preferred but not required
    "disqualifier",         # 0.0x - Blocks application entirely
    "neutral"               # 1.0x - Neither required nor preferred
]
```

#### PassionLevel (lines 67-74) - **Phase 4 Addition**

```python
PassionLevel = Literal[
    "love_it",              # 1.5x boost - Genuinely excited, highlight prominently
    "enjoy",                # 1.2x - Would enjoy doing regularly
    "neutral",              # 1.0x - Neither excited nor dreading
    "tolerate",             # 0.8x - Can do but would rather not
    "avoid"                 # 0.5x - Would strongly prefer NOT to do
]
```

**Purpose**: Guides authenticity in cover letters and interview responses. Enables genuine enthusiasm vs. fake interest detection.

#### IdentityLevel (lines 76-83) - **Phase 4 Addition**

```python
IdentityLevel = Literal[
    "core_identity",        # 2.0x boost - This IS who you are professionally
    "strong_identity",      # 1.5x - Significant part of identity
    "developing",           # 1.2x - Growing into this identity
    "peripheral",           # 1.0x - Not central but have experience
    "not_identity"          # 0.3x penalty - NOT how candidate wants to be seen
]
```

**Purpose**: Controls professional identity framing. Determines what goes in headline/introduction vs. what gets buried.

#### AnnotationType (lines 28-35)

```python
AnnotationType = Literal[
    "skill_match",          # JD requirement matches candidate skill
    "reframe",              # Standalone reframe opportunity
    "highlight",            # General highlight for emphasis
    "comment",              # Free-form note/observation
    "concern"               # Red flag or dealbreaker
]
```

### 2.3 Boost Calculation Formula

**File**: `src/common/annotation_boost.py` (lines 181-216)

```python
def calculate_annotation_boost(annotation: JDAnnotation) -> float:
    """
    Calculate compound boost multiplier for an annotation.

    Formula:
        boost = relevance_mult × requirement_mult × passion_mult ×
                identity_mult × priority_mult × type_modifier

    Returns:
        float: Final multiplier (0.0 to ~13.5x theoretical max)
    """
    relevance_mult = RELEVANCE_MULTIPLIERS.get(annotation.get("relevance", "relevant"), 1.0)
    requirement_mult = REQUIREMENT_MULTIPLIERS.get(annotation.get("requirement_type", "neutral"), 1.0)
    passion_mult = PASSION_MULTIPLIERS.get(annotation.get("passion", "neutral"), 1.0)
    identity_mult = IDENTITY_MULTIPLIERS.get(annotation.get("identity", "peripheral"), 1.0)
    priority_mult = PRIORITY_MULTIPLIERS.get(annotation.get("priority", 3), 1.0)
    type_mod = TYPE_MODIFIERS.get(annotation.get("annotation_type", "skill_match"), 1.0)

    return relevance_mult * requirement_mult * passion_mult * identity_mult * priority_mult * type_mod
```

### 2.4 Multiplier Constants

**File**: `src/common/annotation_types.py` (lines 493-543)

```python
# Relevance Multipliers (lines 493-499)
RELEVANCE_MULTIPLIERS = {
    "core_strength": 3.0,
    "extremely_relevant": 2.0,
    "relevant": 1.5,
    "tangential": 1.0,
    "gap": 0.3
}

# Requirement Multipliers (lines 502-507)
REQUIREMENT_MULTIPLIERS = {
    "must_have": 1.5,
    "nice_to_have": 1.0,
    "disqualifier": 0.0,  # Blocks everything
    "neutral": 1.0
}

# Passion Multipliers (lines 510-516)
PASSION_MULTIPLIERS = {
    "love_it": 1.5,
    "enjoy": 1.2,
    "neutral": 1.0,
    "tolerate": 0.8,
    "avoid": 0.5
}

# Identity Multipliers (lines 519-525)
IDENTITY_MULTIPLIERS = {
    "core_identity": 2.0,
    "strong_identity": 1.5,
    "developing": 1.2,
    "peripheral": 1.0,
    "not_identity": 0.3
}

# Priority Multipliers (lines 528-534)
PRIORITY_MULTIPLIERS = {
    1: 1.5,  # Highest priority
    2: 1.3,
    3: 1.0,  # Neutral
    4: 0.8,
    5: 0.6   # Lowest priority
}

# Type Modifiers (lines 537-543)
TYPE_MODIFIERS = {
    "skill_match": 1.0,
    "reframe": 1.2,     # Enhanced - reframes are valuable
    "highlight": 0.8,   # Reduced - highlights are supplementary
    "comment": 0.5,     # Minimal - comments don't drive content
    "concern": 0.0      # Blocked - concerns prevent inclusion
}
```

### 2.5 Theoretical Boost Ranges

| Scenario | Calculation | Boost |
|----------|-------------|-------|
| **Maximum (best case)** | 3.0 × 1.5 × 1.5 × 2.0 × 1.5 × 1.2 | **16.2x** |
| **Strong fit** | 3.0 × 1.5 × 1.2 × 1.5 × 1.3 × 1.0 | **10.5x** |
| **Good fit** | 2.0 × 1.5 × 1.0 × 1.0 × 1.0 × 1.0 | **3.0x** |
| **Neutral** | 1.5 × 1.0 × 1.0 × 1.0 × 1.0 × 1.0 | **1.5x** |
| **Weak fit** | 1.0 × 1.0 × 0.8 × 1.0 × 0.8 × 0.8 | **0.5x** |
| **Gap** | 0.3 × 1.0 × 1.0 × 1.0 × 1.0 × 1.0 | **0.3x** |
| **Disqualifier** | Any × 0.0 × Any × Any × Any × Any | **0.0x** |
| **Concern type** | Any × Any × Any × Any × Any × 0.0 | **0.0x** |

### 2.6 Color Coding System

**File**: `src/common/annotation_types.py` (lines 546-570)

```python
# Relevance Colors (visual feedback)
RELEVANCE_COLORS = {
    "core_strength": "#22c55e",      # Green
    "extremely_relevant": "#14b8a6", # Teal
    "relevant": "#3b82f6",           # Blue
    "tangential": "#eab308",         # Yellow
    "gap": "#ef4444"                 # Red
}

# Passion Colors (emotional indicators)
PASSION_COLORS = {
    "love_it": "#ec4899",            # Pink 🔥
    "enjoy": "#a855f7",              # Purple 😊
    "neutral": "#6b7280",            # Gray 😐
    "tolerate": "#64748b",           # Slate 😕
    "avoid": "#78716c"               # Stone 🚫
}

# Identity Colors (professional branding)
IDENTITY_COLORS = {
    "core_identity": "#6366f1",      # Indigo ⭐
    "strong_identity": "#8b5cf6",    # Violet 💪
    "developing": "#06b6d4",         # Cyan 🌱
    "peripheral": "#6b7280",         # Gray ○
    "not_identity": "#71717a"        # Zinc ✗
}
```

### 2.7 Validation Rules

**File**: `src/common/annotation_validator.py`

| Rule | Level | Condition | Message |
|------|-------|-----------|---------|
| `core_strength_requires_star` | ERROR | `relevance=core_strength` without `star_ids` | Core strengths MUST link ≥1 STAR story |
| `gap_requires_mitigation` | ERROR | `relevance=gap` without `reframe_note` | Gap annotations MUST include reframe_note |
| `must_have_gap_warning` | WARNING | `requirement_type=must_have` AND `relevance=gap` | Risk: must-have skill is a gap |
| `overlapping_spans` | WARNING | >50% character overlap with another annotation | Overlapping annotations detected |
| `section_coverage` | INFO | Section has <3 annotations | Section may need more annotations |
| `disqualifier_warning` | WARNING | `requirement_type=disqualifier` | Dealbreaker flagged - review before proceeding |

### 2.8 Status Flow

```
                ┌─────────────┐
                │   draft     │ (initial state)
                └──────┬──────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌───────────┐  ┌─────────────┐  ┌──────────┐
│ approved  │  │needs_review │  │ rejected │
└───────────┘  └─────────────┘  └──────────┘
        │              │
        │              ▼
        │      ┌───────────┐
        └─────►│ approved  │
               └───────────┘
```

---

## 3. Pipeline Flow Analysis

### 3.1 Layer 1.4: JD Structuring (Annotation Creation)

**File**: `src/services/structure_jd_service.py`

#### Purpose
Converts raw job description text into structured HTML sections and creates the `jd_annotations` container in MongoDB.

#### Code Path

```python
# Entry point (lines 45-78)
async def structure_jd(job_id: str, tier: str = "balanced") -> Dict:
    """
    Process raw JD into structured HTML sections.

    Flow:
    1. Fetch job from MongoDB
    2. Extract raw JD text (job_description or description field)
    3. Call LLM to parse into sections (Responsibilities, Qualifications, etc.)
    4. Store processed_jd_html in job.jd_annotations
    5. Return structured output
    """
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    raw_jd = job.get("job_description") or job.get("description", "")

    # LLM processing
    processed = await self._process_jd(raw_jd, tier)

    # Initialize jd_annotations container
    jd_annotations = {
        "annotation_version": "2.0",
        "processed_jd_html": processed["html"],
        "annotations": [],           # Empty - populated via UI
        "concerns": [],
        "settings": default_settings(),
        "section_summaries": {},
        "relevance_counts": {},
        "type_counts": {},
        "validation_passed": True,
        "validation_errors": [],
        "ats_readiness_score": 0
    }

    # Persist to MongoDB
    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"jd_annotations": jd_annotations}}
    )
```

#### Output Schema

```python
JDAnnotations = TypedDict("JDAnnotations", {
    "annotation_version": str,           # "2.0"
    "processed_jd_html": str,            # HTML for rendering
    "annotations": List[JDAnnotation],   # User-created annotations
    "concerns": List[ConcernAnnotation], # Red flags
    "settings": AnnotationSettings,      # Per-job config
    "section_summaries": Dict[str, SectionSummary],
    "relevance_counts": Dict[str, int],  # {relevance: count}
    "type_counts": Dict[str, int],       # {type: count}
    "validation_passed": bool,
    "validation_errors": List[str],
    "ats_readiness_score": int           # 0-100
})
```

#### Annotation Status at This Layer
- **Creates**: `jd_annotations` container with empty `annotations[]`
- **Populates**: `processed_jd_html` for UI rendering
- **Does NOT**: Create individual annotations (that's done via frontend UI)

---

### 3.2 Layer 2: Pain Point Miner (Annotation Enrichment)

**File**: `src/layer2/pain_point_miner.py`

#### Purpose
Extracts pain points from JD and **enriches analysis using annotation context**.

#### Annotation Integration (lines 198-415)

##### A. Extract Annotation Context (lines 216-298)

```python
def extract_annotation_context(jd_annotations: Dict) -> Dict:
    """
    Extract annotation signals for pain point mining.

    Returns:
        {
            "must_have_keywords": List[str],    # From requirement_type=must_have
            "gap_areas": List[str],             # From relevance=gap + reframe_note
            "reframe_notes": List[str],         # From has_reframe=True
            "core_strength_areas": List[str]    # From relevance=core_strength
        }
    """
    context = {
        "must_have_keywords": [],
        "gap_areas": [],
        "reframe_notes": [],
        "core_strength_areas": []
    }

    for ann in jd_annotations.get("annotations", []):
        if not ann.get("is_active", True):
            continue  # Skip inactive annotations

        # Extract must-have keywords
        if ann.get("requirement_type") == "must_have":
            keywords = ann.get("suggested_keywords", [])
            context["must_have_keywords"].extend(keywords)
            # Also add the annotated text itself
            if ann.get("target", {}).get("text"):
                context["must_have_keywords"].append(ann["target"]["text"][:50])

        # Extract gap areas with reframe notes
        if ann.get("relevance") == "gap":
            gap_text = ann.get("target", {}).get("text", "")[:100]
            reframe = ann.get("reframe_note", "")
            context["gap_areas"].append(f"{gap_text} (reframe: {reframe})")

        # Extract reframe notes
        if ann.get("has_reframe") and ann.get("reframe_note"):
            context["reframe_notes"].append(ann["reframe_note"])

        # Extract core strengths
        if ann.get("relevance") == "core_strength":
            skill = ann.get("matching_skill") or ann.get("target", {}).get("text", "")
            context["core_strength_areas"].append(skill[:50])

    return context
```

##### B. Build Annotation-Aware Prompt (lines 301-356)

```python
def build_annotation_aware_prompt(context: Dict) -> str:
    """
    Build LLM prompt section with annotation priorities.

    Effect:
    - Prioritizes pain points matching must-have keywords (+10 points)
    - Deprioritizes gap areas (-5 points)
    - Guides LLM toward annotated priorities
    """
    prompt_parts = []

    if context["must_have_keywords"]:
        keywords = ", ".join(context["must_have_keywords"][:10])
        prompt_parts.append(f"""
## PRIORITY KEYWORDS (from annotations)
These keywords are marked as MUST-HAVE by the candidate:
{keywords}

INSTRUCTION: Pain points related to these keywords should be scored HIGHER (+10 priority).
""")

    if context["core_strength_areas"]:
        strengths = ", ".join(context["core_strength_areas"][:5])
        prompt_parts.append(f"""
## CANDIDATE CORE STRENGTHS
The candidate excels in: {strengths}

INSTRUCTION: Identify pain points where these strengths provide value.
""")

    if context["gap_areas"]:
        gaps = "\n".join(f"- {g}" for g in context["gap_areas"][:5])
        prompt_parts.append(f"""
## GAP AREAS (lower priority)
These areas are gaps for the candidate:
{gaps}

INSTRUCTION: Pain points in gap areas should be scored LOWER (-5 priority).
""")

    return "\n".join(prompt_parts)
```

##### C. Rank Pain Points with Annotations (lines 359-415)

```python
def rank_pain_points_with_annotations(
    pain_points: List[Dict],
    annotation_context: Dict
) -> List[Dict]:
    """
    Re-rank extracted pain points using annotation priorities.

    Algorithm:
    1. Base score from LLM confidence (high=3, medium=2, low=1)
    2. +3 if matches must-have keyword
    3. -2 if matches gap area
    4. Sort descending by total score
    """
    must_have_keywords = set(
        kw.lower() for kw in annotation_context.get("must_have_keywords", [])
    )
    gap_keywords = set(
        g.split("(reframe:")[0].strip().lower()[:30]
        for g in annotation_context.get("gap_areas", [])
    )

    for pp in pain_points:
        # Base score from confidence
        confidence_scores = {"high": 3, "medium": 2, "low": 1}
        pp["_rank_score"] = confidence_scores.get(pp.get("confidence", "low"), 1)

        # Boost for must-have matches
        pp_text = pp.get("pain_point", "").lower()
        for kw in must_have_keywords:
            if kw in pp_text:
                pp["_rank_score"] += 3
                pp["_annotation_boosted"] = True
                break

        # Penalty for gap matches
        for gap in gap_keywords:
            if gap in pp_text:
                pp["_rank_score"] -= 2
                pp["_annotation_penalized"] = True
                break

    # Sort by score descending
    return sorted(pain_points, key=lambda x: x.get("_rank_score", 0), reverse=True)
```

#### Dimensions Used

| Dimension | Used | How |
|-----------|------|-----|
| relevance | ✅ | core_strength → boost, gap → penalize |
| requirement_type | ✅ | must_have → keyword extraction |
| passion | ❌ | Not used |
| identity | ❌ | Not used |
| reframe_note | ✅ | Included in gap context |
| suggested_keywords | ✅ | Added to must_have keywords |

---

### 3.3 Layer 2.5: STAR Selector (Annotation Boost - DISABLED)

**File**: `src/layer2_5/star_selector.py`

#### Purpose
Select most relevant STAR records based on JD match. **Annotation boost exists but is DISABLED by default.**

#### Configuration

```python
# Default configuration (lines 25-32)
STAR_SELECTOR_CONFIG = {
    "enabled": False,                    # DISABLED by default
    "use_annotation_boost": True,        # Would use if enabled
    "annotation_weight": 0.3,            # 30% weight for annotation signal
    "embedding_weight": 0.7,             # 70% weight for semantic similarity
    "max_stars_per_role": 5
}
```

#### Annotation Boost Logic (lines 145-189)

```python
def get_annotation_boost_for_star(
    star_id: str,
    annotation_calculator: AnnotationBoostCalculator
) -> float:
    """
    Get boost multiplier for a STAR record based on linked annotations.

    Flow:
    1. Find annotations with this star_id in their star_ids list
    2. Calculate compound boost for each
    3. Return max boost (conflict resolution: max_boost strategy)
    """
    boost_result = annotation_calculator.get_boost_for_star(star_id)
    return boost_result.boost  # Returns 1.0 if no linked annotations
```

#### Why Disabled
- **Reason**: Requires embedding-based similarity scoring infrastructure
- **Cost**: Embedding calls add latency and API cost
- **Status**: Flagged as GAP-090 for future enablement

---

### 3.4 Layer 3 & 3.5: Company/Role Research (NO ANNOTATION INTEGRATION)

**Files**:
- `src/layer3/company_researcher.py`
- `src/layer3_5/role_researcher.py`
- `src/services/company_research_service.py`

#### Current State

```python
# company_research_service.py (lines 45-78)
async def research_company(job_id: str, tier: str = "balanced") -> Dict:
    """
    Research company using FireCrawl and LLM analysis.

    NOTE: Does NOT use jd_annotations at all.

    Flow:
    1. Fetch job from MongoDB
    2. Extract company name
    3. FireCrawl company website
    4. LLM analyze company culture, news, growth
    5. Return research results
    """
    # NO annotation context passed or used
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    company_name = job.get("company_name", "")

    # Research proceeds WITHOUT annotation guidance
    research = await self._research_company(company_name, tier)
    return research
```

#### Gap Analysis (GAP-085)

**What's Missing:**
1. Passion annotations not used to guide research focus
2. Must-have priorities not informing what company aspects to research
3. Identity annotations not guiding culture fit analysis

**Potential Enhancement:**
```python
# PROPOSED: Annotation-aware company research
def build_research_focus(jd_annotations: Dict) -> Dict:
    """
    Build research focus from annotation priorities.

    Example:
    - If passion=love_it for "remote work": Research company remote policy
    - If must_have="Kubernetes": Research company's cloud infrastructure
    - If identity=core_identity for "engineering leadership": Research company's engineering blog
    """
    focus = {"technical_areas": [], "culture_signals": [], "growth_indicators": []}

    for ann in jd_annotations.get("annotations", []):
        if ann.get("passion") == "love_it":
            focus["culture_signals"].append(ann.get("target", {}).get("text", ""))
        if ann.get("requirement_type") == "must_have":
            focus["technical_areas"].append(ann.get("matching_skill", ""))

    return focus
```

---

### 3.5 Layer 4: Fit Signal (Annotation Blending)

**File**: `src/layer4/annotation_fit_signal.py`

#### Purpose
Calculate fit signal from annotations and blend with LLM score (70/30 split).

#### AnnotationFitSignal Calculator (lines 44-220)

```python
class AnnotationFitSignal:
    """
    Calculate fit signal from JD annotations.

    Algorithm:
    1. Count annotations by relevance level
    2. Weight each level: core_strength=1.0, gap=-0.5
    3. Sum weighted scores
    4. Apply sigmoid to normalize to [0, 1]
    """

    def __init__(self, jd_annotations: Dict):
        self.annotations = [
            a for a in jd_annotations.get("annotations", [])
            if a.get("is_active", True)  # Only active annotations
        ]
        self._compute_counts()

    def _compute_counts(self):
        """Count annotations by relevance level."""
        self.core_strength_count = 0
        self.extremely_relevant_count = 0
        self.relevant_count = 0
        self.tangential_count = 0
        self.gap_count = 0
        self.disqualifier_count = 0

        for ann in self.annotations:
            relevance = ann.get("relevance", "relevant")
            if relevance == "core_strength":
                self.core_strength_count += 1
            elif relevance == "extremely_relevant":
                self.extremely_relevant_count += 1
            elif relevance == "relevant":
                self.relevant_count += 1
            elif relevance == "tangential":
                self.tangential_count += 1
            elif relevance == "gap":
                self.gap_count += 1

            if ann.get("requirement_type") == "disqualifier":
                self.disqualifier_count += 1
```

#### Fit Signal Formula (lines 139-189)

```python
def calculate_fit_signal(self) -> float:
    """
    Calculate normalized fit signal.

    Formula:
        positive_signal = (core × 1.0) + (extremely × 0.8) +
                          (relevant × 0.5) + (tangential × 0.2)
        negative_signal = gap × 0.5
        net_signal = positive_signal - negative_signal
        fit_signal = sigmoid(0.3 × net_signal)

    Sigmoid: f(x) = 1 / (1 + e^(-x))

    Returns:
        float: Fit signal in range [0.0, 1.0]
    """
    # Weights for positive contributions
    WEIGHTS = {
        "core_strength": 1.0,
        "extremely_relevant": 0.8,
        "relevant": 0.5,
        "tangential": 0.2
    }

    positive = (
        self.core_strength_count * WEIGHTS["core_strength"] +
        self.extremely_relevant_count * WEIGHTS["extremely_relevant"] +
        self.relevant_count * WEIGHTS["relevant"] +
        self.tangential_count * WEIGHTS["tangential"]
    )

    negative = self.gap_count * 0.5
    net = positive - negative

    # Sigmoid transformation
    import math
    fit_signal = 1 / (1 + math.exp(-0.3 * net))

    return fit_signal
```

#### Score Blending (lines 222-265)

```python
def blend_fit_scores(
    llm_score: int,
    annotation_signal: float,
    llm_weight: float = 0.7,
    annotation_weight: float = 0.3
) -> int:
    """
    Blend LLM fit score with annotation signal.

    Formula:
        blended = (llm_score × 0.7) + (annotation_signal × 100 × 0.3)

    Args:
        llm_score: LLM-generated fit score (0-100)
        annotation_signal: Annotation-derived signal (0.0-1.0)
        llm_weight: Weight for LLM score (default 0.7)
        annotation_weight: Weight for annotation signal (default 0.3)

    Returns:
        int: Blended score (0-100)
    """
    annotation_score = annotation_signal * 100  # Convert to 0-100 scale

    blended = (llm_score * llm_weight) + (annotation_score * annotation_weight)

    return int(min(100, max(0, blended)))
```

#### Disqualifier Detection (lines 127-134)

```python
def has_disqualifier(self) -> bool:
    """Check if any annotation is marked as disqualifier."""
    return self.disqualifier_count > 0

def get_disqualifier_details(self) -> List[str]:
    """Get text of disqualifier annotations for review."""
    return [
        ann.get("target", {}).get("text", "")
        for ann in self.annotations
        if ann.get("requirement_type") == "disqualifier"
    ]
```

#### Dimensions Used

| Dimension | Used | How |
|-----------|------|-----|
| relevance | ✅ | Weighted sum for fit signal |
| requirement_type | ✅ | Disqualifier detection only |
| passion | ❌ | Not used in fit calculation |
| identity | ❌ | Not used in fit calculation |

---

### 3.6 Layer 5: People Mapper (NO ANNOTATION INTEGRATION)

**File**: `src/layer5/people_mapper.py`

#### Current State

```python
# people_mapper.py (lines 56-89)
async def discover_contacts(job: Dict, company_research: Dict) -> List[Dict]:
    """
    Discover contacts at target company.

    NOTE: Does NOT use jd_annotations.

    Flow:
    1. Extract company name and role title
    2. Generate SEO queries for LinkedIn
    3. FireCrawl or synthetic fallback
    4. Return contact list
    """
    # NO annotation context used
    company = job.get("company_name", "")
    role = job.get("title", "")

    queries = generate_seo_queries(company, role)  # Generic queries
    contacts = await discover_via_firecrawl(queries)
    return contacts
```

#### Gap Analysis (GAP-086)

**What's Missing:**
1. Pain point keywords not used in SEO queries
2. Must-have annotations not guiding which contacts to prioritize
3. No filtering based on annotation-derived focus areas

**Potential Enhancement:**
```python
# PROPOSED: Annotation-aware contact discovery
def generate_annotation_aware_queries(
    company: str,
    role: str,
    jd_annotations: Dict
) -> List[str]:
    """
    Generate SEO queries informed by annotations.

    Example:
    - If must_have="Kubernetes": Search for "DevOps lead" or "Platform engineer"
    - If pain_point="scaling": Search for "Infrastructure" or "SRE"
    """
    base_queries = [f"{company} {role} LinkedIn"]

    for ann in jd_annotations.get("annotations", []):
        if ann.get("requirement_type") == "must_have":
            skill = ann.get("matching_skill", "")
            if skill:
                base_queries.append(f"{company} {skill} team lead LinkedIn")

    return base_queries
```

---

### 3.7 Layer 6: CV Generation (Full Annotation Consumption)

**Files**:
- `src/layer6_v2/annotation_header_context.py`
- `src/layer6_v2/orchestrator.py`
- `src/layer6_v2/header_generator.py`
- `src/common/annotation_boost.py`

#### AnnotationHeaderContextBuilder (lines 145-669)

```python
class AnnotationHeaderContextBuilder:
    """
    Build HeaderGenerationContext from annotations for CV generation.

    Responsibilities:
    1. Extract and rank annotation priorities (weighted scoring)
    2. Create reframe map (skill → JD-aligned language)
    3. Generate gap mitigation clauses
    4. Extract STAR snippets for proof statements
    5. Build ATS requirements (keywords, variants, targets)
    """

    def __init__(self, jd_annotations: Dict, all_stars: List[Dict]):
        self.jd_annotations = jd_annotations
        self.all_stars = {s["id"]: s for s in all_stars}
        self.annotations = [
            a for a in jd_annotations.get("annotations", [])
            if a.get("is_active", True) and a.get("status") != "rejected"
        ]
```

##### Priority Extraction (lines 213-288)

```python
def extract_priorities(self) -> List[AnnotationPriority]:
    """
    Extract and rank annotation priorities.

    Priority Score Formula:
        score = (relevance_score × 0.4) +
                (requirement_score × 0.3) +
                (user_priority × 0.2) +
                (has_star_evidence × 0.1)

    Relevance Scores:
        core_strength=5.0, extremely_relevant=4.0, relevant=3.0,
        tangential=2.0, gap=1.0

    Requirement Scores:
        must_have=5.0, nice_to_have=3.0, neutral=2.0, disqualifier=0.0

    Returns:
        List[AnnotationPriority]: Sorted by priority_score descending
    """
    RELEVANCE_SCORES = {
        "core_strength": 5.0,
        "extremely_relevant": 4.0,
        "relevant": 3.0,
        "tangential": 2.0,
        "gap": 1.0
    }

    REQUIREMENT_SCORES = {
        "must_have": 5.0,
        "nice_to_have": 3.0,
        "neutral": 2.0,
        "disqualifier": 0.0
    }

    priorities = []
    for ann in self.annotations:
        relevance = ann.get("relevance", "relevant")
        requirement = ann.get("requirement_type", "neutral")
        user_priority = ann.get("priority", 3)
        has_star = bool(ann.get("star_ids"))

        score = (
            RELEVANCE_SCORES.get(relevance, 3.0) * 0.4 +
            REQUIREMENT_SCORES.get(requirement, 2.0) * 0.3 +
            (6 - user_priority) * 0.2 +  # Invert: priority 1 → score 5
            (1.0 if has_star else 0.0) * 0.1
        )

        priorities.append(AnnotationPriority(
            annotation_id=ann["id"],
            text=ann.get("target", {}).get("text", ""),
            relevance=relevance,
            requirement_type=requirement,
            passion=ann.get("passion", "neutral"),
            identity=ann.get("identity", "peripheral"),
            priority_score=score,
            star_snippets=self._extract_star_snippets(ann.get("star_ids", [])),
            reframe_note=ann.get("reframe_note"),
            suggested_keywords=ann.get("suggested_keywords", []),
            ats_variants=ann.get("ats_variants", [])
        ))

    # Sort by priority_score descending
    priorities.sort(key=lambda p: p.priority_score, reverse=True)

    # Assign rank
    for i, p in enumerate(priorities):
        p.rank = i + 1

    return priorities
```

##### Reframe Map Building (lines 309-343)

```python
def build_reframe_map(self) -> Dict[str, str]:
    """
    Build mapping from skills/text to reframe guidance.

    Keys:
    - matching_skill (if present)
    - reframe_from (if present)
    - First 50 chars of target text (fallback)

    Returns:
        Dict[str, str]: {original_skill: reframe_guidance}
    """
    reframe_map = {}

    for ann in self.annotations:
        if not ann.get("has_reframe") or not ann.get("reframe_note"):
            continue

        reframe = ann["reframe_note"]

        # Add by matching_skill
        if ann.get("matching_skill"):
            reframe_map[ann["matching_skill"].lower()] = reframe

        # Add by reframe_from
        if ann.get("reframe_from"):
            reframe_map[ann["reframe_from"].lower()] = reframe

        # Add by target text
        target_text = ann.get("target", {}).get("text", "")[:50].lower()
        if target_text:
            reframe_map[target_text] = reframe

    return reframe_map
```

##### Gap Mitigation Generation (lines 345-408)

```python
def generate_gap_mitigation(self) -> Optional[str]:
    """
    Generate mitigation clause for highest-priority must-have gap.

    Strategy: "Reframe if possible"

    Only generates ONE mitigation for the highest-priority gap
    that has a reframe_note.

    Returns:
        Optional[str]: Mitigation clause or None

    Example:
        "Strong foundation in [reframe_to] with proven ability to quickly
        master new technologies as demonstrated by [evidence]."
    """
    # Find must-have gaps with reframe notes
    gaps = [
        ann for ann in self.annotations
        if (ann.get("relevance") == "gap" and
            ann.get("requirement_type") == "must_have" and
            ann.get("reframe_note"))
    ]

    if not gaps:
        return None

    # Sort by priority (lower = higher priority)
    gaps.sort(key=lambda a: a.get("priority", 3))
    top_gap = gaps[0]

    reframe_to = top_gap.get("reframe_to", "related technologies")
    reframe_note = top_gap.get("reframe_note", "")

    mitigation = f"Strong foundation in {reframe_to} with {reframe_note}"

    return mitigation
```

##### ATS Requirements Building (lines 410-465)

```python
def build_ats_requirements(self) -> Dict[str, ATSRequirement]:
    """
    Build ATS keyword requirements from annotations.

    Returns:
        Dict[str, ATSRequirement]: {keyword: {min, max, variants, sections}}
    """
    requirements = {}

    for ann in self.annotations:
        keywords = ann.get("suggested_keywords", [])
        variants = ann.get("ats_variants", [])
        min_occ = ann.get("min_occurrences", 2)
        max_occ = ann.get("max_occurrences", 3)
        sections = ann.get("preferred_sections", ["skills", "experience"])

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in requirements:
                # Merge: take max of mins, min of maxes
                existing = requirements[kw_lower]
                existing["min"] = max(existing["min"], min_occ)
                existing["max"] = min(existing["max"], max_occ)
                existing["variants"] = list(set(existing["variants"] + variants))
            else:
                requirements[kw_lower] = {
                    "min": min_occ,
                    "max": max_occ,
                    "variants": variants,
                    "sections": sections
                }

    return requirements
```

#### Orchestrator Integration (lines 145-275)

```python
# orchestrator.py - Phase 2: Role bullet generation
async def _generate_all_role_bullets(self, state: JobState) -> List[GeneratedRole]:
    """
    Generate role bullets with annotation boost.
    """
    jd_annotations = state.get("jd_annotations")

    if jd_annotations:
        logger.info("Annotations detected - applying annotation boost to generation")

        # Build annotation context
        context_builder = AnnotationHeaderContextBuilder(
            jd_annotations,
            state.get("all_stars", [])
        )
        annotation_context = context_builder.build()

        # Build boost calculator
        boost_calculator = AnnotationBoostCalculator(jd_annotations)

        # Pass to generators
        self.header_generator.set_annotation_context(annotation_context)
        self.skills_generator.set_boost_calculator(boost_calculator)
```

#### HeaderGenerator with Annotation Context (lines 84-150)

```python
# header_generator.py
class HeaderGenerator:
    def __init__(self, model: str, annotation_context: Optional[HeaderGenerationContext] = None):
        self.annotation_context = annotation_context

    def _build_prompt_with_annotations(self) -> str:
        """
        Build prompt with annotation priorities injected.
        """
        prompt_parts = [self.base_prompt]

        if self.annotation_context:
            priorities = self.annotation_context.priorities[:10]  # Top 10

            must_haves = [p for p in priorities if p.is_must_have]
            core_strengths = [p for p in priorities if p.is_core_strength]
            passions = [p for p in priorities if p.is_passion_love_it]

            if must_haves:
                prompt_parts.append(f"""
## MUST-HAVE PRIORITIES (from annotations)
These skills MUST appear prominently in the profile:
{', '.join(p.text[:30] for p in must_haves)}

INSTRUCTION: Feature these in headline and opening summary.
""")

            if core_strengths:
                prompt_parts.append(f"""
## CORE STRENGTHS (from annotations)
Candidate's proven strengths:
{', '.join(p.text[:30] for p in core_strengths)}

INSTRUCTION: These should anchor the professional narrative.
""")

            if passions:
                prompt_parts.append(f"""
## PASSION AREAS (from annotations)
Candidate is genuinely excited about:
{', '.join(p.text[:30] for p in passions)}

INSTRUCTION: Use these for authentic enthusiasm in summary.
""")

        return "\n".join(prompt_parts)
```

#### AnnotationBoostCalculator (lines 67-497)

```python
class AnnotationBoostCalculator:
    """
    Pre-compute annotation indexes and provide boost lookups.

    Indexes:
    - keywords_to_annotations: keyword → List[annotation]
    - star_id_to_annotations: star_id → List[annotation]
    - gap_annotations: List[annotation]
    - core_strength_annotations: List[annotation]
    - passion_love_it_annotations: List[annotation]
    - passion_avoid_annotations: List[annotation]
    - identity_core_annotations: List[annotation]
    - identity_not_me_annotations: List[annotation]
    """

    def __init__(self, jd_annotations: Dict):
        self.annotations = [
            a for a in jd_annotations.get("annotations", [])
            if a.get("is_active", True)
        ]
        self._build_indexes()

    def _build_indexes(self):
        """Build lookup indexes for efficient boost calculation."""
        self.keywords_to_annotations = defaultdict(list)
        self.star_id_to_annotations = defaultdict(list)
        self.gap_annotations = []
        self.core_strength_annotations = []
        self.passion_love_it_annotations = []
        self.passion_avoid_annotations = []
        self.identity_core_annotations = []
        self.identity_not_me_annotations = []

        for ann in self.annotations:
            # Index by keywords
            for kw in ann.get("suggested_keywords", []):
                self.keywords_to_annotations[kw.lower()].append(ann)

            # Index by STAR IDs
            for star_id in ann.get("star_ids", []):
                self.star_id_to_annotations[star_id].append(ann)

            # Index by relevance
            if ann.get("relevance") == "gap":
                self.gap_annotations.append(ann)
            elif ann.get("relevance") == "core_strength":
                self.core_strength_annotations.append(ann)

            # Index by passion
            if ann.get("passion") == "love_it":
                self.passion_love_it_annotations.append(ann)
            elif ann.get("passion") == "avoid":
                self.passion_avoid_annotations.append(ann)

            # Index by identity
            if ann.get("identity") == "core_identity":
                self.identity_core_annotations.append(ann)
            elif ann.get("identity") == "not_identity":
                self.identity_not_me_annotations.append(ann)

    def get_boost_for_star(self, star_id: str) -> BoostResult:
        """Get boost for a STAR record."""
        annotations = self.star_id_to_annotations.get(star_id, [])
        return self._calculate_max_boost(annotations)

    def get_boost_for_text(self, text: str) -> BoostResult:
        """Get boost for text via keyword matching."""
        text_lower = text.lower()
        matching_annotations = []
        matched_keywords = []

        for kw, anns in self.keywords_to_annotations.items():
            if kw in text_lower:
                matching_annotations.extend(anns)
                matched_keywords.append(kw)

        result = self._calculate_max_boost(matching_annotations)
        result.matched_keywords = matched_keywords
        return result

    def get_passions(self) -> List[JDAnnotation]:
        """Get love_it annotations for enthusiasm highlights."""
        return self.passion_love_it_annotations

    def get_avoid_areas(self) -> List[JDAnnotation]:
        """Get avoid annotations to de-emphasize."""
        return self.passion_avoid_annotations

    def get_identity_core(self) -> List[JDAnnotation]:
        """Get core_identity for headlines/intros."""
        return self.identity_core_annotations

    def get_identity_not_me(self) -> List[JDAnnotation]:
        """Get not_identity to avoid in introductions."""
        return self.identity_not_me_annotations
```

#### GeneratedBullet Traceability (lines 18-78)

```python
# types.py
class GeneratedBullet(TypedDict):
    """
    A generated CV bullet with full annotation traceability.
    """
    text: str                           # The bullet text
    star_id: Optional[str]              # Source STAR record ID
    role_id: str                        # Target role ID
    category: str                       # Skills category

    # Annotation traceability
    annotation_influenced: bool         # Was this influenced by annotations?
    annotation_ids: List[str]           # Which annotations contributed
    reframe_applied: Optional[str]      # Reframe guidance used
    annotation_keywords_used: List[str] # Keywords matched
    annotation_boost: float             # Final boost multiplier applied
```

#### Dimensions Used

| Dimension | Used | How |
|-----------|------|-----|
| relevance | ✅ | Priority scoring, boost calculation |
| requirement_type | ✅ | Must-have detection, priority scoring |
| passion | ⚠️ | Indexed but minimally used in prompts |
| identity | ⚠️ | Indexed but minimally used in prompts |
| reframe_note | ✅ | Reframe map, gap mitigation |
| star_ids | ✅ | STAR snippet extraction |
| suggested_keywords | ✅ | ATS requirements, keyword matching |
| ats_variants | ⚠️ | Stored but not validated post-generation |

---

### 3.8 Layer 6a: Cover Letter (Partial Integration)

**File**: `src/layer6a/cover_letter_generator.py`

#### Current State

```python
# cover_letter_generator.py (lines 89-145)
async def generate_cover_letter(
    job: Dict,
    cv_content: str,
    pain_points: List[Dict],
    company_research: Dict,
    jd_annotations: Optional[Dict] = None  # Optional parameter
) -> str:
    """
    Generate cover letter.

    NOTE: jd_annotations is passed but minimally used.

    Current usage:
    - Extract must_have keywords for mention
    - Extract core_strength for positioning

    NOT used:
    - passion dimension for genuine hooks
    - identity dimension for authentic positioning
    - avoid areas for tone adjustment
    """
    prompt = self._build_prompt(job, cv_content, pain_points, company_research)

    # Minimal annotation usage
    if jd_annotations:
        must_haves = [
            a.get("target", {}).get("text", "")
            for a in jd_annotations.get("annotations", [])
            if a.get("requirement_type") == "must_have"
        ]
        if must_haves:
            prompt += f"\n\nMust mention these skills: {', '.join(must_haves[:5])}"
```

#### Gap Analysis (GAP-088)

**What's Missing:**
1. Passion dimension not used for enthusiasm hooks
2. Identity dimension not guiding positioning/tone
3. Avoid areas not used to de-emphasize topics

**Potential Enhancement:**
```python
# PROPOSED: Full annotation integration in cover letter
def _build_annotation_aware_prompt(self, jd_annotations: Dict) -> str:
    """
    Build prompt with full annotation context.
    """
    parts = []

    # Extract passion=love_it for enthusiasm hooks
    love_its = [
        a for a in jd_annotations.get("annotations", [])
        if a.get("passion") == "love_it" and a.get("is_active")
    ]
    if love_its:
        texts = [a.get("target", {}).get("text", "")[:50] for a in love_its]
        parts.append(f"""
## AUTHENTIC ENTHUSIASM (passion=love_it)
The candidate is GENUINELY excited about: {', '.join(texts)}

INSTRUCTION: Use these as natural enthusiasm hooks. Write with real passion
about these topics - they're not just buzzwords, they're what the candidate
truly enjoys.
""")

    # Extract identity=core_identity for positioning
    core_identities = [
        a for a in jd_annotations.get("annotations", [])
        if a.get("identity") == "core_identity" and a.get("is_active")
    ]
    if core_identities:
        texts = [a.get("target", {}).get("text", "")[:50] for a in core_identities]
        parts.append(f"""
## PROFESSIONAL IDENTITY (identity=core_identity)
How the candidate SEES themselves professionally: {', '.join(texts)}

INSTRUCTION: Frame the entire letter around this identity. This is WHO they
are, not just what they do.
""")

    # Extract passion=avoid for de-emphasis
    avoids = [
        a for a in jd_annotations.get("annotations", [])
        if a.get("passion") == "avoid" and a.get("is_active")
    ]
    if avoids:
        texts = [a.get("target", {}).get("text", "")[:50] for a in avoids]
        parts.append(f"""
## DE-EMPHASIZE (passion=avoid)
The candidate would prefer NOT to do: {', '.join(texts)}

INSTRUCTION: Don't emphasize these. If they must be mentioned, keep it brief
and pivot quickly to strengths.
""")

    return "\n".join(parts)
```

---

### 3.9 Layer 6c: Outreach Generation (NO ANNOTATION INTEGRATION)

**File**: `src/layer6c/outreach_generator.py`

#### Current State

```python
# outreach_generator.py (lines 45-89)
async def generate_connection_request(
    contact: Dict,
    job: Dict,
    pain_points: List[Dict],
    company_research: Dict
) -> str:
    """
    Generate 300-char LinkedIn connection request.

    NOTE: Does NOT use jd_annotations.

    Flow:
    1. Extract contact name and role
    2. Select top pain point
    3. Generate templated message
    4. Validate character limit
    """
    # NO annotation context
    template = CONNECTION_REQUEST_TEMPLATE

    message = template.format(
        first_name=contact.get("first_name", "there"),
        role=job.get("title", "role"),
        company=job.get("company_name", "your company"),
        pain_point=pain_points[0].get("pain_point", "challenges")[:50],
        calendly_url=CALENDLY_URL
    )

    return message[:300]  # Truncate to limit
```

#### Gap Analysis (GAP-091)

**What's Missing:**
1. Passion annotations not used for genuine hooks
2. Identity annotations not guiding positioning
3. Core strengths not emphasized in value proposition

**Potential Enhancement:**
```python
# PROPOSED: Annotation-aware outreach
async def generate_annotation_aware_connection_request(
    contact: Dict,
    job: Dict,
    jd_annotations: Dict
) -> str:
    """
    Generate connection request with annotation-derived personalization.
    """
    # Find passion=love_it annotations for genuine hooks
    passions = [
        a.get("target", {}).get("text", "")[:30]
        for a in jd_annotations.get("annotations", [])
        if a.get("passion") == "love_it" and a.get("is_active")
    ]

    # Find core_identity for positioning
    identities = [
        a.get("target", {}).get("text", "")[:30]
        for a in jd_annotations.get("annotations", [])
        if a.get("identity") == "core_identity" and a.get("is_active")
    ]

    # Build personalized message
    passion_hook = passions[0] if passions else "your work"
    identity_frame = identities[0] if identities else "engineer"

    message = f"Hi {contact['first_name']}, I'm a {identity_frame} genuinely " \
              f"passionate about {passion_hook}. Saw your role at {job['company_name']} " \
              f"and would love to connect. {CALENDLY_URL} Best. Taimoor Alam"

    return message[:300]
```

---

### 3.10 Layer 7: Publisher (Partial Integration)

**Files**:
- `src/layer7/interview_predictor.py`
- `src/layer7/outcome_tracker.py`
- `src/layer7/output_publisher.py`

#### Current State

```python
# interview_predictor.py (lines 67-123)
async def predict_interview_questions(
    job: Dict,
    cv_content: str,
    pain_points: List[Dict],
    jd_annotations: Optional[Dict] = None  # Passed but NOT USED
) -> List[InterviewQuestion]:
    """
    Predict likely interview questions.

    NOTE: jd_annotations parameter exists but is NOT USED.

    Flow:
    1. Analyze JD for key requirements
    2. Generate questions based on pain points
    3. Categorize by type (technical, behavioral, situational)
    """
    # jd_annotations is IGNORED
    questions = await self._generate_questions(job, cv_content, pain_points)
    return questions
```

#### Gap Analysis (GAP-087)

**What's Missing:**
1. Gap annotations not used to predict "weakness" questions
2. Must-have annotations not prioritizing technical questions
3. Reframe notes not informing answer preparation
4. Outcome tracker not linking outcomes to annotation accuracy

**Potential Enhancement:**
```python
# PROPOSED: Annotation-aware interview prediction
async def predict_annotation_aware_questions(
    job: Dict,
    cv_content: str,
    jd_annotations: Dict
) -> List[InterviewQuestion]:
    """
    Predict questions informed by annotations.
    """
    questions = []

    # Questions about gaps (must-have gaps are likely interview topics)
    gaps = [
        a for a in jd_annotations.get("annotations", [])
        if a.get("relevance") == "gap" and a.get("requirement_type") == "must_have"
    ]
    for gap in gaps:
        gap_text = gap.get("target", {}).get("text", "")
        reframe = gap.get("reframe_note", "")
        questions.append(InterviewQuestion(
            question_text=f"Tell me about your experience with {gap_text}",
            question_type="technical",
            difficulty="hard",
            preparation_note=f"PREPARE: Use reframe strategy: {reframe}",
            source="gap_annotation"
        ))

    # Questions about core strengths (expect deep dives)
    core_strengths = [
        a for a in jd_annotations.get("annotations", [])
        if a.get("relevance") == "core_strength"
    ]
    for cs in core_strengths:
        cs_text = cs.get("target", {}).get("text", "")
        star_ids = cs.get("star_ids", [])
        questions.append(InterviewQuestion(
            question_text=f"Describe a challenging project involving {cs_text}",
            question_type="behavioral",
            difficulty="medium",
            preparation_note=f"PREPARE: Use STAR story IDs: {star_ids}",
            source="core_strength_annotation"
        ))

    return questions
```

---

## 4. Frontend Integration

### 4.1 Annotation Manager Class

**File**: `frontend/static/js/jd-annotation.js` (~1200 lines)

#### Class Structure

```javascript
class AnnotationManager {
    constructor(jobId) {
        this.jobId = jobId;
        this.annotations = [];              // Current annotations
        this.activeAnnotation = null;       // Selected annotation
        this.unsavedChanges = false;        // Dirty flag
        this.autosaveTimer = null;          // Debounce timer
        this.highlightElements = new Map(); // DOM element cache

        // Constants
        this.AUTOSAVE_DELAY = 3000;         // 3 second debounce
        this.MAX_KEYWORDS = 10;             // Max keywords per annotation
    }

    // Lifecycle methods
    async init() { ... }                    // Load annotations from API
    async save() { ... }                    // Persist to MongoDB

    // Selection handling
    handleTextSelection(event) { ... }      // Create annotation from selection
    showAnnotationPopover(target) { ... }   // Display edit popover

    // Rendering
    applyHighlights() { ... }               // Render highlights in JD text
    renderAnnotationList() { ... }          // Render sidebar list

    // State management
    setActiveAnnotation(id) { ... }         // Select annotation
    updateAnnotation(id, updates) { ... }   // Modify annotation
    deleteAnnotation(id) { ... }            // Remove annotation
}
```

#### Text Selection Handler (lines 156-234)

```javascript
handleTextSelection(event) {
    const selection = window.getSelection();
    if (!selection.rangeCount || selection.isCollapsed) return;

    const range = selection.getRangeAt(0);
    const text = selection.toString().trim();

    if (text.length < 3) return; // Minimum selection length

    // Find section container
    const sectionEl = range.commonAncestorContainer.closest('[data-section]');
    if (!sectionEl) return;

    const section = sectionEl.dataset.section;
    const sectionText = sectionEl.textContent;

    // Calculate character offsets
    const charStart = sectionText.indexOf(text);
    const charEnd = charStart + text.length;

    // Create annotation target
    const target = {
        section: section,
        index: 0,
        text: text,
        char_start: charStart,
        char_end: charEnd
    };

    // Show popover at selection position
    this.showAnnotationPopover(target, range.getBoundingClientRect());
}
```

#### Popover UI (lines 278-456)

```javascript
showAnnotationPopover(target, position) {
    const popover = document.createElement('div');
    popover.className = 'annotation-popover';
    popover.innerHTML = `
        <div class="popover-header">
            <span class="selected-text">"${target.text.slice(0, 50)}..."</span>
            <button class="close-btn">&times;</button>
        </div>

        <div class="popover-body">
            <!-- Relevance selector -->
            <div class="field-group">
                <label>Relevance</label>
                <div class="button-group" data-field="relevance">
                    <button data-value="core_strength" class="btn-green">Core (3.0x)</button>
                    <button data-value="extremely_relevant" class="btn-teal">Strong (2.0x)</button>
                    <button data-value="relevant" class="btn-blue">Good (1.5x)</button>
                    <button data-value="tangential" class="btn-yellow">Weak (1.0x)</button>
                    <button data-value="gap" class="btn-red">Gap (0.3x)</button>
                </div>
            </div>

            <!-- Requirement type selector -->
            <div class="field-group">
                <label>Requirement</label>
                <div class="button-group" data-field="requirement_type">
                    <button data-value="must_have" class="btn-primary">Must Have (1.5x)</button>
                    <button data-value="nice_to_have" class="btn-secondary">Nice to Have</button>
                    <button data-value="neutral" class="btn-gray">Neutral</button>
                    <button data-value="disqualifier" class="btn-danger">Disqualifier</button>
                </div>
            </div>

            <!-- Passion selector (Phase 4) -->
            <div class="field-group">
                <label>Passion Level</label>
                <div class="button-group" data-field="passion">
                    <button data-value="love_it" class="btn-pink">Love it (1.5x)</button>
                    <button data-value="enjoy" class="btn-purple">Enjoy (1.2x)</button>
                    <button data-value="neutral" class="btn-gray">Neutral</button>
                    <button data-value="tolerate" class="btn-slate">Tolerate (0.8x)</button>
                    <button data-value="avoid" class="btn-stone">Avoid (0.5x)</button>
                </div>
            </div>

            <!-- Identity selector (Phase 4) -->
            <div class="field-group">
                <label>Identity Level</label>
                <div class="button-group" data-field="identity">
                    <button data-value="core_identity" class="btn-indigo">Core Identity (2.0x)</button>
                    <button data-value="strong_identity" class="btn-violet">Strong (1.5x)</button>
                    <button data-value="developing" class="btn-cyan">Developing (1.2x)</button>
                    <button data-value="peripheral" class="btn-gray">Peripheral</button>
                    <button data-value="not_identity" class="btn-zinc">Not Me (0.3x)</button>
                </div>
            </div>

            <!-- STAR links -->
            <div class="field-group">
                <label>Link STAR Stories</label>
                <div class="star-checkboxes" id="star-links"></div>
            </div>

            <!-- Reframe note -->
            <div class="field-group">
                <label>Reframe Note</label>
                <textarea data-field="reframe_note" placeholder="How to position this..."></textarea>
            </div>

            <!-- Keywords -->
            <div class="field-group">
                <label>ATS Keywords</label>
                <input type="text" data-field="keywords" placeholder="comma, separated, keywords">
            </div>
        </div>

        <div class="popover-footer">
            <button class="btn-save">Save</button>
            <button class="btn-cancel">Cancel</button>
        </div>
    `;

    document.body.appendChild(popover);
    this.positionPopover(popover, position);
}
```

#### Highlight Rendering (lines 567-678)

```javascript
applyHighlights() {
    // Remove existing highlights
    document.querySelectorAll('.annotation-highlight').forEach(el => {
        el.outerHTML = el.innerHTML;
    });

    // Apply new highlights
    for (const ann of this.annotations) {
        if (!ann.is_active) continue;

        const section = ann.target?.section;
        const sectionEl = document.querySelector(`[data-section="${section}"]`);
        if (!sectionEl) continue;

        const text = ann.target?.text;
        if (!text) continue;

        // Find and wrap text
        const walker = document.createTreeWalker(
            sectionEl,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );

        let node;
        while (node = walker.nextNode()) {
            const idx = node.textContent.indexOf(text);
            if (idx >= 0) {
                const range = document.createRange();
                range.setStart(node, idx);
                range.setEnd(node, idx + text.length);

                const wrapper = document.createElement('span');
                wrapper.className = `annotation-highlight annotation-highlight-${ann.relevance}`;
                wrapper.dataset.annotationId = ann.id;
                wrapper.style.backgroundColor = RELEVANCE_COLORS[ann.relevance];

                range.surroundContents(wrapper);
                break;
            }
        }
    }
}
```

### 4.2 Annotation Heatmap Display

**File**: `frontend/templates/job_detail.html` (lines 1009-1095)

```html
<!-- Annotation Signals Panel -->
<div class="annotation-signals-panel" x-show="job.annotation_signals">
    <h3>Opportunity & Fit Analysis</h3>

    <!-- Score Card -->
    <div class="score-card">
        <span class="score-value"
              :class="{
                  'text-green-600': job.annotation_signals?.annotation_score >= 70,
                  'text-blue-600': job.annotation_signals?.annotation_score >= 50 && job.annotation_signals?.annotation_score < 70,
                  'text-yellow-600': job.annotation_signals?.annotation_score >= 30 && job.annotation_signals?.annotation_score < 50,
                  'text-red-600': job.annotation_signals?.annotation_score < 30
              }">
            <span x-text="job.annotation_signals?.annotation_score || 0"></span>%
        </span>
        <span class="score-label">Match</span>
    </div>

    <!-- Heatmap Bar -->
    <div class="heatmap-bar">
        <div class="bar-segment bar-good"
             :style="{ width: (job.annotation_signals?.good_match_count / totalAnnotations * 100) + '%' }">
        </div>
        <div class="bar-segment bar-partial"
             :style="{ width: (job.annotation_signals?.partial_match_count / totalAnnotations * 100) + '%' }">
        </div>
        <div class="bar-segment bar-gap"
             :style="{ width: (job.annotation_signals?.gap_count / totalAnnotations * 100) + '%' }">
        </div>
    </div>

    <!-- Legend -->
    <div class="heatmap-legend">
        <span class="legend-item">
            <span class="dot bg-green-500"></span>
            Core/Strong (<span x-text="job.annotation_signals?.good_match_count || 0"></span>)
        </span>
        <span class="legend-item">
            <span class="dot bg-yellow-500"></span>
            Partial (<span x-text="job.annotation_signals?.partial_match_count || 0"></span>)
        </span>
        <span class="legend-item">
            <span class="dot bg-red-500"></span>
            Gaps (<span x-text="job.annotation_signals?.gap_count || 0"></span>)
        </span>
    </div>

    <!-- Must-Have Gaps Alert -->
    <div class="gap-alert" x-show="job.annotation_signals?.must_have_gaps?.length > 0">
        <span class="alert-icon">⚠️</span>
        <span class="alert-text">
            <span x-text="job.annotation_signals?.must_have_gaps?.length"></span> must-have gap(s):
            <span x-text="job.annotation_signals?.must_have_gaps?.slice(0, 3).join(', ')"></span>
            <span x-show="job.annotation_signals?.must_have_gaps?.length > 3">...</span>
        </span>
    </div>
</div>
```

### 4.3 API Endpoints

**File**: `frontend/app.py`

```python
# GET /api/jobs/{job_id}/jd-annotations
@app.get("/api/jobs/<job_id>/jd-annotations")
async def get_jd_annotations(job_id: str):
    """Get JD annotations for a job."""
    job = await db.jobs.find_one({"_id": ObjectId(job_id)})
    return job.get("jd_annotations", {
        "annotation_version": "2.0",
        "annotations": [],
        "processed_jd_html": ""
    })

# PUT /api/jobs/{job_id}/jd-annotations
@app.put("/api/jobs/<job_id>/jd-annotations")
async def save_jd_annotations(job_id: str):
    """Save JD annotations for a job."""
    data = await request.get_json()

    await db.jobs.update_one(
        {"_id": ObjectId(job_id)},
        {"$set": {"jd_annotations": data}}
    )

    return {"status": "saved"}
```

---

## 5. Gap Analysis Matrix

### 5.1 Layer-by-Layer Gap Breakdown

| Layer | Current Status | Missing Capability | Gap ID | Priority |
|-------|---------------|-------------------|--------|----------|
| **2.5 STAR Selector** | Disabled | Annotation boost not applied | GAP-090 | P2 |
| **3 Company Research** | No integration | Passion/must-have context | GAP-085 | P2 |
| **3.5 Role Research** | No integration | Annotation-guided focus | GAP-085 | P2 |
| **5 People Mapper** | No integration | Annotation-aware SEO queries | GAP-086 | P3 |
| **6a Cover Letter** | Basic | Passion/identity dimensions | GAP-088 | P1 |
| **6c Outreach** | No integration | Full annotation context | GAP-091 | P2 |
| **6 CV Generator** | Full | ATS validation post-gen | GAP-089 | P2 |
| **6 CV Generator** | Full | Reframe traceability | GAP-092 | P3 |
| **7 Interview** | Partial | Gap-based question prediction | GAP-087 | P2 |
| **7 Outcome** | No integration | Annotation accuracy tracking | GAP-087 | P3 |
| **Frontend** | Full | Section coverage enforcement | GAP-093 | P3 |
| **Frontend** | Full | Review workflow | GAP-094 | P3 |

### 5.2 Dimension Usage Matrix

| Dimension | Layer 2 | Layer 4 | Layer 6 | Layer 6a | Layer 6c | Layer 7 | Frontend |
|-----------|---------|---------|---------|----------|----------|---------|----------|
| **relevance** | ✅ Full | ✅ Full | ✅ Full | ⚠️ Basic | ❌ None | ⚠️ Partial | ✅ Full |
| **requirement_type** | ✅ Full | ✅ Full | ✅ Full | ⚠️ Basic | ❌ None | ❌ None | ✅ Full |
| **passion** | ❌ None | ❌ None | ⚠️ Indexed | ❌ None | ❌ None | ❌ None | ✅ Full |
| **identity** | ❌ None | ❌ None | ⚠️ Indexed | ❌ None | ❌ None | ❌ None | ✅ Full |
| **reframe_note** | ✅ Full | - | ✅ Full | ❌ None | ❌ None | ❌ None | ✅ Full |
| **star_ids** | - | - | ✅ Full | - | - | ⚠️ Partial | ✅ Full |
| **suggested_keywords** | ✅ Full | - | ✅ Full | ❌ None | ❌ None | ❌ None | ✅ Full |
| **ats_variants** | - | - | ⚠️ Stored | ❌ None | ❌ None | ❌ None | ✅ Full |

**Legend:**
- ✅ Full = Actively used and implemented
- ⚠️ Partial/Indexed = Code exists but underutilized
- ❌ None = Not used at all

### 5.3 Impact Scoring

| Gap ID | Impact Area | Severity | Effort | ROI Score |
|--------|-------------|----------|--------|-----------|
| **GAP-088** | CV/Cover authenticity | High | Medium | **9/10** |
| **GAP-091** | Outreach personalization | High | Medium | **8/10** |
| **GAP-090** | STAR selection quality | Medium | Low | **7/10** |
| **GAP-085** | Research relevance | Medium | Medium | **6/10** |
| **GAP-089** | ATS optimization | Medium | Low | **6/10** |
| **GAP-087** | Interview prep quality | Medium | Medium | **5/10** |
| **GAP-086** | Contact discovery | Low | Medium | **4/10** |
| **GAP-092** | Debugging/traceability | Low | Low | **4/10** |
| **GAP-093** | Data quality | Low | Low | **3/10** |
| **GAP-094** | Workflow UX | Low | Medium | **3/10** |

---

## 6. Recommendations & Priority Order

### 6.1 Quick Wins (< 4 hours each)

#### 1. Enable STAR Selector Annotation Boost (GAP-090)
**Effort**: 2 hours | **Impact**: Medium

```python
# Change in src/layer2_5/star_selector.py
STAR_SELECTOR_CONFIG = {
    "enabled": True,  # <- Change from False
    "use_annotation_boost": True,
    ...
}
```

#### 2. Add ATS Keyword Validation Post-Generation (GAP-089)
**Effort**: 3 hours | **Impact**: Medium

```python
# Add to src/layer6_v2/orchestrator.py
async def _validate_ats_coverage(self, cv_text: str, ats_requirements: Dict) -> Dict:
    """Validate that CV meets ATS keyword targets."""
    violations = []
    for keyword, req in ats_requirements.items():
        count = cv_text.lower().count(keyword.lower())
        if count < req["min"]:
            violations.append(f"{keyword}: {count}/{req['min']} occurrences")
    return {"passed": len(violations) == 0, "violations": violations}
```

### 6.2 Medium-Term Improvements (4-16 hours each)

#### 3. Passion/Identity in Cover Letter (GAP-088)
**Effort**: 8 hours | **Impact**: High

- Add passion dimension to cover letter prompt
- Use identity for positioning/tone
- De-emphasize avoid areas

#### 4. Annotation-Aware Outreach (GAP-091)
**Effort**: 12 hours | **Impact**: High

- Pass jd_annotations to outreach generator
- Use passion for genuine hooks
- Use identity for value proposition framing

#### 5. Company Research Annotation Context (GAP-085)
**Effort**: 8 hours | **Impact**: Medium

- Extract must-have priorities for research focus
- Use passion areas to guide culture analysis
- Return annotation-relevant insights

### 6.3 Strategic Enhancements (16+ hours)

#### 6. Full Interview Predictor Integration (GAP-087)
**Effort**: 20 hours | **Impact**: Medium

- Predict gap-based weakness questions
- Provide reframe-based answer preparation
- Link questions to STAR stories

#### 7. Annotation Review Workflow (GAP-094)
**Effort**: 24 hours | **Impact**: Low

- Implement status flow in UI
- Add review queue for pipeline suggestions
- Add approval/rejection with notes

---

## 7. Appendix: File Reference

### Core Type Definitions
- `src/common/annotation_types.py` - All TypedDict definitions
- `src/common/annotation_boost.py` - Boost calculator and multipliers

### Pipeline Integration
- `src/layer2/pain_point_miner.py` - Annotation enrichment (lines 198-415)
- `src/layer4/annotation_fit_signal.py` - Fit signal calculation
- `src/layer6_v2/annotation_header_context.py` - CV context builder
- `src/layer6_v2/orchestrator.py` - CV orchestration with annotations

### Frontend
- `frontend/static/js/jd-annotation.js` - Annotation manager class
- `frontend/templates/job_detail.html` - Heatmap display
- `frontend/templates/partials/job_detail/_annotation_popover.html` - Popover template

### Services
- `src/services/structure_jd_service.py` - JD structuring
- `src/services/cv_generation_service.py` - CV generation entry point
- `src/services/company_research_service.py` - Company research (no annotations)

---

**Report Generated**: 2025-12-10
**Analysis Duration**: Full technical deep-dive
**Lines**: ~2100
