"""Classify scraped LinkedIn items using Claude Code CLI.

Uses Claude Code (via subprocess) instead of direct API calls, leveraging
the CLAUDE_CODE_OAUTH_TOKEN for authentication. This avoids needing a
separate API key.

Typical invocation (via cron at 8 PM Mon-Sat):
    python3 classifier.py

Test mode (classify 1 item and print):
    python3 classifier.py --test
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import mongo_store
from safety_manager import SafetyManager
from utils import setup_logging

logger = setup_logging("classifier")

DEFAULT_MODEL = "haiku"  # "haiku" or "sonnet"

CLASSIFICATION_PROMPT = """\
You are a LinkedIn content classifier for an Enterprise Architect job seeker.

Classify this LinkedIn item and return a JSON object with these fields:
- "type": one of "job", "post", "article", "opportunity", "event"
- "category": one of "target_jobs", "freelance", "thought_leadership", "pain_points", "niche", "learning_related", "other"
- "relevance_score": integer 1-10 (10 = perfect match for Enterprise/Solution Architect role)
- "tags": list of strings (e.g. ["respond-worthy", "save-for-later", "post-inspiration", "high-priority"])
- "action": one of "engage", "apply", "save", "ignore"
- "reasoning": 1-2 sentence explanation

Scoring guide:
- 9-10: Direct job match or high-value networking opportunity
- 7-8: Relevant to career goals, worth engaging with
- 5-6: Tangentially related, might be useful
- 1-4: Low relevance, generic content

Tag "respond-worthy" if the post warrants a thoughtful comment.
Tag "post-inspiration" if it could inspire an original post.

Return ONLY valid JSON, no markdown formatting.

Item to classify:
Title: {title}
Author: {author}
Type: {type}
Content: {content}
Source keyword: {keyword}
"""


def call_claude(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call Claude Code CLI and return the response text.

    Unsets ANTHROPIC_API_KEY so Claude Code uses CLAUDE_CODE_OAUTH_TOKEN instead.
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        ["npx", "-y", "@anthropic-ai/claude-code", "-p", prompt, "--model", model, "--output-format", "text"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude Code failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def classify_items(test_mode: bool = False, model: str = DEFAULT_MODEL) -> dict:
    """Classify all unclassified items from the last 48 hours.

    Returns stats dict.
    """
    safety = SafetyManager()

    since = datetime.now(timezone.utc) - timedelta(hours=48)
    items = mongo_store.get_unclassified_items(since)

    if not items:
        logger.info("No unclassified items found")
        return {"classified": 0}

    logger.info("Found %d unclassified items (model: %s)", len(items), model)

    if test_mode:
        items = items[:1]
        logger.info("TEST MODE: classifying 1 item only")

    stats = {"classified": 0, "errors": 0, "model": model}

    for item in items:
        allowed, reason = safety.can_make_call()
        if not allowed:
            logger.warning("Stopping classification: %s", reason)
            break

        try:
            prompt = CLASSIFICATION_PROMPT.format(
                title=item.get("title", ""),
                author=item.get("author", ""),
                type=item.get("type", "unknown"),
                content=item.get("content_preview", "")[:1000],
                keyword=item.get("search_keyword", ""),
            )

            safety.record_call()
            raw_text = call_claude(prompt, model=model)
            safety.wait_between_calls()

            # Handle potential markdown code fences
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            classification = json.loads(raw_text)
            classification["model_used"] = model

            mongo_store.update_classification(item["_id"], classification)
            stats["classified"] += 1

            if test_mode:
                logger.info("Classification result:\n%s", json.dumps(classification, indent=2))

        except json.JSONDecodeError as e:
            logger.error("Failed to parse classification for '%s': %s\nRaw: %s", item.get("title"), e, raw_text[:200])
            stats["errors"] += 1
        except Exception as e:
            logger.error("Classification error for '%s': %s", item.get("title"), e)
            stats["errors"] += 1

    logger.info("Classification complete: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Classify LinkedIn intel items")
    parser.add_argument("--test", action="store_true", help="Classify 1 item only")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=["haiku", "sonnet"],
                        help="Claude model to use (default: haiku)")
    args = parser.parse_args()

    result = classify_items(test_mode=args.test, model=args.model)
    if result.get("errors", 0) > result.get("classified", 0):
        sys.exit(1)
