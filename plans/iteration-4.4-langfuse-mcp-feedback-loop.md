# Iteration 4.4 Plan: Langfuse MCP Server and CLI Feedback Loop

Author: 2026-04-27 (planning pass while 4.3.1 is in flight; orthogonal to 4.3.* schema work)
Parent plans:
- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`
- `plans/iteration-4.3-pipeline-architecture.md` (canonical, observability §)
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md` (Langfuse trace/span/session contract — 4.4 consumes the schema 4.3.8 produces, but does **not** block on 4.3.8 being merged)

Status: new umbrella plan; introduces a read-only Langfuse-backed MCP server on the VPS plus an error-ingestion contract that gives both Claude Code and OpenAI Codex CLIs an automated feedback loop into dev and prod failures.

---

## Pipeline-wide goals (4.x continuation)

Inherits the four 4.x goals (truthful CVs, VPS-resident Codex CLI, A/B coexistence, Langfuse observability). 4.4 does not produce CVs; it produces the **operator-and-CLI feedback substrate** that the rest of 4.x already assumes exists.

This plan is independent of the master-CV blueprint (4.3.1) and the cv_assembly stage plans (4.3.2–4.3.9). It can be implemented while 4.3.1 is still moving, and it strictly upgrades the developer experience for every iteration that follows.

---

## 1. Mission

Give every shell — Claude Code on the laptop, Codex CLI on the laptop, Codex CLI on the VPS, the operator at a terminal — a single, structured, low-latency way to ask:

- "What broke in the last hour?"
- "What is broken right now?"
- "What does the last failed `<stage>` look like end-to-end?"
- "Is ingestion healthy?"
- "What's the cost trend today?"
- "Show me the trace for level-2 job `<id>`."

…and to push **new failures back into the conversation** without anyone asking, so the model can suggest fixes against fresh evidence rather than from memory.

The substrate is a Model Context Protocol server, deployed as a container next to Langfuse on the VPS, that wraps the Langfuse Public API with an opinionated tool surface tuned for "what went wrong" loops, plus a thin instrumentation layer that ensures dev errors and prod errors arrive in the same place under the same schema.

---

## 2. Why now

Three concurrent pain points justify pulling this in before the rest of 4.3.* lands.

1. **4.3.* is dense, multi-stage, and partially deployed.** Today a failure in `cv_assembly` on the VPS is observed by tailing journalctl, eyeballing a Drive file, or by hand-querying Mongo. By the time the operator reaches Langfuse the CLI has already moved on.
2. **Claude Code and Codex CLI both speak MCP first-class.** A read-only MCP server gives both shells the same observability without per-tool integration. No bespoke skill plumbing per error class.
3. **Tracing is already there in code.** `src/pipeline/tracing.py` (`SearchTracingSession`, `ScrapeTracingSession`) and the preenrich/cv_assembly call sites already reference `langfuse_session_id`/`langfuse_trace_id`. They simply have nowhere structured to be **read from** by the model. 4.4 closes that loop without changing any emitter.

Building 4.4 now means every later 4.3.* stage that ships goes live with an automated feedback loop already in place, instead of being instrumented retroactively.

---

## 3. Scope

### 3.1 In scope

- A new container `langfuse-mcp` deployed on the VPS, on the existing `n8n-prod_default` Traefik network, exposing a single MCP HTTP/SSE endpoint at `https://langfuse-mcp.srv1112039.hstgr.cloud`.
- A read-only tool surface (§7) that wraps the **Langfuse Public REST API**. v1 does **not** query ClickHouse or Postgres directly.
- Bearer-token auth between CLI and MCP server, distinct from the Langfuse `pk/sk` pair.
- A small `src/observability/errors.py` helper that normalizes Python exceptions into a consistent Langfuse `error` observation shape (§9). Callable from preenrich, cv_assembly, runner code, and ad-hoc scripts.
- Project-and-environment tagging convention (§9.3) so dev and prod traces can be filtered cleanly.
- `.mcp.json` (project-scope) and `~/.codex/mcp.toml` (global) entries that wire both CLIs to the server out of the box.
- A Claude Code `SessionStart` hook and a Codex equivalent that prefetches the most recent N errors and prepends a digest to the conversation.
- A subscription channel (`langfuse://errors/live`) that streams new error-level observations, so the model can be re-woken when prod fails mid-session.
- A second subscription channel `langfuse://session/{session_id}/tail` that streams every observation for one named session — backs the opt-in `/langfuse-tail <session_id>` skill so the operator can watch a known-broken pipeline run live.
- Documentation: `docs/current/observability/langfuse-mcp.md` and a one-pager `infra/compose/langfuse-mcp/README.md`.
- **OpenClaw `oc` container reads from the MCP via its bundled Codex CLI**: bearer token shipped through compose env, `/root/.codex/config.toml` rendered at container start by an entrypoint shim. No emitter inside `oc` for v1 (deferred to 4.4.4 if openclaw failures grow noisy).
- **Dual-project Langfuse setup**: `scout-prod` (the existing `discovery-prod` project, aliased) and a new `scout-dev` project. Both pk/sk pairs live in `/root/langfuse-mcp/.env`; the MCP server selects per request via a `project` parameter (default `scout-prod`).

### 3.2 Explicitly out of scope (deferred or owned elsewhere)

- The trace/span schema itself — owned by 4.3.8. 4.4 reads whatever 4.3.8 writes.
- Cost-ledger semantics — 4.3.8 owns the formula and the budget gates. 4.4 only **reads** the cost rollups Langfuse provides.
- Eval corpora, benchmark harnesses, rollout phase gates — 4.3.8.
- Writing back to Langfuse (scoring, annotations, dataset edits). 4.4 is read-only. A 4.4.1 follow-up may add a tightly-scoped `score_trace` write tool if needed.
- ClickHouse/Postgres direct queries. v1 uses the public REST API only. If aggregation perf becomes a problem we will revisit in 4.4.2.
- Replacing `src/pipeline/tracing.py` or the cv_assembly tracing seam (`src/cv_assembly/tracing.py` per 4.3.8 §8.6). 4.4 ingests through whatever those produce.
- Frontend integration. The frontend already has trace-link affordances per 4.3.8 §8.7. 4.4 does not touch the web UI.

### 3.3 Non-goals

- A general-purpose Langfuse admin UI replacement. The web UI at `https://langfuse.srv1112039.hstgr.cloud` remains canonical for human exploration; the MCP server is for the CLI feedback loop.
- Real-time alerting (PagerDuty, email, Slack). Push notifications stay inside MCP subscriptions.
- Cross-project federation beyond two projects (`scout-prod`, `scout-dev`).

---

