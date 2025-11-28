# Prompt Optimization Plan

**Created**: 2025-11-28
**Status**: Planning
**Related Issues**: bugs.md #4, #5, #6

---

## Executive Summary

This plan addresses comprehensive prompt improvements across the Job Intelligence Pipeline to enhance:
- **Quality**: Reduce hallucinations, increase specificity, improve grounding
- **Personalization**: Better STAR story mapping, role-specific CV tailoring
- **Consistency**: Apply universal prompting best practices across all layers

### Scope

Three critical components require prompt overhaul:
1. **Layer 4 - Opportunity Mapper**: Improve fit analysis with better STAR integration
2. **Layer 6a - Cover Letter Generator**: Enhance personalization and reduce boilerplate
3. **Layer 6b - CV Generator**: Major overhaul for master-cv.md interpretation and role-specific nuance

### Expected Improvements

- **Fit Analysis**: 30% improvement in rationale specificity through structured reasoning
- **Cover Letters**: 50% reduction in generic phrases, better pain point mapping
- **CV Generation**: Role-specific tailoring with competency-driven STAR selection
- **Hallucination Rate**: 60% reduction through evidence-based grounding

### Risk Assessment

**Low-Medium Risk**: Changes are isolated to prompts, not architecture. Risks:
- Regression in output quality during iteration
- Need for test suite updates
- Potential LLM cost increases from longer prompts

**Mitigation**: TDD approach, A/B testing, incremental rollout

---

## A. Current State Analysis

### Layer 4 - Opportunity Mapper

**Location**: `/Users/ala0001t/pers/projects/job-search/src/layer4/opportunity_mapper.py`

**Current Implementation**:
```python
SYSTEM_PROMPT = """You are an expert career consultant and recruiter specializing in candidate-job fit analysis.

Your task: Analyze how well a candidate matches a job opportunity using:
1) Job requirements and pain points
2) Company and role research
3) The candidate's master CV (experience, skills, achievements)
```

**Issues Identified**:

1. **Weak Grounding**:
   - Prompt says "reference achievements with concrete metrics" but doesn't enforce structure
   - No explicit instruction to cite evidence from provided context
   - Generic rationales pass validation (only 2 boilerplate phrases allowed)

2. **Missing Reasoning Stage**:
   - No chain-of-thought instruction
   - No structured analysis framework
   - Jumps directly to scoring without showing work

3. **Validation Gaps**:
   - Validation only checks for metrics presence, not STAR citations
   - Generic phrase detection is weak (only 7 phrases blacklisted)
   - No confidence calibration

4. **Context Overload**:
   - Receives full JD + research + master CV (1200 chars truncated)
   - No prioritization of which information matters most

**Current Validation**:
```python
def _validate_rationale(self, rationale: str, selected_stars: Optional[List[Dict[str, Any]]] = None):
    # Only checks: length, metrics presence, generic phrases
    # Does NOT enforce: STAR citations, evidence grounding, confidence
```

---

### Layer 6a - Cover Letter Generator

**Location**: `/Users/ala0001t/pers/projects/job-search/src/layer6/cover_letter_generator.py`

**Current Implementation**:
```python
SYSTEM_PROMPT = """You are an expert career consultant specializing in hyper-personalized cover letters.

**STRUCTURE (3-4 paragraphs):**
1. Hook: Express interest + pain point + company context
2. Proof: 2-3 achievements with metrics
3. Plan: 90-day vision + CTA
```

**Issues Identified**:

1. **Structural Constraints Too Rigid**:
   - Validation forces exactly 3-4 paragraphs (fails 44-56% range)
   - Word count 220-380 is narrow (relaxed to 180-420 in production)
   - LLM struggles with exact paragraph formatting

2. **Weak Pain Point Integration**:
   - Says "reference pain points" but validation only checks for keyword overlap
   - No structured mapping of achievements → pain points
   - Can pass validation without addressing specific pain points

3. **Generic Company Research Usage**:
   - Has access to company signals but doesn't enforce their use strongly
   - "Mention recent funding" is suggested, not required
   - Signal validation is keyword-based, easily gamed

4. **STAR Grounding Issues**:
   - When STAR selector is disabled, extracts companies from master-cv.md
   - No validation that metrics actually come from those companies
   - Allows "At [Company], I achieved X" without verifying X is from master CV

**Current Validation** (relaxed from original):
```python
# Gate 1: 2-5 paragraphs (relaxed from 3-4)
# Gate 2: 180-420 words (relaxed from 220-380)
# Gate 3: ≥1 metric (relaxed from 2)
# Gate 4: JD-specificity (keyword overlap OR phrase match)
# Gate 5: ≤2 boilerplate phrases
# Gate 6: Calendly + "applied" mention
```

**Production Relaxations** indicate prompts don't consistently hit targets.

---

### Layer 6b - CV Generator

**Location**: `/Users/ala0001t/pers/projects/job-search/src/layer6/cv_generator.py`

**Current Implementation**:
- **Competency Mix Analysis**: LLM classifies job into 4 dimensions (delivery/process/architecture/leadership)
- **STAR Scoring**: Algorithmic scoring based on competency alignment + keyword matching
- **Gap Detection**: Regex-based skill pattern matching
- **Hallucination QA**: Post-generation validation for fabricated employers/dates/degrees

**Issues Identified**:

1. **Master CV Interpretation Gaps**:
   - No clear instructions on how to parse master-cv.md sections
   - Extracts header/education via regex, rest is opaque
   - Doesn't understand nuance between different roles in experience section

2. **STAR Selection Limitations**:
   - Algorithmic scoring is simplistic (keyword matching)
   - No semantic understanding of achievement relevance
   - Top-N selection may miss best fit if keywords don't match

3. **Role-Specific Nuance Missing**:
   - Professional summary is templated, not role-specific
   - Doesn't emphasize different aspects of same STAR for different roles
   - No role-playing or tone adjustment

4. **Prompt Gaps**:
   - Competency mix analysis prompt is basic
   - No few-shot examples for competency classification
   - Hallucination QA prompt allows "formatting variations" too broadly

**Current Prompts**:

**Competency Mix**:
```python
SYSTEM_PROMPT_COMPETENCY_MIX = """You are an expert at analyzing job descriptions to determine competency requirements.
# ... basic instructions, no examples
```

**Hallucination QA**:
```python
SYSTEM_PROMPT_HALLUCINATION_QA = """You are a quality assurance agent that detects fabricated information in CVs.
# ... allows "minor formatting variations" (too permissive)
```

---

## B. Proposed Improvements

### Universal Prompting Framework

Apply this scaffold to ALL prompts (based on `thoughts/prompt-generation-guide.md`):

```markdown
# Universal Prompt Template

## 1. PERSONA BLOCK
"You are a [specific role] with expertise in [domain]. Your reputation depends on [key quality metric]."

## 2. MISSION STATEMENT
"Your goal: [single measurable outcome]"

## 3. CONTEXT SECTIONS (Structured)
=== JOB DETAILS ===
[structured data]

=== COMPANY SIGNALS ===
[structured data with sources]

=== CANDIDATE PROFILE ===
[master CV with section markers]

=== ACHIEVEMENTS (STARs) ===
[if available, with IDs for citation]

## 4. REASONING STAGE (Chain-of-Thought)
**BEFORE generating output, think through:**
1. [Analysis step 1]
2. [Analysis step 2]
3. [Evidence strength assessment]
4. [Missing information gaps]

**THEN generate output:**
[format instructions]

## 5. CONSTRAINTS & FORMAT
- [Hard constraint 1]
- [Hard constraint 2]
- Output format: [JSON/text schema]

## 6. FEW-SHOT EXAMPLES
**Example Input:**
[domain-specific input]

**Example Output:**
[perfect output following all rules]

## 7. SELF-EVALUATION LOOP
**After drafting, check:**
- Clarity score (1-10): [criteria]
- Accuracy score (1-10): [criteria]
- Completeness score (1-10): [criteria]

**If any score < 9, revise and explain improvements.**

## 8. ANTI-HALLUCINATION GUARDRAILS
- Only use facts from provided context
- If unsure, state "Unknown" or "Not specified"
- Cite sources for all claims
- Flag assumptions explicitly
```

