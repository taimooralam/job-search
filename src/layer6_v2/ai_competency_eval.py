"""
AI Competency Hallucination Evaluator

Checks AI skill claims in generated CV text against the Commander-4 build checklist.
Read-only flagging -- never removes skills from the CV, only reports status.

Called from orchestrator grading phase for AI jobs only.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ClaimStatus:
    """Status of a single skill claim."""

    claim: str
    status: str  # "verified", "unverified", "not_yet_built"
    matched_to: Optional[str] = None  # What it matched against


@dataclass
class EvalResult:
    """Result of AI competency evaluation."""

    passed: bool
    total_claims: int
    verified_count: int
    unverified_count: int
    flagged_count: int  # Claims matching not_yet_built
    claims: List[ClaimStatus] = field(default_factory=list)
    summary: str = ""


def _load_ground_truth() -> Dict[str, List[str]]:
    """Load Commander-4 skills ground truth from JSON."""
    path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "master-cv"
        / "projects"
        / "commander4_skills.json"
    )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load commander4_skills.json: %s", e)
        return {"verified_skills": [], "verified_patterns": [], "not_yet_built": []}


def _normalize(text: str) -> str:
    """Normalize text for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _fuzzy_match(claim: str, reference_list: List[str]) -> Optional[str]:
    """Check if a claim fuzzy-matches any item in the reference list."""
    claim_norm = _normalize(claim)
    for ref in reference_list:
        ref_norm = _normalize(ref)
        # Exact substring match in either direction
        if ref_norm in claim_norm or claim_norm in ref_norm:
            return ref
    return None


def extract_ai_claims(cv_text: str) -> List[str]:
    """Extract AI/Commander-4-related skill claims from CV text.

    Looks for claims in:
    - Commander-4/Joyia project section bullets
    - Header/core competencies mentioning AI/LLM terms
    - Technical skills section

    Returns list of claim strings.
    """
    claims: List[str] = []

    # Extract AI project section bullets (lines starting with - or * after project header)
    ai_project_section = False
    for line in cv_text.split("\n"):
        line_stripped = line.strip()
        if any(term in line_stripped.lower() for term in ("commander", "joyia", "knowledgeflow")):
            ai_project_section = True
            continue
        if ai_project_section:
            if line_stripped.startswith(("- ", "- ", "* ")):
                claims.append(line_stripped.lstrip("-* ").strip())
            elif line_stripped and not line_stripped.startswith((" ", "\t")):
                # New section started
                ai_project_section = False

    # Extract AI-related terms from header/competencies that correspond to
    # not-yet-built features -- these are the hallucination candidates
    ai_terms_pattern = re.compile(
        r"\b(semantic caching|vector (?:database|search|store)|"
        r"circuit breaker|rate limit(?:ing)?|streaming|eval harness|"
        r"golden.set|fine.tun(?:ing)?|cost track(?:ing)?|load balanc(?:ing)?|"
        r"multi.provider|LLM gateway|provider (?:fallback|routing)|"
        r"quality gate|model registry|raptor|mcp|zod|guardrail|"
        r"knowledgeflow|confluence|jira.adf|document.ingestion|"
        r"structured.output|tool.calling)\b",
        re.IGNORECASE,
    )
    seen: set = set()
    for match in ai_terms_pattern.finditer(cv_text):
        term = match.group(0)
        if term not in seen:
            seen.add(term)
            claims.append(term)

    return claims


def evaluate_ai_competencies(
    cv_text: str,
    ground_truth: Optional[Dict[str, List[str]]] = None,
) -> EvalResult:
    """Evaluate AI competency claims in CV text against ground truth.

    Args:
        cv_text: Generated CV text (markdown)
        ground_truth: Optional override for testing. If None, loads from file.

    Returns:
        EvalResult with per-claim status and pass/fail
    """
    if ground_truth is None:
        ground_truth = _load_ground_truth()

    verified_skills: List[str] = ground_truth.get("verified_skills", [])
    verified_patterns: List[str] = ground_truth.get("verified_patterns", [])
    not_yet_built: List[str] = ground_truth.get("not_yet_built", [])
    all_verified = verified_skills + verified_patterns

    claims = extract_ai_claims(cv_text)

    if not claims:
        return EvalResult(
            passed=True,
            total_claims=0,
            verified_count=0,
            unverified_count=0,
            flagged_count=0,
            summary="No AI competency claims found",
        )

    statuses: List[ClaimStatus] = []
    for claim in claims:
        # Check not_yet_built first (these are hallucinations)
        flagged_match = _fuzzy_match(claim, not_yet_built)
        if flagged_match:
            statuses.append(
                ClaimStatus(claim=claim, status="not_yet_built", matched_to=flagged_match)
            )
            continue

        # Check verified
        verified_match = _fuzzy_match(claim, all_verified)
        if verified_match:
            statuses.append(
                ClaimStatus(claim=claim, status="verified", matched_to=verified_match)
            )
            continue

        # Unverified (not in either list -- could be a general skill)
        statuses.append(ClaimStatus(claim=claim, status="unverified"))

    verified_count = sum(1 for s in statuses if s.status == "verified")
    flagged_count = sum(1 for s in statuses if s.status == "not_yet_built")
    unverified_count = sum(1 for s in statuses if s.status == "unverified")

    # Pass if no not_yet_built claims are flagged
    passed = flagged_count == 0

    summary_parts = [f"{verified_count} verified"]
    if flagged_count:
        summary_parts.append(f"{flagged_count} FLAGGED (not yet built)")
    if unverified_count:
        summary_parts.append(f"{unverified_count} unverified")

    return EvalResult(
        passed=passed,
        total_claims=len(claims),
        verified_count=verified_count,
        unverified_count=unverified_count,
        flagged_count=flagged_count,
        claims=statuses,
        summary=", ".join(summary_parts),
    )
