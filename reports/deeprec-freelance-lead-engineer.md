# Freelance Lead Engineer — Deeprec.ai / Trinnovo Group

**Date:** 2026-02-20
**Recruiter:** Samuel Oliver (AI Contract Lead - DACH)
**Source:** LinkedIn direct outreach
**Call:** Scheduled today

---

## 1. Company Intelligence

### Trinnovo Group
- Global recruitment & consultancy, HQ in London
- Certified **B Corp** — committed to transparency, sustainability, accountability
- Fully licensed: UK, Ireland, **Switzerland (SECO)**, **Germany (AUG)**, North America
- Member of **Swiss Staffing Association** & **APSCo Deutschland**
- Three recruitment brands under the group umbrella

### DeepRec.ai (Trinnovo Group brand)
- Specialized **deep tech recruitment**: AI, ML, Robotics, NLP, Blockchain, GenAI
- Covers: Computer Vision, NLP, GenAI, Machine Learning, Research, Embedded Engineering
- Markets: UK, Ireland, Germany, Switzerland, United States
- They are the **staffing agency**, not the end client — the actual employer/client is undisclosed

**Key takeaway:** DeepRec.ai is a reputable, licensed recruiter. The end client identity is unknown — **ask Samuel who the client is** during the call.

Sources:
- [Trinnovo Group](https://www.trinnovogroup.com/)
- [DeepRec.ai](https://www.deeprec.ai/)
- [Trinnovo DeepRec.ai](https://www.trinnovogroup.com/disciplines/deeprec-dot-ai)

---

## 2. Hourly Rate Research

### Germany/DACH Freelance Market (2025-2026)

| Category | Hourly Rate Range | Source |
|----------|------------------|--------|
| All-sector Germany mean | €104/hr (2026) | [freelancermap](https://www.freelancermap.com/blog/freelance-market-study-germany/) |
| DACH average | €94.28/hr | [freelancermap](https://www.freelancermap.com/blog/freelance-market-study-germany/) |
| AI/ML specialist premium | +40-60% above generalist | [index.dev](https://www.index.dev/blog/freelance-developer-rates-by-country) |
| Senior AI/ML freelance (5-10yr) | $120-200/hr (€110-185/hr) | [index.dev](https://www.index.dev/blog/freelance-developer-rates-by-country) |
| LLM specialist premium | +15-30% over traditional ML | [index.dev](https://www.index.dev/blog/llm-developer-hourly-rates) |
| LLM development specialists | $150-250/hr (€140-230/hr) | [index.dev](https://www.index.dev/blog/llm-developer-hourly-rates) |
| Staff/Principal (10+ yr) | $200-300+/hr | [various](https://www.index.dev/blog/freelance-developer-rates-by-country) |

### LLM Engineer Salaries (permanent, for context)

| Role | Annual Salary (US) | Source |
|------|-------------------|--------|
| LLM Engineer (avg) | $156,329 | [Glassdoor](https://www.glassdoor.com/Salaries/llm-engineer-salary-SRCH_KO0,12.htm) |
| LLM Engineer (75th pctl) | $203,139 | [Glassdoor](https://www.glassdoor.com/Salaries/llm-engineer-salary-SRCH_KO0,12.htm) |
| Contract ML Engineer | $128,769 | [ZipRecruiter](https://www.ziprecruiter.com/Salaries/Contract-Machine-Learning-Engineer-Salary) |

### Recommended Rate Range

**Target: €110-130/hr** (conservative, reflecting strong systems background but LLM ramp-up)
**Stretch: €130-150/hr** (if positioning as senior lead with production systems expertise)
**Ceiling: €150+/hr** (only if deep LLM evaluation experience were proven)

**Negotiation anchor:** Start at €130/hr, be prepared to accept €110/hr minimum.
German freelance market norm: recruiters typically have a 15-25% margin built in.

---

## 3. Gap Analysis vs. JD

### JD Requirements vs. Candidate Skills

| Requirement | Candidate Strength | Gap | Severity |
|------------|-------------------|-----|----------|
| LLM evaluation frameworks & quality metrics | No direct LLM experience | **No LLM evaluation work** | Critical |
| Monitoring data drift in production | Strong observability (OpenSearch, CloudWatch, billions of events) | No ML-specific drift detection | High |
| Reducing hallucinations | None | No LLM/text generation work | Critical |
| Python (FastAPI) | Python (KI Labs 2018-19, Flask) | FastAPI not used; Python dated | High |
| Docker | Used across 4+ roles | Adequate | Low |
| React + TypeScript | Strong TypeScript (5yr), Angular (not React) | React specifically is a gap | Medium |
| Kubernetes conceptual | AWS ECS container orchestration | K8s not explicitly demonstrated | Medium |
| LLMs via GCP, AWS, or Azure | 5yr deep AWS; some GCP | No LLM-specific cloud services (Bedrock, VertexAI) | High |
| Minimal supervision, delivery-focused | Owns production systems end-to-end at Seven.One | Strong match | None |
| Production systems & workflows | 5yr production architecture, billions of events | Strong match | None |

### Overall Fit Assessment: **55-65%**

**Strong match areas:** Production systems ownership, observability/monitoring, delivery-focused autonomy, architecture & design, team leadership
**Critical gaps:** LLM evaluation, hallucination reduction, FastAPI, React

---

## 4. Gap Mitigation Strategies

### Critical: LLM Evaluation & Hallucination Reduction

**Narrative framing:**
> "I've built evaluation frameworks for production systems at scale — pytest-based quality gates, observability pipelines processing billions of events, systematic alerting. The evaluation methodology transfers directly to LLM outputs. What changes is the metrics (BLEU, ROUGE, factuality scores, hallucination rates) not the engineering discipline."

**Concrete mitigations:**
1. **Reference the job-search pipeline** — you literally built an LLM-powered pipeline with quality gates, persona matching, and hallucination controls
2. **Framework transfer:** pytest evaluation framework → LLM eval harnesses (same pattern: define expected behavior, assert against output, track regressions)
3. **Observability transfer:** OpenSearch dashboards for event quality → LLM output quality dashboards (same architecture, different metrics)
4. **Before the call:** Read up on [DeepEval](https://github.com/confident-ai/deepeval), [Ragas](https://github.com/explodinggradients/ragas), and [LangSmith evaluation](https://docs.smith.langchain.com/) — mention these naturally

### High: Python/FastAPI Gap

**Narrative:**
> "I've been building with Python professionally and in my current AI pipeline project using FastAPI. My production Python goes back to KI Labs where I built pytest evaluation frameworks."

**Reality:** Your job-search pipeline IS FastAPI + Python. This is barely a gap.

### Medium: React

**Narrative:**
> "My frontend work has been Angular and TypeScript. React is a natural transition — same component model, same TypeScript, different lifecycle hooks."

### Medium: Kubernetes

**Narrative:**
> "I've worked extensively with container orchestration through AWS ECS and Fargate. Kubernetes shares the same conceptual model — pods ≈ tasks, services ≈ services, deployments ≈ task definitions. I have a solid conceptual understanding."

---

## 5. Interview Preparation

### Questions to Ask Samuel

1. **Who is the end client?** (DeepRec.ai is the agency)
2. **Contract duration?** (3 months? 6 months? Open-ended?)
3. **Hours per week?** (Full-time 40hr or part-time?)
4. **Team size and composition?** (Solo or within a team?)
5. **Start date?**
6. **Rate range they have in mind?** (Let them anchor first)
7. **What LLMs are in production?** (GPT-4, Claude, open-source?)
8. **What evaluation tools/frameworks are already in place?**
9. **Is this greenfield evaluation or improving existing systems?**
10. **Technical task details?** (What to expect in stage 2)

### Likely Technical Questions & Answers

**Q: How would you evaluate LLM outputs in production?**
A: Multi-layered approach:
- Automated metrics (factuality scoring, semantic similarity, format compliance)
- Human-in-the-loop sampling for edge cases
- A/B testing for prompt/model changes
- Regression test suites with golden datasets
- Real-time monitoring dashboards with drift alerting

**Q: How would you detect and reduce hallucinations?**
A: Systematic strategy:
- Retrieval-augmented generation (RAG) with source attribution
- Confidence scoring and threshold-based filtering
- Fact-checking against knowledge bases
- Chain-of-thought verification
- Output guardrails (format validation, entity extraction verification)
- Human review for high-stakes outputs

**Q: Describe your experience with production monitoring.**
A: At Seven.One, I built an observability pipeline on AWS processing billions of daily events with OpenSearch, real-time dashboards, and alerting via CloudWatch/SNS. Transformed incident response from reactive to proactive, achieving 3 years zero downtime.

### Salary Negotiation Tips

1. **Let them state the range first** — "What's the budget range for this role?"
2. **Anchor high:** If pressed, say €130/hr and justify with production systems expertise
3. **Know your floor:** €110/hr minimum (€880/day at 8hr)
4. **Factor in:** No benefits, no paid leave, no pension contributions as freelance — permanent equivalent would be ~60% of your gross rate
5. **Compare:** Germany all-sector freelance mean is €104/hr; AI/ML specialists command 40-60% premium
6. **Recruiter margin:** They likely take 15-25% — your €130 might be billed at €155-165 to the client
7. **If they push back:** Offer to start at a lower rate for a 2-week trial period, then renegotiate

---

## 6. Key Strengths to Emphasize

1. **Production systems ownership** — "I own systems end-to-end with minimal supervision" (directly matches JD)
2. **Observability at scale** — billions of events, real-time monitoring, quality metrics (transfers to LLM monitoring)
3. **Evaluation framework builder** — pytest-based quality gates, automated testing infrastructure
4. **Current AI pipeline work** — your job-search pipeline uses LLMs, FastAPI, quality evaluation
5. **German market** — based in Germany, native-level work authorization, DACH timezone
6. **Immediate availability** — freelance, can start quickly