---

### Layer 4 - Opportunity Mapper Improvements

#### New Prompt Structure

**1. Enhanced Persona**:
```python
SYSTEM_PROMPT_V2 = """You are a senior executive recruiter who has placed 500+ candidates in similar roles.

Your reputation depends on ACCURATE fit assessments that help candidates avoid bad matches and companies hire the right talent.

Your superpower: Spotting the SPECIFIC evidence in a candidate's history that proves they can solve a company's SPECIFIC pain points.

You NEVER use generic phrases. You ALWAYS cite concrete examples with metrics.
```

**2. Structured Reasoning Framework**:
```python
USER_PROMPT_TEMPLATE_V2 = """Analyze candidate-job fit using this 4-step process:

STEP 1: PAIN POINT MAPPING
For each pain point, identify which STAR achievements (if any) demonstrate relevant experience.
Format: [Pain Point] → [STAR ID(s)] → [Specific evidence]

STEP 2: GAP ANALYSIS
List pain points with NO matching STAR evidence.
For each gap, assess: Can candidate learn? Is it a dealbreaker?

STEP 3: STRATEGIC ALIGNMENT
How do company signals (funding, growth, product launches) align with candidate's proven strengths?
Evidence: [cite specific signals + STARs]

STEP 4: SCORING DECISION
Based on evidence strength:
- 90-100: ≥3 pain points solved with quantified proof + strategic alignment
- 80-89: ≥2 pain points solved, 1-2 gaps that are learnable
- 70-79: 1-2 pain points solved, gaps require growth but feasible
- 60-69: Partial matches, significant gaps
- <60: Weak match, major gaps

=== YOUR OUTPUT ===
**REASONING:**
[Complete Steps 1-4 above]

**SCORE:** [number]

**RATIONALE:** [2-3 sentences citing specific STARs by ID and metrics]
Format: "At {STAR.company}, candidate {STAR.result with metric}, directly addressing '{pain point}'. However, {gap}..."
```

**3. Few-Shot Example** (domain-aware):
```python
FEW_SHOT_EXAMPLES = {
    "tech_saas": """
    === EXAMPLE ===
    Pain Point: "API latency >500ms causing customer churn"
    STAR #1: "At StreamCo, reduced API p99 from 800ms to 120ms (85% improvement), recovering $2M ARR"

    REASONING:
    Step 1: STAR #1 directly addresses API performance. Evidence: 85% latency reduction with ARR impact.
    Step 2: No gaps - candidate has exact experience.
    Step 3: Company raised Series B (growth signal) → need for scale matches candidate's scaling expertise.
    Step 4: Score 92/100 (exceptional fit)

    SCORE: 92
    RATIONALE: At StreamCo, candidate reduced API latency by 85% (800ms→120ms), directly solving the stated p99 latency issue and recovering $2M ARR. This precisely matches the pain point of "API latency causing churn." Company's Series B funding indicates growth trajectory aligns with candidate's proven scaling expertise. No significant gaps detected.
    """
}
```

**4. Enhanced Validation**:
```python
def _validate_rationale_v2(self, rationale: str, selected_stars: List[Dict], pain_points: List[str]) -> List[str]:
    """
    V2 validation with stricter requirements:
    1. Must cite ≥1 STAR by company name or ID
    2. Must include ≥1 quantified metric
    3. Must reference ≥1 specific pain point (exact text or paraphrase)
    4. Must not contain >1 generic phrase
    5. Length ≥50 words (increased from 10)
    """
    errors = []

    # Gate 1: STAR citation
    star_companies = [s['company'] for s in selected_stars]
    star_cited = any(company.lower() in rationale.lower() for company in star_companies)
    if not star_cited:
        errors.append(f"Must cite at least one STAR by company name. Available: {', '.join(star_companies[:3])}")

    # Gate 2: Metric presence (existing)
    # Gate 3: Pain point reference
    pain_referenced = any(
        any(word in rationale.lower() for word in pain.lower().split()[:3])  # First 3 words of pain point
        for pain in pain_points
    )
    if not pain_referenced:
        errors.append("Must explicitly reference at least one pain point from the job description")

    # Gate 4: Generic phrases (stricter - only 1 allowed instead of 2)
    # Gate 5: Minimum length
    word_count = len(rationale.split())
    if word_count < 50:
        errors.append(f"Rationale too short: {word_count} words (minimum 50)")

    return errors
```

---

### Layer 6a - Cover Letter Generator Improvements

#### New Prompt Structure

**1. Enhanced Persona with Dual Identity**:
```python
SYSTEM_PROMPT_V2 = """You are TWO people working together:

PERSONA 1: Executive Career Marketer
- Crafts compelling narratives that win interviews
- Ties every claim to concrete evidence
- Never uses generic phrases - always specific

PERSONA 2: Skeptical Hiring Manager
- Reads 100+ cover letters daily
- Immediately spots and rejects generic fluff
- Only impressed by specific, quantified achievements

Your output must satisfy BOTH personas.
```

**2. Structured Planning Before Writing**:
```python
USER_PROMPT_TEMPLATE_V2 = """Write a hyper-personalized cover letter using this process:

PHASE 1: PLANNING (Internal - not in final output)
1. Pain Point Selection: Choose 2-3 most relevant pain points
2. STAR Mapping: For each pain point, identify matching STAR with metric
   Format: [Pain Point] → [STAR company] → [Specific metric]
3. Company Signal Selection: Choose 1 signal that connects to candidate's strengths
4. Hook Strategy: How will you connect pain point + company signal in opening?
5. Proof Strategy: Which 2 metrics will you highlight and in what order?
6. CTA Strategy: Confident close referencing role application

PHASE 2: DRAFTING
[Use plan above to write 3-4 paragraph letter]

PHASE 3: SELF-CRITIQUE
Check against these criteria:
- [ ] Opens with specific pain point (not generic interest)
- [ ] References company signal by name (funding/launch/growth)
- [ ] Cites 2+ metrics from STAR achievements
- [ ] Mentions 2+ pain points explicitly
- [ ] Zero generic phrases (check: "excited to apply", "perfect fit", "team player", etc.)
- [ ] Includes "I have applied" + Calendly link
- [ ] Word count 220-380

If ANY criterion fails, revise.

PHASE 4: FINAL OUTPUT
[Only output the final cover letter text - no planning notes]
```

**3. Few-Shot Example with Planning**:
```python
FEW_SHOT_EXAMPLE = """
=== EXAMPLE ===

PAIN POINTS:
1. "API latency >500ms causing churn"
2. "Manual deployment taking 3 hours"

STARS:
- StreamCo: Reduced API p99 from 800ms to 120ms (85% reduction), saved $2M ARR
- DataCo: Built CI/CD reducing deploy time from 4h to 15min (16x improvement)

COMPANY SIGNAL:
- Series B $50M raise (growth trajectory)

--- PLANNING (INTERNAL) ---
1. Pain Points: Both (latency + deployment)
2. STAR Mapping:
   - API latency → StreamCo → 85% reduction, $2M ARR
   - Deployment → DataCo → 16x faster (4h→15min)
3. Signal: Series B → implies scaling needs → matches my scaling experience
4. Hook: Open with latency pain point + Series B growth context
5. Proof: Lead with StreamCo API win, follow with DataCo deployment automation
6. CTA: Confident, reference application + Calendly

--- FINAL OUTPUT ---

Your Series B funding signals an exciting growth phase—and also a critical challenge: the API latency issues causing customer churn won't scale without immediate intervention. At StreamCo, I faced the identical problem: 800ms p99 latencies driving churn across our enterprise tier.

I led a 6-month platform modernization that reduced API latency by 85% (800ms to 120ms p99) and recovered $2M in at-risk ARR. The solution combined edge caching, database query optimization, and strategic microservices decomposition—proven techniques that directly address your stated pain points. Additionally, at DataCo, I automated deployments (reducing cycle time from 4 hours to 15 minutes), which would solve your current 3-hour deployment bottleneck.

Your roadmap requires both performance optimization AND deployment velocity. My track record demonstrates I can deliver both simultaneously, critical as you scale post-funding. I have applied for this role. Let's discuss how my experience maps to your specific challenges: https://calendly.com/taimooralam/15min

[Word count: 156] [Metrics: 2] [Pain points referenced: 2] [Generic phrases: 0]
"""
```

