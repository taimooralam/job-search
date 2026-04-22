# Codex CLI vs Claude Routing Report

Date: 2026-03-14  
Repo: `/Users/ala0001t/pers/projects/job-search`  
Observed local tool versions: `codex-cli 0.107.0`, `Claude Code 2.1.76`

## Executive Findings

- The repo does **not** currently route most work through the Anthropic API. The primary path is `claude -p` as a subprocess in `src/common/claude_cli.py`, with LangChain fallback in `src/common/unified_llm.py`.
- Codex CLI does **not** have a `-p` pipe/print flag equivalent. On `codex-cli 0.107.0`, `-p` means `--profile`; non-interactive execution is `codex exec`.
- The safest cost/quality win is **not** "Codex for CV bullets". `layer6_v2` already prefers deterministic variant selection, and all six master-CV role files contain variant-based content. Under the stated constraint "no Codex-generated bullets", the right target is `NO_LLM_NEEDED`, not `CODEX_PRIMARY`, for most role-bullet generation.
- Claude remains the correct owner for pain-point mining, web research, fit reasoning, persona/header narrative, outreach, cover letters, and interview-question generation.
- Several call sites are silently using default routing because their `step_name` is not configured in `src/common/llm_config.py`: `role_analysis`, `contact_classification`, `fallback_cover_letters`, and `title_sanitizer`. That is a routing/config hygiene gap independent of any migration.

## 4a. Pipeline Architecture Summary

The codebase defines a 10-node LangGraph superset pipeline in `src/workflow.py` that can run JD extraction, pain-point mining, STAR selection, company research, role research, opportunity mapping, people mapping, outreach packaging, CV generation, and publishing; however, the repo defaults in `src/common/config.py` currently enable only `jd_extractor -> pain_point_miner -> opportunity_mapper -> generator -> output_publisher`, with research, people-mapping, outreach, and STAR selection gated off by env flags. Data flows from MongoDB job records and master-CV data into structured JD intelligence, then into candidate-fit reasoning and finally into `layer6_v2` CV assembly, where deterministic master-CV provenance, role variants, taxonomy/ATS checks, grading, improvement, and publishing are orchestrated with structured logs and LangSmith-compatible tracing preserved across subprocess execution.

### Active-by-default vs full-capability graph

| Concern | Current repo default | Full capability available |
|---|---|---|
| Entry | `jd_extractor` | same |
| Research nodes | disabled by default | `star_selector`, `company_researcher`, `role_researcher`, `people_mapper`, `outreach_generator` |
| CV path | `layer6_v2` enabled by default | legacy `layer6` still reachable if `ENABLE_CV_GEN_V2=false` |
| Master CV source | MongoDB-backed by default | local file fallback available |
| Primary LLM backend | `claude -p` subprocess via `UnifiedLLM` | LangChain fallback where `use_fallback=True` |

### Routing-relevant architectural notes

- `src/common/unified_llm.py` is the central provider abstraction and the right insertion point for a provider router.
- `src/common/claude_cli.py` shells out to `claude -p ... --output-format text --model ...`.
- Research steps auto-enable Claude CLI tools (`WebSearch`) in `UnifiedLLM` when `step_name` starts with `research_`.
- `layer6_v2/orchestrator.py` defaults `use_variant_selection=True`, and the repo's six role files under `data/master-cv/roles/` all contain variant-selection content.
- `runner_service/executor.py` runs the pipeline as a subprocess and streams stdout, so any router must preserve stdout-based structured events.

## 4b. Component Classification Table

Cost-impact legend used below:

- `Negligible`: `< $2/mo`
- `Low`: `$2-10/mo`
- `Medium`: `$10-30/mo`
- `High`: `> $30/mo`

Assumptions:

- 250 default full CV runs/month
- 150 research-enabled runs/month
- 150 outreach-enabled runs/month
- 2,000 scouting/classification ops/month
- Claude cost bands use repo pricing constants in `src/common/llm_config.py` and `src/common/claude_cli.py`
- Codex savings are directional only because exact Codex production pricing/auth mode is not encoded in the repo
- If the runner is using a sunk-cost Claude Max subscription, real cash savings will be lower than the token-theory bands below

### Core pipeline and shared-core call sites

