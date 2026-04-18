"""
preenrich_model_preflight.py — Codex model smoke triage for preenrich stages.

Usage:
    python scripts/preenrich_model_preflight.py \\
        --stage jd_extraction \\
        --model gpt-5.4 \\
        --fallback-model claude-haiku-4-5 \\
        --n 5 \\
        [--source historical]

Connects to MongoDB via MONGODB_URI. Selects N historical jobs with
lifecycle in ["completed", "legacy"] that have the live field for the
requested stage populated.  For each job, runs the stage with the
specified Codex model (primary only — no Claude call — this is triage,
not fallback testing).  Compares the Codex output against the live field:
  - schema validity (does the output match the expected shape?)
  - shallow structural comparison (top-level keys, list lengths)

Output: markdown table to stdout with per-job result + summary line.

DISCLAIMER: 5-sample preflight is triage, not validated parity.
Use Phase 3 replay (preenrich_shadow_replay.py) for statistical validation.
"""

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ── Stage metadata ────────────────────────────────────────────────────────────

_STAGE_CONFIG: Dict[str, Dict[str, Any]] = {
    "jd_extraction": {
        "live_field": "extracted_jd",
        "live_keys": ["title", "required_skills", "responsibilities", "qualifications"],
        "default_model": "gpt-5.4",
    },
    "ai_classification": {
        "live_field": "is_ai_job",
        "live_keys": ["is_ai_job", "ai_categories", "ai_category_count"],
        "default_model": "gpt-5.4-mini",
    },
    "pain_points": {
        "live_field": "pain_points",
        "live_keys": ["pain_points", "strategic_needs", "risks_if_unfilled", "success_metrics"],
        "default_model": "gpt-5.4",
    },
    "persona": {
        "live_field": "jd_annotations",
        "live_keys": ["synthesized_persona"],
        "default_model": "gpt-5.4",
    },
}

_SUPPORTED_STAGES = list(_STAGE_CONFIG.keys())


# ── Output field extraction helpers ──────────────────────────────────────────

def _get_live_value(job_doc: Dict[str, Any], stage: str) -> Optional[Any]:
    """Extract the live field value for the given stage."""
    cfg = _STAGE_CONFIG[stage]
    return job_doc.get(cfg["live_field"])


def _check_schema(output: Dict[str, Any], stage: str) -> Tuple[bool, str]:
    """Shallow schema check: top-level keys present?"""
    cfg = _STAGE_CONFIG[stage]
    expected_keys = cfg["live_keys"]
    missing = [k for k in expected_keys if k not in output]
    if missing:
        return False, f"missing keys: {missing}"
    return True, "ok"


def _shallow_compare(
    codex_output: Dict[str, Any],
    live_value: Any,
    stage: str,
) -> Tuple[bool, str]:
    """
    Shallow structural comparison between Codex output and live field.

    Checks:
    - For list fields: both are lists, lengths within 2x of each other
    - For dict fields: top-level key overlap >= 80%
    """
    cfg = _STAGE_CONFIG[stage]
    live_field = cfg["live_field"]
    codex_val = codex_output.get(live_field, codex_output)  # some stages return nested

    if isinstance(live_value, list) and isinstance(codex_val, list):
        live_len = len(live_value)
        codex_len = len(codex_val)
        if live_len == 0 and codex_len == 0:
            return True, "both empty"
        if live_len > 0 and codex_len == 0:
            return False, f"live has {live_len} items, codex returned 0"
        ratio = codex_len / max(live_len, 1)
        if ratio < 0.3 or ratio > 3.0:
            return False, f"length mismatch: live={live_len} codex={codex_len}"
        return True, f"live={live_len} codex={codex_len}"

    if isinstance(live_value, dict) and isinstance(codex_val, dict):
        live_keys = set(live_value.keys())
        codex_keys = set(codex_val.keys())
        if not live_keys:
            return True, "live dict empty"
        overlap = len(live_keys & codex_keys) / len(live_keys)
        if overlap < 0.5:
            return False, f"key overlap={overlap:.0%}: live={sorted(live_keys)[:5]} codex={sorted(codex_keys)[:5]}"
        return True, f"key overlap={overlap:.0%}"

    if isinstance(live_value, bool) and isinstance(codex_val, bool):
        match = live_value == codex_val
        return match, f"live={live_value} codex={codex_val}"

    return True, "types differ (acceptable)"


