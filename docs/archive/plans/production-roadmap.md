# Production Roadmap - Complete System Deployment

**Goal**: Deploy a production-ready job intelligence pipeline with monitoring, error handling, and quality gates.

**Target**: Working end-to-end system on VPS + Vercel with full observability

---

## Phase 0: Immediate Blockers (TODAY)

### 0.1: Verify Local Pipeline Works
**Status**: IN PROGRESS
**Time**: 10 minutes

**Actions**:
```bash
# Pipeline is running with job ID: 69270cfd2bdb1c105a6fdffc
# Monitor: tail -f pipeline_test.log

# After completion, verify artifacts
ls -la applications/Acme_Corporation/Senior_Software_Engineer/
# Expected: CV.md, dossier.txt, cover_letter.txt
```

**Success Criteria**:
- Pipeline completes all 7 layers
- Artifacts created in applications/
- MongoDB updated with pain_points, fit_score, cv_path

---

### 0.2: Add Mocking to CV Generator Tests
**Status**: NOT STARTED
**Time**: 30 minutes

**Problem**: CV generator tests make real API calls, fail when credits low

**Action**: Edit `tests/unit/test_layer6_markdown_cv_generator.py`

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def mock_anthropic():
    """Mock ChatAnthropic to avoid real API calls in tests."""
    with patch('src.layer6.generator.ChatAnthropic') as mock_class:
        # Mock for evidence extraction pass
        mock_instance = MagicMock()

        # First call: Evidence extraction
        evidence_response = MagicMock()
        evidence_response.content = '''{
            "evidence_json": {
                "contact_info": {
                    "name": "John Doe",
                    "email": "john@example.com",
                    "phone": "+1-555-0100"
                },
                "professional_summary": "Experienced engineer with 10+ years...",
                "experience": [
                    {
                        "company": "Tech Corp",
                        "role": "Senior Engineer",
                        "duration": "2020-Present",
                        "bullets": [
                            "Led team of 5 engineers",
                            "Reduced latency by 40%"
                        ]
                    }
                ]
            },
            "cv_markdown": "# John Doe\\n\\n## Professional Summary\\nExperienced engineer..."
        }'''

        # Second call: QA pass
        qa_response = MagicMock()
        qa_response.content = "# John Doe\\n\\n## Professional Summary\\nExperienced engineer with 10+ years in distributed systems..."

        mock_instance.invoke.side_effect = [evidence_response, qa_response]
        mock_class.return_value = mock_instance
        yield mock_instance
```

**Verify**:
```bash
python -m pytest tests/unit/test_layer6_markdown_cv_generator.py -v
# Expected: All 21 tests pass
```

**Success Criteria**:
- All CV generator tests pass
- No real API calls made
- Tests run < 5 seconds

---

## Phase 1: Production Infrastructure (WEEK 1)

### 1.1: VPS Environment Setup
**Status**: PARTIALLY COMPLETE
**Time**: 1 hour

**Actions**:
```bash
# SSH into VPS
ssh root@72.61.92.76
cd /root/job-runner

# Create production .env
cat > .env << 'EOF'
# ===== RUNNER SERVICE =====
MAX_CONCURRENCY=3
LOG_BUFFER_LIMIT=1000
PIPELINE_TIMEOUT_SECONDS=900
RUNNER_API_SECRET=<GENERATE_NEW>
CORS_ORIGINS=https://your-production-app.vercel.app
ENVIRONMENT=production

# ===== PIPELINE SECRETS =====
MONGODB_URI=<production-mongodb-uri>
OPENAI_API_KEY=<production-key>
ANTHROPIC_API_KEY=<production-key>
FIRECRAWL_API_KEY=<production-key>

# ===== LANGSMITH (OBSERVABILITY) =====
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<langsmith-key>
LANGCHAIN_PROJECT=job-intelligence-prod

# ===== FEATURE FLAGS =====
DISABLE_FIRECRAWL_OUTREACH=true
USE_ANTHROPIC=true
ENABLE_STAR_SELECTOR=false
ENABLE_REMOTE_PUBLISHING=false

# ===== LOGGING =====
LOG_LEVEL=INFO
LOG_FORMAT=json
EOF

# Generate secure secret
echo "RUNNER_API_SECRET=$(openssl rand -hex 32)" >> .env

# Copy master CV
scp master-cv.md root@72.61.92.76:/root/job-runner/

