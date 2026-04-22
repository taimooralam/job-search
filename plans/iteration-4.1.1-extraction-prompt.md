# Iteration 4.1.1 Plan: Extraction Prompt

Author: planning pass on 2026-04-20
Parent plans:
- `plans/iteration-4.1-job-blueprint-preenrich-cutover.md`
- `plans/extraction-4.1.1-jd-facts-runner-parity.md`
- `plans/scout-pre-enrichment-skills-plan.md`
- `plans/brainstorming-new-cv-v2.md`

Status: planning only. No code changes in this pass. Focus is the prompt contract for `jd_facts`, not the full rollout implementation.

Plan metadata:
- Target stage: `jd_facts`
- Target builder: `src/preenrich/blueprint_prompts.py::build_p_jd_extract`
- Prompt version target: `v2`
- Schema version target: `extraction_4_1_1_v2`
- Taxonomy source of truth: `data/job_archetypes.yaml`
- Compatibility target: preserve `level-2.extracted_jd` as a no-loss projection
- Artifact target: richer `jd_facts.extraction` payload plus additive metadata not projected into legacy consumer fields

---

## 1. Executive Summary

Iteration 4.1 already states the real problem clearly: `jd_facts` is too thin. The current prompt surface is structurally valid, but it is still a light extraction prompt wrapped around a deterministic collector. That is the wrong quality bar. The pipeline does not need a simpler extraction prompt. It needs a richer one than the legacy runner prompt while preserving the 4.1 architecture rules: schema-first, JSON-only, deterministic-first where appropriate, no `job_hypotheses` leakage, and compatibility with the existing `ExtractedJD` consumer surface.

This plan defines that richer prompt contract.

The design intent is:

1. Keep the current runner-grade required schema intact.
2. Preserve every value already recoverable from the legacy prompt.
3. Add an explicit main rich-contract layer for remote/work model detail, expectations, identities, communication/leadership/delivery dimensions, language requirements, and other high-signal role attributes.
4. Make the prompt comprehensive enough that the LLM is operating as a true job-intelligence extractor, not a thin field collector.
5. Keep compatibility safe by making the new richness additive rather than destructive.

This plan does not argue for a thinner execution path. It explicitly rejects that direction.

### 1.1 Assessment of the current draft

The current draft is directionally correct, but it still leaves several important decisions too implicit.

Strengths:

- it preserves the legacy runner contract instead of proposing a clean break
- it makes richness additive rather than destructive
- it already expands beyond the legacy prompt in the right direction
- it treats the prompt as the primary extraction engine instead of a thin schema filler

Current weaknesses that should be fixed:

- the persona is strong, but still too one-dimensional; it should explicitly combine extractor discipline with skeptical hiring-committee review
- the prompt lacks an explicit extraction workflow, so implementers could still collapse it into a vague “read and fill schema” builder
- the plan does not yet distinguish system-generated execution metadata from model-generated analysis metadata
- the additive layer lacks formal weighting constructs beyond the core `competency_weights`, so nuance around communication, collaboration, and operating style is still underspecified
- the plan does not yet spell out truncation and tail-coverage strategy, which is one of the easiest ways to silently lose value
- the guardrails do not yet sharply separate responsibilities, qualifications, expectations, and identity cues in enough detail
- the prompt contract does not yet define a compact inspectability layer for ambiguity, inferred fields, or confidence

This revision addresses those gaps directly.

---

## 2. Requirements Pulled Forward From Iteration 4.1

The new prompt must satisfy the constraints already defined in the 4.1 cutover plan and the existing 4.1.1 parity plan.

### 2.1 Non-negotiable requirements

- `jd_facts` must become full structured JD intelligence, not a shallow deterministic collector.
- The prompt must be schema-first and JSON-only.
- The prompt must preserve the legacy runner richness surface:
  - `role_category`
  - `seniority_level`
  - `competency_weights`
  - `responsibilities`
  - `qualifications`
  - `nice_to_haves`
  - `technical_skills`
  - `soft_skills`
  - `implied_pain_points`
  - `success_metrics`
  - `top_keywords`
  - `industry_background`
  - `years_experience_required`
  - `education_requirements`
  - `ideal_candidate_profile`
- The prompt must not introduce any dependency on `job_hypotheses`.
- The prompt must remain grounded in the provided JD, structured sections, and deterministic hints only.
- The prompt must be richer than the legacy runner prompt, not merely equivalent to it.

### 2.2 Architectural constraints

- Keep deterministic hints as anchors for fields like title, company, location, URL, salary, and obvious work-model clues.
- Do not let the prompt silently clobber definitive deterministic fields.
- Keep compatibility projection to `level-2.extracted_jd` safe for existing consumers.
- Any new richness must be additive and clearly owned by `jd_facts`, not accidentally overwritten downstream by `classification` or `blueprint_assembly`.

