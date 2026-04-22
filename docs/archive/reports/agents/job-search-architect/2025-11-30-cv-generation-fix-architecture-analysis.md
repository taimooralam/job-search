# Architecture Analysis: CV Generation System Redesign

**Date**: 2025-11-30
**Agent**: job-search-architect
**Scope**: Comprehensive analysis of CV generation issues and proposed solutions

---

## 1. Requirements Understanding

### Critical Issues Summary

| ID | Issue | Impact | Priority | Root Cause |
|----|-------|--------|----------|------------|
| **P0-1** | Hallucinated Skills | CRITICAL - Fabricated PHP, Java, Spring Boot in Core Competencies | P0 | Hardcoded skill lists in `header_generator.py` not validated against master-cv |
| **P0-2** | Static Core Skills Categories | CRITICAL - Always 4 categories (Leadership/Technical/Platform/Delivery), not JD-derived | P0 | Hardcoded categories in `generate_skills()` method |
| **P0-3** | Missing STAR Format | HIGH - Bullets lack explicit challenge→skill→result structure | P0 | Role generation prompts don't enforce STAR structure explicitly |
| **P1-1** | No Dynamic Tagline | MEDIUM - Missing location-based relocation message | P1 | No location parsing or conditional tagline injection |
| **P1-2** | Green Color Scheme | LOW - Current teal/green (#0f766e) needs to be dark greyish blue | P1 | Hardcoded color in `app.py` and `base.html` |
| **P2-1** | CV Spacing | LOW - Needs 20% narrower spacing | P2 | CSS padding/margin settings |

### Constraints
- Master-cv data is **ground truth** - MUST NOT be modified
- All skills MUST be sourced from master-cv `roles/*.md` files (hard_skills, soft_skills sections)
- JD parsing already extracts `top_keywords`, `technical_skills`, `soft_skills`
- Frontend and PDF must have consistent styling
- No breaking changes to existing pipeline architecture

---

## 2. System Context Analysis

### Current Architecture (CV Generation V2)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CV GENERATION V2 PIPELINE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 1: CV Loader (cv_loader.py)                                     │
│  ├── Loads: data/master-cv/role_metadata.json                          │
│  ├── Loads: data/master-cv/roles/*.md                                  │
│  ├── Parses: achievements, hard_skills, soft_skills per role           │
│  └── Returns: CandidateData with List[RoleData]                        │
│                                                                          │
│  Phase 2: Per-Role Generator (role_generator.py)                       │
│  ├── Input: RoleData + extracted_jd                                    │
│  ├── Generates: Tailored bullets for each role                         │
│  └── Returns: List[RoleBullets]                                        │
│                                                                          │
│  Phase 3: Role QA (role_qa.py)                                         │
│  ├── Validates: No hallucinations in bullets                           │
│  └── Returns: QAResult per role                                        │
│                                                                          │
│  Phase 4: Stitcher (stitcher.py)                                       │
│  ├── Deduplicates: Cross-role bullet similarities                      │
│  ├── Enforces: Word budget (600 words default)                         │
│  └── Returns: StitchedCV                                               │
│                                                                          │
│  Phase 5: Header Generator (header_generator.py) ⚠️ ISSUE HERE         │
│  ├── Generates: Profile summary (LLM-based, grounded)                  │
│  ├── Generates: Core Competencies ⚠️ HARDCODED SKILLS                  │
│  │   ├── Uses: _extract_skills_from_bullets() with HARDCODED lists    │
│  │   ├── Categories: ALWAYS ["Leadership", "Technical", "Platform",   │
│  │   │                        "Delivery"] - NOT JD-DERIVED             │
│  │   └── Skills: Includes PHP, Java, etc. NOT in master-cv            │
│  └── Returns: HeaderOutput                                             │
│                                                                          │
│  Phase 6: Grader + Improver (grader.py, improver.py)                   │
│  └── Quality control and refinement                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Affected Components

| Component | File | Role | Modification Required |
|-----------|------|------|----------------------|
| **Header Generator** | `src/layer6_v2/header_generator.py` | Generates profile + skills | MAJOR - Dynamic skills extraction |
| **Header Prompts** | `src/layer6_v2/prompts/header_generation.py` | Skill category definitions | MODERATE - Dynamic categories |
| **Role Generator** | `src/layer6_v2/role_generator.py` | Generates experience bullets | MODERATE - STAR format enforcement |
| **Role Prompts** | `src/layer6_v2/prompts/role_generation.py` | Bullet generation prompts | MODERATE - STAR template |
| **Orchestrator** | `src/layer6_v2/orchestrator.py` | Assembles CV text | MINOR - Tagline injection |
| **Frontend App** | `frontend/app.py` | PDF generation + API | MINOR - Color scheme |
| **Frontend Templates** | `frontend/templates/base.html` | HTML rendering | MINOR - Color + spacing |
| **CV Loader** | `src/layer6_v2/cv_loader.py` | Loads master-cv data | NO CHANGE - Already correct |

---

## 3. Root Cause Analysis

### P0-1: Hallucinated Skills (PHP, Java, Spring Boot)

**Location**: `src/layer6_v2/header_generator.py:190-226`

**Problem Code**:
```python
# Line 200-213: HARDCODED skill lists
skill_lists = {
    "Technical": [
        # Languages
        "Python", "Java", "TypeScript", "JavaScript", "Go", "Rust", "Scala", "Kotlin",
        "C#", ".NET", ".NET Core", "Node.js", "Ruby", "PHP",  # ⚠️ PHP NOT in master-cv!
        # Databases
        "SQL", "NoSQL", "PostgreSQL", "MySQL", "MongoDB", "MS SQL Server", "Redis", "DynamoDB",
        # APIs & Architecture
        "REST API", "REST APIs", "GraphQL", "gRPC", "Microservices", "System Design",
        # ...
    ],
    # ...
}
```

**Root Cause**:
- Skills are **not** sourced from master-cv `hard_skills` and `soft_skills`
- Instead, a **predefined dictionary** of common skills is used
- The `_find_skill_evidence()` method checks if skill appears in bullets, but the skill must be in the predefined list first
- If "PHP" is in the predefined list and accidentally matches a bullet (e.g., "used PHP as a..." in a description), it gets included

**Evidence from Master-CV**:
```markdown
# data/master-cv/roles/01_seven_one_entertainment.md
**Hard Skills**: domain-driven-design, architecture, architectural runway, nodejs,
lambda, s3, aws, redis, ecs, eventbridge, cloudfront, microservices, DDD, python,
git, terraform, scaling, serverless, opensearch

**Soft Skills**: technical leadership, mentoring, handling technical debt,
overhauling legacy systems, leading architectural initiatives, requirement analysis,
SCRUM, hiring & interviewing, risk analysis and mitigation, cmp, tcf, gdpr, mentoring
```

**NO mention of**: PHP, Java, Spring Boot, Laravel

---

### P0-2: Static Core Skills Categories

**Location**: `src/layer6_v2/header_generator.py:495-501`

**Problem Code**:
```python
# Build SkillsSection objects
sections = []
for category in ["Leadership", "Technical", "Platform", "Delivery"]:  # ⚠️ HARDCODED
    skills = skills_by_category.get(category, [])
    if skills:  # Only include categories with skills
        sections.append(SkillsSection(
            category=category,
            skills=skills[:8],  # Limit to 8 skills per category
        ))
```

**Root Cause**:
- Categories are **always** the same 4 names
- No logic to derive categories from JD requirements
- JD may need "Cloud Architecture", "Data Engineering", "Product Management" but system forces into 4 buckets

**What's Needed**:
- Parse `extracted_jd.top_keywords`, `technical_skills`, `soft_skills`
- Cluster keywords into 3-4 **JD-specific** categories
- Example: For AI/ML role → ["Machine Learning", "Cloud Platform", "Technical Leadership"]
- Example: For Platform Engineering → ["Cloud Architecture", "DevOps", "System Design", "Engineering Leadership"]

---

### P0-3: Missing STAR Format

**Location**: `src/layer6_v2/prompts/role_generation.py` (bullet generation prompts)

**Current Prompt Structure** (inferred from codebase):
- Prompts ask for "tailored achievement bullets"
- No explicit STAR (Situation-Task-Action-Result) template
- No requirement to mention skills explicitly in action section

**What's Missing**:
```
STAR Structure:
[SITUATION/CHALLENGE] → [TASK/SKILL USED] → [ACTION/HOW] → [RESULT/IMPACT]

Example:
❌ Current: "Led migration to microservices architecture, improving system reliability"
✅ STAR: "Facing 30% annual outage increase in monolithic system, led 12-month
migration to event-driven microservices using AWS Lambda and EventBridge, achieving
75% incident reduction and zero downtime for 3 years"
```

**Challenge Indicators Needed**:
- "Facing...", "To address...", "Despite...", "With..."
- Quantified problem statement

**Skill Mentions Needed**:
- Explicit technology: "using Python", "leveraging Kubernetes", "implementing DDD"
- Explicit soft skill: "by mentoring 10 engineers", "through cross-functional collaboration"

---

### P1-1: No Dynamic Tagline (Relocation)

**Location**: `src/layer6_v2/orchestrator.py:315-333` (`_assemble_cv_text()`)

**Current Code**:
```python
# Header with name and contact
lines.append(f"# {candidate.name}")

# Build contact line with optional languages
contact_parts = [candidate.email, candidate.phone, candidate.linkedin]
if candidate.languages:
    language_str = f"Languages: {', '.join(candidate.languages)}"
    contact_parts.append(language_str)
lines.append(" | ".join(contact_parts))
lines.append("")
```

**Missing Logic**:
1. Parse `extracted_jd.location` or `state.get("location")`
2. Check if location matches: `["Saudi Arabia", "UAE", "Kuwait", "Qatar", "Oman", "Bahrain", "Pakistan"]`
3. If match, inject tagline: `"Available for International Relocation in 2 months"`
4. Placement: After name, before contact line OR after contact line

---

### P1-2: Green Color Scheme

**Location**: Multiple files

**Current Color**: `#0f766e` (deep teal/green)

**Files to Modify**:
1. `frontend/app.py:1967` - PDF generation color
2. `frontend/app.py:2160` - Another PDF color reference
3. `frontend/templates/base.html:1060` - HTML accent color

**Target Color**: Dark greyish blue (suggested: `#475569` - Tailwind `slate-600` or `#334155` - `slate-700`)

---

### P2-1: CV Spacing

**Location**: `frontend/static/css/cv-editor.css` and inline styles

**Current**: Various padding settings
**Target**: Reduce all padding/margins by 20%

---

## 4. Options Considered

### Option A: Minimal Patch (Quick Fix)

**Approach**:
- Replace hardcoded skill lists with master-cv parsing
- Keep 4 categories but populate from master-cv only
- Add STAR prompt guidance (not validation)
- Add tagline conditional logic
- Update colors manually

**Pros**:
- Fast to implement (1-2 days)
- Low risk of breaking existing pipeline
- Addresses P0-1 hallucinations immediately

**Cons**:
- Doesn't solve P0-2 (static categories)
- STAR format not enforced, just suggested
- No validation that skills are truly grounded

**Complexity**: Low
**Risk**: Low
**Time**: 1-2 days

---

### Option B: JD-Driven Dynamic Categories (Recommended)

**Approach**:
1. **P0-1 Fix**: Parse master-cv skills ONLY, create `all_candidate_skills` set
2. **P0-2 Fix**: Build JD-to-category mapper:
   - Input: `extracted_jd.top_keywords`, `technical_skills`, `soft_skills`
   - Use LLM or rule-based clustering to create 3-4 categories
   - Categories are **JD-specific** (e.g., "Machine Learning", "Cloud Platform")
   - Match master-cv skills to these categories
3. **P0-3 Fix**: Add STAR validator to role generation
   - Pydantic model for bullet structure: `{challenge, skill, action, result}`
   - Prompt must produce STAR-compliant bullets
4. **P1-1 Fix**: Add location parser + tagline injector
5. **P1-2 & P2-1**: CSS/color updates

**Pros**:
- Solves ALL P0 issues completely
- CVs truly tailored to JD requirements
- Skills are 100% grounded in master-cv
- STAR format validated

**Cons**:
- More complex implementation (3-4 days)
- Requires new LLM call for category generation (cost)
- May need new Pydantic schemas

**Complexity**: Medium-High
**Risk**: Medium (new LLM logic)
**Time**: 3-4 days

---

### Option C: Hybrid (Two-Phase Rollout)

**Phase 1** (Immediate - 1 day):
- Fix P0-1: Master-cv skill sourcing
- Fix P1-1: Dynamic tagline
- Fix P1-2: Color update
- Fix P2-1: Spacing

**Phase 2** (Next sprint - 2-3 days):
- Fix P0-2: JD-driven categories
- Fix P0-3: STAR validation

**Pros**:
- Quick wins on hallucinations
- Incremental risk
- Can test Phase 1 in production before Phase 2

**Cons**:
- Requires two deployment cycles
- P0-2 and P0-3 remain unresolved in Phase 1

**Complexity**: Split
**Risk**: Low (Phase 1), Medium (Phase 2)
**Time**: 1 day + 2-3 days

---

## 5. Recommended Architecture (Option B)

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   ENHANCED CV GENERATION PIPELINE                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Phase 1: CV Loader ✅ NO CHANGE                                        │
│  └── Already loads hard_skills + soft_skills correctly                 │
│                                                                          │
│  Phase 2: Per-Role Generator 🔧 MODIFY                                  │
│  ├── NEW: STAR-compliant prompt template                               │
│  ├── NEW: Pydantic validator for bullet structure                      │
│  └── Output: RoleBullets with validated STAR format                    │
│                                                                          │
│  Phase 3-4: QA + Stitcher ✅ NO CHANGE                                  │
│                                                                          │
│  Phase 5: Header Generator 🔧 MAJOR REWRITE                             │
│  ├── NEW: _load_all_master_cv_skills()                                 │
│  │   └── Aggregates hard_skills + soft_skills from all roles           │
│  ├── NEW: _generate_jd_skill_categories(extracted_jd, master_skills)   │
│  │   ├── Input: JD keywords + master-cv skills                         │
│  │   ├── LLM Call: "Cluster these skills into 3-4 JD-relevant cats"   │
│  │   └── Output: List[CategoryDefinition]                              │
│  ├── MODIFY: _extract_skills_from_bullets()                            │
│  │   └── Only match skills from master_cv_skills set                   │
│  ├── MODIFY: generate_skills()                                         │
│  │   └── Use dynamic categories from JD, not hardcoded 4               │
│  └── Output: HeaderOutput with JD-specific, grounded skills            │
│                                                                          │
│  Phase 5.5: Tagline Injector 🆕 NEW                                     │
│  ├── Input: extracted_jd.location                                      │
│  ├── Logic: Check if location in MIDDLE_EAST_PAKISTAN list             │
│  └── Output: Optional tagline string                                   │
│                                                                          │
│  Phase 6: Assembler 🔧 MODIFY                                           │
│  ├── MODIFY: _assemble_cv_text()                                       │
│  │   ├── Inject tagline if present                                     │
│  │   └── Apply new color scheme in HTML export                         │
│  └── Output: Final CV markdown + HTML                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Data Flow: Dynamic Skill Categories

```
┌─────────────────────────────────────────────────────────────────────────┐
│  INPUT: extracted_jd                                                    │
│  {                                                                       │
│    "top_keywords": ["Kubernetes", "AWS", "Python", "Team Leadership",   │
│                     "Microservices", "CI/CD", "Agile"],                │
│    "technical_skills": ["Kubernetes", "AWS", "Python", "Docker"],       │
│    "soft_skills": ["Team Leadership", "Mentoring", "Agile"]             │
│  }                                                                       │
│                                                                          │
│  INPUT: all_master_cv_skills (from Phase 1 loader)                     │
│  {                                                                       │
│    "hard": ["nodejs", "lambda", "aws", "redis", "python", "terraform"], │
│    "soft": ["technical leadership", "mentoring", "SCRUM"]               │
│  }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: Skill Matching                                                 │
│  ─────────────────────────────────────────────────────────────────────  │
│  For each JD keyword, check if it exists in master-cv:                  │
│    - "Kubernetes" → NOT in master-cv → SKIP                             │
│    - "AWS" → IN master-cv (hard_skills) → KEEP                          │
│    - "Python" → IN master-cv (hard_skills) → KEEP                       │
│    - "Team Leadership" → IN master-cv as "technical leadership" → KEEP  │
│    - "Microservices" → IN master-cv (hard_skills) → KEEP                │
│                                                                          │
│  Matched Skills: ["AWS", "Python", "Technical Leadership",              │
│                   "Microservices", "SCRUM", "Terraform", "Lambda"]      │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 2: LLM Category Generation (NEW)                                  │
│  ─────────────────────────────────────────────────────────────────────  │
│  Prompt:                                                                 │
│  "Given this JD and candidate skills, create 3-4 skill categories       │
│   that best represent the JD requirements. Each category should have    │
│   a name and list of skills from the candidate's background."           │
│                                                                          │
│  LLM Output (Pydantic validated):                                       │
│  [                                                                       │
│    {                                                                     │
│      "category": "Cloud Platform Engineering",                          │
│      "skills": ["AWS", "Lambda", "Terraform", "Serverless"]             │
│    },                                                                    │
│    {                                                                     │
│      "category": "Backend Architecture",                                │
│      "skills": ["Python", "Microservices", "Node.js", "DDD"]            │
│    },                                                                    │
│    {                                                                     │
│      "category": "Technical Leadership",                                │
│      "skills": ["Technical Leadership", "Mentoring", "SCRUM"]           │
│    }                                                                     │
│  ]                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 3: Evidence Validation                                            │
│  ─────────────────────────────────────────────────────────────────────  │
│  For each skill in each category:                                       │
│    - Find evidence in stitched CV bullets                               │
│    - If no evidence found → REMOVE skill                                │
│    - Build SkillEvidence object with bullet references                  │
│                                                                          │
│  Final Output:                                                           │
│  HeaderOutput.skills_sections = [                                       │
│    SkillsSection(                                                        │
│      category="Cloud Platform Engineering",                             │
│      skills=[                                                            │
│        SkillEvidence(skill="AWS", evidence_bullets=[...]),              │
│        SkillEvidence(skill="Lambda", evidence_bullets=[...])            │
│      ]                                                                   │
│    ),                                                                    │
│    ...                                                                   │
│  ]                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### API Contracts

#### New Pydantic Models

```python
# src/layer6_v2/types.py (additions)

@dataclass
class CategoryDefinition:
    """LLM-generated skill category tailored to JD."""
    category_name: str              # e.g., "Cloud Platform Engineering"
    description: str                # Why this category matters for JD
    skill_keywords: List[str]       # Skills from master-cv that fit
    priority: int                   # 1 = most important for JD

@dataclass
class MasterCVSkills:
    """All skills from master-cv aggregated."""
    hard_skills: Set[str]           # From all roles' hard_skills
    soft_skills: Set[str]           # From all roles' soft_skills

    @property
    def all_skills(self) -> Set[str]:
        return self.hard_skills | self.soft_skills

class STARBullet(BaseModel):
    """STAR-validated bullet structure."""
    situation: str = Field(description="Challenge/context")
    task: str = Field(description="What needed to be done")
    action: str = Field(description="How you did it (must mention skill)")
    result: str = Field(description="Quantified outcome")
    skills_mentioned: List[str] = Field(description="Skills explicitly used")

    @field_validator('skills_mentioned')
    def validate_skills_in_action(cls, v, values):
        """Ensure at least one skill is mentioned in action."""
        if not v:
            raise ValueError("Action must mention at least one skill")
        return v
```

---

### Implementation Phases

#### Phase 1: Master-CV Skill Sourcing (P0-1 Fix) - 0.5 days

**Files**:
- `src/layer6_v2/header_generator.py`

**Changes**:
1. Add method: `_load_all_master_cv_skills(candidate_data: CandidateData) -> MasterCVSkills`
   - Aggregates `hard_skills` and `soft_skills` from all roles
   - Returns deduplicated sets
2. Modify: `_extract_skills_from_bullets()`
   - Remove hardcoded `skill_lists` dictionary
   - Only check if skill from master-cv appears in bullets
   - No longer searches for PHP, Java, etc.
3. Update: `generate_skills()` method
   - Call `_load_all_master_cv_skills()` first
   - Pass master-cv skills to extraction logic

**Testing**:
```python
# Test case: Verify no hallucinated skills
def test_no_hallucinated_skills():
    # Given: Master-CV without PHP
    # When: Generate CV
    # Then: Core Competencies must not contain PHP
    assert "PHP" not in header.all_skill_names
    assert "Java" not in header.all_skill_names
```

---

#### Phase 2: JD-Driven Categories (P0-2 Fix) - 1.5 days

**Files**:
- `src/layer6_v2/header_generator.py`
- `src/layer6_v2/prompts/header_generation.py`
- `src/layer6_v2/types.py`

**Changes**:
1. Add Pydantic model: `CategoryDefinition` (see above)
2. Add method: `_generate_jd_skill_categories(extracted_jd, master_skills) -> List[CategoryDefinition]`
   - LLM prompt: "Given JD keywords and candidate skills, create 3-4 categories"
   - Validates output with Pydantic
   - Falls back to default 4 categories if LLM fails
3. Modify: `generate_skills()` method
   - Call `_generate_jd_skill_categories()` instead of hardcoded categories
   - Use returned categories for skill organization
4. Add prompt: `CATEGORY_GENERATION_SYSTEM_PROMPT` in `header_generation.py`

**Prompt Example**:
```python
CATEGORY_GENERATION_SYSTEM_PROMPT = """You are a CV skill categorization expert.

Your task: Given a job description and a candidate's skills, create 3-4 skill
categories that BEST represent what the JD is looking for.

RULES:
1. Categories must be JD-specific (not generic)
2. Use terminology from the JD when possible
3. Each category should have 4-8 skills
4. Prioritize categories by JD importance
5. Only use skills that exist in the candidate's background

OUTPUT FORMAT:
{
  "categories": [
    {
      "category_name": "Cloud Platform Engineering",
      "description": "Why this matters for the JD",
      "skill_keywords": ["AWS", "Lambda", "Terraform"],
      "priority": 1
    }
  ]
}
"""
```

**Testing**:
```python
def test_dynamic_categories_for_ml_role():
    # Given: JD for ML Engineer
    extracted_jd = {"top_keywords": ["Python", "TensorFlow", "AWS"]}
    # When: Generate categories
    categories = _generate_jd_skill_categories(extracted_jd, master_skills)
    # Then: Categories should be ML-focused, not generic
    assert any("Machine Learning" in c.category_name for c in categories)
    assert not all(c.category_name in ["Technical", "Platform"] for c in categories)
```

---

#### Phase 3: STAR Format Enforcement (P0-3 Fix) - 1 day

**Files**:
- `src/layer6_v2/role_generator.py`
- `src/layer6_v2/prompts/role_generation.py`
- `src/layer6_v2/types.py`

**Changes**:
1. Add Pydantic model: `STARBullet` (see above)
2. Modify: Role generation prompt to include STAR template:
```python
STAR_BULLET_TEMPLATE = """Each bullet must follow STAR format:

[CHALLENGE/SITUATION]: What problem or context existed?
[TASK]: What needed to be done?
[ACTION]: How did you do it? MUST mention specific skill(s) used.
[RESULT]: What was the quantified outcome?

Example:
"Facing 30% annual increase in system outages (CHALLENGE), led 12-month migration
to event-driven microservices (TASK) using AWS Lambda, EventBridge, and Python
(ACTION with skills), achieving 75% incident reduction and zero downtime for 3 years
(RESULT)."

CRITICAL: Action section MUST explicitly mention:
- Hard skills: Technologies, frameworks, architectures
- OR Soft skills: Leadership, mentoring, collaboration
"""
```
3. Add validator: After bullet generation, optionally validate STAR structure
   - Parse bullet into components
   - Check for challenge keywords: "Facing", "To address", "Despite"
   - Check for skill mentions in action section
   - Check for quantified result

**Testing**:
```python
def test_star_format_includes_skills():
    # Given: Generated bullet
    bullet = "Led migration using Python and AWS, achieving 75% reduction"
    # When: Validate STAR
    star = parse_star_bullet(bullet)
    # Then: Skills must be present
    assert "Python" in star.skills_mentioned
    assert "AWS" in star.skills_mentioned
```

---

#### Phase 4: Dynamic Tagline (P1-1 Fix) - 0.5 days

**Files**:
- `src/layer6_v2/orchestrator.py`

**Changes**:
1. Add constant:
```python
RELOCATION_REGIONS = {
    "middle_east": ["Saudi Arabia", "UAE", "United Arab Emirates", "Kuwait",
                    "Qatar", "Oman", "Bahrain"],
    "pakistan": ["Pakistan", "Karachi", "Lahore", "Islamabad"],
}
```
2. Add method: `_should_show_relocation_tagline(location: str) -> bool`
3. Modify: `_assemble_cv_text()` to inject tagline after name:
```python
lines.append(f"# {candidate.name}")

# Add relocation tagline if applicable
if self._should_show_relocation_tagline(state.get("location", "")):
    lines.append("*Available for International Relocation in 2 months*")
    lines.append("")

# Contact line...
```

**Testing**:
```python
def test_relocation_tagline_for_saudi_job():
    # Given: Job in Saudi Arabia
    state = {"location": "Riyadh, Saudi Arabia"}
    # When: Generate CV
    cv_text = orchestrator.generate(state)
    # Then: Tagline present
    assert "International Relocation in 2 months" in cv_text

def test_no_tagline_for_germany_job():
    # Given: Job in Germany
    state = {"location": "Munich, Germany"}
    # When: Generate CV
    cv_text = orchestrator.generate(state)
    # Then: No tagline
    assert "International Relocation" not in cv_text
```

---

#### Phase 5: Color + Spacing (P1-2, P2-1 Fix) - 0.5 days

**Files**:
- `frontend/app.py`
- `frontend/templates/base.html`
- `frontend/static/css/cv-editor.css`

**Changes**:

**Color Update** (Teal → Dark Greyish Blue):
```python
# frontend/app.py (Line 1967, 2160)
# OLD: "colorAccent": "#0f766e"  # Deep teal
# NEW: "colorAccent": "#475569"  # Slate-600 (dark greyish blue)

# frontend/templates/base.html (Line 1060)
# OLD: color: #0f766e;
# NEW: color: #475569;
```

**Spacing Reduction** (20% narrower):
```css
/* frontend/static/css/cv-editor.css */
/* Reduce all padding by 20% */

/* Example: If current padding is 1.5rem, new = 1.2rem (1.5 * 0.8) */
#cv-editor-content .ProseMirror {
    padding: 1.2rem !important;  /* Was 1.5rem */
}

