# LinkedIn Message Character Limit Enforcement Plan

**Created**: 2025-11-30
**Status**: Planning / Ready for Implementation
**Priority**: High (Prevents LinkedIn submission failures)
**Estimated Duration**: 8-12 hours (includes implementation + testing + integration)

---

## Executive Summary

LinkedIn connection request messages have a **strict 300 character limit** enforced by LinkedIn's platform. This plan documents guardrails at multiple layers to ensure generated outreach messages never exceed this limit, preventing submission failures and user frustration.

---

## Problem Statement

### Current Situation

The LinkedIn outreach generator (`src/layer6/outreach_generator.py`) currently:
1. Specifies 300 char requirement in prompt
2. Validates message length post-generation
3. BUT: Does not implement retry logic on validation failure
4. AND: Does not provide user feedback on character count
5. RISK: If LLM generates message > 300 chars, pipeline may fail or produce invalid outreach

### Impact

- LinkedIn API rejects messages exceeding 300 characters
- User's application fails at final step (highest frustration)
- No graceful degradation or retry mechanism
- No transparency to user on message length

### Root Cause

1. Single-layer approach (only prompt instruction)
2. No retry logic if validation fails
3. No UI feedback on character count
4. No backend API-level validation

---

## Solution: Multi-Layer Guardrails

### Layer 1: Prompt-Level Guardrail

**Location**: `src/layer5/people_mapper.py` or `src/layer6/outreach_generator.py`

**Current Prompt**:
```
Generate a LinkedIn connection message...
Keep it under 300 characters...
```

**New Prompt** (Stricter):
```
Generate a LINKEDIN CONNECTION REQUEST MESSAGE that is STRICTLY under 300 characters.

HARD LIMIT: Your message MUST NOT exceed 300 characters. Count carefully.

Format:
- Start with "Hi {FirstName},"
- Reference specific pain point or achievement from their role (1 sentence)
- Show value you can provide (1 sentence)
- End with: "Best. Taimoor Alam"

Example (299 chars):
"Hi Jane, I saw your work on scaling infrastructure at Acme - impressive results.
I've led similar initiatives and would love to discuss opportunities.
Best. Taimoor Alam"

CRITICAL: Do not exceed 300 characters. Verify count before responding.
```

**Implementation**:
```python
# In src/layer6/outreach_generator.py or prompts module

LINKEDIN_CONNECTION_PROMPT = """
Generate a LinkedIn connection request message STRICTLY under 300 characters.

CONSTRAINTS:
- Hard limit: 300 characters (not a preference, absolute limit)
- Must include: Greeting, specific pain point/achievement, value proposition, signature
- Signature: "Best. Taimoor Alam" (required, with period)
- Format: Compact, professional, conversational

Example (299 chars):
"Hi Jane, Impressed by your infrastructure scaling work at Acme - similar to my experience.
Let's connect to discuss opportunities.
Best. Taimoor Alam"

DO NOT EXCEED 300 CHARACTERS.
Character count verification required before submission.
"""
```

### Layer 2: Output Validation with Retry

**Location**: `src/layer6/outreach_generator.py`

