# Project Evaluation: Job Intelligence Pipeline

## Executive Summary
This codebase implements a clean, modular LangGraph-based pipeline that already delivers a working vertical slice: job ingestion from MongoDB, pain-point mining, basic company research, fit scoring, cover letter + CV generation, and publishing to Google Drive/Sheets. Architecture and state management are well thought out for a single-candidate, job-by-job workflow, with clear separation of concerns per layer and a robust configuration setup.

Hyper-personalization is present but not yet as deep or structured as the original n8n workflow. The pipeline passes the full candidate knowledge base (11 STAR records) into key layers and asks the LLM to reference specific achievements, but it does not yet explicitly map pain points to individual STAR stories or enforce concrete examples in outputs. The result is “job-aware and candidate-aware” output that is better than generic boilerplate but below the sophistication of the full Opportunity Dossier.

For a single user targeting ~50 jobs/day, the current design is viable and cost-effective, provided runs remain supervised and you accept occasional external API failures. However, it is not yet ready for fully unattended production at scale: retries and graceful degradation are in place, but observability, caching, batch processing, and People Mapper (Layer 5) need to mature before matching the n8n system’s breadth.

## Ratings (1-10 scale)

### Sub-Ratings
- Architecture design & patterns: **8/10**
- Code organization & modularity: **8/10**
- Error handling & resilience: **7/10**
- Testing coverage & approach: **6/10**
- Documentation quality: **8/10**
- Production readiness: **6/10**
- Scalability potential: **7/10**
- Personalization depth: **7/10**

### Aggregated Ratings
- Architecture: **8/10**
- Personalization: **7/10**
- Scalability: **7/10**
- Code Quality: **8/10**
- Production Readiness: **6/10**
- **Overall Score: 7.3/10**

## Detailed Analysis

### 1. Architecture Review

- **Layered design**  
  - Clear 7-layer conceptual model in `architecture.md` with an explicit decision to ship a simplified vertical slice today (Layers 2, 3, 4, 6, 7 wired in `src/workflow.py`).  
  - Each layer lives in its own module (`src/layer2/pain_point_miner.py`, `src/layer3/company_researcher.py`, `src/layer4/opportunity_mapper.py`, `src/layer6/generator.py`, `src/layer7/output_publisher.py`), matching the AGENTS.md guidelines.

- **State management**  
  - `src/common/state.py` uses a `TypedDict` `JobState` with explicit fields per layer and metadata; this gives good type safety and a clear contract between nodes.  
  - State is simple but extensible toward the full Opportunity Dossier (comments already mark “FUTURE” fields and expansions).

- **LangGraph usage**  
  - `src/workflow.py` uses `StateGraph(JobState)` with named nodes and linear edges, giving a straightforward, debuggable orchestration.  
  - Flow is strictly sequential for now (no branching or batching), which is appropriate at this phase; later, you can introduce branching for optional layers or retries.

- **Patterns and separation of concerns**  
  - Each layer encapsulates external dependencies (LLM, FireCrawl, Google APIs) behind small classes (`PainPointMiner`, `CompanyResearcher`, `OpportunityMapper`, `Generator`, `OutputPublisher`).  
  - Config is centralized in `src/common/config.py`, avoiding secrets in code and making model/temperature choices per layer explicit.

- **Weak points**  
  - Layer 1 (input collector) is primarily embodied in `scripts/run_pipeline.py` and `scripts/list_jobs.py`, not as a reusable node.  
  - Layer 5 (People Mapper) is entirely missing; some advanced Layer 3/4 concepts in `architecture.md` (signals, “why now”, timing analysis) are not implemented yet.  
  - `run_id`, `created_at`, and `status` fields exist in `JobState` but are not actively set or updated, which leaves some observability/value on the table.

**Verdict:** The architecture is solid, modular, and extensible, with a clear path to the full dossier. It’s a good use of LangGraph for this domain.

### 2. Personalization Effectiveness