### 2.3 Taxonomy ruling: use `data/job_archetypes.yaml`

Yes. The YAML taxonomy should be used as the source of truth for archetype and role-category labels.

Why this is the correct source of truth:

- it already defines the canonical `primary_role_categories`
- it already defines `ideal_candidate_archetypes`
- it already provides role-category-to-likely-archetype mappings under `maps_from.ideal_candidate_archetypes`
- 4.1 already says taxonomy versioning and classification should derive from this file
- using the same file avoids parallel archetype vocabularies drifting apart between extraction and classification

What this means for extraction:

- `jd_facts` may still emit `role_category` and `ideal_candidate_profile.archetype` for runner parity
- but the allowed labels and their descriptions should be rendered from `data/job_archetypes.yaml`, not hardcoded in a second manual taxonomy block
- `classification` remains the canonical owner of the standalone classification artifact
- extraction uses the same taxonomy as a constrained vocabulary and as a prior for likely archetypes, not as a replacement for JD evidence

Runtime rule:

- `build_p_jd_extract` should receive `taxonomy_context` derived from `data/job_archetypes.yaml`
- the rendered prompt should include:
  - allowed role-category labels
  - allowed archetype labels
  - short descriptions
  - likely role-category -> archetype priors
- the model must not invent labels outside that taxonomy
- JD evidence still wins when choosing among allowed taxonomy options

---

## 3. No-Loss Output Contract

The output contract for the richer prompt has three layers:

1. The required runner-compat baseline.
2. A required main rich-contract layer.
3. A compact analysis metadata layer.

### 3.1 Required baseline: keep the existing richer schema

The richer prompt must continue to emit the existing runner-grade extraction surface expected by `ExtractedJDModel` / `JDFactsExtractionOutput`.

Required keys:

- `title`
- `company`
- `location`
- `remote_policy`
- `role_category`
- `seniority_level`
- `competency_weights`
- `responsibilities`
- `qualifications`
- `nice_to_haves`
- `technical_skills`
- `soft_skills`
- `implied_pain_points`
- `success_metrics`
- `top_keywords`
- `industry_background`
- `years_experience_required`
- `education_requirements`
- `ideal_candidate_profile`
- `salary_range`
- `application_url`

Compatibility aliases that still need to exist in the compat projection:

- `company_name`
- `required_qualifications`
- `key_responsibilities`
- `salary`

### 3.2 Required main rich-contract layer

The richer dimensions should be part of the main extraction contract for the authoritative artifact, not treated as a sidecar only.

The legacy compat projection can remain narrower until downstream consumers are migrated intentionally, but the primary `jd_facts.extraction` contract should include these dimensions as first-class outputs.

Proposed rich-contract shape:

```json
{
  "remote_location_detail": {
    "remote_anywhere": true,
    "remote_regions": ["EU", "UK"],
    "timezone_expectations": ["2-4 hours overlap with US Eastern"],
    "travel_expectation": "occasional travel to Berlin HQ",
    "onsite_expectation": "quarterly onsite",
    "location_constraints": ["must be based in Germany or Netherlands"],
    "relocation_support": "unknown",
    "primary_locations": ["Berlin, Germany"],
    "secondary_locations": [],
    "geo_scope": "single_city|multi_city|country|region|global|not_specified",
    "work_authorization_notes": "EU work authorization preferred"
  },
  "expectations": {
    "explicit_outcomes": ["build platform reliability", "improve team delivery"],
    "delivery_expectations": ["ship roadmap predictably", "own execution cadence"],
    "leadership_expectations": ["hire and mentor engineers"],
    "communication_expectations": ["present updates to executives"],
    "collaboration_expectations": ["work closely with product and design"],
    "first_90_day_expectations": ["stabilize current roadmap", "assess org gaps"]
  },
  "identity_signals": {
    "primary_identity": "builder-operator engineering leader",
    "alternate_identities": ["player-coach", "systems-minded people leader"],
    "identity_evidence": ["build from scratch", "lead by example"],
    "career_stage_signals": ["startup to scale", "cross-functional leadership"]
  },
  "skill_dimension_profile": {
    "communication_skills": ["executive communication", "cross-functional alignment"],
    "leadership_skills": ["team building", "mentoring", "performance management"],
    "delivery_skills": ["roadmap execution", "prioritization", "delivery discipline"],
    "architecture_skills": ["system design", "scalability planning"],
    "process_skills": ["engineering excellence", "quality culture"],
    "stakeholder_skills": ["product partnership", "customer empathy"]
  },
  "team_context": {
    "team_size": "8 engineers",
    "reporting_to": "VP Engineering",
    "org_scope": "backend platform team",
    "management_scope": "direct manager of ICs"
  },
  "weighting_profiles": {
    "expectation_weights": {
      "delivery": 30,
      "communication": 20,
      "leadership": 25,
      "collaboration": 15,
      "strategic_scope": 10
    },
    "operating_style_weights": {
      "autonomy": 25,
      "ambiguity": 20,
      "pace": 20,
      "process_rigor": 20,
      "stakeholder_exposure": 15
    }
  },
  "operating_signals": [
    "fast-paced startup",
    "high ownership",
    "ambiguity tolerance",
    "data-informed decision making"
  ],
  "ambiguity_signals": [
    "scope suggests first senior platform hire",
    "remote policy is partially specified"
  ],
  "language_requirements": {
    "required_languages": ["English"],
    "preferred_languages": ["German"],
    "fluency_expectations": ["professional fluency in English"],
    "language_notes": "German is a plus for local stakeholder coordination"
  },
  "company_description": "Verbose grounded summary of company information present in the JD but not captured elsewhere.",
  "role_description": "Verbose grounded summary of role information present in the JD but not captured elsewhere.",
  "residual_context": "Any additional grounded information from the JD that remains materially useful but does not fit other fields."
}
```

