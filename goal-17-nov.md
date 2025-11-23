# Goal for 17 Nov: Layer 2.5 STAR Selector - Core Implementation

## Context
**Phase 1.3 - Day 1 of 4-day sprint**

Based on external evaluation (Overall Score: 7.3/10), the **critical gap** is personalization depth:
- Current: 7/10 (job-aware but STAR records passed as monolithic text)
- Target: 9/10 (explicit pain-point → STAR mapping with cited metrics)
- Gap: No structured selection of best-fit achievements per job

**Today's Mission:** Enable hyper-personalization by building Layer 2.5 (STAR Selector) that maps job pain points to the 2-3 most relevant candidate achievements.

---

## Success Criteria for Today

✅ **STAR Parser working**
- Reads `knowledge-base.md` → extracts 11 structured STAR objects
- Each STAR has: ID, company, role, situation, task, actions, results, metrics, keywords
- Test script validates all records parsed correctly

✅ **STAR Selector working**
- Accepts pain points + all STARs → scores relevance with LLM
- Selects top 2-3 STARs with highest aggregate scores
- Outputs: `selected_stars` + `star_to_pain_mapping`

✅ **State schema updated**
- `JobState` has `selected_stars` and `star_to_pain_mapping` fields
- Fields documented with clear types

✅ **Workflow integrated**
- Layer 2.5 node added to `src/workflow.py` after Layer 2
- End-to-end test with one real job passes
- Selected STARs flow to Layer 4 and Layer 6

**Outcome:** Pipeline can identify and select the most relevant achievements for each job automatically.

---

## Implementation Tasks (6.5 hours estimated)

### Task 1: STAR Parser (2 hours) ⏱️

**File:** `src/layer2_5/star_parser.py`

**Requirements:**
- Parse `knowledge-base.md` into structured STAR objects
- Handle markdown sections separated by `================`
- Extract all fields for each STAR record:
  - `id`: UUID from "ID:" line
  - `company`: From "COMPANY:" line
  - `role`: From "ROLE TITLE:" line
  - `period`: From "PERIOD:" line
  - `domain_areas`: From "DOMAIN AREAS:" line
  - `situation`: Full "SITUATION:" section
  - `task`: Full "TASK:" section
  - `actions`: Full "ACTIONS:" section (bullet points)
  - `results`: Full "RESULTS:" section (bullet points)
  - `metrics`: Extract from "METRICS:" section
  - `keywords`: From "ATS KEYWORDS:" line

**Function Signature:**
```python
def parse_star_records(knowledge_base_path: str) -> List[STARRecord]:
    """
    Parse knowledge-base.md into structured STAR objects.

    Args:
        knowledge_base_path: Path to knowledge-base.md file

    Returns:
        List of STARRecord dicts with all fields

    Raises:
        FileNotFoundError: If knowledge base file not found
        ValueError: If parsing fails
    """
```

**Test Script:** `scripts/test_star_parser.py`
- Verify 11 records parsed
- Verify all required fields present
- Print first record to inspect structure
- Validate STAR #1 has correct ID (b7e9df84-84b3-4957-93f1-7f1adfe5588c)

---

### Task 2: STAR Selector (3 hours) ⏱️

**File:** `src/layer2_5/star_selector.py`

**Requirements:**
- Create `STARSelector` class similar to other layers
- Use LLM to score each STAR's relevance to each pain point
- Aggregate scores to select top 2-3 STARs

**Prompt Design:**
```
You are analyzing candidate STAR achievements for job fit.

Job Pain Points:
{pain_points}

Candidate STAR Records:
{star_summaries}

For each STAR record, rate its relevance to EACH pain point on a scale of 0-10:
- 0: Not relevant at all
- 5: Somewhat relevant, transferable skills
- 10: Directly addresses this pain point with proven results

Output format:
STAR_ID: <UUID>
Pain Point 1: <score>
Pain Point 2: <score>
...
Aggregate: <sum of scores>
Reasoning: <1-2 sentences>

---

STAR_ID: <UUID>
...
```

**Selection Logic:**
1. Call LLM with all STARs and pain points
2. Parse response to extract scores per STAR
3. Select top 2-3 STARs by aggregate score
4. Create `star_to_pain_mapping`: For each pain point, which STARs scored >7

**Function Signature:**
```python
def select_stars(state: JobState) -> Dict[str, Any]:
    """
    Layer 2.5: STAR Selector node.

    Selects 2-3 best STAR records matching job pain points.

    Args:
        state: JobState with pain_points and candidate_profile

    Returns:
        Dict with selected_stars and star_to_pain_mapping
    """
```

**Test Script:** `scripts/test_layer2_5.py`
- Use real pain points from a test job
- Verify 2-3 STARs selected
- Verify mapping created
- Print selection reasoning

---

### Task 3: State Schema Update (30 min) ⏱️