- **STAR record usage**  
  - `Config.CANDIDATE_PROFILE_PATH` defaults to `./knowledge-base.md`, which contains the 11 STAR records; `scripts/run_pipeline.py` loads this as the `candidate_profile` field in `JobState`.  
  - Layer 4 (`OpportunityMapper`) and Layer 6 (`OutreachGenerator` in `src/layer6/generator.py`) both receive the full `candidate_profile` and are prompted to use concrete achievements.

- **Layer 4: Opportunity Mapper**  
  - Prompt (`SYSTEM_PROMPT` + `USER_PROMPT_TEMPLATE`) explicitly asks for:  
    - Considering job description, pain points, company summary, and candidate profile.  
    - Producing a numerical score plus rationale.  
  - It does **not** explicitly reference “STAR records” as structured objects or ask the LLM to select specific STAR IDs; it treats the profile as unstructured text.  
  - The fit score rubric is clear and graded (bands for 90–100, 80–89, etc.), which encourages consistent scoring, but it’s still purely LLM-based without calibration to historical outcomes.

- **Layer 6: Cover letter generation**  
  - Prompt explicitly instructs the LLM to:  
    - Use company summary and pain points.  
    - Highlight “specific achievements that address their pain points”.  
  - This should drive use of concrete STAR content when the knowledge base is rich, but there is no hard enforcement (e.g., “mention at least one quantified result” or “cite two specific projects”).

- **CV tailoring**  
  - `CVGenerator._parse_candidate_profile` looks for simple structured markers like `Name:`, `Email:`, `Key Skills:`, and bullet achievements.  
  - The CV `Professional Summary` explicitly mentions the target role and company, and can optionally include fit score if ≥80, which gives a job-specific summary but not deep restructuring of the CV per job.  
  - It does not yet re-order STAR stories or experiences based on job pain points.

- **Pain-point → STAR mapping**  
  - There’s no dedicated layer that maps each pain point to one or two best STAR records; everything is implicit via the LLM’s reasoning on monolithic profile text.  
  - This is the main missing piece for “hyper-personalization”: you’re providing the ingredients but not yet forcing a tight mapping.

**Verdict:** Personalization is **stronger than generic** (job-specific, pain-point-informed, candidate-aware) but falls short of fully structured STAR-driven tailoring. I’d rate it as solid but improvable.

### 3. Scalability Assessment

- **Throughput (jobs/day)**  
  - Docs state ~30 seconds per job end-to-end today.  
  - Sequential processing on a single worker:  
    - 50 jobs/day ⇒ ~25 minutes compute time.  
    - 100 jobs/day ⇒ ~50 minutes compute time.  
  - So from a pure latency perspective, **50–100 jobs/day is achievable** even with a single process, assuming external APIs don’t become the bottleneck.

- **Bottlenecks**  
  - **LLM calls:** Layers 2, 3 (summary), 4, and 6 all call GPT-4o (via `langchain_openai.ChatOpenAI`). These dominate latency and cost.  
  - **FireCrawl:** Web scraping in `CompanyResearcher._scrape_website` can be slow or rate-limited; it uses retries but no caching. For repeated companies across jobs, this is a prime caching target.  
  - **Google APIs:** Drive/Sheets operations (`OutputPublisher`) are lightweight per job but can hit quota limits; failure is currently treated as non-fatal with error messages appended.  
  - **MongoDB:** Reads are trivial compared to LLM/scrape costs at this scale.

- **Cost projection**  
  - Docs estimate ~5,500 tokens per job (L2: ~1500, L3: ~800, L4: ~1200, L6: ~2000).  
  - Using GPT-4o pricing, this roughly aligns with **$0.10–0.15 per job** when including both input and output tokens.  
  - For 1,000 jobs/month:  
    - Cost ≈ **$100–150/month**, which is reasonable given the value of high-quality applications.  
  - If you offload some simpler layers (e.g., L2/L3) to a cheaper model (gpt-4o-mini or similar), you can likely cut this by ~30–50%.

