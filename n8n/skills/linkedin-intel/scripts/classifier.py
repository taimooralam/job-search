"""Classify scraped LinkedIn items using Claude Code CLI.

Uses batched classification — sends 10 items per CLI call to minimize
subprocess overhead (~20s per call). Claude Haiku classifies all items
in the batch and returns a JSON array.

Typical invocation (via cron, or chained from linkedin_search.py):
    python3 classifier.py

Test mode (classify 1 batch of 3 items):
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

DEFAULT_MODEL = "haiku"
BATCH_SIZE = 10

BATCH_PROMPT = """\
You are a LinkedIn content classifier for an Enterprise Architect job seeker.

Classify each of the {count} items below. Return a JSON array with exactly {count} objects, one per item, in the same order.

Each object must have:
- "index": the item number (1-based)
- "type": one of "job", "post", "article", "opportunity", "event"
- "category": one of "target_jobs", "freelance", "thought_leadership", "pain_points", "niche", "learning_related", "other"
- "relevance_score": integer 1-10 (10 = perfect match for Enterprise/Solution Architect role)
- "tags": list from ["respond-worthy", "save-for-later", "post-inspiration", "high-priority"]
- "action": one of "engage", "apply", "save", "ignore"
- "reasoning": 1-2 sentence explanation

Scoring guide:
- 9-10: Direct job match or high-value networking opportunity
- 7-8: Relevant to career goals, worth engaging with
- 5-6: Tangentially related, might be useful
- 1-4: Low relevance, generic content

Tag "respond-worthy" if the post warrants a thoughtful comment.
Tag "post-inspiration" if it could inspire an original post.

Return ONLY a valid JSON array, no markdown formatting.

---
{items}
"""

ITEM_TEMPLATE = """\
ITEM {index}:
  Title: {title}
  Author: {author}
  Type: {type}
  Content: {content}
  Source keyword: {keyword}
"""


def call_claude(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call Claude Code CLI and return the response text."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        ["npx", "-y", "@anthropic-ai/claude-code", "-p", prompt,
         "--model", model, "--output-format", "text"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude Code failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def classify_batch(batch: list[dict], model: str = DEFAULT_MODEL) -> list[dict]:
    """Classify a batch of items in a single Claude call.

    Returns list of classification dicts, one per item.
    """
    items_text = ""
    for i, item in enumerate(batch, 1):
        items_text += ITEM_TEMPLATE.format(
            index=i,
            title=item.get("title", ""),
            author=item.get("author", ""),
            type=item.get("type", "unknown"),
            content=item.get("content_preview", "")[:800],
            keyword=item.get("search_keyword", ""),
        )

    prompt = BATCH_PROMPT.format(count=len(batch), items=items_text)
    raw_text = call_claude(prompt, model=model)

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    classifications = json.loads(raw_text)
    if not isinstance(classifications, list):
        raise ValueError(f"Expected JSON array, got {type(classifications).__name__}")

    return classifications


def classify_items(test_mode: bool = False, model: str = DEFAULT_MODEL) -> dict:
    """Classify all unclassified items from the last 48 hours in batches.

    Returns stats dict.
    """
    safety = SafetyManager()

    since = datetime.now(timezone.utc) - timedelta(hours=48)
    items = mongo_store.get_unclassified_items(since)

    if not items:
        logger.info("No unclassified items found")
        return {"classified": 0}

    logger.info("Found %d unclassified items (model: %s, batch_size: %d)",
                len(items), model, BATCH_SIZE)

    if test_mode:
        items = items[:3]
        logger.info("TEST MODE: classifying %d items in 1 batch", len(items))

    stats = {"classified": 0, "errors": 0, "model": model, "batches": 0}

    # Process items in batches
    for batch_start in range(0, len(items), BATCH_SIZE):
        allowed, reason = safety.can_make_call()
        if not allowed:
            logger.warning("Stopping classification: %s", reason)
            break

        batch = items[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Batch %d/%d: classifying %d items...", batch_num, total_batches, len(batch))

        try:
            safety.record_call()
            classifications = classify_batch(batch, model=model)
            safety.wait_between_calls()
            stats["batches"] += 1

            # Match classifications back to items
            for i, item in enumerate(batch):
                try:
                    if i < len(classifications):
                        cls = classifications[i]
                        cls["model_used"] = model
                        cls.pop("index", None)
                        mongo_store.update_classification(item["_id"], cls)
                        stats["classified"] += 1

                        if test_mode:
                            logger.info("  Item %d: score=%s action=%s — %s",
                                        i + 1, cls.get("relevance_score"), cls.get("action"),
                                        cls.get("reasoning", "")[:80])
                    else:
                        logger.warning("  Item %d: no classification returned", i + 1)
                        stats["errors"] += 1
                except Exception as e:
                    logger.error("  Item %d update failed: %s", i + 1, e)
                    stats["errors"] += 1

        except json.JSONDecodeError as e:
            logger.error("Batch %d: failed to parse JSON: %s", batch_num, e)
            stats["errors"] += len(batch)
        except Exception as e:
            logger.error("Batch %d failed: %s", batch_num, e)
            stats["errors"] += len(batch)

    logger.info("Classification complete: %s", stats)

    # Run edge detection on newly classified items
    try:
        from edge_detector import process_items as run_edge_detection
        logger.info("Running edge detection on classified items...")
        edge_stats = run_edge_detection(test_mode=test_mode)
        stats["edge_matches"] = edge_stats.get("matches", 0)
        logger.info("Edge detection: %d matches found", stats["edge_matches"])
    except Exception as e:
        logger.error("Edge detection failed (non-fatal): %s", e)
        stats["edge_matches"] = 0

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Classify LinkedIn intel items")
    parser.add_argument("--test", action="store_true", help="Classify 1 batch of 3 items")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=["haiku", "sonnet"],
                        help="Claude model to use (default: haiku)")
    parser.add_argument("--no-edge", action="store_true", help="Skip edge detection")
    args = parser.parse_args()

    result = classify_items(test_mode=args.test, model=args.model)
    if result.get("errors", 0) > result.get("classified", 0):
        sys.exit(1)
