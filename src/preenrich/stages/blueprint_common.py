"""Shared deterministic helpers for iteration-4.1 blueprint stages."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.preenrich.blueprint_config import load_job_taxonomy
from src.preenrich.blueprint_models import EvidenceRef

KNOWN_SKILLS = [
    "python",
    "aws",
    "gcp",
    "azure",
    "kubernetes",
    "docker",
    "terraform",
    "llm",
    "genai",
    "machine learning",
    "ml",
    "ai",
    "rag",
    "pytorch",
    "tensorflow",
    "sql",
    "postgresql",
    "spark",
]
KNOWN_SOFT_SKILLS = [
    "leadership",
    "mentoring",
    "communication",
    "stakeholder management",
    "collaboration",
    "ownership",
    "execution",
]


def _clean_lines(text: str) -> list[str]:
    return [line.strip(" -*\t") for line in (text or "").splitlines() if line.strip()]


def extract_bullets_for_headers(text: str, headers: tuple[str, ...]) -> list[str]:
    lines = _clean_lines(text)
    capture = False
    items: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(header in lowered for header in headers):
            capture = True
            continue
        if capture and re.match(r"^[a-z].{0,60}:$", lowered):
            break
        if capture:
            items.append(line)
            if len(items) >= 8:
                break
    return items


def detect_remote_policy(text: str, location: str | None = None) -> str:
    haystack = f"{text} {location or ''}".lower()
    if "hybrid" in haystack:
        return "hybrid"
    if "remote" in haystack:
        return "fully_remote"
    if "onsite" in haystack or "on-site" in haystack:
        return "onsite"
    return "not_specified"


def extract_salary_range(text: str) -> str | None:
    match = re.search(
        r"([$€£]\s?\d[\d,]*(?:[kKmM])?(?:\s?[-–]\s?[$€£]?\d[\d,]*(?:[kKmM])?)?)",
        text or "",
    )
    return match.group(1) if match else None


def extract_keywords(text: str, *, limit: int = 15) -> list[str]:
    lowered = (text or "").lower()
    found = [skill for skill in KNOWN_SKILLS if skill in lowered]
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", text or "")
    for word in words:
        candidate = word.strip()
        if candidate.lower() not in found and candidate.lower() not in {"and", "with", "for", "the"}:
            found.append(candidate.lower())
        if len(found) >= limit:
            break
    return found[:limit]


def extract_skill_signals(text: str) -> tuple[list[str], list[str]]:
    lowered = (text or "").lower()
    hard = [skill for skill in KNOWN_SKILLS if skill in lowered]
    soft = [skill for skill in KNOWN_SOFT_SKILLS if skill in lowered]
    return hard[:12], soft[:8]


def evidence_from_quote(source: str, quote: str, locator: str | None = None) -> EvidenceRef:
    return EvidenceRef(source=source, locator=locator, quote=quote[:280] if quote else None)


def detect_portal_family(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    taxonomy = load_job_taxonomy()
    for family, config in (taxonomy.get("portal_families") or {}).items():
        for pattern in config.get("url_patterns", []):
            if pattern and pattern.lower() in host:
                return family
    return "custom_unknown"


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return None
    return f"https://{value}"


def title_family(title: str) -> str:
    lowered = (title or "").lower()
    if "cto" in lowered or "chief technology" in lowered:
        return "cto"
    if "vp" in lowered and "engineering" in lowered:
        return "vp_engineering"
    if "head of engineering" in lowered:
        return "head_of_engineering"
    if "director" in lowered and "engineering" in lowered:
        return "director_of_engineering"
    if "manager" in lowered:
        return "engineering_manager"
    if "staff" in lowered or "principal" in lowered or "architect" in lowered:
        return "staff_principal_engineer"
    if "lead" in lowered:
        return "tech_lead"
    return "senior_engineer"


def selector_profiles_for_primary(primary_role_category: str) -> list[str]:
    taxonomy = load_job_taxonomy()
    node = (taxonomy.get("primary_role_categories") or {}).get(primary_role_category, {})
    return list((node.get("maps_from") or {}).get("selector_profiles", []))


def search_profiles_for_primary(primary_role_category: str) -> list[str]:
    taxonomy = load_job_taxonomy()
    node = (taxonomy.get("primary_role_categories") or {}).get(primary_role_category, {})
    return list((node.get("maps_from") or {}).get("search_profiles", []))


def tone_for_primary(primary_role_category: str) -> str:
    taxonomy = load_job_taxonomy()
    node = (taxonomy.get("primary_role_categories") or {}).get(primary_role_category, {})
    tones = list((node.get("maps_from") or {}).get("tone_families", []))
    return tones[0] if tones else "hands_on"


def ideal_archetypes_for_primary(primary_role_category: str) -> list[str]:
    taxonomy = load_job_taxonomy()
    node = (taxonomy.get("primary_role_categories") or {}).get(primary_role_category, {})
    return list((node.get("maps_from") or {}).get("ideal_candidate_archetypes", []))


def ai_relevance(text: str, title: str = "") -> dict[str, Any]:
    haystack = f"{title} {text}".lower()
    categories: list[str] = []
    if any(token in haystack for token in ("ai", "machine learning", "ml", "llm", "genai", "rag")):
        categories.append("ai_general")
    if any(token in haystack for token in ("llm", "genai", "rag", "agent")):
        categories.append("genai_llm")
    if "mlops" in haystack or "llmops" in haystack:
        categories.append("mlops_llmops")
    categories = list(dict.fromkeys(categories))
    return {
        "is_ai_job": bool(categories),
        "categories": categories,
        "rationale": "Detected AI-specific terms in the title or JD." if categories else "No AI-specific terms detected.",
    }