# Verify
ls -la .env master-cv.md
```

**Success Criteria**:
- .env file with all production secrets
- master-cv.md on VPS
- RUNNER_API_SECRET is unique and secure

---

### 1.2: Vercel Production Environment
**Status**: NOT STARTED
**Time**: 30 minutes

**Actions**: In Vercel Dashboard > Settings > Environment Variables

| Variable | Value | Notes |
|----------|-------|-------|
| `ENVIRONMENT` | `production` | Distinguishes from dev |
| `LOGIN_PASSWORD` | (secure password) | Use password manager |
| `FLASK_SECRET_KEY` | (generate) | `python -c "import os; print(os.urandom(32).hex())"` |
| `MONGODB_URI` | (production Atlas URI) | Same as VPS |
| `RUNNER_URL` | `http://72.61.92.76:8000` | VPS runner endpoint |
| `RUNNER_API_SECRET` | (same as VPS) | **MUST MATCH** |

**Success Criteria**:
- All 6 environment variables set
- Secrets stored securely (1Password, etc.)
- RUNNER_API_SECRET matches VPS exactly

---

### 1.3: Deploy Runner to VPS
**Status**: READY
**Time**: 15 minutes

**Actions**:
```bash
# Option A: Trigger CI/CD
git add -A
git commit -m "chore: Configure production environment"
git push origin main
# GitHub Actions will deploy automatically

# Option B: Manual deployment
ssh root@72.61.92.76
cd /root/job-runner
docker compose -f docker-compose.runner.yml pull
docker compose -f docker-compose.runner.yml up -d --remove-orphans

# Verify deployment
docker ps | grep runner
curl http://localhost:8000/health
```

**Verify**:
```bash
# Health check
curl http://72.61.92.76:8000/health
# Expected: {"status": "healthy", "active_runs": 0, "max_concurrency": 3}

# Logs
ssh root@72.61.92.76 "docker logs job-runner-runner-1 --tail 50"
# Expected: No errors, "Uvicorn running on..."
```

**Success Criteria**:
- Container running and healthy
- Health endpoint returns 200
- No errors in logs

---

### 1.4: Deploy Frontend to Vercel
**Status**: READY
**Time**: 10 minutes

**Actions**:
```bash
# Push to trigger deployment
git push origin main
# Vercel auto-deploys

# OR manually trigger in Vercel dashboard
```

**Verify**:
```bash
# Test frontend
curl https://your-app.vercel.app/api/health
# Expected: 200 OK

# Test authentication
# Visit URL in browser, verify login works
```

**Success Criteria**:
- Frontend deploys successfully
- Login page loads
- Health indicators show VPS/MongoDB connected

---

### 1.5: End-to-End Integration Test
**Status**: NOT STARTED
**Time**: 15 minutes

**Actions**:
1. Open Vercel frontend URL in browser
2. Login with production LOGIN_PASSWORD
3. Navigate to job detail page (use test job: 69270cfd2bdb1c105a6fdffc)
4. Click "Process Job" button
5. Watch logs stream in real-time
6. Wait for completion (2-5 minutes)

**Verify**:
```bash
# Check MongoDB
mongosh "$MONGODB_URI" --eval "
  db.getSiblingDB('jobs').getCollection('level-2').findOne(
    {_id: ObjectId('69270cfd2bdb1c105a6fdffc')},
    {
      status: 1,
      pain_points: 1,
      fit_score: 1,
      cv_path: 1,
      primary_contacts: 1
    }
  )
"

# Expected output:
# {
#   status: "ready for applying",
#   pain_points: [...],
#   fit_score: 85,
#   cv_path: "applications/Acme_Corporation/Senior_Software_Engineer/CV.md",
#   primary_contacts: [...]
# }
```

**Success Criteria**:
- Process button triggers pipeline
- Logs stream in UI
- Progress bar reaches 100%
- Job status updates to "ready for applying"
- All pipeline fields in MongoDB

---

## Phase 2: Observability & Monitoring (WEEK 2)

### 2.1: Structured Logging
**Status**: NOT STARTED
**Time**: 4 hours

**Problem**: All layers use `print()`, no structured logs

**Action 1**: Create logging module

```python
# src/common/logging.py
import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional
import os

class StructuredLogger:
    """Structured JSON logger with run_id tagging."""

    def __init__(self, name: str, run_id: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.run_id = run_id
        self.log_format = os.getenv("LOG_FORMAT", "simple")  # simple or json

    def _format_message(self, level: str, message: str, **extra) -> str:
        """Format log message as JSON or simple text."""
        if self.log_format == "json":
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": level,
                "message": message,
                "run_id": self.run_id,
                **extra
            }
            return json.dumps(log_data)
        else:
            run_id_str = f"[{self.run_id}] " if self.run_id else ""
            extra_str = f" {extra}" if extra else ""
            return f"{run_id_str}{message}{extra_str}"

    def info(self, message: str, **extra):
        self.logger.info(self._format_message("INFO", message, **extra))

    def error(self, message: str, **extra):
        self.logger.error(self._format_message("ERROR", message, **extra))

    def warning(self, message: str, **extra):
        self.logger.warning(self._format_message("WARNING", message, **extra))
```

