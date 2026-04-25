# Manual Master CV Edit Guide

Date: 2026-04-16

Purpose:
- translate Step 6 findings into manual edits you can make yourself
- improve the curated store for architect-first and player-coach-safe AI targeting
- keep all changes interview-defensible and schema-safe

Primary source artifacts:
- `data/eval/baselines/step6_report.md`
- completed baseline JSONs in `data/eval/baselines/`

Important constraint:
- this guide does not assume `data/master-cv/*` is complete truth
- use only evidence you are personally comfortable claiming
- do not add unsupported executive, people-management-heavy, research, or compliance-program claims

## If You Only Make 3 Changes

1. Edit `data/master-cv/role_metadata.json`
- change `candidate.title_base`
- add `candidate.summary`

2. Reorder the top of `data/master-cv/roles/01_seven_one_entertainment.md`
- put AI platform and governed-delivery evidence into the highest-visibility current-role positions

3. Reorder `Commander-4` and `Lantern`
- Step 6 proxy mode currently sees project descriptions and the first 2 bullets
- bullet order materially affects future baseline reruns

## Why Ordering Matters

Current Step 6 proxy mode reads:
- `candidate.title_base`
- `candidate.summary` if present
- the first 4 achievements from the current role
- each project description plus the first 2 bullets

That means wording matters, but ordering matters just as much.

## Non-Negotiables

Do not add:
- `Head of AI`, `VP AI`, `Chief AI Officer`, or similar executive titles
- broad org-building, budget, or P&L ownership
- deep-ML-research, publication, RLHF, fine-tuning, or academic framing
- broad remote/distributed claims unless explicitly evidenced
- stronger agentic-autonomy language than the current evidence supports

Safe target framing:
- `Technical Architect`
- `AI Platform Architect`
- `Software Architect`
- `Technical Lead`
- `Lead Software Engineer`

## File-by-File Edit Suggestions

### 1. `data/master-cv/role_metadata.json`

#### Recommended `title_base`

Best fit:

```json
"title_base": "Technical Architect / AI Platform Architect"
```

Safer alternatives if you want less AI emphasis:

```json
"title_base": "Technical Architect / Software Architect"
```

```json
"title_base": "AI Platform Architect / Software Architect"
```

Avoid keeping:

```json
"title_base": "Engineering Leader / Software Architect"
```

Reason:
- Step 6 repeatedly flagged the current top line as too generic and too leadership-first
- the strongest completed fits are architect-led categories

#### Add `candidate.summary`

Recommended summary:

```json
"summary": "Hands-on technical architect and player-coach with 11 years building distributed systems, modernizing revenue-critical platforms, and shipping enterprise AI workflows. At Seven.One, combines large-scale platform modernization with AI platform delivery across retrieval quality, evaluation harnesses, guardrails, structured outputs, MCP integrations, observability, and reliability. Earlier Daypaio work adds 0→1 event-sourced SaaS architecture, event storming, and scalable product launch experience."
```

What this fixes:
- weak AI architect branding
- underweighted AI platform / evaluation / guardrails narrative
- underweighted Daypaio greenfield range

What not to change here:
- keep the canonical Seven.One employment title as-is unless you explicitly want to change the source of truth
- do not replace the role title with `Technical Architect`

### 2. `data/master-cv/roles/01_seven_one_entertainment.md`

#### Replace `Role Summary`

Recommended replacement:

```md
Technical Lead and architect driving both large-scale platform modernization and enterprise AI workflow delivery at Seven.One Entertainment Group (ProSiebenSat.1 subsidiary). Responsible for revenue-critical AdTech systems serving millions of impressions daily plus Commander-4/Joyia AI platform capabilities spanning retrieval quality, evaluation, guardrails, structured outputs, MCP integrations, observability, and reliability.
```

#### Add one `Business Context` line

Recommended addition:

```md
- **AI Scope**: Commander-4/Joyia enterprise AI workflow platform serving 2,000 users across 42 plugins
```

#### Add one `Leadership Scope` line

Recommended addition:

```md
- **Architect scope**: Platform lead for Commander-4/Joyia and architectural north-star ownership across modernization and AI workflow delivery
```

#### Reorder the top 4 achievements

Recommended top-visibility order for future Step 6 reruns:
1. `Achievement 15: AI Platform Engineering (Commander-4/Joyia)`
2. `Achievement 17: Structured Outputs & Tool-Calling Architecture`
3. `Achievement 1: Legacy Modernization & Platform Transformation`
4. `Achievement 3: Real-Time Observability Pipeline`

Then keep the rest below them.

Reason:
- Step 6 proxy mode currently only sees the first 4 current-role achievements
- this change alone will improve future baselines more than rewriting lower-priority bullets

#### Optional strengthening from already-vetted upstream evidence

If you are comfortable promoting more from the knowledge base, tighten these facts:

- Observability:
  - add `sub-second latency`
  - add `10x cost reduction`
  - add `cross-functional architecture, engineering, product, and infrastructure collaboration`

- Scaling:
  - add `10x-100x traffic bursts`
  - add `sub-second latency during peak loads`

Recommended stronger observability `Impact` variant:

```md
- **Impact**: Processed billions of data points per day with sub-second latency, reduced observability infrastructure costs by 10x, and improved MTTD/MTTR through real-time dashboards and alerting.
```

Use only if you are personally comfortable claiming it.

