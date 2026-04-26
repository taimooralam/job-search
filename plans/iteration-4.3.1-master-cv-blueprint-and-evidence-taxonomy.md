# Iteration 4.3.1 Plan: Master-CV Blueprint and Evidence Taxonomy

## 1. Executive Summary

The master-CV is the evidence base for everything downstream of `cv_ready`:
headers, per-role bullets, key achievements, core competencies, cover
letters, and dossiers. Its current shape — six role markdown files, two
project markdowns, two project skills JSONs, one `role_metadata.json`, and
one `role_skills_taxonomy.json` — is enough for today's single-pass Layer 6
V2 generator, but it is not rich enough to drive evaluator-aware,
pattern-anchored candidate generation safely.

4.3.1 upgrades the master-CV blueprint to carry explicit metadata that the
later 4.3 stages need to reason about, with first-class provenance and
evidence confidence markers. It adds per-role and per-project metadata
sidecars, extends the role metadata index, and introduces a small family of
new taxonomies (identity, leadership, industry, domain, operating-model,
credibility-marker) that make presentation-contract reasoning actionable.

This plan is a schema and migration plan, not a prose rewrite of anyone's
career. No achievement content is invented. Every new field is either
directly extracted from existing markdown, lifted from public factual
references (dates, team sizes, named systems), or marked `unresolved` with
a confidence band that deterministically downstreams prevent from being
used as a claim.

## 2. Mission

Make the master-CV rich enough, explicit enough, and provenance-tagged
enough that every downstream 4.3 stage can ground every claim it emits in a
specific, checkable piece of evidence — without loss of existing prose
content and without inventing career facts.

## 3. Objective

Define and ship:

- an extended role record schema with scope/scale/seniority/stakeholder/
  domain/AI-relevance/reliability/platform metadata;
- an extended project record schema with business-impact/architecture/
  reliability/scale/AI-relevance metadata;
- six new taxonomies (identity, leadership, industry, domain, operating-
  model, credibility-marker) alongside the existing role and skill
  taxonomies;
- a per-role and per-project sidecar metadata file pattern;
- a deterministic backfill strategy that fills unambiguous fields from
  existing markdown and flags ambiguous fields for manual review;
- a provenance / confidence / traceability field layout that every 4.3
  consumer honors;
- a frozen eval corpus under `data/eval/validation/cv_assembly_4_3_1_master_cv/`
  that benchmarks loader behavior and change detection.

## 4. Success Criteria

4.3.1 is done when:

- every role in `data/master-cv/roles/` has a sibling
  `<id>.meta.json` with the full metadata schema populated, `unresolved`
  where appropriate, and no fabricated fields;
- every project in `data/master-cv/projects/` has a sibling
  `<id>.meta.json` with the full metadata schema populated;
- six new taxonomy files exist under `data/master-cv/taxonomies/`,
  versioned, stable-slug-keyed, and with evidence confidence fields on
  every entry;
- `cv_loader.load()` returns a `CandidateData` whose `RoleData`
  instances expose the new metadata, and whose `CandidateData.projects`
  is a typed list (new) with the new project metadata;
- the deterministic evidence validator used by 4.3.2–4.3.5 can resolve
  every structured claim it receives to a `(role_id | project_id,
  achievement_id?, variant_id?, source_fragment_ref?)` tuple;
- the 4.3.1 backfill dry-run reports zero silent fabrications and
  produces an identical report on two consecutive runs;
- the loader regression eval passes with 100% schema validity on the
  frozen corpus.

## 5. Non-Goals

- Rewriting the prose of any role or project markdown.
- Adding new achievements or new variants.
- Moving master-CV storage fully to Mongo (MongoDB remains optional; the
  file tree remains authoritative).
- Normalizing per-role bullet text.
- Introducing multi-candidate support.
- Changing the variant parsing format in enhanced role files.
- Touching the CV Editor UI (a follow-up plan).

## 6. Why This Artifact Exists

Today the master-CV encodes:

- role identity (company, title, period, industry, team size);
- achievements and variants;
- skill lists (`hard_skills`, `soft_skills`);
- a per-target-role taxonomy with persona guidance and competency
  sections.

It does not encode:

- role **scope** (reports_count, dotted_line_count, cross-team reach,
  budget);
- role **leadership signals** (managerial level, whether direct reports
  were ICs or managers, performance-reviews authored, hiring involvement);
- role **stakeholder exposure** (C-level, VP, board, external partner,
  customer-facing);
- role **business impact** markers tied to evidence
  (revenue-adjacent, cost-adjacent, reliability-adjacent, compliance-
  adjacent);
- role **AI relevance** beyond keyword presence (AI intensity band,
  whether AI systems were owned end-to-end or consumed, model family
  exposure, data-side or serving-side exposure);
- role **platform/scaling/change** evidence (QPS ceilings, SLO targets
  owned, migrations led, fleet size);
- role **identity** anchors (operator, architect, builder, leader,
  transformation, platform, execution — same enum as
  `ideal_candidate_presentation_model.tone_profile`);
- role **operating model** (delivery cadence, ownership model, on-call
  rotation, incident ownership);
- role **credibility markers** (named systems owned, named stacks
  deployed, named frameworks authored);
- per-field **evidence confidence** (how strongly the claim is backed —
  directly stated in the role doc, inferred, or unresolved);
- per-field **source fragment references** (which line or paragraph in
  the role markdown is the source, so the evidence validator can
  spot-check);
- **domain exposure** (which industries, which domains, which regulatory
  regimes);
- **geography / visa / availability / disclosure scope** (limited to
  fields already supported by the status quo — nationality, languages,
  remote posture).

Without this metadata, the pattern selector cannot defensibly pick three
distinct patterns from the same career story, the header blueprint cannot
commit to a visible identity, and the grader cannot check for
hallucination with deterministic rules. Everything ends up re-derived
from raw markdown at every stage, which is both expensive and unreliable.

## 7. Stage Boundary

### 7.1 Repository layout after 4.3.1

