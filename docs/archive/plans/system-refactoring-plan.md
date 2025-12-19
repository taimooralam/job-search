# System Refactoring Plan: Technical Debt Reduction & Functionality Catalogue

**Created**: 2025-12-11
**Status**: Ready for Implementation

---

## Executive Summary

Comprehensive refactoring of the Job Intelligence Pipeline to:
1. **Reduce technical debt** by consolidating Layer 6 dual implementation
2. **Increase modularization** with clear service boundaries and grouped common modules
3. **Create Functionality Catalogue** (YAML) for AI agent context management
4. **Improve naming** with consistent conventions
5. **Consolidate documentation** to reduce 150+ docs to essential set

### User Decisions
- **Catalogue Format**: YAML with JSON Schema validation
- **Archive Strategy**: Keep in git history (`/archive/` tracked)
- **Doc Timing**: Documentation BEFORE code refactoring

---

## Phase 1: Functionality Catalogue 🚀 START HERE

### 1.1 Create Catalogue Structure

**Files to Create:**
```
/catalogue/
├── functionality.yaml      # Main catalogue
├── query.py               # Python query interface
├── schema.json            # JSON Schema for validation
└── README.md              # Usage guide
```

**Catalogue Schema (`functionality.yaml`):**
```yaml
version: "1.0.0"
last_updated: "2025-12-11"
updated_by: "doc-sync"

# Execution surfaces (where code runs)
surfaces:
  - name: "Runner"
    path: "runner_service/"
    description: "VPS-hosted FastAPI with JWT auth"
    operations: [process-job, research-company, generate-cv, full-extraction]

# Pipeline layers (7-layer LangGraph)
layers:
  - id: "layer-6"
    name: "Artifact Generation"
    path: "src/layer6_v2/"          # CANONICAL: layer6_v2 is the active implementation
    canonical: true
    node_function: "cv_generator_v2_node"
    subdirs: [cover_letter/, outreach/]

# Shared utilities grouped by domain
common:
  llm: [llm_factory.py, tiering.py, token_tracker.py]
  annotations: [annotation_types.py, annotation_boost.py, annotation_validator.py]
  database: [database.py, updater.py]
  state: [state.py, types.py]
  logging: [logger.py, structured_logger.py, tracing.py]

# Deprecated code (agents should not use)
deprecated:
  - path: "src/layer6/"
    reason: "Legacy layer - functionality moved to layer6_v2"
    replacement: "src/layer6_v2/"
    status: "deprecated"

# Services with clear responsibilities
services:
  extraction: [full_extraction_service.py, structure_jd_service.py]
  research: [company_research_service.py]
  generation: [cv_generation_service.py, outreach_service.py]
  analytics: [annotation_tracking_service.py]
```

### 1.2 Query Interface (`catalogue/query.py`)

```python
"""
Functionality Catalogue Query Interface.

Usage by agents:
    from catalogue.query import find_module, get_layer, list_deprecated

    # Find modules by keyword
    modules = find_module("annotation")  # Returns all annotation-related

    # Get canonical layer info
    layer6 = get_layer("layer-6")  # Returns consolidated structure

    # Check if path is deprecated
    is_old = is_deprecated("src/layer6/generator.py")  # True - use layer6_v2
"""
```

### 1.3 Update Agent Instructions

**Add to CLAUDE.md:**
```markdown
## Functionality Catalogue

All agents MUST consult `/catalogue/functionality.yaml` before:
- Searching for functionality (use catalogue instead of grep)
- Importing modules (check if deprecated)
- Adding new code (follow established patterns)

### doc-sync Agent Responsibilities
- Update catalogue when files are added/removed/moved
- Maintain "deprecated" section with removal dates
- Verify "exports" are accurate after changes
```

**Critical Files:**
- `/catalogue/functionality.yaml` (create)
- `/catalogue/query.py` (create)
- `/CLAUDE.md` (update agent instructions)

---

## Phase 2: Documentation Consolidation

### 2.1 Archive Old Documents

**Move to `/archive/` (git-tracked):**
- All dated reports: `reports/*_2025-11-*.md` → `archive/reports/`
- Completed plans: `plans/*-implementation.md` → `archive/plans/`
- Session-specific docs: `reports/sessions/` → `archive/sessions/`