**4. Tighter Validation**:
```python
def validate_cover_letter_v2(text: str, state: JobState) -> None:
    """
    V2 validation with stricter pain point mapping:

    NEW GATES:
    1. Must reference ≥2 pain points by semantic similarity (not just keyword match)
    2. Must cite ≥2 distinct metrics (deduped)
    3. Must reference ≥1 company signal by type (funding/launch/acquisition)
    4. Zero generic phrases allowed (down from 2)
    5. Must include STAR company name + metric in same sentence
    """
    errors = []

    # Gate 1: Semantic pain point matching (improved from keyword overlap)
    pain_points = state.get("pain_points") or []
    pain_matches = 0
    for pain in pain_points:
        # Extract key terms (nouns/verbs) from pain point
        pain_keywords = extract_key_terms(pain)  # New helper function
        # Check if ≥50% of key terms appear in cover letter
        match_ratio = sum(1 for kw in pain_keywords if kw in text.lower()) / len(pain_keywords)
        if match_ratio >= 0.5:
            pain_matches += 1

    if pain_matches < 2:
        errors.append(f"Must reference at least 2 pain points semantically. Found {pain_matches}/2")

    # Gate 2: Company + metric co-occurrence
    star_companies = extract_star_companies(state)
    metric_patterns = [r'\d+%', r'\d+x', r'\$\d+[KMB]', r'\d+\s*min']

    company_metric_pairs = 0
    for company in star_companies:
        # Find sentences containing company name
        sentences = extract_sentences_with_keyword(text, company)
        for sent in sentences:
            if any(re.search(pattern, sent) for pattern in metric_patterns):
                company_metric_pairs += 1
                break

    if company_metric_pairs < 1:
        errors.append("Must cite at least one metric in the same sentence as a company name")

    # Gate 3: Signal type reference
    company_research = state.get("company_research") or {}
    signals = company_research.get("signals") or []
    signal_types = {s['type'] for s in signals}

    signal_type_keywords = {
        'funding': ['funding', 'raised', 'series', 'investment'],
        'product_launch': ['launch', 'launched', 'product', 'released'],
        'acquisition': ['acquired', 'acquisition', 'merger'],
        'growth': ['growth', 'expansion', 'scaling']
    }

    signal_referenced = False
    for sig_type in signal_types:
        keywords = signal_type_keywords.get(sig_type, [])
        if any(kw in text.lower() for kw in keywords):
            signal_referenced = True
            break

    if signals and not signal_referenced:
        errors.append(f"Must reference company context. Available signals: {', '.join(signal_types)}")

    # Gate 4: Zero generic phrases
    generic_count = sum(1 for phrase in GENERIC_BOILERPLATE_PHRASES if phrase in text.lower())
    if generic_count > 0:
        errors.append(f"Generic phrases detected ({generic_count}). Rewrite without: {GENERIC_BOILERPLATE_PHRASES[:5]}")

    if errors:
        raise ValueError("\n".join(errors))
```

---

### Layer 6b - CV Generator Improvements

#### Major Overhaul Strategy

**Current Pain Points**:
1. Master CV interpretation is opaque (regex extraction)
2. STAR selection is algorithmic (no semantic understanding)
3. No role-specific nuance or emphasis shifting
4. Professional summary is templated

**New Approach**: LLM-Driven Master CV Parsing + Role-Specific Emphasis

#### 1. Master CV Interpretation Prompts

**New Helper: Master CV Parser**:
```python
class MasterCVParser:
    """
    LLM-driven parser to extract structured data from master-cv.md.

    Outputs:
    - Header (name, contact, title)
    - Profile summary
    - Core skills (categorized)
    - Experience entries (structured per role)
    - Education & certifications
    """

    SYSTEM_PROMPT = """You are a CV data extractor.

    Your task: Parse a master CV markdown file into structured JSON.

    CRITICAL RULES:
    - Extract EXACTLY as written (no rewording)
    - Preserve all metrics, dates, company names
    - If a section is missing, use empty array/null
    - Do NOT invent any information

    Output JSON schema:
    {
      "header": {
        "name": "string",
        "title": "string",
        "contact": {"email": "string", "phone": "string", "linkedin": "string"},
        "location": "string",
        "languages": ["string"]
      },
      "profile_summary": "string (2-3 sentences)",
      "core_skills": {
        "leadership": ["string"],
        "technical": ["string"],
        "domain": ["string"]
      },
      "experience": [
        {
          "role": "string",
          "company": "string",
          "period": "string",
          "achievements": ["string (one bullet = one achievement)"]
        }
      ],
      "education": ["string"]
    }
    """

    def parse_master_cv(self, cv_text: str) -> MasterCVStructure:
        """Parse master CV into structured format."""
        # LLM call with schema validation
        ...
```

#### 2. Role-Specific Emphasis Prompts

**New: CV Tailoring Strategist**:
```python
SYSTEM_PROMPT_CV_TAILORING = """You are a CV tailoring strategist.

Your task: Given a job's competency mix and a candidate's experience, determine HOW to emphasize different aspects of the same achievements for maximum impact.

COMPETENCY MIX (from job analysis):
- Delivery: {delivery}%
- Process: {process}%
- Architecture: {architecture}%
- Leadership: {leadership}%

EXAMPLE:
If job is 60% architecture, 20% delivery, 10% process, 10% leadership:

SAME ACHIEVEMENT, DIFFERENT EMPHASIS:

Original (master CV):
"Led migration from monolith to microservices, reducing deployment time from 4h to 15min and enabling 10x team scaling"

Architecture-Heavy Role (60%):
"Architected event-driven microservices decomposition of legacy monolith, establishing patterns for bounded contexts, API contracts, and eventual consistency that enabled 10x team scaling"

Delivery-Heavy Role (60%):
"Delivered monolith-to-microservices migration ahead of schedule, unblocking 15 product features and accelerating deployment cycles from 4h to 15min"

Leadership-Heavy Role (60%):
"Led cross-functional migration team (12 engineers) through monolith decomposition, mentoring on microservices patterns and enabling 10x team scaling through improved architecture"

YOUR OUTPUT FORMAT:
For each selected achievement:
{
  "original_text": "from master CV",
  "tailored_text": "reframed for this role's competency mix",
  "emphasis_rationale": "why this framing works"
}
"""

USER_PROMPT_CV_TAILORING = """Tailor these achievements for the target role:

TARGET ROLE COMPETENCY MIX:
{competency_mix}

SELECTED ACHIEVEMENTS (from master CV):
{achievements}

For each achievement, reframe to emphasize the dominant competency dimension(s).
Output JSON array of tailored achievements.
"""
```

#### 3. Enhanced Professional Summary Generator

**New: Role-Specific Summary Builder**:
```python
SYSTEM_PROMPT_PROFESSIONAL_SUMMARY = """You are an executive career marketer specializing in opening statements.

Your task: Craft a 2-3 sentence professional summary that:
1. Leads with the candidate's superpower matching the role's top competency
2. Includes 1-2 quantified highlights from STARs
3. Signals cultural fit based on company signals

ANTI-PATTERNS (never use):
- "Seasoned professional" (vague)
- "Proven track record" (cliché)
- "Strong background" (generic)

PATTERN TO FOLLOW:
"[Specific expertise] leader who [quantified achievement] at [notable company/context]. Expertise in [top 2 skills from job] with [specific outcome metric]."

EXAMPLE:
Bad: "Seasoned software architect with proven track record in scaling systems."

Good: "Infrastructure architect who reduced AWS costs by $2M/year while scaling throughput 10x at a Series B SaaS platform. Specializes in event-driven microservices and cloud-native architecture, with 15+ production migrations from monolith to distributed systems."
```

