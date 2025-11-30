# CV Generation Fix: Implementation Checklist

**Date**: 2025-11-30
**Owner**: TBD
**Estimated Time**: 5 developer days

---

## Pre-Implementation

- [ ] Review full architecture analysis (`reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`)
- [ ] Review architecture comparison (`plans/cv-generation-architecture-comparison.md`)
- [ ] Confirm color choice with user: #475569 (dark greyish blue) or different?
- [ ] Confirm STAR validation: warning or error on failure?
- [ ] Confirm tagline placement: after name or after contact line?
- [ ] Create feature branch: `fix/cv-generation-hallucinations`

---

## Phase 1: Master-CV Skill Sourcing (Day 1)

### Files to Modify
- `src/layer6_v2/header_generator.py`
- `src/layer6_v2/types.py`

### Tasks

- [ ] **Task 1.1**: Add `MasterCVSkills` dataclass to `types.py`
  ```python
  @dataclass
  class MasterCVSkills:
      hard_skills: Set[str]
      soft_skills: Set[str]

      @property
      def all_skills(self) -> Set[str]:
          return self.hard_skills | self.soft_skills
  ```

- [ ] **Task 1.2**: Add `_load_all_master_cv_skills()` method to `HeaderGenerator`
  ```python
  def _load_all_master_cv_skills(self, roles: List[RoleData]) -> MasterCVSkills:
      """Aggregate all skills from master-cv roles."""
      hard = set()
      soft = set()
      for role in roles:
          hard.update(role.hard_skills)
          soft.update(role.soft_skills)
      return MasterCVSkills(hard_skills=hard, soft_skills=soft)
  ```

- [ ] **Task 1.3**: Modify `_extract_skills_from_bullets()` method
  - Remove hardcoded `skill_lists` dictionary
  - Accept `master_skills: MasterCVSkills` parameter
  - Only check skills that exist in `master_skills.all_skills`
  - Use fuzzy matching (case-insensitive)

- [ ] **Task 1.4**: Update `generate_skills()` method
  - Load master-cv skills first
  - Pass to extraction logic
  - Remove references to hardcoded skill lists

- [ ] **Task 1.5**: Update `generate()` method signature
  - Accept `roles: List[RoleData]` parameter
  - Pass roles to skill loading

- [ ] **Task 1.6**: Update `orchestrator.py` to pass roles to header generator
  ```python
  header_output = generate_header(
      stitched_cv,
      extracted_jd,
      candidate_data,
      roles=roles  # NEW parameter
  )
  ```

### Testing

- [ ] **Test 1.1**: `test_load_master_cv_skills()`
  - Verify all skills from all roles loaded
  - Check deduplication works

- [ ] **Test 1.2**: `test_no_hallucinated_skills()`
  - Generate CV for sample JD
  - Assert "PHP" not in output
  - Assert "Java" not in output
  - Assert "Spring Boot" not in output

- [ ] **Test 1.3**: `test_skill_case_insensitive_matching()`
  - Master-cv has "AWS"
  - JD has "aws"
  - Assert match found

---

## Phase 2: JD-Driven Category Generation (Day 2-3)

### Files to Modify
- `src/layer6_v2/header_generator.py`
- `src/layer6_v2/prompts/header_generation.py`
- `src/layer6_v2/types.py`

### Tasks

- [ ] **Task 2.1**: Add `CategoryDefinition` dataclass to `types.py`
  ```python
  @dataclass
  class CategoryDefinition:
      category_name: str
      description: str
      skill_keywords: List[str]
      priority: int  # 1 = highest
  ```

- [ ] **Task 2.2**: Add category generation prompt to `prompts/header_generation.py`
  ```python
  CATEGORY_GENERATION_SYSTEM_PROMPT = """You are a CV skill categorization expert.

  Given a job description and candidate skills, create 3-4 skill categories
  that BEST represent what the JD is looking for.

  RULES:
  1. Categories must be JD-specific (not generic)
  2. Use JD terminology when possible
  3. Each category should have 4-8 skills
  4. Prioritize by JD importance
  5. ONLY use skills from candidate's background

  OUTPUT: JSON array of categories
  """
  ```

