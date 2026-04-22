# Mirai Technical Interview — 5-Hour Prep Plan

**Interview:** Friday, Feb 13, 2026 — 1:30 PM AST (11:30 AM CET)
**Duration:** 90 minutes (1:30 PM - 3:00 PM AST)
**Format:** On-call technical interview + assessment — **LAPTOP REQUIRED, CAMERA ON**
**Call Link:** https://meet.google.com/set-ketm-qaq
**Interviewer:** **Ketan Velip** — Sr. AI Software Engineer @ Scopely (Bangalore)
**Also on call:** Hussam Aljabri (Talent Partner)
**Focus:** Technical experience, problem-solving approach, live technical tasks
**Team:** 8 engineers (2 seniors, 6 juniors) — no current lead
**Company focus:** Internal AI tools for gaming operations, NOT player-facing AI

---

## CRITICAL UPDATE: Interviewer Profile — Ketan Velip

### Who Is Ketan Velip?

| Fact | Detail |
|------|--------|
| **Title** | Sr. AI Software Engineer @ Scopely (promoted Apr 2024) |
| **Location** | Bangalore, India (remote from Mirai's Riyadh HQ) |
| **At Scopely since** | Jan 2022 (~4 years) |
| **Previously** | Senior SWE at GSN Games (Jul 2017 - Jan 2022) — worked on "Bingo Bash" (#2 bingo game) |
| **Earlier career** | Web developer path: WordPress → MEAN stack → game backend |
| **Education** | B.E. Information Technology, Goa Engineering College (2010-2014) |
| **Certifications** | Executive PG in AI & ML (IIT Roorkee 2025), NVIDIA Deep Learning Fundamentals (2024), AWS SA Associate |
| **GitHub** | github.com/ketanvelip — 20 repos, active in AI/gaming projects |

### His Tech Stack (from GitHub)

| Category | Technologies |
|----------|-------------|
| **AI/ML** | Python, LangChain, OpenAI, Stable Diffusion, TensorFlow, LoRA |
| **Backend** | FastAPI, Node.js, PHP, REST APIs, WebSockets |
| **Frontend** | React, TypeScript, JavaScript, AngularJS |
| **Cloud** | AWS, GCP, Docker, Linux |
| **Databases** | MySQL, MongoDB, BigQuery, Firestore |

### His Focus at Scopely

From his GitHub bio: *"I architect and ship AI-driven systems for game operations and internal tooling, working on gaming platforms that serve millions of players worldwide."*

His current focus areas:
1. **GenAI Platform Engineering** — integrating GenAI into game ops, automation, analytics, content generation
2. **Full-Stack AI Solutions** — end-to-end systems connecting model pipelines → APIs → interactive UIs
3. **Production ML** — scalable, production-ready AI with guardrails and observability
4. **Technical Leadership** — mentoring engineers, defining AI strategy

### His Notable Projects (GitHub)

| Project | What It Is | Relevance |
|---------|-----------|-----------|
| **entropy-realms** | Survival game on AWS EKS (distributed microservices) | He values system design + gaming |
| **neurojam** | React + Vite rhythm game with Gemini API (real-time AI code gen) | GenAI + gaming + React/TypeScript |
| **poker_rl_agent** | RL agent that learns poker | ML depth beyond just LLMs |
| **resume-screening-ml-pipeline** | NLP pipeline with FastAPI endpoint | He built something similar to YOUR project |
| **neural-network-from-scratch** | Neural net in pure NumPy | Understands ML fundamentals |
| **openai_assistants_cli_chatbot** | OpenAI Assistants API chatbot | Familiar with agent patterns |
| **dependency-hell-visualizer** (Feb 2026) | TypeScript project | Actively building |
| **roast-my-code** (Feb 2026) | Python project | Actively building |

### What This Means for Your Interview

1. **He's a PEER, not a manager.** Ketan is a Senior AI Software Engineer — same level, not above you. He's evaluating whether you'd be a good **lead** for the team he's on. This changes the dynamic — you need his technical respect AND he needs to feel you'd elevate the team.

2. **He's deeply technical in AI.** IIT Roorkee PG in AI/ML, NVIDIA cert, LangChain experience, RL agents, neural nets from scratch. **He will probe your AI depth.** Your LangGraph pipeline knowledge must be rock-solid.

3. **He knows FastAPI + MongoDB + React/TypeScript.** Your stack overlap is excellent. He'll evaluate fluency, not just awareness.

4. **He built a resume-screening ML pipeline.** This is remarkably similar to your job-search pipeline. He'll understand and appreciate your project — but he'll also know enough to ask hard follow-up questions.

5. **He's from GSN Games (casino/bingo games).** He has deep gaming backend experience. Expect gaming-specific questions about scale, live-ops, real-time systems.

6. **He posts about LoRA and Stable Diffusion.** He's interested in fine-tuning and image generation — be ready for questions beyond just LLM/RAG.

7. **"On-Call Technical Interview on a Laptop"** = **expect live coding.** Given his GitHub activity, he values people who can actually build, not just talk architecture. Have your IDE ready.

### How to Connect with Ketan

- **Mention your resume pipeline** — his `resume-screening-ml-pipeline` project is a direct parallel. *"I noticed a similar approach in my own project..."* (only if natural)
- **Show production AI depth** — he's building "production-ready AI with guardrails and observability" — speak his language
- **Respect his gaming experience** — he's been in gaming since 2017 (GSN → Scopely). Acknowledge the domain expertise
- **Be a collaborative lead** — he's a senior on the team. Show you'd lead WITH people like him, not OVER them

---

## Interview Format Analysis

**90-minute technical interview with LAPTOP REQUIRED** — this is NOT a pure conversation. Expect hands-on work.

Based on Scopely Glassdoor reviews (154+ interviews) and the calendar invite details, the likely 90-minute structure:

| Segment | Duration | What Happens |
|---------|----------|-------------|
| **Warm-up & experience** | 15-20 min | "Tell me about yourself," walk through past projects, architecture decisions |
| **Live coding assessment** | 40-50 min | Screen-share your IDE, solve a problem or build something. **THIS IS THE CORE.** |
| **System design / architecture Q&A** | 10-15 min | Discuss trade-offs, scaling, or review your code's architecture |
| **Your questions** | 5-10 min | Always have 2-3 ready |

**Scopely-specific patterns:**
- Frequently asks about SOLID principles, concurrency, system design trade-offs
- Take-home assessments are common (build a simple game/app, log design decisions)
- For Lead roles: expect more system design than LeetCode
- "Assessment" may mean a take-home sent AFTER this call — but the laptop requirement suggests live work

**CRITICAL: Pre-Interview Setup (30 min before the call)**
1. Open VS Code with a **Python project** (FastAPI hello world) AND a **TypeScript project** (Node.js or React)
2. Terminal ready with `python`, `node`, `npm/npx` working
3. Have a browser tab with Google Meet link ready
4. Close all notifications, messaging apps, browser distractions
5. Test screen sharing in Google Meet BEFORE the call
6. Good lighting on your face, clean background, camera at eye level
7. Water bottle within reach, notepad for writing down questions

---

## Schedule Overview

| Time Block | Duration | Topic | Priority |
|------------|----------|-------|----------|
| **Hour 1** | 60 min | Technical Storytelling — STAR narratives | CRITICAL |
| **Hour 2** | 60 min | System Design — GenAI Platform for Gaming | CRITICAL |
| **Hour 3** | 60 min | System Design — Gaming-Specific Problems | HIGH |
| **Hour 4** | 60 min | Technical Fundamentals + Live Coding Warm-Up | HIGH |
| **Hour 5** | 60 min | GenAI Deep Dive + Mock Run | CRITICAL |

---

## HOUR 1: Technical Storytelling (CRITICAL)

**Goal:** Prepare 4 polished narratives. Rehearse each in both 3-minute and 90-second versions.

### Story 1: "The Platform Transformation" (Seven.One) — YOUR LEAD STORY

**Use when:** "Tell me about yourself," "Describe a system you designed," "How do you handle complexity"

> **Situation:** Inherited a 2015-era monolithic AdTech platform serving millions of daily impressions for Germany's largest broadcaster. Callback hell, mixed-criticality endpoints, frontend-orchestrated async workflows, no observability.
>
> **Task:** Modernize while maintaining 100% uptime for revenue-critical ad delivery.
>
> **Action:** Diagnosed problems across 5 interconnected dimensions — code, architecture, infrastructure, process, and cost. Didn't just fix code; moved responsibilities to the right layer:
> - Caching: Redis (app-level) → CloudFront (infrastructure)
> - Orchestration: Frontend-driven → EventBridge choreography
> - Observability: Scattered logs → OpenSearch pipeline processing billions of events
> - Introduced "Architectural Runway" — parallel modernization + feature delivery
>
> **Result:** 75% incident reduction. >99.9% availability over 3 years. Cost reduction across 6 dimensions. 70% system modernization while maintaining continuous delivery.

**Differentiator to land:** *"I don't just see code problems — I see how code, architecture, infrastructure, process, and cost are interconnected. That's what lets me transform systems, not just patch them."*

---

### Story 2: "The 0→1 Product" (Samdock) — FOR STARTUP/BUILDING QUESTIONS

**Use when:** "Have you built something from scratch?" "How do you make technical decisions early?"

> **S:** Early-stage CRM startup. Zero codebase, 4-person team.
> **T:** Architect and ship a multi-tenant SaaS platform under startup constraints.
> **A:** Chose event sourcing/CQRS with NestJS/TypeScript. Ran event storming workshops. Built component library, CI/CD pipeline, 85% test coverage.
> **R:** 25 production tenants. Sprint velocity improved 30%. Shipped on time.

**Differentiator:** *"I know how to make architecture decisions under uncertainty — commit to the right abstractions early, defer the ones that can wait."*

---

### Story 3: "The AI Pipeline" (Portfolio Project) — YOUR DIFFERENTIATOR

**Use when:** "What's your experience with AI/ML?" "How do you integrate LLMs into production?"

> **S:** Wanted to go beyond theory — demonstrate production-grade agentic AI capability.
> **T:** Build a multi-layer LangGraph pipeline that processes job postings into hyper-personalized outputs.
> **A:** Designed 7-layer orchestration:
> 1. JD Processing (structured extraction with LLM)
> 2. Pain Point Mining (context-aware analysis)
> 3. Company/Role Research (FireCrawl + RAG)
> 4. Opportunity Mapping (matching algorithm)
> 5. CV Generation (multi-pass with quality gates)
> 6. Evaluation harness (80+ test scenarios, hallucination detection)
> 7. Structured outputs with 5-dimension quality gates
>
> Stack: LangGraph, FastAPI, MongoDB, LangSmith. Production controls: typed tool contracts, retries/timeouts, trace IDs, cost tracking.
>
> **R:** 1700+ tests passing. Working system processing real data. Quality gates catch hallucinations before output.

**Frame it as:** *"I built this because the best way to understand production AI systems is to build one. The patterns — layered orchestration, evaluation harnesses, quality gates, observability — are the same patterns you need for any production GenAI system."*

**DO NOT frame as:** "I have a side project playing with AI."

---

### Story 4: "The Team Builder" — FOR LEADERSHIP QUESTIONS

**Use when:** "How do you mentor?" "How do you lead a team?"

> **S:** Seven.One engineering team needed to grow, level up, and own architectural decisions.
> **T:** Build a high-performing team while delivering platform modernization.
> **A:** Three pillars:
> 1. **Collaborative design sessions** — facilitated with Miro, guided with questions not answers
> 2. **Stretch assignments with safety net** — slightly beyond current level, paired when stuck
> 3. **"Lean Friday" innovation program** — one Friday per sprint for technical exploration
> Plus: Introduced DDD standards, blameless postmortems, code reviews as teaching moments.
>
> **R:** Promoted 3 engineers to lead roles. Reduced onboarding from 6 to 3 months. Team velocity improved 25%.

**For Mirai specifically:** *"Your team is 2 seniors and 6 juniors. That's actually my sweet spot — I know how to set architectural direction, establish standards, and grow people. Within 6 months, I'd expect those juniors to be operating at a significantly higher level."*

---

### Practice Drill (15 min)

1. Set a timer for 3 minutes → tell Story 1 out loud
2. Set a timer for 90 seconds → compress Story 1
3. Repeat for Story 3 (your AI differentiator)
4. Practice the opening pitch (30 seconds):

> *"I'm a technical lead with 11+ years experience. Currently at Seven.One Entertainment in Munich leading 10+ engineers building high-scale platforms on AWS — billions of events daily. I combine hands-on architecture with team leadership, and I'm actively building in GenAI with a 7-layer LangGraph pipeline. The intersection of full-stack engineering and AI in gaming is exactly where I want to be."*

---

## HOUR 2: System Design — GenAI Platform for Gaming (CRITICAL)

**Goal:** Be able to whiteboard this end-to-end in 30 minutes. This is the MOST LIKELY system design question.

### The Question

*"Design an AI-powered internal platform for a gaming company that helps operations teams analyze player data, generate reports, and automate decisions."*

This maps directly to the JD: *"enhancing productivity, automation, and data-driven decision-making within internal operations and enterprise platforms."*

### Step 1: Clarify Requirements (2 min)

Ask these questions (shows maturity):
- "How many internal users? Dozens or hundreds?"
- "What data sources? Player events, game configs, support tickets?"
- "Latency requirements? Real-time dashboards or async reports?"
- "What security constraints? Who can access player data?"

Assume: ~100 internal users, multiple game titles, player event streams (Kafka), game configs (MongoDB), support tickets (PostgreSQL).

### Step 2: High-Level Architecture (5 min)

```
┌─────────────────────────────────────────────────────────┐
│                    React + TypeScript Frontend            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │
│  │Dashboard │ │ Report   │ │ Chat     │ │ Admin      │ │
│  │(D3/Plotly│ │Generator │ │Interface │ │ Panel      │ │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + WebSocket (SSE for streaming)
┌──────────────────────┴──────────────────────────────────┐
│                  API Gateway (Node.js/Express)            │
│  Auth (JWT) │ Rate Limiting │ Request Routing             │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│ Analytics    │ │ LLM      │ │ Data         │
│ Service      │ │ Orchestr.│ │ Pipeline     │
│ (FastAPI)    │ │ (FastAPI) │ │ Service      │
└──────┬───────┘ └────┬─────┘ └──────┬───────┘
       │              │              │
       ▼              ▼              ▼
┌──────────────────────────────────────────────┐
│              Shared Data Layer                 │
│ MongoDB    │ PostgreSQL │ Redis  │ Vector DB  │
│ (game data)│ (analytics)│ (cache)│ (embeddings│
└──────────────────────────────────────────────┘
```

### Step 3: LLM Orchestration Layer — The Core (10 min)

```
User Query
    │
    ▼
┌─────────────────┐
│ Intent Classifier│ ← Cheap model (Haiku/GPT-4o-mini)
│ "What type of    │   Classify: report | analysis | chat | action
│  request?"       │
└────────┬────────┘
         │
    ┌────┴─────────────────────────┐
    ▼                              ▼
┌───────────┐              ┌───────────────┐
│ Simple Q&A│              │ Complex Task  │
│ (cached   │              │ (orchestrated)│
│  response)│              │               │
└───────────┘              └───────┬───────┘
                                   │
                           ┌───────┴───────┐
                           ▼               ▼
                    ┌────────────┐  ┌────────────┐
                    │ RAG Path   │  │ Agent Path │
                    │ (retrieve  │  │ (multi-step│
                    │  + answer) │  │  reasoning)│
                    └─────┬──────┘  └─────┬──────┘
                          │               │
                          ▼               ▼
                    ┌─────────────────────────┐
                    │  Output Post-Processor   │
                    │  - Format validation     │
                    │  - PII detection         │
                    │  - Hallucination check   │
                    │  - Cost logging          │
                    └─────────────────────────┘
```

**Key design decisions to explain:**

| Decision | Choice | Why |
|----------|--------|-----|
| **Model routing** | Tiered: Haiku for classification, Sonnet for RAG, Opus for complex reasoning | Cost control — 90% of queries can use cheap models |
| **RAG vs fine-tuning** | RAG for game docs/knowledge | Data changes frequently (game updates), fine-tuning too slow |
| **Streaming** | SSE for LLM responses | Users see output appearing — much better UX for reports |
| **Caching** | Redis for common queries (TTL: 1hr for data, 24hr for docs) | 60%+ of internal queries are repeated patterns |
| **Vector DB** | pgvector (PostgreSQL extension) | Already have PostgreSQL; simpler ops than standalone vector DB |
| **Safety** | Output filter + prompt injection detection | Internal tool, but still need PII protection for player data |

### Step 4: Key Components to Discuss (5 min)

**Prompt Registry (version-controlled):**
- Templates stored in MongoDB with version history
- Game designers can update report templates without code deploys
- A/B testing: try different prompt versions, measure quality scores

**Evaluation Harness:**
- Every LLM output gets a quality score (0-1)
- Automated checks: factual grounding against source data, format compliance
- Low-confidence outputs flagged for human review
- Weekly quality reports to track drift

**Cost Management:**
- Per-request cost attribution (model + tokens + retrieval)
- Budget limits per team/feature
- Dashboard showing daily/weekly LLM spend
- Alert when cost exceeds threshold

### Step 5: Tie to Your Experience (2 min)

> *"This architecture maps directly to what I've built:*
> - *My LangGraph pipeline uses the same layered orchestration pattern*
> - *I have evaluation harnesses with hallucination detection across 80+ scenarios*
> - *The RAG pipeline with MongoDB vector search is production-tested*
> - *At Seven.One, I built event-driven pipelines processing billions of events — same scale patterns*
> - *The observability layer mirrors the OpenSearch pipeline I designed"*

### Local Resource

Review: `~/pers/projects/tools/system-design-academy/` — especially the real-time gaming leaderboard and data visualization case studies.

---

## HOUR 3: System Design — Gaming-Specific Problems (HIGH)

**Goal:** Speed-run 4 system designs at 15 minutes each. You don't need to go deep — you need to show you can reason about gaming-scale problems.

### Design 1: Real-Time Game Analytics Dashboard (15 min)

**The question:** *"Design a real-time dashboard showing player metrics across multiple game titles."*

```
Game Servers → Kafka → Stream Processor → Time-Series DB → FastAPI → React + D3.js
                              │                                         │
                              ▼                                    WebSocket
                     Aggregation Service                         (live updates)
                     (1s, 1m, 1hr windows)
```

**Key points:**
- **Kafka** for event ingestion (millions of player events/sec)
- **Stream processing** (Flink or Kinesis Data Analytics) for real-time aggregations
- **Time-series DB** (TimescaleDB or InfluxDB) for metric storage
- **WebSocket** for pushing live updates to dashboard
- **React + D3.js/Plotly** for visualization (JD mentions these explicitly)
- **Redis** for caching pre-computed aggregations (last 5 min, last hour)

**Tie to experience:** *"At Seven.One, I built an observability pipeline processing billions of events daily with OpenSearch. Same pattern — ingest at scale, aggregate in real time, visualize."*

### Design 2: AI-Powered Content Generation Pipeline (15 min)

**The question:** *"Design a system that generates NPC dialogue, quest descriptions, or marketing copy for game teams."*

```
Content Request → Prompt Builder → LLM Router → Generation → Quality Gate → Human Review → Publish
                       │                                          │
                  Template DB                              Style Checker
                  (per-game,                              (tone, length,
                   per-NPC)                                brand voice)
```

**Key points:**
- **Prompt templates** per game, per content type, per locale (version-controlled)
- **Style consistency** — embedding-based similarity check against approved examples
- **Batch generation** for bulk content (async queue) vs on-demand (sync API)
- **Human-in-the-loop** — reviewers approve before content goes live
- **Cost estimation** — predict token costs before batch runs
- **Hallucination prevention** — content grounded in game lore database (RAG)

### Design 3: Real-Time Leaderboard System (15 min)

**The question:** *"Design a global leaderboard for a mobile game with millions of daily players."*

```
Game Event → Kafka → Score Processor → Redis Sorted Set → API → Client
                                            │
                                    Regional Sharding
                                    (NA, EU, MENA, APAC)
```

**Key points:**
- **Redis Sorted Sets** — O(log N) for insert and rank queries
- **Sharding** by region for latency, with global aggregation
- **Near-real-time** — eventual consistency acceptable (1-5 sec delay)
- **Pagination** — top 100 cached, deeper queries hit DB
- **Anti-cheat** — score validation before insertion

**Reference:** `~/pers/projects/tools/system-design-academy/` → Real-Time Gaming Leaderboard case study

### Design 4: RAG-Based Internal Knowledge System (15 min)

**The question:** *"Design an internal chatbot that answers questions about game documentation, runbooks, and player support history."*

```
User Question → Embedding → Vector Search → Re-ranking → Prompt Assembly → LLM → Response
                    │              │
               Same model as   pgvector or
               ingestion       MongoDB Atlas Search
```

**Key points:**
- **Chunking strategy** — 500-token chunks with 100-token overlap for docs; whole entries for FAQs
- **Hybrid search** — BM25 keyword + dense vector (semantic) for best recall
- **Re-ranking** — cross-encoder re-ranker on top-20 results before sending to LLM
- **Source attribution** — always cite which document/page the answer came from
- **Feedback loop** — thumbs up/down to improve retrieval quality over time

**Tie to experience:** *"My LangGraph pipeline has a RAG subsystem with exactly this pattern — ingestion, chunking, embeddings, vector search, evaluation harness for retrieval quality."*

---

## HOUR 4: Technical Fundamentals Speed Review (HIGH)

**Goal:** Refresh the JD-specific technologies. Don't deep-study — just make sure you can speak confidently.

### 4.1 SOLID Principles (10 min) — Scopely asks this frequently

| Principle | One-Liner | Your Example |
|-----------|-----------|-------------|
| **S**ingle Responsibility | One class, one reason to change | "Each microservice at Seven.One owns one domain" |
| **O**pen/Closed | Open for extension, closed for modification | "EventBridge handlers — add new subscribers without changing publishers" |
| **L**iskov Substitution | Subtypes must be substitutable | "LLM provider interface — swap Claude for GPT without changing orchestration" |
| **I**nterface Segregation | Many specific interfaces > one general | "Typed tool contracts in LangGraph — each tool has its own schema" |
| **D**ependency Inversion | Depend on abstractions, not concretions | "Repository pattern in FastAPI — services depend on abstract repo, not MongoDB directly" |

### 4.2 Concurrency (10 min) — Scopely asks this

**Node.js:**
- Single-threaded event loop + libuv thread pool for I/O
- `async/await` for non-blocking I/O
- Worker threads for CPU-intensive work
- *When to use:* API gateways, real-time WebSocket servers, I/O-heavy services

**Python/FastAPI:**
- `asyncio` event loop with `async/await`
- `motor` for async MongoDB, `httpx` for async HTTP
- `concurrent.futures` / multiprocessing for CPU-bound work
- GIL limitation — use multiprocessing for true parallelism
- *When to use:* AI/ML services, data processing, RAG pipelines

**When to use which:**
> *"Node.js for the API gateway and real-time features — its event loop excels at high-concurrency I/O. Python/FastAPI for AI orchestration and data processing — richer ML ecosystem, native LangGraph/LangChain support."*

### 4.3 Database Selection (10 min)

| Database | When to Use | Gaming Example |
|----------|-------------|---------------|
| **MongoDB** | Flexible schema, document-oriented, rapid iteration | Player profiles, game configs, AI prompt templates, content catalogs |
| **PostgreSQL** | ACID transactions, complex queries, relational data | In-app purchases, user auth, analytics aggregations, leaderboards |
| **Redis** | Sub-millisecond reads, ephemeral data, pub/sub | Session state, real-time leaderboards, LLM response cache, rate limiting |

**Key trade-off to articulate:** *"MongoDB for flexibility and developer velocity — perfect for a GenAI team where schemas evolve fast. PostgreSQL where you need ACID guarantees. Redis where you need speed."*

### 4.4 Docker/Kubernetes (10 min)

Be ready to discuss:
- **Docker:** Multi-stage builds (minimize image size), health checks, env var configuration
- **Kubernetes:** Horizontal pod autoscaling (HPA), rolling deployments, readiness/liveness probes
- **CI/CD:** GitHub Actions → build → test → deploy to K8s
- **Zero-downtime deployments:** Rolling updates, blue/green, canary

> *"At Seven.One, I drove the migration from Jenkins to GitLab CI, reducing release cycles from weeks to days. For a GenAI platform, I'd add model validation gates and cost estimation checks in the CI pipeline."*

### 4.5 Live Coding Warm-Up (15 min) — CRITICAL FOR 90-MIN FORMAT

**Do these in your IDE, not just in your head:**

**Exercise 1: FastAPI + LLM endpoint (Python, 10 min)**
```python
# Build this from scratch without looking:
# POST /api/chat that accepts {"message": str}, calls an LLM, returns {"response": str}
# Include: Pydantic model, error handling, streaming support
```

**Exercise 2: React streaming component (TypeScript, 5 min)**
```typescript
// Build a component that:
// - Sends a message to /api/chat
// - Displays the response as it streams in (SSE)
// - Has a loading state and error state
```

**Why this matters:** Ketan will watch you code. The first 2 minutes of live coding determine his impression. If you fumble with imports or basic FastAPI setup, it signals "talks architecture but can't execute." These warm-ups ensure your muscle memory is primed.

### 4.6 React + TypeScript (10 min)

Key patterns to mention:
- **Custom hooks** for data fetching and WebSocket connections
- **TypeScript generics** for reusable components
- **State management:** Context API for simple state, Zustand for complex (lighter than Redux)
- **SSE/WebSocket** for streaming LLM responses
- **Component architecture:** Atomic design pattern for building a component library

### 4.7 AWS Services (10 min)

| Service | Your Experience | Gaming/AI Use |
|---------|----------------|---------------|
| **Lambda** | Serverless functions at Seven.One | Event-triggered AI processing |
| **ECS/Fargate** | Container orchestration | Long-running AI services |
| **EventBridge** | Event bus choreography | Async pipeline orchestration |
| **SQS** | Message queuing | LLM request queue (burst handling) |
| **Kinesis** | Real-time streaming | Player event ingestion |
| **S3** | Object storage | Model artifacts, generated content |
| **CloudFront** | CDN caching | Static assets, cached API responses |
| **SageMaker** | ML model serving | (Know it exists; mention if they ask about GCP alternatives) |

---

## HOUR 5: GenAI Deep Dive + Mock Run (CRITICAL)

### 5.1 GenAI Concepts Speed Review (20 min)

**RAG Architecture (be able to draw this):**
```
Documents → Chunking → Embedding → Vector Store → Retrieval → Re-ranking → Prompt Assembly → LLM → Output
```

**Key decisions to explain:**
- Chunking: 500-1000 tokens, overlap 10-20%, respect document boundaries
- Embedding: text-embedding-3-large (OpenAI) or all-MiniLM-L6-v2 (open source)
- Vector store: pgvector (simple), Pinecone (managed), FAISS (local)
- Hybrid search: BM25 + dense vectors for best recall
- Re-ranking: cross-encoder model on top-20 candidates

**Agentic AI Patterns (know the top 5):**

| Pattern | What It Does | When to Use |
|---------|-------------|-------------|
| **ReAct** | Reason + Act loop | General agent tasks (your LangGraph pipeline uses this) |
| **Tool Use** | LLM calls external APIs | Data fetching, calculations, integrations |
| **Planning** | Decompose complex tasks | Multi-step workflows (report generation) |
| **Reflection** | Self-critique and refine | Quality improvement, iterative content |
| **Multi-Agent** | Multiple specialized agents | Complex systems (researcher + writer + reviewer) |

**Reference:** `~/pers/projects/tools/all-agentic-architectures/` — 17 implementations with notebooks

**Hallucination Prevention (your quality gates):**
1. Grounding checks — compare output against source material
2. Structural validation — output matches expected schema
3. Confidence scoring — low confidence → human review
4. Source attribution — cite where information came from
5. Eval harness — automated testing across scenarios

**Cost Management:**
- Token math: `users × queries/day × (input + output tokens) × price/1K tokens`
- Example: 100 users × 20 queries × 2000 tokens × $0.003/1K = $12/day
- Strategies: caching (Redis), model tiering, prompt optimization, batch processing

**LLM Key Numbers (quick reference):**

| Metric | Value |
|--------|-------|
| GPT-4o context | 128K tokens |
| Claude 3.5 Sonnet context | 200K tokens |
| Typical RAG chunk | 500-1000 tokens |
| Typical embedding dimension | 768-1536 |
| Acceptable RAG latency | <3 seconds |
| Cost: GPT-4o | ~$2.50/1M input, $10/1M output |
| Cost: Claude Sonnet | ~$3/1M input, $15/1M output |
| Cost: GPT-4o-mini | ~$0.15/1M input, $0.60/1M output |

### 5.2 Questions to Ask Them (10 min — pick 3)

**Technical depth questions (impress the interviewer):**

1. **"What types of AI-powered products has the GenAI team shipped so far, and what's the current architecture?"**
   — Shows you want to understand their maturity level and build on existing work

2. **"How does the team handle evaluation and quality assurance for GenAI outputs at scale?"**
   — Shows you think about production quality, not just demos

3. **"How does Mirai's engineering org relate to Scopely's? Shared infrastructure, shared standards, or independent?"**
   — Shows you understand corporate dynamics and want to leverage existing assets

4. **"What's the biggest technical challenge the team is facing right now?"**
   — Positions you as a problem-solver; their answer tells you what they really need

5. **"What does success look like for this role in the first 90 days?"**
   — Shows you're already thinking about delivery and impact

### 5.3 Full Mock Run (30 min)

Do this timed, out loud. Simulate the actual **90-minute** interview:

**[0:00-0:03] Opening pitch** (30 seconds)
> Practice your elevator pitch. Be warm, not robotic. Connect with Ketan — he's a peer, not a gatekeeper.

**[0:03-0:15] "Walk me through a complex system you built"**
> Tell Story 1 (Seven.One) in 3 minutes. Then expect follow-up questions:
> - "Why EventBridge over SQS?" → "Choreography pattern — services publish events without knowing subscribers. SQS is point-to-point; EventBridge enables fan-out and flexible routing."
> - "How did you handle the migration with zero downtime?" → "Strangler fig pattern — new services alongside old, gradual traffic shift, feature flags for rollback."
> - "What would you do differently?" → "I'd invest in contract testing earlier. We caught some inter-service schema issues in staging that contract tests would have caught in CI."

**[0:15-0:20] "What's your experience with AI/GenAI?"**
> Tell Story 3 (LangGraph pipeline) in 90 seconds. Then expect:
> - "How do you handle hallucinations?" → Walk through your 5 quality gates
> - "What models do you use?" → "Claude for complex reasoning, GPT-4o-mini for classification and simple tasks. Model routing based on task complexity."
> - "Is this in production?" → "It's a reference system demonstrating production patterns. What IS in production is 5 years of high-scale consumer platforms at Seven.One."
> - **Ketan connection:** If natural, mention evaluation harness — he built a `resume-screening-ml-pipeline` and will appreciate the ML pipeline thinking.

**[0:20-1:05] Live Coding Assessment — THE MAIN EVENT (45 min)**
> This is why the laptop is required. Expect ONE of these formats:
>
> **Format A: "Build a small feature/API"** (most likely for a Lead role)
> - Could be: "Build a FastAPI endpoint that takes user input, calls an LLM, and returns a structured response"
> - Could be: "Build a React component that displays streaming LLM output"
> - Show: types-first approach, error handling, tests awareness
>
> **Format B: "Debug/refactor existing code"**
> - They give you a codebase, you fix issues or improve it
> - Show: systematic debugging, read before writing, explain trade-offs
>
> **Format C: "System design with code"**
> - Design an architecture and implement a key piece
> - Show: start with interface, build incrementally, test as you go
>
> **UNIVERSAL LIVE CODING RULES:**
> 1. **Think out loud** — narrate your approach. Silence = lost points.
> 2. **Start with types/interfaces** before implementation — shows production thinking
> 3. **Ask clarifying questions** — "Should I optimize for readability or performance?" "Can I use external libraries?"
> 4. **Handle edge cases** — null checks, empty inputs, error states
> 5. **If stuck, say so** — "I'm considering two approaches... let me think about the trade-offs"
> 6. **Don't over-engineer** — simple working code > clever incomplete code
> 7. **Test your code** — run it, show it works, handle a failing case

**[1:05-1:20] System Design / Architecture Discussion (15 min)**
> If they ask you to design something, use the GenAI Platform from Hour 2. Walk through:
> 1. Requirements clarification (2 min)
> 2. High-level architecture (3 min)
> 3. LLM orchestration layer (5 min)
> 4. Key decisions — model routing, caching, safety (3 min)
> 5. Tie to your experience (2 min)

**[1:20-1:30] Your Questions**
> Pick 2-3 from Section 5.2. End with energy: *"This is exactly the kind of challenge I'm looking for."*

---

## Critical Reminders — Print This

### Lead Role Framing
Every answer should show BOTH sides:
- ❌ "I built the system" → ✅ "I designed the architecture AND mentored the team through implementation"
- ❌ Pure coding answer → ✅ "Here's the technical solution, and here's how I'd decompose this for a team of 8"

### Mirai-Specific Context
- **Internal tools, not player-facing AI** — Frame answers around enterprise productivity
- **8 engineers, mostly junior** — They need an architect-teacher, show you can grow people
- **Scopely parent** — Expect mature engineering standards, data-driven culture
- **Gaming industry** — Show respect for the domain, mention their games (MONOPOLY GO!, Stumble Guys)

### The "No Gaming Experience" Reframe
> *"My 5 years at Seven.One are in the entertainment industry — millions of users, real-time delivery, data-driven optimization, live operations. The patterns translate directly to gaming."*

### Things NOT to Say
- ❌ "I've never worked in gaming" → ✅ "I come from entertainment — parallel patterns"
- ❌ "My AI project is a side project" → ✅ "I built a production-grade reference system"
- ❌ "I'm interested because of the tax benefits" → ✅ "Vision 2030 and the gaming investment"
- ❌ Technical-only answers → ✅ Always connect to team impact and business outcomes

### Energy and Presence
- Camera on, good lighting, clean background
- Show genuine enthusiasm for gaming + AI
- Be warm in the first 2 minutes — don't rush to business
- Use "we" language: "I'd love to build this with the team"
- End strong: "I'm very excited about this opportunity"

---

## Local Study Resources

| Resource | Path | Use For |
|----------|------|---------|
| **System Design Academy** | `~/pers/projects/tools/system-design-academy/` | Gaming leaderboard, data viz case studies, distributed systems |
| **All Agentic Architectures** | `~/pers/projects/tools/all-agentic-architectures/` | 17 agentic patterns — review ReAct, Tool Use, Planning, Multi-Agent |
| **Agentic AI Courses** | `~/pers/projects/certifications/agentic-ai/courses/` | LangGraph, RAG, evaluation, multi-agent |
| **Interview Prep Checklist** | `~/pers/projects/certifications/architect/02-interview-prep-checklist.md` | Practice questions, system design framework |
| **Value Positioning Guide** | `~/pers/projects/certifications/architect/03-value-positioning-guide.md` | How to frame experience, skill transfer matrix |
| **Tech Interview Handbook** | `~/pers/projects/tools/tech-interview-handbook/` | Behavioral prep, coding fundamentals |
| **Differentiators** | `~/pers/projects/job-search/docs/differentiators.md` | Your unique "bird's-eye-to-specifics" differentiator |

---

## Post-Interview

After the interview, immediately:
1. Write down every question they asked (for future rounds)
2. Note the interviewer's name and role
3. Note any take-home assessment details
4. Send a brief thank-you email within 2 hours
5. Update the interview prep report with debrief notes

---

*Prep plan generated 2026-02-12. Interview: Friday, Feb 13, 2026, 1:30 PM AST / 11:30 AM CET.*
