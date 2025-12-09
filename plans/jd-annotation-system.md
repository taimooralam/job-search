# JD Annotation System - Implementation Plan

## Overview

Build a JD (Job Description) annotation system that enables manual marking of JD sections with match strength, reframe notes, STAR story links, and keyword suggestions. This human-in-the-loop enhancement improves **CV, cover letter, AND outreach** personalization, with a **feedback loop to master-cv data** via MongoDB.

**User Choices:**
- Annotation Types: Rich (match strength + reframe notes + STAR links + keywords)
- Suggestions: Both modes (gap analysis first, on-demand fix generation)
- CV Integration: Manual selection (user chooses which annotations apply)
- UI Location: Side panel on job detail page
- Suggestions UI: Modal for reviewing and approving improvements
- Master-CV Sync: MongoDB storage (real-time sync to runner)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     JD Annotation & Feedback Loop                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Raw JD ──▶ LLM Processing ──▶ Structured JD HTML                        │
│                                                                             │
│  2. User annotates in TipTap viewer (read-only with selection)              │
│     └── Select text → Popover → Set strength/STAR/keywords                  │
│                                                                             │
│  3. Annotations stored in Job document (MongoDB)                            │
│     └── jd_annotations: { annotations: [], settings: {} }                   │
│                                                                             │
│  4. User toggles is_active per annotation                                   │
│                                                                             │
│  5. Pipeline uses active annotations to:                                    │
│     ├── Boost linked STAR stories in Layer 2.5                              │
│     ├── Add reframe guidance to Layer 6a (CV) prompts                       │
│     ├── Enhance Layer 6b (Outreach) personalization                         │
│     └── Prioritize suggested keywords in bullet generation                  │
│                                                                             │
│  6. LLM generates improvement suggestions (gaps + fixes)                    │
│     └── User reviews in modal → Approve/Reject                              │
│                                                                             │
│  7. Approved suggestions update MongoDB master-cv collections               │
│     └── Runner reads from MongoDB (real-time sync)                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                     Master-CV MongoDB Storage                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Collections (in jobs database):                                            │
│  ├── master_cv_metadata     ← role_metadata.json content                    │
│  ├── master_cv_taxonomy     ← role_skills_taxonomy.json content             │
│  └── master_cv_roles        ← Individual role markdown files                │
│                                                                             │
│  Benefits:                                                                  │
│  • Real-time sync: Changes immediately available to runner                  │
│  • Version history: Track changes with timestamps                           │
│  • Rollback: Revert to previous versions if needed                          │
│  • No git dependency: Runner doesn't need local files                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## User Journey

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER JOURNEY                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │ 1. VIEW JOB │───▶│ 2. ANNOTATE │───▶│ 3. REVIEW   │───▶│ 4. GENERATE │  │
│  │    DETAIL   │    │    JD       │    │  SUGGESTIONS│    │  CV/OUTREACH│  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│        │                  │                  │                  │          │
│        ▼                  ▼                  ▼                  ▼          │
│  User opens job     User clicks         Modal shows         Pipeline runs  │
│  detail page       "Annotate JD"        gap analysis        with active    │
│                    button               & suggestions        annotations   │
│                         │                    │                             │
│                         ▼                    ▼                             │
│                    ┌─────────────────────────────────────┐                 │
│                    │        ANNOTATION PANEL              │                 │
│                    ├─────────────────────────────────────┤                 │
│                    │                                     │                 │
│                    │  a) JD auto-formatted by LLM        │                 │
│                    │     (whitespace, sections)          │                 │
│                    │                                     │                 │
│                    │  b) User selects text               │                 │
│                    │     └──▶ Popover appears            │                 │
│                    │                                     │                 │
│                    │  c) User sets annotation:           │                 │
│                    │     • Type: skill_match/reframe/    │                 │
│                    │            highlight/comment        │                 │
│                    │     • Relevance: core_strength/     │                 │
│                    │            extremely_relevant/      │                 │
│                    │            relevant/tangential/gap  │                 │
│                    │     • Matching skill (dropdown)     │                 │
│                    │     • Reframe note (optional)       │                 │
│                    │     • STAR stories (multi-select)   │                 │
│                    │     • Keywords (tag input)          │                 │
│                    │     • Comment (free text)           │                 │
│                    │                                     │                 │
│                    │  d) Auto-save to MongoDB            │                 │
│                    │                                     │                 │
│                    │  e) Toggle annotations list view    │                 │
│                    │     • Filter by type/relevance      │                 │
│                    │     • Toggle is_active per item     │                 │
│                    │     • Edit/delete annotations       │                 │
│                    │                                     │                 │
│                    └─────────────────────────────────────┘                 │
│                                                                             │
│                    ┌─────────────────────────────────────┐                 │
│                    │     IMPROVEMENT SUGGESTIONS MODAL   │                 │
│                    ├─────────────────────────────────────┤                 │
│                    │                                     │                 │
│                    │  Tab 1: GAP ANALYSIS                │                 │
│                    │  • Critical gaps (red)              │                 │
│                    │  • Significant gaps (orange)        │                 │
│                    │  • Minor gaps (yellow)              │                 │
│                    │  • Mitigation strategy per gap      │                 │
│                    │                                     │                 │
│                    │  Tab 2: SKILLS TAXONOMY             │                 │
│                    │  • "Add X to section Y" suggestions │                 │
│                    │  • Preview change                   │                 │
│                    │  • [Accept] [Reject] buttons        │                 │
│                    │                                     │                 │
│                    │  Tab 3: ROLE METADATA               │                 │
│                    │  • "Add keyword X to role Y"        │                 │
│                    │  • Preview change                   │                 │
│                    │  • [Accept] [Reject] buttons        │                 │
│                    │                                     │                 │
│                    │  Tab 4: ROLE CONTENT                │                 │
│                    │  • "Add achievement to role file"   │                 │
│                    │  • Diff preview                     │                 │
│                    │  • [Accept] [Reject] buttons        │                 │
│                    │                                     │                 │
│                    │  ───────────────────────────────    │                 │
│                    │  [Accept] → Update MongoDB          │                 │
│                    │           → Version incremented     │                 │
│                    │           → Runner sees immediately │                 │
│                    │                                     │                 │
│                    └─────────────────────────────────────┘                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Calibration & QA (Codex Gap: drift prevention)

### Relevance Level Rubric

To prevent scoring drift, use these calibrated definitions with examples:

| Level | Definition | Example JD Text | Correct Assessment |
|-------|------------|-----------------|-------------------|
| **Core Strength** | Candidate has 5+ years direct experience; could teach others | "Lead engineering teams of 10+" | Core if candidate led 15-person team |
| **Extremely Relevant** | 3-5 years experience; used daily in recent role | "Experience with Kubernetes" | Extremely if candidate deploys K8s weekly |
| **Relevant** | 1-3 years; transferable with minor framing | "CI/CD pipeline expertise" | Relevant if candidate built Jenkins pipelines (not GitHub Actions) |
| **Tangential** | <1 year or adjacent skill | "GraphQL API design" | Tangential if candidate designed REST APIs only |
| **Gap** | No experience; would need training | "AWS Certified Solutions Architect" | Gap if candidate has no AWS certs |

### Requirement Type Rubric

| Type | Definition | Example JD Text | How to Identify |
|------|------------|-----------------|-----------------|
| **Must-Have** | Explicitly required; "required", "must have" | "Must have 5+ years Python" | Uses "must", "required", "essential" |
| **Nice-to-Have** | Preferred but not required | "Experience with Go is a plus" | Uses "preferred", "plus", "bonus", "ideally" |
| **Disqualifier** | Candidate explicitly doesn't want | "Requires 50% travel" | Personal preference; mark if unacceptable |
| **Neutral** | Neither required nor preferred | "Fast-paced environment" | Context/culture statements |

### Annotation Validation Rules (Lints)

Block save if any rule fails:

```python
VALIDATION_RULES = {
    "core_strength_requires_star": {
        "condition": "relevance == 'core_strength' and len(star_ids) == 0",
        "error": "Core strength annotations MUST link at least one STAR story",
        "severity": "error"
    },
    "gap_requires_mitigation": {
        "condition": "relevance == 'gap' and not reframe_note",
        "error": "Gap annotations MUST include a mitigation strategy in reframe_note",
        "severity": "error"
    },
    "must_have_gap_is_critical": {
        "condition": "requirement_type == 'must_have' and relevance == 'gap'",
        "error": "Must-have gap detected - add mitigation or reconsider application",
        "severity": "warning"
    },
    "overlapping_spans": {
        "condition": "overlaps_with_existing_annotation(target)",
        "error": "Annotation overlaps with existing annotation - review for conflicts",
        "severity": "warning"
    },
}
```

### Section Coverage Checklist

Ensure all JD sections are annotated:

```
┌─────────────────────────────────────────────────────────────┐
│              SECTION COVERAGE                               │
├─────────────────────────────────────────────────────────────┤
│ Section           │ Annotations │ Coverage │ Status        │
├───────────────────┼─────────────┼──────────┼───────────────┤
│ Responsibilities  │ 5           │ ████████ │ ✓ Complete    │
│ Qualifications    │ 3           │ ██████░░ │ ⚠ Review      │
│ Technical Skills  │ 0           │ ░░░░░░░░ │ ✗ Missing     │
│ Nice-to-Haves     │ 2           │ ████░░░░ │ ⚠ Review      │
└───────────────────┴─────────────┴──────────┴───────────────┘

Minimum coverage: 1 annotation per section (configurable)
```

---

## Algorithm: Annotation → Pipeline Integration

### 1. Annotation Storage (MongoDB)

```
Job Document (level-2 collection)
├── _id: ObjectId
├── title, company, description, ...
├── jd_annotations: {                    ◄── NEW FIELD
│   ├── annotation_version: 1
│   ├── processed_jd_html: "<p>...</p>"
│   ├── annotations: [
│   │   {
│   │     id: "ann-001",
│   │     target: { section: "responsibilities", index: 2, text: "..." },
│   │     annotation_type: "skill_match",
│   │     relevance: "core_strength",
│   │     matching_skill: "Technical Leadership",
│   │     has_reframe: true,
│   │     reframe_note: "Frame as 'platform modernization leadership'",
│   │     star_ids: ["star-003", "star-007"],
│   │     suggested_keywords: ["platform", "modernization", "leadership"],
│   │     is_active: true,
│   │     priority: 1
│   │   },
│   │   ...
│   │ ]
│   └── settings: { ... }
│ }
├── improvement_suggestions: {           ◄── NEW FIELD
│   ├── gap_analysis: [ ... ],
│   ├── skills_taxonomy_suggestions: [ ... ],
│   └── role_metadata_suggestions: [ ... ]
│ }
└── ... (existing fields)
```

### 2. Annotation Boost Algorithm (Pipeline Integration)

```python
# Called in Layer 2.5 (STAR Selector) and Layer 6 (CV Generator)

def calculate_annotation_influence(
    base_score: float,
    annotation: JDAnnotation,
) -> tuple[float, dict]:
    """
    Calculate boosted score and metadata for pipeline traceability.

    Returns:
        (boosted_score, influence_metadata)
    """

    # Relevance multipliers (5 levels)
    RELEVANCE_MULTIPLIERS = {
        "core_strength": 3.0,       # Massive boost - this IS the candidate
        "extremely_relevant": 2.0,  # Strong boost
        "relevant": 1.5,            # Moderate boost
        "tangential": 1.0,          # No boost, but include
        "gap": 0.3,                 # Penalty - de-prioritize
    }

    # Type modifiers
    TYPE_MODIFIERS = {
        "skill_match": 1.0,         # Standard
        "reframe": 1.2,             # Slight boost for reframe opportunities
        "highlight": 0.8,           # Lower priority
        "comment": 0.5,             # Informational only
    }

    # Priority modifier (1=highest, 5=lowest)
    PRIORITY_MODIFIERS = {
        1: 1.5,
        2: 1.3,
        3: 1.0,
        4: 0.8,
        5: 0.6,
    }

    # Calculate boost
    relevance_mult = RELEVANCE_MULTIPLIERS.get(annotation.get("relevance"), 1.0)
    type_mult = TYPE_MODIFIERS.get(annotation.get("annotation_type"), 1.0)
    priority_mult = PRIORITY_MODIFIERS.get(annotation.get("priority", 3), 1.0)

    boosted_score = base_score * relevance_mult * type_mult * priority_mult

    # Build influence metadata for traceability
    influence_metadata = {
        "annotation_id": annotation["id"],
        "annotation_type": annotation.get("annotation_type"),
        "relevance": annotation.get("relevance"),
        "reframe_applied": annotation.get("reframe_note") if annotation.get("has_reframe") else None,
        "keywords_from_annotation": annotation.get("suggested_keywords", []),
        "boost_factor": boosted_score / base_score if base_score > 0 else 0,
    }

    return boosted_score, influence_metadata


def aggregate_annotation_influence(
    annotations: List[JDAnnotation],
    target_pain_point: str = None,
    target_skill: str = None,
) -> dict:
    """
    Aggregate all active annotations relevant to a target.

    Used to determine which achievements/STARs to prioritize.
    """
    active = [a for a in annotations if a.get("is_active", False)]

    # Filter by target if specified
    if target_pain_point:
        active = [a for a in active if target_pain_point.lower() in a.get("target", {}).get("text", "").lower()]
    if target_skill:
        active = [a for a in active if a.get("matching_skill", "").lower() == target_skill.lower()]

    # Aggregate
    result = {
        "total_annotations": len(active),
        "core_strength_count": len([a for a in active if a.get("relevance") == "core_strength"]),
        "reframe_opportunities": len([a for a in active if a.get("has_reframe")]),
        "linked_star_ids": list(set(s for a in active for s in a.get("star_ids", []))),
        "all_keywords": list(set(k for a in active for k in a.get("suggested_keywords", []))),
        "reframe_notes": [a.get("reframe_note") for a in active if a.get("reframe_note")],
    }

    return result
```

### 3. Prompt Enhancement with Annotations

```python
# In Layer 6 role_generation.py

def format_annotation_guidance_for_prompt(
    annotations: List[JDAnnotation],
) -> str:
    """
    Format active annotations as LLM guidance for bullet generation.
    """
    active = [a for a in annotations if a.get("is_active")]
    active.sort(key=lambda x: (
        {"core_strength": 0, "extremely_relevant": 1, "relevant": 2, "tangential": 3, "gap": 4}.get(x.get("relevance"), 5),
        x.get("priority", 3)
    ))

    lines = [
        "=== ANNOTATION-BASED GUIDANCE (from human review) ===",
        "",
    ]

    for i, ann in enumerate(active[:10], 1):  # Top 10 annotations
        ann_type = ann.get("annotation_type", "unknown")
        relevance = ann.get("relevance", "unknown")
        target_text = ann.get("target", {}).get("text", "")[:60]

        lines.append(f"{i}. [{relevance.upper()}] \"{target_text}...\"")

        if ann.get("matching_skill"):
            lines.append(f"   → Match: {ann['matching_skill']}")

        if ann.get("has_reframe") and ann.get("reframe_note"):
            lines.append(f"   → Reframe: {ann['reframe_note']}")

        if ann.get("suggested_keywords"):
            lines.append(f"   → Keywords: {', '.join(ann['suggested_keywords'][:5])}")

        if ann.get("star_ids"):
            lines.append(f"   → Evidence: STAR {', '.join(ann['star_ids'][:3])}")

        lines.append("")

    return "\n".join(lines)
```

### 4. Improvement Suggestion Generation

