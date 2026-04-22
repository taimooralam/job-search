# CV System Redesign 2A: AI Architecture Highlights Section

## Context

The current Layer 6 v2 pipeline already injects AI evidence for AI jobs, but it does so as a raw Commander-4 project block inside the final text assembly rather than as a targeted architecture story. The practical result is that AI proof is still concentrated in one project and is not framed in the same recruiter-friendly shape as the rest of the CV.

This feature exists to solve a specific grading and narrative problem:

- The CV reviewer is reading the candidate as "elite platform architect who does some AI work" rather than "engineering leader / software architect with AI platform depth".
- The strongest AI evidence is real and grounded, but it is buried in one project block.
- AI and architect-role JDs should see a short, ATS-safe, high-signal section that surfaces architecture capabilities before the role history starts.

Expected impact:

- Better JD alignment for `ai_architect`, `ai_leadership`, and architecture-heavy `staff_principal_engineer` jobs.
- Better reviewer perception because AI capability is visible before the Seven.One role bullets.
- No incremental LLM cost if the section is selected in post-processing from grounded portfolio data.

## Current Architecture Findings

### Pipeline flow

Live CV generation goes through `CVGeneratorV2.generate()` in [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:455):

1. Phase 1 loads candidate data, role files, and the achievement-grounded whitelist at `455-463`.
2. The AI gate runs immediately after loading at `481-524`.
3. Phase 2 generates per-role bullets at `526-540`.
4. Phase 3 runs QA at `559-573`.
5. Phase 4 stitches role bullets into `StitchedCV` at `595-615`.
6. AI project context is loaded for header generation at `660-672`.
7. Phase 5 generates the header at `674-759`.
8. Final `cv_text` is assembled by `_assemble_cv_text()` at `799-805`, implemented at `1608-1764`.
9. Grading consumes the assembled `cv_text` at `870-881`.
10. `cv_generation_service` persists that same `cv_text` to MongoDB at [src/services/cv_generation_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_generation_service.py:200) and [src/services/cv_generation_service.py](/Users/ala0001t/pers/projects/job-search/src/services/cv_generation_service.py:249).

### Where header ends and experience begins

The seam is explicit inside `_assemble_cv_text()`:

- Summary title at `1676-1678`
- Value proposition / narrative at `1680-1688`
- Header key achievements at `1690-1694`
- Core competencies at `1696-1708`
- Current AI project block at `1710-1726`
- `PROFESSIONAL EXPERIENCE` starts at `1728-1729`

That means there is already a clean insertion point between competencies and experience, but it is hard-coded inside the orchestrator rather than modeled as a reusable section.

### Types and ordering

`StitchedCV` in [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:431) only contains:

- `roles`
- `total_word_count`
- `total_bullet_count`
- `keywords_coverage`
- `deduplication_result`

There is no generic "extra section" or "custom section" concept.

`HeaderOutput` in [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1459) contains profile, skills, education, contact, certifications, and languages. Semantically, it already represents the non-experience part of the CV.

`FinalCV.to_markdown()` exists at [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:2197), but the live path does not use it. The real assembly path is still `_assemble_cv_text()` in the orchestrator.

### Stitcher behavior

`CVStitcher.stitch()` at [src/layer6_v2/stitcher.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/stitcher.py:428) only:

- deduplicates bullets across roles
- builds `StitchedRole`
- returns `StitchedCV`

It does not own header rendering or any custom sections. No insertion point exists there.

### Header grounding detail that affects dedup

The header generator adds AI project bullets to the candidate pool for header key achievements at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:865), but the returned V2 `ProfileOutput` currently sets `highlights_used=[]` at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:1097).

That matters because dedup cannot rely on `profile.highlights_used` today. It must compare against `profile.key_achievements` text and `profile.achievement_sources`.

### Existing AI-specific rendering

The current AI block in `_assemble_cv_text()` at `1710-1726` renders only Commander-4:

- no Lantern evidence
- no dedup against header achievements
- no role-category gating beyond `state["is_ai_job"]`
- no structured selection logic

This block should be replaced, not preserved alongside the new section, otherwise the CV will contain two adjacent AI sections with overlapping claims.