| File:line | Component name | Current model | Category | Reasoning | Estimated monthly LLM cost impact if rerouted |
|---|---|---|---|---|---|
| `src/layer1_4/jd_processor.py:447` | JD structure parsing | Claude CLI Haiku (`jd_structure_parsing`) | `CODEX_PRIMARY` | The task is schema-bound section extraction with rule-based fallback and no persona-sensitive judgment. | `Negligible` |
| `src/layer1_4/claude_jd_extractor.py:518` | JD extraction | Claude CLI Haiku (`jd_extraction`) | `EITHER` | Output is structured, but role categorization and ideal-candidate inference can be plausibly wrong while still validating. | `Negligible` |
| `src/layer2/pain_point_miner.py:1025` | Pain-point mining | Claude CLI Sonnet (`pain_point_extraction`) | `CLAUDE_PRIMARY` | This prompt asks for implicit pain, strategic need, and success-metric synthesis where schema validation alone will not catch plausible mistakes. | `Low` |
| `src/layer2_5/star_selector.py:151` | STAR scoring/selection | Claude CLI Sonnet (`star_selection`) | `NO_LLM_NEEDED` | The repo already has deterministic variant/achievement scoring primitives, and this call is a brittle formatted-ranker over known source records. | `Low` |
| `src/layer3/company_researcher.py:483` | Company type classification | Claude CLI Haiku (`classify_company_type`) | `CODEX_PRIMARY` | Ambiguous employer-vs-agency classification is still a short structured classification task with clear labels and heuristics already in front. | `Negligible` |
| `src/layer3/company_researcher.py:582` | Company web research | Claude CLI Sonnet + WebSearch (`research_company`) | `CLAUDE_PRIMARY` | This is tool-using multi-source research with source-grounded synthesis where failure is "convincing but stale/wrong business signals". | `Low` |
| `src/layer3/company_researcher.py:1198` | Company summarization fallback | Claude CLI Haiku (`summarize_with_llm`) | `EITHER` | Summarization of provided content is structured enough for Codex, but the general-knowledge fallback mode makes this less than a pure extraction task. | `Negligible` |
| `src/layer3/role_researcher.py:278` | Role web research | Claude CLI Sonnet + WebSearch (`research_role`) | `CLAUDE_PRIMARY` | This call depends on external web evidence plus synthesis of why-now/team-context tradeoffs. | `Low` |
| `src/layer3/role_researcher.py:408` | Legacy role analysis | Default middle-tier Claude (`role_analysis`, unconfigured) | `CLAUDE_PRIMARY` | It is a long-context reasoning task over JD, company signals, and candidate context with easy schema-pass failure modes. | `Low` |
| `src/layer4/opportunity_mapper.py:516` | Fit analysis and rationale | Claude CLI Sonnet (`fit_analysis`) | `CLAUDE_PRIMARY` | Recruiter-style fit judgment is exactly the kind of plausible-but-wrong reasoning that schema-free output will not catch. | `Low` |
| `src/layer5/people_mapper.py:926` | People web research | Claude CLI Sonnet + WebSearch (`research_people`) | `CLAUDE_PRIMARY` | Contact discovery depends on live web evidence and role relevance ranking rather than fixed extraction rules. | `Low` |
| `src/layer5/people_mapper.py:1384` | Fallback cover-letter batch | Default middle-tier Claude (`fallback_cover_letters`, unconfigured) | `CLAUDE_PRIMARY` | This is persuasive writing, not deterministic transformation. | `Negligible` |
| `src/layer5/people_mapper.py:1448` | Contact classification | Default middle-tier Claude (`contact_classification`, unconfigured) | `CODEX_PRIMARY` | The output is structured prioritization of known contact rows against explicit criteria and can be constrained tightly. | `Low` |
| `src/layer5/people_mapper.py:1799` | Outreach package generation | Claude CLI Sonnet (`outreach_generation`) | `CLAUDE_PRIMARY` | Personalized networking copy requires judgment, tone, and anti-hallucination by understanding relevance, not just schema. | `Medium` |
| `src/common/persona_builder.py:418` | Persona synthesis | Direct `ClaudeCLI(tier="quality")` / Opus | `CLAUDE_PRIMARY` | This is identity-aware branding copy with high subjective-quality sensitivity. | `Low` |
| `src/layer6_v2/role_generator.py:285` | Fallback role-bullet generation | Claude CLI Sonnet (`role_generator`) | `NO_LLM_NEEDED` | Under the stated constraints, bullet generation should come from deterministic variant selection; all 6 role files already carry variants. | `High*` |
| `src/layer6_v2/role_generator.py:882` | STAR correction pass | Claude CLI Sonnet (`role_generator`) | `NO_LLM_NEEDED` | If bullets come from curated variants rather than free generation, this repair pass should disappear. | `Negligible` |
| `src/layer6_v2/header_generator.py:816` | Value-proposition/tagline generation | Claude CLI Sonnet (`header_generator`) | `CLAUDE_PRIMARY` | This is persona-driven executive framing where stylistic and grounding judgment matter more than schema. | `Low` |
| `src/layer6_v2/header_generator.py:892` | Key-achievement selection | Claude CLI Sonnet (`header_generator`) | `NO_LLM_NEEDED` | The operation should be deterministic ranking over traceable source bullets, not another generative selection layer. | `Low` |
| `src/layer6_v2/ensemble_header_generator.py:415` | Ensemble persona pass | Claude CLI Sonnet (`ensemble_header`) | `CLAUDE_PRIMARY` | Multi-pass persona synthesis is exactly where Claude's long-context judgment is useful and Codex is weakest. | `Medium` |
| `src/layer6_v2/ensemble_header_generator.py:505` | Ensemble synthesis pass | Claude CLI Sonnet (`ensemble_header`) | `CLAUDE_PRIMARY` | The synthesis step resolves tradeoffs among multiple subjective header candidates. | `Low` |
| `src/layer6_v2/grader.py:714` | CV grading | Claude CLI Haiku (`grader`) | `CLAUDE_PRIMARY` | Grading includes executive presence and anti-hallucination reasoning, not only deterministic rubric matching. | `Negligible` |
| `src/layer6_v2/improver.py:326` | CV improver | Claude CLI Haiku (`improver`) | `CLAUDE_PRIMARY` | This is a rewrite stage where plausible-but-untraceable edits are a real failure mode. | `Negligible` |
| `src/layer6_v2/cv_tailorer.py:531` | Final keyword tailorer | Claude CLI Sonnet (`cv_tailorer`) | `CODEX_PRIMARY` | The operation is a constrained rewrite over existing grounded text and is well suited to a coding-oriented structured editor. | `Low` |
| `src/layer6_v2/title_sanitizer.py:132` | Title sanitizer fallback | Default middle-tier Claude (`title_sanitizer`, unconfigured) | `NO_LLM_NEEDED` | The function already has regex guards and the allowed transformation is pure deletion, not generation. | `Negligible` |
| `src/layer6_v2/cover_letter_generator.py:94` | V2 cover letter | Claude CLI Sonnet (`cover_letter_generation`) | `CLAUDE_PRIMARY` | Grounded persuasive writing remains a Claude task in this stack. | `Low` |
| `src/layer7/interview_predictor.py:447` | Interview question generation | Claude CLI Sonnet (`interview_prediction`) | `CLAUDE_PRIMARY` | The task mixes gap analysis, question quality, and interview coaching judgment. | `Low` |