- **Concurrency & scaling up**  
  - Current pipeline is strictly synchronous (`run_pipeline` processes one job). There is no batching, queuing, or concurrency control.  
  - For 3,135 jobs at 30s each, sequential processing is about 26 hours; so for that backlog you’d want either:  
    - A batched runner that processes, say, 100–200 jobs/day; or  
    - Multiple worker processes each handling a subset of jobs.  
  - LangGraph plus a simple queue (or cron + job list) would make this manageable without architectural overhaul.

**Verdict:** Scaling to 50–100 jobs/day is feasible with the current design, especially for a single user, but larger backlogs (thousands of jobs) will benefit from caching, batching, and a simple job queue.

### 4. Code Quality

- **Organization & modularity**  
  - Per-layer modules under `src/layer*`, shared utilities in `src/common`, and CLI scripts in `scripts/` follow the stated guidelines.  
  - Function and class names are descriptive; modules are cohesive and small.

- **Prompts & LLM usage**  
  - Prompts are clear, task-focused, and include explicit formatting instructions (e.g., “Format as: SCORE: [number] / RATIONALE: ...”), which improves parsing reliability.  
  - Temperature settings are appropriately split: analytical tasks (L2, L3, L4) at 0.3; creative generation (L6) at 0.7.  
  - There are no few-shot examples yet; everything is instruction-based. This is acceptable but might limit robustness in edge cases.

- **Error handling**  
  - Tenacity-based retries on all external calls:  
    - L2 `_call_llm`, L3 `_scrape_website` + `_summarize_with_llm`, L4 `_analyze_fit`, L6 `generate_cover_letter`, L7 `_upload_file_to_drive` and `_log_to_sheets`.  
  - Each layer catches exceptions, logs a clear error message, and returns default values plus an appended `errors` list in `JobState`.  
  - This achieves **graceful degradation**: one failing layer won’t crash the whole pipeline, though downstream quality may suffer.

- **Testing approach**  
  - TDD-style scripts in `scripts/test_layer2.py` … `test_layer7.py` define expected behaviors and assertions.  
  - These are **integration tests** that call real external services; they are useful but not deterministic or automated under pytest.  
  - `tests/` is present but currently empty; no unit tests for prompt parsing or state transitions.  
  - This is a good start for exploration but not yet a production-grade test suite.

- **Type safety & style**  
  - `JobState` as a `TypedDict` is a strong choice; many functions annotate args/returns.  
  - Code is PEP 8-compliant, with clear docstrings and minimal inline complexity.  
  - A few places could benefit from stricter typing (e.g., `Dict[str, Any]` everywhere) but overall style is good.

**Verdict:** Code quality is high for a solo project at this stage—clean, readable, and modular. The main gaps are formal tests and some minor inconsistencies between docs and current code (e.g., PROGRESS vs actual implementation status).

### 5. Production Readiness

- **Security & secrets**  
  - All secrets loaded via environment variables in `Config`; no hard-coded keys.  
  - Google service account JSON is referenced by path but not committed.  
  - `.env` and `.env.example` are documented in `PROGRESS.md`/`ROADMAP.md` (and presumably exist locally).

- **Logging & observability**  
  - Logging is primarily `print` statements per layer, which is fine for CLI usage but not ideal for long-running services.  
  - LangSmith integration is documented in `docs/langsmith-usage.md`, and environment variables are set up to trace the workflow.  
  - There is no structured logging (JSON logs, log levels) yet.

- **Error handling & retries**  
  - Tenacity retries on external calls are a strong point.  
  - Non-fatal errors (e.g., Drive quota issues) are captured in `errors` but do not abort the pipeline, which matches the “graceful degradation” goal.  
  - However, missing outputs (e.g., no CV or cover letter) aren’t explicitly signaled via `status` or a separate “partial success” flag.

- **Deployment readiness**  
  - Code is CLI-centric (`scripts/run_pipeline.py` and `scripts/list_jobs.py`); there’s no Dockerfile or deployment scripts yet.  
  - For a VPS deployment, you’d need:  
    - A process supervisor (systemd, supervisord, or a simple cron + shell wrapper)  
    - A `.env` deployment strategy  
    - Possibly containerization if you want easy portability.  
  - There is no built-in scheduling or queue; these would be external concerns.

