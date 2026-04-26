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
    "jd_facts": {
        "live_field": "pre_enrichment.outputs.jd_facts",
        "live_keys": ["merged_view", "provenance", "deterministic"],
        "default_model": "gpt-5.2",
    },
    "classification": {
        "live_field": "pre_enrichment.outputs.classification",
        "live_keys": [
            "primary_role_category",
            "search_profiles",
            "selector_profiles",
            "tone_family",
            "taxonomy_version",
            "confidence",
            "ambiguity_score",
            "ai_taxonomy",
        ],
        "default_model": "gpt-5.4-mini",
    },
    "research_enrichment": {
        "live_field": "pre_enrichment.outputs.research_enrichment",
        "live_keys": ["status", "company_profile", "role_profile", "application_profile", "capability_flags"],
        "default_model": "gpt-5.2",
    },
    "application_surface": {
        "live_field": "pre_enrichment.outputs.application_surface",
        "live_keys": ["status", "application_url", "canonical_application_url", "portal_family", "resolution_status"],
        "default_model": "gpt-5.2",
    },
    "stakeholder_surface": {
        "live_field": "pre_enrichment.outputs.stakeholder_surface",
        "live_keys": ["status", "evaluator_coverage_target", "evaluator_coverage", "real_stakeholders", "inferred_stakeholder_personas"],
        "default_model": "gpt-5.2",
    },
    "pain_point_intelligence": {
        "live_field": "pre_enrichment.outputs.pain_point_intelligence",
        "live_keys": ["status", "pain_points", "proof_map", "search_terms", "source_scope"],
        "default_model": "gpt-5.4",
    },
    "presentation_contract": {
        "live_field": "pre_enrichment.outputs.presentation_contract",
        "live_keys": ["status", "document_expectations", "cv_shape_expectations"],
        "default_model": "gpt-5.4",
    },
    "job_inference": {
        "live_field": "pre_enrichment.outputs.job_inference",
        "live_keys": ["semantic_role_model", "company_model", "qualifications", "application_surface"],
        "default_model": "gpt-5.4",
    },
    "job_hypotheses": {
        "live_field": "pre_enrichment.outputs.job_hypotheses",
        "live_keys": ["status", "hypothesis_count"],
        "default_model": "gpt-5.4-mini",
    },
    "cv_guidelines": {
        "live_field": "pre_enrichment.outputs.cv_guidelines",
        "live_keys": [
            "title_guidance",
            "identity_guidance",
            "bullet_theme_guidance",
            "ats_keyword_guidance",
            "cover_letter_expectations",
        ],
        "default_model": "gpt-5.4",
    },
    "blueprint_assembly": {
        "live_field": "pre_enrichment.outputs.blueprint_assembly",
        "live_keys": ["job_blueprint_version", "snapshot", "compatibility_projection"],
        "default_model": "none",
    },
}

_SUPPORTED_STAGES = list(_STAGE_CONFIG.keys())


# ── Output field extraction helpers ──────────────────────────────────────────

def _get_live_value(job_doc: Dict[str, Any], stage: str) -> Optional[Any]:
    """Extract the live field value for the given stage."""
    cfg = _STAGE_CONFIG[stage]
    value: Any = job_doc
    for part in cfg["live_field"].split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


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
        elif stage == "jd_facts":
            from src.preenrich.stages.jd_facts import JDFactsStage
            stage_obj = JDFactsStage()
        elif stage == "classification":
            from src.preenrich.stages.classification import ClassificationStage
            stage_obj = ClassificationStage()
        elif stage == "research_enrichment":
            from src.preenrich.stages.research_enrichment import ResearchEnrichmentStage
            stage_obj = ResearchEnrichmentStage()
        elif stage == "application_surface":
            from src.preenrich.stages.application_surface import ApplicationSurfaceStage
            stage_obj = ApplicationSurfaceStage()
        elif stage == "stakeholder_surface":
            from src.preenrich.stages.stakeholder_surface import StakeholderSurfaceStage
            stage_obj = StakeholderSurfaceStage()
        elif stage == "pain_point_intelligence":
            from src.preenrich.stages.pain_point_intelligence import PainPointIntelligenceStage
            stage_obj = PainPointIntelligenceStage()
        elif stage == "presentation_contract":
            from src.preenrich.stages.presentation_contract import PresentationContractStage
            stage_obj = PresentationContractStage()
        elif stage == "job_inference":
            from src.preenrich.stages.job_inference import JobInferenceStage
            stage_obj = JobInferenceStage()
        elif stage == "job_hypotheses":
            from src.preenrich.stages.job_hypotheses import JobHypothesesStage
            stage_obj = JobHypothesesStage()
        elif stage == "cv_guidelines":
            from src.preenrich.stages.cv_guidelines import CVGuidelinesStage
            stage_obj = CVGuidelinesStage()
        elif stage == "blueprint_assembly":
            from src.preenrich.stages.blueprint_assembly import BlueprintAssemblyStage
            stage_obj = BlueprintAssemblyStage()
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
        output = stage_result.stage_output or stage_result.output
        return True, output, f"{elapsed_ms}ms"
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


