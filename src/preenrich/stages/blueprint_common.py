"""Shared deterministic helpers for iteration-4.1 blueprint stages."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from src.preenrich.blueprint_config import load_job_taxonomy
from src.preenrich.blueprint_models import AITaxonomyDoc, ClassificationEvidence, EvidenceRef

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


def detect_ats_vendor(url: str | None) -> str | None:
    family = detect_portal_family(url)
    if family in {None, "custom_unknown"}:
        return "unknown"
    return family


def canonical_domain_from_url(url: str | None) -> str | None:
    normalized = normalize_url(url)
    if not normalized:
        return None
    host = (urlparse(normalized).netloc or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def company_slug(value: str | None) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return text


AGGREGATOR_HOST_TOKENS = (
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "welcometothejungle.com",
)


def is_aggregator_url(url: str | None) -> bool:
    host = canonical_domain_from_url(url) or ""
    return any(token in host for token in AGGREGATOR_HOST_TOKENS)


def url_matches_company(url: str | None, company_name: str | None, company_domain: str | None = None) -> bool:
    host = canonical_domain_from_url(url) or ""
    if not host:
        return False
    if company_domain and company_domain in host:
        return True
    slug = company_slug(company_name)
    if slug and slug.replace("-", "") in host.replace(".", "").replace("-", ""):
        return True
    family = detect_portal_family(url)
    return bool(family and family != "custom_unknown")


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


def _normalized_slug(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(item) for item in value if item).lower()
    return str(value).lower()


def _normalized_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value).strip()]


def _match_patterns(text: str, patterns: list[str]) -> list[str]:
    haystack = _normalized_text(text)
    hits: list[str] = []
    for pattern in patterns or []:
        probe = str(pattern).strip().lower()
        if probe and probe in haystack and probe not in hits:
            hits.append(probe)
    return hits


def _score_text_block(text: str, patterns: list[str]) -> tuple[float, list[str]]:
    hits = _match_patterns(text, patterns)
    return float(len(hits)), hits


def _competency_similarity(actual: dict[str, Any] | None, anchors: dict[str, Any] | None) -> tuple[float, dict[str, int]]:
    if not isinstance(actual, dict) or not isinstance(anchors, dict):
        return 0.0, {}
    deltas: dict[str, int] = {}
    distance = 0
    for key in ("delivery", "process", "architecture", "leadership"):
        try:
            actual_value = int(actual.get(key, 0))
            anchor_value = int(anchors.get(key, 0))
        except Exception:
            return 0.0, {}
        deltas[key] = abs(actual_value - anchor_value)
        distance += deltas[key]
    similarity = max(0.0, 1.0 - (distance / 200.0))
    return similarity, deltas


def role_categories() -> list[str]:
    return list((load_job_taxonomy().get("primary_role_categories") or {}).keys())


def score_categories_from_taxonomy(inputs: dict[str, Any], taxonomy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    payload = taxonomy or load_job_taxonomy()
    role_nodes = payload.get("primary_role_categories") or {}
    weights = ((payload.get("classification_engine") or {}).get("score_weights") or {})
    title_text = _normalized_text(inputs.get("title"))
    responsibilities_text = _normalized_text(inputs.get("responsibilities"))
    qualifications_text = _normalized_text(inputs.get("qualifications"))
    keywords_text = _normalized_text(inputs.get("top_keywords"))
    jd_facts_role_category = _normalized_slug(str(inputs.get("jd_facts_role_category") or "")) if inputs.get("jd_facts_role_category") else None
    ideal_archetype = _normalized_slug(str(inputs.get("ideal_candidate_archetype") or "")) if inputs.get("ideal_candidate_archetype") else None
    seniority = _normalized_slug(str(inputs.get("seniority_level") or "")) if inputs.get("seniority_level") else None
    competency = inputs.get("competency_weights") or {}

    entries: list[dict[str, Any]] = []
    for category, node in role_nodes.items():
        title_hits = _match_patterns(title_text, list(node.get("title_signals") or []))
        title_negative_hits = _match_patterns(title_text, list(node.get("title_negatives") or []))
        responsibility_hits = _match_patterns(responsibilities_text, list(node.get("responsibility_signals") or []))
        qualification_hits = _match_patterns(qualifications_text, list(node.get("qualification_signals") or []))
        keyword_hits = _match_patterns(keywords_text, list(node.get("keyword_signals") or []))
        archetype_hits = [ideal_archetype] if ideal_archetype and ideal_archetype in { _normalized_slug(x) for x in node.get("archetype_signals") or [] } else []
        seniority_hits = [seniority] if seniority and seniority in { _normalized_slug(x) for x in node.get("seniority_signals") or [] } else []
        competency_score, competency_delta = _competency_similarity(competency, node.get("competency_anchors") or {})

        score = 0.0
        score += float(weights.get("title", 3.0)) * len(title_hits)
        score -= float(weights.get("title", 3.0)) * len(title_negative_hits)
        score += float(weights.get("responsibilities", 2.0)) * len(responsibility_hits)
        score += float(weights.get("qualifications", 1.5)) * len(qualification_hits)
        score += float(weights.get("keywords", 1.2)) * len(keyword_hits)
        score += float(weights.get("competency", 1.4)) * competency_score
        score += float(weights.get("archetype", 1.0)) * len(archetype_hits)
        score += float(weights.get("seniority", 1.0)) * len(seniority_hits)
        if jd_facts_role_category == category:
            score += float(weights.get("jd_facts_role_category", 2.8))

        entries.append(
            {
                "category": category,
                "score": round(score, 4),
                "matched_signal_count": len(title_hits)
                + len(responsibility_hits)
                + len(qualification_hits)
                + len(keyword_hits)
                + len(archetype_hits)
                + len(seniority_hits),
                "evidence": ClassificationEvidence(
                    title_matches=title_hits + title_negative_hits,
                    responsibility_matches=responsibility_hits,
                    qualification_matches=qualification_hits,
                    keyword_matches=keyword_hits,
                    competency_anchor_match=competency_delta,
                    archetype_matches=archetype_hits,
                    section_refs=[],
                ).model_dump(),
            }
        )
    entries.sort(key=lambda item: item["score"], reverse=True)
    return entries


def apply_disambiguation_rules(
    pre_score: list[dict[str, Any]],
    inputs: dict[str, Any],
    taxonomy: dict[str, Any] | None = None,
    margin: float | None = None,
) -> tuple[str, list[str]]:
    if not pre_score:
        return title_family(str(inputs.get("title") or "")), ["missing_taxonomy_signals"]
    payload = taxonomy or load_job_taxonomy()
    effective_margin = (
        margin
        if margin is not None
        else float((((payload.get("classification_engine") or {}).get("thresholds") or {}).get("disambiguation_margin") or 0.15)
        )
    )
    top = pre_score[0]
    second = pre_score[1] if len(pre_score) > 1 else None
    if second is None or (top["score"] - second["score"]) > effective_margin:
        return str(top["category"]), []

    title_text = _normalized_text(inputs.get("title"))
    responsibilities_text = _normalized_text(inputs.get("responsibilities"))
    qualifications_text = _normalized_text(inputs.get("qualifications"))
    seniority = _normalized_slug(str(inputs.get("seniority_level") or "")) if inputs.get("seniority_level") else None

    reason_codes: list[str] = []
    top_two = {str(top["category"]), str(second["category"])}
    for rule in payload.get("disambiguation_rules") or []:
        pair = {_normalized_slug(item) for item in rule.get("pair") or []}
        if not top_two.issubset(pair):
            continue
        title_priority = rule.get("title_priority") or {}
        for category, patterns in title_priority.items():
            hits = _match_patterns(title_text, list(patterns or []))
            if hits:
                reason_codes.append(f"disambiguation:{rule.get('id')}")
                return _normalized_slug(category), reason_codes
        when_any = rule.get("when_any") or {}
        responsibility_signals = when_any.get("responsibility_signals") or {}
        qualification_signals = when_any.get("qualification_signals") or {}
        seniority_signals = when_any.get("seniority_signals") or {}
        for category, patterns in responsibility_signals.items():
            if _match_patterns(responsibilities_text, list(patterns or [])):
                reason_codes.append(f"disambiguation:{rule.get('id')}")
                return _normalized_slug(category), reason_codes
        for category, patterns in qualification_signals.items():
            if _match_patterns(qualifications_text, list(patterns or [])):
                reason_codes.append(f"disambiguation:{rule.get('id')}")
                return _normalized_slug(category), reason_codes
        for category, values in seniority_signals.items():
            if seniority and seniority in {_normalized_slug(item) for item in values or []}:
                reason_codes.append(f"disambiguation:{rule.get('id')}")
                return _normalized_slug(category), reason_codes
    return str(top["category"]), reason_codes


def detect_ai_taxonomy(inputs: dict[str, Any], taxonomy: dict[str, Any] | None = None) -> AITaxonomyDoc:
    payload = taxonomy or load_job_taxonomy()
    ai_taxonomy = payload.get("ai_taxonomy") or {}
    text = "\n".join(
        [
            _normalized_text(inputs.get("title")),
            _normalized_text(inputs.get("responsibilities")),
            _normalized_text(inputs.get("qualifications")),
            _normalized_text(inputs.get("top_keywords")),
        ]
    )
    matched: list[tuple[str, int, dict[str, Any]]] = []
    for specialization, node in (ai_taxonomy.get("specializations") or {}).items():
        title_hits = _match_patterns(_normalized_text(inputs.get("title")), list(node.get("title_signals") or []))
        resp_hits = _match_patterns(_normalized_text(inputs.get("responsibilities")), list(node.get("responsibility_signals") or []))
        keyword_hits = _match_patterns(_normalized_text(inputs.get("top_keywords")), list(node.get("keyword_signals") or []))
        score = len(title_hits) * 3 + len(resp_hits) * 2 + len(keyword_hits)
        if score > 0:
            matched.append((specialization, score, node))

    if not matched:
        return AITaxonomyDoc(
            is_ai_job=False,
            primary_specialization="none",
            secondary_specializations=[],
            intensity="none",
            scope_tags=[],
            legacy_ai_categories=[],
            rationale="No AI specialization signals detected from title, responsibilities, qualifications, or keywords.",
        )

    matched.sort(key=lambda item: item[1], reverse=True)
    primary, primary_score, primary_node = matched[0]
    secondary = [name for name, _, _ in matched[1:3]]
    intensity = "adjacent"
    if primary_score >= 6:
        intensity = "core"
    elif primary_score >= 4:
        intensity = "significant"
    rationale = f"Matched AI specialization signals for {primary}: score={primary_score}."
    scope_tags: list[str] = []
    legacy_categories: list[str] = []
    for name, _, node in matched[:3]:
        for tag in node.get("scope_tags") or []:
            if tag not in scope_tags:
                scope_tags.append(tag)
        for category in node.get("legacy_categories") or []:
            if category not in legacy_categories:
                legacy_categories.append(category)
    return AITaxonomyDoc(
        is_ai_job=True,
        primary_specialization=_normalized_slug(primary),
        secondary_specializations=[_normalized_slug(item) for item in secondary if _normalized_slug(item) != "none"],
        intensity=intensity,
        scope_tags=scope_tags,
        legacy_ai_categories=legacy_categories,
        rationale=rationale,
    )


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