\* `role_generator` only becomes a real spend center if variant coverage is missing and the LLM fallback is active; on the current role corpus, deterministic variants should dominate.

### Adjacent scouting, legacy, and service-only call sites

| File:line | Component name | Current model | Category | Reasoning | Estimated monthly LLM cost impact if rerouted |
|---|---|---|---|---|---|
| `src/services/ai_classifier_llm.py:176` | AI job classification | Claude CLI Haiku (`ai_classification`) | `NO_LLM_NEEDED` | The repo already has deterministic AI-role classifiers and rule scorers for this prefiltering problem. | `Negligible` |
| `src/services/quick_scorer.py:164` | Quick fit scorer | Claude CLI Haiku (`quick_scorer`) | `NO_LLM_NEEDED` | This can be reduced to deterministic rule scoring plus keyword coverage without paying for free-form rationale. | `Low` |
| `src/services/claude_outreach_service.py:228` | Service-layer outreach generation | Claude CLI Opus via `UnifiedLLM` | `CLAUDE_PRIMARY` | This is still high-touch personalized writing, only exposed via a service wrapper. | `Medium` |
| `src/services/claude_cv_service.py:404` | Service-layer role bullet generation | Direct `ClaudeCLI(tier="balanced")` | `NO_LLM_NEEDED` | Same constraint as `layer6_v2`: deterministic variants should replace free bullet generation. | `High` |
| `src/services/claude_cv_service.py:511` | Service-layer profile synthesis | Direct `ClaudeCLI(tier="balanced")` | `CLAUDE_PRIMARY` | Profile/tagline synthesis is subjective positioning copy. | `Low` |
| `src/services/claude_cv_service.py:596` | Service-layer ATS validation | Direct `ClaudeCLI(tier="fast")` | `EITHER` | ATS issue extraction is structured and can be done by either provider if the rubric stays strict. | `Negligible` |
| `src/layer6/generator.py:132` | Legacy single-pass CV generator | Legacy tracked LLM factory | `CLAUDE_PRIMARY` | Whole-CV free generation is the riskiest place to swap to Codex, and should really be retired, not migrated. | `Medium` |
| `src/layer6/cv_generator.py:214` | Legacy competency-mix analyzer | Legacy tracked LLM factory | `CODEX_PRIMARY` | This is a simple structured percentage-allocation task over the JD. | `Negligible` |
| `src/layer6/cv_generator.py:455` | Legacy hallucination QA | Legacy tracked LLM factory | `NO_LLM_NEEDED` | Hallucination checks against employers/dates/degrees should be deterministic validators. | `Negligible` |
| `src/layer6/cover_letter_generator.py:722` | Legacy employer cover letter | Claude CLI Sonnet (`cover_letter_generation`) | `CLAUDE_PRIMARY` | Same reasoning as V2 cover letter. | `Low` |
| `src/layer6/recruiter_cover_letter.py:191` | Legacy recruiter cover letter | Claude CLI Sonnet (`recruiter_cover_letter`) | `CLAUDE_PRIMARY` | This is still persuasive recruiter-facing writing. | `Low` |

