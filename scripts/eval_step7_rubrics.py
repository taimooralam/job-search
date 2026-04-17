#!/usr/bin/env python3
"""
Eval Step 7: Generate reusable category CV evaluation rubrics.

Reads:
  data/eval/blueprints/{category}_blueprint.json
  data/eval/baselines/{category}_baseline.json (preferred; optional)

Writes:
  data/eval/rubrics/{category}_rubric.json
  data/eval/rubrics/{category}_rubric.md
  data/eval/rubrics/scorecard_template.json
  data/eval/rubrics/stage_scorecard_template.json
  data/eval/rubrics/index.md
  data/eval/rubrics/README.md

Usage:
  python scripts/eval_step7_rubrics.py
  python scripts/eval_step7_rubrics.py --category ai_architect_global
  python scripts/eval_step7_rubrics.py --force --provider claude
  python scripts/eval_step7_rubrics.py --render-only
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.common.json_utils import parse_llm_json

EVAL_DIR = Path("data/eval")
BLUEPRINT_DIR = EVAL_DIR / "blueprints"
BASELINE_DIR = EVAL_DIR / "baselines"
RUBRIC_DIR = EVAL_DIR / "rubrics"
RUBRIC_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR = RUBRIC_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

DIMENSIONS: List[Dict[str, Any]] = [
    {"key": "ats_optimization", "weight": 20},
    {"key": "impact_clarity", "weight": 25},
    {"key": "jd_alignment", "weight": 25},
    {"key": "executive_presence", "weight": 15},
    {"key": "anti_hallucination", "weight": 15},
]
DIMENSION_KEYS = [d["key"] for d in DIMENSIONS]
DIMENSION_WEIGHTS = {d["key"]: d["weight"] for d in DIMENSIONS}

TOP_LEVEL_KEYS = [
    "meta",
    "rubric_identity",
    "dimension_rubrics",
    "gates",
    "verdict_thresholds",
    "scoring_guidance",
    "scorecard_template_mapping",
    "evidence_ledger",
]

VERDICT_THRESHOLDS = {
    "strong_match_min": 8.5,
    "good_match_min": 7.0,
    "needs_work_min": 5.5,
    "weak_match_max": 5.49,
}

GATE_KEYS = ["must_have_coverage_gate", "unsafe_claim_gate", "persona_fit_gate"]

PLACEHOLDER_LANGUAGE = {
    "best-in-class",
    "world-class",
    "visionary",
    "thought leader",
}

EXECUTIVE_INFLATION_PATTERNS = [
    r"\bexecutive leadership\b",
    r"\bc-suite\b",
    r"\bceo\b",
    r"\bcto\b",
    r"\bboardroom\b",
    r"\bp&l owner\b",
    r"\bp&l ownership\b",
]

DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_CODEX_TIMEOUT_SECONDS = 420

MIN_LEDGER_BY_PRIORITY = {
    "primary_target": 8,
    "secondary_target": 6,
    "tertiary_target": 6,
}

RUBRIC_VERSION = time.strftime("%Y-%m-%d")


# ---------- IO helpers ----------


def log_stage(message: str, verbose: bool = False, always: bool = False) -> None:
    if verbose or always:
        print(message)


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


def build_debug_run_dir(category_id: str) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = DEBUG_DIR / category_id / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_attempt_debug(
    run_dir: Path,
    attempt: int,
    stage: str,
    prompt: str,
    response_payload: Optional[Dict[str, Any]] = None,
    parsed_rubric: Optional[Dict[str, Any]] = None,
    issues: Optional[Sequence[str]] = None,
) -> None:
    prefix = f"attempt_{attempt:02d}_{stage}"
    (run_dir / f"{prefix}_prompt.txt").write_text(prompt)
    if response_payload is not None:
        write_json_file(run_dir / f"{prefix}_response_meta.json", response_payload.get("meta", {}))
        raw_output = str(response_payload.get("raw_output", ""))
        (run_dir / f"{prefix}_raw_output.txt").write_text(raw_output)
    if parsed_rubric is not None:
        write_json_file(run_dir / f"{prefix}_parsed_rubric.json", parsed_rubric)
    if issues is not None:
        write_json_file(run_dir / f"{prefix}_issues.json", list(issues))


def load_blueprint(category_id: str) -> Dict[str, Any]:
    path = BLUEPRINT_DIR / f"{category_id}_blueprint.json"
    with open(path) as f:
        return json.load(f)


def load_baseline(category_id: str) -> Optional[Dict[str, Any]]:
    path = BASELINE_DIR / f"{category_id}_baseline.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_categories() -> List[str]:
    return sorted(
        p.stem.replace("_blueprint", "")
        for p in BLUEPRINT_DIR.glob("*_blueprint.json")
    )


# ---------- input summary ----------


def build_input_summary(
    blueprint: Dict[str, Any],
    baseline: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compact input summary fed into the rubric prompt."""
    meta = blueprint.get("meta", {})
    summary: Dict[str, Any] = {
        "category_id": meta.get("category_id"),
        "category_name": meta.get("category_name"),
        "macro_family": meta.get("macro_family"),
        "priority": meta.get("priority"),
        "confidence": meta.get("confidence"),
        "total_jobs": meta.get("total_jobs"),
        "blueprint": {
            "category_signature": blueprint.get("category_signature", {}),
            "headline_pattern": blueprint.get("headline_pattern", {}),
            "tagline_profile_angle": blueprint.get("tagline_profile_angle", {}),
            "core_competency_themes": blueprint.get("core_competency_themes", []),
            "key_achievement_archetypes": blueprint.get("key_achievement_archetypes", []),
            "role_weighting_guidance": blueprint.get("role_weighting_guidance", {}),
            "language_and_tone": blueprint.get("language_and_tone", {}),
            "unsafe_or_weak_framing": blueprint.get("unsafe_or_weak_framing", {}),
        },
    }
    if baseline is not None:
        summary["baseline"] = {
            "overall_assessment": baseline.get("overall_assessment", {}),
            "score_breakdown": baseline.get("score_breakdown", {}),
            "strongest_supported_signals": baseline.get("strongest_supported_signals", []),
            "gap_analysis_top": (baseline.get("gap_analysis", []) or [])[:10],
            "safe_claims_now": baseline.get("safe_claims_now", {}),
            "representation_diagnosis": baseline.get("representation_diagnosis", {}),
            "curation_priorities_top": (baseline.get("curation_priorities", []) or [])[:8],
        }
    return summary


