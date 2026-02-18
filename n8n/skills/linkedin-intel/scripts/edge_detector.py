"""Edge & niche opportunity detection for LinkedIn Intelligence.

Applies heuristic rules from config/edge-rules.json to classified
intel items. Adds score boosts and edge_opportunities metadata.

Typical invocation (via cron, after classifier):
    python3 edge_detector.py

Test mode (process 1 item and print):
    python3 edge_detector.py --test
"""

import sys
from datetime import datetime, timedelta, timezone

import mongo_store
from utils import load_config, setup_logging

logger = setup_logging("edge-detector")


def load_rules() -> list[dict]:
    """Load edge detection rules from config."""
    config = load_config("edge-rules")
    return config.get("rules", [])


def text_corpus(item: dict) -> str:
    """Build searchable text from an intel item."""
    parts = [
        item.get("title", ""),
        item.get("content_preview", ""),
        item.get("full_content", ""),
        item.get("company", ""),
        item.get("author", ""),
        item.get("location", ""),
    ]
    # Include classification reasoning if available
    classification = item.get("classification", {})
    if isinstance(classification, dict):
        parts.append(classification.get("reasoning", ""))
    return " ".join(parts).lower()


def check_rule(rule: dict, text: str) -> bool:
    """Check if a rule matches: needs at least 1 signal AND 1 cross-ref."""
    has_signal = any(s in text for s in rule["signals"])
    has_cross = any(c in text for c in rule["cross_ref"])
    return has_signal and has_cross


def detect_edges(item: dict, rules: list[dict]) -> list[dict]:
    """Run all rules against an item. Returns list of matched rules with boosts."""
    text = text_corpus(item)
    matches = []
    for rule in rules:
        if check_rule(rule, text):
            matches.append({
                "rule_id": rule["id"],
                "description": rule["description"],
                "boost": rule["boost"],
                "draft_type": rule.get("draft_type"),
            })
    return matches


def process_items(test_mode: bool = False) -> dict:
    """Run edge detection on recently classified items.

    Adds `edge_opportunities` field and adjusts `relevance_score`.
    """
    rules = load_rules()
    logger.info("Loaded %d edge detection rules", len(rules))

    since = datetime.now(timezone.utc) - timedelta(hours=48)
    db = mongo_store.get_db()

    # Items that have classification but no edge detection yet
    items = list(db.linkedin_intel.find({
        "scraped_at": {"$gte": since},
        "classification": {"$exists": True},
        "edge_opportunities": {"$exists": False},
    }).sort("relevance_score", -1))

    if not items:
        logger.info("No items pending edge detection")
        return {"processed": 0, "matches": 0}

    logger.info("Processing %d items for edge detection", len(items))

    if test_mode:
        items = items[:1]
        logger.info("TEST MODE: processing 1 item only")

    stats = {"processed": 0, "matches": 0, "total_boost": 0}

    for item in items:
        matches = detect_edges(item, rules)
        total_boost = sum(m["boost"] for m in matches)
        current_score = item.get("relevance_score", 0)
        adjusted_score = min(10, current_score + total_boost)

        update: dict = {
            "edge_opportunities": [m["rule_id"] for m in matches],
            "edge_details": matches,
            "edge_detected_at": datetime.now(timezone.utc),
        }
        if total_boost > 0:
            update["relevance_score"] = adjusted_score
            update["original_relevance_score"] = current_score

        db.linkedin_intel.update_one({"_id": item["_id"]}, {"$set": update})
        stats["processed"] += 1

        if matches:
            stats["matches"] += 1
            stats["total_boost"] += total_boost
            logger.info(
                "Edge match: '%s' — rules: %s, boost: +%d (%d→%d)",
                item.get("title", "?")[:60],
                [m["rule_id"] for m in matches],
                total_boost,
                current_score,
                adjusted_score,
            )

        if test_mode and matches:
            import json
            logger.info("Edge details:\n%s", json.dumps(matches, indent=2))

    logger.info("Edge detection complete: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Detect edge/niche opportunities in intel items")
    parser.add_argument("--test", action="store_true", help="Process 1 item only")
    args = parser.parse_args()

    result = process_items(test_mode=args.test)
    if result["processed"] == 0 and not args.test:
        sys.exit(0)