## 4c. Codex Migration Candidates (detailed)

### 1. JD structure parsing (`src/layer1_4/jd_processor.py`)

- Current implementation summary: `parse_jd_sections_with_llm()` builds a fixed JSON-only prompt over up to 12k chars of JD text, parses sections, and falls back to rule-based parsing if quality is poor.
- Why Codex is better/equal quality: the task is "given text X, return JSON schema Z" with no persona or narrative requirements, which matches Codex's deterministic transformation strengths.
- Migration sketch: add `src/common/codex_cli.py`; route `step_name="jd_structure_parsing"` to Codex in `UnifiedLLM`; use `codex exec --output-schema ... --json` or `-o` capture; keep the existing rule-based fallback unchanged.
- Anti-hallucination risk assessment: low if output stays limited to headers/items present in the JD and post-parse validation continues rejecting low-section responses.
- Rollback plan if Codex output degrades: env flip `LLM_PROVIDER_jd_structure_parsing=claude`, preserve identical prompt + parser, and rely on the current rule-based fallback.

### 2. Company type classification (`src/layer3/company_researcher.py`)

- Current implementation summary: heuristic keyword detection runs first; an LLM classifies only ambiguous cases into `employer|recruitment_agency|unknown`.
- Why Codex is better/equal quality: the label set is tiny, the schema is explicit, and heuristics already narrow the hard cases.
- Migration sketch: route only the ambiguous branch to Codex; add a JSON schema with `company_type`, `confidence`, `reasoning`; keep the heuristic fast path and default-to-employer behavior.
- Anti-hallucination risk assessment: low because the allowed output space is tiny and downstream behavior is conservative on failure.
- Rollback plan if Codex output degrades: restore Claude for ambiguous cases and keep the heuristic pre-check untouched.

### 3. Contact classification (`src/layer5/people_mapper.py`)

- Current implementation summary: after raw contact discovery, an LLM splits contacts into primary/secondary lists using job context, role context, and pain points.
- Why Codex is better/equal quality: this is structured prioritization over known rows, not empathy-heavy writing.
- Migration sketch: first tighten the contract to "return contact ids + scores only"; then route that call to Codex; keep final object assembly in Python.
- Anti-hallucination risk assessment: medium-low if the prompt forbids inventing people and the parser cross-checks ids against the input contact set.
- Rollback plan if Codex output degrades: revert the provider env var and keep the current LLM/classification interface unchanged.

### 4. Final keyword tailorer (`src/layer6_v2/cv_tailorer.py`)

- Current implementation summary: the model receives the existing CV text plus keyword-placement analysis and performs a constrained rewrite intended to front-load or reposition verified keywords.
- Why Codex is better/equal quality: this is a constrained editing problem, not a persona-generation problem; Codex is strong at "edit text under rules without changing facts".
- Migration sketch: route `cv_tailorer` to Codex with a prompt that explicitly forbids adding claims, technologies, metrics, or bullet lines not already present; diff the output against the input and reject if it introduces novel noun phrases.
- Anti-hallucination risk assessment: medium unless you add a post-diff guard; with a "no novel content" diff check, it becomes acceptable.
- Rollback plan if Codex output degrades: keep the original CV when diff guards fail and flip `LLM_PROVIDER_cv_tailorer=claude`.

### 5. Legacy competency-mix analyzer (`src/layer6/cv_generator.py`)

- Current implementation summary: a legacy LLM returns four percentages for delivery/process/architecture/leadership that sum to 100.
- Why Codex is better/equal quality: the output is pure structured scoring with arithmetic validation.
- Migration sketch: either move it to Codex with strict JSON schema or replace it with deterministic keyword-weight scoring and retire the legacy call.
- Anti-hallucination risk assessment: low because the output is bounded and arithmetic constraints are easy to validate.
- Rollback plan if Codex output degrades: keep legacy path gated behind `ENABLE_CV_GEN_V2=false` and preserve the old call as dead-simple fallback.

## 4d. Claude-Mandatory Components (detailed)

### 1. Pain-point mining (`src/layer2/pain_point_miner.py`)

- Why Claude specifically is required: the model must infer organizational pain, strategic need, and success metrics from ambiguous JD language and examples, not merely extract spans.
- What would break with Codex: output would likely stay syntactically valid while becoming semantically generic or over-literal, which harms every downstream tailoring layer.
- Can a weaker/cheaper Claude model be used instead: Haiku is possible only if you materially simplify the prompt and accept weaker strategic insight; Sonnet is the right default.

### 2. Company/role/people web research (`src/layer3/*`, `src/layer5/people_mapper.py`, `src/common/claude_web_research.py`)

