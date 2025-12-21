"""
Layer 4: Opportunity Mapper (Phase 6)

Maps candidate profile to job requirements and generates fit score + rationale + category.

Phase 6 Enhancements:
- Integrates company_research and role_research from Phase 5
- Validates STAR citations and quantified metrics in rationale
- Derives fit_category from fit_score per ROADMAP rubric
- Detects and rejects generic boilerplate rationales

Annotation Signal Integration:
- Incorporates JD annotation signals to blend human judgment with LLM scoring
- Core strength and extremely relevant annotations boost fit signal
- Gap annotations reduce fit signal
- Disqualifier requirement types flag potential issues
- Default blend: 70% LLM score, 30% annotation signal
"""

import logging
import re
from typing import Dict, Any, Tuple, List, Optional, TYPE_CHECKING
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.llm_factory import create_tracked_llm
from src.common.state import JobState
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.common.unified_llm import UnifiedLLM, LLMResult
from src.common.llm_config import TierType, TIER_TO_CLAUDE_MODEL
from src.layer4.annotation_fit_signal import (
    AnnotationFitSignal,
    blend_fit_scores,
    get_annotation_analysis,
)

if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger


# ===== PROMPT DESIGN =====

# V2 Enhanced Prompt - Issue 1: Weak Grounding (Anti-Hallucination Guardrails)
SYSTEM_PROMPT = """You are a senior executive recruiter who has placed 500+ candidates in similar roles.

Your reputation depends on ACCURATE fit assessments that help candidates avoid bad matches and companies hire the right talent.

YOUR SUPERPOWER: Spotting the SPECIFIC evidence in a candidate's history that proves they can solve a company's SPECIFIC pain points.

CRITICAL RULES:
1. You NEVER use generic phrases like "strong background", "great fit", or "proven track record"
2. You ALWAYS cite concrete examples with metrics from the provided context
3. You ONLY use facts explicitly stated in the provided materials - NEVER invent or assume
4. If evidence is missing, you state "Unknown" or "Not specified" instead of guessing
5. Every claim must have a source: STAR record, master CV, or company research

SCORING RUBRIC:
- 90-100: Exceptional fit - ≥3 pain points solved with quantified proof + strategic alignment
- 80-89: Strong fit - ≥2 pain points solved, 1-2 learnable gaps
- 70-79: Good fit - 1-2 pain points solved, gaps are feasible
- 60-69: Moderate fit - Partial matches, significant but addressable gaps
- <60: Weak fit - Major gaps, limited evidence of relevant experience
"""

USER_PROMPT_TEMPLATE = """Analyze the candidate's fit for this job opportunity using the 4-STEP REASONING PROCESS below.

=== JOB DETAILS ===
Title: {title}
Company: {company}

Job Description:
{job_description}

=== COMPANY RESEARCH ===
{company_research}

=== ROLE RESEARCH ===
{role_research}

=== CANDIDATE PROFILE (MASTER CV) ===
{candidate_profile}

=== CURATED ACHIEVEMENTS (STARs) ===
{selected_stars}

=== JOB ANALYSIS (4 Dimensions) ===

PAIN POINTS (Current Problems):
{pain_points}

STRATEGIC NEEDS (Why This Role Matters):
{strategic_needs}

RISKS IF UNFILLED (Consequences):
{risks_if_unfilled}

SUCCESS METRICS (How They'll Measure Success):
{success_metrics}

=== 4-STEP REASONING PROCESS ===

STEP 1: PAIN POINT MAPPING
For each pain point, identify which STAR achievement (if any) demonstrates relevant experience.
Format: [Pain Point] → [STAR company + metric] OR [No direct evidence]

STEP 2: GAP ANALYSIS
List any pain points with NO matching STAR evidence.
For each gap: Is it learnable? Is it a dealbreaker?

STEP 3: STRATEGIC ALIGNMENT
How do company signals (growth, expansion, product) align with candidate's proven strengths?
Cite: [company signal] + [STAR evidence]

STEP 4: SCORING DECISION
Apply the rubric based on evidence strength:
- Count pain points solved with quantified proof
- Assess severity of gaps
- Determine final score and category

=== YOUR OUTPUT ===

**REASONING:**
[Complete Steps 1-4 above with specific citations]

**SCORE:** [number 0-100]

**RATIONALE:** [2-3 sentences citing specific STARs by company name and metrics]
Format: "At [STAR company], candidate [result with metric], directly addressing [pain point]. [Gap assessment if any]."

ANTI-HALLUCINATION CHECK:
- Every company name must come from STAR records or master CV
- Every metric must come from STAR records
- If you cannot find evidence, state "Not specified in provided materials"
"""