Main rich-contract fields:

- `remote_location_detail`
- `expectations`
- `identity_signals`
- `skill_dimension_profile`
- `team_context`
- `weighting_profiles`
- `operating_signals`
- `ambiguity_signals`
- `language_requirements`
- `company_description`
- `role_description`
- `residual_context`

Rules for the main rich-contract layer:

- each nested block may be `null` or omitted if evidence is insufficient
- `application_url` must be extracted from the job description when present in the JD text
- `salary_range` must be extracted from the job description when present in the JD text
- `language_requirements` must capture explicit required and preferred language expectations when present
- `company_description` must stay grounded in company information present in the JD
- `role_description` must stay grounded in role information present in the JD
- `residual_context` is for grounded overflow context, not speculation
- `weighting_profiles.expectation_weights` must sum to 100 when present
- `weighting_profiles.operating_style_weights` must sum to 100 when present
- weighting blocks express relative emphasis, not candidate quality or certainty
- `remote_anywhere=true` requires genuinely broad geography with no meaningful region restriction
- if the role is remote but region-limited, preserve that in `remote_regions` and/or `location_constraints` instead of using `remote_anywhere=true`

### 3.3 Additive analysis metadata

The richer prompt should also support a compact optional top-level object named `analysis_metadata`.

This is not narrative reasoning. It is a compact inspectability layer for downstream debugging and review.

Proposed shape:

```json
{
  "analysis_metadata": {
    "overall_confidence": "high|medium|low",
    "field_confidence": {
      "role_category": "high",
      "seniority_level": "medium",
      "ideal_candidate_profile": "medium",
      "rich_contract": "low"
    },
    "inferred_fields": [
      "implied_pain_points",
      "success_metrics",
      "identity_signals"
    ],
    "ambiguities": [
      "role title suggests staff-plus IC, but duties include light people management"
    ],
    "source_coverage": {
      "used_structured_sections": true,
      "used_raw_excerpt": true,
      "tail_coverage": "full|partial|unknown",
      "truncation_risk": "none|low|medium|high"
    },
    "quality_checks": {
      "competency_weights_sum_100": true,
      "weighting_profile_sums_valid": true,
      "top_keywords_ranked": true,
      "duplicate_list_items_removed": true
    }
  }
}
```

Rules for metadata:

- `analysis_metadata` is artifact-only and should not be projected into `level-2.extracted_jd`
- it must remain compact; no long rationales and no hidden chain-of-thought dumping
- `field_confidence` should focus on high-risk interpretive fields, not every single primitive
- `ambiguities` should capture real tensions, not generic caveats

### 3.4 Why the main rich-contract layer stays separate from compat projection

The nested shape is deliberate.

- It preserves the stable `ExtractedJD` contract already consumed across CV, outreach, review, and job-detail surfaces.
- It creates room for materially richer extraction without forcing every current consumer to migrate immediately.
- It allows 4.1.1 prompt improvement to ship independently of a broad repo-wide schema migration.
- It gives the prompt room to express nuance, weighting, and inspectability without destabilizing the legacy projection.

If later consumers need these extra dimensions directly, they can be promoted selectively after separate ownership and migration decisions.

---

## 4. Richness Principles For The New Prompt

The new prompt must be optimized for information preservation and role intelligence, not brevity.

### 4.1 Extraction principles

- Preserve explicit information first.
- Use strong inference only when the JD clearly supports it.
- Prefer `null` or empty lists over invention.
- Preserve exact terminology that is ATS-relevant.
- Separate responsibilities from qualifications from nice-to-haves.
- Extract both what the role does and what the role expects from the candidate.
- Treat the role as an operating system, not a keyword bag.

### 4.2 Role-intelligence principles

