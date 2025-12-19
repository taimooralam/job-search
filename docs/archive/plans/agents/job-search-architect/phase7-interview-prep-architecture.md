# Architecture Analysis: Phase 7 - Interview Prep & Analytics

## 1. Requirements Understanding

### Phase 7 Components (from `jd-annotation-system.md`)

1. **Interview Question Predictor** - Generate likely interview questions from JD gaps and concerns
2. **Interview Prep Panel UI** - Frontend panel showing predicted questions with STAR-based answers
3. **Outcome Tracking** - Track application outcomes (applied/response/interview/offer)

### Assumptions

- Phase 6 (Pipeline Integration - Outreach) is complete
- The annotation system already has: JD annotations, concern tracking, STAR evidence linking, LinkedIn headline optimizer
- Existing types `InterviewQuestion`, `InterviewPrep`, and `AnnotationOutcome` are defined in `src/common/annotation_types.py`
- The `interview_prep` field exists in `JobState` but is unused
- Frontend job detail page already has extensive sections for CV, cover letter, contacts, and JD annotations

### Constraints

- Quality over speed - correctness and anti-hallucination over throughput
- All generation must cite sources from provided context (gap annotations, concerns)
- JSON-only outputs with Pydantic validation
- Env-driven config - no hardcoded secrets
- Explicit state - LangGraph state passed explicitly

## 2. System Impact Assessment

### Components Affected

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PHASE 7 SYSTEM IMPACT                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  NEW COMPONENTS:                                                         │
│  ├── src/layer7/interview_predictor.py        (Interview Q generator)   │
│  ├── src/analytics/outcome_tracker.py         (Outcome tracking)        │
│  ├── frontend/templates/partials/job_detail/                            │
│  │   ├── _interview_prep_panel.html           (Interview prep UI)       │
│  │   └── _outcome_tracker.html                (Outcome tracking UI)     │
│  ├── frontend/static/js/interview-prep.js     (Panel JS)                │
│  └── frontend/static/js/outcome-tracker.js    (Tracker JS)              │
│                                                                          │
│  MODIFIED COMPONENTS:                                                    │
│  ├── frontend/app.py                          (+6 API endpoints)        │
│  ├── frontend/templates/job_detail.html       (Include new panels)      │
│  ├── src/common/state.py                      (interview_prep used)     │
│  └── src/common/annotation_types.py           (Minor additions)         │
│                                                                          │
│  DATABASE:                                                               │
│  ├── level-2 collection: +interview_prep, +outcome fields per job       │
│  └── NEW analytics collection: annotation_outcomes (aggregation)        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Integration Points

1. **Gap Annotations -> Interview Questions**: Annotations with `relevance="gap"` trigger question generation
2. **Concern Annotations -> Interview Questions**: `ConcernAnnotation` items with `discuss_in_interview=True`
3. **STAR Records -> Answer Suggestions**: Link existing STARs to predicted questions for prep
4. **Outcome Data -> Analytics**: Track conversions to measure annotation effectiveness

## 3. Options Considered

### 3.1 Interview Question Predictor - Where to Place

| Aspect | Option A: Standalone Module | Option B: Pipeline Layer | Option C: Frontend-Only |
|--------|---------------------------|-------------------------|------------------------|
| **Approach** | New `src/layer7/interview_predictor.py` callable on-demand | Add as Layer 7.5 in pipeline graph | Generate client-side with LLM API |
| **Pros** | Flexible, testable, can be called from API | Automatic generation with pipeline | No backend changes |
| **Cons** | Needs explicit API trigger | Always runs (cost overhead) | No server-side validation, API key exposure |
| **Complexity** | Medium | Medium-High | Low |
| **Risk** | Low - isolated module | Medium - modifies pipeline | High - security concern |

**Recommendation: Option A (Standalone Module)**

*Rationale:* Interview prep is not needed for all jobs - only those the user intends to interview for. Making it on-demand reduces LLM costs and aligns with the "manual selection" pattern established in the annotation system.

### 3.2 Interview Prep Panel UI - Layout Choice

| Aspect | Option A: Collapsible Section | Option B: Tab Panel | Option C: Modal |
|--------|------------------------------|---------------------|-----------------|
| **Approach** | Collapsible `<details>` like "Intelligence Summary" | New tab in job detail | Modal popup on button click |
| **Pros** | Consistent with existing UI, always visible | Clean separation, organized | Non-intrusive, focused view |
| **Cons** | Page gets longer | Requires refactoring page structure | Context switch, loses job context |
| **Complexity** | Low | High | Medium |
| **Risk** | Low | Medium | Low |

