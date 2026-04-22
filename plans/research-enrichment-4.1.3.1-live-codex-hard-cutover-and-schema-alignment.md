# Iteration 4.1.3.1 Plan: Live Codex Hard Cutover and Schema Alignment

## 1. Executive Summary

Iteration 4.1.3 proved that the 4.1 DAG can execute live Codex-only research end-to-end. The live run also proved something more important: the models are producing **richer grounded output than the plan assumed**, and the current validators, schemas, and stage controllers are discarding that richness because they were written for a thinner scalar contract.

Iteration 4.1.3.1 is the corrective slice, and it is biased in one direction on purpose.

**Governing principles for 4.1.3.1:**

1. **Richer grounded output is the preferred output.** When a live Codex subpass returns evidence-bearing structure, confidence, sources, aliases, or intermediate reasoning, the first instinct is to keep it, not to flatten it.
2. **Validation is loose on shape and strict on truth.** Unexpected wrappers, aliases, null literals, and list/dict/scalar drift are normalized at ingress. Fabricated URLs, fabricated identities, cross-company URLs, private contact data, protected-trait inference, and low-confidence outreach guidance are still rejected hard.
3. **`application_surface` must always find something useful.** It is no longer a pass/fail gate on exact canonical URL resolution. Verified employer jobs homepages, verified aggregator-only states, verified stale/closed signals, inferred-but-grounded portal/ATS hypotheses, and honest unresolved artifacts with evidence are all valid, first-class outputs. `unresolved` is not the same as `empty`. The stage fails closed on falsehood; it does not fail empty on incompleteness.
4. **Compatibility is for readers, not for canonical truth.** Compact scalar aliases remain so current downstream readers keep working, but they are a projection, not the source of truth. The canonical artifact evolves toward the richer shape that the prompts naturally induce.
5. **Schema follows stable richer output.** When a richer shape proves stable across live runs, the canonical schema evolves toward it rather than forcing repeated flattening. Flattening is a downstream concern, not an ingress concern.

Iteration 4.1.3.1 does not redesign the 4.1 DAG.
It does not reintroduce Claude fallback.
It does not abandon `application_surface` as a separate stage.
It does not treat the compact scalar schema as the “real” truth.

It does:

- harden model routing with explicit Codex-only defaults
- move `application_surface` from fail-closed to **always-produce-a-useful-artifact** behavior
- accept richer research payloads at ingress and evolve the canonical schema toward them
- keep compact aliases only as a consumer/snapshot projection
- benchmark the exact Codex-available GPT-5.3 variant against `gpt-5.2` and `gpt-5.4-mini` for `research_enrichment`
- define a hard migration path away from V1/V2 compatibility debt and toward direct canonical consumption of the richer artifact

The primary lesson from the live run is not “research is poor”.
The primary lesson is:

- `jd_facts` on `gpt-5.2` is operationally strong
- `classification` on `gpt-5.4-mini` is operationally acceptable
- `application_surface` and `research_enrichment` are producing grounded, richer-than-expected live Codex outputs
- the current validators are too fail-closed, too scalar-thin, and too compat-first for the payloads the prompts naturally induce
- the thinner schema is the drift, not the richer output

4.1.3.1 therefore treats schema alignment, richer-first ingress normalization, and canonical evolution as first-class work, not cleanup.

## 2. Inputs and Evidence Base

Primary source plans:

- `plans/research-enrichment-4.1.3-unified-company-role-application-people-intelligence.md`
- `plans/iteration-4.1-job-blueprint-preenrich-cutover.md`
- `plans/extraction-4.1.1-jd-facts-runner-parity.md`
- `plans/classification-4.1.2-taxonomy-engine-hardening.md`
- `plans/iteration-4-e2e-preenrich-cv-ready-and-infra.md`

Current implementation surfaces reviewed:

- `src/preenrich/blueprint_models.py`
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/research_transport.py`
- `src/preenrich/stages/jd_facts.py`
- `src/preenrich/stages/classification.py`
- `src/preenrich/stages/application_surface.py`
- `src/preenrich/stages/research_enrichment.py`
- `src/preenrich/types.py`
- `src/preenrich/blueprint_config.py`
- `scripts/preenrich_model_preflight.py`
- `docs/current/architecture.md`
- `docs/current/missing.md`
- `docs/current/decisions/2026-04-21-jd-facts-model-selection.md`

Live run evidence used in this plan:

- local live Codex-only execution against `level-2._id=69e63f7e12725d7147cc499c`
- title: `Lead AI Engineer`
- company: `Robson Bale`

External decision inputs:

- GPT-5.4 mini pricing:
  - input `$0.75 / 1M`
  - output `$4.50 / 1M`
  - sources:
    - `https://openai.com/index/introducing-gpt-5-4-mini-and-nano/`
    - `https://openai.com/api/pricing/`
- GPT-5.2 pricing:
  - input `$1.75 / 1M`
  - output `$14.00 / 1M`
  - sources:
    - `https://openai.com/index/introducing-gpt-5-2`
    - `https://platform.openai.com/docs/pricing/`
- GPT-5.2 Codex reasoning effort support:
  - `low`, `medium`, `high`, `xhigh`
  - sources:
    - `https://platform.openai.com/docs/models/gpt-5.2-codex`
    - `https://platform.openai.com/docs/guides/latest-model`