```text
data/master-cv/
  role_metadata.json                      # extended (index + candidate profile)
  role_skills_taxonomy.json               # extended (per-target persona + credibility)
  roles/
    01_seven_one_entertainment.md         # prose (unchanged)
    01_seven_one_entertainment.meta.json  # NEW — per-role metadata sidecar
    ...
  projects/
    commander4.md
    commander4.meta.json                  # NEW — per-project metadata sidecar
    commander4_skills.json                # unchanged
    lantern.md
    lantern.meta.json                     # NEW
    lantern_skills.json                   # unchanged
  taxonomies/                             # NEW
    identity_taxonomy.json
    leadership_taxonomy.json
    industry_taxonomy.json
    domain_taxonomy.json
    operating_model_taxonomy.json
    credibility_marker_taxonomy.json
```

Prose markdown stays authoritative for achievements and text. Sidecars
own structured metadata. Splitting keeps the prose uncluttered and lets
metadata evolve without risking prose edits.

### 7.2 Loader boundary

- `src/layer6_v2/cv_loader.py` is extended to read sidecars alongside
  markdown and merge them into `RoleData` as `.metadata: RoleMetadata`.
- `src/common/master_cv_store.py` is extended to expose the same shape in
  MongoDB-backed mode, using the same metadata schema.
- A new `CandidateData.projects: List[ProjectData]` is added. Today
  projects are implicitly referenced in role content; 4.3.1 makes them
  first-class so the pattern selector and evidence map can cite them
  directly.
- All 4.3 consumers read from the loader, never from the file system
  directly.

### 7.3 Snapshot invalidation

`master_cv_checksum = sha256(sort_json(roles_meta || projects_meta ||
taxonomies || role_metadata_index))`, refreshed at loader time, pinned
into every 4.3 stage work-item `payload.master_cv_checksum`. Mid-flight
master-CV edits invalidate in-flight drafts using the iteration-4
snapshot invalidation mechanism (§6.6 of the umbrella), identical shape.

## 8. Inputs

### 8.1 Authoritative inputs (unchanged by 4.3.1)

- `data/master-cv/roles/*.md`
- `data/master-cv/projects/*.md`
- `data/master-cv/projects/*_skills.json`

### 8.2 Sources for the new metadata

- Existing role markdown content — factual dates, named systems, team
  sizes, stakeholder mentions that are directly present in prose.
- Existing `role_metadata.json` — already encodes industry, team_size,
  duration_years, primary_competencies, keywords, career_stage.
- Explicit candidate-provided facts (new `candidate_facts.yml` at the
  root of `data/master-cv/` to capture identity, regional
  availability, nationality, visa facts, disclosure scope — all fields
  already supported by status quo candidate data).
- Nothing else. No web scraping, no LLM guessing, no inference.

### 8.3 Opportunistic inputs for inference checks (advisory only)

- 4.2 `stakeholder_surface` outputs from past jobs (for evaluator-axis
  learning only — never to inject evaluator preferences back into the
  master-CV).
- 4.2 `classification.ai_taxonomy.intensity` distribution across past
  jobs (advisory band, never writeback).

These are advisory signals only. They cannot write to the master-CV.

## 9. Output Shape / Schema Direction

### 9.1 `RoleMetadata` (per-role sidecar)

```text
RoleMetadata {
  role_id,                             # stable slug; must match filename
  schema_version,                      # "1"
  identity {
    tone_profile {                     # mirrors 4.2.4 tone_profile dimensions
      operator,        # 0..1
      architect,
      builder,
      leader,
      transformation,
      platform,
      execution
    },
    identity_tags[],                   # refs to identity_taxonomy ids
    disclaimer_markers[]               # e.g. "not_a_people_manager"
  },
  scope {
    headcount_total,                   # nullable int
    direct_reports_total,              # nullable int
    indirect_reports_total,            # nullable int
    budget_usd_per_year,               # nullable int
    cross_team_reach,                  # nullable enum: squad | team | multi_team | org | company
    geographies[],                     # ISO country codes / region codes
    operating_hours_span,              # nullable enum: single_tz | two_tz | follow_the_sun
    fleet_size,                        # nullable enum: none | small | medium | large | very_large
    qps_ceiling_band,                  # nullable enum: n_a | low | medium | high | very_high
    data_volume_band                   # nullable enum: n_a | low | medium | high | very_high
  },
  seniority {
    managerial_level,                  # enum: ic | tl | em | sem | dir | head | vp | c_level
    ic_band,                           # enum: junior | mid | senior | staff | principal | distinguished | n_a
    managerial_span,                   # enum: none | squad | multi_squad | multi_team | org
    managed_levels[],                  # enum: ic | tl | em | sem | dir
    performance_reviews_authored,      # bool
    hiring_involvement,                # enum: none | interviewer | bar_raiser | hiring_manager
    on_call_rotation                   # enum: none | secondary | primary | owner
  },
  management_enablement {
    coaching_cadence,                  # enum: none | ad_hoc | weekly_1_1 | structured_program
    enablement_artifacts[],            # refs to named playbooks / onboarding docs
    team_growth,                       # enum: none | partial | full_cycle
    promotions_authored                # nullable int
  },
  stakeholder_exposure {
    c_level,                           # enum: none | rare | frequent | standing
    vp_level,                          # same enum
    board,                             # same enum
    external_partners,                 # same enum
    customer_facing,                   # same enum
    procurement_involvement,           # enum: none | input | negotiator | owner
    legal_privacy_involvement          # enum: none | input | reviewer | owner
  },
  business_impact {
    revenue_adjacent,                  # bool
    cost_adjacent,                     # bool
    reliability_adjacent,              # bool
    compliance_adjacent,               # bool
    growth_initiative,                 # bool
    transformation_program             # bool
  },
  platform_architecture {
    delivery_model,                    # enum: monolith | service_oriented | microservices | platform | serverless | mixed
    architecture_influence,            # enum: contributor | reviewer | co_author | owner
    systems_named[],                   # credibility-marker refs
    migrations_led[],                  # migration_taxonomy refs
    sre_ownership                      # enum: none | on_call | slo_owner | platform_owner
  },
  ai_relevance {
    intensity_band,                    # enum: none | adjacent | significant | core
    model_families_touched[],          # refs (e.g. llama, gpt, claude) — not free text
    modalities[],                      # enum: text | vision | audio | multimodal | tabular
    serving_side,                      # bool
    data_side,                         # bool
    evaluation_side,                   # bool
    owned_ai_systems[],                # system refs (must match credibility markers)
    agentic_systems,                   # bool
    retrieval_systems,                 # bool
    fine_tuning_exposure               # enum: none | prompt_engineering | finetuning | rlhf
  },
  soft_hard_skills {
    hard_skills[],                     # slug refs to role_skills_taxonomy skill ids
    soft_skills[],                     # slug refs to role_skills_taxonomy skill ids
    evidence_for_skill {<skill_id>: [achievement_id, ...]}
    skill_surface_authorization {      # which surfaces the skill may appear on
      <skill_id>: [
        core_competency | summary_safe | experience_only | regional_optional
      ]
    }
  },
  domain_depth {
    industries[],                      # refs to industry_taxonomy ids
    domains[],                         # refs to domain_taxonomy ids
    regulatory[],                      # e.g. gdpr, hipaa — taxonomy-backed
    locale_coverage[]
  },
  operating_model {
    methodology,                       # refs to operating_model_taxonomy ids
    cadence,                           # enum: continuous | weekly | biweekly | monthly | ad_hoc
    ownership_model,                   # enum: individual | shared | platform_as_service
    on_call_discipline                 # enum: none | weekly | 24x7
  },
  credibility_markers[] {              # list, each is a credibility_marker_taxonomy ref
    marker_id,
    evidence_ref,                      # achievement_id or source_fragment_ref
    confidence: ConfidenceDoc
  },
  geography_availability {
    eligible_countries[],              # ISO codes — from candidate_facts
    visa_status,                       # enum: citizen | permanent_resident | work_permit | none
    remote_posture,                    # enum: remote | hybrid | on_site | flexible
    disclosure_scope                   # enum: public | limited | private
  },
  achievements[] {
    achievement_id,                    # stable slug within this role
    summary_ref,                       # source_fragment_ref into the role markdown
    variants[] {
      variant_id,                      # stable slug
      variant_type,                    # technical | architecture | impact | leadership | short
      source_fragment_ref
    },
    proof_categories[],                # canonical 4.2.3 proof-category enum
    dimensions[],                      # canonical 4.2.5 dimension enum
    credibility_markers[],             # refs
    ai_relevance_band,                 # enum: none | adjacent | significant | core
    scope_band,                        # enum: individual | squad | team | cross_team | org | company
    metric_band,                       # enum: none | small | medium | large | flagship
    allowed_surfaces[],                # enum: header_proof | summary_safe | key_achievement |
                                       #       core_competency | experience_only |
                                       #       regional_optional | recruiter_private | do_not_use
    confidence: ConfidenceDoc
  },
  evidence_provenance {
    source_fragment_refs {             # map fragment_id -> {role_markdown_path, start_char, end_char}
      ...
    },
    normalization_events[],            # how the sidecar was derived / updated
    last_reviewed_at,
    last_reviewed_by                   # "manual" | "backfill" | "llm_suggested_then_reviewed"
  },
  unresolved_fields[]                  # names of fields that are null with reason
}
```

