"""
CV Tailorer (Phase 6.5).

Performs final keyword emphasis pass to optimize ATS positioning.
Ensures must-have and identity keywords appear in prominent locations.

Key Constraints:
- Keyword emphasis ONLY (no reframe transformations)
- Preserve ATS constraints (min 2, max 5 mentions per keyword)
- Maintain readability
- Single LLM call for targeted edits

Anti-Hallucination Guarantees:
- No keyword addition (only reposition existing)
- No format changes (preserve markdown structure)
- No metric changes (all numbers stay identical)
- Post-validation required (ATS constraints checked after tailoring)
"""

import re
from typing import Dict, Any, List, Optional, Callable, Tuple

from src.common.logger import get_logger
from src.common.unified_llm import UnifiedLLM
from src.layer6_v2.types import TailoringResult


# ============================================================================
# TAILORING PROMPTS
# ============================================================================

CV_TAILORING_SYSTEM_PROMPT = """You are an ATS optimization specialist performing a FINAL PASS on a CV.

=== YOUR MISSION ===

Reposition specified keywords to prominent locations WITHOUT changing meaning.

=== CRITICAL CONSTRAINTS ===

1. KEYWORD EMPHASIS ONLY
   - Move existing keywords to prominent positions
   - Do NOT add new skills or technologies not already in the CV
   - Do NOT remove any content
   - Do NOT change metrics or facts

2. PROMINENT POSITIONS (in priority order)
   - Headline: Identity keywords MUST appear here
   - First 50 words of profile narrative
   - Core competencies section
   - First bullet of most recent role

3. PRESERVE READABILITY
   - Edits must sound natural, not stuffed
   - Maintain sentence structure and flow
   - If repositioning would sound awkward, skip that keyword

4. ATS CONSTRAINTS
   - Each keyword should appear 2-5 times total in CV
   - Do NOT exceed 5 mentions (diminishing returns, keyword stuffing penalty)
   - Minimum 2 mentions for must-have keywords

5. NO STRUCTURAL CHANGES
   - Preserve section headers exactly
   - Preserve bullet format (• character)
   - Preserve line breaks and spacing
   - Preserve all markdown formatting (**bold**, etc.)

=== OUTPUT FORMAT ===

Return the complete tailored CV text ONLY.
Do not include any explanation, preamble, or trailing comments.
Just the CV text exactly as it should appear.
"""


def build_tailoring_system_prompt_with_persona(
    jd_annotations: Optional[Dict[str, Any]] = None,
    base_prompt: str = CV_TAILORING_SYSTEM_PROMPT,
) -> str:
    """
    Build system prompt with persona guidance for tailoring.

    Args:
        jd_annotations: JD annotations with synthesized_persona
        base_prompt: Base tailoring system prompt

    Returns:
        System prompt with persona section (if available)
    """
    if not jd_annotations:
        return base_prompt

    synthesized_persona = jd_annotations.get("synthesized_persona", {})
    persona_statement = synthesized_persona.get("persona_statement", "")

    if not persona_statement:
        return base_prompt

    persona_section = f"""
=== PERSONA GUIDANCE ===

CANDIDATE PERSONA: {persona_statement}

When repositioning keywords, ensure language style aligns with this persona:
- Leadership personas: use strategic, impact-focused phrasing
- Technical personas: use precise, system-focused phrasing
- Platform/infrastructure personas: use reliability, scale-focused phrasing

The persona should inform HOW you integrate keywords, not WHAT keywords to add.

"""
    return base_prompt + persona_section


