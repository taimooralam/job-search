# Token & Cost Optimization — Job Intelligence Pipeline (2026-04-17)

Author: pipeline-doctor session
Scope: strategic + tactical guidance for token use in this repo, for Claude Code subagents, and for the Claude-CLI-driven pipeline (`src/common/unified_llm.py`).
Context: user is currently 91% "subagent-heavy", 74% >150k context, 73% sessions 8h+, with $199.75/$300 extra-usage burn before week reset. Opus 4.7 is live; its tokenizer can emit up to ~35% more tokens for the same text, so old habits quietly get more expensive.

---

## 1. TL;DR — what will actually move the needle

Ranked by expected $ saved per hour of effort on this project:

1. **Stop running Opus as the driver for 8h+ sessions.** Switch Claude Code default to Sonnet; invoke Opus deliberately (`/model opus` for hard design turns, then back). The *advisor* pattern (Opus plans, Sonnet executes) is Anthropic's own recommendation and benchmarks at ~11% cheaper than all-Opus while keeping quality. ([MindStudio][advisor])
2. **Downgrade every subagent that does not need Opus.** Today 3 of 15 agents in `.claude/agents/` are pinned to `model: opus` (`job-search-architect`, `cv-profile-agent`, `pipeline-analyst`). Every spawn of these is a fresh Opus context that bypasses your main-session cache. `pipeline-analyst` in particular does MongoDB inspection — that is Sonnet/Haiku work. Target state: ≤1 Opus agent (`job-search-architect`), rest Sonnet or Haiku.
3. **Clear, don't compact, between unrelated tasks.** 74% of your usage is at >150k context. `/compact` only pays off mid-task and *only while the 5-minute cache is warm*; after that it re-processes the whole context at full price. `/clear` costs nothing. ([MindStudio][clear-compact], [ClaudeCodeCamp][caching])
4. **Treat the 5-minute prompt-cache TTL as a scheduling primitive.** If you are going to idle >5 min, either finish the turn or accept you'll pay uncached read next time. Long "thinking while I grab coffee" sessions are the single most wasteful pattern in your stats.
5. **Pipeline: force `tier="low"` (Haiku) wherever output is extractive/classification, not generative.** Several `middle` steps in `llm_config.py` are really classification (see §5).
6. **Pipeline: batch pre-processing through the Batch API** (50% off input+output, ≤24h SLA). Any research, grading, scoring, eval step that runs nightly or in bulk qualifies. ([Anthropic Pricing][pricing])

Realistic target: **30–45% weekly-token reduction** without quality loss, mostly from #1 + #2 + #3. The pipeline changes (#5, #6) compound on top but require code edits.

---

## 2. How tokens flow in this project today

### 2.1 Claude Code (your interactive sessions)

Each turn bills = **(cached input read) + (new input) + (output) + (thinking)**. Caching is automatic at 1024-token boundaries for Sonnet/Opus (2048 for Haiku), 5-min TTL, with an optional 1h TTL at 2× write cost. ([Anthropic caching][caching-api])

Three amplifiers that show up in your stats:

- **Subagent-heavy (91%)**: every `Agent()` call is a new conversation with its own system prompt, its own CLAUDE.md load, its own tool list. The subagent's tokens do *not* share cache with your main session. Spawning 5 subagents in a turn = 5 separate cache warm-ups.
- **>150k context (74%)**: even with 90% cache hits, reading 150k cached tokens is ~$0.135 on Opus *per turn* just to re-prime. Multiply by hundreds of turns per day.
- **8h+ sessions (73%)**: the 5-min TTL means almost every turn after an idle crosses into uncached territory. A 200k-context session that goes cold once costs ~$3 just to re-warm (Opus input $15/M, 90% cache discount gone).

### 2.2 The pipeline (`src/common/unified_llm.py`)

The pipeline calls Claude via the local `claude` CLI (not the API). This matters:

