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
professional identity statements. You excel at distilling multiple professional
qualities into a single, memorable positioning statement."""

    SYNTHESIS_PROMPT = """Given these professional identity markers for a job candidate:

{identity_context}

Write a single sentence (15-25 words) that positions this professional.

Rules:
- Start with "A" or "An"
- Focus on WHO they are professionally, not a list of skills
- Make it sound natural and compelling, not like a bulleted list
- Capture their unique professional essence
- If developing skills are mentioned, frame them as growth areas

Return ONLY the persona sentence, nothing else. No quotes around it."""

    def __init__(self, layer: str = "persona_builder"):
        """
        Initialize the PersonaBuilder.

        Args:
            layer: Layer name for token tracking attribution
        """
        self.layer = layer

    def _extract_identity_annotations(
        self, jd_annotations: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract and group identity annotations by strength level.

        Args:
            jd_annotations: Full jd_annotations dict from job document

        Returns:
            Dict with keys: core_identity, strong_identity, developing
            Each value is a list of matching annotations
        """
        annotations = jd_annotations.get("annotations", [])
        grouped: Dict[str, List[Dict[str, Any]]] = {
            "core_identity": [],
            "strong_identity": [],
            "developing": [],
        }

        for ann in annotations:
            # Skip inactive annotations
            if not ann.get("is_active", False):
                continue

            identity = ann.get("identity")
            if identity in grouped:
                grouped[identity].append(ann)

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

    def _build_identity_context(
        self, grouped: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Build the identity context string for the LLM prompt.

        Args:
            grouped: Grouped identity annotations

        Returns:
            Formatted context string for prompt
        """
        lines = []

        # Primary (core identity)
        core = grouped.get("core_identity", [])
        if core:
            core_texts = [self._get_identity_text(a) for a in core[:3]]
            lines.append(f"- Primary (core identity): {', '.join(core_texts)}")

        # Secondary (strong identity)
        strong = grouped.get("strong_identity", [])
        if strong:
            strong_texts = [self._get_identity_text(a) for a in strong[:3]]
            lines.append(f"- Secondary (strong identity): {', '.join(strong_texts)}")

        # Developing
        developing = grouped.get("developing", [])
        if developing:
            dev_texts = [self._get_identity_text(a) for a in developing[:2]]
            lines.append(f"- Developing: {', '.join(dev_texts)}")

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
            for ann in grouped.get(level, [])[:3]:  # Max 3 per level
                ann_id = ann.get("id") or ann.get("_id")
                if ann_id:
                    ids.append(str(ann_id))
        return ids

    def has_identity_annotations(self, jd_annotations: Dict[str, Any]) -> bool:
        """
        Check if there are any active identity annotations.

        Args:
            jd_annotations: Full jd_annotations dict

        Returns:
            True if at least one identity annotation exists
        """
        grouped = self._extract_identity_annotations(jd_annotations)
        return any(len(anns) > 0 for anns in grouped.values())

    async def synthesize(
        self, jd_annotations: Dict[str, Any]
    ) -> Optional[SynthesizedPersona]:
        """
        Synthesize persona from identity annotations using LLM.

        Args:
            jd_annotations: Full jd_annotations dict from job document

        Returns:
            SynthesizedPersona if identity annotations exist, else None
        """
        # Extract and group identity annotations
        grouped = self._extract_identity_annotations(jd_annotations)

        # Check if we have any identities to work with
        total_annotations = sum(len(anns) for anns in grouped.values())
        if total_annotations == 0:
            logger.debug("No identity annotations found, skipping persona synthesis")
            return None

        # Build context for prompt
        identity_context = self._build_identity_context(grouped)

        logger.info(
            f"Synthesizing persona from {total_annotations} identity annotations"
        )

        try:
            # Create LLM (cheap model for simple task)
            llm = create_tracked_cheap_llm(layer=self.layer)

            # Build prompt
            user_prompt = self.SYNTHESIS_PROMPT.format(identity_context=identity_context)

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

            # Determine primary identity
            core = grouped.get("core_identity", [])
            primary_identity = ""
            if core:
                primary_identity = self._get_identity_text(core[0])
            elif grouped.get("strong_identity"):
                primary_identity = self._get_identity_text(
                    grouped["strong_identity"][0]
                )
            elif grouped.get("developing"):
                primary_identity = self._get_identity_text(grouped["developing"][0])

            # Gather secondary identities
            secondary = []
            for level in ["strong_identity", "developing"]:
                for ann in grouped.get(level, []):
                    text = self._get_identity_text(ann)
                    if text and text != primary_identity:
                        secondary.append(text)

            logger.info(f"Synthesized persona: {persona_statement[:50]}...")

            return SynthesizedPersona(
                persona_statement=persona_statement,
                primary_identity=primary_identity,
                secondary_identities=secondary[:5],  # Cap at 5
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
