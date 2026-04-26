# Iteration 4.3.9 Plan: Shared Validator Framework And Determinism Harness

Author: Codex planning pass on 2026-04-25
Parent plans:
- `plans/iteration-4.3-candidate-evidence-assembly-grading-and-publishing.md`
- `plans/iteration-4.3.1-master-cv-blueprint-and-evidence-taxonomy.md`
- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
- `plans/iteration-4.3.3-cv-pattern-selection-and-evidence-mapping.md`
- `plans/iteration-4.3.4-multi-draft-cv-assembly.md`
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
- `plans/iteration-4.3.6-publisher-renderer-and-remote-delivery-integration.md`
- `plans/iteration-4.3.7-dossier-and-mongodb-state-contract.md`
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md`

Status: new peer plan; introduces a shared validator framework consumed by
4.3.2, 4.3.3, 4.3.4, 4.3.5, 4.3.6, and 4.3.7. Owns no DAG node, no
work-item, no lease, no lifecycle. Substrate-only.

---

## 1. Executive Summary

The 4.3 family declares four deterministic validators — `validate_header()`
(4.3.2), `validate_patterns()` (4.3.3), `validate_lineage()` (4.3.4), and
`validate_dossier()` (4.3.7) — each living at
`src/cv_assembly/validators/<x>_validator.py`. Each plan independently
restates the same load-bearing core contract: a `*ValidatorReport` shape
with `status`, `violations[]`, `repair_applied`, `repair_actions[]`,
`repaired_struct?`, and `determinism_hash`; one-pass repair semantics; no
LLM in repair; byte-determinism guarantees asserted by paired test
fixtures; a Langfuse `*.validate` span shape.

That copy-paste pattern is the leading source of drift risk in the 4.3
lane. The validators are the load-bearing anti-hallucination boundary:
when one of them silently diverges from the others (different
`severity` enum, different canonical JSON ordering, different repair
semantics, different rule_id collisions), the truth guarantees the
umbrella plan promises become unprovable.

Iteration 4.3.9 introduces a single shared framework that owns the
**base contract**: a versioned `ValidatorReport` base class, a `Violation`
base class, a `RepairAction` enum protocol, a canonical JSON
serialization, a `determinism_hash` algorithm, a global `rule_id`
registry, a per-validator `mode` registry, a conformance test harness,
and a canonical Langfuse trace contract for every validator span.

4.3.9 is not a stage. It does not own a queue, a lease, a work-item,
or a lifecycle state. It is the substrate that the four validators
inherit from, with a single feature flag
(`CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE`) that gates strict
conformance. Its rollout depends on, and unblocks, every per-stage
validator plan from 4.3.2 onward.

By the end of iteration 4.3.9, every 4.3 validator must:

- subclass the shared framework's report and violation base classes;
- emit a `determinism_hash` produced by the canonical algorithm;
- register its `rule_id` slugs in the global registry;
- pass the cross-validator conformance test harness;
- emit Langfuse spans under the canonical `scout.cv.validator.*`
  taxonomy.

## 2. Mission

Own the shared anti-hallucination substrate for 4.3 candidate-aware
generation: one base report shape, one byte-determinism algorithm,
one repair semantics contract, one rule_id namespace, one Langfuse
trace shape, one conformance harness — so that 4.3.2 / 4.3.3 / 4.3.4 /
4.3.5 / 4.3.6 / 4.3.7 inherit truth-correctness as a structural
property, not an ad-hoc per-stage assertion.

## 3. Objectives

1. Define `ValidatorReport`, `Violation`, `RepairAction`, and `Mode`
   base shapes that every 4.3 validator inherits, with explicit
   per-validator extension points.
2. Specify the canonical JSON serialization rule and the
   `determinism_hash` algorithm so reports are byte-equivalent across
   processes, hosts, Python versions, and OS line-ending modes.
3. Specify the one-pass repair contract: bounded, deterministic,
   no-LLM, no-pool-growth, idempotent.
4. Own the global `rule_id` namespace (`<validator_name>:<rule_slug>`)
   with explicit collision detection at module-import time.
5. Own the per-validator `mode` registry so 4.3.2's
   `{blueprint, draft, synthesis}`, 4.3.3's `{selection,
   draft_consumption}`, 4.3.4's `{draft, synthesis}`, and 4.3.7's
   single mode are all surfaced through one registry instead of
   parallel string enums.
6. Ship a conformance test harness — pytest fixtures and a generic
   `assert_validator_conforms(...)` helper — that every validator
   imports.
7. Ship a canonical Langfuse trace shape for `scout.cv.validator.<name>
   .{run, repair}` spans plus `scout.cv.validator.violation`,
   `scout.cv.validator.repair_applied`, and
   `scout.cv.validator.determinism_failure` events.
8. Ship a shared evidence resolver that 4.3.4's lineage validator and
   4.3.7's dossier validator both consume (resolved as a partial-
   sharing decision in 4.3.7 §1975).
9. Provide a single feature flag —
   `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE` — that enforces
   conformance at module-import time after rollout, with a
   well-defined non-strict mode for legacy code paths.

## 4. Success Criteria

4.3.9 is done when all of the following are true in production:

### 4.1 Functional

- Every 4.3 validator (`validate_header`, `validate_patterns`,
  `validate_lineage`, `validate_dossier`) subclasses the shared
  `ValidatorReport`, `Violation`, and `RepairAction` base shapes.
- Every validator's `determinism_hash` is produced by the canonical
  algorithm in §10.2 and is byte-identical across two runs of the
  same `(struct, blueprint, master_cv, presentation_contract, mode,
  pattern?)` inputs, asserted by the conformance harness.
- The global `rule_id` registry rejects collisions at module-import
  time; no two validators share a fully-qualified `rule_id`.
- The shared evidence resolver is consumed by `validate_lineage()`
  and `validate_dossier()`; both validators produce identical
  resolution outcomes for identical refs.

### 4.2 Architectural

- `src/cv_assembly/validators/__init__.py` exposes only the base
  framework and the registry; per-validator modules import from it,
  never the reverse.
- No 4.3 validator constructs a raw report dict; every report is
  produced by `ValidatorReport.build(...)` so the canonical shape
  cannot drift.
- The framework owns no DAG node, no work-item type, no lease, no
  lifecycle state. It is in-process library code only.
- The framework emits Langfuse spans only via the existing
  `CvAssemblyTracingSession` (4.3.8 §7.6); it never instantiates a
  raw `langfuse.Langfuse(...)` client.
- Validator reports are persisted only inside the consuming
  artifact's subtree on `level-2.cv_assembly.*` (e.g.,
  `cv_assembly.header_blueprint.validator_report`). 4.3.9 never
  writes to Mongo directly; it returns a dataclass that the
  consuming stage persists.

### 4.3 Observability

- Every validator run emits a `scout.cv.validator.<name>.run` span
  carrying `validator_name`, `mode`, `determinism_hash`,
  `violations_count`, `severity_counts`, `repair_actions_count`,
  `repaired`, `input_snapshot_id`, and the consuming stage's
  `level2_job_id` + `correlation_id`.
- Every repair pass emits a `scout.cv.validator.<name>.repair` span.
- Every blocking violation emits a `scout.cv.validator.violation`
  event.
- Determinism-hash mismatches between two runs (detected by the
  conformance harness or by the live double-run sweeper) emit a
  `scout.cv.validator.determinism_failure` event with `expected_hash`,
  `actual_hash`, and `field_diff_summary`.

### 4.4 Safety / anti-hallucination

- The framework's repair contract is no-LLM by construction:
  `RepairAction.apply()` is a pure function over the validator's
  input struct + the framework's allowed action set, and the
  framework imports from `src.common.unified_llm` are statically
  forbidden in `validators/_framework.py`.
- The one-pass bound is enforced structurally: the framework's
  `run_with_repair()` helper raises `ValidatorContractViolation`
  if the consumer attempts more than one repair pass.
- The pool-growth guard rejects any repair that adds content not
  present in the validator's allowed input pools (header blueprint
  pools, pattern evidence map, master-CV resolved entries).
- All repairs are idempotent: applying `RepairAction` to a fixed
  point produces the same fixed point.

### 4.5 Eval / benchmark

- A frozen conformance corpus under
  `data/eval/validation/cv_assembly_4_3_9_validator_framework/`
  exists, with one fixture per validator covering: clean pass,
  every supported `severity=blocking` violation, every supported
  `severity=repairable` violation, a determinism double-run, and a
  no-IO sandbox run.
- The cross-validator conformance harness runs all four validators
  under the same fixtures and asserts shape equivalence.

## 5. Non-Goals

Iteration 4.3.9 explicitly does not:

- Rewrite per-validator semantics. The framework provides the base;
  per-validator rule logic stays in 4.3.2 / 4.3.3 / 4.3.4 / 4.3.7.
- Own DAG edges, work-item types, leases, or lifecycle states.
- Replace any per-validator test suite. Per-validator tests stay
  with their owning plan; 4.3.9 adds a *cross-validator* harness.
- Run any LLM call. The framework is no-LLM by construction.
- Do web research, hit Mongo, or hit pdf-service. Pure in-process
  library code.
- Define a new Mongo collection, a new persistence layout, or a
  new sidecar artifact. Validator reports embed in their consuming
  artifact's subtree per §14.
- Replace the existing 4.3.4 / 4.3.7 evidence resolvers. 4.3.9
  centralizes a *shared* resolver that both already use; per-
  validator helpers above the resolver remain in their plans.
- Touch preenrich. Validators run after `cv_ready`; 4.3.9 lives in
  the candidate-aware lane only.

Deferred to iteration 4.4+:

- A validator-driven CV Editor diff surface that lets a human
  override repair decisions before publish.
- Automatic rule_id deprecation tooling (currently manual).
- A Langfuse-side regression dashboard for repair-rate trends.

## 6. Why This Artifact Exists

Three converging pressures justify a standalone framework plan:

1. **Drift risk is structural, not stylistic.** 4.3.2's
   `HeaderValidatorReport`, 4.3.3's `PatternValidatorReport`, 4.3.4's
   `EvidenceLineageValidatorReport`, and 4.3.7's
   `DossierValidatorReport` each restate the same skeleton. A small
   change in any one (e.g., 4.3.4 reorders `violations[]` by
   `rule_id` while 4.3.2 keeps insertion order) produces a silent
   `determinism_hash` divergence on the same input — and the only
   place that catches it today is per-validator eval. A single
   base contract makes the field set, ordering, and serialization
   structurally identical.
2. **Anti-hallucination is the production-readiness gate.** The
   umbrella plan (§9.1) makes truth-first invariants load-bearing
   for every candidate-aware stage. Repair semantics — one-pass,
   no-LLM, no-pool-growth, idempotent — are the rule that prevents
   the family from quietly fabricating its way back to a "passing"
   state. That rule must be enforced once, structurally, not four
   times in prose.
3. **Cross-validator interactions need a single owner.** 4.3.4 calls
   `validate_header(mode="draft")` on every draft; 4.3.5 calls both
   `validate_lineage(mode="synthesis")` and `validate_header(mode=
   "synthesis")` on the synthesis output; 4.3.6 reads
   `validate_dossier()`'s report on the render path. Without a
   shared registry, mode strings drift, rule_ids collide, and span
   metadata fragments. With a shared registry, an operator
   inspecting a Langfuse trace sees one consistent shape for every
   validator pass.

The umbrella plan (§9.1, §9.5) and missing.md
(`docs/current/missing.md:6470-6481`, `:6504-6506`) both flag this
substrate as needing standalone ownership. 4.3.9 is the smallest,
non-stage plan that absorbs that ownership without bloating any
existing 4.3 sub-plan.

## 7. Boundary And Ownership

### 7.1 Scope

4.3.9 owns:

- `src/cv_assembly/validators/_framework/` (new package):
  - `report.py` — `ValidatorReport` base dataclass + `Violation` +
    `RepairAction` + `Severity` + `ValidatorStatus` enums.
  - `determinism.py` — canonical JSON serializer + hash algorithm.
  - `registry.py` — `RuleIdRegistry`, `ModeRegistry`,
    `ValidatorRegistry`.
  - `repair.py` — `run_with_repair()` helper enforcing the
    one-pass bound and the no-LLM static guard.
  - `evidence.py` — shared `EvidenceResolver` consumed by 4.3.4
    and 4.3.7.
  - `tracing.py` — canonical Langfuse span/event emitters that
    wrap `CvAssemblyTracingSession`.
  - `conformance.py` — pytest fixtures + `assert_validator_conforms`
    helper.
- `tests/unit/cv_assembly/validators/test_framework_*.py` — base
  framework tests.
- `tests/unit/cv_assembly/validators/conformance/` — cross-validator
  conformance fixtures.
- `data/eval/validation/cv_assembly_4_3_9_validator_framework/` —
  cross-validator conformance corpus.
- The single feature flag
  `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE` (default `false` in
  shadow, `true` post-rollout).

### 7.2 Inputs

The framework itself takes no Mongo input. Its consumers pass:

- the validator's input struct (e.g., `HeaderStruct`,
  `PatternDoc`, `DraftDoc`, `DossierStateDoc`);
- the upstream artifact (e.g., `HeaderBlueprintDoc`,
  `PatternDoc` for draft validation, `MasterCv` resolved entries);
- a `mode: ValidatorMode` value drawn from the registry;
- an optional `tracer: CvAssemblyTracingSession`.

### 7.3 Hard Prerequisites

Before any 4.3.9 code is enabled, the following must be true in
production:

- `src/cv_assembly/tracing.py` exists and exposes
  `CvAssemblyTracingSession` per 4.3.8 §7.6. The framework refuses
  to import otherwise (raises `ImportError` at module load).
- `src/common/master_cv_store.py` v2 (4.3.1) is present and exposes
  the resolved-entry interface that the shared evidence resolver
  consumes. The framework refuses to import otherwise.
- The host Python is 3.11+ so that `dataclasses.dataclass(slots=True,
  frozen=True, kw_only=True)` semantics are stable for the report
  base classes (canonical-JSON sort behavior depends on stable dict
  ordering, and the framework asserts this at import time).
- No prerequisite presentation_contract or jd_facts data is needed
  by the framework itself; consumers pass those through.

If any prerequisite is unmet, the framework does **not** fail open —
it raises `ValidatorFrameworkUnavailable` at import. Consuming
stages must then fall back to their non-strict (legacy) report
shape. The framework never writes a degraded validator report that
silently passes; failure to import means the consuming stage runs
its legacy validator path, which is always more conservative.

### 7.4 What 4.3.9 owns vs what stages still own

| Concern | Owned by | Defined in |
|---------|----------|------------|
| `ValidatorReport` base shape (`status`, `mode`, `violations[]`, `repair_applied`, `repair_actions[]`, `repaired_struct?`, `determinism_hash`) | 4.3.9 | §9.1 |
| `Violation` base shape (`rule_id`, `severity`, `location`, `detail`, `suggested_action`) | 4.3.9 | §9.2 |
| `RepairAction` base shape and per-validator extension protocol | 4.3.9 | §9.3 |
| `Severity` enum (`blocking`, `repairable`, `warning`) | 4.3.9 | §9.1 |
| `ValidatorStatus` enum (`pass`, `repair_attempted`, `failed`) | 4.3.9 | §9.1 |
| Canonical JSON serializer + `determinism_hash` algorithm | 4.3.9 | §10.1, §10.2 |
| Global `rule_id` registry (`<validator_name>:<rule_slug>`) | 4.3.9 | §9.5 |
| Per-validator `mode` registry | 4.3.9 | §9.6 |
| One-pass repair bound + no-LLM static guard | 4.3.9 | §10.3, §10.4 |
| Shared evidence resolver (master-CV ref → resolved entry) | 4.3.9 | §7.1 |
| Langfuse `scout.cv.validator.*` span/event taxonomy | 4.3.9 | §15 |
| Conformance test harness (`assert_validator_conforms`) | 4.3.9 | §16.1 |
| Per-validator rule logic and rule_ids | 4.3.2 / 4.3.3 / 4.3.4 / 4.3.7 | their plans |
| Per-validator repair-action enum members | 4.3.2 / 4.3.3 / 4.3.4 / 4.3.7 | their plans |
| Per-validator mode strings (registered via 4.3.9 registry) | 4.3.2 / 4.3.3 / 4.3.4 / 4.3.7 | their plans |
| Per-validator determinism corpus | 4.3.2 / 4.3.3 / 4.3.4 / 4.3.7 | their plans |
| Validator report persistence (Mongo writes) | consuming stage | 4.3.2 / 4.3.4 / 4.3.7 |

Implications:

- 4.3.9 is the **only place** that defines the shape and hash of a
  validator report. Per-validator subclasses extend with their own
  `rule_id` enum and per-rule check functions, but the field set,
  ordering, and serialization come from the base.
- 4.3.9 is the **only place** the no-LLM-in-repair guarantee is
  structurally enforced. Per-validator plans assert it in prose;
  the framework enforces it via `run_with_repair()`'s static guard.
- 4.3.9 owns no Mongo write path. Per-stage workers persist the
  returned report into the consuming artifact's subtree.

### 7.5 Source-of-truth chain

| Concern | Single source of truth |
|---------|------------------------|
| Field set on every `*ValidatorReport` | 4.3.9 §9.1 (base shape) |
| Field ordering for canonical JSON | 4.3.9 §10.1 (alphabetical, stable) |
| `determinism_hash` algorithm | 4.3.9 §10.2 |
| `rule_id` namespace and uniqueness | 4.3.9 §9.5 (`RuleIdRegistry`) |
| Allowed `severity` values | 4.3.9 §9.1 |
| One-pass repair bound | 4.3.9 §10.3 |
| Modes available per validator | per-validator plan; registered via 4.3.9 §9.6 |
| Allowed repair actions per validator | per-validator plan; subclasses 4.3.9's `RepairAction` |
| Master-CV ref resolution | 4.3.9 §7.1 (`EvidenceResolver`) |
| Metadata display-policy resolution | 4.3.9 §7.1 (`EvidenceResolver` + display-policy helpers) |

Per-validator plans **may not redefine** the base shape, the
canonical JSON rule, the hash algorithm, or the repair bound. They
extend by:

1. Subclassing `ValidatorReport` with extra fields (e.g.,
   `HeaderValidatorReport.audience_variants_checked: tuple[str,...]`).
2. Subclassing `Violation` with extra fields if needed (rare).
3. Registering their `rule_id` slugs in the global registry.
4. Registering their modes in the mode registry.
5. Defining their per-rule check functions that produce `Violation`
   instances and (where applicable) `RepairAction` instances.

## 8. Cross-Artifact Invariants

These invariants are asserted by the conformance harness and by
unit tests at module-import time:

- Every concrete `*ValidatorReport` is a frozen, slotted dataclass
  inheriting `ValidatorReport`.
- Every concrete report's `mode` field's value is registered in
  `ModeRegistry` for that validator's `validator_name`.
- Every `Violation.rule_id` is registered in `RuleIdRegistry` and
  belongs to exactly one validator.
- Every `RepairAction.action` value is in the validator's allowed
  action set, registered at module-import time.
- `determinism_hash` ⇔ `sha256(canonical_json(report_without_hash))`
  for every emitted report; the conformance harness recomputes and
  asserts equality.
- `repair_applied=True` ⇔ `len(repair_actions) >= 1` and
  `repaired_struct is not None`.
- `status="pass"` ⇒ `len(violations.where(severity=blocking)) == 0`
  and `repair_applied=False`.
- `status="repair_attempted"` ⇒ `repair_applied=True` and after
  repair `len(violations.where(severity=blocking)) == 0`.
- `status="failed"` ⇒ either repair was attempted but blocking
  violations remain, or repair was not attempted because no allowed
  action covered the violation.
- No validator imports `src.common.unified_llm`,
  `src.preenrich.research_transport`, or any module in
  `src.layer6_v2.prompts.*`. Enforced by an import-graph test
  (§16.4).
- No validator opens a network socket. Enforced by the no-IO test
  fixture (§16.5).
- No validator instantiates `langfuse.Langfuse(...)`. Spans go
  through `CvAssemblyTracingSession` only.
- `EvidenceResolver` returns the same resolved-entry payload for
  the same `(role_id, achievement_id?, variant_id?, project_id?)`
  tuple across `validate_lineage()` and `validate_dossier()` runs.
  Enforced by the cross-validator resolver fixture in §16.3.
- `EvidenceResolver` returns the same disclosure-policy payload for the
  same candidate metadata field across `validate_header()`,
  `validate_patterns()`, `validate_dossier()`, and publish-time checks.
- Any validator that checks competencies must consume the same
  4.3.1 `skill_surface_authorization` source of truth.

Failure of any invariant fails the conformance harness; rollout
gates block on conformance failures (§18.1).

## 9. Output Shape — Base Schemas

### 9.1 `ValidatorReport` base

```python
# src/cv_assembly/validators/_framework/report.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Optional, TypeVar

