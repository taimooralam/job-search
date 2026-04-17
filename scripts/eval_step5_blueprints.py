#!/usr/bin/env python3
"""
Eval Step 5: Generate evidence-bound CV blueprints from category composites.

Reads:
  data/eval/composites/{category}.json
  data/eval/normalized/{category}/deep_analysis.json

Outputs:
  data/eval/blueprints/{category}_blueprint.json
  data/eval/blueprints/{category}_blueprint.md
  data/eval/blueprints/index.md

Usage:
  python scripts/eval_step5_blueprints.py
  python scripts/eval_step5_blueprints.py --category ai_architect_global
  python scripts/eval_step5_blueprints.py --force
  python scripts/eval_step5_blueprints.py --render-only
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
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.common.json_utils import parse_llm_json

EVAL_DIR = Path("data/eval")
COMP_DIR = EVAL_DIR / "composites"
NORM_DIR = EVAL_DIR / "normalized"
BLUEPRINT_DIR = EVAL_DIR / "blueprints"
BLUEPRINT_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR = BLUEPRINT_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

TOP_LEVEL_KEYS = [
    "meta",
    "category_signature",
    "headline_pattern",
    "tagline_profile_angle",
    "core_competency_themes",
    "key_achievement_archetypes",
    "role_weighting_guidance",
    "language_and_tone",
    "unsafe_or_weak_framing",
    "evidence_ledger",
]

PLACEHOLDER_LANGUAGE = {
    "best-in-class",
    "world-class",
    "visionary",
    "thought leader",
}

POSITIVE_RESEARCH_TERMS = {
    "research",
    "publication",
    "publications",
    "published",
    "phd",
    "doctorate",
    "doctoral",
}

UNCERTAINTY_TERMS = {
    "uncertain",
    "uncertainty",
    "sample",
    "sparse",
    "emerging signal",
    "do not overfit",
    "limited evidence",
}

MIN_LEDGER_BY_PRIORITY = {
    "primary_target": 10,
    "secondary_target": 8,
    "tertiary_target": 6,
}

DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_CODEX_TIMEOUT_SECONDS = 420
PLACEHOLDER_REPLACEMENTS = {
    "best-in-class": "strong",
    "world-class": "strong",
    "visionary": "strategic",
    "thought leader": "experienced practitioner",
}
RESEARCH_TERM_REPLACEMENTS = {
    "research": "advanced experimentation",
    "publication": "formal external credential",
    "publications": "formal external credentials",
    "published": "externally documented",
    "phd": "advanced academic",
    "doctorate": "advanced academic",
    "doctoral": "advanced academic",
}


def log_stage(message: str, verbose: bool = False, always: bool = False) -> None:
    """Print a stage update when verbose is enabled, or always if requested."""
    if verbose or always:
        print(message)


def build_debug_run_dir(category_id: str) -> Path:
    """Create a unique debug artifact directory for one generation run."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = DEBUG_DIR / category_id / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_json_file(path: Path, payload: Any) -> None:
    """Write JSON payload with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)


def write_attempt_debug(
    run_dir: Path,
    attempt: int,
    stage: str,
    prompt: str,
    response_payload: Optional[Dict[str, Any]] = None,
    parsed_blueprint: Optional[Dict[str, Any]] = None,
    issues: Optional[Sequence[str]] = None,
    notes: Optional[Sequence[str]] = None,
) -> None:
    """Persist prompt/response/debug artifacts for one attempt stage."""
    prefix = f"attempt_{attempt:02d}_{stage}"
    (run_dir / f"{prefix}_prompt.txt").write_text(prompt)

    if response_payload is not None:
        write_json_file(run_dir / f"{prefix}_response_meta.json", response_payload.get("meta", {}))
        raw_output = str(response_payload.get("raw_output", ""))
        (run_dir / f"{prefix}_raw_output.txt").write_text(raw_output)
        stdout = str(response_payload.get("stdout", ""))
        stderr = str(response_payload.get("stderr", ""))
        if stdout:
            (run_dir / f"{prefix}_stdout.log").write_text(stdout)
        if stderr:
            (run_dir / f"{prefix}_stderr.log").write_text(stderr)

    if parsed_blueprint is not None:
        write_json_file(run_dir / f"{prefix}_parsed_blueprint.json", parsed_blueprint)

    if issues is not None:
        write_json_file(run_dir / f"{prefix}_issues.json", list(issues))

    if notes is not None:
        write_json_file(run_dir / f"{prefix}_notes.json", list(notes))


def load_composite(category_id: str) -> Dict[str, Any]:
    """Load a composite JSON payload for one category."""
    path = COMP_DIR / f"{category_id}.json"
    with open(path) as f:
        return json.load(f)


def load_deep_analysis(category_id: str) -> List[Dict[str, Any]]:
    """Load deep analysis exemplars for one category."""
    path = NORM_DIR / category_id / "deep_analysis.json"
    if not path.exists():
        return []
    with open(path) as f:
        return [item for item in json.load(f) if not item.get("_extraction_failed")]


def list_categories() -> List[str]:
    """List category ids from the composites directory."""
    categories = []
    for path in sorted(COMP_DIR.glob("*.json")):
        if path.stem == "cross_category_matrix":
            continue
        categories.append(path.stem)
    return categories


def normalize_concept(value: str) -> str:
    """Normalize repeated concept spellings into one comparable label."""
    normalized = value.strip().lower()
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("/", " / ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    canonical_map = {
        "ci cd": "ci/cd",
        "ci / cd": "ci/cd",
        "ci/cd pipelines": "ci/cd",
        "stakeholder management": "stakeholder management",
        "stakeholder_management": "stakeholder management",
        "genai": "generative ai",
        "llm": "llms",
    }
    return canonical_map.get(normalized, normalized)


def merge_frequency_entries(
    entries: Sequence[Dict[str, Any]],
    label_key: str = "skill",
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """Merge duplicate frequency entries after concept normalization."""
    counts: Dict[str, int] = {}
    totals: Dict[str, int] = {}

    for entry in entries:
        raw_label = str(entry.get(label_key, "")).strip()
        if not raw_label:
            continue
        label = normalize_concept(raw_label)
        counts[label] = counts.get(label, 0) + int(entry.get("count", 0) or 0)
        totals[label] = max(totals.get(label, 0), int(entry.get("total", 0) or 0))

    merged = []
    for label, count in counts.items():
        total = totals.get(label, 0)
        pct = round(count / total * 100, 1) if total else 0.0
        merged.append({"label": label, "count": count, "total": total, "pct": pct})

    merged.sort(key=lambda item: (-item["count"], item["label"]))
    return merged[:limit]


def summarize_counter_mapping(mapping: Dict[str, Any], limit: int = 8) -> Dict[str, Any]:
    """Keep only the most common mapping entries in descending order."""
    items = sorted(
        ((str(key), int(value or 0)) for key, value in mapping.items()),
        key=lambda item: (-item[1], item[0]),
    )
    return dict(items[:limit])


def summarize_string_list(values: Iterable[str], limit: int = 12) -> List[Dict[str, Any]]:
    """Aggregate free-text lists into a compact count summary."""
    counter: Counter[str] = Counter()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        counter[normalize_concept(text)] += 1

    summary = []
    for label, count in counter.most_common(limit):
        summary.append({"label": label, "count": count})
    return summary


def infer_expected_title_families(category_id: str, macro_family: str) -> set[str]:
    """Infer which title families should dominate a healthy category."""
    if category_id.startswith("head_of_ai"):
        return {"head_of_ai", "director_ai", "vp_ai"}
    if category_id.startswith("ai_architect"):
        return {"ai_architect", "solutions_architect"}
    if category_id.startswith("staff_ai_engineer"):
        return {"staff_engineer", "principal_engineer", "senior_engineer"}
    if category_id.startswith("tech_lead_ai"):
        return {"tech_lead", "engineering_manager", "senior_engineer"}
    if category_id.startswith("ai_eng_manager"):
        return {"engineering_manager", "tech_lead"}
    if category_id.startswith("senior_ai_engineer"):
        return {"senior_engineer", "staff_engineer"}
    if macro_family == "ai_architect":
        return {"ai_architect", "solutions_architect"}
    if macro_family == "ai_leadership":
        return {"head_of_ai", "director_ai", "vp_ai", "engineering_manager"}
    return set()


def detect_low_sample_mode(composite: Dict[str, Any]) -> bool:
    """Return true when the category should be treated as sparse."""
    return composite.get("total_jobs", 0) < 12 or composite.get("confidence") != "high"


def detect_noisy_title_mode(composite: Dict[str, Any]) -> bool:
    """Detect categories whose literal titles are too noisy to trust directly."""
    families = composite.get("title_families", {})
    total_jobs = max(int(composite.get("total_jobs", 0) or 0), 1)
    expected = infer_expected_title_families(
        str(composite.get("category_id", "")),
        str(composite.get("macro_family", "")),
    )
    expected_hits = sum(int(families.get(family, 0) or 0) for family in expected)
    expected_share = expected_hits / total_jobs if total_jobs else 0.0
    other_share = int(families.get("other", 0) or 0) / total_jobs if total_jobs else 0.0
    return expected_share < 0.55 or other_share > 0.25


def management_signals_are_weak(composite: Dict[str, Any]) -> bool:
    """Determine if executive/people-lead framing would be overreach."""
    management = composite.get("management_leadership", {})
    role_scope = composite.get("role_scope_distribution", {})
    total_jobs = max(int(composite.get("total_jobs", 0) or 0), 1)

    explicit_management_pct = max(
        float(management.get(field, {}).get("pct", 0) or 0)
        for field in ["hiring", "performance_management", "org_building", "budget_pnl"]
    )
    managerial_scope_pct = (
        sum(int(role_scope.get(scope, 0) or 0) for scope in ["manager", "director", "executive"])
        / total_jobs
        * 100
    )
    return explicit_management_pct < 20 and managerial_scope_pct < 40


def build_composite_summary(composite: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact composite summary for the Step 5 prompt."""
    ai_stack = composite.get("ai_ml_stack", {})
    ai_signal_summary = {}
    for key in [
        "rag",
        "agents_orchestration",
        "fine_tuning",
        "evaluation_quality",
        "guardrails_governance",
        "prompt_engineering",
        "vector_search",
        "model_serving_routing",
    ]:
        signal = ai_stack.get(key, {})
        ai_signal_summary[key] = {
            "count": int(signal.get("count", 0) or 0),
            "total": int(signal.get("total", 0) or 0),
            "pct": float(signal.get("pct", 0) or 0),
        }

    return {
        "signal_strength": composite.get("signal_strength", {}),
        "title_signals": {
            "title_families": summarize_counter_mapping(composite.get("title_families", {}), limit=6),
            "top_title_variants": summarize_counter_mapping(composite.get("title_variants", {}), limit=8),
            "noisy_title_mode": detect_noisy_title_mode(composite),
        },
        "role_archetype_signals": {
            "seniority_distribution": summarize_counter_mapping(
                composite.get("seniority_distribution", {}),
                limit=8,
            ),
            "role_scope_distribution": summarize_counter_mapping(
                composite.get("role_scope_distribution", {}),
                limit=8,
            ),
            "management_signals_weak": management_signals_are_weak(composite),
        },
        "management_leadership": composite.get("management_leadership", {}),
        "architecture": composite.get("architecture", {}),
        "hard_skills_top": merge_frequency_entries(composite.get("hard_skills", []), label_key="skill", limit=15),
        "soft_skills_top": merge_frequency_entries(composite.get("soft_skills", []), label_key="skill", limit=10),
        "programming_languages": {
            "required": merge_frequency_entries(
                composite.get("programming_languages", {}).get("required", []),
                label_key="skill",
                limit=6,
            ),
            "preferred": merge_frequency_entries(
                composite.get("programming_languages", {}).get("preferred", []),
                label_key="skill",
                limit=6,
            ),
        },
        "ai_ml_stack": {
            "signals": ai_signal_summary,
            "frameworks": merge_frequency_entries(ai_stack.get("top_frameworks", []), label_key="skill", limit=10),
            "observability": merge_frequency_entries(ai_stack.get("top_observability", []), label_key="skill", limit=8),
        },
        "governance_compliance_top": merge_frequency_entries(
            composite.get("governance_compliance", []),
            label_key="skill",
            limit=8,
        ),
        "pain_points_top": composite.get("pain_points", [])[:8],
        "market_context": {
            "domain_industry": summarize_counter_mapping(composite.get("domain_industry", {}), limit=5),
            "company_stage": summarize_counter_mapping(composite.get("company_stage", {}), limit=5),
            "collaboration_model": summarize_counter_mapping(composite.get("collaboration_model", {}), limit=5),
        },
        "disqualifiers": composite.get("disqualifiers", {}),
    }