- Why Claude specifically is required: these calls rely on live web search, source citation, and synthesis of multiple documents into grounded business or contact intelligence.
- What would break with Codex: Codex is not a drop-in replacement for Claude's current tool-enabled `research_*` flow, and the installed Codex CLI here exposes no equivalent web-search flag in `exec`.
- Can a weaker/cheaper Claude model be used instead: Haiku can work for `research_people` in low-value runs, but `research_company` and `research_role` are better left on Sonnet.

### 3. Opportunity mapping (`src/layer4/opportunity_mapper.py`)

- Why Claude specifically is required: the fit score/rationale is effectively recruiter judgment over JD, research, pain points, and candidate evidence.
- What would break with Codex: you would still get a score and rationale, but confidence would exceed true grounding quality, and bad fit rationales propagate into CV/header/outreach choices.
- Can a weaker/cheaper Claude model be used instead: Haiku is possible for coarse scoring only if you are comfortable using the result for tiering rather than final-fit explanation.

### 4. Persona and narrative header generation (`src/common/persona_builder.py`, `src/layer6_v2/header_generator.py`, `src/layer6_v2/ensemble_header_generator.py`)

- Why Claude specifically is required: these steps are where the system turns evidence into positioning language, not just selection/ranking.
- What would break with Codex: output would trend literal, stiff, or tone-inconsistent, and subtle grounding rules like "sound human but do not invent identity claims" become harder to trust.
- Can a weaker/cheaper Claude model be used instead: the simple persona/tagline path can likely stay on Sonnet; the multi-pass ensemble should remain Sonnet and only escalate to Opus if you see repeated quality failures.

### 5. Outreach and cover letters (`src/layer5/people_mapper.py`, `src/layer6_v2/cover_letter_generator.py`, legacy `layer6` writers, `src/services/claude_outreach_service.py`)

- Why Claude specifically is required: these outputs are empathetic, audience-aware writing where a schema cannot enforce tone, diplomacy, or contextual judgment.
- What would break with Codex: messages would be more template-like and more likely to miss implicit social constraints while still satisfying length/field rules.
- Can a weaker/cheaper Claude model be used instead: Sonnet is likely enough for most cover letters and outreach; reserve Opus only for truly high-stakes outreach variants.

### 6. Interview question generation (`src/layer7/interview_predictor.py`)

- Why Claude specifically is required: good interview questions need balanced difficulty, realistic probing, and gap-aware coaching guidance.
- What would break with Codex: question quality would likely flatten into generic or overly literal probes even if the JSON schema validates.
- Can a weaker/cheaper Claude model be used instead: yes, this is a strong Haiku/Sonnet candidate depending how much coaching nuance you want.

## 4e. Codex `-p` Mode Compatibility

### Does Codex support `-p` equivalent?

No. On the locally installed `codex-cli 0.107.0`:

- `codex -p` means `--profile`
- non-interactive/headless execution is `codex exec`
- stdin is supported by `codex exec` when prompt is omitted or `-` is passed
- JSON event streaming is enabled with `codex exec --json`

### Which current pipeline components use `claude -p` or subprocess Claude calls?

Two categories exist:

1. Centralized `claude -p` path via `UnifiedLLM`

- Every `UnifiedLLM`/`invoke_unified_sync` call eventually routes through `src/common/claude_cli.py`, which shells out with:
  - `claude -p <prompt> --output-format text --model <model> --dangerously-skip-permissions`
- That includes the core layer call sites listed in section 4b: extraction, pain-point mining, research, fit analysis, people/outreach, header, grading, improvement, cover letters, and interview prediction.

2. Direct `ClaudeCLI` users bypassing `UnifiedLLM`

- `src/common/persona_builder.py`
- `src/services/claude_cv_service.py`

### Which current `claude -p` invocations can swap to Codex?

Good swap candidates:

- `jd_structure_parsing`
- `classify_company_type`
- `contact_classification`
- `cv_tailorer`
- legacy `competency_mix`

Do not swap directly:

- `research_company`, `research_role`, `research_people`
- `pain_point_extraction`
- `fit_analysis`
- `persona_synthesis`
- `outreach_generation`
- `cover_letter_generation`
- `interview_prediction`

Should be removed rather than swapped:

- `star_selection`
- `title_sanitizer`
- `role_generator` fallback bullet generation
- `role_generator` STAR correction
- `header_generator` key-achievement selection
- legacy hallucination QA

### Interface differences to account for

