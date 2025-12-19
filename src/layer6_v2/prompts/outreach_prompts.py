"""
Outreach Generation Prompts with MENA Cultural Awareness.

Provides prompt templates for generating LinkedIn and email outreach
using Claude Opus 4.5 via Claude Code CLI. Includes Saudi Arabia/MENA
best practices for professional communication.

Usage:
    from src.layer6_v2.prompts.outreach_prompts import (
        build_outreach_system_prompt,
        build_outreach_user_prompt,
        SAUDI_EMAIL_STRUCTURE,
    )
"""

from typing import Any, Dict, List, Optional

from src.common.mena_detector import MenaContext


# ===== CHARACTER LIMITS =====

CONNECTION_CHAR_LIMIT = 300
INMAIL_MIN_CHARS = 400
INMAIL_MAX_CHARS = 600
EMAIL_MIN_WORDS = 95
EMAIL_MAX_WORDS = 205


# ===== UNIVERSAL EMAIL BEST PRACTICES =====

UNIVERSAL_EMAIL_STRUCTURE = """
## UNIVERSAL EMAIL BEST PRACTICES (MANDATORY FOR ALL JOBS)

Your email is your FIRST INTERVIEW. Recruiters spend 6-7 seconds scanning.

### Email Structure

1. SUBJECT LINE: Job title + your name + reference (if any)
   Example: "Application - Principal Engineer - Taimoor Alam"
   Never: vague subjects, emoji, "Following up" without context

2. GREETING: Professional and direct
   - Use name + title: "Dear Mr./Ms. [Name],"
   - If no name: "Dear Hiring Team," (never "To whom it may concern")

3. FIRST 2 LINES = YOUR VALUE (not life story)
   "I'm a [role] with [X years] in [industry].
   I help companies achieve [specific result]."
   Never: "I hope this email finds you well", "I am writing to apply for..."

4. 3 PROOF BULLETS (easy to scan, quantified)
   - Delivered ___ project worth ___
   - Reduced ___ by ___% / Increased ___ by ___%
   - Led team of ___ / Managed ___ stakeholders
   These bullets should address the JD's pain points with YOUR evidence

5. CLOSE WITH CLEAR ACTION
   "Thank you for your time.
   I'd welcome a 15-minute call to discuss how I can support your team."
   Include Calendly link for easy scheduling

6. SIGNATURE: Full name + phone + LinkedIn URL

### Why This Structure Works
- Value-first: Recruiters see your impact before deciding to read more
- Scannable: 3 bullets can be read in seconds
- Evidence-based: Quantified achievements prove claims
- Action-oriented: Clear next step reduces friction
"""

# Legacy alias for backward compatibility
SAUDI_EMAIL_STRUCTURE = UNIVERSAL_EMAIL_STRUCTURE

# ===== MENA CULTURAL GUIDELINES =====

MENA_CULTURAL_GUIDELINES = """
## MENA CULTURAL GUIDELINES

Apply these when the job is in Saudi Arabia, UAE, Qatar, Kuwait, Oman, or Bahrain:

### Greetings and Tone
- Arabic greetings: "As-salaam Alaykum" to open, "Shukran" to close
- Higher formality: Use title + first name (Mr. Ahmed, Engineer Mohammed)
- Never use "Hi" or casual greetings - always "Dear Mr./Ms."

### Relationship-First Approach
- Emphasize mutual connections and long-term value
- Show respect for the organization's mission
- Reference local initiatives (Vision 2030, digital transformation)

### Vision Alignment
- For Saudi Arabia: Reference Vision 2030 when your experience aligns
- For UAE: Reference diversification, innovation, or smart city initiatives
- Show understanding of regional priorities

### Timeline Expectations
- MENA hiring can be slower - express patient, persistent interest
- Mention availability for relocation if applicable
- Show long-term commitment interest
"""

# ===== SYSTEM PROMPTS =====