**Action 2**: Update all layers to use structured logger

```python
# Example: src/layer2/pain_point_miner.py
from src.common.logging import StructuredLogger

def pain_point_miner_node(state: JobState) -> Dict[str, Any]:
    logger = StructuredLogger(__name__, run_id=state.get("run_id"))
    logger.info("Starting pain point mining", job_id=state.get("job_id"))

    try:
        # ... existing code ...
        logger.info("Pain point mining complete", count=len(pain_points))
    except Exception as e:
        logger.error("Pain point mining failed", error=str(e))
```

**Verify**:
```bash
# Run pipeline with JSON logging
LOG_FORMAT=json python scripts/run_pipeline.py --job-id <id>

# Check logs are structured
grep "pain_point" pipeline.log | jq .
# Expected: Valid JSON with timestamp, level, run_id, message
```

**Success Criteria**:
- All layers use StructuredLogger
- JSON logs parse correctly
- run_id present in all log lines

---

### 2.2: Cost Tracking
**Status**: NOT STARTED
**Time**: 3 hours

**Action**: Add cost tracking to LLM calls

```python
# src/common/cost_tracker.py
from typing import Dict, List
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass
class LLMCall:
    """Record of a single LLM API call."""
    timestamp: str
    layer: str
    model: str
    provider: str  # openai, anthropic, openrouter
    input_tokens: int
    output_tokens: int
    cost_usd: float
    run_id: str

class CostTracker:
    """Track and report LLM API costs."""

    # Pricing per 1M tokens (update from provider docs)
    PRICING = {
        "openai": {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        },
        "anthropic": {
            "claude-3-5-haiku-20241022": {"input": 1.00, "output": 5.00},
        }
    }

    def __init__(self):
        self.calls: List[LLMCall] = []

    def record_call(self, layer: str, model: str, provider: str,
                    input_tokens: int, output_tokens: int, run_id: str):
        """Record a single LLM call."""
        pricing = self.PRICING.get(provider, {}).get(model, {"input": 0, "output": 0})
        cost = (input_tokens / 1_000_000 * pricing["input"]) + \
               (output_tokens / 1_000_000 * pricing["output"])

        call = LLMCall(
            timestamp=datetime.utcnow().isoformat(),
            layer=layer,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            run_id=run_id
        )
        self.calls.append(call)

    def get_run_cost(self, run_id: str) -> float:
        """Get total cost for a specific run."""
        return sum(call.cost_usd for call in self.calls if call.run_id == run_id)

    def export_to_file(self, path: Path):
        """Export cost data to JSON."""
        with open(path, 'w') as f:
            json.dump([asdict(call) for call in self.calls], f, indent=2)
```

**Integration**: Wrap LLM calls

```python
# Update ChatOpenAI wrapper
from src.common.cost_tracker import cost_tracker

def tracked_llm_call(layer: str, messages, model, run_id):
    """Wrapper that tracks costs."""
    response = llm.invoke(messages)

    # Extract token counts from response metadata
    usage = response.response_metadata.get("token_usage", {})
    cost_tracker.record_call(
        layer=layer,
        model=model,
        provider="openai",
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        run_id=run_id
    )

    return response
```

**Verify**:
```bash
# Run pipeline
python scripts/run_pipeline.py --job-id <id>

# Check cost report
python -c "
from src.common.cost_tracker import cost_tracker
print(f'Total cost: ${cost_tracker.get_run_cost(\"run_id\"):.4f}')
"
```

**Success Criteria**:
- Every LLM call tracked
- Cost per run accurate
- Cost data exported to JSON

---

### 2.3: Health Monitoring & Alerts
**Status**: NOT STARTED
**Time**: 4 hours

**Action 1**: Add detailed health checks

