"""
Layer 6 V2: Multi-Stage CV Generation

Replaces monolithic CV generation with divide-and-conquer architecture:

1. CV Loader - Load pre-split role files from data/master-cv/roles/
2. Role Generator - Generate tailored bullets per role (sequential)
3. Stitcher - Combine roles with deduplication
4. Header Generator - Create header/skills grounded in achievements
5. Grader + Improver - Single-pass quality improvement

Key benefits:
- 100% career coverage (all 6 companies)
- Per-role hallucination QA (smaller scope = better validation)
- Role-category-aware emphasis (IC vs leadership tailoring)
- ATS optimization with 15-keyword tracking
"""

from src.layer6_v2.cv_loader import CVLoader, RoleData, CandidateData
from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    QAResult,
    ATSResult,
    CareerContext,
    # Phase 4 types
    DuplicatePair,
    DeduplicationResult,
    StitchedRole,
    StitchedCV,
    # Phase 5 types
    SkillEvidence,
    SkillsSection,
    ProfileOutput,
    ValidationResult,
    HeaderOutput,
    # Phase 6 types
    DimensionScore,
    GradeResult,
    ImprovementResult,
    FinalCV,
)
from src.layer6_v2.role_generator import RoleGenerator, generate_all_roles_sequential
from src.layer6_v2.role_qa import RoleQA, run_qa_on_all_roles
from src.layer6_v2.stitcher import CVStitcher, stitch_all_roles
from src.layer6_v2.header_generator import HeaderGenerator, generate_header
from src.layer6_v2.grader import CVGrader, grade_cv
from src.layer6_v2.improver import CVImprover, improve_cv
from src.layer6_v2.orchestrator import CVGeneratorV2, cv_generator_v2_node

__all__ = [
    # Phase 2: CV Loader
    "CVLoader",
    "RoleData",
    "CandidateData",
    # Phase 3: Per-Role Generator types
    "GeneratedBullet",
    "RoleBullets",
    "QAResult",
    "ATSResult",
    "CareerContext",
    # Phase 3: Per-Role Generator
    "RoleGenerator",
    "generate_all_roles_sequential",
    # Phase 3: Per-Role QA
    "RoleQA",
    "run_qa_on_all_roles",
    # Phase 4: Stitcher types
    "DuplicatePair",
    "DeduplicationResult",
    "StitchedRole",
    "StitchedCV",
    # Phase 4: Stitcher
    "CVStitcher",
    "stitch_all_roles",
    # Phase 5: Header Generator types
    "SkillEvidence",
    "SkillsSection",
    "ProfileOutput",
    "ValidationResult",
    "HeaderOutput",
    # Phase 5: Header Generator
    "HeaderGenerator",
    "generate_header",
    # Phase 6: Grader + Improver types
    "DimensionScore",
    "GradeResult",
    "ImprovementResult",
    "FinalCV",
    # Phase 6: Grader + Improver
    "CVGrader",
    "grade_cv",
    "CVImprover",
    "improve_cv",
    # Orchestrator (ties all phases together)
    "CVGeneratorV2",
    "cv_generator_v2_node",
]