### 2.2 Create Consolidated Documentation

**New Structure:**
```
/docs/
├── architecture.md          # Single truth source (consolidate from plans/)
├── api/
│   ├── runner-api.md       # Runner endpoints
│   └── frontend-routes.md  # Frontend routes
├── guides/
│   ├── adding-layer.md     # How to add pipeline layer
│   ├── writing-tests.md    # Testing patterns
│   └── deployment.md       # Deployment guide
└── changelog.md            # Consolidated from reports
```

### 2.3 Essential Documents to Preserve

| Document | Location | Action |
|----------|----------|--------|
| `architecture.md` | plans/ → docs/ | Consolidate + update |
| `missing.md` | plans/ | Keep, add refactoring tasks |
| `CLAUDE.md` | root | Update with catalogue |
| `bugs.md` | plans/ | Keep current |
| `ROADMAP.md` | plans/ | Merge key items into missing.md |

**Critical Files:**
- `/docs/architecture.md` (consolidate)
- `/plans/missing.md` (update with refactoring gaps)
- `/archive/` (create structure)

---

## Phase 3: Layer 6 Consolidation

### 3.1 Current State (13 files across 2 directories)

**Layer 6 Legacy (to DEPRECATE & DELETE):**
- `generator.py` (~650 lines) → DEPRECATE
- `cv_generator.py` (~300 lines) → DEPRECATE
- `html_cv_generator.py` (~150 lines) → DELETE immediately
- `cover_letter_generator.py` → MOVE to layer6_v2/cover_letter/
- `outreach_generator.py` → MOVE to layer6_v2/outreach/
- `recruiter_cover_letter.py` → MOVE to layer6_v2/cover_letter/
- `linkedin_optimizer.py` → MOVE to layer6_v2/outreach/

**Layer 6 V2 (CANONICAL - KEEP AS-IS):**
- All 15 files → KEEP in current location
- Add subdirectories for cover_letter and outreach

### 3.2 Target Structure (Keep layer6_v2 as canonical)

```
src/layer6_v2/                     # CANONICAL - Keep this structure
├── __init__.py                    # Main exports
├── orchestrator.py                # CV generation orchestrator
├── cv_loader.py
├── role_generator.py
├── variant_parser.py
├── variant_selector.py
├── role_qa.py
├── stitcher.py
├── header_generator.py
├── ensemble_header_generator.py
├── grader.py
├── improver.py
├── ats_checker.py
├── keyword_placement.py
├── annotation_header_context.py
├── types.py
├── cover_letter/                  # NEW: Move from layer6
│   ├── __init__.py
│   ├── generator.py               # cover_letter_generator.py
│   └── recruiter.py               # recruiter_cover_letter.py
└── outreach/                      # NEW: Move from layer6
    ├── __init__.py
    ├── generator.py               # outreach_generator.py
    └── linkedin.py                # linkedin_optimizer.py

src/layer6/                        # DEPRECATED - Will be removed
├── __init__.py                    # Re-exports from layer6_v2 (backward compat)
└── (all other files marked for deletion)
```

### 3.3 Migration Steps

**Step 1: Organize layer6_v2 (non-breaking)**
```bash
# Create subdirectories in layer6_v2
mkdir -p src/layer6_v2/{cover_letter,outreach}

# Move files from layer6 to layer6_v2 subdirectories
mv src/layer6/cover_letter_generator.py src/layer6_v2/cover_letter/generator.py
mv src/layer6/outreach_generator.py src/layer6_v2/outreach/generator.py
mv src/layer6/linkedin_optimizer.py src/layer6_v2/outreach/linkedin.py
mv src/layer6/recruiter_cover_letter.py src/layer6_v2/cover_letter/recruiter.py
```

**Step 2: Update layer6 `__init__.py` for backward compatibility**
```python
# src/layer6/__init__.py
import warnings
warnings.warn(
    "src.layer6 is deprecated. Use src.layer6_v2 instead.",
    DeprecationWarning
)

# Re-export from canonical location for backward compatibility
from src.layer6_v2.orchestrator import CVGeneratorV2, cv_generator_v2_node
from src.layer6_v2.cover_letter.generator import *
from src.layer6_v2.outreach.generator import outreach_generator_node
```

