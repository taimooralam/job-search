## Critical

- **§8.3, §12.5**: The network story is wrong as written: a separate compose project’s `default` network will not let `langfuse-mcp` reach `langfuse-web`, so the direct `http://langfuse-web:3000` checks are not valid.  
  **Remediation:** Replace the §8.3 paragraph with: `langfuse-mcp MUST join the same Docker network that langfuse-web is attached to for in-cluster API access (either a shared external network such as langfuse_internal, or the existing langfuse compose project). Do not rely on the langfuse-mcp compose project's default network for service discovery.` Also change §12.5 to use `docker compose exec langfuse-mcp ...` on that shared network.

- **§8.4, §12, §13**: First-ever deploy bootstrap is missing; the workflow assumes the image exists, `/root/langfuse-mcp/.env` exists, DNS resolves, TLS is issued, and both Langfuse projects already exist.  
  **Remediation:** Add a new subsection `### 8.3.1 First deploy bootstrap (manual, one-time)` with explicit order: `1. create /root/langfuse-mcp/.env`, `2. create scout-dev and capture pk/sk`, `3. add DNS A record and wait for resolution`, `4. start langfuse-mcp manually`, `5. wait for Traefik cert issuance`, `6. only then enable deploy-langfuse-mcp.yml`. Update Phase A to require this bootstrap completion before the 24h soak.

- **§5.3, §11.1, §11.4**: The bearer token leaks through the planned transport paths: shared `n8n-prod` compose env, inline `curl -H "Authorization: Bearer $LANGFUSE_MCP_TOKEN"` argv, and rendered config files inside containers.  
  **Remediation:** Change §5.3 to: `Do not place LANGFUSE_MCP_TOKEN in a shared compose .env consumed by unrelated services. Mount it only into langfuse-mcp and oc via service-scoped env_file or Docker secret.` Replace the hook and alias examples in §11.1/§11.3 with `python infra/scripts/langfuse_digest.py ...` or equivalent so the literal token never appears in process argv or shell history.

- **§4.1, §8.2, §10, §17.4**: Local dev emission is impossible or under-specified: `SCOUT_LANGFUSE_DEV=true` on the laptop requires a Langfuse dev secret key off-VPS, but the plan never defines that secret distribution model.  
  **Remediation:** Add to §8.2: `LANGFUSE_DEV_PUBLIC_KEY and LANGFUSE_DEV_SECRET_KEY are stored in the operator's local secret file for dev-only emission; prod keys never leave the VPS.` If that is unacceptable, change §10 and §17.4 to remove direct laptop emission and require dev synthetic errors to be emitted from the VPS only.

## Major

- **§8.2, §12.3, §14**: Missing `scout-dev` project keys currently look like a full rollout blocker, even though prod observability should be able to go live first.  
  **Remediation:** Add a §14 row: `scout-dev unconfigured -> server starts in prod_only degraded mode; project=scout-dev calls return {degraded: true, reason: "project_unconfigured"}; scout-prod remains available.` Change §12.3 to make `scout-dev` a gate for dev features, not for prod bring-up.

- **§5.3, §11.4**: The `oc` wiring is inconsistent with the current container model: the service drops to user `node`, but the plan writes `/root/.codex/config.toml` and assumes `envsubst` exists.  
  **Remediation:** Replace the `oc` path in §5.3/§11.4 with `/home/node/.codex/config.toml`; add `chown -R node:node /home/node/.codex && chmod 0600 /home/node/.codex/config.toml`; and explicitly require `gettext-base` or a small Python renderer instead of assuming `envsubst`.

- **§5.1, §8.3**: The healthcheck depends on tooling that is not guaranteed in the planned images; `python:3.12-slim` does not reliably include `wget`.  
  **Remediation:** Replace the compose healthcheck with a Python-based check or explicitly add `curl`/`wget` installation to the Dockerfile. Exact text to add: `The image MUST install the binary used by healthcheck, or healthcheck MUST be implemented in Python so it has no extra package dependency.`

- **§7.3, §11.2, §11.4, §14**: The polling design does not say whether upstream polls are shared; if implemented per subscriber, many `tail` sessions will hammer Langfuse and blow up MCP memory.  
  **Remediation:** Add to §7.3: `Polling MUST be shared per upstream key with fan-out to subscribers; never poll Langfuse once per connected client.` Also add `max_concurrent_tails`, adaptive backoff on 429, and idle-session expiry.

- **§14**: The failure table omits likely operational failures: Langfuse ClickHouse OOM, MCP OOM under SSE fanout, and Langfuse REST shape drift during partial upgrades.  
  **Remediation:** Add three rows covering `upstream_unhealthy`, `capacity`, and `schema_mismatch`, with explicit behavior: degrade reads, pause subscriptions, reject new tails under pressure, and fail CI smoke on unexpected response shape.

- **§3.2, §7.1, §17.8**: The plan claims independence from 4.3.8 but bakes in 4.3.8’s canonical session contract via `find_session_for_job`, `job/{id}` resources, and tail expectations.  
  **Remediation:** Either remove those conveniences from v1 or add: `These job/session convenience features are gated behind ENABLE_CANONICAL_JOB_SESSION=false until the 4.3.8 session-id contract is merged; core MCP tools do not depend on them.`

- **§8.1, §12.4, §13, §17.7**: Token rotation sequencing is incomplete; swapping a single value plus SIGHUP will break active laptop sessions and `oc` unless there is overlap and restart order.  
  **Remediation:** Replace the one-line rotation claim with a 4-step runbook: `accept old+new token`, `update client secret stores`, `restart/reload oc and langfuse-mcp`, `remove old token after overlap window`. Make this a gate in §12.4.

- **§11.1, §11.2, §14**: The push path will spam operators: every new `ERROR` becomes a system message, including repeat fingerprints and infrastructure noise.  
  **Remediation:** Add: `Live notifications are deduped by (project, env, fingerprint) with a cooldown and count-delta threshold; infrastructure-class events never trigger proactive user-facing messages.`

## Minor

- **§5.2, §16.3**: The fingerprint algorithm uses `top_frame_file|func|lineno`, which will split the same bug across Windows/Linux paths and after harmless refactors.  
  **Remediation:** Change §5.2 step 2 now to use `repo_relative_posix_path` and drop `lineno` from the hash; keep line number as metadata only.

- **§12.5**: The prerequisite command uses `docker exec langfuse-mcp ...`, but the compose snippet never sets `container_name`, so the command is wrong as written.  
  **Remediation:** Either add `container_name: langfuse-mcp` in §8.3 or change the command to `docker compose exec langfuse-mcp ...`.

- **§12.5**: The reachability probe hits an authenticated public API endpoint without auth, so it can fail even when networking is fine.  
  **Remediation:** Change the verification line to use authenticated basic auth or a dedicated unauthenticated upstream health endpoint.

- **§11.1, §11.3**: The Windows story is still treated as a fallback, but this repo is PowerShell-centric; the bash-first examples will fail in week 1 for someone following the doc literally.  
  **Remediation:** Replace the note with: `Ship bash and PowerShell variants from day 1; neither is optional.` Inline both examples in the plan, not just in docs.

## Nits

- **§5.3**: `.mcp.json` is intended to be local-only, but the plan reads like it is a repo-authored artifact.  
  **Remediation:** Add one sentence after the snippet: ```.mcp.json remains untracked local config; if a checked-in sample is needed, use `.mcp.example.json` only.```

needs Critical fixes first
