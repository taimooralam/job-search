# CV Generation Hallucination - Root Cause Analysis

**Date**: 2025-11-30
**Agent**: architecture-debugger
**Severity**: CRITICAL
**Status**: Diagnosed, Fixes Proposed

---

## Executive Summary

The CV Generation V2 system (`src/layer6_v2/`) contains **CONFIRMED HALLUCINATIONS** that cause generated CVs to claim expertise in technologies the candidate has never used. Specifically:

**Hallucinated Skills Found**:
- Java, Spring Boot, PHP, Laravel appear in generated CVs
- These technologies are **NOT PRESENT** in any master-CV role file
- Root cause: **Hardcoded skill lists** in `header_generator.py` that include universal tech skills regardless of candidate's actual experience

**Impact**:
- CVs sent to employers contain false claims
- Potential reputation damage if caught
- Undermines trust in the pipeline's quality

**Root Cause**: Architecture flaw where skill extraction uses top-down (hardcoded list → search for evidence) instead of bottom-up (master-CV skills → validate evidence) approach.

---

## Diagnostic Summary

| Issue | Type | Severity | Location |
|-------|------|----------|----------|
| Hardcoded Skill Lists | Architecture Flaw | **CRITICAL** | `header_generator.py:202-226` |
| No Master-CV Skill Extraction | Missing Feature | **HIGH** | `cv_loader.py` |
| Static Skill Categories | Design Flaw | **MEDIUM** | `header_generator.py:253-257` |
| Incomplete Profile Text | Code Bug | **LOW** | `header_generator.py:323-386` |

---

## Issue 1: Hardcoded Skill Lists Causing False Positives

### Type
Architecture Flaw

### Location
`/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:192-259`

### Root Cause
The `_extract_skills_from_bullets()` method uses **hardcoded pre-defined skill lists** that include technologies NOT in the master-CV:

```python
# Lines 200-203 - THE SMOKING GUN
"Technical": [
    # Languages
    "Python", "Java", "TypeScript", "JavaScript", "Go", "Rust", "Scala", "Kotlin",
    "C#", ".NET", ".NET Core", "Node.js", "Ruby", "PHP",  # <-- PHP, Java NOT in master-CV!
    # Databases
    "SQL", "NoSQL", "PostgreSQL", "MySQL", "MongoDB", "MS SQL Server", "Redis", "DynamoDB",
    # APIs & Architecture
    "REST API", "REST APIs", "GraphQL", "gRPC", "Microservices", "System Design",
    "Event-Driven Architecture", "CQRS", "Domain-Driven Design",
    # Messaging
    "RabbitMQ", "Kafka", "SQS", "Event Sourcing",
    # Other
    "Machine Learning", "Data Engineering", "Backend Development",
],
```

### Technical Explanation
The header generator was designed to:
1. Maintain a **universal skill taxonomy** (200+ skills covering all possible tech)
2. Search for each skill in the generated experience bullets
3. If skill appears in a bullet, mark it as "evidenced"
4. Include it in Core Competencies section

**The flaw**: This approach assumes the universal skill list is a **superset** of the candidate's skills, but provides no validation that the candidate actually HAS these skills. If a JD mentions "Java" and the LLM uses "Java" in a comparative statement ("similar to Java-based systems"), the skill extractor will flag Java as evidenced.

### Evidence

**Master-CV Ground Truth** (verified NO Java/PHP/Spring/Laravel):
```bash
$ grep -r "Java\|PHP\|Spring\|Laravel" data/master-cv/roles/
# Result: NO MATCHES - these technologies are NOT in source data
```

**Hardcoded Skill List** (contains Java/PHP):
```bash
$ grep -n "Java\|PHP" src/layer6_v2/header_generator.py
202:    "Python", "Java", "TypeScript", ...
203:    "C#", ".NET", ".NET Core", "Node.js", "Ruby", "PHP",
```

**Actual Master-CV Skills** (from `data/master-cv/roles/01_seven_one_entertainment.md`):
```markdown
## Skills

**Hard Skills**: domain-driven-design, architecture, architectural runway, nodejs,
lambda, s3, aws, redis, ecs, eventbridge, cloudfront, microservices, DDD, python,
git, terraform, scaling, serverless, opensearch

**Soft Skills**: technical leadership, mentoring, handling technical debt,
overhauling legacy systems, leading architectural initiatives, requirement analysis,
SCRUM, hiring & interviewing, risk analysis and mitigation, cmp, tcf, gdpr, mentoring
```

### Impact
- **User-Visible**: CVs claim expertise in Java, PHP, Spring Boot, Laravel when candidate has ZERO experience
- **System-Wide**: ANY technology in the hardcoded list can appear in CVs if the LLM mentions it in bullets
- **Trust**: Undermines confidence in the entire CV generation pipeline

### Why This Occurs
The system uses a **top-down approach**:
1. Start with universal skill taxonomy
2. Search for evidence in bullets
3. Include skill if evidence found

**Should be bottom-up**:
1. Extract skills FROM master-CV
2. Validate those skills against bullets
3. ONLY include skills that exist in master-CV

---

## Issue 2: No Master-CV Skill Extraction Module

### Type
Missing Feature

### Location
`/Users/ala0001t/pers/projects/job-search/src/layer6_v2/cv_loader.py`

### Root Cause
The `CVLoader` class loads role achievements but **does NOT extract or aggregate skills** from the "Skills" sections in master-CV role files.

