# Annotation Suggestion System - Plan

**Created**: 2025-12-01
**Status**: Completed
**Completed**: 2026-01-11

## Overview

Graceful Discovering Sparrow is the annotation suggestion system that intelligently recommends CV annotations (skills, responsibilities, impact) when users review job descriptions. The system learns from user feedback and adapts over time to avoid suggesting irrelevant skills while highlighting matches to their experience.

**Core Innovation**: Context-aware learning modes (NO_LEARNING, SOFT_PENALTY, FULL_LEARNING) that distinguish between skill noise, mismatches, and genuine gaps based on section type and skill ownership.

## Requirements

1. **4-Source Suggestion Architecture**
   - Master CV data (hard/soft skills, JD signals, keywords)
   - Structured JD (role-parsed into sections)
   - Extracted JD (detailed content from web-scraped job pages)
   - Priors (user feedback history and skill confidence scores)

2. **Smart Deletion Feedback**
   - Analyze context of deletion (section type, skill ownership)
   - Apply appropriate learning penalty (NO_LEARNING, SOFT_PENALTY, FULL_LEARNING)
   - Update skill confidence and avoid flags

3. **Configurable Learning Parameters**
   - SOFT_PENALTY_MULTIPLIER (0.8 default): gentle confidence reduction
   - FULL_PENALTY_MULTIPLIER (0.3 default): strong penalty for skill gaps
   - CORRECT_PREDICTION_BOOST (0.05 default): confidence growth on accepts
   - WRONG_PREDICTION_DECAY (0.7 default): confidence reduction on edits

4. **Comprehensive Testing**
   - 240+ unit tests covering all suggestion and learning paths
   - Tests for edge cases, thresholds, and statistical convergence

## Architecture

### Components

```
annotation_suggester.py
  ├─ should_generate_annotation() - Selective generation logic
  ├─ find_best_match() - Semantic + keyword matching
  ├─ infer_requirement_type() - Auto-detect skill category
  └─ generate_annotations_for_job() - Full pipeline

annotation_priors.py
  ├─ load_priors() - Load from MongoDB
  ├─ save_priors() - Persist updates
  ├─ capture_feedback() - Record user actions
  ├─ determine_deletion_response() - Classify learning mode
  └─ rebuild_priors() - Batch update embeddings

priors_repository.py
  └─ MongoDB singleton access to priors document
```

### Data Flow

```
User Reviews Job
  ↓
extract_jd() → Structured + Extracted JD
  ↓
load_priors() → Skill confidence + embeddings
  ↓
should_generate_annotation() → Check 4 sources
  ↓
find_best_match() → Semantic + keyword matching
  ↓
_create_annotation() → Format for UI
  ↓
User Actions (Accept/Edit/Delete)
  ↓
capture_feedback() → Determine learning mode
  ├─ NO_LEARNING (skill irrelevant to role)
  ├─ SOFT_PENALTY (skill noise)
  └─ FULL_LEARNING (skill gap)
  ↓
Update skill_priors[skill][dimension]
  ↓
save_priors() → Persist
  ↓
rebuild_priors() → Batch update embeddings
```

### MongoDB Schema

**Priors Document (_id: "priors")**

```yaml
_id: "priors"
version: 2
sentence_index:
  count: 1234
  last_updated: "2025-01-11T12:00:00Z"
  embeddings: []  # Embeddings for ~100 sample sentences per skill

skill_priors:
  "python":
    relevance:
      value: "relevant"
      confidence: 0.85
      n: 12  # observations
    passion:
      value: null
      confidence: 0.0
      n: 0
    identity:
      value: null
      confidence: 0.0
      n: 0
    requirement:
      value: "required"
      confidence: 0.75
      n: 8
    avoid: false

  "php":
    relevance:
      value: null
      confidence: 0.0
      n: 0
    requirement:
      value: null
      confidence: 0.0
      n: 0
    avoid: true  # User marked to avoid

stats:
  total_annotations_at_build: 150
  total_acceptances: 145
  total_soft_deletions: 3
  total_hard_deletions: 2
  last_rebuild: "2025-01-10T12:00:00Z"
```

### Learning Modes