| Concern | `claude -p` today | `codex exec` equivalent / issue |
|---|---|---|
| Non-interactive flag | `-p` / `--print` | `exec` subcommand, not `-p` |
| Prompt input | positional prompt | positional prompt, stdin when prompt omitted or `-` |
| Output format | `--output-format text|json|stream-json` | `--json` emits JSONL events; plain mode mixes progress + final text unless you capture `-o` |
| Structured output | JSON prompt discipline, optional CLI parsing | use `--output-schema` plus JSONL parsing or `-o` final-message capture |
| Tool control | `--tools ""` disables tools; research leaves tools enabled | no comparable per-call tool allowlist in `exec --help`; sandbox/approvals are the control surface |
| Sandbox | Claude permission model | explicit `-s read-only|workspace-write|danger-full-access` |
| Web research | current pipeline relies on Claude tool-enabled research flow | no verified drop-in web-search equivalent observed in local Codex CLI |
| Working directory bleed-through | wrapper intentionally runs Claude in temp dir to avoid `CLAUDE.md` token bleed | a Codex wrapper should similarly avoid `AGENTS.md`/workspace instruction bleed unless you explicitly want it |
| Exit behavior observed locally | wrapper expects normal subprocess exit semantics | local `codex exec --json` exited `1` on transport failure and streamed JSONL `error` / `turn.failed` events |

### Additional compatibility warning

The local Codex CLI attempted to connect to `chatgpt.com/backend-api/codex/responses` during `codex exec`, then failed because network access is restricted in this environment. Before building a production router around Codex, verify the exact headless authentication path you intend to support on the runner and do not assume that `CODEX_API_KEY` alone is already wired into the current local CLI behavior.

## 4f. Recommended Routing Architecture

### Recommended router shape

Add a provider router below component code but above provider wrappers:

- New file: `src/common/model_router.py`
- New wrapper: `src/common/codex_cli.py`
- Minimal edits in `src/common/unified_llm.py` to choose provider by `step_name`

Rationale:

- Component code keeps its current `step_name`, logging, and retry behavior.
- Provider selection stays centralized.
- Structured logging and LangSmith traceability are preserved because the router still returns a unified `LLMResult`.

### Decision tree

```python
def route_step(step_name, prompt, metadata):
    if step_name in NO_LLM_STEPS:
        return deterministic_handler(step_name, metadata)

    provider = env_override(step_name) or classification_default(step_name)

    if provider == "codex":
        result = codex_cli.invoke(step_name, prompt, schema=metadata.schema)
        if result.ok:
            return result
        return claude_cli.invoke(step_name, prompt, schema=metadata.schema)

    if provider == "claude":
        result = claude_cli.invoke(step_name, prompt, schema=metadata.schema)
        if result.ok:
            return result
        if deterministic_fallback_exists(step_name):
            return deterministic_handler(step_name, metadata)
        return result
```

### Where to add the router

- Primary insertion point: `src/common/unified_llm.py`
- Secondary changes: replace direct `ClaudeCLI` usage in `src/common/persona_builder.py` and `src/services/claude_cv_service.py` only if you decide those flows should also become router-aware
- Do **not** route `research_*` through Codex in the first migration wave

### Env-var-only config surface

Recommended env vars:

- `LLM_PROVIDER_DEFAULT=claude`
- `LLM_PROVIDER_<step_name>=claude|codex|none`
- `CODEX_MODEL=<model>`
- `CODEX_MODEL_<step_name>=<model>`
- `CODEX_SANDBOX=read-only`
- `CODEX_API_KEY=<secret>` if/when your Codex runtime supports it on the runner

### Fallback chain

- `NO_LLM_NEEDED` steps: deterministic primary -> no model fallback
- `CODEX_PRIMARY` steps: Codex -> Claude -> deterministic safe fallback
- `CLAUDE_PRIMARY` steps: Claude -> deterministic safe fallback where one exists
- `EITHER` steps: default Claude first until Codex quality is benchmarked, then flip by env var

### Estimated cost reduction vs current all-Claude approach

Two realities matter:

1. Metered-token equivalent

- Default active graph: roughly `10-20%` reduction if you remove `NO_LLM_NEEDED` calls and move structured edit/classification calls to Codex
- Full 7-layer graph with research/outreach enabled: roughly `20-35%` reduction if you also move contact classification and other structured transforms off Claude

2. Actual cash impact on the current subprocess-CLI architecture

- If most work is being absorbed by a sunk Claude Max subscription, direct invoice savings may be close to `0-15%`
- If Codex is additive rather than replacing Claude seats/fallback API spend, the cash line item can even increase

Net recommendation:

- Treat the first migration wave as **quality/risk partitioning plus future optional cost leverage**, not guaranteed immediate cash savings

## 4g. Priority Implementation Order

Ranked by `(cost savings x confidence x implementation ease)`:

1. Remove `title_sanitizer` LLM fallback entirely and keep regex-only sanitization.
2. Make deterministic variant selection the only allowed role-bullet path in `layer6_v2`; disable LLM fallback when all roles have variants.
3. Replace `header_generator` key-achievement LLM selection with deterministic ranking over source bullets.
4. Route `jd_structure_parsing` to Codex behind an env flag and benchmark parse quality.
5. Route `classify_company_type` to Codex behind an env flag.
6. Route `contact_classification` to Codex, but first tighten the contract to ids/scores only.
7. Route `cv_tailorer` to Codex with a post-diff "no novel content" guard.
8. Replace legacy hallucination QA and quick-scoring/classification service calls with deterministic validators/rule scorers.
9. Clean up unconfigured `step_name` values in `llm_config.py` before any provider rollout.
10. Only after the above, consider Codex for legacy `competency_mix`; do not touch research or writing flows in wave 1.

