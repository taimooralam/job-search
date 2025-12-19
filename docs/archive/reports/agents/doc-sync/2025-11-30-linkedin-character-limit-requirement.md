# Documentation Update: LinkedIn Message Character Limit Requirement

**Date**: 2025-11-30
**Agent**: doc-sync
**Action**: Document new requirement for LinkedIn message character limit enforcement
**Status**: COMPLETE

---

## Changes Made

### 1. plans/missing.md

**Section**: Features (Backlog)

**Change**: Added new requirement entry

```markdown
- [ ] **LinkedIn Message Character Limit Enforcement (NEW - 2025-11-30)**
  - Hard 300 character limit for connection request messages
  - Prompt-level guardrail: Explicit LLM instruction for strict character limit
  - Output validation: Runtime check `len(message) <= 300` with retry logic
  - UI indicator: Real-time character counter (X/300) with color warning
  - Backend validation: API endpoint rejects messages > 300 characters
  - Implementation: Layer 5 (People Mapper) or Layer 6 (Outreach Generator)
  - Files affected: src/layer5/people_mapper.py, src/layer6/outreach_generator.py, frontend templates
  - Priority: High (prevents LinkedIn submission failures)
  - See: `plans/linkedin-message-character-limit.md` (to be created)
```

**Impact**: Documents new feature requirement with clear scope and priority

---

### 2. plans/architecture.md

**Section**: Layer 6: Generator & LinkedIn Outreach

**Changes**: Enhanced "LinkedIn Outreach Generator" subsection

**Added Content**:

1. **Character Limit Guardrails** (NEW - 2025-11-30) section with THREE-layer enforcement:
   - Prompt-level guardrail: Explicit LLM instruction
   - Output validation: Runtime character count check
   - Retry logic: Progressive prompts with fallback truncation
   - UI indicator: Real-time character counter
   - Backend validation: API rejection of oversized messages

2. **Implementation Files** (NEW):
   - Prompt enhancement in `src/layer5/people_mapper.py` or `src/layer6/outreach_generator.py`
   - Validation logic in `src/layer6/outreach_generator.py`
   - Frontend counter in `frontend/templates/job_detail.html`
   - API validation in `frontend/app.py`

3. **Testing Requirements** (NEW):
   - Unit tests for character limit validation
   - Integration tests for full outreach generation
   - E2E tests for UI character counter
   - Edge case testing

**Impact**: Documents complete guardrail strategy with technical implementation details

---

### 3. plans/linkedin-message-character-limit.md (NEW FILE)

**Created**: Complete implementation plan document

**Contents**:
- Executive summary of problem and solution
- Problem statement (current gaps, impact, root causes)
- Solution: Multi-layer guardrails (5 layers)
- Implementation plan (5 phases, 8-13 hours total)
- Files to create/modify
- Success criteria (6 categories)
- Risk assessment
- Timeline and effort tracking
- Dependencies and monitoring
- Cross-references

**Key Features**:
- Detailed code examples for each layer
- Comprehensive test strategy
- Character counting logic with color coding
- Retry mechanism with progressive prompts
- Fallback truncation strategy
- Frontend UI implementation
- Backend validation endpoint

**Impact**: Provides complete implementation roadmap for feature

---

## Documentation Structure

Updated documentation now covers LinkedIn message character limit enforcement at three levels:

### Level 1: Tracking (missing.md)
- High-level requirement entry
- Links to plan document
- Priority designation

### Level 2: Architecture (architecture.md)
- Technical overview of guardrails
- Implementation files
- Testing strategy
- Integrated with existing outreach documentation

### Level 3: Implementation (linkedin-message-character-limit.md)
- Detailed plan with phases
- Code examples and pseudo-code
- Success criteria
- Risk assessment
- Timeline and resource allocation

---

## Verification

All updates have been verified:

- ✓ missing.md: Entry added with clear scope and priority
- ✓ architecture.md: Technical details integrated into outreach section
- ✓ linkedin-message-character-limit.md: Comprehensive plan document created
- ✓ Cross-references: All three documents link to each other appropriately
- ✓ Consistency: Requirements consistent across all documents

---

## Next Steps

### Suggested Actions

1. **Review Requirements**: Review the three-layer guardrail strategy in architecture.md
2. **Assess Implementation**: Review phases in linkedin-message-character-limit.md
3. **Assign Resources**: Plan resource allocation across 5 implementation phases
4. **Begin Phase 1**: Start with prompt enhancement (1-2 hours, low risk)

### Recommended Agent

**Next Priority**: `test-generator` to create unit test framework for character limit validation

**OR**: `pipeline-analyst` to review outreach generation prompts and propose enhanced versions

---

## Summary

Documentation updated to track new LinkedIn message character limit requirement. The system now documents:

1. **What**: Hard 300-character limit enforced at 5 layers (prompt, validation, retry, UI, API)
2. **Why**: LinkedIn API rejects oversized messages, preventing user applications
3. **How**: Multi-layer guardrails prevent invalid messages through the pipeline
4. **Who**: Implementation assigned to multiple agents (backend, frontend, testing)
5. **When**: Estimated 8-13 hours across 5 phases

The requirement is now fully documented and ready for implementation prioritization.