```python
# runner_service/health.py
from typing import Dict, Any
from datetime import datetime
import requests

async def comprehensive_health_check() -> Dict[str, Any]:
    """Detailed health check for all dependencies."""
    health = {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_status": "healthy",
        "checks": {}
    }

    # Check MongoDB
    try:
        from src.common.database import db
        db.db.admin.command('ping')
        health["checks"]["mongodb"] = {"status": "healthy"}
    except Exception as e:
        health["checks"]["mongodb"] = {"status": "unhealthy", "error": str(e)}
        health["overall_status"] = "degraded"

    # Check OpenAI API
    try:
        from src.common.config import Config
        # Make a minimal test call
        test_response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {Config.OPENAI_API_KEY}"},
            timeout=5
        )
        if test_response.status_code == 200:
            health["checks"]["openai"] = {"status": "healthy"}
        else:
            health["checks"]["openai"] = {"status": "unhealthy", "code": test_response.status_code}
            health["overall_status"] = "degraded"
    except Exception as e:
        health["checks"]["openai"] = {"status": "unhealthy", "error": str(e)}
        health["overall_status"] = "degraded"

    # Check FireCrawl
    try:
        from firecrawl import FirecrawlApp
        from src.common.config import Config
        fc = FirecrawlApp(api_key=Config.FIRECRAWL_API_KEY)
        # Test with quota check (if available)
        health["checks"]["firecrawl"] = {"status": "healthy"}
    except Exception as e:
        health["checks"]["firecrawl"] = {"status": "unhealthy", "error": str(e)}
        health["overall_status"] = "degraded"

    return health
```

**Action 2**: Set up UptimeRobot or similar

1. Create account at https://uptimerobot.com
2. Add HTTP monitor for `http://72.61.92.76:8000/health`
3. Set check interval: 5 minutes
4. Add alert contacts (email, Slack)

**Action 3**: Add error rate monitoring

```python
# runner_service/metrics.py
from collections import defaultdict
from datetime import datetime, timedelta

class MetricsCollector:
    """Simple in-memory metrics."""

    def __init__(self):
        self.error_count = 0
        self.success_count = 0
        self.error_by_layer = defaultdict(int)
        self.last_reset = datetime.utcnow()

    def record_error(self, layer: str):
        self.error_count += 1
        self.error_by_layer[layer] += 1

    def record_success(self):
        self.success_count += 1

    def get_error_rate(self) -> float:
        total = self.error_count + self.success_count
        return self.error_count / total if total > 0 else 0.0

    def reset_hourly(self):
        """Reset metrics every hour."""
        if datetime.utcnow() - self.last_reset > timedelta(hours=1):
            self.error_count = 0
            self.success_count = 0
            self.error_by_layer.clear()
            self.last_reset = datetime.utcnow()
```

**Success Criteria**:
- Health endpoint shows all dependency status
- UptimeRobot monitors VPS runner
- Alerts trigger on failures

---

## Phase 3: Testing & Quality (WEEK 3)

### 3.1: Integration Test Suite
**Status**: NOT STARTED
**Time**: 6 hours

**Action**: Create end-to-end integration tests

```python
# tests/integration/test_full_pipeline.py
import pytest
from bson import ObjectId
from datetime import datetime
from src.workflow import run_pipeline
from src.common.database import db

@pytest.mark.integration
def test_full_pipeline_with_real_job():
    """Test complete pipeline execution."""
    # Create test job
    test_job = {
        "_id": ObjectId(),
        "jobId": 9999,
        "title": "Test Engineer",
        "company": "Test Corp",
        "job_description": "Test job description with pain points...",
        "created_at": datetime.utcnow(),
        "status": "new"
    }

    db.db['level-2'].insert_one(test_job)
    job_id = str(test_job["_id"])

    try:
        # Run pipeline
        final_state = run_pipeline(job_id, "master-cv.md")

        # Verify all layers executed
        assert "pain_points" in final_state
        assert len(final_state["pain_points"]) >= 5

        assert "company_research" in final_state
        assert final_state["company_research"] is not None

        assert "fit_score" in final_state
        assert 0 <= final_state["fit_score"] <= 100

        assert "primary_contacts" in final_state
        assert len(final_state["primary_contacts"]) >= 4

        assert "cv_path" in final_state

        # Verify MongoDB updated
        updated_job = db.db['level-2'].find_one({"_id": test_job["_id"]})
        assert updated_job["status"] == "ready for applying"
        assert "pain_points" in updated_job

    finally:
        # Cleanup
        db.db['level-2'].delete_one({"_id": test_job["_id"]})


@pytest.mark.integration
def test_pipeline_error_handling():
    """Test pipeline handles errors gracefully."""
    # Test with invalid job ID
    with pytest.raises(Exception):
        run_pipeline("invalid_id", "master-cv.md")

    # Test with missing master CV
    test_job = {...}  # minimal job
    db.db['level-2'].insert_one(test_job)

    try:
        # Should fail gracefully, not crash
        final_state = run_pipeline(str(test_job["_id"]), "nonexistent.md")
        assert "errors" in final_state
        assert len(final_state["errors"]) > 0
    finally:
        db.db['level-2'].delete_one({"_id": test_job["_id"]})
```