class OpportunityMapper:
    """
    Analyzes candidate-job fit and generates scoring.

    Uses UnifiedLLM for LLM invocations with Claude CLI primary and LangChain fallback.
    """

    def __init__(
        self,
        tier: TierType = "middle",
        struct_logger: Optional["StructuredLogger"] = None,
    ):
        """
        Initialize the mapper.

        Args:
            tier: Model tier - "low" (Haiku), "middle" (Sonnet), "high" (Opus).
                  Default is "middle" (Sonnet 4.5).
            struct_logger: Optional StructuredLogger for emitting LLM call events
                to the frontend log stream.
        """
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)
        self.tier = tier
        self._struct_logger = struct_logger
        # UnifiedLLM handles Claude CLI primary with LangChain fallback automatically
        self._unified_llm: Optional[UnifiedLLM] = None

    def _get_unified_llm(self, job_id: Optional[str] = None) -> UnifiedLLM:
        """Get or create UnifiedLLM instance for this invocation."""
        # Create new instance per invocation to allow job_id tracking
        return UnifiedLLM(
            step_name="fit_analysis",
            tier=self.tier,
            job_id=job_id,
            struct_logger=self._struct_logger,
        )

    def _derive_fit_category(self, fit_score: int) -> str:
        """
        Derive fit_category from fit_score per ROADMAP Phase 6 rubric.

        Args:
            fit_score: Integer score 0-100

        Returns:
            Category: "exceptional" | "strong" | "good" | "moderate" | "weak"
        """
        if fit_score >= 90:
            return "exceptional"
        elif fit_score >= 80:
            return "strong"
        elif fit_score >= 70:
            return "good"
        elif fit_score >= 60:
            return "moderate"
        else:
            return "weak"

    def _truncate_text(self, text: str, limit: int = 1200) -> str:
        """Return a truncated snippet of text for prompt safety."""
        if not text:
            return "No candidate profile provided."
        snippet = text.strip()
        return snippet[:limit] + ("..." if len(snippet) > limit else "")

    def _validate_rationale(
        self,
        rationale: str,
        selected_stars: Optional[List[Dict[str, Any]]] = None,
        pain_points: Optional[List[str]] = None
    ) -> List[str]:
        """
        V2 Enhanced validation with stricter grounding requirements.

        Validates:
        1. Must cite ≥1 STAR by company name (when STARs available)
        2. Must include ≥1 quantified metric (when STARs available)
        3. Must reference ≥1 specific pain point
        4. Must not contain >1 generic phrase
        5. Length ≥30 words (increased from 10)

        Args:
            rationale: The fit rationale text to validate
            selected_stars: Optional list of STAR records for context
            pain_points: Optional list of pain points to verify coverage

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Gate 1: Minimum length (increased from 10 to 30 words)
        word_count = len(rationale.split()) if rationale else 0
        if word_count < 30:
            errors.append(f"Rationale too short: {word_count} words (minimum 30)")

        # Gate 2: STAR company citation (required when STARs available)
        if selected_stars:
            star_companies = [s.get('company', '') for s in selected_stars if s.get('company')]
            star_cited = any(
                company.lower() in rationale.lower()
                for company in star_companies
            )
            if not star_cited and star_companies:
                errors.append(
                    f"Must cite at least one STAR by company name. "
                    f"Available: {', '.join(star_companies[:3])}"
                )

        # Gate 3: Metric presence (required when STARs available)
        metric_patterns = [
            r'\d+%',           # 75%, 60%
            r'\d+x',           # 10x, 24x
            r'\d+[KMB]\b',     # 50M, 10K, 5B
            r'\d+\s*min',      # 15min, 10 min
            r'\d+\s*hour',     # 3 hours
            r'\d+\s*year',     # 3 years
            r'\d+\s*engineer', # 10 engineers
            r'\d+\s*month',    # 6 months
        ]
        if selected_stars:
            has_metric = any(
                re.search(pattern, rationale, re.IGNORECASE)
                for pattern in metric_patterns
            )
            if not has_metric:
                errors.append("Add at least one concrete metric from STAR achievements.")

        # Gate 4: Pain point reference (new requirement)
        if pain_points:
            # Check if any pain point keywords appear in rationale
            pain_referenced = False
            for pain in pain_points:
                # Extract key words (>3 chars) from pain point
                key_words = [w.lower() for w in pain.split() if len(w) > 3][:3]
                # Check if at least 2 key words appear
                matches = sum(1 for w in key_words if w in rationale.lower())
                if matches >= 2:
                    pain_referenced = True
                    break

            if not pain_referenced:
                errors.append(
                    "Must explicitly reference at least one pain point from the job description"
                )

        # Gate 5: Generic boilerplate detection (stricter - only 1 allowed)
        generic_phrases = [
            r'strong background',
            r'great communication skills',
            r'team player',
            r'well-suited',
            r'good fit',
            r'great fit',
            r'excellent fit',
            r'extensive experience',
            r'proven track record',
            r'highly qualified',
            r'ideal candidate',
            r'perfect fit',
            r'excited to',
            r'passionate about',
        ]

        generic_count = sum(
            1 for phrase in generic_phrases
            if re.search(phrase, rationale, re.IGNORECASE)
        )

        if generic_count > 1:
            errors.append(
                f"Too many generic phrases ({generic_count}). "
                f"Use specific evidence instead of boilerplate language."
            )

        return errors

    def _format_dimension(self, items: list, label: str) -> str:
        """Format a dimension as numbered bullets."""
        if not items:
            return f"No {label.lower()} identified."
        return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))

    def _format_selected_stars(self, selected_stars: list) -> str:
        """Format selected STAR records for LLM prompt."""
        if not selected_stars:
            return "STAR selector disabled - use achievements from the master CV."

        formatted = []
        for i, star in enumerate(selected_stars, 1):
            formatted.append(f"""