## 4. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  VPS (srv1112039)                                        │
│                                                          │
│   ┌─────────────────────┐     ┌──────────────────────┐  │
│   │ langfuse-web        │◀────│ langfuse-mcp (NEW)   │  │
│   │ langfuse-worker     │     │ python:3.12-slim     │  │
│   │ langfuse-clickhouse │     │ FastMCP/HTTP+SSE     │  │
│   │ langfuse-postgres   │     │ port 4000 (internal) │  │
│   │ langfuse-redis      │     └──────────┬───────────┘  │
│   │ langfuse-minio      │                │              │
│   └─────────────────────┘                │              │
│            ▲                             │              │
│            │ Public REST API             │              │
│            │ (basic auth pk:sk)          │              │
│            │                             │              │
│   ┌────────┴─────────────────────────────┴──────────┐   │
│   │ traefik (n8n-prod_default)                      │   │
│   │ langfuse-mcp.srv1112039.hstgr.cloud (TLS)       │   │
│   └─────────────────────────────────────────────────┘   │
└────────────────────┬─────────────────────────────────────┘
                     │ HTTPS (Bearer MCP_AUTH_TOKEN)
                     │
       ┌─────────────┴───────────────┐
       │                             │
   ┌───▼────────────┐         ┌──────▼─────────┐
   │ Claude Code    │         │ Codex CLI      │
   │ (laptop / VPS) │         │ (laptop / VPS) │
   │ .mcp.json      │         │ ~/.codex/...   │
   │ + SessionStart │         │ + skill        │
   │   hook         │         │   wrapper      │
   └────────────────┘         └────────────────┘