/* Apply 0.8x multiplier to all CV content padding/margin */
.cv-section {
    margin-bottom: 0.8rem;  /* Was 1rem */
}
```

**Testing**:
- Visual inspection of PDF output
- Compare before/after screenshots

---

### Configuration Changes

**New Environment Variables**:
None required (LLM uses existing OpenRouter config)

**Database Schema**:
No changes required (all changes are generation logic)

---

### Testing Strategy

#### Unit Tests (Required)

| Test | File | Purpose |
|------|------|---------|
| `test_master_cv_skill_loading` | `test_header_generator.py` | Verify all skills loaded from roles |
| `test_no_hallucinated_skills` | `test_header_generator.py` | Ensure PHP, Java excluded |
| `test_jd_category_generation` | `test_header_generator.py` | Verify dynamic categories |
| `test_star_format_validation` | `test_role_generator.py` | Validate STAR structure |
| `test_relocation_tagline_logic` | `test_orchestrator.py` | Test tagline conditions |

#### Integration Tests

| Test | Purpose |
|------|---------|
| `test_end_to_end_cv_generation` | Full pipeline with JD → CV |
| `test_skill_grounding_validation` | Ensure all skills have evidence |

#### Manual Testing

1. **Hallucination Check**: Generate CV for 3 different JDs, manually verify no fabricated skills
2. **Category Relevance**: Generate CV for ML role, verify categories are ML-specific
3. **STAR Format**: Read 10 random bullets, verify challenge/skill/result present
4. **Tagline**: Test with Saudi Arabia job vs Germany job
5. **Color/Spacing**: Visual comparison of PDF before/after

---

## 6. Risk Assessment

### High Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **LLM category generation fails** | Falls back to hardcoded 4 categories | Add robust fallback logic + retries |
| **Skill matching too strict** | CV has very few skills | Use fuzzy matching (e.g., "kubernetes" matches "Kubernetes") |
| **STAR validation rejects good bullets** | Pipeline failures | Make STAR validation optional (warning, not error) |

### Medium Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Performance degradation** | Extra LLM call adds latency | Cache category generation per JD |
| **Cost increase** | Category generation adds $0.02/CV | Acceptable for quality improvement |

### Low Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Color preference subjective** | User doesn't like new color | Make color configurable via env var |
| **Spacing too tight** | CV looks cramped | A/B test with users |

---

## 7. Open Questions

### For User Clarification

1. **Category Count**: Always 3-4 categories, or flexible (2-5)?
2. **STAR Enforcement**: Should we reject bullets that don't pass STAR validation, or just warn?
3. **Tagline Placement**: After name or after contact line?
4. **Color Choice**: Confirm `#475569` (slate-600) or prefer different shade?
5. **Spacing Reduction**: Apply to PDF only, or also HTML editor view?
6. **JD Location Field**: Is location always in `extracted_jd.location` or `state["location"]`?