- **CLI calls bill against your Claude Code subscription/quota**, not a separate API key. So every pipeline run competes with your interactive session for the same weekly limit. That is almost certainly why the $199.75/$300 burn feels surprising — the pipeline is silently eating subscription quota.
- The CLI does *not* currently expose cache breakpoints to you, so caching is best-effort based on prompt prefixes. Long, stable system prompts at the top of each pipeline step *will* cache if the step runs multiple times within 5 min on the same tier. Randomizing the prefix order kills this.
- `STEP_CONFIGS` in `src/common/llm_config.py` routes ~25 steps to tiers:
  - `low` → Haiku 4.5
  - `middle` → Sonnet 4.5
  - `high` → Opus 4.5
- Research steps (`research_*`) enable CLI tools including WebSearch (`unified_llm.py:414`) — those tool turns cost extra tokens on every call.

---

## 3. Strategic framework — when to spend

Three questions, in order, before any token burn:

1. **Can I not ask?** Reading a file, `git log`, `grep` — these cost you nothing, they cost Claude ~nothing cached. Delegating research to a subagent that then reads 20 files costs you the subagent's full context twice (spawn + return).
2. **What's the cheapest model that reliably does this?** Classification/extraction → Haiku. Implementation from a clear spec → Sonnet. Open-ended design / synthesis under ambiguity → Opus. Default assumption should be Sonnet; Opus is the exception.
3. **Is this cache-friendly?** Stable system prompt + stable context + varying last message = cache-friendly. Rotating contexts, freshly-assembled prompts, or spawning fresh subagents = not.

---

## 4. Tactical — Claude Code interactive use

### 4.1 Session hygiene

- **`/clear` between unrelated tasks.** Zero cost, wipes everything. Your default move when switching topics. ([MindStudio][clear-compact])
- **`/compact` only mid-task, and only while cache is warm (<5 min since last turn).** After 5 min idle, `/compact` re-reads the whole context at full price — the opposite of what you want. Use `/compact` with explicit preservation: *"preserve file paths, active bug, decisions made."* ([SitePoint][sitepoint])
- **Target ≤60% context fill.** Once you cross ~120k in a 200k window the model starts losing middle content ("lost in the middle") and every turn is expensive. Checkpoint with `/compact`, then `/clear` when the task is done.
- **Kill parallel sessions you're not driving.** Your 28% "4+ parallel" slice is free lunch for Anthropic — each idle session still warms cache on each turn you touch it.

### 4.2 Model selection inside Claude Code

- Default to **Sonnet** for the driver. `/model sonnet` at session start.
- Escalate to Opus only when you hit a genuine synthesis/design turn. Do one-shot reasoning, then `/model sonnet` back. This is the advisor pattern. ([MindStudio][advisor])
- **Cap thinking tokens.** `export MAX_THINKING_TOKENS=10000` in your shell; the default is much higher. Most turns don't need more than that.
- For Opus 4.7 specifically: remember the tokenizer change means a prompt that cost X on 4.5 may cost ~1.2–1.35X on 4.7. Budget accordingly. ([Finout][opus47-cost])

### 4.3 Subagent discipline

This is where 91% of your burn lives. Rules:

1. **Never spawn a subagent for work you could do in <3 tool calls yourself.** A subagent costs you: its system prompt (~2–5k) + CLAUDE.md load + tool list + its own exploration + its return summary. For a single `grep` that's pure waste.
2. **Pin the cheapest model in the agent's frontmatter.** `model: haiku` for file discovery / lookups / formatting. `model: sonnet` for implementation. `model: opus` only where an agent genuinely synthesizes across many unknowns.
3. **Batch subagent calls in parallel when truly independent.** One message with 3 `Agent()` calls ≈ 3 × single-agent cost, but wall-clock is one agent. *Don't* serialize independent research.
4. **Give the subagent a tight, self-contained prompt** (the meta-guidance already in your system prompt). Vague prompts → exploratory meandering → 10× tokens.
5. **Never let a subagent spawn a subagent unless strictly needed.** Deep agent trees explode fast.