**Step 3: Update imports (search & replace)**
```
# Update any remaining imports from layer6 to layer6_v2
FROM: from src.layer6.cover_letter_generator import
TO:   from src.layer6_v2.cover_letter.generator import

FROM: from src.layer6.outreach_generator import
TO:   from src.layer6_v2.outreach.generator import
```

**Step 4: Immediate cleanup**
- Delete `src/layer6/html_cv_generator.py` (dead code, no imports)

**Step 5: Delete after 4 weeks**
- Remove `src/layer6/` directory entirely (all imports should use layer6_v2)
- Remove `src/layer6/generator.py` (legacy)
- Remove `src/layer6/cv_generator.py` (legacy)

**Critical Files:**
- `src/layer6_v2/__init__.py` (update exports)
- `src/layer6_v2/cover_letter/__init__.py` (create)
- `src/layer6_v2/outreach/__init__.py` (create)
- `src/layer6/__init__.py` (rewrite with deprecation + re-exports)
- `src/workflow.py` (verify imports use layer6_v2)

---

## Phase 4: Service Layer Rationalization

### 4.1 Create Centralized MongoDB Updater

**New File: `src/common/database/updater.py`**
```python
class JobDocumentUpdater:
    """
    Centralized job document updates.
    All services use this instead of direct collection.update_one().

    Benefits:
    - Consistent timestamp updates
    - Validation before write
    - Audit logging
    """

    def update_extracted_jd(self, job_id: str, extracted_jd: dict) -> bool:
        """Update extracted_jd with validation."""

    def update_cv_output(self, job_id: str, cv_text: str, cv_path: str) -> bool:
        """Update CV with generation metadata."""

    def update_company_research(self, job_id: str, research: dict) -> bool:
        """Update company research with cache timestamp."""
```

### 4.2 Service Boundaries

| Service | Responsibility | MongoDB Collections |
|---------|---------------|---------------------|
| `FullExtractionService` | L1.4 + L2 + L4 extraction | level-2 |
| `StructureJDService` | JD text → HTML sections | level-2 |
| `CompanyResearchService` | External research + caching | level-2, company_cache |
| `CVGenerationService` | State → tailored CV | level-2 |
| `OutreachService` | Contact → messages | level-2 |
| `AnnotationTrackingService` | A/B testing | annotation_outcomes |
| `StrengthSuggestionService` | Strength analysis | None (stateless) |

**Critical Files:**
- `src/common/database/updater.py` (create)
- All service files (refactor to use updater)

---

## Phase 5: Common Module Reorganization

### 5.1 Target Structure

```
src/common/
├── __init__.py              # Re-exports for backward compatibility
├── state/
│   ├── __init__.py
│   ├── job_state.py         # JobState TypedDict
│   └── types.py             # Shared types
├── config/
│   ├── __init__.py
│   ├── settings.py          # From config.py
│   └── ingest.py            # From ingest_config.py
├── database/
│   ├── __init__.py
│   ├── client.py            # From database.py
│   └── updater.py           # NEW: Centralized updates
├── llm/
│   ├── __init__.py
│   ├── factory.py           # From llm_factory.py
│   ├── tiering.py           # Merged tiering.py + model_tiers.py
│   └── token_tracker.py
├── logging/
│   ├── __init__.py
│   ├── logger.py
│   ├── structured.py        # From structured_logger.py
│   └── tracing.py
├── annotations/
│   ├── __init__.py
│   ├── types.py             # From annotation_types.py
│   ├── boost.py             # From annotation_boost.py
│   ├── validator.py         # From annotation_validator.py
│   └── persona.py           # From persona_builder.py
├── cv/
│   ├── __init__.py
│   ├── master_store.py      # From master_cv_store.py
│   └── star_parser.py
├── resilience/
│   ├── __init__.py
│   ├── rate_limiter.py
│   └── circuit_breaker.py
├── monitoring/
│   ├── __init__.py
│   ├── alerting.py
│   └── metrics.py
└── utils/
    ├── __init__.py
    ├── markdown.py          # From markdown_sanitizer.py
    ├── paths.py
    └── errors.py            # From error_handling.py
```

