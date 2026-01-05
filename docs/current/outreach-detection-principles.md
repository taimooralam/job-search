# Outreach Detection and Contact Classification Principles

This document describes the algorithms and principles used to detect, classify, and prioritize contacts for professional outreach during job applications.

## Contact Type Classification

### Priority Order (Highest to Lowest)

| Type | Definition | Keywords | Priority |
|------|------------|----------|----------|
| `executive` | C-suite leadership | cto, ceo, cfo, chief, founder, president | Highest |
| `vp_director` | Senior leaders | vp, vice president, director, head of, svp, principal director | High |
| `hiring_manager` | Direct decision-makers | hiring manager, engineering manager, team lead, tech lead, manager | Medium-High |
| `recruiter` | Talent acquisition | recruiter, talent acquisition, sourcer, hr business partner, people partner | Medium |
| `peer` | Individual contributors | staff engineer, principal engineer, senior engineer, architect, developer | Lower |

### Classification Implementation

**Location:** `/src/layer5/people_mapper.py:206-227`

```python
def classify_contact_type(role: str) -> str:
    """
    Priority order: executive > vp_director > hiring_manager > recruiter > peer
    Checks role title for keywords, returns first match or defaults to "peer"
    """
```

**Classification Logic:**
1. Normalize role title to lowercase
2. Check against keyword lists in priority order
3. Return first matching contact type
4. Default to "peer" if no keywords match

---

## Primary vs Secondary Contacts

### Primary Contacts (4-6 maximum)
- **Purpose:** Directly relevant to hiring decision
- **Types:** hiring_manager, recruiter, department head, team lead
- **Priority:** First outreach targets

### Secondary Contacts (4-6 maximum)
- **Purpose:** Cross-functional support and referrals
- **Types:** product managers, designers, peers, executives, stakeholders
- **Use:** Warm introductions, additional signals

---

## Detection Signals

### Title-Based Pattern Matching

| Pattern | Classification | Confidence |
|---------|---------------|------------|
| Contains "Chief", "CEO", "CTO", "CFO" | `executive` | High |
| Contains "VP", "Vice President", "Director" | `vp_director` | High |
| Contains "Manager" + team context | `hiring_manager` | Medium |
| Contains "Recruiter", "Talent", "HR" | `recruiter` | High |
| Contains "Engineer", "Developer", "Architect" | `peer` | Medium |

### Contact Data Structure

```python
class Contact:
    name: str                    # Real name or role-based identifier
    role: str                    # Job title
    linkedin_url: str            # Profile URL
    contact_type: str            # Classification result
    why_relevant: str            # Reason for outreach (grounded in JD)
    recent_signals: List[str]    # Recent posts, promotions, projects
    is_synthetic: bool           # True if placeholder (no real person found)
```

---

## Message Tailoring by Contact Type

### Format and Length Constraints

| Message Type | Target | Constraint |
|--------------|--------|------------|
| LinkedIn Connection | All types | 300 characters max (enforced by LinkedIn) |
| LinkedIn InMail | All types | 400-600 characters |
| Professional Email | All types | 95-205 words |
| InMail Subject | Mobile | 25-30 characters |

### Contact Type Strategies

#### Executive (`executive`)
- **Style:** Industry trends, extreme brevity
- **Length:** <100 words
- **Focus:** Market positioning, strategic vision alignment
- **Avoid:** Technical details, lengthy explanations

#### VP/Director (`vp_director`)
- **Style:** Strategic outcomes, business impact
- **Length:** 50-150 words maximum
- **Focus:** Company initiatives, long-term value
- **Avoid:** Implementation details

#### Hiring Manager (`hiring_manager`)
- **Style:** Peer-level, technical depth
- **Length:** Medium (full email structure)
- **Focus:** Team fit, specific project examples, skills alignment
- **Key:** Reference their team's projects/challenges

#### Recruiter (`recruiter`)
- **Style:** ATS-friendly, keyword-rich
- **Length:** Standard (95-205 words)
- **Focus:** Quantified achievements, JD keyword matching
- **Key:** Compliance with job requirements, specific metrics

#### Peer (`peer`)
- **Style:** Technical credibility, collaborative
- **Length:** Medium
- **Focus:** Shared challenges, technical depth, mutual learning
- **Key:** Partnership opportunities, technical discussions

---

## MENA Cultural Adaptations

### Region Detection

**Location:** `/src/common/mena_detector.py`

