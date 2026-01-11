# Implementation Gaps

## Completed (2026-01-11)

- [x] Annotation suggestion system with 4-source architecture ✅ **COMPLETED 2026-01-11**
  - Smart deletion feedback with context-aware learning (NO_LEARNING, SOFT_PENALTY, FULL_LEARNING)
  - Enhanced priors system tracking skill confidence and avoid flags
  - Configurable thresholds for tuning suggestion accuracy
  - 240+ unit tests passing
  - Key files: `src/services/annotation_suggester.py`, `src/services/annotation_priors.py`, `src/common/repositories/priors_repository.py`

## Current Blockers

| Issue | Impact | Fix |
|-------|--------|-----|
| Suggestion UI not wired to backend | Users can't see suggestions | Frontend-developer to integrate suggestion generation to editor |
| Priors feedback not captured on frontend | Learning disabled | Frontend-developer to hook deletion/edit to capture_feedback() |
| No rebuild schedule | Embeddings stale | Add weekly rebuild job to runner_service |

## Remaining Gaps (Non-Blocking)

### CV Generation & Annotation Pipeline

- [ ] Bridge suggestion results into CV generation pipeline
- [ ] Auto-update master CV from accepted annotations
- [ ] Implement annotation influence scoring (how much each annotation affects CV)
- [ ] Validate annotation consistency with STAR framework
- [ ] Add role-specific annotation tailoring

### UI/Frontend

- [ ] Suggestion popover in job detail view
- [ ] Batch suggestion UI (review all suggestions for job at once)
- [ ] Suggestion confidence badges with explanations
- [ ] Undo/redo for suggestion actions
- [ ] Suggestion filtering by type (hard_skill, soft_skill, jd_signal, etc)

### Monitoring & Analytics

- [ ] Dashboard: suggestion accuracy over time
- [ ] Metrics: acceptance rate, soft vs hard deletion ratio
- [ ] Priors stats visualization (confidence distributions, avoid flags)
- [ ] Rebuild quality metrics (embedding coverage, similarity improvements)
- [ ] User feedback heatmap (which suggestions are most valuable)

### Advanced Features

- [ ] Multi-skill suggestions (suggest skill combinations, not just singles)
- [ ] Temporal suggestions (suggest when/where skills were used)
- [ ] Confidence-aware UI (highlight high-confidence suggestions)
- [ ] Reverse suggestions (highlight gaps in master CV)
- [ ] Cross-job suggestion patterns (learn from similar roles)

### Performance & Scaling

- [ ] Priors caching strategy (in-memory vs MongoDB)
- [ ] Batch suggestion generation (all jobs at once)
- [ ] Async rebuild during background processing
- [ ] Embedding indexing for faster semantic search
- [ ] Rate limiting for suggestion generation

### Data Quality

- [ ] Validation: no hallucinated skills in suggestions
- [ ] Deduplication: handle skill aliases properly
- [ ] Normalization: standardize skill names across sources
- [ ] Consistency checks: priors vs master CV alignment
- [ ] Data migration: backfill missing skill priors

## Architecture Overview

### Annotation Suggestion System

**Status**: Production Ready (all tests passing)

The system uses a 4-source architecture to generate intelligent CV annotation suggestions when users review job descriptions:

1. **Master CV Source**: Hard skills, soft skills, JD signals (taxonomy of user strengths)
2. **Structured JD Source**: Role-parsed job description with sections (requirements, nice-to-haves, etc)
3. **Extracted JD Source**: Full job posting content from web scraping
4. **Priors Source**: User feedback history with skill confidence scores and avoid flags

**Learning System**: Context-aware penalty modes
- `NO_LEARNING`: Skill irrelevant to role type (no confidence impact)
- `SOFT_PENALTY`: Skill noise, user has it but not relevant here (0.8x multiplier)
- `FULL_LEARNING`: Skill gap, user doesn't have this skill (0.3x multiplier)

**Key Components**:
- `annotation_suggester.py`: Selective generation + semantic/keyword matching (400+ lines)
- `annotation_priors.py`: Feedback capture and learning (600+ lines)
- `priors_repository.py`: MongoDB singleton for priors document (100+ lines)

**Configurable Parameters** (all in `annotation_priors.py`):
- Deletion penalties: SOFT_PENALTY_MULTIPLIER, FULL_PENALTY_MULTIPLIER
- Confidence adjustments: CORRECT_PREDICTION_BOOST, WRONG_PREDICTION_DECAY
- Value adoption: VALUE_ADOPTION_THRESHOLD, MIN_OBSERVATIONS_FOR_STABILITY
- Cache: OWNED_SKILLS_CACHE_TTL, OWNERSHIP_CONFIDENCE_THRESHOLD

**Test Coverage**: 240+ unit tests
- Suggester logic (60+ tests)
- Priors management (70+ tests)
- Repository operations (30+ tests)
- Tracking service (40+ tests)
- Integration flows (40+ tests)

### System Layers

```
Layer 7: Interview Predictor (future)
  ↓
Layer 6: Cover Letter & LinkedIn
  ↓
Layer 5: Annotation Suggestion System (ACTIVE)
  ├─ should_generate_annotation()
  ├─ find_best_match()
  ├─ capture_feedback()
  └─ rebuild_priors()
  ↓
Layer 4: JD Extraction & Parsing
  ├─ Structured JD (sections, requirements)
  └─ Extracted JD (web content)
  ↓
Layer 1-3: Job Source & Filtering
```

## Known Limitations

1. **Embedding Staleness**: Priors embeddings updated only on rebuild, not in real-time
2. **Cold Start Problem**: New skills take multiple feedback events to build confidence
3. **Skill Aliases**: Manual management of skill_aliases in master CV
4. **Context Loss**: Priors don't track job title/industry context for suggestions
5. **No Temporal Data**: Can't suggest skills for specific time periods

## Success Metrics

- [ ] Suggestion acceptance rate > 70%
- [ ] Soft deletion rate < 10% (indicates good suggestion quality)
- [ ] Hard deletion rate < 5% (indicates skill ownership classification working)
- [ ] Rebuild stability: <5% variance in suggestion scores after rebuild
- [ ] User retention: > 80% of users provide feedback on suggestions

## Related Files

- **Feature Plan**: `plans/graceful-discovering-sparrow.md`
- **Architecture**: See `CLAUDE.md` for agent workflow
- **CV Guide**: `docs/current/cv-generation-guide.md`
- **Source Code**: `src/services/annotation_*.py`, `src/common/repositories/priors_repository.py`
- **Tests**: `tests/unit/test_annotation_*.py`, `tests/unit/test_priors_repository.py`
