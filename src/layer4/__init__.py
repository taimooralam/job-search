# Layer 4: Opportunity Mapper
#
# Analyzes candidate-job fit using LLM analysis + annotation signals.
# Exports:
# - OpportunityMapper: Main fit scoring class
# - opportunity_mapper_node: LangGraph node function
# - AnnotationFitSignal: Annotation signal calculator
# - blend_fit_scores: Score blending function

from src.layer4.opportunity_mapper import OpportunityMapper, opportunity_mapper_node
from src.layer4.annotation_fit_signal import (
    AnnotationFitSignal,
    blend_fit_scores,
    get_annotation_analysis,
)

__all__ = [
    "OpportunityMapper",
    "opportunity_mapper_node",
    "AnnotationFitSignal",
    "blend_fit_scores",
    "get_annotation_analysis",
]