**Implementation Pattern**:
```python
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

def generate_linkedin_connection_message(
    state: dict,
    max_retries: int = 2
) -> Tuple[Optional[str], bool]:
    """
    Generate LinkedIn connection message with character limit enforcement.

    Args:
        state: JobState with contact and pain point info
        max_retries: Number of retry attempts (default: 2)

    Returns:
        Tuple of (message, validated) where validated indicates if message is valid
    """
    message = None

    for attempt in range(max_retries + 1):
        # Generate message from LLM
        message = llm_call(LINKEDIN_CONNECTION_PROMPT, state)

        # Validate message length
        if len(message) <= 300:
            logger.info(f"LinkedIn message valid: {len(message)}/300 chars (attempt {attempt + 1})")
            return message, True

        logger.warning(
            f"LinkedIn message too long: {len(message)}/300 chars (attempt {attempt + 1}). "
            f"Excess: {len(message) - 300} chars. Retrying..."
        )

        # Retry with stricter prompt
        if attempt < max_retries:
            state['_retry_attempt'] = attempt + 1
            state['_message_length'] = len(message)
            continue

    # Fallback: Truncate intelligently
    message_truncated = truncate_message_smartly(message, target_length=300)

    logger.warning(
        f"LinkedIn message truncated: {len(message)}->{len(message_truncated)} chars. "
        f"Final validation: {len(message_truncated)}/300"
    )

    return message_truncated, len(message_truncated) <= 300


def truncate_message_smartly(message: str, target_length: int = 300) -> str:
    """
    Intelligently truncate message while preserving meaning and signature.

    Strategy:
    1. Preserve signature: "Best. Taimoor Alam" (23 chars)
    2. Preserve greeting: "Hi {FirstName}," (15+ chars)
    3. Remove less important details (examples, extra context)
    4. Trim at sentence boundaries (no orphaned punctuation)

    Args:
        message: Full message to truncate
        target_length: Target character count

    Returns:
        Truncated message
    """
    SIGNATURE = "Best. Taimoor Alam"

    # Check if message already valid
    if len(message) <= target_length:
        return message

    # Ensure signature is preserved
    if SIGNATURE not in message:
        # Add signature if missing
        message = message.rstrip() + "\n" + SIGNATURE

    # Calculate space available for content (excluding signature and spacing)
    available = target_length - len(SIGNATURE) - 3  # -3 for newline + space padding

    # Find a good cut point (sentence boundary)
    sentences = message.split('. ')
    truncated_sentences = []
    current_length = 0

    for sentence in sentences:
        sentence_with_period = sentence + '. ' if not sentence.endswith('.') else sentence + ' '

        if current_length + len(sentence_with_period) <= available:
            truncated_sentences.append(sentence)
            current_length += len(sentence_with_period)
        else:
            break

    # Reconstruct message
    result = '. '.join(truncated_sentences)
    if result and not result.endswith('.'):
        result += '.'

    # Add signature
    result += '\n' + SIGNATURE

    return result[:target_length]  # Final safety trim
```

### Layer 3: Retry Logic in Outreach Generator

**Enhanced retry mechanism with progressively stricter prompts**:

```python
def generate_linkedin_connection_with_retries(state: dict) -> dict:
    """
    Generate LinkedIn connection message with progressive retry strategy.
    """
    retry_prompts = [
        # Attempt 1: Standard prompt
        {
            "prompt": LINKEDIN_CONNECTION_PROMPT,
            "description": "Standard generation"
        },
        # Attempt 2: Stricter constraint
        {
            "prompt": LINKEDIN_CONNECTION_PROMPT_STRICT,
            "description": "Strict 250-char target (buffer for safety)"
        },
        # Attempt 3: Template-based (minimal content)
        {
            "prompt": LINKEDIN_CONNECTION_PROMPT_TEMPLATE,
            "description": "Template with required fields only"
        }
    ]

    message = None
    for attempt, retry_config in enumerate(retry_prompts):
        logger.info(f"LinkedIn message generation attempt {attempt + 1}: {retry_config['description']}")

        # Generate with current prompt
        message = llm_call(retry_config['prompt'], state)

        # Validate
        if len(message) <= 300:
            logger.info(f"Success on attempt {attempt + 1}: {len(message)}/300 chars")
            return {
                "message": message,
                "validated": True,
                "attempt": attempt + 1,
                "length": len(message),
                "validation_status": "passed"
            }

        logger.warning(
            f"Attempt {attempt + 1} failed: {len(message)} chars (excess: {len(message) - 300})"
        )

    # All retries exhausted: Truncate
    message_truncated = truncate_message_smartly(message)

    return {
        "message": message_truncated,
        "validated": len(message_truncated) <= 300,
        "attempt": len(retry_prompts) + 1,
        "length": len(message_truncated),
        "validation_status": "truncated",
        "original_length": len(message),
        "warning": f"Message truncated from {len(message)} to {len(message_truncated)} characters"
    }
```

### Layer 4: UI Character Counter (Frontend Enhancement)

**Location**: `frontend/templates/job_detail.html` and `frontend/static/js/cv-editor.js`

**Feature**: Real-time character count display with visual feedback

