"""
Layer 5: People Mapper

Identifies key contacts at target company and generates personalized outreach.
Uses FireCrawl to find team pages, LLM to extract contacts and craft messages.
"""

from .people_mapper import people_mapper_node

__all__ = ["people_mapper_node"]