---

## 8. Implementation Roadmap

### Week 1: P0 Fixes

| Day | Tasks | Deliverables |
|-----|-------|--------------|
| **Day 1** | Phase 1 (Skill Sourcing) + Phase 4 (Tagline) | No hallucinations, dynamic tagline |
| **Day 2** | Phase 2 (Dynamic Categories) | JD-driven skill categories |
| **Day 3** | Phase 3 (STAR Format) | STAR-compliant bullets |
| **Day 4** | Phase 5 (Color + Spacing) + Testing | Visual polish, unit tests |
| **Day 5** | Integration testing + Documentation | Deployment-ready |

**Total Effort**: 5 days (1 developer week)

---

## 9. Success Metrics

### Before vs After

| Metric | Current | Target |
|--------|---------|--------|
| **Hallucinated Skills** | 3-5 per CV (PHP, Java, etc.) | 0 |
| **Category Relevance** | Generic 4 categories | 90%+ JD-aligned |
| **STAR Compliance** | ~30% of bullets | 80%+ of bullets |
| **Tagline Accuracy** | 0% (not implemented) | 100% for target regions |
| **Color Scheme** | Green/teal | Dark greyish blue |

---

## 10. Files to Modify (Summary)

### Core Changes (P0)

| File | Lines Changed | Complexity |
|------|---------------|------------|
| `src/layer6_v2/header_generator.py` | ~200 lines | High |
| `src/layer6_v2/prompts/header_generation.py` | ~100 lines | Medium |
| `src/layer6_v2/role_generator.py` | ~50 lines | Medium |
| `src/layer6_v2/prompts/role_generation.py` | ~80 lines | Medium |
| `src/layer6_v2/types.py` | ~50 lines (new models) | Low |
| `src/layer6_v2/orchestrator.py` | ~30 lines | Low |

