# Architecture Analysis: Role-Specific CV Header/Profile Generation

**Date**: 2025-12-12
**Analysis Type**: System Design & ROI Assessment
**Target Roles**: Engineering Manager, Director, Head of Engineering, Staff/Principal Engineer, VP Engineering, CTO, Head of Technology

---

## Executive Summary

This analysis evaluates whether to implement role-specific modules/prompts for engineering leadership CV generation or enhance the current universal prompt system with persona-based configuration.

**Recommendation: Enhanced Universal System with Role Persona Registry**

The current system already has substantial role-specific infrastructure (~70% built) that is underutilized. Rather than creating separate modules per role (over-engineering), we should expand the existing `RoleSkillsTaxonomy`, `CareerContext`, and `ROLE_SUPERPOWERS` systems to include richer role-specific persona data and tagline guidance.

---

## 1. Current System Analysis

### 1.1 Existing Role-Specific Infrastructure

| Component | Location | Purpose |
|-----------|----------|---------|
| **RoleCategory Enum** | `src/layer1_4/jd_extractor.py` | 7 role categories defined |
| **Competency Weights** | JD extraction output | delivery/process/architecture/leadership mix |
| **Role Skills Taxonomy** | `data/master-cv/role_skills_taxonomy.json` | Per-role skill sections with priority ordering |
| **CareerContext Emphasis** | `src/layer6_v2/types.py:236-299` | Role-category-aware bullet emphasis |
| **ROLE_SUPERPOWERS** | `src/layer6_v2/prompts/header_generation.py` | Role → characteristic strengths mapping |
| **Role Category Guidance** | `header_generation.py:124-149` | Per-category prompt guidance |

### 1.2 Current Role Categories

```python
class RoleCategory(str, Enum):
    ENGINEERING_MANAGER = "engineering_manager"
    STAFF_PRINCIPAL_ENGINEER = "staff_principal_engineer"
    DIRECTOR_OF_ENGINEERING = "director_of_engineering"
    HEAD_OF_ENGINEERING = "head_of_engineering"
    CTO = "cto"
    TECH_LEAD = "tech_lead"
    SENIOR_ENGINEER = "senior_engineer"
```

### 1.3 What's Missing

| Gap | Impact | Priority |
|-----|--------|----------|
| **No VP Engineering category** | VP roles misclassified as CTO/Head | HIGH |
| **No role-specific tagline templates** | Generic examples in prompts | HIGH |
| **No role-specific power verbs** | Same verbs for all roles | MEDIUM |
| **No persona characteristics** | No defined "voice" per role | MEDIUM |
| **No role-specific metric priorities** | All metrics treated equally | MEDIUM |

---

## 2. Options Evaluated

### Option A: Separate Module Per Role ❌

```
src/layer6_v2/personas/
  engineering_manager.py
  director_engineering.py
  head_engineering.py
  staff_engineer.py
  principal_engineer.py
  cto.py
  vp_engineering.py
```

| Aspect | Assessment |
|--------|------------|
| Complexity | HIGH (8x code paths) |
| Maintenance | HIGH (80% duplication) |
| Hallucination Risk | MODERATE |
| ROI | LOW |

**Verdict: NOT RECOMMENDED** - Over-engineering with minimal benefit

### Option B: Enhanced Universal System with Role Persona Registry ✅

Extend existing `role_skills_taxonomy.json` with persona data per role.

| Aspect | Assessment |
|--------|------------|
| Complexity | MEDIUM |
| Maintenance | LOW (single config) |
| Hallucination Risk | LOW (centralized grounding) |
| ROI | HIGH |

**Verdict: RECOMMENDED**

### Option C: Prompt-Only Differentiation

Just expand the role guidance section in prompts.

| Aspect | Assessment |
|--------|------------|
| Complexity | LOW |
| Maintenance | MEDIUM (prompt bloat) |
| ROI | MEDIUM |

**Verdict: PARTIAL SOLUTION** - Good interim, not sustainable

---

## 3. Recommended Architecture

### 3.1 Role Persona Schema

Add to `role_skills_taxonomy.json`:

```json
{
  "target_roles": {
    "engineering_manager": {
      "display_name": "Engineering Manager",
      "persona": {
        "identity_statement": "team multiplier and talent developer",
        "voice": "confident, people-focused, delivery-oriented",
        "tagline_templates": [
          "{Identity} who builds high-performing teams that {metric_hook}.",
          "Engineering leader passionate about {passion} and {passion}."
        ],
        "power_verbs": ["built", "scaled", "grew", "coached", "developed", "delivered"],
        "metric_priorities": ["team_size", "retention", "velocity", "delivery"],
        "headline_pattern": "{Title} | {Years}+ Years Engineering Leadership",
        "key_achievement_focus": ["team growth", "culture impact", "delivery improvement"],
        "differentiators": ["multiplier effect", "high-performing teams", "engineering excellence"]
      }
    }
  }
}
```