- [ ] **Task 2.3**: Add `_generate_jd_skill_categories()` method to `HeaderGenerator`
  - Input: `extracted_jd`, `master_skills`, `matched_skills`
  - LLM call with structured output (Pydantic)
  - Return: `List[CategoryDefinition]`
  - Fallback: If LLM fails, return default 4 categories

- [ ] **Task 2.4**: Modify `generate_skills()` method
  - Call `_generate_jd_skill_categories()` instead of hardcoded loop
  - Use returned categories for skill organization
  - Map skills to dynamic categories

- [ ] **Task 2.5**: Add retry logic with tenacity
  ```python
  @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
  def _generate_jd_skill_categories(...):
      # LLM call here
  ```

- [ ] **Task 2.6**: Add fallback category generation
  ```python
  def _fallback_categories(self) -> List[CategoryDefinition]:
      """Default categories if LLM fails."""
      return [
          CategoryDefinition("Leadership", "People management", [], 1),
          CategoryDefinition("Technical", "Technical skills", [], 2),
          CategoryDefinition("Platform", "Infrastructure", [], 3),
          CategoryDefinition("Delivery", "Execution", [], 4),
      ]
  ```

### Testing

- [ ] **Test 2.1**: `test_category_generation_for_ml_role()`
  - JD keywords: TensorFlow, Python, AWS
  - Assert categories include "Machine Learning" or similar
  - Assert NOT just "Technical"

- [ ] **Test 2.2**: `test_category_generation_for_platform_role()`
  - JD keywords: Kubernetes, AWS, DevOps
  - Assert categories include "Cloud" or "Platform Engineering"

- [ ] **Test 2.3**: `test_fallback_categories_on_llm_failure()`
  - Mock LLM failure
  - Assert returns 4 default categories

- [ ] **Test 2.4**: `test_category_skills_grounded_in_master_cv()`
  - Generated categories must only include master-cv skills
  - No hallucinations even in category generation

---

## Phase 3: STAR Format Enforcement (Day 3-4)

### Files to Modify
- `src/layer6_v2/role_generator.py`
- `src/layer6_v2/prompts/role_generation.py`
- `src/layer6_v2/types.py`

### Tasks

- [ ] **Task 3.1**: Add `STARBullet` Pydantic model to `types.py`
  ```python
  class STARBullet(BaseModel):
      situation: str = Field(description="Challenge/context")
      task: str = Field(description="What needed to be done")
      action: str = Field(description="How (must mention skills)")
      result: str = Field(description="Quantified outcome")
      skills_mentioned: List[str] = Field(description="Skills used")

      @field_validator('skills_mentioned')
      def validate_skills_present(cls, v, values):
          if not v:
              raise ValueError("Must mention at least one skill in action")
          return v
  ```

- [ ] **Task 3.2**: Add STAR template to `prompts/role_generation.py`
  ```python
  STAR_BULLET_TEMPLATE = """Each bullet must follow STAR format:

  [CHALLENGE]: What problem existed? (Use: "Facing...", "To address...")
  [TASK]: What needed to be done?
  [ACTION]: How did you do it? MUST mention specific skills.
  [RESULT]: Quantified outcome (numbers, percentages, timelines)

  Example:
  "Facing 30% annual increase in outages (CHALLENGE), led 12-month migration
  (TASK) using AWS Lambda and Python (ACTION with skills), achieving 75%
  incident reduction (RESULT)."
  """
  ```

- [ ] **Task 3.3**: Update role generation prompt to include STAR template

- [ ] **Task 3.4**: Add optional STAR validator
  ```python
  def _validate_star_format(self, bullet: str) -> bool:
      """Check if bullet has STAR elements."""
      has_challenge = any(word in bullet.lower() for word in
                          ["facing", "to address", "despite", "with"])
      has_result = bool(re.search(r'\d+%', bullet))  # Has percentage
      has_skill = # Check if mentions any hard/soft skill
      return has_challenge and has_result and has_skill
  ```

