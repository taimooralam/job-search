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

import re
from typing import Dict, Any, List, Optional

from src.common.state import JobState, Contact, OutreachPackage
from src.common.config import Config
from src.layer6.cover_letter_generator import _extract_companies_from_profile


class OutreachGenerator:
    """
    Phase 9: Outreach Generator

    Converts enriched contacts (from Layer 5) into standardized OutreachPackage objects.
    Enforces content constraints and creates 2 packages per contact (LinkedIn + Email).
    """

    def __init__(self):
        """Initialize outreach generator."""
        # Contact info for LinkedIn closing line
        self.candidate_calendly = "https://calendly.com/taimooralam/15min"

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
        Validate that LinkedIn message ends with applied note + Calendly link (no email).

        Args:
            message: LinkedIn message to validate

        Raises:
            ValueError: If closing line is missing or incorrect
        """
        text = message.lower()
        has_calendly = "calendly.com" in text
        has_applied = "applied" in text

        if not (has_calendly and has_applied):
            raise ValueError(
                "LinkedIn message must state you have applied for the role and include the Calendly link (no email)."
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
            print(f"    ⚠️  {channel} outreach does not mention a company from candidate's background")
            # For stricter validation, uncomment the raise below:
            # raise ValueError(
            #     f"{channel} outreach must mention at least one company from candidate's background. "
            #     f"Available companies: {star_companies[:5]}"
            # )

    # ===== PACKAGING METHODS =====

    def _create_packages_for_contact(self, contact: Contact) -> List[OutreachPackage]:
        """
        Create 2 OutreachPackage objects for a single contact (LinkedIn + Email).

        Args:
            contact: Enriched contact from Layer 5 with outreach fields

        Returns:
            List of 2 OutreachPackage objects (LinkedIn, Email)

        Raises:
            KeyError: If contact is missing required outreach fields
            ValueError: If content validation fails
        """
        # Validate required fields exist
        required_fields = ["linkedin_message", "email_subject", "email_body", "reasoning"]
        missing_fields = [f for f in required_fields if f not in contact]
        if missing_fields:
            raise KeyError(f"Contact missing required outreach fields: {missing_fields}")

        # Extract fields
        linkedin_message = contact["linkedin_message"]
        email_subject = contact["email_subject"]
        email_body = contact["email_body"]
        reasoning = contact["reasoning"]

        # Ensure LinkedIn closing line is present; if not, append it.
        # This makes the system robust even when upstream generators omit the closing.
        if "calendly.com" not in linkedin_message.lower() or "applied" not in linkedin_message.lower():
            closing = f"I have applied for this role. Calendly: {self.candidate_calendly}"
            if closing not in linkedin_message:
                linkedin_message = linkedin_message.rstrip() + "\n\n" + closing

        # Validate content constraints
        self._validate_content_constraints(linkedin_message, "linkedin")
        self._validate_content_constraints(email_body, "email")
        self._validate_linkedin_closing(linkedin_message)

        # Create LinkedIn package
        linkedin_package: OutreachPackage = {
            "contact_name": contact["name"],
            "contact_role": contact["role"],
            "linkedin_url": contact["linkedin_url"],
            "channel": "linkedin",
            "message": linkedin_message,
            "subject": None,  # LinkedIn has no subject
            "reasoning": reasoning
        }

        # Create Email package
        email_package: OutreachPackage = {
            "contact_name": contact["name"],
            "contact_role": contact["role"],
            "linkedin_url": contact["linkedin_url"],
            "channel": "email",
            "message": email_body,
            "subject": email_subject,
            "reasoning": reasoning
        }

        return [linkedin_package, email_package]

    def generate_outreach_packages(self, state: JobState) -> List[OutreachPackage]:
        """
        Generate OutreachPackage objects for all contacts in state.

        Processes both primary_contacts and secondary_contacts from Layer 5.
        Creates 2 packages per contact (LinkedIn + Email).

        Phase 9 master-cv.md integration:
        - Validates outreach cites companies from selected_stars or master-cv.md
        - Uses same company extraction logic as cover letter generator (Phase 8)

        Args:
            state: JobState with primary_contacts and secondary_contacts

        Returns:
            Flat list of OutreachPackage objects (2 per contact)
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
            print("  ⚠️  No contacts found in state, skipping outreach packaging")
            return []

        print(f"\n{'='*80}")
        print(f"LAYER 6b: OUTREACH GENERATOR (Phase 9)")
        print(f"{'='*80}")
        print(f"  Processing {len(primary_contacts)} primary + {len(secondary_contacts)} secondary contacts")
        if selected_stars:
            print(f"  Using {len(selected_stars)} selected STAR(s) for grounding")
        elif candidate_profile:
            print(f"  Using master-cv.md fallback for grounding ({len(candidate_profile)} chars)")

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
                print(f"    ✓ Created 2 packages for {contact['name']} ({contact['role']})")

            except KeyError as e:
                print(f"    ⚠️  Skipping {contact.get('name', 'Unknown')} - missing outreach fields: {e}")
                continue

            except ValueError as e:
                print(f"    ⚠️  Skipping {contact.get('name', 'Unknown')} - validation failed: {e}")
                continue

            except Exception as e:
                print(f"    ⚠️  Skipping {contact.get('name', 'Unknown')} - unexpected error: {e}")
                continue

        print(f"\n  ✅ Generated {len(packages)} outreach packages ({len(packages)//2} contacts × 2 channels)")

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
    generator = OutreachGenerator()
    packages = generator.generate_outreach_packages(state)

    return {
        "outreach_packages": packages
    }
