"""Benchmark harness for extraction 4.1.1 runner-parity evaluation."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.layer1_4.claude_jd_extractor import ExtractedJDModel
from src.preenrich.types import StageContext, StepConfig

DEFAULT_THRESHOLDS = {
    "schema_validity_pass_rate": 1.0,
    "remote_policy_match_rate": 0.95,
    "responsibilities_item_f1_mean": 0.55,
    "qualifications_item_f1_mean": 0.60,
    "technical_skills_item_f1_mean": 0.65,
    "success_metrics_item_f1_mean": 0.40,
    "keyword_precision_at_10": 0.60,
    "keyword_recall_at_10": 0.60,
    "ideal_candidate_archetype_match_rate": 0.80,
}


def _normalize_text(value: str) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(value)).split())


def _normalize_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        norm = _normalize_text(value)
        if norm and norm not in seen:
            seen.add(norm)
            normalized.append(norm)
    return normalized


def item_f1(expected: list[str], actual: list[str]) -> float:
    expected_set = set(_normalize_list(expected))
    actual_set = set(_normalize_list(actual))
    if not expected_set and not actual_set:
        return 1.0
    if not expected_set or not actual_set:
        return 0.0
    overlap = len(expected_set & actual_set)
    precision = overlap / len(actual_set)
    recall = overlap / len(expected_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def precision_recall_at_k(expected: list[str], actual: list[str], *, k: int = 10) -> tuple[float, float]:
    expected_slice = set(_normalize_list(expected[:k]))
    actual_slice = set(_normalize_list(actual[:k]))
    if not expected_slice and not actual_slice:
        return 1.0, 1.0
    if not actual_slice:
        return 0.0, 0.0
    overlap = len(expected_slice & actual_slice)
    precision = overlap / len(actual_slice)
    recall = overlap / len(expected_slice) if expected_slice else 1.0
    return precision, recall


def validate_projection(payload: dict[str, Any]) -> tuple[bool, str]:
    try:
        ExtractedJDModel(**payload)
        return True, "ok"
    except Exception as exc:  # pragma: no cover - surfaced in report
        return False, str(exc)


def compare_extractions(runner: dict[str, Any], candidate: dict[str, Any], gold: dict[str, Any] | None = None) -> dict[str, Any]:
    schema_valid, schema_message = validate_projection(candidate)
    keyword_precision, keyword_recall = precision_recall_at_k(
        runner.get("top_keywords", []),
        candidate.get("top_keywords", []),
    )
    comparison = {
        "schema_valid": schema_valid,
        "schema_message": schema_message,
        "presence": {field: field in candidate and candidate.get(field) not in (None, "") for field in runner.keys()},
        "enum_matches": {
            "role_category": runner.get("role_category") == candidate.get("role_category"),
            "seniority_level": runner.get("seniority_level") == candidate.get("seniority_level"),
            "remote_policy": runner.get("remote_policy") == candidate.get("remote_policy"),
            "ideal_candidate_archetype": (runner.get("ideal_candidate_profile") or {}).get("archetype")
            == (candidate.get("ideal_candidate_profile") or {}).get("archetype"),
        },
        "numeric_deltas": {
            "years_experience_required": abs((runner.get("years_experience_required") or 0) - (candidate.get("years_experience_required") or 0)),
            "competency_weights": {
                key: abs((runner.get("competency_weights") or {}).get(key, 0) - (candidate.get("competency_weights") or {}).get(key, 0))
                for key in ("delivery", "process", "architecture", "leadership")
            },
        },
        "list_scores": {
            "responsibilities": item_f1(runner.get("responsibilities", []), candidate.get("responsibilities", [])),
            "qualifications": item_f1(runner.get("qualifications", []), candidate.get("qualifications", [])),
            "technical_skills": item_f1(runner.get("technical_skills", []), candidate.get("technical_skills", [])),
            "implied_pain_points": item_f1(runner.get("implied_pain_points", []), candidate.get("implied_pain_points", [])),
            "success_metrics": item_f1(runner.get("success_metrics", []), candidate.get("success_metrics", [])),
        },
        "keyword_scores": {
            "precision_at_10": keyword_precision,
            "recall_at_10": keyword_recall,
        },
    }
    if gold:
        comparison["gold_overrides"] = {
            key: {
                "expected": value,
                "candidate": candidate.get(key),
                "match": candidate.get(key) == value,
            }
            for key, value in gold.items()
        }
    return comparison


def summarize_report(report: list[dict[str, Any]]) -> dict[str, Any]:
    if not report:
        return {"count": 0, "passes_thresholds": False, "thresholds": DEFAULT_THRESHOLDS}
    schema_pass_rate = sum(1 for item in report if item["comparison"]["schema_valid"]) / len(report)
    remote_policy_match = sum(1 for item in report if item["comparison"]["enum_matches"]["remote_policy"]) / len(report)
    archetype_match = sum(1 for item in report if item["comparison"]["enum_matches"]["ideal_candidate_archetype"]) / len(report)
    list_metric = lambda name: statistics.mean(item["comparison"]["list_scores"][name] for item in report)
    keyword_precision = statistics.mean(item["comparison"]["keyword_scores"]["precision_at_10"] for item in report)
    keyword_recall = statistics.mean(item["comparison"]["keyword_scores"]["recall_at_10"] for item in report)
    summary = {
        "count": len(report),
        "schema_validity_pass_rate": schema_pass_rate,
        "remote_policy_match_rate": remote_policy_match,
        "responsibilities_item_f1_mean": list_metric("responsibilities"),
        "qualifications_item_f1_mean": list_metric("qualifications"),
        "technical_skills_item_f1_mean": list_metric("technical_skills"),
        "implied_pain_points_item_f1_mean": list_metric("implied_pain_points"),
        "success_metrics_item_f1_mean": list_metric("success_metrics"),
        "keyword_precision_at_10": keyword_precision,
        "keyword_recall_at_10": keyword_recall,
        "ideal_candidate_archetype_match_rate": archetype_match,
        "thresholds": DEFAULT_THRESHOLDS,
    }
    summary["passes_thresholds"] = all(summary[key] >= threshold for key, threshold in DEFAULT_THRESHOLDS.items())
    return summary


def _build_context(job: dict[str, Any], *, model: str) -> StageContext:
    return StageContext(
        job_doc={
            "_id": job.get("_id", "benchmark"),
            "job_id": job.get("job_id") or str(job.get("_id", "benchmark")),
            "title": job.get("title"),
            "company": job.get("company"),
            "description": job.get("description", ""),
            "location": job.get("location"),
            "processed_jd_sections": job.get("processed_jd_sections", []),
            "pre_enrichment": {"outputs": {}},
        },
        jd_checksum="sha256:benchmark-jd",
        company_checksum="sha256:benchmark-company",
        input_snapshot_id="sha256:benchmark-snapshot",
        attempt_number=1,
        config=StepConfig(
            provider="codex",
            primary_model=model,
            fallback_provider="none",
            fallback_model=None,
        ),
        shadow_mode=False,
    )


@contextmanager
def _override_jd_facts_codex_timeout(timeout_seconds: int | None):
    if not timeout_seconds:
        yield
        return
    import src.preenrich.stages.jd_facts as jd_facts_module
    from src.common.codex_cli import (
        CodexCLI as BaseCodexCLI,
        CodexResult,
        _extract_json_from_stdout,
    )
    from src.common.json_utils import parse_llm_json

    original = jd_facts_module.CodexCLI

    class BenchmarkCodexCLI(BaseCodexCLI):
        def __init__(self, model: str, timeout: int = timeout_seconds):
            super().__init__(model=model, timeout=timeout)

        def invoke(self, prompt: str, job_id: str, validate_json: bool = True) -> CodexResult:
            start_time = datetime.utcnow()
            cmd = [
                "codex",
                "exec",
                "--model", self.model,
                "--skip-git-repo-check",
                prompt,
            ]
            print(
                f"[codex] start job={job_id} model={self.model} timeout={self.timeout}s prompt_len={len(prompt)}",
                flush=True,
            )
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            heartbeat_seconds = 30
            last_heartbeat = time.monotonic()
            while True:
                returncode = proc.poll()
                if returncode is not None:
                    stdout, stderr = proc.communicate()
                    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                    if returncode != 0:
                        error_msg = (stderr.strip() or stdout.strip() or f"codex exec exited with code {returncode}")
                        print(
                            f"[codex] error job={job_id} model={self.model} duration_ms={duration_ms} error={error_msg}",
                            flush=True,
                        )
                        return CodexResult(
                            job_id=job_id,
                            success=False,
                            result=None,
                            raw_result=stdout or None,
                            error=error_msg,
                            model=self.model,
                            duration_ms=duration_ms,
                            invoked_at=start_time.isoformat(),
                        )
                    if not validate_json:
                        print(
                            f"[codex] complete job={job_id} model={self.model} duration_ms={duration_ms}",
                            flush=True,
                        )
                        return CodexResult(
                            job_id=job_id,
                            success=True,
                            result=None,
                            raw_result=stdout,
                            error=None,
                            model=self.model,
                            duration_ms=duration_ms,
                            invoked_at=start_time.isoformat(),
                        )
                    json_str = _extract_json_from_stdout(stdout)
                    if not json_str:
                        error_msg = "No JSON found in codex exec output"
                        print(
                            f"[codex] parse-miss job={job_id} model={self.model} duration_ms={duration_ms}",
                            flush=True,
                        )
                        return CodexResult(
                            job_id=job_id,
                            success=False,
                            result=None,
                            raw_result=stdout,
                            error=error_msg,
                            model=self.model,
                            duration_ms=duration_ms,
                            invoked_at=start_time.isoformat(),
                        )
                    try:
                        parsed = parse_llm_json(json_str)
                    except Exception as exc:
                        error_msg = f"JSON parse error: {exc}"
                        print(
                            f"[codex] parse-error job={job_id} model={self.model} duration_ms={duration_ms} error={error_msg}",
                            flush=True,
                        )
                        return CodexResult(
                            job_id=job_id,
                            success=False,
                            result=None,
                            raw_result=stdout,
                            error=error_msg,
                            model=self.model,
                            duration_ms=duration_ms,
                            invoked_at=start_time.isoformat(),
                        )
                    print(
                        f"[codex] complete job={job_id} model={self.model} duration_ms={duration_ms}",
                        flush=True,
                    )
                    return CodexResult(
                        job_id=job_id,
                        success=True,
                        result=parsed,
                        raw_result=None,
                        error=None,
                        model=self.model,
                        duration_ms=duration_ms,
                        invoked_at=start_time.isoformat(),
                    )

                elapsed = time.monotonic() - last_heartbeat
                total_elapsed = time.monotonic() - (time.monotonic() - elapsed)
                if elapsed >= heartbeat_seconds:
                    runtime = int((datetime.utcnow() - start_time).total_seconds())
                    print(
                        f"[codex] heartbeat job={job_id} model={self.model} runtime_s={runtime}",
                        flush=True,
                    )
                    last_heartbeat = time.monotonic()
                if (datetime.utcnow() - start_time).total_seconds() >= self.timeout:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                    error_msg = f"codex exec timeout after {self.timeout}s"
                    print(
                        f"[codex] timeout job={job_id} model={self.model} duration_ms={duration_ms}",
                        flush=True,
                    )
                    return CodexResult(
                        job_id=job_id,
                        success=False,
                        result=None,
                        raw_result=stdout or None,
                        error=error_msg,
                        model=self.model,
                        duration_ms=duration_ms,
                        invoked_at=start_time.isoformat(),
                    )
                time.sleep(1)

    jd_facts_module.CodexCLI = BenchmarkCodexCLI
    try:
        yield
    finally:
        jd_facts_module.CodexCLI = original


def run_benchmark(
    corpus: list[dict[str, Any]],
    *,
    model: str = "gpt-5.4-mini",
    use_fixture_candidate: bool = False,
    codex_timeout_seconds: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report: list[dict[str, Any]] = []
    with _override_jd_facts_codex_timeout(codex_timeout_seconds):
        for index, item in enumerate(corpus, start=1):
            runner = item["runner_extracted_jd"]
            job_id = item.get("job_id") or item.get("_id")
            print(f"[{index}/{len(corpus)}] benchmarking {job_id} :: {item.get('title')}", flush=True)
            error_message: str | None = None
            if use_fixture_candidate:
                candidate = item["candidate_extracted_jd"]
            else:
                try:
                    from src.preenrich.stages.jd_facts import JDFactsStage

                    stage = JDFactsStage()
                    result = stage.run(_build_context(item, model=model))
                    candidate = result.output.get("extracted_jd") or result.stage_output.get("extraction") or result.stage_output.get("merged_view") or {}
                except Exception as exc:  # pragma: no cover - exercised on real corpora
                    candidate = {}
                    error_message = str(exc)
                    print(f"[{index}/{len(corpus)}] error for {job_id}: {error_message}", flush=True)
            comparison = compare_extractions(runner, candidate, item.get("gold_reference"))
            report.append(
                {
                    "job_id": job_id,
                    "title": item.get("title"),
                    "company": item.get("company"),
                    "comparison": comparison,
                    "error": error_message,
                }
            )
    return report, summarize_report(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark extraction 4.1.1 against runner-era extracted_jd.")
    parser.add_argument("--corpus", required=True, help="Path to benchmark corpus JSON")
    parser.add_argument("--report-out", help="Optional output path for JSON report")
    parser.add_argument("--model", default="gpt-5.4-mini")
    parser.add_argument("--use-fixture-candidate", action="store_true", help="Use candidate_extracted_jd from the corpus instead of invoking jd_facts")
    parser.add_argument("--codex-timeout-seconds", type=int, default=None, help="Override Codex subprocess timeout for benchmark stage invocations")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    report, summary = run_benchmark(
        corpus,
        model=args.model,
        use_fixture_candidate=args.use_fixture_candidate,
        codex_timeout_seconds=args.codex_timeout_seconds,
    )
    payload = {"summary": summary, "report": report}
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if summary.get("passes_thresholds") else 1


if __name__ == "__main__":
    raise SystemExit(main())
