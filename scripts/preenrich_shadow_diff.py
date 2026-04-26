"""
preenrich_shadow_diff.py — Phase 3 parity diff report.

Compares pre_enrichment.shadow_legacy_fields.* against live top-level fields
for each stage. Emits per-stage schema validity, cosine parity, and structural
parity. Outputs Markdown at --out and a Telegram summary.

Usage:
    python -m scripts.preenrich_shadow_diff [--since 2026-04-17] [--limit 20] [--out report.md]

Environment:
    MONGODB_URI   — MongoDB connection string
    OPENAI_API_KEY — Used for text-embedding-3-small cosine parity

Output:
    --out (default: /var/lib/scout/shadow_diff_<timestamp>.md)
    Telegram notification
    Embedding cache: /var/lib/scout/shadow_diff_embeddings.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EMBEDDING_CACHE_PATH = Path("/var/lib/scout/shadow_diff_embeddings.json")
OUTPUT_DIR = Path("/var/lib/scout")

# ---- Stage definitions -------------------------------------------------------
# Stages in DAG order; includes the text fields used for cosine parity.
STAGES = [
    "jd_structure",
    "jd_extraction",
    "ai_classification",
    "pain_points",
    "annotations",
    "persona",
    "company_research",
    "role_research",
]

# Text-heavy sub-paths to embed for cosine parity.
# Format: (shadow_field_key, dot-path inside that field to text)
TEXT_FIELDS_BY_STAGE: Dict[str, List[Tuple[str, str]]] = {
    "jd_extraction": [("extracted_jd", "summary")],
    "pain_points": [("pain_points", "description")],  # first element
    "persona": [("persona", "summary")],
    "company_research": [("company_research", "summary")],
    "role_research": [("role_research", "summary")],
}

# Gate thresholds
SCHEMA_VALIDITY_THRESHOLD = 0.97   # 97%
COSINE_MEAN_THRESHOLD = 0.85


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_embedding_cache() -> Dict[str, List[float]]:
    if EMBEDDING_CACHE_PATH.exists():
        try:
            return json.loads(EMBEDDING_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_embedding_cache(cache: Dict[str, List[float]]) -> None:
    EMBEDDING_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EMBEDDING_CACHE_PATH.write_text(json.dumps(cache), encoding="utf-8")


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _embed_texts(
    texts: List[str],
    cache: Dict[str, List[float]],
    openai_api_key: str,
) -> List[List[float]]:
    """
    Embed a batch of texts using text-embedding-3-small.
    Checks cache first; only calls API for uncached texts.

    Args:
        texts: List of text strings to embed
        cache: In-memory cache keyed by text hash
        openai_api_key: OpenAI API key

    Returns:
        List of embedding vectors in the same order as texts
    """
    import openai

    client = openai.OpenAI(api_key=openai_api_key)

    results: List[Optional[List[float]]] = []
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []

    for i, text in enumerate(texts):
        key = _text_hash(text)
        if key in cache:
            results.append(cache[key])
        else:
            results.append(None)
            uncached_indices.append(i)
            uncached_texts.append(text)

    if uncached_texts:
        try:
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=uncached_texts,
            )
            for idx, emb_data in zip(uncached_indices, resp.data):
                vec = emb_data.embedding
                key = _text_hash(texts[idx])
                cache[key] = vec
                results[idx] = vec
        except Exception as exc:
            logger.warning("OpenAI embedding call failed: %s", exc)
            for idx in uncached_indices:
                results[idx] = []

    return [r or [] for r in results]


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_from_field(value: Any, dot_path: str) -> str:
    """
    Extract a text string from a nested field using a dot-path.

    For list fields, extracts the first element's sub-path.

    Args:
        value: Field value (dict, list, or scalar)
        dot_path: Dot-separated path within the value

    Returns:
        Extracted text, or empty string if not found
    """
    if not value:
        return ""
    parts = dot_path.split(".")
    current: Any = value
    for part in parts:
        if isinstance(current, list):
            if not current:
                return ""
            current = current[0]
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return str(current) if current else ""
    if isinstance(current, str):
        return current
    if isinstance(current, list) and current and isinstance(current[0], str):
        return current[0]
    return str(current) if current else ""


def _is_schema_valid(stage_name: str, value: Any) -> bool:
    """
    Check schema validity of a stage output value.

    Validates that the value is present and has the expected top-level type.
    Full Pydantic validation is skipped here to avoid importing heavy deps;
    we check structural shape only.

    Args:
        stage_name: Name of the stage
        value: Shadow output value to validate

    Returns:
        True if the value passes basic schema checks
    """
    if value is None:
        return False
    expected: Dict[str, Any] = {
        "jd_structure": list,
        "jd_extraction": dict,
        "ai_classification": (dict, str),
        "pain_points": list,
        "annotations": (list, dict),
        "persona": dict,
        "company_research": dict,
        "role_research": dict,
    }
    exp = expected.get(stage_name)
    if exp is None:
        return value is not None
    return isinstance(value, exp)


def _jaccard_keys(a: Any, b: Any) -> float:
    """
    Compute Jaccard similarity of top-level keys (dicts) or array lengths.

    Args:
        a: First value
        b: Second value

    Returns:
        Jaccard score in [0, 1]
    """
    if isinstance(a, dict) and isinstance(b, dict):
        keys_a = set(a.keys())
        keys_b = set(b.keys())
        if not keys_a and not keys_b:
            return 1.0
        intersection = keys_a & keys_b
        union = keys_a | keys_b
        return len(intersection) / len(union) if union else 1.0
    if isinstance(a, list) and isinstance(b, list):
        len_a, len_b = len(a), len(b)
        if len_a == 0 and len_b == 0:
            return 1.0
        return min(len_a, len_b) / max(len_a, len_b) if max(len_a, len_b) > 0 else 1.0
    return 1.0 if a == b else 0.0


# ---------------------------------------------------------------------------
# Per-stage diff logic
# ---------------------------------------------------------------------------

def _diff_stage(
    stage_name: str,
    jobs: List[Dict[str, Any]],
    embedding_cache: Dict[str, List[float]],
    openai_api_key: str,
) -> Dict[str, Any]:
    """
    Compute parity metrics for a single stage across all jobs.

    Args:
        stage_name: Stage to evaluate
        jobs: List of job documents with shadow fields populated
        embedding_cache: Shared embedding cache (mutated in-place)
        openai_api_key: For embedding API calls

    Returns:
        Dict with schema_validity, cosine_mean, cosine_p50, cosine_p5,
        structural_jaccard_mean, cost_usd_mean, duration_ms_mean,
        sample_size, passes_gate, divergence_cases
    """
    schema_valid_count = 0
    cosine_scores: List[float] = []
    jaccard_scores: List[float] = []
    cost_usds: List[float] = []
    duration_mss: List[float] = []
    divergence_cases: List[Dict[str, Any]] = []

    text_field_specs = TEXT_FIELDS_BY_STAGE.get(stage_name, [])

    # Determine the shadow field key for this stage (first output field name)
    # We look inside pre_enrichment.shadow_legacy_fields for any key that
    # corresponds to this stage's output. Since each stage maps to specific
    # top-level fields, we check all keys that overlap with stage outputs.
    stage_to_shadow_keys: Dict[str, List[str]] = {
        "jd_structure": ["processed_jd_sections"],
        "jd_extraction": ["extracted_jd"],
        "ai_classification": ["ai_classification"],
        "pain_points": ["pain_points"],
        "annotations": ["annotations"],
        "persona": ["persona"],
        "company_research": ["company_research"],
        "role_research": ["role_research"],
    }
    shadow_keys = stage_to_shadow_keys.get(stage_name, [stage_name])

    sample_size = 0

    for job in jobs:
        pre = job.get("pre_enrichment", {})
        shadow_fields = pre.get("shadow_legacy_fields", {})
        stages_doc = pre.get("stages", {})
        stage_doc = stages_doc.get(stage_name, {})

        # Skip jobs where this stage didn't run in shadow
        if not stage_doc.get("shadow_output"):
            continue

        sample_size += 1

        for sk in shadow_keys:
            shadow_val = shadow_fields.get(sk)
            live_val = job.get(sk)

            # Schema validity on shadow output
            is_valid = _is_schema_valid(stage_name, shadow_val)
            if is_valid:
                schema_valid_count += 1

            # Structural parity
            jaccard = _jaccard_keys(shadow_val, live_val)
            jaccard_scores.append(jaccard)

            # Cosine parity for text-heavy fields
            for field_key, dot_path in text_field_specs:
                if field_key != sk:
                    continue
                shadow_text = _extract_text_from_field(shadow_val, dot_path)
                live_text = _extract_text_from_field(live_val, dot_path)
                if shadow_text and live_text:
                    vecs = _embed_texts(
                        [shadow_text, live_text], embedding_cache, openai_api_key
                    )
                    if vecs[0] and vecs[1]:
                        cs = _cosine(vecs[0], vecs[1])
                        cosine_scores.append(cs)
                        if cs < COSINE_MEAN_THRESHOLD:
                            divergence_cases.append({
                                "job_id": str(job.get("_id", "")),
                                "stage": stage_name,
                                "field": f"{sk}.{dot_path}",
                                "cosine": round(cs, 4),
                            })

            # Cost + latency from stage doc
            cost = stage_doc.get("cost_usd") or 0.0
            duration = stage_doc.get("duration_ms") or 0.0
            cost_usds.append(cost)
            duration_mss.append(float(duration))

    if sample_size == 0:
        return {
            "stage": stage_name,
            "sample_size": 0,
            "schema_validity_pct": None,
            "cosine_mean": None,
            "cosine_p50": None,
            "cosine_p5": None,
            "structural_jaccard_mean": None,
            "cost_usd_mean": None,
            "duration_ms_mean": None,
            "passes_gate": False,
            "gate_reason": "no shadow data",
            "top_divergence": [],
        }

    schema_validity = schema_valid_count / sample_size
    cosine_mean = sum(cosine_scores) / len(cosine_scores) if cosine_scores else None
    cosine_sorted = sorted(cosine_scores)
    cosine_p50 = cosine_sorted[len(cosine_sorted) // 2] if cosine_sorted else None
    cosine_p5 = cosine_sorted[max(0, int(len(cosine_sorted) * 0.05))] if cosine_sorted else None
    jaccard_mean = sum(jaccard_scores) / len(jaccard_scores) if jaccard_scores else None
    cost_mean = sum(cost_usds) / len(cost_usds) if cost_usds else None
    duration_mean = sum(duration_mss) / len(duration_mss) if duration_mss else None

    gate_fails = []
    if schema_validity < SCHEMA_VALIDITY_THRESHOLD:
        gate_fails.append(f"schema_validity={schema_validity:.1%} < {SCHEMA_VALIDITY_THRESHOLD:.0%}")
    if cosine_mean is not None and cosine_mean < COSINE_MEAN_THRESHOLD:
        gate_fails.append(f"cosine_mean={cosine_mean:.3f} < {COSINE_MEAN_THRESHOLD}")

    passes_gate = not gate_fails

    top_divergence = sorted(divergence_cases, key=lambda d: d["cosine"])[:5]

    return {
        "stage": stage_name,
        "sample_size": sample_size,
        "schema_validity_pct": round(schema_validity * 100, 1),
        "cosine_mean": round(cosine_mean, 4) if cosine_mean is not None else None,
        "cosine_p50": round(cosine_p50, 4) if cosine_p50 is not None else None,
        "cosine_p5": round(cosine_p5, 4) if cosine_p5 is not None else None,
        "structural_jaccard_mean": round(jaccard_mean, 4) if jaccard_mean is not None else None,
        "cost_usd_mean": round(cost_mean, 6) if cost_mean is not None else None,
        "duration_ms_mean": round(duration_mean, 1) if duration_mean is not None else None,
        "passes_gate": passes_gate,
        "gate_reason": "; ".join(gate_fails) if gate_fails else "PASS",
        "top_divergence": top_divergence,
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _render_markdown(
    stage_results: List[Dict[str, Any]],
    overall_pass: bool,
    generated_at: str,
    limit: int,
    since: Optional[str],
) -> str:
    """
    Render the parity diff report as Markdown.

    Args:
        stage_results: List of per-stage diff dicts
        overall_pass: True iff all stages pass gate thresholds
        generated_at: ISO timestamp string
        limit: Number of jobs in sample
        since: Optional since date filter string

    Returns:
        Markdown-formatted report string
    """
    overall_label = "PASS" if overall_pass else "FAIL"
    lines = [
        "# Preenrich Shadow Diff Report",
        "",
        f"**Generated:** {generated_at}",
        f"**Sample limit:** {limit}",
        f"**Since filter:** {since or 'none'}",
        f"**Overall gate:** **{overall_label}**",
        "",
        "## Per-Stage Results",
        "",
        "| Stage | Sample | Schema Valid % | Cosine Mean | Cosine P50 | Cosine P5 | Jaccard | Cost USD | Latency ms | Gate |",
        "|-------|--------|---------------|-------------|-----------|----------|---------|----------|-----------|------|",
    ]

    for r in stage_results:
        gate_cell = "PASS" if r["passes_gate"] else f"FAIL ({r['gate_reason']})"
        lines.append(
            f"| {r['stage']} "
            f"| {r['sample_size']} "
            f"| {r['schema_validity_pct'] if r['schema_validity_pct'] is not None else 'N/A'}% "
            f"| {r['cosine_mean'] if r['cosine_mean'] is not None else 'N/A'} "
            f"| {r['cosine_p50'] if r['cosine_p50'] is not None else 'N/A'} "
            f"| {r['cosine_p5'] if r['cosine_p5'] is not None else 'N/A'} "
            f"| {r['structural_jaccard_mean'] if r['structural_jaccard_mean'] is not None else 'N/A'} "
            f"| {r['cost_usd_mean'] if r['cost_usd_mean'] is not None else 'N/A'} "
            f"| {r['duration_ms_mean'] if r['duration_ms_mean'] is not None else 'N/A'} "
            f"| {gate_cell} |"
        )

    # Top divergence cases
    all_divergences = []
    for r in stage_results:
        all_divergences.extend(r.get("top_divergence", []))
    all_divergences = sorted(all_divergences, key=lambda d: d["cosine"])[:5]

    if all_divergences:
        lines += [
            "",
            "## Top 5 Divergence Cases",
            "",
            "| Job ID | Stage | Field | Cosine |",
            "|--------|-------|-------|--------|",
        ]
        for d in all_divergences:
            lines.append(
                f"| {d['job_id']} | {d['stage']} | {d['field']} | {d['cosine']} |"
            )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main diff orchestration
# ---------------------------------------------------------------------------

def run_diff(
    since: Optional[str],
    limit: int,
    out_path: Path,
    mongodb_uri: Optional[str] = None,
    openai_api_key: Optional[str] = None,
) -> None:
    """
    Orchestrate the shadow parity diff.

    Args:
        since: Optional ISO date string to filter jobs processed after this date
        limit: Maximum number of jobs to evaluate
        out_path: Path to write the Markdown report
        mongodb_uri: MongoDB URI (falls back to MONGODB_URI env)
        openai_api_key: OpenAI API key (falls back to OPENAI_API_KEY env)
    """
    import pymongo

    uri = mongodb_uri or os.environ.get("MONGODB_URI", "")
    if not uri:
        logger.error("MONGODB_URI not set")
        sys.exit(1)

    openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        logger.warning(
            "OPENAI_API_KEY not set — cosine parity will be skipped for all stages"
        )

    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10_000)
    db = client["jobs"]

    match: Dict[str, Any] = {
        "pre_enrichment.shadow_legacy_fields": {"$exists": True}
    }
    if since:
        try:
            since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
            match["selected_at"] = {"$gte": since_dt}
        except ValueError:
            logger.warning("Could not parse --since date: %s", since)

    jobs = list(
        db["level-2"].find(match).sort("selected_at", -1).limit(limit)
    )
    logger.info("Loaded %d jobs with shadow_legacy_fields", len(jobs))

    if not jobs:
        logger.warning("No jobs with shadow_legacy_fields found — run shadow replay first")
        client.close()
        return

    embedding_cache = _load_embedding_cache()

    stage_results = []
    for stage_name in STAGES:
        logger.info("Diffing stage: %s", stage_name)
        result = _diff_stage(stage_name, jobs, embedding_cache, openai_key)
        stage_results.append(result)
        logger.info(
            "  %s — sample=%d schema=%.1f%% cosine_mean=%s gate=%s",
            stage_name,
            result["sample_size"],
            result["schema_validity_pct"] or 0,
            result["cosine_mean"],
            "PASS" if result["passes_gate"] else "FAIL",
        )

    _save_embedding_cache(embedding_cache)

    overall_pass = all(r["passes_gate"] for r in stage_results)
    generated_at = datetime.now(timezone.utc).isoformat()

    md = _render_markdown(
        stage_results, overall_pass, generated_at, limit, since
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    logger.info("Report written to %s", out_path)
    print(md)

    # Telegram summary
    fail_stages = [r["stage"] for r in stage_results if not r["passes_gate"]]
    tg_lines = [
        "<b>Preenrich Shadow Diff</b>",
        f"Jobs: {len(jobs)} | Overall: {'PASS' if overall_pass else 'FAIL'}",
    ]
    if fail_stages:
        tg_lines.append(f"Failed stages: {fail_stages}")
    else:
        tg_lines.append("All stages passed gate thresholds")
    tg_lines.append(f"<code>{out_path}</code>")

    try:
        from src.common.telegram import send_telegram
        send_telegram("\n".join(tg_lines))
    except Exception as exc:
        logger.warning("Telegram notify failed: %s", exc)

    client.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    default_out = OUTPUT_DIR / f"shadow_diff_{timestamp}.md"

    parser = argparse.ArgumentParser(
        description="Generate Phase 3 shadow parity diff report."
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Filter jobs processed since this ISO date (e.g. 2026-04-17)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Max number of jobs to evaluate (default: 20)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help="Output path for the Markdown report",
    )

    args = parser.parse_args()
    run_diff(since=args.since, limit=args.limit, out_path=args.out)


if __name__ == "__main__":
    main()