**Verdict:** Ready for **supervised personal use** on a VPS (you running it interactively or via simple cron), but not yet ready for multi-tenant or unattended operation at scale.

### 6. Gap Analysis (vs. n8n Workflow)

#### Feature Comparison

| Capability                                      | n8n Workflow (sample-dossier) | LangGraph Pipeline (current) |
|------------------------------------------------|--------------------------------|------------------------------|
| 10-section Opportunity Dossier                 | ✅ Full                       | ❌ Only partial (no full dossier file yet) |
| Company signals (funding, acquisitions, etc.)  | ✅                            | ❌ Not implemented (basic summary only) |
| Hiring reasoning & timing significance         | ✅                            | ❌ Not implemented           |
| Strategic pain point analysis (needs, risks…)  | ✅ Deep                       | ⚠️ Simplified to 3–5 bullets |
| People Mapper (8–12 contacts)                  | ✅                            | ❌ Not implemented (Layer 5 missing) |
| Per-person outreach (LinkedIn/email templates) | ✅                            | ❌ Not implemented           |
| Fit scoring (0–100 + rationale)                | ✅                            | ✅ Implemented (Layer 4)    |
| Company + role research                        | ✅ Rich                       | ✅ Simplified summary        |
| Cover letter generation                        | ✅ Rich & context-heavy       | ✅ 3-paragraph tailored letter |
| Tailored CV (.docx)                            | ✅ Yes                        | ✅ Basic tailored CV         |
| Google Drive/Sheets integration                | ✅                            | ✅ Implemented (Layer 7), with known quota issues |
| FireCrawl query logging & metadata             | ✅                            | ❌ Not yet                   |
| Validation metadata per section                | ✅                            | ❌ Not yet                   |

#### Functional coverage estimate

- Implemented vs full dossier:  
  - You have roughly **4 of 10 major dossier sections** in a simplified form: job summary (via CIO + CLI context), basic company overview, pain points, fit analysis, and outreach artifacts (cover letter + CV).  
  - Absent are People Mapper, detailed signals, timing analysis, validation metadata, and FireCrawl query logging.  
  - This is about **35–40% of the full functionality**, which aligns with your own estimate.

- Practical value of current slice
  - For actual applications, the current outputs (pain points, company summary, fit score + rationale, tailored cover letter, tailored CV) are **already useful**: you get a job-specific story and artifacts that are likely better than generic templates.  
  - What’s missing vs. n8n is the **networking strategy** (People Mapper, outreach templates) and deeper strategic context (signals, timing, “why now”), which are crucial for high-touch roles but not strictly necessary for every application.

**Verdict:** The simplified version is a **viable MVP** for serious applications (assuming manual review), but it doesn’t yet deliver the full “opportunity dossier” superpower that the n8n workflow has.

### 7. Improvement Recommendations

#### Critical (Must-Fix before production-like use)

- Add robust test harness with pytest  
  - Move TDD scripts under `tests/` as pytest tests, mocking external services (OpenAI, FireCrawl, Google, MongoDB) per AGENTS guidelines.  
  - Add unit tests for parsing logic (`_parse_pain_points`, `_parse_llm_response`, `_parse_candidate_profile`).

- Harden error signaling and state flags  
  - Actively set `run_id`, `created_at`, and a final `status` (`completed`, `failed`, `partial`) in `JobState` (`src/workflow.py` and layers).  
  - Fail fast (or mark as partial) when critical outputs (fit score, cover letter, CV) are missing.

- Cache company research  
  - Introduce a simple caching layer for `CompanyResearcher` results (e.g., Mongo collection keyed by company name) to avoid repeated FireCrawl calls for the same company, improving latency and cost.

- Guard against missing configs at runtime  
  - Re-enable `Config.validate()` during startup in CLI (`scripts/run_pipeline.py`) to prevent half-configured runs (with clear user-facing messages).

