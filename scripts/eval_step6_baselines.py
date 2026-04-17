#!/usr/bin/env python3
"""
Eval Step 6: Generate category baselines from Step 5 blueprints.

Reads:
  data/eval/blueprints/{category}_blueprint.json
  data/master-cv/*
  docs/current/*
  docs/archive/*

Outputs:
  data/eval/baselines/{category}_baseline.json
  data/eval/baselines/{category}_baseline.md
  data/eval/baselines/index.md
  data/eval/baselines/evidence_map.json

Usage:
  python scripts/eval_step6_baselines.py
  python scripts/eval_step6_baselines.py --category ai_architect_global
  python scripts/eval_step6_baselines.py --force
  python scripts/eval_step6_baselines.py --render-only
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

import yaml
from tenacity import RetryError, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.common.json_utils import parse_llm_json

EVAL_DIR = Path("data/eval")
BLUEPRINT_DIR = EVAL_DIR / "blueprints"
BASELINE_DIR = EVAL_DIR / "baselines"
BASELINE_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR = BASELINE_DIR / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

MASTER_CV_DIR = Path("data/master-cv")
ROLES_DIR = MASTER_CV_DIR / "roles"
PROJECTS_DIR = MASTER_CV_DIR / "projects"
ROLE_METADATA_PATH = MASTER_CV_DIR / "role_metadata.json"
ROLE_TAXONOMY_PATH = MASTER_CV_DIR / "role_skills_taxonomy.json"

UPSTREAM_ALLOWLIST = [
    ("docs/archive/knowledge-base.md", "claimable_evidence"),
    ("docs/current/achievement-review-index.md", "supporting_context"),
    ("docs/current/achievement-review-tracker.yaml", "supporting_context"),
    ("docs/current/cv-generation-guide.md", "guidance_only"),
    ("docs/current/prompt-optimization-plan.md", "guidance_only"),
]

CANONICAL_REPRESENTATION_CANDIDATES = [
    Path("master-cv.md"),
    Path("master_cv.md"),
    Path("data/master-cv/master-cv.md"),
    Path("data/master-cv/current-master-cv.md"),
]

TOP_LEVEL_KEYS = [
    "meta",
    "overall_assessment",
    "score_breakdown",
    "strongest_supported_signals",
    "gap_analysis",
    "safe_claims_now",
    "representation_diagnosis",
    "curation_priorities",
    "master_cv_upgrade_actions",
    "evidence_ledger",
]

ALLOWED_STATUS = {"supported_and_curated"}
ALLOWED_GAP_TYPES = {
    "supported_upstream_pending_curation",
    "curated_but_underrepresented",
    "unsupported_or_unsafe",
}
ALLOWED_CLASSIFICATIONS = {
    "supported_and_curated",
    "supported_upstream_pending_curation",
    "curated_but_underrepresented",
    "unsupported_or_unsafe",
}
ALLOWED_READINESS = {"STRONG", "GOOD", "STRETCH", "LOW"}
ALLOWED_SECTIONS = {"headline", "summary", "role_bullets", "projects", "skills", "metadata"}

PLACEHOLDER_LANGUAGE = {
    "best-in-class",
    "world-class",
    "visionary",
    "thought leader",
}
PLACEHOLDER_REPLACEMENTS = {
    "best-in-class": "strong",
    "world-class": "strong",
    "visionary": "strategic",
    "thought leader": "experienced",
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
STOPWORDS = {
    "and", "the", "with", "that", "this", "from", "into", "for", "are", "was", "were",
    "have", "has", "had", "only", "more", "than", "their", "them", "then", "when", "what",
    "where", "which", "while", "will", "would", "should", "could", "about", "across", "through",
    "within", "using", "used", "show", "shows", "showed", "prove", "proves", "demonstrate",
    "demonstrates", "quantify", "name", "explicitly", "category", "candidate", "evidence",
    "supported", "curated", "pending", "representation", "current", "likely", "safely", "role",
}

MIN_LEDGER_BY_PRIORITY = {
    "primary_target": 8,
    "secondary_target": 6,
    "tertiary_target": 4,
}

DEFAULT_CODEX_MODEL = "gpt-5.4"
DEFAULT_CODEX_TIMEOUT_SECONDS = 420


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
    parsed_baseline: Optional[Dict[str, Any]] = None,
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

    if parsed_baseline is not None:
        write_json_file(run_dir / f"{prefix}_parsed_baseline.json", parsed_baseline)

    if issues is not None:
        write_json_file(run_dir / f"{prefix}_issues.json", list(issues))

    if notes is not None:
        write_json_file(run_dir / f"{prefix}_notes.json", list(notes))


def normalize_text(value: str) -> str:
    """Normalize text for overlap scoring."""
    normalized = value.lower().replace("_", " ").replace("/", " ")
    normalized = re.sub(r"[^a-z0-9+.# -]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize(text: str) -> List[str]:
    """Tokenize normalized text for matching."""
    tokens = []
    for token in normalize_text(text).split():
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def build_ref(path: Path, line_no: int) -> str:
    """Build a stable file:line reference string."""
    return f"{path.as_posix()}:{line_no}"


def read_lines(path: Path) -> List[str]:
    """Read file lines with trailing newlines stripped."""
    return path.read_text().splitlines()


def find_line_ref(path: Path, needle: str, fallback_line: int = 1) -> str:
    """Return a file:line reference for the first matching line."""
    if not path.exists():
        return path.as_posix()
    for idx, line in enumerate(read_lines(path), start=1):
        if needle in line:
            return build_ref(path, idx)
    return build_ref(path, fallback_line)


def list_categories() -> List[str]:
    """List category ids from the blueprints directory."""
    categories = []
    for path in sorted(BLUEPRINT_DIR.glob("*_blueprint.json")):
        categories.append(path.stem.replace("_blueprint", ""))
    return categories


def load_blueprint(category_id: str) -> Dict[str, Any]:
    """Load a saved Step 5 blueprint JSON."""
    path = BLUEPRINT_DIR / f"{category_id}_blueprint.json"
    with open(path) as f:
        return json.load(f)


def maybe_load_json(path: Path) -> Any:
    """Load JSON content from disk."""
    with open(path) as f:
        return json.load(f)


def parse_role_markdown(path: Path) -> Dict[str, Any]:
    """Parse one role markdown file into structured evidence blocks."""
    lines = read_lines(path)
    data: Dict[str, Any] = {
        "file": path.as_posix(),
        "title": "",
        "company": "",
        "metadata": {},
        "achievements": [],
        "blocks": [],
    }
    if lines:
        heading = lines[0].strip()
        if heading.startswith("# "):
            data["company"] = heading[2:].strip()

    metadata_pattern = re.compile(r"^\*\*(.+?)\*\*:\s*(.+)$")
    achievement_heading_pattern = re.compile(r"^### Achievement\s+\d+:\s+(.+)$")
    bullet_variant_pattern = re.compile(r"^- \*\*(.+?)\*\*:\s*(.+)$")

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        metadata_match = metadata_pattern.match(line.strip())
        if metadata_match:
            key = metadata_match.group(1).strip()
            value = metadata_match.group(2).strip()
            data["metadata"][key] = {"value": value, "ref": build_ref(path, idx + 1)}
            if key == "Role":
                data["title"] = value
            idx += 1
            continue

        achievement_match = achievement_heading_pattern.match(line.strip())
        if achievement_match:
            title = achievement_match.group(1).strip()
            start_line = idx + 1
            idx += 1
            core_fact = ""
            core_ref = build_ref(path, start_line)
            variants: List[Dict[str, Any]] = []
            keywords: List[str] = []
            while idx < len(lines):
                inner = lines[idx]
                if achievement_heading_pattern.match(inner.strip()):
                    break
                if inner.strip().startswith("**Core Fact**:"):
                    core_fact = inner.split("**Core Fact**:", 1)[1].strip()
                    core_ref = build_ref(path, idx + 1)
                else:
                    variant_match = bullet_variant_pattern.match(inner.strip())
                    if variant_match:
                        variants.append(
                            {
                                "label": variant_match.group(1).strip(),
                                "text": variant_match.group(2).strip(),
                                "ref": build_ref(path, idx + 1),
                            }
                        )
                    elif inner.strip().startswith("**Keywords**:"):
                        keywords = [item.strip() for item in inner.split("**Keywords**:", 1)[1].split(",") if item.strip()]
                idx += 1

            achievement = {
                "title": title,
                "title_ref": build_ref(path, start_line),
                "core_fact": core_fact,
                "core_ref": core_ref,
                "variants": variants,
                "keywords": keywords,
            }
            data["achievements"].append(achievement)
            block_text = core_fact or " ".join(variant["text"] for variant in variants)
            data["blocks"].append(
                {
                    "kind": "role_achievement",
                    "label": f"{data['company']} — {title}",
                    "text": block_text,
                    "refs": [core_ref] if core_fact else [build_ref(path, start_line)],
                    "keywords": keywords,
                }
            )
            continue

        idx += 1

    return data


def parse_project_markdown(path: Path) -> Dict[str, Any]:
    """Parse one project markdown file into bullets and metadata."""
    lines = read_lines(path)
    data: Dict[str, Any] = {
        "file": path.as_posix(),
        "title": "",
        "metadata": {},
        "bullets": [],
        "blocks": [],
    }
    if lines and lines[0].startswith("# "):
        data["title"] = lines[0][2:].strip()

    metadata_pattern = re.compile(r"^([a-zA-Z_]+):\s*(.+)$")
    in_bullets = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "## Bullets":
            in_bullets = True
            continue
        if in_bullets and stripped.startswith("- "):
            bullet = stripped[2:].strip()
            ref = build_ref(path, idx + 1)
            data["bullets"].append({"text": bullet, "ref": ref})
            data["blocks"].append(
                {
                    "kind": "project_bullet",
                    "label": f"{data['title']} bullet",
                    "text": bullet,
                    "refs": [ref],
                    "keywords": [],
                }
            )
            continue
        if not in_bullets:
            metadata_match = metadata_pattern.match(stripped)
            if metadata_match:
                key = metadata_match.group(1).strip()
                value = metadata_match.group(2).strip()
                data["metadata"][key] = {"value": value, "ref": build_ref(path, idx + 1)}

    description = data["metadata"].get("description", {}).get("value", "")
    if description:
        data["blocks"].append(
            {
                "kind": "project_description",
                "label": f"{data['title']} description",
                "text": description,
                "refs": [data["metadata"]["description"]["ref"]],
                "keywords": [],
            }
        )
    return data


def parse_skill_json(path: Path) -> Dict[str, Any]:
    """Load one project skills JSON and attach references."""
    payload = maybe_load_json(path)
    lines = read_lines(path)
    refs: Dict[str, List[str]] = {}
    for key in payload.keys():
        refs[key] = []
        pattern = f'"{key}"'
        for idx, line in enumerate(lines):
            if pattern in line:
                refs[key].append(build_ref(path, idx + 1))
                break
    payload["_file"] = path.as_posix()
    payload["_refs"] = refs
    return payload


def load_curated_evidence() -> Dict[str, Any]:
    """Load curated candidate evidence from data/master-cv/*."""
    roles = [parse_role_markdown(path) for path in sorted(ROLES_DIR.glob("*.md"))]
    projects = [parse_project_markdown(path) for path in sorted(PROJECTS_DIR.glob("*.md"))]
    project_skills = [parse_skill_json(path) for path in sorted(PROJECTS_DIR.glob("*_skills.json"))]
    metadata = maybe_load_json(ROLE_METADATA_PATH)
    taxonomy = maybe_load_json(ROLE_TAXONOMY_PATH)
    return {
        "roles": roles,
        "projects": projects,
        "project_skills": project_skills,
        "role_metadata": metadata,
        "role_taxonomy": taxonomy,
    }


def parse_knowledge_base(path: Path) -> List[Dict[str, Any]]:
    """Parse STAR records from the knowledge base."""
    lines = read_lines(path)
    blocks: List[Dict[str, Any]] = []
    header_pattern = re.compile(r"^STAR RECORD #\d+")
    starts = [idx for idx, line in enumerate(lines) if header_pattern.match(line.strip())]
    starts.append(len(lines))
    for pos in range(len(starts) - 1):
        start = starts[pos]
        end = starts[pos + 1]
        chunk = lines[start:end]
        chunk_text = "\n".join(chunk).strip()
        if not chunk_text:
            continue
        title = f"STAR record {pos + 1}"
        company = ""
        role = ""
        for line in chunk:
            if line.startswith("COMPANY:"):
                company = line.split(":", 1)[1].strip()
            elif line.startswith("ROLE TITLE:"):
                role = line.split(":", 1)[1].strip()
        if company or role:
            title = f"{company} — {role}".strip(" —")
        blocks.append(
            {
                "source_type": "claimable_evidence",
                "label": title,
                "text": chunk_text,
                "ref": build_ref(path, start + 1),
                "file": path.as_posix(),
            }
        )
    return blocks


def parse_markdown_sections(path: Path, source_type: str) -> List[Dict[str, Any]]:
    """Parse markdown headings or significant lines into upstream blocks."""
    lines = read_lines(path)
    blocks: List[Dict[str, Any]] = []
    heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$")
    for idx, line in enumerate(lines):
        match = heading_pattern.match(line.strip())
        if match:
            title = match.group(2).strip()
            snippet_lines = [title]
            for inner_idx in range(idx + 1, min(idx + 8, len(lines))):
                if heading_pattern.match(lines[inner_idx].strip()):
                    break
                if lines[inner_idx].strip():
                    snippet_lines.append(lines[inner_idx].strip())
            blocks.append(
                {
                    "source_type": source_type,
                    "label": title,
                    "text": " ".join(snippet_lines),
                    "ref": build_ref(path, idx + 1),
                    "file": path.as_posix(),
                }
            )
        elif "`" in line and source_type == "supporting_context":
            blocks.append(
                {
                    "source_type": source_type,
                    "label": line.strip()[:120],
                    "text": line.strip(),
                    "ref": build_ref(path, idx + 1),
                    "file": path.as_posix(),
                }
            )
    return blocks[:120]


def parse_tracker_yaml(path: Path) -> List[Dict[str, Any]]:
    """Parse achievement tracker YAML into compact evidence items."""
    payload = yaml.safe_load(path.read_text()) or {}
    achievements = payload.get("achievements", [])
    blocks = []
    lines = read_lines(path)
    for item in achievements:
        achievement_id = str(item.get("id", ""))
        title = str(item.get("title", "")).strip()
        gaps = item.get("gaps", {}) or {}
        text = (
            f"{achievement_id} {title}. "
            f"Recommended variant: {gaps.get('recommended_variant', '')}. "
            f"Competency gap: {gaps.get('competency_gap', '')}. "
            f"Missing keywords: {', '.join(gaps.get('missing_keywords', [])[:8])}."
        ).strip()
        ref = path.as_posix()
        for idx, line in enumerate(lines):
            if achievement_id and achievement_id in line:
                ref = build_ref(path, idx + 1)
                break
        blocks.append(
            {
                "source_type": "supporting_context",
                "label": f"{achievement_id} — {title}".strip(" —"),
                "text": text,
                "ref": ref,
                "file": path.as_posix(),
            }
        )
    return blocks


def load_upstream_evidence_inventory() -> Dict[str, Any]:
    """Load a bounded inventory of upstream evidence sources."""
    inventory: List[Dict[str, Any]] = []
    files: List[Dict[str, Any]] = []
    for rel_path, source_type in UPSTREAM_ALLOWLIST:
        path = Path(rel_path)
        if not path.exists():
            continue
        files.append({"path": path.as_posix(), "source_type": source_type})
        if path.name == "knowledge-base.md":
            inventory.extend(parse_knowledge_base(path))
        elif path.suffix in {".yaml", ".yml"}:
            inventory.extend(parse_tracker_yaml(path))
        else:
            inventory.extend(parse_markdown_sections(path, source_type))
    return {"files": files, "blocks": inventory}


def select_canonical_representation_path() -> Optional[Path]:
    """Return the first known canonical master-CV artifact if it exists."""
    for path in CANONICAL_REPRESENTATION_CANDIDATES:
        if path.exists():
            return path
    return None


def build_proxy_representation(curated_evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Build a temporary representation proxy from curated files."""
    metadata = curated_evidence["role_metadata"].get("candidate", {})
    roles = curated_evidence["roles"]
    projects = curated_evidence["projects"]
    current_role = next((role for role in roles if str(role.get("metadata", {}).get("Is Current", {}).get("value", "")).lower() == "true"), roles[0] if roles else {})

    headline = metadata.get("title_base", "")
    headline_ref = find_line_ref(ROLE_METADATA_PATH, '"title_base"', 3)
    summary_ref = find_line_ref(ROLE_METADATA_PATH, '"summary"', 3)
    metadata_summary = str(metadata.get("summary", "")).strip()
    if metadata_summary:
        summary = metadata_summary
    else:
        summary_parts = [
            f"{metadata.get('title_base', '')} with {metadata.get('years_experience', '')} years of experience.",
            f"Current role: {current_role.get('title', '')} at {current_role.get('company', '')}.",
        ]
        if current_role.get("achievements"):
            summary_parts.append(current_role["achievements"][0].get("core_fact", ""))
        summary = " ".join(part for part in summary_parts if part).strip()

    role_bullets = []
    if current_role:
        for achievement in current_role.get("achievements", [])[:4]:
            text = achievement.get("core_fact") or (achievement.get("variants", [{}])[0].get("text", ""))
            if text:
                role_bullets.append({"text": text, "ref": achievement.get("core_ref", achievement.get("title_ref"))})

    project_bullets = []
    for project in projects:
        description = project.get("metadata", {}).get("description", {})
        if description:
            project_bullets.append({"text": description.get("value", ""), "ref": description.get("ref", project["file"])})
        for bullet in project.get("bullets", [])[:2]:
            project_bullets.append({"text": bullet["text"], "ref": bullet["ref"]})

    skills = []
    for skill_json in curated_evidence["project_skills"]:
        skills.extend(skill_json.get("verified_competencies", [])[:8])
        skills.extend(skill_json.get("verified_skills", [])[:8])
    skills = list(dict.fromkeys(skills))[:20]

    return {
        "mode": "proxy",
        "headline": {"text": headline, "refs": [headline_ref]},
        "summary": {"text": summary, "refs": [summary_ref]},
        "role_bullets": role_bullets,
        "projects": project_bullets,
        "skills": skills,
    }


def load_master_cv_representation(curated_evidence: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Load current representation artifact or derive a proxy."""
    canonical_path = select_canonical_representation_path()
    if source == "canonical":
        if not canonical_path:
            raise FileNotFoundError("No canonical master CV representation artifact found")
        lines = read_lines(canonical_path)
        return {
            "mode": "canonical",
            "canonical_path": canonical_path.as_posix(),
            "headline": {"text": lines[0] if lines else "", "refs": [build_ref(canonical_path, 1)]},
            "summary": {"text": "\n".join(lines[:30]), "refs": [build_ref(canonical_path, 1)]},
            "role_bullets": [],
            "projects": [],
            "skills": [],
        }
    if source == "auto" and canonical_path:
        return load_master_cv_representation(curated_evidence, "canonical")
    return build_proxy_representation(curated_evidence)


def keyword_overlap_score(text: str, keywords: Sequence[str]) -> int:
    """Compute a simple keyword overlap score."""
    token_set = set(tokenize(text))
    return sum(1 for keyword in keywords if keyword in token_set)


def extract_blueprint_keywords(blueprint: Dict[str, Any]) -> List[str]:
    """Extract a compact keyword set from the blueprint JSON."""
    texts: List[str] = []
    meta = blueprint.get("meta", {})
    signature = blueprint.get("category_signature", {})
    headline = blueprint.get("headline_pattern", {})
    tagline = blueprint.get("tagline_profile_angle", {})
    tone = blueprint.get("language_and_tone", {})

    texts.append(str(meta.get("category_name", "")))
    texts.extend(signature.get("distinctive_signals", []))
    texts.extend(headline.get("safe_title_families", []))
    texts.extend(headline.get("safe_title_variants", []))
    texts.extend(headline.get("evidence_first_rules", []))
    texts.extend(tagline.get("foreground", []))
    texts.extend(tagline.get("safe_positioning", []))
    texts.extend(tone.get("preferred_vocabulary", []))

    for section in blueprint.get("core_competency_themes", []):
        texts.append(str(section.get("section_name", "")))
        for theme in section.get("themes", []):
            texts.append(str(theme.get("theme", "")))
            texts.append(str(theme.get("why_it_matters", "")))
    for item in blueprint.get("key_achievement_archetypes", []):
        texts.append(str(item.get("archetype", "")))
        texts.append(str(item.get("what_it_proves", "")))
    for item in blueprint.get("evidence_ledger", []):
        texts.append(str(item.get("recommendation", "")))
        texts.extend(item.get("support", []))

    keyword_counter = Counter()
    for text in texts:
        keyword_counter.update(tokenize(text))
    return [token for token, _ in keyword_counter.most_common(80)]


def rank_blocks(blocks: Sequence[Dict[str, Any]], blueprint_keywords: Sequence[str], limit: int = 12) -> List[Dict[str, Any]]:
    """Rank evidence blocks by keyword overlap against blueprint signals."""
    ranked = []
    for block in blocks:
        text = f"{block.get('label', '')} {block.get('text', '')} {' '.join(block.get('keywords', []))}"
        score = keyword_overlap_score(text, blueprint_keywords)
        if score <= 0:
            continue
        ranked.append((score, block))
    ranked.sort(key=lambda item: (-item[0], item[1].get("label", "")))
    return [dict(item[1], score=item[0]) for item in ranked[:limit]]


def gather_curated_blocks(curated_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten curated evidence into comparable blocks."""
    blocks: List[Dict[str, Any]] = []
    for role in curated_evidence["roles"]:
        blocks.extend(role.get("blocks", []))
    for project in curated_evidence["projects"]:
        blocks.extend(project.get("blocks", []))
    return blocks


def collect_skill_entries(curated_evidence: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Aggregate verified, supporting, and do-not-claim skill entries with refs."""
    verified = []
    supporting = []
    do_not_claim = []
    for skill_json in curated_evidence["project_skills"]:
        file_path = Path(skill_json["_file"])
        refs = skill_json.get("_refs", {})
        for key in ("verified_skills", "verified_patterns", "verified_competencies"):
            for item in skill_json.get(key, []):
                verified.append({"label": item, "ref": refs.get(key, [file_path.as_posix()])[0], "source": file_path.as_posix()})
        for key in ("post_checklist_skills", "post_checklist_competencies"):
            for item in skill_json.get(key, []):
                supporting.append({"label": item, "ref": refs.get(key, [file_path.as_posix()])[0], "source": file_path.as_posix()})
        for item in skill_json.get("not_yet_built", []):
            do_not_claim.append({"label": item, "ref": refs.get("not_yet_built", [file_path.as_posix()])[0], "source": file_path.as_posix()})
    return {"verified": verified, "supporting": supporting, "do_not_claim": do_not_claim}


def extract_metric_snippets(blocks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract compact metric-bearing snippets from evidence blocks."""
    metric_pattern = re.compile(r"\b\d[\d,.%+xX→\- ]{0,20}\b")
    metrics = []
    for block in blocks:
        matches = metric_pattern.findall(block.get("text", ""))
        if not matches:
            continue
        metrics.append(
            {
                "label": block.get("label", ""),
                "metrics": list(dict.fromkeys(matches))[:6],
                "refs": block.get("refs", []),
            }
        )
    return metrics[:12]


def build_curated_evidence_summary(blueprint: Dict[str, Any], curated_evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact curated evidence summary for one category."""
    blueprint_keywords = extract_blueprint_keywords(blueprint)
    blocks = gather_curated_blocks(curated_evidence)
    ranked_blocks = rank_blocks(blocks, blueprint_keywords, limit=14)
    skills = collect_skill_entries(curated_evidence)

    leadership_blocks = [block for block in ranked_blocks if any(token in normalize_text(block["text"]) for token in ("mentor", "hiring", "team", "stakeholder", "lead", "manager"))][:8]
    architecture_blocks = [block for block in ranked_blocks if any(token in normalize_text(block["text"]) for token in ("architect", "platform", "microservices", "event driven", "system", "integration", "ddd", "governance"))][:8]
    reliability_blocks = [block for block in ranked_blocks if any(token in normalize_text(block["text"]) for token in ("incident", "observability", "alert", "compliance", "guardrail", "evaluation", "reliability", "zero downtime", "gdpr"))][:8]

    verified_ranked = sorted(
        (
            (keyword_overlap_score(item["label"], blueprint_keywords), item)
            for item in skills["verified"]
        ),
        key=lambda item: (-item[0], item[1]["label"].lower()),
    )
    supporting_ranked = sorted(
        (
            (keyword_overlap_score(item["label"], blueprint_keywords), item)
            for item in skills["supporting"]
        ),
        key=lambda item: (-item[0], item[1]["label"].lower()),
    )

    metadata = curated_evidence["role_metadata"].get("candidate", {})
    current_role = next((role for role in curated_evidence["roles"] if str(role.get("metadata", {}).get("Is Current", {}).get("value", "")).lower() == "true"), None)
    evidence_density_notes = {
        "role_count": len(curated_evidence["roles"]),
        "project_count": len(curated_evidence["projects"]),
        "current_role_present": bool(current_role),
        "verified_skill_count": len(skills["verified"]),
        "supporting_skill_count": len(skills["supporting"]),
        "do_not_claim_count": len(skills["do_not_claim"]),
        "candidate_anchor": {
            "title_base": metadata.get("title_base", ""),
            "years_experience": metadata.get("years_experience", ""),
        },
    }

    return {
        "role_evidence": ranked_blocks[:8],
        "project_evidence": [block for block in ranked_blocks if block["kind"].startswith("project")][:6],
        "verified_skills": [item[1] for item in verified_ranked[:18] if item[0] > 0] or [item[1] for item in verified_ranked[:12]],
        "supporting_skills": [item[1] for item in supporting_ranked[:12] if item[0] > 0] or [item[1] for item in supporting_ranked[:8]],
        "do_not_claim": skills["do_not_claim"][:12],
        "leadership_signals": leadership_blocks,
        "architecture_signals": architecture_blocks,
        "impact_metrics": extract_metric_snippets(ranked_blocks),
        "governance_reliability_signals": reliability_blocks,
        "evidence_density_notes": evidence_density_notes,
    }


def build_upstream_evidence_summary(blueprint: Dict[str, Any], upstream_inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact upstream evidence summary for one category."""
    blueprint_keywords = extract_blueprint_keywords(blueprint)
    blocks = upstream_inventory["blocks"]

    claimable = [block for block in blocks if block["source_type"] == "claimable_evidence"]
    supporting = [block for block in blocks if block["source_type"] == "supporting_context"]
    guidance = [block for block in blocks if block["source_type"] == "guidance_only"]

    ranked_claimable = rank_blocks(claimable, blueprint_keywords, limit=10)
    ranked_supporting = rank_blocks(supporting, blueprint_keywords, limit=10)
    ranked_guidance = rank_blocks(guidance, blueprint_keywords, limit=8)

    pending_curation_signals = []
    for block in ranked_claimable[:6] + ranked_supporting[:4]:
        pending_curation_signals.append(
            {
                "signal": block["label"],
                "why_relevant": f"Matches category signals with overlap score {block['score']}.",
                "source_refs": [block["ref"]],
                "confidence": "high" if block["source_type"] == "claimable_evidence" else "medium",
                "recommended_target_files": [
                    "data/master-cv/roles/01_seven_one_entertainment.md",
                    "data/master-cv/role_metadata.json",
                ],
            }
        )

    ambiguous_signals = []
    for block in ranked_supporting[:6]:
        ambiguous_signals.append(
            {
                "signal": block["label"],
                "note": "Useful for curation prioritization but not automatically claimable.",
                "source_refs": [block["ref"]],
            }
        )

    guidance_only_items = []
    for block in ranked_guidance[:5]:
        guidance_only_items.append(
            {
                "signal": block["label"],
                "note": "Guidance-only context; do not treat as direct claimable evidence.",
                "source_refs": [block["ref"]],
            }
        )

    upstream_risks = [
        "Do not promote planning or rubric language into the curated store unless it references actual candidate work.",
        "Treat achievement-review tracker items as prioritization hints, not verified claims by themselves.",
    ]

    return {
        "pending_curation_signals": pending_curation_signals,
        "ambiguous_signals": ambiguous_signals,
        "guidance_only_items": guidance_only_items,
        "upstream_risks": upstream_risks,
    }


def build_blueprint_summary(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact blueprint summary for Step 6 prompts."""
    meta = blueprint.get("meta", {})
    headline = blueprint.get("headline_pattern", {})
    tagline = blueprint.get("tagline_profile_angle", {})
    tone = blueprint.get("language_and_tone", {})
    role_weighting = blueprint.get("role_weighting_guidance", {})
    unsafe = blueprint.get("unsafe_or_weak_framing", {})

    competency_sections = []
    for section in blueprint.get("core_competency_themes", [])[:4]:
        competency_sections.append(
            {
                "section_name": section.get("section_name", ""),
                "themes": [
                    {
                        "theme": theme.get("theme", ""),
                        "classification": theme.get("classification", ""),
                        "why_it_matters": theme.get("why_it_matters", ""),
                        "citation": theme.get("citation", ""),
                    }
                    for theme in section.get("themes", [])[:4]
                ],
            }
        )

    achievement_archetypes = []
    for item in blueprint.get("key_achievement_archetypes", [])[:5]:
        achievement_archetypes.append(
            {
                "rank": item.get("rank"),
                "archetype": item.get("archetype", ""),
                "what_it_proves": item.get("what_it_proves", ""),
                "citation": item.get("citation", ""),
            }
        )

    evidence_ledger = []
    for item in blueprint.get("evidence_ledger", [])[:8]:
        evidence_ledger.append(
            {
                "recommendation": item.get("recommendation", ""),
                "confidence": item.get("confidence", ""),
                "support": item.get("support", [])[:3],
            }
        )

    return {
        "meta": {
            "category_id": meta.get("category_id", ""),
            "category_name": meta.get("category_name", ""),
            "macro_family": meta.get("macro_family", ""),
            "priority": meta.get("priority", ""),
            "confidence": meta.get("confidence", ""),
            "uncertainty_note": meta.get("uncertainty_note", ""),
        },
        "category_signature": blueprint.get("category_signature", {}),
        "headline_pattern": {
            "recommended_structure": headline.get("recommended_structure", ""),
            "safe_title_families": headline.get("safe_title_families", [])[:6],
            "safe_title_variants": headline.get("safe_title_variants", [])[:6],
            "avoid_title_variants": headline.get("avoid_title_variants", [])[:6],
            "evidence_first_rules": headline.get("evidence_first_rules", [])[:5],
            "citations": headline.get("citations", [])[:4],
        },
        "tagline_profile_angle": {
            "positioning_angle": tagline.get("positioning_angle", [])[:4],
            "foreground": tagline.get("foreground", [])[:6],
            "avoid": tagline.get("avoid", [])[:6],
            "safe_positioning": tagline.get("safe_positioning", [])[:6],
            "unsafe_positioning": tagline.get("unsafe_positioning", [])[:6],
            "citations": tagline.get("citations", [])[:4],
        },
        "core_competency_themes": competency_sections,
        "key_achievement_archetypes": achievement_archetypes,
        "role_weighting_guidance": {
            "highest_weight_roles": role_weighting.get("highest_weight_roles", [])[:6],
            "expand_in_work_history": role_weighting.get("expand_in_work_history", [])[:6],
            "compress_in_work_history": role_weighting.get("compress_in_work_history", [])[:6],
            "how_to_frame_non_ai_experience": role_weighting.get("how_to_frame_non_ai_experience", [])[:6],
            "citations": role_weighting.get("citations", [])[:4],
        },
        "language_and_tone": {
            "recommended_tone": tone.get("recommended_tone", ""),
            "formality": tone.get("formality", ""),
            "preferred_vocabulary": tone.get("preferred_vocabulary", [])[:10],
            "avoid_vocabulary": tone.get("avoid_vocabulary", [])[:10],
            "citations": tone.get("citations", [])[:4],
        },
        "unsafe_or_weak_framing": {
            "avoid_claims": unsafe.get("avoid_claims", [])[:10],
            "title_inflation_risks": unsafe.get("title_inflation_risks", [])[:8],
            "research_framing_risks": unsafe.get("research_framing_risks", [])[:8],
            "domain_or_region_risks": unsafe.get("domain_or_region_risks", [])[:8],
            "citations": unsafe.get("citations", [])[:6],
        },
        "evidence_ledger": evidence_ledger,
    }


def build_master_cv_representation_summary(
    blueprint: Dict[str, Any],
    curated_evidence: Dict[str, Any],
    representation: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a summary of how the current representation surfaces curated evidence."""
    blueprint_keywords = extract_blueprint_keywords(blueprint)
    role_text = " ".join(item["text"] for item in representation.get("role_bullets", []))
    project_text = " ".join(item["text"] for item in representation.get("projects", []))
    skills_text = " ".join(representation.get("skills", []))
    headline_text = representation.get("headline", {}).get("text", "")
    summary_text = representation.get("summary", {}).get("text", "")
    combined = " ".join([headline_text, summary_text, role_text, project_text, skills_text])
    combined_tokens = set(tokenize(combined))

    curated_blocks = rank_blocks(gather_curated_blocks(curated_evidence), blueprint_keywords, limit=20)
    underrepresented = []
    for block in curated_blocks:
        block_tokens = set(tokenize(block["text"]))
        if not block_tokens:
            continue
        overlap = len(block_tokens & combined_tokens)
        if overlap == 0:
            underrepresented.append(block["label"])

    overstated = []
    if representation.get("mode") == "proxy":
        overstated.append("Representation is proxy-derived; treat headline and summary fit as provisional until a canonical master CV artifact exists.")

    return {
        "representation_proxy_mode": representation.get("mode") != "canonical",
        "headline_current_state": {
            "text": headline_text,
            "refs": representation.get("headline", {}).get("refs", []),
        },
        "summary_current_state": {
            "text": summary_text,
            "refs": representation.get("summary", {}).get("refs", []),
        },
        "role_priority_current_state": representation.get("role_bullets", [])[:6],
        "project_priority_current_state": representation.get("projects", [])[:6],
        "skills_priority_current_state": representation.get("skills", [])[:18],
        "underrepresented_signals": underrepresented[:8],
        "overstated_risks": overstated,
    }


def build_evidence_reference_index(
    curated_evidence: Dict[str, Any],
    upstream_inventory: Dict[str, Any],
    representation: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a compact ref -> snippet lookup used by prompt/debugging."""
    index: Dict[str, Dict[str, Any]] = {}
    for role in curated_evidence["roles"]:
        for achievement in role.get("achievements", []):
            ref = achievement.get("core_ref", achievement.get("title_ref"))
            index[ref] = {
                "layer": "curated",
                "label": achievement["title"],
                "snippet": achievement.get("core_fact", "")[:240],
            }
    for project in curated_evidence["projects"]:
        for bullet in project.get("bullets", []):
            index[bullet["ref"]] = {
                "layer": "curated",
                "label": project["title"],
                "snippet": bullet["text"][:240],
            }
    for block in upstream_inventory["blocks"][:120]:
        index[block["ref"]] = {
            "layer": block["source_type"],
            "label": block["label"],
            "snippet": block["text"][:240],
        }
    headline = representation.get("headline", {})
    for ref in headline.get("refs", []):
        index[ref] = {"layer": "representation", "label": "headline", "snippet": headline.get("text", "")[:240]}
    summary = representation.get("summary", {})
    for ref in summary.get("refs", []):
        index[ref] = {"layer": "representation", "label": "summary", "snippet": summary.get("text", "")[:240]}
    return index


def build_baseline_prompt(
    category_id: str,
    blueprint_summary: Dict[str, Any],
    curated_summary: Dict[str, Any],
    upstream_summary: Dict[str, Any],
    representation_summary: Dict[str, Any],
    evidence_reference_index: Dict[str, Any],
    blueprint: Dict[str, Any],
) -> str:
    """Build the strict JSON-first Step 6 baseline prompt."""
    meta = blueprint_summary["meta"]
    strict_schema = build_baseline_json_schema(blueprint)
    return f"""
You are an evidence-bound CV baseline evaluator.

Your task is to evaluate exactly one target job category against:
1. the candidate's current curated evidence store,
2. vetted upstream evidence that may support additional claims but is not yet curated,
3. the current master-CV representation.

You are not writing a new CV.
You are not giving generic career advice.
You are producing a category-specific baseline that will guide evidence curation and master-CV improvement.

CATEGORY META
- category_id: {category_id}
- category_name: {meta["category_name"]}
- macro_family: {meta["macro_family"]}
- priority: {meta["priority"]}
- confidence: {meta["confidence"]}

BLUEPRINT INPUT
{json.dumps(blueprint_summary, indent=2)}

CANDIDATE CONTEXT
- candidate_name: Taimoor Alam
- anchor_identity: Engineering Leader / Software Architect
- current_role: Technical Lead at Seven.One Entertainment Group (ProSiebenSat.1), Munich
- years_experience: 11

EVIDENCE MODEL
Use this 3-layer hierarchy strictly:

1. CURATED EVIDENCE STORE
- normalized evidence already promoted into pipeline-friendly candidate files
- reusable for downstream CV generation if safely cited

2. UPSTREAM RAW EVIDENCE
- candidate-authored or vetted supporting material that may contain valid evidence not yet promoted into the curated store
- useful for identifying curation opportunities
- not automatically reusable by the pipeline until curated with provenance

3. REPRESENTATION LAYER
- the current master CV and related representation artifacts
- used to judge how well curated evidence is surfaced, prioritized, and framed

IMPORTANT TRUTH RULES
- Do not treat the current master CV as the source of truth.
- Do not treat the curated evidence store as complete.
- Missing from curated files does not automatically mean unsupported.
- Upstream evidence can justify a "pending curation" conclusion, but not a fully reusable downstream claim unless it is already curated.
- Every concrete claim must cite exact evidence references.
- If evidence is ambiguous, prefer the safer label.
- Do not infer hiring, org-building, deep ML research, fine-tuning, RLHF, publications, or executive ownership unless explicitly supported.
- Do not over-credit title labels when underlying scope evidence is mixed.

INPUTS

CURATED EVIDENCE SUMMARY
{json.dumps(curated_summary, indent=2)}

UPSTREAM EVIDENCE SUMMARY
{json.dumps(upstream_summary, indent=2)}

CURRENT MASTER CV REPRESENTATION SUMMARY
{json.dumps(representation_summary, indent=2)}

OPTIONAL RAW EVIDENCE REFS
{json.dumps(evidence_reference_index, indent=2)}

REQUIRED GAP TAXONOMY
Every important missing or weak signal must be classified into exactly one of these:

- supported_and_curated
- supported_upstream_pending_curation
- curated_but_underrepresented
- unsupported_or_unsafe

SCORING FRAMEWORK
Return a combined score from 0.0 to 10.0 using these weighted components:

- candidate_evidence_coverage_score: 30%
- evidence_curation_completeness_score: 15%
- master_cv_representation_quality_score: 25%
- ai_architecture_fit_score: 15%
- leadership_scope_fit_score: 10%
- impact_proof_strength_score: 5%

READINESS TIERS
- STRONG: >= 8.5
- GOOD: 7.0 to 8.49
- STRETCH: 5.5 to 6.99
- LOW: < 5.5

OUTPUT RULES
- Return valid JSON only.
- No markdown fences.
- No explanatory preamble.
- Every substantive section must contain citations.
- Be concrete, operational, and category-specific.
- Use exact file references when available.
- Prefer evidence-first wording:
  "supported by", "not yet curated from", "underrepresented in", "unsafe because", "promote into", "surface in"
- Do not give generic resume advice.
- Do not recommend fabricating evidence.
- Do not collapse curation gaps into unsupported gaps.
- Do not collapse representation gaps into evidence gaps.
- If the category confidence is low or the evidence is sparse, include uncertainty notes.

STRICT JSON SCHEMA (OUTPUT MUST CONFORM EXACTLY)
You MUST emit JSON that conforms to the following JSON Schema.
- Field names MUST match exactly (e.g., use `combined_fit_score`, NOT `combined_score`).
- Object types MUST be objects; array types MUST be arrays. Do NOT replace an object section with a list or vice versa.
- All keys listed as `required` MUST be present.
- Do NOT add extra top-level keys or extra keys where `additionalProperties: false`.
- Every `citations` array requires at least one string citation.
- `safe_claims_now` is an OBJECT with fields headline_safe, profile_safe, experience_safe, leadership_safe, unsafe_or_too_weak, citations — NOT a list.
- `representation_diagnosis` is an OBJECT with fields well_represented_now, underrepresented_now, overstated_risk_now, representation_priorities, citations — NOT a list.

EVIDENCE REFERENCE FORMAT (CRITICAL)
Every `evidence_refs[]` and every `support[]` entry MUST be a CLEAN PATH REFERENCE, not a narrative string.
- Correct: `"data/master-cv/roles/01_seven_one_entertainment.md:28"`
- Wrong: `"Commander-4 serves 2,000 users — data/master-cv/roles/01_seven_one_entertainment.md:28"`
- Curated refs MUST start with `data/master-cv/` (not `data/master-cv` appearing mid-string).
- Upstream refs MUST start with `docs/` (not `docs/` appearing mid-string).
- Narrative explanations belong in description fields like `why_it_matters`, `current_state`, `recommendation`, NOT in refs/support arrays.

CLASSIFICATION vs REF CONSISTENCY (CRITICAL)
- `supported_and_curated` → at least one ref in `support`/`evidence_refs` must start with `data/master-cv/`.
- `supported_upstream_pending_curation` → at least one ref must start with `docs/`.
- `curated_but_underrepresented` → at least one ref must start with `data/master-cv/`.
- Do NOT classify as `supported_upstream_pending_curation` if you only have curated refs. Reclassify instead.

SCHEMA:
{json.dumps(strict_schema, indent=2)}
"""


def non_empty_string_schema() -> Dict[str, Any]:
    """Return JSON schema for a required non-empty string."""
    return {"type": "string", "minLength": 1}


def build_baseline_json_schema(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    """Build a strict JSON schema for baseline generation."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": TOP_LEVEL_KEYS,
        "properties": {
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "required": ["category_id", "category_name", "macro_family", "priority", "confidence", "representation_proxy_mode"],
                "properties": {
                    "category_id": non_empty_string_schema(),
                    "category_name": non_empty_string_schema(),
                    "macro_family": non_empty_string_schema(),
                    "priority": non_empty_string_schema(),
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "representation_proxy_mode": {"type": "boolean"},
                },
            },
            "overall_assessment": {
                "type": "object",
                "additionalProperties": False,
                "required": ["combined_fit_score", "readiness_tier", "one_sentence_verdict", "uncertainty_note", "citations"],
                "properties": {
                    "combined_fit_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "readiness_tier": {"type": "string", "enum": sorted(ALLOWED_READINESS)},
                    "one_sentence_verdict": non_empty_string_schema(),
                    "uncertainty_note": {"type": "string"},
                    "citations": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                },
            },
            "score_breakdown": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "candidate_evidence_coverage_score",
                    "evidence_curation_completeness_score",
                    "master_cv_representation_quality_score",
                    "ai_architecture_fit_score",
                    "leadership_scope_fit_score",
                    "impact_proof_strength_score",
                    "weighted_score_explanation",
                    "citations",
                ],
                "properties": {
                    "candidate_evidence_coverage_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "evidence_curation_completeness_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "master_cv_representation_quality_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "ai_architecture_fit_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "leadership_scope_fit_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "impact_proof_strength_score": {"type": "number", "minimum": 0, "maximum": 10},
                    "weighted_score_explanation": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                    "citations": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                },
            },
            "strongest_supported_signals": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["signal", "why_it_matters_for_category", "status", "evidence_refs", "citation"],
                    "properties": {
                        "signal": non_empty_string_schema(),
                        "why_it_matters_for_category": non_empty_string_schema(),
                        "status": {"type": "string", "enum": sorted(ALLOWED_STATUS)},
                        "evidence_refs": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                        "citation": non_empty_string_schema(),
                    },
                },
            },
            "gap_analysis": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["signal", "gap_type", "why_it_matters", "current_state", "safe_interpretation", "recommended_action", "evidence_refs", "citation"],
                    "properties": {
                        "signal": non_empty_string_schema(),
                        "gap_type": {"type": "string", "enum": sorted(ALLOWED_GAP_TYPES)},
                        "why_it_matters": non_empty_string_schema(),
                        "current_state": non_empty_string_schema(),
                        "safe_interpretation": non_empty_string_schema(),
                        "recommended_action": non_empty_string_schema(),
                        "evidence_refs": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                        "citation": non_empty_string_schema(),
                    },
                },
            },
            "safe_claims_now": {
                "type": "object",
                "additionalProperties": False,
                "required": ["headline_safe", "profile_safe", "experience_safe", "leadership_safe", "unsafe_or_too_weak", "citations"],
                "properties": {
                    "headline_safe": {"type": "array", "items": non_empty_string_schema()},
                    "profile_safe": {"type": "array", "items": non_empty_string_schema()},
                    "experience_safe": {"type": "array", "items": non_empty_string_schema()},
                    "leadership_safe": {"type": "array", "items": non_empty_string_schema()},
                    "unsafe_or_too_weak": {"type": "array", "items": non_empty_string_schema()},
                    "citations": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                },
            },
            "representation_diagnosis": {
                "type": "object",
                "additionalProperties": False,
                "required": ["well_represented_now", "underrepresented_now", "overstated_risk_now", "representation_priorities", "citations"],
                "properties": {
                    "well_represented_now": {"type": "array", "items": non_empty_string_schema()},
                    "underrepresented_now": {"type": "array", "items": non_empty_string_schema()},
                    "overstated_risk_now": {"type": "array", "items": non_empty_string_schema()},
                    "representation_priorities": {"type": "array", "items": non_empty_string_schema()},
                    "citations": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                },
            },
            "curation_priorities": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["priority_rank", "action", "why_now", "target_files", "source_refs", "expected_category_impact", "citation"],
                    "properties": {
                        "priority_rank": {"type": "integer", "minimum": 1},
                        "action": non_empty_string_schema(),
                        "why_now": non_empty_string_schema(),
                        "target_files": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                        "source_refs": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                        "expected_category_impact": non_empty_string_schema(),
                        "citation": non_empty_string_schema(),
                    },
                },
            },
            "master_cv_upgrade_actions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["priority_rank", "action", "section", "why_now", "supported_by", "citation"],
                    "properties": {
                        "priority_rank": {"type": "integer", "minimum": 1},
                        "action": non_empty_string_schema(),
                        "section": {"type": "string", "enum": sorted(ALLOWED_SECTIONS)},
                        "why_now": non_empty_string_schema(),
                        "supported_by": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                        "citation": non_empty_string_schema(),
                    },
                },
            },
            "evidence_ledger": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["recommendation", "classification", "support", "confidence"],
                    "properties": {
                        "recommendation": non_empty_string_schema(),
                        "classification": {"type": "string", "enum": sorted(ALLOWED_CLASSIFICATIONS)},
                        "support": {"type": "array", "minItems": 1, "items": non_empty_string_schema()},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                },
            },
        },
    }


def _text_block(value: Any, skip_dict_keys: Optional[set[str]] = None) -> str:
    """Flatten nested JSON content into comparable text."""
    parts: List[str] = []
    skip_dict_keys = skip_dict_keys or set()
    if isinstance(value, dict):
        for key, inner in value.items():
            if key in skip_dict_keys:
                continue
            parts.append(_text_block(inner, skip_dict_keys))
    elif isinstance(value, list):
        for inner in value:
            parts.append(_text_block(inner, skip_dict_keys))
    elif isinstance(value, str):
        parts.append(value)
    return " ".join(part for part in parts if part)


def section_has_citations(baseline: Dict[str, Any]) -> List[str]:
    """Validate citation coverage across all substantive baseline sections."""
    issues = []
    dict_sections = [
        "overall_assessment",
        "score_breakdown",
        "safe_claims_now",
        "representation_diagnosis",
    ]
    for section_name in dict_sections:
        citations = baseline.get(section_name, {}).get("citations", [])
        if not citations:
            issues.append(f"{section_name} must include citations")

    for idx, item in enumerate(baseline.get("strongest_supported_signals", [])):
        if not item.get("citation"):
            issues.append(f"strongest_supported_signals[{idx}] must include citation")
    for idx, item in enumerate(baseline.get("gap_analysis", [])):
        if not item.get("citation"):
            issues.append(f"gap_analysis[{idx}] must include citation")
    for idx, item in enumerate(baseline.get("curation_priorities", [])):
        if not item.get("citation"):
            issues.append(f"curation_priorities[{idx}] must include citation")
    for idx, item in enumerate(baseline.get("master_cv_upgrade_actions", [])):
        if not item.get("citation"):
            issues.append(f"master_cv_upgrade_actions[{idx}] must include citation")
    return issues


def contains_placeholder_language(baseline: Dict[str, Any]) -> bool:
    """Check for banned filler language outside citation/support fields."""
    skip_keys = {"citations", "citation", "support", "evidence_refs", "source_refs", "supported_by"}
    text = _text_block(baseline, skip_dict_keys=skip_keys).lower()
    return any(term in text for term in PLACEHOLDER_LANGUAGE)


def has_positive_research_framing(baseline: Dict[str, Any]) -> bool:
    """Detect unsupported research/publication framing in positive sections."""
    positive_sections = {
        "overall_assessment": baseline.get("overall_assessment", {}),
        "strongest_supported_signals": baseline.get("strongest_supported_signals", []),
        "safe_claims_now": {
            "headline_safe": baseline.get("safe_claims_now", {}).get("headline_safe", []),
            "profile_safe": baseline.get("safe_claims_now", {}).get("profile_safe", []),
            "experience_safe": baseline.get("safe_claims_now", {}).get("experience_safe", []),
            "leadership_safe": baseline.get("safe_claims_now", {}).get("leadership_safe", []),
        },
        "representation_diagnosis": {
            "well_represented_now": baseline.get("representation_diagnosis", {}).get("well_represented_now", []),
            "representation_priorities": baseline.get("representation_diagnosis", {}).get("representation_priorities", []),
        },
    }
    text = _text_block(positive_sections, skip_dict_keys={"citations", "citation"}).lower()
    return any(term in text for term in POSITIVE_RESEARCH_TERMS)


def compute_weighted_score(score_breakdown: Dict[str, Any]) -> float:
    """Compute weighted combined score from component subscores."""
    return round(
        0.30 * float(score_breakdown.get("candidate_evidence_coverage_score", 0.0))
        + 0.15 * float(score_breakdown.get("evidence_curation_completeness_score", 0.0))
        + 0.25 * float(score_breakdown.get("master_cv_representation_quality_score", 0.0))
        + 0.15 * float(score_breakdown.get("ai_architecture_fit_score", 0.0))
        + 0.10 * float(score_breakdown.get("leadership_scope_fit_score", 0.0))
        + 0.05 * float(score_breakdown.get("impact_proof_strength_score", 0.0)),
        2,
    )


def ref_points_to_curated(ref: str) -> bool:
    """Check whether a ref belongs to the curated store."""
    return ref.startswith("data/master-cv/")


def ref_points_to_upstream(ref: str) -> bool:
    """Check whether a ref belongs to upstream docs."""
    return ref.startswith("docs/")


def validate_baseline(
    baseline: Dict[str, Any],
    blueprint: Dict[str, Any],
    curated_summary: Dict[str, Any],
    upstream_summary: Dict[str, Any],
) -> List[str]:
    """Validate one baseline against the JSON contract and evidence gates."""
    issues: List[str] = []
    for key in TOP_LEVEL_KEYS:
        if key not in baseline:
            issues.append(f"missing top-level section: {key}")

    if issues:
        return issues

    issues.extend(section_has_citations(baseline))

    meta = baseline.get("meta", {})
    blueprint_meta = blueprint.get("meta", {})
    if meta.get("category_id") != blueprint_meta.get("category_id"):
        issues.append("meta.category_id must match the source blueprint")
    if meta.get("category_name") != blueprint_meta.get("category_name"):
        issues.append("meta.category_name must match the source blueprint")
    if meta.get("macro_family") != blueprint_meta.get("macro_family"):
        issues.append("meta.macro_family must match the source blueprint")
    if meta.get("priority") != blueprint_meta.get("priority"):
        issues.append("meta.priority must match the source blueprint")
    if meta.get("confidence") != blueprint_meta.get("confidence"):
        issues.append("meta.confidence must match the source blueprint")
    if not isinstance(meta.get("representation_proxy_mode"), bool):
        issues.append("meta.representation_proxy_mode must be a boolean")

    overall = baseline.get("overall_assessment", {})
    if overall.get("readiness_tier") not in ALLOWED_READINESS:
        issues.append("overall_assessment.readiness_tier must be one of STRONG|GOOD|STRETCH|LOW")

    score_breakdown = baseline.get("score_breakdown", {})
    score_keys = [
        "candidate_evidence_coverage_score",
        "evidence_curation_completeness_score",
        "master_cv_representation_quality_score",
        "ai_architecture_fit_score",
        "leadership_scope_fit_score",
        "impact_proof_strength_score",
    ]
    for key in score_keys:
        try:
            score = float(score_breakdown.get(key))
        except (TypeError, ValueError):
            issues.append(f"{key} must be a numeric score")
            continue
        if score < 0 or score > 10:
            issues.append(f"{key} must be between 0.0 and 10.0")

    try:
        combined = float(overall.get("combined_fit_score"))
        expected = compute_weighted_score(score_breakdown)
        if abs(combined - expected) > 0.2:
            issues.append(f"combined_fit_score must match weighted components (expected ~{expected})")
    except (TypeError, ValueError):
        issues.append("overall_assessment.combined_fit_score must be numeric")

    for idx, item in enumerate(baseline.get("strongest_supported_signals", [])):
        if item.get("status") not in ALLOWED_STATUS:
            issues.append(f"strongest_supported_signals[{idx}] has invalid status")
        refs = item.get("evidence_refs", [])
        if not refs or not any(ref_points_to_curated(ref) for ref in refs):
            issues.append(f"strongest_supported_signals[{idx}] must cite curated evidence")

    for idx, item in enumerate(baseline.get("gap_analysis", [])):
        if item.get("gap_type") not in ALLOWED_GAP_TYPES:
            issues.append(f"gap_analysis[{idx}] has invalid gap_type")
        refs = item.get("evidence_refs", [])
        gap_type = item.get("gap_type")
        if gap_type == "supported_upstream_pending_curation" and not any(ref_points_to_upstream(ref) for ref in refs):
            issues.append(f"gap_analysis[{idx}] pending curation item must cite upstream refs")
        if gap_type == "curated_but_underrepresented" and not any(ref_points_to_curated(ref) for ref in refs):
            issues.append(f"gap_analysis[{idx}] underrepresented item must cite curated refs")

    for idx, item in enumerate(baseline.get("master_cv_upgrade_actions", [])):
        if item.get("section") not in ALLOWED_SECTIONS:
            issues.append(f"master_cv_upgrade_actions[{idx}] has invalid section")

    ledger = baseline.get("evidence_ledger", [])
    min_ledger = MIN_LEDGER_BY_PRIORITY.get(str(blueprint_meta.get("priority", "")), 4)
    if len(ledger) < min_ledger:
        issues.append(f"evidence_ledger must contain at least {min_ledger} entries for {blueprint_meta.get('priority')}")
    for idx, item in enumerate(ledger):
        classification = item.get("classification")
        if classification not in ALLOWED_CLASSIFICATIONS:
            issues.append(f"evidence_ledger[{idx}] has invalid classification")
            continue
        support = item.get("support", [])
        if not support:
            issues.append(f"evidence_ledger[{idx}] must include support entries")
        elif classification == "supported_and_curated" and not any(ref_points_to_curated(ref) for ref in support):
            issues.append(f"evidence_ledger[{idx}] supported_and_curated must cite curated refs")
        elif classification == "supported_upstream_pending_curation" and not any(ref_points_to_upstream(ref) for ref in support):
            issues.append(f"evidence_ledger[{idx}] pending_curation must cite upstream refs")
        elif classification == "curated_but_underrepresented" and not any(ref_points_to_curated(ref) for ref in support):
            issues.append(f"evidence_ledger[{idx}] curated_but_underrepresented must cite curated refs")

    if contains_placeholder_language(baseline):
        issues.append("reject placeholder language such as best-in-class/world-class/visionary/thought leader")

    research_heavy_pct = 0.0
    for citation in blueprint.get("unsafe_or_weak_framing", {}).get("citations", []):
        if "research_heavy" in citation:
            match = re.search(r"research_heavy\s+(\d+(?:\.\d+)?)", citation)
            if match:
                research_heavy_pct = float(match.group(1))
                break
    if research_heavy_pct <= 5 and has_positive_research_framing(baseline):
        issues.append("reject research/publication/PhD framing because research_heavy_pct is near zero")

    unsafe_items = baseline.get("safe_claims_now", {}).get("unsafe_or_too_weak", [])
    if blueprint_meta.get("priority") == "primary_target" and not unsafe_items:
        issues.append("safe_claims_now.unsafe_or_too_weak must not be empty for primary categories")

    if meta.get("representation_proxy_mode") and "proxy" not in overall.get("uncertainty_note", "").lower():
        issues.append("overall_assessment.uncertainty_note must mention proxy mode when representation_proxy_mode is true")

    return issues


def replace_terms_in_value(value: Any, replacements: Dict[str, str]) -> Any:
    """Apply string replacements recursively."""
    if isinstance(value, dict):
        return {key: replace_terms_in_value(inner, replacements) for key, inner in value.items()}
    if isinstance(value, list):
        return [replace_terms_in_value(inner, replacements) for inner in value]
    if isinstance(value, str):
        updated = value
        for source, target in replacements.items():
            updated = re.sub(source, target, updated, flags=re.IGNORECASE)
        return updated
    return value


def derive_readiness_tier(combined_score: float) -> str:
    """Derive readiness tier from numeric score."""
    if combined_score >= 8.5:
        return "STRONG"
    if combined_score >= 7.0:
        return "GOOD"
    if combined_score >= 5.5:
        return "STRETCH"
    return "LOW"


def apply_lightweight_baseline_repairs(
    baseline: Dict[str, Any],
    blueprint: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Apply deterministic low-risk repairs before retrying the model."""
    repaired = copy.deepcopy(baseline)
    notes: List[str] = []

    if not isinstance(repaired.get("meta", {}).get("representation_proxy_mode"), bool):
        repaired.setdefault("meta", {})["representation_proxy_mode"] = True
        notes.append("added meta.representation_proxy_mode=true")

    repaired = replace_terms_in_value(repaired, PLACEHOLDER_REPLACEMENTS)

    readiness = str(repaired.get("overall_assessment", {}).get("readiness_tier", "")).upper()
    if readiness in ALLOWED_READINESS:
        repaired["overall_assessment"]["readiness_tier"] = readiness
        notes.append("normalized readiness tier casing")

    if "score_breakdown" in repaired and "overall_assessment" in repaired:
        expected = compute_weighted_score(repaired["score_breakdown"])
        repaired["overall_assessment"]["combined_fit_score"] = expected
        repaired["overall_assessment"]["readiness_tier"] = derive_readiness_tier(expected)
        notes.append("recomputed combined_fit_score from component weights")

    if repaired.get("meta", {}).get("representation_proxy_mode"):
        note = repaired.setdefault("overall_assessment", {}).get("uncertainty_note", "")
        if "proxy" not in note.lower():
            prefix = "Representation assessment is currently in proxy mode because no canonical master CV artifact was found."
            repaired["overall_assessment"]["uncertainty_note"] = f"{prefix} {note}".strip()
            notes.append("added proxy-mode uncertainty note")

    return repaired, notes


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_baseline_codex(
    prompt: str,
    blueprint: Dict[str, Any],
    model: str,
    timeout_seconds: int,
    verbose: bool = False,
    heartbeat_seconds: int = 15,
) -> Dict[str, Any]:
    """Call Codex CLI for one category baseline and require JSON output."""
    schema = build_baseline_json_schema(blueprint)
    category_id = str(blueprint.get("meta", {}).get("category_id", "unknown"))

    with tempfile.TemporaryDirectory(prefix="step6_codex_") as temp_dir:
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
            f"    codex launch: category={category_id}, model={model}, timeout={timeout_seconds}s, temp_dir={temp_path}",
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
                    raise RuntimeError(f"Codex generation timed out after {timeout_seconds}s (temp_dir={temp_path})")
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
            f"    codex exited: return_code={return_code}, elapsed={elapsed}s, output_exists={output_path.exists()}",
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
        log_stage(f"    output received: bytes={len(raw_output.encode('utf-8'))}", verbose=verbose)

        try:
            parsed = json.loads(raw_output)
            log_stage("    json parsed: stdlib json.loads", verbose=verbose)
        except json.JSONDecodeError:
            parsed = parse_llm_json(raw_output)
            if not isinstance(parsed, dict):
                raise ValueError("Codex final message was not a JSON object")
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
            },
        }


@retry(
    retry=retry_if_exception_type((RuntimeError, ValueError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
)
def call_baseline_claude(prompt: str, category_id: str) -> Dict[str, Any]:
    """Call Claude for one category baseline and require parsed JSON output."""
    from src.common.unified_llm import invoke_unified_sync

    result = invoke_unified_sync(
        prompt=prompt,
        step_name="eval_baseline_generation",
        job_id=category_id,
        validate_json=True,
    )
    if not result.success:
        error = result.error or f"LLM failed for {category_id}"
        lowered = error.lower()
        if "not logged in" in lowered or "/login" in lowered:
            raise PermissionError("Claude CLI is not authenticated. Run `claude /login` and rerun Step 6.")
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


def build_repair_prompt(
    blueprint: Dict[str, Any],
    current_baseline: Dict[str, Any],
    issues: Sequence[str],
) -> str:
    """Build a minimal-edit repair prompt for a previously generated baseline."""
    return f"""
You are repairing a previously generated Step 6 baseline JSON.

Return valid JSON only. Preserve content that is already correct. Make the smallest edits needed to fix the issues.

SOURCE BLUEPRINT META
{json.dumps(blueprint.get("meta", {}), indent=2)}

VALIDATION ISSUES
{json.dumps(list(issues), indent=2)}

CURRENT BASELINE JSON
{json.dumps(current_baseline, indent=2)}
"""


def generate_baseline(
    blueprint: Dict[str, Any],
    curated_evidence: Dict[str, Any],
    upstream_inventory: Dict[str, Any],
    representation: Dict[str, Any],
    max_attempts: int,
    provider: str,
    model: str,
    timeout_seconds: int,
    verbose: bool = False,
    heartbeat_seconds: int = 15,
) -> Dict[str, Any]:
    """Generate a validated Step 6 baseline with retries and repairs."""
    category_id = str(blueprint["meta"]["category_id"])
    run_dir = build_debug_run_dir(category_id)

    blueprint_summary = build_blueprint_summary(blueprint)
    curated_summary = build_curated_evidence_summary(blueprint, curated_evidence)
    upstream_summary = build_upstream_evidence_summary(blueprint, upstream_inventory)
    representation_summary = build_master_cv_representation_summary(blueprint, curated_evidence, representation)
    evidence_reference_index = build_evidence_reference_index(curated_evidence, upstream_inventory, representation)

    write_json_file(run_dir / "blueprint_summary.json", blueprint_summary)
    write_json_file(run_dir / "curated_evidence_summary.json", curated_summary)
    write_json_file(run_dir / "upstream_evidence_summary.json", upstream_summary)
    write_json_file(run_dir / "representation_summary.json", representation_summary)
    write_json_file(run_dir / "evidence_reference_index.json", evidence_reference_index)

    prompt = build_baseline_prompt(
        category_id=category_id,
        blueprint_summary=blueprint_summary,
        curated_summary=curated_summary,
        upstream_summary=upstream_summary,
        representation_summary=representation_summary,
        evidence_reference_index=evidence_reference_index,
        blueprint=blueprint,
    )

    for attempt in range(1, max_attempts + 1):
        log_stage(f"  attempt {attempt}/{max_attempts} started", always=True)
        log_stage("  building prompt", verbose=verbose)
        log_stage(f"  prompt built: chars={len(prompt)}", verbose=verbose)

        try:
            if provider == "codex":
                response_payload = call_baseline_codex(
                    prompt=prompt,
                    blueprint=blueprint,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    verbose=verbose,
                    heartbeat_seconds=heartbeat_seconds,
                )
            elif provider == "claude":
                response_payload = call_baseline_claude(prompt, category_id)
            else:
                raise ValueError(f"Unsupported provider: {provider}")
        except (RetryError, RuntimeError, ValueError, PermissionError) as exc:
            error_message = str(exc)
            write_attempt_debug(
                run_dir,
                attempt,
                "call_failed",
                prompt,
                issues=[error_message],
                notes=["provider call failed before a parsed baseline was returned"],
            )
            print(f"  attempt {attempt}/{max_attempts} provider failure: {error_message}")
            if attempt == max_attempts:
                raise
            continue

        baseline = response_payload["parsed_json"]
        write_attempt_debug(run_dir, attempt, "raw", prompt, response_payload=response_payload, parsed_baseline=baseline)
        log_stage("  validation started", verbose=verbose)
        issues = validate_baseline(baseline, blueprint, curated_summary, upstream_summary)
        if not issues:
            write_attempt_debug(run_dir, attempt, "validated", prompt, parsed_baseline=baseline, notes=["validation passed"])
            log_stage("  validation passed", verbose=verbose)
            return baseline

        repaired_baseline, repair_notes = apply_lightweight_baseline_repairs(baseline, blueprint)
        repaired_issues = validate_baseline(repaired_baseline, blueprint, curated_summary, upstream_summary)
        if not repaired_issues:
            write_attempt_debug(run_dir, attempt, "lightweight_repair", prompt, parsed_baseline=repaired_baseline, issues=issues, notes=repair_notes)
            log_stage("  validation passed after lightweight repair", verbose=verbose)
            return repaired_baseline

        repair_prompt = build_repair_prompt(blueprint, repaired_baseline, repaired_issues)
        if provider == "codex":
            repair_response = call_baseline_codex(
                prompt=repair_prompt,
                blueprint=blueprint,
                model=model,
                timeout_seconds=timeout_seconds,
                verbose=verbose,
                heartbeat_seconds=heartbeat_seconds,
            )
        else:
            repair_response = call_baseline_claude(repair_prompt, category_id)
        repaired_by_model = repair_response["parsed_json"]
        final_issues = validate_baseline(repaired_by_model, blueprint, curated_summary, upstream_summary)
        if not final_issues:
            write_attempt_debug(run_dir, attempt, "model_repair", repair_prompt, response_payload=repair_response, parsed_baseline=repaired_by_model, issues=repaired_issues, notes=["validation passed after model repair"])
            log_stage("  validation passed after model repair", verbose=verbose)
            return repaired_by_model

        write_attempt_debug(run_dir, attempt, "rejected", repair_prompt, response_payload=repair_response, parsed_baseline=repaired_by_model, issues=final_issues, notes=repair_notes)
        print(f"  attempt {attempt}/{max_attempts} rejected:")
        for issue in final_issues:
            print(f"    - {issue}")

    raise RetryError("Step 6 generation exhausted without a valid baseline")


def render_baseline_markdown(baseline: Dict[str, Any]) -> str:
    """Render a deterministic Markdown report from saved baseline JSON."""
    meta = baseline["meta"]
    overall = baseline["overall_assessment"]
    scores = baseline["score_breakdown"]

    lines = [
        f"# {meta['category_name']} Baseline",
        "",
        f"- Category ID: `{meta['category_id']}`",
        f"- Macro family: `{meta['macro_family']}`",
        f"- Priority: `{meta['priority']}`",
        f"- Confidence: `{meta['confidence']}`",
        f"- Representation proxy mode: `{meta['representation_proxy_mode']}`",
        "",
        "## Overall Assessment",
        "",
        f"- Combined fit score: **{overall['combined_fit_score']:.2f} / 10**",
        f"- Readiness tier: **{overall['readiness_tier']}**",
        f"- Verdict: {overall['one_sentence_verdict']}",
        f"- Uncertainty: {overall['uncertainty_note']}",
        "",
        "### Citations",
    ]
    for citation in overall.get("citations", []):
        lines.append(f"- {citation}")

    lines.extend(
        [
            "",
            "## Score Breakdown",
            "",
            f"- Candidate evidence coverage: {scores['candidate_evidence_coverage_score']:.2f}",
            f"- Evidence curation completeness: {scores['evidence_curation_completeness_score']:.2f}",
            f"- Master CV representation quality: {scores['master_cv_representation_quality_score']:.2f}",
            f"- AI / architecture fit: {scores['ai_architecture_fit_score']:.2f}",
            f"- Leadership / scope fit: {scores['leadership_scope_fit_score']:.2f}",
            f"- Impact proof strength: {scores['impact_proof_strength_score']:.2f}",
            "",
            "### Weighted Score Explanation",
        ]
    )
    for item in scores.get("weighted_score_explanation", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Citations")
    for citation in scores.get("citations", []):
        lines.append(f"- {citation}")

    lines.extend(["", "## Strongest Supported Signals", ""])
    for item in baseline.get("strongest_supported_signals", []):
        lines.append(f"### {item['signal']}")
        lines.append(f"- Why it matters: {item['why_it_matters_for_category']}")
        lines.append(f"- Status: `{item['status']}`")
        lines.append(f"- Evidence refs: {', '.join(item.get('evidence_refs', []))}")
        lines.append(f"- Citation: {item['citation']}")
        lines.append("")

    lines.extend(["## Gap Analysis", ""])
    grouped_gaps: Dict[str, List[Dict[str, Any]]] = {gap_type: [] for gap_type in ALLOWED_GAP_TYPES}
    for item in baseline.get("gap_analysis", []):
        grouped_gaps[item["gap_type"]].append(item)
    for gap_type in sorted(grouped_gaps.keys()):
        lines.append(f"### {gap_type}")
        for item in grouped_gaps[gap_type]:
            lines.append(f"- Signal: {item['signal']}")
            lines.append(f"- Why it matters: {item['why_it_matters']}")
            lines.append(f"- Current state: {item['current_state']}")
            lines.append(f"- Safe interpretation: {item['safe_interpretation']}")
            lines.append(f"- Recommended action: {item['recommended_action']}")
            lines.append(f"- Evidence refs: {', '.join(item.get('evidence_refs', []))}")
            lines.append(f"- Citation: {item['citation']}")
            lines.append("")

    safe_claims = baseline.get("safe_claims_now", {})
    lines.extend(["## Safe Claims Now", ""])
    for key in ["headline_safe", "profile_safe", "experience_safe", "leadership_safe", "unsafe_or_too_weak"]:
        lines.append(f"### {key}")
        for item in safe_claims.get(key, []):
            lines.append(f"- {item}")
        lines.append("")
    lines.append("### Citations")
    for citation in safe_claims.get("citations", []):
        lines.append(f"- {citation}")

    diagnosis = baseline.get("representation_diagnosis", {})
    lines.extend(["", "## Representation Diagnosis", ""])
    for key in ["well_represented_now", "underrepresented_now", "overstated_risk_now", "representation_priorities"]:
        lines.append(f"### {key}")
        for item in diagnosis.get(key, []):
            lines.append(f"- {item}")
        lines.append("")
    lines.append("### Citations")
    for citation in diagnosis.get("citations", []):
        lines.append(f"- {citation}")

    lines.extend(["", "## Curation Priorities", ""])
    for item in baseline.get("curation_priorities", []):
        lines.append(f"### {item['priority_rank']}. {item['action']}")
        lines.append(f"- Why now: {item['why_now']}")
        lines.append(f"- Target files: {', '.join(item.get('target_files', []))}")
        lines.append(f"- Source refs: {', '.join(item.get('source_refs', []))}")
        lines.append(f"- Expected impact: {item['expected_category_impact']}")
        lines.append(f"- Citation: {item['citation']}")
        lines.append("")

    lines.extend(["## Master CV Upgrade Actions", ""])
    for item in baseline.get("master_cv_upgrade_actions", []):
        lines.append(f"### {item['priority_rank']}. {item['action']}")
        lines.append(f"- Section: `{item['section']}`")
        lines.append(f"- Why now: {item['why_now']}")
        lines.append(f"- Supported by: {', '.join(item.get('supported_by', []))}")
        lines.append(f"- Citation: {item['citation']}")
        lines.append("")

    lines.extend(["## Evidence Ledger", ""])
    for item in baseline.get("evidence_ledger", []):
        lines.append(f"- `{item['classification']}` ({item['confidence']}): {item['recommendation']}")
        lines.append(f"  Support: {', '.join(item.get('support', []))}")

    return "\n".join(lines).strip() + "\n"


def write_baseline_files(category_id: str, baseline: Dict[str, Any]) -> None:
    """Write JSON and Markdown artifacts for one validated baseline."""
    json_path = BASELINE_DIR / f"{category_id}_baseline.json"
    md_path = BASELINE_DIR / f"{category_id}_baseline.md"
    with open(json_path, "w") as f:
        json.dump(baseline, f, indent=2)
    with open(md_path, "w") as f:
        f.write(render_baseline_markdown(baseline))


def render_baseline_index() -> None:
    """Render a Markdown index from saved baseline JSON files."""
    rows = []
    for path in sorted(BASELINE_DIR.glob("*_baseline.json")):
        if path.name == "evidence_map.json":
            continue
        with open(path) as f:
            baseline = json.load(f)
        rows.append(
            {
                "category_id": baseline.get("meta", {}).get("category_id", path.stem.replace("_baseline", "")),
                "category_name": baseline.get("meta", {}).get("category_name", ""),
                "score": baseline.get("overall_assessment", {}).get("combined_fit_score", 0),
                "tier": baseline.get("overall_assessment", {}).get("readiness_tier", ""),
                "proxy": baseline.get("meta", {}).get("representation_proxy_mode", True),
                "next_actions": [
                    item.get("action", "")
                    for item in baseline.get("curation_priorities", [])[:1] + baseline.get("master_cv_upgrade_actions", [])[:1]
                    if item.get("action")
                ],
            }
        )

    lines = [
        "# Step 6 Baselines Index",
        "",
        f"Generated baselines: {len(rows)}",
        "",
    ]
    for row in rows:
        lines.append(f"## {row['category_name']} (`{row['category_id']}`)")
        lines.append(f"- Combined fit score: **{row['score']:.2f} / 10**")
        lines.append(f"- Readiness tier: `{row['tier']}`")
        lines.append(f"- Representation proxy mode: `{row['proxy']}`")
        for action in row["next_actions"]:
            lines.append(f"- Next action: {action}")
        lines.append("")

    (BASELINE_DIR / "index.md").write_text("\n".join(lines).strip() + "\n")


def render_only() -> None:
    """Re-render markdown artifacts from saved baseline JSON files."""
    for path in sorted(BASELINE_DIR.glob("*_baseline.json")):
        if path.name == "evidence_map.json":
            continue
        with open(path) as f:
            baseline = json.load(f)
        category_id = baseline.get("meta", {}).get("category_id", path.stem.replace("_baseline", ""))
        with open(BASELINE_DIR / f"{category_id}_baseline.md", "w") as f:
            f.write(render_baseline_markdown(baseline))
    render_baseline_index()


def write_evidence_map(
    curated_evidence: Dict[str, Any],
    upstream_inventory: Dict[str, Any],
    representation: Dict[str, Any],
) -> None:
    """Write a compact evidence inventory for debugging and reuse."""
    payload = {
        "curated_files": {
            "roles": [role["file"] for role in curated_evidence["roles"]],
            "projects": [project["file"] for project in curated_evidence["projects"]],
            "project_skills": [skill["_file"] for skill in curated_evidence["project_skills"]],
            "role_metadata": ROLE_METADATA_PATH.as_posix(),
            "role_taxonomy": ROLE_TAXONOMY_PATH.as_posix(),
        },
        "upstream_files": upstream_inventory["files"],
        "representation_source_mode": representation.get("mode"),
    }
    write_json_file(BASELINE_DIR / "evidence_map.json", payload)


def main() -> int:
    """CLI entrypoint for Step 6 baseline generation."""
    parser = argparse.ArgumentParser(description="Eval Step 6: Generate category baselines from blueprints")
    parser.add_argument("--category", action="append", help="Process a single category id; can be passed multiple times")
    parser.add_argument("--force", action="store_true", help="Regenerate existing baseline JSON files")
    parser.add_argument("--render-only", action="store_true", help="Render Markdown/index from existing baseline JSON files")
    parser.add_argument("--provider", choices=["codex", "claude"], default="codex", help="LLM backend for baseline generation")
    parser.add_argument("--model", default=DEFAULT_CODEX_MODEL, help="Model to use when --provider=codex")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_CODEX_TIMEOUT_SECONDS, help="Timeout for one model invocation")
    parser.add_argument("--max-attempts", type=int, default=2, help="Maximum attempts per category")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose generation logs")
    parser.add_argument("--heartbeat-seconds", type=int, default=15, help="Heartbeat interval while waiting for Codex")
    parser.add_argument("--representation-source", choices=["auto", "proxy", "canonical"], default="auto", help="How to load the current master-CV representation")
    args = parser.parse_args()

    if args.render_only:
        render_only()
        print("Rendered Markdown and index from existing baseline JSON files")
        return 0

    categories = args.category or list_categories()
    if not categories:
        print("No blueprint JSON files found in data/eval/blueprints")
        return 1

    curated_evidence = load_curated_evidence()
    upstream_inventory = load_upstream_evidence_inventory()
    representation = load_master_cv_representation(curated_evidence, args.representation_source)
    write_evidence_map(curated_evidence, upstream_inventory, representation)

    print(
        f"Step 6: Generating baselines for {len(categories)} categories "
        f"(provider={args.provider}{', model=' + args.model if args.provider == 'codex' else ''}, "
        f"representation={representation.get('mode')})"
    )

    for category_id in categories:
        output_path = BASELINE_DIR / f"{category_id}_baseline.json"
        if output_path.exists() and not args.force:
            print(f"[{category_id}] skipped - baseline exists (use --force to regenerate)")
            continue

        blueprint_path = BLUEPRINT_DIR / f"{category_id}_blueprint.json"
        if not blueprint_path.exists():
            print(f"[{category_id}] skipped - blueprint missing at {blueprint_path}")
            continue

        print(f"[{category_id}] generating...")
        blueprint = load_blueprint(category_id)
        try:
            baseline = generate_baseline(
                blueprint=blueprint,
                curated_evidence=curated_evidence,
                upstream_inventory=upstream_inventory,
                representation=representation,
                max_attempts=args.max_attempts,
                provider=args.provider,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
                verbose=args.verbose,
                heartbeat_seconds=args.heartbeat_seconds,
            )
            log_stage("  writing baseline files", verbose=args.verbose)
            write_baseline_files(category_id, baseline)
            print(
                f"[{category_id}] done - score={baseline['overall_assessment']['combined_fit_score']:.2f}, "
                f"tier={baseline['overall_assessment']['readiness_tier']}"
            )
        except (RetryError, RuntimeError, PermissionError, ValueError, FileNotFoundError) as exc:
            print(f"[{category_id}] failed: {exc}")

    render_baseline_index()
    print("Step 6 complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