- [ ] **Task 3.5**: Add STAR validation to role generation (warning mode)
  ```python
  if not self._validate_star_format(bullet):
      self._logger.warning(f"Bullet may not be STAR-compliant: {bullet[:50]}")
  ```

### Testing

- [ ] **Test 3.1**: `test_star_bullet_has_challenge()`
  - Parse bullet
  - Assert contains challenge indicator

- [ ] **Test 3.2**: `test_star_bullet_mentions_skills()`
  - Bullet: "Led migration using Python and AWS..."
  - Assert "Python" and "AWS" in skills_mentioned

- [ ] **Test 3.3**: `test_star_bullet_has_quantified_result()`
  - Assert bullet contains number or percentage

- [ ] **Test 3.4**: `test_non_star_bullet_logged_as_warning()`
  - Generate bullet without STAR
  - Assert warning logged (but not error)

---

## Phase 4: Dynamic Tagline (Day 4)

### Files to Modify
- `src/layer6_v2/orchestrator.py`

### Tasks

- [ ] **Task 4.1**: Add relocation regions constant
  ```python
  RELOCATION_REGIONS = {
      "middle_east": ["saudi arabia", "uae", "united arab emirates",
                      "kuwait", "qatar", "oman", "bahrain"],
      "pakistan": ["pakistan", "karachi", "lahore", "islamabad"],
  }
  ```

- [ ] **Task 4.2**: Add `_should_show_relocation_tagline()` method
  ```python
  def _should_show_relocation_tagline(self, location: str) -> bool:
      """Check if location requires relocation tagline."""
      if not location:
          return False
      location_lower = location.lower()
      for regions in RELOCATION_REGIONS.values():
          if any(region in location_lower for region in regions):
              return True
      return False
  ```

- [ ] **Task 4.3**: Modify `_assemble_cv_text()` method
  ```python
  # Header with name
  lines.append(f"# {candidate.name}")

  # Add relocation tagline if applicable
  location = state.get("location", "")  # Or extracted_jd.get("location")
  if self._should_show_relocation_tagline(location):
      lines.append("*Available for International Relocation in 2 months*")
      lines.append("")

  # Contact line...
  ```

- [ ] **Task 4.4**: Update orchestrator to pass state to assembler
  - Ensure `state` or `location` accessible in `_assemble_cv_text()`

### Testing

- [ ] **Test 4.1**: `test_tagline_for_saudi_arabia()`
  - Location: "Riyadh, Saudi Arabia"
  - Assert tagline present

- [ ] **Test 4.2**: `test_tagline_for_uae()`
  - Location: "Dubai, UAE"
  - Assert tagline present

- [ ] **Test 4.3**: `test_tagline_for_pakistan()`
  - Location: "Karachi, Pakistan"
  - Assert tagline present

- [ ] **Test 4.4**: `test_no_tagline_for_germany()`
  - Location: "Munich, Germany"
  - Assert tagline NOT present

- [ ] **Test 4.5**: `test_no_tagline_for_remote()`
  - Location: "Remote"
  - Assert tagline NOT present

---

## Phase 5: Color & Spacing Polish (Day 5)

### Files to Modify
- `frontend/app.py`
- `frontend/templates/base.html`
- `frontend/static/css/cv-editor.css`

### Tasks

- [ ] **Task 5.1**: Update color in `frontend/app.py`
  ```python
  # Line 1967
  "colorAccent": "#475569"  # Was: #0f766e (teal)

  # Line 2160
  "colorAccent": "#475569"  # Was: #0f766e (teal)
  ```

- [ ] **Task 5.2**: Update color in `frontend/templates/base.html`
  ```css
  /* Line 1060 */
  color: #475569;  /* Was: #0f766e */
  ```

- [ ] **Task 5.3**: Reduce spacing in `frontend/static/css/cv-editor.css`
  ```css
  /* Multiply all padding/margin by 0.8 (20% reduction) */

  #cv-editor-content .ProseMirror {
      padding: 1.2rem !important;  /* Was 1.5rem */
  }

  .cv-section {
      margin-bottom: 0.8rem;  /* Was 1rem */
  }

  /* Repeat for all CV-specific spacing */
  ```