- Identify the real scope of the role, not just the literal title.
- Distinguish people leadership from technical leadership.
- Distinguish delivery emphasis from architecture emphasis from process emphasis.
- Identify the candidate identity the company is implicitly searching for.
- Surface communication expectations, leadership expectations, and delivery expectations explicitly.
- Capture remote and location nuance beyond the coarse `remote_policy` enum.

### 4.3 Prompt-quality principles

- The prompt should carry domain guidance, category guidance, extraction rules, and guardrails directly.
- The prompt should not be a minimal “fill the schema” instruction.
- The prompt should include explicit anti-loss instructions:
  - do not drop tail-end sections
  - do not compress multiple concepts into one generic bullet
  - do not reduce distinct leadership / communication / delivery signals into a generic soft-skills list
- The prompt should instruct the model to recover value from:
  - structured sections first
  - raw JD text second
  - deterministic hints third as anchors

### 4.4 Clarity and anti-collapse rules

The prompt should explicitly prevent category collapse.

- do not mix responsibilities into qualifications
- do not mix expectations into responsibilities when the text is clearly about how success or collaboration is measured
- do not treat all communication signals as generic soft skills
- do not treat all leadership signals as people-management signals; distinguish technical leadership from formal management
- do not flatten remote nuance into a single enum when the JD provides richer constraints
- do not turn candidate identity into motivational language; keep it as a grounded hiring profile
- do not treat every repeated buzzword as a top keyword; prioritize ATS usefulness and semantic distinctness

### 4.5 Input packaging and tail-preservation rules

The plan should be explicit that prompt quality depends on input packaging, not just wording.

- if the JD is long, do not send only the first N characters
- preserve tail sections where compensation, work model, travel, authorization, or benefits often appear
- package structured sections in semantic buckets before raw excerpt text
- when truncation is unavoidable, prefer:
  - section-aware extraction first
  - then head window
  - then tail window
- the prompt should always know whether truncation risk exists, and `analysis_metadata.source_coverage.truncation_risk` should reflect that

---

## 5. Proposed Prompt Contract

The prompt should be split into:

- a comprehensive system prompt
- a structured user prompt template

The builder can still render this into one Codex-facing string at runtime, but the content should be designed as two conceptual parts.

### 5.1 Proposed system prompt