#### 4. Hallucination QA Improvements

**Stricter Hallucination Detection**:
```python
SYSTEM_PROMPT_HALLUCINATION_QA_V2 = """You are a forensic CV auditor detecting fabrications.

Your job: Verify EVERY factual claim in the CV matches the source master CV.

VERIFICATION CHECKLIST:
1. Employers: Every company name must appear in master CV (exact match or obvious abbreviation)
2. Dates: Employment periods must match master CV (allow formatting but not different years)
3. Metrics: Every number must trace to master CV (no invented percentages/amounts)
4. Achievements: Every accomplishment must be in master CV (no paraphrasing that changes meaning)
5. Skills: Every skill listed must be evidenced in master CV experience

IMPORTANT DISTINCTIONS:
✅ ACCEPTABLE: Reformatting dates (2020-2023 → 2020–2023)
✅ ACCEPTABLE: Company abbreviations (Seven.One Entertainment Group → Seven.One)
✅ ACCEPTABLE: Reordering bullets from same experience entry
❌ FABRICATION: Different companies than in master CV
❌ FABRICATION: Different date ranges (2020-2023 when master CV says 2021-2023)
❌ FABRICATION: Different metrics (75% when master CV says 60%)
❌ FABRICATION: Combining metrics from different roles without context

OUTPUT FORMAT:
{
  "is_valid": boolean,
  "issues": [
    {
      "type": "fabricated_employer" | "fabricated_date" | "fabricated_metric" | "fabricated_achievement",
      "claim": "text from CV",
      "master_cv_evidence": "what master CV actually says or null if not found",
      "severity": "critical" | "major" | "minor"
    }
  ],
  "confidence": "high" | "medium" | "low"
}

ONLY flag SUBSTANTIVE issues. Do not flag formatting variations.
"""
```

#### 5. Implementation Phases for CV Generator

**Phase 1: Master CV Parsing** (2-3 days)
- Implement `MasterCVParser` class
- Write tests for extraction accuracy
- Validate against current master-cv.md

**Phase 2: Role-Specific Emphasis** (3-4 days)
- Implement CV tailoring strategist
- Create few-shot examples per competency mix
- A/B test tailored vs. original phrasing

**Phase 3: Enhanced Summary Generation** (1-2 days)
- Rewrite professional summary prompt
- Add few-shot examples
- Test against 10 sample job profiles

**Phase 4: Stricter Hallucination QA** (2-3 days)
- Upgrade validation logic
- Add severity scoring
- Implement retry logic for critical issues

---

## C. Testing Strategy (TDD Approach)

### Test-First Development Process

For each prompt improvement, follow this sequence:

1. **Write Failing Tests First**
2. **Implement Prompt Changes**
3. **Verify Tests Pass**
4. **Add Regression Tests**

### Layer 4 - Opportunity Mapper Tests

**File**: `tests/unit/test_layer4_opportunity_mapper_v2.py`

```python
"""
Unit tests for V2 opportunity mapper prompts.
"""

class TestOpportunityMapperV2:

    def test_rationale_cites_star_by_company_name(self):
        """Rationale must cite at least one STAR by company name."""
        state = {
            "selected_stars": [{"company": "StreamCo", "results": "Reduced latency 85%"}],
            "pain_points": ["API latency issues"],
            # ... other fields
        }

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(state)

        # Assert: rationale contains "StreamCo"
        assert "streamco" in result["fit_rationale"].lower()

    def test_rationale_references_specific_pain_point(self):
        """Rationale must reference at least one pain point by key terms."""
        state = {
            "pain_points": ["API latency >500ms causing churn"],
            # ... other fields
        }

        mapper = OpportunityMapper()
        result = mapper.map_opportunity(state)

        # Assert: rationale contains "latency" or "api" or "churn"
        rationale_lower = result["fit_rationale"].lower()
        assert any(term in rationale_lower for term in ["latency", "api", "churn"])

    def test_rationale_minimum_length_50_words(self):
        """Rationale must be at least 50 words for substantive analysis."""
        # ... test implementation

    def test_validation_rejects_generic_rationale(self):
        """Validation must reject rationales with >1 generic phrase."""
        generic_rationale = "Candidate has strong background and is a team player with proven track record."

        with pytest.raises(ValueError, match="generic"):
            mapper._validate_rationale_v2(generic_rationale, ...)

    def test_few_shot_example_improves_quality(self):
        """Test that domain-specific few-shot examples improve output quality."""
        # Run with few-shot vs without, compare generic phrase count
        ...
```

### Layer 6a - Cover Letter Generator Tests

**File**: `tests/unit/test_layer6_cover_letter_generator_v2.py`

```python
class TestCoverLetterGeneratorV2:

    def test_references_at_least_two_pain_points(self):
        """Cover letter must reference ≥2 pain points semantically."""
        state = {
            "pain_points": [
                "API latency causing churn",
                "Manual deployment taking 3 hours",
                "No infrastructure as code"
            ],
            # ... other fields
        }

        generator = CoverLetterGenerator()
        cover_letter = generator.generate_cover_letter(state)

        # Assert: At least 2 pain points referenced by key terms
        pain_matches = count_pain_point_references(cover_letter, state["pain_points"])
        assert pain_matches >= 2

    def test_cites_company_and_metric_in_same_sentence(self):
        """Must cite company name + metric in same sentence for grounding."""
        state = {
            "selected_stars": [
                {"company": "StreamCo", "results": "Reduced latency 85%"}
            ],
            # ... other fields
        }

        generator = CoverLetterGenerator()
        cover_letter = generator.generate_cover_letter(state)

        # Assert: "StreamCo" and "85%" appear in same sentence
        sentences = extract_sentences(cover_letter)
        has_grounded_claim = any(
            "streamco" in s.lower() and "85%" in s
            for s in sentences
        )
        assert has_grounded_claim

    def test_references_company_signal_by_type(self):
        """Must reference at least one company signal (funding/launch/etc)."""
        state = {
            "company_research": {
                "signals": [
                    {"type": "funding", "description": "Raised $50M Series B"}
                ]
            },
            # ... other fields
        }

        generator = CoverLetterGenerator()
        cover_letter = generator.generate_cover_letter(state)

        # Assert: Contains funding-related keywords
        funding_keywords = ["funding", "raised", "series", "investment"]
        assert any(kw in cover_letter.lower() for kw in funding_keywords)

    def test_zero_generic_phrases_allowed(self):
        """V2 validation allows zero generic phrases (down from 2)."""
        state = create_sample_state()

        # Mock LLM to return generic letter
        with patch.object(generator.llm, 'invoke') as mock_llm:
            mock_llm.return_value.content = "I am excited to apply for this perfect fit role..."

            with pytest.raises(ValueError, match="Generic phrases detected"):
                generator.generate_cover_letter(state)

    def test_planning_phase_improves_structure(self):
        """Test that structured planning reduces validation failures."""
        # Run 10 generations, track validation pass rate with vs without planning phase
        ...
```

### Layer 6b - CV Generator Tests

**File**: `tests/unit/test_layer6_cv_generator_v2.py`