All numeric scope fields may be `null` — absence is explicitly legal and
must not be fabricated by a downstream consumer. Every band uses an
ordered enum so 4.3.5 grading can rank by ordinal position.

### 9.2 `ProjectMetadata` (per-project sidecar)

```text
ProjectMetadata {
  project_id,
  schema_version,
  project_type,                        # enum: product | platform | internal_tool | research | oss
  industry_context[],
  domain_context[],
  stage,                               # enum: poc | pilot | ga | scaled | deprecated
  ownership {
    role_in_project,                   # enum: contributor | tech_lead | architect | owner | co_owner
    associated_role_ids[]              # RoleData.role_id values
  },
  architecture {
    delivery_model,                    # enum as in RoleMetadata.platform_architecture
    named_subsystems[],                # credibility-marker refs
    data_stores[],                     # neutral taxonomy (refs)
    integration_surface[]
  },
  reliability {
    slo_owned,                         # bool
    incident_playbook_authored,        # bool
    on_call_ownership                  # enum as above
  },
  business_impact {
    revenue_adjacent,
    cost_adjacent,
    reliability_adjacent,
    compliance_adjacent
  },
  ai_relevance {                       # same shape as RoleMetadata.ai_relevance
    ...
  },
  achievements_referenced[] {          # cross-links to role achievements
    role_id,
    achievement_id
  },
  skills_ref,                          # path to existing *_skills.json
  credibility_markers[],
  evidence_provenance { ... },
  unresolved_fields[]
}
```

### 9.3 New taxonomies (under `data/master-cv/taxonomies/`)

All taxonomies share a common frame:

```text
Taxonomy {
  version,
  taxonomy_id,                         # stable enum label
  description,
  entries[] {
    id,                                # stable slug
    display_name,
    synonyms[],
    parents[],                         # id refs to allow hierarchy
    canonical_evidence_shape,          # what evidence must look like to cite this
    confidence_default: ConfidenceDoc
  }
}
```

- **`identity_taxonomy.json`** — identity tags the header blueprint and
  pattern selector lean on. Entries: `operator`, `architect`, `builder`,
  `leader`, `transformation`, `platform`, `execution`,
  `ai_practitioner`, `ai_system_owner`, `rag_practitioner`,
  `agent_systems_owner`, `sre_operator`, `incident_leader`,
  `cost_optimizer`, `scale_scaler`, `zero_to_one`, `one_to_n`,
  `b2b_operator`, `b2c_operator`. Same slugs drive
  `RoleMetadata.identity.identity_tags`.
- **`leadership_taxonomy.json`** — leadership signals: `ic_tech_lead`,
  `em_first_line`, `em_multi_team`, `senior_em`, `director_of_engineering`,
  `head_of_engineering`, `vp_engineering`, `c_level`, `mentor`,
  `coach_program_owner`, `hiring_manager`, `bar_raiser`,
  `cross_functional_partner`, `board_observer`. Each carries required
  `RoleMetadata.seniority.*` shape for citation.
- **`industry_taxonomy.json`** — industry slugs aligned with existing
  `classification.primary_role_category` domain sets: `media`, `adtech`,
  `martech`, `fintech`, `b2b_saas`, `b2c_saas`, `enterprise_ai`,
  `industrial`, `automotive`, `manufacturing`, `healthcare`, `public_sector`,
  `telco`, `ecommerce`, `gaming`, etc. Each has `sub_industries[]`.
