#!/bin/sh
# ── LinkedIn Intelligence init patch ──────────────────────────────
# Add this block to /root/n8n-prod/openclaw-init.sh on the VPS,
# BEFORE the final exec/startup command (section 6b).
#
# It installs Python dependencies for the linkedin-intel skill and
# creates the symlink OpenClaw expects.

echo "[init] Installing linkedin-intel dependencies..."
if ! python3 -m pip --version > /dev/null 2>&1; then
  echo "[init] Installing pip3..."
  apt-get update -qq && apt-get install -y -qq python3-pip > /dev/null 2>&1
fi
python3 -m pip install --break-system-packages --quiet --no-cache-dir \
  "requests>=2.31" "pymongo>=4.6" "python-dateutil>=2.8" \
  "linkedin-api>=2.2.0"

LINKEDIN_SKILL_SRC=/home/node/skills/linkedin-intel
LINKEDIN_SKILL_LINK=/home/node/.openclaw/skills/linkedin-intel
ln -sf "$LINKEDIN_SKILL_SRC" "$LINKEDIN_SKILL_LINK" 2>/dev/null || true

if [ -f "$LINKEDIN_SKILL_LINK/SKILL.md" ]; then
  echo "[init] linkedin-intel skill verified."
else
  echo "[init] WARNING: linkedin-intel SKILL.md not found"
fi

if [ -f "/home/node/linkedin-cookies.txt" ]; then
  echo "[init] LinkedIn cookies mounted."
else
  echo "[init] WARNING: linkedin-cookies.txt not found. LinkedIn scraping will fail."
fi

# ── URL Resolver init ──────────────────────────────────────────────
echo "[init] Installing url-resolver dependencies..."
python3 -m pip install --break-system-packages --quiet --no-cache-dir \
  "duckduckgo-search>=6.0" "anthropic>=0.40" "firecrawl-py>=0.0.5"

URL_RESOLVER_SRC=/home/node/skills/url-resolver
URL_RESOLVER_LINK=/home/node/.openclaw/skills/url-resolver
ln -sf "$URL_RESOLVER_SRC" "$URL_RESOLVER_LINK" 2>/dev/null || true

if [ -f "$URL_RESOLVER_LINK/SKILL.md" ]; then
  echo "[init] url-resolver skill verified."
else
  echo "[init] WARNING: url-resolver SKILL.md not found"
fi