# ---------- prompt ----------


def _family_presence_guidance(category_id: str, macro_family: str) -> str:
    cid = category_id.lower()
    if cid.startswith("ai_architect"):
        return (
            "ARCHITECT CATEGORY: interpret executive_presence as architectural authority and "
            "system ownership (platform design, governance, production AI integration, stakeholder "
            "translation). DO NOT reward direct-reports/C-suite/P&L framing as executive_presence."
        )
    if cid.startswith("staff_ai_engineer") or cid.startswith("senior_ai_engineer") or cid.startswith("principal"):
        return (
            "STAFF/SENIOR IC CATEGORY: interpret executive_presence as senior IC authority, "
            "technical judgment, cross-team influence WITHOUT formal management. "
            "Penalize manager/director/VP framing as persona inflation."
        )
    if cid.startswith("head_of_ai"):
        return (
            "HEAD-OF-AI CATEGORY (architect-first / player-coach-safe): this candidate's evidence "
            "supports architect-first player-coach framing. Interpret executive_presence as "
            "player-coach AI platform leadership. Do NOT force executive / boardroom inflation. "
            "Only reward stronger management framing when baseline evidence explicitly supports it."
        )
    if "tech_lead" in cid or "ai_eng_manager" in cid:
        return (
            "TECH-LEAD / ENG-MANAGER CATEGORY: interpret executive_presence as hands-on team "
            "leadership + delivery ownership. Avoid director/VP framing unless evidence supports."
        )
    return f"macro_family={macro_family}: interpret executive_presence proportionally to evidenced scope."


