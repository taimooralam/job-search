"""
Persona Builder Module.

Synthesizes identity annotations into a coherent persona statement using LLM.
The persona frames how the candidate is positioned in CV, cover letter, and outreach.

Usage:
    from src.common.persona_builder import PersonaBuilder

    # Synthesize persona from annotations
    builder = PersonaBuilder()
    persona = await builder.synthesize(jd_annotations)
    if persona:
        print(persona.persona_statement)  # "A solutions architect who leads..."

    # Get stored persona for prompt injection
    guidance = builder.get_persona_for_prompt(jd_annotations)
    # Returns "CANDIDATE PERSONA: ..." or empty string
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from src.common.llm_factory import create_tracked_cheap_llm

logger = logging.getLogger(__name__)

# Identity levels in order of strength (strongest first)
IDENTITY_STRENGTH_ORDER = ["core_identity", "strong_identity", "developing"]

# Passion levels that indicate genuine interest (for persona)
PASSION_LEVELS = ["love_it", "enjoy"]

# Relevance levels that indicate core strengths
STRENGTH_LEVELS = ["core_strength", "extremely_relevant"]


@dataclass
class SynthesizedPersona:
    """Result of persona synthesis from identity annotations."""

    persona_statement: str
    primary_identity: str
    secondary_identities: List[str] = field(default_factory=list)
    source_annotations: List[str] = field(default_factory=list)
    is_user_edited: bool = False
    synthesized_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB storage."""
        return {
            "persona_statement": self.persona_statement,
            "primary_identity": self.primary_identity,
            "secondary_identities": self.secondary_identities,
            "source_annotations": self.source_annotations,
            "is_user_edited": self.is_user_edited,
            "synthesized_at": self.synthesized_at or datetime.utcnow(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SynthesizedPersona":
        """Create from dictionary (MongoDB document)."""
        return cls(
            persona_statement=data.get("persona_statement", ""),
            primary_identity=data.get("primary_identity", ""),
            secondary_identities=data.get("secondary_identities", []),
            source_annotations=data.get("source_annotations", []),
            is_user_edited=data.get("is_user_edited", False),
            synthesized_at=data.get("synthesized_at"),
        )


class PersonaBuilder:
    """
    Synthesizes coherent persona from identity annotations using LLM.

    Identity annotations marked as core_identity, strong_identity, or developing
    are combined into a natural-sounding persona statement that captures
    the candidate's professional essence.
    """

    SYSTEM_PROMPT = """You are a professional branding expert who crafts compelling
professional identity statements. You excel at distilling identity, passions, and
strengths into a single, memorable positioning statement that captures someone's
professional essence."""

    SYNTHESIS_PROMPT = """Given these professional attributes for a job candidate:

{persona_context}

Write a persona statement (35-60 words, 1-2 sentences) that positions this professional.

=== CRITICAL: THIRD-PERSON ABSENT VOICE ===

You MUST use third-person absent voice. This means:
- NO pronouns: I, my, me, you, your, we, our, us
- Use "who" clauses to connect identity to action
- Start with role/identity noun phrase ("A", "An")

CORRECT examples (third-person absent voice):
- "An engineering leader WHO thrives on building high-performing teams and scalable systems."
- "A platform architect WHO transforms infrastructure challenges into competitive advantages."
- "An enthusiastic technologist with deep expertise in cloud-native systems and a passion for developing talent."

INCORRECT examples (NEVER write like this - has pronouns):
- "I am an engineering leader who thrives on..." (uses "I")
- "My passion is building teams..." (uses "My")
- "An engineering leader, I thrive on..." (uses "I")

=== OTHER RULES ===

- Start with "A" or "An"
- Weave together their identity, passions, and strengths naturally
- Focus on WHO they are and WHAT drives them, not just skills
- Make it sound authentic and compelling, not like a list
- If they love something, let that passion shine through ("passionate about", "thrives on")
- If developing skills are mentioned, frame them as growth direction
- For candidates with many identities/strengths, use two sentences to capture their multi-faceted nature

Return ONLY the persona statement, nothing else. No quotes around it."""

    def __init__(self, layer: str = "persona_builder"):
        """
        Initialize the PersonaBuilder.

        Args:
            layer: Layer name for token tracking attribution
        """
        self.layer = layer

    def _extract_persona_annotations(
        self, jd_annotations: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract and group annotations relevant to persona synthesis.

        Extracts three dimensions:
        1. Identity annotations (core_identity, strong_identity, developing)
        2. Passion annotations (love_it, enjoy)
        3. Strength annotations (core_strength, extremely_relevant)

        Args:
            jd_annotations: Full jd_annotations dict from job document

        Returns:
            Dict with keys for each dimension
        """
        annotations = jd_annotations.get("annotations", [])
        grouped: Dict[str, List[Dict[str, Any]]] = {
            # Identity dimension
            "core_identity": [],
            "strong_identity": [],
            "developing": [],
            # Passion dimension
            "love_it": [],
            "enjoy": [],
            # Strength dimension
            "core_strength": [],
            "extremely_relevant": [],
        }

        for ann in annotations:
            # Skip inactive annotations (default to True for backward compatibility
            # with annotations that don't have is_active field yet)
            if not ann.get("is_active", True):
                continue

            # Check identity
            identity = ann.get("identity")
            if identity in grouped:
                grouped[identity].append(ann)

            # Check passion
            passion = ann.get("passion")
            if passion in grouped:
                grouped[passion].append(ann)

            # Check relevance/strength
            relevance = ann.get("relevance")
            if relevance in grouped:
                grouped[relevance].append(ann)

        return grouped

    def _get_identity_text(self, annotation: Dict[str, Any]) -> str:
        """
        Extract the best text representation of an identity annotation.

        Priority: matching_skill > target.text (truncated)

        Args:
            annotation: Single annotation dict

        Returns:
            Text representation of the identity
        """
        matching_skill = annotation.get("matching_skill")
        if matching_skill:
            return matching_skill

        target = annotation.get("target", {})
        text = target.get("text", "")
        # Truncate long text to key phrase
        if len(text) > 50:
            text = text[:47] + "..."
        return text

    def _build_persona_context(
        self, grouped: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Build the full persona context string for the LLM prompt.

        Includes identity, passion, and strength dimensions.

        Args:
            grouped: Grouped persona annotations

        Returns:
            Formatted context string for prompt
        """
        lines = []

        # === IDENTITY DIMENSION ===
        identity_lines = []

        # Core identity (WHO they are)
        core = grouped.get("core_identity", [])
        if core:
            if len(core) > 6:
                logger.debug(f"Truncating {len(core)} core_identity annotations to 6")
            core_texts = [self._get_identity_text(a) for a in core[:6]]
            identity_lines.append(f"  • Core identity: {', '.join(core_texts)}")

        # Strong identity
        strong = grouped.get("strong_identity", [])
        if strong:
            if len(strong) > 5:
                logger.debug(f"Truncating {len(strong)} strong_identity annotations to 5")
            strong_texts = [self._get_identity_text(a) for a in strong[:5]]
            identity_lines.append(f"  • Strong identity: {', '.join(strong_texts)}")

        # Developing identity
        developing = grouped.get("developing", [])
        if developing:
            if len(developing) > 4:
                logger.debug(f"Truncating {len(developing)} developing annotations to 4")
            dev_texts = [self._get_identity_text(a) for a in developing[:4]]
            identity_lines.append(f"  • Developing: {', '.join(dev_texts)}")

        if identity_lines:
            lines.append("PROFESSIONAL IDENTITY (who they are):")
            lines.extend(identity_lines)

        # === PASSION DIMENSION ===
        passion_lines = []

        # Things they love
        love = grouped.get("love_it", [])
        if love:
            if len(love) > 5:
                logger.debug(f"Truncating {len(love)} love_it annotations to 5")
            love_texts = [self._get_identity_text(a) for a in love[:5]]
            passion_lines.append(f"  • Loves: {', '.join(love_texts)}")

        # Things they enjoy
        enjoy = grouped.get("enjoy", [])
        if enjoy:
            if len(enjoy) > 5:
                logger.debug(f"Truncating {len(enjoy)} enjoy annotations to 5")
            enjoy_texts = [self._get_identity_text(a) for a in enjoy[:5]]
            passion_lines.append(f"  • Enjoys: {', '.join(enjoy_texts)}")

        if passion_lines:
            lines.append("\nPASSIONS (what energizes them):")
            lines.extend(passion_lines)

        # === STRENGTH DIMENSION ===
        strength_lines = []

        # Core strengths
        core_str = grouped.get("core_strength", [])
        if core_str:
            if len(core_str) > 5:
                logger.debug(f"Truncating {len(core_str)} core_strength annotations to 5")
            str_texts = [self._get_identity_text(a) for a in core_str[:5]]
            strength_lines.append(f"  • Core strengths: {', '.join(str_texts)}")

        # Strong skills
        ext_rel = grouped.get("extremely_relevant", [])
        if ext_rel:
            if len(ext_rel) > 5:
                logger.debug(f"Truncating {len(ext_rel)} extremely_relevant annotations to 5")
            ext_texts = [self._get_identity_text(a) for a in ext_rel[:5]]
            strength_lines.append(f"  • Strong skills: {', '.join(ext_texts)}")

        if strength_lines:
            lines.append("\nCORE STRENGTHS (what they excel at):")
            lines.extend(strength_lines)

        return "\n".join(lines)

    def _get_source_annotation_ids(
        self, grouped: Dict[str, List[Dict[str, Any]]]
    ) -> List[str]:
        """
        Get list of annotation IDs used in synthesis.

        Args:
            grouped: Grouped identity annotations

        Returns:
            List of annotation IDs
        """
        ids = []
        for level in IDENTITY_STRENGTH_ORDER:
            for ann in grouped.get(level, [])[:6]:  # Max 6 per level
                ann_id = ann.get("id") or ann.get("_id")
                if ann_id:
                    ids.append(str(ann_id))
        return ids

    def has_persona_annotations(self, jd_annotations: Dict[str, Any]) -> bool:
        """
        Check if there are any annotations relevant for persona synthesis.

        Checks for identity, passion, or strength annotations.

        Args:
            jd_annotations: Full jd_annotations dict

        Returns:
            True if at least one relevant annotation exists
        """
        grouped = self._extract_persona_annotations(jd_annotations)
        return any(len(anns) > 0 for anns in grouped.values())

    # Alias for backward compatibility
    def has_identity_annotations(self, jd_annotations: Dict[str, Any]) -> bool:
        """Alias for has_persona_annotations for backward compatibility."""
        return self.has_persona_annotations(jd_annotations)

    async def synthesize(
        self, jd_annotations: Dict[str, Any]
    ) -> Optional[SynthesizedPersona]:
        """
        Synthesize persona from identity, passion, and strength annotations using LLM.

        Args:
            jd_annotations: Full jd_annotations dict from job document

        Returns:
            SynthesizedPersona if relevant annotations exist, else None
        """
        # Extract and group all persona-relevant annotations
        grouped = self._extract_persona_annotations(jd_annotations)

        # Check if we have any annotations to work with
        total_annotations = sum(len(anns) for anns in grouped.values())
        if total_annotations == 0:
            logger.debug("No persona-relevant annotations found, skipping synthesis")
            return None

        # Build context for prompt
        persona_context = self._build_persona_context(grouped)

        logger.info(
            f"Synthesizing persona from {total_annotations} annotations "
            f"(identity: {len(grouped.get('core_identity', [])) + len(grouped.get('strong_identity', []))}, "
            f"passion: {len(grouped.get('love_it', [])) + len(grouped.get('enjoy', []))}, "
            f"strength: {len(grouped.get('core_strength', [])) + len(grouped.get('extremely_relevant', []))})"
        )

        try:
            # Create LLM (cheap model for simple task)
            llm = create_tracked_cheap_llm(layer=self.layer)

            # Build prompt
            user_prompt = self.SYNTHESIS_PROMPT.format(persona_context=persona_context)

            # Call LLM
            messages = [
                SystemMessage(content=self.SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            response = await llm.ainvoke(messages)

            # Extract persona statement
            persona_statement = response.content.strip()

            # Clean up any quotes
            if persona_statement.startswith('"') and persona_statement.endswith('"'):
                persona_statement = persona_statement[1:-1]
            if persona_statement.startswith("'") and persona_statement.endswith("'"):
                persona_statement = persona_statement[1:-1]

            # Determine primary identity (from identity or passion or strength)
            primary_identity = ""
            for key in ["core_identity", "love_it", "core_strength",
                        "strong_identity", "enjoy", "extremely_relevant"]:
                if grouped.get(key):
                    primary_identity = self._get_identity_text(grouped[key][0])
                    break

            # Gather secondary identities from all dimensions
            secondary = []
            for key in ["strong_identity", "developing", "enjoy", "extremely_relevant"]:
                for ann in grouped.get(key, []):
                    text = self._get_identity_text(ann)
                    if text and text != primary_identity:
                        secondary.append(text)

            logger.info(f"Synthesized persona: {persona_statement[:50]}...")

            if len(secondary) > 10:
                logger.debug(f"Truncating {len(secondary)} secondary_identities to 10")

            return SynthesizedPersona(
                persona_statement=persona_statement,
                primary_identity=primary_identity,
                secondary_identities=secondary[:10],  # Cap at 10
                source_annotations=self._get_source_annotation_ids(grouped),
                is_user_edited=False,
                synthesized_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Failed to synthesize persona: {e}")
            return None

    def get_persona_for_prompt(self, jd_annotations: Dict[str, Any]) -> str:
        """
        Get the stored persona statement formatted for prompt injection.

        This is a synchronous method that reads the stored synthesized_persona.
        Use this in generation layers to inject persona context.

        Args:
            jd_annotations: Full jd_annotations dict from job document

        Returns:
            Formatted persona guidance string, or empty string if no persona
        """
        stored = jd_annotations.get("synthesized_persona", {})
        persona_statement = stored.get("persona_statement")

        if not persona_statement:
            return ""

        return f"CANDIDATE PERSONA: {persona_statement}"

    def get_full_persona_guidance(self, jd_annotations: Dict[str, Any]) -> str:
        """
        Get full persona guidance with framing instructions.

        Use this for detailed prompt injection that includes positioning guidance.

        Args:
            jd_annotations: Full jd_annotations dict from job document

        Returns:
            Full persona guidance with instructions, or empty string
        """
        stored = jd_annotations.get("synthesized_persona", {})
        persona_statement = stored.get("persona_statement")

        if not persona_statement:
            return ""

        return f"""CANDIDATE PERSONA: {persona_statement}

This persona should be the central theme of the content.
Frame the narrative around this professional identity.
The opening should naturally incorporate this positioning.
Avoid sounding like a list of qualifications - embody this persona."""


# Convenience function for simple access
def get_persona_guidance(jd_annotations: Optional[Dict[str, Any]]) -> str:
    """
    Convenience function to get persona guidance for prompt injection.

    Args:
        jd_annotations: JD annotations dict (or None)

    Returns:
        Persona guidance string or empty string
    """
    if not jd_annotations:
        return ""
    return PersonaBuilder().get_persona_for_prompt(jd_annotations)
