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

## 2026-04-22 Windows Bootstrap And VPS Recovery Notes

These notes were added after a real Windows-machine bootstrap plus interrupted
VPS stakeholder-validation recovery. Treat them as required procedure, not
tribal knowledge.

### Fresh Windows machine bootstrap

Do this in order:

1. Confirm the repo is present and on the expected branch/commit.
2. Fetch latest from GitHub before orienting deeply.
3. Verify the exact stage files and tests you expect are present before
   writing code.
4. Create `.venv` with a real Python install, not the Windows Store stub.
5. Install `requirements.txt`.
6. Run only the targeted tests for the checkpoint you are resuming.
7. Only then start live VPS validation.

Observed failures:
- PowerShell profile noise (`Microsoft.PowerShell_profile.ps1 cannot be loaded`)
  looked like repo breakage but was only local shell-policy noise.
- `python.exe` and `py.exe` resolved to Windows Store shims under
  `C:\\Users\\<user>\\AppData\\Local\\Microsoft\\WindowsApps\\`, which are not
  usable as the project interpreter.
- `git fetch`, `pip install`, and `ssh` all required outside-sandbox /
  network-enabled execution.

Corrections:
- On Windows automation, prefer shells that do not load the user PowerShell
  profile when you only need repo commands.
- Do not trust `python`, `py`, or `winget` aliases blindly on a fresh machine.
  Verify the real interpreter path first.
- For this repo, `python_requires >= 3.11`; if PATH is wrong, use the concrete
  interpreter path directly to create `.venv`.
- Treat GitHub sync, dependency install, and SSH as first-class bootstrap
  steps, not optional cleanup.

### Windows bootstrap checklist

Before any live run:
- verify `git fetch origin` succeeds
- verify `HEAD` and `origin/main` are what you think they are
- verify `.venv` exists
- verify `requirements.txt` installed cleanly
- verify the target checkpoint test file passes before touching the VPS

### VPS repo shape and sync rules

Observed on the live host:
- the active preenrich path was `/root/scout-cron`
- `/root/scout-cron` was a deployed working tree, not a Git checkout
- `/root/job-runner` also was not a Git checkout

Implication:
- do not assume `git pull` is the right recovery path on the VPS
- inspect the live files directly
- when the VPS tree is deployment-shaped instead of Git-shaped, sync only the
  necessary files with `scp` / `rsync` and then verify the exact lines landed

Required procedure:
- identify the actual live repo path first
- check whether it is a real Git checkout or a deployed copy
- if it is a deployed copy, verify code state by content, not by commit SHA
- after syncing targeted files, grep the specific fix markers on the VPS before
  rerunning the stage

### Remote Python launch rule

Observed failure:
- running stdin Python from `/root/scout-cron` imported the repo's top-level
  `types.py` instead of the stdlib `types` module
- this broke even read-only recovery scripts before stage code ran

Correction:
- when using `python -`, heredoc launchers, or temporary recovery scripts on
  the VPS, run them from `/tmp` (or another neutral directory), not from the
  repo root
- use the repo `.venv` interpreter explicitly, e.g.
  `/root/scout-cron/.venv/bin/python -u /tmp/<script>.py`

### Windows to SSH launcher rule

Observed failure:
- long inline SSH heredocs from Windows hit quoting collisions before the VPS
  stage even started

Correction:
- for non-trivial live-debug launchers from Windows, prefer:
  1. upload a temporary script to `/tmp`
  2. execute it with the repo `.venv`
  3. capture output to a named artifact path

Do not waste time debugging nested PowerShell + SSH + heredoc quoting when the
real task is stage validation.

### Detached VPS run rule

Observed failure:
- a detached `nohup ... &` launch from Windows was interrupted before it left a
  durable log or report
- follow-up inspection only showed `stdin is not a terminal`
- the result was ambiguity about whether the remote Python / Codex work was
  still alive

Correction:
- for detached VPS runs, use a wrapper script uploaded to `/tmp`, not an inline
  command