```text
You are a principal job-intelligence analyst and skeptical hiring-committee evaluator specializing in engineering, platform, data, AI, product-engineering, and technology leadership roles.

Your task is to extract the fullest possible structured operating profile of a job description for downstream CV tailoring, screening analysis, research, and application strategy.

You are not a summarizer.
You are not a generic recruiter assistant.
You are a high-recall, high-precision extractor.
You are also the last reviewer before the extraction is accepted into a production artifact.

Your priorities, in order:
1. Preserve all explicit information that matters for screening, tailoring, and candidate fit.
2. Recover strong implied signals when the JD clearly supports them.
3. Keep taxonomy decisions internally consistent.
4. Return only valid JSON matching the required schema.
5. Prefer null or [] over guessed content.

EXTRACTION WORKFLOW
1. Anchor explicit identity and logistics first: title, company, location, remote/work model, compensation, application URL.
2. Separate the JD into responsibilities, qualifications, and nice-to-haves without mixing them.
3. Classify role category and seniority using the whole role, not just the literal title.
4. Assign competency weights based on real scope and expectations.
5. Extract ATS-critical skills and keywords while preserving role-specific terminology.
6. Synthesize implied pain points, success metrics, and ideal candidate identity only after the explicit extraction is complete.
7. Populate extended optional dimensions only when they are supportable from the JD.
8. Run a final consistency pass before output: no duplicates, no missing required fields, valid weight totals, and no category collapse.

SOURCE PRIORITY
- First use structured sections when provided.
- Then use the raw JD excerpt to recover missing context and tail-end details.
- Use deterministic hints as anchors for definitive fields, not as a substitute for reading the JD.
- Never use outside knowledge about the company or role.

TAXONOMY SOURCE OF TRUTH
- Use the supplied taxonomy context derived from `data/job_archetypes.yaml` as the canonical source for:
  - allowed role-category labels
  - allowed ideal-candidate archetype labels
  - short taxonomy descriptions
  - likely role-category -> archetype priors
- Do not invent labels outside the supplied taxonomy.
- Treat taxonomy mappings as priors, not overrides; the JD text remains the deciding evidence.

NO-LOSS RULE
- Do not drop information just because it appears redundant.
- If multiple sections express materially different requirements, preserve both in the most appropriate fields.
- If the JD contains explicit remote/location restrictions, preserve them in the main rich-contract remote/location fields.
- If the JD contains delivery, communication, leadership, or stakeholder expectations, preserve them in dedicated main rich-contract dimensions instead of collapsing them into generic soft skills.
- If the JD is truncated or incomplete, do not overclaim that a field is absent; reflect uncertainty in analysis metadata where appropriate.
- If the JD includes language requirements, preserve them explicitly.
- If the JD includes grounded company or role context that does not fit cleanly elsewhere, preserve it in `company_description`, `role_description`, or `residual_context`.

ROLE CLASSIFICATION
Classify the role into exactly one role category from the supplied taxonomy context.
Use the taxonomy descriptions, but decide from JD evidence across the whole role, not title keywords alone.

SENIORITY CALIBRATION
Choose exactly one:
- senior
- staff
- principal
- director
- vp
- c_level

COMPETENCY WEIGHTS
Return integer weights for:
- delivery
- process
- architecture
- leadership

The weights must sum to exactly 100.

Interpretation:
- delivery: roadmap execution, shipping, operational throughput, delivery ownership
- process: quality systems, planning discipline, SDLC rigor, DevOps/process excellence
- architecture: system design, technical strategy, platform scalability, technical depth
- leadership: people management, coaching, hiring, org design, executive leadership

WEIGHTING AND NUANCE RULES
When evidence is sufficient, also return:

- `weighting_profiles.expectation_weights`
  - delivery
  - communication
  - leadership
  - collaboration
  - strategic_scope
- `weighting_profiles.operating_style_weights`
  - autonomy
  - ambiguity
  - pace
  - process_rigor
  - stakeholder_exposure

Each weighting block must sum to exactly 100 when present.
These weights express relative role emphasis, not confidence and not candidate fit quality.
If evidence is insufficient for an entire weighting block, set that block to null rather than guessing.

RESPONSIBILITIES VS QUALIFICATIONS
- responsibilities: what the role will do, own, lead, build, improve, or drive
- qualifications: hard or required candidate requirements
- nice_to_haves: preferred, bonus, or advantageous requirements

EXPECTATIONS
Extract not only duties but expectations.
Examples:
- delivery expectations
- communication expectations
- leadership expectations
- collaboration expectations
- first-90-day expectations
- executive presence expectations

SUCCESS METRICS
Extract explicit or strong implied success conditions.
Examples:
- shipping outcomes
- team growth outcomes
- platform reliability outcomes
- stakeholder satisfaction outcomes
- business impact outcomes

IDEAL CANDIDATE PROFILE
Synthesize who the company is really trying to hire.
This must not be generic.
Return:
- identity_statement
- archetype
- key_traits
- experience_profile
- culture_signals

Candidate archetypes:
Use exactly one archetype from the supplied taxonomy context.
Use the role-category -> likely-archetype mappings as priors only.
The final archetype must be grounded in the JD language and expectations.

MAIN RICH-CONTRACT DIMENSIONS
Populate these as part of the primary extraction contract when supported:

remote_location_detail
- remote_anywhere
- remote_regions
- timezone_expectations
- travel_expectation
- onsite_expectation
- location_constraints
- relocation_support
- primary_locations
- secondary_locations
- geo_scope
- work_authorization_notes

expectations
- explicit_outcomes
- delivery_expectations
- leadership_expectations
- communication_expectations
- collaboration_expectations
- first_90_day_expectations

identity_signals
- primary_identity
- alternate_identities
- identity_evidence
- career_stage_signals

skill_dimension_profile
- communication_skills
- leadership_skills
- delivery_skills
- architecture_skills
- process_skills
- stakeholder_skills

team_context
- team_size
- reporting_to
- org_scope
- management_scope

weighting_profiles
- expectation_weights
- operating_style_weights

language_requirements
- required_languages
- preferred_languages
- fluency_expectations
- language_notes

operating_signals
- work-style and environment signals such as pace, autonomy, ambiguity, data orientation, customer focus

ambiguity_signals
- only when ambiguity or tension is strongly present in the JD

company_description
- grounded company information present in the JD but not captured elsewhere

role_description
- grounded role information present in the JD but not captured elsewhere

residual_context
- grounded overflow information from the JD that remains useful downstream

ANALYSIS METADATA
Also return compact `analysis_metadata` when supported:
- overall_confidence
- field_confidence for high-risk interpretive fields
- inferred_fields
- ambiguities
- source_coverage
- quality_checks

This metadata must be compact and inspection-oriented.
Do not output full reasoning, hidden scratch work, or essay-like justifications.

KEYWORD EXTRACTION
Extract 10-20 ATS keywords in priority order.
Prioritize:
1. core technical skills and tools
2. exact role-title variants
3. domain or platform terminology
4. execution / leadership terms when role-relevant
5. methodologies or operating-model terms

QUALITY BAR
- Preserve high-signal phrases.
- Do not collapse distinct requirements into vague labels.
- Do not turn explicit requirements into abstract summaries unless the original requirement is also preserved elsewhere.
- Do not omit important signals that appear late in the JD.
- Do not infer candidate identity without grounding it in JD language.

GROUNDING RULES
- Only use the supplied content.
- If evidence is weak, stay conservative.
- If a field is absent, use null or [].
- If the JD is contradictory, choose the best-supported value and preserve the contradiction in `ambiguity_signals` when applicable.
- `remote_anywhere=true` only when the role is truly broadly location-flexible.
- If the JD says remote but restricts geography, timezone, entity, or work authorization, capture that nuance explicitly.
- If communication is expected with executives, customers, or cross-functional leadership, preserve it in dedicated communication/stakeholder signals.
- If leadership is technical influence rather than line management, preserve that distinction.
- If salary or compensation is present in the JD, extract it into `salary_range`.
- If an application URL or apply instruction URL is present in the JD, extract it into `application_url`.
- If language expectations are present in the JD, extract them into `language_requirements`.
- Keep `company_description`, `role_description`, and `residual_context` grounded and non-speculative.

OUTPUT RULES
- Return only valid JSON.
- No prose.
- No markdown fences.
- No explanations.
- Match the schema exactly.
```

