"""
Deterministic Level‑1 rule scoring for job filtering.

This module implements the Level‑1 (non‑LLM) check in the pipeline.
Jobs that pass this check are eligible for the cheap Level‑1.5 LLM gate.
Only after both Level‑1 and Level‑1.5 pass is a job promoted to Level‑2.
"""

from typing import Any, Dict


TARGET_TITLES = [
    "software architect",
    "senior software architect",
    "enterprise architect",
]

DESIRED_SENIORITY = [
    "mid-senior level",
    "senior",
    "director",
    "executive",
]

UNWANTED_SENIORITY = [
    "entry level",
    "associate",
    "internship",
    "intern",
    "junior",
]

ARCH_KEYWORDS = [
    "architecture",
    "architect",
    "system design",
    "distributed systems",
    "microservices",
    "event-driven",
    "event driven",
    "ddd",
    "domain-driven design",
    "cloud-native",
    "cloud native",
    "aws",
    "gcp",
    "azure",
]


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _count_keywords(text: str, keywords: list[str]) -> int:
    t = text.lower()
    return sum(1 for k in keywords if k in t)


def _has_target_role_title(title: str) -> bool:
    """
    Check whether the job title matches one of the architect roles
    using substring matching so variants such as "Principal Software Architect"
    are also captured.
    """
    return _contains_any(title, TARGET_TITLES)


def compute_rule_score(job_dict: Dict[str, str]) -> int:
    """
    Compute a cheap 0–100 rule-based score for a job.

    Args:
        job_dict: dict with at least keys:
            - title
            - job_criteria
            - job_description
            - location

    Returns:
        Integer score between 0 and 100.
    """
    title = job_dict.get("title", "") or ""
    job_criteria = job_dict.get("job_criteria", "") or ""
    job_description = job_dict.get("job_description", "") or ""
    location = job_dict.get("location", "") or ""

    title_lower = title.lower()
    crit_lower = job_criteria.lower()
    desc_lower = job_description.lower()
    loc_lower = location.lower()

    # 1) Title score (0–40), only for architect roles
    if _has_target_role_title(title_lower):
        title_score = 40
    else:
        title_score = 0

    # 2) Seniority score (0–20)
    seniority_score = 0
    for s in DESIRED_SENIORITY:
        if s in crit_lower:
            seniority_score = 20
            break
    if seniority_score == 0:
        for s in UNWANTED_SENIORITY:
            if s in crit_lower:
                seniority_score = 0
                break

    # 3) Architecture / domain keywords (0–20)
    kw_count = _count_keywords(desc_lower + " " + crit_lower, ARCH_KEYWORDS)
    arch_score = min(kw_count * 5, 20)

    # 4) Remote preference (−10 to +10)
    remote_score = 0
    if any(
        kw in (loc_lower + " " + desc_lower)
        for kw in ["remote", "remote-first", "distributed", "work from anywhere", "rowe"]
    ):
        remote_score += 10
    if any(
        kw in (loc_lower + " " + desc_lower)
        for kw in ["onsite", "on-site", "on site", "office only"]
    ):
        remote_score -= 10

    # 5) Language score (−10 to +10)
    language_score = 0
    if any(
        kw in desc_lower
        for kw in ["fluent arabic", "arabic speaker", "fluent spanish", "spanish speaker"]
    ):
        language_score -= 10

    # Very rough heuristic for non-english postings: lots of non-ascii
    non_ascii_chars = sum(1 for ch in job_description if ord(ch) > 127)
    total_chars = len(job_description) or 1
    non_ascii_ratio = non_ascii_chars / total_chars
    if non_ascii_ratio > 0.3:
        language_score -= 10

    # Sum and clamp
    raw_score = title_score + seniority_score + arch_score + remote_score + language_score
    score = max(0, min(100, raw_score))
    return int(score)


def should_promote_to_level_2(job_dict: Dict[str, str], threshold: int = 50) -> bool:
    """
    Decide whether a job passes the deterministic Level‑1 filter.

    In the overall pipeline:
      - Level‑1 = this rule-based filter.
      - Level‑1.5 = cheap LLM relevance check.
      - Level‑2 = full LangGraph processing.

    Jobs that return True here are eligible for the Level‑1.5 LLM check;
    actual promotion to Level‑2 should only happen after both checks pass.

    Args:
        job_dict: job document with basic fields.
        threshold: minimum score to consider promotion.

    Returns:
        True if job passes the rule-based Level‑1 filter, else False.
    """
    title = job_dict.get("title", "") or ""
    if not _has_target_role_title(title):
        return False

    score = compute_rule_score(job_dict)
    return score >= threshold


def _score_single_job(job: Dict[str, str]) -> Dict[str, Any]:
    """
    Helper to score a single job dict and attach rule-based scoring fields.

    Fields added:
      - rule_score: integer 0–100 from compute_rule_score (Level‑1).
      - rule_promote_to_level_2: bool; True if the job passes Level‑1 rules
        and is eligible for the Level‑1.5 LLM check (kept for compatibility).
    """
    score = compute_rule_score(job)
    promote = should_promote_to_level_2(job)
    enriched: Dict[str, Any] = dict(job)
    enriched["rule_score"] = score
    enriched["rule_promote_to_level_2"] = promote
    return enriched


def _process_n8n_payload(payload: Any) -> Any:
    """
    Process input payloads coming from n8n.

    Supported shapes:
      - A single job dict with the expected fields.
      - A list of job dicts.
      - A list of n8n items: [{ "json": { ...job... } }, ...].
      - A dict with "items": [ { "json": { ...job... } }, ... ].

    Returns:
      - Always a list of dictionaries suitable for n8n, one per item:
        [{ "json": { ...scored_job... } }, ...]
    """
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and "json" in payload[0]:
            # List of n8n items.
            result_items = []
            for item in payload:
                job = item.get("json", {}) or {}
                scored_job = _score_single_job(job)
                new_item = dict(item)
                new_item["json"] = scored_job
                result_items.append(new_item)
            return result_items
        # List of plain job dicts -> wrap as n8n items.
        return [{"json": _score_single_job(job)} for job in payload]

    if isinstance(payload, dict):
        if "items" in payload and isinstance(payload["items"], list):
            items = payload["items"]
            return _process_n8n_payload(items)
        # Single job dict -> single n8n item.
        return [{"json": _score_single_job(payload)}]

    raise ValueError("Unsupported input format for rule scoring.")


def main() -> Any:
    """
    Entry point intended for use from an n8n Python / Code node or from CLI.

    In n8n:
      - Expects a global `items` variable (standard n8n input).
      - Returns a list of item dictionaries: [{ "json": { ... } }, ...].

    From CLI:
      - Reads JSON from stdin and returns the same list shape.
    """
    import json
    import sys

    # n8n Python/Code node usage: `items` is provided as input.
    items = globals().get("items")
    if items is not None:
        return _process_n8n_payload(items)

    # CLI usage: read JSON from stdin.
    raw = sys.stdin.read().strip()
    if not raw:
        return []
    payload = json.loads(raw)
    return _process_n8n_payload(payload)


if __name__ == "__main__":
    import json
    import sys

    result = main()
    json.dump(result, sys.stdout)