- invoke it with `ssh -tt` so the remote launch path gets a real TTY even if
  the actual Python/Codex subprocesses later run detached
- redirect all stdout/stderr to a named `/tmp/<run>.out`
- always write a named `/tmp/<run>.json` report artifact
- always truncate/create the named log before launch so an empty file is a real
  signal, not leftover state from an older run
- do not rely on inline Windows quoting like `echo \$! > /tmp/<run>.pid`; it
  can write the literal string `$!` instead of the remote background PID
- use the repo helper `scripts/ops/launch_vps_detached.py`, which uploads a
  real remote wrapper, captures `pid=$!` on the VPS, writes a numeric pid file,
  returns the launched PID, and now fails fast if the detached process dies
  before the initial startup poll window
- for long Python or Codex-backed runners, plain detached `nohup ... &` was
  still not durable enough on the current VPS path; the helper now launches
  with `setsid nohup ... &` so the runner survives SSH session teardown and
  keeps writing the named `/tmp/<run>.out`
- do not keep a giant streamed SSH session open for long Codex-backed runs;
  launch once, then poll in short SSH calls only

Required strict detach-poll pattern:
1. launch with:
   - `python scripts/ops/launch_vps_detached.py --host <host> --launcher-name <run> --log-path /tmp/<run>.out --pid-path /tmp/<run>.pid --startup-check-seconds 5 -- <command...>`
2. run an initial startup poll within 5-15 seconds:
   - `cat /tmp/<run>.pid`
   - `ps -p <pid> -o pid,etime,cmd --no-headers`
   - `tail -n 80 /tmp/<run>.out`
3. if the PID is gone or the log is still empty, stop and inspect before
   relaunching
4. only after the startup poll passes, switch to periodic polls every 60-120
   seconds:
   - `ps -p <pid> -o pid,etime,cmd --no-headers`
   - `ls -l /tmp/<run>.json`
   - `grep -n 'stage_start\\|stage_complete\\|stage_failed\\|runner_complete\\|runner_failed' /tmp/<run>.out | tail -n 60`
   - `tail -n 120 /tmp/<run>.out`
5. when the PID exits, inspect the final log and report artifact before
   deciding whether the run succeeded, failed, or needs a foreground repro

Negative rules:
- do not watch a long multi-stage run through one continuous SSH stream
- do not relaunch a detached run until the initial startup poll has shown why
  the previous launch died
- do not rerun a full chain when a single-stage resume path exists
- do not debug nested Windows quoting when the helper can upload a real wrapper

Required pattern:
- launch with:
  - `python scripts/ops/launch_vps_detached.py --host <host> --launcher-name <run> --log-path /tmp/<run>.out --pid-path /tmp/<run>.pid --startup-check-seconds 5 -- <command...>`
- upload `/tmp/<runner>.py` first if the detached command depends on a new temp
  runner script
- poll separately; do not keep one giant streamed SSH session open just to
  watch Codex stderr for long multi-stage runs

### Artifact recovery rule

Observed failure:
- the target job did not expose `pre_enrichment.outputs.research_enrichment`
  on the live document
- it only exposed a legacy `pre_enrichment.stages` shape

Correction:
- when recovering a fast-path stage rerun, inspect both:
  - `pre_enrichment.outputs`
  - `pre_enrichment.stages`
- do not declare the fast path unavailable until both shapes and any
  collection-backed artifact refs have been checked

### Correct develop/test-run order for recovery sessions

Use this order when resuming an interrupted stage validation:

1. verify local repo state and expected checkpoint files
2. run the minimum local targeted tests
3. verify VPS connectivity and live code path
4. determine whether the VPS path is Git-backed or deployment-backed
5. recover the upstream artifact from the live document, legacy stage state,
   or collection-backed artifact ref
6. rerun only the target stage if the upstream artifact is recoverable
7. rerun the full chain only if the fast path is genuinely unavailable

This order is mandatory for interrupted live-validation work. It avoids
re-solving already-solved work and keeps operator attention on the real
blocker.

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