### 3. `data/master-cv/roles/02_samdock_daypaio.md`

#### Replace `Role Summary`

Recommended replacement:

```md
Lead Software Engineer responsible for end-to-end architecture and market launch of a greenfield CRM SaaS platform. Combined event storming, CQRS/event sourcing, engineering standards, and hands-on delivery to ship a scalable multi-tenant product from domain discovery to production in a fast-paced 0→1 environment.
```

#### Tighten `Business Context`

Recommended replacement for the challenge line:

```md
- **Challenge**: Build scalable platform at startup speed without sacrificing architectural runway
```

#### Tighten `What Made This Role Unique`

Recommended replacements:

```md
- **0→1 ownership**: Full architecture responsibility from blank slate through market launch
- **DDD practitioner**: Event storming facilitation with real business impact and bounded-context discovery
```

Reason:
- Step 6 repeatedly flagged Daypaio as underweighted
- this role is the strongest greenfield complement to Seven.One modernization

### 4. `data/master-cv/projects/commander4.md`

#### Replace `description`

Recommended replacement:

```md
description: Enterprise AI workflow platform at ProSiebenSat.1 serving 2,000 users with 42 plugins - hybrid retrieval, evaluation harnesses, governed structured outputs, MCP integrations, semantic caching, and per-silo guardrails/access control
```

#### Reorder bullets

Recommended order:
1. structured outputs + MCP + guardrails + per-silo access control
2. evaluation harness + guardrail profiles
3. semantic caching architecture
4. hybrid retrieval
5. document ingestion pipeline

Why this order:
- Step 6 wants governance, evaluation, and controls surfaced before tool inventory
- proxy mode only sees the first 2 bullets

Recommended first 2 bullets:

```md
- Designed structured-output and tool-calling architecture using Zod schema validation for all LLM responses, 5 MCP server tools for external integrations, 42 workflow plugins, per-silo guardrail injection via LiteLLM proxy, and per-silo access control.
- Implemented retrieval evaluation harness with MRR@k and NDCG@k (exponential gain) scoring functions, guardrail profiles for per-silo content policy enforcement, and threshold tuning validated against 14 unit tests.
```

Recommended semantic-caching bullet to include above retrieval if you want stronger cost/latency proof:

```md
- Architected two-tier semantic caching with L1 SHA-256 exact-match lookups (~2ms) and L2 semantic similarity via S3 Vectors (>= 0.95 threshold, ~200ms), backed by Redis TTL to cut LLM cost while preserving response quality.
```

### 5. `data/master-cv/projects/lantern.md`

#### Replace `description`

Recommended replacement:

```md
description: Multi-provider LLM gateway with routing/fallback, semantic caching, eval-driven quality gates, and production observability
```

#### Reorder bullets

Recommended order:
1. gateway routing/fallback
2. eval-driven quality gates
3. observability stack
4. semantic caching
5. optional operational safeguards

Why:
- Step 6 repeatedly wants gateway design, evaluation, and operational controls surfaced before lower-level detail
- proxy mode sees only the first 2 bullets

Recommended first 2 bullets:

```md
- Architected multi-provider LLM gateway with LiteLLM routing, model registry, request validation, and automatic fallback across OpenAI, Anthropic, and Azure endpoints.
- Implemented eval-driven quality gates with golden-set evaluation, scoring LLM responses against reference outputs before serving them to downstream consumers and catching regressions earlier.
```

Recommended optional extra bullet:

```md
- Added operational safeguards around multi-provider routing with request ID propagation, retry/backoff behavior, and circuit-breaker protections for degraded provider conditions.
```

### 6. `data/master-cv/projects/lantern_skills.json` (optional)

Only change this if you believe these are fully verified and you want them elevated out of the post-checklist bucket.

Potential additions to `verified_competencies`:

```json
"Golden-Set Testing",
"Eval Harness Design",
"Cost Optimization"
```

This is optional.
The stronger wins are still in `role_metadata.json`, `01_seven_one_entertainment.md`, `02_samdock_daypaio.md`, `commander4.md`, and `lantern.md`.

## Suggested Manual Edit Sequence

1. Edit `data/master-cv/role_metadata.json`
- `title_base`
- `summary`

2. Edit `data/master-cv/roles/01_seven_one_entertainment.md`
- role summary
- AI scope line
- architect scope line
- reorder top 4 achievements

3. Edit `data/master-cv/roles/02_samdock_daypaio.md`
- role summary
- challenge line
- 0→1 / event storming lines

4. Edit `data/master-cv/projects/commander4.md`
- description
- bullet order

5. Edit `data/master-cv/projects/lantern.md`
- description
- bullet order

6. Only then consider `lantern_skills.json`

## What Not To Spend Time On Yet

Do not optimize these first:
- long-tail early-career roles
- deferred Step 6 secondary categories
- broad taxonomy redesign
- adding new metadata keys unless you want them for your own documentation

The shortest high-value path is still:
- top-line identity
- Seven.One current-role ordering
- Daypaio greenfield visibility
- Commander-4 / Lantern governance + evaluation + ops emphasis

## After You Finish Manual Edits

Rerun only:
- `ai_architect_global`
- `head_of_ai_global`
- optionally `staff_ai_engineer_eea`

Reason:
- those are enough to test whether your manual edits improved the architect-first and player-coach-safe targeting
- you do not need a full Step 6 rerun immediately
