"""
Outreach Generation Service (Phase 5).

Provides button-triggered outreach message generation per contact.
Generates LinkedIn connection requests (<=300 chars) and InMail/Email messages.

Usage:
    service = OutreachGenerationService()
    result = await service.execute(
        job_id="...",
        contact_index=0,
        contact_type="primary",
        tier=ModelTier.BALANCED,
        message_type="connection"  # or "inmail"
    )
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from bson import ObjectId

from src.common.unified_llm import invoke_unified_sync
from src.common.repositories import get_job_repository, JobRepositoryInterface

from src.common.model_tiers import ModelTier, get_model_for_operation
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)

# Outreach message type
MessageType = Literal["connection", "inmail"]
ContactTypeField = Literal["primary", "secondary"]

# Character limits
CONNECTION_CHAR_LIMIT = 300
INMAIL_MIN_CHARS = 400
INMAIL_MAX_CHARS = 600

# Candidate contact info (from outreach generator)
CANDIDATE_CALENDLY = "calendly.com/taimooralam/15min"
CANDIDATE_NAME = "Taimoor Alam"
CANDIDATE_SIGNATURE = f"Best. {CANDIDATE_NAME}"

# System prompts for outreach generation
# Base system prompt (used when no persona available)
CONNECTION_SYSTEM_PROMPT_BASE = """You are an expert at writing highly personalized LinkedIn connection requests.

## Guidelines
- Maximum {char_limit} characters INCLUDING signature and Calendly link
- Professional but warm tone
- Reference specific pain points or company signals when available
- End with: "{signature}"
- Include Calendly link naturally: "{calendly}"
- No emojis
- No placeholder text like [Company Name] - use actual values
- Frame as "already applied" adding context

## Contact Type Guidelines
- hiring_manager: Focus on skills + team fit, peer-level thinking
- recruiter: Keywords matching JD, quantified achievements
- vp_director: Strategic outcomes, extreme brevity (50-100 words)
- executive: Industry trends, extreme brevity
- peer: Technical credibility, collaborative tone

## Output
Return ONLY the connection message text. No explanations."""

# Persona-enhanced system prompt (used when persona is available)
CONNECTION_SYSTEM_PROMPT_PERSONA = """You ARE {candidate_name}, writing YOUR OWN LinkedIn connection request.

## YOUR PROFESSIONAL PERSONA
{persona_statement}

## YOUR CORE STRENGTHS (use 1-2 naturally in the message)
{core_strengths}

## MESSAGE CONSTRAINTS
- Maximum {char_limit} characters INCLUDING your signature and Calendly link
- Write in first person ("I", "my") - this is YOUR message
- Professional but warm - this is how YOU communicate
- Reference specific pain points that YOU can solve
- End with: "{signature}"
- Include your Calendly naturally: "{calendly}"
- No emojis
- No placeholder text - use actual company/role names

## CONTACT TYPE APPROACH
- hiring_manager: Show YOUR skills + how you fit THEIR team
- recruiter: Keywords matching JD, YOUR quantified achievements
- vp_director: YOUR strategic outcomes, extreme brevity (50-100 words)
- executive: Industry trends YOU understand, extreme brevity
- peer: YOUR technical credibility, collaborative tone

## FRAMING
You have already applied to this role. You're reaching out to add context and make a personal connection.

## Output
Return ONLY the connection message text. No explanations. Write as yourself."""

# Keep backward compatibility alias
CONNECTION_SYSTEM_PROMPT = CONNECTION_SYSTEM_PROMPT_BASE

CONNECTION_USER_PROMPT = """Generate a LinkedIn connection request for this contact.

## Job Details
- Company: {company}
- Role: {role}
- Pain Points: {pain_points}

## Contact
- Name: {contact_name}
- Title: {contact_role}
- Contact Type: {contact_type}
- Why Relevant: {why_relevant}

## Company Signals
{company_signals}

