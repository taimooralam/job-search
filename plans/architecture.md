# System Architecture

## Overview

Job Intelligence Pipeline - 7-layer LangGraph system with professional CV editor and job matching.

## System Diagram

```
Inputs (MongoDB) → JD Processing → CV Analysis → Company Research → Contact Discovery → Enrichment → Output
                        ↓
                  CLI/Web UI (Flask, TipTap Editor)
```

## Pipeline Layers

1. **JD Structure Analysis** - Extract job requirements from job descriptions
2. **CV Coverage Mapping** - Map candidate qualifications to job requirements
3. **Gap Analysis** - Identify skill/experience gaps
4. **Company Research** - Gather company context and insights
5. **Contact Discovery** - Find hiring managers and decision makers
6. **Enrichment & Ranking** - Score fit and generate personalized output
7. **Output Generation** - Create tailored CV, cover letter, and strategy

## Data Model

### JobState (LangGraph State)

```python
class JobState(TypedDict):
    job_id: str                          # MongoDB _id from level-2 collection
    jd: str                             # Job description text
    jd_structured: dict                 # Extracted job requirements
    cv_coverage: dict                   # Section-level coverage mapping
    company_info: dict                  # Company research results
    contacts: list[ContactInfo]        # Discovered contacts
    enrichment: dict                    # Ranking and insights
    output: OutputFormat               # Final deliverables
    error: Optional[str]               # Error context
```

### MongoDB Collections

- **level-2**: Job listings with full descriptions
- **cv-annotations**: JD analysis with section markers
- **company-research**: Cached company data
- **contacts**: Discovered contacts and enrichment

## Key Design Patterns

### Section Coverage Tracking (BUG 4)

**Components:**
- `_annotation_list.html` - Data section attributes on annotation elements
- `jd-annotation.js` - updateCoverage() method updates DOM for section tracking
- Data flow: JD annotations → section attributes → frontend coverage display

**Purpose:** Enable precise tracking of which CV sections address which job requirements

### Verbose Logging Pipeline (BUG 1)

**Components:**
- `StructureJDService.execute()` - Accepts progress_callback and log_callback parameters
- `routes/operations.py` - Passes logging callbacks to service layer
- Data flow: Service layer → callbacks → web UI progress display

**Purpose:** Real-time visibility into JD processing progress for users

### Async-Safe Coroutine Handling (BUG 3/5)

**Components:**
- `orchestrator.py` - New _run_async_safely() method
- Uses ThreadPoolExecutor to handle nested event loops
- Wraps async CV generation in thread-safe executor

**Purpose:** Prevent "RuntimeError: running event loop" when calling async code from sync context

**Architecture:**
```python
def _run_async_safely(self, coro):
    """Handle nested event loops with ThreadPoolExecutor"""
    executor = ThreadPoolExecutor(max_workers=1)
    return executor.submit(asyncio.run, coro).result()
```

### Smart Cache Logic (BUG 2)

**Components:**
- `company_research_service.py` - Modified cache check logic
- Partial cache hit detection triggers people_mapper
- Data flow: Check existing contacts → if partial → call people_mapper → merge results

**Purpose:** Improve contact discovery by combining cached company data with fresh contact mapping

**Logic:**
```
If cached_company_data exists:
  If contacts_from_cache are complete:
    Return cached + contacts
  Else (partial):
    Call people_mapper(company_data)
    Return merged results
```

## Frontend Architecture

### CV Editor (TipTap)

- Rich text editing with inline annotations
- Section-level highlighting for coverage display
- Two-way sync with MongoDB

### Annotation System

- JD annotations display alongside CV editor
- Coverage indicators show section alignment
- Click-to-edit for quick gap filling

### Progress Display

- Real-time callback integration
- Step-by-step logging of JD processing
- Status updates for long-running operations

## Backend Architecture

### Pipeline Orchestration

- LangGraph state machine coordinating 7 layers
- Async-safe execution for event loop compatibility
- Error handling and recovery at each layer

### Service Layer

- StructureJDService: JD analysis with callbacks
- CVMappingService: Coverage calculation
- CompanyResearchService: Smart caching with fallback
- ContactDiscoveryService: Enriched contact mapping

### Database Layer

- MongoDB for persistent state
- Indexed queries on job_id and cv_section
- TTL indexes for cache expiration

## Configuration (Feature Flags)

All config via environment variables:

```bash
# Pipeline
PIPELINE_TIMEOUT=300
ENABLE_VERBOSE_LOGGING=true

# Services
COMPANY_RESEARCH_CACHE_TTL=604800  # 1 week
ENABLE_PEOPLE_MAPPER=true

# Integrations
FIRECRAWL_API_KEY=...
OPENROUTER_API_KEY=...
MONGODB_URI=...
```

## External Services

- **FireCrawl**: Web scraping for company research
- **OpenRouter**: LLM for JD analysis, gap identification
- **MongoDB**: State persistence
- **Google Drive**: CV/cover letter storage

## Error Handling & Recovery

### Nested Event Loop Errors (FIXED)

- Scenario: Async CV generation called from sync routes
- Solution: ThreadPoolExecutor wrapper in orchestrator
- Impact: Eliminates "RuntimeError: running event loop" crashes

### Cache Consistency (IMPROVED)

- Scenario: Partial cache hit in company research
- Solution: Check completeness before cache return
- Impact: More comprehensive contact discovery

### Progress Visibility (ENHANCED)

- Scenario: Long JD processing with no feedback
- Solution: progress_callback and log_callback in service layer
- Impact: Real-time user feedback on processing status

## Data Flow Examples

### JD Processing with Coverage Tracking

```
1. Upload JD → StructureJDService.execute(jd, progress_callback, log_callback)
2. Extract sections → Mark with data-section attributes
3. Update frontend → Coverage display via updateCoverage()
4. Map to CV → Section-level matching
5. Display results → User sees aligned requirements
```

### Contact Discovery with Smart Cache

```
1. Company research triggered
2. Check MongoDB cache
3. If cached + has contacts → return (full cache hit)
4. If cached + no/partial contacts → call people_mapper
5. Merge results → return comprehensive contact list
```

### CV Generation with Safe Async

```
1. User requests CV generation
2. orchestrator._run_async_safely(async_cv_gen_coro)
3. ThreadPoolExecutor spawns new event loop
4. Async operation completes safely
5. Result returned to caller without event loop conflicts
```

## See Also

- `ROADMAP.md` - Overall project direction
- `missing.md` - Implementation gaps tracker
- `next-steps.md` - Immediate action items