**Run integration tests**:
```bash
python -m pytest tests/integration/ -v -m integration
```

**Success Criteria**:
- Integration tests pass consistently
- Error scenarios handled gracefully
- Tests run in < 5 minutes

---

### 3.2: Add Integration Tests to CI
**Status**: NOT STARTED
**Time**: 2 hours

**Action**: Update `.github/workflows/pipeline-ci.yml`

```yaml
name: Pipeline CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run unit tests
        run: python -m pytest tests/unit/ -v --ignore=tests/unit/test_layer6_markdown_cv_generator.py

  integration-tests:
    runs-on: ubuntu-latest
    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017

    env:
      MONGODB_URI: mongodb://localhost:27017/test
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run integration tests
        run: python -m pytest tests/integration/ -v -m integration
```

**Success Criteria**:
- CI runs on every push
- Both unit and integration tests run
- Tests use ephemeral MongoDB

---

### 3.3: Code Coverage Tracking
**Status**: NOT STARTED
**Time**: 2 hours

**Action**: Add coverage reporting

```bash
# Install coverage
pip install pytest-cov

# Update GitHub Actions
- name: Run tests with coverage
  run: python -m pytest tests/unit/ --cov=src --cov-report=xml --cov-report=term

- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

**Success Criteria**:
- Coverage > 70%
- Coverage badge in README
- Coverage tracked over time

---

## Phase 4: Feature Completeness (WEEK 4-5)

### 4.1: STAR Selector Improvements
**Status**: NOT STARTED
**Time**: 8 hours

**Current**: LLM-only scoring, disabled by default
**Target**: Hybrid selector with embeddings and caching

**Action 1**: Add embedding generation

```python
# src/layer2_5/embeddings.py
from openai import OpenAI
import numpy as np

def generate_embeddings(texts: List[str]) -> np.ndarray:
    """Generate embeddings for STAR records."""
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts
    )

    embeddings = [item.embedding for item in response.data]
    return np.array(embeddings)
```

**Action 2**: Add cosine similarity filtering

```python
def hybrid_star_selection(pain_points: List[str],
                         all_stars: List[Dict],
                         top_k: int = 10) -> List[Dict]:
    """Hybrid selection: embeddings + LLM scoring."""

    # 1. Generate embeddings for pain points
    pain_embeddings = generate_embeddings(pain_points)

    # 2. Get cached or generate STAR embeddings
    star_embeddings = get_or_create_star_embeddings(all_stars)

    # 3. Compute similarities
    similarities = cosine_similarity(pain_embeddings, star_embeddings)

    # 4. Filter to top_k candidates
    top_indices = np.argsort(similarities.mean(axis=0))[-top_k:]
    candidates = [all_stars[i] for i in top_indices]

    # 5. LLM scoring on filtered set
    final_stars = llm_score_stars(pain_points, candidates)

    return final_stars[:3]  # Return top 3
```

**Action 3**: Add caching

```python
# Cache selections by pain point hash
def get_cached_selection(pain_points: List[str], job_id: str) -> Optional[List[Dict]]:
    """Get cached STAR selection."""
    pain_hash = hashlib.sha256(json.dumps(sorted(pain_points)).encode()).hexdigest()

    cache_doc = db.db['star_selection_cache'].find_one({
        "pain_hash": pain_hash,
        "created_at": {"$gte": datetime.utcnow() - timedelta(days=30)}
    })

    if cache_doc:
        return cache_doc["selected_stars"]
    return None
```

**Success Criteria**:
- Embedding-based filtering 10x faster than full LLM scoring
- Cache hit rate > 60%
- Selection quality as good or better than LLM-only

---

### 4.2: .docx CV Export
**Status**: NOT STARTED
**Time**: 4 hours

**Action**: Add docx generation

```bash
pip install python-docx
```

```python
# src/layer6/docx_generator.py
from docx import Document
from docx.shared import Pt, Inches

def generate_docx_cv(markdown_cv: str, output_path: Path):
    """Convert markdown CV to professional .docx."""
    doc = Document()

    # Set margins
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)

    # Parse markdown and add to doc
    lines = markdown_cv.split('\n')
    for line in lines:
        if line.startswith('# '):
            # Heading 1: Name
            p = doc.add_heading(line[2:], level=1)
            p.style.font.size = Pt(16)
        elif line.startswith('## '):
            # Heading 2: Section
            p = doc.add_heading(line[3:], level=2)
            p.style.font.size = Pt(14)
        elif line.startswith('- '):
            # Bullet point
            doc.add_paragraph(line[2:], style='List Bullet')
        else:
            # Regular paragraph
            doc.add_paragraph(line)

    doc.save(output_path)