```python
class TestCVGeneratorV2:

    def test_master_cv_parser_extracts_all_sections(self):
        """Master CV parser must extract all sections without loss."""
        parser = MasterCVParser()
        parsed = parser.parse_master_cv(SAMPLE_MASTER_CV)

        assert parsed.header.name
        assert parsed.profile_summary
        assert len(parsed.experience) > 0
        assert len(parsed.education) > 0

    def test_master_cv_parser_preserves_metrics(self):
        """Parser must preserve all metrics exactly as written."""
        cv_with_metrics = """
        ### Experience
        At CompanyX, reduced costs by 75% and improved velocity 10x.
        """

        parser = MasterCVParser()
        parsed = parser.parse_master_cv(cv_with_metrics)

        achievements_text = " ".join(parsed.experience[0].achievements)
        assert "75%" in achievements_text
        assert "10x" in achievements_text

    def test_cv_tailoring_emphasizes_dominant_competency(self):
        """Tailored achievements must emphasize dominant competency dimension."""
        competency_mix = {"delivery": 20, "architecture": 60, "process": 10, "leadership": 10}
        achievement = "Led migration to microservices, reducing deploy time 4h to 15min"

        tailored = cv_generator.tailor_achievement(achievement, competency_mix)

        # Assert: Tailored version emphasizes architecture (pattern, design, structure)
        architecture_keywords = ["architect", "pattern", "design", "structure", "bounded context"]
        assert any(kw in tailored.lower() for kw in architecture_keywords)

    def test_professional_summary_includes_quantified_highlight(self):
        """Professional summary must include ≥1 quantified highlight."""
        state = {
            "selected_stars": [
                {"company": "StreamCo", "results": "Reduced costs $2M/year"}
            ],
            # ... other fields
        }

        summary = cv_generator.generate_professional_summary(state, competency_mix)

        # Assert: Contains a metric
        metric_patterns = [r'\$\d+M', r'\d+%', r'\d+x']
        assert any(re.search(pattern, summary) for pattern in metric_patterns)

    def test_hallucination_qa_detects_fabricated_company(self):
        """Hallucination QA must catch companies not in master CV."""
        master_cv = "Experience: StreamCo (2020-2023)"
        generated_cv = "Experience: FakeCorp (2018-2020)"  # Not in master CV

        qa_result = cv_generator._run_hallucination_qa(generated_cv, master_cv)

        assert not qa_result.is_valid
        assert any(issue.type == "fabricated_employer" for issue in qa_result.issues)

    def test_hallucination_qa_allows_formatting_variations(self):
        """QA should allow date format variations (2020-2023 vs 2020–2023)."""
        master_cv = "Experience: StreamCo (2020-2023)"
        generated_cv = "Experience: StreamCo (2020–2023)"  # Em-dash instead of hyphen

        qa_result = cv_generator._run_hallucination_qa(generated_cv, master_cv)

        assert qa_result.is_valid

    def test_hallucination_qa_detects_metric_inflation(self):
        """QA must catch inflated metrics (75% claimed when master CV says 60%)."""
        master_cv = "Reduced incidents by 60%"
        generated_cv = "Reduced incidents by 75%"  # Inflated

        qa_result = cv_generator._run_hallucination_qa(generated_cv, master_cv)

        assert not qa_result.is_valid
        assert any(issue.type == "fabricated_metric" for issue in qa_result.issues)
```

### Integration Tests

**File**: `tests/integration/test_prompt_improvements_e2e.py`

```python
"""
End-to-end tests for prompt improvements across layers.
"""

class TestPromptImprovementsE2E:

    def test_full_pipeline_quality_gates(self):
        """Run full pipeline and validate all quality gates pass."""
        job_state = create_sample_job_state()

        # Run pipeline
        result = run_pipeline(job_state)

        # Layer 4: Opportunity Mapper
        assert result["fit_rationale"]  # Contains STAR citation
        assert len(result["fit_rationale"].split()) >= 50  # Min 50 words

        # Layer 6a: Cover Letter
        assert count_generic_phrases(result["cover_letter"]) == 0
        assert count_pain_point_references(result["cover_letter"], job_state["pain_points"]) >= 2

        # Layer 6b: CV
        assert result["cv_path"]
        qa_result = validate_cv_against_master_cv(result["cv_path"], MASTER_CV_PATH)
        assert qa_result.is_valid

    def test_prompt_consistency_across_domains(self):
        """Test that prompts work across different job domains."""
        domains = ["tech_saas", "fintech", "healthcare", "transportation"]

        for domain in domains:
            job_state = create_sample_job_state(domain=domain)
            result = run_pipeline(job_state)

            # All quality gates must pass regardless of domain
            assert result["fit_score"] is not None
            assert validate_cover_letter_v2(result["cover_letter"], job_state)
```

### Test Data Fixtures

**File**: `tests/fixtures/sample_jobs.py`

```python
"""
Sample job descriptions and expected outputs for testing.
"""

SAMPLE_JOBS = {
    "tech_saas_backend_engineer": {
        "title": "Senior Backend Engineer",
        "company": "StreamCo",
        "job_description": """
        Build scalable API platform for 10M users.

        Must have:
        - Microservices architecture
        - Kubernetes expertise
        - High-throughput systems

        You'll own:
        - Service reliability
        - Monolith migration
        - Team technical standards
        """,
        "expected_pain_points": [
            "API platform cannot handle traffic growth",
            "Monolithic architecture blocking feature velocity"
        ],
        "expected_fit_score_range": (80, 95)  # For matching candidate
    },

    "fintech_payments_architect": {
        # ... similar structure
    }
}
```

---

## D. Implementation Roadmap

### Phase 1: Test Infrastructure (Week 1)

**Goal**: Set up comprehensive test suite before changing any prompts

**Tasks**:
1. Create test data fixtures for all domains (tech SaaS, fintech, healthcare, etc.)
2. Write failing tests for new validation rules:
   - Layer 4: STAR citation, pain point reference, 50-word minimum
   - Layer 6a: Zero generic phrases, company+metric co-occurrence, 2+ pain points
   - Layer 6b: Master CV parsing, hallucination QA strictness
3. Implement test helpers:
   - `count_pain_point_references(text, pain_points)`
   - `extract_sentences_with_keyword(text, keyword)`
   - `extract_star_companies(state)`
   - `count_generic_phrases(text)`

**Success Criteria**:
- 30+ new tests written (10 per layer)
- All tests failing (expected - prompts not yet updated)
- Test coverage >80% for prompt-related code

**Deliverables**:
- `tests/unit/test_layer4_opportunity_mapper_v2.py`
- `tests/unit/test_layer6_cover_letter_generator_v2.py`
- `tests/unit/test_layer6_cv_generator_v2.py`
- `tests/fixtures/sample_jobs.py`
- `tests/helpers/validation_helpers.py`

---

### Phase 2: Layer 4 - Opportunity Mapper (Week 2)

**Goal**: Implement structured reasoning framework and stricter validation

**Tasks**:
1. Update prompts:
   - New persona with "senior executive recruiter" framing
   - 4-step reasoning framework (pain mapping → gap analysis → strategic alignment → scoring)
   - Few-shot examples (one per domain)
2. Update validation:
   - Implement `_validate_rationale_v2()` with 5 gates
   - Require STAR citation, pain point reference, 50-word minimum
   - Allow only 1 generic phrase (down from 2)
3. A/B testing:
   - Run 20 sample jobs through old vs new prompts
   - Measure: generic phrase count, STAR citation rate, validation pass rate
4. Regression testing:
   - Ensure fit scores remain stable (±5 points)
   - Verify no performance degradation

**Success Criteria**:
- All V2 tests passing
- Generic phrase rate reduced by >50%
- STAR citation rate >90%
- Validation pass rate >80%

**Deliverables**:
- Updated `src/layer4/opportunity_mapper.py` with V2 prompts
- A/B test results report (`reports/layer4-prompt-improvement-results.md`)
- Updated unit tests

---

### Phase 3: Layer 6a - Cover Letter Generator (Week 3)

**Goal**: Implement structured planning phase and tighter validation

**Tasks**:
1. Update prompts:
   - Dual persona (career marketer + skeptical hiring manager)
   - 4-phase process (planning → drafting → self-critique → final output)
   - Few-shot example with planning notes
2. Update validation:
   - Implement `validate_cover_letter_v2()` with 6 gates
   - Semantic pain point matching (key term extraction)
   - Company + metric co-occurrence check
   - Zero generic phrases allowed
3. Implement helper functions:
   - `extract_key_terms(pain_point)` for semantic matching
   - `extract_sentences_with_keyword(text, keyword)` for validation