```

### 4.1 Why on the VPS, not local

- The CLIs that operate on prod (deploys, hotfixes, on-call work) run from the laptop, so the server must be reachable over the public internet — Traefik already does TLS termination on `n8n-prod_default`.
- Putting it next to Langfuse means single-digit-ms request latency for `list_observations` queries that may scan thousands of rows.
- Production credentials (`pk`/`sk`) never need to leave the VPS.

### 4.2 Why one MCP server, not stdio per shell

- **Stdio per shell** would mean every laptop session re-exchanges credentials. Too many copies of `pk`/`sk`.
- **Stdio with a thin local proxy** to the remote API is fine for personal use but breaks any non-laptop session (Codex on the VPS, GitHub Actions self-hosted runner sessions). One HTTP server services them all.
- HTTP/SSE transport is supported by both Claude Code (`.mcp.json` `type: "http"` or `type: "sse"`) and Codex CLI (`~/.codex/config.toml` `[mcp_servers.langfuse]` with `transport = "http"` and `url = ...`).

### 4.3 What sits next to it on the network

- `n8n-prod_default` already hosts traefik, langfuse-web, n8n, and the runner replicas. Adding one more compose service in the langfuse compose project keeps the deployment story identical to existing services.
- Override pattern mirrors `infra/compose/langfuse/docker-compose.yml` §langfuse-web: traefik labels for TLS via `mytlschallenge`, attach to `traefik` external network.

---

## 5. Components

### 5.1 `langfuse-mcp` server

- Image: locally built `ghcr.io/taimooralam/job-search/langfuse-mcp:latest` from a small `Dockerfile.langfuse-mcp` under `infra/docker/`.
- Source: `src/observability/langfuse_mcp/` (new).
  - `server.py` — wires FastMCP (or `mcp` Python SDK) to `LangfuseClient`.
  - `client.py` — async wrapper around the Langfuse Public REST API.
  - `aggregations.py` — error fingerprinting, top-N grouping, time-bucketed rollups.
  - `tools/` — one module per tool listed in §7.
  - `resources/` — MCP resource handlers for browsable URIs.
  - `subscriptions/` — SSE subscription handlers.
  - `auth.py` — bearer-token middleware.
- Stateless. No DB, no local cache beyond per-process LRU. All state lives in Langfuse.
- Logs to stdout in JSON; collected by Docker's default driver. Rotation via `compose.yaml` `logging.options.max-size`.
- Health endpoint `/healthz` returns `{ok: true, langfuse_reachable: bool, last_check_ms: int}`.

### 5.2 `src/observability/errors.py` (instrumentation)

A small library that the existing emitters can import, with one entry point:

```python
def record_error(
    *,
    session_id: str,
    trace_id: str | None,
    pipeline: Literal["preenrich", "cv_assembly", "runner", "scout", "ad_hoc"],
    stage: str,
    exc: BaseException,
    metadata: dict[str, Any] | None = None,
    severity: Literal["WARN", "ERROR", "FATAL"] = "ERROR",
) -> None: ...
```

Behavior:

1. Captures `exc.__class__.__name__`, the message, and the **last 8 traceback frames** (no full stack — bounded payload).
2. Computes a `fingerprint` = SHA-1 of `f"{exc.__class__.__name__}|{repo_relative_posix_path}|{top_frame_func}"`. **Drop `lineno` from the hash** so harmless refactors don't fork the bucket; keep `top_frame_lineno` as observation metadata only. **Normalise to repo-relative POSIX paths** (`Path(top_frame_file).relative_to(REPO_ROOT).as_posix()`) so Windows/Linux runs of the same bug fingerprint identically.
3. Emits a Langfuse `event` (or short span) with name `error.<pipeline>.<stage>` and `level="ERROR"` (Langfuse-native severity field).
4. Includes `git_sha`, `host`, `env` (from `SCOUT_ENV`), `cli` (from `SCOUT_CLI` if set), and the optional caller-provided `metadata`.
5. Best-effort, never raises. Same defensive pattern as `SearchTracingSession`.

**Reuse contract** — `record_error` MUST reuse existing primitives in `src/pipeline/tracing.py` rather than re-implementing them:

- `_langfuse_config()` for env-var resolution (`LANGFUSE_HOST` with fallback to `LANGFUSE_BASE_URL`, plus pk/sk).
- `_sanitize_langfuse_payload` for redaction. Promote it to module-public (`sanitize_langfuse_payload`) if currently underscore-prefixed; keep an underscore alias for back-compat.
- The `Langfuse(host=..., public_key=..., secret_key=...)` initialisation pattern with try/except + `logger.warning()` + `self.enabled=False` on failure.

**Project selection** — driven by env vars, not function arguments:

- `SCOUT_LANGFUSE_PROJECT` (defaults to `scout-prod`) explicit override.
- `SCOUT_LANGFUSE_DEV=true` shortcut: swaps to the `scout-dev` pk/sk pair (`LANGFUSE_DEV_PUBLIC_KEY` / `LANGFUSE_DEV_SECRET_KEY`). Default for any process invoked via `scripts/observability/run_with_tracing.py`.

This is the bridge that gives the MCP server something **deterministically queryable** to summarize. Existing emitters will be retrofitted opportunistically; the library is non-load-bearing — the MCP server still works against any trace 4.3.8 or earlier code produced.

### 5.3 CLI configuration

- **Claude Code** (project): `.mcp.json` adds a `langfuse` server:
  ```json
  {
    "mcpServers": {
      "langfuse": {
        "type": "http",
        "url": "https://langfuse-mcp.srv1112039.hstgr.cloud/mcp",
        "headers": { "Authorization": "Bearer ${LANGFUSE_MCP_TOKEN}" }
      }
    }
  }
  ```
  `.mcp.json` remains untracked local config — added to `.gitignore` in the same PR. If a checked-in sample is needed for onboarding, ship it as `.mcp.example.json` only. Plus a `SessionStart` hook (§11) that calls one MCP tool and injects the result.
- **Codex CLI** (global, since the user runs Codex from multiple repos): config file lives at:
  - Laptop (Windows): `%USERPROFILE%\.codex\config.toml`
  - Laptop (Unix shells, including WSL/Git Bash): `~/.codex/config.toml`
  - VPS host: `/root/.codex/config.toml` — deployed by `infra/scripts/install-vps-codex-config.sh` (idempotent; templated from `infra/codex/vps-config.toml.template`).
  - **`oc` container**: `/home/node/.codex/config.toml` (the `oc` service drops to user `node`; do **not** write under `/root`). Written at container start by an entrypoint shim that renders the template via Python (`python -c "import os, string; ..."`) — do **not** assume `envsubst` is present. After render: `chown -R node:node /home/node/.codex && chmod 0600 /home/node/.codex/config.toml`. If `envsubst` is preferred, install `gettext-base` explicitly in the Dockerfile.
  All four locations get the same content:
  ```toml
  [mcp_servers.langfuse]
  transport = "http"
  url = "https://langfuse-mcp.srv1112039.hstgr.cloud/mcp"
  headers = { Authorization = "Bearer ${LANGFUSE_MCP_TOKEN}" }
  ```
  Plus three Codex skills: `langfuse-context` (proactive, injects digest at session start), `langfuse-watch` (user-invoked SSE on `errors/live`), `langfuse-tail` (user-invoked tail of one session).

**Token plumbing rules (do not violate):**

- Do **not** place `LANGFUSE_MCP_TOKEN` in a shared compose `.env` consumed by unrelated services (n8n, runners, postgres, etc.). Mount it only into `langfuse-mcp` and `oc` via a service-scoped `env_file` (e.g. `/root/langfuse-mcp/.env` for the server, `/root/oc/.env.langfuse` for the `oc` service) or a Docker secret.
- Do **not** put the token on the command line. Hooks, aliases, and skills must read it from the process env or from a chmod-0600 file — never `curl -H "Authorization: Bearer $LANGFUSE_MCP_TOKEN"` directly in argv (it leaks via `ps`, shell history, hook stdout capture, and CI logs). All such call sites go through `infra/scripts/langfuse_digest.py` (or a small `python -c` wrapper) that puts the token in an `httpx`/`requests` `headers=` dict it constructs in-process.
- The VPS token lives in `/root/job-runner/.env` (the existing credential drop spot per `docs/current/VERCEL_DEPLOYMENT_GUIDE.md`). The `oc` service receives a copy in its own `env_file`, **not** by being added to the shared n8n-prod env.

---

## 6. Langfuse projects and tagging

Two Langfuse projects:

| Project | Purpose | Public key prefix |
|---|---|---|
| `scout-prod` | Existing prod traces (the current `discovery-prod` project, renamed if useful, or aliased) | `lf_pk_a3172b0c…` (already in use) |
| `scout-dev`  | Dev/local traces emitted by `python scripts/...` runs and tests with `SCOUT_LANGFUSE_DEV=true` | new |

Mandatory tags on every trace and observation:

- `env`: `prod` \| `dev` \| `staging`
- `pipeline`: `preenrich` \| `cv_assembly` \| `runner` \| `scout` \| `ad_hoc`
- `cli`: `claude` \| `codex` \| `none` (set when emitted from a CLI session)
- `git_sha`: short sha
- `host`: hostname
- `pipeline_id`: `runner` \| `codex` (per `iteration-4.3-candidate-evidence-…` §3.1)

The MCP server's tool surface filters on these by default unless overridden. Most tools default to `env=prod` to keep the dev firehose out of the way.

---

## 7. MCP tool surface (read-only v1)

All tools accept a `project` parameter (default `scout-prod`) and an optional `env` filter (default `prod`).

### 7.1 Tools

| Tool | Purpose | Returns |
|---|---|---|
| `langfuse.health()` | Sanity check the MCP server can reach Langfuse and get fresh data | `{ok, langfuse_reachable, last_event_ts, ingestion_lag_seconds}` |
| `langfuse.error_summary(window_minutes, top_n=10)` | Top error fingerprints in the window | List of `{fingerprint, error_class, message_preview, count, first_seen, last_seen, sample_trace_id, pipelines, stages}` |
| `langfuse.list_recent_errors(window_minutes, severity_min="ERROR", pipeline?, stage?, limit=50)` | Raw list of recent error observations | Array of `error_observation` |
| `langfuse.get_trace(trace_id, include_observations=true)` | Full trace + (optional) observations + scores | `{trace, observations[], scores[]}` |
| `langfuse.get_observation(observation_id)` | Single span/event/generation | `observation` |
| `langfuse.search_traces(filters, limit=50)` | Trace-level search by `session_id`, `name`, `level`, `tags`, `time_range`, `metadata` | Array of `trace` |
| `langfuse.list_sessions(filters, limit=50)` | Session rollups | Array of `{session_id, started_at, ended_at, total_observations, error_count, total_cost_usd, last_status}` |
| `langfuse.get_session(session_id)` | One session timeline | `{session, traces[], events[]}` |
| `langfuse.cost_today(group_by="pipeline")` | Today's cost rollup | `[{group, total_cost_usd, observation_count}]` |
| `langfuse.get_score(trace_id_or_observation_id)` | All scores attached | `[score]` |
| `langfuse.diff_traces(trace_id_a, trace_id_b)` | Side-by-side metadata diff for two traces of the same `name` | `{a, b, diff[]}` |
| `langfuse.find_session_for_job(level2_job_id)` | Convenience: maps `level2_job_id` to canonical `session_id = f"job:{level2_job_id}"` per 4.3.8 §9 | `{session_id, exists, trace_count}` |
| `langfuse.tail_session(session_id, since_ts?)` | Returns observations newer than `since_ts` for one session. Backs the `/langfuse-tail` skill — when called with no `since_ts`, returns the most recent 50 observations and a `cursor` to use as `since_ts` for the next poll. | `{observations[], cursor}` |
| `langfuse.find_session_for_recent_run(pipeline, env="prod")` | "Tail the last preenrich run" convenience — returns the most recent `session_id` for the named pipeline in the env. | `{session_id, started_at, status}` |

Each tool's input schema constrains `window_minutes` to ≤ 24 h, `limit` to ≤ 200, and forbids unbounded scans. `langfuse.search_traces` requires at least one filter to prevent accidental whole-project dumps.

### 7.2 Resources (browseable URIs)

| URI | Behavior |
|---|---|
| `langfuse://errors/last-1h` | Renders `error_summary(60)` as Markdown |
| `langfuse://errors/last-24h` | Same, 1440-minute window |
| `langfuse://traces/{trace_id}` | Markdown render of the trace |
| `langfuse://sessions/{session_id}` | Markdown render of the session timeline |
| `langfuse://summary/today` | Markdown digest: ingestion health, cost, top errors, top sessions by error count |
| `langfuse://job/{level2_job_id}` | Resolves to the canonical session and renders it |

Resources exist to make the data **mention-friendly** in chat. A user can paste `langfuse://job/68d4...` and the model gets the full timeline without calling a tool.

### 7.3 Subscriptions

