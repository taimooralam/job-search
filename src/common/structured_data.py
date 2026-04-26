"""Shared structured-source loader for the 4.3 soft JSON->YAML migration.

Policy (see plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md
and AGENTS.md):

- Human-authored source files in the migrated subset are authored as YAML
  when possible. Codex / preenrich / manual-review readers should prefer
  ``.yml`` (or ``.yaml``) when present and fall back to ``.json``.
- Legacy runner contracts, deterministic machine artifacts, validator
  reports, canonical-hash payloads, and external workflow JSON remain JSON
  only and must not flow through these helpers as a substitute for
  ``json.dumps`` / ``canonical_json``.

This module deliberately stays small and dependency-light. It only uses
``yaml.safe_load`` / ``yaml.safe_dump``, UTF-8 text I/O, and standard
library types. It does not implement merging, anchors, custom tags, or
schema validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

# Extension preference order: YAML wins over JSON, .yml wins over .yaml.
PREFERRED_EXTENSIONS: tuple[str, ...] = (".yml", ".yaml", ".json")


class UnsupportedStructuredFileError(ValueError):
    """Raised when a path does not have a recognized structured-data suffix."""


def _suffix(path: Path) -> str:
    return path.suffix.lower()


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_structured_file(path: Path) -> Any:
    """Load a JSON or YAML file based on its extension.

    Returns the parsed payload (typically dict or list). Raises
    :class:`UnsupportedStructuredFileError` for unknown extensions.
    """
    suffix = _suffix(path)
    if suffix in (".yml", ".yaml"):
        return _load_yaml(path)
    if suffix == ".json":
        return _load_json(path)
    raise UnsupportedStructuredFileError(
        f"Unsupported structured-data extension for {path!s}: {suffix!r}"
    )


def dump_yaml_file(path: Path, payload: Any) -> None:
    """Write ``payload`` to ``path`` in stable, block-style YAML.

    Uses UTF-8, preserves key insertion order (``sort_keys=False``), no
    flow style, no anchors, with a trailing newline.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        payload,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=1000,
    )
    if not text.endswith("\n"):
        text += "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def resolve_preferred_path(base_path: Path) -> Path:
    """Return the preferred existing variant of ``base_path``.

    For an input like ``foo.json`` (or any sibling stem), look for
    ``foo.yml`` first, then ``foo.yaml``, then ``foo.json``. If none
    exist, return the input ``base_path`` unchanged so callers can still
    surface a useful "missing file" error.
    """
    stem = base_path.with_suffix("")
    for ext in PREFERRED_EXTENSIONS:
        candidate = stem.with_suffix(ext)
        if candidate.exists():
            return candidate
    return base_path


def load_preferred(base_path: Path) -> Any:
    """Resolve YAML-first then load the structured payload."""
    return load_structured_file(resolve_preferred_path(base_path))


def discover_preferred_files(
    directory: Path,
    suffix_pattern: str,
    *,
    extensions: Iterable[str] = PREFERRED_EXTENSIONS,
) -> list[Path]:
    """Discover one preferred file per logical asset under ``directory``.

    ``suffix_pattern`` is the trailing portion of the stem that identifies
    the asset family (for example ``"_skills"`` matches
    ``commander4_skills.{yml,yaml,json}``). The function returns one path
    per stem, choosing the first available extension from ``extensions``.

    The result is sorted by stem name for deterministic ordering.
    """
    if not directory.exists():
        return []

    seen: dict[str, Path] = {}
    pattern_lc = suffix_pattern.lower()
    for ext in extensions:
        for candidate in directory.glob(f"*{suffix_pattern}{ext}"):
            stem = candidate.stem
            if stem.lower().endswith(pattern_lc) and stem not in seen:
                seen[stem] = candidate

    return [seen[stem] for stem in sorted(seen)]


def find_first_existing(*candidates: Path) -> Optional[Path]:
    """Return the first existing path from ``candidates``, or ``None``."""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


__all__ = [
    "PREFERRED_EXTENSIONS",
    "UnsupportedStructuredFileError",
    "discover_preferred_files",
    "dump_yaml_file",
    "find_first_existing",
    "load_preferred",
    "load_structured_file",
    "resolve_preferred_path",
]