- **`domain_taxonomy.json`** — domain slugs (not industry):
  `search`, `recsys`, `rag`, `conversational_ai`, `personalization`,
  `forecasting`, `pricing`, `fraud`, `risk`, `security_ops`, `data_ops`,
  `ml_ops`, `observability`, `content_moderation`, `ad_serving`, etc.
- **`operating_model_taxonomy.json`** — `agile_squad`, `shape_up`,
  `kanban`, `platform_team`, `spotify_tribes`, `scrumban`,
  `stream_aligned`, etc.
- **`credibility_marker_taxonomy.json`** — **named** systems,
  frameworks, stacks, and deployments as named refs. Each marker
  captures `display_name`, `category`, `scale_band`,
  `canonical_evidence_shape`, so a later claim "owned X" must have an
  achievement-level evidence reference to X. Examples:
  `commander4`, `lantern`, `hybrid_search_platform`,
  `multi_provider_llm_fallback`, `incident_playbook_pagerduty`,
  `data_lakehouse_v2`, etc. Only candidate-proven markers are entered.
  This is the single source of truth for which "named system" strings a
  CV may mention.

### 9.4 Extensions to `role_metadata.json`

Today the file carries `candidate_profile` plus `roles[]` with
`primary_competencies`, `keywords`, `achievement_themes`, etc. 4.3.1
keeps that shape verbatim and adds:

```text
{
  schema_version: "1",
  master_cv_checksum,                  # derived at load time, not stored authoritatively
  candidate_facts_ref: "candidate_facts.yml",
  identity_summary {
    primary_identity_tags[],           # identity_taxonomy ids
    tone_profile { ... }               # same enum as RoleMetadata.identity.tone_profile
  },
  acceptable_titles {                  # global allowlist, feeds 4.3.2 header blueprint
    exact[],
    closest_truthful[],
    functional_label[]
  },
  not_identity[],                      # identity tags never to claim — e.g. "designer",
                                       # "data_scientist_statistics_pure", etc.
  differentiators[],                   # refs to credibility markers
  global_credibility_markers[]         # candidate-wide markers (e.g. "10y_engineering",
                                       # "multi_industry") with evidence refs
}
```

### 9.5 `candidate_facts.yml` (new)

Flat, explicit, candidate-owned facts (no LLM authorship):

```text
{
  name,
  contact { email, phone, linkedin, github, website },
  location_primary,
  work_authorization[] {               # explicit hiring-friction facts
    region_code,
    countries[],
    authorization_type,                # citizen | permanent_resident | work_permit |
                                       # visa_required | sponsorship_required
    visa_status,
    confidence,
    disclosure_scope                   # public | limited | private
  },
  eligible_countries[],
  visa_status,
  remote_posture,
  disclosure_scope,
  personal_metadata {
    nationality,
    date_of_birth,
    driving_licenses[],
    confidence,
    disclosure_scope
  },
  display_policy {
    default_variant,                   # ats_safe | recruiter_rich | regional_enriched
    public_contact_fields[],
    public_personal_fields[],
    recruiter_only_fields[],
    region_overrides[] {
      region_code,
      default_variant,
      allowed_public_fields[],
      forbidden_public_fields[],
      preferred_header_fields[],
      rationale
    }
  },
  languages[],                         # {code, proficiency}
  education[] { degree, institution, year, confidence },
  certifications[] { name, issuer, year, ref_url?, confidence },
  public_talks[] { title, venue, year, ref_url? },
  publications[] { title, venue, year, ref_url? },
  awards[] { name, issuer, year, ref_url? },
  schema_version,
  last_reviewed_at,
  last_reviewed_by
}
```

All fields are marked `confidence: ConfidenceDoc` and can be
`unresolved`. Any field marked `unresolved` is never used as a CV claim
unless a later candidate-facing interactive flow confirms it.

### 9.6 `ConfidenceDoc`

Shared shape (identical to 4.2 conventions):

```text
ConfidenceDoc {
  score,                               # 0.0 - 1.0
  band,                                # low | medium | high | unresolved
  basis                                # <= 240 chars, free text rationale
}
```

Downstream consumption rule: no 4.3 stage may emit a claim whose basis
carries `confidence.band == unresolved`. Claims with `low` are permitted
only in the most conservative framings and must be deterministically
softened by `truth_constrained_emphasis_rules`.

### 9.7 Candidate display policy and editorial surface contract

The eval corpus and current regional guidance require a strict separation
between:

- facts that are true in the candidate store,
- facts that are safe for the default ATS/public CV,
- facts that are safe only in region-specific variants,
- and facts that should stay recruiter-private or application-form-only.

4.3.1 therefore owns two additional policy surfaces:

1. `candidate_facts.display_policy`
   - stores the public/recruiter/private decision once;
   - is the single source of truth for nationality, date of birth, visa
     status, relocation, driving-license, and language disclosure;
   - downstream stages may not "just decide" to expose those fields because a
     market commonly expects them.
2. `RoleMetadata.achievements[].allowed_surfaces` plus
   `RoleMetadata.soft_hard_skills.skill_surface_authorization`
   - determine which claims are safe for header, summary, key achievements,
     competencies, detailed experience, or only region-specific surfaces;
   - are the hard stop against unsupported competency inflation and
     over-eager header proof.

This separation is not optional. It is the only reliable way to support:

- ATS-safe global outputs,
- recruiter-rich variants,
- GCC/UAE/KSA enriched variants,
- and conservative EEA/UK/global outputs

from one truthful store.

### 9.8 Manual review workflow (normative)

4.3.1 is manual truth-architecture work first, backfill second.

The required order is:

1. Review `candidate_facts.yml`
   - contact, location, languages, work authorization, sensitive personal
     metadata, and `display_policy`.
2. Review global `role_metadata.json`
   - identity tags, acceptable titles, not-identity tags, differentiators,
     global credibility markers.
3. Review every role markdown file and author its sidecar
   - scope, seniority, stakeholder exposure, AI relevance, skill evidence,
     achievement surfaces.
4. Review every project markdown file and author its sidecar
   - ownership, architecture, reliability, AI relevance, cross-links.
5. Review taxonomies
   - only candidate-proven entries may be added.
