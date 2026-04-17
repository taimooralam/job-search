#!/usr/bin/env python3
"""
Eval Step 9: Score generated CV outputs against Step 7 category rubrics.

Reads:
  data/eval/rubrics/{category}_rubric.json     (scoring source of truth)
  data/eval/rubrics/scorecard_template.json    (output shape)
  data/eval/raw/{category}/jobs_all.json       (authoritative job_id via ordinal)
  data/eval/raw/{category}/jd_texts/NN_*.md    (JD text)
  data/eval/normalized/{category}/normalized_jobs.json  (optional overlay)
  outputs/{company}/cv_{title}.md              (CV markdown)

Writes:
  data/eval/scorecards/{category}/{jd_stem}_scorecard.json
  data/eval/scorecards/{category}/{jd_stem}_scorecard.md
  data/eval/scorecards/index.md
  data/eval/scorecards/summary.md
  data/eval/scorecards/debug/{category}/{timestamp}/...

Usage:
  python scripts/eval_step9_score_cv_outputs.py --batch data/eval/scorecards/batches/step9_anchor_batch.json --provider claude --verbose
  python scripts/eval_step9_score_cv_outputs.py --category X --job-id ID --jd-path PATH --cv-path PATH
  python scripts/eval_step9_score_cv_outputs.py --render-only
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
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.common.json_utils import parse_llm_json

EVAL_DIR = Path("data/eval")
RUBRIC_DIR = EVAL_DIR / "rubrics"
RAW_DIR = EVAL_DIR / "raw"
NORM_DIR = EVAL_DIR / "normalized"
SCORECARD_DIR = EVAL_DIR / "scorecards"
SCORECARD_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR = SCORECARD_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

DIMENSION_WEIGHTS = {
    "ats_optimization": 20,
    "impact_clarity": 25,
    "jd_alignment": 25,
    "executive_presence": 15,
    "anti_hallucination": 15,
}
DIMENSION_KEYS = list(DIMENSION_WEIGHTS.keys())
GATE_KEYS = ["must_have_coverage_gate", "unsafe_claim_gate", "persona_fit_gate"]
VERDICTS = ["STRONG_MATCH", "GOOD_MATCH", "NEEDS_WORK", "WEAK_MATCH"]

IC_CATEGORY_PREFIXES = ("ai_architect_", "staff_", "senior_", "principal_", "tech_lead_")
EXEC_TITLE_TOKENS = [r"\bhead\b", r"\bvp\b", r"\bdirector\b", r"\bchief\b"]

DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_TIMEOUT_SECONDS = 300

ALLOWED_REF_PREFIXES = ("outputs/", "data/master-cv/", "data/eval/", "docs/")


# ---------- logging / io ----------


def log_stage(message: str, verbose: bool = False, always: bool = False) -> None:
    if verbose or always:
        print(message)


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


def build_debug_run_dir(category_id: str, jd_stem: str) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = DEBUG_DIR / category_id / f"{jd_stem}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_attempt_debug(
    run_dir: Path,
    attempt: int,
    stage: str,
    prompt: str,
    response_payload: Optional[Dict[str, Any]] = None,
    parsed_scorecard: Optional[Dict[str, Any]] = None,
    issues: Optional[Sequence[str]] = None,
    notes: Optional[Sequence[str]] = None,
) -> None:
    prefix = f"attempt_{attempt:02d}_{stage}"
    (run_dir / f"{prefix}_prompt.txt").write_text(prompt)
    if response_payload is not None:
        write_json_file(run_dir / f"{prefix}_response_meta.json", response_payload.get("meta", {}))
        raw = str(response_payload.get("raw_output", ""))
        (run_dir / f"{prefix}_raw_output.txt").write_text(raw)
    if parsed_scorecard is not None:
        write_json_file(run_dir / f"{prefix}_parsed_scorecard.json", parsed_scorecard)
    if issues is not None:
        write_json_file(run_dir / f"{prefix}_issues.json", list(issues))
    if notes is not None:
        write_json_file(run_dir / f"{prefix}_notes.json", list(notes))


# ---------- JD / job resolution ----------


JD_ORDINAL_RE = re.compile(r"^(\d{1,3})_")


def parse_jd_ordinal(jd_path: Path) -> int:
    m = JD_ORDINAL_RE.match(jd_path.name)
    if not m:
        raise ValueError(f"cannot parse leading ordinal from jd filename: {jd_path.name}")
    return int(m.group(1))


def resolve_job_from_jd(category_id: str, jd_path: Path) -> Dict[str, Any]:
    """Resolve the authoritative raw job record using the JD filename ordinal."""
    jobs_path = RAW_DIR / category_id / "jobs_all.json"
    if not jobs_path.exists():
        raise FileNotFoundError(f"missing jobs_all.json for category {category_id}: {jobs_path}")
    jobs = json.loads(jobs_path.read_text())
    ordinal = parse_jd_ordinal(jd_path)
    if ordinal < 1 or ordinal > len(jobs):
        raise ValueError(
            f"jd ordinal {ordinal} out of range for {category_id} (max {len(jobs)})"
        )
    return jobs[ordinal - 1]


def load_normalized_overlay(category_id: str, job_id: str) -> Optional[Dict[str, Any]]:
    path = NORM_DIR / category_id / "normalized_jobs.json"
    if not path.exists():
        return None
    try:
        records = json.loads(path.read_text())
    except Exception:
        return None
    for rec in records:
        if str(rec.get("job_id") or rec.get("_id") or "") == str(job_id):
            return rec
    return None


def prune_normalized_overlay(overlay: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep only the high-signal fields to keep the prompt compact."""
    if not overlay:
        return {}
    keep = [
        "title_normalized",
        "title_family",
        "seniority",
        "role_scope",
        "management",
        "architecture",
        "hard_skills_must_have",
        "hard_skills_nice_to_have",
        "programming_languages",
        "cloud_platform",
        "ai_ml_stack",
        "pain_points",
        "disqualifiers",
        "success_metrics",
    ]
    return {k: overlay.get(k) for k in keep if overlay.get(k) is not None}


