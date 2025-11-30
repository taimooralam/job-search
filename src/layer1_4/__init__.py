"""
Layer 1.4: JD Extractor

Extracts structured intelligence from job descriptions to enable precise CV tailoring.
This layer runs BEFORE Layer 2 (Pain Point Miner) and provides:

1. Role Classification: Engineering Manager, Staff/Principal Engineer, Director, Head of Eng, CTO
2. Competency Weights: delivery, process, architecture, leadership (sum=100)
3. ATS Keywords: Top 15 keywords for CV optimization
4. Structured Content: responsibilities, qualifications, nice-to-haves, skills
5. Inferred Intelligence: implied pain points, success metrics, industry background

The extracted data augments Layer 2's analysis and drives role-category-aware CV generation.
"""

from src.layer1_4.jd_extractor import jd_extractor_node, JDExtractor

__all__ = ["jd_extractor_node", "JDExtractor"]