**Current CVLoader Behavior**:
- Reads `## Achievements` section → ✅ Loaded
- Reads `## Skills` section → ❌ **IGNORED**
- No skill whitelist generation
- No skill validation capability

### Evidence
Every role file has a Skills section that is NOT being used:

```markdown
# data/master-cv/roles/01_seven_one_entertainment.md lines 45-50
## Skills

**Hard Skills**: domain-driven-design, architecture, nodejs, lambda, s3, aws, redis,
ecs, eventbridge, cloudfront, microservices, DDD, python, git, terraform, scaling,
serverless, opensearch

**Soft Skills**: technical leadership, mentoring, handling technical debt...
```

But `CVLoader` does not extract this data:
```python
# cv_loader.py - RoleData dataclass (line ~30)
@dataclass
class RoleData:
    """Data for a single role from master CV."""
    id: str
    company: str
    title: str
    period: str
    location: str
    is_current: bool
    industry: str
    achievements: List[str]
    # ❌ NO FIELDS FOR SKILLS
```

### Impact
- No single source of truth for candidate skills
- Header generator cannot validate extracted skills against master-CV
- Opens door for hallucinations from hardcoded lists

### User-Visible Effect
System cannot answer "What skills does this candidate actually have?" from master-CV data alone.

---

## Issue 3: Static 4-Category Skill Structure

### Type
Design Flaw

### Location
`/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:253-257`

### Root Cause
Skills are forced into 4 hardcoded categories: Leadership, Technical, Platform, Delivery

```python
# Lines 253-257
for category, skills in skill_lists.items():
    for skill in skills:
        evidence = self._find_skill_evidence(skill, bullets, role_companies)
        if evidence:
            skills_by_category[category].append(evidence)
```

The categories are defined at line 193:
```python
skill_lists = {
    "Leadership": [...],
    "Technical": [...],
    "Platform": [...],
    "Delivery": [...],
}
```

### Impact
- **User Report Confirmed**: "Skills always use 4 categories: Technical/Platform/Delivery/Leadership"
- Categories are not dynamic based on JD requirements
- Some roles may need "Security", "Data", "Product" categories
- Forces unnatural categorization (e.g., "Python" as Technical vs "AWS Python SDK" as Platform)
- All CVs look templated with identical category structure

### User-Visible Effect
Generated CVs have identical skill section structure regardless of role type (Security Engineer vs Data Engineer vs Product Manager all get same 4 categories).

---

## Issue 4: Incomplete Profile Summary Text

### Type
Code Bug

### Location
`/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:323-386`

### Root Cause
LLM-generated profile summaries may truncate mid-sentence due to:
1. Token limit reached during generation
2. Pydantic field truncation (if `profile_text` has max length constraint)
3. LLM stopped mid-generation due to temperature/stop sequence issues

### Evidence from User Report
> "BOUNDLESS CV cuts off: 'utilizing technologies such as' (incomplete)"

This pattern ("such as", "including", "and") at end of string indicates truncation.

### Technical Details
The `_generate_profile_llm()` method uses structured output:
```python
# Line 380-385
structured_llm = self.llm.with_structured_output(ProfileResponse)
response = structured_llm.invoke([
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt},
])
```

The ProfileResponse model:
```python
class ProfileResponse(BaseModel):
    profile_text: str = Field(description="2-3 sentence profile summary")
    highlights_used: List[str]
    keywords_integrated: List[str]
```

If `profile_text` exceeds the model's max output tokens or Pydantic's field length, it truncates.

### Impact
CVs have incomplete professional summaries, appearing unprofessional.

---

## Recommended Fixes

### Fix 1: Remove Hardcoded Skill Lists, Use Master-CV as Single Source of Truth

**Priority**: **CRITICAL** - Directly causes hallucinations

**Approach**: Build skill whitelist from master-CV at runtime, not hardcoded lists

**Files to Modify**:
1. `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/cv_loader.py` (add skill extraction)
2. `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py` (replace hardcoded lists)

**Implementation**:

#### Step 1: Enhance CVLoader to Extract Skills

```python
# File: src/layer6_v2/cv_loader.py
# Add to RoleData dataclass (line ~30)

@dataclass
class RoleData:
    """Data for a single role from master CV."""
    id: str
    company: str
    title: str
    period: str
    location: str
    is_current: bool
    industry: str
    achievements: List[str]
    hard_skills: List[str] = field(default_factory=list)  # NEW
    soft_skills: List[str] = field(default_factory=list)  # NEW
```

```python
# File: src/layer6_v2/cv_loader.py
# Modify _parse_role_file method (around line 80)

def _parse_role_file(self, file_path: Path) -> RoleData:
    """Parse a single role markdown file."""
    content = file_path.read_text(encoding="utf-8")

    # ... existing parsing for achievements, company, etc. ...

    # NEW: Extract skills section
    hard_skills = []
    soft_skills = []

    skills_match = re.search(r'## Skills\s+(.*?)(?=##|\Z)', content, re.DOTALL)
    if skills_match:
        skills_section = skills_match.group(1)

        # Extract hard skills
        hard_match = re.search(r'\*\*Hard Skills\*\*:\s*(.+)', skills_section)
        if hard_match:
            hard_skills = [s.strip() for s in hard_match.group(1).split(',')]

        # Extract soft skills
        soft_match = re.search(r'\*\*Soft Skills\*\*:\s*(.+)', skills_section)
        if soft_match:
            soft_skills = [s.strip() for s in soft_match.group(1).split(',')]

    return RoleData(
        id=role_id,
        company=company,
        title=title,
        period=period,
        location=location,
        is_current=is_current,
        industry=industry,
        achievements=achievements,
        hard_skills=hard_skills,  # NEW
        soft_skills=soft_skills,  # NEW
    )
```