#### High Priority (Next sprint)

- STAR-aware personalization layer  
  - Add a new LangGraph node (e.g., `star_selector`) that:  
    - Parses `knowledge-base.md` into structured STAR records.  
    - Selects 2–3 best-fit STAR stories per job based on pain points.  
    - Supplies those to Layer 4 & Layer 6 (instead of raw monolithic profile).  
  - Update prompts in L4/L6 to explicitly reference selected STAR records and require citing at least one metric.

- People Mapper (Layer 5)  
  - Implement a minimal People Mapper that:  
    - Accepts company and role.  
    - Uses FireCrawl/API to find 4–6 key contacts (even if imperfect at first).  
    - Generates short LinkedIn messages and emails per contact.  
  - This restores a major differentiator vs. generic application tooling.

- Dossier assembler and file output  
  - Add a simple `dossier_generator` node or extend Layer 7 to create a `dossier.txt` file locally (`applications/<company>/<role>/dossier.txt`) with a simplified structure mirroring `sample-dosier.txt`.  
  - This gives you a single artifact to review and share, closer to the n8n experience.

- Batch processing CLI  
  - Add a `scripts/run_batch.py` that:  
    - Uses `list_jobs.py` filters to select, say, N jobs.  
    - Iterates over them, calling `run_pipeline` with concurrency limits (even simple sequential is fine initially).  
  - Log summary metrics (processed/failed, average latency, average cost if available from LangSmith).

#### Medium Priority

- Cost and latency optimization  
  - Use a cheaper model (e.g., gpt-4o-mini or similar) for L2 and parts of L3 where high fidelity is less critical.  
  - Measure per-layer token usage via LangSmith (already documented in `docs/langsmith-usage.md`) and adjust prompts to trim unnecessary context.  
  - Experiment with prompt brevity while preserving quality.

- More structured company and job modeling  
  - Extend `JobState` and L3 to capture: `industry`, `headcount`, `recent_events`, `signals` list.  
  - Use these in L4 to improve reasoning about timing and strategic fit.

- Improved CV tailoring  
  - Have `CVGenerator` use selected STAR stories to build a “Key Achievements” section that aligns with pain points.  
  - Consider per-job re-ordering of achievements and skills based on L4’s analysis.

#### Low Priority (Future considerations)

- Alternate orchestration options (Prefect/Temporal)  
  - For large-scale, multi-user workflows, consider wrapping LangGraph calls inside a Prefect or Temporal workflow to get scheduling, retries, and observability at a higher level. For your single-candidate use case, current LangGraph + CLI setup is sufficient.

- Advanced monitoring and alerts  
  - Add a small monitoring script/dashboard that pulls LangSmith metrics (latency, failure rate) and sends alerts (Telegram/email) when error rate spikes or costs exceed thresholds.

- UI layer  
  - Long-term, a simple web UI to review dossiers, approve/reject runs, and trigger resubmissions would significantly improve UX, but it’s not necessary for your immediate goals.

## Conclusion

The current LangGraph pipeline is well-architected, cleanly coded, and already valuable for generating tailored applications for a single candidate. It can comfortably handle 50–100 jobs/day for your own search, with manageable cost and good-enough reliability, especially if you keep a human-in-the-loop review step.

However, it does not yet match the full power of your n8n Opportunity Dossier workflow—particularly around People Mapping, company signals, and structured STAR-to-pain-point mapping. I would give a **“Go for supervised personal production use”** (for your own job search) but a **“Not yet”** for fully unattended, large-scale deployment. For a dream job, I would trust this pipeline as a first-pass generator and analysis tool, but I would still review and refine the outputs manually before sending.

---

# Project Evaluation: Job Intelligence Pipeline (Tough-Love Hiring Manager Review)