- Local `codex exec --help` evidence:
  - no explicit `--reasoning-effort` CLI flag
  - `-c key=value` config overrides are supported
  - therefore CLI support for reasoning effort is plausible but not yet proven in this repo’s exact runtime path

## 3. Live Run Findings That 4.1.3.1 Must Solve

### 3.1 `jd_facts` on `gpt-5.2` worked

Observed result:

- completed in about `118.75s`
- title, company, location, remote policy, skills, responsibilities, qualifications, and application URL were all extracted successfully
- quality was materially stronger and more complete than earlier `gpt-5.4-mini` runs

Decision impact:

- `jd_facts` should remain pinned to `gpt-5.2`
- no escalation
- no fallback

### 3.2 `classification` on `gpt-5.4-mini` worked, but post-LLM collapse needs inspection

Observed result:

- completed in about `30.91s`
- primary run on `gpt-5.4-mini` succeeded
- configured escalation to `gpt-5.2` did not trigger
- final persisted output was acceptable, but richer live classification detail appears to be getting collapsed during normalization / projection

Decision impact:

- keep `classification` primary on `gpt-5.4-mini`
- retain escalation to `gpt-5.2` for ambiguity / schema / failure cases only
- explicitly audit where useful richer detail is being discarded downstream

### 3.3 `application_surface` collapsed a useful finding to empty

Observed live Codex payload found useful verified evidence:

- `job_url = https://linkedin.com/jobs/view/4401620360`
- `canonical_application_url = https://www.robsonbale.com/jobs/`
- `final_http_status = 200`
- `resolution_status = partial`
- verified employer jobs portal found, but exact job-specific URL not directly exposed

This is a useful, grounded, employer-safe outcome. It is the shape `application_surface` should retain and persist.

Observed rejection reasons were pure shape drift:

- enum drift:
  - `ui_actionability = applyable`
  - `form_fetch_status = unavailable`
- null-vs-literal drift:
  - `stale_signal = null`
  - `closed_signal = null`
- object-vs-scalar drift:
  - `geo_normalization` string vs dict
  - `apply_instructions` list vs string
- dict-vs-null drift:
  - `duplicate_signal = null`

Result:

- the stage had a verified employer-safe `200` on the jobs portal with a clean `partial` status
- the validator discarded the whole payload because of benign shape drift
- the final persisted stage output was an empty unresolved summary with no evidence, no URL, and no hypothesis preserved
- downstream consumers saw nothing, as if nothing was discovered

This is the central example that shapes the plan. The output was correct. The validator was wrong. The stage should have preserved the verified employer portal, the evidence, and the `partial` classification as its canonical artifact.

Decision impact (strong form):

- `application_surface` must **always produce a useful artifact** for downstream consumption — partial, negative, unresolved-but-evidenced, or fully resolved.
- Normalization must absorb benign shape drift; drift is not a rejection reason.
- `resolution_status=partial` must be first-class and fully persisted with its evidence.
- Negative findings (stale, closed, aggregator-only, no employer-safe URL) are valid first-class artifacts with evidence, not failure modes.
- “Unresolved” is a grounded outcome with reasons and intermediate conclusions, not an empty sentinel.
- The stage fails closed only on falsehood (fabricated URL, cross-company URL, guessed ATS deep link). It does not fail empty on incompleteness.

### 3.4 `research_enrichment` is producing better output than the schema permits

Observed result:

- stage completed end-to-end
- multiple live subpasses returned richer, grounded, source-attributed research
- the final persisted artifact remained unresolved / partial because the validator dropped that richer output

The richer output is not noise. It is the correct response to a prompt family that demands evidence, sources, and confidence. Treating it as drift reverses cause and effect.

Observed drift classes (reframed as value, not mismatch):

1. company research produced evidence-bearing objects:
- signals as `{name, value, confidence, evidence}` instead of bare strings
- canonical identity as `{value, confidence, excerpt}` instead of scalar strings
- this is strictly more useful for downstream reasoning, UI evidence surfacing, and audit

2. application merge attached grounded intermediate context:
- `application_surface_artifact`, `job_document_hints`, `company_profile` context blocks
- this is the merge stage citing what it merged from and why
- that provenance is exactly what later stages and operators need

3. role research produced richer nested structure:
- `summary`, `role_summary`, `why_now`, `company_context_alignment` as objects with status / confidence / evidence rather than bare strings
- this preserves what the model knows and how it knows it

4. stakeholder discovery used semantic aliases:
- `title` for `current_title`, `company` for `current_company`, `relationship` for `relationship_to_role`
- these are synonyms of canonical fields, not drift

Decision impact (strong form):

- The current scalar-only persisted schema is the drift; the richer live output is the target shape.
- 4.1.3.1 adopts richer-first: the canonical artifact evolves toward the richer shape, compact scalars are preserved as a reader/snapshot projection.
- Ingress normalization absorbs aliases, wrapper extras, and shape variation. It does not down-cast richness as a matter of policy.
- Aggressive down-flattening is explicitly rejected. Flattening belongs in snapshot/compat projections, not in canonical persistence.