def build_prompt(
    category_id: str,
    blueprint: Dict[str, Any],
    baseline: Optional[Dict[str, Any]],
    input_summary: Dict[str, Any],
    validation_feedback: Optional[Sequence[str]] = None,
) -> str:
    meta = blueprint.get("meta", {})
    priority = str(meta.get("priority", ""))
    min_ledger = MIN_LEDGER_BY_PRIORITY.get(priority, 6)
    family_guidance = _family_presence_guidance(category_id, str(meta.get("macro_family", "")))
    feedback_block = ""
    if validation_feedback:
        feedback_lines = "\n".join(f"- {issue}" for issue in validation_feedback)
        feedback_block = (
            "\nPREVIOUS ATTEMPT FAILED VALIDATION\n"
            "Fix EVERY issue below in the next JSON response:\n"
            f"{feedback_lines}\n"
        )

    return f"""
You are an evidence-bound CV evaluation rubric synthesizer.

Your job: produce a reusable Category Eval Rubric that a downstream scorer will apply to candidate CVs (generated or edited) for this specific job category. The rubric must be category-specific, evidence-first, and safe against hallucination and title inflation.

CATEGORY META
- category_id: {category_id}
- category_name: {meta.get("category_name")}
- macro_family: {meta.get("macro_family")}
- priority: {meta.get("priority")}
- confidence: {meta.get("confidence")}
- rubric_version: {RUBRIC_VERSION}

FAMILY-SPECIFIC PERSONA GUIDANCE
{family_guidance}

FIVE SCORED DIMENSIONS (FIXED WEIGHTS — SUM = 100)
- ats_optimization: 20
- impact_clarity: 25
- jd_alignment: 25
- executive_presence: 15
- anti_hallucination: 15

VERDICT THRESHOLDS (FIXED)
- strong_match_min: 8.5
- good_match_min: 7.0
- needs_work_min: 5.5
- weak_match_max: 5.49

EVIDENCE INPUT (BLUEPRINT + BASELINE SUMMARY)
{json.dumps(input_summary, indent=2)}
{feedback_block}
YOUR TASK
Return ONE valid JSON rubric object. No markdown. No preamble.

Every major section MUST carry citations (clean path references only — see format rules below). Each dimension MUST have Layer A (category_core) + Layer B (job_specific_overlay) + full score_anchors (9_10, 7_8, 5_6, 0_4) + red_flags + citations.

CITATION FORMAT (CRITICAL)
Every citation MUST be a clean path reference — NOT a narrative string.
- Correct: "data/eval/blueprints/{category_id}_blueprint.json"
- Correct: "data/eval/baselines/{category_id}_baseline.json"
- Correct: "data/master-cv/projects/commander4.md:12"
- Wrong:   "strong evidence in blueprint — data/eval/..."
- Allowed prefixes: data/eval/, data/master-cv/, docs/

EXECUTIVE PRESENCE RULES
- For architect/staff/senior-IC categories: DO NOT describe executive_presence as literal executive leadership, C-suite, boardroom, or P&L ownership. Frame it as architectural / IC authority.
- For head_of_ai_* (architect-first player-coach-safe): frame it as player-coach leadership.
- Penalty criteria in red_flags MUST include "unsupported people-management framing" or equivalent.

ANTI-HALLUCINATION RULES
- `anti_hallucination` dimension MUST include:
  - red_flags listing unsupported metrics, fabricated titles, PhD/publication inflation, unsupported scope of reports
  - score anchors that explicitly penalize unsourced numbers and unsupported claims
  - category-specific unsafe_or_weak_framing items from the blueprint

FORBIDDEN LANGUAGE
- Do NOT use: "best-in-class", "world-class", "visionary", "thought leader".

EVIDENCE LEDGER
- Minimum {min_ledger} entries for this category ({priority}).
- Each entry: rubric_rule (what rule), support (citations), confidence (high|medium|low).

JSON SCHEMA (STRICT — OUTPUT MUST CONFORM EXACTLY)
{{
  "meta": {{
    "category_id": "{category_id}",
    "category_name": "{meta.get('category_name')}",
    "macro_family": "{meta.get('macro_family')}",
    "priority": "{meta.get('priority')}",
    "confidence": "{meta.get('confidence')}",
    "rubric_version": "{RUBRIC_VERSION}"
  }},
  "rubric_identity": {{
    "one_sentence_purpose": "string",
    "core_persona": "string",
    "job_overlay_notes": ["string", ...],
    "citations": ["string", ...]
  }},
  "dimension_rubrics": [
    {{
      "dimension": "ats_optimization|impact_clarity|jd_alignment|executive_presence|anti_hallucination",
      "weight": 20|25|25|15|15,
      "category_core": {{
        "what_good_looks_like": ["string", ...],
        "common_failures": ["string", ...]
      }},
      "job_specific_overlay": {{
        "what_to_adjust_per_jd": ["string", ...],
        "company_domain_overrides": ["string", ...],
        "region_overrides": ["string", ...]
      }},
      "score_anchors": {{
        "9_10": ["string", ...],
        "7_8": ["string", ...],
        "5_6": ["string", ...],
        "0_4": ["string", ...]
      }},
      "red_flags": ["string", ...],
      "citations": ["string", ...]
    }}
    // EXACTLY 5 entries, one per dimension, weights sum to 100
  ],
  "gates": {{
    "must_have_coverage_gate": {{
      "pass_criteria": ["string", ...],
      "fail_conditions": ["string", ...],
      "citations": ["string", ...]
    }},
    "unsafe_claim_gate": {{
      "pass_criteria": ["string", ...],
      "fail_conditions": ["string", ...],
      "citations": ["string", ...]
    }},
    "persona_fit_gate": {{
      "pass_criteria": ["string", ...],
      "fail_conditions": ["string", ...],
      "citations": ["string", ...]
    }}
  }},
  "verdict_thresholds": {{
    "strong_match_min": 8.5,
    "good_match_min": 7.0,
    "needs_work_min": 5.5,
    "weak_match_max": 5.49
  }},
  "scoring_guidance": {{
    "how_to_interpret_executive_presence": "string",
    "how_to_penalize_unsupported_claims": "string",
    "how_to_handle_category_vs_job_tradeoffs": "string",
    "citations": ["string", ...]
  }},
  "scorecard_template_mapping": {{
    "dimension_keys": ["ats_optimization","impact_clarity","jd_alignment","executive_presence","anti_hallucination"],
    "gate_keys": ["must_have_coverage_gate","unsafe_claim_gate","persona_fit_gate"],
    "required_output_fields": ["overall_score","verdict","top_strengths","top_failures","unsupported_claims","missing_must_haves"]
  }},
  "evidence_ledger": [
    {{"rubric_rule": "string", "support": ["string", ...], "confidence": "high|medium|low"}}
    // minimum {min_ledger} entries
  ]
}}

QUALITY BAR
- Rubric must meaningfully differ from nearby categories in the same macro family.
- Layer B (job_specific_overlay) must call out concrete axes of variation (stack, domain, region, company stage).
- Gates must cite actual blueprint must-have signals and unsafe framing.
- Evidence ledger MUST tie each rubric rule to a specific blueprint or baseline location.
""".strip()


# ---------- validation ----------


def _iter_strings(value: Any, skip_keys: Optional[set] = None) -> Iterable[str]:
    skip_keys = skip_keys or set()
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if k in skip_keys:
                continue
            yield from _iter_strings(v, skip_keys)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_strings(item, skip_keys)


def _text_block(value: Any, skip_keys: Optional[set] = None) -> str:
    return "\n".join(_iter_strings(value, skip_keys)).lower()


def _is_clean_ref(value: str) -> bool:
    v = value.strip()
    return v.startswith("data/eval/") or v.startswith("data/master-cv/") or v.startswith("docs/")