## Architecture Decision

### Recommended approach

Introduce a lightweight reusable section model on `HeaderOutput`, then populate it in the orchestrator after header generation and before final text assembly.

Why this is the best fit:

- The feature belongs to the non-experience part of the CV, not to `StitchedCV`.
- The stitcher should remain role-only; forcing portfolio sections into `StitchedCV` would blur Phase 4 responsibilities.
- The section should be selected deterministically in post-processing, not by LLM.
- The current live seam is already in `_assemble_cv_text()`, so the implementation can be low-risk.

### Concrete design

1. Add a small dataclass in `src/layer6_v2/types.py` near `HeaderOutput`:
   - `SupplementalSection`
   - fields: `title`, `bullets`, `section_type`, `source_ids`

2. Add `supplemental_sections: List[SupplementalSection] = field(default_factory=list)` to `HeaderOutput` in [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1459).

3. Build the AI highlights section in the orchestrator after header generation and before `_assemble_cv_text()` is called:
   - insertion seam: [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:799)

4. Render `header.supplemental_sections` inside `_assemble_cv_text()` after core competencies and before `PROFESSIONAL EXPERIENCE`, replacing the current hard-coded AI project block at `1710-1726`.

### Why not the other options

- New field on `StitchedCV`: wrong ownership. `StitchedCV` is clearly role-centric today.
- Append to header narrative or competencies: makes ATS structure worse and prevents clean ordering.
- LLM-generated section: unnecessary token cost and weaker grounding than deterministic selection.

## Design Decisions

### 1. Insertion point

Use the existing seam in `_assemble_cv_text()`:

- after competencies at [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1696)
- before `PROFESSIONAL EXPERIENCE` at [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1728)

No stitcher restructuring is required.

### 2. Data structure

Use `HeaderOutput.supplemental_sections`, not `StitchedCV`.

This keeps the model aligned with the rendered order: summary -> competencies -> AI highlights -> experience.

### 3. Triggering logic

Replace the current `should_include_ai_section(state)` logic at [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:128) with a role-aware helper:

```python
ALLOWED_AI_HIGHLIGHT_CATEGORIES = {
    "ai_architect",
    "ai_leadership",
    "staff_principal_engineer",
}
```

Render when:

- `extracted_jd["role_category"]` is in the allowed set, and
- either `state["is_ai_job"]` is true, or the role category is already architecture-heavy (`staff_principal_engineer`)

This uses the AI gate output at [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:481), which already normalizes AI roles into `ai_architect` / `ai_leadership`.

### 4. Bullet source

Use a static structured file: `data/master-cv/ai_portfolio.json`.

Reasoning:

- The source material is already verified and stable.
- This avoids another LLM call.
- It supports richer metadata than raw markdown bullets: metrics, tags, role categories, dedup keys, source references.
- It allows mixing Commander-4 and Lantern cleanly.

Keep `commander4.md` and `lantern.md` as the source of truth for authored evidence, but use `ai_portfolio.json` as the section-ready projection.

### 5. Deduplication strategy

Do not depend on `profile.highlights_used`; it is empty in the V2 path today at [src/layer6_v2/header_generator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/header_generator.py:1097).

Dedup should happen in the orchestrator after header generation and before section rendering:

Inputs:

- `header.profile.key_achievements`
- `header.profile.achievement_sources`
- candidate AI portfolio entries

Rules:

1. Normalize header achievement text to lowercase, stripped punctuation.
2. Extract numeric tokens from header achievements, for example `2000`, `42`, `40`, `14`, `5`.
3. For each AI portfolio entry, skip it if:
   - any `dedup_keys` phrase already appears in a header key achievement, or
   - any primary metric appears in a header key achievement together with a matching theme word such as `users`, `plugins`, `spend`, `tests`, `mcp`
4. Keep at most one bullet per architecture tag family unless there is remaining room.

This should live in a new orchestrator helper such as `_select_ai_highlights_section(...)`.

### 6. ATS safety

Use:

- standard bold heading: `**AI & PLATFORM ARCHITECTURE**`
- standard bullet lines: `• ...`
- no tables, columns, badges, or inline source annotations