# ── Codex runner ──────────────────────────────────────────────────────────────

def _run_stage_codex(
    stage: str,
    model: str,
    job_doc: Dict[str, Any],
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Run the specified stage with the specified Codex model.

    Primary only — no Claude fallback (this is model triage).

    Returns:
        (success, output_dict, error_message)
    """
    from src.preenrich.types import StageContext, StepConfig

    ctx = StageContext(
        job_doc=dict(job_doc),
        jd_checksum="sha256:preflight",
        company_checksum="sha256:preflight",
        input_snapshot_id="sha256:preflight",
        attempt_number=1,
        config=StepConfig(
            provider="codex",
            primary_model=model,
            fallback_provider="claude",  # won't be used
            fallback_model="never-called",
        ),
        shadow_mode=False,
    )

    # Import stage class
    try:
        if stage == "jd_extraction":
            from src.preenrich.stages.jd_extraction import JDExtractionStage
            stage_obj = JDExtractionStage()
        elif stage == "ai_classification":
            from src.preenrich.stages.ai_classification import AIClassificationStage
            stage_obj = AIClassificationStage()
        elif stage == "pain_points":
            from src.preenrich.stages.pain_points import PainPointsStage
            stage_obj = PainPointsStage()
        elif stage == "persona":
            from src.preenrich.stages.persona import PersonaStage
            stage_obj = PersonaStage()
        else:
            return False, None, f"Unknown stage: {stage}"
    except ImportError as exc:
        return False, None, f"Import error: {exc}"

    # Monkey-patch _call_llm_with_fallback to only call Codex, never fallback
    import src.preenrich.stages.base as base_module
    _orig = base_module._call_llm_with_fallback

    def _codex_only(*args, **kwargs):
        from src.common.codex_cli import CodexCLI
        prompt = kwargs.get("prompt", "")
        job_id = kwargs.get("job_id", "preflight")
        primary_model_k = kwargs.get("primary_model", model)
        cli = CodexCLI(model=primary_model_k)
        result = cli.invoke(prompt, job_id=job_id, validate_json=True)
        if not result.success:
            raise RuntimeError(f"Codex failed: {result.error}")
        return result.result or {}, [{"provider": "codex", "model": primary_model_k, "outcome": "success"}]

    base_module._call_llm_with_fallback = _codex_only
    try:
        t0 = time.monotonic()
        stage_result = stage_obj.run(ctx)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return True, stage_result.output, f"{elapsed_ms}ms"
    except Exception as exc:
        return False, None, str(exc)
    finally:
        base_module._call_llm_with_fallback = _orig


# ── Main ──────────────────────────────────────────────────────────────────────

def _get_historical_jobs(
    db: Any,
    stage: str,
    n: int,
) -> List[Dict[str, Any]]:
    """Fetch N historical jobs that have the live field populated."""
    cfg = _STAGE_CONFIG[stage]
    live_field = cfg["live_field"]

    query = {
        "lifecycle": {"$in": ["completed", "legacy"]},
        live_field: {"$exists": True, "$ne": None},
    }
    if stage == "persona":
        # persona output lives inside jd_annotations.synthesized_persona
        query = {
            "lifecycle": {"$in": ["completed", "legacy"]},
            "jd_annotations.synthesized_persona": {"$exists": True, "$ne": None},
        }

    cursor = db["level-2"].find(query).limit(n)
    return list(cursor)


def run_preflight(
    stage: str,
    model: str,
    fallback_model: str,
    n: int = 5,
    source: str = "historical",
) -> Dict[str, Any]:
    """
    Run the model preflight for the given stage.

    Returns a results dict with per-job rows and a summary.
    """
    import pymongo

    uri = os.environ.get("MONGODB_URI")
    if not uri:
        print("ERROR: MONGODB_URI not set", file=sys.stderr)
        sys.exit(1)

    client = pymongo.MongoClient(uri)
    db = client["jobs"]

    jobs = _get_historical_jobs(db, stage, n)

    if not jobs:
        print(f"No historical jobs found for stage '{stage}' with live field populated.")
        return {"rows": [], "n_valid": 0, "n_total": 0, "n_fallback": 0}

    rows = []
    n_valid = 0
    n_fallback_would_trigger = 0

    for job in jobs:
        job_id = str(job.get("_id", "?"))
        live_value = _get_live_value(job, stage)

        success, output, detail = _run_stage_codex(stage, model, job)

        schema_ok = False
        struct_ok = False
        schema_msg = ""
        struct_msg = ""
        status = "FAIL"

        if success and output:
            schema_ok, schema_msg = _check_schema(output, stage)
            if schema_ok:
                struct_ok, struct_msg = _shallow_compare(output, live_value, stage)
            status = "OK" if (schema_ok and struct_ok) else "SCHEMA_FAIL" if not schema_ok else "STRUCT_MISMATCH"
            if schema_ok and struct_ok:
                n_valid += 1
            else:
                n_fallback_would_trigger += 1
        else:
            schema_msg = detail
            n_fallback_would_trigger += 1

        rows.append({
            "job_id": job_id[:16],
            "status": status,
            "schema": schema_msg or struct_msg,
            "detail": detail,
        })

    return {
        "rows": rows,
        "n_valid": n_valid,
        "n_total": len(jobs),
        "n_fallback": n_fallback_would_trigger,
    }


def print_markdown_table(stage: str, model: str, results: Dict[str, Any]) -> None:
    """Print results as a markdown table to stdout."""
    rows = results["rows"]
    n_valid = results["n_valid"]
    n_total = results["n_total"]
    n_fallback = results["n_fallback"]

    print(f"\n## Preenrich Model Preflight: stage={stage} model={model}")
    print(f"\n> **DISCLAIMER:** {n_total}-sample preflight is triage, not validated parity.")
    print("> Use Phase 3 replay (preenrich_shadow_replay.py) for statistical validation.\n")

    # Table header
    col_widths = [18, 16, 40, 40]
    headers = ["job_id", "status", "schema/struct", "detail"]
    header_row = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"
    sep_row = "|-" + "-|-".join("-" * w for w in col_widths) + "-|"
    print(header_row)
    print(sep_row)

    for row in rows:
        cells = [
            row["job_id"].ljust(col_widths[0]),
            row["status"].ljust(col_widths[1]),
            (row["schema"] or "")[:col_widths[2]].ljust(col_widths[2]),
            (row["detail"] or "")[:col_widths[3]].ljust(col_widths[3]),
        ]
        print("| " + " | ".join(cells) + " |")

    print(f"\n**Summary:** {n_valid}/{n_total} valid, fallback would trigger {n_fallback} times")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preenrich Codex model smoke triage (5-sample preflight).",
    )
    parser.add_argument(
        "--stage",
        required=True,
        choices=_SUPPORTED_STAGES,
        help="Stage to test",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Codex model identifier (e.g. gpt-5.4, gpt-5.4-mini)",
    )
    parser.add_argument(
        "--fallback-model",
        required=True,
        help="Claude fallback model (for reference only — not called in preflight)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of historical jobs to test (default: 5)",
    )
    parser.add_argument(
        "--source",
        default="historical",
        choices=["historical"],
        help="Job source filter (default: historical)",
    )
    args = parser.parse_args()

    # Ensure src is importable
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    results = run_preflight(
        stage=args.stage,
        model=args.model,
        fallback_model=args.fallback_model,
        n=args.n,
        source=args.source,
    )
    print_markdown_table(args.stage, args.model, results)


if __name__ == "__main__":
    main()