6. Run deterministic validation and freeze the checksum boundary.

The detailed manual method now lives in
`reports/4.3-manual-master-cv-review-methodology.md`.

Backfill tooling may pre-populate only obvious fields. It must not author
title envelopes, display policy, competency-surface authorization, or
achievement-surface authorization without manual review.

### 9.9 Granular implementation checklist (normative)

The following checklist defines how to execute a manual `4.3.1` pass in
practice. It is intentionally granular so the operator can work artifact
by artifact without collapsing evidence capture, disclosure policy, and
editorial authorization into one vague editing step.

#### 9.9.1 Preparation and operating posture

- [ ] Re-read the objective, anti-hallucination policy, and invariants for
  `4.3.1` before changing any master-CV artifact.
- [ ] Confirm that this pass is truth-authoring and authorization work,
  not downstream CV drafting or prose beautification.
- [ ] Confirm the source surfaces allowed to write candidate truth:
  - approved role markdown in `data/master-cv/roles/`
  - approved project markdown in `data/master-cv/projects/`
  - current global `role_metadata.json`
  - approved candidate-side source material already recognized by the
    master-CV corpus
- [ ] Confirm that evaluator outputs, benchmark notes, plan wording, and
  internet research may inform judgment but must not be written back as
  canonical candidate fact unless separately verified and approved.
- [ ] Start a temporary unresolved-facts log for ambiguities, missing
  metrics, unclear ownership, and disclosure questions.
- [ ] Confirm the downstream render/disclosure modes that this blueprint
  must support:
  - `ats_safe`
  - `recruiter_rich`
  - `regional_enriched`
- [ ] Decide the review order and start with the highest-leverage items
  first. Recommended order:
  - `candidate_facts.yml`
  - global `role_metadata.json`
  - `01_seven_one_entertainment`
  - `02_samdock_daypaio`
  - flagship projects such as `commander4` and `lantern`

#### 9.9.2 Candidate facts file

- [ ] Create or update `candidate_facts.yml`.
- [ ] Record only globally true candidate facts; do not mix in role-level
  interpretations.
- [ ] Review contact and location data.
- [ ] Review language data and attach explicit proficiency / confidence
  labels where needed.
- [ ] Review work authorization, visa, sponsorship, relocation, and remote
  posture only when factually known.
- [ ] Review sensitive personal metadata only when there is a clear factual
  basis and a likely downstream need.
- [ ] Define or confirm `display_policy` coverage for:
  - default behavior
  - `ats_safe`
  - `recruiter_rich`
  - `regional_enriched`
  - any region-specific overrides
- [ ] For each sensitive metadata field, mark whether it is:
  - never disclose
  - disclose only on regional variants
  - disclose only on explicit request
  - safe for global default
- [ ] Confirm that nationality, date of birth, visa status, or similar
  fields are not treated as always-on header content merely because they
  exist in storage.
- [ ] Leave unknown or unresolved metadata blank / unresolved rather than
  inferring likely answers.

#### 9.9.3 Global identity and title contract

- [ ] Review and update global `role_metadata.json`.
- [ ] Define `primary_identity_tags`.
- [ ] Define `acceptable_titles.exact`.
- [ ] Define `acceptable_titles.closest_truthful`.
- [ ] Define `acceptable_titles.functional_label`.
- [ ] Define `not_identity` labels that must not become the default
  candidate framing.
- [ ] Define global differentiators that downstream stages may safely use.
- [ ] Confirm that executive, founder, or head-of-function framings are
  only present when explicitly justified by evidence.
- [ ] Confirm that downstream title selection is constrained to the
  candidate-side allowlist established here.
- [ ] Record unresolved title ambiguity explicitly rather than widening the
  identity envelope.

#### 9.9.4 Role-by-role review loop

- [ ] Create or update a sidecar for each role under review.
- [ ] Re-read the full role markdown before classifying it.
- [ ] Extract only facts supported by approved source surfaces.
- [ ] Populate role-level fields for:
  - scope / scale
  - seniority band
  - stakeholder exposure
  - operating model
  - business impact
  - AI relevance
  - credibility markers
  - provenance
- [ ] Decide which persona lanes the role legitimately strengthens:
  - architect
  - staff / principal
  - tech lead / player-coach
  - applied AI / AI engineering
  - head-adjacent / org-shaping
- [ ] Confirm that one strong project is not inflating the scope or
  seniority of the full role unless the full role evidence supports that
  move.
- [ ] Record unresolved scope, team size, budget, or impact claims
  explicitly.

#### 9.9.5 Role achievement classification

- [ ] Create a structured achievement entry for each important role-level
  achievement.
- [ ] Map each achievement to supported proof categories.
- [ ] Map each achievement to one or more experience dimensions.
- [ ] Classify metric confidence:
  - exact metric proven
  - directional metric only
  - impact evident but unquantified
  - no metric allowed
- [ ] Classify scope / complexity conservatively.
- [ ] Classify AI relevance conservatively.
- [ ] Mark stakeholder / leadership exposure only when explicitly
  supported.
- [ ] Assign `allowed_surfaces[]` for each achievement, evaluating at
  minimum:
  - `header_proof`
  - `summary_safe`
  - `key_achievement`
  - `core_competency`
  - `experience_only`
  - `regional_optional`
  - `recruiter_private`
  - `do_not_use`
- [ ] Confirm that `header_proof` and `summary_safe` are reserved for
  high-confidence, high-signal evidence only.
- [ ] Confirm that true achievements may remain `experience_only`.
- [ ] Do not promote weakly evidenced achievements into stronger surfaces
  just to make the profile look richer.

#### 9.9.6 Role prose tightening after classification

- [ ] Only after the sidecar is materially complete, review the role
  markdown wording.
- [ ] Reorder bullets so the strongest, most relevant, and best-supported
  evidence appears first.
- [ ] Tighten vague or inflated wording so it matches the structured truth.
- [ ] Preserve useful narrative context needed by downstream mapping.
- [ ] Remove or soften claims that the structured sidecar does not support.
- [ ] Do not expand prose merely to create more downstream "material".
- [ ] Keep the markdown readable for humans; the sidecar carries the richer
  machine-readable authorization.

#### 9.9.7 Project-by-project review loop