## 4. 4.1.3.1 Core Decisions

### 4.1 Model Routing Decision

Recommended routing:

| Stage | Provider | Primary Model | Escalation | Fallback | Recommendation |
| --- | --- | --- | --- | --- | --- |
| `jd_facts` | Codex | `gpt-5.2` | none | none | Adopt as hard default |
| `classification` | Codex | `gpt-5.4-mini` | `gpt-5.2` | none | Keep as default |
| `application_surface` | Codex | `gpt-5.2` | none | none | Change from `gpt-5.4-mini` |
| `research_enrichment` | Codex | benchmark the exact Codex-available GPT-5.3 variant vs `gpt-5.2` vs `gpt-5.4-mini` | none | none | Choose via benchmark gate |

Decision details:

#### `jd_facts`

- Keep `gpt-5.2`
- no escalation
- no fallback

Reason:

- live evidence shows materially better structured extraction stability
- the stage is schema-heavy and failure cost is high
- extra cost is justified because `jd_facts` is foundational and called once per job

#### `classification`

- Keep `gpt-5.4-mini` as primary
- keep `gpt-5.2` as escalation only
- no fallback

Reason:

- current live run succeeded without escalation
- classification is bounded and comparatively cheap to keep on `gpt-5.4-mini`
- escalation remains useful for ambiguity / schema-failure edge cases without paying 5.2 cost on every job

#### `application_surface`

- move to `gpt-5.2`
- no escalation
- no fallback

Reason:

- URL safety and fail-open correctness matter more than raw token cost here
- the stage is low-frequency and high-consequence
- partial verified employer-portal acceptance must be stable and conservative

#### `research_enrichment`

Recommendation for 4.1.3.1:

- treat the exact Codex-available GPT-5.3 variant as the benchmark candidate for the full research bundle
- do not hard-pin production default to that GPT-5.3 variant until it passes acceptance gates
- if that GPT-5.3 variant does not clear those gates, use `gpt-5.2` for production hard-cut research until schema stability is achieved
- keep `gpt-5.4-mini` as the cost baseline and fallback benchmark baseline, not as the presumed winner

Reason:

- the user explicitly wants GPT-5.3 evaluated for all research subpasses
- we do not yet have live run evidence proving the available GPT-5.3 Codex variant is sufficient
- research quality must be judged on schema-acceptance rate, evidence quality, unresolved correctness, stakeholder safety, and cost

### 4.2 Cost Decision

Verified pricing comparison:

- GPT-5.2 input is about `2.33x` the cost of GPT-5.4 mini input
- GPT-5.2 output is about `3.11x` the cost of GPT-5.4 mini output

Therefore:

- using `gpt-5.2` everywhere is not justified by default
- use `gpt-5.2` where schema-fit, extraction stability, or verified-URL precision meaningfully outweighs cost
- keep `classification` on `gpt-5.4-mini`
- justify `application_surface` on `gpt-5.2`
- treat `research_enrichment` model choice as benchmark-gated

### 4.3 Schema Strategy Decision

Decision: **richer canonical, compact projections.** The canonical artifact is the rich one. Compact scalars exist as a projection for readers that have not yet migrated.

This is a deliberate reversal of the earlier hybrid posture that treated compact scalars as canonical and rich fields as optional detail. That posture is the drift.

The rules:

1. **Canonical truth is the rich, evidence-bearing form** where the live prompts naturally produce it:
- company identity, mission, product, business model, and signals carry `{value, confidence, evidence, sources}` wrappers
- company signals remain a collection of rich signal objects
- role summary / role_summary / why_now / company_context_alignment carry status, confidence, and evidence
- application findings carry resolution status, evidence, and intermediate conclusions
- stakeholder entries retain all source attribution and confidence metadata

2. **Compact aliases are a projection**, not the source of truth:
- `company_profile.summary`, `company_profile.url`, `company_profile.signals` (flat)
- `role_profile.summary`, `role_profile.role_summary`, `role_profile.why_now`
- `application_profile.canonical_application_url`
- compact stakeholder summary fields
- these are derived from the rich canonical artifact at write time for readers / snapshots
- they are not authoritative; if a reader needs nuance, it reads the rich canonical form directly

3. **Ingress is permissive on shape**, always:
- extras are accepted
- aliases (`title`, `company`, `relationship`, etc.) are mapped to canonical names without rejecting the payload
- scalar/list/dict coercions are performed at ingress, not refused
- null-to-unknown normalization is applied where semantics are obvious
- unknown but grounded wrappers are kept (preserved under a named rich field or structured debug slot) rather than stripped

4. **Ingress is strict on truth**, always:
- fabricated URLs, cross-company URLs, guessed ATS deep links → rejected
- fabricated dates or stakeholder identities → rejected
- private contact data, protected-trait inference → rejected
- low-confidence outreach guidance → rejected or down-weighted per policy
- safety validation is independent of shape validation and does not get relaxed

5. **Schema follows stable richer output.** If a richer shape shows up across live runs and proves stable and useful, promote it into the canonical model. Do not leave it as an ingress-only shape indefinitely, and do not force the model to flatten to match a thinner schema.

This means 4.1.3.1:

- treats richer grounded outputs as the target, not an exception
- preserves stable compact aliases as a reader convenience, clearly marked as a projection
- prevents unsafe fields from ever being persisted, regardless of shape
- does not let backward compatibility block the canonical from evolving toward the richer stable shape

### 4.4 `application_surface` Always-Find-Something Decision

Decision:

`application_surface` is no longer a pass/fail gate on exact canonical URL resolution. It is a stage whose job is to **always produce a grounded artifact** for downstream consumers — fully resolved, partially resolved, negatively resolved, or honestly unresolved with evidence. “Unresolved” is a finding, not an absence.

The stage must preserve and persist whichever of the following it discovered, in order of preference:

1. **Resolved**: exact, verified, employer-safe job-specific apply URL observed in fetched content or trusted search results.
2. **Partial (employer-portal success)**: verified employer jobs homepage or verified company-safe ATS landing page, even when the exact job-specific apply URL is not directly observed. `canonical_application_url` holds the employer jobs page; `resolution_status=partial`; evidence is preserved.
3. **Partial (ATS family inferred)**: portal family and/or ATS vendor inferred from grounded evidence (URL patterns, page content, structured signals), with confidence and the evidence chain preserved, even when no deep link is verified.
4. **Negative / stale / closed**: verified signal that the role is stale, closed, duplicate, or aggregator-only. This is a first-class output with evidence, not a failure.
5. **Unresolved-but-evidenced**: no employer-safe URL could be verified, but the intermediate evidence (what was fetched, what was rejected and why, which hypotheses were considered) is preserved. This is the minimum acceptable artifact — never an empty placeholder.

Shape rules for any of the above:

- benign shape drift (enum aliases, null-vs-literal, list-vs-scalar, object-vs-scalar) is normalized at ingress — never a reason to discard the finding.
- `ui_actionability` is normalized into the canonical vocabulary (`ready`, `caution`, `blocked`, `not_attempted`) rather than rejected.
- `geo_normalization` strings are accepted and wrapped; lists for `apply_instructions` are accepted and either persisted as list or projected to a compact alias.
- null state fields (`stale_signal`, `closed_signal`, `duplicate_signal`) are normalized to explicit `unknown` / empty-object forms.
- `resolution_note` explicitly states what was found, what was not, and why — enough for an operator to understand the artifact without rerunning.

The stage fails closed only on falsehood:

- fabricated job URLs → rejected
- guessed ATS probe URLs not grounded in evidence → rejected
- cross-company links → rejected
- inferred or synthesized exact job-specific apply pages presented as verified → rejected

The stage never fails empty on incompleteness. If the only honest answer is “no verified employer URL, here is what we tried and what we saw,” that is a valid persisted artifact and must be retained in full.

### 4.5 Reasoning Effort Decision

Current decision:

- do not rely on CLI reasoning-effort tuning in production until the actual Codex CLI path is verified
- default reasoning effort remains whatever the Codex CLI is already using in this repo path
- add an explicit 4.1.3.1 spike to verify whether reasoning effort can be passed through `codex exec -c ...`

Reason:

- official model docs support reasoning effort
- local CLI help does not expose a first-class flag
- the repo uses CLI invocation, not direct API transport
- shipping unverified config assumptions would create another hidden drift source

## 5. Why `research_enrichment` Returned a Richer Schema

This behavior is expected.

The 4.1.3 prompt family instructs the model to:

- include sources for every claim
- include evidence arrays
- include confidence objects
- emit status-aware partial / unresolved subdocuments

When given that contract, the model naturally upgrades scalar fields into evidence-bearing wrappers.

Examples:

- plain `summary` becomes `{status, text, confidence, evidence}`
- plain identity strings become `{value, confidence, excerpt}`
- signal strings become `{name, value, confidence, evidence}`

That means the model is not merely “overcomplicating the output”.
It is trying to satisfy the richer evidence discipline that the prompt requires.

4.1.3.1 therefore treats this as contract mismatch, not raw model error.

## 6. Detailed 4.1.3.1 Architecture

### 6.1 Two-Layer Validation

Introduce two distinct layers with clearly separated responsibilities:

1. **Ingress response models** — permissive on shape:
- prompt-specific
- alias-aware (`title`, `company`, `relationship`, etc. accepted as synonyms)
- extra-tolerant (unknown-but-grounded wrappers preserved, not stripped)
- scalar/list/dict coercions performed here
- null-to-literal normalization performed here
- richer wrappers (e.g. `{value, confidence, evidence}`) accepted as-is and carried forward

2. **Persisted canonical models** — strict on truth, rich on shape:
- the canonical shape is the richer, evidence-bearing shape where the prompts naturally produce it
- safety rules enforced (no fabricated URLs/identities, no cross-company links, no private/protected-trait content, no low-confidence outreach guidance)
- compact aliases are **derived projections** written alongside the rich canonical, not the primary persisted form
- consumer stability is provided by the compact projection layer, not by forcing the canonical to stay scalar

This is the main architectural correction: the ingress layer does not down-cast richness, and the persisted layer does not pretend compact scalars are truth.

### 6.2 Canonical Schema Changes

Guiding rule for every subsection below: the **rich fields are canonical**, and the compact scalar fields are derived projections kept for reader convenience during migration.