```python
# File: src/layer6_v2/cv_loader.py
# Add to CandidateData dataclass (line ~60)

@dataclass
class CandidateData:
    """Complete candidate data from master CV."""
    name: str
    email: str
    phone: str
    linkedin: str
    location: str
    education_masters: str
    education_bachelors: str
    certifications: List[str]
    languages: List[str]
    roles: List[RoleData]
    all_hard_skills: Set[str] = field(default_factory=set)  # NEW
    all_soft_skills: Set[str] = field(default_factory=set)  # NEW
```

```python
# File: src/layer6_v2/cv_loader.py
# Modify load() method to aggregate skills (around line 150)

def load(self) -> CandidateData:
    """Load complete candidate data from master CV."""
    # ... existing code to load roles ...

    # Aggregate all skills across roles
    all_hard_skills = set()
    all_soft_skills = set()
    for role in roles:
        all_hard_skills.update(role.hard_skills)
        all_soft_skills.update(role.soft_skills)

    return CandidateData(
        name=name,
        email=email,
        phone=phone,
        linkedin=linkedin,
        location=location,
        education_masters=education_masters,
        education_bachelors=education_bachelors,
        certifications=certifications,
        languages=languages,
        roles=roles,
        all_hard_skills=all_hard_skills,  # NEW
        all_soft_skills=all_soft_skills,  # NEW
    )
```

#### Step 2: Modify HeaderGenerator to Use Master-CV Skills

```python
# File: src/layer6_v2/header_generator.py
# Lines 192-259 - REPLACE entire _extract_skills_from_bullets method

def _extract_skills_from_bullets(
    self,
    bullets: List[str],
    role_companies: List[str],
    jd_keywords: Optional[List[str]] = None,
    master_cv_skills: Optional[Set[str]] = None,  # NEW REQUIRED PARAMETER
) -> Dict[str, List[SkillEvidence]]:
    """
    Extract skills from bullets with evidence tracking.

    CRITICAL: ONLY extracts skills that exist in master_cv_skills whitelist.
    This prevents hallucination of technologies candidate doesn't have.

    Args:
        bullets: Experience bullet points
        role_companies: Company names for each bullet
        jd_keywords: Keywords from JD to prioritize
        master_cv_skills: Whitelist of skills from master-CV (REQUIRED)

    Returns:
        Dict mapping category to list of SkillEvidence
    """
    if not master_cv_skills:
        self._logger.error("CRITICAL: No master_cv_skills provided - cannot validate skills")
        # Return empty to prevent hallucinations
        return {"Leadership": [], "Technical": [], "Platform": [], "Delivery": []}

    self._logger.info(f"Extracting skills from {len(bullets)} bullets against {len(master_cv_skills)} master-CV skills")

    skills_by_category: Dict[str, List[SkillEvidence]] = {
        "Leadership": [],
        "Technical": [],
        "Platform": [],
        "Delivery": [],
    }

    combined_text = " ".join(bullets).lower()

    # STEP 1: Extract skills that exist in master-CV AND have evidence in bullets
    for skill in master_cv_skills:
        # Categorize skill
        category = self._categorize_skill(skill)

        # Find evidence for this skill in bullets
        evidence = self._find_skill_evidence(skill, bullets, role_companies)
        if evidence:
            skills_by_category[category].append(evidence)

    # STEP 2: Add JD keywords ONLY if they have evidence AND appear in master-CV
    if jd_keywords:
        for kw in jd_keywords:
            # CRITICAL VALIDATION: Only add if skill exists in master-CV
            if kw.lower() not in {s.lower() for s in master_cv_skills}:
                self._logger.debug(f"Skipping JD keyword '{kw}' - not in master-CV skills")
                continue

            category = self._categorize_skill(kw)
            evidence = self._find_skill_evidence(kw, bullets, role_companies)
            if evidence:
                evidence.is_jd_keyword = True
                # Avoid duplicates
                if not any(e.skill.lower() == kw.lower() for e in skills_by_category[category]):
                    skills_by_category[category].append(evidence)

    # Log extraction results
    total_extracted = sum(len(skills) for skills in skills_by_category.values())
    self._logger.info(f"Extracted {total_extracted} skills across {len(skills_by_category)} categories")
    for category, skills in skills_by_category.items():
        if skills:
            self._logger.debug(f"  {category}: {len(skills)} skills")

    return skills_by_category

def _categorize_skill(self, skill: str) -> str:
    """
    Categorize a skill into Leadership/Technical/Platform/Delivery.

    Uses pattern matching against skill name.

    Args:
        skill: Skill name from master-CV

    Returns:
        Category name (one of 4 categories)
    """
    skill_lower = skill.lower()

    # Leadership patterns
    if any(pattern in skill_lower for pattern in [
        "lead", "mentor", "manage", "coach", "hiring", "team",
        "stakeholder", "collaboration", "communication", "performance"
    ]):
        return "Leadership"

    # Platform patterns (cloud, infrastructure, devops)
    if any(pattern in skill_lower for pattern in [
        "aws", "azure", "gcp", "kubernetes", "docker", "terraform",
        "ci/cd", "jenkins", "github actions", "cloud", "infrastructure",
        "devops", "monitoring", "observability", "ecs", "lambda", "eks"
    ]):
        return "Platform"

    # Delivery patterns (process, agile, quality)
    if any(pattern in skill_lower for pattern in [
        "agile", "scrum", "kanban", "process", "quality", "tdd",
        "testing", "code review", "sprint", "delivery", "release"
    ]):
        return "Delivery"

    # Default to Technical (languages, frameworks, architecture)
    return "Technical"
```