### 5.2 Proposed user prompt template

```text
# JOB EXTRACTION REQUEST

Use the structured sections first, then the raw JD excerpt, and use deterministic hints as anchors.

## JOB IDENTITY
- title: {title}
- company: {company}

## TAXONOMY CONTEXT
Source of truth: `data/job_archetypes.yaml`
taxonomy_version: {taxonomy_version}
{taxonomy_context_json}

## DETERMINISTIC HINTS
{deterministic_hints_json}

## STRUCTURED SECTIONS
{structured_sections_json}

## RAW JD EXCERPT
{raw_jd_excerpt}

## REQUIRED OUTPUT JSON SCHEMA
{
  "title": "string",
  "company": "string",
  "location": "string",
  "remote_policy": "fully_remote|hybrid|onsite|not_specified",
  "role_category": "engineering_manager|staff_principal_engineer|director_of_engineering|head_of_engineering|vp_engineering|cto|tech_lead|senior_engineer",
  "seniority_level": "senior|staff|principal|director|vp|c_level",
  "competency_weights": {
    "delivery": 25,
    "process": 25,
    "architecture": 25,
    "leadership": 25
  },
  "responsibilities": ["string"],
  "qualifications": ["string"],
  "nice_to_haves": ["string"],
  "technical_skills": ["string"],
  "soft_skills": ["string"],
  "implied_pain_points": ["string"],
  "success_metrics": ["string"],
  "top_keywords": ["string"],
  "industry_background": "string|null",
  "years_experience_required": 10,
  "education_requirements": "string|null",
  "ideal_candidate_profile": {
    "identity_statement": "string",
    "archetype": "technical_architect|people_leader|execution_driver|strategic_visionary|domain_expert|builder_founder|process_champion|hybrid_technical_leader",
    "key_traits": ["string"],
    "experience_profile": "string",
    "culture_signals": ["string"]
  },
  "salary_range": "string|null",
  "application_url": "string|null",
  "remote_location_detail": {
      "remote_anywhere": true,
      "remote_regions": ["string"],
      "timezone_expectations": ["string"],
      "travel_expectation": "string|null",
      "onsite_expectation": "string|null",
      "location_constraints": ["string"],
      "relocation_support": "string|null",
      "primary_locations": ["string"],
      "secondary_locations": ["string"],
      "geo_scope": "single_city|multi_city|country|region|global|not_specified",
      "work_authorization_notes": "string|null"
  },
  "expectations": {
      "explicit_outcomes": ["string"],
      "delivery_expectations": ["string"],
      "leadership_expectations": ["string"],
      "communication_expectations": ["string"],
      "collaboration_expectations": ["string"],
      "first_90_day_expectations": ["string"]
  },
  "identity_signals": {
      "primary_identity": "string|null",
      "alternate_identities": ["string"],
      "identity_evidence": ["string"],
      "career_stage_signals": ["string"]
  },
  "skill_dimension_profile": {
      "communication_skills": ["string"],
      "leadership_skills": ["string"],
      "delivery_skills": ["string"],
      "architecture_skills": ["string"],
      "process_skills": ["string"],
      "stakeholder_skills": ["string"]
  },
  "team_context": {
      "team_size": "string|null",
      "reporting_to": "string|null",
      "org_scope": "string|null",
      "management_scope": "string|null"
  },
  "weighting_profiles": {
      "expectation_weights": {
        "delivery": 30,
        "communication": 20,
        "leadership": 25,
        "collaboration": 15,
        "strategic_scope": 10
      },
      "operating_style_weights": {
        "autonomy": 25,
        "ambiguity": 20,
        "pace": 20,
        "process_rigor": 20,
        "stakeholder_exposure": 15
      }
  },
  "language_requirements": {
    "required_languages": ["string"],
    "preferred_languages": ["string"],
    "fluency_expectations": ["string"],
    "language_notes": "string|null"
  },
  "operating_signals": ["string"],
  "ambiguity_signals": ["string"],
  "company_description": "string|null",
  "role_description": "string|null",
  "residual_context": "string|null",
  "analysis_metadata": {
    "overall_confidence": "high|medium|low",
    "field_confidence": {
      "role_category": "high|medium|low",
      "seniority_level": "high|medium|low",
      "ideal_candidate_profile": "high|medium|low",
      "rich_contract": "high|medium|low"
    },
    "inferred_fields": ["string"],
    "ambiguities": ["string"],
    "source_coverage": {
      "used_structured_sections": true,
      "used_raw_excerpt": true,
      "tail_coverage": "full|partial|unknown",
      "truncation_risk": "none|low|medium|high"
    },
    "quality_checks": {
      "competency_weights_sum_100": true,
      "weighting_profile_sums_valid": true,
      "top_keywords_ranked": true,
      "duplicate_list_items_removed": true
    }
  }
}

## EXTRACTION RULES
1. Do not omit any required baseline field.
2. Keep the baseline contract richer than the legacy runner output, never thinner.
3. Populate the main rich-contract fields when the JD supports them; otherwise use null/[] conservatively.
4. `application_url` and `salary_range` must be extracted from the JD when present in the JD text.
5. Preserve explicit remote/location nuance.
6. Preserve explicit expectations around communication, leadership, collaboration, and delivery.
7. Keep ATS-critical terminology intact in `top_keywords`, `technical_skills`, and role-relevant lists.
8. If a weighting block is present, its values must sum to 100.
9. Preserve language requirements explicitly when present.
10. Use `company_description`, `role_description`, and `residual_context` for grounded overflow information that does not fit the structured fields.
11. Populate `analysis_metadata` compactly; it is for inspectability, not reasoning dumps.
12. Use empty lists or null rather than inventing unsupported content.

Return only the JSON object.
```

