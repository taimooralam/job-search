# Architecture Documentation

## System Overview

The Job Intelligence Pipeline is a 7-layer agentic AI system designed to automate the job search process. It processes job descriptions through specialized AI agents, each focusing on a specific aspect of job intelligence, ultimately generating a tailored, ATS-optimized CV.

### Design Principles

1. **Separation of Concerns**: Each layer has a single responsibility
2. **Observability First**: Full tracing via LangSmith for debugging and optimization
3. **Graceful Degradation**: System continues with partial results when services fail
4. **RAG-Grounded Generation**: All CV content grounded in actual candidate experience
5. **Production Patterns**: Circuit breakers, rate limiters, and structured logging

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           INPUT                                          │
│  ┌─────────────────┐                    ┌─────────────────┐             │
│  │ Job Description │                    │    Master CV    │             │
│  │   (MongoDB)     │                    │    (Markdown)   │             │
│  └────────┬────────┘                    └────────┬────────┘             │
└───────────┼──────────────────────────────────────┼──────────────────────┘
            │                                      │
            ▼                                      │
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 1: JD PROCESSOR                              │
│  • Parse raw job description                                            │
│  • Extract structured requirements (skills, experience, education)      │
│  • Identify role level and domain                                       │
│  • Output: Structured JD analysis                                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 2: PAIN POINT MINER                          │
│  • Analyze JD for implicit challenges                                   │
│  • Identify problems the role is meant to solve                         │
│  • Extract signals of team/org challenges                               │
│  • Output: Pain points with evidence                                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 3: COMPANY RESEARCHER                        │
│  • Scrape company website (FireCrawl)                                   │
│  • Gather public information (news, press releases)                     │
│  • Identify company culture and values                                  │
│  • Output: Company intelligence dossier                                 │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 4: OPPORTUNITY MAPPER                        │
│  • Map pain points to candidate strengths                               │
│  • Identify unique value propositions                                   │
│  • Calculate fit scores                                                 │
│  • Output: Opportunity map with alignment scores                        │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 5: PEOPLE MAPPER                             │
│  • Research hiring manager (LinkedIn, company page)                     │
│  • Identify key stakeholders                                            │
│  • Gather background for personalization                                │
│  • Output: People intelligence for outreach                             │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 6: CV TAILORER                               │
│  • RAG retrieval of relevant achievements ◄────────┐                    │
│  • Role-specific bullet generation                 │                    │
│  • ATS keyword optimization                        │                    │
│  • Hallucination guards                            │                    │
│  • Output: Tailored CV sections      ┌─────────────┴────────┐           │
│                                      │  RAG Knowledge Base  │           │
│                                      │  (MongoDB + Vector)  │           │
│                                      └──────────────────────┘           │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LAYER 7: OUTPUT PUBLISHER                          │
│  • Assemble final CV document                                           │
│  • Generate PDF via WeasyPrint                                          │
│  • Store results in MongoDB                                             │
│  • Output: Markdown CV + PDF                                            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           OUTPUT                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │   Tailored CV   │  │   PDF Export    │  │ Outreach Draft  │         │
│  │   (Markdown)    │  │   (WeasyPrint)  │  │   (Optional)    │         │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### State Management

The pipeline uses LangGraph's state management with a typed `PipelineState` object:

```python
class PipelineState(TypedDict):
    # Input
    job_id: str
    job_description: str
    master_cv: str

    # Layer outputs (accumulated)
    jd_analysis: JDAnalysis
    pain_points: List[PainPoint]
    company_intel: CompanyIntelligence
    opportunity_map: OpportunityMap
    people_intel: PeopleIntelligence

    # Generation
    cv_sections: Dict[str, str]

    # Metadata
    trace_id: str
    layer_timings: Dict[str, float]
    errors: List[str]
```

### Data Persistence

| Data Type | Storage | Purpose |
|-----------|---------|---------|
| Job descriptions | MongoDB `level-2` | Input jobs to process |
| Pipeline results | MongoDB `results` | Layer outputs and final CVs |
| Vectors | MongoDB Atlas Search | RAG retrieval |
| Session state | Redis | Pipeline execution state |
| Traces | LangSmith | Observability and debugging |

---

## Production Patterns

### Circuit Breaker

Protects against cascading failures when external services fail:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError()

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

**Usage:**
- LLM calls (Claude API)
- Web scraping (FireCrawl)
- External API integrations

### Rate Limiter

Respects API rate limits using token bucket algorithm:

```python
class TokenBucketRateLimiter:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()

    async def acquire(self, tokens: int = 1):
        await self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
```

**Rate limits enforced:**
- Claude API: 40 requests/minute
- FireCrawl: 10 requests/minute

### Structured Logging

JSON-formatted logs with correlation IDs:

```python
{
    "timestamp": "2025-01-15T10:30:00Z",
    "level": "INFO",
    "trace_id": "abc-123",
    "layer": "layer6",
    "message": "CV generation complete",
    "duration_ms": 1523,
    "tokens_used": 4521
}
```

---

## RAG System