**HTML Structure**:
```html
<div class="linkedin-message-section">
  <label>LinkedIn Connection Message</label>

  <div class="character-counter">
    <span id="char-count">0</span> / 300 characters
    <span id="char-warning" class="warning" style="display: none;">
      Message exceeds limit - will be truncated
    </span>
  </div>

  <textarea
    id="linkedin-message"
    class="message-editor"
    placeholder="LinkedIn connection message will appear here..."
    rows="6">
  </textarea>

  <div class="character-status">
    <span class="status-indicator" id="status-indicator"></span>
    <span id="status-text">Ready</span>
  </div>
</div>

<style>
.character-counter {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 0.875rem;
}

#char-count {
  font-weight: bold;
  color: var(--primary-500);
}

/* Color coding based on character count */
.character-status.green {
  background-color: #d1fae5;
  color: #065f46;
}

.character-status.yellow {
  background-color: #fef3c7;
  color: #92400e;
}

.character-status.red {
  background-color: #fee2e2;
  color: #991b1b;
}

.status-indicator {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-right: 8px;
}

.status-indicator.green { background-color: #10b981; }
.status-indicator.yellow { background-color: #f59e0b; }
.status-indicator.red { background-color: #ef4444; }

#char-warning {
  color: #ef4444;
  font-weight: bold;
  margin-left: auto;
}
</style>
```

**JavaScript Logic**:
```javascript
// In frontend/static/js/cv-editor.js or new linkedin-message.js

class LinkedInMessageCounter {
  constructor() {
    this.maxChars = 300;
    this.warningThreshold = 290;
    this.caution = 250;

    this.init();
  }

  init() {
    const textarea = document.getElementById('linkedin-message');
    if (!textarea) return;

    textarea.addEventListener('input', () => this.updateCounter());
    textarea.addEventListener('paste', () => this.updateCounterDelayed());
  }

  updateCounter() {
    const textarea = document.getElementById('linkedin-message');
    const charCount = document.getElementById('char-count');
    const statusText = document.getElementById('status-text');
    const statusIndicator = document.getElementById('status-indicator');
    const statusDiv = statusText.parentElement;
    const charWarning = document.getElementById('char-warning');

    const length = textarea.value.length;
    charCount.textContent = length;

    // Update color based on length
    statusDiv.className = 'character-status';
    statusIndicator.className = 'status-indicator';

    if (length <= this.caution) {
      // Green: Safe
      statusDiv.classList.add('green');
      statusIndicator.classList.add('green');
      statusText.textContent = `Safe (${this.maxChars - length} chars remaining)`;
      charWarning.style.display = 'none';
    } else if (length <= this.warningThreshold) {
      // Yellow: Caution
      statusDiv.classList.add('yellow');
      statusIndicator.classList.add('yellow');
      statusText.textContent = `Caution (${this.maxChars - length} chars remaining)`;
      charWarning.style.display = 'none';
    } else if (length <= this.maxChars) {
      // Red: Limit approaching
      statusDiv.classList.add('red');
      statusIndicator.classList.add('red');
      statusText.textContent = `At limit (${this.maxChars - length} chars remaining)`;
      charWarning.style.display = 'inline';
      charWarning.textContent = 'Message at limit - may be truncated';
    } else {
      // Red: Over limit
      statusDiv.classList.add('red');
      statusIndicator.classList.add('red');
      statusText.textContent = `Over limit by ${length - this.maxChars} characters`;
      charWarning.style.display = 'inline';
      charWarning.textContent = 'Message WILL be truncated';
    }
  }

  updateCounterDelayed() {
    // Debounce paste events (data arrives after event)
    setTimeout(() => this.updateCounter(), 10);
  }

  getStatus() {
    const textarea = document.getElementById('linkedin-message');
    const length = textarea.value.length;

    return {
      message: textarea.value,
      length: length,
      isValid: length <= this.maxChars,
      remainingChars: Math.max(0, this.maxChars - length)
    };
  }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  new LinkedInMessageCounter();
});
```

### Layer 5: Backend API Validation

**Location**: `frontend/app.py` (LinkedIn message submission endpoint)