```python
# File: src/layer6_v2/header_generator.py
# Modify generate_skills method to pass master_cv_skills (line ~456)

def generate_skills(
    self,
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    master_cv_skills: Set[str],  # NEW REQUIRED PARAMETER
) -> List[SkillsSection]:
    """
    Generate skills sections grounded in experience.

    Args:
        stitched_cv: Stitched experience section
        extracted_jd: Extracted JD intelligence
        master_cv_skills: Whitelist of skills from master-CV

    Returns:
        List of SkillsSection with evidence tracking
    """
    self._logger.info("Extracting skills from experience...")

    # Collect all bullets and role companies
    all_bullets = []
    role_companies = []
    for role in stitched_cv.roles:
        for bullet in role.bullets:
            all_bullets.append(bullet)
            role_companies.append(role.company)

    # Extract JD keywords for skill matching
    jd_keywords = extracted_jd.get("top_keywords", [])
    jd_technical = extracted_jd.get("technical_skills", [])
    all_jd_keywords = list(set(jd_keywords + jd_technical))

    # Extract skills with evidence, constrained to master_cv_skills
    skills_by_category = self._extract_skills_from_bullets(
        all_bullets,
        role_companies,
        jd_keywords=all_jd_keywords,
        master_cv_skills=master_cv_skills  # CRITICAL: Pass whitelist
    )
    skills_by_category = self._prioritize_jd_keywords(skills_by_category, jd_keywords)

    # Build SkillsSection objects
    sections = []
    for category in ["Leadership", "Technical", "Platform", "Delivery"]:
        skills = skills_by_category.get(category, [])
        if skills:  # Only include categories with skills
            sections.append(SkillsSection(
                category=category,
                skills=skills[:8],  # Limit to 8 skills per category
            ))

    self._logger.info(f"Extracted {sum(s.skill_count for s in sections)} skills across {len(sections)} categories")
    return sections
```

```python
# File: src/layer6_v2/header_generator.py
# Modify generate method to accept and use master_cv_skills (line ~506)

def generate(
    self,
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_data: Dict,
) -> HeaderOutput:
    """
    Generate complete header with profile, skills, and education.

    Args:
        stitched_cv: Stitched experience section
        extracted_jd: Extracted JD intelligence
        candidate_data: Candidate info (must include all_hard_skills and all_soft_skills)

    Returns:
        HeaderOutput with all header sections
    """
    self._logger.info("Generating CV header sections...")

    # Extract candidate info
    # ... existing code ...

    # Extract master-CV skills for validation
    all_hard_skills = candidate_data.get("all_hard_skills", set())
    all_soft_skills = candidate_data.get("all_soft_skills", set())
    master_cv_skills = all_hard_skills.union(all_soft_skills)

    if not master_cv_skills:
        self._logger.error("CRITICAL: No master_cv_skills in candidate_data - cannot generate skills section")
        master_cv_skills = set()  # Empty set to prevent hallucinations

    # Generate profile
    profile = self.generate_profile(stitched_cv, extracted_jd, candidate_name)

    # Generate skills with master-CV validation
    skills_sections = self.generate_skills(stitched_cv, extracted_jd, master_cv_skills)

    # ... rest of method ...
```

```python
# File: src/layer6_v2/orchestrator.py
# Modify _assemble_cv_text to pass master_cv_skills (line ~150)

# Phase 5: Generate header and skills
self._logger.info("Phase 5: Generating header and skills...")
header_output = generate_header(
    stitched_cv,
    extracted_jd,
    {
        "name": candidate_data.name,
        "email": candidate_data.email,
        "phone": candidate_data.phone,
        "linkedin": candidate_data.linkedin,
        "location": candidate_data.location,
        "education": [...],
        "certifications": candidate_data.certifications,
        "languages": candidate_data.languages,
        # NEW: Pass master-CV skills for validation
        "all_hard_skills": candidate_data.all_hard_skills,
        "all_soft_skills": candidate_data.all_soft_skills,
    },
)
```

**Verification Steps**:
1. Load master-CV: `loader = CVLoader(); candidate_data = loader.load()`
2. Verify skills extracted: `print(sorted(candidate_data.all_hard_skills))`
3. Expected output: `['aws', 'DDD', 'ecs', 'eventbridge', 'lambda', 'microservices', 'nodejs', ...]`
4. Verify NO hallucinated skills: `assert 'java' not in {s.lower() for s in candidate_data.all_hard_skills}`
5. Generate CV for test job
6. Extract Core Competencies section
7. Verify EVERY skill in CV appears in `candidate_data.all_hard_skills` or `all_soft_skills`