- [ ] Create or update a sidecar for each important project.
- [ ] Start with projects that provide the strongest differentiation for
  likely target roles.
- [ ] Re-read each project markdown in full before classifying it.
- [ ] Populate fields for:
  - project description
  - ownership level
  - systems / architecture relevance
  - delivery model
  - business / user impact
  - AI relevance
  - credibility markers
  - provenance
- [ ] Link each project to the roles it strengthens.
- [ ] Confirm whether the project is suitable for header proof, summary
  proof, or experience-only support.
- [ ] Tighten project prose only after classification is complete.
- [ ] Mark unresolved architecture, impact, or production-readiness claims
  explicitly rather than inferring them.

#### 9.9.8 Skills and competency authorization

- [ ] Review `soft_hard_skills` only after the main role/project evidence
  base has been classified.
- [ ] For each skill, verify that concrete role or project evidence exists.
- [ ] Add or update `skill_surface_authorization`.
- [ ] Confirm whether the skill is safe for:
  - `core_competencies`
  - `summary`
  - `experience_only`
  - `restricted`
- [ ] Remove or downgrade skills that are true but too weakly evidenced
  for prominent surfaces.
- [ ] Do not let ATS keyword coverage override evidence quality.
- [ ] Prefer a narrower but defensible competency surface over a broader
  speculative one.

#### 9.9.9 Taxonomy curation

- [ ] Review the taxonomies introduced by `4.3.1`.
- [ ] Ensure every taxonomy value used in sidecars is defined and
  documented.
- [ ] Remove duplicate, ad hoc, or non-reusable labels.
- [ ] Keep taxonomy granularity high enough for differentiation but stable
  enough for future reuse.
- [ ] Confirm that evaluator-only concepts are not leaking into canonical
  candidate taxonomies unless intentionally promoted and defined.

#### 9.9.10 Disclosure and regional policy validation

- [ ] Review whether each stored metadata item has an explicit disclosure
  rule.
- [ ] Confirm that ATS-safe output can be rendered without relying on
  sensitive or region-specific metadata.
- [ ] Confirm that regional enrichment can add lawful or customary metadata
  without changing candidate truth.
- [ ] Confirm that recruiter-rich output may expose more detail only when
  permitted by `display_policy`.
- [ ] Confirm that downstream header logic will consume metadata through
  policy, not by raw field presence alone.

#### 9.9.11 Review completion and freeze criteria

- [ ] Confirm that high-leverage roles have materially complete sidecars.
- [ ] Confirm that flagship projects have materially complete sidecars.
- [ ] Confirm that unresolved facts remain explicit and are not hidden in
  prose.
- [ ] Confirm that title authorization, competency authorization, and
  disclosure policy are coherent with each other.
- [ ] Run deterministic validation / dry-run tooling for schemas and
  invariants.
- [ ] Review validation failures manually; do not “fix” them by inserting
  guesses.
- [ ] Freeze the checksum boundary only when the master data is stable
  enough for deterministic downstream consumption.
- [ ] Record the snapshot/version information required for traceability.

#### 9.9.12 Red flags and failure conditions

- [ ] Stop and correct the pass if any metric was invented, widened, or
  implicitly upgraded.
- [ ] Stop and correct the pass if any title climbed above the truthful
  identity envelope.
- [ ] Stop and correct the pass if any competency was authorized without
  concrete supporting evidence.
- [ ] Stop and correct the pass if any sensitive metadata became
  default-visible without explicit display policy.
- [ ] Stop and correct the pass if evaluator language or draft copy was
  written back as canonical candidate truth.
- [ ] Stop and correct the pass if a sidecar encodes interpretation without
  provenance.

#### 9.9.13 Definition of done for `4.3.1`

- [ ] `candidate_facts.yml` exists and has explicit display-policy
  coverage.
- [ ] Global `role_metadata.json` defines the candidate identity and title
  envelope.
- [ ] High-leverage roles have sidecars with structured evidence,
  provenance, and surface authorization.
- [ ] High-leverage projects have sidecars with structured evidence,
  provenance, and surface authorization.
- [ ] Skills are authorized by evidence rather than by keyword aspiration.
- [ ] Taxonomies are coherent and reusable.
- [ ] Validation and invariants pass.
- [ ] A checksum-bounded master-CV snapshot can be handed to `4.3.2+`
  without requiring those stages to reinterpret raw prose as truth.

## 10. Cross-Artifact Invariants

- Every `credibility_markers[]` ref in `RoleMetadata` /
  `ProjectMetadata` must be an id present in
  `credibility_marker_taxonomy.json`.
- Every `identity_tags[]` ref must be an id present in
  `identity_taxonomy.json`.
- Every `industries[]`, `domains[]` ref must resolve in the respective
  taxonomies.
- Every `RoleMetadata.achievements[].achievement_id` must resolve to an
  achievement present in the role's markdown (confirmed at load-time).
- Every `RoleMetadata.achievements[].variants[].variant_id` must resolve
  to a variant present in the enhanced role file (confirmed at
  load-time via `VariantParser`).
- `acceptable_titles.exact[]` must align with
  `role_skills_taxonomy.json::target_roles[*].display_name` (at least
  every entry in `exact` must appear in at least one target_role
  display_name or synonym set). This keeps 4.3.2 title selection
  coherent with 4.2.
- `tone_profile` keys match the 4.2.4 `tone_profile` enum exactly.
- Every `ai_relevance.intensity_band` on a role must be ≤ the inferred
  global intensity ordinal (a role cannot claim higher intensity than
  is supported by its evidence). Deterministic validator enforces.
- Every `scope.*` band must be consistent with `seniority.managerial_level`
  (e.g. a `managerial_level=ic` role cannot carry
  `direct_reports_total > 0`). Deterministic validator enforces.
- Any metadata surfaced publicly by downstream stages must be permitted by
  `candidate_facts.display_policy` for the active render variant and region.
- Any skill emitted into `core_competencies` must have
  `skill_surface_authorization[skill_id]` containing `core_competency`.
- Any achievement used in header or summary must have `allowed_surfaces[]`
  containing `header_proof` or `summary_safe` respectively.

A failure of any invariant fails the loader with a precise error
message and refuses to serve that role to downstream consumers.

## 11. Fail-Open / Fail-Closed Rules

Fail open:

- A role that is missing some metadata fields but with `unresolved`
  correctly populated is loaded and served; downstream stages treat
  `unresolved` fields as "do not cite".
- A missing sidecar file is loaded as "all-unresolved metadata" with
  the role still usable for legacy Layer 6 V2 single-pass generation
  (no 4.3 lane).

Fail closed:

- A sidecar file that violates any cross-artifact invariant from §10 is
  rejected at load-time and the loader emits a structured error; the
  role is not served to the 4.3 lane until fixed.
- A sidecar file that references a taxonomy id absent from the
  taxonomies is rejected (hard).
- A sidecar file with a `credibility_markers[]` ref lacking any
  `evidence_ref` is rejected (hard).
- A `candidate_facts.yml` that fabricates visa or nationality values
  inconsistent with the configured disclosure_scope is rejected.
- Any sidecar or fact record that exposes sensitive personal metadata without
  an explicit display-policy allowance is rejected.

## 12. Anti-Hallucination Rules

4.3.1 is where hallucination risk is most subtle because metadata
sidecars are easy to silently pad. Rules:

- **No metric invention.** Any `budget_usd_per_year`, `headcount_total`,
  `qps_ceiling_band`, or `metric_band` must have either a direct quote
  in the role markdown or a manual `last_reviewed_by: manual` stamp.
  Otherwise the field is `null` with confidence `unresolved`.
- **No title climbing.** `acceptable_titles.exact[]` is whitelisted,
  period. No future generator may write a title outside that list.
- **No synonym drift.** Skill aliases stay in `role_skills_taxonomy.json`
  exactly as they are today. 4.3.1 does not introduce new aliases.
- **No new AI depth.** `ai_relevance.fine_tuning_exposure` can only
  be `finetuning` or `rlhf` if there is a direct source fragment
  reference. `agentic_systems` can only be true if a named agentic
  system is cited.
- **No invented named systems.** `credibility_marker_taxonomy.json` is
  strictly authored by the candidate; new markers require a manual
  addition, not an LLM suggestion.
- **No evaluator-side bias.** No field in a sidecar may be derived
  from any stakeholder_surface or evaluator lens.
- **No silent metadata exposure.** Nationality, date of birth, visa status,
  relocation, and similar facts may be stored when true, but must remain
  policy-gated. Downstream consumers are forbidden from treating stored truth
  as default-to-public truth.

A post-load deterministic auditor checks these rules and emits a fail-
closed log entry if any claim in a sidecar is not backed by a fragment
reference, a direct quote, or a manual stamp.

## 13. Tracing / Observability Contract

This stage is load-time, not work-item-driven, so its tracing is
loader-local:

- Every `cv_loader.load()` call emits a span `scout.cv.master_cv_load`
  with `langfuse_session_id=job:<level2_object_id>` when called from the
  4.3 lane, or the loader-default session when called from legacy paths.
- Span metadata must include: `master_cv_checksum`,
  `roles_count`, `projects_count`, `unresolved_fields_total`,
  `taxonomy_versions` (map), and a boolean `loader_mode_v2_enabled`.
- Validation failures emit an event
  `scout.cv.master_cv_load.invariant_violation` with `rule_id` and
  `role_id`/`project_id` ref. Never attach full sidecar JSON as
  payload.
- Backfill runs (below) emit a top-level trace
  `scout.cv.master_cv_backfill` with `dry_run`, `input_path`,
  `fields_filled`, `fields_flagged_for_manual`, and
  `fabrications_prevented`. Per-field diffs go to a report file, not
  Langfuse.

## 14. Eval / Benchmark Strategy

### 14.1 Corpus

`data/eval/validation/cv_assembly_4_3_1_master_cv/` holds:

- `snapshots/<date>/` — frozen copies of each role's sidecar, each
  project's sidecar, all six taxonomies, `role_metadata.json`, and
  `candidate_facts.yml` at benchmark time.
- `expected/loader_output.json` — the canonical `CandidateData` shape
  expected after loading the frozen snapshot.
- `expected/invariant_report.json` — the list of invariant checks and
  their expected PASS/FAIL per role.
- `cases/` — targeted edge cases (role with missing sidecar, role with
  invalid taxonomy ref, candidate_facts with unresolved visa, etc.)
  each with `input/` and `expected/` subfolders.

### 14.2 Benchmark harness

`scripts/benchmark_master_cv_4_3_1.py`:

- Points the loader at the frozen snapshot.
- Asserts byte-level equality for the canonical loader output.
- Asserts the invariant report is identical between runs.
- Reports `fields_filled`, `fields_unresolved`, `invariant_violations`
  per role.
- Flags any unexpected difference as a regression.

### 14.3 What to measure

- Loader schema validity (target = 1.00 over all roles and projects).
- Cross-artifact invariant pass rate (target = 1.00).
- Unresolved-field rate (report only; used to prioritize manual review).
- Taxonomy coverage rate — fraction of credibility_markers referenced
  across roles that resolve in the taxonomy (target = 1.00).
- Backfill dry-run idempotence — two consecutive dry-runs must produce
  byte-identical reports.

### 14.4 Regression gates

Rollout is blocked if:

- the frozen corpus loader output changes,
- any invariant regresses,
- the unresolved-field total grows without an intentional schema
  extension landing in the same commit.

## 15. Rollout / Migration / Compatibility

### 15.1 Rollout order

1. Land the six new taxonomies with initial entries derived from
   existing roles, projects, and `role_skills_taxonomy.json`.
2. Land the schema definitions (`RoleMetadata`, `ProjectMetadata`,
   `ConfidenceDoc`) in `src/common/master_cv_store.py` and
   `src/layer6_v2/cv_loader.py`.
3. Run `scripts/backfill-master-cv-blueprint.py --dry-run` to
   generate draft sidecars. The script:
   - extracts unambiguous fields from existing markdown and
     `role_metadata.json` (period, industry, team_size,
     primary_competencies);
   - leaves every ambiguous field `null` with a `pending_manual_review`
     note;
   - never populates metrics, AI depth, or seniority bands from
     heuristics — those require manual review;
   - produces a per-role report `reports/master_cv_backfill_<ts>/
     <role_id>.json` with proposed values.