- [ ] **Task 5.4**: Test color consistency
  - Check PDF output
  - Check HTML detail page
  - Check editor view

### Testing

- [ ] **Test 5.1**: Visual inspection of PDF
  - Generate CV
  - Export to PDF
  - Verify headers are dark greyish blue (#475569)

- [ ] **Test 5.2**: Visual inspection of HTML
  - Open job detail page
  - Verify color consistency

- [ ] **Test 5.3**: Spacing measurement
  - Measure padding in dev tools
  - Verify 20% reduction applied

- [ ] **Test 5.4**: Print preview
  - Test print CSS
  - Verify spacing looks good on paper

---

## Integration Testing (Day 5)

- [ ] **Test I.1**: End-to-end CV generation
  - Load sample JD from database
  - Run full pipeline
  - Verify:
    - [ ] No hallucinated skills
    - [ ] Categories are JD-specific
    - [ ] Bullets have STAR structure
    - [ ] Tagline present if applicable
    - [ ] Color is dark greyish blue
    - [ ] Spacing is narrower

- [ ] **Test I.2**: Multiple JD types
  - [ ] Machine Learning Engineer JD
  - [ ] Platform Engineer JD
  - [ ] Director of Engineering JD
  - [ ] CTO JD

- [ ] **Test I.3**: Edge cases
  - [ ] JD with no matching skills (should still generate CV)
  - [ ] JD with empty location (no tagline)
  - [ ] Master-cv with only 3 skills (should not error)

---

## Documentation & Cleanup (Day 5)

- [ ] **Doc 1**: Update `plans/architecture.md`
  - Add section on dynamic skill extraction
  - Document category generation flow

- [ ] **Doc 2**: Update `plans/missing.md`
  - Mark P0-1, P0-2, P0-3 as COMPLETE
  - Remove from gaps list

- [ ] **Doc 3**: Add docstrings to new methods
  - `_load_all_master_cv_skills()`
  - `_generate_jd_skill_categories()`
  - `_should_show_relocation_tagline()`

- [ ] **Doc 4**: Update README if needed
  - New features: JD-driven categories, STAR format

---

## Pre-Deployment Checklist

- [ ] All unit tests pass (pytest)
- [ ] All integration tests pass
- [ ] Manual testing on 5+ sample JDs complete
- [ ] Performance benchmarking (should be <10s per CV)
- [ ] Cost analysis (LLM category generation adds ~$0.02/CV)
- [ ] Code review completed
- [ ] Documentation updated
- [ ] Feature branch merged to main

---

## Deployment

- [ ] **Deploy to VPS**
  - SSH to VPS
  - Pull latest code
  - Restart runner service
  - Monitor logs for errors

- [ ] **Smoke Test**
  - Generate 3 CVs in production
  - Verify no errors
  - Check for hallucinations

- [ ] **Monitor**
  - Check LangSmith for traces
  - Monitor API costs
  - Watch for user feedback

---

## Rollback Plan (If Needed)

- [ ] Keep backup branch: `backup/cv-generation-old`
- [ ] Environment variable: `USE_DYNAMIC_CATEGORIES=false` to revert
- [ ] Database: No changes, so no rollback needed
- [ ] Frontend: Simple git revert for CSS/color changes

---

## Success Metrics (Post-Deployment)

Measure after 1 week:

- [ ] Hallucinated skills: 0 (was 3-5 per CV)
- [ ] JD-aligned categories: 90%+ (was 0%)
- [ ] STAR-compliant bullets: 80%+ (was ~30%)
- [ ] Relocation tagline accuracy: 100%
- [ ] User feedback: Positive on color/spacing

---

## Notes

- Estimated effort: 5 developer days
- Critical path: Phase 1 → Phase 2 (dependencies)
- Can parallelize: Phase 4 (tagline) independent of Phase 3 (STAR)
- Biggest risk: LLM category generation failures → mitigated with fallback

---

*Last updated: 2025-11-30*
*Owner: TBD*
*Status: Ready for implementation*
