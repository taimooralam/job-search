# Layer 6 Variant Selection Implementation Plan

**Date**: 2025-12-05
**Status**: Ready for Implementation
**Priority**: P0 - Core CV Generation Quality

---

## Executive Summary

Transform Layer 6 CV generation from **LLM-based text generation** to **intelligent variant selection** from pre-written, interview-defensible achievement bullets. This approach ensures:

1. **Authenticity**: All bullets are pre-validated and interview-defensible
2. **ATS Compliance**: Proper keyword integration without stuffing
3. **Consistency**: No hallucination risk - only select from verified content
4. **Speed**: Reduce LLM calls and generation time

---

## Problem Analysis

### Current Architecture Issues

1. **Generation vs Selection**: Current `role_generator.py` uses LLM to *generate* new bullet text from raw achievements. This introduces:
   - Hallucination risk (invented metrics, technologies)
   - Inconsistent output quality
   - High LLM cost per CV generation
   - Non-reproducible results

2. **Parser Mismatch**: `cv_loader.py` parses simple bullet format (`## Achievements` → `• text`), but enhanced role files now have:
   ```markdown
   ### Achievement N: [Title]
   **Core Fact**: ...
   **Variants**:
   - **Technical**: ...
   - **Architecture**: ...
   - **Impact**: ...
   - **Leadership**: ...
   - **Short**: ...
   **Keywords**: ...
   ```

3. **Lost Metadata**: The enhanced files contain rich metadata (keywords, interview defensibility, selection guides) that the current parser ignores.

### Research-Driven Requirements

From `ats-compliance-research.md`, `ats-guide.md`, `resume-guide.md`:

1. **ATS Compliance**:
   - Include both acronym AND full term (e.g., "Kubernetes (K8s)")
   - Natural keyword integration, not stuffing
   - Keywords in context near metrics
   - Target 70%+ keyword match to JD

2. **Recruiter Optimization**:
   - 6-8 seconds initial scan time
   - Clear metrics and outcomes
   - Role-appropriate emphasis (IC vs Management track)
   - No generic language

3. **System-Specific Quirks**:
   - Greenhouse: Word frequency matters (3-5 natural repetitions)
   - Lever: No abbreviation expansion - need both forms
   - Taleo: Extreme literalism - exact JD phrasing

---

## Proposed Architecture

### Core Concept: Variant Selection Algorithm

Instead of generating new text, the system will:

1. **Parse** the enhanced role files to extract all variants and metadata
2. **Score** each variant against JD requirements (keywords, pain points, role category)
3. **Select** the best variant per achievement based on composite score
4. **Assemble** the final CV with optimal variant mix

### New Component: `VariantParser`

```python
@dataclass
class AchievementVariant:
    """A single variant of an achievement."""
    variant_type: str  # "Technical", "Architecture", "Impact", "Leadership", "Short"
    text: str

@dataclass
class Achievement:
    """A complete achievement with all variants."""
    id: str
    title: str
    core_fact: str
    variants: Dict[str, AchievementVariant]  # variant_type -> variant
    keywords: List[str]
    interview_defensibility: str

@dataclass
class EnhancedRoleData(RoleData):
    """Extended role data with achievements and variants."""
    achievements_structured: List[Achievement]
    selection_guide: Dict[str, List[str]]  # JD emphasis -> achievement IDs
```

### New Component: `VariantSelector`

```python
class VariantSelector:
    """
    Selects optimal variants based on JD analysis.

    Scoring factors:
    1. Keyword overlap with JD (40%)
    2. Pain point alignment (30%)
    3. Role category match (20%)
    4. Variant type preference (10%)
    """

    def select_variants(
        self,
        role: EnhancedRoleData,
        extracted_jd: ExtractedJD,
        target_count: int,
    ) -> List[SelectedBullet]:
        """Select best variants for a role."""
        pass

    def _score_variant(
        self,
        variant: AchievementVariant,
        achievement: Achievement,
        extracted_jd: ExtractedJD,
    ) -> float:
        """Score a single variant against JD requirements."""
        pass
```

### Variant Type Selection Rules

Based on role category from JD:

| Role Category | Primary Variants | Secondary Variants |
|---------------|------------------|-------------------|
| `staff_principal_engineer` | Technical, Architecture | Impact |
| `engineering_manager` | Leadership, Impact | Technical |
| `director_of_engineering` | Leadership, Impact | Architecture |
| `head_of_engineering` | Leadership, Architecture | Impact |
| `cto` | Architecture, Leadership | Impact |