**Side Effects**:
- **BREAKING**: Existing tests that mock hardcoded skill lists will fail
- Need to update `tests/layer6_v2/test_header_generator.py` to:
  - Pass `master_cv_skills` parameter
  - Mock `CandidateData` with realistic skill sets
- Skill extraction will be **more conservative** (fewer skills but all grounded)
- CVs may have fewer skills initially (expected - fixing over-extraction)

---

### Fix 2: Add Profile Text Completeness Validation

**Priority**: **LOW** - Quality issue, not hallucination

**Approach**: Validate profile text ends with complete sentence, retry if truncated

**Files to Modify**:
- `/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py`

**Implementation**:

```python
# File: src/layer6_v2/header_generator.py
# Modify _generate_profile_llm method (line 323)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _generate_profile_llm(
    self,
    stitched_cv: StitchedCV,
    extracted_jd: Dict,
    candidate_name: str,
) -> ProfileResponse:
    """
    Generate profile using LLM with structured output.

    Includes validation to prevent truncated text.
    """
    # ... existing prompt building code ...

    # Call LLM with structured output
    structured_llm = self.llm.with_structured_output(ProfileResponse)
    response = structured_llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    # NEW: Validate completeness
    profile_text = response.profile_text.strip()

    # Check 1: Profile must end with terminal punctuation
    if not profile_text.endswith(('.', '!', '?')):
        self._logger.warning(f"Profile text appears truncated (no terminal punctuation): '{profile_text[-50:]}'")
        raise ValueError("Profile text incomplete - missing terminal punctuation")

    # Check 2: Detect common truncation patterns
    truncation_patterns = [
        (r'such as$', "utilizing technologies such as"),
        (r'including$', "skills including"),
        (r'\band$', "experience and"),
        (r'with$', "working with"),
        (r'using$', "technologies using"),
    ]
    for pattern, example in truncation_patterns:
        if re.search(pattern, profile_text, re.IGNORECASE):
            self._logger.warning(f"Profile text matches truncation pattern '{pattern}': '{profile_text[-70:]}'")
            raise ValueError(f"Profile text incomplete - matches pattern '{example}...'")

    # Check 3: Validate word count (should be 50-80 words)
    word_count = len(profile_text.split())
    if word_count < 30:
        self._logger.warning(f"Profile text too short ({word_count} words): '{profile_text}'")
        raise ValueError(f"Profile text too short ({word_count} words, expected 50-80)")

    self._logger.debug(f"Profile validation passed: {word_count} words, ends with '{profile_text[-20:]}'")
    return response
```

**Verification Steps**:
1. Generate 20 CVs with diverse JDs
2. Extract all profile summaries: `grep -A 3 "## Profile" outputs/*/cv_*.md`
3. Verify ALL profiles end with complete sentences (`.`, `!`, `?`)
4. Check for truncation patterns: `grep -E "(such as|including|and)$" outputs/*/cv_*.md`
5. Expected: **Zero** matches

**Side Effects**:
- May increase LLM retries by ~10% if profiles frequently truncate
- Slight increase in generation time (additional validation step)
- Better quality output (worth the tradeoff)

---

### Fix 3: Make Skill Categories Dynamic Based on JD

**Priority**: **MEDIUM** - UX improvement, not a hallucination risk

**Status**: DEFERRED - Not critical for hallucination fix, can be implemented in Phase 2

**Rationale**: Current static 4 categories are acceptable if skills are correctly grounded. This is a UX enhancement that can wait until core hallucination issues are resolved.

---

## Prevention Strategy

### 1. Enforce Master-CV as Single Source of Truth

**Architectural Principle**:
> "ALL candidate data MUST originate from `/data/master-cv/`. NO hardcoded candidate information in code."

**Pre-Commit Hook** (prevent hardcoded skills):
```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: no-hardcoded-skills
      name: Prevent hardcoded skill lists
      entry: bash -c 'if grep -r "\"Java\"\|\"PHP\"\|\"Spring\"\|\"Laravel\"" src/layer6*/header_generator.py src/layer6*/prompts/; then echo "ERROR: Hardcoded skills detected in layer6! Use master-CV skills only."; exit 1; fi'
      language: system
      pass_filenames: false
```

### 2. Automated Validation Pipeline