```python
# Called when user clicks "Generate Suggestions" button

def generate_improvement_suggestions(
    job_state: JobState,
    annotations: List[JDAnnotation],
    master_cv_data: MasterCVData,
) -> ImprovementSuggestions:
    """
    Analyze gaps and generate improvement suggestions.
    """

    # 1. Find gaps (annotations with relevance="gap")
    gaps = [a for a in annotations if a.get("relevance") == "gap"]

    gap_analysis = []
    for gap in gaps:
        gap_analysis.append(GapAnalysisResult(
            gap_id=str(uuid4()),
            gap_type="skill_gap",  # Could also be "experience_gap", "keyword_gap"
            severity="critical" if gap.get("priority", 3) <= 2 else "significant",
            requirement_text=gap.get("target", {}).get("text", ""),
            closest_match=find_closest_skill(gap, master_cv_data),
            mitigation_strategy=generate_mitigation(gap, master_cv_data),
        ))

    # 2. Suggest skills taxonomy additions
    skills_suggestions = []
    for ann in annotations:
        if ann.get("suggested_keywords"):
            for keyword in ann["suggested_keywords"]:
                if not skill_exists_in_taxonomy(keyword, master_cv_data.taxonomy):
                    skills_suggestions.append(SkillsImprovementSuggestion(
                        suggestion_type="add_skill",
                        target_role=job_state.get("extracted_jd", {}).get("role_category"),
                        skill_name=keyword,
                        reason=f"Appears in JD annotation for '{ann.get('target', {}).get('text', '')[:30]}...'",
                        status="pending",
                    ))

    # 3. Suggest role metadata additions
    role_suggestions = []
    # ... similar logic for role_metadata.json updates

    return ImprovementSuggestions(
        gap_analysis=gap_analysis,
        skills_taxonomy_suggestions=skills_suggestions,
        role_metadata_suggestions=role_suggestions,
    )
```

### 5. Suggestion Approval → MongoDB Update

```python
# API endpoint: PUT /api/master-cv/taxonomy

def approve_suggestion(
    collection: str,  # "metadata", "taxonomy", or "roles"
    suggestion_id: str,
    suggestion_data: dict,
) -> dict:
    """
    Apply approved suggestion to MongoDB master-cv collection.
    """
    db = get_db()

    if collection == "taxonomy":
        # Update skills taxonomy
        current = db.master_cv_taxonomy.find_one({"_id": "canonical"})

        # Apply the change
        if suggestion_data["suggestion_type"] == "add_skill":
            target_role = suggestion_data["target_role"]
            skill_name = suggestion_data["skill_name"]

            # Add to appropriate section
            current["target_roles"][target_role]["sections"][0]["skills"].append(skill_name)

        # Increment version, update timestamp
        current["version"] = current.get("version", 0) + 1
        current["updated_at"] = datetime.utcnow().isoformat()
        current["updated_by"] = "user"

        # Save to history before update
        db.master_cv_taxonomy_history.insert_one({
            "version": current["version"] - 1,
            "data": db.master_cv_taxonomy.find_one({"_id": "canonical"}),
            "timestamp": datetime.utcnow(),
        })

        # Update canonical
        db.master_cv_taxonomy.replace_one({"_id": "canonical"}, current)

        return {"success": True, "new_version": current["version"]}

    # Similar for "metadata" and "roles" collections
```

---

## Implementation Phases

### Phase 1: Schema & Types (Foundation)
**Files to create/modify:**
- `src/common/annotation_types.py` (NEW)
- `src/common/state.py` (ADD fields)

**Schema (Enhanced with Combined Attributes):**
```python
# Skill relevance levels (5 levels for granular matching)
SkillRelevance = Literal[
    "core_strength",      # Perfect match - this IS your core competency
    "extremely_relevant", # Very strong match - directly applicable
    "relevant",           # Good match - transferable with minor framing
    "tangential",         # Weak match - loosely related, needs reframing
    "gap"                 # No match - candidate lacks this skill/experience
]

# Annotation type (primary classification)
AnnotationType = Literal[
    "skill_match",        # JD requirement matches candidate skill
    "reframe",            # Standalone reframe opportunity
    "highlight",          # General highlight for emphasis
    "comment"             # Free-form note/observation
]

class JDAnnotation(TypedDict):
    # === Identification ===
    id: str                         # UUID
    target: TextSpan                # { section, index, text, line_start, line_end }

    # === Audit Trail (Codex Gap: governance) ===
    created_at: str
    created_by: str                 # "human" | "pipeline_suggestion" | "preset"
    updated_at: str
    status: str                     # "draft" | "approved" | "rejected" | "needs_review"
    last_reviewed_by: Optional[str] # Reviewer identifier (for team scenarios)
    review_note: Optional[str]      # Rationale for approval/rejection

    # === Primary Type ===
    annotation_type: AnnotationType # "skill_match" | "reframe" | "highlight" | "comment"

    # === Skill Match Attributes (when type=skill_match) ===
    relevance: Optional[SkillRelevance]  # 5-level strength
    matching_skill: Optional[str]        # Which candidate skill matches

    # === Reframe Attributes (can be standalone OR on skill_match) ===
    has_reframe: bool                    # Whether reframe guidance exists
    reframe_note: Optional[str]          # How to frame/position this
    reframe_from: Optional[str]          # Original skill/experience to reframe
    reframe_to: Optional[str]            # Target framing for JD alignment

    # === Evidence Linking ===
    star_ids: List[str]                  # Linked STAR record IDs
    evidence_summary: Optional[str]      # Brief summary of supporting evidence

    # === Keywords & ATS ===
    suggested_keywords: List[str]        # Keywords to integrate in CV/outreach

    # === Comment (when type=comment OR as additional note) ===
    comment: Optional[str]               # Free-form observation/note

    # === Visual Styling ===
    highlight_color: Optional[str]       # Custom color override (hex)

    # === Pipeline Control ===
    is_active: bool                      # Toggle for CV/outreach generation
    priority: int                        # 1-5 (1 = highest priority)
    confidence: float                    # 0.0-1.0 confidence in assessment

    # === Source Tracking ===
    source: str                          # "auto" | "manual" | "hybrid"
    source_model: Optional[str]          # LLM model if auto-generated


class AnnotationSettings(TypedDict):
    """Per-job annotation settings (Codex Gap: UX efficiency)."""
    job_priority: str                    # "critical" | "high" | "medium" | "low"
    deadline: Optional[str]              # ISO date for application deadline
    require_full_section_coverage: bool  # Enforce annotation per JD section
    section_coverage: Dict[str, bool]    # {"responsibilities": True, "qualifications": False, ...}
    auto_approve_presets: bool           # Auto-approve preset annotations (vs draft)


class JDAnnotations(TypedDict):
    annotation_version: int
    processed_jd_html: str               # LLM-structured JD for display
    annotations: List[JDAnnotation]
    settings: AnnotationSettings
    section_summaries: Dict[str, SectionSummary]

    # === Aggregate Stats ===
    relevance_counts: Dict[str, int]     # Count per relevance level
    type_counts: Dict[str, int]          # Count per annotation type
    reframe_count: int                   # Total reframe opportunities
    gap_count: int                       # Total gaps identified

    # === Validation State (Codex Gap: ATS readiness) ===
    validation_passed: bool              # All lints pass
    validation_errors: List[str]         # ["core_strength without STAR link", ...]
    ats_readiness_score: Optional[int]   # 0-100 based on keyword coverage


class ImprovementSuggestions(TypedDict):
    gap_analysis: List[GapAnalysisResult]
    skills_taxonomy_suggestions: List[SkillsImprovementSuggestion]
    role_metadata_suggestions: List[RoleMetadataImprovementSuggestion]
```

