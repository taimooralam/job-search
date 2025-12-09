# JD Annotation Calibration Rubric

This document provides calibrated definitions and examples for the JD annotation system.
Use these rubrics to ensure consistent scoring and prevent drift over time.

## Purpose

Consistent annotation scoring is critical because:
1. **Boost calculations** use these scores to prioritize CV bullets
2. **ATS optimization** depends on accurate requirement classification
3. **Gap analysis** identifies what needs mitigation
4. **Outcome tracking** measures effectiveness by annotation profile

---

## Relevance Levels (5-Level Scale)

### Core Strength (3.0x boost)

**Definition:** Candidate has 5+ years of direct experience; could teach others; this is a defining characteristic of their professional identity.

| Example JD Text | Correct Assessment | Reasoning |
|-----------------|-------------------|-----------|
| "Lead engineering teams of 10+" | Core Strength | Candidate led 15-person team for 4 years |
| "Expert in Python with production systems" | Core Strength | Candidate has 8 years Python, architected multiple systems |
| "Drive technical strategy" | Core Strength | Candidate defined tech roadmap at 3 companies |

**When to use:**
- The skill/experience is mentioned in candidate's LinkedIn headline
- Candidate has keynote talks or blog posts about this topic
- Candidate would be comfortable teaching a workshop on this
- This is a top-3 skill on the candidate's resume

**Validation rule:** Must link at least one STAR story as evidence.

---

### Extremely Relevant (2.0x boost)

**Definition:** Candidate has 3-5 years of experience; used daily in recent role; directly applicable without framing.

| Example JD Text | Correct Assessment | Reasoning |
|-----------------|-------------------|-----------|
| "Experience with Kubernetes" | Extremely Relevant | Candidate deploys to K8s weekly, 3 years experience |
| "Agile/Scrum methodology" | Extremely Relevant | Candidate ran sprint ceremonies for 4 years |
| "Mentored junior engineers" | Extremely Relevant | Candidate has 5 direct reports, regular 1:1s |

**When to use:**
- Skill appears in current or previous job description
- Candidate uses this skill regularly (weekly+)
- Could be verified in a technical interview without preparation
- Strong but not defining characteristic

---

### Relevant (1.5x boost)

**Definition:** Candidate has 1-3 years of experience; transferable with minor framing or context.

| Example JD Text | Correct Assessment | Reasoning |
|-----------------|-------------------|-----------|
| "CI/CD pipeline expertise" | Relevant | Candidate built Jenkins pipelines (JD mentions GitHub Actions) |
| "Experience with AWS" | Relevant | Candidate has 2 years GCP, principles transfer |
| "Product-minded engineering" | Relevant | Candidate has shipped features, less PM collaboration |

**When to use:**
- Adjacent technology/methodology
- Skill used periodically (monthly)
- Would need brief preparation for technical discussion
- Transferable with clear framing

**Tip:** Add a reframe note explaining how the candidate's experience maps to the requirement.

---

### Tangential (1.0x boost)

**Definition:** Less than 1 year of experience; loosely related skill; requires significant reframing.

| Example JD Text | Correct Assessment | Reasoning |
|-----------------|-------------------|-----------|
| "GraphQL API design" | Tangential | Candidate designed REST APIs only |
| "Mobile development experience" | Tangential | Candidate built responsive web apps, no native mobile |
| "Machine learning background" | Tangential | Candidate used ML APIs, never trained models |

**When to use:**
- Related concept but different execution
- Touched briefly in a project
- Would need learning curve to apply fully
- Only include if other skills are strong

---

### Gap (0.3x penalty)

**Definition:** No experience; would need training; this requirement is not met.

| Example JD Text | Correct Assessment | Reasoning |
|-----------------|-------------------|-----------|
| "AWS Certified Solutions Architect" | Gap | Candidate has no AWS certifications |
| "5+ years people management" | Gap | Candidate has 2 years (3-year gap) |
| "Healthcare/HIPAA experience" | Gap | Candidate has no regulated industry experience |

**When to use:**
- Candidate genuinely lacks this skill/experience
- No reasonable way to frame existing experience
- Would require formal training or significant time to acquire

**Validation rule:** Must include a mitigation strategy in the reframe note.

**Mitigation strategies:**
- "Currently pursuing certification, expected completion Q2"
- "While I haven't worked in healthcare, my FinTech experience with SOX compliance demonstrates..."
- "I have 2 years direct experience + 3 years in adjacent tech lead roles where I..."