---

## Implementation Steps

### Phase 1: Enhanced Parser (Day 1-2)

**File**: `src/layer6_v2/variant_parser.py` (new)

1. Create `VariantParser` class that reads enhanced role markdown files
2. Parse structured achievements with variants
3. Extract keywords and metadata
4. Handle backward compatibility with old format

**Key Functions**:
```python
def parse_role_file(file_path: Path) -> EnhancedRoleData
def parse_achievement_section(content: str) -> List[Achievement]
def extract_variants(achievement_block: str) -> Dict[str, AchievementVariant]
def extract_selection_guide(content: str) -> Dict[str, List[str]]
```

### Phase 2: Variant Selector (Day 2-3)

**File**: `src/layer6_v2/variant_selector.py` (new)

1. Implement scoring algorithm
2. Create variant selection logic based on JD analysis
3. Handle career stage weighting (recent vs early career)
4. Implement deduplication for similar achievements across roles

**Scoring Algorithm**:
```python
def calculate_variant_score(
    variant: AchievementVariant,
    achievement: Achievement,
    jd: ExtractedJD,
) -> float:
    score = 0.0

    # Keyword overlap (40%)
    variant_keywords = set(extract_keywords(variant.text))
    jd_keywords = set(jd.get("top_keywords", []))
    keyword_overlap = len(variant_keywords & jd_keywords) / max(len(jd_keywords), 1)
    score += keyword_overlap * 0.4

    # Pain point alignment (30%)
    pain_points = jd.get("implied_pain_points", [])
    pain_match = max(
        semantic_similarity(variant.text, pp) for pp in pain_points
    ) if pain_points else 0.5
    score += pain_match * 0.3

    # Role category match (20%)
    role_category = jd.get("role_category", "")
    preferred_types = VARIANT_PREFERENCES.get(role_category, ["Technical"])
    type_bonus = 1.0 if variant.variant_type in preferred_types else 0.5
    score += type_bonus * 0.2

    # Achievement keywords match (10%)
    achievement_kw_match = len(set(achievement.keywords) & jd_keywords) / max(len(achievement.keywords), 1)
    score += achievement_kw_match * 0.1

    return score
```

### Phase 3: Update CVLoader (Day 3)

**File**: `src/layer6_v2/cv_loader.py` (modify)

1. Extend `_parse_achievements` to detect enhanced format
2. Add `load_enhanced()` method for new format
3. Maintain backward compatibility with simple format
4. Update `RoleData` dataclass to include structured achievements

### Phase 4: Replace Generation with Selection (Day 4)

**File**: `src/layer6_v2/role_generator.py` (major refactor)

1. Keep `RoleGenerator` class but change core logic
2. Replace LLM generation with variant selection
3. Add optional LLM "polish" pass for keyword integration
4. Simplify STAR enforcement (variants already follow format)

**New Flow**:
```python
def generate(self, role: RoleData, extracted_jd: ExtractedJD, ...) -> RoleBullets:
    # Step 1: Load enhanced role data
    enhanced_role = self.variant_parser.parse_role(role)

    # Step 2: Select best variants
    selected = self.variant_selector.select_variants(
        role=enhanced_role,
        extracted_jd=extracted_jd,
        target_count=self._get_bullet_count(career_context),
    )

    # Step 3: Optional keyword polish (minimal LLM use)
    if self.enable_keyword_polish:
        selected = self._polish_keywords(selected, extracted_jd)

    # Step 4: Build RoleBullets
    return self._build_role_bullets(role, selected)
```

### Phase 5: Update Prompts (Day 4)

**File**: `src/layer6_v2/prompts/role_generation.py` (modify)

1. Create new prompt for optional "keyword polish" pass
2. Remove full generation prompt (no longer needed)
3. Add prompt for handling edge cases (no matching variants)

### Phase 6: Update Orchestrator (Day 5)

**File**: `src/layer6_v2/orchestrator.py` (modify)

1. Update `_generate_all_role_bullets` to use new flow
2. Simplify QA (variants are pre-validated)
3. Update logging to show selection decisions
4. Add metrics for variant selection coverage

### Phase 7: Testing & Validation (Day 5-6)

