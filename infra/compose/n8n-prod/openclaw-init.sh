#!/bin/sh
# Legacy init script — superseded by inline entrypoint command in docker-compose.yml.
# Kept for reference. The oc service now runs skills copy + gateway start inline.
#
# WARNING: NEVER run this script from the shell or Claude Code.
# If this script needs to be executed, always tell the user to run it manually
# from their phone terminal (Termius/SSH app). Do not invoke it programmatically.
set -e

REPO_DIR=/home/node/.openclaw/repos/agentic-ai
TOGAF_REPO_DIR=/home/node/.openclaw/repos/togaf
SKILL_LINK=/home/node/.openclaw/skills/audio-teacher
TOGAF_SKILL_LINK=/home/node/.openclaw/skills/togaf-audio-teacher
SKILLS_DIR=/home/node/.openclaw/skills
GATEWAY_DIR=/app

# --- 1. Install system deps (idempotent, cached after first run) ---
if ! command -v gh > /dev/null 2>&1 || ! command -v python3 > /dev/null 2>&1 || ! command -v yt-dlp > /dev/null 2>&1 || ! command -v deno > /dev/null 2>&1; then
  echo "[init] Installing python3, gh, git, pip, yt-dlp, deno..."
  apt-get update -qq && apt-get install -y -qq python3 python3-pip gh git curl unzip > /dev/null 2>&1
  pip3 install --break-system-packages yt-dlp > /dev/null 2>&1
  curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh > /dev/null 2>&1
else
  echo "[init] Dependencies already installed."
fi

# --- 2. Git config ---
git config --global user.name "${GIT_AUTHOR_NAME}"
git config --global user.email "${GIT_AUTHOR_EMAIL}"
git config --global --add safe.directory "$REPO_DIR"
git config --global --add safe.directory "$TOGAF_REPO_DIR"

# --- 3. Clone or pull agentic-ai repo ---
REPO_URL="https://${GITHUB_TOKEN}@github.com/taimooralam/agentic-ai.git"

if [ -d "$REPO_DIR/.git" ]; then
  echo "[init] agentic-ai repo exists. Fixing remote URL and pulling..."
  git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
  git -C "$REPO_DIR" pull origin main || echo "[init] Pull failed (non-fatal, using cached)"
else
  echo "[init] Cloning agentic-ai repo..."
  mkdir -p /home/node/.openclaw/repos
  git clone "$REPO_URL" "$REPO_DIR"
fi

# --- 3b. Clone or pull togaf repo ---
TOGAF_REPO_URL="https://${GITHUB_TOKEN}@github.com/taimooralam/togaf.git"

if [ -d "$TOGAF_REPO_DIR/.git" ]; then
  echo "[init] togaf repo exists. Fixing remote URL and pulling..."
  git -C "$TOGAF_REPO_DIR" remote set-url origin "$TOGAF_REPO_URL"
  git -C "$TOGAF_REPO_DIR" pull origin main || echo "[init] Pull failed (non-fatal, using cached)"
else
  echo "[init] Cloning togaf repo..."
  mkdir -p /home/node/.openclaw/repos
  git clone "$TOGAF_REPO_URL" "$TOGAF_REPO_DIR"
fi

# --- 4. Set up skills ---
mkdir -p "$SKILLS_DIR"

rm -rf "$SKILL_LINK" && cp -r "$REPO_DIR/skills/audio-teacher" "$SKILL_LINK"
rm -rf "$TOGAF_SKILL_LINK" && cp -r "$TOGAF_REPO_DIR/skills/togaf-audio-teacher" "$TOGAF_SKILL_LINK"

for SKILL_NAME in yt-dlp linkedin-intel url-resolver; do
  SRC="/home/node/skills/$SKILL_NAME"
  DST="$SKILLS_DIR/$SKILL_NAME"
  if [ -d "$SRC" ]; then
    rm -rf "$DST"
    cp -r "$SRC" "$DST"
    echo "[init] Copied $SKILL_NAME skill into volume."
  fi
done

# --- 5. Fix ownership for node user ---
chown -R node:node /home/node/.openclaw 2>/dev/null || true

# --- 6. Verify skills ---
for SKILL_NAME in audio-teacher togaf-audio-teacher yt-dlp linkedin-intel url-resolver; do
  if [ -f "$SKILLS_DIR/$SKILL_NAME/SKILL.md" ]; then
    echo "[init] $SKILL_NAME skill verified."
  else
    echo "[init] WARNING: $SKILL_NAME SKILL.md not found"
  fi
done

echo "[init] yt-dlp version: $(yt-dlp --version 2>/dev/null || echo 'not found')"
echo "[init] deno version: $(deno --version 2>/dev/null | head -1 || echo 'not found')"

# --- 6b. Install Python deps for skills ---
echo "[init] Installing skill Python dependencies..."
python3 -m pip install --break-system-packages --quiet --no-cache-dir \
  "requests>=2.31" "pymongo>=4.6" "python-dateutil>=2.8" \
  "linkedin-api>=2.2.0" \
  "duckduckgo-search>=6.0" "openai>=1.0" "firecrawl-py>=0.0.5"

# --- 7. Start gateway ---
echo "[init] Starting OpenClaw gateway..."
cd "$GATEWAY_DIR"
exec su -s /bin/sh node -c "cd $GATEWAY_DIR && exec node openclaw.mjs gateway --allow-unconfigured --bind lan --port 18789 --auth token"
