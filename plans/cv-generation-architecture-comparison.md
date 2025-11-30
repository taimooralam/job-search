# CV Generation Architecture: Current vs Proposed

**Date**: 2025-11-30

---

## Current Architecture (Has Issues)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      CURRENT PIPELINE (BROKEN)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT: Job Description                                                  │
│  ├── "Senior Platform Engineer"                                         │
│  ├── Keywords: ["Kubernetes", "AWS", "Python", "Team Leadership"]       │
│  └── Company: ACME Corp                                                 │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  PHASE 5: Header Generator (PROBLEM HERE! ⚠️)                           │
│  ├── Profile Generation: ✅ WORKS (LLM-based, grounded)                 │
│  ├── Skills Generation: ❌ BROKEN                                       │
│  │   ├── Step 1: Check bullets against HARDCODED skill list            │
│  │   │   skill_lists = {                                                │
│  │   │     "Technical": ["Python", "Java", "PHP", "Ruby", ...]  ⚠️     │
│  │   │     "Platform": ["AWS", "Kubernetes", "Docker", ...]             │
│  │   │   }                                                              │
│  │   ├── Step 2: If "PHP" in bullets → ADD TO CV                       │
│  │   │   (Even though PHP NOT in master-cv!)                           │
│  │   ├── Step 3: ALWAYS output 4 categories:                           │
│  │   │   ["Leadership", "Technical", "Platform", "Delivery"]           │
│  │   │   (Not JD-specific!)                                            │
│  │   └── Step 4: Limit to 8 skills per category                        │
│  └── Output:                                                             │
│      Core Competencies:                                                  │
│      - Leadership: Team Leadership, Mentorship                          │
│      - Technical: Python, Java, PHP ⚠️ HALLUCINATION!                   │
│      - Platform: AWS, Kubernetes, Docker                                │
│      - Delivery: Agile, Scrum                                           │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  OUTPUT: CV with FABRICATED SKILLS ❌                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Problems Illustrated

1. **Hallucination Path**:
   ```
   Hardcoded "PHP" in skill_lists
        ↓
   Finds "PHP" in a bullet (false positive OR hallucinated bullet)
        ↓
   Adds "PHP" to Technical skills
        ↓
   CV claims "PHP" expertise despite ZERO evidence in master-cv
   ```

2. **Static Categories Path**:
   ```
   JD asks for: "Machine Learning", "Data Engineering", "MLOps"
        ↓
   System ignores JD requirements
        ↓
   Outputs generic: "Technical", "Platform", "Delivery"
        ↓
   ATS sees NO category match for "Machine Learning"
        ↓
   CV gets filtered out
   ```

---

