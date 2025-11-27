# Agent Documentation Guidelines

## Overview

All specialized agents in the Job Intelligence Pipeline follow a consistent documentation structure to ensure clarity, organization, and easy navigation across agent-specific work.

## Folder Structure

```
job-search/
├── plans/agents/
│   ├── doc-sync/              # Doc synchronization agent plans
│   ├── frontend-developer/    # Frontend implementation plans
│   ├── pipeline-analyst/      # Pipeline analysis plans
│   ├── architecture-debugger/ # Architecture and debugging plans
│   └── README.md              # THIS FILE - guidelines for all agents
│
└── reports/agents/
    ├── doc-sync/              # Doc sync reports and summaries
    ├── frontend-developer/    # Frontend implementation reports
    ├── pipeline-analyst/      # Pipeline analysis reports
    ├── architecture-debugger/ # Debugging and architecture reports
    └── (other agents as needed)
```

## Documentation Types

### Plans (What to do)

**Location**: `plans/agents/{agent-name}/`

Plans document implementation strategies, testing approaches, and architectural decisions before or during work.

**Naming Convention**:
- `{feature}-plan.md` - Implementation plan for a feature
- `{feature}-testing-guide.md` - Testing strategy for a feature
- `{feature}-architecture.md` - Detailed architecture for a feature
- `{component}-requirements.md` - Requirements analysis for a component

**Example**:
```
plans/agents/frontend-developer/
├── cv-editor-plan.md
├── cv-editor-testing-guide.md
└── cv-editor-ux-fixes-plan.md
```

### Reports (What was done)

**Location**: `reports/agents/{agent-name}/`

Reports document implementation results, analysis findings, and work completed with dates and status.

**Naming Convention**:
- `{feature}-report-{date}.md` - Implementation report with results
- `{feature}-summary-{date}.md` - Executive summary of completed work
- `{component}-analysis-{date}.md` - Analysis results from investigation

**Example**:
```
reports/agents/frontend-developer/
├── cv-editor-fix-report-2025-11-27.md
├── cv-editor-ux-fixes-2025-11-27.md
└── implementation-summary-2025-11-27.md
```

## Core Documentation (NOT for agents)

These files remain in `plans/` root and are shared across all agents:

- **`ROADMAP.md`** - High-level project roadmap (never create agent-specific versions)
- **`architecture.md`** - System architecture overview (update when making architectural changes)
- **`missing.md`** - Implementation tracking across all agents (see section below)
- **`next-steps.md`** - Immediate priority action items

**Important**: Do NOT create duplicate versions of these core files. Instead:
- Update them in place when new information becomes available
- Reference agent-specific plans/reports from these core docs
- Use cross-references like "See also: reports/agents/frontend-developer/cv-editor-fix-report-2025-11-27.md"

## missing.md Update Protocol

The `plans/missing.md` file is the central tracking document. All agents should update it when:

### Completing a Feature/Task

```markdown
## Before
### Features (Backlog)
- [ ] CV rich text editor implementation

## After
### Features (Backlog)
- [x] CV rich text editor implementation ✅ **COMPLETED 2025-11-27**
```

### Adding New Gaps Discovered

```markdown
### Remaining Gaps (Non-Blocking)
- [x] CV Display Not Updating Immediately ✅ **IDENTIFIED 2025-11-27**
  - Expected: Changes visible when editor closes
  - Actual: Changes only appear after page reload
  - Status: [See reports/agents/frontend-developer/cv-editor-phase2-issues.md](../../reports/agents/frontend-developer/cv-editor-phase2-issues.md)
```

### Documenting Blockers

```markdown
## Current Blockers

| Issue | Impact | Fix | Assigned To |
|-------|--------|-----|-------------|
| Anthropic credits low | CV generation fails | Add credits or use env flag | [See reports/...] |
```

## Workflow Examples

### Example 1: Frontend Developer Completes CV Editor Phase

1. **Create plan document** in `plans/agents/frontend-developer/`:
   - File: `cv-editor-phase1-plan.md`
   - Content: Implementation strategy, architecture, phases

2. **Work on implementation** (no docs during this phase)

3. **Create report** in `reports/agents/frontend-developer/`:
   - File: `cv-editor-phase1-report-2025-11-26.md`
   - Content: What was built, test results, known issues