**Recommendation: Option A (Collapsible Section)**

*Rationale:* The job detail page already uses collapsible sections for "Intelligence Summary" and "Full Job Description". Adding Interview Prep as another collapsible maintains UI consistency and keeps all interview-relevant info on one page.

### 3.3 Outcome Tracking UI - Display Style

| Aspect | Option A: Status Badge + Dropdown | Option B: Timeline View | Option C: Kanban-style |
|--------|----------------------------------|------------------------|----------------------|
| **Approach** | Badge in header, dropdown to update | Vertical timeline showing progression | Drag-drop between columns |
| **Pros** | Compact, matches existing status UI | Visual journey, good for history | Intuitive status changes |
| **Cons** | Less visual feedback | Takes more space | Overkill for single job view |
| **Complexity** | Low | Medium | High |
| **Risk** | Low | Low | Medium |

**Recommendation: Option A (Status Badge + Dropdown)**

*Rationale:* The job detail page already has a status dropdown in the "Status & Actions" section. Extending this with outcome tracking badges is the most consistent approach. A timeline view can be added later as an enhancement for the analytics dashboard.

## 4. Recommended Architecture

### 4.1 Data Model Additions

The types already exist in `src/common/annotation_types.py`. Minor enhancements needed:

```python
# In src/common/annotation_types.py - EXISTING (with minor additions)

class InterviewQuestion(TypedDict):
    """Predicted interview question based on gaps/concerns."""
    question_id: str                        # UUID
    question: str                           # The predicted question
    source_annotation_id: str               # Gap/concern annotation that triggered this
    source_type: str                        # NEW: "gap" | "concern" | "general"
    question_type: str                      # "gap_probe" | "concern_probe" | "behavioral"
    difficulty: str                         # NEW: "easy" | "medium" | "hard"
    suggested_answer_approach: str          # How to approach answering
    sample_answer_outline: Optional[str]    # NEW: Brief answer structure (not full answer)
    relevant_star_ids: List[str]            # STAR stories to reference
    practice_status: str                    # NEW: "not_started" | "practiced" | "confident"
    user_notes: Optional[str]               # NEW: User's own answer notes
    created_at: str


class InterviewPrep(TypedDict):
    """Interview preparation data for a job."""
    predicted_questions: List[InterviewQuestion]
    gap_summary: str                        # Summary of gaps to address
    concerns_summary: str                   # Summary of concerns to address
    company_context: str                    # NEW: Key company facts for interview
    role_context: str                       # NEW: Key role insights
    generated_at: str
    generated_by: str                       # NEW: Model used for generation


# Outcome Status Constants - NEW
OutcomeStatus = Literal[
    "not_applied",                          # Default state
    "applied",                              # Application submitted
    "response_received",                    # Got a response (any type)
    "screening_scheduled",                  # Phone/video screen scheduled
    "interview_scheduled",                  # Interview scheduled
    "interviewing",                         # In interview process
    "offer_received",                       # Got an offer
    "offer_accepted",                       # Accepted the offer
    "rejected",                             # Application rejected
    "withdrawn",                            # User withdrew
]


class ApplicationOutcome(TypedDict):
    """
    Tracks application outcome for a specific job.
    Stored in job document for per-job tracking.
    """
    status: str                             # OutcomeStatus value
    applied_at: Optional[str]               # ISO timestamp
    applied_via: Optional[str]              # "linkedin" | "website" | "email" | "referral"
    response_at: Optional[str]
    response_type: Optional[str]            # "rejection" | "interest" | "screening"
    screening_at: Optional[str]
    interview_at: Optional[str]
    interview_rounds: int                   # Number of interview rounds
    offer_at: Optional[str]
    offer_details: Optional[str]            # Brief notes about offer
    final_status_at: Optional[str]          # When final status was set
    notes: Optional[str]                    # User notes

    # Computed for analytics
    days_to_response: Optional[int]
    days_to_interview: Optional[int]
    days_to_offer: Optional[int]
```

### 4.2 Backend Components

#### 4.2.1 Interview Question Predictor

**File:** `src/layer7/interview_predictor.py`