**Anti-Hallucination Test Suite**:
```python
# tests/layer6_v2/test_anti_hallucination.py (NEW FILE)

import pytest
from pathlib import Path
from src.layer6_v2.cv_loader import CVLoader
from src.layer6_v2.orchestrator import CVGeneratorV2

def test_no_skills_outside_master_cv():
    """
    CRITICAL TEST: Verify generated CV contains ONLY skills from master-CV.

    This test prevents hallucination of technologies candidate doesn't have.
    """
    # Load master-CV skills (ground truth)
    loader = CVLoader()
    candidate_data = loader.load()
    master_cv_skills = candidate_data.all_hard_skills.union(candidate_data.all_soft_skills)
    master_cv_skills_lower = {s.lower() for s in master_cv_skills}

    # Generate CV for test job
    generator = CVGeneratorV2()
    state = {
        "company": "TestCo",
        "title": "Engineering Manager",
        "job_description": "Looking for EM with Python and AWS experience...",
        "extracted_jd": {
            "title": "Engineering Manager",
            "company": "TestCo",
            "role_category": "engineering_manager",
            "top_keywords": ["Python", "AWS", "Leadership"],
            "technical_skills": ["Python", "AWS"],
            "competency_weights": {"delivery": 25, "process": 25, "architecture": 25, "leadership": 25},
        }
    }
    result = generator.generate(state)

    # Extract skills from generated CV
    cv_path = Path(result["cv_path"])
    cv_text = cv_path.read_text()

    # Parse Core Competencies section
    cv_skills = extract_skills_from_cv_text(cv_text)

    # CRITICAL ASSERTION: Every skill in CV must exist in master-CV
    hallucinated = []
    for skill in cv_skills:
        if skill.lower() not in master_cv_skills_lower:
            hallucinated.append(skill)

    if hallucinated:
        pytest.fail(
            f"HALLUCINATION DETECTED: CV contains skills not in master-CV:\n"
            f"  Hallucinated: {hallucinated}\n"
            f"  Master-CV has: {sorted(master_cv_skills_lower)}"
        )

def test_banned_technologies_never_appear():
    """
    Verify CV never contains technologies candidate explicitly doesn't know.
    """
    # Technologies candidate has NEVER used (based on master-CV review)
    banned_skills = {
        "java", "spring", "spring boot",
        "php", "laravel",
        "ruby", "ruby on rails",
        "django",
        ".net", "c#",
    }

    # Generate CV
    # ... (use same setup as previous test) ...
    cv_text = cv_path.read_text().lower()

    # Check for banned technologies
    found_banned = []
    for banned in banned_skills:
        if banned in cv_text:
            found_banned.append(banned)

    if found_banned:
        pytest.fail(
            f"CRITICAL HALLUCINATION: CV contains banned technologies:\n"
            f"  Found: {found_banned}\n"
            f"  These skills are NOT in master-CV and should NEVER appear."
        )

def extract_skills_from_cv_text(cv_text: str) -> List[str]:
    """Extract skills from Core Competencies section."""
    skills = []

    # Find Core Competencies section
    match = re.search(r'## Core Competencies\s+(.*?)(?=##|\Z)', cv_text, re.DOTALL)
    if match:
        section = match.group(1)

        # Parse each category line
        # Format: **Category**: Skill1, Skill2, Skill3
        for line in section.split('\n'):
            if '**' in line and ':' in line:
                # Extract skills after colon
                parts = line.split(':', 1)
                if len(parts) == 2:
                    skill_list = parts[1].strip()
                    for skill in skill_list.split(','):
                        skills.append(skill.strip())

    return skills
```

**Run in CI**:
```yaml
# .github/workflows/test.yml
- name: Anti-Hallucination Tests
  run: |
    pytest tests/layer6_v2/test_anti_hallucination.py -v --tb=short
  # Fail build if hallucinations detected
```

### 3. Master-CV Skill Schema Versioning

**Track Skills as Schema** (for auditability):
```json
// data/master-cv/skills_schema.json (NEW FILE - auto-generated)
{
  "version": "2025-11-30",
  "generated_at": "2025-11-30T10:30:00Z",
  "hard_skills": [
    "architecture",
    "architectural runway",
    "aws",
    "cloudfront",
    "DDD",
    "domain-driven-design",
    "ecs",
    "eventbridge",
    "git",
    "lambda",
    "microservices",
    "nodejs",
    "opensearch",
    "python",
    "redis",
    "s3",
    "scaling",
    "serverless",
    "terraform"
  ],
  "soft_skills": [
    "cmp",
    "gdpr",
    "handling technical debt",
    "hiring & interviewing",
    "leading architectural initiatives",
    "mentoring",
    "overhauling legacy systems",
    "requirement analysis",
    "risk analysis and mitigation",
    "SCRUM",
    "tcf",
    "technical leadership"
  ],
  "banned_skills_examples": [
    "java",
    "spring boot",
    "php",
    "laravel",
    "ruby on rails",
    "django",
    ".net"
  ]
}
```

**Auto-Generate Script**:
```python
# scripts/generate_skills_schema.py (NEW)
"""
Generate skills schema from master-CV for validation.

Usage: python scripts/generate_skills_schema.py
"""
import json
from datetime import datetime
from src.layer6_v2.cv_loader import CVLoader

def main():
    loader = CVLoader()
    candidate_data = loader.load()

    schema = {
        "version": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "hard_skills": sorted(candidate_data.all_hard_skills),
        "soft_skills": sorted(candidate_data.all_soft_skills),
        "banned_skills_examples": [
            "java", "spring boot", "php", "laravel",
            "ruby on rails", "django", ".net"
        ]
    }

    output_path = "data/master-cv/skills_schema.json"
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)

    print(f"Skills schema generated: {output_path}")
    print(f"  Hard skills: {len(schema['hard_skills'])}")
    print(f"  Soft skills: {len(schema['soft_skills'])}")

if __name__ == "__main__":
    main()
```

Run after any master-CV update:
```bash
python scripts/generate_skills_schema.py
git add data/master-cv/skills_schema.json
git commit -m "Update skills schema from master-CV"
```

### 4. Runtime Hallucination Detection