4. A/B testing:
   - Run 30 sample jobs through old vs new prompts
   - Measure: generic phrases, pain point references, validation failures, retry count

**Success Criteria**:
- All V2 tests passing
- Generic phrase rate reduced to 0%
- Pain point reference rate >95% (2+ per letter)
- Validation pass rate >75% (reduced retries)

**Deliverables**:
- Updated `src/layer6/cover_letter_generator.py` with V2 prompts
- Helper functions in `src/common/validation_helpers.py`
- A/B test results report

---

### Phase 4: Layer 6b - CV Generator Overhaul (Weeks 4-5)

**Goal**: Implement LLM-driven master CV parsing and role-specific emphasis

**Subphase 4.1: Master CV Parser** (Week 4)

**Tasks**:
1. Implement `MasterCVParser` class:
   - System prompt for structured extraction
   - Pydantic schema for validation (`MasterCVStructure`)
   - Tests for extraction accuracy
2. Update CV generator to use parsed structure:
   - Replace regex extraction with `parser.parse_master_cv()`
   - Validate all sections present
3. Add tests:
   - Test extraction accuracy on current master-cv.md
   - Test metric preservation
   - Test handling of missing sections

**Success Criteria**:
- Parser extracts all sections from master-cv.md
- Zero metric loss (100% preservation)
- All extraction tests passing

**Subphase 4.2: Role-Specific Emphasis** (Week 5, Days 1-3)

**Tasks**:
1. Implement `CVTailoringStrategist` class:
   - System prompt for achievement reframing
   - Few-shot examples per competency mix
   - Integration with CV generator pipeline
2. Update `generate_cv()` to use tailoring:
   - After STAR selection, tailor each achievement
   - Pass competency mix to tailoring prompt
3. Add tests:
   - Test emphasis shift for different competency mixes
   - Validate metrics unchanged (no inflation)

**Success Criteria**:
- Tailored achievements emphasize dominant competency
- Original metrics preserved exactly
- 10+ tailoring examples tested

**Subphase 4.3: Enhanced Summary & QA** (Week 5, Days 4-5)

**Tasks**:
1. Rewrite professional summary prompt:
   - Role-specific framing based on top competency
   - Include 1-2 quantified highlights
   - Signal cultural fit with company signals
2. Upgrade hallucination QA:
   - Implement `SYSTEM_PROMPT_HALLUCINATION_QA_V2`
   - Add severity scoring (critical/major/minor)
   - Implement retry logic for critical issues
3. Add tests:
   - Summary includes metrics
   - QA catches fabricated companies/dates/metrics
   - QA allows formatting variations

**Success Criteria**:
- 100% of summaries include quantified highlight
- Hallucination detection rate >95%
- False positive rate <5% (formatting variations allowed)

**Deliverables**:
- Updated `src/layer6/cv_generator.py` with all V2 components
- New `src/common/cv_parser.py` with `MasterCVParser`
- A/B test results report
- Updated unit tests

---

### Phase 5: Integration Testing & Validation (Week 6)

**Goal**: Ensure all layers work together, no regressions

**Tasks**:
1. Run full pipeline on 50 diverse jobs:
   - 10 tech SaaS
   - 10 fintech
   - 10 healthcare
   - 10 transportation
   - 10 general/consulting
2. Measure quality metrics:
   - Fit rationale: STAR citation rate, generic phrase count, validation pass rate
   - Cover letter: Pain point references, generic phrases, validation failures
   - CV: Hallucination QA pass rate, metric preservation, tailoring quality
3. Regression testing:
   - Compare outputs to Phase 1 baseline
   - Ensure no quality degradation
   - Verify performance (latency, cost)
4. User acceptance testing:
   - Generate 5 real applications
   - Manually review quality
   - Collect feedback

**Success Criteria**:
- All integration tests passing
- Quality metrics meet targets:
  - Fit rationale: >90% STAR citation, <10% generic phrases
  - Cover letter: >95% pain point references, 0% generic phrases
  - CV: >95% hallucination QA pass rate
- No performance regressions (latency within 10% of baseline)

**Deliverables**:
- Integration test suite (`tests/integration/test_prompt_improvements_e2e.py`)
- Quality metrics report (`reports/prompt-optimization-final-results.md`)
- User acceptance test results

---

### Phase 6: Documentation & Rollout (Week 7)

**Goal**: Document changes, update guides, deploy to production

**Tasks**:
1. Update documentation:
   - Update `missing.md` to mark prompt improvements complete
   - Add section to `architecture.md` on prompt design principles
   - Create `docs/prompt-engineering-guide.md` with best practices
2. Create migration guide:
   - How to rollback if issues arise
   - Feature flags for gradual rollout
   - Monitoring dashboards for quality metrics
3. Deploy to production:
   - Gradual rollout (10% → 50% → 100% of jobs)
   - Monitor quality metrics via LangSmith
   - Alert on validation failure rate spikes
4. Training materials:
   - Record demo video showing improvements
   - Update onboarding docs for future prompt changes

**Success Criteria**:
- All documentation updated
- Smooth production deployment
- Zero critical bugs reported in first week
- Quality metrics stable in production

**Deliverables**:
- Updated `missing.md`, `architecture.md`
- New `docs/prompt-engineering-guide.md`
- Migration guide in `plans/prompt-rollout-plan.md`
- Demo video

---

## E. Agent Delegation Plan

### Recommended Agent Sequence

**Phase 1: Test Infrastructure**
- **Agent**: `test-generator`
- **Task**: Write comprehensive test suite for all 3 layers
- **Handoff**: Test files + fixtures ready for development

**Phase 2-4: Implementation**
- **Agent**: Main Claude (architecture-aware)
- **Rationale**: Prompt changes require understanding of full system context
- **Support**: `architecture-debugger` on standby for integration issues

**Phase 5: Integration Testing**
- **Agent**: `test-generator` or `pipeline-analyst`
- **Task**: Run full pipeline tests, collect quality metrics
- **Handoff**: Quality report for review

**Phase 6: Documentation**
- **Agent**: `doc-sync`
- **Task**: Update all documentation, mark items complete in missing.md
- **Handoff**: Updated docs ready for review

### Handoff Points

**After Phase 1 (Tests Ready)**:
> "Test infrastructure complete. 30+ tests written covering Layer 4/6a/6b validation. All tests currently failing (expected). Recommend using **main Claude** for implementation phases 2-4 to maintain system context."

**After Phase 4 (Implementation Complete)**:
> "All prompt improvements implemented and unit tests passing. Ready for integration testing. Recommend using **pipeline-analyst** to run full pipeline on 50 diverse jobs and collect quality metrics."

**After Phase 5 (Testing Complete)**:
> "Integration testing complete. Quality metrics meet all targets. Ready for documentation phase. Recommend using **doc-sync** to update missing.md, architecture.md, and create prompt engineering guide."

---

## F. Success Metrics

### Quantitative Targets

**Layer 4 - Opportunity Mapper**:
| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| STAR citation rate | ~40% | >90% | % of rationales citing STAR by company name |
| Generic phrase count | 1.5 avg | <0.5 avg | Avg generic phrases per rationale |
| Validation pass rate | ~60% | >80% | % of first attempts passing validation |
| Rationale length | 30 words avg | 60 words avg | Avg word count per rationale |

**Layer 6a - Cover Letter Generator**:
| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Generic phrase count | 2.0 avg | 0 | Zero tolerance for generic phrases |
| Pain point references | 1.2 avg | 2.5 avg | Avg pain points referenced per letter |
| Company signal mentions | ~30% | >80% | % of letters mentioning company signal |
| Validation pass rate | ~50% | >75% | % of first attempts passing validation |
| Retry count | 1.5 avg | <1.0 avg | Avg retries per letter generation |

**Layer 6b - CV Generator**:
| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Hallucination QA pass rate | ~85% | >95% | % of CVs passing QA without issues |
| Metric preservation | ~95% | 100% | % of metrics extracted exactly from master CV |
| Role-specific tailoring | N/A (new) | >80% | % of achievements emphasizing dominant competency |
| Professional summary quality | N/A | >90% | % of summaries including quantified highlight |