```python
"""
Interview Question Predictor (Phase 7).

Generates likely interview questions from JD gaps and concerns.
Uses gap annotations and concern annotations as source material.

Key Features:
- Questions grounded in actual gaps (anti-hallucination)
- STAR story linking for answer preparation
- Difficulty classification for practice prioritization
- Sample answer outlines (not full answers - user should prep)
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage

from src.common.annotation_types import (
    JDAnnotation, ConcernAnnotation, InterviewQuestion, InterviewPrep
)
from src.common.state import JobState
from src.common.llm_factory import create_tracked_llm
from src.common.config import Config


QUESTION_TYPES = {
    "gap_probe": "Question that probes a skill/experience gap",
    "concern_probe": "Question that addresses a red flag or concern",
    "behavioral": "Behavioral question (STAR format expected)",
    "technical": "Technical deep-dive question",
    "situational": "Hypothetical situation question",
}


class InterviewPredictor:
    """
    Predicts interview questions from gaps and concerns.

    Algorithm:
    1. Extract gap annotations (relevance="gap")
    2. Extract concerns marked for interview discussion
    3. For each gap/concern, generate 1-3 likely questions
    4. Link relevant STAR stories for answer preparation
    5. Classify difficulty and provide answer approach
    """

    def __init__(self):
        self.llm = create_tracked_llm(
            model=Config.DEFAULT_MODEL,
            temperature=0.3,  # Lower temp for more consistent predictions
            layer="layer7_interview_prep",
        )

    def predict_questions(
        self,
        state: JobState,
        max_questions: int = 10,
    ) -> InterviewPrep:
        """
        Generate interview questions from job state.

        Args:
            state: JobState with annotations, concerns, STARs
            max_questions: Maximum questions to generate

        Returns:
            InterviewPrep with predicted questions
        """
        # Extract gaps and concerns
        jd_annotations = state.get("jd_annotations") or {}
        annotations = jd_annotations.get("annotations", [])
        concerns = jd_annotations.get("concerns", [])

        gaps = [a for a in annotations if a.get("relevance") == "gap"]
        interview_concerns = [c for c in concerns if c.get("discuss_in_interview")]

        # Get available STARs for linking
        all_stars = state.get("all_stars") or state.get("selected_stars") or []
        star_map = {s.get("id"): s for s in all_stars if s.get("id")}

        # Generate questions via LLM
        questions = self._generate_questions(
            gaps=gaps,
            concerns=interview_concerns,
            job_title=state.get("title", ""),
            company=state.get("company", ""),
            all_stars=all_stars,
            max_questions=max_questions,
        )

        # Build summaries
        gap_summary = self._build_gap_summary(gaps)
        concerns_summary = self._build_concerns_summary(interview_concerns)

        return InterviewPrep(
            predicted_questions=questions,
            gap_summary=gap_summary,
            concerns_summary=concerns_summary,
            company_context=self._extract_company_context(state),
            role_context=self._extract_role_context(state),
            generated_at=datetime.utcnow().isoformat(),
            generated_by=Config.DEFAULT_MODEL,
        )
```

#### 4.2.2 Outcome Tracker

**File:** `src/analytics/outcome_tracker.py`