1. Unit tests for VariantParser
2. Unit tests for VariantSelector
3. Integration tests with real JDs
4. A/B comparison: old generation vs new selection
5. ATS compliance validation

---

## Files to Create/Modify

### New Files
- `src/layer6_v2/variant_parser.py` - Parse enhanced role files
- `src/layer6_v2/variant_selector.py` - Select optimal variants
- `tests/layer6_v2/test_variant_parser.py` - Parser tests
- `tests/layer6_v2/test_variant_selector.py` - Selector tests

### Modified Files
- `src/layer6_v2/cv_loader.py` - Add enhanced format support
- `src/layer6_v2/role_generator.py` - Replace generation with selection
- `src/layer6_v2/orchestrator.py` - Update pipeline flow
- `src/layer6_v2/prompts/role_generation.py` - Simplify prompts
- `src/layer6_v2/types.py` - Add new dataclasses

---

## ATS Compliance Features

### Keyword Integration Strategy

1. **Both Forms Rule**: When a keyword has an acronym, include both:
   - "Kubernetes (K8s)" or "K8s (Kubernetes)"
   - "Continuous Integration/Continuous Deployment (CI/CD)"

2. **Natural Repetition**: Target 3-5 natural occurrences of key terms:
   - Once in summary/profile
   - Once in skills section
   - 2-3 times in achievement bullets (in context)

3. **Context Near Metrics**: Keywords placed near quantified results:
   - GOOD: "Reduced latency by 40% using Redis caching"
   - BAD: Skills list with "Redis" and separate bullet with "Reduced latency by 40%"

### Format Compliance

1. **Standard Headers**: "Professional Experience", "Education", "Skills"
2. **Single Column**: No tables or multi-column layouts
3. **Simple Bullets**: Use only `•` character
4. **No Graphics**: Plain text only in generated output

---

## Backward Compatibility

The system will support both formats:

1. **Legacy Detection**: Check for `### Achievement N:` pattern
   - If found: Parse as enhanced format
   - If not: Fall back to simple bullet parsing

2. **Hybrid Mode**: For roles not yet enhanced:
   - Use simple bullets directly
   - Skip variant selection
   - Apply lighter keyword integration

---

## Success Metrics

1. **Generation Speed**: 50% reduction in LLM calls
2. **Consistency**: Zero hallucination flags in QA
3. **ATS Score**: Target 75%+ keyword coverage
4. **Interview Defensibility**: 100% of bullets traceable to core facts
5. **Human Quality**: Recruiter feedback score >= 8/10

---

## Risk Mitigation

1. **Missing Variants**: If a role lacks variants for a JD type, fall back to Technical or Short variant
2. **Low Coverage**: If selected variants don't cover enough JD keywords, trigger optional LLM polish
3. **Edge Cases**: Keep legacy generation as fallback for unusual situations

---

## Timeline

| Day | Tasks |
|-----|-------|
| 1 | Create VariantParser, write unit tests |
| 2 | Create VariantSelector, implement scoring |
| 3 | Update CVLoader, integration with parser |
| 4 | Refactor RoleGenerator, update prompts |
| 5 | Update Orchestrator, integration testing |
| 6 | Full pipeline testing, A/B validation |

---

## Next Steps

1. [ ] Review and approve this plan
2. [ ] Begin Phase 1: VariantParser implementation
3. [ ] Set up test fixtures with sample JDs
4. [ ] Create A/B testing framework for comparison

---

## Appendix: Enhanced Role File Format Reference

```markdown
### Achievement N: [Title]

**Core Fact**: [Factual description - source of truth]

**Variants**:
- **Technical**: [Technical depth emphasis]
- **Architecture**: [System design emphasis]
- **Impact**: [Business outcome emphasis]
- **Leadership**: [People/team emphasis]
- **Short**: [Concise version for space-constrained CVs]

**Keywords**: [comma-separated ATS keywords]

**Interview Defensibility**: ✅ Can explain [specific details]

**Business Context**: [Optional - provides SITUATION for ARIS/STAR]
```

## Appendix: Selection Guide Reference

```markdown
## Selection Guide by JD Type

| JD Emphasis | Recommended Achievements |
|-------------|-------------------------|
| Python/Backend | 1, 4 (Flask APIs, MongoDB) |
| API Design | 1, 3 (REST APIs, Swagger) |
| Architecture | 1, 5 (onion architecture, event-driven) |
| Leadership | 5, 6 (team leadership, mentoring) |
```