**Relevance Level Colors (for highlighting):**
| Level | Color | Hex | Use Case |
|-------|-------|-----|----------|
| Core Strength | Green | `#22c55e` | Perfect match - emphasize heavily |
| Extremely Relevant | Teal | `#14b8a6` | Strong match - prioritize |
| Relevant | Blue | `#3b82f6` | Good match - include |
| Tangential | Yellow | `#eab308` | Weak match - may need reframe |
| Gap | Red | `#ef4444` | Missing - address or mitigate |
| Reframe (standalone) | Purple | `#a855f7` | Reframe opportunity |
| Highlight | Gray | `#6b7280` | General emphasis |
| Comment | Orange | `#f97316` | Note/observation |

---

### Critical Additions (from Expert Assessment)

**1. Requirement Type (Recruiter Filtering)**
```python
RequirementType = Literal[
    "must_have",       # 1.5x boost - recruiters filter on these FIRST
    "nice_to_have",    # 1.0x - tie-breakers only
    "disqualifier",    # 0.0x - don't even try to match
    "neutral"          # 1.0x - default
]
```

**2. Achievement Context (Quantified Impact)**
```python
# Forces CV bullets to include specific metrics
achievement_context: Optional[Dict] = {
    "metric_type": "percentage" | "dollar" | "time" | "count",
    "target_format": "reduced costs by X% ($Y) through Z",
    "min_impact_threshold": "20%"  # Only use STARs with >= this impact
}
```

**3. ATS Optimization Fields**
```python
# Prevents ATS filtering failures
ats_variants: List[str] = []              # ["Kubernetes", "K8s", "k8s", "kube"]
min_occurrences: Optional[int] = None      # Target: appear 2-3x in resume
max_occurrences: Optional[int] = None      # Avoid keyword stuffing
preferred_sections: List[str] = []         # ["skills", "experience"] - ATS weights sections
exact_phrase_match: bool = False           # Must use exact JD phrasing
```

**4. Concern/Red Flag Annotation**
```python
# Address dealbreakers proactively
class ConcernAnnotation(TypedDict):
    concern: str                           # "on-call rotation"
    severity: str                          # "blocker" | "concern" | "preference"
    mitigation_strategy: str               # How to address in cover letter
    discuss_in_interview: bool             # Flag for interview prep
```

**5. Conflict Resolution**
```python
# At AnnotationSet level
conflict_resolution_strategy: Literal[
    "max_boost",    # Use highest boost when multiple annotations on same text
    "avg_boost",    # Average all boosts
    "last_write"    # Most recent annotation wins
] = "max_boost"
```

**6. Annotation Provenance**
```python
created_by: Literal["human", "pipeline_suggestion"] = "human"
# Enables measuring human vs AI annotation effectiveness
```

**Enhanced Boost Algorithm with All Factors:**
```python
def calculate_total_boost(annotation: JDAnnotation) -> float:
    # Relevance multiplier (5 levels)
    RELEVANCE = {"core_strength": 3.0, "extremely_relevant": 2.0,
                 "relevant": 1.5, "tangential": 1.0, "gap": 0.3}

    # Requirement type multiplier (recruiter priority)
    REQUIREMENT = {"must_have": 1.5, "nice_to_have": 1.0,
                   "disqualifier": 0.0, "neutral": 1.0}

    # Priority multiplier (user importance)
    PRIORITY = {1: 1.5, 2: 1.3, 3: 1.0, 4: 0.8, 5: 0.6}

    # Type modifier
    TYPE = {"skill_match": 1.0, "reframe": 1.2, "achievement_context": 1.3,
            "highlight": 0.8, "comment": 0.5, "concern": 0.0}

    return (RELEVANCE[annotation.relevance] *
            REQUIREMENT[annotation.requirement_type] *
            PRIORITY[annotation.priority] *
            TYPE[annotation.annotation_type])
```

**Add to JobState:**
```python
jd_annotations: Optional[JDAnnotations]
improvement_suggestions: Optional[ImprovementSuggestions]
```

---

### Industry Best Practices (from Expert Assessment)

**1. Skills Gap Heatmap Visualization**
```
Purpose: Visual dashboard showing skill coverage across all annotations

┌─────────────────────────────────────────────────────────────┐
│              SKILLS GAP HEATMAP                             │
├─────────────────────────────────────────────────────────────┤
│ Skill            │ JD Weight │ Candidate │ Gap    │ Action │
├──────────────────┼───────────┼───────────┼────────┼────────┤
│ Kubernetes       │ ████████  │ ████████  │ 0%     │ ✓      │
│ Team Leadership  │ ████████  │ ██████    │ 25%    │ Reframe│
│ AWS Certification│ ██████    │ ░░░░░░    │ 100%   │ Gap    │
│ Python           │ ████      │ ████████  │ Over   │ -      │
└──────────────────┴───────────┴───────────┴────────┴────────┘

Implementation:
- Aggregate annotations by matching_skill
- Calculate coverage % = (candidate_strength / jd_requirement)
- Color code: Green (>80%), Yellow (50-80%), Red (<50%)
- Show in annotation panel summary tab
```

**2. Cover Letter Generation from Concerns**
```python
# Concerns feed directly into cover letter paragraphs
def generate_cover_letter_from_concerns(
    concerns: List[ConcernAnnotation],
    job_state: JobState,
) -> str:
    """
    Proactively address red flags in cover letter.

    Example: "on-call rotation" concern →
    Cover letter paragraph: "I understand the role involves on-call
    responsibilities. In my current position at X, I've established
    efficient on-call rotations that reduced incident response time
    by 40% while maintaining team work-life balance..."
    """
    # Prioritize blockers, then concerns, then preferences
    sorted_concerns = sorted(concerns,
        key=lambda c: {"blocker": 0, "concern": 1, "preference": 2}[c["severity"]])

    # Generate mitigation paragraphs
    # Max 2 concerns addressed in cover letter (don't overexplain)
```

**3. LinkedIn Headline Optimizer**
```python
# Use annotation keywords to suggest headline variants
def suggest_linkedin_headlines(
    annotations: List[JDAnnotation],
    current_headline: str,
) -> List[str]:
    """
    Generate 3-5 headline variants optimized for this JD.

    Approach:
    1. Extract top 3 core_strength keywords
    2. Cross-reference with LinkedIn algorithm preferences
    3. Generate headlines under 120 chars

    Example outputs:
    - "Engineering Manager | Platform Scaling | Kubernetes | Team Builder"
    - "Staff Engineer → Director Track | Systems Architecture | AdTech"
    """
```

**4. Interview Question Predictor**
```python
# Predict interview questions from gap annotations
def predict_interview_questions(
    gap_annotations: List[JDAnnotation],
    concern_annotations: List[ConcernAnnotation],
) -> List[InterviewQuestion]:
    """
    For each gap/concern, predict likely interview questions.

    Example gap: "5+ years Kubernetes" (candidate has 2 years)
    Predicted questions:
    - "Tell me about a complex Kubernetes deployment you managed"
    - "How would you handle migrating legacy apps to K8s?"
    - "What's your approach to learning new infrastructure tools?"

    Store in job document for interview prep feature.
    """

class InterviewQuestion(TypedDict):
    question: str
    source_annotation_id: str
    question_type: str  # "gap_probe", "concern_probe", "behavioral"
    suggested_answer_approach: str
    relevant_star_ids: List[str]
```

**5. Outcome Tracking for Annotation Effectiveness**
```python
# Track whether annotated jobs convert to interviews/offers
class AnnotationOutcome(TypedDict):
    job_id: str
    annotation_count: int
    core_strength_count: int
    gap_count: int
    reframe_count: int

    # Outcomes (updated manually or via integration)
    applied: bool
    response_received: bool
    interview_scheduled: bool
    offer_received: bool

    # Analysis
    response_rate: float  # Calculated across jobs with similar profiles
    interview_rate: float

# Enables: "Jobs with 3+ core_strength annotations have 2.5x interview rate"
```

