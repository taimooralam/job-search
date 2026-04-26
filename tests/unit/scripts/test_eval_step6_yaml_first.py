"""YAML-first / JSON-fallback behavior for scripts/eval_step6_baselines.

Covers the soft 4.3 JSON->YAML migration: the eval baseline generator must
prefer YAML source files for ``role_metadata``, ``role_skills_taxonomy``,
and project ``*_skills`` discovery, while still working correctly when
only the legacy JSON files are present.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write_yaml(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_role_metadata_prefers_yaml_when_present(monkeypatch, tmp_path):
    master_cv = tmp_path / "data" / "master-cv"
    (master_cv / "projects").mkdir(parents=True)
    (master_cv / "roles").mkdir(parents=True)
    _write_json(master_cv / "role_metadata.json", {"candidate": {"name": "JSON"}})
    _write_yaml(master_cv / "role_metadata.yml", "candidate:\n  name: YAML\n")
    _write_json(master_cv / "role_skills_taxonomy.json", {"version": "1"})

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("scripts.eval_step6_baselines", None)
    module = importlib.import_module("scripts.eval_step6_baselines")

    assert module.ROLE_METADATA_PATH.suffix == ".yml"
    payload = module.maybe_load_json(module.ROLE_METADATA_PATH)
    assert payload["candidate"]["name"] == "YAML"


def test_role_metadata_falls_back_to_json(monkeypatch, tmp_path):
    master_cv = tmp_path / "data" / "master-cv"
    (master_cv / "projects").mkdir(parents=True)
    (master_cv / "roles").mkdir(parents=True)
    _write_json(master_cv / "role_metadata.json", {"candidate": {"name": "JSON"}})
    _write_json(master_cv / "role_skills_taxonomy.json", {"version": "1"})

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("scripts.eval_step6_baselines", None)
    module = importlib.import_module("scripts.eval_step6_baselines")

    assert module.ROLE_METADATA_PATH.suffix == ".json"
    payload = module.maybe_load_json(module.ROLE_METADATA_PATH)
    assert payload["candidate"]["name"] == "JSON"


def test_project_skills_discovery_prefers_yaml_and_dedupes(monkeypatch, tmp_path):
    master_cv = tmp_path / "data" / "master-cv"
    projects = master_cv / "projects"
    projects.mkdir(parents=True)
    (master_cv / "roles").mkdir(parents=True)

    _write_json(master_cv / "role_metadata.json", {"candidate": {}})
    _write_json(master_cv / "role_skills_taxonomy.json", {"version": "1"})

    _write_json(projects / "commander4_skills.json", {"verified_skills": ["json"]})
    _write_yaml(projects / "commander4_skills.yml", "verified_skills:\n- yaml\n")
    _write_json(projects / "lantern_skills.json", {"verified_skills": ["json-only"]})

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("scripts.eval_step6_baselines", None)
    module = importlib.import_module("scripts.eval_step6_baselines")

    from src.common.structured_data import discover_preferred_files

    found = discover_preferred_files(module.PROJECTS_DIR, "_skills")
    names = sorted(p.name for p in found)
    assert names == ["commander4_skills.yml", "lantern_skills.json"]
    # Confirm dedup: commander4 appears exactly once.
    assert sum(1 for p in found if p.stem == "commander4_skills") == 1


def test_parse_skill_json_handles_yaml_with_refs(monkeypatch, tmp_path):
    master_cv = tmp_path / "data" / "master-cv"
    projects = master_cv / "projects"
    projects.mkdir(parents=True)
    (master_cv / "roles").mkdir(parents=True)
    _write_json(master_cv / "role_metadata.json", {"candidate": {}})
    _write_json(master_cv / "role_skills_taxonomy.json", {"version": "1"})

    yaml_path = projects / "commander4_skills.yml"
    _write_yaml(
        yaml_path,
        "verified_skills:\n- TypeScript\nverified_competencies:\n- Hybrid Search\n",
    )

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("scripts.eval_step6_baselines", None)
    module = importlib.import_module("scripts.eval_step6_baselines")

    payload = module.parse_skill_json(yaml_path)
    assert payload["_file"].endswith("commander4_skills.yml")
    assert payload["verified_skills"] == ["TypeScript"]
    assert payload["_refs"]["verified_skills"], "verified_skills must have a YAML line ref"
    assert payload["_refs"]["verified_competencies"], "verified_competencies must have a YAML line ref"


def test_find_key_line_ref_works_for_yaml_and_json(monkeypatch, tmp_path):
    master_cv = tmp_path / "data" / "master-cv"
    (master_cv / "projects").mkdir(parents=True)
    (master_cv / "roles").mkdir(parents=True)
    _write_json(master_cv / "role_metadata.json", {"candidate": {"title_base": "X"}})
    _write_json(master_cv / "role_skills_taxonomy.json", {"version": "1"})

    monkeypatch.chdir(tmp_path)
    sys.modules.pop("scripts.eval_step6_baselines", None)
    module = importlib.import_module("scripts.eval_step6_baselines")

    json_ref = module.find_key_line_ref(master_cv / "role_metadata.json", "title_base", 1)
    assert json_ref.endswith("role_metadata.json:3") or "role_metadata.json:" in json_ref

    yaml_path = master_cv / "role_metadata.yml"
    _write_yaml(yaml_path, "candidate:\n  title_base: hello\n")
    yaml_ref = module.find_key_line_ref(yaml_path, "title_base", 1)
    assert "role_metadata.yml:" in yaml_ref