## Appendix A. Layer Map

### A1. Layer files

| Path | Input -> Output | External service calls | Determinism | Hallucination risk if wrong model used |
|---|---|---|---|---|
| `src/layer1_4/claude_jd_extractor.py` | raw JD -> structured JD dict | `UnifiedLLM`, Mongo-facing callers | mixed | medium |
| `src/layer1_4/jd_processor.py` | raw JD text -> semantic sections + HTML | `UnifiedLLM` | mostly deterministic | low-medium |
| `src/layer1_4/prompts.py` | templates -> prompt strings | none | deterministic | none |
| `src/layer2/pain_point_miner.py` | JD text (+ annotations) -> pain points / needs / risks / metrics | `UnifiedLLM` | judgment-heavy | high |
| `src/layer2_5/star_selector.py` | STAR records + pain points -> selected STARs | `UnifiedLLM` today | should be deterministic | medium |
| `src/layer3/company_researcher.py` | company/job context -> company research | Mongo cache, `ClaudeWebResearcher`, `UnifiedLLM` | mixed | high |
| `src/layer3/role_researcher.py` | title/company/JD -> role research | `ClaudeWebResearcher`, `UnifiedLLM` | mixed | high |
| `src/layer4/annotation_fit_signal.py` | annotations + fit context -> score modifiers | none | deterministic | none |
| `src/layer4/opportunity_mapper.py` | JD + research + candidate data -> fit score/rationale | `UnifiedLLM` | judgment-heavy | high |
| `src/layer5/people_mapper.py` | company/role context -> contacts + outreach package | `ClaudeWebResearcher`, optional FireCrawl path, `UnifiedLLM` | mixed | high |
| `src/layer6/generator.py` | full job state -> legacy markdown CV | legacy tracked LLM | generative | high |
| `src/layer6/cv_generator.py` | JD + STAR/candidate data -> legacy CV sections | legacy tracked LLM | mixed | high |
| `src/layer6/cover_letter_generator.py` | job state -> employer cover letter | `UnifiedLLM` | writing-heavy | high |
| `src/layer6/recruiter_cover_letter.py` | job state -> recruiter cover letter | `UnifiedLLM` | writing-heavy | high |
| `src/layer6/outreach_generator.py` | contact artifacts -> packaged outreach | none | deterministic | none |
| `src/layer6/linkedin_optimizer.py` | JD annotations -> headline variants | none | deterministic | none |
| `src/layer6/html_cv_generator.py` | CV structures -> HTML/markdown rendering | none | deterministic | none |
| `src/layer7/interview_predictor.py` | gaps/concerns/STARs -> interview questions | `UnifiedLLM` | judgment-heavy | medium-high |
| `src/layer7/dossier_generator.py` | pipeline state -> dossier text | local FS | deterministic | none |
| `src/layer7/output_publisher.py` | final artifacts -> local/Drive/Sheets/Telegram outputs | local FS, Google Drive, Google Sheets, Telegram, MongoDB | deterministic | none |

### A2. `src/layer6_v2/` subcomponents mapped individually

| Path | Input -> Output | LLM calls | Determinism | Notes |
|---|---|---|---|---|
| `orchestrator.py` | `JobState` -> final CV/cover-letter artifacts | indirect only | mixed | active CV pipeline coordinator |
| `cv_loader.py` | Mongo/files -> `CandidateData`, `RoleData` | none | deterministic | master-CV ingress |
| `variant_parser.py` | role markdown -> enhanced variant structures | none | deterministic | parses curated role variants |
| `variant_selector.py` | variants + JD -> `SelectionResult` | none | deterministic | recommended primary bullet path |
| `achievement_mapper.py` | achievements + pain points -> mapping scores | none | deterministic | useful for replacing LLM ranking |
| `role_generator.py` | role + JD -> bullets | yes, but fallback only should remain | mixed | free-generation path should be phased down |
| `role_qa.py` | bullets + source role -> QA results | none | deterministic | STAR, metric, phrase checks |
| `stitcher.py` | role bullets -> `StitchedCV` | none | deterministic | dedupe + word budgeting |
| `annotation_header_context.py` | annotations + STARs -> header context | none | deterministic | priority/context builder |
| `header_generator.py` | stitched CV + JD + candidate -> `HeaderOutput` | yes | mixed | narrative + selection blended |
| `ensemble_header_generator.py` | candidate/JD/header context -> synthesized header | yes | judgment-heavy | high-tier multi-pass path |
| `skills_taxonomy.py` | JD + whitelist -> competency sections | none | deterministic | already does major non-LLM work |
| `keyword_placement.py` | CV text + keywords -> placement diagnostics | none | deterministic | feeds tailorer |
| `ats_checker.py` | CV text + keyword sets -> ATS diagnostics | none | deterministic | ATS-only checks |
| `grader.py` | CV + JD + master CV -> grade JSON | yes | judgment-heavy | improvement driver |
| `improver.py` | CV + grades + JD -> rewritten CV | yes | judgment-heavy | risky rewrite stage |
| `cv_tailorer.py` | CV + placement diagnostics -> constrained final rewrite | yes | mostly deterministic edit | strong Codex candidate |
| `title_sanitizer.py` | raw title -> cleaned title | optional | deterministic | current LLM fallback unnecessary |
| `cover_letter_generator.py` | final CV + JD context -> cover letter | yes | writing-heavy | keep on Claude |
| `ai_competency_eval.py` | CV text -> grounded AI-claim validation | none | deterministic | good anti-hallucination check |
| `types.py` | shared typed models | none | deterministic | provenance/data contracts |
| `prompts/*.py` | prompt builders/schemas | none | deterministic | routing-relevant only as prompt size drivers |