def validate_citations_list(citations: Any, section_label: str) -> List[str]:
    issues = []
    if not isinstance(citations, list) or not citations:
        issues.append(f"{section_label} must include at least one citation")
        return issues
    for idx, c in enumerate(citations):
        if not isinstance(c, str) or not _is_clean_ref(c):
            issues.append(
                f"{section_label} citation[{idx}] must be a clean path ref starting with "
                f"data/eval/, data/master-cv/, or docs/ (got: {str(c)[:80]!r})"
            )
    return issues


def validate_rubric(rubric: Dict[str, Any], blueprint: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    meta = blueprint.get("meta", {})
    category_id = str(meta.get("category_id", ""))
    priority = str(meta.get("priority", ""))
    min_ledger = MIN_LEDGER_BY_PRIORITY.get(priority, 6)

    for key in TOP_LEVEL_KEYS:
        if key not in rubric:
            issues.append(f"missing top-level section: {key}")
    if issues:
        return issues

    # meta
    r_meta = rubric.get("meta", {})
    for k in ["category_id", "category_name", "macro_family", "priority", "confidence", "rubric_version"]:
        if not r_meta.get(k):
            issues.append(f"meta.{k} missing or empty")
    if r_meta.get("category_id") != category_id:
        issues.append(f"meta.category_id must equal {category_id!r}")

    # rubric_identity
    identity = rubric.get("rubric_identity", {})
    if not identity.get("one_sentence_purpose"):
        issues.append("rubric_identity.one_sentence_purpose missing")
    if not identity.get("core_persona"):
        issues.append("rubric_identity.core_persona missing")
    if not identity.get("job_overlay_notes"):
        issues.append("rubric_identity.job_overlay_notes must be non-empty")
    issues.extend(validate_citations_list(identity.get("citations"), "rubric_identity.citations"))

    # dimension rubrics
    dims = rubric.get("dimension_rubrics", [])
    if not isinstance(dims, list) or len(dims) != 5:
        issues.append("dimension_rubrics must contain exactly 5 entries")
    else:
        seen = set()
        weight_sum = 0
        for idx, d in enumerate(dims, 1):
            label = f"dimension_rubrics[{idx}]"
            dim_key = d.get("dimension")
            if dim_key not in DIMENSION_KEYS:
                issues.append(f"{label}.dimension must be one of {DIMENSION_KEYS}")
                continue
            if dim_key in seen:
                issues.append(f"{label}.dimension duplicated: {dim_key}")
            seen.add(dim_key)
            weight = d.get("weight")
            if weight != DIMENSION_WEIGHTS[dim_key]:
                issues.append(f"{label}.weight must be {DIMENSION_WEIGHTS[dim_key]} for {dim_key}")
            else:
                weight_sum += int(weight)
            core = d.get("category_core", {})
            if not core.get("what_good_looks_like") or not core.get("common_failures"):
                issues.append(f"{label}.category_core incomplete")
            overlay = d.get("job_specific_overlay", {})
            if not overlay.get("what_to_adjust_per_jd"):
                issues.append(f"{label}.job_specific_overlay.what_to_adjust_per_jd empty")
            anchors = d.get("score_anchors", {})
            for anchor_key in ["9_10", "7_8", "5_6", "0_4"]:
                if not anchors.get(anchor_key):
                    issues.append(f"{label}.score_anchors.{anchor_key} empty")
            if not d.get("red_flags"):
                issues.append(f"{label}.red_flags empty")
            issues.extend(validate_citations_list(d.get("citations"), f"{label}.citations"))
        missing = set(DIMENSION_KEYS) - seen
        if missing:
            issues.append(f"dimension_rubrics missing dimensions: {sorted(missing)}")
        if dims and weight_sum != 100:
            issues.append(f"dimension_rubrics weights must sum to 100 (got {weight_sum})")

    # gates
    gates = rubric.get("gates", {})
    for gk in GATE_KEYS:
        g = gates.get(gk, {})
        if not g.get("pass_criteria"):
            issues.append(f"gates.{gk}.pass_criteria empty")
        if not g.get("fail_conditions"):
            issues.append(f"gates.{gk}.fail_conditions empty")
        issues.extend(validate_citations_list(g.get("citations"), f"gates.{gk}.citations"))

    # verdict thresholds
    vt = rubric.get("verdict_thresholds", {})
    for k, v in VERDICT_THRESHOLDS.items():
        if vt.get(k) != v:
            issues.append(f"verdict_thresholds.{k} must equal {v} (got {vt.get(k)})")

    # scoring guidance
    sg = rubric.get("scoring_guidance", {})
    for k in ["how_to_interpret_executive_presence", "how_to_penalize_unsupported_claims", "how_to_handle_category_vs_job_tradeoffs"]:
        if not sg.get(k):
            issues.append(f"scoring_guidance.{k} missing")
    issues.extend(validate_citations_list(sg.get("citations"), "scoring_guidance.citations"))

    # scorecard mapping
    sm = rubric.get("scorecard_template_mapping", {})
    if sorted(sm.get("dimension_keys") or []) != sorted(DIMENSION_KEYS):
        issues.append("scorecard_template_mapping.dimension_keys must match the 5 fixed dimensions")
    if sorted(sm.get("gate_keys") or []) != sorted(GATE_KEYS):
        issues.append("scorecard_template_mapping.gate_keys must match the 3 fixed gates")
    if not sm.get("required_output_fields"):
        issues.append("scorecard_template_mapping.required_output_fields empty")

    # evidence ledger
    ledger = rubric.get("evidence_ledger", [])
    if not isinstance(ledger, list) or len(ledger) < min_ledger:
        issues.append(f"evidence_ledger must contain at least {min_ledger} entries (got {len(ledger) if isinstance(ledger, list) else 'n/a'})")
    else:
        for idx, entry in enumerate(ledger, 1):
            if not entry.get("rubric_rule"):
                issues.append(f"evidence_ledger[{idx}].rubric_rule empty")
            support = entry.get("support")
            if not isinstance(support, list) or not support:
                issues.append(f"evidence_ledger[{idx}].support empty")
            else:
                for sidx, ref in enumerate(support):
                    if not isinstance(ref, str) or not _is_clean_ref(ref):
                        issues.append(
                            f"evidence_ledger[{idx}].support[{sidx}] must be a clean path ref (got: {str(ref)[:80]!r})"
                        )
            if entry.get("confidence") not in ("high", "medium", "low"):
                issues.append(f"evidence_ledger[{idx}].confidence must be high|medium|low")

    # global forbidden language in all text (skipping citations)
    skip = {"citations", "support", "citation"}
    text = _text_block(rubric, skip_keys=skip)
    for phrase in PLACEHOLDER_LANGUAGE:
        if phrase in text:
            issues.append(f"forbidden placeholder language found: {phrase!r}")

    # executive presence rule for architect / staff / senior / principal categories
    cid_low = category_id.lower()
    if cid_low.startswith("ai_architect") or cid_low.startswith("staff_") or cid_low.startswith("senior_") or cid_low.startswith("principal"):
        ep_dim = next((d for d in dims if d.get("dimension") == "executive_presence"), {})
        positive_scope = {
            "what_good_looks_like": ep_dim.get("category_core", {}).get("what_good_looks_like", []),
            "9_10": ep_dim.get("score_anchors", {}).get("9_10", []),
            "7_8": ep_dim.get("score_anchors", {}).get("7_8", []),
        }
        ep_text = _text_block(positive_scope)
        if any(re.search(p, ep_text) for p in EXECUTIVE_INFLATION_PATTERNS):
            issues.append(
                "executive_presence frames the category as literal executive leadership — "
                "reframe as architectural or senior IC authority"
            )

    return issues


# ---------- LLM calls ----------


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_rubric_claude(prompt: str, category_id: str) -> Dict[str, Any]:
    from src.common.unified_llm import invoke_unified_sync

    result = invoke_unified_sync(
        prompt=prompt,
        step_name="eval_rubric_generation",
        job_id=category_id,
        validate_json=True,
    )
    if not result.success:
        error = result.error or f"LLM failed for {category_id}"
        lowered = error.lower()
        if "not logged in" in lowered or "/login" in lowered:
            raise PermissionError("Claude CLI is not authenticated. Run `claude /login` and rerun.")
        raise RuntimeError(error)
    if not result.parsed_json:
        raise ValueError(f"LLM returned no parsed JSON for {category_id}")
    return {
        "provider": "claude",
        "parsed_json": result.parsed_json,
        "raw_output": result.content,
        "meta": {
            "model": result.model,
            "tier": result.tier,
            "duration_ms": result.duration_ms,
            "backend": result.backend,
        },
    }


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_rubric_codex(
    prompt: str,
    category_id: str,
    model: str,
    timeout_seconds: int,
    verbose: bool,
    heartbeat_seconds: int,
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="step7_codex_") as temp_dir:
        temp_path = Path(temp_dir)
        output_path = temp_path / "last_message.json"
        stdout_path = temp_path / "codex_stdout.log"
        stderr_path = temp_path / "codex_stderr.log"
        command = [
            "codex", "exec", "-m", model,
            "--full-auto", "--ephemeral",
            "--output-last-message", str(output_path),
            "-",
        ]
        log_stage(f"    codex launch: category={category_id}, model={model}, timeout={timeout_seconds}s", verbose)
        start_time = time.monotonic()
        next_heartbeat = heartbeat_seconds
        with open(stdout_path, "w") as so, open(stderr_path, "w") as se:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=so, stderr=se, text=True, cwd=ROOT_DIR,
            )
            assert process.stdin is not None
            process.stdin.write(prompt)
            process.stdin.close()
            while True:
                return_code = process.poll()
                elapsed = int(time.monotonic() - start_time)
                if return_code is not None:
                    break
                if elapsed >= timeout_seconds:
                    process.kill()
                    process.wait(timeout=5)
                    raise RuntimeError(f"Codex generation timed out after {timeout_seconds}s")
                if verbose and elapsed >= next_heartbeat:
                    print(f"    heartbeat: elapsed={elapsed}s, pid={process.pid}")
                    next_heartbeat += heartbeat_seconds
                time.sleep(1)
        stdout = stdout_path.read_text().strip() if stdout_path.exists() else ""
        stderr = stderr_path.read_text().strip() if stderr_path.exists() else ""
        if return_code != 0:
            error_text = stderr or stdout or f"Codex exited with code {return_code}"
            raise RuntimeError(error_text)
        if not output_path.exists():
            raise ValueError("Codex did not write the final message file")
        raw_output = output_path.read_text().strip()
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            parsed = parse_llm_json(raw_output)
            if not isinstance(parsed, dict):
                raise ValueError("Codex final message was not a JSON object")
        return {
            "provider": "codex",
            "parsed_json": parsed,
            "raw_output": raw_output,
            "meta": {"model": model, "timeout_seconds": timeout_seconds},
        }