```

**Integrate into generator**:
```python
# After generating markdown CV
cv_md_path = output_dir / "CV.md"
cv_md_path.write_text(cv_markdown)

# Generate .docx
cv_docx_path = output_dir / "CV.docx"
generate_docx_cv(cv_markdown, cv_docx_path)

return {
    "cv_path": str(cv_md_path),
    "cv_docx_path": str(cv_docx_path),
    ...
}
```

**Success Criteria**:
- .docx CV generated alongside .md
- Professional formatting
- Compatible with ATS systems

---

### 4.3: Enable FireCrawl Contact Discovery
**Status**: PARTIALLY COMPLETE
**Time**: 2 hours

**Current**: Disabled by default, uses synthetic contacts
**Target**: Enable with rate limiting

**Action**: Add token bucket rate limiter

```python
# src/common/rate_limiter.py
import time
from collections import deque

class TokenBucket:
    """Token bucket rate limiter for FireCrawl API."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: Maximum tokens (requests per minute)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def wait_for_token(self, tokens: int = 1):
        """Block until tokens available."""
        while not self.consume(tokens):
            time.sleep(0.1)

# Global limiter: 100 requests/minute
firecrawl_limiter = TokenBucket(capacity=100, refill_rate=100/60)
```

**Integrate into people mapper**:
```python
# Before each FireCrawl call
firecrawl_limiter.wait_for_token()
search_response = self.firecrawl.search(query, limit=5)
```

**Success Criteria**:
- Rate limiting prevents API quota exhaustion
- Requests distributed evenly over time
- No 429 errors from FireCrawl

---

### 4.4: Complete State Model
**Status**: NOT STARTED
**Time**: 3 hours

**Problem**: JobState missing fields

**Action**: Update `src/common/state.py`

```python
class JobState(TypedDict, total=False):
    # ... existing fields ...

    # Missing fields
    tier: str  # "high", "medium", "low"
    dossier_path: str  # Path to generated dossier
    cv_text: str  # Full CV text for MongoDB
    application_form_fields: Dict[str, str]  # Parsed form fields

    # Outreach persistence
    outreach_packages: List[Dict]  # Per-contact packages
    fallback_cover_letters: List[str]  # Generic letters
```

**Update publisher** to populate these fields:
```python
# Layer 7
dossier_path = output_dir / "dossier.txt"
dossier_path.write_text(dossier_content)

return {
    "dossier_path": str(dossier_path),
    "cv_text": cv_markdown,  # For MongoDB
    "tier": calculate_tier(state["fit_score"]),
    ...
}
```

**Success Criteria**:
- All state fields populated
- MongoDB documents complete
- No missing data in output

---

## Phase 5: Production Hardening (WEEK 6)

### 5.1: Error Recovery & Retries
**Status**: PARTIAL
**Time**: 4 hours

**Current**: Tenacity retries on LLM calls only
**Target**: Layer-level retry with exponential backoff

**Action**: Add retry decorator to nodes

```python
# src/common/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

def retry_node(max_attempts: int = 3):
    """Retry decorator for LangGraph nodes."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        retry=retry_if_exception_type((
            requests.exceptions.RequestException,
            TimeoutError,
            ConnectionError
        )),
        reraise=True
    )

# Apply to nodes
@retry_node(max_attempts=3)
def pain_point_miner_node(state: JobState) -> Dict[str, Any]:
    # ... existing code ...
```

**Success Criteria**:
- Transient errors automatically retried
- Permanent errors fail fast
- Retry attempts logged

---

### 5.2: Resource Limits & Quotas
**Status**: NOT STARTED
**Time**: 3 hours

**Action**: Add budget constraints

```python
# src/common/budget.py
class BudgetLimits:
    """Enforce cost and rate limits."""

    MAX_COST_PER_RUN = 0.50  # USD
    MAX_FIRECRAWL_CALLS_PER_RUN = 20

    def __init__(self):
        self.current_cost = 0.0
        self.firecrawl_calls = 0

    def check_cost_limit(self, estimated_cost: float):
        """Raise if adding this cost exceeds budget."""
        if self.current_cost + estimated_cost > self.MAX_COST_PER_RUN:
            raise BudgetExceededError(
                f"Cost limit exceeded: ${self.current_cost + estimated_cost:.2f} > ${self.MAX_COST_PER_RUN}"
            )
        self.current_cost += estimated_cost

    def check_firecrawl_limit(self):
        """Raise if FireCrawl calls exceed limit."""
        self.firecrawl_calls += 1
        if self.firecrawl_calls > self.MAX_FIRECRAWL_CALLS_PER_RUN:
            raise BudgetExceededError(
                f"FireCrawl limit exceeded: {self.firecrawl_calls} > {self.MAX_FIRECRAWL_CALLS_PER_RUN}"
            )