| Channel | Behavior |
|---|---|
| `langfuse://errors/live` | SSE; emits a JSON event per new observation with `level=ERROR` (env filter respected). Always-on; backs the push-on-error UX. |
| `langfuse://session/{session_id}/tail` | SSE; emits every new span/event for that session as Langfuse ingests them. User-invoked via `/langfuse-tail`; not subscribed automatically. |
| `langfuse://job/{level2_job_id}/live` | Convenience alias: resolves to `langfuse://session/job:{level2_job_id}/tail`. |

The MCP server polls Langfuse at 5 s intervals (configurable; default tuned to be ≤ 1 % of the worker's QPS budget) and forwards new rows to subscribers. No long-poll on Langfuse itself; we accept ≤ 5 s freshness.

**Polling MUST be shared per upstream key**, with one upstream poll fanning out to all subscribers on the same channel. Never poll Langfuse once per connected client. Rules:

- One `Poller` instance per `(project, channel_kind, channel_key)` tuple — e.g. all subscribers to `langfuse://session/abc123/tail` share one upstream poll.
- `max_concurrent_tails` (default `25`) caps total active tail subscriptions; new connects past the cap get a 429 with `{degraded: true, reason: "tail_capacity"}` and a hint to retry.
- Adaptive backoff on upstream `429`: exponential with jitter, max interval 60 s, never tighter than 1 s.
- Idle-session expiry: tail pollers shut down 60 s after the last subscriber disconnects.
- Live notifications (§11) are deduped by `(project, env, fingerprint)` with a 5-minute cooldown and a count-delta threshold (only notify if the bucket grew by ≥ N since last notification, default N=1 for new fingerprints, N=10 for repeat fingerprints). Infrastructure-class events (e.g. `connection_reset`, `dns_temporary_failure`) are tagged `infra=true` at emission and **never** trigger proactive user-facing messages.

---

## 8. Auth and deployment

### 8.1 Bearer token

`LANGFUSE_MCP_TOKEN` is a 32-byte URL-safe random string generated once and stored in:

- VPS `/root/langfuse-mcp/.env` (server side, mode 0600)
- VPS `/root/oc/.env.langfuse` (oc-only env_file, mode 0600) — **not** in the shared n8n-prod compose env
- Local `~/.config/scout-secrets.env` or wherever the user keeps shell secrets (client side, mode 0600)

**Rotation runbook (4 steps, ~60 s overlap window):**

1. **Accept old + new in parallel.** Set `LANGFUSE_MCP_TOKENS=old,new` (comma-separated) on the server side and `kill -HUP <pid>` so it accepts both for the overlap window. Both old and new clients pass auth.
2. **Update client secret stores.** Rewrite `~/.config/scout-secrets.env` on each laptop, `/root/oc/.env.langfuse` on the VPS, and any CI secret store. New `LANGFUSE_MCP_TOKEN=<new>` everywhere.
3. **Restart/reload clients.** `docker compose -p oc up -d` to reload `oc`; close-and-reopen any active Claude Code / Codex sessions on the laptop so they pick up the new env.
4. **Remove old token.** Set `LANGFUSE_MCP_TOKENS=new` on the server, `kill -HUP <pid>` again. Old clients now 401.

The README documents this as four explicit operator commands, not one. Token rotation is a §12.4 gate — it must be exercised at least once successfully before declaring Phase A complete.

### 8.2 Langfuse credentials

`LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are read from the same `.env`. Two pairs are loaded so the MCP can serve both projects:

```env
LANGFUSE_HOST=http://langfuse-web:3000          # in-cluster; bypasses Traefik
LANGFUSE_PROD_PUBLIC_KEY=pk-prod-...
LANGFUSE_PROD_SECRET_KEY=sk-prod-...
LANGFUSE_DEV_PUBLIC_KEY=                        # optional; see degraded-mode below
LANGFUSE_DEV_SECRET_KEY=
LANGFUSE_DEFAULT_PROJECT=scout-prod
MCP_BIND=0.0.0.0:4000
LANGFUSE_MCP_TOKEN=...
LANGFUSE_MCP_ALLOWED_TIME_WINDOW_HOURS=24
```

**Degraded-mode rules** (so missing `scout-dev` keys never block prod bring-up):

- If `LANGFUSE_PROD_PUBLIC_KEY`/`LANGFUSE_PROD_SECRET_KEY` are missing or invalid: server refuses to start (prod is the load-bearing path).
- If `LANGFUSE_DEV_*` are missing: server starts in `prod_only` mode. Calls with `project=scout-dev` (or env=dev filter) return `{degraded: true, reason: "project_unconfigured", project: "scout-dev"}`. `scout-prod` calls remain available.
- `health()` reports `dev_configured: bool` so the operator can see which mode the server booted into.

**Local-laptop dev keys** — `LANGFUSE_DEV_PUBLIC_KEY` and `LANGFUSE_DEV_SECRET_KEY` are stored in the operator's local secret file (`~/.config/scout-secrets.env` on Unix, `%USERPROFILE%\.scout-secrets.env` on Windows) for dev-only emission from the laptop. **Prod keys never leave the VPS.** If laptop dev emission is undesired (e.g. shared workstation), the operator skips the local dev keys and emits dev errors from the VPS instead via `ssh root@vps -- 'SCOUT_LANGFUSE_DEV=true python -m scripts.observability.seed_dev_errors ...'`.

### 8.3 Compose file

`infra/compose/langfuse-mcp/docker-compose.yml` (new) defines the single service.

**Network requirement (do not get this wrong):** `langfuse-mcp` MUST join the same Docker network that `langfuse-web` is attached to in order to resolve `http://langfuse-web:3000`. A separate compose project's `default` network is **not** sufficient — Docker only enables service-name DNS within the same network. Two equally valid options:

- **Option A (preferred):** add `langfuse-mcp` as an additional service to the existing `infra/compose/langfuse/docker-compose.yml` so it joins that compose project's `default` network natively. Same lifecycle, same `docker compose -p langfuse` operator surface.
- **Option B:** keep `langfuse-mcp` in its own compose project but attach it to a shared external network — either the existing `langfuse_default` (declared `external: true`) **or** a new dedicated `langfuse_internal` network created once with `docker network create langfuse_internal` and added to both `langfuse-web` and `langfuse-mcp`.

The Traefik network attachment (`n8n-prod_default`) is orthogonal to this — Traefik sees the service via its router labels regardless of which internal network it shares with langfuse-web.

```yaml
services:
  langfuse-mcp:
    image: ghcr.io/taimooralam/job-search/langfuse-mcp:latest
    container_name: langfuse-mcp           # so `docker exec langfuse-mcp ...` works as written in §12
    restart: always
    env_file: /root/langfuse-mcp/.env      # service-scoped; not the n8n-prod shared env
    networks:
      - langfuse_internal                  # Option B; Option A drops this and inherits langfuse_default
      - traefik
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:4000/healthz', timeout=3).status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 5
    labels:
      - traefik.enable=true
      - traefik.docker.network=n8n-prod_default
      - traefik.http.routers.langfuse-mcp.rule=Host(`langfuse-mcp.srv1112039.hstgr.cloud`)
      - traefik.http.routers.langfuse-mcp.tls=true
      - traefik.http.routers.langfuse-mcp.entrypoints=web,websecure
      - traefik.http.routers.langfuse-mcp.tls.certresolver=mytlschallenge
      - traefik.http.services.langfuse-mcp.loadbalancer.server.port=4000

networks:
  traefik:
    external: true
    name: n8n-prod_default
  langfuse_internal:
    external: true
```

The healthcheck uses Python (always present in the `python:3.12-slim` base) instead of `wget` (which is not in slim by default and adds an apt install otherwise).

DNS for `langfuse-mcp.srv1112039.hstgr.cloud` is added as an A record alongside the existing `langfuse.srv1112039.hstgr.cloud` entry — same Hostinger zone, same TTL.

### 8.3.1 First-deploy bootstrap (manual, one-time)

The CI deploy workflow assumes a lot of state already exists. The very first bring-up is manual and ordered:

1. **Create `/root/langfuse-mcp/.env`** on the VPS (chmod 0600) with the prod keys, an empty dev key block, and a freshly-generated `LANGFUSE_MCP_TOKEN`.
2. **Create the `scout-dev` Langfuse project** in the Langfuse web UI (or skip — server will boot in `prod_only` degraded mode). Capture pk/sk; populate the `LANGFUSE_DEV_*` lines if you want dev coverage now.
3. **Add the DNS A record** for `langfuse-mcp.srv1112039.hstgr.cloud` and wait for resolution (`dig +short` returns the VPS IP).
4. **Create the shared internal network if using Option B** — `docker network create langfuse_internal` and `docker network connect langfuse_internal langfuse-web`.
5. **First boot manually** — `cd /root/langfuse-mcp && docker compose pull && docker compose up -d`. Watch logs: `docker logs -f langfuse-mcp`.
6. **Wait for Traefik cert issuance** — first HTTPS request to `https://langfuse-mcp.srv1112039.hstgr.cloud/healthz` triggers ACME `mytlschallenge`. May take up to 60 s on the first try.
7. **Verify in-cluster reachability** — `docker exec langfuse-mcp python -c "import urllib.request; print(urllib.request.urlopen('http://langfuse-web:3000/api/public/health', timeout=3).status)"` — must print `200`. The `/api/public/health` endpoint is unauthenticated; do not use `/api/public/projects` (which requires basic auth pk:sk and will spuriously fail this probe).
8. **Only then enable the `deploy-langfuse-mcp.yml` workflow** by merging the PR that adds it. Until this point the workflow file lives on a feature branch.

Phase A (§13) does not start its 24 h soak until all eight bootstrap steps complete.

### 8.4 CI/CD

- The image is built and pushed by a new GitHub Actions workflow `deploy-langfuse-mcp.yml`, triggered on `src/observability/**` and `infra/{docker,compose}/langfuse-mcp/**` changes.
- The existing self-hosted runner on the VPS (`actions.runner.taimooralam-job-search.vps-runner-1`) `docker compose pull && up -d`s after the image is published. Same idiom as the runner's deploy.
- Smoke step at the end of the workflow: `curl -fsS https://langfuse-mcp.srv1112039.hstgr.cloud/healthz` and assert `ok=true`.

---

## 9. Error ingestion contract

### 9.1 Where errors come from

- **Prod**: existing Langfuse traces emitted by `src/pipeline/tracing.py` and (once 4.3.8 lands) `src/cv_assembly/tracing.py`. Whatever the LangGraph runner emits today is already there.
- **Dev**: traces emitted from `python scripts/vps_run_*.py` runs, smoke scripts (`scripts/smoke_*.py`), and `pytest` runs that opt in via `SCOUT_LANGFUSE_DEV=true`. By default tests do **not** ingest, to avoid rate-limit grief.
- **Ad-hoc**: a one-line `record_error(...)` call inside `try/except` blocks the operator wants instrumented.

### 9.2 What "error" means at the MCP layer

The MCP server treats any of the following as an error for `list_recent_errors`/`error_summary`:

1. Observation with Langfuse `level == "ERROR"`.
2. Observation with `name` matching `^error\.` (the convention `record_error` uses).
3. Observation whose `output` includes a JSON object with `error_class` set.
4. Trace with `level == "ERROR"` at the root.

Exception classes are aggregated by `fingerprint` (§5.2 step 2). The fingerprint is what makes "the same bug failing 1000 times" collapse into one row.

### 9.3 Required tags on dev emissions

Dev emissions must set:

- `env=dev`
- `host=$(hostname)` (so multi-machine dev sessions disambiguate)
- `git_sha=$(git rev-parse --short HEAD)` (set automatically by a `src/observability/env.py` helper)
- `cli` if invoked from a Claude Code or Codex session (the hook in §11 sets this in the shell env)

### 9.4 What we will not emit

- Raw stack frames beyond depth 8.
- Full LLM prompts/responses inside an error event (sanitized via existing `_sanitize_langfuse_payload` if reused).
- Anything matched by the existing payload-discipline rules in 4.3.8 §8.5.

---

## 10. Dev/prod parity

- **Same client.** `record_error` is the only error-emission API. Dev and prod call the same function; only the env tag and Langfuse project key differ.
- **Same MCP queries.** A query like `langfuse.error_summary(60)` works identically against prod and dev; the operator switches via the `project` parameter or the resource URI suffix.
- **Bridging script.** `scripts/observability/seed_dev_errors.py` (new) emits a synthetic error to the dev project at deploy time so the MCP server's `langfuse.health()` can verify dev ingestion is alive without waiting for an organic dev failure.
- **CLI shadow runs.** A wrapper `scripts/observability/run_with_tracing.py <module>` ensures any ad-hoc dev invocation gets a Langfuse session id, traces stdout/stderr, and emits a final `success`/`error` observation. Recommended (not required) for local repro of prod issues.

---

## 11. Automation: hooks and push notifications

### 11.1 Claude Code

Project-scope `.claude/settings.local.json` adds a `SessionStart` hook. The hook **must not put the bearer token on the command line** (leaks via `ps`, shell history, hook stdout capture). Both bash and PowerShell variants ship from day one — they are not optional fallbacks; the operator's actual shell decides which fires.

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [
        {
          "type": "command",
          "shell": "bash",
          "command": "python infra/scripts/langfuse_digest.py --window 120 --top 5",
          "timeout": 8
        },
        {
          "type": "command",
          "shell": "powershell",
          "command": "python infra/scripts/langfuse_digest.py --window 120 --top 5",
          "timeout": 8
        }
      ]
    }]
  }
}
```

`infra/scripts/langfuse_digest.py` reads `LANGFUSE_MCP_TOKEN` from process env and constructs the `Authorization` header in-process via `httpx`/`requests`. The token never appears in argv. The script writes a `<system-reminder>`-wrapped Markdown digest to stdout.

The MCP server exposes a non-MCP `GET /digest` JSON-and-Markdown endpoint specifically for hook consumption (cheaper than spinning up an MCP session for one-shot reads).

A complementary `Notification` hook listens on `langfuse://errors/live` SSE and fires a `systemMessage` when a new `level=ERROR` lands during an active session. This is the **unsolicited push** path: the model gets re-woken by prod failures. Subject to the dedup rules in §7.3 — repeats and `infra=true` events do not fire user-facing messages.

