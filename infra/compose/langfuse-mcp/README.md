# langfuse-mcp — operator runbook

Read-only MCP server next to Langfuse. See
`plans/iteration-4.4-langfuse-mcp-feedback-loop.md` for the full design;
this README is just for operating the box on the VPS.

## First-time bootstrap

Per iteration-4.4 §8.3.1. Run on the VPS as root:

```sh
# 1. Drop the env file (chmod 0600).
mkdir -p /root/langfuse-mcp
cp .env.example /root/langfuse-mcp/.env
chmod 0600 /root/langfuse-mcp/.env
$EDITOR /root/langfuse-mcp/.env       # populate prod keys + bearer token

# 2. (Optional) create scout-dev project in the Langfuse UI, populate dev keys.

# 3. DNS — add A record for langfuse-mcp.srv1112039.hstgr.cloud, then:
dig +short langfuse-mcp.srv1112039.hstgr.cloud   # must return the VPS IP

# 4. Shared docker network so the MCP can reach langfuse-web by name.
docker network inspect langfuse_internal >/dev/null 2>&1 \
  || docker network create langfuse_internal
docker network connect langfuse_internal langfuse-web

# 5. First pull + boot. Image is published by .github/workflows/deploy-langfuse-mcp.yml.
cd /root/langfuse-mcp
cp /path/to/repo/infra/compose/langfuse-mcp/docker-compose.yml ./docker-compose.yml
docker compose pull
docker compose up -d
docker logs -f langfuse-mcp

# 6. Wait for Traefik to issue the cert (mytlschallenge ACME).
curl -fsS https://langfuse-mcp.srv1112039.hstgr.cloud/healthz | jq .

# 7. Verify in-cluster reachability of langfuse-web.
docker compose exec langfuse-mcp \
  python -c "import urllib.request; print(urllib.request.urlopen('http://langfuse-web:3000/api/public/health', timeout=3).status)"

# 8. Now enable the deploy-langfuse-mcp.yml workflow (merge to main).
```

## Token rotation (4 steps, ~60 s overlap window)

Per iteration-4.4 §8.1. Goal: no client-visible outage.

```sh
# 1. ACCEPT old + new tokens in parallel on the server.
NEW=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
sed -i "s/^LANGFUSE_MCP_TOKENS=.*/LANGFUSE_MCP_TOKENS=$(grep ^LANGFUSE_MCP_TOKEN /root/langfuse-mcp/.env | cut -d= -f2),$NEW/" /root/langfuse-mcp/.env
docker compose restart langfuse-mcp                # picks up the new env

# 2. UPDATE every client secret store with the new value.
#    - laptop: ~/.config/scout-secrets.env (or %USERPROFILE%\.scout-secrets.env on Windows)
#    - VPS oc service: /root/oc/.env.langfuse
#    - any CI secret store

# 3. RELOAD clients. Restart oc; close & reopen any active Claude Code / Codex sessions.
docker compose -p oc restart oc

# 4. REMOVE the old token from the server.
sed -i "s/^LANGFUSE_MCP_TOKENS=.*/LANGFUSE_MCP_TOKENS=$NEW/" /root/langfuse-mcp/.env
docker compose restart langfuse-mcp
```

Total wall time should be < 60 s. If any client lags, re-add the old token to
`LANGFUSE_MCP_TOKENS` to keep them online.

## Routine ops

```sh
# Live logs
docker logs -f --tail=200 langfuse-mcp

# Health
curl -fsS https://langfuse-mcp.srv1112039.hstgr.cloud/healthz | jq .

# Restart in place (preserves state — there isn't any)
docker compose restart langfuse-mcp

# Pull latest image after a CI deploy
docker compose pull && docker compose up -d
```

## Failure modes (quick reference)

| Symptom | Likely cause | First check |
|---|---|---|
| `/healthz` returns `langfuse_reachable=false` | Langfuse down or `langfuse_internal` network not attached | `docker network inspect langfuse_internal` |
| All MCP calls 401 | Bearer token mismatch | `grep LANGFUSE_MCP_TOKEN /root/langfuse-mcp/.env` and operator-side env |
| First HTTPS hit returns Traefik 404 | Container not on `n8n-prod_default` | `docker network inspect n8n-prod_default \| jq '.[0].Containers'` |
| Boot loops with "scout-prod credentials missing" | `.env` not mounted | `docker compose config` |

See iteration-4.4 §14 for the full table.