## Character Limit
{char_limit} characters maximum (including signature and Calendly link)"""

# Base InMail system prompt (used when no persona available)
INMAIL_SYSTEM_PROMPT_BASE = """You are an expert at writing highly personalized LinkedIn InMail messages.

## Guidelines
- Target length: {min_chars}-{max_chars} characters
- Professional tone with clear value proposition
- Reference specific pain points or company signals
- Include 2-3 quantified achievements from candidate's background
- Subject line: 25-30 characters for mobile display
- No emojis
- No placeholder text - use actual values
- Frame as "already applied" adding context
- End with clear call to action

## Contact Type Guidelines
- hiring_manager: Skills + team fit, specific project examples
- recruiter: Keywords matching JD, quantified achievements, ATS-friendly
- vp_director: Strategic outcomes, business impact, 50-150 words
- executive: Extreme brevity, industry trends, market positioning
- peer: Technical credibility, collaborative projects, mutual learning

## Output Format
Return a JSON object with:
- subject: InMail subject line (25-30 chars)
- body: InMail message body ({min_chars}-{max_chars} chars)"""

# Persona-enhanced InMail system prompt
INMAIL_SYSTEM_PROMPT_PERSONA = """You ARE {candidate_name}, writing YOUR OWN LinkedIn InMail.

## YOUR PROFESSIONAL PERSONA
{persona_statement}

## YOUR CORE STRENGTHS (weave 2-3 into your message naturally)
{core_strengths}

## MESSAGE CONSTRAINTS
- Target length: {min_chars}-{max_chars} characters for the body
- Write in first person ("I", "my") - this is YOUR message
- Professional tone with YOUR clear value proposition
- Reference pain points that YOU can solve with YOUR experience
- Include YOUR quantified achievements (specific numbers, outcomes)
- Subject line: 25-30 characters for mobile display
- No emojis
- No placeholder text - use actual company/role names
- End with YOUR clear call to action

## CONTACT TYPE APPROACH
- hiring_manager: YOUR skills + how YOU fit their team, YOUR specific project examples
- recruiter: Keywords matching JD, YOUR quantified achievements
- vp_director: YOUR strategic outcomes, YOUR business impact, 50-150 words
- executive: Extreme brevity, YOUR industry insights, YOUR market positioning
- peer: YOUR technical credibility, collaborative opportunities

## FRAMING
You have already applied to this role. You're reaching out to add context, share YOUR unique value, and make a personal connection.

## Output Format
Return a JSON object with:
- subject: InMail subject line (25-30 chars)
- body: InMail message body ({min_chars}-{max_chars} chars) - written as yourself"""

# Keep backward compatibility alias
INMAIL_SYSTEM_PROMPT = INMAIL_SYSTEM_PROMPT_BASE

INMAIL_USER_PROMPT = """Generate a LinkedIn InMail for this contact.

## Job Details
- Company: {company}
- Role: {role}
- Pain Points: {pain_points}

## Contact
- Name: {contact_name}
- Title: {contact_role}
- Contact Type: {contact_type}
- Why Relevant: {why_relevant}

## Company Signals
{company_signals}

## Candidate Background
{candidate_summary}

## Selected Achievements
{achievements}

