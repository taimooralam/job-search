"""
Unified LLM-Based Outreach Generation Service.

Provides multi-agent outreach generation using UnifiedLLM with:
- Claude Opus 4.5 (claude-opus-4-5-20251101) via CLI as primary
- Automatic LangChain/GPT-4o fallback when CLI fails
- MENA/Saudi cultural awareness
- Parallel processing for multiple contacts

Usage:
    from src.services.claude_outreach_service import ClaudeOutreachService

    service = ClaudeOutreachService()
    result = await service.generate_for_contact(
        contact=contact_dict,
        job_context=job_context_dict,
    )
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.common.unified_llm import UnifiedLLM, LLMResult
from src.common.llm_config import TierType
from src.common.mena_detector import MenaContext, detect_mena_region
from src.layer6_v2.prompts.outreach_prompts import (
    CONNECTION_CHAR_LIMIT,
    EMAIL_MAX_WORDS,
    EMAIL_MIN_WORDS,
    INMAIL_MAX_CHARS,
    INMAIL_MIN_CHARS,
    build_outreach_system_prompt,
    build_outreach_user_prompt,
    validate_connection_message,
    validate_email_message,
    validate_inmail_message,
)

logger = logging.getLogger(__name__)


# Candidate info (should be loaded from config in production)
CANDIDATE_NAME = "Taimoor Alam"
CANDIDATE_CALENDLY = "calendly.com/taimooralam/15min"
CANDIDATE_SIGNATURE = f"Best regards,\n{CANDIDATE_NAME}"


@dataclass
class OutreachPackage:
    """
    Complete outreach package for a single contact.

    Contains all three message types plus metadata.
    """

    contact_name: str
    contact_role: str
    contact_type: str
    linkedin_connection: str
    linkedin_connection_chars: int
    linkedin_inmail_subject: str
    linkedin_inmail_body: str
    linkedin_inmail_chars: int
    email_subject: str
    email_body: str
    email_words: int
    mena_context: Optional[MenaContext]
    generation_cost_usd: Optional[float]
    generation_time_ms: int
    model_used: str
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/MongoDB serialization."""
        return {
            "contact_name": self.contact_name,
            "contact_role": self.contact_role,
            "contact_type": self.contact_type,
            "linkedin_connection": {
                "message": self.linkedin_connection,
                "char_count": self.linkedin_connection_chars,
            },
            "linkedin_inmail": {
                "subject": self.linkedin_inmail_subject,
                "body": self.linkedin_inmail_body,
                "char_count": self.linkedin_inmail_chars,
            },
            "email": {
                "subject": self.email_subject,
                "body": self.email_body,
                "word_count": self.email_words,
            },
            "metadata": {
                "is_mena": self.mena_context.is_mena if self.mena_context else False,
                "region": self.mena_context.region if self.mena_context else None,
                "generation_cost_usd": self.generation_cost_usd,
                "generation_time_ms": self.generation_time_ms,
                "model_used": self.model_used,
                "generated_at": self.generated_at,
            },
        }