**File:** `src/common/state.py`

**Add to JobState:**
```python
class STARRecord(TypedDict):
    """Structured STAR achievement record."""
    id: str
    company: str
    role: str
    period: str
    domain_areas: str
    situation: str
    task: str
    actions: str
    results: str
    metrics: str
    keywords: str

class JobState(TypedDict):
    # ... existing fields ...

    # ===== LAYER 2.5: STAR Selector (NEW - Phase 1.3) =====
    selected_stars: Optional[List[STARRecord]]  # 2-3 best-fit STAR records for this job
    star_to_pain_mapping: Optional[Dict[str, List[str]]]  # pain_point -> [star_ids]
```

**Documentation:**
- Update docstring to explain Layer 2.5 fields
- Document that `selected_stars` are used in Layer 4 & 6 instead of full `candidate_profile`

---

### Task 4: Workflow Integration (1 hour) ⏱️

**File:** `src/workflow.py`

**Changes:**
1. Import Layer 2.5: `from src.layer2_5 import select_stars`
2. Add node: `workflow.add_node("layer_2_5_star_selector", select_stars)`
3. Update edges:
   ```python
   workflow.add_edge("layer_2_pain_points", "layer_2_5_star_selector")  # After Layer 2
   workflow.add_edge("layer_2_5_star_selector", "layer_3_company")      # Before Layer 3
   ```

**Verification:**
- Run `scripts/run_pipeline.py` with one test job
- Check LangSmith trace shows Layer 2.5 node
- Verify `selected_stars` in final state
- Print selected STAR IDs to console

---

## Testing Checklist

**STAR Parser:**
- [ ] All 11 records parsed successfully
- [ ] STAR #1 ID matches expected UUID
- [ ] All required fields present (no None values)
- [ ] Metrics field contains quantified results

**STAR Selector:**
- [ ] LLM scores all STARs against pain points
- [ ] Top 2-3 STARs selected (not more, not less)
- [ ] Mapping created showing which STAR addresses which pain point
- [ ] Selection reasoning makes sense

**State Schema:**
- [ ] TypedDict compiles without errors
- [ ] Fields properly documented
- [ ] Optional types used correctly

**Workflow Integration:**
- [ ] Layer 2.5 node appears in LangSmith trace
- [ ] End-to-end pipeline completes successfully
- [ ] `selected_stars` populated in final state
- [ ] No errors in layer execution order

---

## Files to Create/Modify

**New Files:**
- `src/layer2_5/__init__.py`
- `src/layer2_5/star_parser.py`
- `src/layer2_5/star_selector.py`
- `scripts/test_star_parser.py`
- `scripts/test_layer2_5.py`

**Modified Files:**
- `src/common/state.py` - Add Layer 2.5 fields
- `src/workflow.py` - Add Layer 2.5 node and edges

---

## Dependencies

**Python packages (already installed):**
- `langchain_openai` - For LLM calls
- `tenacity` - For retries
- `typing` - For TypedDict

**External services:**
- OpenAI API (via OpenRouter) - For STAR scoring
- MongoDB - For reading knowledge-base.md path from config

**Config:**
- `Config.CANDIDATE_PROFILE_PATH` - Path to knowledge-base.md
- `Config.OPENAI_API_KEY` - For LLM calls

---

## Next Steps (Day 2 - 18 Nov)

After today's implementation:
1. **Layer 4 Enhancement**: Update Opportunity Mapper to use `selected_stars` instead of full profile
2. **Layer 6 Enhancement**: Update cover letter prompt to cite specific STAR metrics
3. **Pytest Foundation**: Add unit tests with mocked LLM calls

---

## Risks & Mitigation

**Risk:** Knowledge base parsing fails on unexpected format
- **Mitigation:** Test parser with full file; add clear error messages

**Risk:** LLM scoring is inconsistent or doesn't follow format
- **Mitigation:** Use clear prompt with format examples; add parsing fallbacks

**Risk:** Too many/too few STARs selected
- **Mitigation:** Hardcode selection logic (top 2-3 by aggregate score)

**Risk:** Integration breaks existing pipeline
- **Mitigation:** Test end-to-end after each change; keep Layer 4/6 using `candidate_profile` for now

---

## Definition of Done

✅ Parser extracts all 11 STAR records with complete fields
✅ Selector chooses 2-3 best STARs using LLM scoring
✅ State schema includes `selected_stars` and `star_to_pain_mapping`
✅ Layer 2.5 integrated into workflow between Layer 2 and Layer 3
✅ End-to-end test completes with selected STARs in state
✅ All test scripts pass
✅ LangSmith trace shows Layer 2.5 execution
✅ Code committed to git with clear commit message

**Time Budget:** 6.5 hours focused work
**Stretch Goal:** If time allows, start Day 2 tasks (Layer 4 prompt enhancement)