```python
"""
Application Outcome Tracker (Phase 7).

Tracks application outcomes and enables annotation effectiveness analysis.

Key Features:
- Per-job outcome tracking with timestamps
- Conversion metrics calculation
- Annotation profile correlation
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pymongo import MongoClient

from src.common.database import get_db


class OutcomeTracker:
    """
    Tracks and analyzes application outcomes.

    Enables measuring annotation effectiveness:
    - Response rate by annotation density
    - Interview rate by gap count
    - Offer rate by core_strength count
    """

    def __init__(self):
        self.db = get_db()

    def update_outcome(
        self,
        job_id: str,
        status: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Update application outcome for a job.

        Args:
            job_id: MongoDB job document ID
            status: New outcome status
            **kwargs: Additional fields (applied_via, notes, etc.)

        Returns:
            Updated outcome document
        """
        now = datetime.utcnow().isoformat()

        # Get current outcome or initialize
        job = self.db["level-2"].find_one({"_id": job_id})
        if not job:
            raise ValueError(f"Job {job_id} not found")

        outcome = job.get("application_outcome") or {
            "status": "not_applied",
            "interview_rounds": 0,
        }

        # Update status and timestamp
        outcome["status"] = status

        # Set appropriate timestamp based on status
        timestamp_map = {
            "applied": "applied_at",
            "response_received": "response_at",
            "screening_scheduled": "screening_at",
            "interview_scheduled": "interview_at",
            "interviewing": "interview_at",
            "offer_received": "offer_at",
        }

        if status in timestamp_map:
            field = timestamp_map[status]
            if not outcome.get(field):  # Don't overwrite existing
                outcome[field] = now

        # Update any additional fields
        for key, value in kwargs.items():
            if key in ApplicationOutcome.__annotations__:
                outcome[key] = value

        # Calculate derived metrics
        outcome = self._calculate_metrics(outcome)

        # Save to database
        self.db["level-2"].update_one(
            {"_id": job_id},
            {"$set": {"application_outcome": outcome}},
        )

        # Also update analytics collection for aggregation
        self._update_analytics(job_id, job, outcome)

        return outcome

    def get_effectiveness_report(
        self,
        date_range_days: int = 90,
    ) -> Dict[str, Any]:
        """
        Generate annotation effectiveness report.

        Returns:
            Report with conversion rates by annotation profile
        """
        # Aggregate outcomes by annotation profile
        pipeline = [
            {"$match": {"application_outcome.status": {"$ne": "not_applied"}}},
            {"$project": {
                "annotation_count": {"$size": {"$ifNull": ["$jd_annotations.annotations", []]}},
                "core_strength_count": {
                    "$size": {
                        "$filter": {
                            "input": {"$ifNull": ["$jd_annotations.annotations", []]},
                            "as": "a",
                            "cond": {"$eq": ["$$a.relevance", "core_strength"]}
                        }
                    }
                },
                "gap_count": {"$ifNull": ["$jd_annotations.gap_count", 0]},
                "outcome": "$application_outcome",
            }},
            {"$group": {
                "_id": {
                    "annotation_bucket": {
                        "$switch": {
                            "branches": [
                                {"case": {"$gte": ["$annotation_count", 10]}, "then": "high"},
                                {"case": {"$gte": ["$annotation_count", 5]}, "then": "medium"},
                            ],
                            "default": "low"
                        }
                    }
                },
                "total": {"$sum": 1},
                "responses": {
                    "$sum": {"$cond": [{"$ne": ["$outcome.response_at", None]}, 1, 0]}
                },
                "interviews": {
                    "$sum": {"$cond": [{"$ne": ["$outcome.interview_at", None]}, 1, 0]}
                },
                "offers": {
                    "$sum": {"$cond": [{"$ne": ["$outcome.offer_at", None]}, 1, 0]}
                },
            }},
        ]

        results = list(self.db["level-2"].aggregate(pipeline))
        return self._format_effectiveness_report(results)
```

### 4.3 API Endpoints

**File:** `frontend/app.py` (additions)

```python
# ===== INTERVIEW PREP ENDPOINTS =====

@app.route("/api/jobs/<job_id>/interview-prep", methods=["GET"])
def get_interview_prep(job_id: str):
    """Get interview prep data for a job."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    interview_prep = job.get("interview_prep")
    return jsonify({
        "success": True,
        "interview_prep": interview_prep,
        "has_prep": interview_prep is not None,
    })


@app.route("/api/jobs/<job_id>/interview-prep/generate", methods=["POST"])
def generate_interview_prep(job_id: str):
    """Generate interview prep questions from annotations."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Check if annotations exist
    jd_annotations = job.get("jd_annotations")
    if not jd_annotations:
        return jsonify({
            "error": "No annotations found. Add gap annotations first."
        }), 400

    # Build job state from document
    state = build_job_state_from_document(job)

    # Generate questions
    predictor = InterviewPredictor()
    interview_prep = predictor.predict_questions(state)

    # Save to database
    db["level-2"].update_one(
        {"_id": job_id},
        {"$set": {"interview_prep": interview_prep}}
    )

    return jsonify({
        "success": True,
        "interview_prep": interview_prep,
    })


@app.route("/api/jobs/<job_id>/interview-prep/questions/<question_id>", methods=["PATCH"])
def update_interview_question(job_id: str, question_id: str):
    """Update a specific interview question (practice status, notes)."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    data = request.get_json()
    allowed_fields = ["practice_status", "user_notes"]
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    # Update specific question in array
    result = db["level-2"].update_one(
        {"_id": job_id, "interview_prep.predicted_questions.question_id": question_id},
        {"$set": {f"interview_prep.predicted_questions.$.{k}": v for k, v in updates.items()}}
    )

    return jsonify({"success": True, "updated": result.modified_count > 0})


# ===== OUTCOME TRACKING ENDPOINTS =====

@app.route("/api/jobs/<job_id>/outcome", methods=["GET"])
def get_job_outcome(job_id: str):
    """Get application outcome for a job."""
    job = get_job_by_id(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    outcome = job.get("application_outcome") or {
        "status": "not_applied",
        "interview_rounds": 0,
    }

    return jsonify({
        "success": True,
        "outcome": outcome,
    })


@app.route("/api/jobs/<job_id>/outcome", methods=["PATCH"])
def update_job_outcome(job_id: str):
    """Update application outcome for a job."""
    data = request.get_json()

    tracker = OutcomeTracker()
    outcome = tracker.update_outcome(job_id, **data)

    return jsonify({
        "success": True,
        "outcome": outcome,
    })


@app.route("/api/analytics/outcomes", methods=["GET"])
def get_outcome_analytics():
    """Get aggregated outcome analytics."""
    days = request.args.get("days", 90, type=int)

    tracker = OutcomeTracker()
    report = tracker.get_effectiveness_report(date_range_days=days)

    return jsonify({
        "success": True,
        "report": report,
    })
```

