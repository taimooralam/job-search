from __future__ import annotations

import json
import sys
from pathlib import Path

import scripts.vps_run_presentation_contract as runner
from src.preenrich.types import StageResult

FIXTURE_PATH = Path("data/presentation_contract_fixtures/low_ai_adjacent_full_upstream.json")


class _FakeSpan:
    def __init__(self) -> None:
        self.output = None

    def complete(self, *, output=None) -> None:
        self.output = output


class _FakeSession:
    def __init__(self, *args, **kwargs) -> None:
        self.trace_id = "trace:test"
        self.trace_url = "https://langfuse.example/trace:test"
        self.completed = None

    def start_stage_span(self, stage_name: str, metadata: dict) -> _FakeSpan:
        self.stage_name = stage_name
        self.metadata = metadata
        return _FakeSpan()

    def complete(self, output=None) -> None:
        self.completed = output


class _FakeThread:
    def __init__(self, *args, **kwargs) -> None:
        return None

    def start(self) -> None:
        return None


class _FakePresentationContractStage:
    def run(self, ctx) -> StageResult:
        return StageResult(
            stage_output={
                "status": "completed",
                "ideal_candidate_presentation_model": {
                    "status": "completed",
                    "acceptable_titles": ["Principal Platform Architect"],
                    "proof_ladder": [{"proof_category": "architecture"}],
                    "defaults_applied": [],
                },
                "experience_dimension_weights": {
                    "status": "completed",
                    "overall_weights": {
                        "architecture_system_design": 40,
                        "business_impact": 35,
                        "ai_ml_depth": 15,
                        "hands_on_implementation": 10,
                    },
                    "stakeholder_variant_weights": {
                        "recruiter": {
                            "architecture_system_design": 40,
                            "business_impact": 35,
                            "ai_ml_depth": 15,
                            "hands_on_implementation": 10,
                        }
                    },
                },
                "truth_constrained_emphasis_rules": {
                    "status": "completed",
                    "global_rules": [{"rule_id": "title_guard"}],
                    "section_rules": {"experience": [{"rule_id": "credibility_marker_experience"}]},
                    "allowed_if_evidenced": [{"rule_id": "ai_claims_ai"}],
                    "downgrade_rules": [{"rule_id": "stakeholder_soften"}],
                    "omit_rules": [{"rule_id": "metric_guard"}],
                    "forbidden_claim_patterns": [{}, {}],
                    "credibility_ladder_rules": [{}],
                    "topic_coverage": [
                        {"topic_family": "title_inflation", "rule_count": 1},
                        {"topic_family": "ai_claims", "rule_count": 1},
                    ],
                },
                "trace_ref": {"trace_url": "https://langfuse.example/trace:test"},
            },
            provider_used="codex",
            model_used="gpt-5.4",
        )


def test_vps_runner_supports_fixture_mode_without_mongo(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "run_report.json"
    artifact_dir = tmp_path / "artifacts"

    monkeypatch.setattr(runner, "_load_env", lambda: None)
    monkeypatch.setattr(runner, "_configure_flags", lambda: None)
    monkeypatch.setattr(runner, "validate_blueprint_feature_flags", lambda: None)
    monkeypatch.setattr(runner, "PreenrichTracingSession", _FakeSession)
    monkeypatch.setattr(runner, "PresentationContractStage", lambda: _FakePresentationContractStage())
    monkeypatch.setattr(runner.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        runner,
        "MongoClient",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fixture mode should not open Mongo")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vps_run_presentation_contract.py",
            "--fixture",
            str(FIXTURE_PATH),
            "--report-out",
            str(report_path),
            "--artifact-dir",
            str(artifact_dir),
        ],
    )

    exit_code = runner.main()

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["source"]["kind"] == "fixture"
    assert report["summary"]["job_id"] == "fixture-low-ai-adjacent-platform-architect"
    assert report["stages"][0]["output_preview"]["emphasis_rules_status"] == "completed"
    subdocument = json.loads((artifact_dir / "subdocument.json").read_text(encoding="utf-8"))
    assert subdocument["status"] == "completed"
    assert len(subdocument["forbidden_claim_patterns"]) == 2
    assert (artifact_dir / "parent_stage_output.json").exists()
    assert "PRESENTATION_CONTRACT_RUN_OK" in (artifact_dir / "run.log").read_text(encoding="utf-8")