# ---------- generation ----------


def generate_rubric(
    category_id: str,
    blueprint: Dict[str, Any],
    baseline: Optional[Dict[str, Any]],
    max_attempts: int,
    provider: str,
    model: str,
    timeout_seconds: int,
    verbose: bool,
    heartbeat_seconds: int,
) -> Dict[str, Any]:
    input_summary = build_input_summary(blueprint, baseline)
    run_dir = build_debug_run_dir(category_id)
    write_json_file(run_dir / "input_summary.json", input_summary)
    validation_feedback: List[str] = []

    for attempt in range(1, max_attempts + 1):
        log_stage(f"  attempt {attempt}/{max_attempts} started", always=True)
        prompt = build_prompt(
            category_id=category_id,
            blueprint=blueprint,
            baseline=baseline,
            input_summary=input_summary,
            validation_feedback=validation_feedback or None,
        )
        if provider == "claude":
            response = call_rubric_claude(prompt, category_id)
        elif provider == "codex":
            response = call_rubric_codex(prompt, category_id, model, timeout_seconds, verbose, heartbeat_seconds)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        rubric = response["parsed_json"]
        write_attempt_debug(run_dir, attempt, "initial", prompt, response, rubric)
        issues = validate_rubric(rubric, blueprint)
        if not issues:
            write_attempt_debug(run_dir, attempt, "accepted", prompt, response, rubric, issues=[])
            return rubric
        validation_feedback = issues
        write_attempt_debug(run_dir, attempt, "rejected", prompt, response, rubric, issues=issues)
        print(f"  attempt {attempt}/{max_attempts} rejected ({len(issues)} issues):")
        for issue in issues[:10]:
            print(f"    - {issue}")
    raise ValueError(f"Rubric validation failed for {category_id} after {max_attempts} attempts")