#### Company

Canonical (rich) fields:

- `identity` — evidence-bearing `{value, confidence, excerpt, sources}`
- `mission`, `product`, `business_model` — evidence-bearing structured fields
- `signals` — list of `{name, value, confidence, evidence, sources}` objects (rich signal is the canonical signal form)
- `recent_signals`, `role_relevant_signals` — list of rich signal objects
- `canonical_name`, `canonical_domain`, `canonical_url` — still stored; accepted at ingress as either plain strings or evidence-bearing wrappers

Compact projections (written alongside canonical for readers):

- `summary` — derived compact string (snapshot / compat)
- `url` — derived from canonical identity / canonical_url
- `signals_compact` — flat list of display strings derived from rich signals
- projections are rewritten every time the rich canonical is updated

#### Role

Canonical (rich) fields:

- `summary`, `role_summary`, `why_now`, `company_context_alignment` — stored as `{status, text, confidence, evidence, sources}` objects when the live prompt produces them
- when the model returns only a string, ingress wraps it into the rich shape so downstream consumers see a uniform form

Compact projections (written alongside canonical):

- `summary_text`, `role_summary_text`, `why_now_text`, `company_context_alignment_text` — derived strings for readers that cannot yet consume the rich form

#### Application

The application profile follows the same rule: the rich artifact is canonical, and the compact scalar view is a projection.

Canonical fields (rich where useful):

- `job_url`
- `canonical_application_url` — with provenance: `{value, source, confidence, observed_at}`
- `resolution_status` — one of `resolved`, `partial`, `negative`, `unresolved_evidenced`
- `resolution_note` — a grounded explanation of what was found and what was not
- `portal_family`, `ats_vendor` — with confidence and evidence
- `ui_actionability` — canonical vocabulary (`ready`, `caution`, `blocked`, `not_attempted`), normalized from aliases at ingress
- `final_http_status`
- `geo_normalization` — canonical as object; string inputs coerced at ingress
- `apply_instructions` — canonical as list; string inputs coerced at ingress; compact display alias derived for readers
- `apply_caveats`
- `stale_signal`, `closed_signal`, `duplicate_signal` — canonical as structured objects with status + evidence; null inputs normalized to `{status: "unknown"}` at ingress
- `evidence` — the intermediate evidence the stage gathered, preserved even when the result is `unresolved_evidenced`
- `hypotheses` — the portal/ATS hypotheses considered, with confidence and why each was accepted or rejected

Canonical posture:

- shape drift is always absorbed at ingress
- any verified employer-safe finding is preserved in full
- negative and unresolved outcomes retain their evidence and intermediate conclusions

#### Stakeholders

Canonical field names:

- `current_title`, `current_company`, `relationship_to_role`

Ingress alias normalization (always applied, never rejected):

- `title -> current_title`
- `company -> current_company`
- `relationship -> relationship_to_role`
- any additional evidence-bearing wrappers around these fields are preserved as companion richer forms

Rich canonical:

- every stakeholder entry carries `sources`, `confidence`, and evidence as part of the canonical artifact (not as optional metadata)
- medium/high identity gating stays strict; safety validation is independent of shape normalization

### 6.3 Normalization Rules

4.1.3.1 must add explicit normalization tables. The posture is: **absorb drift, preserve grounding**.

#### `application_surface` enum aliases

- `applyable -> ready`
- `actionable -> ready`
- `unavailable -> not_attempted` or `blocked` depending on whether fetch was attempted
- `null stale_signal -> {status: "unknown"}`
- `null closed_signal -> {status: "unknown"}`
- `null duplicate_signal -> {}`

#### scalar/list coercions

- `apply_instructions: string | list[string]` → canonical `list[string]`; compact string projection derived for readers
- `geo_normalization: string` → canonical object `{"raw": <string>}`
- `summary / role_summary / why_now / company_context_alignment`:
  - string input → canonical rich object `{status: "stated", text: <string>, confidence: "unknown", evidence: [], sources: []}`
  - object input → preserved as-is (canonical)
  - compact string projection derived from canonical for readers

#### extra-field handling

For every subpass, useful extras are:

- accepted at ingress
- mapped into canonical rich fields where a mapping exists
- preserved under a named companion slot (e.g. `merge_debug`, `research_debug`, `surface_debug`) when they are grounded but not yet canonical
- **never silently dropped**
- never rejected via blanket `extra="forbid"` at ingress

Drop decisions happen only after explicit review of real live-run evidence, not as a default policy.

### 6.4 Prompt Contract Changes

Prompts are updated to make the richer, evidence-bearing shape the **expected** output, not an exception. They also explicitly give `application_surface` permission to preserve partial and negative findings as first-class results.

Prompt changes required:

- `P-application-surface`
  - explicitly require one of: `resolved`, `partial`, `negative`, `unresolved_evidenced`
  - explicitly allow employer jobs landing page as canonical partial success
  - explicitly allow verified aggregator-only or stale/closed results as canonical negative success
  - require preserved evidence and intermediate conclusions even in the unresolved case
  - align enum vocabulary (`ui_actionability`, `form_fetch_status`, `resolution_status`) to canonical accepted values; document aliases that the ingress layer will normalize