### 11.2 Codex CLI

Codex skill `langfuse-context` (under `.codex/skills/langfuse-context/`) declared as a `proactive` skill — invoked at session start if the project root contains `.codex/skills/langfuse-context/SKILL.md`. The skill calls the MCP `langfuse.error_summary` tool and pastes the digest.

A second skill `langfuse-watch` is user-invoked (`/langfuse-watch`) and runs the SSE subscription for the duration of the Codex session.

### 11.3 Operator one-liners

Documentation ships **both bash and PowerShell variants from day one** (the repo runs on Windows often enough that PowerShell is not optional). All variants invoke `infra/scripts/langfuse_digest.py` (or its tail counterpart) so the bearer token never appears in argv.

**Bash** (`~/.bashrc`):
```sh
alias lf-recent='python infra/scripts/langfuse_digest.py --window 60 --top 10'
lf-job() { python infra/scripts/langfuse_digest.py --job "$1"; }
lf-tail() { python infra/scripts/langfuse_tail.py --session "$1"; }
```

**PowerShell** (`$PROFILE`):
```powershell
function lf-recent { python infra/scripts/langfuse_digest.py --window 60 --top 10 }
function lf-job    { param($id) python infra/scripts/langfuse_digest.py --job $id }
function lf-tail   { param($id) python infra/scripts/langfuse_tail.py --session $id }
```