**6. ATS Keyword Density Checker**
```python
def check_keyword_density(
    cv_text: str,
    annotations: List[JDAnnotation],
) -> KeywordDensityReport:
    """
    Ensure ATS keywords appear correct number of times.

    Rules:
    - Must-have keywords: 2-4 occurrences
    - Nice-to-have keywords: 1-2 occurrences
    - No keyword > 5 occurrences (stuffing penalty)
    - Exact phrase matches where required

    Returns actionable suggestions:
    - "Add 'Kubernetes' 1 more time in Skills section"
    - "Remove 1 occurrence of 'Python' (currently 6x)"
    """
```

---

### Phase 2: Backend API Endpoints
**Files to modify:**
- `frontend/app.py` (ADD routes)

**Endpoints:**
| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/jobs/<id>/jd-annotations` | Get processed JD + annotations |
| PUT | `/api/jobs/<id>/jd-annotations` | Save annotations |
| POST | `/api/jobs/<id>/process-jd` | LLM-process raw JD for annotation |
| POST | `/api/jobs/<id>/generate-suggestions` | Generate improvement suggestions |
| PUT | `/api/jobs/<id>/improvement-suggestions/<id>` | Accept/reject suggestion |

---

### Phase 3: Frontend - Annotation Panel
**Files to create:**
- `frontend/templates/partials/job_detail/_jd_annotation_panel.html`
- `frontend/templates/partials/job_detail/_annotation_popover.html`
- `frontend/templates/partials/job_detail/_annotation_list.html`
- `frontend/templates/partials/job_detail/_section_coverage.html`
- `frontend/templates/partials/job_detail/_validation_errors.html`
- `frontend/static/js/jd-annotation.js`
- `frontend/static/css/jd-annotation.css`

**Files to modify:**
- `frontend/templates/job_detail.html` (ADD panel include + button)
- `frontend/templates/base.html` (ADD TipTap Mark extension import)

**UI Components:**

1. **Side Panel Header** - Job priority badge + deadline indicator
   ```html
   <div class="flex items-center gap-2">
     <span class="badge badge-critical">CRITICAL</span>
     <span class="text-sm text-gray-500">Due: Dec 15</span>
     <span class="ml-auto">ATS Score: 85/100</span>
   </div>
   ```

2. **JD Viewer** - TipTap read-only with custom AnnotationMark extension

3. **Selection Popover** - Appears on text selection with:
   - **Quick Presets** (Codex Gap: UX efficiency):
     ```
     ┌─────────────────────────────────────────────────┐
     │  QUICK ACTIONS                                  │
     ├─────────────────────────────────────────────────┤
     │  [🎯 Core Match]  [⚡ Must-Have Match]          │
     │  [📝 Add Reframe] [⚠️ Gap + Mitigation]         │
     │  [🔗 Link STAR]   [💬 Add Comment]              │
     └─────────────────────────────────────────────────┘
     ```
   - Relevance selector (5 levels with color chips)
   - Requirement type selector (must-have/nice-to-have/disqualifier)
   - STAR story multi-select dropdown
   - Reframe notes textarea
   - Keywords tag input (with ATS variant suggestions)

4. **Section Coverage Panel** (Codex Gap: completeness):
   ```
   ┌─────────────────────────────────────────────────┐
   │  SECTION COVERAGE                    [Expand]   │
   ├─────────────────────────────────────────────────┤
   │  ✓ Responsibilities    5 annotations           │
   │  ⚠ Qualifications      3 annotations           │
   │  ✗ Technical Skills    0 annotations  [→]      │
   │  ⚠ Nice-to-Haves       2 annotations           │
   ├─────────────────────────────────────────────────┤
   │  Progress: ███████░░░ 70%                       │
   └─────────────────────────────────────────────────┘
   ```

5. **Annotation List** - Toggle view with filter by strength/type/status

6. **Validation Errors Panel** (Codex Gap: lints):
   ```
   ┌─────────────────────────────────────────────────┐
   │  ⚠️ 2 ISSUES NEED ATTENTION                     │
   ├─────────────────────────────────────────────────┤
   │  ❌ "Lead engineering teams" (core_strength)    │
   │     Missing STAR link                    [Fix]  │
   │                                                 │
   │  ⚠️ "AWS certification" (gap)                   │
   │     Missing mitigation strategy          [Fix]  │
   └─────────────────────────────────────────────────┘
   ```

7. **Active Toggle** - Per-annotation is_active switch with bulk actions

**Relevance Level Colors:**
| Level | Background | Border | Badge |
|-------|------------|--------|-------|
| Core Strength | `bg-green-500/20` | `border-green-500` | `badge-green` |
| Extremely Relevant | `bg-teal-500/20` | `border-teal-500` | `badge-teal` |
| Relevant | `bg-blue-500/20` | `border-blue-500` | `badge-blue` |
| Tangential | `bg-yellow-500/20` | `border-yellow-500` | `badge-yellow` |
| Gap | `bg-red-500/20` | `border-red-500` | `badge-red` |

---

### Phase 4: Pipeline Integration (CV + Outreach)
**Files to modify:**
- `src/layer2_5/star_selector.py` - Add annotation boost to STAR scoring
- `src/layer6_v2/achievement_mapper.py` - Add annotation keyword boost
- `src/layer6_v2/prompts/role_generation.py` - Add reframe guidance section
- `src/layer6_v2/variant_selector.py` - Add annotation keywords to JD keywords
- `src/layer6_v2/orchestrator.py` - Wire annotations through all phases
- `src/layer6_v2/types.py` - Add traceability fields to GeneratedBullet
- `src/layer6/outreach_generator.py` - Use annotations for outreach personalization

**CV Integration Algorithm:**
```python
# Boost calculation for annotated items
def calculate_annotation_boost(base_score: float, annotation: JDAnnotation) -> float:
    MATCH_MULTIPLIERS = {"strong": 2.0, "medium": 1.5, "weak": 1.0, "gap": 0.5}
    match_mult = MATCH_MULTIPLIERS[annotation["match_strength"]]
    conf_boost = annotation.get("confidence_boost", 0.5)
    return base_score * match_mult * (1 + conf_boost)
```

**Outreach Integration:**
- Layer 5 (People Mapper) receives annotation context:
  - Strong match keywords → emphasize in recruiter messages
  - Reframe notes → shape value proposition per contact type
  - Gap mitigations → address proactively in outreach
- Layer 6b packages annotation-influenced messages

**Traceability fields (add to GeneratedBullet):**
```python
annotation_influenced: bool = False
annotation_ids: List[str] = []
reframe_applied: Optional[str] = None
annotation_keywords_used: List[str] = []
```

---

### Phase 5: MongoDB Master-CV Storage
**Files to create:**
- `src/common/master_cv_store.py` (NEW) - MongoDB CRUD for master-cv data
- `scripts/migrate_master_cv_to_mongo.py` (NEW) - One-time migration script

**Files to modify:**
- `src/layer6_v2/cv_loader.py` - Read from MongoDB with file fallback
- `src/layer6/outreach_generator.py` - Read company list from MongoDB

**MongoDB Collections:**
```python
# Collection: master_cv_metadata (single document)
{
    "_id": "canonical",
    "version": 1,
    "updated_at": "2025-01-15T...",
    "updated_by": "user",
    "candidate": { name, title_base, contact, languages, education, certifications, years_experience },
    "roles": [
        { id, company, title, period, start_year, end_year, is_current, duration_years,
          file, industry, team_size, primary_competencies, keywords, hard_skills, soft_skills,
          achievement_themes, career_stage }
    ]
}

# Collection: master_cv_taxonomy (single document)
{
    "_id": "canonical",
    "version": "1.0",
    "updated_at": "2025-01-15T...",
    "target_roles": { engineering_manager: {...}, staff_principal_engineer: {...}, ... },
    "skill_aliases": { ... },
    "default_fallback_role": "engineering_manager"
}