**Implementation**:
```python
from flask import request, jsonify

@app.route('/api/jobs/<job_id>/linkedin-message', methods=['POST'])
def submit_linkedin_message(job_id):
    """
    Submit LinkedIn connection message with character limit validation.
    """
    try:
        data = request.get_json()
        message = data.get('message', '').strip()

        # Validate character limit (hard enforcement)
        if len(message) > 300:
            return jsonify({
                "success": False,
                "error": "Message exceeds 300 character limit",
                "length": len(message),
                "limit": 300,
                "excess": len(message) - 300
            }), 400

        # Validate required components
        if "Best. Taimoor Alam" not in message:
            return jsonify({
                "success": False,
                "error": "Message must include signature: 'Best. Taimoor Alam'"
            }), 400

        if "Hi " not in message[:20]:  # Greeting in first 20 chars
            return jsonify({
                "success": False,
                "error": "Message must start with personalized greeting"
            }), 400

        # Persist to MongoDB
        db = get_database()
        result = db['linkedin_messages'].insert_one({
            'job_id': job_id,
            'message': message,
            'length': len(message),
            'timestamp': datetime.datetime.utcnow(),
            'status': 'pending_review'
        })

        return jsonify({
            "success": True,
            "message_id": str(result.inserted_id),
            "length": len(message),
            "status": "pending_review"
        }), 201

    except Exception as e:
        logger.error(f"LinkedIn message submission error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
```

---

## Implementation Plan

### Phase 1: Prompt Enhancement (1-2 hours)

**Task**: Update LLM prompts with strict character limit instruction

**Files**:
- `src/layer5/people_mapper.py` (if outreach generated here)
- `src/layer6/outreach_generator.py` (if outreach generated here)
- Create: `src/layer6/linkedin_prompts.py` (new prompt constants)

**Deliverables**:
- Stricter prompt with "DO NOT EXCEED 300" emphasis
- Three retry-level prompts with progressively stricter constraints
- Character counting verification instruction

**Testing**:
- Manual: Generate 10 messages and verify all <= 300 chars
- Unit tests: Mock LLM with out-of-spec response, verify retry

### Phase 2: Output Validation + Retry Logic (2-3 hours)

**Task**: Implement character validation and retry mechanism

**Files**:
- `src/layer6/outreach_generator.py` (new functions)

**Deliverables**:
- `validate_linkedin_message(message: str) -> bool`
- `truncate_message_smartly(message: str) -> str`
- `generate_linkedin_connection_with_retries(state) -> dict`
- Retry logic with 2 attempt limit
- Fallback truncation strategy

**Testing**:
- Unit tests: 30 test cases
  - Valid messages (280-300 chars)
  - Invalid messages (301+ chars)
  - Truncation at sentence boundaries
  - Signature preservation
  - Edge cases (exactly 300, no signature, etc.)

### Phase 3: Frontend Character Counter (2-3 hours)

**Task**: Add real-time character counter to job detail page

**Files**:
- `frontend/templates/job_detail.html` (new UI section)
- `frontend/static/js/cv-editor.js` or new `linkedin-message.js`
- `frontend/static/css/styles.css` (new styles)

**Deliverables**:
- Character counter display (X/300)
- Color-coded status (green/yellow/red)
- Real-time updates on input
- Warning message when over limit
- Status indicator with accessibility labels

**Testing**:
- Manual: Type in textarea, verify counter updates
- Unit tests: Counter logic for various lengths
- Accessibility: Verify ARIA labels, keyboard navigation

### Phase 4: Backend API Validation (1-2 hours)

**Task**: Add API-level character limit enforcement

**Files**:
- `frontend/app.py` (new endpoint or update existing)

**Deliverables**:
- `POST /api/jobs/<job_id>/linkedin-message` endpoint
- Character limit validation (400 if > 300)
- Signature validation
- Greeting validation
- MongoDB persistence (new `linkedin_messages` collection)

**Testing**:
- Unit tests: Happy path, error paths (too long, missing signature, etc.)
- Integration tests: API + frontend flow

### Phase 5: Integration & Testing (2-3 hours)

**Task**: Wire all layers together and test end-to-end

**Files**:
- Update `src/layer5/people_mapper.py` (use new generation function)
- Update `src/layer6/outreach_generator.py` (use new validation)
- Update `frontend/templates/job_detail.html` (show counter, submit)

**Deliverables**:
- Full pipeline integration test
- E2E test: Generate message -> Validate -> Display counter -> Submit
- Manual testing checklist
- Documentation update

**Testing**:
- 10+ integration tests covering full flow
- E2E tests with Playwright (if enabled)
- Manual verification on staging environment

