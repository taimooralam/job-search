"""
Services module for button-triggered pipeline operations.

Each service extends OperationService to provide consistent
execution, cost tracking, and persistence for independent operations.
"""

from src.services.operation_base import OperationResult, OperationService, OperationTimer
from src.services.structure_jd_service import StructureJDService, structure_jd
from src.services.outreach_service import (
    OutreachGenerationService,
    generate_outreach,
)

__all__ = [
    # Base classes
    "OperationResult",
    "OperationService",
    "OperationTimer",
    # Services
    "StructureJDService",
    "structure_jd",
    "OutreachGenerationService",
    "generate_outreach",
]