class ClaudeOutreachService:
    """
    Opus-based outreach generation with MENA awareness.

    Uses UnifiedLLM with Claude Opus 4.5 (via CLI) as primary for high-quality
    outreach generation, with automatic LangChain fallback when CLI fails.
    Includes cultural adaptation for MENA/Saudi opportunities.

    Attributes:
        tier: LLM tier level ("high" for Opus quality)
        timeout: LLM timeout in seconds
    """

    def __init__(
        self,
        timeout: int = 180,
        candidate_name: Optional[str] = None,
        calendly_link: Optional[str] = None,
    ):
        """
        Initialize the Claude outreach service.

        Args:
            timeout: LLM timeout in seconds (default 180s)
            candidate_name: Override candidate name (default from constant)
            calendly_link: Override Calendly link (default from constant)
        """
        # Use high tier (Opus) for outreach generation
        self.tier: TierType = "high"
        self.timeout = timeout

        # Candidate info
        self.candidate_name = candidate_name or CANDIDATE_NAME
        self.calendly_link = calendly_link or CANDIDATE_CALENDLY
        self.signature = f"Best regards,\n{self.candidate_name}"

    async def generate_for_contact(
        self,
        contact: Dict[str, Any],
        job_context: Dict[str, Any],
        mena_context: Optional[MenaContext] = None,
    ) -> OutreachPackage:
        """
        Generate complete outreach package for a single contact.

        Args:
            contact: Contact dictionary with name, role, contact_type, why_relevant
            job_context: Job context with company, role, location, pain_points, etc.
            mena_context: Optional pre-computed MENA context (will detect if not provided)

        Returns:
            OutreachPackage with all three message types
        """
        start_time = datetime.utcnow()

        # Detect MENA region if not provided
        if mena_context is None:
            mena_context = detect_mena_region(
                location=job_context.get("location"),
                company=job_context.get("company"),
                jd_text=job_context.get("jd_text"),
            )

        # Extract context fields
        contact_name = contact.get("name", "Hiring Manager")
        contact_role = contact.get("role", "Unknown")
        contact_type = contact.get("contact_type", "peer")
        why_relevant = contact.get("why_relevant", "Relevant to the role")

        # Build persona from job context
        persona_statement = job_context.get(
            "persona_statement",
            f"Senior engineering leader with expertise in building high-performing teams"
        )
        core_strengths = job_context.get(
            "core_strengths",
            "- Engineering leadership\n- Technical strategy\n- Team development"
        )

        # Build prompts
        system_prompt = build_outreach_system_prompt(
            candidate_name=self.candidate_name,
            persona_statement=persona_statement,
            core_strengths=core_strengths,
            calendly_link=self.calendly_link,
            signature=self.signature,
            mena_context=mena_context,
        )

        user_prompt = build_outreach_user_prompt(
            company=job_context.get("company", "Unknown"),
            role=job_context.get("role", "Unknown"),
            location=job_context.get("location", ""),
            contact_name=contact_name,
            contact_role=contact_role,
            contact_type=contact_type,
            why_relevant=why_relevant,
            pain_points=job_context.get("pain_points", []),
            company_signals=job_context.get("company_signals", []),
            achievements=job_context.get("achievements", []),
            candidate_summary=job_context.get("candidate_summary", ""),
        )

        # Combine prompts for CLI
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        # Generate job ID for tracking
        job_id = job_context.get("job_id", f"outreach-{contact_name[:10]}")

        logger.info(
            f"Generating outreach for {contact_name} ({contact_type}) - "
            f"MENA: {mena_context.is_mena}, Region: {mena_context.region}"
        )

        # Invoke UnifiedLLM (Claude CLI primary, LangChain fallback)
        llm = UnifiedLLM(
            step_name="outreach_generation",
            tier=self.tier,
            job_id=job_id,
        )
        result = await llm.invoke(
            prompt=full_prompt,
            job_id=job_id,
            validate_json=True,
        )

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        if not result.success:
            logger.error(f"LLM invocation failed for {contact_name}: {result.error}")
            # Return fallback package
            return self._create_fallback_package(
                contact_name=contact_name,
                contact_role=contact_role,
                contact_type=contact_type,
                mena_context=mena_context,
                error=result.error or "Unknown error",
                duration_ms=duration_ms,
            )

        # Parse and validate result
        return self._parse_outreach_result(
            result=result,
            contact_name=contact_name,
            contact_role=contact_role,
            contact_type=contact_type,
            mena_context=mena_context,
            duration_ms=duration_ms,
        )

    async def generate_batch(
        self,
        contacts: List[Dict[str, Any]],
        job_context: Dict[str, Any],
        max_concurrent: int = 5,
    ) -> List[OutreachPackage]:
        """
        Generate outreach for multiple contacts in parallel.

        Args:
            contacts: List of contact dictionaries
            job_context: Shared job context
            max_concurrent: Maximum concurrent generations (default 5)

        Returns:
            List of OutreachPackage in same order as input contacts
        """
        # Detect MENA region once for all contacts
        mena_context = detect_mena_region(
            location=job_context.get("location"),
            company=job_context.get("company"),
            jd_text=job_context.get("jd_text"),
        )

        logger.info(
            f"Generating outreach batch for {len(contacts)} contacts - "
            f"MENA: {mena_context.is_mena}, max_concurrent: {max_concurrent}"
        )

        # Use semaphore for controlled concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_limit(contact: Dict[str, Any]) -> OutreachPackage:
            async with semaphore:
                return await self.generate_for_contact(
                    contact=contact,
                    job_context=job_context,
                    mena_context=mena_context,
                )

        # Run all generations in parallel with limit
        tasks = [generate_with_limit(contact) for contact in contacts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        packages = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Error generating outreach for contact {i}: {result}")
                packages.append(
                    self._create_fallback_package(
                        contact_name=contacts[i].get("name", "Unknown"),
                        contact_role=contacts[i].get("role", "Unknown"),
                        contact_type=contacts[i].get("contact_type", "peer"),
                        mena_context=mena_context,
                        error=str(result),
                        duration_ms=0,
                    )
                )
            else:
                packages.append(result)

        return packages

    def _parse_outreach_result(
        self,
        result: LLMResult,
        contact_name: str,
        contact_role: str,
        contact_type: str,
        mena_context: MenaContext,
        duration_ms: int,
    ) -> OutreachPackage:
        """
        Parse LLM result into OutreachPackage.

        Args:
            result: LLMResult from UnifiedLLM
            contact_name: Contact's name
            contact_role: Contact's role
            contact_type: Contact type classification
            mena_context: MENA context
            duration_ms: Generation duration in milliseconds

        Returns:
            OutreachPackage with parsed messages
        """
        try:
            # Use parsed_json if available, otherwise parse content
            data = result.parsed_json
            if data is None:
                data = json.loads(result.content)

            # Extract LinkedIn connection
            connection_data = data.get("linkedin_connection", {})
            connection_msg = connection_data.get("message", "")
            connection_chars = len(connection_msg)

            # Validate connection message
            is_valid, error = validate_connection_message(connection_msg)
            if not is_valid:
                logger.warning(f"Connection message validation failed: {error}")
                # Truncate if too long
                if connection_chars > CONNECTION_CHAR_LIMIT:
                    connection_msg = connection_msg[:CONNECTION_CHAR_LIMIT - 3] + "..."
                    connection_chars = len(connection_msg)

            # Extract InMail
            inmail_data = data.get("linkedin_inmail", {})
            inmail_subject = inmail_data.get("subject", "")
            inmail_body = inmail_data.get("body", "")
            inmail_chars = len(inmail_body)

            # Validate InMail
            is_valid, error = validate_inmail_message(inmail_body, inmail_subject)
            if not is_valid:
                logger.warning(f"InMail validation failed: {error}")

            # Extract email
            email_data = data.get("email", {})
            email_subject = email_data.get("subject", "")
            email_body = email_data.get("body", "")
            email_words = len(email_body.split())

            # Validate email
            is_valid, error = validate_email_message(email_body)
            if not is_valid:
                logger.warning(f"Email validation failed: {error}")

            return OutreachPackage(
                contact_name=contact_name,
                contact_role=contact_role,
                contact_type=contact_type,
                linkedin_connection=connection_msg,
                linkedin_connection_chars=connection_chars,
                linkedin_inmail_subject=inmail_subject,
                linkedin_inmail_body=inmail_body,
                linkedin_inmail_chars=inmail_chars,
                email_subject=email_subject,
                email_body=email_body,
                email_words=email_words,
                mena_context=mena_context,
                generation_cost_usd=result.cost_usd,
                generation_time_ms=duration_ms,
                model_used=result.model,
                generated_at=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            logger.error(f"Error parsing outreach result: {e}")
            return self._create_fallback_package(
                contact_name=contact_name,
                contact_role=contact_role,
                contact_type=contact_type,
                mena_context=mena_context,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _create_fallback_package(
        self,
        contact_name: str,
        contact_role: str,
        contact_type: str,
        mena_context: MenaContext,
        error: str,
        duration_ms: int,
    ) -> OutreachPackage:
        """
        Create fallback outreach package when generation fails.

        Args:
            contact_name: Contact's name
            contact_role: Contact's role
            contact_type: Contact type
            mena_context: MENA context
            error: Error message
            duration_ms: Duration in milliseconds

        Returns:
            OutreachPackage with placeholder content
        """
        logger.warning(f"Creating fallback package for {contact_name}: {error}")

        # Basic fallback messages
        connection_msg = (
            f"Hi {contact_name}, I've applied for a role at your company and would "
            f"love to connect. My background in engineering leadership may be relevant. "
            f"{self.signature}"
        )[:CONNECTION_CHAR_LIMIT]

        inmail_subject = "Following up on my application"
        inmail_body = (
            f"Dear {contact_name},\n\n"
            f"I recently applied for a position at your company and wanted to introduce myself. "
            f"I'm a senior engineering leader with experience in building high-performing teams.\n\n"
            f"I'd welcome the opportunity to discuss how my background might be valuable.\n\n"
            f"{self.signature}"
        )

        email_subject = f"Application follow-up - {self.candidate_name}"
        email_body = inmail_body

        return OutreachPackage(
            contact_name=contact_name,
            contact_role=contact_role,
            contact_type=contact_type,
            linkedin_connection=connection_msg,
            linkedin_connection_chars=len(connection_msg),
            linkedin_inmail_subject=inmail_subject,
            linkedin_inmail_body=inmail_body,
            linkedin_inmail_chars=len(inmail_body),
            email_subject=email_subject,
            email_body=email_body,
            email_words=len(email_body.split()),
            mena_context=mena_context,
            generation_cost_usd=None,
            generation_time_ms=duration_ms,
            model_used="fallback",
            generated_at=datetime.utcnow().isoformat(),
        )


# Convenience function for direct usage
async def generate_outreach_with_claude(
    contact: Dict[str, Any],
    job_context: Dict[str, Any],
    timeout: int = 180,
) -> OutreachPackage:
    """
    Generate outreach for a single contact using Claude Opus 4.5.

    Convenience wrapper around ClaudeOutreachService.

    Args:
        contact: Contact dictionary
        job_context: Job context dictionary
        timeout: CLI timeout in seconds

    Returns:
        OutreachPackage with generated messages
    """
    service = ClaudeOutreachService(timeout=timeout)
    return await service.generate_for_contact(contact, job_context)