---

## Requirement Types

### Must-Have (1.5x boost multiplier)

**Definition:** Explicitly required; using words like "required", "must have", "essential".

| Indicator Phrases |
|-------------------|
| "Must have..." |
| "Required: ..." |
| "X years of experience required" |
| "Essential skills include..." |
| "Candidates must demonstrate..." |

**Impact:** Must-have + Gap = Critical gap requiring strong mitigation or reconsider application.

---

### Nice-to-Have (1.0x boost multiplier)

**Definition:** Preferred but not required; tie-breaker between candidates.

| Indicator Phrases |
|-------------------|
| "Preferred: ..." |
| "Nice to have..." |
| "Experience with X is a plus" |
| "Bonus points for..." |
| "Ideally you have..." |

**Impact:** Can de-prioritize if other requirements are strong.

---

### Disqualifier (0.0x boost multiplier)

**Definition:** Candidate explicitly doesn't want this requirement, regardless of ability.

| Examples |
|----------|
| "Requires 50% travel" (candidate wants remote) |
| "On-call rotation required" (candidate has constraints) |
| "Relocation to X required" (candidate can't relocate) |

**Impact:** Should seriously reconsider application. Used sparingly.

---

### Neutral (1.0x boost multiplier)

**Definition:** Neither required nor preferred; context or culture statement.

| Examples |
|----------|
| "Fast-paced environment" |
| "Collaborative team culture" |
| "Growth mindset" |

**Impact:** No boost impact; informational only.

---

## Section Coverage Checklist

For complete annotation coverage, ensure at least 1 annotation per section:

| Section | Minimum Annotations | Focus |
|---------|---------------------|-------|
| Responsibilities | 3-5 | Match to STAR stories |
| Qualifications | 3-5 | Must-haves first |
| Nice-to-Haves | 1-2 | Low priority |
| Technical Skills | 2-4 | Exact keyword matches |

**Progress bar targets:**
- 70%+ coverage = Ready for CV generation
- 50-70% = Review gaps
- <50% = Incomplete annotation

---

## Annotation Quality Checklist

Before saving annotations, verify:

- [ ] All core_strength annotations have at least one STAR link
- [ ] All gap annotations have a mitigation strategy
- [ ] Must-have gaps are flagged and addressed
- [ ] ATS keywords include variants (e.g., Kubernetes/K8s)
- [ ] Each JD section has at least 1 annotation
- [ ] No overlapping annotations on same text

---

## Examples: Full Annotation Flow

### Example 1: Strong Match

**JD Text:** "Lead a team of 8-12 engineers building real-time data pipelines"

**Annotation:**
- Type: skill_match
- Relevance: core_strength
- Requirement: must_have
- Matching Skill: "Team Leadership"
- STAR IDs: ["seven_one_streaming_platform", "prosiebensat1_ad_platform"]
- Keywords: ["real-time", "data pipeline", "team lead", "engineering manager"]
- Reframe: None needed

### Example 2: Gap with Mitigation

**JD Text:** "5+ years of experience with Kubernetes in production"

**Annotation:**
- Type: skill_match
- Relevance: gap
- Requirement: must_have
- Matching Skill: "Kubernetes"
- STAR IDs: []
- Keywords: ["Kubernetes", "K8s", "container orchestration"]
- Reframe: "I have 2 years hands-on K8s experience plus 5 years with Docker and container orchestration principles. Currently preparing for CKA certification."

### Example 3: Reframe Opportunity

**JD Text:** "Experience with AdTech platforms and RTB systems"

**Annotation:**
- Type: skill_match (with reframe)
- Relevance: extremely_relevant
- Requirement: nice_to_have
- Matching Skill: "Digital Advertising"
- STAR IDs: ["prosiebensat1_ad_platform"]
- Keywords: ["AdTech", "RTB", "real-time bidding", "programmatic"]
- Reframe From: "Video streaming platform with ad insertion"
- Reframe To: "Real-time advertising decision systems with millisecond latency requirements"

---

## Monthly Calibration Check

To prevent drift, monthly review:

1. Sample 10% of recent annotations
2. Re-score without looking at original scores
3. Compare: variance > 10% = recalibration needed
4. Update examples in this document if patterns shift

**Target:** <10% scoring variance between reviews.