class Severity(str, Enum):
    BLOCKING = "blocking"
    REPAIRABLE = "repairable"
    WARNING = "warning"

class ValidatorStatus(str, Enum):
    PASS = "pass"
    REPAIR_ATTEMPTED = "repair_attempted"
    FAILED = "failed"

S = TypeVar("S")  # the validator's input struct (e.g., HeaderStruct)

@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatorReport(Generic[S]):
    schema_version: str          # "4.3.9.v1"
    validator_name: str          # e.g., "header", "patterns",
                                 # "lineage", "dossier"
    mode: str                    # registered in ModeRegistry
    status: ValidatorStatus
    violations: tuple["Violation", ...]
    repair_applied: bool
    repair_actions: tuple["RepairAction", ...]
    repaired_struct: Optional[S]
    determinism_hash: str        # sha256:<hex64>; see §10.2
    input_snapshot_id: str       # caller-provided, opaque to framework
    duration_ms: int
    framework_version: str       # "4.3.9.v1"

    @classmethod
    def build(
        cls,
        *,
        validator_name: str,
        mode: str,
        violations: tuple["Violation", ...],
        repair_actions: tuple["RepairAction", ...],
        repaired_struct: Optional[S],
        input_snapshot_id: str,
        duration_ms: int,
    ) -> "ValidatorReport[S]":
        """The only way to construct a report. Computes status and
        determinism_hash deterministically. No subclass may bypass."""