### A3. Shared utilities relevant to routing

| Path | Role in routing | Notes |
|---|---|---|
| `src/common/config.py` | feature flags and env configuration | defaults disable research/people/outreach nodes |
| `src/common/state.py` | `JobState` schema | pipeline data contract |
| `src/common/llm_config.py` | per-step tier/fallback config | contains unconfigured-step gap |
| `src/common/unified_llm.py` | central provider abstraction | best insertion point for model router |
| `src/common/claude_cli.py` | direct `claude -p` subprocess wrapper | current primary provider path |
| `src/common/claude_web_research.py` | shared research helper | routes `research_*` steps through tool-enabled Claude |
| `src/common/persona_builder.py` | direct persona synthesis | bypasses `UnifiedLLM` today |
| `src/common/llm_factory.py` | legacy tracked model factories | used by legacy Layer 6 |
| `src/common/model_tiers.py` | tier-cost helpers | useful for cost banding only |
| `src/common/structured_logger.py` | stdout/Redis structured logging | must be preserved in any provider swap |
| `src/common/token_tracker.py` | token/cost accounting | already integrated into pipeline run tracking |
| `src/common/tracing.py` | LangSmith/run context helpers | keep unchanged |
| `src/common/master_cv_store.py` | master-CV source-of-truth store | critical for traceability |
| `src/common/rule_scorer.py` | deterministic AI-role scoring | strong replacement candidate for quick scoring |
| `src/common/ai_classifier.py` | deterministic AI classification | strong replacement candidate for LLM classifier |

## Appendix B. Notable Gaps and Drift

- The docs talk about "Claude API" frequently, but the code overwhelmingly uses `claude -p` subprocesses.
- `src/common/config.py` defaults the research/outreach nodes off, so the default live graph is narrower than the full architecture docs imply.
- `src/services/claude_cv_service.py` comments describe Opus profile synthesis, but the actual `profile_cli` is initialized with `tier="balanced"` rather than `quality`.
- Unconfigured step names in `llm_config.py` make several call sites inherit default middle-tier routing silently.

### Codex Review Checklist

1. Verify that `codex exec` is the correct non-interactive entrypoint on the target runner, and confirm whether production auth will use ChatGPT session auth or `CODEX_API_KEY`.
2. Add a tiny `codex exec --json` smoke test in a sandboxed environment with network enabled and capture the exact JSONL event shape needed for a new `CodexCLI.invoke()` wrapper.
3. Instrument `layer6_v2` to log how often `generate_all_roles_from_variants()` actually falls back to `RoleGenerator.generate()` in real runs.
4. Confirm that all six role files under `data/master-cv/roles/` still parse cleanly with `VariantParser` and still expose usable variant data.
5. Benchmark `jd_structure_parsing` on a representative sample of compressed JDs using current Claude vs Codex vs rule-based fallback, and compare section count plus parse validity.
6. Benchmark `classify_company_type` and `contact_classification` with a fixed gold set before changing provider routing.
7. Prototype a deterministic replacement for `header_generator` key-achievement selection using `achievement_mapper`, `annotation_header_context`, and keyword scoring, then compare selected bullets against current outputs.
8. Add explicit `llm_config.py` entries for `role_analysis`, `contact_classification`, `fallback_cover_letters`, and `title_sanitizer` before any provider migration.
9. Add a post-diff guard for `cv_tailorer` that rejects any output introducing noun phrases, metrics, or technologies not present in the input CV.
10. Replace `title_sanitizer` LLM fallback with regex-only logic and regression-test a corpus of noisy LinkedIn titles.
11. Replace legacy hallucination QA with deterministic employer/date/degree validators and compare false-positive/false-negative rates against the current LLM path.
12. Measure actual runner cash cost vs theoretical token cost to determine whether Codex migration is a real savings lever or mainly a quality/risk-partitioning change under the existing Claude Max setup.