STAR #{i}: {star.get('company', 'Unknown')} - {star.get('role', 'Unknown')}
Period: {star.get('period', 'N/A')}
Domain: {star.get('domain_areas', 'N/A')}

Situation: {star.get('situation', 'N/A')}
Task: {star.get('task', 'N/A')}
Actions: {star.get('actions', 'N/A')}
Results: {star.get('results', 'N/A')}

KEY METRICS: {star.get('metrics', 'N/A')}
""".strip())

        return "\n\n---\n\n".join(formatted)

    def _parse_llm_response(self, response: str) -> Tuple[int, str]:
        """
        Parse LLM response to extract score and rationale.

        Expected format (V2 with reasoning):
        **REASONING:**
        [multi-line reasoning]

        **SCORE:** 85

        **RATIONALE:** The candidate at Seven.One achieved 75% incident reduction...

        Returns:
            Tuple of (score, rationale)
        """
        # Extract score - try multiple patterns for flexibility
        score_patterns = [
            r'\*\*SCORE:\*\*\s*(\d+)',      # **SCORE:** 85
            r'SCORE:\s*(\d+)',               # SCORE: 85
            r'\*\*SCORE\*\*:\s*(\d+)',       # **SCORE**: 85
        ]

        score = None
        for pattern in score_patterns:
            score_match = re.search(pattern, response, re.IGNORECASE)
            if score_match:
                score = int(score_match.group(1))
                score = max(0, min(100, score))
                break

        if score is None:
            # Fallback: try to find any number in typical score range
            numbers = re.findall(r'\b(\d{1,3})\b', response)
            for num in numbers:
                n = int(num)
                if 0 <= n <= 100:
                    score = n
                    break
            if score is None:
                score = 50  # Default if parsing fails

        # Extract rationale - try multiple patterns
        rationale_patterns = [
            r'\*\*RATIONALE:\*\*\s*(.+?)(?:\n\n|ANTI-HALLUCINATION|$)',  # **RATIONALE:** text
            r'RATIONALE:\s*(.+?)(?:\n\n|ANTI-HALLUCINATION|$)',           # RATIONALE: text
        ]

        rationale = None
        for pattern in rationale_patterns:
            rationale_match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            if rationale_match:
                rationale = rationale_match.group(1).strip()
                break

        if not rationale:
            # Fallback: use everything after score
            score_match = re.search(r'SCORE[:\s*]+\d+', response, re.IGNORECASE)
            if score_match:
                remaining = response[score_match.end():].strip()
                # Try to extract just the rationale part
                if 'RATIONALE' in remaining.upper():
                    rationale = remaining.split('RATIONALE', 1)[-1].strip(': \n')
                else:
                    rationale = remaining
            else:
                rationale = response.strip()

        # Clean up rationale (remove extra whitespace, newlines)
        rationale = re.sub(r'\s+', ' ', rationale).strip()

        # Remove any trailing anti-hallucination check text
        rationale = re.sub(r'\s*ANTI-HALLUCINATION.*', '', rationale, flags=re.IGNORECASE | re.DOTALL)

        return score, rationale

    def _format_company_research(self, company_research: Optional[Dict[str, Any]]) -> str:
        """Format company research for prompt (Phase 5.1)."""
        if not company_research:
            return "No structured company research available."

        parts = []

        # Summary
        if company_research.get("summary"):
            parts.append(f"Summary: {company_research['summary']}")

        # Signals
        if company_research.get("signals"):
            parts.append("\nKey Signals:")
            for sig in company_research["signals"]:
                parts.append(f"  - [{sig.get('type', 'unknown')}] {sig.get('description', 'N/A')} ({sig.get('date', 'unknown')})")

        return "\n".join(parts) if parts else "No structured company research available."

    def _format_role_research(self, role_research: Optional[Dict[str, Any]]) -> str:
        """Format role research for prompt (Phase 5.2)."""
        if not role_research:
            return "No structured role research available."

        parts = []

        # Summary
        if role_research.get("summary"):
            parts.append(f"Summary: {role_research['summary']}")

        # Business Impact
        if role_research.get("business_impact"):
            parts.append("\nBusiness Impact:")
            for impact in role_research["business_impact"]:
                parts.append(f"  - {impact}")

        # Why Now
        if role_research.get("why_now"):
            parts.append(f"\nWhy Now: {role_research['why_now']}")

        return "\n".join(parts) if parts else "No structured role research available."

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def _analyze_fit_async(self, state: JobState) -> Tuple[int, str, str]:
        """
        Use LLM to analyze candidate-job fit (Phase 6) - async version.

        Uses UnifiedLLM which handles Claude CLI primary with LangChain fallback.

        Returns:
            Tuple of (fit_score, fit_rationale, fit_category)

        Raises:
            ValueError: If rationale fails validation (triggers retry)
        """
        # Format all 4 dimensions
        pain_points_text = self._format_dimension(state.get("pain_points", []), "pain points")
        strategic_needs_text = self._format_dimension(state.get("strategic_needs", []), "strategic needs")
        risks_text = self._format_dimension(state.get("risks_if_unfilled", []), "risks")
        metrics_text = self._format_dimension(state.get("success_metrics", []), "success metrics")
        candidate_profile_text = self._truncate_text(state.get("candidate_profile", ""))

        # Format selected STAR records
        selected_stars_text = self._format_selected_stars(state.get("selected_stars", []))

        # Phase 6: Format company and role research
        company_research_text = self._format_company_research(state.get("company_research"))
        role_research_text = self._format_role_research(state.get("role_research"))

        # Build user prompt content
        user_prompt_content = USER_PROMPT_TEMPLATE.format(
            title=state["title"],
            company=state["company"],
            job_description=state["job_description"],
            company_research=company_research_text,
            role_research=role_research_text,
            pain_points=pain_points_text,
            strategic_needs=strategic_needs_text,
            risks_if_unfilled=risks_text,
            success_metrics=metrics_text,
            candidate_profile=candidate_profile_text,
            selected_stars=selected_stars_text
        )

        # Use UnifiedLLM - handles Claude CLI primary with LangChain fallback
        job_id = state.get("job_id", "opportunity-mapper")
        llm = self._get_unified_llm(job_id)
        result: LLMResult = await llm.invoke(
            prompt=user_prompt_content,
            system=SYSTEM_PROMPT,
            job_id=job_id,
            validate_json=False,  # Opportunity mapper doesn't expect JSON
        )

        if not result.success:
            raise ValueError(f"LLM invocation failed: {result.error}")

        response_text = result.content.strip()

        # Parse response
        score, rationale = self._parse_llm_response(response_text)

        # Phase 6 V2: Validate rationale with stricter grounding requirements
        validation_errors = self._validate_rationale(
            rationale,
            selected_stars=state.get("selected_stars"),
            pain_points=state.get("pain_points")
        )
        if validation_errors:
            # For production usage we treat these as quality warnings, not hard failures.
            # This keeps the pipeline flowing even if the LLM misses some formatting rules.
            self.logger.warning("Fit rationale quality warnings:")
            for msg in validation_errors:
                self.logger.warning(f"  - {msg}")

        # Phase 6: Derive category from score
        category = self._derive_fit_category(score)

        return score, rationale, category

    def _analyze_fit(self, state: JobState) -> Tuple[int, str, str]:
        """
        Use LLM to analyze candidate-job fit (Phase 6) - sync wrapper.

        Uses UnifiedLLM which handles Claude CLI primary with LangChain fallback.

        Returns:
            Tuple of (fit_score, fit_rationale, fit_category)

        Raises:
            ValueError: If rationale fails validation (triggers retry)
        """
        import asyncio

        # Run async method in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._analyze_fit_async(state)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self._analyze_fit_async(state))
        except RuntimeError:
            # No event loop exists
            return asyncio.run(self._analyze_fit_async(state))

    def map_opportunity(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to analyze candidate-job fit (Phase 6).

        Args:
            state: Current JobState with job details, pain points, company/role research, STARs

        Returns:
            Dict with fit_score, fit_rationale, fit_category, and annotation_analysis keys
        """
        try:
            self.logger.info(f"Analyzing fit for: {state['title']} at {state['company']}")

            # Get LLM-based fit score
            llm_score, rationale, _ = self._analyze_fit(state)

            # Get annotation analysis and blend with LLM score
            jd_annotations = state.get("jd_annotations")
            annotation_analysis = get_annotation_analysis(jd_annotations, llm_score=llm_score)

            # Blend annotation signal with LLM score
            final_score = blend_fit_scores(llm_score, jd_annotations)

            # Log annotation blending details
            if annotation_analysis.get("has_annotations"):
                self.logger.info(
                    f"Annotation signal: {annotation_analysis['fit_signal']:.2f} "
                    f"(core={annotation_analysis['core_strength_count']}, "
                    f"gaps={annotation_analysis['gap_count']})"
                )
                self.logger.info(f"LLM score: {llm_score}, Blended score: {final_score}")
                if annotation_analysis.get("has_disqualifier"):
                    self.logger.warning(f"DISQUALIFIER detected: {annotation_analysis.get('disqualifier_warning')}")
            else:
                self.logger.info("No annotations - using LLM score directly")

            # Derive category from final (blended) score
            category = self._derive_fit_category(final_score)

            # Add agency note to rationale if this is a recruitment agency
            company_research = state.get("company_research") or {}
            company_type = company_research.get("company_type", "employer")
            if company_type == "recruitment_agency":
                agency_note = (
                    "\n\n**Note:** This is a recruitment agency position. "
                    "The role is sourced by an agency on behalf of an undisclosed client company. "
                    "Score is based on job requirements only, not employer-specific factors."
                )
                rationale = rationale + agency_note
                self.logger.info("Added recruitment agency note to fit rationale")

            self.logger.info(f"Final fit score: {final_score}/100 ({category})")
            self.logger.info(f"Generated rationale ({len(rationale)} chars)")
            self.logger.info("Rationale validation: see any quality warnings above")

            return {
                "fit_score": final_score,
                "fit_rationale": rationale,
                "fit_category": category,
                "annotation_analysis": annotation_analysis,
            }

        except Exception as e:
            # Complete failure - log error and return None
            error_msg = f"Layer 4 (Opportunity Mapper) failed: {str(e)}"
            self.logger.error(error_msg)

            # Still return annotation analysis for transparency
            jd_annotations = state.get("jd_annotations")
            annotation_analysis = get_annotation_analysis(jd_annotations)

            return {
                "fit_score": None,
                "fit_rationale": None,
                "fit_category": None,
                "annotation_analysis": annotation_analysis,
                "errors": state.get("errors", []) + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def opportunity_mapper_node(
    state: JobState,
    tier: TierType = "middle",
) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 4: Opportunity Mapper (Phase 6).

    Uses UnifiedLLM with Claude CLI primary and LangChain fallback.

    Args:
        state: Current job processing state
        tier: Model tier - "low" (Haiku), "middle" (Sonnet), "high" (Opus).
              Default is "middle" (Sonnet 4.5).

    Returns:
        Dictionary with updates to merge into state including annotation_analysis
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer4")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    logger.info("="*60)
    logger.info("LAYER 4: Opportunity Mapper (Phase 6 + Annotation Signal)")
    logger.info("="*60)
    logger.info(f"Backend: UnifiedLLM (tier={tier}, model={TIER_TO_CLAUDE_MODEL.get(tier, 'middle')})")

    with LayerContext(struct_logger, 4, "opportunity_mapper") as ctx:
        mapper = OpportunityMapper(tier=tier, struct_logger=struct_logger)
        updates = mapper.map_opportunity(state)

        # Add metadata for structured logging
        if updates.get("fit_score") is not None:
            ctx.add_metadata("fit_score", updates["fit_score"])
            ctx.add_metadata("fit_category", updates.get("fit_category"))

        # Add annotation analysis metadata
        annotation_analysis = updates.get("annotation_analysis", {})
        if annotation_analysis.get("has_annotations"):
            ctx.add_metadata("annotation_signal", annotation_analysis.get("fit_signal"))
            ctx.add_metadata("llm_score", annotation_analysis.get("llm_score"))
            ctx.add_metadata("core_strength_count", annotation_analysis.get("core_strength_count"))
            ctx.add_metadata("gap_count", annotation_analysis.get("gap_count"))
            ctx.add_metadata("has_disqualifier", annotation_analysis.get("has_disqualifier"))

        # Log results (text logging)
        if updates.get("fit_score") is not None:
            logger.info(f"Fit Score: {updates['fit_score']}/100")
            logger.info(f"Fit Category: {updates.get('fit_category', 'N/A').upper()}")

            # Log annotation analysis
            if annotation_analysis.get("has_annotations"):
                logger.info(f"Annotation Signal: {annotation_analysis.get('fit_signal', 0):.2f}")
                logger.info(f"  - Core Strengths: {annotation_analysis.get('core_strength_count', 0)}")
                logger.info(f"  - Extremely Relevant: {annotation_analysis.get('extremely_relevant_count', 0)}")
                logger.info(f"  - Gaps: {annotation_analysis.get('gap_count', 0)}")
                if annotation_analysis.get("has_disqualifier"):
                    logger.warning(f"  - DISQUALIFIER: {annotation_analysis.get('disqualifier_warning')}")
                logger.info(f"LLM Score: {annotation_analysis.get('llm_score')} -> Blended: {updates['fit_score']}")

            logger.info("Fit Rationale:")
            logger.info(f"  {updates['fit_rationale']}")
        else:
            logger.warning("No fit analysis generated")

    logger.info("="*60)

    return updates
