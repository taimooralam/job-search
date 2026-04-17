"""
Checksum utilities for pre-enrichment.

Provides deterministic, normalized checksums for JD text and company identity.
Used to detect staleness and drive transitive invalidation (§2.6).

All checksums are prefixed with "sha256:" to make the algorithm explicit.
"""

import hashlib
import re
import unicodedata
from typing import Optional


def normalize_jd(text: str) -> str:
    """
    Normalize JD text for stable checksum computation.

    Applies the following transformations:
    1. Unicode NFC normalization
    2. Strip leading/trailing whitespace
    3. Collapse all internal whitespace runs to single spaces
    4. Lowercase (so minor casing variations don't invalidate stages)

    Args:
        text: Raw JD text

    Returns:
        Normalized JD string
    """
    if not text:
        return ""
    # NFC normalization handles composed vs decomposed characters
    normalized = unicodedata.normalize("NFC", text)
    # Strip and collapse whitespace
    normalized = normalized.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def jd_checksum(text: str) -> str:
    """
    Compute a stable checksum for a JD text.

    Normalizes the text before hashing so minor formatting changes
    (trailing spaces, double newlines) do not trigger re-enrichment.

    Args:
        text: Raw JD text

    Returns:
        Checksum string in the form "sha256:<64-char-hex>"
    """
    normalized = normalize_jd(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def company_checksum(name: Optional[str], domain: Optional[str]) -> str:
    """
    Compute a stable checksum for a company identity.

    Case-insensitive and whitespace-tolerant so that "OpenAI" and "openai"
    produce the same checksum. Domain is optional; passing None is the same
    as passing an empty string.

    Args:
        name: Company name (e.g. "Anthropic")
        domain: Company domain (e.g. "anthropic.com") or None

    Returns:
        Checksum string in the form "sha256:<64-char-hex>"
    """
    name_norm = (name or "").strip().lower()
    domain_norm = (domain or "").strip().lower()
    raw = f"{name_norm}|{domain_norm}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