---

## 6. Implementation Direction

This is still a prompt plan, but the intended implementation surface should be clear.

### 6.1 Input packaging and context-budget rules

The implementation should not assume prompt wording alone will recover richness. Context assembly must also become explicit.

- always pass deterministic anchors
- always pass taxonomy context derived from `data/job_archetypes.yaml`
- always pass structured sections when available
- include both head and tail windows when the raw JD must be truncated
- preserve the sections most likely to carry late-appearing value:
  - compensation
  - remote/work model
  - travel
  - authorization
  - benefits
  - application instructions
- prefer semantic section packing over a single flat text blob

### 6.2 Prompt ownership

- `src/preenrich/blueprint_prompts.py::build_p_jd_extract` becomes the canonical runtime builder for this contract.
- The current use of `JD_EXTRACTION_SYSTEM_PROMPT` as a partial baseline is acceptable only if it is expanded to include the additive richness dimensions above.
- the builder should stop hardcoding the archetype vocabulary and instead render it from `data/job_archetypes.yaml`
- Prefer extracting the final system/user prompt text into dedicated prompt files if the builder becomes too large to maintain inline.

### 6.3 Metadata split

The plan should separate two kinds of metadata clearly.

System-generated execution metadata:

- `prompt_version`
- `schema_version`
- `taxonomy_version`
- `input_packaging_version`
- `truncation_applied`
- `used_structured_sections`
- `raw_excerpt_length`

Model-generated analysis metadata:

- `overall_confidence`
- `field_confidence`
- `inferred_fields`
- `ambiguities`
- `source_coverage`
- `quality_checks`

Only the second category belongs in prompt output. The first category should be attached deterministically by stage code.

### 6.4 Schema ownership

- The baseline fields remain owned by `JDFactsExtractionOutput`.
- The main rich-contract fields should be represented as first-class nested schemas rather than one catch-all optional object.
- The compact metadata object should be represented as a separate optional nested schema, for example `ExtractionAnalysisMetadataModel`.
- `level-2.extracted_jd` should continue receiving the stable compat projection only.
- The richer full payload should live in the authoritative `jd_facts` artifact.

### 6.5 Deterministic merge rule

The prompt should not be trusted blindly for every field.

- Deterministic wins on clearly anchored fields:
  - title
  - company
  - application_url when resolver already has a canonical URL
  - salary_range when the deterministic parser extracted an explicit salary
- Prompt output wins on interpretive richness fields:
  - role category
  - seniority
  - competency weights
  - responsibilities
  - qualifications
  - candidate identity
  - implied pain points
  - success metrics
  - extended optional dimensions

### 6.6 Field registry and implementation discipline

Implementation should maintain a field registry or equivalent mapping that defines, for each field:

- owner: deterministic | model | hybrid
- source priority: structured_sections | raw_excerpt | deterministic_hint
- allowed inference level: explicit_only | strong_implication | optional_inference
- projection target: compat | artifact_only | both

