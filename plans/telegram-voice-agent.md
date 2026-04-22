# Plan: Telegram Voice Agent for Claude Code

**Created**: 2026-01-24
**Status**: Draft
**Priority**: P1 - High Value Mobile Access

---

## Overview

Build a Telegram bot that enables voice interaction with Claude Code running on your VPS. Speak commands from your phone, get work done in your job-search project, and receive audio/text responses.

```
┌─────────────────┐     ┌──────────────────────────────────────────────┐
│   YOUR PHONE    │     │              YOUR VPS                         │
│                 │     │  ┌────────────────────────────────────────┐  │
│  Telegram App   │────►│  │  telegram-voice-bot/                   │  │
│  - Voice msg    │     │  │  ├── bot.py          (Telegram handler)│  │
│  - Text cmd     │     │  │  ├── transcriber.py  (Whisper API)     │  │
│                 │◄────│  │  ├── claude_runner.py (CC subprocess)  │  │
│  Audio/Text     │     │  │  ├── tts.py          (Edge-TTS/OpenAI) │  │
│  Response       │     │  │  └── config.py       (Settings)        │  │
│                 │     │  └────────────────────────────────────────┘  │
└─────────────────┘     └──────────────────────────────────────────────┘
```

---

## Phase 1: Core Bot Setup (2-3 hours)

### 1.1 Create Bot Structure

```bash
# On VPS
mkdir -p ~/telegram-voice-bot
cd ~/telegram-voice-bot

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install python-telegram-bot openai edge-tts aiofiles python-dotenv
```

### 1.2 Bot Registration

1. Message @BotFather on Telegram
2. Create new bot: `/newbot`
3. Name: "Claude Code Voice Assistant" (or similar)
4. Save the API token to `.env`

### 1.3 Core Files to Create

**config.py**
```python
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [int(id) for id in os.getenv("ALLOWED_USER_IDS", "").split(",")]

# OpenAI (for Whisper)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Claude Code
PROJECT_DIR = os.getenv("PROJECT_DIR", "/path/to/job-search")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "120"))

# Trigger words (optional - process all if empty)
TRIGGER_WORDS = ["claude", "sonnet", "opus", "hey claude"]

# TTS
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge")  # "edge" (free) or "openai"
```

**transcriber.py**
```python
import openai
from config import OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)

async def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio file using Whisper API."""
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en"
        )
    return transcript.text
```

**claude_runner.py**
```python
import subprocess
import asyncio
from config import PROJECT_DIR, CLAUDE_TIMEOUT

async def run_claude_code(prompt: str) -> dict:
    """Run Claude Code with the given prompt and return result."""

    cmd = [
        "claude",
        "--print",           # Non-interactive, print output
        "-p", prompt,        # The prompt/command
        "--output-format", "text"
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=PROJECT_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=CLAUDE_TIMEOUT
        )

        return {
            "success": process.returncode == 0,
            "output": stdout.decode("utf-8"),
            "error": stderr.decode("utf-8") if stderr else None
        }

    except asyncio.TimeoutError:
        process.kill()
        return {
            "success": False,
            "output": None,
            "error": f"Command timed out after {CLAUDE_TIMEOUT}s"
        }
```

**tts.py**
```python
import edge_tts
import openai
from config import TTS_ENGINE, OPENAI_API_KEY

async def text_to_speech(text: str, output_path: str) -> str:
    """Convert text to speech audio file."""

    # Compress long responses for voice
    if len(text) > 500:
        text = await compress_for_voice(text)

    if TTS_ENGINE == "edge":
        # Free Edge TTS
        communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
        await communicate.save(output_path)
    else:
        # OpenAI TTS (paid, higher quality)
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text
        )
        response.stream_to_file(output_path)

    return output_path

async def compress_for_voice(text: str) -> str:
    """Compress verbose output for concise voice response."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": "Compress this into 2-3 sentences suitable for voice. Be concise and conversational."
        }, {
            "role": "user",
            "content": text
        }],
        max_tokens=150
    )

    return response.choices[0].message.content
```

**bot.py**
```python
import os
import tempfile
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, TRIGGER_WORDS
from transcriber import transcribe_audio
from claude_runner import run_claude_code
from tts import text_to_speech

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS

def has_trigger_word(text: str) -> bool:
    """Check if text contains a trigger word."""
    if not TRIGGER_WORDS:
        return True
    return any(word.lower() in text.lower() for word in TRIGGER_WORDS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return

    await update.message.reply_text(
        "Voice Claude Code Bot Ready!\n\n"
        "Send me:\n"
        "- Voice message with your command\n"
        "- Text message starting with trigger word\n\n"
        f"Trigger words: {', '.join(TRIGGER_WORDS) or 'any'}"
    )

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages."""
    if not is_authorized(update.effective_user.id):
        return

    status_msg = await update.message.reply_text("🎤 Transcribing...")

    # Download voice message
    voice = await update.message.voice.get_file()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        await voice.download_to_drive(f.name)
        audio_path = f.name

    try:
        # Transcribe
        transcript = await transcribe_audio(audio_path)
        await status_msg.edit_text(f"📝 Heard: {transcript[:100]}...")

        # Check trigger
        if not has_trigger_word(transcript):
            await status_msg.edit_text(f"No trigger word detected.\nHeard: {transcript}")
            return

        # Run Claude Code
        await status_msg.edit_text("🧠 Running Claude Code...")
        result = await run_claude_code(transcript)

        if result["success"]:
            output = result["output"]

            # Send text response
            if len(output) > 4000:
                # Split long messages
                for i in range(0, len(output), 4000):
                    await update.message.reply_text(output[i:i+4000])
            else:
                await update.message.reply_text(f"✅ {output}")

            # Generate and send voice response
            await status_msg.edit_text("🔊 Generating audio...")
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                audio_out = await text_to_speech(output, f.name)
                await update.message.reply_voice(voice=open(audio_out, "rb"))
                os.unlink(audio_out)
        else:
            await update.message.reply_text(f"❌ Error: {result['error']}")

        await status_msg.delete()

    finally:
        os.unlink(audio_path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    if not is_authorized(update.effective_user.id):
        return

    text = update.message.text

    if not has_trigger_word(text):
        return

    status_msg = await update.message.reply_text("🧠 Running Claude Code...")

    result = await run_claude_code(text)

    if result["success"]:
        output = result["output"]
        if len(output) > 4000:
            for i in range(0, len(output), 4000):
                await update.message.reply_text(output[i:i+4000])
        else:
            await update.message.reply_text(f"✅ {output}")
    else:
        await update.message.reply_text(f"❌ Error: {result['error']}")

    await status_msg.delete()

def main():
    """Start the bot."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
```