### Qualitative Targets

**Fit Analysis**:
- Rationales are specific and evidence-based
- Clear mapping of achievements to pain points
- Transparent about gaps and how to mitigate

**Cover Letters**:
- Opening hooks are specific to company/role
- Achievements tied directly to pain points
- Company context woven naturally into narrative

**CVs**:
- Tailored achievements emphasize role-relevant competencies
- Professional summary compelling and specific
- Zero fabricated information

### Cost/Performance Considerations

**Prompt Length Impact**:
- Longer prompts (with reasoning, few-shot) may increase:
  - **Latency**: +20-30% per LLM call (acceptable)
  - **Cost**: +30-40% per job (mitigated by better quality = fewer retries)

**Expected ROI**:
- Better quality = fewer manual edits
- Fewer validation failures = fewer retries = net cost neutral or savings
- Higher interview rate from better applications = significant value

---

## G. Risk Mitigation

### Risk 1: Regression in Output Quality

**Probability**: Medium
**Impact**: High

**Mitigation**:
- Comprehensive test suite catches regressions early
- A/B testing validates improvements before full rollout
- Feature flags allow instant rollback
- Manual review of first 10 outputs per layer

### Risk 2: Increased LLM Costs

**Probability**: Medium
**Impact**: Low

**Mitigation**:
- Longer prompts offset by fewer retries (validation failures)
- Monitor cost per job in LangSmith
- Set alerts if cost exceeds baseline by >50%
- Can reduce few-shot examples if needed

### Risk 3: Test Suite Maintenance Burden

**Probability**: Low
**Impact**: Medium

**Mitigation**:
- Tests are well-documented and modular
- Test helpers reduce duplication
- CI/CD runs tests automatically
- Quarterly review to prune outdated tests

### Risk 4: Prompt Drift Over Time

**Probability**: Medium
**Impact**: Medium

**Mitigation**:
- Document prompt design principles in `docs/prompt-engineering-guide.md`
- Version control all prompts
- Regular quality audits (monthly)
- LangSmith traces for debugging

### Risk 5: Integration Issues Between Layers

**Probability**: Low
**Impact**: High

**Mitigation**:
- Integration tests run full pipeline
- `architecture-debugger` agent on standby
- Incremental rollout allows early detection
- Detailed logging at layer boundaries

---

## H. Key Files Modified

### Core Implementation Files

| File | Changes | Lines Added | Risk Level |
|------|---------|-------------|------------|
| `src/layer4/opportunity_mapper.py` | New prompts, validation v2 | ~200 | Medium |
| `src/layer6/cover_letter_generator.py` | New prompts, validation v2, helpers | ~300 | Medium |
| `src/layer6/cv_generator.py` | Master CV parser integration, tailoring, QA v2 | ~400 | High |
| `src/common/cv_parser.py` | New file - master CV parser | ~250 | Medium |
| `src/common/validation_helpers.py` | New file - shared validation functions | ~150 | Low |

### Test Files

| File | Purpose | Lines Added |
|------|---------|-------------|
| `tests/unit/test_layer4_opportunity_mapper_v2.py` | Layer 4 prompt validation | ~300 |
| `tests/unit/test_layer6_cover_letter_generator_v2.py` | Layer 6a prompt validation | ~400 |
| `tests/unit/test_layer6_cv_generator_v2.py` | Layer 6b prompt validation | ~500 |
| `tests/integration/test_prompt_improvements_e2e.py` | Full pipeline quality gates | ~200 |
| `tests/fixtures/sample_jobs.py` | Test data for all domains | ~400 |
| `tests/helpers/validation_helpers.py` | Shared test utilities | ~200 |

### Documentation Files

| File | Changes | Purpose |
|------|---------|---------|
| `missing.md` | Mark items #4, #5, #6 complete | Tracking |
| `architecture.md` | Add prompt design principles section | Reference |
| `docs/prompt-engineering-guide.md` | New file - best practices guide | Training |
| `plans/prompt-rollout-plan.md` | New file - deployment strategy | Ops |
| `reports/prompt-optimization-final-results.md` | New file - quality metrics report | Validation |

**Total Estimated Changes**: ~3,500 lines of code/tests/docs

---

## I. Effort Estimation

### Development Time

| Phase | Duration | Developer Days | Notes |
|-------|----------|----------------|-------|
| Phase 1: Test Infrastructure | 1 week | 3 days | Front-load test creation |
| Phase 2: Layer 4 (Opportunity Mapper) | 1 week | 4 days | Includes A/B testing |
| Phase 3: Layer 6a (Cover Letter) | 1 week | 4 days | Includes validation helpers |
| Phase 4: Layer 6b (CV Generator) | 2 weeks | 8 days | Most complex, 3 subphases |
| Phase 5: Integration Testing | 1 week | 3 days | Run 50+ jobs, collect metrics |
| Phase 6: Documentation & Rollout | 1 week | 2 days | Update docs, deploy |

**Total**: 7 weeks calendar time, 24 developer days

### Assumptions

- 1 developer working full-time (40 hours/week)
- Agent delegation reduces manual effort by ~30%
- Includes time for testing, iteration, documentation
- Excludes user acceptance testing (can run in parallel)

### Calendar Schedule (Optimistic)

- **Week 1**: Test infrastructure
- **Week 2**: Layer 4 implementation
- **Week 3**: Layer 6a implementation
- **Weeks 4-5**: Layer 6b implementation (major overhaul)
- **Week 6**: Integration testing
- **Week 7**: Documentation & rollout

**Critical Path**: Layer 6b (CV Generator) is the bottleneck due to complexity.

---

## J. Appendix: Prompt Engineering Best Practices

### Universal Principles (from `thoughts/prompt-generation-guide.md`)

1. **Persona First**: Always start with "You are..." to set expertise level
2. **Context Structured**: Use labeled sections (=== HEADING ===) not narrative
3. **Reasoning Required**: Add chain-of-thought instructions ("Before answering, think through...")
4. **Format Explicit**: Specify exact output format (JSON schema, word count, structure)
5. **Examples Included**: Few-shot examples dramatically improve consistency
6. **Anti-Hallucination**: "Only use facts from provided context" + "If unsure, say 'Unknown'"
7. **Self-Evaluation**: "Score your output 1-10 on clarity/accuracy/completeness; if <9, revise"

### Layer-Specific Tips

**Layer 4 (Opportunity Mapper)**:
- Frame as recruiter/consultant, not generic AI
- Require structured reasoning (pain mapping → gaps → alignment → score)
- Use domain-specific few-shot examples
- Enforce STAR citations for grounding

**Layer 6a (Cover Letter)**:
- Dual persona (career marketer + skeptical hiring manager)
- 4-phase process (plan → draft → critique → finalize)
- Zero tolerance for generic phrases
- Require company+metric co-occurrence for grounding

**Layer 6b (CV Generator)**:
- LLM-driven parsing instead of regex
- Role-specific emphasis based on competency mix
- Hallucination QA with severity scoring
- Professional summary must include quantified highlight

### Validation Philosophy

**Fail Fast**: Validation should catch issues immediately, not after generation
**Specific Errors**: Error messages must explain exactly what's wrong and how to fix
**Progressive**: Start lenient, tighten over time as prompts improve
**Monitored**: Track validation pass rates in LangSmith to detect regressions

---

## K. Next Steps

### Immediate Actions (This Week)

1. **Review this plan** with stakeholders
2. **Approve scope and timeline**
3. **Create work branches**:
   - `feature/layer4-prompt-improvements`
   - `feature/layer6a-prompt-improvements`
   - `feature/layer6b-prompt-overhaul`
4. **Set up monitoring** in LangSmith for quality metrics

### Recommended First Task

**Start with Phase 1 (Test Infrastructure)** using `test-generator` agent:

> "I need comprehensive tests for prompt improvements across Layer 4 (Opportunity Mapper), Layer 6a (Cover Letter Generator), and Layer 6b (CV Generator). See `/Users/ala0001t/pers/projects/job-search/plans/prompt-optimization-plan.md` Section C for test requirements. Create failing tests that validate new quality gates before we implement prompt changes."

This ensures we're doing true TDD: tests first, implementation second.

---

## G. A/B Testing & Iterative Improvement Methodology

### Reference Documents

All prompt improvements MUST reference these foundational documents:

| Document | Purpose | Key Techniques |
|----------|---------|----------------|
| `thoughts/prompt-generation-guide.md` | Universal prompting cheat-sheet | Personas §1.1, CoT §2.1, Few-Shot §2.3, Battle-of-Bots §3.2 |
| `thoughts/prompt-modernization-blueprint.md` | Layer-specific improvement blueprint | Universal scaffold, layer-by-layer upgrades |
| `thoughts/change.md` | Vision for role-play & mentorship flow | Persona debates, critique loops |

### A/B Testing Protocol

For **EVERY issue** in each layer, follow this protocol:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    A/B TESTING CYCLE (Per Issue)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Step 1: BASELINE (Status Quo)                                      │
│  ├── Run current prompt with 3 test jobs                            │
│  ├── Capture outputs in reports/prompt-ab/baseline/                 │
│  └── Score: specificity, grounding, hallucinations (1-10)           │
│                                                                     │
│  Step 2: ENHANCED (New Prompt)                                      │
│  ├── Apply technique from thoughts/*.md                             │
│  ├── Run enhanced prompt with SAME 3 test jobs                      │
│  ├── Capture outputs in reports/prompt-ab/enhanced/                 │
│  └── Score: same metrics (1-10)                                     │
│                                                                     │
│  Step 3: ANALYZE                                                    │
│  ├── Compare side-by-side                                           │
│  ├── Calculate improvement delta                                    │
│  ├── Identify remaining weaknesses                                  │
│  └── Document in reports/prompt-ab/analysis/                        │
│                                                                     │
│  Step 4: ITERATE                                                    │
│  ├── If delta < target: refine prompt, go to Step 2                 │
│  ├── If delta >= target: mark issue RESOLVED                        │
│  └── Max 3 iterations per issue                                     │
│                                                                     │
│  Step 5: DISPLAY ANALYSIS                                           │
│  └── Output comparison table + recommendations                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Issue-by-Issue Testing Matrix

#### Layer 4 - Opportunity Mapper

| Issue | Baseline Test | Enhanced Technique | Success Metric |
|-------|---------------|-------------------|----------------|
| Weak grounding | Check for vague rationales | Anti-hallucination guardrails (§3.4) + citation enforcement | 100% of rationales cite specific STAR/metric |
| No chain-of-thought | Count reasoning steps in output | Reasoning-first (§2.2) + `<thinking>` blocks | Visible 4-step reasoning in every output |
| Generic rationales pass | Count boilerplate phrases | Constraint prompting (§3.5) + self-eval scoring | 0 generic phrases allowed |
| Context overload | Measure relevance of cited context | Context prioritization + few-shot (§2.3) | Only top-3 relevant context items cited |

#### Layer 6a - Cover Letter

| Issue | Baseline Test | Enhanced Technique | Success Metric |
|-------|---------------|-------------------|----------------|
| Rigid structure | Measure paragraph variance | Flexible format with reasoning plan (§2.2) | Accept 2-5 paragraphs based on content |
| Weak pain point integration | Check pain point → achievement mapping | Show+Ask rubric (§2.4) + explicit mapping | Every pain point addressed with evidence |
| Generic company research | Count company-specific details | Candidate-aware context + specificity scoring | Min 3 unique company facts per letter |
| STAR grounding not validated | Check if metrics come from master-cv | Battle-of-Bots critique (§3.2) | 100% of metrics traceable to master-cv |

#### Layer 6b - CV Generation

| Issue | Baseline Test | Enhanced Technique | Success Metric |
|-------|---------------|-------------------|----------------|
| Regex-based parsing | Test with edge-case CVs | LLM-driven parser with Tree-of-Thoughts (§3.1) | Parse 100% of master-cv sections correctly |
| No role-specific selection | Check achievement relevance to role | Competency mix analysis + debate mode (§5.2) | Top achievements match role requirements |
| Generic summaries | Count specific vs vague phrases | Self-consistency (§5.1) + scoring (§5.3) | 0 generic phrases, min 3 quantified claims |
| Hallucination gaps | Check facts against master-cv | Assumption ledger + source validation | 0 invented facts, all claims grounded |

### Analysis Output Format

After each issue's A/B cycle, display analysis in this format:

```markdown
## 📊 A/B Analysis: [Layer] - [Issue]

### Baseline (Status Quo)
- **Prompt Version**: v1.0
- **Test Jobs**: [job_id_1, job_id_2, job_id_3]
- **Scores**: Specificity: X/10, Grounding: X/10, Hallucinations: X/10
- **Sample Output**: [truncated example]

### Enhanced (New Prompt)
- **Prompt Version**: v2.0
- **Technique Applied**: [from thoughts/*.md]
- **Scores**: Specificity: X/10, Grounding: X/10, Hallucinations: X/10
- **Sample Output**: [truncated example]

### Comparison
| Metric | Baseline | Enhanced | Delta | Target | Status |
|--------|----------|----------|-------|--------|--------|
| Specificity | X | Y | +Z | ≥8 | ✅/❌ |
| Grounding | X | Y | +Z | ≥9 | ✅/❌ |
| Hallucinations | X | Y | -Z | ≤1 | ✅/❌ |

### Verdict
- **Improvement**: X% overall
- **Remaining Issues**: [list]
- **Next Iteration**: [yes/no + reason]
- **Recommended Technique**: [if iterating]
```

### Directory Structure for A/B Testing

```
reports/
└── prompt-ab/
    ├── layer4/
    │   ├── weak-grounding/
    │   │   ├── baseline-v1.json
    │   │   ├── enhanced-v2.json
    │   │   ├── enhanced-v3.json (if iteration needed)
    │   │   └── analysis.md
    │   ├── no-cot/
    │   ├── generic-rationales/
    │   └── context-overload/
    ├── layer6a/
    │   ├── rigid-structure/
    │   ├── weak-painpoints/
    │   ├── generic-research/
    │   └── star-grounding/
    └── layer6b/
        ├── regex-parsing/
        ├── role-selection/
        ├── generic-summaries/
        └── hallucination-gaps/
```

### Iteration Rules

1. **Max 3 iterations** per issue (avoid infinite loops)
2. **Cumulative techniques**: Each iteration adds to previous, doesn't replace
3. **Regression check**: If v3 < v2, rollback to v2
4. **Cross-issue impact**: After fixing one issue, re-test others for regression
5. **Document everything**: Every prompt version saved for reproducibility

### Final Phase Output

At the end of each layer's optimization, produce a summary report:

```markdown
# Layer X Prompt Optimization - Final Analysis

## Issues Resolved
| Issue | Iterations | Final Score | Technique Stack |
|-------|------------|-------------|-----------------|
| Issue 1 | 2 | 9.2/10 | CoT + Few-shot |
| Issue 2 | 1 | 8.8/10 | Battle-of-Bots |
| ... | ... | ... | ... |

## Aggregate Improvement
- **Baseline Average**: X.X/10
- **Final Average**: Y.Y/10
- **Total Improvement**: +Z.Z (+XX%)

## Recommended Production Rollout
- [ ] Feature flag: layer_X_enhanced_prompts
- [ ] Gradual rollout: 10% → 50% → 100%
- [ ] Monitoring: LangSmith quality dashboards

## Lessons Learned
1. [What worked well]
2. [What didn't work]
3. [Recommendations for other layers]
```

---

**End of Plan**

*This plan represents ~7 weeks of work to systematically improve prompt quality across the Job Intelligence Pipeline. The TDD approach with A/B testing ensures we measure improvements objectively, iterate based on evidence, and catch regressions early. All improvements are grounded in the prompting techniques from `thoughts/*.md`.*