This matches the rest of `_assemble_cv_text()` and remains ATS-safe because the grader and downstream persistence already operate on plain markdown text.

### 7. Token cost

Selection should happen in deterministic post-processing.

This is better than LLM generation because:

- no extra prompt cost
- easier dedup
- easier testing
- zero hallucination risk beyond the curated source file

### 8. Grading impact

No grader changes are required.

`CVGrader._grade_jd_alignment()` scores the assembled `cv_text` directly and uses role-category keyword matches at [src/layer6_v2/grader.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/grader.py:376). Adding AI architecture terms to `cv_text` should naturally raise:

- role-category match for `ai_architect` / `ai_leadership`
- JD terminology score
- pain-point coverage when the JD mentions platform, evaluation, retrieval, or gateway patterns

## Data File Spec

Create `data/master-cv/ai_portfolio.json` with this exact initial content:

```json
{
  "section_title": "AI & PLATFORM ARCHITECTURE",
  "version": 1,
  "selection_rules": {
    "min_bullets": 3,
    "max_bullets": 4,
    "allowed_role_categories": [
      "ai_architect",
      "ai_leadership",
      "staff_principal_engineer"
    ]
  },
  "highlights": [
    {
      "id": "commander4_hybrid_retrieval",
      "text": "Architected hybrid retrieval for an enterprise AI platform serving 2,000 users, combining BM25 scoring, reciprocal rank fusion, and LLM-as-judge reranking to improve search quality at production scale.",
      "source_file": "data/master-cv/projects/commander4.md",
      "source_lines": [2, 7],
      "source_project": "Commander-4 (Joyia)",
      "skills": [
        "BM25",
        "RRF fusion",
        "LLM-as-Judge",
        "Hybrid Search",
        "RAG Pipeline"
      ],
      "metrics": [
        "2,000 users"
      ],
      "architect_tags": [
        "retrieval_architecture",
        "search_quality",
        "production_scale"
      ],
      "role_categories": [
        "ai_architect",
        "ai_leadership",
        "staff_principal_engineer"
      ],
      "priority": 100,
      "dedup_keys": [
        "2,000 users",
        "hybrid retrieval",
        "llm-as-judge",
        "reranking"
      ]
    },
    {
      "id": "commander4_ingestion_indexing",
      "text": "Designed document-ingestion and RAPTOR indexing architecture for a 2,000-user AI workflow platform, using Confluence/XML parsing, Jira ADF conversion, sentence-boundary chunking, and SHA-256 incremental updates for retrieval-ready knowledge pipelines.",
      "source_file": "data/master-cv/projects/commander4.md",
      "source_lines": [2, 6],
      "source_project": "Commander-4 (Joyia)",
      "skills": [
        "Document Ingestion Pipeline",
        "RAPTOR",
        "Confluence XML parsing",
        "Jira ADF parsing",
        "SHA-256 change detection"
      ],
      "metrics": [
        "2,000 users"
      ],
      "architect_tags": [
        "knowledge_pipeline",
        "indexing_architecture",
        "enterprise_platform"
      ],
      "role_categories": [
        "ai_architect",
        "ai_leadership",
        "staff_principal_engineer"
      ],
      "priority": 95,
      "dedup_keys": [
        "2,000 users",
        "document ingestion",
        "raptor",
        "sha-256"
      ]
    },
    {
      "id": "commander4_eval_guardrails",
      "text": "Built retrieval evaluation and guardrail architecture with MRR/NDCG scoring, per-silo policy enforcement, and two-tier semantic caching, validating behavior through 14 unit tests before production rollout.",
      "source_file": "data/master-cv/projects/commander4.md",
      "source_lines": [8],
      "source_project": "Commander-4 (Joyia)",
      "skills": [
        "Retrieval Evaluation (MRR, NDCG)",
        "Semantic Caching",
        "Guardrail Engineering",
        "Search Quality Optimization"
      ],
      "metrics": [
        "14 unit tests"
      ],
      "architect_tags": [
        "evaluation_architecture",
        "guardrails",
        "quality_assurance"
      ],
      "role_categories": [
        "ai_architect",
        "ai_leadership",
        "staff_principal_engineer"
      ],
      "priority": 90,
      "dedup_keys": [
        "14 unit tests",
        "semantic caching",
        "mrr",
        "ndcg",
        "guardrail"
      ]
    },
    {
      "id": "commander4_structured_outputs",
      "text": "Established structured-output and tool-integration architecture with Zod validation, 5 MCP server tools, and 42 workflow plugins, enforcing per-silo access control across an enterprise AI platform.",
      "source_file": "data/master-cv/projects/commander4.md",
      "source_lines": [2, 9],
      "source_project": "Commander-4 (Joyia)",
      "skills": [
        "Structured Outputs",
        "Zod schema validation",
        "MCP Tool Design",
        "Guardrail Engineering"
      ],
      "metrics": [
        "5 MCP server tools",
        "42 workflow plugins"
      ],
      "architect_tags": [
        "platform_architecture",
        "tooling_architecture",
        "governance"
      ],
      "role_categories": [
        "ai_architect",
        "ai_leadership",
        "staff_principal_engineer"
      ],
      "priority": 92,
      "dedup_keys": [
        "5 mcp server tools",
        "42 workflow plugins",
        "structured output",
        "zod"
      ]
    },
    {
      "id": "lantern_gateway_routing",
      "text": "Architected a multi-provider LLM gateway using LiteLLM routing, model registry, and automatic fallback across OpenAI, Anthropic, and Azure endpoints to harden downstream AI service reliability.",
      "source_file": "data/master-cv/projects/lantern.md",
      "source_lines": [7],
      "source_project": "Lantern",
      "skills": [
        "LLM Gateway Design",
        "Multi-Provider Routing",
        "Provider Fallback Chain",
        "Model Routing"
      ],
      "metrics": [],
      "architect_tags": [
        "gateway_architecture",
        "resilience",
        "platform_reliability"
      ],
      "role_categories": [
        "ai_architect",
        "ai_leadership",
        "staff_principal_engineer"
      ],
      "priority": 80,
      "dedup_keys": [
        "llm gateway",
        "multi-provider",
        "automatic fallback",
        "litellm routing"
      ]
    },
    {
      "id": "lantern_semantic_cache",
      "text": "Built semantic caching and cost-aware routing with Redis and Qdrant vector similarity, reducing redundant LLM API spend by ~40% in testing while improving gateway efficiency.",
      "source_file": "data/master-cv/projects/lantern.md",
      "source_lines": [2, 8],
      "source_project": "Lantern",
      "skills": [
        "Semantic Caching",
        "Cost Optimization",
        "Redis",
        "Qdrant"
      ],
      "metrics": [
        "~40% API spend reduction"
      ],
      "architect_tags": [
        "cost_architecture",
        "gateway_optimization",
        "semantic_caching"
      ],
      "role_categories": [
        "ai_architect",
        "ai_leadership",
        "staff_principal_engineer"
      ],
      "priority": 88,
      "dedup_keys": [
        "~40%",
        "semantic caching",
        "api spend",
        "qdrant"
      ]
    }
  ]
}
```