### 4.4 Prompting patterns that save tokens

- Name the files. "Edit `src/layer6/cover_letter_generator.py:722`" beats "find where the cover letter is generated."
- State the outcome. "Return a list of X." beats "look into Y."
- Forbid exploration when you know the answer already. "Don't search; just edit."
- Ask for deltas, not re-reads. "Show me just the changed lines."
- Prefer `Edit` over `Write` when modifying files (Write sends the whole file; Edit sends only the diff).

---

## 5. This project's subagents — audit & recommendations

Current state (from `.claude/agents/*.md`):

| Agent | Current model | Recommendation | Why |
|---|---|---|---|
| `job-search-architect` | opus | **keep opus** | Genuine synthesis across principles + code + trade-offs. |
| `pipeline-analyst` | opus | **→ sonnet** | MongoDB inspection + output validation is structured analysis, not synthesis. |
| `cv-profile-agent` | opus | **→ sonnet** (or keep opus only for "high" tier CV runs) | Creative writing benefits from Opus, but ensemble passes multiply cost; gate on a flag. |
| `architecture-debugger` | sonnet | keep sonnet | Correct. |
| `backend-developer` | sonnet | keep sonnet | Correct. |
| `frontend-developer` | sonnet | keep sonnet | Correct. |
| `test-generator` | sonnet | keep sonnet | Correct. |
| `cv-role-bullet-agent` | sonnet | keep sonnet | Bullet generation wants Sonnet's quality. |
| `outreach-agent` | sonnet | keep sonnet | Personalization benefits from Sonnet. |
| `cv-creator` | (check) | sonnet | Generation task. |
| `systems-architect-guide` | (check) | sonnet | Guidance, not open-ended synthesis. |
| `cv-ats-validator-agent` | haiku | keep haiku | Correct. |
| `doc-sync` | haiku | keep haiku | Correct. |
| `session-continuity` | haiku | keep haiku | Correct. |
| `region-detector-agent` | haiku | keep haiku | Correct. |

**Expected savings from the two downgrades alone**: roughly 60–70% on every `pipeline-analyst` call and every `cv-profile-agent` call that doesn't need Opus reasoning. Given your 91% subagent-heavy usage, this is material.

**One process change**: add a note in CLAUDE.md that agents default to Sonnet; Opus is opt-in per call via `model: opus` override when you explicitly ask for it. Makes accidental Opus spawns impossible.

---

## 6. The pipeline — strategic levers

### 6.1 Tier audit of `STEP_CONFIGS` (`src/common/llm_config.py`)

Steps currently at `middle` (Sonnet) that I'd push to `low` (Haiku) unless a validation run proves quality loss:

- `classify_company_type` — already `low`, good.
- `summarize_with_llm` — already `low`, good.
- `ats_validation` — already `low`, good.
- `quick_scorer` — already `low`, good.
- `ai_classification` — already `low`, good.
- `pain_point_extraction` (`middle`) — **candidate for `low`**. Extraction task with a stable schema.
- `fit_analysis` (`middle`) — **keep `middle`**; reasoning about fit.
- `analyze_company_signals` (`middle`) — **candidate for `low`** if inputs are structured.
- `star_selection` (`middle`) — **keep `middle`**; selection reasoning.
- `form_scraping` (`low`) — good.
- `answer_generation` (`middle`) — keep.
- `interview_prediction` (`middle`) — keep.
- Research steps (`research_*`, `middle`) — these use WebSearch tools, so downshifting to Haiku risks weaker query strategy. Keep `middle`.
- `cover_letter_generation`, `recruiter_cover_letter`, `outreach_generation` (`middle`) — keep; creative.
- Eval steps (`eval_*`, `high`) — justified; these drive rubric quality.
- `persona_synthesis` (`high`) — justified.