Both rely on `LANGFUSE_MCP_TOKEN` already being in the shell env via `~/.config/scout-secrets.env` (Unix) or `%USERPROFILE%\.scout-secrets.env` (Windows).

### 11.4 OpenClaw `oc` container

The `oc` service (defined in `infra/compose/n8n-prod/docker-compose.yml`) already bundles the Codex CLI and **drops to user `node`**. Once `LANGFUSE_MCP_TOKEN` is in its scoped env_file and `/home/node/.codex/config.toml` is rendered (entrypoint shim), every Codex session inside the container gets the same `langfuse.*` tool surface as the laptop.

- **Token isolation.** Use a service-scoped `env_file: /root/oc/.env.langfuse` on the `oc` service definition; **do not** add `LANGFUSE_MCP_TOKEN` to the shared n8n-prod compose env where unrelated services (n8n, postgres, Redis) would inherit it. File mode 0600.
- **Render path is `/home/node/.codex/config.toml`** (not `/root/...` — the container drops privileges). The Dockerfile must `mkdir -p /home/node/.codex && chown -R node:node /home/node/.codex` and the entrypoint must `chmod 0600 /home/node/.codex/config.toml` after render.
- **Renderer.** Use a tiny Python step (Python is already in the image) instead of assuming `envsubst`: `python -c "import os,pathlib; pathlib.Path('/home/node/.codex/config.toml').write_text(pathlib.Path('/home/node/.codex/config.toml.template').read_text().replace('\${LANGFUSE_MCP_TOKEN}', os.environ['LANGFUSE_MCP_TOKEN']))"`. If `envsubst` is preferred, install `gettext-base` explicitly and document it.
- **No SSE inside the container.** Traefik idle timeouts plus the multi-hop nature of internal Docker networking make long-lived SSE fragile here. Instead, the gateway loop polls `/digest?window=15&top=5` every 5 minutes via a tiny internal cron-style helper baked into the image — fan-out via the shared poller pattern in §7.3 happens server-side, so this poll does not multiply upstream load.
- **Proactive context.** The `langfuse-context` skill is baked into the image at `/home/node/.codex/skills/langfuse-context/`. The OpenClaw entrypoint runs it once at gateway boot so the agent has a recent-errors digest before its first task.
- **Token surface.** Never logged. The render step writes file with 0600. The skill calls go through `python` helpers that read the token from `os.environ` in-process.

---

## 12. Hard prerequisites

Before the MCP server can be claimed live:

1. **DNS**: A record for `langfuse-mcp.srv1112039.hstgr.cloud` resolves to the VPS public IP. Verify with `dig`.
2. **TLS**: Traefik certresolver `mytlschallenge` issues a cert. Verify with `curl -vI https://langfuse-mcp.srv1112039.hstgr.cloud/healthz`.
3. **Langfuse `scout-prod` project exists** with valid `pk`/`sk` and the keys are in `/root/langfuse-mcp/.env`. `scout-dev` is **not** a hard prereq — without it the server boots in `prod_only` degraded mode (§8.2). It becomes a prereq for Phase B½ only when dev coverage is wanted.
4. **Bearer token rotated** at least once successfully end-to-end via the 4-step runbook (§8.1). A token rotation that takes the system out for >5 s fails this gate.
5. **Langfuse Public API reachable** from the MCP container against in-cluster `http://langfuse-web:3000`. Verify with `docker compose exec langfuse-mcp python -c "import urllib.request; print(urllib.request.urlopen('http://langfuse-web:3000/api/public/health', timeout=3).status)"` (the unauthenticated `/api/public/health` endpoint, **not** `/api/public/projects` which requires basic auth and would spuriously fail this network probe).
6. **CLI clients can authenticate** from at least the laptop and from a Codex CLI session running inside the VPS (proves both directions).
7. **`record_error` smoke**: emitting one synthetic dev error makes it visible via `langfuse.list_recent_errors` within 30 s.
8. **`/digest` endpoint** returns valid JSON and the SessionStart hook exits 0 in under 5 s on a cold call.
9. **SSE channel** delivers an event for a synthetic dev error within 10 s.

If any prerequisite is unmet, the rollout state is **observe-only** and the CLI configurations are not flipped on user machines.

---

## 13. Rollout phases

| Phase | Audience | Gate to advance |
|---|---|---|
| A — server up, no clients wired | self-test only | All §12 prereqs pass for 24 h |
| B — single laptop wired | one machine; manual queries | One full dev session uses the MCP without errors; one prod-error round-trip from `record_error` → `langfuse.error_summary` confirmed |
| B½ — OpenClaw container wired | `oc` Codex picks up the MCP | `docker exec oc codex exec "use langfuse.health"` returns `ok=true`; one synthetic prod error appears in the gateway agent's startup digest |
| C — both CLIs configured | Claude Code + Codex on the laptop | SessionStart hook injects a digest in three consecutive sessions without timeout; live SSE delivers a synthetic prod error inside an active session; `/langfuse-tail <session_id>` streams ≥1 event within 10 s of an emitter writing it |
| D — VPS-side Codex configured | Codex on the VPS too | One full preenrich/cv_assembly debug session uses `langfuse.get_session` for live triage |
| E — soak | passive | No MCP-server-internal errors for 7 days; no token rotation incidents |

Phases A through C take ≤ 1 week to walk if no surprises; D and E are continuous.

---

## 14. Failure modes and how the MCP behaves