# ---------- markdown rendering ----------


def render_rubric_markdown(rubric: Dict[str, Any]) -> str:
    meta = rubric["meta"]
    identity = rubric["rubric_identity"]
    lines: List[str] = []
    lines.append(f"# {meta['category_name']} — Eval Rubric")
    lines.append("")
    lines.append("## Meta")
    lines.append(f"- Category ID: {meta['category_id']}")
    lines.append(f"- Macro family: {meta['macro_family']}")
    lines.append(f"- Priority: {meta['priority']}")
    lines.append(f"- Confidence: {meta['confidence']}")
    lines.append(f"- Rubric version: {meta['rubric_version']}")
    lines.append("")
    lines.append("## Identity")
    lines.append(f"- Purpose: {identity['one_sentence_purpose']}")
    lines.append(f"- Core persona: {identity['core_persona']}")
    lines.append("Job overlay notes:")
    for n in identity.get("job_overlay_notes", []):
        lines.append(f"- {n}")
    lines.append("Citations:")
    for c in identity.get("citations", []):
        lines.append(f"- {c}")
    lines.append("")

    lines.append("## Dimension Rubrics")
    for d in rubric.get("dimension_rubrics", []):
        lines.append(f"### {d['dimension']} (weight {d['weight']})")
        core = d.get("category_core", {})
        lines.append("**Layer A — Category core**")
        lines.append("What good looks like:")
        for item in core.get("what_good_looks_like", []):
            lines.append(f"- {item}")
        lines.append("Common failures:")
        for item in core.get("common_failures", []):
            lines.append(f"- {item}")
        overlay = d.get("job_specific_overlay", {})
        lines.append("**Layer B — Job-specific overlay**")
        lines.append("Adjust per JD:")
        for item in overlay.get("what_to_adjust_per_jd", []):
            lines.append(f"- {item}")
        if overlay.get("company_domain_overrides"):
            lines.append("Company/domain overrides:")
            for item in overlay["company_domain_overrides"]:
                lines.append(f"- {item}")
        if overlay.get("region_overrides"):
            lines.append("Region overrides:")
            for item in overlay["region_overrides"]:
                lines.append(f"- {item}")
        anchors = d.get("score_anchors", {})
        lines.append("**Score anchors**")
        for anchor_key, label in [("9_10", "9-10"), ("7_8", "7-8"), ("5_6", "5-6"), ("0_4", "<=4")]:
            lines.append(f"- {label}:")
            for item in anchors.get(anchor_key, []):
                lines.append(f"  - {item}")
        lines.append("Red flags:")
        for item in d.get("red_flags", []):
            lines.append(f"- {item}")
        lines.append("Citations:")
        for c in d.get("citations", []):
            lines.append(f"- {c}")
        lines.append("")

    lines.append("## Gates")
    for gk in GATE_KEYS:
        g = rubric.get("gates", {}).get(gk, {})
        lines.append(f"### {gk}")
        lines.append("Pass criteria:")
        for item in g.get("pass_criteria", []):
            lines.append(f"- {item}")
        lines.append("Fail conditions:")
        for item in g.get("fail_conditions", []):
            lines.append(f"- {item}")
        lines.append("Citations:")
        for c in g.get("citations", []):
            lines.append(f"- {c}")
        lines.append("")

    vt = rubric.get("verdict_thresholds", {})
    lines.append("## Verdict Thresholds")
    lines.append(f"- STRONG_MATCH >= {vt.get('strong_match_min')}")
    lines.append(f"- GOOD_MATCH   >= {vt.get('good_match_min')}")
    lines.append(f"- NEEDS_WORK   >= {vt.get('needs_work_min')}")
    lines.append(f"- WEAK_MATCH   <= {vt.get('weak_match_max')}")
    lines.append("")

    sg = rubric.get("scoring_guidance", {})
    lines.append("## Scoring Guidance")
    lines.append(f"- Executive presence: {sg.get('how_to_interpret_executive_presence')}")
    lines.append(f"- Unsupported claims: {sg.get('how_to_penalize_unsupported_claims')}")
    lines.append(f"- Category vs job tradeoffs: {sg.get('how_to_handle_category_vs_job_tradeoffs')}")
    lines.append("Citations:")
    for c in sg.get("citations", []):
        lines.append(f"- {c}")
    lines.append("")

    lines.append("## Evidence Ledger")
    for item in rubric.get("evidence_ledger", []):
        lines.append(f"- [{item.get('confidence')}] {item.get('rubric_rule')}")
        for s in item.get("support", []):
            lines.append(f"  - {s}")

    return "\n".join(lines).rstrip() + "\n"