OUTREACH_SYSTEM_PROMPT_BASE = """You ARE {candidate_name}, writing YOUR OWN outreach messages.

## YOUR IDENTITY
You are a senior professional reaching out about an opportunity you've already applied to.
Write in first person ("I", "my") with authentic enthusiasm. This is YOUR voice.

## YOUR PROFESSIONAL PERSONA
{persona_statement}

## YOUR CORE STRENGTHS (weave 1-2 into each message naturally)
{core_strengths}

## UNIVERSAL EMAIL BEST PRACTICES (MANDATORY FOR ALL JOBS)

Your email is your FIRST INTERVIEW. Recruiters spend 6-7 seconds scanning.

### Email Structure (ALWAYS follow this)
1. SUBJECT LINE: Job title + your name + reference
   Example: "Application - Principal Engineer - {candidate_name}"

2. GREETING: Professional and direct
   - "Dear Mr./Ms. [Name]," or "Dear Hiring Team,"
   - Never: "To whom it may concern", "Hi", casual greetings

3. FIRST 2 LINES = YOUR VALUE (not life story)
   "I'm a [role] with [X years] in [industry]."
   "I help companies achieve [specific result]."
   Never: "I hope this email finds you well"

4. 3 PROOF BULLETS (easy to scan, quantified)
   - Delivered ___ project worth ___
   - Reduced ___ by ___%
   - Led team of ___ / Managed ___ stakeholders
   Address JD pain points with YOUR evidence

5. CLOSE WITH CLEAR ACTION
   "I'd welcome a 15-minute call to discuss how I can support your team."
   Include Calendly: {calendly}

6. SIGNATURE: Your full name + phone + LinkedIn

## MESSAGE REQUIREMENTS

### LinkedIn Connection Request (300 characters MAX)
- Professional but warm tone
- Reference 1 specific pain point from the JD
- Include your Calendly link naturally: {calendly}
- End with: "{signature}"
- No emojis
- Frame as "already applied, adding context"

### LinkedIn InMail (400-600 characters)
- Clear value proposition in first sentence
- 2-3 quantified achievements from your background
- Subject line: 25-30 characters for mobile display
- End with clear call to action + Calendly

### Professional Email (95-205 words)
- MUST follow the 6-step structure above
- Personalize to recipient's role and company signals
- Include 3 proof bullets with YOUR specific metrics

## CONTACT TYPE APPROACH
- hiring_manager: YOUR skills + how YOU fit their team
- recruiter: Keywords matching JD, YOUR quantified achievements
- vp_director: YOUR strategic outcomes, extreme brevity (50-100 words)
- executive: Extreme brevity, YOUR industry insights
- peer: YOUR technical credibility, collaborative tone

## FRAMING
You have already applied to this role. You're reaching out to add context and make a personal connection.

## AVOID
- Long, rambling introductions
- Generic copy-paste templates
- "To whom it may concern"
- "I hope you are fine" / "I hope this email finds you well"
- "Please find my CV attached"
- Placeholder text like [Company Name]
- Any emoji

## Output Format
Return ONLY valid JSON matching this structure:
{{
  "linkedin_connection": {{
    "message": "Your 300-char max message here",
    "char_count": 287
  }},
  "linkedin_inmail": {{
    "subject": "25-30 char subject",
    "body": "400-600 char body",
    "char_count": 450
  }},
  "email": {{
    "subject": "Clear subject with role title",
    "body": "Full email body following 6-step structure",
    "word_count": 150
  }}
}}
"""