```

**Integrate into workflow**:
```python
budget = BudgetLimits()

# Before expensive LLM call
budget.check_cost_limit(estimated_cost=0.02)

# Before FireCrawl call
budget.check_firecrawl_limit()
```

**Success Criteria**:
- Runaway costs prevented
- Budget limits configurable
- Graceful degradation when limits hit

---

### 5.3: Security Audit
**Status**: NOT STARTED
**Time**: 4 hours

**Actions**:
1. **Secrets management**: Ensure no secrets in git
   ```bash
   git log -p | grep -i "api_key\|secret\|password"
   # Should return nothing
   ```

2. **Path traversal**: Verify artifact serving security
   ```python
   # Already implemented in runner_service/app.py
   # Verify no vulnerabilities
   ```

3. **Input validation**: Add schema validation
   ```python
   from pydantic import BaseModel, validator

   class JobInput(BaseModel):
       job_id: str
       title: str
       company: str

       @validator('job_id')
       def validate_job_id(cls, v):
           if not ObjectId.is_valid(v):
               raise ValueError('Invalid job ID format')
           return v
   ```

4. **Dependency audit**:
   ```bash
   pip install safety
   safety check

   # Fix vulnerabilities
   pip install --upgrade <package>
   ```

**Success Criteria**:
- No secrets in git history
- No path traversal vulnerabilities
- Input validation on all endpoints
- All dependencies up to date

---

### 5.4: Backup & Disaster Recovery
**Status**: NOT STARTED
**Time**: 3 hours

**Action**: Set up MongoDB backups

```bash
# On VPS, create backup script
cat > /root/backup_mongo.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/root/backups/mongodb"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.gz"

mkdir -p $BACKUP_DIR

# Dump database
mongodump --uri="$MONGODB_URI" --gzip --archive=$BACKUP_FILE

# Keep only last 7 backups
ls -t $BACKUP_DIR/backup_*.gz | tail -n +8 | xargs rm -f

echo "Backup complete: $BACKUP_FILE"
EOF

chmod +x /root/backup_mongo.sh

# Add to crontab (daily at 2 AM)
crontab -e
0 2 * * * /root/backup_mongo.sh >> /var/log/mongo_backup.log 2>&1
```

**Success Criteria**:
- Daily automated backups
- 7 days retention
- Tested restore procedure

---

## Phase 6: Documentation & Handoff (WEEK 7)

### 6.1: API Documentation
**Status**: NOT STARTED
**Time**: 4 hours

**Action**: Add OpenAPI docs to runner service

```python
# runner_service/app.py
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Job Intelligence Runner API",
        version="1.0.0",
        description="API for triggering and monitoring job pipeline runs",
        routes=app.routes,
    )

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# Access at: http://72.61.92.76:8000/docs
```

**Success Criteria**:
- Interactive API docs at /docs
- All endpoints documented
- Example requests/responses

---

### 6.2: Runbook
**Status**: NOT STARTED
**Time**: 6 hours

**Action**: Create `RUNBOOK.md`

```markdown
# Production Runbook

## Common Issues

### Pipeline Fails on Layer 2 (Pain Points)
**Symptoms**: Error in logs: "Pain point mining failed"
**Cause**: LLM returned invalid JSON
**Fix**:
1. Check logs for actual LLM response
2. Verify pain_points in response match schema
3. If schema mismatch, update Pydantic model

### VPS Runner Returns 503
**Symptoms**: Frontend shows "Service Unavailable"
**Cause**: All 3 concurrent slots occupied
**Fix**:
1. Check active runs: `curl http://localhost:8000/health`
2. If stuck runs, restart: `docker restart job-runner-runner-1`
3. Increase MAX_CONCURRENCY in .env if needed

### MongoDB Connection Timeout
**Symptoms**: "ServerSelectionTimeoutError"
**Cause**: VPS IP not whitelisted in Atlas
**Fix**:
1. Go to MongoDB Atlas > Network Access
2. Add VPS IP: 72.61.92.76
3. Restart runner

## Deployment Procedures

### Rolling Back VPS
\`\`\`bash
ssh root@72.61.92.76
cd /root/job-runner
git log --oneline -10
git checkout <previous-commit>
docker compose up -d --build
\`\`\`

### Emergency Shutdown
\`\`\`bash
# Stop runner immediately
ssh root@72.61.92.76 "docker stop job-runner-runner-1"

# Disable frontend
# In Vercel dashboard > Deployments > Promote previous
\`\`\`
```