### Polish Changes (P1-P2)

| File | Lines Changed | Complexity |
|------|---------------|------------|
| `frontend/app.py` | 3 lines (color) | Low |
| `frontend/templates/base.html` | 2 lines (color) | Low |
| `frontend/static/css/cv-editor.css` | ~20 lines (spacing) | Low |

### Tests

| File | Lines Added | Complexity |
|------|-------------|------------|
| `tests/layer6_v2/test_header_generator.py` | ~150 lines | Medium |
| `tests/layer6_v2/test_role_generator.py` | ~80 lines | Medium |
| `tests/layer6_v2/test_orchestrator.py` | ~50 lines | Low |

---

## 11. Deployment Considerations

### Pre-Deployment Checklist

- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing on 5+ sample JDs
- [ ] Performance benchmarking (should be <10s per CV)
- [ ] Cost analysis (new LLM call adds ~$0.02/CV)
- [ ] Update `missing.md` to mark P0-1, P0-2, P0-3 complete

### Rollout Strategy

**Option A: Big Bang**
- Deploy all changes at once
- Risk: Multiple failure modes
- Benefit: All issues fixed immediately

**Option B: Phased** (Recommended)
1. **Week 1**: Deploy Phase 1 (skill sourcing) + Phase 4 (tagline)
2. **Week 2**: Deploy Phase 2 (categories) + Phase 3 (STAR)
3. **Week 3**: Deploy Phase 5 (polish)

