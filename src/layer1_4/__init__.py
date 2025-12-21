"""
Layer 1.4: JD Extractor & Processor

Extracts structured intelligence from job descriptions to enable precise CV tailoring.
This layer runs BEFORE Layer 2 (Pain Point Miner) and provides:

1. Role Classification: Engineering Manager, Staff/Principal Engineer, Director, Head of Eng, CTO
2. Competency Weights: delivery, process, architecture, leadership (sum=100)
3. ATS Keywords: Top 15 keywords for CV optimization
4. Structured Content: responsibilities, qualifications, nice-to-haves, skills
5. Inferred Intelligence: implied pain points, success metrics, industry background
6. JD Processing: Structures raw JD into annotatable HTML sections (for annotation system)

The extracted data augments Layer 2's analysis and drives role-category-aware CV generation.
"""

# Primary JD Extractor (Claude Code CLI based)
from src.layer1_4.claude_jd_extractor import (
    JDExtractor,
    ExtractionResult,
    ExtractedJDModel,
    CompetencyWeightsModel,
    RoleCategory,
    SeniorityLevel,
    RemotePolicy,
    extract_jd,
    # LangGraph node function
    jd_extractor_node,
    # Backwards compatibility aliases
    ClaudeJDExtractor,
    extract_jd_with_claude,
)

# JD Processor (for annotation system)
from src.layer1_4.jd_processor import (
    process_jd,
    process_jd_sync,
    ProcessedJD,
    JDSection,
    JDSectionType,
    processed_jd_to_dict,
    dict_to_processed_jd,
)

__all__ = [
    # JD Extractor (primary)
    "JDExtractor",
    "ExtractionResult",
    "ExtractedJDModel",
    "CompetencyWeightsModel",
    "RoleCategory",
    "SeniorityLevel",
    "RemotePolicy",
    "extract_jd",
    # LangGraph node function
    "jd_extractor_node",
    # Backwards compatibility
    "ClaudeJDExtractor",
    "extract_jd_with_claude",
    # JD Processor (for annotation system)
    "process_jd",
    "process_jd_sync",
    "ProcessedJD",
    "JDSection",
    "JDSectionType",
    "processed_jd_to_dict",
    "dict_to_processed_jd",
]
