# Mirai Technical Interview Debrief

**Date:** February 13, 2026 — 1:30 PM AST
**Duration:** 90 minutes
**Format:** On-call technical interview + live system design
**Interviewer:** Ketan Velip (Sr. AI Software Engineer, Scopely/Bangalore)
**Also present:** Hussam Aljabri (Talent Partner)
**Candidate assessment:** Went well overall. Outcome depends on Ketan's evaluation of foundational knowledge depth.

---

## 1. Role Clarification (Confirmed in Interview)

The role is broader than the JD suggests:

| Aspect | What was confirmed |
|--------|-------------------|
| **Team structure** | 8 engineers (2 senior, 6 junior), no current lead |
| **Reporting** | CEO currently handles people management — lead takes this over |
| **Service model** | Platform engineering team serving non-engineering departments (HR, Finance, Acquisitions, Game Studios) |
| **Scope** | Build internal AI tools, replace legacy tools, deliver projects, grow the team |
| **Growth** | Team will expand; this is a foundational leadership hire |
| **Not in the game** | Team does NOT build player-facing features — strictly internal tooling |

### Key Insight: This is a Platform Engineering Lead Role

The title says "Lead Full Stack Engineer — Gen AI Team" but the reality is closer to:
- **60% people management** — team lead, hiring, mentoring, removing CEO from day-to-day management
- **30% technical leadership** — architecture decisions, system design, legacy modernization
- **10% hands-on coding** — primarily guiding and reviewing

---

## 2. Company & Team Context (New Information)

| Detail | Notes |
|--------|-------|
| **Mirai's purpose** | Internal AI tooling group within Scopely/Savvy Games |
| **Users** | Non-engineering teams across Scopely properties |
| **Legacy situation** | Existing tools that need replacement/modernization |
| **Projects** | Multiple active projects from Scopely pipeline |
| **Barcelona connection** | Some team members or operations in Barcelona (Scopely office) |
| **Saudi visa challenges** | Indian team members faced visa difficulties — cultural/logistical awareness important |
| **Distributed team** | Cross-regional (Saudi + Barcelona + Bangalore) team management required |

---

## 3. Technical Assessment: System Design Challenge

### The Problem

Ketan presented a real business problem: **Engineers running out of LLM tokens and using expensive models for simple tasks.** Design a smart LLM gateway/routing middleware that provides cost-effective, unlimited internal access.

### Requirements (from interview)

- **Scale:** 1,000 developers, 3 regions (33% each), 200K requests/hour
- **Infrastructure:** ECS Fargate
- **Models:** Claude Opus, GPT-4o, Haiku, GPT-4o-mini (mixed providers)
- **Core features:** Authentication, team segregation, smart routing, caching, memory/context, audit/security, cost tracking

### Architecture Discussed

```
┌──────────┐    ┌──────────────────────────┐    ┌─────────────────┐
│  Clients  │───>│  LLM Routing Middleware   │───>│  LLM Providers  │
│  (1000    │    │  ├── Auth (API keys/OAuth)│    │  ├── Claude      │
│  devs,    │    │  ├── Team segregation     │    │  ├── OpenAI     │
│  3 regions│    │  ├── Complexity classifier│    │  └── Self-hosted│
│  200K/hr) │    │  ├── Model router         │    └─────────────────┘
└──────────┘    │  ├── Caching (3 layers)   │
                │  ├── Memory/context store  │    ┌─────────────────┐
                │  ├── Audit logging         │───>│  Vector Store    │
                │  └── Cost tracking         │    └─────────────────┘
                └──────────────────────────┘
```

### Key Technical Question: "How do we cache in an LLM decider router?"

Three caching layers:

1. **Exact match cache (Redis):** Hash (prompt + model + params) → cached response. ~15-25% hit rate. 100% cost savings per hit.
2. **Semantic cache (Vector Store):** Embed prompt → find similar past prompts (similarity > 0.95). Additional ~10-20% hit rate. Catches paraphrased duplicates.
3. **Routing decision cache:** Cache the complexity classification itself — "fix unit test" patterns always route to coding model without running the classifier.

### Complexity-Based Routing Logic

| Request pattern | Complexity | Model |
|----------------|-----------|-------|
| "Fix unit test on line 135" | Low | Haiku / GPT-4o-mini |
| "Higher weightage based on plan modes" | Medium | Sonnet / GPT-4o |
| "Design system architecture based on constraints" | High | Opus / GPT-4o |

---

## 4. Diagnostic Prep Session Results (Pre-Interview)

A 42-question diagnostic assessment was conducted across 6 domains:

| Round | Domain | Score | Notes |
|-------|--------|-------|-------|
| 1 | Full Stack Fundamentals | 2/5 | Weak on Node.js event loop internals, Pydantic, TS discriminated unions |
| 2 | System Design & Architecture | 4/5 | Strongest domain — one over-engineering miss (EKS vs ECS) |
| 3 | GenAI & LLM Engineering | 2/5 | RAG failure modes were the main gap (now taught) |
| 4 | Cloud & DevOps | 1/5 | Pattern: consistently over-engineers infrastructure choices |
| 5 | Leadership & Team Management | 3/5 | Good instincts, needs "listen first, prescribe second" |
| 6 | Mirai-Specific Scenarios | 4/5 | Strong product sense, gaming context mapping |
| **Total** | | **16/30** | |

### Strengths Confirmed

- System design and architecture decision-making
- Event-driven architecture (real production experience)
- Product scoping and V1 definition
- Strategic framing (build vs buy, no-gaming-experience reframe)
- Cost estimation and model tiering

### Gaps Identified and Addressed

| Gap | Status | Risk Level |
|-----|--------|------------|
| RAG architecture details | Taught (lost in middle, thresholds, evaluation) | Medium — Ketan's domain |
| Pydantic fundamentals | Taught (BaseModel, FastAPI integration, validators) | High — core to the stack |
| "Simple first" infrastructure instinct | Identified pattern, coached | Medium — lead-level judgment |
| React (no experience, Angular background) | Acknowledged, bridging strategies provided | Low — transferable, learnable |
| Node.js event loop internals | Taught (CPU-bound parsing trap) | Low — unlikely deep dive |

---

## 5. Scripted Answers Prepared

| Topic | Key message |
|-------|-------------|
| **No gaming experience** | Bridge (event-driven at scale) + reframe (AI + leadership) + evidence (Seven.One team) + minimize (gaming is easiest gap) |
| **LangChain weaknesses** | Honest: abstraction depth hurts debugging. Contextual: productivity wins for team with 6 juniors. Build custom only for game-specific orchestration. |
| **RAG failure modes** | Three layers: similarity threshold + faithfulness check + grounding instruction |
| **Differentiator** | Bird's-eye-to-specifics: whiteboard with VP in the morning, pair-program Pydantic with a junior in the afternoon |
| **Questions for Ketan** | AI team ↔ studio interaction / model eval strategy / what should new lead change first |

---

## 6. Interview Outcome Assessment

### Positive Signals

- Interview went well by candidate's assessment
- System design challenge was relevant and candidate could draw on real experience
- Role confirmation matches candidate's strengths (platform engineering + people management + team building)
- The people management angle is a strong fit — Seven.One team leadership experience maps directly

### Risk Factors

- Ketan may probe fundamentals depth (React, Pydantic, Node.js specifics)
- Gaming domain gap — even though internal tools, Ketan may value gaming context
- Visa/cultural dynamics in Saudi — potential logistical friction
- Candidate's tendency to over-engineer may have surfaced in system design discussion

### Probability Assessment

| Outcome | Likelihood | Reasoning |
|---------|-----------|-----------|
| **Advance to next round** | 55-60% | Strong on architecture and leadership, system design was relevant. Risk: fundamentals depth perception. |
| **Receive offer** | 35-40% | Depends on competing candidates and whether they prioritize gaming experience |
| **Rejection** | 40-45% | Most likely reason: perceived gap in foundational full-stack depth or gaming domain |

---

## 7. Follow-Up Actions

| Action | Priority | Deadline |
|--------|----------|----------|
| Send thank-you message to Ketan via LinkedIn | High | Within 24 hours |
| Send thank-you to Hussam (Talent Partner) | High | Within 24 hours |
| Review all 42 diagnostic questions and scripted answers | Medium | Done (pre-interview) |
| Prepare deeper system design write-up for LLM Gateway (in case of follow-up round) | Medium | Within 48 hours |
| Research Scopely Barcelona office and distributed team patterns | Low | Within 1 week |

---

## 8. Key Takeaways for Future Interviews

1. **The "simple first" bias:** Practice choosing Kinesis over Kafka, ECS over EKS, layer caching over Alpine. Lead engineers pick boring, appropriate technology.
2. **RAG is table stakes:** Any AI lead role will probe RAG failure modes. The three failure modes (lost in middle, no threshold, no faithfulness check) must be automatic.
3. **Pydantic is non-negotiable for FastAPI roles:** Treat it like TypeScript interfaces but with runtime validation. Practice writing models cold.
4. **People management is the differentiator:** The CEO wants out of day-to-day management. The leadership stories (Seven.One, Samdock) are more valuable than any technical answer.
5. **Frame gaming gap proactively:** Don't wait to be asked. Mention it early, bridge it, and move to strengths.