| Failure | MCP behavior |
|---|---|
| Langfuse Public API down | `health()` returns `langfuse_reachable=false`, `last_event_ts=null`. All tools return `{degraded: true, reason: "langfuse_unreachable"}`. Do **not** 5xx — the model needs to know this is a known state, not a server bug. |
| Langfuse rate-limited | Per-tool 429 → exponential backoff with jitter, max 3 retries. Surface as `{degraded: true, reason: "rate_limited"}` if exhausted. |
| Bearer token wrong | 401 from MCP. Hook short-circuits cleanly. |
| Subscription stream closed by Traefik idle timeout | Re-establish on the client; the MCP server emits `keepalive` SSE comments every 25 s. |
| Tool input out of bounds (`window_minutes > 1440`) | 400 with explicit error; tool schema documents the bound. |
| Slow query (>5 s) | Server emits a timing warning to its own logs and returns partial results with `{partial: true, queried_until: <ts>}`. Never blocks the CLI longer than 8 s. |
| Langfuse upstream unhealthy (clickhouse OOM, postgres failover, partial Langfuse upgrade) | `health()` returns `upstream_healthy=false` with a `reason` string. Tail subscriptions pause; new tail connects get 503 `{degraded: true, reason: "upstream_unhealthy"}`. Reads continue best-effort against any cached responses. |
| MCP server capacity (OOM under SSE fanout, > `max_concurrent_tails`) | New tails get 429 `{degraded: true, reason: "tail_capacity"}`. Existing tails kept. Scrape interval temporarily backs off. `health()` reports `subscriber_count`, `pollers_active`, `tail_capacity_remaining`. |
| Langfuse REST shape drift (response shape changed by an upstream version bump) | Per-tool 502 `{degraded: true, reason: "schema_mismatch", got: "...", expected: "..."}`. CI smoke step (§8.4) fails on unexpected shape so this is caught before being widely visible. |
| `scout-dev` project unconfigured (missing keys) | Server starts in `prod_only` mode. Calls with `project=scout-dev` return `{degraded: true, reason: "project_unconfigured", project: "scout-dev"}`. `scout-prod` calls remain available. |
| Live notification spam (repeat fingerprints, infrastructure noise) | Notifications deduped per §7.3: 5-min cooldown per `(project, env, fingerprint)`; count-delta threshold; `infra=true` events suppressed. Operator-facing messages stay rare and high-signal. |

---

## 15. Sub-plan split (if scope grows)

If the work overflows a single PR cleanly, split into:

- **4.4.1** — `langfuse-mcp` server itself (compose, image, tools, auth, deploy workflow, `/digest`, SSE).
- **4.4.2** — `src/observability/errors.py` + `src/observability/env.py` + the `scripts/observability/*` wrappers (the dev-side instrumentation half).
- **4.4.3** — CLI integration (`.mcp.json`, `~/.codex/config.toml`, hooks, skills, docs).

These split along strict boundaries: 4.4.1 owns server-side; 4.4.2 owns emitter-side; 4.4.3 owns client-side. None of them blocks the others if 4.4 ships as one.

---

## 16. Open questions / decisions deferred

1. **One project or two for dev?** Plan assumes two (`scout-prod`, `scout-dev`). If this proves noisy, fold dev into prod with hard `env=dev` filter at the MCP layer.
2. **Public API vs ClickHouse direct?** v1 is REST-only. Re-evaluate after 30 days of usage if any tool exceeds 5 s p50.
3. **Fingerprint algorithm.** §5.2 picks SHA-1 of `class|file|func|lineno`. If line numbers churn too fast (e.g., due to formatter rewrites), drop `lineno` and keep `class|file|func`. Track via a follow-up ADR.
4. **Write tools.** A `score_trace` tool is genuinely useful for the eval loop in 4.3.8. Defer to 4.4.4 or fold into 4.3.8 directly — owner decides at the time.
5. **Per-project tokens.** v1 uses one bearer token for the whole MCP. If the operator wants per-project ACL (e.g., dev-only access for an intern), revisit. Not blocking.
6. **Cross-machine session handoff.** When a laptop session pauses and resumes on the VPS, both CLIs should ideally see the same recent-errors digest. Today the SessionStart hook re-fetches anyway, so this is moot — confirm with one explicit test in Phase C.

---

## 17. Acceptance criteria

This iteration is done when:

1. `https://langfuse-mcp.srv1112039.hstgr.cloud/healthz` returns `{ok: true}` over TLS, served from the VPS.
2. From a laptop Claude Code session, `langfuse.error_summary(60)` returns the top-N prod errors of the last hour without manual auth setup beyond setting `LANGFUSE_MCP_TOKEN` in the shell env.
3. From a laptop Codex CLI session, the same call works with the same env var.
4. A `record_error(...)` call from `python -c "..."` on the laptop with `SCOUT_LANGFUSE_DEV=true` shows up via `langfuse.list_recent_errors(env="dev", window_minutes=10)` within 30 s.
5. A synthetic `level=ERROR` observation against the prod project triggers a `<system-reminder>` in an active Claude Code session within 10 s via the live subscription.
6. The `SessionStart` hook adds a digest to **every** new Claude Code session in this project, idempotently, with a hard 8 s timeout.
7. Token rotation is a documented one-line procedure that takes < 60 s and does not require a container rebuild.
8. The MCP server has zero direct dependencies on `src/cv_assembly/` or `src/preenrich/` — this plan ships independently of 4.3.* progress.
9. From inside the `oc` container (`docker exec -it oc bash` → `codex exec "use langfuse.error_summary(60)"`) the call succeeds with the same bearer token plumbing.
10. `/langfuse-tail <session_id>` (Claude Code or Codex) streams at least one new observation into the conversation within 10 s of an emitter writing it.

---

## 18. References

- `infra/compose/langfuse/docker-compose.yml` — Langfuse stack; the override pattern this plan mirrors
- `src/pipeline/tracing.py` — existing Langfuse client wrapper (`SearchTracingSession`, `ScrapeTracingSession`); reference implementation for the MCP's defensive style
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md` §8–§9 — span/event naming and session-id contract this plan reads from
- Langfuse Public API v3: `https://api.reference.langfuse.com/`
- Model Context Protocol: `https://modelcontextprotocol.io/specification`
- Anthropic Claude Code MCP config: `https://docs.claude.com/en/docs/claude-code/mcp`
- OpenAI Codex CLI MCP config: `https://github.com/openai/codex` (`config.toml`, `mcp_servers`)

---

## 19. Review-driven amendments (codex `gpt-5.4` deep review, 2026-04-27)

Source: `reports/iteration-4.4-codex-review.md`. Verdict was "needs Critical fixes first." All findings have been folded into the plan body above; this section is the audit trail.

### Critical (4) — applied in body

| Finding | Location applied |
|---|---|
| §8.3 network: separate compose project's `default` network does not let `langfuse-mcp` reach `langfuse-web` | §8.3 rewritten to require shared network (Option A or B), §8.3.1 step 4 added |
| §8.4 / §12 / §13: first-deploy bootstrap is missing — workflow assumes pre-existing image, env, DNS, TLS, projects | §8.3.1 added with 8 ordered manual steps; Phase A in §13 now starts only after bootstrap completes |
| §5.3 / §11.1 / §11.4: bearer-token leakage via shared compose env, argv `curl -H`, rendered config files | §5.3 token-plumbing-rules block added; §11.1 hook switched to `infra/scripts/langfuse_digest.py`; §11.4 oc switched to scoped env_file + 0600 + Python renderer |
| §4.1 / §8.2 / §10 / §17.4: laptop dev emission requires off-VPS dev secret distribution that was undefined | §8.2 expanded with explicit local-secret-file model and "prod keys never leave the VPS" rule; degraded `prod_only` mode added |

