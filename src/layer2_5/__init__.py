"""
Layer 2.5: STAR Selector

Maps job pain points to candidate's best-fit STAR achievements.
Enables hyper-personalization by selecting 2-3 most relevant experiences.
"""

from .star_selector import select_stars

__all__ = ["select_stars"]