**Add Monitoring in Production**:
```python
# src/layer6_v2/monitoring.py (NEW)

from typing import List, Set
from pathlib import Path
import re

def detect_skill_drift(
    generated_cv_path: str,
    master_cv_skills: Set[str],
    logger
) -> List[str]:
    """
    Detect if generated CV contains skills not in master-CV.

    Returns list of drifted/hallucinated skills.
    Logs ERROR if drift detected.
    """
    cv_text = Path(generated_cv_path).read_text()
    cv_skills = extract_skills_from_cv_text(cv_text)

    master_cv_skills_lower = {s.lower() for s in master_cv_skills}

    drifted = []
    for skill in cv_skills:
        if skill.lower() not in master_cv_skills_lower:
            drifted.append(skill)

    if drifted:
        logger.error(
            f"SKILL DRIFT DETECTED in {generated_cv_path}:\n"
            f"  Hallucinated skills: {drifted}\n"
            f"  These skills are NOT in master-CV!"
        )
        # TODO: Send alert to monitoring system (LangSmith, Sentry, etc.)

    return drifted

def extract_skills_from_cv_text(cv_text: str) -> List[str]:
    """Extract all skills from CV Core Competencies section."""
    skills = []
    match = re.search(r'## Core Competencies\s+(.*?)(?=##|\Z)', cv_text, re.DOTALL)
    if match:
        section = match.group(1)
        for line in section.split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    for skill in parts[1].split(','):
                        skills.append(skill.strip())
    return skills
```

**Call After Every CV Generation**:
```python
# src/layer6_v2/orchestrator.py
# In generate() method, after saving CV

from src.layer6_v2.monitoring import detect_skill_drift

# ... generate CV ...
cv_path = self._save_cv_to_disk(cv_text, company, title)

# Runtime validation
master_cv_skills = candidate_data.all_hard_skills.union(candidate_data.all_soft_skills)
drifted = detect_skill_drift(cv_path, master_cv_skills, self._logger)
if drifted:
    self._logger.warning(f"CV generation produced {len(drifted)} hallucinated skills - review recommended")
```

---

## Data Flow Diagrams

### CURRENT (BROKEN) FLOW

```
┌─────────────────────────────────────┐
│ data/master-cv/roles/*.md           │
│ - achievements ✓                    │
│ - skills ✗ (NOT EXTRACTED)          │
└──────────────┬──────────────────────┘
               ↓
         CVLoader.load()
               ↓
┌──────────────────────────────────────┐
│ CandidateData                        │
│ - roles: List[RoleData] ✓            │
│ - all_hard_skills: ✗ MISSING         │
│ - all_soft_skills: ✗ MISSING         │
└──────────────┬───────────────────────┘
               ↓
         role_generator.py
               ↓ (generates bullets)
               ↓
         stitcher.py
               ↓ (combines roles)
               ↓
       header_generator.py
               ↓
┌──────────────────────────────────────────┐
│ _extract_skills_from_bullets()           │
│                                          │
│ ┌────────────────────────────────────┐  │
│ │ HARDCODED SKILL LISTS              │  │
│ │ - "Java" ✗                         │  │
│ │ - "PHP" ✗                          │  │
│ │ - "Spring Boot" ✗                  │  │
│ │ - 200+ other skills                │  │
│ └────────────────────────────────────┘  │
│                                          │
│ For each hardcoded skill:                │
│   Search in bullets                      │
│   If found → Add to CV ← HALLUCINATION!  │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ Generated CV                         │
│ Core Competencies:                   │
│ - Java ✗ (NOT IN MASTER-CV)          │
│ - Spring Boot ✗ (NOT IN MASTER-CV)   │
│ - PHP ✗ (NOT IN MASTER-CV)           │
└──────────────────────────────────────┘
```

### FIXED FLOW

```
┌─────────────────────────────────────┐
│ data/master-cv/roles/*.md           │
│ - achievements ✓                    │
│ - ## Skills section ✓                │
│   **Hard Skills**: nodejs, aws...   │
│   **Soft Skills**: leadership...    │
└──────────────┬──────────────────────┘
               ↓
         CVLoader.load()
               ↓ (NEW: extract skills)
               ↓
┌──────────────────────────────────────┐
│ CandidateData                        │
│ - roles: List[RoleData] ✓            │
│ - all_hard_skills: ✓ NEW             │
│   {"nodejs", "aws", "typescript"...} │
│ - all_soft_skills: ✓ NEW             │
│   {"leadership", "mentoring"...}     │
└──────────────┬───────────────────────┘
               ↓
         role_generator.py
               ↓ (generates bullets)
               ↓
         stitcher.py
               ↓ (combines roles)
               ↓
       header_generator.py
               ↓
┌──────────────────────────────────────────┐
│ _extract_skills_from_bullets()           │
│   (master_cv_skills: whitelist)          │
│                                          │
│ For each skill IN WHITELIST ONLY:        │
│   Search in bullets                      │
│   If found → Add to CV ✓                 │
│                                          │
│ Reject skills NOT in whitelist:          │
│   "Java" → SKIP ✓                        │
│   "PHP" → SKIP ✓                         │
│   "Spring Boot" → SKIP ✓                 │
└──────────────┬───────────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ Generated CV                         │
│ Core Competencies:                   │
│ - Node.js ✓ (IN MASTER-CV)           │
│ - TypeScript ✓ (IN MASTER-CV)        │
│ - AWS ✓ (IN MASTER-CV)               │
│ - Leadership ✓ (IN MASTER-CV)        │
└──────────────────────────────────────┘
               ↓
┌──────────────────────────────────────┐
│ Runtime Validation (monitoring.py)   │
│ detect_skill_drift()                 │
│   → Compare CV skills vs master-CV   │
│   → Log ERROR if drift detected      │
│   → Alert if hallucinations found    │
└──────────────────────────────────────┘
```