### Rollback Plan

- Keep old `header_generator.py` as `header_generator_v1.py`
- Add feature flag: `USE_DYNAMIC_CATEGORIES` (env var)
- If issues arise, set flag to `false` to revert to old logic

---

## 12. Conclusion

### Recommended Path Forward

**Adopt Option B (JD-Driven Dynamic Categories)** with phased rollout:

1. **Immediate**: Implement Phase 1 (master-cv skill sourcing) to eliminate hallucinations
2. **Week 1**: Add Phase 2 (dynamic categories) for true JD tailoring
3. **Week 2**: Implement Phase 3 (STAR format) for richer bullets
4. **Week 3**: Polish with Phase 4-5 (tagline, color, spacing)

### Next Steps

1. **User Approval**: Confirm approach and answer open questions (Section 7)
2. **Agent Handoff**: For implementation, recommend using:
   - Main Claude for backend logic (Phases 1-4)
   - `frontend-developer` agent for CSS/HTML changes (Phase 5)
   - `test-generator` agent for comprehensive test suite
3. **Documentation**: Update `plans/architecture.md` with new skill extraction flow
4. **Tracking**: Update `plans/missing.md` to reflect these fixes

---

**For implementation, I recommend using the main Claude agent to handle Phases 1-4 (backend logic), then `frontend-developer` for Phase 5 (CSS/color changes), and finally `test-generator` to write comprehensive tests.**

---

*End of Architecture Analysis*