Notes:

- `commander4.md` source lines are [data/master-cv/projects/commander4.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/commander4.md:2), [data/master-cv/projects/commander4.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/commander4.md:6), [data/master-cv/projects/commander4.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/commander4.md:7), [data/master-cv/projects/commander4.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/commander4.md:8), and [data/master-cv/projects/commander4.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/commander4.md:9).
- `lantern.md` source lines are [data/master-cv/projects/lantern.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/lantern.md:2), [data/master-cv/projects/lantern.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/lantern.md:7), and [data/master-cv/projects/lantern.md](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/lantern.md:8).
- `commander4_skills.json` at [data/master-cv/projects/commander4_skills.json](/Users/ala0001t/pers/projects/job-search/data/master-cv/projects/commander4_skills.json:2) already contains the competency vocabulary needed to validate wording.

## Code Changes

### 1. Replace the current raw AI project block with a structured highlights section

Primary file: `src/layer6_v2/orchestrator.py`

Current relevant lines:

- `128-130`: `should_include_ai_section(state)` only checks `state["is_ai_job"]`
- `133-143`: `_load_ai_project_skills()`
- `147-191`: `_load_ai_project()`
- `481-524`: AI gate and role-category override
- `660-672`: AI project context loaded for header generation
- `1608-1764`: final markdown assembly
- `1710-1726`: current Commander-4 project rendering block