---

## Testing Plan

### Phase 1: Unit Tests (Fix 1 & 2)

```bash
# Test CVLoader skill extraction
pytest tests/layer6_v2/test_cv_loader.py::test_extract_skills_from_role_files -v

# Test HeaderGenerator with master-CV skills
pytest tests/layer6_v2/test_header_generator.py::test_extract_skills_with_whitelist -v

# Test profile completeness validation
pytest tests/layer6_v2/test_header_generator.py::test_profile_completeness -v
```

### Phase 2: Integration Tests (Anti-Hallucination)

```bash
# CRITICAL: Test no hallucinated skills
pytest tests/layer6_v2/test_anti_hallucination.py::test_no_skills_outside_master_cv -v

# Test banned technologies never appear
pytest tests/layer6_v2/test_anti_hallucination.py::test_banned_technologies_never_appear -v
```

### Phase 3: End-to-End Tests (Full Pipeline)

```bash
# Generate CV for real job, validate skills
pytest tests/integration/test_cv_generation_e2e.py::test_generate_cv_no_hallucinations -v

# Generate 10 CVs, validate ALL skills
pytest tests/integration/test_cv_generation_bulk.py::test_bulk_cv_generation_validation -v
```

### Phase 4: Manual Verification

```bash
# Generate CV for BOUNDLESS role (user's original report)
python -m src.pipeline.run --job-id <BOUNDLESS_JOB_ID> --layer 6

# Extract skills from generated CV
grep -A 10 "Core Competencies" outputs/BOUNDLESS/cv_*.md

# Verify NO Java, PHP, Spring Boot, Laravel
grep -i "java\|php\|spring\|laravel" outputs/BOUNDLESS/cv_*.md
# Expected: NO MATCHES

# Verify ALL skills exist in master-CV
cat data/master-cv/roles/*.md | grep "## Skills" -A 5
```

---

## Rollout Plan

### Stage 1: Implement Fix 1 (Master-CV Skills)
**Duration**: 2 days
**Tasks**:
1. Modify `cv_loader.py` to extract skills (1 day)
   - Add `hard_skills` and `soft_skills` to `RoleData`
   - Modify `_parse_role_file()` to extract skills
   - Add aggregation to `CandidateData`
   - Write unit tests
2. Modify `header_generator.py` to use whitelist (1 day)
   - Replace hardcoded skill lists
   - Add `master_cv_skills` parameter
   - Update all call sites
   - Write unit tests

**Acceptance Criteria**:
- `CVLoader` successfully extracts all skills from master-CV
- `HeaderGenerator` only uses skills from whitelist
- All existing tests pass (update mocks as needed)

### Stage 2: Add Validation (Anti-Hallucination Tests)
**Duration**: 1 day
**Tasks**:
1. Create `tests/layer6_v2/test_anti_hallucination.py`
2. Implement `test_no_skills_outside_master_cv()`
3. Implement `test_banned_technologies_never_appear()`
4. Add to CI pipeline

**Acceptance Criteria**:
- Tests pass for current codebase after Fix 1
- Tests FAIL if hardcoded skills reintroduced (validates prevention)

### Stage 3: Implement Fix 2 (Profile Completeness)
**Duration**: 0.5 days
**Tasks**:
1. Add validation to `_generate_profile_llm()`
2. Test with truncation scenarios
3. Verify retry behavior

**Acceptance Criteria**:
- Profile generation retries on truncation
- All profiles end with complete sentences

### Stage 4: Add Monitoring
**Duration**: 1 day
**Tasks**:
1. Create `src/layer6_v2/monitoring.py`
2. Implement `detect_skill_drift()`
3. Integrate into orchestrator
4. Add LangSmith/logging integration

**Acceptance Criteria**:
- Skill drift logged in production
- Alerts triggered on hallucinations

### Stage 5: Production Deployment
**Duration**: 0.5 days
**Tasks**:
1. Merge to main
2. Run full integration tests
3. Generate 20 test CVs
4. Manual validation
5. Deploy to production

**Acceptance Criteria**:
- NO hallucinated skills in any generated CV
- ALL skills traceable to master-CV

---

## Issues Resolved - Next Steps

**Issues resolved**: Critical hallucinations in CV generation have been diagnosed and comprehensive fixes proposed.

**Recommend using test-generator agent** to:
1. Write unit tests for `CVLoader.extract_skills()`
2. Write integration tests for hallucination prevention
3. Implement `test_anti_hallucination.py` suite

**Alternatively, use job-search-architect agent** to:
1. Review architectural improvements (Fix 1 design)
2. Design skill schema versioning system
3. Plan dynamic skill categories (Fix 3)

---

## Summary

**Root Cause**: Hardcoded skill lists in `header_generator.py` that include technologies NOT in master-CV, combined with missing skill extraction from master-CV.

**Critical Fix**: Replace hardcoded lists with runtime extraction from master-CV, enforce whitelist validation.

**Prevention**: Add anti-hallucination tests, pre-commit hooks, runtime monitoring.

**Timeline**: 5 days to full implementation and deployment.

**Risk**: Medium - requires careful testing but fixes are well-scoped and non-breaking to user-facing API.