### 4.4 Frontend Components

#### 4.4.1 Interview Prep Panel

**File:** `frontend/templates/partials/job_detail/_interview_prep_panel.html`

```html
<!-- Interview Prep Panel (Phase 7) -->
<!-- Collapsible section with predicted questions and STAR answer links -->

{% if job.jd_annotations and job.jd_annotations.annotations %}
<div class="mb-6" id="interview-prep-section">
    <details class="group" {% if job.interview_prep %}open{% endif %}>
        <summary class="cursor-pointer list-none">
            <div class="flex items-center justify-between p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
                <div class="flex items-center">
                    <svg class="h-5 w-5 text-orange-600 dark:text-orange-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <span class="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase">Interview Prep</span>
                </div>
                <div class="flex items-center gap-2">
                    {% if job.interview_prep %}
                    <span class="px-2 py-0.5 text-xs font-medium bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-400 rounded-full">
                        {{ job.interview_prep.predicted_questions | length }} Questions
                    </span>
                    {% set practiced = job.interview_prep.predicted_questions | selectattr('practice_status', 'equalto', 'confident') | list | length %}
                    {% if practiced > 0 %}
                    <span class="px-2 py-0.5 text-xs font-medium bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-400 rounded-full">
                        {{ practiced }} Practiced
                    </span>
                    {% endif %}
                    {% else %}
                    <button onclick="generateInterviewPrep('{{ job._id }}')"
                            class="px-3 py-1 text-xs font-medium text-orange-700 bg-orange-100 hover:bg-orange-200 rounded border border-orange-300 transition"
                            id="generate-prep-btn">
                        <svg class="inline-block h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
                        </svg>
                        Generate Questions
                    </button>
                    {% endif %}
                    <svg class="h-4 w-4 text-gray-400 transform group-open:rotate-90 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
                    </svg>
                </div>
            </div>
        </summary>

        <div class="mt-3 space-y-4" id="interview-prep-content">
            {% if job.interview_prep %}

            <!-- Gap Summary -->
            {% if job.interview_prep.gap_summary %}
            <div class="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
                <h4 class="text-xs font-semibold text-red-700 dark:text-red-400 uppercase mb-1">Gaps to Address</h4>
                <p class="text-sm text-gray-700 dark:text-gray-300">{{ job.interview_prep.gap_summary }}</p>
            </div>
            {% endif %}

            <!-- Concerns Summary -->
            {% if job.interview_prep.concerns_summary %}
            <div class="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
                <h4 class="text-xs font-semibold text-yellow-700 dark:text-yellow-400 uppercase mb-1">Concerns to Address</h4>
                <p class="text-sm text-gray-700 dark:text-gray-300">{{ job.interview_prep.concerns_summary }}</p>
            </div>
            {% endif %}

            <!-- Predicted Questions -->
            <div class="space-y-3">
                <h4 class="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase flex items-center justify-between">
                    Predicted Questions
                    <span class="text-xs font-normal text-gray-500">Click to expand answer guidance</span>
                </h4>

                {% for question in job.interview_prep.predicted_questions %}
                <div class="question-card border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden"
                     data-question-id="{{ question.question_id }}">
                    <details class="group">
                        <summary class="cursor-pointer p-3 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition">
                            <div class="flex items-start justify-between">
                                <div class="flex-1">
                                    <div class="flex items-center gap-2 mb-1">
                                        <!-- Question Type Badge -->
                                        <span class="px-2 py-0.5 text-xs font-medium rounded
                                            {% if question.question_type == 'gap_probe' %}bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-400
                                            {% elif question.question_type == 'concern_probe' %}bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-400
                                            {% elif question.question_type == 'behavioral' %}bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-400
                                            {% else %}bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300{% endif %}">
                                            {{ question.question_type | replace('_', ' ') | title }}
                                        </span>
                                        <!-- Difficulty Badge -->
                                        <span class="px-2 py-0.5 text-xs font-medium rounded
                                            {% if question.difficulty == 'hard' %}bg-purple-100 text-purple-800
                                            {% elif question.difficulty == 'medium' %}bg-orange-100 text-orange-800
                                            {% else %}bg-green-100 text-green-800{% endif %}">
                                            {{ question.difficulty | title }}
                                        </span>
                                    </div>
                                    <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ question.question }}</p>
                                </div>
                                <!-- Practice Status -->
                                <div class="ml-3 flex items-center">
                                    <select class="practice-status-select text-xs border rounded p-1"
                                            onchange="updateQuestionStatus('{{ job._id }}', '{{ question.question_id }}', this.value)">
                                        <option value="not_started" {% if question.practice_status == 'not_started' %}selected{% endif %}>Not Started</option>
                                        <option value="practiced" {% if question.practice_status == 'practiced' %}selected{% endif %}>Practiced</option>
                                        <option value="confident" {% if question.practice_status == 'confident' %}selected{% endif %}>Confident</option>
                                    </select>
                                </div>
                            </div>
                        </summary>

                        <div class="p-3 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700">
                            <!-- Answer Approach -->
                            <div class="mb-3">
                                <h5 class="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">Suggested Approach</h5>
                                <p class="text-sm text-gray-700 dark:text-gray-300">{{ question.suggested_answer_approach }}</p>
                            </div>

                            <!-- Sample Answer Outline -->
                            {% if question.sample_answer_outline %}
                            <div class="mb-3">
                                <h5 class="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">Answer Outline</h5>
                                <p class="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{{ question.sample_answer_outline }}</p>
                            </div>
                            {% endif %}

                            <!-- Relevant STARs -->
                            {% if question.relevant_star_ids %}
                            <div class="mb-3">
                                <h5 class="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">Relevant STAR Stories</h5>
                                <div class="flex flex-wrap gap-2">
                                    {% for star_id in question.relevant_star_ids %}
                                    <span class="px-2 py-1 text-xs bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-400 rounded cursor-pointer hover:bg-indigo-200"
                                          onclick="showStarDetail('{{ star_id }}')">
                                        {{ star_id }}
                                    </span>
                                    {% endfor %}
                                </div>
                            </div>
                            {% endif %}

                            <!-- User Notes -->
                            <div>
                                <h5 class="text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">Your Notes</h5>
                                <textarea class="w-full text-sm p-2 border rounded resize-none"
                                          rows="3"
                                          placeholder="Add your own answer notes..."
                                          onblur="saveQuestionNotes('{{ job._id }}', '{{ question.question_id }}', this.value)">{{ question.user_notes or '' }}</textarea>
                            </div>
                        </div>
                    </details>
                </div>
                {% endfor %}
            </div>

            <!-- Regenerate Button -->
            <div class="mt-4 flex justify-end">
                <button onclick="generateInterviewPrep('{{ job._id }}')"
                        class="px-3 py-1 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded border border-gray-300 transition">
                    <svg class="inline-block h-3 w-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                    </svg>
                    Regenerate
                </button>
            </div>

            {% else %}
            <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                <svg class="mx-auto h-12 w-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <p class="text-sm mb-2">No interview prep generated yet.</p>
                <p class="text-xs">Click "Generate Questions" to predict interview questions from your gap annotations.</p>
            </div>
            {% endif %}
        </div>
    </details>
</div>
{% endif %}
```