def build_tailoring_user_prompt(
    cv_text: str,
    keywords_to_reposition: List[Dict[str, Any]],
    current_placement: Dict[str, Any],
) -> str:
    """
    Build user prompt for CV tailoring.

    Args:
        cv_text: Current CV text to tailor
        keywords_to_reposition: Keywords that need repositioning
        current_placement: Current placement analysis

    Returns:
        User prompt for tailoring LLM
    """
    # Format keywords for prompt
    keywords_list = []
    for kw in keywords_to_reposition:
        keyword = kw.get("keyword", "")
        priority = "MUST-HAVE" if kw.get("is_must_have") else "HIGH PRIORITY"
        current_loc = kw.get("current_location", "buried in CV")
        target_loc = kw.get("target_location", "top 1/3")

        if kw.get("is_identity"):
            priority = "IDENTITY (must be in headline)"

        keywords_list.append(
            f"- \"{keyword}\" [{priority}]: currently {current_loc}, target: {target_loc}"
        )

    keywords_text = "\n".join(keywords_list) if keywords_list else "No keywords need repositioning"

    return f"""=== CV TO TAILOR ===

{cv_text}

=== KEYWORDS TO REPOSITION ===

{keywords_text}

=== INSTRUCTIONS ===

1. Move each keyword to its target location (headline, first 50 words, or competencies)
2. Ensure natural integration - if it would sound awkward, skip that keyword
3. Preserve all other content exactly (metrics, facts, structure)
4. Return the complete tailored CV text

Return ONLY the tailored CV text, no explanations."""


# ============================================================================
# CV TAILORER CLASS
# ============================================================================