**Action**: add a `scripts/eval_tier_downshift.py` that runs N jobs through both tiers for the two candidates above and compares outputs. If delta <5%, flip the default.

### 6.2 Pipeline cost amplifiers to kill

- **Repeated system prompts per step**: verify each step's system prompt is stable across calls (no timestamps, no random ordering). If two consecutive runs on the same tier within 5 minutes share 90%+ prefix, you get the cache discount for free.
- **`use_fallback=False` on many steps** (grader, ensemble_header, improver, cv_tailorer, research_*, eval_*, cover letters): these steps *must* use Claude CLI. That's fine for quality but means CLI downtime fails the pipeline. No direct token impact, but be aware.
- **Research tools on every research step** (`unified_llm.py:414`): each WebSearch turn is a multi-step tool loop. Cache expensive outputs (company research) in Mongo with a TTL (e.g., 7 days) and skip re-running.
- **`claude_web_research.py` calls three times** (company, role, people): if the job is from a company you've seen recently, hit Mongo cache first. Almost certainly already done — confirm.

### 6.3 Pipeline moves with real leverage

- **Route bulk/overnight work through the Batch API** where possible. Currently the pipeline uses the Claude CLI (Pro/Max subscription quota). For scout-cron-scale work, moving evals, re-grading, and bulk classification to the Batch API via `anthropic` SDK is **50% cheaper** on input+output and sidesteps the weekly subscription cap entirely. ([Anthropic Pricing][pricing])
- **Decouple pipeline from subscription quota.** Your $300 weekly cap is being burned by both interactive and pipeline use. Option: route pipeline LangChain fallback to API key billing (already done via OpenAI fallback), and either (a) disable CLI for high-volume steps and force API billing via Anthropic SDK, or (b) gate scout-cron runs to not touch subscription-backed Claude during business hours.
- **Add prompt-cache breakpoints explicitly** if/when `unified_llm.py` moves to API calls: `cache_control: {"type": "ephemeral"}` on the system prompt block. 90% read discount on stable prefixes. ([Anthropic caching][caching-api])
- **Emit actual cost metrics**: `LLMResult.cost_usd` is already captured (unified_llm.py:453) — surface it in a weekly "top 10 most expensive steps" report so regressions are visible. You already have structured logging in place; a small aggregation script is enough.

---

## 7. A concrete weekly-budget playbook

For someone at 91% subagent-heavy, 74% >150k, 73% 8h+ sessions:

**Session-level:**
1. Start session: `/model sonnet`.
2. Set `MAX_THINKING_TOKENS=10000` in your shell profile.
3. First task: do it. When done, `/clear`.
4. When a task needs design: one Opus turn via `/model opus`, then `/model sonnet`.
5. Check `/context` every ~30 turns; if >60%, `/compact` with explicit preservation (while warm) *or* `/clear` if you're changing topic.
6. Close unused parallel sessions.

**Subagent-level:**
1. Before spawning, ask: could 1-3 direct tool calls do this? If yes, skip.
2. If yes to subagent: pin cheapest viable model in frontmatter.
3. Parallelize independent subagent calls in one message.
4. Downgrade `pipeline-analyst` and `cv-profile-agent` to `sonnet` in their frontmatter.

**Pipeline-level (this week):**
1. Run the tier-downshift evaluation on `pain_point_extraction` and `analyze_company_signals`.
2. Audit research-cache TTLs in `claude_web_research.py`.
3. Add a `cost_usd` rollup script that reads structured logs and prints weekly top-10 expensive steps.

**Pipeline-level (next month):**
1. Move scout-cron bulk scoring off Claude CLI and onto the Batch API (50% discount, 24h SLA is fine for cron).
2. Add explicit cache breakpoints if moving to API calls.
3. Gate Opus usage in eval steps behind a `QUALITY_MODE=high` flag; default to Sonnet for dev iterations.