#### 4.4.2 Outcome Tracker UI

**File:** `frontend/templates/partials/job_detail/_outcome_tracker.html`

```html
<!-- Outcome Tracker (Phase 7) -->
<!-- Compact status badge + dropdown in Status & Actions section -->

<div class="outcome-tracker flex items-center gap-3" data-job-id="{{ job._id }}">
    <div>
        <label class="block text-xs theme-text-tertiary mb-1">Application Outcome</label>
        {% set outcome = job.application_outcome or {'status': 'not_applied'} %}

        <div class="flex items-center gap-2">
            <!-- Status Badge -->
            <span class="outcome-badge px-2 py-1 text-xs font-medium rounded-full
                {% if outcome.status == 'offer_received' or outcome.status == 'offer_accepted' %}bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-400
                {% elif outcome.status == 'interviewing' or outcome.status == 'interview_scheduled' %}bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-400
                {% elif outcome.status == 'response_received' or outcome.status == 'screening_scheduled' %}bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-400
                {% elif outcome.status == 'applied' %}bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-400
                {% elif outcome.status == 'rejected' %}bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-400
                {% elif outcome.status == 'withdrawn' %}bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300
                {% else %}bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400{% endif %}">
                {{ outcome.status | replace('_', ' ') | title }}
            </span>

            <!-- Status Dropdown -->
            <select id="outcome-status-select"
                    class="form-select text-xs py-1 px-2"
                    onchange="updateOutcomeStatus('{{ job._id }}', this.value)">
                <option value="not_applied" {% if outcome.status == 'not_applied' %}selected{% endif %}>Not Applied</option>
                <option value="applied" {% if outcome.status == 'applied' %}selected{% endif %}>Applied</option>
                <option value="response_received" {% if outcome.status == 'response_received' %}selected{% endif %}>Response Received</option>
                <option value="screening_scheduled" {% if outcome.status == 'screening_scheduled' %}selected{% endif %}>Screening Scheduled</option>
                <option value="interview_scheduled" {% if outcome.status == 'interview_scheduled' %}selected{% endif %}>Interview Scheduled</option>
                <option value="interviewing" {% if outcome.status == 'interviewing' %}selected{% endif %}>Interviewing</option>
                <option value="offer_received" {% if outcome.status == 'offer_received' %}selected{% endif %}>Offer Received</option>
                <option value="offer_accepted" {% if outcome.status == 'offer_accepted' %}selected{% endif %}>Offer Accepted</option>
                <option value="rejected" {% if outcome.status == 'rejected' %}selected{% endif %}>Rejected</option>
                <option value="withdrawn" {% if outcome.status == 'withdrawn' %}selected{% endif %}>Withdrawn</option>
            </select>
        </div>
    </div>

    <!-- Applied Via (shown when status >= applied) -->
    {% if outcome.status != 'not_applied' %}
    <div>
        <label class="block text-xs theme-text-tertiary mb-1">Applied Via</label>
        <select id="applied-via-select"
                class="form-select text-xs py-1 px-2"
                onchange="updateOutcomeField('{{ job._id }}', 'applied_via', this.value)">
            <option value="" {% if not outcome.applied_via %}selected{% endif %}>Select...</option>
            <option value="linkedin" {% if outcome.applied_via == 'linkedin' %}selected{% endif %}>LinkedIn</option>
            <option value="website" {% if outcome.applied_via == 'website' %}selected{% endif %}>Company Website</option>
            <option value="email" {% if outcome.applied_via == 'email' %}selected{% endif %}>Email</option>
            <option value="referral" {% if outcome.applied_via == 'referral' %}selected{% endif %}>Referral</option>
        </select>
    </div>
    {% endif %}

    <!-- Interview Rounds (shown when interviewing) -->
    {% if outcome.status in ['interview_scheduled', 'interviewing', 'offer_received', 'offer_accepted'] %}
    <div>
        <label class="block text-xs theme-text-tertiary mb-1">Rounds</label>
        <input type="number" min="0" max="10"
               class="form-input text-xs w-16 py-1 px-2"
               value="{{ outcome.interview_rounds or 0 }}"
               onchange="updateOutcomeField('{{ job._id }}', 'interview_rounds', parseInt(this.value))">
    </div>
    {% endif %}
</div>
```