4. Manual review pass: the candidate (or operator with candidate sign-
   off) fills the remaining fields authoritatively; this is the only
   path by which "hard" facts enter the sidecar.
5. Commit the reviewed sidecars.
6. Flip `MASTER_CV_BLUEPRINT_V2_ENABLED=true` in the loader. Legacy
   callers see a compatibility projection (see §15.3).
7. Benchmark eval corpus and lock the regression gate.

### 15.2 Required flags

| Flag | Default | Post-cutover | Notes |
|------|---------|--------------|-------|
| `MASTER_CV_BLUEPRINT_V2_ENABLED` | false | true | Gates sidecar reading |
| `MASTER_CV_BLUEPRINT_V2_STRICT` | false | true | Fails closed on invariant violations |
| `MASTER_CV_BLUEPRINT_BACKFILL_DRY_RUN` | true | n/a | Tooling-only |
| `MASTER_CV_EVAL_REGRESSION_GATE` | false | true | CI gate |

### 15.3 Compatibility projection for legacy readers

Consumers of the loader that predate 4.3.1 may continue to access
`RoleData` fields (e.g., `primary_competencies`, `hard_skills`,
`soft_skills`). The new `RoleData.metadata: RoleMetadata` is additive.
Field removal from the legacy shape is not permitted in 4.3.1.

### 15.4 Backward compatibility on Mongo

`src/common/master_cv_store.py` is extended with a sidecar-aware
write/read path. Existing stored records are read as "all-unresolved
metadata" until a sidecar is synced. This means 4.3 stages will refuse
to run against a master-CV record that was never upgraded; the legacy
single-pass Layer 6 V2 path is unaffected.

### 15.5 Rollback

Flag-flip disables sidecar reading; loader falls back to the legacy
shape. No data is mutated on rollback.

## 16. Open Questions

- Should sidecars be JSON or YAML? Current recommendation: JSON, for
  deterministic hashing and Mongo round-trip compatibility.
- Should per-role `achievements[]` sidecar metadata be a separate file
  for very role-rich candidates? Out of scope for now — six roles fit
  in one sidecar comfortably.
- Should the `credibility_marker_taxonomy.json` be versioned per
  marker with effective_from/effective_to? Recommendation: add a
  `status` enum (`active | deprecated`) in v1; full versioning deferred.
- Should publication/award evidence live in `candidate_facts.yml` or
  its own sidecar? v1: `candidate_facts.yml`, flatten for now.
- How frequently should the master-CV checksum be recomputed? v1: per
  loader call (cheap). Revisit if load volume grows.

## 17. Primary Source Surfaces

- `data/master-cv/roles/*.md`
- `data/master-cv/projects/*.md` and `*_skills.json`
- `data/master-cv/role_metadata.json`
- `data/master-cv/role_skills_taxonomy.json`
- `src/layer6_v2/cv_loader.py` (`CVLoader`, `CandidateData`, `RoleData`,
  `EnhancedRoleData`, `VariantParser` integration)
- `src/common/master_cv_store.py` (`MasterCVStore`, schema TypedDicts)
- `src/layer6_v2/variant_parser.py`
- `plans/iteration-4.2.4-ideal-candidate-presentation-model.md`
  (`tone_profile`, `acceptable_titles`, `proof_ladder`)
- `plans/iteration-4.2.5-experience-dimension-weights-and-salience.md`
  (canonical dimension enum)
- `plans/iteration-4.2.6-truth-constrained-emphasis-rules.md`
  (canonical rule topics)
- `docs/current/cv-generation-guide.md` (Part 3 & Part 6)
- `reports/4.3-manual-master-cv-review-methodology.md`
- `docs/current/architecture.md`

## 18. Implementation Targets

### Data surfaces

- `data/master-cv/taxonomies/identity_taxonomy.json` (new)
- `data/master-cv/taxonomies/leadership_taxonomy.yml` (new; YAML preferred for human-authored taxonomies; JSON fallback if present)
- `data/master-cv/taxonomies/industry_taxonomy.yml` (new)
- `data/master-cv/taxonomies/domain_taxonomy.yml` (new)
- `data/master-cv/taxonomies/operating_model_taxonomy.yml` (new)
- `data/master-cv/taxonomies/credibility_marker_taxonomy.yml` (new)
- `data/master-cv/candidate_facts.yml` (new; YAML is the canonical authoring source. The transitional JSON mirror that briefly existed during the 4.3 soft JSON->YAML migration has been removed.)
- `data/master-cv/roles/<id>.meta.yml` (new, one per role; YAML preferred)
- `data/master-cv/projects/<id>.meta.yml` (new, one per project; YAML preferred)
- `data/master-cv/role_metadata.{json,yml}` (extended schema; legacy `layer6_v2` runner reads JSON; Codex/eval/manual readers prefer YAML via `src/common/structured_data.py`)

### Code surfaces

- `src/layer6_v2/cv_loader.py`
  - extended `CVLoader._load_from_files()` and `_load_from_mongodb()`
    to read sidecars and taxonomies
  - extended `RoleData` dataclass with `metadata: RoleMetadata`
  - new `CandidateData.projects: List[ProjectData]`
  - new `CandidateData.master_cv_checksum: str`
- `src/common/master_cv_store.py`
  - extended schema TypedDicts with sidecar shapes
  - new `get_master_cv_checksum()` method
- `src/layer6_v2/variant_parser.py`
  - no API changes; the parser already exposes variant ids used by
    `achievements[].variants[].variant_id`
- `src/cv_assembly/models.py` (new package from umbrella 16.2)
  - `RoleMetadata`, `ProjectMetadata`, `ConfidenceDoc` Pydantic models
    (shared with 4.3.2+)

### Scripts / infra

- `infra/scripts/backfill-master-cv-blueprint.py` (new)
- `scripts/benchmark_master_cv_4_3_1.py` (new)
- `infra/scripts/verify-master-cv-blueprint.sh` (new — runs loader,
  asserts invariants, prints summary)

### Evals

- `data/eval/validation/cv_assembly_4_3_1_master_cv/` (new)

### Docs

- `docs/current/architecture.md` — add "Master-CV Blueprint v2" section.
- `docs/current/cv-generation-guide.md` — reference the new taxonomies
  and acceptable-title whitelist.
- `docs/current/missing.md` — log the migration.