def parse_jd_header(jd_text: str) -> Dict[str, str]:
    """Extract title/company/location from the JD file header block."""
    out: Dict[str, str] = {}
    lines = jd_text.splitlines()
    if lines and lines[0].startswith("# "):
        out["title"] = lines[0][2:].strip()
    for line in lines[:12]:
        m = re.match(r"\*\*(\w+):\*\*\s*(.*)", line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip()
    return out


def cross_check_job(jd_text: str, raw_job: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    header = parse_jd_header(jd_text)
    raw_title = str(raw_job.get("title", "")).strip()
    raw_company = str(raw_job.get("company", "")).strip()
    if header.get("title") and raw_title and header["title"].strip().lower() != raw_title.lower():
        issues.append(
            f"jd header title {header['title']!r} != raw job title {raw_title!r}"
        )
    if header.get("company") and raw_company and header["company"].strip().lower() != raw_company.lower():
        issues.append(
            f"jd header company {header['company']!r} != raw job company {raw_company!r}"
        )
    return issues


# ---------- text helpers ----------


def line_number_text(text: str) -> str:
    """Prefix each line with its 1-based line number for ref-grounding."""
    out_lines = []
    for idx, line in enumerate(text.splitlines(), start=1):
        out_lines.append(f"{idx:04d}: {line}")
    return "\n".join(out_lines)


def jd_stem_from_path(jd_path: Path) -> str:
    return jd_path.stem


# ---------- prompt ----------


def build_scoring_prompt(
    category_id: str,
    job_id: str,
    rubric: Dict[str, Any],
    template: Dict[str, Any],
    jd_text: str,
    cv_text: str,
    jd_path: str,
    cv_path: str,
    overlay: Dict[str, Any],
    raw_job_meta: Dict[str, Any],
    validation_feedback: Optional[Sequence[str]] = None,
) -> str:
    numbered_jd = line_number_text(jd_text)
    numbered_cv = line_number_text(cv_text)
    feedback_block = ""
    if validation_feedback:
        feedback_lines = "\n".join(f"- {i}" for i in validation_feedback)
        feedback_block = (
            "\nPREVIOUS ATTEMPT FAILED VALIDATION\n"
            "Fix EVERY issue below in the next JSON response:\n"
            f"{feedback_lines}\n"
        )
    return f"""
You are a rubric-bound CV evaluator.

You are scoring ONE CV against ONE JD, using the Step 7 category rubric as the scoring source of truth. Return ONE strict JSON scorecard only. No markdown. No preamble.

CATEGORY: {category_id}
JOB_ID: {job_id}
JD_PATH: {jd_path}
CV_PATH: {cv_path}

RAW JOB META (authoritative)
{json.dumps({k: raw_job_meta.get(k) for k in ["title", "company", "location", "score", "status"]}, indent=2)}

NORMALIZED OVERLAY (structured context only; do NOT re-classify)
{json.dumps(overlay, indent=2) if overlay else "(no normalized overlay available)"}

RUBRIC (source of truth — score against this)
{json.dumps(rubric, indent=2)}

SCORECARD TEMPLATE SHAPE (populate this exact shape; copy all top-level keys verbatim)
{json.dumps(template, indent=2)}
{feedback_block}
JD TEXT (line-numbered)
{numbered_jd}

CV MARKDOWN (line-numbered)
{numbered_cv}

STRICT RULES
- Return ONE JSON object only. No markdown fences. No explanatory text.
- Populate EVERY key from the scorecard template.
- `category_id` must equal "{category_id}"; `job_id` must equal "{job_id}".
- `dimension_scores`: numeric floats in [0, 10]. Keys exactly: ats_optimization, impact_clarity, jd_alignment, executive_presence, anti_hallucination.
- `gate_outcomes`: booleans. Keys exactly: must_have_coverage_gate, unsafe_claim_gate, persona_fit_gate.
- `overall_score`: weighted sum (20/25/25/15/15); Python will recompute and may override.
- `verdict`: one of STRONG_MATCH, GOOD_MATCH, NEEDS_WORK, WEAK_MATCH; Python may gate-cap it.
- `top_strengths`, `top_failures`, `unsupported_claims`, `missing_must_haves`, `persona_fit_notes`: each entry is a compact string ending with refs=<ref[,ref,...]>.
  Accepted ref shorthands: `cv:<line>` (points to CV_PATH), `jd:<line>` (points to JD_PATH), or a full path `outputs/... :line` / `data/master-cv/... :line` / `data/eval/... :line` / `docs/... :line`.
  Every entry MUST end with a `refs=...` suffix and at least one ref. Examples:
    - "Strong architecture framing in opening bullets refs=cv:9,cv:12"
    - "JD requires Kubernetes but CV silent on K8s refs=jd:45,cv:33"
- `evidence_refs`: deduped union of all refs cited across qualitative arrays, expanded to full paths, in stable order.
- `representation_gap_hits`, `curation_gap_hits`: may be empty lists if no gap observed.

SCORING RULES
- Use the rubric's dimension_rubrics[].score_anchors to pick scores.
- `executive_presence` is category-relative:
  * ai_architect_*: architectural authority and system ownership, NOT executive management
  * staff_*/senior_*/principal_*: senior IC authority, NOT people management
  * tech_lead_*: hands-on delivery leadership, NOT director/VP framing
  * head_of_ai_*: player-coach leadership unless stronger management evidence is real
- Do NOT infer claims from the JD back into the CV. Only credit what the CV actually states.
- Penalize title inflation, fabricated metrics, unsupported cloud/provider authority, and unsupported people-management scope inside `unsupported_claims` and drop `unsafe_claim_gate` accordingly.
- If the CV omits rubric must-have coverage items from `gates.must_have_coverage_gate.pass_criteria`, list them in `missing_must_haves` and drop `must_have_coverage_gate`.
- For IC/player-coach categories, if the CV uses literal Head/VP/Director/Executive framing without direct evidence in the CV text, drop `persona_fit_gate` and list the mismatch in `persona_fit_notes`.
- Keep qualitative arrays concise — 2-6 items each, not essays.

META
- Set meta.rubric_path = "data/eval/rubrics/{category_id}_rubric.json"
- Set meta.blueprint_path = "data/eval/blueprints/{category_id}_blueprint.json"
- Set meta.baseline_path = "data/eval/baselines/{category_id}_baseline.json"
- Set meta.scorer_model = "claude-opus-4-5-20251101" (or codex model if provider=codex; Python may overwrite)
- Set meta.generated_at = ISO-8601 timestamp (Python may overwrite)

OUTPUT: the populated scorecard JSON only.
""".strip()


# ---------- validation / repair ----------


SHORTHAND_RE = re.compile(r"^(cv|jd):\d+$", re.IGNORECASE)


def _is_clean_ref(ref: str) -> bool:
    if not isinstance(ref, str):
        return False
    r = ref.strip()
    if any(r.startswith(p) for p in ALLOWED_REF_PREFIXES):
        return True
    if SHORTHAND_RE.match(r):
        return True
    return False


def expand_ref(ref: str, cv_path: str, jd_path: str) -> str:
    """Expand shorthand refs to full paths. Leaves full paths unchanged."""
    if not isinstance(ref, str):
        return ref
    r = ref.strip()
    m = SHORTHAND_RE.match(r)
    if m:
        kind, _, line = r.partition(":")
        kind = kind.lower()
        if kind == "cv":
            return f"{cv_path}:{line}"
        if kind == "jd":
            return f"{jd_path}:{line}"
    return r


def expand_refs_in_entry(entry: str, cv_path: str, jd_path: str) -> str:
    if not isinstance(entry, str):
        return entry
    m = re.search(r"refs=([^\s]+)$", entry.strip())
    if not m:
        return entry
    raw_refs = [r.strip() for r in m.group(1).split(",") if r.strip()]
    expanded = [expand_ref(r, cv_path, jd_path) for r in raw_refs]
    prefix = entry[: m.start()].rstrip()
    return f"{prefix} refs={','.join(expanded)}"


def _extract_refs_from_entry(entry: str) -> List[str]:
    if not isinstance(entry, str):
        return []
    m = re.search(r"refs=([^\s]+)$", entry.strip())
    if not m:
        return []
    return [r.strip() for r in m.group(1).split(",") if r.strip()]


def base_verdict_from_score(score: float) -> str:
    if score >= 8.5:
        return "STRONG_MATCH"
    if score >= 7.0:
        return "GOOD_MATCH"
    if score >= 5.5:
        return "NEEDS_WORK"
    return "WEAK_MATCH"


def compute_overall_score(dim_scores: Dict[str, float]) -> float:
    total = 0.0
    for k, w in DIMENSION_WEIGHTS.items():
        total += float(dim_scores.get(k, 0) or 0) * w
    return round(total / 100.0, 2)


def validate_structure(scorecard: Dict[str, Any], category_id: str, job_id: str) -> List[str]:
    issues: List[str] = []
    required_keys = [
        "rubric_version", "category_id", "job_id",
        "dimension_scores", "gate_outcomes", "overall_score", "verdict",
        "top_strengths", "top_failures", "unsupported_claims", "missing_must_haves",
        "persona_fit_notes", "representation_gap_hits", "curation_gap_hits",
        "evidence_refs", "meta",
    ]
    for k in required_keys:
        if k not in scorecard:
            issues.append(f"missing top-level key: {k}")
    if issues:
        return issues

    if scorecard.get("category_id") != category_id:
        issues.append(f"category_id must equal {category_id!r}")
    if str(scorecard.get("job_id")) != str(job_id):
        issues.append(f"job_id must equal {job_id!r}")

    dim = scorecard.get("dimension_scores") or {}
    if not isinstance(dim, dict):
        issues.append("dimension_scores must be object")
    else:
        for k in DIMENSION_KEYS:
            v = dim.get(k)
            if not isinstance(v, (int, float)):
                issues.append(f"dimension_scores.{k} must be numeric (got {type(v).__name__})")
            elif not (0 <= float(v) <= 10):
                issues.append(f"dimension_scores.{k} must be in [0,10] (got {v})")
        extras = set(dim.keys()) - set(DIMENSION_KEYS)
        if extras:
            issues.append(f"dimension_scores has unknown keys: {sorted(extras)}")

    gates = scorecard.get("gate_outcomes") or {}
    if not isinstance(gates, dict):
        issues.append("gate_outcomes must be object")
    else:
        for k in GATE_KEYS:
            v = gates.get(k)
            if not isinstance(v, bool):
                issues.append(f"gate_outcomes.{k} must be boolean (got {type(v).__name__})")
        extras = set(gates.keys()) - set(GATE_KEYS)
        if extras:
            issues.append(f"gate_outcomes has unknown keys: {sorted(extras)}")

    # verdict label
    if scorecard.get("verdict") not in VERDICTS:
        issues.append(f"verdict must be one of {VERDICTS}")

    return issues


def validate_refs(scorecard: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    qual_keys = ["top_strengths", "top_failures", "unsupported_claims", "missing_must_haves", "persona_fit_notes"]
    for k in qual_keys:
        arr = scorecard.get(k) or []
        if not isinstance(arr, list):
            issues.append(f"{k} must be a list")
            continue
        for idx, entry in enumerate(arr):
            if not isinstance(entry, str) or not entry.strip():
                issues.append(f"{k}[{idx}] must be non-empty string")
                continue
            refs = _extract_refs_from_entry(entry)
            if not refs:
                issues.append(f"{k}[{idx}] missing refs=<path:line,...> suffix")
                continue
            for r in refs:
                if not _is_clean_ref(r):
                    issues.append(f"{k}[{idx}] ref not a clean path: {r!r}")

    ev = scorecard.get("evidence_refs") or []
    if not isinstance(ev, list):
        issues.append("evidence_refs must be a list")
    else:
        for idx, r in enumerate(ev):
            if not isinstance(r, str) or not _is_clean_ref(r):
                issues.append(f"evidence_refs[{idx}] not a clean path: {r!r}")
    return issues


def apply_lightweight_repairs(
    scorecard: Dict[str, Any],
    category_id: str,
    job_id: str,
    rubric_version: str,
    rubric_path: str,
    blueprint_path: str,
    baseline_path: str,
    scorer_model: str,
    cv_path: str,
    jd_path: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Deterministic fixes applied before model repair."""
    repaired = copy.deepcopy(scorecard)
    notes: List[str] = []

    # stable identity
    repaired["category_id"] = category_id
    repaired["job_id"] = str(job_id)
    repaired["rubric_version"] = rubric_version

    # meta fill-ins
    meta = repaired.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    meta.setdefault("rubric_path", rubric_path)
    meta.setdefault("blueprint_path", blueprint_path)
    meta.setdefault("baseline_path", baseline_path)
    meta["scorer_model"] = scorer_model
    meta["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["cv_path"] = cv_path
    meta["jd_path"] = jd_path
    repaired["meta"] = meta

    # coerce dim scores to floats if str-numeric
    dim = repaired.get("dimension_scores") or {}
    if isinstance(dim, dict):
        for k in DIMENSION_KEYS:
            v = dim.get(k)
            if isinstance(v, str):
                try:
                    dim[k] = float(v)
                    notes.append(f"coerced dimension_scores.{k} from string to float")
                except ValueError:
                    pass
        repaired["dimension_scores"] = dim

    # coerce gates to booleans if lowercase strings
    gates = repaired.get("gate_outcomes") or {}
    if isinstance(gates, dict):
        for k in GATE_KEYS:
            v = gates.get(k)
            if isinstance(v, str) and v.lower() in ("true", "false"):
                gates[k] = v.lower() == "true"
                notes.append(f"coerced gate_outcomes.{k} from string to bool")
        repaired["gate_outcomes"] = gates

    # ensure list fields exist
    for k in ["top_strengths", "top_failures", "unsupported_claims", "missing_must_haves",
              "persona_fit_notes", "representation_gap_hits", "curation_gap_hits", "evidence_refs"]:
        if not isinstance(repaired.get(k), list):
            repaired[k] = []
            notes.append(f"coerced {k} to list")

    # expand shorthand refs to full paths
    qual_keys = ["top_strengths", "top_failures", "unsupported_claims", "missing_must_haves", "persona_fit_notes"]
    for k in qual_keys:
        expanded_list = []
        for entry in repaired.get(k) or []:
            expanded_list.append(expand_refs_in_entry(entry, cv_path=cv_path, jd_path=jd_path))
        repaired[k] = expanded_list
    ev_expanded = []
    for r in repaired.get("evidence_refs") or []:
        ev_expanded.append(expand_ref(r, cv_path=cv_path, jd_path=jd_path))
    repaired["evidence_refs"] = ev_expanded

    return repaired, notes


def cross_check_gates(scorecard: Dict[str, Any], category_id: str) -> List[str]:
    """Semantic cross-checks. Emit issues only — caller decides how to cap."""
    issues: List[str] = []
    gates = scorecard.get("gate_outcomes") or {}
    dims = scorecard.get("dimension_scores") or {}

    missing = scorecard.get("missing_must_haves") or []
    if missing and gates.get("must_have_coverage_gate") is True:
        issues.append("must_have_coverage_gate=true contradicts non-empty missing_must_haves")

    unsupported = scorecard.get("unsupported_claims") or []
    if unsupported and gates.get("unsafe_claim_gate") is True:
        issues.append("unsafe_claim_gate=true contradicts non-empty unsupported_claims")

    persona = scorecard.get("persona_fit_notes") or []
    if persona and gates.get("persona_fit_gate") is True:
        issues.append("persona_fit_gate=true contradicts non-empty persona_fit_notes")

    # IC category title-inflation sniff (lightweight advisory; gate must also catch)
    if category_id.startswith(IC_CATEGORY_PREFIXES):
        cv_text = (scorecard.get("meta") or {}).get("_cv_text_sample", "")
        # No-op if we don't embed sample; the scorer itself should catch via unsupported_claims.
    return issues


def finalize_score_and_verdict(scorecard: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    notes: List[str] = []
    dims = scorecard.get("dimension_scores") or {}
    authoritative = compute_overall_score(dims)
    if abs(float(scorecard.get("overall_score") or 0) - authoritative) > 0.05:
        notes.append(
            f"overall_score overwritten {scorecard.get('overall_score')} -> {authoritative}"
        )
    scorecard["overall_score"] = authoritative

    base = base_verdict_from_score(authoritative)
    gates = scorecard.get("gate_outcomes") or {}
    final = base

    # Cap rules
    if any(not bool(gates.get(k)) for k in GATE_KEYS):
        if VERDICTS.index(base) < VERDICTS.index("NEEDS_WORK"):
            final = "NEEDS_WORK"
            notes.append("verdict capped to NEEDS_WORK (a gate failed)")
    if gates.get("unsafe_claim_gate") is False:
        final = "WEAK_MATCH"
        notes.append("verdict dropped to WEAK_MATCH (unsafe_claim_gate false)")

    if scorecard.get("verdict") != final:
        notes.append(f"verdict overwritten {scorecard.get('verdict')!r} -> {final!r}")
        scorecard["verdict"] = final
    return scorecard, notes


def dedupe_evidence_refs(scorecard: Dict[str, Any]) -> Dict[str, Any]:
    seen: List[str] = []
    qual = ["top_strengths", "top_failures", "unsupported_claims", "missing_must_haves", "persona_fit_notes"]
    for k in qual:
        for entry in scorecard.get(k) or []:
            for r in _extract_refs_from_entry(entry):
                if _is_clean_ref(r) and r not in seen:
                    seen.append(r)
    existing = scorecard.get("evidence_refs") or []
    for r in existing:
        if isinstance(r, str) and _is_clean_ref(r) and r not in seen:
            seen.append(r)
    scorecard["evidence_refs"] = seen
    return scorecard


# ---------- LLM calls ----------


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_scorer_claude(prompt: str, job_id: str) -> Dict[str, Any]:
    from src.common.unified_llm import invoke_unified_sync

    result = invoke_unified_sync(
        prompt=prompt,
        step_name="eval_cv_scoring",
        job_id=job_id,
        validate_json=True,
    )
    if not result.success:
        err = result.error or f"LLM failed for {job_id}"
        if "not logged in" in err.lower() or "/login" in err.lower():
            raise PermissionError("Claude CLI is not authenticated. Run `claude /login` and rerun.")
        raise RuntimeError(err)
    if not result.parsed_json:
        raise ValueError(f"LLM returned no parsed JSON for {job_id}")
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
def call_scorer_codex(
    prompt: str, job_id: str, model: str, timeout_seconds: int,
    verbose: bool, heartbeat_seconds: int,
) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="step9_codex_") as temp_dir:
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
        log_stage(f"    codex launch: job={job_id}, model={model}, timeout={timeout_seconds}s", verbose)
        start = time.monotonic()
        next_hb = heartbeat_seconds
        with open(stdout_path, "w") as so, open(stderr_path, "w") as se:
            p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=so, stderr=se, text=True, cwd=ROOT_DIR)
            assert p.stdin is not None
            p.stdin.write(prompt)
            p.stdin.close()
            while True:
                rc = p.poll()
                elapsed = int(time.monotonic() - start)
                if rc is not None:
                    break
                if elapsed >= timeout_seconds:
                    p.kill()
                    p.wait(timeout=5)
                    raise RuntimeError(f"Codex timed out after {timeout_seconds}s")
                if verbose and elapsed >= next_hb:
                    print(f"    heartbeat: elapsed={elapsed}s, pid={p.pid}")
                    next_hb += heartbeat_seconds
                time.sleep(1)
        stdout = stdout_path.read_text().strip() if stdout_path.exists() else ""
        stderr = stderr_path.read_text().strip() if stderr_path.exists() else ""
        if rc != 0:
            raise RuntimeError(stderr or stdout or f"codex exited with {rc}")
        if not output_path.exists():
            raise ValueError("codex produced no final message")
        raw = output_path.read_text().strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = parse_llm_json(raw)
            if not isinstance(parsed, dict):
                raise ValueError("codex final message was not JSON object")
        return {
            "provider": "codex",
            "parsed_json": parsed,
            "raw_output": raw,
            "meta": {"model": model, "timeout_seconds": timeout_seconds},
        }


# ---------- scoring pipeline per pair ----------


def score_pair(
    pair: Dict[str, Any],
    provider: str,
    model: str,
    timeout_seconds: int,
    max_attempts: int,
    verbose: bool,
    heartbeat_seconds: int,
) -> Dict[str, Any]:
    category_id = pair["category_id"]
    jd_path = Path(pair["jd_path"])
    cv_path = Path(pair["cv_path"])
    expected_job_id = str(pair["job_id"])
    jd_stem = jd_stem_from_path(jd_path)
    run_dir = build_debug_run_dir(category_id, jd_stem)
    log_stage(f"  debug: {run_dir}", verbose)

    # resolve raw job authoritatively
    raw_job = resolve_job_from_jd(category_id, jd_path)
    resolved_id = str(raw_job.get("_id"))
    if resolved_id != expected_job_id:
        raise ValueError(
            f"manifest job_id {expected_job_id} != jobs_all[{parse_jd_ordinal(jd_path)}]._id {resolved_id}"
        )

    jd_text = jd_path.read_text()
    cv_text = cv_path.read_text()

    header_issues = cross_check_job(jd_text, raw_job)
    if header_issues:
        raise ValueError(
            f"jd/jobs_all header mismatch for {jd_path}: {header_issues}"
        )

    rubric_path = RUBRIC_DIR / f"{category_id}_rubric.json"
    rubric = json.loads(rubric_path.read_text())
    template = json.loads((RUBRIC_DIR / "scorecard_template.json").read_text())
    overlay = prune_normalized_overlay(load_normalized_overlay(category_id, resolved_id))
    rubric_version = rubric.get("meta", {}).get("rubric_version", time.strftime("%Y-%m-%d"))
    scorer_model = "claude-opus-4-5-20251101" if provider == "claude" else model

    validation_feedback: List[str] = []
    for attempt in range(1, max_attempts + 1):
        log_stage(f"  attempt {attempt}/{max_attempts} started", always=True)
        prompt = build_scoring_prompt(
            category_id=category_id, job_id=resolved_id, rubric=rubric, template=template,
            jd_text=jd_text, cv_text=cv_text, jd_path=str(jd_path), cv_path=str(cv_path),
            overlay=overlay, raw_job_meta=raw_job,
            validation_feedback=validation_feedback or None,
        )
        if provider == "claude":
            resp = call_scorer_claude(prompt, resolved_id)
        elif provider == "codex":
            resp = call_scorer_codex(prompt, resolved_id, model, timeout_seconds, verbose, heartbeat_seconds)
        else:
            raise ValueError(f"unsupported provider: {provider}")
        scorecard = resp["parsed_json"]
        write_attempt_debug(run_dir, attempt, "initial", prompt, resp, scorecard)

        # structural validation first
        struct_issues = validate_structure(scorecard, category_id, resolved_id)
        if struct_issues:
            write_attempt_debug(run_dir, attempt, "rejected_structure", prompt, resp, scorecard, struct_issues)
            validation_feedback = struct_issues
            print(f"  attempt {attempt} rejected ({len(struct_issues)} structural issues):")
            for i in struct_issues[:8]:
                print(f"    - {i}")
            continue

        # lightweight repairs
        repaired, repair_notes = apply_lightweight_repairs(
            scorecard, category_id, resolved_id, rubric_version,
            rubric_path=f"data/eval/rubrics/{category_id}_rubric.json",
            blueprint_path=f"data/eval/blueprints/{category_id}_blueprint.json",
            baseline_path=f"data/eval/baselines/{category_id}_baseline.json",
            scorer_model=scorer_model,
            cv_path=str(cv_path), jd_path=str(jd_path),
        )

        # refs validation
        ref_issues = validate_refs(repaired)
        if ref_issues:
            write_attempt_debug(run_dir, attempt, "rejected_refs", prompt, resp, repaired, ref_issues, repair_notes)
            validation_feedback = ref_issues
            print(f"  attempt {attempt} rejected ({len(ref_issues)} ref issues):")
            for i in ref_issues[:8]:
                print(f"    - {i}")
            continue

        # cross-checks: emit as issues only on first attempt; attempt repair via feedback
        cross_issues = cross_check_gates(repaired, category_id)
        if cross_issues and attempt < max_attempts:
            write_attempt_debug(run_dir, attempt, "rejected_cross", prompt, resp, repaired, cross_issues, repair_notes)
            validation_feedback = cross_issues
            print(f"  attempt {attempt} rejected ({len(cross_issues)} cross-check issues):")
            for i in cross_issues[:8]:
                print(f"    - {i}")
            continue

        # finalize arithmetic + verdict
        repaired = dedupe_evidence_refs(repaired)
        repaired, verdict_notes = finalize_score_and_verdict(repaired)
        all_notes = list(repair_notes) + list(verdict_notes) + list(cross_issues)
        write_attempt_debug(run_dir, attempt, "accepted", prompt, resp, repaired, [], all_notes)
        return repaired

    raise ValueError(f"scorecard validation failed for {category_id}/{jd_stem} after {max_attempts} attempts")


# ---------- markdown render ----------


def render_scorecard_markdown(scorecard: Dict[str, Any], pair: Dict[str, Any]) -> str:
    meta = scorecard.get("meta") or {}
    lines: List[str] = []
    lines.append(f"# Scorecard — {scorecard.get('category_id')} / {Path(pair['jd_path']).stem}")
    lines.append("")
    lines.append("## Identity")
    lines.append(f"- Category: {scorecard.get('category_id')}")
    lines.append(f"- Job ID: {scorecard.get('job_id')}")
    lines.append(f"- JD path: {pair.get('jd_path')}")
    lines.append(f"- CV path: {pair.get('cv_path')}")
    lines.append(f"- CV source: {pair.get('cv_source','')}")
    lines.append(f"- Rubric version: {scorecard.get('rubric_version')}")
    lines.append(f"- Scorer model: {meta.get('scorer_model')}")
    lines.append(f"- Generated at: {meta.get('generated_at')}")
    lines.append("")
    lines.append(f"## Overall: **{scorecard.get('overall_score')}** — **{scorecard.get('verdict')}**")
    lines.append("")
    lines.append("## Dimension Scores")
    dims = scorecard.get("dimension_scores") or {}
    for k in DIMENSION_KEYS:
        lines.append(f"- {k} ({DIMENSION_WEIGHTS[k]}%): **{dims.get(k)}**")
    lines.append("")
    lines.append("## Gate Outcomes")
    gates = scorecard.get("gate_outcomes") or {}
    for k in GATE_KEYS:
        lines.append(f"- {k}: **{gates.get(k)}**")
    lines.append("")
    for label, key in [
        ("Top Strengths", "top_strengths"),
        ("Top Failures", "top_failures"),
        ("Unsupported Claims", "unsupported_claims"),
        ("Missing Must-Haves", "missing_must_haves"),
        ("Persona Fit Notes", "persona_fit_notes"),
        ("Representation Gap Hits", "representation_gap_hits"),
        ("Curation Gap Hits", "curation_gap_hits"),
    ]:
        lines.append(f"## {label}")
        arr = scorecard.get(key) or []
        if not arr:
            lines.append("- (none)")
        else:
            for item in arr:
                lines.append(f"- {item}")
        lines.append("")
    lines.append("## Evidence Refs")
    for r in scorecard.get("evidence_refs") or []:
        lines.append(f"- {r}")
    return "\n".join(lines).rstrip() + "\n"


# ---------- output writers ----------


def write_scorecard_files(pair: Dict[str, Any], scorecard: Dict[str, Any]) -> Path:
    cat = scorecard["category_id"]
    stem = Path(pair["jd_path"]).stem
    out_json = SCORECARD_DIR / cat / f"{stem}_scorecard.json"
    out_md = SCORECARD_DIR / cat / f"{stem}_scorecard.md"
    write_json_file(out_json, scorecard)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_scorecard_markdown(scorecard, pair))
    return out_json


def iter_scorecards() -> Iterable[Tuple[Path, Dict[str, Any]]]:
    for p in sorted(SCORECARD_DIR.rglob("*_scorecard.json")):
        # skip debug artifacts — only top-level {category}/{stem}_scorecard.json
        rel = p.relative_to(SCORECARD_DIR)
        if rel.parts[0] in ("debug", "batches"):
            continue
        try:
            yield p, json.loads(p.read_text())
        except Exception:
            continue


def render_index() -> None:
    rows: List[Dict[str, Any]] = []
    for path, sc in iter_scorecards():
        rows.append({
            "category": sc.get("category_id"),
            "job_id": sc.get("job_id"),
            "overall": sc.get("overall_score"),
            "verdict": sc.get("verdict"),
            "path": str(path.relative_to(SCORECARD_DIR)),
        })
    lines = ["# Scorecards Index", "", f"Total scorecards: {len(rows)}", "",
             "| Category | Job ID | Overall | Verdict | File |",
             "|----------|--------|---------|---------|------|"]
    for r in rows:
        lines.append(
            f"| {r['category']} | {r['job_id']} | {r['overall']} | {r['verdict']} | {r['path']} |"
        )
    (SCORECARD_DIR / "index.md").write_text("\n".join(lines).rstrip() + "\n")


def render_summary(batch_pairs: Optional[List[Dict[str, Any]]] = None) -> None:
    rows: List[Dict[str, Any]] = []
    failure_cluster: Counter = Counter()
    verdict_counts: Counter = Counter()
    gate_fails: Counter = Counter()
    for path, sc in iter_scorecards():
        verdict = sc.get("verdict")
        verdict_counts[verdict] += 1
        gates = sc.get("gate_outcomes") or {}
        failed_gates = [k for k in GATE_KEYS if gates.get(k) is False]
        for g in failed_gates:
            gate_fails[g] += 1
        failures = sc.get("top_failures") or []
        top_fail = failures[0] if failures else ""
        for f in failures[:3]:
            # crude clustering: first 6 words as bucket key
            bucket = " ".join(str(f).split()[:6]).lower()
            failure_cluster[bucket] += 1
        pair_info = {}
        if batch_pairs:
            for p in batch_pairs:
                if str(p.get("job_id")) == str(sc.get("job_id")) and p.get("category_id") == sc.get("category_id"):
                    pair_info = p
                    break
        rows.append({
            "category": sc.get("category_id"),
            "job_id": sc.get("job_id"),
            "jd_path": pair_info.get("jd_path") or (sc.get("meta") or {}).get("jd_path"),
            "cv_path": pair_info.get("cv_path") or (sc.get("meta") or {}).get("cv_path"),
            "cv_source": pair_info.get("cv_source", ""),
            "overall": sc.get("overall_score"),
            "verdict": verdict,
            "failed_gates": failed_gates,
            "top_failure": top_fail,
        })

    lines = ["# Step 9 Scoring Summary", "",
             f"Scored pairs: {len(rows)}",
             "",
             "## Verdict distribution"]
    for v in VERDICTS:
        lines.append(f"- {v}: {verdict_counts.get(v, 0)}")
    lines.append("")
    lines.append("## Gate failures")
    for g in GATE_KEYS:
        lines.append(f"- {g}: {gate_fails.get(g, 0)}")
    lines.append("")
    lines.append("## Pair detail")
    lines.append("| Category | Job ID | Overall | Verdict | Failed gates | Top failure | CV source |")
    lines.append("|----------|--------|---------|---------|--------------|-------------|-----------|")
    for r in rows:
        fg = ",".join(r["failed_gates"]) or "-"
        tf = (r["top_failure"] or "").replace("|", " ")
        lines.append(
            f"| {r['category']} | {r['job_id']} | {r['overall']} | {r['verdict']} | {fg} | {tf[:120]} | {r['cv_source']} |"
        )
    lines.append("")

    # Recommendation
    good_or_strong = verdict_counts.get("STRONG_MATCH", 0) + verdict_counts.get("GOOD_MATCH", 0)
    weak_or_needs = verdict_counts.get("NEEDS_WORK", 0) + verdict_counts.get("WEAK_MATCH", 0)
    lines.append("## Recommendation")
    if good_or_strong >= 3 and sum(gate_fails.values()) == 0:
        lines.append("- Scorer is operational and current outputs clear GOOD/STRONG for the anchor batch. Expand to: ai_architect_eea, staff_ai_engineer_global, ai_eng_manager_eea, senior_ai_engineer_eea.")
    elif weak_or_needs >= 2:
        top_cluster = failure_cluster.most_common(1)
        cluster_hint = top_cluster[0][0] if top_cluster else "(see top_failures)"
        lines.append(f"- {weak_or_needs} pairs scored NEEDS_WORK or WEAK_MATCH. Run Step 8b stage diagnostics targeting the dominant failure cluster: {cluster_hint!r}.")
    else:
        lines.append("- Mixed results. Add 1-2 more scored pairs for the weak anchors only before expanding the batch.")

    (SCORECARD_DIR / "summary.md").write_text("\n".join(lines).rstrip() + "\n")


# ---------- render-only mode ----------


def render_only() -> None:
    # re-render markdown from existing scorecard JSONs
    for path, sc in iter_scorecards():
        cat = sc.get("category_id")
        stem = path.stem.replace("_scorecard", "")
        pair = {
            "category_id": cat,
            "job_id": sc.get("job_id"),
            "jd_path": (sc.get("meta") or {}).get("jd_path", ""),
            "cv_path": (sc.get("meta") or {}).get("cv_path", ""),
            "cv_source": "",
        }
        (path.parent / f"{stem}_scorecard.md").write_text(render_scorecard_markdown(sc, pair))
    render_index()
    render_summary()


# ---------- batch loader ----------


def load_batch(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text())
    pairs = data.get("pairs") or []
    if not isinstance(pairs, list) or not pairs:
        raise ValueError(f"batch file has no 'pairs' list: {path}")
    for p in pairs:
        for k in ("category_id", "job_id", "jd_path", "cv_path"):
            if not p.get(k):
                raise ValueError(f"pair missing '{k}': {p}")
    return pairs


# ---------- CLI ----------


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval Step 9: Score CVs against category rubrics")
    parser.add_argument("--batch", help="Path to batch JSON manifest")
    parser.add_argument("--category", action="append", help="Single-pair mode: category id")
    parser.add_argument("--job-id", help="Single-pair mode: MongoDB _id")
    parser.add_argument("--jd-path", help="Single-pair mode: JD markdown path")
    parser.add_argument("--cv-path", help="Single-pair mode: CV markdown path")
    parser.add_argument("--cv-source", default="existing_output", help="Provenance tag")
    parser.add_argument("--selection-notes", default="", help="Why this pair was chosen")
    parser.add_argument("--force", action="store_true", help="Regenerate existing scorecards")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--provider", choices=["claude", "codex"], default="claude")
    parser.add_argument("--model", default=DEFAULT_CODEX_MODEL)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--heartbeat-seconds", type=int, default=15)
    args = parser.parse_args()

    if args.render_only:
        render_only()
        print("Rendered scorecard markdown, index, summary from existing JSONs")
        return

    if args.batch:
        pairs = load_batch(Path(args.batch))
    else:
        if not (args.category and args.job_id and args.jd_path and args.cv_path):
            parser.error("single-pair mode requires --category, --job-id, --jd-path, --cv-path")
        pairs = [{
            "category_id": args.category[0],
            "job_id": args.job_id,
            "jd_path": args.jd_path,
            "cv_path": args.cv_path,
            "cv_source": args.cv_source,
            "selection_notes": args.selection_notes,
        }]

    print(f"Step 9: scoring {len(pairs)} pair(s) (provider={args.provider})")
    print()
    generated = skipped = failed = 0
    for pair in pairs:
        cat = pair["category_id"]
        stem = Path(pair["jd_path"]).stem
        out_path = SCORECARD_DIR / cat / f"{stem}_scorecard.json"
        if out_path.exists() and not args.force:
            print(f"[{cat}/{stem}] skipped - scorecard exists (use --force)")
            skipped += 1
            continue
        print(f"[{cat}/{stem}] scoring...")
        try:
            sc = score_pair(
                pair, provider=args.provider, model=args.model,
                timeout_seconds=args.timeout_seconds, max_attempts=args.max_attempts,
                verbose=args.verbose, heartbeat_seconds=args.heartbeat_seconds,
            )
            write_scorecard_files(pair, sc)
            print(f"[{cat}/{stem}] done - overall={sc['overall_score']}, verdict={sc['verdict']}")
            generated += 1
        except Exception as exc:
            if isinstance(exc, RetryError) and exc.last_attempt.failed:
                inner = exc.last_attempt.exception()
                if inner is not None:
                    exc = inner
            print(f"[{cat}/{stem}] FAILED - {exc}")
            failed += 1

    render_index()
    render_summary(batch_pairs=pairs if args.batch else None)
    print()
    print(f"Step 9 complete: {generated} generated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