def validate_stage_routing(stage: str | None = None) -> list[str]:
    """Return routing config errors for the requested stage or all supported stages."""
    from src.preenrich.blueprint_config import (
        classification_escalate_on_failure_enabled,
        classification_escalation_model,
        jd_facts_escalate_on_failure_enabled,
    )
    from src.preenrich.types import get_stage_step_config

    targets = [stage] if stage else _SUPPORTED_STAGES
    errors: list[str] = []
    for name in targets:
        cfg = get_stage_step_config(name)
        if cfg.provider != "none" and not cfg.primary_model:
            errors.append(f"{name}: provider={cfg.provider} missing primary_model")
        if name == "jd_facts":
            if cfg.provider == "none":
                errors.append("jd_facts: active stage requires a real provider")
            if (
                jd_facts_escalate_on_failure_enabled()
                and not os.getenv("PREENRICH_JD_FACTS_ESCALATION_MODEL", "").strip()
                and not os.getenv("PREENRICH_JD_FACTS_ESCALATION_MODELS", "").strip()
            ):
                errors.append(
                    "jd_facts: escalation enabled requires "
                    "PREENRICH_JD_FACTS_ESCALATION_MODEL or PREENRICH_JD_FACTS_ESCALATION_MODELS"
                )
        if name == "classification":
            if cfg.provider == "none":
                errors.append("classification: active stage requires a real provider")
            if os.getenv("PREENRICH_CLASSIFICATION_SHADOW_MODE_ENABLED", "false").strip().lower() == "true":
                errors.append("classification: shadow mode is no longer supported")
            if (
                classification_escalate_on_failure_enabled()
                and not os.getenv("PREENRICH_CLASSIFICATION_ESCALATION_MODEL", classification_escalation_model()).strip()
            ):
                errors.append(
                    "classification: escalation enabled requires PREENRICH_CLASSIFICATION_ESCALATION_MODEL"
                )
        if name in {"research_enrichment", "application_surface", "stakeholder_surface"}:
            v2_enabled = os.getenv("PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED", "false").strip().lower() == "true"
            live_web_enabled = os.getenv("WEB_RESEARCH_ENABLED", "false").strip().lower() == "true"
            shadow_mode = os.getenv("PREENRICH_RESEARCH_SHADOW_MODE_ENABLED", "false").strip().lower() == "true"
            live_compat = os.getenv("PREENRICH_RESEARCH_LIVE_COMPAT_WRITE_ENABLED", "false").strip().lower() == "true"
            expanded_snapshot = os.getenv("PREENRICH_RESEARCH_UI_SNAPSHOT_EXPANDED_ENABLED", "false").strip().lower() == "true"
            stakeholders_enabled = os.getenv("PREENRICH_RESEARCH_ENABLE_STAKEHOLDERS", "false").strip().lower() == "true"
            outreach_enabled = os.getenv("PREENRICH_RESEARCH_ENABLE_OUTREACH_GUIDANCE", "false").strip().lower() == "true"
            require_sources = os.getenv("PREENRICH_RESEARCH_REQUIRE_SOURCE_ATTRIBUTION", "true").strip().lower() == "true"
            if name == "stakeholder_surface":
                stage_enabled = os.getenv("PREENRICH_STAKEHOLDER_SURFACE_ENABLED", "false").strip().lower() == "true"
                if stage_enabled and cfg.provider == "none":
                    errors.append("stakeholder_surface: enabled stage requires a real provider")
                if stage_enabled and cfg.provider != "codex":
                    errors.append("stakeholder_surface: enabled stage requires provider=codex")
                if stage_enabled and live_web_enabled and not (cfg.transport or "").startswith("codex"):
                    errors.append("stakeholder_surface: WEB_RESEARCH_ENABLED=true requires a codex research transport")
                continue
            if v2_enabled and cfg.provider == "none":
                errors.append(f"{name}: V2 enabled requires a real provider")
            if v2_enabled and cfg.provider != "codex":
                errors.append(f"{name}: V2 enabled requires provider=codex")
            if v2_enabled and live_web_enabled and not (cfg.transport or "").startswith("codex"):
                errors.append(f"{name}: WEB_RESEARCH_ENABLED=true requires a codex research transport")
            if shadow_mode and not v2_enabled:
                errors.append(f"{name}: shadow mode requires PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true")
            if live_compat and not v2_enabled:
                errors.append(f"{name}: live compat write requires PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true")
            if expanded_snapshot and not v2_enabled:
                errors.append(f"{name}: expanded UI snapshot requires PREENRICH_RESEARCH_ENRICHMENT_V2_ENABLED=true")
            if outreach_enabled and not stakeholders_enabled:
                errors.append(f"{name}: outreach guidance requires stakeholders enabled")
            if live_compat and not require_sources:
                errors.append(f"{name}: live compat write requires source attribution")
        if name == "pain_point_intelligence":
            stage_enabled = os.getenv("PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED", "false").strip().lower() == "true"
            supplemental_web = os.getenv("PREENRICH_PAIN_POINT_SUPPLEMENTAL_WEB_ENABLED", "false").strip().lower() == "true"
            live_web_enabled = os.getenv("WEB_RESEARCH_ENABLED", "false").strip().lower() == "true"
            if stage_enabled and cfg.provider == "none":
                errors.append("pain_point_intelligence: enabled stage requires a real provider")
            if stage_enabled and cfg.provider != "codex":
                errors.append("pain_point_intelligence: enabled stage requires provider=codex")
            if stage_enabled and (cfg.transport or "none") != "none":
                errors.append("pain_point_intelligence: enabled stage must default to non-web transport")
            if supplemental_web and not stage_enabled:
                errors.append("pain_point_intelligence: supplemental web requires the stage to be enabled")
            if supplemental_web and not live_web_enabled:
                errors.append("pain_point_intelligence: supplemental web requires WEB_RESEARCH_ENABLED=true")
        if name == "presentation_contract":
            stage_enabled = os.getenv("PREENRICH_PRESENTATION_CONTRACT_ENABLED", "false").strip().lower() == "true"
            if stage_enabled and cfg.provider == "none":
                errors.append("presentation_contract: enabled stage requires a real provider")
            if stage_enabled and cfg.provider != "codex":
                errors.append("presentation_contract: enabled stage requires provider=codex")
            if stage_enabled and (cfg.transport or "none") != "none":
                errors.append("presentation_contract: enabled stage must not use web transport")
            if stage_enabled and os.getenv("PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED", "false").strip().lower() != "true":
                errors.append("presentation_contract: enabled stage requires PREENRICH_PAIN_POINT_INTELLIGENCE_ENABLED=true")
    return errors


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
        choices=_SUPPORTED_STAGES,
        help="Stage to test",
    )
    parser.add_argument(
        "--model",
        help="Codex model identifier (e.g. gpt-5.4, gpt-5.4-mini)",
    )
    parser.add_argument(
        "--fallback-model",
        help="Claude fallback model (for reference only — not called in preflight)",
    )
    parser.add_argument(
        "--validate-routing",
        action="store_true",
        help="Validate provider/model routing for preenrich stages and exit",
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

    if args.validate_routing:
        errors = validate_stage_routing(args.stage)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            raise SystemExit(1)
        target = args.stage or "all supported stages"
        print(f"Routing validation OK for {target}")
        return

    if not args.stage or not args.model or not args.fallback_model:
        parser.error("--stage, --model, and --fallback-model are required unless --validate-routing is used")

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