### 4.5 Database Schema Changes

```
Job Document (level-2 collection) - ADDITIONS:
├── interview_prep: InterviewPrep           # Phase 7: Interview prep data
│   ├── predicted_questions: List[InterviewQuestion]
│   ├── gap_summary: str
│   ├── concerns_summary: str
│   ├── company_context: str
│   ├── role_context: str
│   ├── generated_at: str
│   └── generated_by: str
│
└── application_outcome: ApplicationOutcome  # Phase 7: Outcome tracking
    ├── status: str
    ├── applied_at: str
    ├── applied_via: str
    ├── response_at: str
    ├── interview_at: str
    ├── interview_rounds: int
    ├── offer_at: str
    ├── days_to_response: int
    ├── days_to_interview: int
    └── notes: str

NEW Collection: annotation_analytics
├── _id: str (job_id)
├── annotation_profile: {
│   annotation_count: int,
│   core_strength_count: int,
│   gap_count: int,
│   reframe_count: int,
│   section_coverage: float
│ }
├── outcome_snapshot: {
│   status: str,
│   applied_at: str,
│   response_at: str,
│   interview_at: str,
│   offer_at: str
│ }
└── computed_at: str
```

## 5. Implementation Roadmap

### Phase 7.1: Data Model & Backend (1 day)
1. **Add types to `annotation_types.py`** (30 min)
   - Add `sample_answer_outline`, `difficulty`, `practice_status`, `user_notes` to `InterviewQuestion`
   - Add `OutcomeStatus` literal type
   - Add `ApplicationOutcome` TypedDict