**Success Criteria**:
- All common issues documented
- Step-by-step procedures
- Emergency contacts listed

---

### 6.3: Performance Benchmarks
**Status**: NOT STARTED
**Time**: 3 hours

**Action**: Document baseline performance

```python
# tests/benchmarks/test_performance.py
import pytest
import time

@pytest.mark.benchmark
def test_pipeline_latency():
    """Measure end-to-end pipeline latency."""
    start = time.time()

    # Run pipeline
    run_pipeline(job_id="test", profile="master-cv.md")

    elapsed = time.time() - start

    # Assert reasonable latency
    assert elapsed < 180, f"Pipeline too slow: {elapsed}s"

    print(f"Pipeline completed in {elapsed:.1f}s")

@pytest.mark.benchmark
def test_layer_breakdown():
    """Measure per-layer latency."""
    timings = {}

    # Time each layer
    for layer in [2, 3, 4, 5, 6, 7]:
        start = time.time()
        # Run layer...
        timings[f"layer_{layer}"] = time.time() - start

    # Print breakdown
    for layer, duration in timings.items():
        print(f"{layer}: {duration:.2f}s")
```

**Document in README**:
```markdown
## Performance Benchmarks

| Metric | Target | Actual |
|--------|--------|--------|
| End-to-end latency | < 3 min | 2.5 min |
| Layer 2 (Pain Points) | < 15s | 12s |
| Layer 3 (Company Research) | < 30s | 25s |
| Layer 6 (CV Generation) | < 60s | 55s |
| Throughput | 20 jobs/hour | 22 jobs/hour |
```

**Success Criteria**:
- Baseline metrics documented
- Performance regressions tracked
- Optimization targets identified

---

## Phase 7: Production Launch (WEEK 8)

### 7.1: Soft Launch
**Status**: NOT STARTED
**Time**: 1 week

**Actions**:
1. Process 10 test jobs through production pipeline
2. Monitor logs, costs, errors
3. Collect feedback on output quality
4. Fix any critical issues

**Success Criteria**:
- 90% success rate on test jobs
- No critical bugs
- Output quality meets expectations

---

### 7.2: Production Monitoring Setup
**Status**: NOT STARTED
**Time**: 1 day

**Actions**:
1. Set up Grafana dashboard (optional)
2. Configure log aggregation (Papertrail, Logtail)
3. Set up alerts:
   - Error rate > 10%
   - Cost per job > $1
   - VPS CPU > 80%
   - MongoDB connection failures

**Success Criteria**:
- Metrics visible in dashboard
- Alerts trigger correctly
- On-call rotation defined

---

### 7.3: Full Production Launch
**Status**: NOT STARTED
**Time**: Ongoing

**Actions**:
1. Announce to team
2. Process real jobs
3. Monitor closely for first week
4. Iterate based on feedback

**Success Criteria**:
- System handles production load
- Quality maintained
- Users satisfied

---

## Summary Checklist

### Week 1: Infrastructure
- [ ] Local pipeline verified with Anthropic
- [ ] CV generator tests mocked
- [ ] VPS environment configured
- [ ] Vercel environment configured
- [ ] End-to-end test passing

### Week 2: Observability
- [ ] Structured logging implemented
- [ ] Cost tracking operational
- [ ] Health monitoring setup
- [ ] Alerts configured

### Week 3: Testing
- [ ] Integration test suite complete
- [ ] Tests in CI/CD
- [ ] Coverage > 70%

### Week 4-5: Features
- [ ] STAR selector with embeddings
- [ ] .docx CV export
- [ ] FireCrawl rate limiting
- [ ] Complete state model

### Week 6: Hardening
- [ ] Error recovery improved
- [ ] Budget limits enforced
- [ ] Security audit complete
- [ ] Backups automated

### Week 7: Documentation
- [ ] API docs published
- [ ] Runbook complete
- [ ] Performance benchmarks

### Week 8: Launch
- [ ] Soft launch successful
- [ ] Monitoring operational
- [ ] Production launch

---

## Estimated Total Time

| Phase | Duration |
|-------|----------|
| 0. Immediate Blockers | 1 day |
| 1. Infrastructure | 1 week |
| 2. Observability | 1 week |
| 3. Testing | 1 week |
| 4-5. Features | 2 weeks |
| 6. Hardening | 1 week |
| 7. Documentation | 1 week |
| 8. Launch | 1 week |
| **Total** | **~8 weeks** |

With focused work: **4-6 weeks**