# Collection: master_cv_roles (one doc per role)
{
    "_id": "01_seven_one_entertainment",
    "role_id": "01_seven_one_entertainment",
    "updated_at": "2025-01-15T...",
    "markdown_content": "# Seven.One Entertainment Group\n...",
    "parsed": {
        "achievements": [...],
        "hard_skills": [...],
        "soft_skills": [...],
        "variants": {...}
    }
}
```

**CVLoader Changes:**
```python
class CVLoader:
    def __init__(self, use_mongodb: bool = True):
        self.use_mongodb = use_mongodb
        self.db = get_db() if use_mongodb else None

    def load(self) -> CandidateData:
        if self.use_mongodb:
            return self._load_from_mongodb()
        return self._load_from_files()  # Fallback for local dev
```

---

### Phase 6: Improvement Suggestions Modal
**Files to create:**
- `frontend/templates/partials/job_detail/_improvement_modal.html` (NEW)
- `frontend/templates/partials/job_detail/_submission_readiness.html` (NEW)
- `frontend/static/js/improvement-modal.js` (NEW)

**Files to modify:**
- `frontend/templates/job_detail.html` (ADD modal + trigger button)
- `frontend/app.py` (ADD endpoints)

**Modal Header - Submission Readiness Badge** (Codex Gap: ATS validation):
```
┌─────────────────────────────────────────────────────────────────────────┐
│  SUBMISSION READINESS                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ KEYWORDS    │  │ SECTIONS    │  │ VARIANTS    │  │ LINTS       │    │
│  │   ✓ PASS    │  │   ✓ PASS    │  │   ⚠ WARN    │  │   ✓ PASS    │    │
│  │   8/10      │  │   4/4       │  │   K8s only  │  │   0 errors  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                         │
│  Overall: ████████████████░░░░ 85% Ready                    [Details]  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ ⚠️ 1 Warning: Add "Kubernetes" variant (currently only "K8s") │    │
│  │   Recommendation: Include both forms for ATS compatibility     │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  [✓ Ready to Apply]  or  [⚠️ Review Issues Before Applying]            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Modal Tabs:**

1. **Gap Analysis Tab**
   - Critical/significant/minor gaps with severity badges
   - Mitigation strategies for each (editable)
   - "Address in CV" toggle
   - "Discuss in interview" checkbox

2. **Skills Taxonomy Tab**
   - Suggested additions: "Add 'Kubernetes' to Technical Leadership section"
   - Preview of change with diff highlight
   - Accept/Reject buttons with rationale field

3. **Role Metadata Tab**
   - Suggested keyword additions per role
   - Competency additions
   - Accept/Reject buttons with rationale field

4. **Role Content Tab**
   - Suggested achievement additions/edits to role markdown files
   - Preview diff (unified diff format)
   - Accept/Reject buttons with rationale field

5. **ATS Readiness Tab** (NEW - Codex Gap):
   - Keyword density report (current vs target)
   - Missing variants list with auto-add button
   - Section presence checklist
   - Parser test results (if available)

**Approval Flow:**
```
User clicks "Accept" →
  API call to /api/master-cv/<collection>/<id> →
    Update MongoDB document →
      Store rationale + actor + timestamp →
        Return success + new version

User clicks "Reject" →
  Prompt for rationale (required) →
    Store rejection with reasoning →
      Feed back into LLM prompt tuning
```

**API Endpoints:**
| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/master-cv/metadata` | Get current role_metadata |
| PUT | `/api/master-cv/metadata` | Update role_metadata |
| GET | `/api/master-cv/taxonomy` | Get skills taxonomy |
| PUT | `/api/master-cv/taxonomy` | Update skills taxonomy |
| GET | `/api/master-cv/roles/<id>` | Get role content |
| PUT | `/api/master-cv/roles/<id>` | Update role content |
| GET | `/api/master-cv/history/<collection>` | Get version history |
| POST | `/api/master-cv/rollback/<collection>/<version>` | Rollback to version |

---

### Phase 7: LLM JD Processing
**Files to create:**
- `src/layer1_4/jd_processor.py` (NEW) - Format JD for annotation

**Processing steps:**
1. Parse raw JD text
2. Add semantic whitespace (paragraphs between sections)
3. Structure into responsibilities/qualifications/skills sections
4. Output HTML with `<section>` tags for annotation targeting

---

## File Change Summary

| File | Action | Scope |
|------|--------|-------|
| **Schema & Types** | | |
| `src/common/annotation_types.py` | CREATE | TypedDict definitions (JDAnnotation, ConcernAnnotation, InterviewQuestion, AnnotationOutcome, AnnotationSettings) |
| `src/common/annotation_validator.py` | CREATE | Validation rules (lints) implementation |
| `src/common/state.py` | MODIFY | Add 3 fields to JobState (jd_annotations, improvement_suggestions, interview_prep) |
| `src/common/master_cv_store.py` | CREATE | MongoDB CRUD for master-cv with history |
| **Backend API** | | |
| `frontend/app.py` | MODIFY | Add ~25 API endpoints (annotations, master-cv, ATS readiness, interview prep) |
| **Frontend - Annotation Panel** | | |
| `frontend/templates/partials/job_detail/_jd_annotation_panel.html` | CREATE | ~300 lines (panel with header, priority badge, ATS score) |
| `frontend/templates/partials/job_detail/_annotation_popover.html` | CREATE | ~200 lines (quick presets, relevance, requirement type) |
| `frontend/templates/partials/job_detail/_annotation_list.html` | CREATE | ~120 lines |
| `frontend/templates/partials/job_detail/_section_coverage.html` | CREATE | ~80 lines (coverage checklist + progress bar) |
| `frontend/templates/partials/job_detail/_validation_errors.html` | CREATE | ~60 lines (lint errors panel) |
| `frontend/templates/partials/job_detail/_skills_heatmap.html` | CREATE | ~100 lines (visual gap coverage) |
| `frontend/static/js/jd-annotation.js` | CREATE | ~600 lines (includes presets, validation) |
| `frontend/static/css/jd-annotation.css` | CREATE | ~250 lines |
| **Frontend - Improvement Modal** | | |
| `frontend/templates/partials/job_detail/_improvement_modal.html` | CREATE | ~350 lines |
| `frontend/templates/partials/job_detail/_submission_readiness.html` | CREATE | ~100 lines (readiness badge) |
| `frontend/static/js/improvement-modal.js` | CREATE | ~400 lines |
| **Frontend - Interview Prep** | | |
| `frontend/templates/partials/job_detail/_interview_prep_panel.html` | CREATE | ~150 lines |
| `frontend/static/js/interview-prep.js` | CREATE | ~200 lines |
| **Frontend - Analytics** | | |
| `frontend/templates/partials/dashboard/_outcome_dashboard.html` | CREATE | ~150 lines (conversion rates) |
| **Frontend - Common** | | |
| `frontend/templates/job_detail.html` | MODIFY | Add includes + buttons |
| `frontend/templates/base.html` | MODIFY | Add TipTap Mark import |
| **Pipeline - JD Processing** | | |
| `src/layer1_4/jd_processor.py` | CREATE | JD structuring to sections + HTML spans [Phase 1 - BLOCKING] |
| **Pipeline - CV (Phase 5)** | ✅ COMPLETE | |
| `src/layer2_5/star_selector.py` | ✅ MODIFIED | Annotation boost already in Phase 4 |
| `src/layer6_v2/achievement_mapper.py` | ✅ MODIFIED | Add annotation keyword boost (+50 lines) |
| `src/layer6_v2/prompts/role_generation.py` | ✅ MODIFIED | Add reframe guidance section (+100 lines) |
| `src/layer6_v2/variant_selector.py` | ✅ MODIFIED | Annotation keywords already in Phase 4 |
| `src/layer6_v2/orchestrator.py` | ✅ MODIFIED | Wired annotations |
| `src/layer6_v2/types.py` | ✅ MODIFIED | Traceability fields already in Phase 4 |
| `src/layer6_v2/cv_loader.py` | ✅ MODIFIED | MongoDB support with file fallback (+150 lines) |
| `src/layer6_v2/variant_parser.py` | ✅ MODIFIED | Add parse_content() for MongoDB content (+45 lines) |
| `src/layer6_v2/skills_taxonomy.py` | ✅ MODIFIED | Add from_dict() for MongoDB support (+25 lines) |
| `src/layer6_v2/ats_checker.py` | ✅ CREATED | Keyword density checker + variant validation (~350 lines) |
| `tests/unit/test_ats_checker.py` | ✅ CREATED | 28 unit tests for ATS checker |
| **Pipeline - Header/Summary (Phase 4.5)** | ✅ COMPLETE | |
| `src/layer6_v2/annotation_header_context.py` | ✅ CREATED | Priority extraction, context builder, gap mitigation (~300 lines) |
| `src/layer6_v2/header_generator.py` | ✅ MODIFIED | Add annotation context integration (+150 lines) |
| `src/layer6_v2/ensemble_header_generator.py` | ✅ MODIFIED | Pass annotation context to personas (+80 lines) |
| `src/layer6_v2/prompts/header_generation.py` | ✅ MODIFIED | Add annotation guidance section to prompts (+100 lines) |
| `src/layer6_v2/skills_taxonomy.py` | ✅ MODIFIED | Add annotation-aware scoring (+120 lines) |
| `src/layer6_v2/types.py` | ✅ MODIFIED | Add AnnotationPriority, HeaderGenerationContext, ATSRequirement, HeaderProvenance |
| `src/layer6_v2/orchestrator.py` | ✅ MODIFIED | Wire annotation context through header generation |
| `tests/unit/test_annotation_header_context.py` | ✅ CREATED | 39 unit tests for annotation header context (~450 lines) |
| **Pipeline - Outreach** | | |
| `src/layer5/people_mapper.py` | MODIFY | Pass annotation context |
| `src/layer6/outreach_generator.py` | MODIFY | Use annotations + concerns |
| `src/layer6/cover_letter_generator.py` | MODIFY | Add concern mitigation paragraphs |
| **Pipeline - LinkedIn** | | |
| `src/layer6/linkedin_optimizer.py` | CREATE | Headline variants generator |
| **Pipeline - Interview Prep** | | |
| `src/layer7/interview_predictor.py` | CREATE | Gap-based question predictor |
| **Analytics** | | |
| `src/analytics/outcome_tracker.py` | CREATE | Annotation effectiveness tracking + conversion metrics |
| **Documentation** | | |
| `docs/calibration_rubric.md` | CREATE | Relevance/requirement level definitions with examples |
| **Migration** | | |
| `scripts/migrate_master_cv_to_mongo.py` | CREATE | One-time migration |

---

## Implementation Order

**Critical Dependency Fix (Codex Gap):** JD Processing moved to Phase 1 - all UI/pipeline features depend on structured JD sections.

```
Phase 1: Foundation & JD Processing (2.5 days) [BLOCKING]
    ├── jd_processor.py - JD structuring to sections + HTML spans
    ├── annotation_types.py (all TypedDicts with audit fields)
    ├── state.py modifications (3 new fields)
    ├── Calibration rubric documentation
    └── Validation rules (lints) implementation

