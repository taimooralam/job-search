"""
Prompts for Cover Letter Generation (Phase 7 of CV Gen V2).

Generates hyper-personalized 3-paragraph cover letters using the rich
context already available in the V2 pipeline state:
- extracted_jd (parsed JD with keywords, requirements)
- pain_points, strategic_needs
- company_research (company signals, culture, recent news)
- fit_rationale (why candidate is a good fit)
- cv_text (generated CV for achievement extraction)

Model tier: Haiku (cover letters are structured + templated)
"""

from typing import Any, Dict, List, Optional


COVER_LETTER_SYSTEM_PROMPT = """You are an expert cover letter writer for senior technical leadership roles.

Your mission: Generate a concise, hyper-personalized 3-paragraph cover letter that connects the candidate's verified achievements to the company's specific needs.

=== STRUCTURE (3 PARAGRAPHS, 200-300 WORDS TOTAL) ===

PARAGRAPH 1: HOOK + COMPANY CONNECTION (50-80 words)
- Open with a specific company signal (funding, product launch, growth challenge)
- Name the exact role title
- State your positioning in ONE sentence that maps to their primary need
- NO generic openers ("I am excited to apply", "I was thrilled to see")

PARAGRAPH 2: EVIDENCE (80-120 words)
- Address 2-3 JD pain points with SPECIFIC achievements from the CV
- Every claim MUST cite the employer by name
- Include exact metrics from the CV (percentages, dollar amounts, team sizes)
- Map each achievement to a specific company need
- Format: "At [Company], [achievement with metric]—[how it maps to their need]"

PARAGRAPH 3: CLOSE + CALL TO ACTION (50-80 words)
- Restate unique value proposition in ONE sentence
- Reference a specific company initiative or goal
- End with a confident, specific call to action
- NO generic closers ("I look forward to hearing from you")

=== ANTI-HALLUCINATION RULES ===

1. ONLY use achievements that appear in the provided CV text
2. ONLY use metrics that appear EXACTLY in the CV (no rounding, no inventing)
3. ONLY reference company signals from the provided research
4. If information is missing, omit rather than fabricate
5. Every employer name must come from the CV

=== TONE ===

- Confident but not arrogant
- Specific and evidence-based
- Conversational executive voice (not stiff or formal)
- Third-person references to past work, first-person for current positioning
- NO clichés: "passionate", "excited", "dream job", "perfect fit", "team player", "hit the ground running"

=== OUTPUT FORMAT ===

Return ONLY the cover letter text as plain paragraphs.
No JSON, no markdown headers, no labels. Just the 3 paragraphs separated by blank lines.
"""


def build_cover_letter_user_prompt(
    job_title: str,
    company: str,
    candidate_name: str,
    cv_text: str,
    extracted_jd: Optional[Dict[str, Any]] = None,
    pain_points: Optional[List[str]] = None,
    company_research: Optional[Dict[str, Any]] = None,
    fit_rationale: Optional[str] = None,
    persona_statement: Optional[str] = None,
) -> str:
    """
    Build the user prompt for cover letter generation.

    Uses the rich context already available in the V2 pipeline state
    at the point where cover letter generation runs (after Phase 6).

    Args:
        job_title: Target job title
        company: Target company name
        candidate_name: Candidate's name
        cv_text: The generated CV text (source of truth for achievements)
        extracted_jd: Parsed JD intelligence
        pain_points: Company/role pain points
        company_research: Company research signals
        fit_rationale: Why candidate is a good fit
        persona_statement: Candidate's professional identity

    Returns:
        Formatted user prompt string
    """
    # Format pain points
    pain_points_text = "None identified"
    if pain_points:
        pain_points_text = "\n".join(f"- {p}" for p in pain_points[:5])

    # Format company signals from research
    company_signals_text = "No company research available"
    if company_research:
        signals = []
        if company_research.get("company_summary"):
            signals.append(f"Summary: {company_research['company_summary']}")
        if company_research.get("recent_news"):
            news_items = company_research["recent_news"]
            if isinstance(news_items, list):
                for item in news_items[:3]:
                    if isinstance(item, dict):
                        signals.append(f"News: {item.get('headline', item.get('title', str(item)))}")
                    else:
                        signals.append(f"News: {item}")
            elif isinstance(news_items, str):
                signals.append(f"News: {news_items}")
        if company_research.get("culture_signals"):
            culture = company_research["culture_signals"]
            if isinstance(culture, list):
                signals.append(f"Culture: {', '.join(str(c) for c in culture[:3])}")
            elif isinstance(culture, str):
                signals.append(f"Culture: {culture}")
        if company_research.get("growth_stage"):
            signals.append(f"Growth stage: {company_research['growth_stage']}")
        if company_research.get("funding"):
            signals.append(f"Funding: {company_research['funding']}")
        if signals:
            company_signals_text = "\n".join(signals)

    # Format JD keywords
    jd_keywords_text = "None specified"
    if extracted_jd:
        keywords = extracted_jd.get("top_keywords", [])
        if keywords:
            jd_keywords_text = ", ".join(keywords[:10])

    # Format fit rationale
    fit_text = ""
    if fit_rationale:
        fit_text = f"""
=== FIT RATIONALE (use to inform positioning) ===
{fit_rationale}
"""

    # Format persona
    persona_text = ""
    if persona_statement:
        persona_text = f"""
=== CANDIDATE PERSONA (frame letter from this identity) ===
{persona_statement}
"""

    # Truncate CV to key sections (achievements are what matter)
    cv_excerpt = cv_text[:3000] if cv_text else "No CV text available"

    return f"""Generate a cover letter for {candidate_name} applying to {company} for the {job_title} role.

=== TARGET ROLE ===
Title: {job_title}
Company: {company}
{persona_text}
=== COMPANY INTELLIGENCE (reference in paragraph 1) ===
{company_signals_text}

=== JD PAIN POINTS (address 2-3 in paragraph 2) ===
{pain_points_text}

=== JD KEYWORDS (integrate naturally) ===
{jd_keywords_text}
{fit_text}
=== CV TEXT (source of truth for achievements - cite employer names and exact metrics) ===
{cv_excerpt}

=== REQUIREMENTS ===
1. Three paragraphs, 200-300 words total
2. Paragraph 1: Hook with company signal + positioning
3. Paragraph 2: 2-3 achievements with employer names and exact metrics
4. Paragraph 3: Value restatement + specific call to action
5. NO generic phrases, NO fabricated metrics
6. Plain text only, no markdown

Write the cover letter now:"""