```

Notes:

- `schema_version` and `framework_version` are pinned strings.
  Changes require a coordinated bump across all four validators.
- `mode` is a string (not an enum) because each validator has its
  own legal modes; `ModeRegistry` (§9.6) checks legality at
  `build()` time.
- `repaired_struct` is `Optional[S]`; subclasses fix `S` to their
  concrete struct type via `Generic[S]`.
- `duration_ms` is required — even the framework's tracer
  bookkeeping must be visible in the persisted report.

### 9.2 `Violation` base

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Violation:
    rule_id: str                 # registered in RuleIdRegistry; <name>:<slug>
    severity: Severity
    location: "Location"
    detail: str                  # <= 240 chars; no full prose
    suggested_action: Optional[str]  # name of a RepairAction subclass
                                     # value or None when no repair
                                     # is permitted

@dataclass(frozen=True, slots=True, kw_only=True)
class Location:
    section: str                 # e.g., "title", "tagline",
                                 # "key_achievement", "evidence_map.header",
                                 # "dossier.section.proof_pillars"
    slot_index: Optional[int]
    field_path: Optional[str]    # canonical jq-style path within section
```

Per-validator subclasses may add fields, but every concrete
violation must serialize the base fields above.

### 9.3 `RepairAction` base

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class RepairAction:
    rule_id: str                 # the violation that triggered this repair
    action: str                  # validator-specific enum value;
                                 # registered at module-import time
    before_hash: str             # sha256 of pre-repair sub-struct slice
    after_hash: str              # sha256 of post-repair sub-struct slice
    detail: str                  # <= 240 chars

    def apply(self, struct: S, context: "RepairContext") -> S:
        """Pure function. No I/O. No LLM. No pool growth. Idempotent.
        Subclasses override; the framework enforces the contract via
        run_with_repair()."""
```

Per-validator subclasses (e.g.,
`HeaderRepairAction.SUBSTITUTE_FROM_POOL`,
`LineageRepairAction.SURGICAL_REMOVE_BULLET`,
`DossierRepairAction.OMIT_SECTION`) extend by registering enum
values and implementing `apply()`.

### 9.4 Per-validator extension surface

Per-validator plans subclass like this:

```python
# src/cv_assembly/validators/header_validator.py (4.3.2)

@dataclass(frozen=True, slots=True, kw_only=True)
class HeaderValidatorReport(ValidatorReport[HeaderStruct]):
    audience_variants_checked: tuple[str, ...]
    blueprint_pool_summary: PoolSummary

@dataclass(frozen=True, slots=True, kw_only=True)
class HeaderViolation(Violation):
    blueprint_pool_id: Optional[str]