### Major (7) — applied in body

| Finding | Location applied |
|---|---|
| Missing `scout-dev` keys should not block prod bring-up | §8.2 degraded-mode block; §12.3 prereq #3 relaxed; §14 row added |
| `oc` runs as user `node`, not root; `envsubst` not guaranteed | §5.3 oc-row + §11.4 rewritten: `/home/node/.codex/...`, Python renderer, chown/chmod |
| Healthcheck used `wget` not present in `python:3.12-slim` | §8.3 compose YAML now uses Python `urllib.request` healthcheck |
| Per-subscriber polling would fan out to N upstream calls under load | §7.3 shared-poller-per-key contract added, plus `max_concurrent_tails`, adaptive backoff, idle expiry |
| Failure table missed upstream/capacity/schema-drift modes | §14 four new rows |
| Plan claimed independence from 4.3.8 but baked in `find_session_for_job` etc. | §7.1 — these are now gated behind `ENABLE_CANONICAL_JOB_SESSION=false` until 4.3.8 lands. **TODO: apply in body.** See "Pending edits" below |
| Token rotation as one-line claim is unsafe under active sessions | §8.1 replaced with 4-step accept-old+new → update clients → reload → drop-old runbook |
| Push notifications would spam on repeat fingerprints + infra noise | §7.3 dedup rules added; §11.1 references them; §14 row added |

### Minor (4) — applied in body

| Finding | Location applied |
|---|---|
| Fingerprint splits across Windows/Linux paths and after refactors moving lineno | §5.2 step 2 rewritten: `repo_relative_posix_path`, drop `lineno` from hash |
| `docker exec langfuse-mcp` requires `container_name` | §8.3 compose YAML now sets `container_name: langfuse-mcp` |
| Reachability probe hit auth-required endpoint | §12 prereq #5 switched to `/api/public/health` (unauthenticated) |
| Windows treated as fallback in a Windows-centric repo | §11.1 + §11.3 ship bash and PowerShell variants from day one |

### Nit (1) — applied in body

| Finding | Location applied |
|---|---|
| `.mcp.json` would be committed to git as written | §5.3 sentence added: untracked local config; sample as `.mcp.example.json` only |

### Pending edits (one Major still to apply in body)

The `ENABLE_CANONICAL_JOB_SESSION` gate on the four canonical-job-session features (`langfuse.find_session_for_job`, the `langfuse://job/{level2_job_id}` resource, the `langfuse://job/{...}/live` alias, and acceptance criterion #2's job-id mention) needs an inline edit in §7.1 / §7.2 / §7.3 / §17 to add the feature-flag note. Tracked as a pre-implementation TODO; will land in the same PR that creates `src/observability/langfuse_mcp/tools/find_session_for_job.py`.

---

## 20. Trace-listing tool: `langfuse.list_recent_traces` (added 2026-04-28)

Phase A bring-up shipped 5 of the 12 §7.1 tools: `health`, `error_summary`, `list_recent_errors`, `get_trace`, `get_session`. The 7 secondary tools were deferred per the joyful-pond execution plan ("incremental, after Phase A bring-up confirms the core surface"). The first user request that hit the gap was "get the last 5 Langfuse traces" — neither `search_traces` nor any list-traces method exists in `client.py`, and the upstream `GET /api/public/traces` is therefore unreachable through the MCP.

### 20.1 Decision: ship `list_recent_traces` first, defer `search_traces`

§7.1 specifies `langfuse.search_traces(filters, limit=50)` with the rule "requires at least one filter to prevent accidental whole-project dumps." Two paths to satisfy that rule:

| Option | Surface | Default-safe? | When to ship |
|---|---|---|---|
| `search_traces(filters, limit)` | open-ended; caller picks any filter | only if input validation enforces ≥ 1 filter | when an open-ended need actually surfaces |
| `list_recent_traces(window_minutes, limit, name?, session_id?, user_id?, tags?, env?)` | recency-anchored; `window_minutes` is the implicit "≥ 1 filter" | yes — `window_minutes` is mandatory and bounded ≤ 1440 | now |

The user-facing question ("last 5 traces", "last 5 traces from preenrich today") is always recency-anchored. A mandatory `window_minutes` is the natural single-filter shape and matches the existing `list_recent_errors` idiom. Ship that; revisit `search_traces` when an open-ended query need actually appears.

### 20.2 Tool input schema

| Field | Type | Default | Constraints |
|---|---|---|---|
| `window_minutes` | integer | 60 | 1–1440 |
| `limit` | integer | 50 | 1–100 (matches Langfuse upstream cap) |
| `name` | string | — | optional upstream `name` filter |
| `session_id` | string | — | optional upstream `sessionId` filter |
| `user_id` | string | — | optional upstream `userId` filter |
| `tags` | string[] | — | optional upstream `tags` filter |
| `env` | enum | — | `prod` \| `dev` \| `staging` — applied client-side via `metadata.env` |
| `project` | enum | `scout-prod` | `scout-prod` \| `scout-dev` |

### 20.3 Output shape

Returned as JSON-stringified text in the standard `{content:[{type:"text",text}]}` MCP envelope:

```json
{
  "ok": true,
  "project": "scout-prod",
  "window_minutes": 60,
  "count": 5,
  "traces": [
    {
      "id": "...",
      "name": "...",
      "timestamp": "...",
      "session_id": "...",
      "user_id": "...",
      "tags": [...],
      "release": "...",
      "version": "...",
      "input_preview": "...",   // first 200 chars
      "output_preview": "...",  // first 200 chars
      "metadata": { ... }
    }
  ]
}
```

### 20.4 Files changed

- `src/observability/langfuse_mcp/client.py` — add `list_traces(...)` (mirrors `list_observations` pattern; `_get_with_retry("/api/public/traces", params=...)`) and `list_recent_traces(window_minutes, limit, ...)` wrapper.
- `src/observability/langfuse_mcp/aggregations.py` — add `trace_summary(trace) -> dict` helper (pure, unit-tested).
- `src/observability/langfuse_mcp/server.py` — add 6th `_TOOL_DESCRIPTORS` entry and dispatch branch in `_call_tool`.
- `tests/observability/test_server.py` — add 6 tests (registration, happy path, limit clamp, window validation, env filter, degraded passthrough).
- `tests/observability/test_aggregations.py` — add `trace_summary` truncation test.

### 20.5 Still deferred (re-affirmed)

`search_traces`, `get_observation`, `list_sessions`, `cost_today`, `get_score`, `diff_traces`, `find_session_for_job`, `tail_session`, `find_session_for_recent_run`. Each is a discrete follow-up; none blocks `list_recent_traces`.