# ---------- file outputs ----------


def write_rubric_files(category_id: str, rubric: Dict[str, Any]) -> None:
    write_json_file(RUBRIC_DIR / f"{category_id}_rubric.json", rubric)
    (RUBRIC_DIR / f"{category_id}_rubric.md").write_text(render_rubric_markdown(rubric))


def write_scorecard_template() -> None:
    template = {
        "$schema": "cv-eval-scorecard/v1",
        "rubric_version": RUBRIC_VERSION,
        "category_id": None,
        "job_id": None,
        "dimension_scores": {k: None for k in DIMENSION_KEYS},
        "gate_outcomes": {k: None for k in GATE_KEYS},
        "overall_score": None,
        "verdict": None,
        "top_strengths": [],
        "top_failures": [],
        "unsupported_claims": [],
        "missing_must_haves": [],
        "persona_fit_notes": [],
        "representation_gap_hits": [],
        "curation_gap_hits": [],
        "evidence_refs": [],
        "meta": {
            "generated_at": None,
            "scorer_model": None,
            "rubric_path": None,
            "blueprint_path": None,
            "baseline_path": None,
        },
    }
    write_json_file(RUBRIC_DIR / "scorecard_template.json", template)


def write_stage_scorecard_template() -> None:
    stages = {
        "pain_point_extraction": ["coverage", "specificity", "grounding", "prioritization"],
        "jd_extraction": ["accuracy", "completeness", "seniority_detection"],
        "role_bullet_selection": [
            "pain_point_coverage",
            "achievement_relevance",
            "aris_format_compliance",
            "metric_grounding",
            "keyword_integration",
        ],
        "header_generation": [
            "headline_accuracy",
            "tagline_evidence_first",
            "achievement_diversity",
            "competency_coverage",
        ],
        "competency_selection": [
            "section_coverage",
            "jd_keyword_match",
            "whitelist_compliance",
            "ats_density",
        ],
        "grading": [
            "score_accuracy",
            "improvement_effectiveness",
            "hallucination_detection",
        ],
        "fit_analysis": ["score_calibration", "rationale_quality", "gap_identification"],
    }
    template = {
        "$schema": "cv-eval-stage-scorecard/v0-placeholder",
        "rubric_version": RUBRIC_VERSION,
        "job_id": None,
        "category_id": None,
        "stage": None,
        "expected_stage_dimensions": stages,
        "stage_scores": {},
        "stage_verdict": None,
        "bottleneck_contribution": None,
        "specific_failures": [],
        "improvement_suggestions": [],
        "meta": {
            "note": "Step 8b placeholder — stage-level scoring not yet implemented. "
                    "Future scorer should populate stage_scores using expected_stage_dimensions.",
        },
    }
    write_json_file(RUBRIC_DIR / "stage_scorecard_template.json", template)


def render_index() -> None:
    rows = []
    for path in sorted(RUBRIC_DIR.glob("*_rubric.json")):
        with open(path) as f:
            rubric = json.load(f)
        meta = rubric.get("meta", {})
        identity = rubric.get("rubric_identity", {})
        rows.append({
            "category_id": meta.get("category_id", path.stem.replace("_rubric", "")),
            "category_name": meta.get("category_name", path.stem),
            "priority": meta.get("priority", ""),
            "confidence": meta.get("confidence", ""),
            "rubric_version": meta.get("rubric_version", ""),
            "ledger": len(rubric.get("evidence_ledger", [])),
            "purpose": identity.get("one_sentence_purpose", ""),
        })
    lines = [
        "# Rubric Index",
        "",
        f"Generated rubrics: {len(rows)}",
        "",
        "| Category | Priority | Confidence | Version | Ledger |",
        "|----------|----------|------------|---------|--------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['category_name']} | {r['priority']} | {r['confidence']} | "
            f"{r['rubric_version']} | {r['ledger']} |"
        )
    lines.append("")
    for r in rows:
        lines.append(f"## {r['category_name']}")
        lines.append(f"- Category ID: {r['category_id']}")
        lines.append(f"- Purpose: {r['purpose']}")
        lines.append(f"- JSON: {r['category_id']}_rubric.json")
        lines.append(f"- Markdown: {r['category_id']}_rubric.md")
        lines.append("")
    (RUBRIC_DIR / "index.md").write_text("\n".join(lines).rstrip() + "\n")