### Knowledge Base Structure

The RAG system stores achievements and experiences as searchable vectors:

```python
class Achievement:
    id: str
    text: str
    vector: List[float]  # Embedding from text-embedding-3-small

    # Metadata for filtering
    role: str  # "Technical Lead", "Software Engineer"
    domain: str  # "AdTech", "IoT", "CRM"
    skill_tags: List[str]
    impact_type: str  # "revenue", "efficiency", "quality"
    metrics: Dict[str, Any]
```

### Retrieval Strategy

1. **Query Expansion**: Expand JD requirements into search queries
2. **Hybrid Search**: Combine vector similarity + keyword matching
3. **Reranking**: Score results by relevance to specific JD requirements
4. **Diversity**: Ensure coverage across different achievement types

```python
async def retrieve_achievements(jd_requirements: List[str], top_k: int = 10):
    # 1. Generate embeddings for requirements
    query_vectors = await embed_batch(jd_requirements)

    # 2. Vector search with metadata filtering
    candidates = await mongodb.aggregate([
        {"$vectorSearch": {...}},
        {"$match": {"domain": {"$in": target_domains}}},
        {"$limit": top_k * 3}  # Over-fetch for reranking
    ])

    # 3. Rerank by requirement coverage
    ranked = rerank_by_coverage(candidates, jd_requirements)

    # 4. Ensure diversity
    final = ensure_diversity(ranked, top_k)
    return final
```

---

## Observability

### LangSmith Integration

Every layer is traced with:
- Input/output payloads
- Token usage
- Latency measurements
- Error details

```python
@traceable(name="layer6_cv_tailor")
async def generate_cv_section(state: PipelineState, section: str):
    with trace_span(f"generate_{section}"):
        # Retrieve relevant achievements
        achievements = await retrieve_achievements(state.jd_analysis.requirements)

        # Generate section
        result = await llm.generate(
            prompt=CV_SECTION_PROMPT,
            achievements=achievements,
            requirements=state.jd_analysis.requirements
        )

        return result
```

### Metrics Collected

| Metric | Description |
|--------|-------------|
| `layer_duration_ms` | Time spent in each layer |
| `tokens_input` | Input tokens per LLM call |
| `tokens_output` | Output tokens per LLM call |
| `retrieval_count` | Achievements retrieved by RAG |
| `retrieval_relevance` | Average relevance score |
| `error_rate` | Errors per layer |

---

## Service Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DOCKER COMPOSE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │   FastAPI    │  │    Flask     │  │   Runner     │                   │
│  │   (API)      │  │  (Frontend)  │  │  (Worker)    │                   │
│  │   :8000      │  │   :5000      │  │              │                   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                   │
│         │                 │                 │                           │
│         └────────────┬────┴────────────────┘                            │
│                      │                                                  │
│         ┌────────────┼────────────┐                                     │
│         │            │            │                                     │
│         ▼            ▼            ▼                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │   MongoDB    │  │    Redis     │  │ PDF Service  │                   │
│  │   :27017     │  │   :6379      │  │   :8080      │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Responsibilities

| Service | Port | Purpose |
|---------|------|---------|
| **FastAPI** | 8000 | REST API for pipeline operations |
| **Flask** | 5000 | Web UI with CV editor |
| **Runner** | - | Background job processing |
| **MongoDB** | 27017 | Data persistence + vector search |
| **Redis** | 6379 | Job queue + session state |
| **PDF Service** | 8080 | CV PDF generation |

---

## Error Handling

### Error Categories

| Category | Handling | Retry |
|----------|----------|-------|
| **Transient** (network, timeout) | Retry with backoff | Yes, 3x |
| **Rate Limit** | Wait and retry | Yes, after delay |
| **Validation** | Skip with warning | No |
| **Fatal** (auth, config) | Fail pipeline | No |

### Graceful Degradation

When services fail, the pipeline continues with degraded functionality:

| Service Failure | Degradation |
|-----------------|-------------|
| FireCrawl down | Skip company research, use cached data |
| RAG retrieval slow | Use keyword matching fallback |
| PDF service down | Return Markdown only |

---

## Security Considerations

### Secrets Management

All secrets via environment variables:
- `ANTHROPIC_API_KEY`
- `MONGODB_URI`
- `FIRECRAWL_API_KEY`
- `LANGCHAIN_API_KEY`

Never committed to version control.

### Data Privacy

- Personal CV data stored locally only
- No PII in logs or traces
- MongoDB access restricted by IP whitelist

---

## Performance Characteristics

| Metric | Target | Actual |
|--------|--------|--------|
| Full pipeline (7 layers) | < 5 min | ~3-4 min |
| Single CV generation | < 60s | ~45s |
| RAG retrieval | < 2s | ~1.5s |
| PDF generation | < 10s | ~5s |

---

## Future Improvements

1. **Caching Layer**: Redis cache for company research
2. **Parallel Execution**: Run independent layers concurrently
3. **A/B Testing**: Compare CV generation strategies
4. **Feedback Loop**: Track application outcomes to improve generation
