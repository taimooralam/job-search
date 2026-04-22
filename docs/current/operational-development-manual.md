# Operational Development Manual

This document is the required procedure for long-running local development and live-debug sessions in this repo.

Use it when running:
- live preenrich stage debugging
- Codex CLI stage smoke tests
- outside-sandbox validation runs
- any session expected to run for more than a few seconds

## Core Rule

Do not run blind.

Long-running local or live-debug sessions must be:
- outside the sandbox when they need real MongoDB, Codex, or networked tools
- unbuffered
- heartbeat-enabled
- verbose
- launched from the repo root
- run from `.venv`
- configured with the correct Mongo env key: `MONGODB_URI`
- isolated from repo context by default for pure stage runs

## Required Launch Defaults

For live stage debugging:
- use `.venv`
- use `python -u`
- load `.env` from Python, not `source .env`
- use `dotenv_values(Path.cwd() / ".env")` or equivalent explicit path loading
- use `MONGODB_URI`, not `MONGO_URI`, unless a specific script explicitly requires otherwise
- do not rely on default timeouts
- use no timeout by default for error discovery and long live-debug sessions
- only set a timeout when you are explicitly testing timeout behavior or need a bounded experiment
- print stage heartbeats every 15-30s
- enable DEBUG logging for the launcher and subprocess monitor
- stream inner Codex stdout/stderr live
- log spawned Codex PID
- make repo context opt-in, not default
- default Codex subprocess `cwd` to an isolated temp directory for:
  - `jd_facts`
  - `classification`
  - `application_surface`
  - `research_enrichment`
- only allow repo-context execution when the task explicitly needs local code/files
- when production, VPS, or a Codex skill needs a specific workdir, set:
  - `PREENRICH_CODEX_WORKDIR_JD_FACTS`
  - `PREENRICH_CODEX_WORKDIR_CLASSIFICATION`
  - `PREENRICH_CODEX_WORKDIR_APPLICATION_SURFACE`
  - `PREENRICH_CODEX_WORKDIR_RESEARCH_ENRICHMENT`
  instead of relying on inherited repo cwd

## Why `.env` Must Be Loaded From Python

Do not rely on `source .env`.

Observed failure:
- repo `.env` contains shell-incompatible content
- `source .env` failed with parse errors

Correct pattern:

```python
from pathlib import Path
from dotenv import dotenv_values
import os

values = dotenv_values(Path.cwd() / ".env")
for key, value in values.items():
    if value is not None and key not in os.environ:
        os.environ[key] = value
```

Do not use `load_dotenv()` auto-discovery from stdin-driven heredoc runs.

Observed failure:
- `load_dotenv()` called without explicit path raised an assertion failure under stdin execution

## Correct Mongo Variable

Use:
- `MONGODB_URI`

Observed failure:
- multiple debug launches used `MONGO_URI`
- the repo’s worker and preenrich code actually use `MONGODB_URI`
- this caused runs to fail before any stage started

## Correct Python Environment

Always activate:

```bash
source .venv/bin/activate
```

Then launch unbuffered:

```bash
python -u ...
```

Do not use buffered Python for long sessions where stage progress matters.

## Outside-Sandbox Requirement

If the run needs:
- real MongoDB access
- real Codex execution
- live web research

run it outside the sandbox.

Observed failure:
- process introspection and real external dependencies were not reliably visible or reachable inside sandbox-only runs

## Required Observability

Every long-running launcher must provide:

1. outer heartbeat
- print current stage
- print elapsed seconds
- print UTC timestamp

2. inner Codex subprocess telemetry
- spawned PID
- alive/dead state
- stdout bytes received
- stderr bytes received
- last output age

3. live stdout/stderr streaming
- do not wait until subprocess exit to inspect Codex output

4. stage boundary logging
- explicit `[STAGE_START]`
- explicit stage completion summary
- final status summary

## Current Proven Launcher Pattern

The live-debug launcher should:
- start from repo root
- activate `.venv`
- load `.env` from Python with explicit path
- construct the real `StageContext`
- use worker-compatible checksums and snapshot ids
- use `get_stage_step_config(...)` where available so stage defaults like isolated Codex workdir are preserved
- run with `python -u`
- emit heartbeats while stages run

Required context construction pattern:

```python
from src.preenrich.checksums import company_checksum, jd_checksum
from src.preenrich.types import StageContext, StepConfig

description = job.get("description", "") or job.get("job_description", "") or ""
pre = job.get("pre_enrichment") or {}
jd_cs = str(pre.get("jd_checksum") or jd_checksum(description))
company_cs = str(pre.get("company_checksum") or company_checksum(job.get("company"), job.get("company_domain")))
snapshot_id = str(pre.get("input_snapshot_id") or ("sha256:" + hashlib.sha256(description.encode("utf-8")).hexdigest()))
attempt_number = int(pre.get("attempt_number", 0) or 0) + 1

ctx = StageContext(
    job_doc=job,
    jd_checksum=jd_cs,
    company_checksum=company_cs,
    input_snapshot_id=snapshot_id,
    attempt_number=attempt_number,
    config=StepConfig(),
    shadow_mode=False,
)
```

## Observed Failures And Corrections

### Failure 1: Buffered silent runs

Observed:
- long session appeared stuck
- no stage output
- no heartbeat
- no way to distinguish dead process from active subprocess wait

Correction:
- use `python -u`
- add launcher heartbeats
- stream inner Codex stdout/stderr

### Failure 2: Non-TTY sessions could not be interrupted cleanly

Observed:
- `write_stdin(..., "\\u0003")` failed because stdin was closed

Correction:
- prefer TTY-backed observable runs for long debug sessions
- when killing stale non-TTY sessions, inspect and stop OS processes directly outside sandbox

### Failure 3: `source .env` parse failure

Observed:
- shell parse error near `&`

Correction:
- load `.env` in Python using explicit dotenv parsing

### Failure 4: Wrong Mongo variable

Observed:
- `KeyError: 'MONGO_URI'`

Correction:
- use `MONGODB_URI`

### Failure 5: `load_dotenv()` auto-discovery failure in heredoc execution

Observed:
- assertion failure inside dotenv auto-discovery

Correction:
- pass explicit path with `dotenv_values(Path.cwd() / ".env")`

### Failure 6: Wrong `StageContext` constructor

Observed:
- launcher tried `StageContext(job_id=..., ...)`
- actual dataclass requires worker-style checksum/snapshot fields

Correction:
- construct `StageContext` exactly as worker code does

### Failure 7: Launcher called non-existent stage helper

Observed:
- `JDFactsStage` had no `get_config()`

Correction:
- call `stage.run(ctx)` directly unless the stage actually exposes config accessors

### Failure 8: Blindness inside inner Codex subprocess

Observed:
- wrapper process looked alive, but there was no proof the inner model call was progressing

Correction:
- use monitored `Popen`
- log PID
- stream stdout/stderr
- emit subprocess heartbeat

### Failure 9: Codex spent time exploring the repo mid-run

Observed from live `jd_facts` stderr:
- Codex inspected repo files like `blueprint_prompts.py`, `jd_facts.py`, and tests while trying to infer output expectations
- this increased latency and made the run appear stuck

Correction:
- watch stderr for tool wandering
- tighten prompts so schema/output contract is fully explicit
- if a stage is expected to be strictly extraction-only, inspect whether the Codex invocation mode or prompt still invites repo exploration

### Failure 10: Repo cwd was inherited by `codex exec`

Observed:
- `codex exec` inherited the repo working directory
- pure JSON stages like `jd_facts` and `classification` explored tests and source files instead of returning the stage payload directly

Correction:
- add `codex_workdir` / `allow_repo_context` to stage config
- default 4.1 stages to an isolated temp cwd
- only opt into repo context deliberately

Required policy:
- repo context is opt-in, not default, for preenrich stage runs
- production/VPS/Codex-skill launches must preserve this policy unless there is a deliberate reason to override it with a stage-specific `PREENRICH_CODEX_WORKDIR_<STAGE>`

## Minimum Live-Debug Checklist

Before launching:
- confirm outside-sandbox execution
- confirm `.venv` is active
- confirm `.env` is loaded explicitly from Python
- confirm `MONGODB_URI` is present
- confirm `python -u`
- confirm launcher heartbeat enabled
- confirm Codex subprocess monitoring enabled
- confirm timeout policy is explicit:
  - unset / empty / `0` means no timeout
  - positive integer means intentional timeout for that run

During run:
- verify stage start message appears
- verify Codex PID is logged
- verify stdout/stderr bytes increase or last output age remains reasonable
- verify Mongo heartbeat remains healthy

If a run looks stuck:
- check whether stage heartbeat still advances
- check whether Codex PID is alive
- check `last_output_age_s`
- inspect stderr for repo exploration or tool wandering
- do not assume silence means success

## Recommended Default For Future Debug Sessions

Use outside-sandbox, unbuffered, TTY-backed runs with:
- explicit dotenv loading
- `MONGODB_URI`
- `.venv`
- launcher heartbeats
- monitored `Popen`
- live stderr/stdout streaming

This is the default operating procedure for long preenrich debugging sessions.