4. **Update missing.md**:
   - Mark feature as completed with date
   - Add any discovered issues to "Current Blockers" or "Remaining Gaps"
   - Add reference to the report

### Example 2: Pipeline Analyst Investigates Test Failures

1. **Create analysis plan** in `plans/agents/pipeline-analyst/`:
   - File: `test-failure-investigation-plan.md`
   - Content: Investigation approach, test matrix

2. **Conduct analysis** (run tests, logs, etc.)

3. **Create report** in `reports/agents/pipeline-analyst/`:
   - File: `test-failure-analysis-2025-11-27.md`
   - Content: Root causes found, recommendations, evidence

4. **Update missing.md**:
   - Add findings to "Current Blockers" or remove if issue resolved
   - Reference the analysis report

### Example 3: Doc-Sync Agent Organizing Documentation

1. **Create organization plan** in `plans/agents/doc-sync/`:
   - File: `documentation-reorganization-plan.md`
   - Content: Folder structure, migration strategy

2. **Execute reorganization** (move files, create structure)

3. **Create report** in `reports/agents/doc-sync/`:
   - File: `documentation-sync-report-2025-11-27.md`
   - Content: Files moved, structure created, verification results

4. **Update missing.md**:
   - If any documentation gaps identified, add to "Remaining Gaps"
   - Document the organization change as complete

## File Naming Best Practices

### For Plans
Use descriptive names without dates (plans are timeless):
- `cv-editor-plan.md` (correct)
- `cv-editor-2025-11-26.md` (avoid - doesn't indicate it's a plan)

### For Reports
Always include dates (reports are timestamped):
- `cv-editor-report-2025-11-26.md` (correct)
- `cv-editor-report.md` (incomplete)

### Use Hyphens, Not Underscores
- `cv-editor-plan.md` (correct)
- `cv_editor_plan.md` (avoid)

## Cross-Referencing

When referencing other documents, use relative paths from the root:

```markdown
See also:
- [CV Editor Phase 1 Report](../../reports/agents/frontend-developer/cv-editor-phase1-report-2025-11-26.md)
- [Missing Implementation Gaps](../missing.md)
- [System Architecture](../architecture.md)
```

## Verification Checklist

Before marking work as complete, verify:

- [ ] Plan document created (if complex task)
- [ ] Implementation completed
- [ ] Report document created in `reports/agents/{agent}/`
- [ ] `missing.md` updated with completion or new gaps
- [ ] Files organized in proper folders
- [ ] Cross-references added where needed
- [ ] No files left in project root (except core docs)

## Integration with CLAUDE.md

The agent delegation system in `/CLAUDE.md` references this structure:

| Agent | Plans | Reports | Core Docs |
|-------|-------|---------|-----------|
| doc-sync | `plans/agents/doc-sync/` | `reports/agents/doc-sync/` | Update `missing.md` |
| frontend-developer | `plans/agents/frontend-developer/` | `reports/agents/frontend-developer/` | Update `missing.md` |
| pipeline-analyst | `plans/agents/pipeline-analyst/` | `reports/agents/pipeline-analyst/` | Update `missing.md` |
| architecture-debugger | `plans/agents/architecture-debugger/` | `reports/agents/architecture-debugger/` | Update `architecture.md` |

All agents share responsibility for keeping `plans/missing.md` current.

## FAQ

### Q: Can I create a subdirectory under plans/agents/my-agent/?
**A**: Yes, for complex projects with many related documents. Example:
```
plans/agents/frontend-developer/
├── cv-editor/
│   ├── phase1-plan.md
│   ├── phase2-plan.md
│   └── testing-guide.md
└── README.md
```

### Q: Should I delete old reports?
**A**: No. Archive them if needed, but keep them for historical reference. They document the development journey.

### Q: What if I need to reference a report while creating a plan?
**A**: That's fine. Cross-reference it. Example: "See prior analysis in [reports/agents/pipeline-analyst/test-failure-analysis-2025-11-26.md](...)".

### Q: Can multiple agents work on the same feature?
**A**: Yes. Keep plans/reports separate but ensure `missing.md` reflects the full status. Coordinate through `missing.md` blockers section.

### Q: How often should missing.md be updated?
**A**: After significant progress or completion. At minimum: daily during active development.

---

**Last Updated**: 2025-11-27
**Created by**: doc-sync agent