| Mode | Trigger | Penalty | Use Case |
|------|---------|---------|----------|
| **NO_LEARNING** | Deletion in non-skill sections (summary, header) | None | Skill is irrelevant to role type |
| **SOFT_PENALTY** | Deletion with moderate confidence | 0.8x multiplier | Skill noise (user has skill but not relevant here) |
| **FULL_LEARNING** | Deletion of non-owned skill in requirements | 0.3x multiplier | Skill gap (user doesn't have skill) |

### Configuration Parameters

All parameters are documented and tunable in `/src/services/annotation_priors.py`:

- **Deletion Learning**: SOFT_PENALTY_MULTIPLIER, FULL_PENALTY_MULTIPLIER
- **Confidence Adjustment**: CORRECT_PREDICTION_BOOST, WRONG_PREDICTION_DECAY, MIN_CONFIDENCE, MAX_CONFIDENCE
- **Value Adoption**: VALUE_ADOPTION_THRESHOLD, MIN_OBSERVATIONS_FOR_STABILITY
- **Cache**: OWNED_SKILLS_CACHE_TTL, OWNERSHIP_CONFIDENCE_THRESHOLD

## Implementation Phases

### Phase 1: Core Suggestion Engine (COMPLETED)
- [x] Extract 4 sources of truth (Master CV, JD, Priors)
- [x] Implement selective generation logic
- [x] Build semantic + keyword matching
- [x] Auto-infer requirement types

### Phase 2: Feedback Learning (COMPLETED)
- [x] Implement deletion response classification
- [x] Add learning mode determination (NO/SOFT/FULL)
- [x] Update skill confidence scores
- [x] Support avoid flags for non-owned skills

### Phase 3: Priors Management (COMPLETED)
- [x] MongoDB singleton access (priors_repository.py)
- [x] Load/save/rebuild priors document
- [x] Batch update embeddings on rebuild
- [x] Compute statistics for monitoring

### Phase 4: Testing & Tuning (COMPLETED)
- [x] 240+ unit tests passing
- [x] Mock MongoDB and LLM dependencies
- [x] Edge case coverage (thresholds, convergence, etc.)
- [x] Configurable parameters for tuning

## Testing Strategy

### Test Coverage: 240+ Tests

**Unit Tests by Component:**
- `test_annotation_suggester.py` (60+ tests)
  - should_generate_annotation logic
  - Semantic and keyword matching
  - Requirement type inference

- `test_annotation_priors.py` (70+ tests)
  - Priors load/save/rebuild
  - Feedback capture and learning
  - Statistics computation
  - Deletion response classification

- `test_priors_repository.py` (30+ tests)
  - MongoDB CRUD operations
  - Singleton pattern
  - Error handling

- `test_annotation_tracking_service.py` (40+ tests)
  - Tracking state lifecycle
  - UI interaction flows

- `test_annotation_tailoring.py` (20+ tests)
  - Annotation adaptation to role

- `test_layer4_annotation_fit_signal.py` (15+ tests)
  - JD signal extraction

- `test_annotation_types_phase7.py` (5+ tests)
  - Type validation

### Test Approach

- **Mocking**: All external dependencies (MongoDB, LLM embeddings) are mocked
- **Edge Cases**: Threshold values, statistical convergence, empty states
- **Integration**: Full pipeline from JD to feedback capture

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Over-correcting on deletions | System avoids good skills | Monitor FULL_LEARNING deletions; tune FULL_PENALTY_MULTIPLIER |
| Slow adaptation to changes | User preferences not reflected | Increase CORRECT_PREDICTION_BOOST; track convergence |
| Embedding staleness | Old suggestions cached too long | Rebuild priors periodically (weekly) |
| MongoDB latency | Slow suggestion generation | Cache priors in memory; async rebuild |
| Hallucinated suggestions | LLM makes up skills | Use SIMILARITY_THRESHOLD; require keyword match |

## Key Files

### Source Code
- `/src/services/annotation_suggester.py` - Suggestion generation (400+ lines)
- `/src/services/annotation_priors.py` - Feedback learning (600+ lines)
- `/src/common/repositories/priors_repository.py` - MongoDB access (100+ lines)

### Tests
- `/tests/unit/test_annotation_suggester.py` (60+ tests)
- `/tests/unit/test_annotation_priors.py` (70+ tests)
- `/tests/unit/test_priors_repository.py` (30+ tests)
- `/tests/unit/test_annotation_tracking_service.py` (40+ tests)
- `/tests/unit/test_annotation_tailoring.py` (20+ tests)
- `/tests/unit/test_layer4_annotation_fit_signal.py` (15+ tests)
- `/tests/unit/test_annotation_types_phase7.py` (5+ tests)

### Configuration
- `/src/services/annotation_priors.py` (lines 45-148) - All learning parameters

## Next Steps

1. **UI Integration**: Wire suggestion generation to annotation editor
2. **Frontend Feedback Capture**: Hook deletion/edit actions to capture_feedback()
3. **Priors Visualization**: Dashboard to monitor suggestion accuracy
4. **A/B Testing**: Compare learning mode effectiveness in real usage
5. **Periodic Rebuild**: Schedule weekly priors rebuild for embedding updates

## Related Documentation

- See `CLAUDE.md` for development workflow
- See `docs/current/cv-generation-guide.md` for annotation integration in CV pipeline
- See `architecture.md` for system-wide design overview