---

## 8. Watchouts specific to Opus 4.7

- **New tokenizer emits up to ~35% more tokens for the same text.** A workload that fit in 150k on 4.5 may hit 200k on 4.7. Your "74% >150k" number will drift up on 4.7 even if nothing else changes. ([Finout][opus47-cost])
- Per-token price is held flat ($15/$75 per M for Opus 4.7), but effective $/request rose because of the tokenizer. ([Anthropic Pricing][pricing])
- Caching and batch discounts stack the same way (90% read discount, 50% batch discount). These become *more* important on 4.7, not less.
- If you're pinning any agent/config to `claude-opus-4-5-*`, decide deliberately whether to upgrade to 4.7 or stay — don't let auto-upgrade surprise you mid-week.

---

## 9. Concrete code/config changes proposed

Small, high-leverage, no architectural churn:

1. **`.claude/agents/pipeline-analyst.md`**: `model: opus` → `model: sonnet`.
2. **`.claude/agents/cv-profile-agent.md`**: `model: opus` → `model: sonnet` (or gate via parameter).
3. **CLAUDE.md**: add a "Token discipline" section with rules from §7.
4. **`src/common/llm_config.py`**: after evaluation, downshift `pain_point_extraction` and `analyze_company_signals` to `low`.
5. **New**: `scripts/cost_rollup.py` — weekly report of cost by step from structured logs.
6. **New**: `scripts/eval_tier_downshift.py` — tier comparison harness.
7. **Medium-term**: new `src/common/anthropic_batch.py` that routes low-SLA bulk work through the Batch API for the 50% discount.

None of these are speculative — each maps to a measurable cost line item.

---

## Sources

- [Manage costs effectively — Claude Code Docs](https://code.claude.com/docs/en/costs)
- [Claude Code Token Optimization: Full System Guide (2026)](https://buildtolaunch.substack.com/p/claude-code-token-optimization)
- [Claude Code Cost Optimisation Guide — systemprompt.io](https://systemprompt.io/guides/claude-code-cost-optimisation)
- [Create custom subagents — Claude Code Docs](https://code.claude.com/docs/en/sub-agents)
- [Claude Code's Advisor Strategy — MindStudio][advisor]
- [Clear vs. Compact in Claude Code — Medium][clear-compact]
- [How Prompt Caching Actually Works in Claude Code — ClaudeCodeCamp][caching]
- [Claude Code Context Management Guide — SitePoint][sitepoint]
- [Prompt caching — Claude API Docs][caching-api]
- [Pricing — Claude API Docs][pricing]
- [Claude Opus 4.7 Pricing: The Real Cost Story — Finout][opus47-cost]
- [Run Claude Code programmatically — Claude Code Docs](https://code.claude.com/docs/en/headless)
- [Scaling Claude Code: 4 to 35 Agents in 90 Days — Kaxo](https://kaxo.io/insights/scaling-claude-code-sub-agent-architecture/)
- [Claude Opus 4.7 Deep Dive — Caylent](https://caylent.com/blog/claude-opus-4-7-deep-dive-capabilities-migration-and-the-new-economics-of-long-running-agents)

[advisor]: https://www.mindstudio.ai/blog/claude-code-advisor-strategy-opus-sonnet-haiku
[clear-compact]: https://medium.com/@nustianrwp/managing-your-context-window-clear-vs-compact-in-claude-code-8b00ae2ed91b
[caching]: https://www.claudecodecamp.com/p/how-prompt-caching-actually-works-in-claude-code
[caching-api]: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
[pricing]: https://platform.claude.com/docs/en/about-claude/pricing
[sitepoint]: https://www.sitepoint.com/claude-code-context-management/
[opus47-cost]: https://www.finout.io/blog/claude-opus-4.7-pricing-the-real-cost-story-behind-the-unchanged-price-tag
