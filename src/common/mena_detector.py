"""
MENA Region Detection Utility.

Provides deterministic detection of Middle East and North Africa (MENA) region
from job location, company name, and other contextual signals. Used to apply
cultural adaptations to outreach messages.

Usage:
    from src.common.mena_detector import detect_mena_region, MenaContext

    # From job data
    context = detect_mena_region(
        location="Riyadh, Saudi Arabia",
        company="NEOM"
    )

    if context.is_mena:
        # Apply MENA-specific formatting
        greeting = "As-salaam Alaykum" if context.use_arabic_greeting else "Dear"
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Set

logger = logging.getLogger(__name__)


# Type definitions
FormalityLevel = Literal["high", "standard"]
ConfidenceLevel = Literal["high", "medium", "low", "none"]


@dataclass
class MenaContext:
    """
    MENA region context for outreach personalization.

    Attributes:
        is_mena: Whether the job/company is in MENA region
        region: Specific country/region detected (e.g., "Saudi Arabia")
        confidence: Detection confidence level
        use_arabic_greeting: Whether to use Arabic greetings
        formality_level: Expected formality ("high" for MENA, "standard" otherwise)
        timeline_multiplier: Hiring timeline adjustment (1.5x for MENA)
        signals_detected: List of signals that triggered MENA detection
        vision_references: Relevant vision/initiative references (e.g., "Vision 2030")
        suggested_adaptations: List of suggested cultural adaptations
    """

    is_mena: bool = False
    region: Optional[str] = None
    confidence: ConfidenceLevel = "none"
    use_arabic_greeting: bool = False
    formality_level: FormalityLevel = "standard"
    timeline_multiplier: float = 1.0
    signals_detected: List[str] = field(default_factory=list)
    vision_references: List[str] = field(default_factory=list)
    suggested_adaptations: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_mena": self.is_mena,
            "region": self.region,
            "confidence": self.confidence,
            "use_arabic_greeting": self.use_arabic_greeting,
            "formality_level": self.formality_level,
            "timeline_multiplier": self.timeline_multiplier,
            "signals_detected": self.signals_detected,
            "vision_references": self.vision_references,
            "suggested_adaptations": self.suggested_adaptations,
        }


# ===== MENA DETECTION INDICATORS =====

# GCC (Gulf Cooperation Council) countries - highest priority
GCC_COUNTRIES = {
    "saudi arabia": "Saudi Arabia",
    "kingdom of saudi arabia": "Saudi Arabia",
    "ksa": "Saudi Arabia",
    "united arab emirates": "UAE",
    "uae": "UAE",
    "qatar": "Qatar",
    "kuwait": "Kuwait",
    "oman": "Oman",
    "bahrain": "Bahrain",
}

# Broader MENA countries
MENA_COUNTRIES = {
    **GCC_COUNTRIES,
    "egypt": "Egypt",
    "jordan": "Jordan",
    "lebanon": "Lebanon",
    "morocco": "Morocco",
    "tunisia": "Tunisia",
    "algeria": "Algeria",
    "iraq": "Iraq",
}

# Major cities mapped to countries
MENA_CITIES = {
    # Saudi Arabia
    "riyadh": "Saudi Arabia",
    "jeddah": "Saudi Arabia",
    "dammam": "Saudi Arabia",
    "mecca": "Saudi Arabia",
    "makkah": "Saudi Arabia",
    "medina": "Saudi Arabia",
    "madinah": "Saudi Arabia",
    "khobar": "Saudi Arabia",
    "dhahran": "Saudi Arabia",
    "tabuk": "Saudi Arabia",
    # UAE
    "dubai": "UAE",
    "abu dhabi": "UAE",
    "sharjah": "UAE",
    "ajman": "UAE",
    "ras al khaimah": "UAE",
    # Qatar
    "doha": "Qatar",
    # Kuwait
    "kuwait city": "Kuwait",
    # Oman
    "muscat": "Oman",
    # Bahrain
    "manama": "Bahrain",
    # Egypt
    "cairo": "Egypt",
    "alexandria": "Egypt",
    "giza": "Egypt",
    # Jordan
    "amman": "Jordan",
    # Lebanon
    "beirut": "Lebanon",
}

# Company/project indicators (primarily Saudi mega-projects)
COMPANY_INDICATORS = {
    # Saudi Mega Projects
    "neom": ("Saudi Arabia", ["Vision 2030", "digital transformation"]),
    "the line": ("Saudi Arabia", ["Vision 2030", "sustainable city"]),
    "oxagon": ("Saudi Arabia", ["Vision 2030", "industrial innovation"]),
    "trojena": ("Saudi Arabia", ["Vision 2030", "tourism"]),
    "red sea": ("Saudi Arabia", ["Vision 2030", "tourism"]),
    "qiddiya": ("Saudi Arabia", ["Vision 2030", "entertainment"]),
    "diriyah": ("Saudi Arabia", ["Vision 2030", "heritage"]),
    # Saudi Companies
    "aramco": ("Saudi Arabia", ["energy transformation"]),
    "saudi aramco": ("Saudi Arabia", ["energy transformation"]),
    "sabic": ("Saudi Arabia", ["industrial diversification"]),
    "stc": ("Saudi Arabia", ["digital transformation"]),
    "saudi telecom": ("Saudi Arabia", ["digital transformation"]),
    "misk": ("Saudi Arabia", ["Vision 2030", "youth development"]),
    "misk foundation": ("Saudi Arabia", ["Vision 2030", "youth development"]),
    "acwa power": ("Saudi Arabia", ["renewable energy", "Vision 2030"]),
    "pif": ("Saudi Arabia", ["Vision 2030", "investment"]),
    "public investment fund": ("Saudi Arabia", ["Vision 2030", "investment"]),
    # UAE Companies
    "adnoc": ("UAE", ["energy diversification"]),
    "emirates": ("UAE", ["aviation"]),
    "etisalat": ("UAE", ["digital transformation"]),
    "masdar": ("UAE", ["renewable energy"]),
    # Qatar
    "qatar airways": ("Qatar", ["aviation"]),
    "qatar foundation": ("Qatar", ["education", "innovation"]),
}

# Keywords that suggest MENA context
MENA_KEYWORDS = {
    "vision 2030",
    "saudi vision",
    "gcc",
    "gulf cooperation council",
    "digital transformation saudi",
    "giga project",
    "mega project",
}


def detect_mena_region(
    location: Optional[str] = None,
    company: Optional[str] = None,
    jd_text: Optional[str] = None,
) -> MenaContext:
    """
    Detect MENA region from job context.

    Uses a multi-signal approach:
    1. Explicit country/city in location (highest confidence)
    2. Known company/project indicators
    3. Keywords in JD text (lowest confidence)

    Args:
        location: Job location string (e.g., "Riyadh, Saudi Arabia")
        company: Company name
        jd_text: Full job description text (optional, for keyword detection)

    Returns:
        MenaContext with detection results and cultural context
    """
    signals: List[str] = []
    detected_region: Optional[str] = None
    confidence: ConfidenceLevel = "none"
    vision_refs: Set[str] = set()

    # Normalize inputs for matching
    location_lower = (location or "").lower().strip()
    company_lower = (company or "").lower().strip()
    jd_lower = (jd_text or "").lower()

    # Step 1: Check location for countries (highest confidence)
    for country_key, country_name in MENA_COUNTRIES.items():
        if country_key in location_lower:
            detected_region = country_name
            signals.append(f"Location: {country_name}")
            confidence = "high"
            # Add Vision 2030 reference for Saudi Arabia
            if country_name == "Saudi Arabia":
                vision_refs.add("Vision 2030")
            break

    # Step 2: Check location for cities
    if not detected_region:
        for city, country_name in MENA_CITIES.items():
            if city in location_lower:
                detected_region = country_name
                signals.append(f"City: {city.title()} ({country_name})")
                confidence = "high"
                if country_name == "Saudi Arabia":
                    vision_refs.add("Vision 2030")
                break

    # Step 3: Check company name for known indicators
    for company_key, (country_name, refs) in COMPANY_INDICATORS.items():
        if company_key in company_lower:
            if not detected_region:
                detected_region = country_name
                confidence = "medium"
            signals.append(f"Company: {company_key.title()}")
            vision_refs.update(refs)
            break

    # Step 4: Check JD text for keywords (only if no other signals)
    if not detected_region and jd_lower:
        for keyword in MENA_KEYWORDS:
            if keyword in jd_lower:
                # Don't set region from keywords alone, but note the signal
                signals.append(f"Keyword: {keyword}")
                if "vision 2030" in keyword or "saudi" in keyword:
                    detected_region = "Saudi Arabia"
                    confidence = "low"
                    vision_refs.add("Vision 2030")
                    break
                elif "gcc" in keyword or "gulf" in keyword:
                    detected_region = "GCC Region"
                    confidence = "low"
                    break

    # If no MENA detected, return default context
    if not detected_region:
        logger.debug("No MENA region detected")
        return MenaContext()

    # Build cultural context based on region
    is_gcc = detected_region in ["Saudi Arabia", "UAE", "Qatar", "Kuwait", "Oman", "Bahrain", "GCC Region"]
    is_saudi = detected_region == "Saudi Arabia"

    # Build suggested adaptations
    adaptations = []
    if is_gcc:
        adaptations.append("Use formal greeting (Dear Mr./Ms.)")
        adaptations.append("Use title + first name format")
        adaptations.append("Emphasize long-term value and relationship")
        if is_saudi:
            adaptations.append("Reference Vision 2030 alignment if relevant")
            adaptations.append("Consider As-salaam Alaykum greeting")
            adaptations.append("Use Saudi email structure (value-first, 3 proof bullets)")

    logger.info(
        f"MENA region detected: {detected_region} (confidence: {confidence}) - "
        f"signals: {signals}"
    )

    return MenaContext(
        is_mena=True,
        region=detected_region,
        confidence=confidence,
        use_arabic_greeting=is_saudi,  # Only for Saudi Arabia
        formality_level="high" if is_gcc else "standard",
        timeline_multiplier=1.5 if is_gcc else 1.0,
        signals_detected=signals,
        vision_references=sorted(vision_refs),
        suggested_adaptations=adaptations,
    )


def format_mena_greeting(
    contact_name: str,
    context: MenaContext,
    contact_title: Optional[str] = None,
) -> str:
    """
    Format greeting based on MENA context.

    Args:
        contact_name: Contact's name
        context: MENA context from detection
        contact_title: Optional title (Mr., Ms., Dr., etc.)

    Returns:
        Formatted greeting string
    """
    if not context.is_mena or context.formality_level != "high":
        # Standard greeting
        if contact_title:
            return f"Dear {contact_title} {contact_name},"
        return f"Dear {contact_name},"

    # MENA high-formality greeting
    if context.use_arabic_greeting:
        # Saudi Arabic greeting
        if contact_title:
            return f"As-salaam Alaykum,\n\nDear {contact_title} {contact_name},"
        return f"As-salaam Alaykum,\n\nDear {contact_name},"

    # GCC formal greeting (non-Saudi)
    if contact_title:
        return f"Dear {contact_title} {contact_name},"
    return f"Dear {contact_name},"


def format_mena_closing(context: MenaContext) -> str:
    """
    Format email closing based on MENA context.

    Args:
        context: MENA context from detection

    Returns:
        Formatted closing string
    """
    if context.use_arabic_greeting:
        return "Shukran for your time and consideration.\n\nBest regards,"
    elif context.is_mena:
        return "Thank you for your time and consideration.\n\nBest regards,"
    else:
        return "Best regards,"


def get_vision_reference(context: MenaContext) -> Optional[str]:
    """
    Get appropriate vision/initiative reference for the region.

    Args:
        context: MENA context from detection

    Returns:
        Vision reference string or None
    """
    if not context.vision_references:
        return None

    # Prioritize Vision 2030 for Saudi Arabia
    if "Vision 2030" in context.vision_references:
        return "Vision 2030"

    return context.vision_references[0] if context.vision_references else None