## Executive Summary
From a hiring manager’s seat, this system is already far above the average “spray and pray” tooling: it forces structured thinking about pain points, business impact, and your STAR achievements. But it is still too easy for the pipeline to produce outputs that feel like “intelligent generic” rather than “painfully specific to my role and my team,” and there is real risk of quiet hallucinations in company signals and outreach if you scale without tightening constraints. Architecture and code are not your bottleneck now; the bottleneck is ruthless focus on: (1) mapping each job’s business pain to 2–3 proof-backed STAR stories, and (2) making the first screen of every artifact (CV, cover letter, outreach) scream “this person deeply understands our problem and has solved it before.”

If you want a hiring manager to be biased toward you, you must treat each A-priority job as a mini go-to-market campaign. That means opinionated dossier structure, strict control of sources, and deliberate time allocation (A/B/C tiers) so you can hit 100–200 jobs/day without diluting quality. The good news: your current system is ~40% of the way to the n8n dossier and already capable of supporting that volume with supervision; the bad news: unless you implement the STAR selector, tighten prompts to forbid speculation, and redesign outputs around “pain → proof → plan,” your extra sophistication will not translate into more interviews.

## Ratings (1–10 scale, hiring-manager lens)
- Architecture: **8/10** (still strong; not your constraint)
- Personalization (felt as a recipient): **7/10** now, **9/10 potential**
- Scalability to 100–200 jobs/day: **7/10** with supervision, **5/10** if unattended
- Code Quality: **8/10**
- Production Readiness (for your personal search): **7/10**
- Overall: **7.5/10** today with a clear path to **9/10** if you execute the improvements below

## 1. What Actually Impresses a Hiring Manager (and How the Pipeline Maps)

- I care about three things:
  - Do you understand the **business problem** behind this role, in my context?
  - Have you **solved this exact type of problem before**, with numbers?
  - Are you **low-risk to onboard**: concise, structured, no BS, easy to advocate for?
- Your pipeline already:
  - Extracts pain points and strategic needs (Layer 2).
  - Generates company/role understanding (Layer 3).
  - Produces a fit narrative plus cover letter and CV (Layers 4 and 6).
- Where it falls short for me as a hiring manager:
  - STAR stories are not **surgically matched** to each pain point; they come through as a cloud of good achievements rather than a sniper shot.
  - Outputs are sometimes verbose and narrative-heavy instead of “punchy, metric-driven, and skimmable in 30 seconds.”
  - There is limited **explicit evidence** that facts are grounded in real sources vs. the model’s imagination (hallucination risk).

## 2. Strategic Gaps to Fix Next (Tough-Love Priorities)

1. **Mandatory STAR Selector (Layer 2.5) – Non-negotiable**
   - Parse `knowledge-base.md` into structured STAR objects once (ID, situation, task, actions, metrics, tags).
   - For each job, map pain points → ranked STARs with explicit scores.
   - Feed only the top 2–3 STARs into downstream layers, with IDs, and require outputs to:
     - Mention STAR IDs or labels explicitly in internal reasoning.
     - Cite at least 1–2 concrete metrics per artifact (CV, cover letter, outreach).
   - This is the single highest-ROI change for hyper-personalization.

2. **Dossier Structure: Pain → Proof → Plan**
   - Redesign the top of `dossier.txt` to be:
     - Section 1: “Top 3 business pains I will solve in this role” (their language, not yours).
     - Section 2: “Proof I’ve solved them before” (one STAR per pain, with metrics).
     - Section 3: “90-day plan at a glance” (3–5 bullets).
   - Push long-form narrative and research to later sections; hiring managers skim first.

3. **Hallucination Guardrails by Contract, Not Hope**
   - For all research layers (L3, future People Mapper):
     - Pass **only** scraped snippets + job text; forbid the model from using “world knowledge” to make claims about the company.
     - In prompts, require it to label any unknown as `"unknown"` or “not found in provided context.”
     - Penalize speculation: add explicit instructions like “If you are not 100% certain based on the provided text, say ‘Unknown’ rather than guessing.”
   - Log and spot-check a small sample daily (e.g., 5 dossiers) specifically for hallucinated facts.