- `P-research-company`
  - emit rich evidence-bearing fields as the canonical shape (signals as rich objects, identity with excerpt and confidence)
- `P-research-role`
  - emit rich evidence-bearing fields (`summary`, `role_summary`, `why_now`, `company_context_alignment`) as canonical; ingress will derive compact strings
- `P-research-application-merge`
  - the merge may emit grounded intermediate context (`application_surface_artifact`, `job_document_hints`, `company_profile` context); those are preserved under a `merge_debug` slot when not part of canonical, never stripped
- `P-stakeholder-discovery`
  - emit canonical names where possible; ingress maps aliases (`title`, `company`, `relationship`) without rejection
  - always emit `sources`, `confidence`, and evidence at the entry level

### 6.5 Validator Safety Rules

Validation is **loose on shape and strict on truth**. Shape validation and truth validation are separate concerns; they never borrow leniency from each other.

Loose on shape (always applied at ingress):

- aliases accepted and mapped
- richer evidence-bearing wrappers accepted and preserved
- nulls normalized where semantics are obvious (e.g. null state signals → `{status: "unknown"}`)
- extra context fields tolerated, preserved in a named companion slot when they carry grounded information
- list/scalar/dict coercions performed
- unknown-but-grounded wrappers carried forward rather than stripped

Strict on truth (always enforced, independent of shape):

- no fabricated URLs
- no fabricated dates
- no fabricated stakeholder identities
- no cross-company application URLs
- no guessed ATS deep links presented as verified
- no low-confidence outreach guidance
- no protected-trait or private-contact leakage
- no synthesized exact job-specific apply pages when only a landing page was observed

## 7. Research Model Evaluation Plan

### 7.1 Benchmark Matrix

Evaluate these candidates for `research_enrichment`:

- `gpt-5.4-mini`
- the exact Codex-available GPT-5.3 variant
- `gpt-5.2`

Subpasses to evaluate separately:

- company profile
- application merge
- role profile
- stakeholder discovery
- stakeholder profile
- outreach guidance

### 7.2 Acceptance Criteria

The exact Codex-available GPT-5.3 variant is good enough for all research subpasses only if it meets all of:

- schema-acceptance rate >= `95%` after ingress normalization
- no critical fabricated-URL violations
- no critical stakeholder identity violations
- company factuality >= `gpt-5.4-mini` baseline
- role factuality >= `gpt-5.4-mini` baseline
- stakeholder medium/high precision >= baseline
- unresolved-handling correctness >= `95%`
- reviewer usefulness for UI / inference / outreach handoff >= baseline
- cost materially better than `gpt-5.2`

If the GPT-5.3 benchmark candidate fails those gates:

- do not make it the default production research model
- promote `gpt-5.2` for research production hard cutover until a cheaper model proves stable enough

### 7.3 Where Higher Cost Is Worth Paying

`gpt-5.2` cost is justified for:

- `jd_facts`
- `application_surface`
- possibly `research_enrichment` if benchmark shows materially better schema-fit and safer fail-open behavior

`gpt-5.2` is not justified by default for:

- `classification`

## 8. Codex CLI Reasoning-Effort Validation Plan

### 8.1 Current Answer

At planning time:

- official model docs say reasoning effort is supported
- local Codex CLI help does not expose a first-class reasoning-effort flag
- CLI does expose `-c key=value` config overrides

Therefore the repo cannot yet assume reasoning-effort tuning is wired.

### 8.2 Required Validation Spike

Before relying on reasoning effort in 4.1.3.1:

1. identify the exact supported Codex CLI config key from official docs for the installed CLI version
2. run a no-op validation command with `codex exec --json -c <verified_key>=\"low\" ...`
3. run the same with `high` and `xhigh`
4. verify the emitted JSONL events or stderr explicitly confirm the selected reasoning effort
5. record the working config key and proof output in:
   - `scripts/preenrich_model_preflight.py`
   - rollout docs
   - the relevant decision record

### 8.3 Use Recommendation

Do not use reasoning-effort differentiation in production 4.1.3.1 unless the above spike succeeds.

If it succeeds:

- keep `classification` at low or medium
- keep `jd_facts` at medium first
- evaluate higher reasoning effort only for:
  - `application_surface`
  - stakeholder discovery
  - role/company research if benchmark shows real benefit

## 9. Hard Migration Plan

Guiding bias: **the canonical rich artifact is the destination.** Compatibility projections exist to keep readers working during migration, not to prevent the canonical from evolving. Where there is tension between preserving a compat projection and preserving a richer canonical truth, the canonical truth wins.

### Phase 0: Planning and decision freeze

Deliverables:

- this 4.1.3.1 plan
- architecture update
- decision record update
- missing/gap update

### Phase 1: Ingress normalization and always-find-something fixes

Update:

- `src/preenrich/blueprint_models.py`
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/stages/application_surface.py`
- `src/preenrich/stages/research_enrichment.py`

Goals:

- accept richer grounded live outputs as the canonical artifact
- make `application_surface` always produce a useful artifact (resolved / partial / negative / unresolved-evidenced)
- preserve strict truth safety
- emit compat projections from the rich canonical, not as a competing source of truth

### Phase 2: Reader cutover to canonical research

Switch first-order consumers to read the rich canonical artifact:

- `job_inference`
- `blueprint_assembly`
- job detail research partials
- `outreach_service`
- any live `people_mapper` readers

Goals:

- downstream readers see the rich form directly
- compat projections remain only for readers that genuinely cannot yet consume rich structure
- new consumers added in this iteration read canonical from the start — they do not add new compat dependencies

### Phase 3: Compat contraction

After stable canonical-read rollout:

- stop adding new consumer dependencies on top-level `company_research`, `role_research`, and `application_url`
- keep projection writes only for documented, named temporary readers
- mark the projection fields as retirement surfaces in docs
- any tension between a compat projection and a richer canonical field resolves toward the canonical

### Phase 4: Hard migration

After benchmark and live-run gates pass:

- remove V1 enablement paths for:
  - `jd_facts`
  - `classification`
  - `research_enrichment`
- make the rich canonical outputs authoritative
- remove long-lived shadow-mode expectations from rollout docs
- promote any ingress-only rich shapes that have proven stable into the canonical model

### Phase 5: Compatibility retirement

Only after all direct readers migrate:

- stop live compat writes
- delete deprecated V1 enablement flags
- remove thin legacy scalar projections where no live readers remain
- the rich canonical becomes the only persisted form

## 10. Files and Surfaces 4.1.3.1 Must Update

### Plans / docs

- `plans/research-enrichment-4.1.3.1-live-codex-hard-cutover-and-schema-alignment.md`
- `docs/current/architecture.md`
- `docs/current/missing.md`
- new decision record for 4.1.3.1 routing and schema strategy

### Core models / prompts / stages

- `src/preenrich/blueprint_models.py`
- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/research_transport.py`
- `src/preenrich/stages/application_surface.py`
- `src/preenrich/stages/research_enrichment.py`
- `src/preenrich/stages/classification.py`
- `src/preenrich/types.py`
- `src/preenrich/blueprint_config.py`
- `scripts/preenrich_model_preflight.py`
- `scripts/benchmark_research_enrichment_4_1_3.py`

### Downstream migration surfaces

- `src/preenrich/stages/job_inference.py`
- `src/preenrich/stages/blueprint_assembly.py`
- `frontend/app.py`
- `frontend/templates/job_detail.html`
- job-detail research partials
- `frontend/static/js/job-detail.js`
- `src/services/outreach_service.py`
- any artifact/snapshot readers still using thin top-level compat research

## 11. Validation and Benchmark Plan

### 11.1 Unit tests

Add or update:

- ingress alias normalization tests (company/role/stakeholder aliases absorbed, never rejected)
- `application_surface` always-find-something tests:
  - resolved exact URL preserved
  - partial employer-portal preserved with evidence
  - negative / stale / closed / aggregator-only preserved with evidence
  - unresolved-evidenced preserved with evidence and intermediate conclusions
  - empty unresolved result is a test failure
- rich-wrapper preservation tests for company / role / stakeholder payloads (the rich shape is the canonical persisted shape)
- compact projection derivation tests (compact aliases derived correctly from rich canonical)
- strict URL safety tests (fabricated, cross-company, synthesized deep links still rejected)
- strict stakeholder confidence gating tests
- `jd_facts` model-routing tests
- classification escalation-routing tests
- reasoning-effort config validation tests once the CLI key is verified

### 11.2 Integration tests

Add or update:

- live-style payload replay tests from the Robson Bale run
- `application_surface -> research_enrichment` merge tests with partial canonical application URL
- canonical-read tests for `job_inference`
- compact snapshot tests with richer canonical detail preserved off-snapshot
- compat projection correctness during transition

### 11.3 Benchmarks

Benchmark dimensions must include:

- schema acceptance after normalization
- canonical URL exactness / partial correctness
- company factuality
- role factuality
- stakeholder precision at medium/high
- unresolved-handling correctness
- privacy/safety violations
- compact snapshot usefulness
- cost per job by model
- latency per subpass by model

### 11.4 Production gates

Do not hard-cut `research_enrichment` until:

- live schema-acceptance rate for rich canonical shapes is high enough
- partial employer-portal URLs and unresolved-evidenced artifacts are preserved correctly
- no critical fabricated URL or stakeholder issues are observed
- downstream readers can consume the rich canonical outputs directly
- `application_surface` never produces an empty unresolved artifact across the live-run sample

## 12. Plan-Updating Discipline During Development

The plan itself must be updated during active implementation.

Required process:

1. after each live run, append:
   - job id
   - model route
   - durations
   - accepted outputs
   - rejected outputs
   - drift class
   - code / prompt change made in response

2. after each model-routing change, record:
   - exact stage
   - exact model
   - escalation / no escalation
   - fallback / no fallback
   - rationale

3. after each validator change, record:
   - shape drift accepted
   - normalization rule added
   - safety rule preserved

4. after each benchmark run, append:
   - model matrix
   - corpus
   - pass/fail thresholds
   - cost and latency

5. after each downstream reader cutover, record:
   - reader switched
   - compat field still needed or retired

Plan drift prevention rule:

- the plan is part of the implementation surface for 4.1.3.1
- if prompt contracts or canonical field names change, the plan must be updated in the same change window