Phase 2: MongoDB & API (2 days)
    ├── master_cv_store.py (MongoDB CRUD with history)
    ├── migrate_master_cv_to_mongo.py (run once)
    ├── Annotation endpoints (GET/PUT with validation)
    ├── Master-CV endpoints (CRUD + history + rollback)
    ├── ATS readiness check endpoint
    └── Interview prep endpoints

Phase 3: Frontend - Annotation Panel (3-4 days)
    ├── Panel template (follow CV editor pattern)
    ├── TipTap AnnotationMark extension
    ├── Quick-action presets (Core Match, Must-Have, Gap+Mitigation)
    ├── Selection popover (with requirement type, concerns)
    ├── Section coverage checklist + progress bar
    ├── Validation errors panel
    ├── Annotation list view with filters
    └── Auto-save with debounce + offline warning

Phase 4: Frontend - Improvement Modal (2.5 days)
    ├── Submission Readiness badge (keywords/sections/variants/lints)
    ├── Tabbed modal UI (Gap Analysis, Taxonomy, Metadata, Roles, ATS)
    ├── Gap analysis display with severity badges
    ├── Suggestion preview + diff
    ├── Accept/reject flow with required rationale
    └── Skills gap heatmap visualization

Phase 4.5: Annotation-Driven Header/Summary/Skills (3 days)  ✅ COMPLETE
    ├── ✅ Priority extraction from annotations (must-have > core_strength)
    ├── ✅ Header assembly with annotation context (title + tagline ≤90 chars)
    ├── ✅ Professional summary (60/30/10 formula with reframes + gap mitigation)
    ├── ✅ Core skills prioritization (12-18 skills, 2-3 columns by annotation relevance)
    ├── ✅ ATS optimization (acronym + full form, keyword density 2-4x)
    ├── ✅ Prompt enhancement with annotation guidance section
    └── ✅ Provenance tracking for all annotation influences

    Why Phase 4.5? Header/summary receives 80% of recruiter attention in first 7.4s.
    Current plan only uses annotations for STAR/variant selection, not the critical
    header section. Research shows exact JD title = 10.6x interview probability.

Phase 5: Pipeline Integration - CV (2-3 days)  ✅ COMPLETE
    ├── ✅ CVLoader MongoDB support with file fallback
    ├── ✅ STAR selector boost (already in Phase 4)
    ├── ✅ Achievement mapper with annotation keyword boost
    ├── ✅ Role generator prompt enhancement with reframe guidance
    ├── ✅ Traceability fields (already in GeneratedBullet)
    └── ✅ ATS keyword density checker + variant validation

Phase 6: Pipeline Integration - Outreach (1.5 days) ✅ COMPLETED 2025-12-09
    ├── ✅ People mapper annotation context (`src/layer5/people_mapper.py`)
    ├── ✅ Outreach generator enhancements
    ├── ✅ Cover letter concern mitigation paragraphs (`src/layer6/cover_letter_generator.py`)
    └── ✅ LinkedIn headline optimizer (`src/layer6/linkedin_optimizer.py`)

Phase 7: Interview Prep & Analytics (2 days)
    ├── Interview question predictor from gaps
    ├── Interview prep panel UI
    ├── Outcome tracking (applied/response/interview/offer)
    └── Annotation effectiveness dashboard (conversion by density)
```

**Total estimated: 18-21 days** (includes Phase 4.5)

### Phased Rollout Strategy

```
MVP (12-14 days) - Core Annotation + CV Integration + Header Generation
    ├── Phase 1: Foundation + JD Processing [BLOCKING]
    ├── Phase 2: API + ATS readiness checks
    ├── Phase 3: Annotation panel with presets + validation
    ├── Phase 4.5: Header/Summary/Skills with annotation context  ◄── CRITICAL
    ├── Phase 5: CV integration with traceability
    └── Outcome tracking foundation (captures conversions from day 1)

Enhancement 1 (3-4 days) - Improvement Suggestions + Heatmap
    ├── Phase 4: Improvement modal with submission readiness
    ├── Skills gap heatmap
    └── Master-CV feedback loop with rationale

Enhancement 2 (2-3 days) - Outreach + LinkedIn
    └── Phase 6: Outreach integration + concern mitigation

Enhancement 3 (2 days) - Interview Prep + Analytics Dashboard
    ├── Phase 7: Interview predictor
    └── Conversion analytics dashboard