```

Extension rules:

- Subclasses MUST be `frozen=True, slots=True, kw_only=True`.
- Subclasses MAY add fields; they MUST NOT remove or rename base
  fields.
- Subclass field types MUST be canonically-JSON-serializable
  (§10.1).
- The conformance harness (§16.1) re-checks every public report
  type against the base shape at test time.

### 9.5 `RuleId` namespace

Format: `<validator_name>:<rule_slug>`.

- `validator_name ∈ {"header", "patterns", "lineage", "dossier"}`.
- `rule_slug` is `[a-z][a-z0-9_]{2,63}`.
- Registry: `RuleIdRegistry` is a frozen `set[str]` populated at
  module-import time via decorator:

  ```python
  @rule_id("header:title_outside_allowlist")
  def check_title_in_allowlist(struct, blueprint, ...) -> Optional[Violation]:
      ...
  ```

- Collisions raise `RuleIdCollision` at import — the consuming
  module fails to load, which fails the worker's startup health
  probe.
- A snapshot of the registry is exported to
  `data/eval/validation/cv_assembly_4_3_9_validator_framework/
  rule_id_registry.json` at every test run for ops visibility.

Stable ordering for canonical JSON: rule_ids are sorted by their
fully-qualified string in `violations[]` and `repair_actions[]`
when inserted into the report. The framework enforces this in
`ValidatorReport.build()`.

### 9.6 `Mode` registry

```python
ModeRegistry.register(
    validator_name="header",
    modes=("blueprint", "draft", "synthesis"),
)
ModeRegistry.register(
    validator_name="patterns",
    modes=("selection", "draft_consumption"),
)
ModeRegistry.register(
    validator_name="lineage",
    modes=("draft", "synthesis"),
)
ModeRegistry.register(
    validator_name="dossier",
    modes=("default",),  # 4.3.7 currently single-mode
)
```

`ValidatorReport.build()` raises `UnknownMode` if the supplied
`mode` is not registered for the supplied `validator_name`. The
mode registry is read-only post-import; tests assert immutability.

## 10. Deterministic Contracts

### 10.1 Canonical JSON serialization

- `json.dumps(payload, sort_keys=True, separators=(",", ":"),
  ensure_ascii=True)`.
- Unicode codepoints are normalized via NFC before serialization.
- Tuples and frozensets are coerced to JSON arrays in their natural
  iteration order; for tuples, that is insertion order; for
  frozensets, the framework rejects frozenset fields at
  `ValidatorReport.build()` time (frozensets have no stable order
  across Python versions).
- Floats are forbidden in any serialized field. Numeric bands are
  integers; weights are integer percentages, not floats.
- `None` is serialized as `null`.
- Datetime fields are serialized as ISO-8601 UTC strings with
  `Z` suffix and second precision.
- `bytes` fields are forbidden; binary data is hex-encoded
  upstream by the consuming validator.
- `dataclasses.asdict()` is **not** used (its dict-traversal can
  vary by Python version when slots are involved). The framework
  uses an explicit `to_canonical_dict()` recursive walk.

The serializer lives in
`src/cv_assembly/validators/_framework/determinism.py::
canonical_json()`.

### 10.2 `determinism_hash` algorithm

```python
def determinism_hash(report_without_hash: dict) -> str:
    payload = canonical_json(report_without_hash)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

`report_without_hash` is the report dict with the
`determinism_hash` field removed. The order of all other fields is
already canonical via §10.1. Two runs of the same validator on the
same inputs produce byte-identical hashes; this is asserted by the
conformance harness (§16.1) and by per-validator determinism tests
(`tests/unit/cv_assembly/test_*_validator_determinism.py`).

### 10.3 One-pass repair bound

The framework helper `run_with_repair()` is the only allowed
entrypoint for a validator that supports repair. Pseudo-signature:

```python
def run_with_repair(
    *,
    validator_name: str,
    mode: str,
    struct: S,
    initial_check: Callable[[S], tuple[Violation, ...]],
    repair_dispatch: Callable[[S, Violation], Optional[RepairAction]],
    apply_action: Callable[[S, RepairAction], S],
    re_check: Callable[[S], tuple[Violation, ...]],
    input_snapshot_id: str,
    tracer: Optional[CvAssemblyTracingSession],
) -> ValidatorReport[S]:
    ...
```

Behavior:

1. Run `initial_check(struct)` → `violations_0`.
2. If no `severity=blocking` or `severity=repairable` violations,
   return `status=pass`.
3. For each violation, call `repair_dispatch` to obtain at most one
   `RepairAction`. If any violation has no dispatchable action,
   collect it as unrepairable.
4. Apply all dispatched actions sequentially via `apply_action`.
   The order is sorted-by-rule_id to enforce determinism.
5. Run `re_check(repaired_struct)` → `violations_1`. If any
   `severity=blocking` violations remain, set `status=failed`.
   Otherwise `status=repair_attempted`.
6. Build the report via `ValidatorReport.build(...)`.

The helper raises `MultiPassRepairAttempted` if a consumer tries
to invoke it twice on the same struct. The struct passes through
the helper exactly once per stage call.

### 10.4 No-LLM-in-repair guarantee

Enforced by three layers:

- **Static import guard**: the framework's `__init__.py` runs an
  import-graph check at test time (§16.4) asserting that no module
  under `src/cv_assembly/validators/` imports
  `src.common.unified_llm`, `src.preenrich.research_transport`,
  `src.layer6_v2.prompts.*`, or any HTTP client.
- **Runtime guard**: `RepairAction.apply()` is required to be a
  pure function. The framework wraps repair calls in a
  `_no_io_sandbox` context manager (§16.5) during conformance
  testing that monkeypatches `socket.socket.__init__` to raise.
  Production runs do not use the sandbox (it is a test-only
  guard).
- **Documentation guard**: every repair action's `detail` string
  is bounded to 240 chars and may not contain LLM-style prose
  patterns; the conformance harness asserts
  `not detail.startswith("Based on the candidate's")` and similar
  smell tests.

### 10.5 Idempotence

For every `RepairAction`, applying `apply()` to a fixed point
struct must produce the same fixed point:

```python
struct_a = action.apply(struct_0, context)
struct_b = action.apply(struct_a, context)
assert canonical_json(struct_a) == canonical_json(struct_b)
```

The conformance harness asserts this for every registered repair
action across the corpus.

## 11. Validator API Template

### 11.1 Public Python signature

Every per-validator module exposes one entrypoint with this
template:

```python
def validate_<name>(
    struct: <StructType>,
    upstream_artifact_1: <T1>,
    upstream_artifact_2: <T2>,
    *,
    mode: str,
    pattern: Optional[PatternDoc] = None,    # only when relevant
    tracer: Optional[CvAssemblyTracingSession] = None,
    input_snapshot_id: str,
) -> <Report>: ...
```

Mandatory:

- `mode` is keyword-only and registered in `ModeRegistry` for
  `<name>`.
- `tracer` is keyword-only and may be `None` in tests; production
  callers always pass a non-None tracer.
- `input_snapshot_id` is keyword-only and required so the report's
  `input_snapshot_id` field is always populated.
- The function returns the validator's concrete `*ValidatorReport`
  subclass; never a dict, never `None`, never raises on validation
  failure (failures are expressed in `status="failed"`).

The function may raise only:

- `ValidatorFrameworkUnavailable` if the framework cannot import.
- `UnknownMode` if `mode` is not registered.
- `RuleIdCollision` (only at import time, not at runtime).
- `ValidatorContractViolation` if a subclass violates §10.3 (e.g.,
  attempting two repair passes).

### 11.2 Required behaviors

- Construct the report exclusively via `ValidatorReport.build(...)`.
- Run all repairs through `run_with_repair()`.
- Resolve master-CV refs via the shared `EvidenceResolver`.
- Emit Langfuse spans via `tracer.start_validator_span(...)`.
- Surface every violation, even after repair, in
  `violations[]` (with status reflecting whether they were
  resolved).

### 11.3 Forbidden behaviors

- Constructing reports as dicts and casting later.
- Sorting `violations[]` or `repair_actions[]` by anything other
  than `rule_id` (would break canonical JSON).
- Calling `apply()` on a repair action outside `run_with_repair()`.
- Importing any LLM transport, HTTP client, or Mongo driver.
- Writing to disk or stdout (logging via `tracer` only).
- Using `json.dumps` directly without `canonical_json()`.

### 11.4 Conformance test obligations

Each per-validator plan ships:

- `test_<name>_validator.py` — one fixture per `rule_id`.
- `test_<name>_validator_determinism.py` — two-run byte-equality
  assertion.
- `test_<name>_validator_no_io.py` — `validate_<name>` in the
  no-IO sandbox (asserts no socket / no Mongo / no file write).

All three import the framework's conformance helpers. 4.3.9 owns
the helpers and the cross-validator orchestration test that runs
all four validators under the same fixture set.

## 12. Fail-Open / Fail-Closed

Fail open:

- The framework itself never falls open. If the framework cannot
  import, the consuming stage falls open to its legacy validator
  path (which is always more conservative, never silent).