4. **Output Brevity and Punch**
   - Tighten prompt instructions for cover letter and outreach:
     - Max word/character counts.
     - Required structure: hook sentence (pain), proof sentence (STAR), closing sentence (call to action).
   - For CV generation, ensure:
     - Bullet points start with **impact verbs** and numbers.
     - Each job section surfaces 2–3 STAR-derived bullets relevant to this role, not everything you’ve ever done.

## 3. Scaling to 100–200 Jobs/Day Without Dilution

Design your **operating model**, not just your code:

- **Tiering Strategy**
  - Tier A (dream / high-signal roles, 5–10/day): Full pipeline (all layers, manual review, tailored outreach to multiple contacts).
  - Tier B (good but not dream, 30–50/day): Pain points + STAR selector + compact cover letter + CV tweak; 1–2 contacts max.
  - Tier C (low-signal, 50–150/day): Minimal automation: fit score + short summary + quick CV variant; no deep research.

- **System implications**
  - Add flags in `JobState` and CLI args for `--tier A|B|C` to:
    - Skip heavy layers (full research, outreach) for C-tier.
    - Use cheaper models for B/C where appropriate.
    - Short-circuit when fit score < threshold for A-tier (don’t waste time).

- **Batching and Caching**
  - Batch jobs by company to reuse company research across multiple postings (huge cost win).
  - Introduce a `company_research` cache collection keyed by normalized company name and last-updated timestamp.
  - Run batch scripts at off-peak times (e.g., nightly) and keep your manual review in a fixed time window.

## 4. Hyper-Personalization & Hallucination Minimization: Concrete Mechanisms

- **Mechanisms for Hyper-Personalization**
  - STAR mapping (already covered) is the backbone.
  - Add “anti-generic” checks in prompts:
    - Require referencing at least 2 **job-specific phrases** from the JD in each artifact.
    - Ask the model to explicitly list which pain point each paragraph addresses.
  - In Layer 4, require a **short bullet list**: “Why I’m unusually good for this role” with direct mapping to STARs.

- **Mechanisms for Minimizing Hallucinations**
  - Source tagging:
    - In state, track `source` for each fact (JD, company site, LinkedIn, your profile).
    - Encourage models to attribute facts to sources in reasoning (even if not surfaced to the final user).
  - JSON-only outputs for analytical layers (you already do some of this):
    - Pain points, research summaries, outreach plans should be machine-parseable, with no extra text.
  - Regular “red-team” reviews:
    - Once per week, manually audit 10 random dossiers: mark hallucinations, prompt failures, and feed back into prompt and test improvements.

## 5. Making the Hiring Manager Biased Toward You

- **Signal you understand leverage and trade-offs**
  - In the dossier and cover letter, explicitly acknowledge trade-offs (e.g., “Given your rapid hiring, I would start with X and delay Y”).
  - That shows judgment, not just competence.

- **Consistency across artifacts**
  - Ensure the **same 2–3 STAR stories** appear in:
    - CV highlights section.
    - Cover letter core paragraph.
    - Outreach messages.
  - Repetition = memorability; it makes it easy for me to sell you internally.

- **Evidence of ownership**
  - Add a short “Owner’s note” section in the dossier (even if just for you) explaining:
    - Why this role.
    - What you would measure in the first 90 days.
  - Use this to quickly customize your talking points for screening calls.

## 6. Next 48-Hour Action Plan

- Implement Layer 2.5 (STAR selector) and wire it into Layers 4 and 6 with explicit IDs and metric requirements.
- Add a simple `tier` field to `JobState` and CLI flags to control which layers run.
- Tighten prompts for hallucination control: explicit “unknown over guessing,” smaller allowed context, and JSON-only analytical outputs.
- Redesign `dossier.txt` header sections around “pain → proof → plan,” aiming to **beat** `sample-dosier.txt` on clarity and punch, not just length.
- Define your personal daily routine: A/B/C-tier quotas, fixed review windows, and a simple tracking sheet of interviews per tier so you can see what truly moves the needle.