---

## Phase 2: Deployment on VPS (1 hour)

### 2.1 Environment Setup

```bash
# Create .env file
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ALLOWED_USER_IDS=your_telegram_user_id
OPENAI_API_KEY=your_openai_api_key
PROJECT_DIR=/path/to/job-search
CLAUDE_TIMEOUT=120
TTS_ENGINE=edge
EOF
```

### 2.2 Systemd Service

```bash
# /etc/systemd/system/telegram-claude-bot.service
[Unit]
Description=Telegram Claude Code Voice Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/telegram-voice-bot
Environment=PATH=/home/your_user/telegram-voice-bot/.venv/bin:/usr/bin
ExecStart=/home/your_user/telegram-voice-bot/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable telegram-claude-bot
sudo systemctl start telegram-claude-bot
```

---

## Phase 3: Enhanced Features (Optional, 2-4 hours)

### 3.1 Project Switching

```python
# Add to bot.py
PROJECT_DIRS = {
    "job": "/path/to/job-search",
    "portfolio": "/path/to/portfolio",
}

current_project = "job"

async def switch_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /project command to switch projects."""
    args = context.args
    if args and args[0] in PROJECT_DIRS:
        global current_project
        current_project = args[0]
        await update.message.reply_text(f"Switched to: {current_project}")
```

### 3.2 Thought Inbox Integration

```python
# Add command to save thoughts without processing
async def save_thought(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save voice/text to thoughts inbox for later processing."""
    from datetime import datetime

    inbox_dir = f"{PROJECT_DIR}/thoughts/inbox"
    os.makedirs(inbox_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")

    if update.message.voice:
        transcript = await transcribe_audio(...)  # transcribe voice
        content = transcript
    else:
        content = update.message.text

    filepath = f"{inbox_dir}/{timestamp}.md"
    with open(filepath, "w") as f:
        f.write(f"# Thought - {timestamp}\n\n{content}\n")

    await update.message.reply_text(f"💭 Saved to inbox: {timestamp}.md")
```

### 3.3 Session Continuity

```python
# Use claude --resume to continue previous sessions
async def continue_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Continue the most recent Claude Code session."""
    cmd = ["claude", "--continue", "--print", "-p", update.message.text]
    # ... run command
```

---

## Phase 4: Job Search-Specific Commands (2 hours)

### 4.1 Quick Commands

| Command | Action |
|---------|--------|
| `/jobs` | List recent jobs in pipeline |
| `/status` | Check application statuses |
| `/research <company>` | Run company research |
| `/cv <job_id>` | Generate CV for specific job |
| `/thought` | Save thought to inbox |

### 4.2 Example Implementations

```python
async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick command to list jobs."""
    result = await run_claude_code(
        "Query MongoDB level-2 collection, show 5 most recent jobs "
        "with their status. Format as a brief list."
    )
    await update.message.reply_text(result["output"])

async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run company research."""
    company = " ".join(context.args) if context.args else None
    if not company:
        await update.message.reply_text("Usage: /research <company name>")
        return

    await update.message.reply_text(f"🔍 Researching {company}...")
    result = await run_claude_code(
        f"Research the company '{company}' using FireCrawl. "
        f"Provide a brief summary suitable for interview prep."
    )
    await update.message.reply_text(result["output"])
```

---

## Security Considerations

1. **User Whitelist**: Only allow specific Telegram user IDs
2. **Rate Limiting**: Add cooldown between commands
3. **Command Sanitization**: Validate inputs before passing to Claude
4. **Audit Logging**: Log all commands for review
5. **Cost Monitoring**: Track API usage (Whisper, TTS, Claude)

---

## Cost Estimates

| Component | Cost per Use | Monthly (50 uses/day) |
|-----------|--------------|----------------------|
| Whisper API | ~$0.006/min | ~$9 |
| Edge TTS | Free | $0 |
| OpenAI TTS | ~$0.015/1K chars | ~$15 |
| Claude Code | Variable | ~$50-100 |
| **Total (Edge TTS)** | | ~$60-110 |
| **Total (OpenAI TTS)** | | ~$75-125 |

---

## Success Criteria

- [ ] Bot responds to voice messages within 30 seconds
- [ ] Authorized user check working
- [ ] Claude Code executes in correct project directory
- [ ] Audio responses are clear and concise
- [ ] Bot recovers from errors gracefully
- [ ] Systemd service runs reliably

---

## Next Steps

1. Register Telegram bot with @BotFather
2. Set up bot files on VPS
3. Configure environment variables
4. Test with simple commands
5. Add job-search specific commands
6. Enable systemd service for persistence