2. **Create `src/layer7/interview_predictor.py`** (3 hours)
   - Implement `InterviewPredictor` class
   - LLM prompt for question generation with anti-hallucination
   - STAR linking algorithm
   - Unit tests

3. **Create `src/analytics/outcome_tracker.py`** (2 hours)
   - Implement `OutcomeTracker` class
   - MongoDB update operations
   - Analytics aggregation pipeline
   - Unit tests

### Phase 7.2: API Endpoints (0.5 day)
4. **Add endpoints to `frontend/app.py`** (2 hours)
   - `GET/POST /api/jobs/<id>/interview-prep`
   - `PATCH /api/jobs/<id>/interview-prep/questions/<qid>`
   - `GET/PATCH /api/jobs/<id>/outcome`
   - `GET /api/analytics/outcomes`

### Phase 7.3: Frontend - Interview Prep Panel (0.5 day)
5. **Create `_interview_prep_panel.html`** (2 hours)
   - Collapsible section with question cards
   - Practice status dropdowns
   - STAR links
   - User notes textarea

6. **Create `interview-prep.js`** (1 hour)
   - `generateInterviewPrep()` function
   - `updateQuestionStatus()` function
   - `saveQuestionNotes()` function

### Phase 7.4: Frontend - Outcome Tracker (0.5 day)
7. **Create `_outcome_tracker.html`** (1 hour)
   - Status badge + dropdown
   - Applied via selector
   - Interview rounds input

8. **Create `outcome-tracker.js`** (1 hour)
   - `updateOutcomeStatus()` function
   - `updateOutcomeField()` function
   - Badge color update logic

### Phase 7.5: Integration & Testing (0.5 day)
9. **Update `job_detail.html`** (30 min)
   - Include `_interview_prep_panel.html`
   - Include `_outcome_tracker.html` in Status section

10. **Integration tests** (2 hours)
    - End-to-end flow: annotation -> question generation -> practice
    - Outcome tracking state transitions
    - Analytics aggregation

**Total: ~2 days**

## 6. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| LLM generates irrelevant questions | Medium | Medium | Strict prompt grounding on gap annotations; validation that source_annotation_id exists |
| Question overload (too many) | Low | Medium | Cap at 10 questions; prioritize by difficulty |
| Outcome tracking not used | Low | Medium | Make it visible in header; show analytics value |
| STAR linking fails | Medium | Low | Fallback to general answer approach if no STARs match |
| Analytics data too sparse | Low | High (initially) | Defer analytics dashboard until 50+ outcomes tracked |

## 7. Open Questions

1. **Should interview prep be auto-generated when annotations are saved?**
   - Current recommendation: No, keep it on-demand to save costs
   - Alternative: Auto-generate for "critical" priority jobs only

2. **Should we add audio recording for practice sessions?**
   - Deferred to future enhancement
   - Would require additional storage and browser API integration

3. **Should outcome tracking integrate with LinkedIn/email for auto-detection?**
   - Deferred - requires OAuth integrations
   - Manual tracking is sufficient for MVP

---

## Summary

Phase 7 adds interview preparation and analytics capabilities to complete the JD Annotation System. The architecture:

- **Stays consistent** with existing UI patterns (collapsible sections, status dropdowns)
- **Minimizes complexity** by making interview prep on-demand (not always-on)
- **Enables measurement** of annotation effectiveness through outcome tracking
- **Maintains quality focus** with grounded question generation from gap annotations

For implementation, I recommend starting with **Phase 7.1 (Data Model & Backend)** using the main Claude agent, then using **frontend-developer** for Phases 7.3-7.4 (UI implementation).
