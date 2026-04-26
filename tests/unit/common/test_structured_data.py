"""Tests for the shared structured-data loader (4.3 soft YAML migration)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.structured_data import (
    PREFERRED_EXTENSIONS,
    UnsupportedStructuredFileError,
    discover_preferred_files,
    dump_yaml_file,
    load_preferred,
    load_structured_file,
    resolve_preferred_path,
)


def test_load_structured_file_reads_json(tmp_path: Path) -> None:
    target = tmp_path / "payload.json"
    target.write_text(json.dumps({"a": 1, "b": [2, 3]}), encoding="utf-8")
    assert load_structured_file(target) == {"a": 1, "b": [2, 3]}


def test_load_structured_file_reads_yaml(tmp_path: Path) -> None:
    target = tmp_path / "payload.yml"
    target.write_text("a: 1\nb:\n- 2\n- 3\n", encoding="utf-8")
    assert load_structured_file(target) == {"a": 1, "b": [2, 3]}


def test_load_structured_file_reads_yaml_long_extension(tmp_path: Path) -> None:
    target = tmp_path / "payload.yaml"
    target.write_text("k: v\n", encoding="utf-8")
    assert load_structured_file(target) == {"k": "v"}


def test_load_structured_file_rejects_unknown_extension(tmp_path: Path) -> None:
    target = tmp_path / "payload.txt"
    target.write_text("k: v\n", encoding="utf-8")
    with pytest.raises(UnsupportedStructuredFileError):
        load_structured_file(target)


def test_resolve_preferred_path_prefers_yml_over_json(tmp_path: Path) -> None:
    (tmp_path / "thing.json").write_text("{}", encoding="utf-8")
    (tmp_path / "thing.yml").write_text("k: 1\n", encoding="utf-8")
    resolved = resolve_preferred_path(tmp_path / "thing.json")
    assert resolved.suffix == ".yml"


def test_resolve_preferred_path_prefers_yml_over_yaml(tmp_path: Path) -> None:
    (tmp_path / "thing.yaml").write_text("k: 2\n", encoding="utf-8")
    (tmp_path / "thing.yml").write_text("k: 1\n", encoding="utf-8")
    resolved = resolve_preferred_path(tmp_path / "thing.json")
    assert resolved.suffix == ".yml"


def test_resolve_preferred_path_falls_back_to_yaml(tmp_path: Path) -> None:
    (tmp_path / "thing.yaml").write_text("k: 1\n", encoding="utf-8")
    resolved = resolve_preferred_path(tmp_path / "thing.json")
    assert resolved.suffix == ".yaml"


def test_resolve_preferred_path_falls_back_to_json(tmp_path: Path) -> None:
    (tmp_path / "thing.json").write_text("{}", encoding="utf-8")
    resolved = resolve_preferred_path(tmp_path / "thing.json")
    assert resolved.suffix == ".json"


def test_resolve_preferred_path_returns_input_when_nothing_exists(tmp_path: Path) -> None:
    base = tmp_path / "thing.json"
    resolved = resolve_preferred_path(base)
    assert resolved == base


def test_load_preferred_uses_yaml_when_present(tmp_path: Path) -> None:
    (tmp_path / "thing.json").write_text(json.dumps({"k": "json"}), encoding="utf-8")
    (tmp_path / "thing.yml").write_text("k: yaml\n", encoding="utf-8")
    assert load_preferred(tmp_path / "thing.json") == {"k": "yaml"}


def test_load_preferred_falls_back_to_json(tmp_path: Path) -> None:
    (tmp_path / "thing.json").write_text(json.dumps({"k": "json"}), encoding="utf-8")
    assert load_preferred(tmp_path / "thing.json") == {"k": "json"}


def test_dump_yaml_file_round_trip(tmp_path: Path) -> None:
    payload = {"name": "Taimoor", "values": [1, 2, 3], "nested": {"x": True}}
    target = tmp_path / "out.yml"
    dump_yaml_file(target, payload)
    assert load_structured_file(target) == payload
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert "{" not in text  # block style only
    assert "*" not in text  # no anchors


def test_dump_yaml_file_preserves_key_order(tmp_path: Path) -> None:
    payload = {"z": 1, "m": 2, "a": 3}
    target = tmp_path / "ordered.yml"
    dump_yaml_file(target, payload)
    text = target.read_text(encoding="utf-8")
    assert text.index("z:") < text.index("m:") < text.index("a:")


def test_discover_preferred_files_dedupes_and_prefers_yaml(tmp_path: Path) -> None:
    (tmp_path / "a_skills.json").write_text("{}", encoding="utf-8")
    (tmp_path / "a_skills.yml").write_text("k: 1\n", encoding="utf-8")
    (tmp_path / "b_skills.json").write_text("{}", encoding="utf-8")
    (tmp_path / "c_skills.yaml").write_text("z: 1\n", encoding="utf-8")
    found = discover_preferred_files(tmp_path, "_skills")
    names = [p.name for p in found]
    assert names == ["a_skills.yml", "b_skills.json", "c_skills.yaml"]


def test_discover_preferred_files_ignores_non_matching_stems(tmp_path: Path) -> None:
    (tmp_path / "a_skills.yml").write_text("k: 1\n", encoding="utf-8")
    (tmp_path / "skills_extra.yml").write_text("k: 1\n", encoding="utf-8")
    (tmp_path / "other.yml").write_text("k: 1\n", encoding="utf-8")
    found = discover_preferred_files(tmp_path, "_skills")
    assert [p.name for p in found] == ["a_skills.yml"]


def test_discover_preferred_files_missing_directory_returns_empty(tmp_path: Path) -> None:
    assert discover_preferred_files(tmp_path / "missing", "_skills") == []


def test_preferred_extensions_order() -> None:
    assert PREFERRED_EXTENSIONS == (".yml", ".yaml", ".json")