- `validate_<name>(..., mode="<x>")` always returns a report; it
  does not raise on validation outcomes.
- A `severity=warning` violation does not affect status; the
  consuming stage may surface it for ops without blocking.

Fail closed:

- `RuleIdCollision` at module import → consuming module fails to
  load → worker startup health probe fails → no work is claimed.
  This is the intended behavior; collisions are bugs, not
  recoverable conditions.
- `UnknownMode` at runtime → the consuming stage's call site has a
  bug; the call raises and the stage worker's normal retry/
  deadletter path engages. There is no silent recovery — a
  validator must never run in an unregistered mode.
- `MultiPassRepairAttempted` → contract violation; the consuming
  stage's retry/deadletter path engages.
- `ValidatorContractViolation` raised by `run_with_repair()` (e.g.,
  `apply_action` returned a struct of the wrong type) → consuming
  stage's deadletter path.
- The `_no_io_sandbox` is test-only and never engages in
  production; the import-graph test (§16.4) is the production-time
  enforcement.

## 13. Safety / Anti-Hallucination

- **No prose generation**: the framework cannot emit text. Every
  field is structured. Every repair action is a transformation of
  existing structure, never a new string outside frozen pools.
- **No master-CV mutation**: `EvidenceResolver` is read-only. It
  raises on resolution failure rather than synthesizing a
  best-effort match.
- **No pool growth**: `RepairAction.apply()` is required to assert
  that any value it introduces is already present in the
  consumer's allowed pool (e.g., `HeaderBlueprintDoc.
  hero_proof_fragments[]`); the framework's `RepairContext` carries
  the pool and exposes a `pool_contains(value, pool_id)` helper.
- **No hallucinated metrics**: numeric tokens in any field are
  rejected at `ValidatorReport.build()` if their string
  representation would change after canonical JSON normalization
  (e.g., trailing-zero floats, locale-specific separators).
- **No protected-trait inference**: the framework's report fields
  cannot store names, contact info, gender, or racial markers; the
  schema is closed.
- **No silent passes**: `status="pass"` requires zero blocking and
  zero repairable violations; `status="repair_attempted"` requires
  at least one repair and zero remaining blocking violations;
  every other state is `status="failed"`. The consuming stage
  decides whether `status="failed"` blocks the run.

## 14. Operational Catalogue

| Concern | 4.3.9 ownership |
|---------|-----------------|
| Owner | Substrate library + conformance harness (no stage) |
| Prerequisite artifacts | `CvAssemblyTracingSession` (4.3.8 §7.6); master-CV v2 loader (4.3.1) |
| Persisted Mongo locations | None directly. Validator reports embed in their consuming artifact's subtree (e.g., `level-2.cv_assembly.header_blueprint.validator_report`) |
| Stage-run / job-run records | Validator outcome counters appear in each consuming stage's `cv_assembly.stage_states.<task>.metadata.validator_report_summary` |
| Work-item semantics | None. The framework runs in-process inside the consuming stage worker |
| Retry / repair behavior | Single repair pass per validator call (§10.3). Stage-level retry is unchanged |
| Cache behavior | None. Reports are computed deterministically per run |
| Heartbeat/operator expectations | Validator runs are bounded by the consuming stage's heartbeat. A validator that exceeds `CV_ASSEMBLY_VALIDATOR_MAX_DURATION_MS` (default 30s) emits a `scout.cv.validator.<name>.slow` event but does not fail; the consuming stage's heartbeat continues |
| Feature flags | `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE` (default `false` shadow / `true` post-rollout); `CV_ASSEMBLY_VALIDATOR_MAX_DURATION_MS` (default 30000) |
| Operator-visible signals | `cv_assembly.<artifact>.validator_report.{status, determinism_hash, repair_applied, violations_count, severity_breakdown}` |
| Downstream consumers | 4.3.2 (header), 4.3.3 (patterns), 4.3.4 (lineage + header), 4.3.5 (lineage + header on synthesis), 4.3.6 (reads dossier report on render), 4.3.7 (dossier) |
| Rollback strategy | Flip `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=false`. Consuming stages continue to use the framework but skip strict-mode conformance assertions; legacy report shape is permitted as a fallback. No data deletion |
| Why no separate trace refs / cache keys / lifecycle state | The framework runs in-process. Each consuming stage already has its own trace ref pinned to `level2_job_id`; validator spans nest under that. No queue → no lease → no lifecycle |

## 15. Langfuse Tracing Contract

### 15.1 Canonical span and event names

Spans (one per validator call):

```
scout.cv.validator.header.run
scout.cv.validator.header.repair             (only if repair attempted)
scout.cv.validator.patterns.run
scout.cv.validator.patterns.repair
scout.cv.validator.lineage.run
scout.cv.validator.lineage.repair
scout.cv.validator.dossier.run
scout.cv.validator.dossier.repair
```

Spans nest under the consuming stage's parent span (e.g.,
`scout.cv.draft_assembly.lineage_validate` from 4.3.4 §1716
remains the parent; 4.3.9's spans are its children).

Events (point-in-time):

```
scout.cv.validator.violation                # one per violation
scout.cv.validator.repair_applied           # one per repair action
scout.cv.validator.determinism_failure      # only on hash mismatch
scout.cv.validator.framework_unavailable    # only on import failure
scout.cv.validator.<name>.slow              # exceeded threshold
```

### 15.2 Required metadata on every span

Inherited from 4.3.8 §7.3:

- `job_id`, `level2_job_id`, `correlation_id`,
  `langfuse_session_id` (`job:<level2_id>`), `run_id`, `worker_id`,
  `task_type`, `attempt_count`, `attempt_token`,
  `input_snapshot_id`, `work_item_id`.

4.3.9-specific:

- `validator_name` ∈ `{"header","patterns","lineage","dossier"}`.
- `validator_mode` (registered string).
- `framework_version` (e.g., `"4.3.9.v1"`).
- `determinism_hash` (sha256:<hex64>).
- `violations_count`, `severity_breakdown.{blocking,repairable,
  warning}`, `repair_actions_count`.
- `repaired` (bool).
- `report_status` ∈ `{"pass","repair_attempted","failed"}`.
- `duration_ms`.

### 15.3 Required metadata on events

`scout.cv.validator.violation`:

- `rule_id`, `severity`, `location.section`, `location.field_path`,
  `detail_truncated` (≤ 160 chars), `suggested_action?`.

`scout.cv.validator.repair_applied`:

- `rule_id`, `action`, `before_hash` (≤ 16 chars), `after_hash`
  (≤ 16 chars).

`scout.cv.validator.determinism_failure`:

- `expected_hash`, `actual_hash`, `field_diff_summary` (≤ 240
  chars; structural diff only, never raw values).

### 15.4 Forbidden in Langfuse

- Full violation `detail` strings beyond 160-char preview.
- Full `repaired_struct` payloads.
- Full `RepairContext` contents (master-CV resolved entries).
- Full report JSON.
- Floats anywhere (forbidden by §10.1).

### 15.5 What may live only in `debug_context`

- The full `*ValidatorReport.repaired_struct`.
- The full `EvidenceResolver` resolution trace.
- The per-rule check timings.

These are persisted under
`level-2.cv_assembly.<artifact>.debug_context.validator_trace[]`
and never mirrored to Langfuse.

### 15.6 Naming and cardinality rules

- Span names are the literal strings in §15.1; no per-job
  cardinality.
- Event names are the literal strings in §15.1; one event per
  occurrence within a span.
- `rule_id` cardinality is bounded by the registry; it is
  high-cardinality but pre-enumerated and acceptable as event
  metadata.
- Per-bullet, per-role-id, per-achievement-id metadata is
  forbidden as a span/event name; those are metadata fields only.

### 15.7 Operator debugging goals

A single operator must be able to:

1. Open a Langfuse trace for `job:<level2_id>`.
2. Drill into any consuming stage's span (e.g.,
   `scout.cv.draft_assembly`).
3. See every validator call as a child span with `validator_name`,
   `mode`, `determinism_hash`, `report_status`, and
   `severity_breakdown`.
4. Click a `scout.cv.validator.violation` event to see `rule_id`
   and a 160-char `detail_truncated` preview.
5. Cross-reference the `determinism_hash` to the persisted Mongo
   `level-2.cv_assembly.<artifact>.validator_report` for the full
   report body.

That round-trip — Langfuse trace → Mongo report — is the canonical
debug path for validator failures.

## 16. Tests And Evals

### 16.1 Cross-validator conformance harness

Module: `src/cv_assembly/validators/_framework/conformance.py`.

```python
def assert_validator_conforms(
    validator_callable: Callable,
    *,
    validator_name: str,
    expected_modes: tuple[str, ...],
    expected_repair_actions: tuple[str, ...],
    fixture_dir: Path,
) -> None: ...
```

Behavior:

- For each fixture under `fixture_dir`, runs the validator twice
  and asserts byte-identical reports.
- Asserts the report is a subclass of `ValidatorReport`.
- Asserts every `rule_id` is in the global registry and namespaced
  to `validator_name`.
- Asserts every `mode` is registered for `validator_name`.
- Asserts every `repair_action.action` is in the validator's
  declared `expected_repair_actions`.
- Asserts `determinism_hash` is reproducible by running
  `canonical_json` + `sha256` over the report dict (without the
  hash field).
- Asserts the no-IO sandbox (§16.5).

The four per-validator plans wire this in via:

```python
def test_header_validator_conforms():
    assert_validator_conforms(
        validate_header,
        validator_name="header",
        expected_modes=("blueprint", "draft", "synthesis"),
        expected_repair_actions=(
            "surgical_remove",
            "substitute_from_pool",
            "collapse_section",
            "clamp_band",
        ),
        fixture_dir=Path("data/eval/validation/"
                         "cv_assembly_4_3_2_header_blueprint/cases"),
    )
