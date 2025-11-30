"""
Prompts for Layer 6 V2 CV Generation Pipeline.

Each prompt module provides system and user prompts for a specific stage:
- role_generation: Per-role bullet generation
- stitching: Cross-role deduplication and combination
- header_generation: Profile and skills section
- grading_rubric: Multi-dimensional CV grading
- improvement: Targeted improvement based on grades
"""

from src.layer6_v2.prompts.role_generation import (
    ROLE_GENERATION_SYSTEM_PROMPT,
    build_role_generation_user_prompt,
)

__all__ = [
    "ROLE_GENERATION_SYSTEM_PROMPT",
    "build_role_generation_user_prompt",
]
