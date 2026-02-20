"""Generate draft content (comments and post ideas) using OpenAI Codex CLI.

For high-relevance items (score >= 7, tagged respond-worthy), generates
comment drafts. For items tagged as post-inspiration, generates post hooks.

Typical invocation (via cron at 8 PM Mon-Sat, after classifier):
    python3 draft_generator.py

Test mode:
    python3 draft_generator.py --test
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import mongo_store
from safety_manager import SafetyManager
from utils import load_brand_voice, setup_logging

logger = setup_logging("draft-generator")

DEFAULT_MODEL = "gpt-5.3-codex"

COMMENT_TEMPLATES = {
    "insight": "Share a specific insight or experience that adds to the discussion",
    "contrarian": "Offer a respectful contrarian view or nuance that the author may have missed",
    "question": "Ask a thought-provoking question that deepens the conversation",
    "bridge": "Bridge the topic to enterprise architecture or TOGAF governance",
}

COMMENT_PROMPT = """\
{brand_voice}

---

Write a LinkedIn comment (max 150 words) responding to this post.
Follow the brand voice guide above strictly.

Comment style: {template_style} — {template_description}

Post title: {title}
Post author: {author}
Post content: {content}

Return ONLY the comment text, no quotes or formatting.
"""

POST_IDEA_PROMPT = """\
{brand_voice}

---

Based on this LinkedIn content, generate a post idea for Taimoor's LinkedIn.
Return a JSON object with:
- "title": working title for the post (max 10 words)
- "hook": attention-grabbing first line (max 20 words)
- "angle": the unique perspective to take (1 sentence)
- "outline": 3-4 bullet points for the post body
- "cta": closing call-to-action or question
- "estimated_words": target word count (100-300)

Inspiration source:
Title: {title}
Author: {author}
Content: {content}

Return ONLY valid JSON, no markdown formatting.
"""


def call_llm(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call Codex CLI (exec mode) and return the response text."""
    out_path = f"/tmp/codex-out-{os.getpid()}.txt"
    # Codex CLI requires a git repo working directory
    workdir = "/home/node/.openclaw/repos/agentic-ai"
    try:
        result = subprocess.run(
            ["codex", "exec", prompt, "-m", model,
             "--output-last-message", out_path, "--ephemeral"],
            capture_output=True, text=True, timeout=120,
            cwd=workdir,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Codex exec failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        with open(out_path) as f:
            return f.read().strip()
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)


def generate_drafts(test_mode: bool = False, model: str = DEFAULT_MODEL) -> dict:
    """Generate comment drafts and post ideas for high-relevance items.

    Returns stats dict.
    """
    safety = SafetyManager()
    brand_voice = load_brand_voice()

    since = datetime.now(timezone.utc) - timedelta(hours=48)
    db = mongo_store.get_db()

    # Items that warrant a comment
    respond_worthy = list(db.linkedin_intel.find({
        "scraped_at": {"$gte": since},
        "relevance_score": {"$gte": 7},
        "classification.tags": "respond-worthy",
        "classification.action": {"$in": ["engage", "apply"]},
    }).sort("relevance_score", -1).limit(10))

    # Items that could inspire a post (tagged or edge-detected)
    post_inspiration = list(db.linkedin_intel.find({
        "scraped_at": {"$gte": since},
        "$or": [
            {"classification.tags": "post-inspiration"},
            {"edge_details.draft_type": "post_idea"},
        ],
    }).sort("relevance_score", -1).limit(5))

    total = len(respond_worthy) + len(post_inspiration)
    if total == 0:
        logger.info("No items qualifying for draft generation")
        return {"comments": 0, "post_ideas": 0}

    logger.info("Draft targets: %d respond-worthy, %d post-inspiration (model: %s)",
                len(respond_worthy), len(post_inspiration), model)

    if test_mode:
        respond_worthy = respond_worthy[:1]
        post_inspiration = post_inspiration[:1]
        logger.info("TEST MODE: max 1 of each type")

    stats = {"comments": 0, "post_ideas": 0, "errors": 0, "model": model}

    # Pick comment template based on item characteristics
    import itertools
    template_cycle = itertools.cycle(list(COMMENT_TEMPLATES.keys()))

    # Generate comment drafts
    for item in respond_worthy:
        allowed, reason = safety.can_make_call()
        if not allowed:
            logger.warning("Stopping: %s", reason)
            break

        try:
            # Pick template: edge items get "bridge", others cycle
            edge_rules = item.get("edge_opportunities", [])
            if "togaf_ai_crossover" in edge_rules or "governance_vacuum" in edge_rules:
                template_key = "bridge"
            elif "pain_without_solution" in edge_rules:
                template_key = "insight"
            else:
                template_key = next(template_cycle)

            prompt = COMMENT_PROMPT.format(
                brand_voice=brand_voice,
                template_style=template_key,
                template_description=COMMENT_TEMPLATES[template_key],
                title=item.get("title", ""),
                author=item.get("author", ""),
                content=item.get("content_preview", "")[:1000],
            )

            safety.record_call()
            comment_text = call_llm(prompt, model=model)
            safety.wait_between_calls()

            mongo_store.store_draft({
                "draft_type": "comment",
                "type": "comment",
                "template": template_key,
                "source_intel_id": item["_id"],
                "source_title": item.get("title"),
                "source_url": item.get("url"),
                "source_author": item.get("author"),
                "content": comment_text,
                "relevance_score": item.get("relevance_score"),
                "model_used": model,
            })
            stats["comments"] += 1

            if test_mode:
                logger.info("Comment draft [%s]:\n%s", template_key, comment_text)

        except Exception as e:
            logger.error("Comment generation error: %s", e)
            stats["errors"] += 1

    # Generate post ideas
    for item in post_inspiration:
        allowed, reason = safety.can_make_call()
        if not allowed:
            logger.warning("Stopping: %s", reason)
            break

        try:
            prompt = POST_IDEA_PROMPT.format(
                brand_voice=brand_voice,
                title=item.get("title", ""),
                author=item.get("author", ""),
                content=item.get("content_preview", "")[:1000],
            )

            safety.record_call()
            raw_text = call_llm(prompt, model=model)
            safety.wait_between_calls()

            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            post_idea = json.loads(raw_text)

            mongo_store.store_draft({
                "draft_type": "post_idea",
                "type": "post_idea",
                "source_intel_id": item["_id"],
                "source_title": item.get("title"),
                "content": post_idea,
                "model_used": model,
                "edge_rules": item.get("edge_opportunities", []),
            })
            stats["post_ideas"] += 1

            if test_mode:
                logger.info("Post idea:\n%s", json.dumps(post_idea, indent=2))

        except json.JSONDecodeError as e:
            logger.error("Failed to parse post idea: %s", e)
            stats["errors"] += 1
        except Exception as e:
            logger.error("Post idea generation error: %s", e)
            stats["errors"] += 1

    logger.info("Draft generation complete: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate content drafts from intel")
    parser.add_argument("--test", action="store_true", help="Generate 1 draft of each type")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        choices=["gpt-5.3-codex", "gpt-4o-mini", "gpt-4o"],
                        help="Codex model (default: gpt-5.3-codex)")
    args = parser.parse_args()

    result = generate_drafts(test_mode=args.test, model=args.model)
    if result.get("errors", 0) > (result.get("comments", 0) + result.get("post_ideas", 0)):
        sys.exit(1)