```

### 16.2 Schema / unit tests

- `tests/unit/cv_assembly/validators/test_framework_report_shape.py`
  — asserts every concrete report subclass passes structural
  conformance (frozen, slots, kw_only; required fields present;
  no float fields).
- `tests/unit/cv_assembly/validators/test_framework_severity_status_logic.py`
  — asserts the status-derivation rules in §8 hold for every
  combination of violations and repairs.
- `tests/unit/cv_assembly/validators/test_framework_canonical_json.py`
  — asserts byte-identical canonical JSON across Python 3.11 and
  3.12 over a curated 24-case fixture.
- `tests/unit/cv_assembly/validators/test_framework_determinism_hash.py`
  — asserts `determinism_hash` matches the documented algorithm
  for every fixture.
- `tests/unit/cv_assembly/validators/test_framework_rule_id_registry.py`
  — asserts collision detection at import time; asserts snapshot
  export to JSON.
- `tests/unit/cv_assembly/validators/test_framework_mode_registry.py`
  — asserts `UnknownMode` raised for unregistered modes; asserts
  registry is read-only post-import.
- `tests/unit/cv_assembly/validators/test_framework_repair_idempotence.py`
  — asserts every registered repair action is idempotent.

### 16.3 Cross-validator resolver fixture

`tests/unit/cv_assembly/validators/test_framework_evidence_resolver.py`:

- Loads a curated 12-role master-CV fixture.
- For every `(role_id, achievement_id?, variant_id?, project_id?)`
  tuple referenced in any of the four validator corpora, calls
  `EvidenceResolver.resolve(...)` from `validate_lineage()` context
  and from `validate_dossier()` context.
- Asserts byte-identical resolved-entry payloads.

### 16.4 Import-graph test

`tests/unit/cv_assembly/validators/test_framework_import_graph.py`:

- Uses `importlib`-based static analysis to walk all modules
  under `src/cv_assembly/validators/`.
- Asserts none of them transitively imports `src.common.unified_llm`,
  `src.preenrich.research_transport`, `src.layer6_v2.prompts.*`,
  any module under `pdf_service.*`, any HTTP client (`httpx`,
  `requests`, `aiohttp`), or any Mongo driver (`pymongo`,
  `motor`).
- Failure is a hard test failure (no allowlist).

### 16.5 No-IO sandbox

`tests/unit/cv_assembly/validators/test_framework_no_io_sandbox.py`:

- Monkeypatches `socket.socket.__init__`, `open` (for write
  modes), and `pathlib.Path.write_*` to raise.
- Runs each of the four validators on a curated fixture; asserts
  no raise.

### 16.6 Determinism double-run sweeper

A live sweeper (`scripts/cv_assembly_validator_double_run.py`)
runs hourly on a sample of recent
`level-2.cv_assembly.*.validator_report` documents and asserts
byte-identical `determinism_hash` re-computation. Failures emit a
`scout.cv.validator.determinism_failure` event and page the
on-call.

### 16.7 Regression corpus design

`data/eval/validation/cv_assembly_4_3_9_validator_framework/`:

```
cases/
  framework_report_shape/
    expected_status_pass.json
    expected_status_repair_attempted.json
    expected_status_failed.json
    expected_warning_only.json
  cross_validator_resolver/
    role_a/
      input.json
      expected_resolved.json
    ...
fixtures/
  golden_report_v1.json                    # canonical hash benchmark
  golden_report_v1_after_field_reorder.json # MUST hash identically
fault_cases/
  rule_id_collision_module.py              # importing this raises
  multi_pass_repair_attempt.py             # using this raises
  unknown_mode_call.py                     # calling this raises