def write_readme() -> None:
    content = f"""# CV Eval Rubrics (Step 7 / Step 8 / Step 8b)

This directory holds reusable category-level CV eval rubrics grounded in Step 5 blueprints and Step 6 baselines.

## Contents

- `{{category}}_rubric.json` — strict rubric JSON (contract defined in scripts/eval_step7_rubrics.py)
- `{{category}}_rubric.md` — deterministic Markdown render of the JSON
- `scorecard_template.json` — Step 8 scorecard template (populate per CV eval run)
- `stage_scorecard_template.json` — Step 8b placeholder (stage-level diagnostics)
- `index.md` — rubric index
- `debug/{{category}}/{{timestamp}}/` — per-run prompt/response/validation artifacts

## Rubric contract

5 dimensions with fixed weights summing to 100:
- ats_optimization (20), impact_clarity (25), jd_alignment (25), executive_presence (15), anti_hallucination (15)

3 gates: must_have_coverage_gate, unsafe_claim_gate, persona_fit_gate

Verdicts:
- STRONG_MATCH >= 8.5, GOOD_MATCH >= 7.0, NEEDS_WORK >= 5.5, WEAK_MATCH <= 5.49

## Persona framing by category family

- ai_architect_*: executive_presence = architectural authority / system ownership
- staff_ai_engineer_* / senior_* / principal_*: senior IC authority / judgment / influence, no formal management
- head_of_ai_*: player-coach AI platform leadership (architect-first, not executive inflation)

## Regeneration

```
python scripts/eval_step7_rubrics.py --force --provider claude --verbose
python scripts/eval_step7_rubrics.py --category ai_architect_global --force
python scripts/eval_step7_rubrics.py --render-only
```

Rubric version: {RUBRIC_VERSION}
"""
    (RUBRIC_DIR / "README.md").write_text(content)


def render_only() -> None:
    for path in sorted(RUBRIC_DIR.glob("*_rubric.json")):
        with open(path) as f:
            rubric = json.load(f)
        category_id = rubric.get("meta", {}).get("category_id", path.stem.replace("_rubric", ""))
        (RUBRIC_DIR / f"{category_id}_rubric.md").write_text(render_rubric_markdown(rubric))
    render_index()
    write_scorecard_template()
    write_stage_scorecard_template()
    write_readme()


# ---------- CLI ----------


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval Step 7: Generate reusable CV eval rubrics")
    parser.add_argument("--category", action="append", help="Process one or more category ids")
    parser.add_argument("--force", action="store_true", help="Regenerate existing rubric JSON files")
    parser.add_argument("--render-only", action="store_true", help="Render Markdown/index/templates from existing JSON")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
    parser.add_argument("--model", default=DEFAULT_CODEX_MODEL)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_CODEX_TIMEOUT_SECONDS)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--heartbeat-seconds", type=int, default=15)
    parser.add_argument(
        "--require-baseline",
        action="store_true",
        help="Skip categories without a Step 6 baseline file",
    )
    args = parser.parse_args()

    if args.render_only:
        render_only()
        print("Rendered Markdown/index/templates from existing rubric JSON files")
        return

    categories = args.category if args.category else list_categories()
    print(
        f"Step 7: Generating rubrics for {len(categories)} categories "
        f"(provider={args.provider}{', model=' + args.model if args.provider == 'codex' else ''})"
    )
    print()

    generated = skipped = failed = 0
    for category_id in categories:
        blueprint_path = BLUEPRINT_DIR / f"{category_id}_blueprint.json"
        baseline_path = BASELINE_DIR / f"{category_id}_baseline.json"
        output_path = RUBRIC_DIR / f"{category_id}_rubric.json"

        if not blueprint_path.exists():
            print(f"[{category_id}] skipped - missing blueprint JSON")
            skipped += 1
            continue
        if args.require_baseline and not baseline_path.exists():
            print(f"[{category_id}] skipped - missing baseline JSON (--require-baseline)")
            skipped += 1
            continue
        if output_path.exists() and not args.force:
            print(f"[{category_id}] skipped - rubric exists (use --force to regenerate)")
            skipped += 1
            continue

        blueprint = load_blueprint(category_id)
        baseline = load_baseline(category_id)

        print(f"[{category_id}] generating (baseline={'yes' if baseline else 'no'})...")
        try:
            rubric = generate_rubric(
                category_id=category_id,
                blueprint=blueprint,
                baseline=baseline,
                max_attempts=args.max_attempts,
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                verbose=args.verbose,
                heartbeat_seconds=args.heartbeat_seconds,
            )
            write_rubric_files(category_id, rubric)
            print(
                f"[{category_id}] done - dimensions={len(rubric.get('dimension_rubrics', []))}, "
                f"ledger={len(rubric.get('evidence_ledger', []))}"
            )
            generated += 1
        except Exception as exc:
            if isinstance(exc, RetryError) and exc.last_attempt.failed:
                inner_exc = exc.last_attempt.exception()
                if inner_exc is not None:
                    exc = inner_exc
            print(f"[{category_id}] failed - {exc}")
            failed += 1

    write_scorecard_template()
    write_stage_scorecard_template()
    render_index()
    write_readme()
    print()
    print(f"Step 7 complete: {generated} generated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