### 3.2 Persona-Enhanced Prompt Building

Modify prompt builders to inject persona data:

```python
def build_profile_user_prompt(
    candidate_name: str,
    job_title: str,
    role_category: str,
    role_persona: dict,  # NEW: from persona registry
    ...
) -> str:
    identity = role_persona.get("identity_statement")
    power_verbs = ", ".join(role_persona.get("power_verbs", []))
    tagline_templates = role_persona.get("tagline_templates", [])

    # Inject persona context into prompt
```

---

## 4. Key Differentiation Points Between Roles

| Role | Primary Value | Tagline Voice | Metric Focus | Key Differentiator |
|------|--------------|---------------|--------------|-------------------|
| **Engineering Manager** | Team multiplier | People-focused | Team size, retention, velocity | People development |
| **Director** | Org builder | Strategic | Org size, teams, budget | Multi-team leadership |
| **Head of Engineering** | Function creator | Executive | Built from scratch, culture | First engineering hire |
| **Staff Engineer** | Technical depth | Technically deep | System scale, latency | Cross-team influence (no reports) |
| **Principal Engineer** | Technical strategy | Visionary | Company-wide impact | Technical vision |
| **VP Engineering** | Exec + operational | Strategic | Org + delivery metrics | Balance exec + hands-on |
| **CTO** | Vision + business | Visionary | Revenue, valuation | Board-level presence |

---

## 5. ROI Analysis

### 5.1 Where Differentiation Matters Most

**HIGH IMPACT** (implement first):
- Tagline voice - EM sounds people-focused, Staff sounds technically deep
- Metric selection - Team metrics for EM, system metrics for Staff
- Power verbs - "coached" for EM, "architected" for Staff

**MEDIUM IMPACT**:
- Key achievements focus
- Headline patterns
- Skill section ordering (already handled)

**LOW IMPACT** (skip):
- Generic structure (same for all)
- Basic format (same for all)

### 5.2 Expected Improvements

| Metric | Expected Improvement |
|--------|---------------------|
| Tagline relevance | +25% |
| Voice consistency | +30% |
| Key achievement selection | +15% |
| Hallucination risk | -10% |

---

## 6. Implementation Plan

### Phase 1: Add VP Engineering Role (2-4 hours)
- Add `VP_ENGINEERING` to `RoleCategory` enum
- Add VP section to `role_skills_taxonomy.json`
- Update JD extractor prompts

### Phase 2: Design Persona Schema (4-6 hours)
- Define persona schema (identity, voice, templates, verbs, metrics)
- Add persona data for all 7+ roles

### Phase 3: Prompt Enhancement (4-6 hours)
- Modify `build_profile_user_prompt()` to accept persona
- Modify ensemble generation with persona context
- Add persona loading to `HeaderGenerator`

### Phase 4: Testing & Validation (4-8 hours)
- Unit tests for persona loading
- Integration tests for persona-enhanced generation
- Manual QA across all role categories

**Total Estimated Effort**: 14-24 hours

---

## 7. Risk Assessment

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Persona data becomes stale | MEDIUM | Version in JSON, quarterly review |
| Templates too prescriptive | LOW | Use as examples, not requirements |
| Role misclassification | MEDIUM | Improve JD extractor signals for VP |
| Increased config complexity | LOW | Good documentation, JSON validation |

---

## 8. Conclusion

### Do NOT:
- Create 8 separate modules per role (over-engineering)
- Hardcode role-specific logic in prompts (maintenance nightmare)
- Treat all roles the same (underutilization)

### DO:
- Extend existing `role_skills_taxonomy.json` with persona data
- Add VP Engineering as a distinct category
- Inject persona context into prompt building
- Focus on HIGH IMPACT differentiators first

The current system is 70% of the way there. The remaining 30% is configuration, not code.

---

## Appendix: File References

| File | Lines | Purpose |
|------|-------|---------|
| `src/layer1_4/jd_extractor.py` | ~50-80 | RoleCategory enum |
| `data/master-cv/role_skills_taxonomy.json` | - | Skills config per role |
| `src/layer6_v2/types.py` | 236-299 | CareerContext with role emphasis |
| `src/layer6_v2/prompts/header_generation.py` | 124-149, 819-856 | Role guidance & superpowers |
