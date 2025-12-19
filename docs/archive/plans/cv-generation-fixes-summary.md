# CV Generation Fixes - Executive Summary

**Date**: 2025-11-30
**Full Analysis**: `/reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`

---

## Priority Issues

### P0 (Critical - Must Fix)

| ID | Issue | Root Cause | Fix Location |
|----|-------|------------|--------------|
| P0-1 | **Hallucinated Skills** (PHP, Java, Spring Boot) | Hardcoded skill lists in `header_generator.py` lines 200-226 | Replace with master-cv skill parsing |
| P0-2 | **Static Categories** (Always Leadership/Technical/Platform/Delivery) | Hardcoded loop in `header_generator.py` line 495 | LLM-driven category generation from JD |
| P0-3 | **Missing STAR Format** (Generic bullets) | No STAR enforcement in `role_generation.py` prompts | Add STAR template + validator |

### P1 (High - Should Fix)

| ID | Issue | Fix Location |
|----|-------|--------------|
| P1-1 | **No Relocation Tagline** | Add location parser in `orchestrator.py` |
| P1-2 | **Green Color** (#0f766e) | Change to #475569 in `app.py` + `base.html` |

### P2 (Nice to Have)

| ID | Issue | Fix Location |
|----|-------|--------------|
| P2-1 | **CV Spacing** (Too wide) | Reduce padding by 20% in `cv-editor.css` |

---

## Recommended Solution: Option B (JD-Driven Dynamic System)

### Core Changes

1. **Load Master-CV Skills ONLY**
   - No more hardcoded PHP, Java, etc.
   - Parse `hard_skills` + `soft_skills` from all roles
   - Only match skills that exist in master-cv

2. **Generate JD-Specific Categories**
   - NEW LLM call: "Given JD keywords, create 3-4 relevant categories"
   - Example: ML role → ["Machine Learning", "Cloud Platform", "Technical Leadership"]
   - Not: Generic ["Technical", "Platform", "Delivery", "Leadership"]

3. **Enforce STAR Format**
   - Add STAR template to prompts: [Challenge] → [Task] → [Action with Skills] → [Result]
   - Validate bullets mention skills explicitly
   - Example: "using Python and AWS" not just "improved system"

4. **Add Dynamic Tagline**
   - If job location in Middle East/Pakistan → "Available for International Relocation in 2 months"

5. **Update Color Scheme**
   - Teal (#0f766e) → Dark greyish blue (#475569)

---

## Implementation Phases (5 days)

| Phase | Tasks | Time | Files Modified |
|-------|-------|------|----------------|
| **1** | Master-CV skill sourcing + Tagline | 1 day | `header_generator.py`, `orchestrator.py` |
| **2** | JD-driven category generation | 1.5 days | `header_generator.py`, `prompts/header_generation.py`, `types.py` |
| **3** | STAR format enforcement | 1 day | `role_generator.py`, `prompts/role_generation.py` |
| **4** | Color + spacing polish | 0.5 days | `app.py`, `base.html`, `cv-editor.css` |
| **5** | Testing + documentation | 1 day | Test files, `missing.md` |

---

## Key Technical Decisions

### New Data Flow

```
JD Keywords + Master-CV Skills
        ↓
LLM Category Generator (NEW)
        ↓
3-4 JD-Specific Categories (e.g., "Cloud Platform Engineering")
        ↓
Skill Matcher (GROUNDED in master-cv only)
        ↓
Evidence Validator (bullets must mention skills)
        ↓
Final Core Competencies (100% grounded, JD-aligned)
```

### New Pydantic Models

```python
class CategoryDefinition:
    category_name: str           # JD-specific category
    skill_keywords: List[str]    # Skills from master-cv
    priority: int                # 1 = most important

class STARBullet:
    situation: str               # Challenge faced
    task: str                    # What needed to be done
    action: str                  # How (MUST mention skills)
    result: str                  # Quantified outcome
    skills_mentioned: List[str]  # Validated skill list
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM category generation fails | Fallback to default 4 categories |
| Skill matching too strict | Fuzzy matching (case-insensitive) |
| STAR validation too harsh | Make warnings not errors |
| Performance impact | Cache category generation per JD |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Hallucinated skills | 3-5 per CV | 0 |
| JD-aligned categories | 0% (always generic) | 90%+ |
| STAR-compliant bullets | ~30% | 80%+ |
| Relocation tagline accuracy | 0% | 100% |

---

## Next Steps

1. Review and approve architecture (see full analysis)
2. Answer open questions:
   - Confirm color choice (#475569)?
   - STAR validation: warning or error?
   - Tagline placement: after name or contact line?
3. Assign implementation:
   - Main Claude: Backend logic (Phases 1-4)
   - `frontend-developer`: CSS changes (Phase 5)
   - `test-generator`: Test suite
4. Update `plans/missing.md` after completion

---

## Files Changed Summary

**Backend** (7 files):
- `src/layer6_v2/header_generator.py` (~200 lines)
- `src/layer6_v2/prompts/header_generation.py` (~100 lines)
- `src/layer6_v2/role_generator.py` (~50 lines)
- `src/layer6_v2/prompts/role_generation.py` (~80 lines)
- `src/layer6_v2/types.py` (~50 lines new models)
- `src/layer6_v2/orchestrator.py` (~30 lines)
- Tests (~280 lines)

**Frontend** (3 files):
- `frontend/app.py` (3 lines)
- `frontend/templates/base.html` (2 lines)
- `frontend/static/css/cv-editor.css` (~20 lines)

**Total Effort**: ~5 developer days
**Total Lines**: ~815 lines (including tests)

---

*See full architecture analysis for detailed design, data flows, and code examples.*