**Detection Signals (priority order):**
1. Explicit country/city in location (highest confidence)
2. Known company/project indicators (medium confidence)
3. Keywords in JD text (lowest confidence)

**Supported Regions:**
- **GCC (highest priority):** Saudi Arabia, UAE, Qatar, Kuwait, Oman, Bahrain
- **Broader MENA:** Egypt, Jordan, Lebanon, Morocco, Tunisia

### Saudi Arabia Indicators
- **Mega-projects:** NEOM, The Line, Oxagon, Trojena, Red Sea, Qiddiya, Diriyah
- **Companies:** Aramco, SABIC, STC, Misk Foundation, ACWA Power, PIF

### MENA-Specific Guidelines

| Aspect | Standard | MENA Adaptation |
|--------|----------|-----------------|
| Greeting | "Hi [Name]" | "Dear Mr./Ms. [Name]" |
| Opening | Casual | "As-salaam Alaykum" (Saudi only) |
| Closing | "Best regards" | "Shukran for your time" (Saudi) |
| Formality | Standard | Higher (title + first name) |
| Timeline | Normal | 1.5x multiplier (slower hiring) |

### Vision Alignment
- **Saudi Arabia:** Reference Vision 2030 when experience aligns
- **UAE:** Reference diversification, innovation, smart city initiatives
- **Qatar:** Reference Qatar National Vision 2030

---

## Message Structure (6-Step Mandatory)

### Email Structure

1. **Subject Line:** Job title + your name + reference
   - Example: "Application - Principal Engineer - Taimoor Alam"

2. **Greeting:** Professional and direct
   - "Dear Mr./Ms. [Name]," or "Dear Hiring Team,"

3. **First 2 Lines = VALUE** (not life story)
   - "I'm a [role] with [X years] in [industry]."
   - "I help companies achieve [specific result]."

4. **3 Proof Bullets** (quantified, scannable)
   - "Delivered ___ project worth ___"
   - "Reduced ___ by ___% / Increased ___ by ___%"
   - "Led team of ___ / Managed ___ stakeholders"

5. **Close with Clear Action**
   - "I'd welcome a 15-minute call to discuss how I can support your team."
   - Include Calendly link

6. **Signature:** Full name + phone + LinkedIn URL

### "Already Applied" Framing (Required)

Every message MUST reference prior application:
- **adding_context:** "I submitted my application and wanted to share context..."
- **value_add:** "Following up on my application—I came across..."
- **specific_interest:** "I applied for [Role] because [specific reason]..."

---

## Quality Gates

### Content Validation

| Check | Requirement | Action |
|-------|-------------|--------|
| No Emojis | Zero emoji characters | Fail if present |
| No Placeholders | Only [Your Name] allowed | Fail if [Company], [Role] found |
| Company Grounding | Mention real company from STAR records | Fail if generic |
| Signature | "Best. Taimoor Alam" format | Fail if missing |
| Character Limits | LinkedIn: 300, InMail: 400-600 | Truncate gracefully |

### Hallucination Prevention
- Outreach MUST cite candidate's actual background
- Company names must exist in master-cv.md or STAR records
- Claims must be grounded in provided context

---

## API Integration Points

### Generate Outreach
```
POST /api/jobs/{job_id}/contacts/{contact_type}/{contact_index}/generate-outreach
Body: { tier: "fast|balanced|quality", message_type: "connection|inmail" }
```

### Model Tiers
- **FAST:** gpt-4o-mini (quick, cheap)
- **BALANCED:** gpt-4o (quality/cost balance)
- **QUALITY:** claude-sonnet or claude-opus-4.5 (best quality, MENA awareness)

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `/src/layer5/people_mapper.py` | Contact discovery, classification |
| `/src/services/outreach_service.py` | Per-contact outreach generation |
| `/src/layer6/outreach_generator.py` | Validation, constraint enforcement |
| `/src/layer6_v2/prompts/outreach_prompts.py` | Prompt templates, MENA awareness |
| `/src/common/mena_detector.py` | Region detection, cultural context |
| `/runner_service/routes/contacts.py` | REST API endpoints |

---

## Future Enhancements

1. **ML-based role classification** - Train classifier on LinkedIn titles for higher accuracy
2. **Influence scoring** - Rank contacts by hiring influence based on seniority and team proximity
3. **Network proximity** - Factor in shared connections for warm introduction opportunities
4. **Engagement signals** - Track response rates by contact type to optimize targeting
5. **A/B message testing** - Test different approaches per contact type