## Target Length
Subject: 25-30 characters
Body: {min_chars}-{max_chars} characters"""


class OutreachGenerationService(OperationService):
    """
    Service for generating per-contact outreach messages on-demand.

    Provides button-triggered outreach generation with tier-based model selection
    and cost tracking. Generates either LinkedIn connection requests (<=300 chars)
    or InMail messages (400-600 chars) per contact.

    The service:
    1. Fetches job data from MongoDB (extracted_jd, contacts, pain_points)
    2. Extracts the specific contact from primary_contacts or secondary_contacts
    3. Builds context (job title, company, JD summary, contact info, pain points)
    4. Generates message using LLM with tier-based model
    5. Persists message back to the contact's record in MongoDB
    6. Returns OperationResult with generated message

    Dual-Backend Support:
    - use_claude_cli=False (default): Uses LangChain with OpenRouter (gpt-4o, claude-sonnet)
    - use_claude_cli=True: Uses Claude Code CLI with Claude Opus 4.5 (claude-opus-4-5-20251101)
      for higher quality outreach with MENA cultural awareness

    Model tiers (LangChain backend):
    - FAST: gpt-4o-mini (cheap, quick)
    - BALANCED: gpt-4o (good quality/cost)
    - QUALITY: claude-sonnet (best quality)
    """

    operation_name = "generate-outreach"

    def __init__(
        self,
        repository: Optional[JobRepositoryInterface] = None,
        use_claude_cli: bool = False,
    ):
        """
        Initialize the outreach generation service.

        Args:
            repository: Optional job repository. If None, uses default factory.
            use_claude_cli: If True, use Claude Code CLI (Opus 4.5) instead of LangChain.
                           Provides higher quality with MENA cultural awareness.
        """
        self._repository = repository
        self._use_claude_cli = use_claude_cli
        self._claude_service = None

        if use_claude_cli:
            # Lazy import to avoid circular dependencies
            from src.services.claude_outreach_service import ClaudeOutreachService
            self._claude_service = ClaudeOutreachService()

    def _get_repository(self) -> JobRepositoryInterface:
        """Get the job repository instance."""
        if self._repository is not None:
            return self._repository
        return get_job_repository()

    def _load_candidate_profile(self) -> Optional[str]:
        """
        Load candidate profile from file for outreach personalization.

        Uses Config.CANDIDATE_PROFILE_PATH with fallback to data/master-cv/master-cv.md.
        This ensures outreach messages have candidate context even when not in MongoDB.

        Returns:
            Candidate profile text, or None if not available
        """
        from pathlib import Path
        from src.common.config import Config

        # Try the configured path first
        profile_path = Path(Config.CANDIDATE_PROFILE_PATH)
        if profile_path.exists():
            try:
                return profile_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Error reading candidate profile from {profile_path}: {e}")

        # Try data/master-cv/master-cv.md as fallback
        fallback_path = Path("data/master-cv/master-cv.md")
        if fallback_path.exists():
            try:
                return fallback_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Error reading candidate profile from {fallback_path}: {e}")

        logger.warning("No candidate profile found - outreach will use generic content")
        return None

    async def execute(
        self,
        job_id: str,
        contact_index: int,
        contact_type: ContactTypeField,
        tier: ModelTier,
        message_type: MessageType = "connection",
        **kwargs,
    ) -> OperationResult:
        """
        Generate an outreach message for a specific contact.

        Args:
            job_id: MongoDB ObjectId of the job
            contact_index: Index in primary_contacts or secondary_contacts array
            contact_type: "primary" or "secondary"
            tier: Model tier (FAST, BALANCED, QUALITY)
            message_type: "connection" (<=300 chars) or "inmail" (400-600 chars)
            **kwargs: Additional arguments (ignored)

        Returns:
            OperationResult with generated message in data
        """
        run_id = self.create_run_id()
        model = self.get_model(tier)

        logger.info(
            f"[{run_id[:16]}] Starting outreach generation for job {job_id}, "
            f"contact_type={contact_type}, contact_index={contact_index}, "
            f"message_type={message_type}, tier={tier.value}, model={model}"
        )

        with self.timed_execution() as timer:
            try:
                # Step 1: Fetch job from MongoDB
                job = self._fetch_job(job_id)
                if job is None:
                    return self.create_error_result(
                        run_id=run_id,
                        error=f"Job not found: {job_id}",
                        duration_ms=timer.duration_ms,
                    )

                # Step 2: Get the specific contact
                contact = self._get_contact(job, contact_type, contact_index)
                if contact is None:
                    return self.create_error_result(
                        run_id=run_id,
                        error=f"Contact not found: {contact_type}[{contact_index}]",
                        duration_ms=timer.duration_ms,
                    )

                # Step 3: Build context for outreach generation
                context = self._build_outreach_context(job, contact)

                # Step 4: Generate message based on type
                if message_type == "connection":
                    message = self._generate_connection_message(context, model)
                    subject = None
                    field_name = "linkedin_connection_message"
                else:  # inmail
                    subject, message = self._generate_inmail_message(context, model)
                    field_name = "linkedin_inmail"

                # Step 5: Persist to MongoDB
                persist_success = self._persist_outreach(
                    job_id=job_id,
                    contact_type=contact_type,
                    contact_index=contact_index,
                    message_type=message_type,
                    message=message,
                    subject=subject,
                )

                if not persist_success:
                    logger.warning(f"[{run_id[:16]}] Failed to persist outreach message")

                # Step 6: Calculate cost estimate
                # Connection messages are shorter, estimate fewer tokens
                if message_type == "connection":
                    input_tokens = 800  # ~800 input (context + system prompt)
                    output_tokens = 150  # ~150 output (short message)
                else:
                    input_tokens = 1200  # ~1200 input (more context)
                    output_tokens = 300  # ~300 output (subject + body)

                cost = self.estimate_cost(tier, input_tokens, output_tokens)

                logger.info(
                    f"[{run_id[:16]}] Outreach generation complete. "
                    f"Type: {message_type}, Length: {len(message)} chars, "
                    f"Duration: {timer.duration_ms}ms"
                )

                return self.create_success_result(
                    run_id=run_id,
                    data={
                        "message": message,
                        "subject": subject,
                        "message_type": message_type,
                        "contact_name": contact.get("name", "Unknown"),
                        "contact_role": contact.get("role", "Unknown"),
                        "contact_type": contact_type,
                        "contact_index": contact_index,
                        "field_name": field_name,
                        "char_count": len(message),
                        "persisted": persist_success,
                    },
                    cost_usd=cost,
                    duration_ms=timer.duration_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model,
                )

            except Exception as e:
                logger.exception(f"[{run_id[:16]}] Outreach generation failed: {e}")
                return self.create_error_result(
                    run_id=run_id,
                    error=str(e),
                    duration_ms=timer.duration_ms,
                )

    def _fetch_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch job document from MongoDB.

        Args:
            job_id: MongoDB ObjectId as string

        Returns:
            Job document or None if not found
        """
        try:
            object_id = ObjectId(job_id)
        except Exception as e:
            logger.error(f"Invalid job ID format: {job_id} - {e}")
            return None

        repo = self._get_repository()
        return repo.find_one({"_id": object_id})

    def _get_contact(
        self,
        job: Dict[str, Any],
        contact_type: ContactTypeField,
        contact_index: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract specific contact from job document.

        Args:
            job: Job document from MongoDB
            contact_type: "primary" or "secondary"
            contact_index: Index in the contacts array

        Returns:
            Contact dictionary or None if not found
        """
        if contact_type == "primary":
            contacts = job.get("primary_contacts") or []
        else:
            contacts = job.get("secondary_contacts") or []

        if not contacts:
            logger.warning(f"No {contact_type}_contacts found in job")
            return None

        if contact_index < 0 or contact_index >= len(contacts):
            logger.warning(
                f"Contact index {contact_index} out of range for {contact_type}_contacts "
                f"(length: {len(contacts)})"
            )
            return None

        return contacts[contact_index]

    def _build_outreach_context(
        self,
        job: Dict[str, Any],
        contact: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build context dictionary for outreach generation.

        Includes persona and core strengths from jd_annotations for enhanced
        personalization.

        Args:
            job: Job document from MongoDB
            contact: Contact dictionary

        Returns:
            Context dictionary with all relevant information
        """
        # Extract JD info
        extracted_jd = job.get("extracted_jd") or {}

        # Get pain points - prefer annotated pain points over extracted
        jd_annotations = job.get("jd_annotations") or {}
        pain_points = self._extract_annotated_pain_points(jd_annotations)
        if not pain_points:
            pain_points = job.get("pain_points") or []
        if not pain_points and extracted_jd:
            pain_points = extracted_jd.get("implied_pain_points") or []

        # Get company signals
        company_research = job.get("company_research") or {}
        signals = company_research.get("signals") or []
        company_signals = []
        for signal in signals[:3]:  # Take top 3 signals
            signal_text = f"- {signal.get('type', 'signal')}: {signal.get('description', '')}"
            if signal.get("date"):
                signal_text += f" ({signal['date']})"
            company_signals.append(signal_text)

        # Get selected STARs for achievements
        selected_stars = job.get("selected_stars") or []
        achievements = []
        for star in selected_stars[:2]:  # Take top 2 STARs
            if star.get("action"):
                actions = star["action"] if isinstance(star["action"], list) else [star["action"]]
                achievement = actions[0] if actions else ""
            else:
                achievement = star.get("situation", "")
            if star.get("result"):
                results = star["result"] if isinstance(star["result"], list) else [star["result"]]
                if results:
                    achievement += f" -> {results[0]}"
            if achievement:
                achievements.append(f"- {achievement}")

        # Build candidate summary from profile or STARs
        # Check MongoDB first, then file fallback for consistent grounding
        candidate_profile = job.get("candidate_profile") or self._load_candidate_profile() or ""
        candidate_summary = ""
        if candidate_profile:
            # Extract first few sentences
            sentences = candidate_profile.split(".")[:3]
            candidate_summary = ". ".join(sentences) + "."
        elif selected_stars:
            # Build from STAR companies
            companies = list(set(star.get("company", "") for star in selected_stars if star.get("company")))
            candidate_summary = f"Experience at: {', '.join(companies[:3])}"

        # Extract persona and core strengths from annotations
        persona_statement = self._extract_persona_statement(jd_annotations)
        core_strengths = self._extract_core_strengths(jd_annotations)

        return {
            "company": job.get("company") or extracted_jd.get("company", "Unknown"),
            "role": job.get("title") or extracted_jd.get("title", "Unknown"),
            "pain_points": "\n".join(f"- {pp}" for pp in pain_points[:5]) if pain_points else "Not available",
            "contact_name": contact.get("name", "Unknown"),
            "contact_role": contact.get("role", "Unknown"),
            "contact_type": contact.get("contact_type", "peer"),
            "why_relevant": contact.get("why_relevant", "Relevant to the role"),
            "company_signals": "\n".join(company_signals) if company_signals else "No recent signals available",
            "candidate_summary": candidate_summary or "Experienced engineering leader",
            "achievements": "\n".join(achievements) if achievements else "See resume for details",
            # New persona-related fields
            "persona_statement": persona_statement,
            "core_strengths": core_strengths,
            "has_persona": bool(persona_statement),
        }

    def _extract_persona_statement(self, jd_annotations: Dict[str, Any]) -> str:
        """
        Extract synthesized persona statement from jd_annotations.

        Args:
            jd_annotations: JD annotations dict from job document

        Returns:
            Persona statement string or empty string if not available
        """
        synthesized = jd_annotations.get("synthesized_persona") or {}
        return synthesized.get("persona_statement", "")

    def _extract_core_strengths(self, jd_annotations: Dict[str, Any]) -> str:
        """
        Extract core strengths from annotations for outreach personalization.

        Looks for annotations marked as core_strength or extremely_relevant relevance,
        or core_identity/strong_identity.

        Args:
            jd_annotations: JD annotations dict from job document

        Returns:
            Formatted string of core strengths, or default if none found
        """
        annotations = jd_annotations.get("annotations") or []
        strengths = []

        for ann in annotations:
            # Skip inactive annotations
            if not ann.get("is_active", True):
                continue

            # Check for strength/relevance indicators
            relevance = ann.get("relevance", "")
            identity = ann.get("identity", "")

            is_strength = relevance in ("core_strength", "extremely_relevant")
            is_identity = identity in ("core_identity", "strong_identity")

            if is_strength or is_identity:
                # Get the skill/text that represents this strength
                text = ann.get("matching_skill") or ann.get("target", {}).get("text", "")
                if text and len(text) < 60:  # Only short, clean texts
                    label = "Core strength" if is_strength else "Identity"
                    strengths.append(f"- {text}")

            # Limit to top 5 strengths
            if len(strengths) >= 5:
                break

        if strengths:
            return "\n".join(strengths)
        else:
            return "- Engineering leadership\n- Technical strategy\n- Team development"

    def _extract_annotated_pain_points(self, jd_annotations: Dict[str, Any]) -> List[str]:
        """
        Extract pain points from annotations that are marked with pain-related categories.

        Args:
            jd_annotations: JD annotations dict from job document

        Returns:
            List of pain point strings from annotations
        """
        annotations = jd_annotations.get("annotations") or []
        pain_points = []

        for ann in annotations:
            # Skip inactive annotations
            if not ann.get("is_active", True):
                continue

            # Check for pain point indicators in category or other fields
            category = ann.get("category", "").lower()
            annotation_type = ann.get("type", "").lower()

            # Look for pain-related annotations
            if "pain" in category or "pain" in annotation_type or "challenge" in category:
                text = ann.get("matching_skill") or ann.get("target", {}).get("text", "")
                if text and len(text) < 100:
                    pain_points.append(text)

            # Limit to top 5
            if len(pain_points) >= 5:
                break

        return pain_points

    def _generate_connection_message(
        self,
        context: Dict[str, Any],
        model: str,
    ) -> str:
        """
        Generate LinkedIn connection request (<=300 chars).

        Uses persona-enhanced prompt if persona is available in context.
        Uses Claude Code CLI exclusively via invoke_unified_sync (no LangChain fallback).

        Args:
            context: Context dictionary with job/contact info
            model: Model name to use (ignored - uses step config)

        Returns:
            Connection message string

        Raises:
            ValueError: If Claude CLI fails (no fallback to OpenAI)
        """
        # Choose system prompt based on persona availability
        if context.get("has_persona") and context.get("persona_statement"):
            # Use persona-enhanced prompt - LLM "becomes" the candidate
            logger.info("Using persona-enhanced system prompt for connection message")
            system_prompt = CONNECTION_SYSTEM_PROMPT_PERSONA.format(
                candidate_name=CANDIDATE_NAME,
                persona_statement=context["persona_statement"],
                core_strengths=context.get("core_strengths", "- Engineering leadership"),
                char_limit=CONNECTION_CHAR_LIMIT,
                signature=CANDIDATE_SIGNATURE,
                calendly=CANDIDATE_CALENDLY,
            )
        else:
            # Use base prompt
            system_prompt = CONNECTION_SYSTEM_PROMPT_BASE.format(
                char_limit=CONNECTION_CHAR_LIMIT,
                signature=CANDIDATE_SIGNATURE,
                calendly=CANDIDATE_CALENDLY,
            )

        user_prompt = CONNECTION_USER_PROMPT.format(
            company=context["company"],
            role=context["role"],
            pain_points=context["pain_points"],
            contact_name=context["contact_name"],
            contact_role=context["contact_role"],
            contact_type=context["contact_type"],
            why_relevant=context["why_relevant"],
            company_signals=context["company_signals"],
            char_limit=CONNECTION_CHAR_LIMIT,
        )

        # Generate message using Claude Code CLI (mandatory - no OpenAI fallback)
        result = invoke_unified_sync(
            prompt=user_prompt,
            system=system_prompt,
            step_name="outreach_generation",
            job_id="outreach",
            validate_json=False,
        )

        if not result.success:
            raise ValueError(f"Claude CLI failed for connection message: {result.error}")

        message = result.content.strip()

        # Validate and fix message
        message = self._validate_connection_message(message)

        return message

    def _generate_inmail_message(
        self,
        context: Dict[str, Any],
        model: str,
    ) -> tuple[str, str]:
        """
        Generate InMail message with subject and body.

        Uses persona-enhanced prompt if persona is available in context.
        Uses Claude Code CLI exclusively via invoke_unified_sync (no LangChain fallback).

        Args:
            context: Context dictionary with job/contact info
            model: Model name to use (ignored - uses step config)

        Returns:
            Tuple of (subject, body)

        Raises:
            ValueError: If Claude CLI fails (no fallback to OpenAI)
        """
        import json
        import re

        # Choose system prompt based on persona availability
        if context.get("has_persona") and context.get("persona_statement"):
            # Use persona-enhanced prompt - LLM "becomes" the candidate
            logger.info("Using persona-enhanced system prompt for InMail message")
            system_prompt = INMAIL_SYSTEM_PROMPT_PERSONA.format(
                candidate_name=CANDIDATE_NAME,
                persona_statement=context["persona_statement"],
                core_strengths=context.get("core_strengths", "- Engineering leadership"),
                min_chars=INMAIL_MIN_CHARS,
                max_chars=INMAIL_MAX_CHARS,
            )
        else:
            # Use base prompt
            system_prompt = INMAIL_SYSTEM_PROMPT_BASE.format(
                min_chars=INMAIL_MIN_CHARS,
                max_chars=INMAIL_MAX_CHARS,
            )

        user_prompt = INMAIL_USER_PROMPT.format(
            company=context["company"],
            role=context["role"],
            pain_points=context["pain_points"],
            contact_name=context["contact_name"],
            contact_role=context["contact_role"],
            contact_type=context["contact_type"],
            why_relevant=context["why_relevant"],
            company_signals=context["company_signals"],
            candidate_summary=context["candidate_summary"],
            achievements=context["achievements"],
            min_chars=INMAIL_MIN_CHARS,
            max_chars=INMAIL_MAX_CHARS,
        )

        # Generate message using Claude Code CLI (mandatory - no OpenAI fallback)
        result = invoke_unified_sync(
            prompt=user_prompt,
            system=system_prompt,
            step_name="outreach_generation",
            job_id="outreach",
            validate_json=False,
        )

        if not result.success:
            raise ValueError(f"Claude CLI failed for InMail message: {result.error}")

        content = result.content.strip()

        # Parse JSON response
        try:
            # Try to extract JSON from response
            if content.startswith("{"):
                parsed = json.loads(content)
            else:
                # Try to find JSON in response
                json_match = re.search(r'\{[^{}]*"subject"[^{}]*"body"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                else:
                    # Fallback: use content as body
                    parsed = {
                        "subject": f"Re: {context['role']} opportunity",
                        "body": content,
                    }
        except json.JSONDecodeError:
            logger.warning("Failed to parse InMail JSON response, using fallback")
            parsed = {
                "subject": f"Re: {context['role']} opportunity",
                "body": content,
            }

        subject = parsed.get("subject", f"Re: {context['role']} opportunity")
        body = parsed.get("body", content)

        # Validate subject length
        if len(subject) > 50:
            subject = subject[:47] + "..."

        return subject, body

    def _validate_connection_message(self, message: str) -> str:
        """
        Validate and fix LinkedIn connection message constraints.

        Ensures:
        - <=300 characters total
        - Contains Calendly link
        - Contains signature

        Args:
            message: Raw connection message

        Returns:
            Validated/fixed connection message
        """
        # Ensure signature is present
        if CANDIDATE_NAME.lower() not in message.lower():
            message = message.rstrip() + " " + CANDIDATE_SIGNATURE

        # Warn if Calendly missing (but don't fail)
        if CANDIDATE_CALENDLY.lower() not in message.lower():
            logger.warning("Connection message missing Calendly link")

        # Enforce 300 character limit
        if len(message) > CONNECTION_CHAR_LIMIT:
            logger.warning(
                f"Connection message exceeds {CONNECTION_CHAR_LIMIT} chars ({len(message)}), truncating..."
            )
            # Truncate while preserving signature
            content = message.replace(CANDIDATE_SIGNATURE, "").strip()
            content_limit = CONNECTION_CHAR_LIMIT - len(CANDIDATE_SIGNATURE) - 1
            if len(content) > content_limit:
                content = content[:content_limit - 3].rsplit(" ", 1)[0] + "..."
            message = content + " " + CANDIDATE_SIGNATURE

        return message

    def _persist_outreach(
        self,
        job_id: str,
        contact_type: ContactTypeField,
        contact_index: int,
        message_type: MessageType,
        message: str,
        subject: Optional[str] = None,
    ) -> bool:
        """
        Update contact in MongoDB with generated message.

        Args:
            job_id: Job ID
            contact_type: "primary" or "secondary"
            contact_index: Index in contacts array
            message_type: "connection" or "inmail"
            message: Generated message
            subject: Optional subject (for inmail)

        Returns:
            True if persisted successfully
        """
        try:
            object_id = ObjectId(job_id)
        except Exception:
            logger.error(f"Invalid job ID for persistence: {job_id}")
            return False

        # Build update path
        if contact_type == "primary":
            field_prefix = f"primary_contacts.{contact_index}"
        else:
            field_prefix = f"secondary_contacts.{contact_index}"

        # Build update document based on message type
        update_doc: Dict[str, Any] = {
            f"{field_prefix}.outreach_generated_at": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }

        if message_type == "connection":
            update_doc[f"{field_prefix}.linkedin_connection_message"] = message
            # Also update legacy field for backward compatibility
            update_doc[f"{field_prefix}.linkedin_message"] = message
        else:  # inmail
            update_doc[f"{field_prefix}.linkedin_inmail"] = message
            if subject:
                update_doc[f"{field_prefix}.linkedin_inmail_subject"] = subject

        repo = self._get_repository()
        try:
            result = repo.update_one(
                {"_id": object_id},
                {"$set": update_doc},
            )
            if result.modified_count > 0:
                logger.info(
                    f"Persisted {message_type} outreach for job {job_id}, "
                    f"{contact_type}[{contact_index}]"
                )
                return True
            else:
                logger.warning(f"No document updated for job {job_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to persist outreach: {e}")
            return False


# Convenience function for direct usage
async def generate_outreach(
    job_id: str,
    contact_index: int,
    contact_type: ContactTypeField = "primary",
    tier: ModelTier = ModelTier.BALANCED,
    message_type: MessageType = "connection",
    repository: Optional[JobRepositoryInterface] = None,
    use_claude_cli: bool = False,
) -> OperationResult:
    """
    Generate outreach message for a specific contact.

    Convenience wrapper around OutreachGenerationService.

    Args:
        job_id: MongoDB ObjectId of the job
        contact_index: Index in contacts array
        contact_type: "primary" or "secondary"
        tier: Model tier (FAST, BALANCED, QUALITY)
        message_type: "connection" or "inmail"
        repository: Optional job repository
        use_claude_cli: If True, use Claude Code CLI (Opus 4.5) for higher quality

    Returns:
        OperationResult with generated message
    """
    service = OutreachGenerationService(repository=repository, use_claude_cli=use_claude_cli)
    return await service.execute(
        job_id=job_id,
        contact_index=contact_index,
        contact_type=contact_type,
        tier=tier,
        message_type=message_type,
    )