Implementation steps:

1. Keep `_load_ai_project_skills()` unchanged.
2. Keep `_load_ai_project()` for header context only.
3. Add new helpers near the existing AI helpers:
   - `_load_ai_portfolio()`
   - `_should_render_ai_highlights(state, extracted_jd)`
   - `_normalize_dedup_text(text)`
   - `_extract_numeric_tokens(text)`
   - `_select_ai_highlights_section(header, extracted_jd, state)`
4. After Phase 5 header generation and before `_assemble_cv_text()` is called, attach the selected section to `header_output.supplemental_sections`.
5. In `_assemble_cv_text()`, replace lines `1710-1726` with generic rendering of `header.supplemental_sections`.

### 2. Add a reusable section type

Primary file: `src/layer6_v2/types.py`

Current relevant lines:

- [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1459) `HeaderOutput`
- [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1490) `to_dict()`
- [src/layer6_v2/types.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/types.py:1510) `to_markdown()`

Implementation:

- Add `SupplementalSection` immediately before `HeaderOutput`.
- Extend `HeaderOutput` with `supplemental_sections`.
- Serialize it in `HeaderOutput.to_dict()`.
- `HeaderOutput.to_markdown()` can optionally render it after `SKILLS & EXPERTISE`, but live correctness depends on the orchestrator renderer, not `to_markdown()`.

### 3. Dedup against header achievements

Location: new helper in `src/layer6_v2/orchestrator.py`, called between header generation and `_assemble_cv_text()`.

Inputs:

- `header.profile.key_achievements`
- `header.profile.achievement_sources`
- AI portfolio entries from `ai_portfolio.json`

Algorithm:

1. Build `header_texts` from `key_achievements` and `achievement_sources[*].source_bullet`.
2. Lowercase and normalize punctuation.
3. Extract numeric tokens from each header text.
4. For each AI portfolio entry:
   - reject if any `dedup_keys` phrase appears in any header text
   - reject if any entry metric number appears in the same header bullet with a matching noun
5. Sort remaining entries by `priority` descending.
6. Enforce tag diversity:
   - no more than one bullet per dominant `architect_tags[0]`
   - prefer keeping both Commander-4 and Lantern if space allows
7. Return 3-4 bullets.

### 4. Triggering condition

Location: replace the current helper at [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:128).

New rule:

- true for `ai_architect`
- true for `ai_leadership`
- true for `staff_principal_engineer`
- false otherwise

This makes the trigger explicit and stable even if `is_ai_job` was inferred earlier by different mechanisms.

### 5. No stitcher change required

`src/layer6_v2/stitcher.py` remains unchanged for this feature because its role is limited to building `StitchedCV.roles` at [src/layer6_v2/stitcher.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/stitcher.py:514).

## Sample Output

Final generated CV should look like this around the insertion seam:

```md
**PROFESSIONAL SUMMARY**

Engineering leader and software architect building AI-enabled platforms, retrieval systems, and developer tooling with strong production grounding.

• Scaled platform adoption across cross-functional engineering environments
• Improved delivery quality through platform and architecture leadership
• ...

**CORE COMPETENCIES**
**Leadership:** Platform Strategy, Technical Leadership, Cross-Functional Delivery
**Technical:** Python, TypeScript, Distributed Systems, LLM Platforms
**Platform:** AWS, Redis, LiteLLM, Observability

**AI & PLATFORM ARCHITECTURE**
• Architected hybrid retrieval for an enterprise AI platform serving 2,000 users, combining BM25 scoring, reciprocal rank fusion, and LLM-as-judge reranking to improve search quality at production scale.
• Built retrieval evaluation and guardrail architecture with MRR/NDCG scoring, per-silo policy enforcement, and two-tier semantic caching, validating behavior through 14 unit tests before production rollout.
• Established structured-output and tool-integration architecture with Zod validation, 5 MCP server tools, and 42 workflow plugins, enforcing per-silo access control across an enterprise AI platform.
• Built semantic caching and cost-aware routing with Redis and Qdrant vector similarity, reducing redundant LLM API spend by ~40% in testing while improving gateway efficiency.

**PROFESSIONAL EXPERIENCE**

**Seven.One Entertainment Group • Head of Software Development** | Munich, DE | 2020–Present
• ...
```