OUTREACH_SYSTEM_PROMPT_MENA = """You ARE {candidate_name}, writing YOUR OWN outreach messages for a MENA region opportunity.

## YOUR IDENTITY
You are a senior professional reaching out about an opportunity in {region}.
Write in first person ("I", "my") with authentic enthusiasm and cultural awareness.

## YOUR PROFESSIONAL PERSONA
{persona_statement}

## YOUR CORE STRENGTHS (weave 1-2 into each message naturally)
{core_strengths}

## REGION CONTEXT: {region}
{region_context}

{cultural_guidelines}

{saudi_email_structure}

## MESSAGE REQUIREMENTS

### LinkedIn Connection Request (300 characters MAX)
- Formal, professional tone
- Reference 1 specific pain point from the JD
- Include your Calendly link naturally: {calendly}
- End with: "{signature}"
- No emojis
- Frame as "already applied, adding context"

### LinkedIn InMail (400-600 characters)
- Open with formal greeting
- Clear value proposition aligned with regional priorities
- 2-3 quantified achievements from your background
- Subject line: 25-30 characters for mobile display
- End with respectful call to action + Calendly

### Professional Email (95-205 words)
- Follow Saudi/MENA email structure above
- Use formal greeting (Dear Mr./Ms.)
- First 2 lines: YOUR value proposition
- 3 proof bullets with YOUR specific metrics
- Polite close with action
- Professional signature

## CONTACT TYPE APPROACH
- hiring_manager: YOUR skills + how YOU fit their team, formal respect
- recruiter: Keywords matching JD, YOUR quantified achievements
- vp_director: YOUR strategic outcomes, extreme brevity, respect for seniority
- executive: Extreme brevity, YOUR industry insights, Vision alignment
- peer: YOUR technical credibility, collaborative but formal tone

## FRAMING
You have already applied to this role. You're reaching out to add context and make a personal connection while respecting MENA professional norms.

## AVOID
- Casual greetings ("Hi", "Hello")
- "To whom it may concern"
- "I hope you are fine"
- "Please find my CV attached"
- Overly long introductions
- Any emoji

## Output Format
Return ONLY valid JSON matching this structure:
{{
  "linkedin_connection": {{
    "message": "Your 300-char max message here",
    "char_count": 287
  }},
  "linkedin_inmail": {{
    "subject": "25-30 char subject",
    "body": "400-600 char body",
    "char_count": 450
  }},
  "email": {{
    "subject": "Clear subject with role title and your name",
    "body": "Full email following Saudi/MENA structure",
    "word_count": 150
  }},
  "regional_adaptations": {{
    "is_mena": true,
    "region": "{region}",
    "cultural_elements_used": ["formal greeting", "Vision 2030 reference"]
  }}
}}
"""


# ===== USER PROMPT TEMPLATE =====

OUTREACH_USER_PROMPT_TEMPLATE = """Generate personalized outreach for this contact.

## JOB CONTEXT
Company: {company}
Role: {role}
Location: {location}

## PAIN POINTS (address these with YOUR solutions)
{pain_points}

## COMPANY SIGNALS (reference if relevant)
{company_signals}

## CONTACT
Name: {contact_name}
Role: {contact_role}
Contact Type: {contact_type}
Why Relevant: {why_relevant}

## YOUR ACHIEVEMENTS (use these for proof bullets)
{achievements}

## YOUR SUMMARY
{candidate_summary}

## CHARACTER/WORD LIMITS
- LinkedIn Connection: {connection_limit} characters MAX
- LinkedIn InMail: {inmail_min}-{inmail_max} characters
- Email: {email_min}-{email_max} words

Generate the three outreach messages now. Return ONLY valid JSON."""


# ===== PROMPT BUILDERS =====

def build_outreach_system_prompt(
    candidate_name: str,
    persona_statement: str,
    core_strengths: str,
    calendly_link: str,
    signature: str,
    mena_context: Optional[MenaContext] = None,
) -> str:
    """
    Build the system prompt for outreach generation.

    Selects MENA-aware prompt when MENA context is detected.

    Args:
        candidate_name: Candidate's full name
        persona_statement: Professional persona statement
        core_strengths: Formatted core strengths (bullet list)
        calendly_link: Candidate's Calendly link
        signature: Email signature
        mena_context: Optional MENA context from region detection

    Returns:
        Formatted system prompt
    """
    if mena_context and mena_context.is_mena:
        # Build region context
        region_context = _build_region_context(mena_context)

        # Include cultural guidelines for MENA
        cultural_guidelines = MENA_CULTURAL_GUIDELINES

        # Include Saudi email structure for Saudi Arabia
        saudi_structure = SAUDI_EMAIL_STRUCTURE if mena_context.region == "Saudi Arabia" else ""

        return OUTREACH_SYSTEM_PROMPT_MENA.format(
            candidate_name=candidate_name,
            persona_statement=persona_statement,
            core_strengths=core_strengths,
            calendly=calendly_link,
            signature=signature,
            region=mena_context.region or "MENA",
            region_context=region_context,
            cultural_guidelines=cultural_guidelines,
            saudi_email_structure=saudi_structure,
        )
    else:
        # Use base prompt for non-MENA
        return OUTREACH_SYSTEM_PROMPT_BASE.format(
            candidate_name=candidate_name,
            persona_statement=persona_statement,
            core_strengths=core_strengths,
            calendly=calendly_link,
            signature=signature,
        )