## 13. Development Prompt for In-Flight Plan Updates

Use this prompt during 4.1.3.1 implementation whenever live testing or prompt tuning changes the plan:

```text
You are updating the active implementation plan for Iteration 4.1.3.1 during development.

Read:
- plans/research-enrichment-4.1.3.1-live-codex-hard-cutover-and-schema-alignment.md
- docs/current/architecture.md
- docs/current/missing.md
- current changed code in src/preenrich/

Then update the plan to reflect the latest real evidence.

You must:
- append the latest live run results
- record exact model routing used per stage
- record prompt/schema/validator mismatches discovered
- record normalization rules added
- record benchmark outcomes and pass/fail decisions
- record any compatibility fields that are no longer needed
- keep the plan aligned with the actual code, not the previous intent

Do not summarize only.
Edit the plan concretely.
If a previous plan statement is now wrong, replace it.
If a migration phase has been completed, mark it completed and state what remains.
If a new failure mode appears, add it to the relevant phase and validation section.
```

## 14. Final Recommendation

4.1.3.1 is executed as a **richer-first** hardening and hard-cutover-prep slice with these defaults:

- `jd_facts`: `gpt-5.2`, no escalation, no fallback
- `classification`: `gpt-5.4-mini` primary, `gpt-5.2` escalation, no fallback
- `application_surface`: move to `gpt-5.2`, no fallback, always produces a useful artifact (resolved / partial / negative / unresolved-evidenced); evidence preserved in every case
- `research_enrichment`: benchmark the exact Codex-available GPT-5.3 variant across all research subpasses; use it only if it clears explicit acceptance gates

Schema strategy is **richer canonical, compact projections**:

- the rich evidence-bearing shape is the canonical persisted artifact
- compact scalar aliases are derived projections written alongside, not authoritative
- ingress validation is permissive on shape and absorbs drift
- persisted truth validation remains strict on safety and factuality
- when a richer shape proves stable in live runs, the canonical schema evolves toward it rather than forcing flattening

Migration strategy is hard and canonical-biased:

- canonical rich artifact first
- downstream reader cutover to the rich canonical next
- compatibility contraction after that (compat is for reader transition, not for constraining canonical truth)
- V1 retirement after stable canonical-read rollout

## 14a. Invariants That 4.1.3.1 Must Encode

These invariants are load-bearing. Any prompt, validator, stage, or reader change that contradicts them is a drift and must be rejected in review.

1. **Richer grounded output is better than prematurely flattened output.** The pipeline prefers the richer shape at every boundary where the model produces it.
2. **Validation is loose on shape and strict on truth.** Shape drift is normalized; safety drift is rejected.
3. **`application_surface` always produces a useful artifact.** The stage classifies every run as `resolved`, `partial`, `negative`, or `unresolved_evidenced`, never as empty.
4. **`unresolved` is not the same as `empty`.** Unresolved outcomes carry evidence and intermediate conclusions; they are grounded artifacts.
5. **Stable richer shapes drive canonical evolution.** If a richer shape proves stable across live runs, the canonical schema evolves toward it; the model is not forced to flatten indefinitely.
6. **Compat aliases are for readers, not for canonical truth.** They are derived projections for migration and snapshots; they never constrain the canonical artifact.
7. **Preserve grounded intermediate structure** even when the schema is thinner than the model output. Do not discard richness to match a thinner schema.
8. **Bias toward direct canonical consumption.** New readers read the rich canonical artifact; legacy scalar compatibility is a finite-lifetime transition, not a permanent contract.

## 15. Appendices

### Appendix A: Live Run Evidence Snapshot

Job:

- `_id = 69e63f7e12725d7147cc499c`
- `Lead AI Engineer`
- `Robson Bale`

Observed route:

- `jd_facts`: `gpt-5.2`, no escalation, no fallback
- `classification`: `gpt-5.4-mini`, escalation configured to `gpt-5.2`, no fallback
- `application_surface`: `gpt-5.4-mini`, Codex web search, no fallback
- `research_enrichment`: `gpt-5.4-mini`, Codex web search, no fallback

Observed durations:

- `jd_facts`: about `118.75s`
- `classification`: about `30.91s`
- `application_surface`: about `206.0s`
- `research_enrichment`: about `524.41s`

Observed failures:

- `application_surface` rejected a useful employer-jobs-portal result because of schema drift
- `research_enrichment` rejected useful company / role / application / stakeholder payloads because of wrapper and alias drift

### Appendix B: External Model / CLI Facts

- GPT-5.4 mini pricing:
  - `https://openai.com/index/introducing-gpt-5-4-mini-and-nano/`
  - `https://openai.com/api/pricing/`
- GPT-5.2 pricing:
  - `https://openai.com/index/introducing-gpt-5-2`
  - `https://platform.openai.com/docs/pricing/`
- GPT-5.2 Codex reasoning effort:
  - `https://platform.openai.com/docs/models/gpt-5.2-codex`
  - `https://platform.openai.com/docs/guides/latest-model`
- local CLI evidence:
  - `codex exec --help` shows `-c key=value` config overrides
  - no explicit `--reasoning-effort` flag was present in the local help output