---

## Files to Create/Modify

### New Files
- `src/layer6/linkedin_prompts.py` - LinkedIn message prompts
- `tests/unit/test_linkedin_message_character_limit.py` - Unit tests (50+ tests)
- `frontend/static/js/linkedin-message.js` - Character counter logic

### Modified Files
- `src/layer5/people_mapper.py` - Use new prompt and validation
- `src/layer6/outreach_generator.py` - Add validation and retry functions
- `src/layer6/__init__.py` - Export new functions
- `frontend/templates/job_detail.html` - Add character counter UI
- `frontend/static/css/base.css` or tailwind config - Character counter styles
- `frontend/app.py` - Add/update LinkedIn message endpoint
- `plans/architecture.md` - Document guardrails (DONE)
- `plans/missing.md` - Mark requirement as in-progress (DONE)

### No Changes Needed
- `src/common/state.py` - JobState already supports outreach messages
- `src/common/config.py` - No new config needed

---

## Success Criteria

1. **Prompt Level**:
   - LLM instruction explicitly states 300 char hard limit
   - Zero tolerance for exceeding limit

2. **Validation Level**:
   - All generated messages: `len(message) <= 300`
   - 2-attempt retry before truncation
   - Truncation preserves signature and meaning

3. **Retry Level**:
   - Retry mechanism triggered on validation failure
   - Progressive prompts: Standard → Strict → Template
   - Logging of all retry attempts

4. **UI Level**:
   - Character counter displays in real-time
   - Color changes at 250/290/300 thresholds
   - Warning message visible when over limit
   - Status indicator accessible (ARIA labels)

5. **API Level**:
   - Endpoint rejects messages > 300 chars (HTTP 400)
   - Validation includes signature and greeting
   - All validation failures logged

6. **Testing**:
   - 50+ unit tests (all passing)
   - 10+ integration tests (all passing)
   - Manual E2E verification complete
   - Edge cases: Exact 300, no signature, at sentence boundary

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| LLM sometimes ignores constraint | Medium | 2-attempt retry + truncation fallback |
| Truncation removes important info | Medium | Truncate at sentence boundaries, preserve signature |
| UI counter shows wrong value | Low | Unit tests + manual verification |
| API validation too strict | Low | Clear error messages, user can edit and resubmit |
| Performance: Character counting slow | Low | JavaScript is fast, debounce paste events |

---

## Timeline & Effort

| Phase | Duration | Owner |
|-------|----------|-------|
| 1. Prompt Enhancement | 1-2h | pipeline-analyst or test-generator |
| 2. Validation + Retry | 2-3h | pipeline-analyst |
| 3. Frontend Counter | 2-3h | frontend-developer |
| 4. API Validation | 1-2h | frontend-developer |
| 5. Integration + Testing | 2-3h | test-generator |
| **Total** | **8-13 hours** | |

**Recommended Approach**: Parallel work
- Phase 1: One engineer (backend)
- Phases 2, 4: Same backend engineer
- Phase 3: Frontend engineer (parallel)
- Phase 5: Both engineers (final integration)

---

## Dependencies

- Existing Layer 5 (People Mapper) or Layer 6 (Outreach Generator) to call new functions
- LLM provider (Anthropic, OpenAI, etc.) functioning
- No external API changes needed
- No MongoDB schema changes (outreach messages already supported)

---

## Monitoring & Metrics

After implementation, track:

1. **Message Generation Success Rate**:
   - % of messages valid on first attempt
   - % requiring retry
   - % truncated

2. **Character Count Distribution**:
   - Average message length
   - Messages at 250-300 char range
   - Messages truncated

3. **Validation Metrics**:
   - API validation errors (HTTP 400)
   - Failed submissions (missing signature, etc.)
   - User re-submission rate

4. **LinkedIn Delivery Success**:
   - Connection requests sent successfully
   - Message rejection rate (if LinkedIn reports)

---

## See Also

- `plans/architecture.md` - Section: LinkedIn Outreach Generator (updated 2025-11-30)
- `src/layer5/people_mapper.py` - Contact discovery and outreach
- `src/layer6/outreach_generator.py` - Message generation
- `plans/missing.md` - Features (Backlog) section (updated 2025-11-30)