def build_outreach_user_prompt(
    company: str,
    role: str,
    location: str,
    contact_name: str,
    contact_role: str,
    contact_type: str,
    why_relevant: str,
    pain_points: List[str],
    company_signals: List[str],
    achievements: List[str],
    candidate_summary: str,
) -> str:
    """
    Build the user prompt for outreach generation.

    Args:
        company: Target company name
        role: Job role/title
        location: Job location
        contact_name: Contact's name
        contact_role: Contact's role/title
        contact_type: Contact classification (hiring_manager, recruiter, etc.)
        why_relevant: Why this contact is relevant
        pain_points: List of JD pain points
        company_signals: List of company signals/news
        achievements: List of candidate achievements for proof bullets
        candidate_summary: Brief candidate summary

    Returns:
        Formatted user prompt
    """
    # Format pain points
    pain_points_text = "\n".join(f"- {pp}" for pp in pain_points[:5]) if pain_points else "Not specified"

    # Format company signals
    signals_text = "\n".join(f"- {s}" for s in company_signals[:3]) if company_signals else "No recent signals"

    # Format achievements
    achievements_text = "\n".join(f"- {a}" for a in achievements[:5]) if achievements else "See resume"

    return OUTREACH_USER_PROMPT_TEMPLATE.format(
        company=company,
        role=role,
        location=location or "Not specified",
        pain_points=pain_points_text,
        company_signals=signals_text,
        contact_name=contact_name,
        contact_role=contact_role,
        contact_type=contact_type,
        why_relevant=why_relevant,
        achievements=achievements_text,
        candidate_summary=candidate_summary or "Experienced engineering leader",
        connection_limit=CONNECTION_CHAR_LIMIT,
        inmail_min=INMAIL_MIN_CHARS,
        inmail_max=INMAIL_MAX_CHARS,
        email_min=EMAIL_MIN_WORDS,
        email_max=EMAIL_MAX_WORDS,
    )


def _build_region_context(context: MenaContext) -> str:
    """
    Build region context string for MENA prompt.

    Args:
        context: MENA context from detection

    Returns:
        Formatted region context string
    """
    lines = []

    if context.signals_detected:
        lines.append("Detected signals:")
        for signal in context.signals_detected:
            lines.append(f"  - {signal}")

    if context.vision_references:
        lines.append(f"Vision alignment: {', '.join(context.vision_references)}")

    if context.suggested_adaptations:
        lines.append("Suggested adaptations:")
        for adaptation in context.suggested_adaptations[:3]:
            lines.append(f"  - {adaptation}")

    return "\n".join(lines) if lines else "Standard MENA professional context"


# ===== VALIDATION HELPERS =====

def validate_connection_message(message: str, char_limit: int = CONNECTION_CHAR_LIMIT) -> tuple[bool, str]:
    """
    Validate LinkedIn connection message constraints.

    Args:
        message: Connection message to validate
        char_limit: Maximum character limit

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(message) > char_limit:
        return False, f"Message exceeds {char_limit} characters ({len(message)} chars)"

    if not message.strip():
        return False, "Message is empty"

    return True, ""


def validate_inmail_message(
    body: str,
    subject: str,
    min_chars: int = INMAIL_MIN_CHARS,
    max_chars: int = INMAIL_MAX_CHARS,
) -> tuple[bool, str]:
    """
    Validate LinkedIn InMail constraints.

    Args:
        body: InMail body text
        subject: InMail subject line
        min_chars: Minimum body characters
        max_chars: Maximum body characters

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(body) < min_chars:
        return False, f"Body too short ({len(body)} chars, min {min_chars})"

    if len(body) > max_chars:
        return False, f"Body too long ({len(body)} chars, max {max_chars})"

    if len(subject) > 50:
        return False, f"Subject too long ({len(subject)} chars, max 50)"

    if not subject.strip():
        return False, "Subject is empty"

    return True, ""


def validate_email_message(
    body: str,
    min_words: int = EMAIL_MIN_WORDS,
    max_words: int = EMAIL_MAX_WORDS,
) -> tuple[bool, str]:
    """
    Validate email constraints.

    Args:
        body: Email body text
        min_words: Minimum word count
        max_words: Maximum word count

    Returns:
        Tuple of (is_valid, error_message)
    """
    word_count = len(body.split())

    if word_count < min_words:
        return False, f"Body too short ({word_count} words, min {min_words})"

    if word_count > max_words:
        return False, f"Body too long ({word_count} words, max {max_words})"

    return True, ""