The registry should also identify taxonomy-bound fields:

- `role_category`
- `ideal_candidate_profile.archetype`

For taxonomy-bound fields, the registry should point to `data/job_archetypes.yaml` as the canonical vocabulary source.

Without a field registry, the richer prompt is likely to drift over time and lose clarity again.

---

## 7. Prompt Tests Required

The new prompt contract needs stronger tests than the current thin builder.

### 7.1 Prompt-contract tests

- assert JSON-only instructions are present
- assert every required baseline schema key appears in the rendered prompt
- assert the main rich-contract dimensions appear in the rendered prompt
- assert `analysis_metadata` appears in the rendered prompt with compact inspectability semantics
- assert `job_hypotheses` does not appear anywhere in the rendered payload
- assert deterministic hints, structured sections, and raw JD excerpt are all represented in the prompt input
- assert taxonomy context from `data/job_archetypes.yaml` is represented in the prompt input
- assert the prompt includes extraction workflow steps, not just schema instructions
- assert the prompt explicitly requires extraction of `application_url`, `salary_range`, and `language_requirements` from the JD when present
- assert the prompt includes `company_description`, `role_description`, and `residual_context`

### 7.2 Schema tests

- validate that baseline required fields still parse through `JDFactsExtractionOutput`
- validate that the promoted main rich-contract fields parse through the new nested schemas
- validate that compact metadata parses through the new metadata schema
- validate that empty / null optional dimensions are allowed
- validate that weighting blocks sum to 100 when present
- validate that taxonomy-bound fields only emit labels defined in `data/job_archetypes.yaml`
- validate that `remote_anywhere=true` is not used together with contradictory hard location restrictions unless ambiguity is flagged
- validate `language_requirements` shape
- validate `company_description`, `role_description`, and `residual_context` remain strings or null

### 7.3 Real-job evaluation tests

Benchmark against runner-era extraction for representative jobs:

- management-heavy
- staff/principal IC
- head/vp/cto
- hybrid remote
- EU-location-constrained remote
- high-ambiguity startup roles
- roles with rich communication/stakeholder requirements

Acceptance direction:

- no required-field regression
- improved recall for responsibilities, qualifications, and top keywords
- materially improved capture of remote nuance and candidate identity nuance
- materially improved capture of communication / leadership / delivery expectations
- materially improved capture of ambiguity and confidence metadata without bloating the main payload

---

## 8. Acceptance Criteria

This prompt plan is considered implemented only when the runtime prompt achieves the following.

### 8.1 No-loss acceptance

- Every baseline field from the runner-grade schema is still present.
- No current consumer loses a field it reads today.
- The compat projection remains valid for `level-2.extracted_jd`.

### 8.2 Clarity and contract acceptance

- The prompt clearly separates:
  - responsibilities
  - qualifications
  - nice-to-haves
  - expectations
  - identity
  - metadata
- The implementation surface clearly separates:
  - compat projection fields
  - artifact-only richness fields
  - system-generated execution metadata
  - model-generated analysis metadata

### 8.3 Richness acceptance

- The new prompt extracts more nuance than the legacy runner prompt for:
  - remote/work model
  - expectations
  - identities
  - communication skills
  - leadership skills
  - delivery skills
  - stakeholder / operating environment
  - language requirements
  - grounded company context from the JD
  - grounded role context from the JD
- The new prompt expresses additional nuance through weighting blocks where supported by the JD.
- The new prompt does not gain nuance by becoming speculative.

### 8.4 Quality acceptance

- The output is still grounded in the JD.
- The model is not rewarded for verbosity or invention.
- The prompt produces structured, durable, downstream-useful output rather than narrative summaries.
- Metadata remains compact and inspection-oriented rather than verbose.

---

## 9. Recommended File Targets For Follow-On Implementation

- `src/preenrich/blueprint_prompts.py`
- `src/preenrich/blueprint_models.py`
- `src/preenrich/stages/jd_facts.py`
- `tests/unit/preenrich/test_build_p_jd_extract.py`
- `tests/unit/preenrich/test_stage_jd_facts.py`
- `scripts/benchmark_extraction_4_1_1.py`

Optional prompt-file extraction if prompt text becomes too large:

- `prompts/preenrich_jd_extract.system.prompt.md`
- `prompts/preenrich_jd_extract.user.prompt.md`

---

## 10. Final Decision

Iteration 4.1.1 should not keep a minimalist extraction prompt. The right design is:

- preserve the existing runner-grade extraction schema
- add an explicit main rich-contract layer
- keep the prompt comprehensive and domain-aware
- keep the output grounded and JSON-only
- treat the prompt as the main extraction engine, not as a thin add-on to deterministic parsing

That is the prompt direction that matches the 4.1 plan, the parity plan, and the actual quality bar the repo needs.