```

**Why Phase 4.5 is in MVP**: Research from cv-guide.plan.md shows:
- Profile receives **80% of initial attention** in recruiter's 6-7 second scan
- Exact JD title = **10.6x more likely** to get interview
- 60/30/10 formula: 60% achievements, 30% qualifications, 10% identity
- Without annotation-driven header, the human feedback loop doesn't influence
  the most critical CV section

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| TipTap read-only mode | Prevents JD edits while enabling selection |
| Custom Mark extension | Allows annotation styling without modifying JD |
| Character offsets for spans | More stable than DOM positions for persistence |
| Multiplicative boost | Preserves relative rankings while elevating annotated items |
| `is_active` toggle | Enables manual selection without deleting annotations |
| Auto-save 3s debounce | Matches CV editor pattern, prevents data loss |
| Backward compatible | Empty annotations = existing pipeline behavior |
| MongoDB for master-cv | Real-time sync to runner without git dependency |
| Single canonical doc | One document per collection with version tracking |
| File fallback in CVLoader | Local development can still use files |
| Tabbed modal for suggestions | Organize by suggestion type (gaps, taxonomy, roles) |
| Version history + rollback | Safety net for approved changes |
| **Requirement type field** | Recruiters filter must-haves first; disqualifiers get 0.0x boost |
| **ConcernAnnotation separate** | Red flags need dedicated handling for cover letters |
| **ATS variant arrays** | Multiple keyword forms (K8s/Kubernetes) ensure ATS matching |
| **Interview question link to gaps** | Prepare for likely questions before they arise |
| **Outcome tracking in MVP** | Capture conversion data from day 1 to measure uplift (Codex Gap) |
| **Phased rollout** | MVP in 9-11 days with enhancements added incrementally |
| **max_boost conflict resolution** | When multiple annotations overlap, use highest boost (most relevant signal) |
| **JD Processing Phase 1** | Critical dependency - all UI/pipeline features need structured sections (Codex Gap) |
| **Validation lints block save** | Enforce quality: core_strength requires STAR, gap requires mitigation (Codex Gap) |
| **Quick-action presets** | Reduce annotation friction (Codex Gap: UX efficiency) |
| **Rejection rationale required** | Feed rejections back into LLM prompt tuning (Codex Gap: governance) |
| **Section coverage checklist** | Ensure completeness before submission (Codex Gap: UX efficiency) |
| **ATS acronym strategy** | Always include BOTH acronym AND full form (ats-guide.md: Greenhouse/Lever/Taleo don't recognize abbreviations) |
| **Keyword density 2-4x** | Repeat must-have keywords 2-4x naturally (ats-guide.md: 5 mentions > 2 mentions in Greenhouse ranking) |
| **Reframe-first gap handling** | If gap has reframe_note → apply; otherwise omit from header/summary (keep positive-focused) |
| **12-18 skills in 2-3 columns** | Standard grouped format by category (Leadership, Technical, Platform) |
| **Header provenance tracking** | Record annotation_ids, STAR_ids, reframes applied for QA and traceability |

---

## Future Considerations (Deferred)

Items identified but deferred to avoid over-engineering MVP:

| Item | Description | When to Add |
|------|-------------|-------------|
| **PII Redaction Hook** | Scan free-text fields before MongoDB writes; implement retention policy | Before production with sensitive data |
| **ATS Parser Stubs** | Test CVs against Greenhouse/Workday-like parsers | When ATS pass rate drops below 90% |
| **Weekly Drift Audit** | Sample 10% annotations, reconcile scores across team | When team size > 1 |
| **Reviewer Workflow** | Approve/reject annotations with multi-user support | When team size > 1 |
| **Offline Retry Queue** | Queue failed saves for retry when connection restored | When mobile/unreliable network use case emerges |
| **Annotation Templates** | Pre-built annotation sets for common role types | After pattern emerges from 50+ annotated JDs |

---

## Testing Strategy

1. **Unit tests** for annotation boost calculations
2. **Unit tests** for MongoDB master-cv store operations
3. **Integration tests** for API endpoints (annotations + master-cv)
4. **E2E tests** for annotation flow (select → annotate → save → pipeline)
5. **E2E tests** for suggestion approval flow (suggest → approve → verify MongoDB)
6. **Manual testing** with real JDs
7. **Runner verification** - Ensure runner reads updated master-cv from MongoDB

---

## Success Criteria

### Core Annotation (MVP)
- [ ] User can select text in JD and create annotations
- [ ] Annotations persist to MongoDB with auto-save (< 3s latency)
- [ ] 5-level relevance system (core_strength → gap) works correctly
- [ ] Requirement type (must_have/nice_to_have/disqualifier) captured
- [ ] Active annotations influence CV bullet generation
- [ ] Reframe notes appear in generated bullet traceability
- [ ] Pipeline works normally when no annotations present (backward compatible)

### Calibration & QA (Codex Gap: drift prevention)
- [ ] Calibration rubric documented with examples for all relevance/requirement levels
- [ ] Validation rules block save for missing STAR on core_strength
- [ ] Validation rules block save for missing mitigation on gaps
- [ ] Section coverage checklist enforces minimum 1 annotation per section
- [ ] **Target: < 10% scoring drift** (sample 10% annotations, reconcile monthly)

### ATS Optimization
- [ ] ATS variants stored (e.g., Kubernetes/K8s/k8s)
- [ ] Keyword density checker validates CV output
- [ ] Preferred sections guide keyword placement
- [ ] Submission Readiness badge shows pass/fail
- [ ] **Target: > 95% ATS readiness pass rate** on submitted applications

### Header/Summary/Skills (Phase 4.5) ✅ COMPLETE
- [x] Annotation priorities extracted and ranked (must_have + core_strength first)
- [x] Header title selection uses annotation signals (exact JD title when possible)
- [x] Tagline includes top 2 must-have skills (≤90 chars)
- [x] Professional summary uses 60/30/10 formula with annotation context
- [x] Summary references linked STAR metrics for proof lines
- [x] Reframe notes applied where annotation `has_reframe=true`
- [x] Gap handling: reframe if `reframe_note` exists, otherwise omit from header
- [x] Core skills section: 12-18 skills in 2-3 columns
- [x] Skills prioritized by annotation relevance (core_strength > must_have > etc.)
- [x] ATS acronym strategy: both forms included (e.g., "Kubernetes (K8s)")
- [x] Keyword density: must-haves appear 2-4x across header/summary/skills
- [x] Provenance tracked: annotation_ids, STAR_ids, reframes applied
- [ ] **Target: 10.6x interview probability** with exact JD title matching (to be validated)

### Improvement Suggestions
- [ ] Improvement suggestions modal shows gaps + fixes
- [ ] User can accept suggestions which update MongoDB
- [ ] Rejection requires rationale (for LLM prompt tuning)
- [ ] CVLoader reads from MongoDB (runner gets real-time updates)
- [ ] Version history allows rollback of master-cv changes
- [ ] Skills gap heatmap displays coverage visually

### Outreach Integration
- [ ] Active annotations influence outreach personalization
- [ ] Concerns generate mitigation paragraphs in cover letters
- [ ] LinkedIn headline variants generated from core strengths

### Interview Prep
- [ ] Gap annotations generate predicted interview questions
- [ ] Interview prep panel shows questions with suggested approaches
- [ ] STAR stories linked to predicted questions

### Analytics & Outcome Tracking (Codex Gap: uplift measurement)
- [ ] Outcome tracking captures: applied → response → interview → offer
- [ ] Annotation counts stored per job (core_strength, gap, reframe counts)
- [ ] Dashboard shows conversion rates by annotation profile
- [ ] **Target deltas:**
  - **+20% response rate** for jobs with ≥3 core_strength annotations
  - **+10% interview rate** for jobs with ≥70% section coverage
  - **-30% rejection rate** for jobs with 0 must-have gaps
- [ ] CSV export available for offline analysis

---

## Migration Checklist

Before going live:
- [ ] Run `migrate_master_cv_to_mongo.py` to populate MongoDB
- [ ] Verify MongoDB collections have correct data
- [ ] Update runner to use `CVLoader(use_mongodb=True)`
- [ ] Test pipeline end-to-end with MongoDB-sourced master-cv
- [ ] Verify local dev still works with file fallback