## Proposed Architecture (Fixed)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      PROPOSED PIPELINE (FIXED)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT: Job Description                                                  │
│  ├── "Senior Platform Engineer"                                         │
│  ├── Keywords: ["Kubernetes", "AWS", "Python", "Team Leadership"]       │
│  └── Location: "Riyadh, Saudi Arabia"                                   │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  STEP 1: Load Master-CV Skills (NEW! ✅)                                │
│  ├── Parse all roles from data/master-cv/roles/*.md                    │
│  ├── Extract hard_skills: ["nodejs", "lambda", "aws", "python", ...]   │
│  ├── Extract soft_skills: ["technical leadership", "mentoring", ...]   │
│  └── Build: master_cv_skills_set = {all unique skills}                 │
│      (Total: ~60 skills across 6 roles)                                 │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  STEP 2: Match JD Keywords to Master-CV (NEW! ✅)                       │
│  ├── For each JD keyword:                                               │
│  │   ├── "Kubernetes" → NOT in master-cv → SKIP ❌                      │
│  │   ├── "AWS" → IN master-cv → KEEP ✅                                 │
│  │   ├── "Python" → IN master-cv → KEEP ✅                              │
│  │   └── "Team Leadership" → IN master-cv (fuzzy match) → KEEP ✅      │
│  └── Matched: ["AWS", "Python", "Lambda", "Technical Leadership", ...] │
│      (Only skills with EVIDENCE)                                        │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  STEP 3: Generate JD-Specific Categories (NEW! ✅)                      │
│  ├── LLM Prompt:                                                        │
│  │   "Given this Platform Engineer JD and candidate's AWS/Python        │
│  │    background, create 3-4 skill categories that align with JD."     │
│  ├── LLM Output (Pydantic validated):                                   │
│  │   [                                                                   │
│  │     {                                                                 │
│  │       "category": "Cloud Platform Engineering",  ✅ JD-SPECIFIC!    │
│  │       "skills": ["AWS", "Lambda", "Serverless", "Terraform"]        │
│  │     },                                                               │
│  │     {                                                                 │
│  │       "category": "Backend Architecture",        ✅ JD-SPECIFIC!    │
│  │       "skills": ["Python", "Microservices", "Node.js", "DDD"]       │
│  │     },                                                               │
│  │     {                                                                 │
│  │       "category": "Technical Leadership",                            │
│  │       "skills": ["Technical Leadership", "Mentoring"]               │
│  │     }                                                                 │
│  │   ]                                                                   │
│  └── Fallback: If LLM fails, use default 4 categories                   │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  STEP 4: Validate Evidence (ENHANCED ✅)                                │
│  ├── For each skill in each category:                                   │
│  │   ├── Search stitched CV bullets for mention                        │
│  │   ├── If found → Build SkillEvidence with bullet references         │
│  │   └── If NOT found → REMOVE skill (no hallucinations!)              │
│  └── Example:                                                            │
│      "AWS" → Found in bullet: "Built platform on AWS Lambda"           │
│      "PHP" → NOT found → REMOVED ✅                                     │
│                                                                          │
│          ↓                                                               │
│                                                                          │
│  STEP 5: Assemble CV with Tagline (NEW! ✅)                             │
│  ├── Check location: "Riyadh, Saudi Arabia"                            │
│  │   → Matches MIDDLE_EAST list                                         │
│  │   → Add tagline: "Available for International Relocation in 2 mos"  │
│  ├── Apply color: #475569 (dark greyish blue) ✅                        │
│  └── Output:                                                             │
│                                                                          │
│      # Tariq Alahdab                                                     │
│      *Available for International Relocation in 2 months* ✅            │
│      tariq@example.com | +49... | linkedin.com/in/tariq                │
│                                                                          │
│      ## Profile                                                          │
│      Engineering leader with 15+ years building high-performing teams...│
│                                                                          │
│      ## Core Competencies                                               │
│      **Cloud Platform Engineering**: AWS, Lambda, Serverless, Terraform │
│      **Backend Architecture**: Python, Microservices, Node.js, DDD      │
│      **Technical Leadership**: Technical Leadership, Mentoring, SCRUM   │
│                                                                          │
│      (NO PHP! NO Java! All skills grounded in master-cv! ✅)            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## STAR Format: Before vs After

### Current (Missing Structure)

```
❌ Generic Bullet (No STAR):
"Led migration to microservices architecture, improving system reliability"

Problems:
- No challenge/situation context
- No mention of HOW (skills used)
- Result is vague ("improving")
```

### Proposed (STAR-Compliant)

```
✅ STAR Bullet:
"Facing 30% annual increase in system outages due to monolithic architecture
[CHALLENGE], led 12-month migration to event-driven microservices [TASK] using
AWS Lambda, EventBridge, and Python [ACTION with skills mentioned], achieving
75% incident reduction and zero downtime for 3 years [RESULT]."

Structure:
- CHALLENGE: "Facing 30% annual increase..."
- TASK: "led 12-month migration..."
- ACTION: "using AWS Lambda, EventBridge, and Python" ← Skills explicit!
- RESULT: "75% incident reduction and zero downtime for 3 years" ← Quantified!
```

---

## Category Generation: Examples

### Example 1: Machine Learning Engineer JD

**JD Keywords**: TensorFlow, PyTorch, Python, AWS, MLOps, Model Deployment

**Current Output** (Generic):
- Leadership: Team Leadership, Mentorship
- Technical: Python, TensorFlow, Machine Learning
- Platform: AWS, Kubernetes
- Delivery: Agile, CI/CD

**Proposed Output** (JD-Specific):
- **Machine Learning Engineering**: Python, TensorFlow *(if in master-cv)*
- **Cloud & MLOps**: AWS, Lambda *(if in master-cv)*
- **Technical Leadership**: Mentoring, SCRUM

---

### Example 2: Director of Engineering JD

**JD Keywords**: Organizational Leadership, Engineering Strategy, Team Scaling, Agile

**Current Output** (Generic):
- Leadership: Team Leadership, Hiring
- Technical: Python, Microservices
- Platform: AWS, Kubernetes
- Delivery: Agile, Scrum

**Proposed Output** (JD-Specific):
- **Engineering Leadership**: Team Leadership, Hiring, Mentoring
- **Organizational Strategy**: SCRUM, Process Improvement
- **Technical Foundation**: Python, AWS, Microservices

---

## Hallucination Prevention: Step-by-Step

### Current Flow (Allows Hallucinations)

```
1. Start with hardcoded list: ["Python", "Java", "PHP", "Ruby", ...]
2. Check if skill appears in bullets
3. If yes → Add to CV
4. PROBLEM: "PHP" might appear in bullet due to:
   - LLM hallucination in bullet generation
   - False positive match (e.g., "API as PHP endpoint" in JD description)
5. RESULT: CV claims PHP skill without master-cv evidence
```

### Proposed Flow (Prevents Hallucinations)

```
1. Load skills ONLY from master-cv:
   master_cv_skills = {"nodejs", "lambda", "aws", "python", ...}
   (NO "PHP", NO "Java")

2. Filter JD keywords through master-cv:
   jd_keywords = ["Kubernetes", "AWS", "Python", "PHP"]
   matched = [kw for kw in jd_keywords if kw.lower() in master_cv_skills]
   → matched = ["AWS", "Python"]
   (Kubernetes not in master-cv → SKIP)
   (PHP not in master-cv → SKIP)

3. Generate categories using ONLY matched skills

4. Validate each skill has evidence in bullets

5. RESULT: 100% grounded CV, no hallucinations possible
```

---

## Data Flow Comparison

### Current (Broken)

```
JD Keywords → Hardcoded Skill Lists → Pattern Matching → 4 Static Categories
                                ↑
                          (Includes PHP, Java)
                                ↓
                          ❌ Hallucinated CV
```

### Proposed (Fixed)

```
JD Keywords → Master-CV Skills → Skill Matching → LLM Category Gen → Evidence Validation → ✅ Grounded CV
                  ↑                                      ↑                    ↑
            (Ground Truth)                      (JD-Specific)         (Bullet-Verified)
```

---

## Implementation Risk vs Reward

### Option A: Minimal Patch
```
Risk:     ██░░░░░░░░ (Low)
Reward:   ████░░░░░░ (Medium)
Time:     1-2 days
Fixes:    P0-1 only (hallucinations)
Leaves:   P0-2, P0-3 unresolved
```

### Option B: Full Rewrite (Recommended)
```
Risk:     ████░░░░░░ (Medium)
Reward:   ██████████ (High)
Time:     5 days
Fixes:    P0-1, P0-2, P0-3, P1-1, P1-2
Result:   Production-grade, JD-tailored CVs
```

---

## Success Criteria

### Before (Current State)

- ❌ Core Competencies include PHP, Java (not in master-cv)
- ❌ Categories always: Leadership, Technical, Platform, Delivery
- ❌ Bullets lack explicit skill mentions
- ❌ No relocation tagline for Middle East jobs
- ⚠️ Green color scheme

### After (Proposed State)

- ✅ All skills sourced from master-cv (zero hallucinations)
- ✅ Categories tailored to JD (e.g., "Cloud Platform Engineering")
- ✅ Bullets follow STAR format with explicit skills
- ✅ Dynamic tagline for relocation
- ✅ Dark greyish blue color scheme

---

*For detailed implementation steps, see `/reports/agents/job-search-architect/2025-11-30-cv-generation-fix-architecture-analysis.md`*