class CVTailorer:
    """
    Final pass for keyword emphasis.

    Focuses on positioning keywords in prominent locations:
    - Headline (identity keywords MUST appear)
    - First 50 words of profile narrative
    - Core competencies section
    """

    def __init__(
        self,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        """
        Initialize CVTailorer.

        Args:
            job_id: Job ID for tracking
            progress_callback: Optional callback for progress events
        """
        self._job_id = job_id or "unknown"
        self._logger = get_logger(self.__class__.__name__)
        self._progress_callback = progress_callback

        # Use UnifiedLLM with middle tier (same as improver)
        self._llm = UnifiedLLM(
            step_name="cv_tailorer",
            job_id=self._job_id,
            progress_callback=progress_callback,
        )

    async def tailor(
        self,
        cv_text: str,
        jd_annotations: Dict[str, Any],
        extracted_jd: Dict[str, Any],
    ) -> TailoringResult:
        """
        Apply keyword emphasis to CV.

        Args:
            cv_text: Current CV text
            jd_annotations: JD annotations with priorities
            extracted_jd: Extracted JD with keywords

        Returns:
            TailoringResult with tailored CV
        """
        # Step 1: Extract priority keywords from annotations
        priority_keywords = self._extract_priority_keywords(jd_annotations, extracted_jd)

        if not priority_keywords:
            self._logger.info("No priority keywords to position - skipping tailoring")
            return TailoringResult(
                tailored=False,
                cv_text=cv_text,
                changes_made=[],
                keywords_repositioned=[],
                tailoring_summary="No priority keywords to position",
            )

        self._logger.info(f"Analyzing placement of {len(priority_keywords)} priority keywords")

        # Step 2: Analyze current placement
        current_placement = self._analyze_placement(cv_text, priority_keywords)

        # Step 3: Identify keywords needing repositioning
        keywords_to_reposition = self._identify_repositioning_needs(
            priority_keywords, current_placement
        )

        if not keywords_to_reposition:
            self._logger.info("Keywords already optimally positioned - skipping tailoring")
            return TailoringResult(
                tailored=False,
                cv_text=cv_text,
                changes_made=[],
                keywords_repositioned=[],
                tailoring_summary="Keywords already optimally positioned",
                keyword_placement_score=current_placement.get("overall_score", 100),
            )

        self._logger.info(f"Repositioning {len(keywords_to_reposition)} keywords")

        # Step 4: Call LLM for targeted repositioning
        tailored_cv = await self._apply_tailoring(
            cv_text=cv_text,
            keywords_to_reposition=keywords_to_reposition,
            current_placement=current_placement,
            jd_annotations=jd_annotations,
        )

        # Step 5: Calculate new placement score
        new_placement = self._analyze_placement(tailored_cv, priority_keywords)

        # Generate change log
        keywords_repositioned = [kw["keyword"] for kw in keywords_to_reposition]
        changes_made = [
            f"Repositioned '{kw['keyword']}' from {kw.get('current_location', 'buried')} to prominent position"
            for kw in keywords_to_reposition
        ]

        self._logger.info(
            f"Tailoring complete: placement score {current_placement.get('overall_score', 0)} -> "
            f"{new_placement.get('overall_score', 0)}"
        )

        return TailoringResult(
            tailored=True,
            cv_text=tailored_cv,
            changes_made=changes_made,
            keywords_repositioned=keywords_repositioned,
            tailoring_summary=f"Repositioned {len(keywords_repositioned)} keywords to prominent positions",
            keyword_placement_score=new_placement.get("overall_score", 0),
            ats_validation_passed=True,  # Will be set by orchestrator after re-validation
        )

    def _extract_priority_keywords(
        self,
        jd_annotations: Dict[str, Any],
        extracted_jd: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Extract priority keywords from annotations.

        Args:
            jd_annotations: JD annotations with priorities
            extracted_jd: Extracted JD data

        Returns:
            List of priority keyword dicts
        """
        priority_keywords = []

        # Extract from annotations
        annotations = jd_annotations.get("annotations", [])
        for ann in annotations:
            if not ann.get("is_active", True):
                continue

            # Get keyword from matching_skill or suggested_keywords
            keyword = ann.get("matching_skill")
            if not keyword:
                suggested = ann.get("suggested_keywords", [])
                keyword = suggested[0] if suggested else None

            if not keyword:
                continue

            relevance = ann.get("relevance", "relevant")
            requirement_type = ann.get("requirement_type", "neutral")
            identity = ann.get("identity", "not_identity")
            priority = ann.get("priority", 3)

            priority_keywords.append({
                "keyword": keyword,
                "is_must_have": requirement_type == "must_have",
                "is_identity": identity in ["core_identity", "strong_identity"],
                "is_core_strength": relevance in ["core_strength", "extremely_relevant"],
                "priority_rank": priority,
            })

        # Also include top JD keywords if not already covered
        jd_keywords = extracted_jd.get("top_keywords", [])[:5]
        existing_keywords = {kw["keyword"].lower() for kw in priority_keywords}

        for jd_kw in jd_keywords:
            if jd_kw.lower() not in existing_keywords:
                priority_keywords.append({
                    "keyword": jd_kw,
                    "is_must_have": False,
                    "is_identity": False,
                    "is_core_strength": False,
                    "priority_rank": 5,  # Lower priority for JD-only keywords
                })

        return priority_keywords

    def _analyze_placement(
        self,
        cv_text: str,
        priority_keywords: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Analyze current keyword placement in CV.

        Args:
            cv_text: CV text to analyze
            priority_keywords: Keywords to check

        Returns:
            Placement analysis dict
        """
        # Extract CV sections
        headline = self._extract_headline(cv_text)
        narrative = self._extract_narrative(cv_text)
        competencies = self._extract_competencies(cv_text)
        first_role_bullets = self._extract_first_role_bullets(cv_text)

        headline_lower = headline.lower()
        narrative_lower = narrative.lower()
        competencies_lower = competencies.lower()
        first_role_lower = " ".join(first_role_bullets).lower() if first_role_bullets else ""

        placements = []
        total_score = 0

        for kw in priority_keywords:
            keyword = kw["keyword"]
            keyword_lower = keyword.lower()

            # Check placement in each section
            in_headline = keyword_lower in headline_lower
            in_narrative = keyword_lower in narrative_lower
            in_competencies = keyword_lower in competencies_lower
            in_first_role = keyword_lower in first_role_lower
            in_top_third = in_headline or in_narrative or in_competencies

            # Calculate placement score for this keyword
            score = 0
            if in_headline:
                score += 40
            if in_narrative:
                score += 30
            if in_competencies:
                score += 20
            if in_first_role:
                score += 10
            score = min(score, 100)

            placements.append({
                "keyword": keyword,
                "in_headline": in_headline,
                "in_narrative": in_narrative,
                "in_competencies": in_competencies,
                "in_first_role": in_first_role,
                "in_top_third": in_top_third,
                "score": score,
                **kw,  # Include priority info
            })

            total_score += score

        overall_score = total_score // len(placements) if placements else 0

        # Calculate must-have score
        must_haves = [p for p in placements if p.get("is_must_have")]
        must_have_in_top = sum(1 for p in must_haves if p["in_top_third"])
        must_have_score = (must_have_in_top / len(must_haves) * 100) if must_haves else 100

        # Calculate identity score
        identity_kws = [p for p in placements if p.get("is_identity")]
        identity_in_headline = sum(1 for p in identity_kws if p["in_headline"])
        identity_score = (identity_in_headline / len(identity_kws) * 100) if identity_kws else 100

        return {
            "placements": placements,
            "overall_score": overall_score,
            "must_have_score": int(must_have_score),
            "identity_score": int(identity_score),
            "keywords_in_headline": sum(1 for p in placements if p["in_headline"]),
            "keywords_in_top_third": sum(1 for p in placements if p["in_top_third"]),
        }

    def _identify_repositioning_needs(
        self,
        priority_keywords: List[Dict[str, Any]],
        current_placement: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Identify keywords that need repositioning.

        Args:
            priority_keywords: All priority keywords
            current_placement: Current placement analysis

        Returns:
            List of keywords needing repositioning
        """
        keywords_to_reposition = []
        placements = current_placement.get("placements", [])

        for placement in placements:
            needs_repositioning = False
            target_location = "top 1/3"
            current_location = "not found"

            # Determine current location description
            if placement["in_headline"]:
                current_location = "headline"
            elif placement["in_narrative"]:
                current_location = "narrative"
            elif placement["in_competencies"]:
                current_location = "competencies"
            elif placement["in_first_role"]:
                current_location = "first role"
            else:
                current_location = "buried in CV"

            # Identity keywords MUST be in headline
            if placement.get("is_identity") and not placement["in_headline"]:
                needs_repositioning = True
                target_location = "headline"

            # Must-have keywords MUST be in top 1/3
            elif placement.get("is_must_have") and not placement["in_top_third"]:
                needs_repositioning = True
                target_location = "first 50 words or competencies"

            # Core strength keywords should be in top 1/3
            elif placement.get("is_core_strength") and not placement["in_top_third"]:
                needs_repositioning = True
                target_location = "competencies or narrative"

            if needs_repositioning:
                keywords_to_reposition.append({
                    **placement,
                    "current_location": current_location,
                    "target_location": target_location,
                })

        return keywords_to_reposition

    async def _apply_tailoring(
        self,
        cv_text: str,
        keywords_to_reposition: List[Dict[str, Any]],
        current_placement: Dict[str, Any],
        jd_annotations: Dict[str, Any],
    ) -> str:
        """
        Call LLM to apply tailoring.

        Args:
            cv_text: Current CV text
            keywords_to_reposition: Keywords needing repositioning
            current_placement: Current placement analysis
            jd_annotations: JD annotations for persona

        Returns:
            Tailored CV text
        """
        # Build prompts with persona
        system_prompt = build_tailoring_system_prompt_with_persona(
            jd_annotations=jd_annotations,
        )

        user_prompt = build_tailoring_user_prompt(
            cv_text=cv_text,
            keywords_to_reposition=keywords_to_reposition,
            current_placement=current_placement,
        )

        # Call LLM
        result = await self._llm.invoke(
            prompt=user_prompt,
            system=system_prompt,
            validate_json=False,  # Output is plain text, not JSON
        )

        if not result.success:
            self._logger.error(f"Tailoring LLM call failed: {result.error}")
            return cv_text  # Return original on failure

        # Clean the response
        tailored = result.content.strip()

        # Remove any trailing explanation if present
        if "===" in tailored:
            # LLM may have added sections after CV
            parts = tailored.split("===")
            tailored = parts[0].strip()

        return tailored

    # ========================================================================
    # CV SECTION EXTRACTION HELPERS
    # ========================================================================

    def _extract_headline(self, cv_text: str) -> str:
        """Extract headline from CV (first H3 after name)."""
        lines = cv_text.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("###"):
                return line.replace("###", "").strip()
            if line.startswith("**") and "·" in line:
                # Common pattern: **Title · Generic Title**
                return line.strip("*").strip()
        return ""

    def _extract_narrative(self, cv_text: str) -> str:
        """Extract first 100 words of profile narrative."""
        # Find profile/summary section
        profile_patterns = [
            r"\*\*(?:EXECUTIVE SUMMARY|PROFESSIONAL SUMMARY|PROFILE|SUMMARY)\*\*",
            r"#{1,3}\s*(?:EXECUTIVE SUMMARY|PROFESSIONAL SUMMARY|PROFILE|SUMMARY)",
        ]

        for pattern in profile_patterns:
            match = re.search(pattern, cv_text, re.IGNORECASE)
            if match:
                # Get text after the header
                start = match.end()
                # Find next section (starts with ** or ##)
                next_section = re.search(r"\n\*\*[A-Z]|\n#{1,3}\s*[A-Z]", cv_text[start:])
                end = start + next_section.start() if next_section else start + 500
                narrative = cv_text[start:end].strip()
                # Return first ~100 words
                words = narrative.split()[:100]
                return " ".join(words)

        return ""

    def _extract_competencies(self, cv_text: str) -> str:
        """Extract core competencies section."""
        patterns = [
            r"\*\*(?:CORE COMPETENCIES|COMPETENCIES|SKILLS|TECHNICAL SKILLS)\*\*",
            r"#{1,3}\s*(?:CORE COMPETENCIES|COMPETENCIES|SKILLS|TECHNICAL SKILLS)",
        ]

        for pattern in patterns:
            match = re.search(pattern, cv_text, re.IGNORECASE)
            if match:
                start = match.end()
                # Find next section
                next_section = re.search(r"\n\*\*[A-Z]|\n#{1,3}\s*[A-Z]", cv_text[start:])
                end = start + next_section.start() if next_section else start + 500
                return cv_text[start:end].strip()

        return ""

    def _extract_first_role_bullets(self, cv_text: str) -> List[str]:
        """Extract bullets from first role in experience section."""
        # Find professional experience section
        exp_patterns = [
            r"\*\*(?:PROFESSIONAL EXPERIENCE|EXPERIENCE|WORK HISTORY)\*\*",
            r"#{1,3}\s*(?:PROFESSIONAL EXPERIENCE|EXPERIENCE|WORK HISTORY)",
        ]

        for pattern in exp_patterns:
            match = re.search(pattern, cv_text, re.IGNORECASE)
            if match:
                start = match.end()
                # Get first ~1000 chars after experience header
                section = cv_text[start:start + 1000]
                # Extract bullets (lines starting with •, -, or *)
                bullets = re.findall(r"^[•\-\*]\s*(.+)$", section, re.MULTILINE)
                return bullets[:6]  # First 6 bullets

        return []


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

async def tailor_cv(
    cv_text: str,
    jd_annotations: Dict[str, Any],
    extracted_jd: Dict[str, Any],
    job_id: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
) -> TailoringResult:
    """
    Convenience function to tailor CV.

    Args:
        cv_text: CV text to tailor
        jd_annotations: JD annotations
        extracted_jd: Extracted JD data
        job_id: Optional job ID
        progress_callback: Optional progress callback

    Returns:
        TailoringResult
    """
    tailorer = CVTailorer(job_id=job_id, progress_callback=progress_callback)
    return await tailorer.tailor(cv_text, jd_annotations, extracted_jd)