baseline_report.json                       # last accepted harness output
README.md
```

### 16.8 Live smoke tests

A live smoke test (`scripts/smoke_validator_framework.py`) on the
VPS (see §17):

- Loads the four validators.
- Runs each over a small frozen fixture.
- Asserts each report's `determinism_hash` matches the expected
  golden hash baked into the script.
- Emits one `scout.cv.validator.<name>.run` span per call (so
  Langfuse contains a baseline trace shape post-deploy).

## 17. VPS End-to-End Validation Plan

### 17.1 Local prerequisite tests before touching VPS

Before any VPS run, on the developer host:

1. `source .venv/bin/activate`.
2. `pytest tests/unit/cv_assembly/validators/test_framework_*.py`
   — all framework tests green.
3. `pytest tests/unit/cv_assembly/test_header_validator_determinism.py
   tests/unit/cv_assembly/test_pattern_validator_determinism.py
   tests/unit/cv_assembly/test_evidence_lineage_validator_determinism.py
   tests/unit/cv_assembly/test_dossier_validator_determinism.py`
   — all per-validator determinism tests green (they consume
   4.3.9's harness).
4. `pytest tests/unit/cv_assembly/validators/test_framework_import_graph.py`
   — no forbidden imports.
5. `python -u scripts/smoke_validator_framework.py --local`
   — emits four expected golden hashes.

If any of the above fails, do not touch the VPS.

### 17.2 Verify VPS repo shape and sync path

Per the operational manual (`docs/current/operational-development-manual.md
:225-244`):

- Identify the active path: `/root/scout-cron`.
- Confirm it is a deployment-shaped tree, not a Git checkout.
- Sync `src/cv_assembly/validators/_framework/` and the four
  per-validator modules via `rsync -av` from a clean branch HEAD.
- Verify content-by-grep, not commit SHA:
  `grep -n "framework_version" /root/scout-cron/src/cv_assembly/
  validators/_framework/report.py`
- Run from `/tmp`, not the repo root, to avoid the `types.py`
  shadow per the manual.

### 17.3 Choose a real eligible job / artifact set

Pick one job that already has a complete `level-2.cv_assembly.*`
subtree from a prior shadow-mode run:

- `cv_assembly.header_blueprint.status in {completed, partial}`,
- `cv_assembly.pattern_selection.status in {completed, partial}`,
- at least two `cv_assembly.drafts[].status` non-failed,
- `cv_assembly.synthesis` populated,
- `cv_assembly.dossier_state` populated.

If no such job exists, run 4.3.2 → 4.3.7 in shadow mode against a
canary job until prerequisites are met (their respective live
validation plans cover this). 4.3.9 itself does not generate any
of these; it only validates.

### 17.4 Verify / recover prerequisites

For each consuming stage, verify the persisted artifact exists and
is non-degraded. If any is missing, run that stage's repair path
per its plan (4.3.2 §15 / 4.3.3 §15 / etc.) — never fabricate.

### 17.5 Fast-path: when to run only 4.3.9

4.3.9 has no stage to "run." The fast-path validation is:

1. SSH to VPS.
2. From `/tmp`, with `/root/scout-cron/.venv/bin/python -u`:
   - Load the candidate job's `cv_assembly.*` subtree from Mongo.
   - Re-run each of the four validators on the persisted struct.
   - Assert each re-run's `determinism_hash` equals the persisted
     `determinism_hash`.
3. If any mismatch, emit
   `scout.cv.validator.determinism_failure` and capture the
   per-field diff to a `/tmp/<run>.json` artifact.

Script: `/tmp/validator_framework_revalidate.py` (uploaded for
the run; not committed to the deployed tree).

### 17.6 When to rerun more of the chain

Only rerun upstream stages if a prerequisite artifact is missing
or fails its own validator on revalidation. 4.3.9 revalidation is
read-only — never triggers a re-enqueue.

### 17.7 Required launcher behavior

Per the operational manual:

- Activate `/root/scout-cron/.venv` via direct interpreter path.
- `python -u`.
- Explicit `dotenv_values(Path("/root/scout-cron/.env"))` from
  Python.
- `MONGODB_URI` (not `MONGO_URI`).
- Heartbeats every 15-30s during the per-validator re-run loop.
- Subprocess monitoring is not needed (no Codex / no LLM in
  4.3.9).
- Workdir: `/tmp/validator_framework_revalidate/`, isolated.
- Capture output to `/tmp/validator_framework_revalidate.out`.
- Capture results to `/tmp/validator_framework_revalidate.json`.

### 17.8 Expected Mongo writes

**None**. 4.3.9 revalidation is read-only. Any attempt to write
Mongo from a revalidation run is a bug; the script must not
import `pymongo` for writes (read-only client only).

### 17.9 Expected trace/span structure

After the revalidation run, Langfuse should contain four spans
under `job:<level2_id>`:

- `scout.cv.validator.header.run`
- `scout.cv.validator.patterns.run`
- `scout.cv.validator.lineage.run`
- `scout.cv.validator.dossier.run`

each with `report_status="pass"` (or `"repair_attempted"` if the
persisted report was repair_attempted), `determinism_hash` matching
the persisted hash, and the canonical metadata set in §15.2.

### 17.10 Expected stage-run / job-run records

**None**. 4.3.9 has no stage. No `pre_enrichment.stage_states.*`
or `cv_assembly.stage_states.*` rows are written. The revalidation
result is captured only as Langfuse spans + the `/tmp` artifact.

### 17.11 Stuck-run operator checks

Since 4.3.9 has no long-running work, "stuck" means the
revalidation script itself is hung. Operator checks:

- `ps -p <pid>` to confirm the script is alive.
- `tail -n 80 /tmp/validator_framework_revalidate.out` for
  heartbeat lines.
- If stuck, kill and inspect the heartbeat log to identify which
  validator did not return; that is a per-validator bug, not a
  framework bug.

### 17.12 Acceptance criteria

- All four `determinism_hash` re-runs match persisted hashes.
- Langfuse contains four canonical spans with the §15.2 metadata.
- The `/tmp/validator_framework_revalidate.json` artifact reports
  `overall=pass`.
- No Mongo writes.

### 17.13 Artifact / log / report capture

- `/tmp/validator_framework_revalidate.out` — full stdout/stderr.
- `/tmp/validator_framework_revalidate.json` — structured report:
  `{job_id, validator_results: [{name, expected_hash,
  actual_hash, match}], overall, ts}`.
- Langfuse trace URL recorded in the operator session log.

## 18. Rollout / Migration / Compatibility

### 18.1 Rollout order

4.3.9 is plumbing every other 4.3 sub-plan depends on. Order:

1. Ship 4.3.9 framework code (`src/cv_assembly/validators/
   _framework/`) plus its own unit tests behind
   `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=false`. The
   framework is loadable but no consumer imports it yet.
2. Migrate 4.3.2 `validate_header()` to subclass the framework
   base. Run conformance harness. Keep
   `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=false`; legacy
   report shape is still accepted by 4.3.2's persistence path.
3. Migrate 4.3.3 `validate_patterns()`. Conformance harness.
4. Migrate 4.3.4 `validate_lineage()` and rewire 4.3.4's
   `validate_header(mode="draft")` call site through the
   framework's tracer. Conformance harness.
5. Migrate 4.3.7 `validate_dossier()`. Conformance harness.
6. Run the cross-validator conformance harness end-to-end on the
   eval corpus. Block rollout if any validator fails.
7. Flip `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=true` in
   shadow mode for 72h. Strict mode rejects any non-conformant
   validator at module-import time; the worker startup health
   probe enforces this.
8. Flip strict mode on canary jobs (1 → 5 → 25 → 100% per the
   4.3.8 staircase).
9. Soak 72h. Block on any
   `scout.cv.validator.determinism_failure` event.
10. Flip default-on. Deprecate the legacy report shape; remove
    after one stable release.

### 18.2 Required flags

| Flag | Default | Post-cutover | Notes |
|------|---------|--------------|-------|
| `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE` | `false` | `true` | Strict-mode conformance enforcement |
| `CV_ASSEMBLY_VALIDATOR_MAX_DURATION_MS` | `30000` | `30000` | Per-validator slow-event threshold |
| `CV_ASSEMBLY_VALIDATOR_DOUBLE_RUN_SWEEPER_ENABLED` | `false` | `true` | Hourly determinism revalidation sweeper |
| `CV_ASSEMBLY_VALIDATOR_DOUBLE_RUN_SAMPLE_PCT` | `1` | `1` | Percentage of recent reports to revalidate per hour |

Mutual-exclusion invariants:

- `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=true` requires every
  per-validator plan's flag to also be at its post-cutover state
  (4.3.8 §10.2 invariants are extended with this row).
- `CV_ASSEMBLY_VALIDATOR_DOUBLE_RUN_SWEEPER_ENABLED=true` requires
  `LANGFUSE_CV_ASSEMBLY_TRACING_ENABLED=true`.

### 18.3 Backfill

None. The framework operates on validator runs going forward.
Pre-4.3.9 reports remain in their legacy shape; the
`scripts/mark_legacy_cv_ready.py` tool (4.3.7) covers the
discriminator semantics.

### 18.4 Rollback

- Flag-flip `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=false`
  disables strict-mode conformance assertions. Consuming stages
  continue to call the framework but accept legacy report shapes
  if a per-validator module reverts.
- A full rollback (revert the per-validator migration commits)
  restores the pre-4.3.9 ad-hoc report shapes. Persisted
  `validator_report` fields with the framework shape remain in
  Mongo for audit; consuming readers (frontend, dossier render)
  must accept either shape until rollback is complete.
- No data deletion.

### 18.5 Compatibility

- Persisted reports under the framework shape are a strict
  superset of the legacy shape (more fields, same ordering rules);
  legacy readers that only inspect `status` and `violations[]`
  continue to work.
- Frontend (`frontend/intel_dashboard.py` + per-job detail view)
  must be updated to read `validator_report.severity_breakdown`
  for new dashboard cards; existing cards keep working without
  changes.
- 4.3.5 synthesis is unaffected — it reads validator reports as
  structured input, never as dicts.

## 19. Open-Questions Triage

| Question | Triage | Resolution-or-recommendation |
|----------|--------|------------------------------|
| Should validator reports persist embedded in `cv_assembly.<artifact>.validator_report` or in a sibling top-level `cv_assembly.validator_reports[]` array? | must-resolve before implementation | **(resolved)** §14 — embedded under each consuming artifact's subtree. Operator ergonomics (one artifact, one report next to it) outweigh the appeal of a flat list. The 4.3.7 status-breakdown rollup already aggregates across validator reports without needing a flat list. |
| Should `RuleIdRegistry` be a Python registry, a JSON file, or both? | must-resolve before implementation | **(resolved)** §9.5 — Python registry populated at module-import time via decorator, with a JSON snapshot exported by tests. Python is canonical (collisions detected at import); JSON is for ops visibility only. |
| Should `determinism_hash` cover `repair_actions[]`? | must-resolve before implementation | **(resolved)** §10.2 — yes. The hash is over the entire report (excluding the hash field itself), which includes `repair_actions[]`. Repair determinism is part of the contract; excluding it would let repair drift go unnoticed. |
| Should `Severity` include a `fatal` level above `blocking`? | safe-to-defer | v1: three levels are sufficient. Fatal-style outcomes (e.g., `RuleIdCollision`) are exceptions, not violations, and are surfaced through the worker's startup health probe. Revisit if eval shows operators conflating blocking and fatal. |
| Should 4.3.6 publisher consume `validate_dossier()` directly or read the prebuilt report from 4.3.7? | must-resolve before implementation | **(resolved)** §14 — 4.3.6 reads the prebuilt report from `cv_assembly.dossier_state.validator_report`. Re-running validation on the render path would split the determinism contract across two different `input_snapshot_id` boundaries. |
| Should `EvidenceResolver` be the same instance across validator calls in one stage worker? | must-resolve before implementation | **(resolved)** §16.3 — yes. The resolver caches resolved entries by `(role_id, achievement_id?, variant_id?, project_id?)` for the duration of a single stage worker process. Cross-validator byte equality is asserted by the conformance fixture. The cache is invalidated on master-CV checksum change. |
| Should mode strings be lowercase / underscored / hyphenated? | must-resolve before implementation | **(resolved)** §9.6 — lowercase, underscored, `[a-z][a-z0-9_]{2,31}`. Validator-name-prefixed strings (`"header.draft"`) are rejected; modes are scoped to their validator via the registry. |
| Should we expose a `validator_report.framework_version_compat[]` so future framework versions can declare back-compat? | safe-to-defer | v1: `framework_version` is pinned and bumps require a coordinated migration. A compat array is premature until the second framework version exists. Revisit at 4.3.9.v2. |
| Should the conformance harness be a pytest plugin? | safe-to-defer | v1: a plain `assert_validator_conforms()` helper. Plugin registration adds packaging complexity without benefit until a third validator family exists outside `cv_assembly`. |
| Should `EvidenceResolver` accept partial refs (only `role_id`)? | safe-to-defer | v1: full refs only, per 4.3.4 §12 and 4.3.7 §11. Partial-ref resolution is a 4.3.5 cross-pattern synthesis concern; if needed, add a separate `resolve_role(role_id)` helper later. |

## 20. Primary Source Surfaces

Upstream (read-only for 4.3.9):

- `src/cv_assembly/tracing.py` (4.3.8 §7.6) — `CvAssemblyTracingSession`.
- `src/common/master_cv_store.py` (4.3.1) — resolved-entry interface.
- `src/cv_assembly/models.py` (umbrella §16.2) — concrete struct
  types `HeaderStruct`, `PatternDoc`, `DraftDoc`,
  `DossierStateDoc`.

Sibling plans this plan unblocks:

- `plans/iteration-4.3.2-header-identity-and-hero-proof-contract.md`
  (§11.2 — `validate_header()` consumes 4.3.9 base shape).
- `plans/iteration-4.3.3-cv-pattern-selection-and-evidence-mapping.md`
  (§13 — `validate_patterns()`).
- `plans/iteration-4.3.4-multi-draft-cv-assembly.md` (§12 —
  `validate_lineage()`).
- `plans/iteration-4.3.5-draft-grading-selection-and-synthesis.md`
  (consumes lineage and header validators on synthesis).
- `plans/iteration-4.3.6-publisher-renderer-and-remote-delivery-integration.md`
  (reads dossier validator report on render).
- `plans/iteration-4.3.7-dossier-and-mongodb-state-contract.md`
  (§11 — `validate_dossier()`).
- `plans/iteration-4.3.8-eval-benchmark-tracing-and-rollout.md`
  (§10.2 — flag mutual-exclusion invariants extended with the
  4.3.9 strict-mode flag).

Documentation surfaces:

- `docs/current/architecture.md` — gains a "Validator framework"
  section under the 4.3 lane.
- `docs/current/cv-generation-guide.md` — references the
  framework's report shape in the truth-correctness chapter.
- `docs/current/missing.md` — lines 6470-6481 and 6504-6506
  resolve to "owned by 4.3.9".
- `docs/current/operational-development-manual.md` — gains a
  validator-revalidation runbook section under §17.

## 21. Implementation Targets

### 21.1 New shared package

`src/cv_assembly/validators/_framework/` (new package):

- `__init__.py` — exports `ValidatorReport`, `Violation`,
  `RepairAction`, `Severity`, `ValidatorStatus`, `RuleIdRegistry`,
  `ModeRegistry`, `assert_validator_conforms`, `run_with_repair`,
  `EvidenceResolver`, `canonical_json`, `determinism_hash`.
- `report.py` — base dataclasses (§9.1, §9.2, §9.3).
- `determinism.py` — `canonical_json()`, `determinism_hash()`
  (§10.1, §10.2).
- `registry.py` — `RuleIdRegistry`, `ModeRegistry`,
  `ValidatorRegistry`, decorator helpers (§9.5, §9.6).
- `repair.py` — `run_with_repair()`, `RepairContext` (§10.3,
  §10.4, §10.5).
- `evidence.py` — `EvidenceResolver` (§7.1, §16.3).
- `tracing.py` — Langfuse span/event emitters (§15).
- `conformance.py` — `assert_validator_conforms()`, fixtures
  (§16.1).
- `errors.py` — `ValidatorFrameworkUnavailable`, `RuleIdCollision`,
  `UnknownMode`, `MultiPassRepairAttempted`,
  `ValidatorContractViolation`.

### 21.2 Per-validator migration touch points

These are minimal touch points; the actual rule logic stays in the
owning plan:

- `src/cv_assembly/validators/header_validator.py` — change
  `HeaderValidatorReport` to subclass `ValidatorReport[HeaderStruct]`;
  register `rule_id`s and modes; route reports through
  `ValidatorReport.build()`; route repairs through
  `run_with_repair()`.
- `src/cv_assembly/validators/pattern_validator.py` — same.
- `src/cv_assembly/validators/evidence_lineage_validator.py` —
  same; switch to shared `EvidenceResolver`.
- `src/cv_assembly/validators/dossier_validator.py` — same;
  switch to shared `EvidenceResolver`.

### 21.3 Tests

- `tests/unit/cv_assembly/validators/test_framework_*.py` — §16.2.
- `tests/unit/cv_assembly/validators/test_framework_evidence_resolver.py`
  — §16.3.
- `tests/unit/cv_assembly/validators/test_framework_import_graph.py`
  — §16.4.
- `tests/unit/cv_assembly/validators/test_framework_no_io_sandbox.py`
  — §16.5.
- `tests/unit/cv_assembly/validators/test_framework_repair_idempotence.py`
  — §16.2 + §10.5.

### 21.4 Eval corpus

`data/eval/validation/cv_assembly_4_3_9_validator_framework/` —
§16.7 layout.

### 21.5 Scripts

- `scripts/cv_assembly_validator_double_run.py` (new) —
  hourly determinism revalidation sweeper (§16.6).
- `scripts/smoke_validator_framework.py` (new) — local + VPS
  smoke test (§16.8, §17).

### 21.6 Infra

- No new `systemd` units. The double-run sweeper runs as a cron
  job on the existing scout-cron host:
  `scout-validator-double-run.timer` + `.service`.
- `infra/scripts/verify-validator-framework-cutover.sh` (new) —
  asserts strict-mode is on, conformance harness green,
  double-run sweeper enabled.

### 21.7 Documentation

- `docs/current/architecture.md` — gain a "Validator framework"
  subsection under "4.3 candidate-aware lane".
- `docs/current/operational-development-manual.md` — gain a
  validator-revalidation procedure.
- `docs/current/missing.md` — session entry per AGENTS.md rules.

## 22. Definition Of Done

Iteration 4.3.9 is done when:

- the four 4.3 validators (`validate_header`, `validate_patterns`,
  `validate_lineage`, `validate_dossier`) all subclass the shared
  `ValidatorReport` base and produce reports through
  `ValidatorReport.build()`;
- every validator's `determinism_hash` is byte-identical across
  two runs of the same inputs, asserted by both the per-validator
  determinism test and the cross-validator conformance harness;
- the `RuleIdRegistry` is populated at module-import time and
  rejects collisions; the JSON snapshot under
  `data/eval/validation/cv_assembly_4_3_9_validator_framework/
  rule_id_registry.json` is committed and tracked;
- the `ModeRegistry` rejects unregistered modes at runtime and
  is read-only post-import;
- `run_with_repair()` enforces the one-pass bound and the no-LLM
  static guard;
- the import-graph test rejects any forbidden import in any
  validator module;
- the no-IO sandbox test passes for every validator;
- the cross-validator `EvidenceResolver` returns byte-identical
  resolved entries for `validate_lineage()` and `validate_dossier()`;
- every validator emits Langfuse spans under
  `scout.cv.validator.<name>.{run,repair}` with the §15.2
  metadata set, and `scout.cv.validator.violation` events for
  every violation;
- `CV_ASSEMBLY_VALIDATOR_FRAMEWORK_STRICT_MODE=true` is in effect
  in production with 72h soak passing every gate;
- the determinism double-run sweeper has run for at least 7 days
  with zero `scout.cv.validator.determinism_failure` events;
- `docs/current/missing.md` lines 6470-6481 and 6504-6506 are
  resolved by reference to this plan;
- the per-validator plans (4.3.2 §11.2, 4.3.3 §13, 4.3.4 §12,
  4.3.7 §11) cite this plan as the canonical source of truth for
  the base report shape, the determinism contract, the rule_id
  namespace, the mode registry, and the repair semantics.

That is the correct production-ready boundary for iteration 4.3.9.