### 5.2 Backward Compatibility

```python
# src/common/__init__.py (maintain for 4 weeks)
# DEPRECATED: Import from submodules directly
from src.common.state.job_state import JobState
from src.common.config.settings import Config
from src.common.database.client import DatabaseClient
from src.common.llm.factory import create_tracked_llm
# ... etc
```

**Critical Files:**
- All files in `src/common/` (reorganize)
- `src/common/__init__.py` (re-exports)

---

## Phase 6: Final Cleanup

### 6.1 Remove Deprecated Code

After backward compatibility period:
- [ ] Delete `src/layer6/` directory entirely (layer6_v2 is canonical)
- [ ] Verify all imports use layer6_v2
- [ ] Remove backward compatibility re-exports from `__init__.py` files
- [ ] Merge `tiering.py` and `model_tiers.py` into single file

### 6.2 Naming Convention Enforcement

| Category | Pattern | Example |
|----------|---------|---------|
| Node functions | `{layer}_node` | `pain_point_miner_node` |
| Services | `{Domain}Service` | `CVGenerationService` |
| Generators | `{Artifact}Generator` | `HeaderGenerator` |
| Validators | `{Domain}Validator` | `KeywordPlacementValidator` |

### 6.3 Final Validation

- [ ] Run full test suite: `pytest -n auto`
- [ ] Verify no deprecated imports in codebase
- [ ] Update catalogue with final structure
- [ ] Tag release: `v2.0.0-refactored`

---

## Implementation Checklist

### Phase 1 & 2: Catalogue & Docs
- [ ] Create `/catalogue/functionality.yaml`
- [ ] Create `/catalogue/query.py`
- [ ] Update CLAUDE.md with catalogue instructions
- [ ] Create `/archive/` and move old reports
- [ ] Create `/docs/architecture.md` (consolidated)

### Phase 3: Layer 6 (Keep layer6_v2 as canonical)
- [ ] Create `src/layer6_v2/cover_letter/`, `src/layer6_v2/outreach/`
- [ ] Move cover_letter_generator.py, outreach_generator.py from layer6 to layer6_v2
- [ ] Add deprecation warnings to layer6 (re-exports from layer6_v2)
- [ ] Delete src/layer6/html_cv_generator.py (dead code)
- [ ] Run tests, fix failures

### Phase 4: Services
- [ ] Create `JobDocumentUpdater`
- [ ] Refactor services to use updater
- [ ] Update catalogue with service boundaries

### Phase 5: Common
- [ ] Create subdirectory structure
- [ ] Add backward-compatible re-exports
- [ ] Update imports incrementally

### Phase 6: Cleanup
- [ ] Remove deprecated code
- [ ] Final test validation
- [ ] Update all documentation
- [ ] Tag release

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking imports | Use `__init__.py` re-exports, 4-week deprecation |
| Test failures | Run full suite after each step |
| Agent context loss | Update catalogue in real-time during refactoring |
| Production bugs | Deploy to staging first, validate with real jobs |

---

## Agent Assignments

| Phase | Agent | Task |
|-------|-------|------|
| 1 | backend-developer | Create catalogue, query.py |
| 2 | doc-sync | Consolidate documentation |
| 3 | backend-developer | Layer 6 consolidation |
| 4 | backend-developer | Service rationalization |
| 5 | backend-developer | Common reorganization |
| 6 | doc-sync | Final cleanup, catalogue update |

---

## Success Metrics

- [ ] Layer 6: layer6_v2 is canonical, layer6 deleted (reduces 13 → 1 location)
- [ ] Layer 6_v2 organized with cover_letter/ and outreach/ subdirectories
- [ ] Common modules grouped into 10 logical domains
- [ ] Documentation reduced from 150+ to ~20 essential docs
- [ ] Functionality catalogue enables agents to query modules without grep
- [ ] 1600+ tests still passing
- [ ] No deprecated imports in codebase after cleanup
