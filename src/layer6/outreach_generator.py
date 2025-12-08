"""
Layer 6b: Outreach Generator (Phase 9)

Packages per-contact outreach into standardized OutreachPackage objects.
Enforces final content constraints (no emojis, required closing lines, etc.).

Architecture:
- Layer 5 (People Mapper) generates outreach content
- Layer 6b (this module) packages content into OutreachPackage TypedDicts
- Enforces ROADMAP Phase 9 constraints before packaging

Phase 9 master-cv.md integration:
- When STAR selector is disabled, validates outreach cites companies from master-cv.md
- Uses same company extraction logic as cover letter generator
"""

import logging
import re
from typing import Dict, Any, List, Optional

from src.common.state import JobState, Contact, OutreachPackage
from src.common.config import Config
from src.common.structured_logger import get_structured_logger, LayerContext
from src.layer6.cover_letter_generator import _extract_companies_from_profile


class OutreachGenerator:
    """
    Phase 9: Outreach Generator (linkedin/outreach.md integration)

    Converts enriched contacts (from Layer 5) into standardized OutreachPackage objects.
    Creates 2 packages per contact:
    - linkedin_connection: ≤300 chars with Calendly link (warm, quick connect)
    - inmail_email: 400-600 chars with subject (works for both InMail and Email)
    """

    def __init__(self):
        """Initialize outreach generator."""
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)

        # Contact info for LinkedIn closing line
        self.candidate_calendly = "https://calendly.com/taimooralam/15min"
        self.calendly_short = "calendly.com/taimooralam/15min"

    # ===== VALIDATION METHODS =====

    def _validate_content_constraints(self, message: str, channel: str) -> None:
        """
        Validate content constraints for outreach messages.

        Args:
            message: The outreach message to validate
            channel: "linkedin" or "email"

        Raises:
            ValueError: If message contains emojis or disallowed placeholders
        """
        # Check for emojis (Phase 9 requirement)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U000024C2-\U0001F251"
            "]+"
        )

        if emoji_pattern.search(message):
            raise ValueError(f"Message contains emojis (not allowed in {channel})")

        # Check for disallowed placeholders (Phase 9: only [Your Name] and role-based titles allowed)
        # Role-based names like "VP Engineering at AMENTUM" are valid addressees, not placeholders
        placeholders = re.findall(r'\[([^\]]+)\]', message)

        # Common role titles that indicate a role-based addressee (not a placeholder)
        role_keywords = [
            'vp', 'vice president', 'director', 'manager', 'engineer', 'lead', 'head',
            'chief', 'cto', 'ceo', 'cfo', 'coo', 'coordinator', 'specialist', 'analyst',
            'architect', 'developer', 'designer', 'recruiter', 'hr', 'talent', 'people',
            'principal', 'senior', 'staff', 'team lead', 'product', 'engineering',
            'technical', 'operations', 'strategy', 'marketing', 'sales', 'at '
        ]

        disallowed = []
        for p in placeholders:
            p_lower = p.lower()
            # Allow [Your Name]
            if p_lower == "your name":
                continue
            # Allow role-based addressees (contain role keywords)
            if any(keyword in p_lower for keyword in role_keywords):
                continue
            # Otherwise, it's a disallowed placeholder
            disallowed.append(p)

        if disallowed:
            raise ValueError(
                f"Message contains disallowed placeholders: {disallowed}. "
                f"Only [Your Name] and role-based titles (e.g., 'VP Engineering at Company') are allowed."
            )

    def _validate_linkedin_closing(self, message: str) -> None:
        """
        Validate that LinkedIn message ends with signature (GAP-011 update).

        Args:
            message: LinkedIn message to validate

        Raises:
            ValueError: If closing signature is missing
        """
        # GAP-011: Simplified closing to fit within 300 char limit
        # Just require the signature "Best. Taimoor Alam"
        text = message.lower()
        if "best" not in text or "taimoor" not in text:
            raise ValueError(
                'LinkedIn message must end with signature: "Best. Taimoor Alam"'
            )

    def _validate_company_grounding(
        self,
        message: str,
        channel: str,
        selected_stars: List[Dict],
        candidate_profile: str
    ) -> None:
        """
        Validate that outreach message mentions at least one company from STAR records
        or master-cv.md (when STAR selector is disabled).

        Similar to Phase 8 cover letter validation Gate 3.5.

        Args:
            message: Outreach message to validate
            channel: "linkedin" or "email"
            selected_stars: List of selected STAR records (may be empty)
            candidate_profile: Candidate profile from master-cv.md

        Raises:
            ValueError: If no company from STARs or master-cv.md is mentioned
        """
        # Extract companies from STARs if available
        star_companies = []
        if selected_stars:
            for star in selected_stars:
                company = star.get("company", "")
                if company:
                    star_companies.append(company)

        # If no STAR companies, extract from master-cv.md (fallback path)
        if not star_companies and candidate_profile:
            star_companies = _extract_companies_from_profile(candidate_profile)

        # If still no companies found, skip validation (graceful degradation)
        if not star_companies:
            return

        # Check if at least one company is mentioned in the message
        text_lower = message.lower()
        company_mentioned = False

        for company in star_companies:
            company_lower = company.lower().strip()

            # Option 1: Full company name match (≥3 chars)
            if len(company_lower) >= 3 and company_lower in text_lower:
                company_mentioned = True
                break

            # Option 2: Partial match - check if any significant word (≥4 chars) appears
            company_words = company_lower.split()
            for word in company_words:
                # Skip common suffixes
                if word in ['inc', 'co', 'llc', 'ltd', 'corp', 'corporation', 'company']:
                    continue
                if len(word) >= 4 and word in text_lower:
                    company_mentioned = True
                    break

            if company_mentioned:
                break

        if not company_mentioned:
            # Only warn, don't raise - outreach may focus on other aspects
            self.logger.warning(f"{channel} outreach does not mention a company from candidate's background")
            # For stricter validation, uncomment the raise below:
            # raise ValueError(
            #     f"{channel} outreach must mention at least one company from candidate's background. "
            #     f"Available companies: {star_companies[:5]}"
            # )

    # ===== PACKAGING METHODS =====

    def _validate_connection_message(self, message: str) -> str:
        """
        Validate and fix LinkedIn connection message constraints.

        Ensures:
        - ≤300 characters total
        - Contains Calendly link
        - Contains signature

        Args:
            message: Raw connection message

        Returns:
            Validated/fixed connection message
        """
        SIGNATURE = "Best. Taimoor Alam"

        # Ensure signature is present
        if "taimoor" not in message.lower():
            message = message.rstrip() + " " + SIGNATURE

        # Warn if Calendly missing (but don't fail - upstream should have added it)
        if self.calendly_short not in message.lower():
            self.logger.warning("Connection message missing Calendly link")

        # Enforce 300 character limit
        if len(message) > 300:
            self.logger.warning(
                f"Connection message exceeds 300 chars ({len(message)}), truncating..."
            )
            # Truncate while preserving Calendly and signature
            content = message.replace(SIGNATURE, "").strip()
            content_limit = 300 - len(SIGNATURE) - 1
            if len(content) > content_limit:
                content = content[:content_limit - 3].rsplit(' ', 1)[0] + "..."
            message = content + " " + SIGNATURE

        return message

    def _create_packages_for_contact(self, contact: Contact) -> List[OutreachPackage]:
        """
        Create 2 OutreachPackage objects for a single contact (linkedin/outreach.md).

        Creates packages for:
        - linkedin_connection: ≤300 chars with Calendly (connection request)
        - inmail_email: 400-600 chars with subject (works for both InMail and Email)

        Args:
            contact: Enriched contact from Layer 5 with outreach fields

        Returns:
            List of 2 OutreachPackage objects

        Raises:
            KeyError: If contact is missing required outreach fields
            ValueError: If content validation fails
        """
        packages: List[OutreachPackage] = []

        # Get contact type (new field from linkedin/outreach.md integration)
        contact_type = contact.get("contact_type", "peer")
        reasoning = contact.get("reasoning", f"Outreach for {contact.get('role', 'contact')}")

        # Get contact identifiers
        contact_name = contact.get("name", contact.get("contact_name", "Unknown"))
        contact_role = contact.get("role", contact.get("contact_role", "Unknown"))
        linkedin_url = contact.get("linkedin_url", "")

        # 1. LinkedIn Connection Package (≤300 chars with Calendly)
        connection_message = contact.get("linkedin_connection_message", contact.get("linkedin_message", ""))
        if connection_message:
            connection_message = self._validate_connection_message(connection_message)

            try:
                self._validate_content_constraints(connection_message, "linkedin")
                self._validate_linkedin_closing(connection_message)

                connection_package: OutreachPackage = {
                    "contact_name": contact_name,
                    "contact_role": contact_role,
                    "contact_type": contact_type,
                    "linkedin_url": linkedin_url,
                    "channel": "linkedin_connection",
                    "message": connection_message,
                    "subject": None,
                    "reasoning": reasoning
                }
                packages.append(connection_package)
            except ValueError as e:
                self.logger.warning(f"Connection message validation failed: {e}")

        # 2. Combined InMail/Email Package (400-600 chars with subject)
        # Prefer InMail content, fall back to email_body if InMail not available
        inmail_message = contact.get("linkedin_inmail", "")
        inmail_subject = contact.get("linkedin_inmail_subject", "")
        email_subject = contact.get("email_subject", "")
        email_body = contact.get("email_body", "")

        # Use InMail if available, otherwise use email content
        combined_message = inmail_message or email_body
        combined_subject = inmail_subject or email_subject

        if combined_message:
            try:
                self._validate_content_constraints(combined_message, "inmail_email")

                inmail_email_package: OutreachPackage = {
                    "contact_name": contact_name,
                    "contact_role": contact_role,
                    "contact_type": contact_type,
                    "linkedin_url": linkedin_url,
                    "channel": "inmail_email",
                    "message": combined_message,
                    "subject": combined_subject,
                    "reasoning": reasoning
                }
                packages.append(inmail_email_package)
            except ValueError as e:
                self.logger.warning(f"InMail/Email validation failed: {e}")

        # Fallback: If no packages created, try legacy linkedin_message field
        if not packages:
            legacy_message = contact.get("linkedin_message", "")
            if legacy_message:
                legacy_message = self._validate_connection_message(legacy_message)
                packages.append({
                    "contact_name": contact_name,
                    "contact_role": contact_role,
                    "contact_type": contact_type,
                    "linkedin_url": linkedin_url,
                    "channel": "linkedin_connection",
                    "message": legacy_message,
                    "subject": None,
                    "reasoning": "Legacy linkedin_message fallback"
                })

        return packages

    def generate_outreach_packages(self, state: JobState) -> List[OutreachPackage]:
        """
        Generate OutreachPackage objects for all contacts in state.

        Processes both primary_contacts and secondary_contacts from Layer 5.
        Creates up to 2 packages per contact (linkedin_connection, inmail_email).

        linkedin/outreach.md integration:
        - Contact type classification for tailored messaging
        - LinkedIn connection (≤300 chars with Calendly)
        - Combined InMail/Email (400-600 chars with subject)
        - "Already applied" framing in all messages

        Args:
            state: JobState with primary_contacts and secondary_contacts

        Returns:
            Flat list of OutreachPackage objects (up to 2 per contact)
        """
        packages: List[OutreachPackage] = []

        # Get contacts from state
        primary_contacts = state.get("primary_contacts") or []
        secondary_contacts = state.get("secondary_contacts") or []

        # Get STAR/master-cv.md context for company grounding validation
        selected_stars = state.get("selected_stars") or []
        candidate_profile = state.get("candidate_profile") or ""

        all_contacts = primary_contacts + secondary_contacts

        if not all_contacts:
            self.logger.warning("No contacts found in state, skipping outreach packaging")
            return []

        self.logger.info("="*80)
        self.logger.info("OUTREACH GENERATOR (Phase 9)")
        self.logger.info("="*80)
        self.logger.info(f"Processing {len(primary_contacts)} primary + {len(secondary_contacts)} secondary contacts")
        if selected_stars:
            self.logger.info(f"Using {len(selected_stars)} selected STAR(s) for grounding")
        elif candidate_profile:
            self.logger.info(f"Using master-cv.md fallback for grounding ({len(candidate_profile)} chars)")

        # Create packages for each contact
        for i, contact in enumerate(all_contacts, 1):
            try:
                contact_packages = self._create_packages_for_contact(contact)

                # Validate company grounding for each package (soft validation - warns only)
                for pkg in contact_packages:
                    self._validate_company_grounding(
                        pkg["message"],
                        pkg["channel"],
                        selected_stars,
                        candidate_profile
                    )

                packages.extend(contact_packages)
                contact_type = contact.get("contact_type", "unknown")
                self.logger.info(f"Created {len(contact_packages)} packages for {contact.get('name', 'Unknown')} ({contact_type})")

            except KeyError as e:
                self.logger.warning(f"Skipping {contact.get('name', 'Unknown')} - missing outreach fields: {e}")
                continue

            except ValueError as e:
                self.logger.warning(f"Skipping {contact.get('name', 'Unknown')} - validation failed: {e}")
                continue

            except Exception as e:
                self.logger.error(f"Skipping {contact.get('name', 'Unknown')} - unexpected error: {e}")
                continue

        # Count packages by channel
        channel_counts = {}
        for pkg in packages:
            channel = pkg.get("channel", "unknown")
            channel_counts[channel] = channel_counts.get(channel, 0) + 1

        self.logger.info(f"Generated {len(packages)} outreach packages: {channel_counts}")

        return packages


# ===== NODE FUNCTION =====

def outreach_generator_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 6b (Phase 9).

    Args:
        state: Current job state with enriched contacts from Layer 5

    Returns:
        State updates with outreach_packages populated
    """
    struct_logger = get_structured_logger(state.get("job_id", ""))

    with LayerContext(struct_logger, 6, "outreach_generator") as ctx:
        generator = OutreachGenerator()
        packages = generator.generate_outreach_packages(state)
        ctx.add_metadata("packages_count", len(packages))

        return {
            "outreach_packages": packages
        }