If the header already uses `2,000 users`, then the first bullet should be dropped and the next highest-priority non-duplicate bullet should replace it.

## Test Strategy

### Unit tests to extend

Primary existing test seam: [tests/unit/test_layer6_v2_orchestrator.py](/Users/ala0001t/pers/projects/job-search/tests/unit/test_layer6_v2_orchestrator.py:349)

Add:

1. `test_ai_highlights_section_renders_for_ai_architect`
   - `role_category="ai_architect"`
   - `state["is_ai_job"]=True`
   - assert `**AI & PLATFORM ARCHITECTURE**` appears before `**PROFESSIONAL EXPERIENCE**`

2. `test_ai_highlights_section_renders_for_staff_principal_engineer`
   - `role_category="staff_principal_engineer"`
   - assert section appears even when `state["is_ai_job"]` is false

3. `test_ai_highlights_section_not_rendered_for_non_ai_manager_role`
   - `role_category="engineering_manager"`
   - assert heading does not appear

4. `test_ai_highlights_dedups_against_header_metrics`
   - seed a header key achievement containing `2,000 users`
   - assert the `commander4_hybrid_retrieval` bullet is excluded

5. `test_ai_highlights_caps_at_four_bullets`
   - ensure selector never emits more than 4 bullets

6. `test_ai_highlights_preserve_standard_markdown_structure`
   - assert plain bold heading and `•` bullet lines only

### Type tests

Extend `tests/unit/test_header_generation_v2.py` or add a focused type test to verify `HeaderOutput.to_dict()` includes `supplemental_sections`.

### AI competency regression check

Because `src/layer6_v2/ai_competency_eval.py` currently looks for Commander/Joyia project markers at [src/layer6_v2/ai_competency_eval.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/ai_competency_eval.py:74), run `tests/unit/test_ai_competency_eval.py` after implementation. If future work removes the project-name strings from the CV entirely, this evaluator will need an update. For 2A, the safer path is to keep Commander/Lantern evidence in the bullet text and leave evaluator behavior unchanged.

### Manual verification

Generate at least two CVs:

1. An AI architect JD
   - section appears
   - bullets are 3-4
   - no header duplication

2. A non-AI engineering manager JD
   - section absent

Recommended commands:

```bash
python -m pytest tests/unit/test_layer6_v2_orchestrator.py -k "ai_highlights or CVAssembly"
python -m pytest tests/unit/test_header_generation_v2.py
python -m pytest tests/unit/test_ai_competency_eval.py
```

## Risks And Rollback

### Main risks

1. Duplicate AI evidence if the old Commander-4 block is not removed.
2. False dedup negatives because header V2 does not populate `highlights_used`.
3. Over-triggering on non-AI architect roles if the helper relies only on `is_ai_job`.
4. AI competency evaluator drift if future edits remove recognizable project terms.

### Mitigations

- Replace the current `1710-1726` block rather than appending.
- Dedup against actual rendered header bullet text, not `highlights_used`.
- Gate by normalized role category, not only the boolean AI flag.
- Keep source-file references in `ai_portfolio.json` so bullet provenance remains obvious.

### Rollback plan

Rollback is straightforward:

1. Remove `HeaderOutput.supplemental_sections`.
2. Remove `ai_portfolio.json` loader and selector helpers.
3. Restore the current hard-coded AI project block at [src/layer6_v2/orchestrator.py](/Users/ala0001t/pers/projects/job-search/src/layer6_v2/orchestrator.py:1710).

Because the feature sits entirely in deterministic assembly and type serialization, rollback does not affect role generation, header LLM calls, or persistence.

