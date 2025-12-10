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
from langchain_core.messages import HumanMessage, SystemMessage
from pymongo import MongoClient

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
CONNECTION_SYSTEM_PROMPT = """You are an expert at writing highly personalized LinkedIn connection requests.

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

INMAIL_SYSTEM_PROMPT = """You are an expert at writing highly personalized LinkedIn InMail messages.

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

    Model tiers:
    - FAST: gpt-4o-mini (cheap, quick)
    - BALANCED: gpt-4o (good quality/cost)
    - QUALITY: claude-sonnet (best quality)
    """

    operation_name = "generate-outreach"

    def __init__(self, db_client: Optional[MongoClient] = None):
        """
        Initialize the outreach generation service.

        Args:
            db_client: Optional MongoDB client. If None, creates one from env.
        """
        self._db_client = db_client

    def _get_db(self) -> MongoClient:
        """Get or create MongoDB client."""
        if self._db_client is not None:
            return self._db_client

        mongo_uri = (
            os.getenv("MONGODB_URI")
            or os.getenv("MONGO_URI")
            or "mongodb://localhost:27017"
        )
        return MongoClient(mongo_uri)

    def _get_db_name(self) -> str:
        """Get database name from environment."""
        return os.getenv("MONGO_DB_NAME", "jobs")

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

        client = self._get_db()
        try:
            db = client[self._get_db_name()]
            return db["level-2"].find_one({"_id": object_id})
        finally:
            if self._db_client is None:
                client.close()

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

        Args:
            job: Job document from MongoDB
            contact: Contact dictionary

        Returns:
            Context dictionary with all relevant information
        """
        # Extract JD info
        extracted_jd = job.get("extracted_jd") or {}

        # Get pain points
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
        candidate_profile = job.get("candidate_profile") or ""
        candidate_summary = ""
        if candidate_profile:
            # Extract first few sentences
            sentences = candidate_profile.split(".")[:3]
            candidate_summary = ". ".join(sentences) + "."
        elif selected_stars:
            # Build from STAR companies
            companies = list(set(star.get("company", "") for star in selected_stars if star.get("company")))
            candidate_summary = f"Experience at: {', '.join(companies[:3])}"

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
        }

    def _generate_connection_message(
        self,
        context: Dict[str, Any],
        model: str,
    ) -> str:
        """
        Generate LinkedIn connection request (<=300 chars).

        Args:
            context: Context dictionary with job/contact info
            model: Model name to use

        Returns:
            Connection message string
        """
        from src.common.llm_factory import create_tracked_llm

        # Create LLM
        llm = create_tracked_llm(
            model=model,
            temperature=0.7,  # Slightly creative for personalization
            layer="outreach_service",
        )

        # Format prompts
        system_prompt = CONNECTION_SYSTEM_PROMPT.format(
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

        # Generate message
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = llm.invoke(messages)
        message = response.content.strip()

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

        Args:
            context: Context dictionary with job/contact info
            model: Model name to use

        Returns:
            Tuple of (subject, body)
        """
        import json

        from src.common.llm_factory import create_tracked_llm

        # Create LLM
        llm = create_tracked_llm(
            model=model,
            temperature=0.7,
            layer="outreach_service",
        )

        # Format prompts
        system_prompt = INMAIL_SYSTEM_PROMPT.format(
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

        # Generate message
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Parse JSON response
        try:
            # Try to extract JSON from response
            if content.startswith("{"):
                result = json.loads(content)
            else:
                # Try to find JSON in response
                import re
                json_match = re.search(r'\{[^{}]*"subject"[^{}]*"body"[^{}]*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    # Fallback: use content as body
                    result = {
                        "subject": f"Re: {context['role']} opportunity",
                        "body": content,
                    }
        except json.JSONDecodeError:
            logger.warning("Failed to parse InMail JSON response, using fallback")
            result = {
                "subject": f"Re: {context['role']} opportunity",
                "body": content,
            }

        subject = result.get("subject", f"Re: {context['role']} opportunity")
        body = result.get("body", content)

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

        client = self._get_db()
        try:
            db = client[self._get_db_name()]
            result = db["level-2"].update_one(
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
        finally:
            if self._db_client is None:
                client.close()


# Convenience function for direct usage
async def generate_outreach(
    job_id: str,
    contact_index: int,
    contact_type: ContactTypeField = "primary",
    tier: ModelTier = ModelTier.BALANCED,
    message_type: MessageType = "connection",
    db_client: Optional[MongoClient] = None,
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
        db_client: Optional MongoDB client

    Returns:
        OperationResult with generated message
    """
    service = OutreachGenerationService(db_client=db_client)
    return await service.execute(
        job_id=job_id,
        contact_index=contact_index,
        contact_type=contact_type,
        tier=tier,
        message_type=message_type,
    )