def build_deep_analysis_summary(deep_analysis: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a compact deep-analysis evidence summary for the Step 5 prompt."""
    unsafe_claims: List[str] = []
    valued_evidence_types: List[str] = []
    success_metrics: List[str] = []
    mapping_themes: List[str] = []
    native_languages: List[str] = []
    specific_domain_years: List[str] = []

    for item in deep_analysis:
        cv_translation = item.get("cv_translation", {})
        unsafe_claims.extend(cv_translation.get("unsafe_claims_for_candidate", []))
        valued_evidence_types.extend(cv_translation.get("most_valued_evidence_types", []))
        mapping_themes.extend(cv_translation.get("best_candidate_experience_mapping", []))
        success_metrics.extend(item.get("success_metrics", []))

        disqualifiers = item.get("disqualifiers", {})
        language = str(disqualifiers.get("requires_native_language", "")).strip()
        if language and language != "not_specified":
            native_languages.append(language)
        specific_years = str(disqualifiers.get("requires_specific_domain_years", "")).strip()
        if specific_years and specific_years != "not_specified":
            specific_domain_years.append(specific_years)

    return {
        "unsafe_claims_top": summarize_string_list(unsafe_claims, limit=12),
        "valued_evidence_types_top": summarize_string_list(valued_evidence_types, limit=10),
        "success_metrics_top": summarize_string_list(success_metrics, limit=10),
        "candidate_mapping_themes_top": summarize_string_list(mapping_themes, limit=8),
        "native_language_requirements": summarize_string_list(native_languages, limit=6),
        "specific_domain_years": summarize_string_list(specific_domain_years, limit=6),
    }


def build_prompt(
    category_id: str,
    composite: Dict[str, Any],
    composite_summary: Dict[str, Any],
    deep_analysis_summary: Dict[str, Any],
    validation_feedback: Optional[Sequence[str]] = None,
) -> str:
    """Build the strict JSON-first blueprint synthesis prompt."""
    feedback_block = ""
    if validation_feedback:
        feedback_lines = "\n".join(f"- {issue}" for issue in validation_feedback)
        feedback_block = (
            "\nPREVIOUS ATTEMPT FAILED VALIDATION\n"
            "Fix every issue below in the next JSON response.\n"
            f"{feedback_lines}\n"
        )

    return f"""
You are an evidence-bound CV blueprint synthesizer.

Your task is to convert market evidence for exactly one job category into a Top-Third CV Blueprint that a downstream CV generation pipeline can use safely.

You are not writing generic career advice.
You are not writing aspirational copy.
You are producing a category-specific, candidate-safe specification grounded only in the supplied evidence.

CATEGORY META
- category_id: {category_id}
- category_name: {composite["category_name"]}
- macro_family: {composite["macro_family"]}
- priority: {composite["priority"]}
- confidence: {composite["confidence"]}
- total_jobs: {composite["total_jobs"]}
- deep_analysis_count: {composite["deep_analysis_count"]}

IMPORTANT DATA QUALITY RULES
- If total_jobs < 12 or confidence != "high", treat the category as sparse. Use softer language such as "common in this sample", "emerging signal", or "do not overfit the CV around this alone".
- If title variants appear noisy or inconsistent with the category label, privilege title_families, seniority_distribution, role_scope_distribution, management_leadership, pain_points, and ai_ml_stack over literal title strings.
- Do not call a skill "must-have" unless pct >= 60.
- If no hard skill reaches 60%, explicitly say there is no single universal must-have technical keyword in this category.
- Do not imply people management, hiring, org-building, or executive ownership unless management_leadership evidence supports it.
- Do not recommend research, publication, or PhD framing unless disqualifier evidence supports it.
- Do not recommend region-, language-, or domain-specific claims unless repeated evidence supports them.
- Prefer normalized concepts over duplicate spellings. Example: merge CI/CD with CI_CD; merge stakeholder_management with stakeholder management.

EVIDENCE INPUT
COMPOSITE SUMMARY
{json.dumps(composite_summary, indent=2)}

DEEP ANALYSIS SUMMARY
{json.dumps(deep_analysis_summary, indent=2)}
{feedback_block}
YOUR JOB
Synthesize the evidence into one differentiated blueprint for this category.

Before writing the blueprint, reason internally through these checks:
1. What is the real role archetype here: executive leader, architect, hands-on senior IC, or player-coach?
2. Which signals are table stakes, which are differentiators, and which are too weak or too rare to drive the CV?
3. Which claims are safe only if explicitly evidenced on the candidate CV?
4. What makes this category meaningfully different from nearby categories in the same macro family?

OUTPUT RULES
- Return valid JSON only. No markdown fences. No explanatory preamble.
- Every substantive recommendation must cite evidence using count/total/pct where available.
- Keep recommendations specific to this category. Avoid generic advice that could fit any AI role.
- Make the blueprint usable for CV generation, not just human reading.
- Keep wording concise and operational.
- Prefer evidence-first language such as "show", "prove", "demonstrate", "quantify", "name explicitly".
- Allowed strength labels are: "table stakes", "common in this sample", "differentiator", and "optional".
- Do not use the phrases "must-have" or "must have" anywhere in the JSON for this category.
- Do not use the phrases "best-in-class", "world-class", "visionary", or "thought leader" anywhere unless directly evidenced, which is rare.
- If research_heavy evidence is near zero, keep research/publication/PhD terms inside risk warnings only, not positive recommendations.
- Keep positive sections applied and delivery-oriented. Do not use research/publication/PhD words outside unsafe/risk sections.
- For ATS guidance, specify keyword repetition strategy:
  strongest 4-6 keywords = 2-3 mentions across headline/profile/experience/skills if true;
  secondary 4-6 keywords = 1-2 mentions if true;
  niche keywords = once only and only if true.
- For competency themes, produce exactly 4 sections with 2-4 themes each.
- For achievement archetypes, produce 4-6 ranked archetypes.
- For primary_target categories, be richer and more specific.
- For low-sample categories, include uncertainty notes and avoid over-precision.

JSON SCHEMA
{{
  "meta": {{
    "category_id": "string",
    "category_name": "string",
    "macro_family": "string",
    "priority": "string",
    "confidence": "high|medium|low|exploratory",
    "total_jobs": "int",
    "deep_analysis_count": "int",
    "low_sample_mode": "bool",
    "noisy_title_mode": "bool",
    "uncertainty_note": "string"
  }},
  "category_signature": {{
    "one_sentence_summary": "string",
    "distinctive_signals": ["string", "string", "string"],
    "citations": ["string"]
  }},
  "headline_pattern": {{
    "recommended_structure": "string",
    "safe_title_families": ["string"],
    "safe_title_variants": ["string"],
    "avoid_title_variants": ["string"],
    "evidence_first_rules": ["string"],
    "citations": ["string"]
  }},
  "tagline_profile_angle": {{
    "positioning_angle": ["string", "string"],
    "foreground": ["string"],
    "avoid": ["string"],
    "safe_positioning": ["string"],
    "unsafe_positioning": ["string"],
    "citations": ["string"]
  }},
  "core_competency_themes": [
    {{
      "section_name": "string",
      "themes": [
        {{
          "theme": "string",
          "classification": "table_stakes|differentiator|optional",
          "why_it_matters": "string",
          "ats_guidance": "string",
          "citation": "string"
        }}
      ]
    }}
  ],
  "key_achievement_archetypes": [
    {{
      "rank": "int",
      "archetype": "string",
      "what_it_proves": "string",
      "pain_points_addressed": ["string"],
      "metrics_to_include": ["string"],
      "story_format_guidance": "STAR or ARIS guidance in 1-2 sentences",
      "citation": "string"
    }}
  ],
  "role_weighting_guidance": {{
    "highest_weight_roles": ["string"],
    "expand_in_work_history": ["string"],
    "compress_in_work_history": ["string"],
    "how_to_frame_non_ai_experience": ["string"],
    "citations": ["string"]
  }},
  "language_and_tone": {{
    "recommended_tone": "executive|architect|hands_on|player_coach",
    "formality": "high|medium|low",
    "preferred_vocabulary": ["string"],
    "avoid_vocabulary": ["string"],
    "citations": ["string"]
  }},
  "unsafe_or_weak_framing": {{
    "avoid_claims": ["string"],
    "buzzword_patterns": ["string"],
    "title_inflation_risks": ["string"],
    "research_framing_risks": ["string"],
    "domain_or_region_risks": ["string"],
    "citations": ["string"]
  }},
  "evidence_ledger": [
    {{
      "recommendation": "string",
      "support": ["string"],
      "confidence": "high|medium|low"
    }}
  ]
}}

QUALITY BAR
- If the category behaves like an architect category, the blueprint must emphasize architecture proof, system integration, productionization, and stakeholder translation.
- If the category behaves like a leadership category, the blueprint must emphasize org-building, delivery ownership, team shaping, and business-to-technical translation only when supported by evidence.
- If the category behaves like a senior IC category, the blueprint must stay hands-on and avoid inflated leadership language.
- Explicitly distinguish table stakes from differentiators.
- Explicitly separate safe claims from unsafe claims.
- Explicitly reflect the hiring pain points.
- The final blueprint should read noticeably differently from adjacent categories in the same macro family.
""".strip()


def build_repair_prompt(
    composite: Dict[str, Any],
    current_blueprint: Dict[str, Any],
    issues: Sequence[str],
) -> str:
    """Build a minimal-edit repair prompt for a previously generated blueprint."""
    return f"""
You are repairing a previously generated CV blueprint JSON.

Your job is to minimally edit the JSON so it passes validation while staying evidence-bound.

HARD RULES
- Return valid JSON only.
- Preserve the existing structure and keep valid content whenever possible.
- Never use the phrases "must-have" or "must have" unless a hard skill is >= 60%, which is not true here.
- In positive recommendation sections, do not use research/publication/PhD framing because research_heavy_pct is near zero for this category.
- Do not use filler phrases like "best-in-class", "world-class", "visionary", or "thought leader".
- Prefer minimal wording edits over full rewrites.

CATEGORY META
- category_id: {composite["category_id"]}
- category_name: {composite["category_name"]}
- total_jobs: {composite["total_jobs"]}
- confidence: {composite["confidence"]}
- research_heavy_pct: {composite.get("disqualifiers", {}).get("research_heavy_pct", 0)}

VALIDATION ISSUES TO FIX
{json.dumps(list(issues), indent=2)}

CURRENT BLUEPRINT JSON
{json.dumps(current_blueprint, indent=2)}
""".strip()


def _iter_string_values(value: Any, skip_dict_keys: Optional[set[str]] = None) -> Iterable[str]:
    """Yield every string value nested inside a blueprint object."""
    skip_dict_keys = skip_dict_keys or set()

    if isinstance(value, str):
        yield value
        return

    if isinstance(value, dict):
        for key, item in value.items():
            if key in skip_dict_keys:
                continue
            yield from _iter_string_values(item, skip_dict_keys=skip_dict_keys)
        return

    if isinstance(value, list):
        for item in value:
            yield from _iter_string_values(item, skip_dict_keys=skip_dict_keys)


def _text_block(value: Any, skip_dict_keys: Optional[set[str]] = None) -> str:
    """Flatten nested strings into one searchable block."""
    return "\n".join(_iter_string_values(value, skip_dict_keys=skip_dict_keys)).lower()


def section_has_citations(blueprint: Dict[str, Any]) -> List[str]:
    """Validate citation coverage across all substantive blueprint sections."""
    issues = []

    for section_name in [
        "category_signature",
        "headline_pattern",
        "tagline_profile_angle",
        "role_weighting_guidance",
        "language_and_tone",
        "unsafe_or_weak_framing",
    ]:
        citations = blueprint.get(section_name, {}).get("citations", [])
        if not isinstance(citations, list) or not [item for item in citations if str(item).strip()]:
            issues.append(f"{section_name} must include at least one citation")

    competency_sections = blueprint.get("core_competency_themes", [])
    if not competency_sections:
        issues.append("core_competency_themes must contain 4 sections")
    for idx, section in enumerate(competency_sections, start=1):
        themes = section.get("themes", [])
        if not themes:
            issues.append(f"core_competency_themes[{idx}] must contain themes")
            continue
        section_citations = [theme.get("citation", "") for theme in themes if str(theme.get("citation", "")).strip()]
        if not section_citations:
            issues.append(f"core_competency_themes[{idx}] must include at least one citation")

    archetypes = blueprint.get("key_achievement_archetypes", [])
    if not archetypes:
        issues.append("key_achievement_archetypes must contain 4-6 entries")
    for idx, archetype in enumerate(archetypes, start=1):
        if not str(archetype.get("citation", "")).strip():
            issues.append(f"key_achievement_archetypes[{idx}] must include a citation")

    ledger = blueprint.get("evidence_ledger", [])
    if not ledger:
        issues.append("evidence_ledger must contain supporting evidence")
    for idx, item in enumerate(ledger, start=1):
        support = item.get("support", [])
        if not isinstance(support, list) or not [entry for entry in support if str(entry).strip()]:
            issues.append(f"evidence_ledger[{idx}] must include support entries")

    return issues


def contains_placeholder_language(blueprint: Dict[str, Any]) -> bool:
    """Check whether banned filler language appears in positive sections."""
    positive_sections = {
        key: value
        for key, value in blueprint.items()
        if key != "unsafe_or_weak_framing"
    }
    text = _text_block(positive_sections, skip_dict_keys={"citations", "citation", "support"})
    return any(term in text for term in PLACEHOLDER_LANGUAGE)


def has_positive_research_framing(blueprint: Dict[str, Any]) -> bool:
    """Check whether research/publication/PhD claims appear in positive guidance."""
    positive_sections = {
        "category_signature": {
            "one_sentence_summary": blueprint.get("category_signature", {}).get("one_sentence_summary", ""),
            "distinctive_signals": blueprint.get("category_signature", {}).get("distinctive_signals", []),
        },
        "headline_pattern": {
            "recommended_structure": blueprint.get("headline_pattern", {}).get("recommended_structure", ""),
            "safe_title_families": blueprint.get("headline_pattern", {}).get("safe_title_families", []),
            "safe_title_variants": blueprint.get("headline_pattern", {}).get("safe_title_variants", []),
            "evidence_first_rules": blueprint.get("headline_pattern", {}).get("evidence_first_rules", []),
        },
        "tagline_profile_angle": {
            "positioning_angle": blueprint.get("tagline_profile_angle", {}).get("positioning_angle", []),
            "foreground": blueprint.get("tagline_profile_angle", {}).get("foreground", []),
            "safe_positioning": blueprint.get("tagline_profile_angle", {}).get("safe_positioning", []),
        },
        "core_competency_themes": blueprint.get("core_competency_themes", []),
        "key_achievement_archetypes": blueprint.get("key_achievement_archetypes", []),
        "role_weighting_guidance": {
            "highest_weight_roles": blueprint.get("role_weighting_guidance", {}).get("highest_weight_roles", []),
            "expand_in_work_history": blueprint.get("role_weighting_guidance", {}).get("expand_in_work_history", []),
            "compress_in_work_history": blueprint.get("role_weighting_guidance", {}).get("compress_in_work_history", []),
            "how_to_frame_non_ai_experience": blueprint.get("role_weighting_guidance", {}).get("how_to_frame_non_ai_experience", []),
        },
        "language_and_tone": {
            "recommended_tone": blueprint.get("language_and_tone", {}).get("recommended_tone", ""),
            "preferred_vocabulary": blueprint.get("language_and_tone", {}).get("preferred_vocabulary", []),
        },
    }
    text = _text_block(positive_sections, skip_dict_keys={"citations", "citation", "support"})
    return any(term in text for term in POSITIVE_RESEARCH_TERMS)


def replace_case_insensitive(text: str, replacements: Dict[str, str]) -> str:
    """Apply case-insensitive whole-string replacements."""
    updated = text
    for source, target in replacements.items():
        updated = re.sub(re.escape(source), target, updated, flags=re.IGNORECASE)
    return updated


def repair_nested_strings(
    value: Any,
    replacements: Dict[str, str],
    skip_dict_keys: Optional[set[str]] = None,
) -> Any:
    """Recursively rewrite nested strings, skipping selected dict keys."""
    skip_dict_keys = skip_dict_keys or set()

    if isinstance(value, str):
        return replace_case_insensitive(value, replacements)

    if isinstance(value, list):
        return [repair_nested_strings(item, replacements, skip_dict_keys=skip_dict_keys) for item in value]

    if isinstance(value, dict):
        repaired = {}
        for key, item in value.items():
            if key in skip_dict_keys:
                repaired[key] = item
            else:
                repaired[key] = repair_nested_strings(item, replacements, skip_dict_keys=skip_dict_keys)
        return repaired

    return value


def apply_lightweight_repairs(
    blueprint: Dict[str, Any],
    composite: Dict[str, Any],
) -> tuple[Dict[str, Any], List[str]]:
    """Apply cheap deterministic repairs before escalating to a repair prompt."""
    repaired = copy.deepcopy(blueprint)
    notes: List[str] = []
    skip_keys = {"citations", "citation", "support"}

    max_skill_pct = max((float(item.get("pct", 0) or 0) for item in composite.get("hard_skills", [])), default=0.0)
    if max_skill_pct < 60 and "must-have" in _text_block(repaired, skip_dict_keys=skip_keys):
        repaired = repair_nested_strings(repaired, {"must-have": "common signal in this sample", "must have": "common signal in this sample"}, skip_dict_keys=skip_keys)
        notes.append("replaced forbidden must-have phrasing with softer evidence-bound wording")

    if contains_placeholder_language(repaired):
        positive_sections = {
            key: repaired[key]
            for key in repaired.keys()
            if key != "unsafe_or_weak_framing"
        }
        positive_sections = repair_nested_strings(positive_sections, PLACEHOLDER_REPLACEMENTS, skip_dict_keys=skip_keys)
        for key, value in positive_sections.items():
            repaired[key] = value
        notes.append("replaced banned placeholder language in positive sections")

    research_heavy_pct = float(composite.get("disqualifiers", {}).get("research_heavy_pct", 0) or 0)
    if research_heavy_pct <= 5 and has_positive_research_framing(repaired):
        for key in [
            "category_signature",
            "headline_pattern",
            "tagline_profile_angle",
            "core_competency_themes",
            "key_achievement_archetypes",
            "role_weighting_guidance",
            "language_and_tone",
        ]:
            if key in repaired:
                repaired[key] = repair_nested_strings(repaired[key], RESEARCH_TERM_REPLACEMENTS, skip_dict_keys=skip_keys)
        notes.append("replaced research/publication/PhD terms in positive sections with safer alternatives")

    return repaired, notes


def validate_blueprint(blueprint: Dict[str, Any], composite: Dict[str, Any]) -> List[str]:
    """Validate one blueprint against the JSON contract and evidence gates."""
    issues = []
    skip_keys = {"citations", "citation", "support"}

    for key in TOP_LEVEL_KEYS:
        if key not in blueprint:
            issues.append(f"missing top-level section: {key}")

    if issues:
        return issues

    issues.extend(section_has_citations(blueprint))

    meta = blueprint.get("meta", {})
    if meta.get("category_id") != composite.get("category_id"):
        issues.append("meta.category_id must match the composite category_id")
    if meta.get("category_name") != composite.get("category_name"):
        issues.append("meta.category_name must match the composite category_name")
    if meta.get("low_sample_mode") != detect_low_sample_mode(composite):
        issues.append("meta.low_sample_mode must match the composite-derived sparse-category flag")
    if meta.get("noisy_title_mode") != detect_noisy_title_mode(composite):
        issues.append("meta.noisy_title_mode must match the composite-derived title-noise flag")

    category_signature = blueprint.get("category_signature", {})
    if len(category_signature.get("distinctive_signals", [])) < 3:
        issues.append("category_signature.distinctive_signals must contain 3 items")

    competency_sections = blueprint.get("core_competency_themes", [])
    if len(competency_sections) != 4:
        issues.append("core_competency_themes must contain exactly 4 sections")
    for idx, section in enumerate(competency_sections, start=1):
        themes = section.get("themes", [])
        if len(themes) < 2 or len(themes) > 4:
            issues.append(f"core_competency_themes[{idx}] must contain 2-4 themes")

    archetypes = blueprint.get("key_achievement_archetypes", [])
    if len(archetypes) < 4 or len(archetypes) > 6:
        issues.append("key_achievement_archetypes must contain 4-6 entries")

    min_ledger = MIN_LEDGER_BY_PRIORITY.get(str(composite.get("priority", "")), 6)
    if len(blueprint.get("evidence_ledger", [])) < min_ledger:
        issues.append(
            f"evidence_ledger must contain at least {min_ledger} entries for {composite.get('priority')}"
        )

    max_skill_pct = max((float(item.get("pct", 0) or 0) for item in composite.get("hard_skills", [])), default=0.0)
    if max_skill_pct < 60 and "must-have" in _text_block(blueprint, skip_dict_keys=skip_keys):
        issues.append('reject "must-have" language because no hard skill reaches 60%')

    tone = str(blueprint.get("language_and_tone", {}).get("recommended_tone", "")).strip().lower()
    if tone == "executive" and management_signals_are_weak(composite):
        issues.append("reject executive tone because management signals are weak")

    research_heavy_pct = float(composite.get("disqualifiers", {}).get("research_heavy_pct", 0) or 0)
    if research_heavy_pct <= 5 and has_positive_research_framing(blueprint):
        issues.append("reject research/publication/PhD framing because research_heavy_pct is near zero")

    noisy_title_mode = detect_noisy_title_mode(composite)
    headline_pattern = blueprint.get("headline_pattern", {})
    if noisy_title_mode:
        avoid_variants = headline_pattern.get("avoid_title_variants", [])
        evidence_rules = headline_pattern.get("evidence_first_rules", [])
        safe_variants = headline_pattern.get("safe_title_variants", [])
        if not avoid_variants:
            issues.append("reject title guidance because noisy-title categories must explicitly list avoid_title_variants")
        if len(safe_variants) > 4:
            issues.append("reject title guidance because noisy-title categories should keep safe_title_variants narrow")
        if not any(
            any(token in str(rule).lower() for token in ("family", "scope", "evidence", "literal"))
            for rule in evidence_rules
        ):
            issues.append("reject title guidance because noisy-title categories must anchor rules in title families or role scope")

    if contains_placeholder_language(blueprint):
        issues.append("reject placeholder language such as best-in-class/world-class/visionary/thought leader")

    if detect_low_sample_mode(composite):
        uncertainty_note = str(meta.get("uncertainty_note", "")).strip().lower()
        if not uncertainty_note:
            issues.append("low-sample categories must include meta.uncertainty_note")
        elif not any(term in uncertainty_note for term in UNCERTAINTY_TERMS):
            issues.append("meta.uncertainty_note must explicitly acknowledge uncertainty for low-sample categories")

    return issues


def build_blueprint_json_schema(composite: Dict[str, Any]) -> Dict[str, Any]:
    """Build a JSON schema matching the strict Step 5 contract."""
    min_ledger = MIN_LEDGER_BY_PRIORITY.get(str(composite.get("priority", "")), 6)
    confidence_values = ["high", "medium", "low", "exploratory"]

    non_empty_string = {"type": "string", "minLength": 1}
    non_empty_string_array = {"type": "array", "items": non_empty_string}

    return {
        "type": "object",
        "additionalProperties": False,
        "required": TOP_LEVEL_KEYS,
        "properties": {
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "category_id",
                    "category_name",
                    "macro_family",
                    "priority",
                    "confidence",
                    "total_jobs",
                    "deep_analysis_count",
                    "low_sample_mode",
                    "noisy_title_mode",
                    "uncertainty_note",
                ],
                "properties": {
                    "category_id": {"type": "string", "const": str(composite.get("category_id", ""))},
                    "category_name": {"type": "string", "const": str(composite.get("category_name", ""))},
                    "macro_family": {"type": "string", "const": str(composite.get("macro_family", ""))},
                    "priority": {"type": "string", "const": str(composite.get("priority", ""))},
                    "confidence": {"type": "string", "enum": confidence_values, "const": str(composite.get("confidence", ""))},
                    "total_jobs": {"type": "integer", "minimum": 0, "const": int(composite.get("total_jobs", 0) or 0)},
                    "deep_analysis_count": {
                        "type": "integer",
                        "minimum": 0,
                        "const": int(composite.get("deep_analysis_count", 0) or 0),
                    },
                    "low_sample_mode": {"type": "boolean"},
                    "noisy_title_mode": {"type": "boolean"},
                    "uncertainty_note": {"type": "string"},
                },
            },
            "category_signature": {
                "type": "object",
                "additionalProperties": False,
                "required": ["one_sentence_summary", "distinctive_signals", "citations"],
                "properties": {
                    "one_sentence_summary": non_empty_string,
                    "distinctive_signals": {"type": "array", "items": non_empty_string, "minItems": 3},
                    "citations": {"type": "array", "items": non_empty_string, "minItems": 1},
                },
            },
            "headline_pattern": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "recommended_structure",
                    "safe_title_families",
                    "safe_title_variants",
                    "avoid_title_variants",
                    "evidence_first_rules",
                    "citations",
                ],
                "properties": {
                    "recommended_structure": non_empty_string,
                    "safe_title_families": non_empty_string_array,
                    "safe_title_variants": non_empty_string_array,
                    "avoid_title_variants": non_empty_string_array,
                    "evidence_first_rules": {"type": "array", "items": non_empty_string, "minItems": 1},
                    "citations": {"type": "array", "items": non_empty_string, "minItems": 1},
                },
            },
            "tagline_profile_angle": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "positioning_angle",
                    "foreground",
                    "avoid",
                    "safe_positioning",
                    "unsafe_positioning",
                    "citations",
                ],
                "properties": {
                    "positioning_angle": {"type": "array", "items": non_empty_string, "minItems": 2},
                    "foreground": non_empty_string_array,
                    "avoid": non_empty_string_array,
                    "safe_positioning": non_empty_string_array,
                    "unsafe_positioning": non_empty_string_array,
                    "citations": {"type": "array", "items": non_empty_string, "minItems": 1},
                },
            },
            "core_competency_themes": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["section_name", "themes"],
                    "properties": {
                        "section_name": non_empty_string,
                        "themes": {
                            "type": "array",
                            "minItems": 2,
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "theme",
                                    "classification",
                                    "why_it_matters",
                                    "ats_guidance",
                                    "citation",
                                ],
                                "properties": {
                                    "theme": non_empty_string,
                                    "classification": {
                                        "type": "string",
                                        "enum": ["table_stakes", "differentiator", "optional"],
                                    },
                                    "why_it_matters": non_empty_string,
                                    "ats_guidance": non_empty_string,
                                    "citation": non_empty_string,
                                },
                            },
                        },
                    },
                },
            },
            "key_achievement_archetypes": {
                "type": "array",
                "minItems": 4,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "rank",
                        "archetype",
                        "what_it_proves",
                        "pain_points_addressed",
                        "metrics_to_include",
                        "story_format_guidance",
                        "citation",
                    ],
                    "properties": {
                        "rank": {"type": "integer", "minimum": 1},
                        "archetype": non_empty_string,
                        "what_it_proves": non_empty_string,
                        "pain_points_addressed": non_empty_string_array,
                        "metrics_to_include": non_empty_string_array,
                        "story_format_guidance": non_empty_string,
                        "citation": non_empty_string,
                    },
                },
            },
            "role_weighting_guidance": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "highest_weight_roles",
                    "expand_in_work_history",
                    "compress_in_work_history",
                    "how_to_frame_non_ai_experience",
                    "citations",
                ],
                "properties": {
                    "highest_weight_roles": non_empty_string_array,
                    "expand_in_work_history": non_empty_string_array,
                    "compress_in_work_history": non_empty_string_array,
                    "how_to_frame_non_ai_experience": non_empty_string_array,
                    "citations": {"type": "array", "items": non_empty_string, "minItems": 1},
                },
            },
            "language_and_tone": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "recommended_tone",
                    "formality",
                    "preferred_vocabulary",
                    "avoid_vocabulary",
                    "citations",
                ],
                "properties": {
                    "recommended_tone": {
                        "type": "string",
                        "enum": ["executive", "architect", "hands_on", "player_coach"],
                    },
                    "formality": {"type": "string", "enum": ["high", "medium", "low"]},
                    "preferred_vocabulary": non_empty_string_array,
                    "avoid_vocabulary": non_empty_string_array,
                    "citations": {"type": "array", "items": non_empty_string, "minItems": 1},
                },
            },
            "unsafe_or_weak_framing": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "avoid_claims",
                    "buzzword_patterns",
                    "title_inflation_risks",
                    "research_framing_risks",
                    "domain_or_region_risks",
                    "citations",
                ],
                "properties": {
                    "avoid_claims": non_empty_string_array,
                    "buzzword_patterns": non_empty_string_array,
                    "title_inflation_risks": non_empty_string_array,
                    "research_framing_risks": non_empty_string_array,
                    "domain_or_region_risks": non_empty_string_array,
                    "citations": {"type": "array", "items": non_empty_string, "minItems": 1},
                },
            },
            "evidence_ledger": {
                "type": "array",
                "minItems": min_ledger,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["recommendation", "support", "confidence"],
                    "properties": {
                        "recommendation": non_empty_string,
                        "support": {"type": "array", "items": non_empty_string, "minItems": 1},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                },
            },
        },
    }


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_blueprint_codex(
    prompt: str,
    composite: Dict[str, Any],
    model: str,
    timeout_seconds: int,
    verbose: bool = False,
    heartbeat_seconds: int = 15,
) -> Dict[str, Any]:
    """Call Codex CLI for one category blueprint and require JSON output."""
    schema = build_blueprint_json_schema(composite)
    category_id = str(composite.get("category_id", "unknown"))

    with tempfile.TemporaryDirectory(prefix="step5_codex_") as temp_dir:
        temp_path = Path(temp_dir)
        schema_path = temp_path / "schema.json"
        output_path = temp_path / "last_message.json"
        stdout_path = temp_path / "codex_stdout.log"
        stderr_path = temp_path / "codex_stderr.log"
        schema_path.write_text(json.dumps(schema, indent=2))

        command = [
            "codex",
            "exec",
            "-m",
            model,
            "--full-auto",
            "--ephemeral",
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ]

        log_stage(
            f"    codex launch: category={category_id}, model={model}, "
            f"timeout={timeout_seconds}s, temp_dir={temp_path}",
            verbose=verbose,
        )

        start_time = time.monotonic()
        next_heartbeat = heartbeat_seconds

        with open(stdout_path, "w") as stdout_file, open(stderr_path, "w") as stderr_file:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                cwd=ROOT_DIR,
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
                    raise RuntimeError(
                        f"Codex generation timed out after {timeout_seconds}s "
                        f"(temp_dir={temp_path})"
                    )

                if verbose and elapsed >= next_heartbeat:
                    output_exists = output_path.exists()
                    output_size = output_path.stat().st_size if output_exists else 0
                    stdout_size = stdout_path.stat().st_size if stdout_path.exists() else 0
                    stderr_size = stderr_path.stat().st_size if stderr_path.exists() else 0
                    print(
                        f"    heartbeat: elapsed={elapsed}s, pid={process.pid}, "
                        f"output_exists={output_exists}, output_size={output_size}, "
                        f"stdout_size={stdout_size}, stderr_size={stderr_size}"
                    )
                    next_heartbeat += heartbeat_seconds

                time.sleep(1)

        stdout = stdout_path.read_text().strip() if stdout_path.exists() else ""
        stderr = stderr_path.read_text().strip() if stderr_path.exists() else ""
        elapsed = int(time.monotonic() - start_time)
        log_stage(
            f"    codex exited: return_code={return_code}, elapsed={elapsed}s, "
            f"output_exists={output_path.exists()}",
            verbose=verbose,
        )

        if return_code != 0:
            error_text = stderr or stdout or f"Codex exited with code {return_code}"
            lowered = error_text.lower()
            if "login" in lowered or "auth" in lowered or "api key" in lowered:
                raise PermissionError(f"Codex CLI is not authenticated: {error_text}")
            raise RuntimeError(error_text)

        if not output_path.exists():
            raise ValueError("Codex did not write the final message file")

        raw_output = output_path.read_text().strip()
        if not raw_output:
            raise ValueError("Codex returned an empty final message")
        log_stage(
            f"    output received: bytes={len(raw_output.encode('utf-8'))}",
            verbose=verbose,
        )

        try:
            parsed = json.loads(raw_output)
            log_stage("    json parsed: stdlib json.loads", verbose=verbose)
            return {
                "provider": "codex",
                "parsed_json": parsed,
                "raw_output": raw_output,
                "stdout": stdout,
                "stderr": stderr,
                "meta": {
                    "model": model,
                    "timeout_seconds": timeout_seconds,
                    "temp_dir": str(temp_path),
                    "elapsed_seconds": elapsed,
                    "return_code": return_code,
                },
            }
        except json.JSONDecodeError:
            parsed = parse_llm_json(raw_output)
            if isinstance(parsed, dict):
                log_stage("    json parsed: repaired parser fallback", verbose=verbose)
                return {
                    "provider": "codex",
                    "parsed_json": parsed,
                    "raw_output": raw_output,
                    "stdout": stdout,
                    "stderr": stderr,
                    "meta": {
                        "model": model,
                        "timeout_seconds": timeout_seconds,
                        "temp_dir": str(temp_path),
                        "elapsed_seconds": elapsed,
                        "return_code": return_code,
                        "json_parser": "repair_fallback",
                    },
                }
            raise ValueError("Codex final message was not a JSON object")


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_blueprint_claude(prompt: str, category_id: str) -> Dict[str, Any]:
    """Call Claude for one category blueprint and require parsed JSON output."""
    from src.common.unified_llm import invoke_unified_sync

    result = invoke_unified_sync(
        prompt=prompt,
        step_name="eval_blueprint_generation",
        job_id=category_id,
        validate_json=True,
    )
    if not result.success:
        error = result.error or f"LLM failed for {category_id}"
        lowered = error.lower()
        if "not logged in" in lowered or "/login" in lowered:
            raise PermissionError("Claude CLI is not authenticated. Run `claude /login` and rerun Step 5.")
        raise RuntimeError(error)
    if not result.parsed_json:
        raise ValueError(f"LLM returned no parsed JSON for {category_id}")
    return {
        "provider": "claude",
        "parsed_json": result.parsed_json,
        "raw_output": result.content,
        "stdout": "",
        "stderr": "",
        "meta": {
            "model": result.model,
            "tier": result.tier,
            "duration_ms": result.duration_ms,
            "backend": result.backend,
        },
    }


def generate_blueprint(
    composite: Dict[str, Any],
    deep_analysis: Sequence[Dict[str, Any]],
    max_attempts: int,
    provider: str,
    model: str,
    timeout_seconds: int,
    verbose: bool = False,
    heartbeat_seconds: int = 15,
) -> Dict[str, Any]:
    """Generate a validated blueprint, retrying with structured feedback."""
    category_id = str(composite["category_id"])
    composite_summary = build_composite_summary(composite)
    deep_analysis_summary = build_deep_analysis_summary(deep_analysis)
    validation_feedback: List[str] = []
    run_dir = build_debug_run_dir(category_id)
    write_json_file(run_dir / "composite_summary.json", composite_summary)
    write_json_file(run_dir / "deep_analysis_summary.json", deep_analysis_summary)

    for attempt in range(1, max_attempts + 1):
        log_stage(f"  attempt {attempt}/{max_attempts} started", always=True)
        log_stage("    building prompt", verbose=verbose)
        prompt = build_prompt(
            category_id=category_id,
            composite=composite,
            composite_summary=composite_summary,
            deep_analysis_summary=deep_analysis_summary,
            validation_feedback=validation_feedback if validation_feedback else None,
        )
        log_stage(f"    prompt built: chars={len(prompt)}", verbose=verbose)
        if provider == "codex":
            response_payload = call_blueprint_codex(
                prompt=prompt,
                composite=composite,
                model=model,
                timeout_seconds=timeout_seconds,
                verbose=verbose,
                heartbeat_seconds=heartbeat_seconds,
            )
        elif provider == "claude":
            log_stage("    claude launch", verbose=verbose)
            response_payload = call_blueprint_claude(prompt, category_id)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        blueprint = response_payload["parsed_json"]
        write_attempt_debug(
            run_dir=run_dir,
            attempt=attempt,
            stage="initial",
            prompt=prompt,
            response_payload=response_payload,
            parsed_blueprint=blueprint,
        )
        log_stage("    validation started", verbose=verbose)
        issues = validate_blueprint(blueprint, composite)
        if not issues:
            log_stage("    validation passed", verbose=verbose)
            write_attempt_debug(
                run_dir=run_dir,
                attempt=attempt,
                stage="accepted",
                prompt=prompt,
                response_payload=response_payload,
                parsed_blueprint=blueprint,
                issues=[],
            )
            return blueprint

        repaired_blueprint, repair_notes = apply_lightweight_repairs(blueprint, composite)
        repaired_issues = validate_blueprint(repaired_blueprint, composite)
        if repair_notes:
            log_stage("    lightweight repairs applied", verbose=verbose)
            write_attempt_debug(
                run_dir=run_dir,
                attempt=attempt,
                stage="lightweight_repair",
                prompt=prompt,
                response_payload=response_payload,
                parsed_blueprint=repaired_blueprint,
                issues=repaired_issues,
                notes=repair_notes,
            )
        if not repaired_issues:
            log_stage("    lightweight repairs passed validation", verbose=verbose)
            return repaired_blueprint

        repair_prompt = build_repair_prompt(composite, repaired_blueprint, repaired_issues)
        log_stage("    repair prompt built", verbose=verbose)
        if provider == "codex":
            repair_response = call_blueprint_codex(
                prompt=repair_prompt,
                composite=composite,
                model=model,
                timeout_seconds=timeout_seconds,
                verbose=verbose,
                heartbeat_seconds=heartbeat_seconds,
            )
        elif provider == "claude":
            repair_response = call_blueprint_claude(repair_prompt, category_id)
        else:
            raise ValueError(f"Unsupported provider: {provider}")
        repaired_by_model = repair_response["parsed_json"]
        write_attempt_debug(
            run_dir=run_dir,
            attempt=attempt,
            stage="repair_prompt",
            prompt=repair_prompt,
            response_payload=repair_response,
            parsed_blueprint=repaired_by_model,
        )
        log_stage("    repair validation started", verbose=verbose)
        final_issues = validate_blueprint(repaired_by_model, composite)
        if not final_issues:
            log_stage("    repair validation passed", verbose=verbose)
            write_attempt_debug(
                run_dir=run_dir,
                attempt=attempt,
                stage="accepted_after_repair",
                prompt=repair_prompt,
                response_payload=repair_response,
                parsed_blueprint=repaired_by_model,
                issues=[],
            )
            return repaired_by_model

        validation_feedback = final_issues
        write_attempt_debug(
            run_dir=run_dir,
            attempt=attempt,
            stage="rejected",
            prompt=repair_prompt,
            response_payload=repair_response,
            parsed_blueprint=repaired_by_model,
            issues=final_issues,
        )
        print(f"  attempt {attempt}/{max_attempts} rejected:")
        for issue in final_issues:
            print(f"    - {issue}")

    raise ValueError(f"Blueprint validation failed for {category_id} after {max_attempts} attempts")


def render_blueprint_markdown(blueprint: Dict[str, Any]) -> str:
    """Render a deterministic Markdown view from a saved blueprint JSON."""
    meta = blueprint["meta"]
    signature = blueprint["category_signature"]
    headline = blueprint["headline_pattern"]
    tagline = blueprint["tagline_profile_angle"]
    weighting = blueprint["role_weighting_guidance"]
    tone = blueprint["language_and_tone"]
    risks = blueprint["unsafe_or_weak_framing"]

    lines = []
    lines.append(f"# {meta['category_name']} Blueprint")
    lines.append("")
    lines.append("## Meta")
    lines.append(f"- Category ID: {meta['category_id']}")
    lines.append(f"- Macro family: {meta['macro_family']}")
    lines.append(f"- Priority: {meta['priority']}")
    lines.append(f"- Confidence: {meta['confidence']}")
    lines.append(f"- Jobs analyzed: {meta['total_jobs']}")
    lines.append(f"- Deep exemplars: {meta['deep_analysis_count']}")
    lines.append(f"- Low-sample mode: {meta['low_sample_mode']}")
    lines.append(f"- Noisy-title mode: {meta['noisy_title_mode']}")
    if meta.get("uncertainty_note"):
        lines.append(f"- Uncertainty note: {meta['uncertainty_note']}")
    lines.append("")

    lines.append("## Category Signature")
    lines.append(signature["one_sentence_summary"])
    lines.append("")
    lines.append("Distinctive signals:")
    for item in signature.get("distinctive_signals", []):
        lines.append(f"- {item}")
    lines.append("Citations:")
    for citation in signature.get("citations", []):
        lines.append(f"- {citation}")
    lines.append("")

    lines.append("## Headline Pattern")
    lines.append(f"- Recommended structure: {headline['recommended_structure']}")
    lines.append(f"- Safe title families: {', '.join(headline.get('safe_title_families', []))}")
    lines.append(f"- Safe title variants: {', '.join(headline.get('safe_title_variants', []))}")
    lines.append(f"- Avoid title variants: {', '.join(headline.get('avoid_title_variants', []))}")
    lines.append("Evidence-first rules:")
    for rule in headline.get("evidence_first_rules", []):
        lines.append(f"- {rule}")
    lines.append("Citations:")
    for citation in headline.get("citations", []):
        lines.append(f"- {citation}")
    lines.append("")

    lines.append("## Tagline and Profile Angle")
    lines.append("Positioning angles:")
    for item in tagline.get("positioning_angle", []):
        lines.append(f"- {item}")
    lines.append("Foreground:")
    for item in tagline.get("foreground", []):
        lines.append(f"- {item}")
    lines.append("Avoid:")
    for item in tagline.get("avoid", []):
        lines.append(f"- {item}")
    lines.append("Safe positioning:")
    for item in tagline.get("safe_positioning", []):
        lines.append(f"- {item}")
    lines.append("Unsafe positioning:")
    for item in tagline.get("unsafe_positioning", []):
        lines.append(f"- {item}")
    lines.append("Citations:")
    for citation in tagline.get("citations", []):
        lines.append(f"- {citation}")
    lines.append("")

    lines.append("## Core Competency Themes")
    for section in blueprint.get("core_competency_themes", []):
        lines.append(f"### {section['section_name']}")
        for theme in section.get("themes", []):
            lines.append(
                f"- {theme['theme']} [{theme['classification']}] - {theme['why_it_matters']} "
                f"(ATS: {theme['ats_guidance']}; Citation: {theme['citation']})"
            )
        lines.append("")

    lines.append("## Key Achievement Archetypes")
    for archetype in blueprint.get("key_achievement_archetypes", []):
        lines.append(f"### {archetype['rank']}. {archetype['archetype']}")
        lines.append(f"- What it proves: {archetype['what_it_proves']}")
        lines.append(f"- Pain points addressed: {', '.join(archetype.get('pain_points_addressed', []))}")
        lines.append(f"- Metrics to include: {', '.join(archetype.get('metrics_to_include', []))}")
        lines.append(f"- Story format guidance: {archetype['story_format_guidance']}")
        lines.append(f"- Citation: {archetype['citation']}")
        lines.append("")

    lines.append("## Role Weighting Guidance")
    lines.append(f"- Highest-weight roles: {', '.join(weighting.get('highest_weight_roles', []))}")
    lines.append("Expand in work history:")
    for item in weighting.get("expand_in_work_history", []):
        lines.append(f"- {item}")
    lines.append("Compress in work history:")
    for item in weighting.get("compress_in_work_history", []):
        lines.append(f"- {item}")
    lines.append("How to frame non-AI experience:")
    for item in weighting.get("how_to_frame_non_ai_experience", []):
        lines.append(f"- {item}")
    lines.append("Citations:")
    for citation in weighting.get("citations", []):
        lines.append(f"- {citation}")
    lines.append("")

    lines.append("## Language and Tone")
    lines.append(f"- Recommended tone: {tone['recommended_tone']}")
    lines.append(f"- Formality: {tone['formality']}")
    lines.append(f"- Preferred vocabulary: {', '.join(tone.get('preferred_vocabulary', []))}")
    lines.append(f"- Avoid vocabulary: {', '.join(tone.get('avoid_vocabulary', []))}")
    lines.append("Citations:")
    for citation in tone.get("citations", []):
        lines.append(f"- {citation}")
    lines.append("")

    lines.append("## Unsafe or Weak Framing")
    for heading, key in [
        ("Avoid claims", "avoid_claims"),
        ("Buzzword patterns", "buzzword_patterns"),
        ("Title inflation risks", "title_inflation_risks"),
        ("Research framing risks", "research_framing_risks"),
        ("Domain or region risks", "domain_or_region_risks"),
    ]:
        lines.append(f"{heading}:")
        for item in risks.get(key, []):
            lines.append(f"- {item}")
    lines.append("Citations:")
    for citation in risks.get("citations", []):
        lines.append(f"- {citation}")
    lines.append("")

    lines.append("## Evidence Ledger")
    for item in blueprint.get("evidence_ledger", []):
        lines.append(f"- {item['recommendation']} [{item['confidence']}]")
        for support in item.get("support", []):
            lines.append(f"  - {support}")

    return "\n".join(lines).rstrip() + "\n"


def write_blueprint_files(category_id: str, blueprint: Dict[str, Any]) -> None:
    """Write JSON and Markdown artifacts for a validated blueprint."""
    json_path = BLUEPRINT_DIR / f"{category_id}_blueprint.json"
    md_path = BLUEPRINT_DIR / f"{category_id}_blueprint.md"

    with open(json_path, "w") as f:
        json.dump(blueprint, f, indent=2)
    with open(md_path, "w") as f:
        f.write(render_blueprint_markdown(blueprint))


def render_index() -> None:
    """Render a Markdown index from saved blueprint JSON files."""
    rows = []
    for path in sorted(BLUEPRINT_DIR.glob("*_blueprint.json")):
        with open(path) as f:
            blueprint = json.load(f)
        meta = blueprint.get("meta", {})
        category_signature = blueprint.get("category_signature", {})
        tone = blueprint.get("language_and_tone", {})
        rows.append(
            {
                "category_id": meta.get("category_id", path.stem.replace("_blueprint", "")),
                "category_name": meta.get("category_name", path.stem),
                "priority": meta.get("priority", ""),
                "confidence": meta.get("confidence", ""),
                "recommended_tone": tone.get("recommended_tone", ""),
                "low_sample_mode": meta.get("low_sample_mode", False),
                "ledger_count": len(blueprint.get("evidence_ledger", [])),
                "summary": category_signature.get("one_sentence_summary", ""),
            }
        )

    lines = []
    lines.append("# Blueprint Index")
    lines.append("")
    lines.append(f"Generated blueprints: {len(rows)}")
    lines.append("")
    lines.append("| Category | Priority | Confidence | Tone | Low Sample | Ledger |")
    lines.append("|----------|----------|------------|------|------------|--------|")
    for row in rows:
        lines.append(
            f"| {row['category_name']} | {row['priority']} | {row['confidence']} | "
            f"{row['recommended_tone']} | {row['low_sample_mode']} | {row['ledger_count']} |"
        )
    lines.append("")
    for row in rows:
        lines.append(f"## {row['category_name']}")
        lines.append(f"- Category ID: {row['category_id']}")
        lines.append(f"- Summary: {row['summary']}")
        lines.append(f"- JSON: {row['category_id']}_blueprint.json")
        lines.append(f"- Markdown: {row['category_id']}_blueprint.md")
        lines.append("")

    with open(BLUEPRINT_DIR / "index.md", "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def render_only() -> None:
    """Re-render Markdown artifacts from saved blueprint JSON files."""
    for path in sorted(BLUEPRINT_DIR.glob("*_blueprint.json")):
        with open(path) as f:
            blueprint = json.load(f)
        category_id = blueprint.get("meta", {}).get("category_id", path.stem.replace("_blueprint", ""))
        with open(BLUEPRINT_DIR / f"{category_id}_blueprint.md", "w") as f:
            f.write(render_blueprint_markdown(blueprint))
    render_index()


def main() -> None:
    """CLI entrypoint for Step 5 blueprint synthesis."""
    parser = argparse.ArgumentParser(description="Eval Step 5: Generate CV blueprints from composites")
    parser.add_argument("--category", action="append", help="Process a single category id; can be passed multiple times")
    parser.add_argument("--force", action="store_true", help="Regenerate existing blueprint JSON files")
    parser.add_argument("--render-only", action="store_true", help="Render Markdown/index from existing blueprint JSON files")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum validation-feedback attempts per category")
    parser.add_argument(
        "--provider",
        choices=["codex", "claude"],
        default="codex",
        help="LLM backend for blueprint generation",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_CODEX_MODEL,
        help="Model to use when --provider=codex",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_CODEX_TIMEOUT_SECONDS,
        help="Timeout per Codex generation attempt",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Emit heartbeat logs while waiting on Codex generation",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=15,
        help="Heartbeat interval in seconds when --verbose is enabled",
    )
    args = parser.parse_args()

    if args.render_only:
        render_only()
        print("Rendered Markdown and index from existing blueprint JSON files")
        return

    categories = args.category if args.category else list_categories()
    print(
        f"Step 5: Generating blueprints for {len(categories)} categories "
        f"(provider={args.provider}{', model=' + args.model if args.provider == 'codex' else ''})"
    )
    print()

    generated = 0
    skipped = 0
    failed = 0
    for category_id in categories:
        composite_path = COMP_DIR / f"{category_id}.json"
        output_path = BLUEPRINT_DIR / f"{category_id}_blueprint.json"
        if not composite_path.exists():
            print(f"[{category_id}] skipped - missing composite JSON")
            skipped += 1
            continue
        if output_path.exists() and not args.force:
            print(f"[{category_id}] skipped - blueprint exists (use --force to regenerate)")
            skipped += 1
            continue

        composite = load_composite(category_id)
        deep_analysis = load_deep_analysis(category_id)

        print(f"[{category_id}] generating...")
        try:
            blueprint = generate_blueprint(
                composite,
                deep_analysis,
                max_attempts=args.max_attempts,
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                verbose=args.verbose,
                heartbeat_seconds=args.heartbeat_seconds,
            )
            log_stage("  writing blueprint files", verbose=args.verbose)
            write_blueprint_files(category_id, blueprint)
            log_stage("  files written", verbose=args.verbose)
            print(
                f"[{category_id}] done - tone={blueprint['language_and_tone']['recommended_tone']}, "
                f"ledger={len(blueprint['evidence_ledger'])}"
            )
            generated += 1
        except Exception as exc:
            if isinstance(exc, RetryError) and exc.last_attempt.failed:
                inner_exc = exc.last_attempt.exception()
                if inner_exc is not None:
                    exc = inner_exc
            print(f"[{category_id}] failed - {exc}")
            failed += 1

    render_index()
    print()
    print(f"Step 5 complete: {generated} generated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
